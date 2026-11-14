"""Mapa de idoneidad del sitio de aterrizaje dentro de un recorte DEM y recomendación de los mejores puntos.

El pipeline evalúa UN punto; aquí se evalúa una MALLA y se buscan los mejores puntos (p. ej. el borde de Shackleton
frente a su pared interna). Flujo:

1. **Prefiltro duro** (barato, vectorizado): pendiente p90 en la huella (mismo estadístico que ``terrain.slope``: disco de
   ``footprint_radius_m`` sobre la capa ``slp``) ≤ umbral de aterrizaje del perfil de misión, margen al borde del DEM y
   fracción mínima de píxeles válidos. Las paredes no gastan cómputo de horizonte.
2. **Candidatos**: horizonte con parámetros GRUESOS (az 1°, paso radial 10 m, campo lejano LOLA 80 m con paso 80 m) y
   simulación temporal en rejilla gruesa SIN refinamiento de eventos (los cruces se interpolan linealmente). Sol y Tierra
   se calculan con SPICE UNA vez por periodo en el centro de la Luna (``spkpos``, igual que ``spice_engine.body_track``,
   que ya resta un observador fijo): para cada punto solo cambia el vector observador, así que NO hay aproximación
   (verificado en tests contra ``body_track``).
3. **Score**: el de ``site_score.compute_score`` con el perfil de misión elegido (mismas puertas, pesos y umbrales que
   ``pipeline.run_analysis``), métricas de ``metrics.compute_metrics`` sobre ventanas de ``timeline.find_windows``.
4. **TOP-N** con separación mínima (selección voraz: no se amontonan vecinos) ordenado por estado de puertas y score.

**Conectividad = enlace DTE**: ``f_earth`` (capa, ventanas y score) es la fracción de ENLACE posible: Tierra con margen de elevación
(perfil, 0° por defecto) Y alguna estación de la red (``SuitabilityParams.link_network``, DSN por defecto) viendo la Luna. La cobertura de
red es del cielo, no del sitio: se calcula UNA vez para la rejilla y se intersecta con la serie de cada punto (error por usar el centro de la
Luna ≲ 0,28° de elevación, medido en ``tests/test_ground_stations.py``). ``link_network=None`` recupera la Tierra geométrica anterior.
La referencia de ``s_earth`` es la esfera lisa con el mismo margen y SIN red.

Aproximaciones (medidas por ``scripts/precompute_suitability.py --validate``, ver ``fine_check``): horizonte
grueso (az 1°, 20/80 m) y rejilla temporal gruesa sin refinar. El resto (SPICE, fracción de disco, score) es idéntico.
Resultado cacheado por hash (DEM+capas+campo lejano+parámetros+perfil+kernels) en ``data/processed/suitability/``.
Núcleo sin UI; determinista (el orden de ejecución entre procesos no altera nada: cada celda es independiente).

**Ventana de misión** (``SuitabilityParams.window_durations_days``): una misión de lander dura días, no un año, así que
el score anual no sirve para la puerta de noche. Con duraciones configuradas, la MISMA serie simulada (sin resimular)
se corta en ventanas deslizantes de ``duration`` días con inicio cada ``window_step_days`` (``mission_window_metrics``:
sumas acumuladas + máximo de rachas con tabla dispersa, vectorizado) y para cada candidato y fecha de inicio se evalúan
f_sol, f_Tierra, f_E,ref, oscuridad máxima DENTRO de la ventana y el score con sus puertas (G0 = Sol al inicio, G1 y G4 sobre
la ventana; G2 y G3 son del punto; G0 como el pipeline desde MODULE_VERSION 3). Por candidato: mejor fecha de inicio (puertas, -score, D_max, -f_sol) y nº de días de inicio aptos.
Resolución: las rachas valen lo que la rejilla (``step_s``); la ventana es [t_i, t_i + n·dt) sobre muestras enteras.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
import warnings
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import spiceypy as sp

from lsi.analysis import metrics as mt
from lsi.analysis.site_score import KEYS, compute_score, continuity_factor, normalize_weights, score_with_range
from lsi.astronomy import ground_stations as gs
from lsi.astronomy import spice_engine
from lsi.astronomy.coordinates import observer_position_km, stereo_inverse, vector_to_azel
from lsi.contracts import (
    CACHE_ALGORITHM_VERSION, SPICE_ABCORR, SPICE_FRAME, Body, BodyTrack, DemLayer, DemNotFoundError, DemWindow, GateStatus,
    HorizonMode, MissionProfile, ObserverPoint, ScoreInputs, ScoreParams, ScoreProfile, SkySeries,
    TimelineParams, TimelineResult, VisibilityParams, VisibilitySeries,
)
from lsi.data import cache as cache_mod
from lsi.data import catalog, loader
from lsi.simulation.timeline import complement_windows, find_windows, intersect_windows
from lsi.simulation.visibility import body_visibility, disc_fraction, link_fraction
from lsi.terrain import horizon as hz_mod
from lsi.terrain.sampling import pixel_coords, sample_bilinear
from lsi.terrain.slope import slope_map_deg

KIND = "suitability"
MODULE_VERSION = 6            # subir al cambiar el algoritmo (entra en la clave de caché). 5: f_Tierra = ENLACE (red + margen); referencia sin red. 6: s_earth con continuidad absoluta del enlace (hueco máximo y horas por día) y mejor fecha por G7; sentido del enlace
APT_NONE, APT_STEEP, APT_EVAL = 0, 1, 2   # aptitud: sin dato/margen | pendiente > umbral | evaluado
_GATE_RANK = {GateStatus.PASS: 0, GateStatus.NOT_APPLICABLE: 0, GateStatus.NO_DATA: 1, GateStatus.FAIL: 2}
_SUBKEYS = ("sun", "night", "earth", "terrain")
# columnas del vector de resultado por punto (mismo orden que las capas float)
_POINT_FIELDS = ("score", "f_sun", "f_earth", "d_max_h", "longest_sun_h", "unknown_fraction",
                 "s_sun", "s_night", "s_earth", "s_terrain", "gate_rank", "weakest")
FLOAT_LAYERS = _POINT_FIELDS + ("slope_p90",)


@dataclass(frozen=True)
class SuitabilityParams:
    """Parámetros del mapa. Los valores por defecto son los validados (ver ``fine_check``)."""
    step_m: float = 250.0                  # paso de la malla de candidatos
    margin_m: float = 300.0                # margen al borde del DEM (≥ huella + píxel)
    footprint_radius_m: float = 50.0       # huella de aterrizaje (config terrain.footprint_radius_m)
    slope_percentile: float = 90.0
    slope_limit_deg: Optional[float] = None  # None = pendiente de diseño del perfil (o g2_max_slope_deg)
    min_valid_fraction: float = 0.9        # fracción mínima de píxeles de pendiente válidos en la huella
    # horizonte grueso
    az_step_deg: float = 1.0
    radial_step_m: float = 10.0
    far_step_m: float = 80.0               # = píxel del campo lejano LOLA 80 m (el fino usa ½ píxel)
    observer_height_m: float = 2.0
    # simulación temporal gruesa
    start_utc: str = "2026-12-01T00:00:00"
    days: float = 365.0
    step_s: float = 1800.0
    n_slices: Optional[int] = None         # None = visibility.n_slices de la configuración
    # recomendación
    top_n: int = 5
    min_separation_m: float = 1000.0
    rank_by_gates: bool = True             # puertas PASS antes que NO_DATA antes que FAIL; dentro, por score
    # ventana de misión (vacío = solo el mapa anual)
    window_durations_days: tuple = ()      # p. ej. (7, 14, 30)
    window_step_days: float = 1.0          # separación entre fechas de inicio
    window_start_days: Optional[float] = None   # rango de fechas de inicio desde start_utc (None = todo lo que quepa)
    range_pad_steps: float = 1.0           # rango del score = D_max ± este nº de pasos de rejilla (resolución temporal)
    # enlace DTE: la capa/ventana ``f_earth`` pasa a ser la fracción de ENLACE POSIBLE (Tierra con margen ∧ red viendo la Luna)
    link_network: Optional[str] = "DSN"    # None = solo geometría (comportamiento anterior)
    min_earth_elevation_deg: Optional[float] = None   # None = el del perfil de score (0° por defecto)
    link_station_min_elevation_deg: Optional[float] = None   # fuerza la elevación mínima de las estaciones (sensibilidad)
    link_direction: str = "receive"        # sentido del enlace: 'receive' | 'transmit' | 'both' (elevación mínima de las estaciones)


@dataclass(frozen=True)
class RecommendedSite:
    """Un sitio recomendado con su desglose (todo sale de las capas del mapa)."""
    rank: int
    lat_deg: float
    lon_deg_e: float
    x_m: float
    y_m: float
    row: int
    col: int
    score: float
    f_sun: float
    f_earth: float
    d_max_h: float
    longest_sun_h: float
    slope_p90_deg: float
    unknown_fraction: float
    subscores: Mapping[str, float]         # s_sun, s_night, s_earth, s_terrain (∈[0,1])
    weights: Mapping[str, float]           # pesos normalizados del perfil
    gate_status: str                       # PASS | NO_DATA | FAIL (peor puerta)
    weakest_key: str


@dataclass(eq=False)
class SuitabilityMap:
    """Rasters sobre la malla (``layers[nombre][fila, col]``, NaN = no evaluado) y TOP-N."""
    dem_key: str
    profile_id: str
    params: SuitabilityParams
    x_m: np.ndarray                        # (nx,) centros de columna
    y_m: np.ndarray                        # (ny,) centros de fila (decrecientes: fila 0 = norte)
    aptitude: np.ndarray                   # (ny, nx) uint8: APT_*
    layers: dict[str, np.ndarray]          # FLOAT_LAYERS, float32
    top: tuple[RecommendedSite, ...]
    n_grid: int
    n_candidates: int
    seconds: float                         # tiempo del cálculo original
    cache_key: str = ""
    cached: bool = False
    slope_limit_deg: float = float("nan")
    notes: tuple[str, ...] = ()
    windows: dict = field(default_factory=dict)   # {duración_d: WindowMap}

    @property
    def lat_lon(self) -> tuple[np.ndarray, np.ndarray]:
        xx, yy = np.meshgrid(self.x_m, self.y_m)
        return stereo_inverse(xx, yy)


# ----------------------------------------------------------------------------------------------- malla y prefiltro
def build_grid(surf: DemWindow, params: SuitabilityParams) -> tuple[np.ndarray, np.ndarray]:
    """Centros de la malla (x ascendente, y descendente) dentro del DEM con ``margin_m`` de margen; ancla en la esquina NO."""
    h, w = surf.data.shape
    px = surf.pixel_size_m
    x_min, x_max = surf.x0_m + params.margin_m, surf.x0_m + (w - 1) * px - params.margin_m
    y_max, y_min = surf.y0_m - params.margin_m, surf.y0_m - (h - 1) * px + params.margin_m
    xs = x_min + params.step_m * np.arange(int(math.floor((x_max - x_min) / params.step_m + 1e-9)) + 1)
    ys = y_max - params.step_m * np.arange(int(math.floor((y_max - y_min) / params.step_m + 1e-9)) + 1)
    return xs, ys


def slope_limit(params: SuitabilityParams, mission: Optional[MissionProfile], score_params: ScoreParams) -> float:
    """Umbral de aterrizaje: el explícito, o el ``max_landing_slope_deg.value`` del perfil (design), o la puerta G2."""
    if params.slope_limit_deg is not None:
        return float(params.slope_limit_deg)
    t = mission.thresholds.get("max_landing_slope_deg") if mission is not None else None
    return float(t.value) if t is not None and t.value is not None else float(score_params.g2_max_slope_deg)


def footprint_slope_p90(slope_arr: np.ndarray, surf: DemWindow, xs: np.ndarray, ys: np.ndarray,
                        r_m: float, percentile: float) -> tuple[np.ndarray, np.ndarray]:
    """(p90 (ny,nx), fracción de píxeles válidos) del disco de radio r en cada nodo. Mismo disco que
    ``terrain.slope.disk_view`` (centro = píxel más cercano, d ≤ r/px) pero vectorizado sobre todos los nodos.
    ``slope_arr`` = capa slp (o ``slope_map_deg``) en float64 sobre la malla de ``surf``. Sin pixeles válidos → NaN."""
    rp = r_m / surf.pixel_size_m
    n = int(math.ceil(rp))
    dr, dc = np.mgrid[-n:n + 1, -n:n + 1]
    sel = (dr ** 2 + dc ** 2) <= rp ** 2
    dr, dc = dr[sel], dc[sel]
    xx, yy = np.meshgrid(xs, ys)
    col, row = pixel_coords(surf, xx.ravel(), yy.ravel())
    c, r = np.rint(col).astype(np.intp), np.rint(row).astype(np.intp)
    h, w = slope_arr.shape
    fits = (r - n >= 0) & (c - n >= 0) & (r + n < h) & (c + n < w)
    rr = np.clip(r, n, h - 1 - n)[:, None] + dr[None, :]
    cc = np.clip(c, n, w - 1 - n)[:, None] + dc[None, :]
    v = slope_arr[rr, cc]
    ok = np.isfinite(v)
    frac = np.where(fits, ok.mean(axis=1), 0.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # filas todo-NaN → NaN, justo lo que se quiere
        p = np.nanpercentile(v, percentile, axis=1)
    p = np.where(fits & ok.any(axis=1), p, np.nan)
    return p.reshape(xx.shape), frac.reshape(xx.shape)


def prefilter(surf: DemWindow, slope_arr: np.ndarray, xs: np.ndarray, ys: np.ndarray, params: SuitabilityParams,
              limit_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """(aptitud uint8, pendiente p90). APT_NONE: sin dato (suelo del DEM o pendiente) / huella incompleta;
    APT_STEEP: p90 > límite; APT_EVAL: candidato."""
    p90, frac = footprint_slope_p90(slope_arr, surf, xs, ys, params.footprint_radius_m, params.slope_percentile)
    xx, yy = np.meshgrid(xs, ys)
    _, ground_ok = sample_bilinear(surf, xx.ravel(), yy.ravel())
    valid = (frac >= params.min_valid_fraction) & ground_ok.reshape(xx.shape) & np.isfinite(p90)
    apt = np.full(p90.shape, APT_NONE, np.uint8)
    apt[valid] = APT_STEEP
    apt[valid & (p90 <= limit_deg)] = APT_EVAL
    return apt, p90


# ----------------------------------------------------------------------------------------------- efemérides
def time_grid(params: SuitabilityParams) -> np.ndarray:
    """Rejilla ET del periodo (el último instante se añade si no es múltiplo del paso, como el pipeline)."""
    et0 = spice_engine.utc_to_et(params.start_utc)
    et1 = et0 + params.days * 86400.0
    spice_engine.utc_to_et(spice_engine.et_to_utc(et1))   # DateOutOfRangeError si se sale del rango del BPC
    et = spice_engine.et_grid(et0, et1, params.step_s)
    return np.append(et, et1) if et1 - et[-1] > 1e-6 else et


def ephemeris(et: np.ndarray, kernel_dir: Optional[Path] = None) -> dict[str, np.ndarray]:
    """Posición de Sol y Tierra respecto al centro de la Luna en MOON_ME (LT+S), UNA vez por periodo ((T,3), km)."""
    info = spice_engine.load_kernels(kernel_dir) if kernel_dir is not None else spice_engine.load_kernels()
    out = {}
    with spice_engine.SPICE_LOCK:
        for b in (Body.SUN, Body.EARTH):
            pos, _ = sp.spkpos(b.value, et, SPICE_FRAME, SPICE_ABCORR, "MOON")
            out[b.value] = np.asarray(pos, dtype=np.float64)
    out["kernel_hash"] = info.kernel_hash
    return out


def sky_from_ephemeris(eph: Mapping, et: np.ndarray, lat: float, lon: float, h_m: float) -> SkySeries:
    """Az/el/radio angular de Sol y Tierra para un observador: restar el vector observador al de la efeméride.
    Es exactamente lo que hace ``spice_engine.body_track`` (que también llama a spkpos desde el centro de la Luna)."""
    obs = observer_position_km(lat, lon, h_m)
    tr = {}
    for b in (Body.SUN, Body.EARTH):
        az, el, d = vector_to_azel(eph[b.value] - obs, lat, lon)
        tr[b] = BodyTrack(b, az, el, d, spice_engine.angular_radius_deg(d, b))
    return SkySeries(et, float(lat), float(lon), float(h_m), tr[Body.SUN], tr[Body.EARTH], kernel_hash=eph["kernel_hash"])


# ----------------------------------------------------------------------------------------------- evaluación de un punto
_S: dict = {}   # estado del proceso (se fija con _init; en serie lo fija compute_map)


def _init(state: dict) -> None:
    _S.clear()
    _S.update(state)


def _eval_point(x: float, y: float, lat: float, lon: float, slope90: float) -> tuple[np.ndarray, dict]:
    """Horizonte grueso + simulación gruesa + score de un nodo. Devuelve el vector ``_POINT_FIELDS``."""
    S = _S
    hp, vp, tp, et = S["hp"], S["vp"], S["tp"], S["et"]
    obs = ObserverPoint(lat, lon, x, y, hp.observer_height_m, HorizonMode.DEM, dem_key=S["dem_key"])
    hz = hz_mod.compute_horizon(S["surf"], obs, hp, far=S["far"], far_step_m=S["far_step_m"])
    sky = sky_from_ephemeris(S["eph"], et, lat, lon, hp.observer_height_m)
    sun_v, earth_v = body_visibility(sky.sun, hz, vp), body_visibility(sky.earth, hz, vp)
    vis = VisibilitySeries(et, sun_v, earth_v, hz.cache_key)
    t0, t1 = float(et[0]), float(et[-1])
    link, margin = S.get("link_iv"), S.get("margin", 0.0)   # link_iv: intervalos con alguna estación viendo la Luna (None = geometría)
    f_e = earth_v.f if not margin else link_fraction(sky.earth, hz, vp, margin)
    sun = find_windows(et, sun_v.f, vp.sun_f_thr, "sun", f"f_sun > {vp.sun_f_thr:g}")
    earth = find_windows(et, f_e, vp.earth_f_thr, "earth", f"f_earth > {vp.earth_f_thr:g}")
    tl = TimelineResult(et0=t0, et1=t1, params=tp, sun=sun, earth=earth, overlap=intersect_windows(sun, earth),
                        dark=complement_windows(sun), events=(), series=vis)
    m = mt.compute_metrics(tl, sky, hz, vp)
    # f_E,ref: Tierra sobre la esfera lisa (mismo motor y rejilla, §7.1)
    sph = hz_mod.smooth_sphere_result(obs, hp)
    f_ref = disc_fraction(sky.earth.el_deg - margin, sky.earth.az_deg, sky.earth.radius_deg, sph, "lb", vp.n_slices, 0.0)
    ws = find_windows(et, f_ref, vp.earth_f_thr, "earth_ref", "f_earth(H_esfera)")
    ref_iv, earth_iv = mt.intervals(ws), mt.intervals(earth)
    if link is not None:   # enlace = geometría con margen ∧ red (cobertura común: una vez por rejilla); la referencia NO lleva red
        earth_iv = mt.intersection(earth_iv, link)
    f_earth_ref = mt.total_duration(ref_iv, t0, t1) / (t1 - t0)
    f_earth = mt.total_duration(earth_iv, t0, t1) / (t1 - t0)
    e_max = max(m.max_sun_elevation_deg, m.max_earth_elevation_deg)
    unknown = hz_mod.limited_fraction(hz, e_max, float(np.max(sky.sun.radius_deg)))
    inp = ScoreInputs(f_sun=m.solar_fraction, d_max_h=m.max_darkness_s / 3600.0, f_earth=f_earth,
                      f_earth_ref=max(f_earth_ref, 1e-6), slope_p90_deg=slope90, unknown_fraction=unknown,
                      observer_in_dem=True, has_dem=True, d_max_truncated=m.max_darkness_truncated)
    r = compute_score(inp, S["profile"], S["score_params"], S["mission"])
    s = {row.key: row.s for row in r.subscores}
    vec = np.array([r.score, m.solar_fraction, f_earth, inp.d_max_h, m.longest_sun_window_s / 3600.0,
                    unknown, s["sun"], s["night"], s["earth"], s["terrain"], _GATE_RANK[r.status],
                    _SUBKEYS.index(r.weakest_key)], dtype=np.float64)
    wins = {}
    if S.get("wd"):   # ventanas de misión sobre las mismas series (sin resimular)
        thr = vp.earth_f_thr
        sun_m, earth_m, ref_m = sun_v.f > vp.sun_f_thr, f_e > thr, f_ref > thr   # NaN → False, como find_windows
        if link is not None:
            earth_m = earth_m & S["link_grid"]
        for d in S["wd"]:
            wins[d] = mission_window_metrics(sun_m, earth_m, et, d, S["wstep"], series_ref_earth=ref_m,
                                              max_start_days=S["wsd"])
    return vec, wins


def _eval_chunk(chunk: Sequence[tuple]) -> list[tuple]:
    return [_eval_point(*c) for c in chunk]


def _run_points(state: dict, pts: list[tuple], workers: int) -> list[tuple]:
    if workers <= 1 or len(pts) < 2 * workers:
        _init(state)
        return _eval_chunk(pts)
    size = max(1, min(32, len(pts) // (workers * 4)))
    chunks = [pts[i:i + size] for i in range(0, len(pts), size)]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(state,)) as ex:
        return [r for part in ex.map(_eval_chunk, chunks) for r in part]   # map conserva el orden: determinista


# ----------------------------------------------------------------------------------------------- TOP-N
def select_top(score: np.ndarray, gate_rank: np.ndarray, x_m: np.ndarray, y_m: np.ndarray, n: int,
               min_sep_m: float, rank_by_gates: bool = True, ties: Sequence[np.ndarray] = ()) -> list[tuple[int, int]]:
    """(fila, col) de los N mejores nodos separados ≥ ``min_sep_m`` (voraz sobre un orden total determinista:
    puertas, -score, ``ties`` (menor = mejor; el score satura en 100 con f_sol ≥ f1, así que desempatan las
    magnitudes físicas), y, x). NaN = no evaluado."""
    rows, cols = np.nonzero(np.isfinite(score))
    if len(rows) == 0:
        return []
    g = gate_rank[rows, cols] if rank_by_gates else np.zeros(len(rows))
    keys = [x_m[cols], -y_m[rows], *(t[rows, cols] for t in reversed(tuple(ties))), -score[rows, cols], g]
    order = np.lexsort(keys)   # último criterio = primario
    picked: list[tuple[int, int]] = []
    for i in order:
        r, c = int(rows[i]), int(cols[i])
        if all(math.hypot(x_m[c] - x_m[pc], y_m[r] - y_m[pr]) >= min_sep_m for pr, pc in picked):
            picked.append((r, c))
            if len(picked) == n:
                break
    return picked


def _weights(profile: ScoreProfile) -> dict[str, float]:
    t = sum(profile.weights.values())
    return {k: float(profile.weights.get(k, 0.0)) / t for k in _SUBKEYS}


def build_top(m_layers: Mapping[str, np.ndarray], x_m, y_m, profile: ScoreProfile, params: SuitabilityParams) -> tuple[RecommendedSite, ...]:
    ties = (-m_layers["f_sun"], m_layers["d_max_h"], -m_layers["f_earth"], m_layers["slope_p90"])
    picks = select_top(m_layers["score"], m_layers["gate_rank"], x_m, y_m, params.top_n, params.min_separation_m,
                       params.rank_by_gates, ties)
    pts = np.array([(x_m[c], y_m[r]) for r, c in picks]).reshape(-1, 2)
    lat, lon = stereo_inverse(pts[:, 0], pts[:, 1]) if len(picks) else (np.empty(0), np.empty(0))
    w = _weights(profile)
    out = []
    for k, (r, c) in enumerate(picks):
        L = {name: float(arr[r, c]) for name, arr in m_layers.items()}
        out.append(RecommendedSite(
            rank=k + 1, lat_deg=float(lat[k]), lon_deg_e=float(lon[k]), x_m=float(x_m[c]), y_m=float(y_m[r]), row=r, col=c,
            score=L["score"], f_sun=L["f_sun"], f_earth=L["f_earth"], d_max_h=L["d_max_h"], longest_sun_h=L["longest_sun_h"],
            slope_p90_deg=L["slope_p90"], unknown_fraction=L["unknown_fraction"],
            subscores={k2: L[f"s_{k2}"] for k2 in _SUBKEYS}, weights=w,
            gate_status={0: "PASS", 1: "NO_DATA", 2: "FAIL"}[int(L["gate_rank"])], weakest_key=_SUBKEYS[int(L["weakest"])]))
    return tuple(out)


# ----------------------------------------------------------------------------------------------- ventana de misión
@dataclass(frozen=True)
class WindowMetrics:
    """Métricas por fecha de inicio (un elemento por inicio) de ventanas deslizantes de ``duration_days``."""
    duration_days: float
    step_days: float
    start_et: np.ndarray            # (S,) inicio de cada ventana
    f_sun: np.ndarray               # fracción de la ventana con Sol visible
    f_earth: np.ndarray
    f_overlap: np.ndarray           # Sol y Tierra a la vez
    longest_sun_h: np.ndarray       # racha de Sol más larga dentro de la ventana (recortada a ella)
    max_dark_h: np.ndarray          # oscuridad continua máxima dentro de la ventana (recortada a ella)
    f_ref: Optional[np.ndarray] = None   # Tierra sobre esfera lisa (para s_earth), si se pasó ``series_ref_earth``
    sun_start: Optional[np.ndarray] = None   # (S,) bool: Sol visible en la muestra de inicio de la ventana (puerta G0)
    max_gap_h: Optional[np.ndarray] = None   # (S,) hueco máximo SIN Tierra/enlace dentro de la ventana (h, recortado a ella; con enlace = G7)
    longest_earth_h: Optional[np.ndarray] = None   # (S,) racha más larga CON Tierra/enlace dentro de la ventana (h; G6)


def _max_run(mask: np.ndarray, i0: np.ndarray, n: int) -> np.ndarray:
    """Racha True más larga (en muestras) de ``mask[i0 : i0+n]`` para cada ``i0``, recortando las rachas a la ventana.
    Rachas = [s, e) disjuntas y ordenadas: las que tocan la ventana son un rango contiguo [kl, kr); la primera y la
    última se recortan a mano y las de en medio (enteras) se resuelven con una tabla dispersa de máximos por rango."""
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    if len(s) == 0:
        return np.zeros(len(i0))
    j = i0 + n
    kl, kr = np.searchsorted(e, i0, side="right"), np.searchsorted(s, j, side="left")   # solapan: kl ≤ k < kr
    R = len(s)
    clip = lambda k: np.minimum(e[k], j) - np.maximum(s[k], i0)   # noqa: E731
    kf, kz = np.minimum(kl, R - 1), np.clip(kr - 1, 0, R - 1)
    out = np.where(kr > kl, np.maximum(clip(kf), clip(kz)), 0.0)
    lo, hi = kl + 1, kr - 1                                       # enteras: kl+1 ≤ k < kr-1
    ok = hi > lo
    if ok.any():
        length = (e - s).astype(np.float64)
        tab, h = [length], 1                                       # tab[k][i] = max(length[i : i + 2**k])
        while 2 * h <= R:
            tab.append(np.maximum(tab[-1][:-h], tab[-1][h:]))
            h *= 2
        tabm = np.zeros((len(tab), R))
        for k_, row in enumerate(tab):
            tabm[k_, :len(row)] = row
        lo_, hi_ = lo[ok], hi[ok]
        k = np.floor(np.log2(hi_ - lo_)).astype(int)
        inner = np.maximum(tabm[k, lo_], tabm[k, hi_ - (1 << k)])
        out[ok] = np.maximum(out[ok], inner)
    return out


def mission_window_metrics(series_visible_sun, series_visible_earth, times, duration_days: float,
                           step_days: float = 1.0, series_ref_earth=None,
                           max_start_days: Optional[float] = None) -> WindowMetrics:
    """Métricas de TODAS las ventanas de ``duration_days`` con inicio cada ``step_days`` a partir de series booleanas de
    visibilidad ya simuladas (``f > umbral``), sin resimular: fracciones por sumas acumuladas, rachas máximas por
    ``_max_run``. ``times`` (ET s) es una rejilla uniforme; la muestra k representa [t_k, t_k+dt) (la última no cubre
    nada), la ventana toma ``round(duration/dt)`` muestras enteras y solo se generan inicios cuya ventana cabe en la serie
    (y, si se da ``max_start_days``, con inicio < ``max_start_days`` días tras el primer instante: un año de fechas).
    La oscuridad es el complemento del Sol dentro de la ventana (una noche que cruza el borde cuenta solo lo de dentro)."""
    t = np.asarray(times, dtype=np.float64)
    if t.ndim != 1 or len(t) < 2:
        raise ValueError("times debe ser 1-D con ≥ 2 instantes")
    dt = (t[-1] - t[0]) / (len(t) - 1)
    if not dt > 0 or np.max(np.abs(np.diff(t) - dt)) > 1e-6 * dt + 1e-6:
        raise ValueError("times debe ser una rejilla uniforme creciente")
    sun, earth = (np.asarray(a, dtype=bool)[:-1] for a in (series_visible_sun, series_visible_earth))
    if len(sun) != len(t) - 1 or len(earth) != len(sun):
        raise ValueError("las series deben tener la misma longitud que times")
    N, n = len(sun), int(round(duration_days * 86400.0 / dt))
    if not (duration_days > 0 and step_days > 0 and 1 <= n <= N):
        raise ValueError(f"duración {duration_days} d fuera de la serie ({N * dt / 86400.0:g} d) o paso no positivo")
    stride = max(1, int(round(step_days * 86400.0 / dt)))
    i0 = np.arange(0, N - n + 1, stride)
    if max_start_days is not None:
        i0 = i0[i0 * dt < max_start_days * 86400.0 - 1e-6]

    def frac(m):
        cs = np.concatenate(([0.0], np.cumsum(m, dtype=np.float64)))
        return (cs[i0 + n] - cs[i0]) / n

    ref = None if series_ref_earth is None else frac(np.asarray(series_ref_earth, dtype=bool)[:-1])
    return WindowMetrics(float(duration_days), float(step_days), t[i0], frac(sun), frac(earth), frac(sun & earth),
                         _max_run(sun, i0, n) * dt / 3600.0, _max_run(~sun, i0, n) * dt / 3600.0, ref, sun[i0],
                         _max_run(~earth, i0, n) * dt / 3600.0, _max_run(earth, i0, n) * dt / 3600.0)


# Puertas y score vectorizados sobre (candidatos × inicios). Réplica de ``site_score`` (``compute_score`` +
# ``evaluate_gates``) verificada en tests/test_mission_windows.py; el score final de cada mejor fecha se recalcula con
# ``score_with_range``.
def window_scores(f_sun, d_max_h, f_earth, f_ref, slope90, unknown, profile: ScoreProfile, sp_: ScoreParams,
                  mission: Optional[MissionProfile], sun_start=None, max_gap_h=None) -> tuple[np.ndarray, np.ndarray]:
    """(score, gate_rank 0/1/2) con la forma de ``f_sun`` (n,S); ``slope90`` y ``unknown`` (n,) por punto.

    ``max_gap_h`` (n,S) = hueco máximo sin enlace de cada ventana: activa la continuidad ABSOLUTA de s_earth (``site_score.continuity_factor``,
    la misma función que el pipeline); ``None`` = geometría, sin continuidad.
    ``sun_start`` (n,S) bool = Sol visible al inicio de cada ventana: activa la puerta G0 (dura en perfiles solares con
    ``g0_needs_sun``), igual que ``pipeline._score_window`` (M2: antes el mapa la ignoraba y su ``apt_days`` quedaba por encima)."""
    d_half = profile.d_half_h if profile.d_half_h is not None else sp_.d_half_h
    w = normalize_weights(profile.weights)
    slope, unk = np.asarray(slope90, float)[:, None], np.asarray(unknown, float)[:, None]
    clip01 = lambda x: np.clip(x, 0.0, 1.0)   # noqa: E731
    floor = sp_.earth_floor if profile.earth_floor is None else profile.earth_floor   # s_earth con mínimo útil
    s = {"sun": clip01((f_sun - sp_.f0) / (sp_.f1 - sp_.f0)), "night": 2.0 ** (-d_max_h / d_half),
         "earth": np.minimum(1.0, f_earth / np.maximum(f_ref, floor)) * (
             1.0 if max_gap_h is None else continuity_factor(max_gap_h, f_earth, profile.max_link_gap_h, sp_.link_gap_half_factor,
                                                             profile.min_link_hours_per_day)),
         "terrain": 1.0 - clip01((slope - sp_.sigma0_deg) / (sp_.sigma1_deg - sp_.sigma0_deg))}
    # parte alta (sin saturar), igual que site_score._quality; mezcla A^(1-λ)·Q^λ como site_score.blend
    q = {"sun": clip01(f_sun), "night": s["night"], "earth": s["earth"],
         "terrain": 1.0 - clip01(slope / sp_.sigma1_deg)}
    lam, lg = sp_.resolution_weight, lambda x: np.log(np.maximum(x, sp_.eps_s))   # noqa: E731
    score = 100.0 * np.exp(sum(w[k] * ((1.0 - lam) * lg(s[k]) + lam * lg(q[k])) for k in KEYS if w[k] > 0))
    thr = (lambda key: mission.thresholds.get(key)) if mission is not None else (lambda key: None)
    t2, t4 = thr("max_landing_slope_deg"), thr("max_dark_h_no_nuclear")
    max_slope = sp_.g2_max_slope_deg if t2 is None or t2.value is None else float(t2.value)
    rank = np.where(slope > max_slope, 2, 0) + np.zeros(score.shape, int)
    rank = np.maximum(rank, np.where(unk > sp_.g3_max_unknown_fraction, 1, 0))
    if profile.uses_solar_gate:
        rank = np.maximum(rank, np.where(f_sun < sp_.g1_min_sun_fraction, 2, 0))
        if sun_start is not None and sp_.g0_needs_sun:   # G0: llegada de noche = no apto
            rank = np.maximum(rank, np.where(np.asarray(sun_start, bool), 0, 2))
    # G4 como site_score.evaluate_gates: el perfil anula (g4_na) o fija su límite; si no, el de la misión. Solo la dura rechaza
    if profile.g4_na:
        lim = typ = None
    elif profile.g4_limit_h is not None:
        lim, typ = float(profile.g4_limit_h), profile.g4_type or "hard"
    else:
        lim, typ = (None, None) if t4 is None or t4.value is None else (float(t4.value), t4.type)
    if lim is not None and typ == "hard":
        rank = np.maximum(rank, np.where(d_max_h > lim, 2, 0))
    return score, rank.astype(np.uint8)


_CUBE = ("score", "gate", "f_sun", "f_earth", "f_ref", "d_max_h", "longest_sun_h", "overlap", "gap_h")
_BEST = ("score", "score_min", "score_max", "gate", "f_sun", "f_earth", "d_max_h", "longest_sun_h", "overlap",
         "start_et", "start_idx", "apt_days", "night_ok_days", "gap_h", "g7_ok")


@dataclass(frozen=True)
class WindowSite:
    """Un punto recomendado para una duración de misión, con su mejor fecha de inicio."""
    rank: int
    lat_deg: float
    lon_deg_e: float
    x_m: float
    y_m: float
    duration_days: float
    best_start_et: float
    best_start_utc: str
    f_sun: float
    f_earth: float
    d_max_h: float
    longest_sun_h: float
    overlap_fraction: float
    score: float
    score_min: float
    score_max: float
    gate_status: str
    apt_start_days: float             # días de inicio (de los evaluados) con TODAS las puertas en PASS
    n_starts: int
    slope_p90_deg: float
    max_link_gap_h: Optional[float] = None   # hueco máximo sin enlace de la mejor ventana (h); None = sin enlace (geometría)
    g7_ok: Optional[bool] = None             # ¿la mejor fecha cumple G7 (hueco ≤ tolerado por el perfil)? None = no se evalúa


@dataclass(eq=False)
class WindowMap:
    """Idoneidad para UNA duración de misión: cubos (candidatos × fechas de inicio) y mejor inicio por candidato."""
    duration_days: float
    shape: tuple[int, int]               # (ny, nx) de la malla
    rows: np.ndarray
    cols: np.ndarray
    start_et: np.ndarray                 # (S,)
    step_days: float
    cube: dict[str, np.ndarray]          # _CUBE → (n, S)
    best: dict[str, np.ndarray]          # _BEST → (n,)
    top: tuple[WindowSite, ...] = ()

    @property
    def n_starts(self) -> int:
        return len(self.start_et)

    def arrays(self) -> dict[str, np.ndarray]:
        out = {"rows": self.rows, "cols": self.cols, "start_et": self.start_et, "step_days": np.array(self.step_days)}
        out.update({f"C_{k}": v for k, v in self.cube.items()})
        out.update({f"B_{k}": v for k, v in self.best.items()})
        return out

    @classmethod
    def from_arrays(cls, duration_days: float, shape, a: Mapping[str, np.ndarray]) -> "WindowMap":
        return cls(duration_days, tuple(shape), a["rows"], a["cols"], a["start_et"], float(a["step_days"]),
                   {k: a[f"C_{k}"] for k in _CUBE}, {k: a[f"B_{k}"] for k in _BEST})

    def raster(self, name: str, start_index: int) -> np.ndarray:
        """Raster (ny,nx) de ``name`` (score, f_sun, d_max_h, …; NaN = no evaluado) para la fecha de inicio ``start_index``."""
        r = np.full(self.shape, np.nan, np.float32)
        r[self.rows, self.cols] = self.cube[name][:, start_index]
        return r

    def best_raster(self, name: str) -> np.ndarray:
        """Raster del mejor valor alcanzable en el año (``score`` = score en la mejor fecha de inicio de cada punto;
        también apt_days, start_idx, d_max_h, …)."""
        r = np.full(self.shape, np.nan, np.float32)
        r[self.rows, self.cols] = self.best[name]
        return r


def best_start_index(gate, score, d_max, f_sun, gap, gap_limit_h) -> int:
    """Mejor fecha de inicio de UN candidato (vectores sobre las fechas): menor rango de puertas; entre ellas las que CUMPLEN G7 (hueco ≤
    ``gap_limit_h``) y, si ninguna, la de menor hueco (misma regla que ``site_score.choose_start``); luego mayor score, menor D_max,
    mayor f_sol y la más temprana. ``gap``/``gap_limit_h`` None = sin G7."""
    idx = np.arange(len(score))
    g7 = np.zeros(len(score))
    if gap is not None and gap_limit_h is not None:
        cand = gate == gate.min()
        ok = gap <= gap_limit_h
        g7 = (~ok).astype(float) if (cand & ok).any() else np.asarray(gap, float)
    return int(np.lexsort((idx, -f_sun, d_max, -score, g7, gate))[0])


def build_window_map(duration_days: float, wins: Sequence[WindowMetrics], rows, cols, shape, slope90, unknown,
                     profile: ScoreProfile, mission: Optional[MissionProfile], sp_: ScoreParams, pad_h: float,
                     link_mode: bool = False) -> WindowMap:
    """Cubos de score/puertas para todos los candidatos y mejor fecha de inicio de cada uno. ``link_mode`` = la serie de Tierra es
    el ENLACE (red + margen): activa la continuidad de s_earth, G7 y la elección de fecha por G7 (revision-enlace B1)."""
    stack = lambda attr: np.stack([getattr(w, attr) for w in wins]).astype(np.float64)   # noqa: E731
    f_sun, f_earth, f_ref, d_max, lsun, ovl = (stack(a) for a in
                                               ("f_sun", "f_earth", "f_ref", "max_dark_h", "longest_sun_h", "f_overlap"))
    n, S = f_sun.shape
    sun0 = np.stack([w.sun_start for w in wins]).astype(bool) if all(w.sun_start is not None for w in wins) else None
    gap = stack("max_gap_h") if link_mode else None
    score, gate = window_scores(f_sun, d_max, f_earth, f_ref, slope90, unknown, profile, sp_, mission, sun0, gap)
    glim = profile.max_link_gap_h if profile.max_link_gap_type in ("hard", "soft") else None
    t4 = mission.thresholds.get("max_dark_h_no_nuclear") if mission is not None else None
    night_ok = d_max <= (float(t4.value) if t4 is not None and t4.value is not None else np.inf)
    idx = np.arange(S)
    best_i = np.array([best_start_index(gate[p], score[p], d_max[p], f_sun[p], None if gap is None else gap[p], glim)
                       for p in range(n)], dtype=np.int64)
    b = {k: np.empty(n, np.float64) for k in _BEST}
    for p in range(n):   # el score de la mejor fecha, con rango, por la API de site_score (el barrido usa la réplica vectorizada)
        i = int(best_i[p])
        nom = ScoreInputs(f_sun=float(f_sun[p, i]), d_max_h=float(d_max[p, i]), f_earth=float(f_earth[p, i]),
                          f_earth_ref=max(float(f_ref[p, i]), 1e-6), slope_p90_deg=float(slope90[p]),
                          unknown_fraction=float(unknown[p]), observer_in_dem=True, has_dem=True, d_max_truncated=False,
                          sun_at_start=None if sun0 is None else bool(sun0[p, i]), link_mode=link_mode,
                          max_link_gap_h=None if gap is None else float(gap[p, i]))
        scen = [dataclasses.replace(nom, d_max_h=max(0.0, nom.d_max_h + sgn * pad_h)) for sgn in (-1.0, 1.0)]
        r = score_with_range(nom, scen, profile, sp_, mission)
        b["score"][p], b["score_min"][p], b["score_max"][p] = r.score, r.score_min, r.score_max
        b["gate"][p] = _GATE_RANK[r.status]
        for k, arr in (("f_sun", f_sun), ("f_earth", f_earth), ("d_max_h", d_max), ("longest_sun_h", lsun), ("overlap", ovl)):
            b[k][p] = arr[p, i]
        b["start_et"][p], b["start_idx"][p] = wins[p].start_et[i], i
        b["gap_h"][p] = np.nan if gap is None else gap[p, i]
        b["g7_ok"][p] = np.nan if gap is None or glim is None else float(gap[p, i] <= glim)
    b["apt_days"] = (gate == 0).sum(axis=1) * wins[0].step_days
    b["night_ok_days"] = night_ok.sum(axis=1) * wins[0].step_days
    cube = {"score": score, "gate": gate, "f_sun": f_sun, "f_earth": f_earth, "f_ref": f_ref, "d_max_h": d_max,
            "longest_sun_h": lsun, "overlap": ovl, "gap_h": gap if gap is not None else np.full(score.shape, np.nan)}
    return WindowMap(float(duration_days), tuple(shape), np.asarray(rows), np.asarray(cols), wins[0].start_et,
                     wins[0].step_days, {k: v.astype(np.uint8 if k == "gate" else np.float32) for k, v in cube.items()},
                     {k: v.astype(np.float32 if k != "start_et" else np.float64) for k, v in b.items()})


def build_window_top(wm: WindowMap, x_m, y_m, layers: Mapping[str, np.ndarray], params: SuitabilityParams) -> tuple[WindowSite, ...]:
    """TOP-N de puntos (separación mínima) para la duración, cada uno con su mejor fecha de inicio. Desempates: puertas,
    score, mayor f_sol, menor D_max, más días de inicio aptos, mayor f_Tierra y menor pendiente (el score satura en 100
    en ventanas cortas, así que sin desempates el ranking sería arbitrario)."""
    R = {k: wm.best_raster(k) for k in ("score", "gate", "f_sun", "f_earth", "d_max_h", "apt_days")}
    ties = (-R["f_sun"], R["d_max_h"], -R["apt_days"], -R["f_earth"], layers["slope_p90"])
    picks = select_top(R["score"], R["gate"], x_m, y_m, params.top_n, params.min_separation_m, params.rank_by_gates, ties)
    pos = {(int(r), int(c)): p for p, (r, c) in enumerate(zip(wm.rows, wm.cols))}
    pts = np.array([(x_m[c], y_m[r]) for r, c in picks]).reshape(-1, 2)
    lat, lon = stereo_inverse(pts[:, 0], pts[:, 1]) if len(picks) else (np.empty(0), np.empty(0))
    utc = spice_engine.et_to_utc(np.array([wm.best["start_et"][pos[rc]] for rc in picks])) if picks else []
    out = []
    for k, (r, c) in enumerate(picks):
        p = pos[(r, c)]
        B = {name: float(arr[p]) for name, arr in wm.best.items()}
        out.append(WindowSite(
            rank=k + 1, lat_deg=float(lat[k]), lon_deg_e=float(lon[k]), x_m=float(x_m[c]), y_m=float(y_m[r]),
            duration_days=wm.duration_days, best_start_et=B["start_et"], best_start_utc=utc[k], f_sun=B["f_sun"],
            f_earth=B["f_earth"], d_max_h=B["d_max_h"], longest_sun_h=B["longest_sun_h"], overlap_fraction=B["overlap"],
            score=B["score"], score_min=B["score_min"], score_max=B["score_max"],
            gate_status={0: "PASS", 1: "NO_DATA", 2: "FAIL"}[int(B["gate"])], apt_start_days=B["apt_days"],
            n_starts=wm.n_starts, slope_p90_deg=float(layers["slope_p90"][r, c]),
            max_link_gap_h=None if not np.isfinite(B["gap_h"]) else B["gap_h"],
            g7_ok=None if not np.isfinite(B["g7_ok"]) else bool(B["g7_ok"])))
    return tuple(out)


# ----------------------------------------------------------------------------------------------- mapa
def default_workers() -> int:
    import os
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def compute_map(surf: DemWindow, slp: Optional[DemWindow], far: Optional[DemWindow], *, dem_key: str,
                profile: ScoreProfile, mission: Optional[MissionProfile], score_params: ScoreParams,
                hp, vp: VisibilityParams, tp: TimelineParams, params: SuitabilityParams, eph: Mapping,
                et: np.ndarray, workers: int = 1, log=None, link=None) -> SuitabilityMap:
    """Mapa sin caché ni E/S (núcleo testeable). ``hp`` = HorizonParams base (r_min, r_max, bloque); se sobrescriben
    az/paso radial/altura/cota superior con los de ``params``."""
    t_start = time.perf_counter()
    notes: list[str] = []
    xs, ys = build_grid(surf, params)
    slope_arr = np.asarray(slp.data if slp is not None else slope_map_deg(surf, max(10.0, 2.0 * surf.pixel_size_m)),
                           dtype=np.float64)   # sin capa slp: diferencia central de 10 m (2 px si el DEM es más grueso)
    limit = slope_limit(params, mission, score_params)
    apt, p90 = prefilter(surf, slope_arr, xs, ys, params, limit)
    z_up = float(np.nanmax(surf.data))
    if far is not None:
        z_up = max(z_up, float(np.nanmax(far.data)))
    hp2 = dataclasses.replace(hp, observer_height_m=params.observer_height_m, az_step_deg=params.az_step_deg,
                              radial_step_m=params.radial_step_m, compute_upper_bound=False, z_up_m=z_up)
    vp2 = dataclasses.replace(vp, n_slices=params.n_slices) if params.n_slices else vp
    state = dict(surf=surf, far=far, eph=eph, et=et, hp=hp2, vp=vp2, tp=tp, profile=profile, mission=mission,
                 score_params=score_params, dem_key=dem_key, far_step_m=params.far_step_m if far is not None else None,
                 wd=tuple(float(d) for d in params.window_durations_days), wstep=params.window_step_days,
                 wsd=params.window_start_days)
    if link is not None:   # LinkContext: la cobertura de red es del cielo, no del sitio → una vez, compartida por todos los nodos
        state.update(link_iv=link.coverage.any_intervals(), link_grid=link.coverage.any_grid,
                     margin=link.min_earth_elevation_deg)
    rr, cc = np.nonzero(apt == APT_EVAL)
    xx, yy = np.meshgrid(xs, ys)
    lat, lon = stereo_inverse(xx, yy)
    pts = [(float(xs[c]), float(ys[r]), float(lat[r, c]), float(lon[r, c]), float(p90[r, c])) for r, c in zip(rr, cc)]
    if log:
        log(f"{dem_key}: malla {len(xs)}x{len(ys)}={apt.size} nodos; pendiente p90 ≤ {limit:g}°: {len(pts)} candidatos")
    res = _run_points(state, pts, workers)
    layers = {k: np.full(apt.shape, np.nan, np.float32) for k in FLOAT_LAYERS}
    layers["slope_p90"] = np.where(apt >= APT_STEEP, p90, np.nan).astype(np.float32)
    for (r, c), (v, _) in zip(zip(rr, cc), res):
        for name, val in zip(_POINT_FIELDS, v):
            layers[name][r, c] = val
    top = build_top(layers, xs, ys, profile, params)
    if far is None:
        notes.append("sin campo lejano: horizonte limitado a la cobertura del DEM")
    windows = {}
    if params.window_durations_days:
        slope_c = np.array([p[4] for p in pts], np.float64)
        unk_c = layers["unknown_fraction"][rr, cc].astype(np.float64)
        pad_h = params.range_pad_steps * float(et[1] - et[0]) / 3600.0
        for d in state["wd"]:
            windows[d] = build_window_map(d, [w[d] for _, w in res], rr, cc, apt.shape, slope_c, unk_c, profile, mission,
                                          score_params, pad_h, link_mode=link is not None)
            windows[d].top = build_window_top(windows[d], xs, ys, layers, params)
    return SuitabilityMap(dem_key, profile.id, params, xs, ys, apt, layers, top, int(apt.size), len(pts),
                          time.perf_counter() - t_start, slope_limit_deg=limit, notes=tuple(notes), windows=windows)


def _content_id(w: Optional[DemWindow]) -> Optional[str]:
    if w is None:
        return None
    if w.meta is not None and w.meta.sha256:
        return w.meta.sha256
    return cache_mod.digest(w.x0_m, w.y0_m, w.pixel_size_m, list(w.data.shape)) + \
        hashlib.sha256(np.ascontiguousarray(w.data).tobytes()).hexdigest()


def cache_key(surf, slp, far, profile, mission, score_params, hp, vp, tp, params, eph, link=None) -> str:
    """Hash de DEM (+slp +campo lejano) + parámetros + perfil/misión/score + efemérides + versión del algoritmo."""
    return cache_mod.digest(CACHE_ALGORITHM_VERSION, MODULE_VERSION, _content_id(surf), _content_id(slp), _content_id(far),
                            params, profile, mission, score_params, hp, vp, tp, eph["kernel_hash"],
                            None if link is None else (link.network, link.min_earth_elevation_deg,
                                                       hashlib.sha256(np.round(link.coverage.el_deg, 3).tobytes()).hexdigest()))


def _save(cache_dir: Path, m: SuitabilityMap) -> None:
    meta = dict(dem_key=m.dem_key, profile_id=m.profile_id, params=dataclasses.asdict(m.params), n_grid=m.n_grid,
                n_candidates=m.n_candidates, seconds=m.seconds, slope_limit_deg=m.slope_limit_deg, notes=list(m.notes))
    arrays = {"x_m": m.x_m, "y_m": m.y_m, "aptitude": m.aptitude, "meta_json": np.array(json.dumps(meta))}
    arrays.update({f"L_{k}": v for k, v in m.layers.items()})
    for i, wm in enumerate(m.windows.values()):
        arrays.update({f"W{i}_{k}": v for k, v in wm.arrays().items()})
    cache_mod.save_npz(cache_dir, KIND, m.cache_key, arrays)


def _load(cache_dir: Path, key: str, profile: ScoreProfile) -> Optional[SuitabilityMap]:
    z = cache_mod.load_npz(cache_dir, KIND, key)
    if z is None or "meta_json" not in z:
        return None
    meta = json.loads(str(z["meta_json"]))
    meta["params"]["window_durations_days"] = tuple(meta["params"].get("window_durations_days", ()))
    params = SuitabilityParams(**meta["params"])
    layers = {k: z[f"L_{k}"] for k in FLOAT_LAYERS}
    windows = {}
    for i, d in enumerate(params.window_durations_days):
        pre = f"W{i}_"
        wm = WindowMap.from_arrays(float(d), layers["score"].shape, {k[len(pre):]: z[k] for k in z if k.startswith(pre)})
        wm.top = build_window_top(wm, z["x_m"], z["y_m"], layers, params)
        windows[wm.duration_days] = wm
    return SuitabilityMap(meta["dem_key"], meta["profile_id"], params, z["x_m"], z["y_m"], z["aptitude"], layers,
                          build_top(layers, z["x_m"], z["y_m"], profile, params), meta["n_grid"], meta["n_candidates"],
                          meta["seconds"], key, True, meta["slope_limit_deg"], tuple(meta["notes"]), windows=windows)


def suitability_map(ctx, dem_key: str, profile_id: str = "lander_solar_no_rhu",
                    params: Optional[SuitabilityParams] = None, *, workers: Optional[int] = None,
                    use_cache: bool = True, log=None) -> SuitabilityMap:
    """Mapa de idoneidad del recorte ``dem_key`` con datos reales (``ctx`` = ``pipeline.build_context``)."""
    from lsi import pipeline   # perezoso: pipeline es el cableado; este módulo solo reutiliza sus helpers de contexto
    cfg = ctx.cfg
    params = params or SuitabilityParams()
    profiles = catalog.score_profiles(cfg)
    if profile_id not in profiles:
        raise catalog.InvalidParameterError(f"Perfil desconocido '{profile_id}'; válidos: {sorted(profiles)}")
    if dem_key not in ctx.dem_refs:
        raise DemNotFoundError(f"DEM '{dem_key}' no descubierto; disponibles: {sorted(ctx.dem_refs)}")
    ref, profile = ctx.dem_refs[dem_key], profiles[profile_id]
    mission = pipeline._mission(ctx, profile.mission_profile_id)
    sp_, vp, tp = catalog.score_params(cfg), catalog.visibility_params(cfg), dataclasses.replace(catalog.timeline_params(cfg), step_s=params.step_s)   # rejilla gruesa a propósito: se salta max_step_s; error medido
    hp = catalog.horizon_params(cfg, params.observer_height_m)
    foot = float(cfg["terrain"]["footprint_radius_m"])
    if abs(foot - params.footprint_radius_m) > 1e-9:
        params = dataclasses.replace(params, footprint_radius_m=foot)
    surf = loader.read_window(ref, DemLayer.SURF)
    try:
        slp = loader.read_window(ref, DemLayer.SLP)
    except DemNotFoundError:
        slp = None
    x0, y0, x1, y1 = ref.bounds_xy_m
    half = 0.5 * max(x1 - x0, y1 - y0)
    far = None
    if loader.discover_far_field(Path(ctx.root) / "data" / "raw") is not None:   # ±(r_max + semiextensión) cubre todo rayo
        far = loader.load_far_field(Path(ctx.root) / "data" / "raw", 0.5 * (x0 + x1), 0.5 * (y0 + y1), hp.r_max_m + half)
    et = time_grid(params)
    eph = ephemeris(et, Path(ctx.root) / "kernels")
    margin = params.min_earth_elevation_deg
    if margin is None:
        margin = profile.min_earth_elevation_deg if profile.min_earth_elevation_deg is not None else 0.0
    link = gs.make_link_context(et, params.link_network, float(margin),
                                station_min_elevation_deg=params.link_station_min_elevation_deg, link_direction=params.link_direction)
    key = cache_key(surf, slp, far, profile, mission, sp_, hp, vp, tp, params, eph, link)
    cdir = Path(ctx.root) / cfg["cache"]["dir"]
    if use_cache:
        hit = _load(cdir, key, profile)
        if hit is not None:
            if log:
                log(f"{dem_key}: mapa en caché ({key[:12]}), calculado en {hit.seconds:.1f} s")
            return hit
    m = compute_map(surf, slp, far, dem_key=dem_key, profile=profile, mission=mission, score_params=sp_, hp=hp, vp=vp,
                    tp=tp, params=params, eph=eph, et=et, workers=default_workers() if workers is None else workers, log=log,
                    link=link)
    m.cache_key = key
    if use_cache:
        _save(cdir, m)
    return m


# ----------------------------------------------------------------------------------------------- mejores puntos precalculados
WINDOWS_SCHEMA = "lsi.suitability.windows/1"
WINDOWS_REVISION = 2   # revisión menor aditiva (14/11/2026), en ``schema_revision`` del JSON; ``schema_version`` sigue en /1 porque ``ui/pages/best_spots.py``
# la compara por igualdad. Rev. 2: cada candidato del TOP-N lleva ``score_range_resolution`` (= el viejo ``score_min``/``score_max``: solo ±1 paso de
# rejilla en D_max, ancho cero si la puerta satura) y ``score_range_uncertainty`` (escenarios REALES ±σz, ΔA y H_ub si aplica sobre el modelo fino en la
# mejor fecha; ``pipeline.run_analysis(with_uncertainty=True)``) más ``score_fine``, ``scenario_scores``, ``metric_ranges``, ``slope_r50/r100``.
# ``score_min``/``score_max`` se conservan como alias de la resolución. Una revisión 1 (sin esas claves) sigue siendo legible.
WINDOWS_SCHEMAS_ACCEPTED = (WINDOWS_SCHEMA, "lsi.suitability.windows/2")   # /2 reservado por si la UI migra


@lru_cache(maxsize=32)
def _read_windows_doc(path: str, mtime_ns: int) -> Optional[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def best_points(cache_dir: Path, dem_key: str, profile_id: str, mission_days: float) -> Optional[dict]:
    """TOP-N PRECALCULADO (``windows_*.json`` de ``scripts/precompute_suitability.py``, la versión más reciente con el
    ``MODULE_VERSION`` actual) del recorte ``dem_key`` para el perfil y la duración de misión más cercana a ``mission_days``
    (empate → la mayor). None si no hay mapa. Devuelve ``{duration_days, requested_days, path, top}``; ``top`` = lista de dicts
    ``WindowSite`` (rank, lat_deg, lon_deg_e, x_m, y_m, best_start_utc, f_sun, f_earth, d_max_h, score, gate_status...)
    ordenada por rango (el primero es el MEJOR PUNTO: puertas, score y desempates físicos). Sin recalcular nada."""
    best = None
    for f in (Path(cache_dir) / KIND).glob("windows_*.json"):
        try:
            st = f.stat()
        except OSError:
            continue
        doc = _read_windows_doc(str(f), st.st_mtime_ns)
        if not doc or doc.get("schema_version") not in WINDOWS_SCHEMAS_ACCEPTED or doc.get("module_version") != MODULE_VERSION:
            continue
        pre = f"{dem_key}|{profile_id}|"
        res = {k: v for k, v in doc.get("results", {}).items() if k.startswith(pre) and v.get("top")}
        if res and (best is None or st.st_mtime_ns > best[0]):
            best = (st.st_mtime_ns, str(f), res)
    if best is None:
        return None
    _, path, res = best
    rec = min(res.values(), key=lambda v: (abs(float(v["duration_days"]) - float(mission_days)), -float(v["duration_days"])))
    return dict(duration_days=float(rec["duration_days"]), requested_days=float(mission_days), path=path, top=list(rec["top"]))


# ----------------------------------------------------------------------------------------------- incertidumbre REAL de un candidato
def candidate_uncertainty(ctx, site: Mapping, profile_id: str, params: SuitabilityParams) -> dict:
    """Incertidumbre REAL del score de un candidato del TOP-N en su mejor fecha, separada del rango de resolución temporal.

    Ejecuta ``pipeline.run_analysis(with_uncertainty=True)`` (modelo fino: az 0,25°, 5 m, campo lejano ½ píxel) sobre
    [best_start_utc, + duración] y puntúa cada escenario (H_ub = terreno no cubierto sube a z_up, z ± k·σz con TOPERR, ΔA = rejilla
    azimutal submuestreada a 0,5°). ``site``: dict de ``WindowSite`` (lat_deg, lon_deg_e, best_start_utc, duration_days).
    Devuelve ``score_fine`` (nominal del modelo fino), ``score_range_uncertainty`` [mín, máx] sobre nominal y escenarios,
    ``scenario_scores``, ``metric_ranges`` (f_sol, D_max h, f_enlace: aquí el ancho no se satura aunque el score sí) y ``note``."""
    from lsi import pipeline
    from lsi.analysis.site_score import compute_score, params_from_config, profiles_from_config
    from lsi.contracts import AnalysisRequest
    days = float(site["duration_days"])
    t0 = spice_engine.utc_to_et(str(site["best_start_utc"]))
    end = spice_engine.et_to_utc(t0 + days * 86400.0)[:19]
    res = pipeline.run_analysis(ctx, AnalysisRequest(
        float(site["lat_deg"]), float(site["lon_deg_e"]), str(site["best_start_utc"])[:19], end,
        observer_height_m=params.observer_height_m, step_s=params.step_s, score_profile_id=profile_id, with_uncertainty=True,
        mission_days=days, snap_to_dem=False, link_network=params.link_network,
        min_earth_elevation_deg=params.min_earth_elevation_deg,
        link_station_min_elevation_deg=params.link_station_min_elevation_deg, link_direction=params.link_direction))
    prof = profiles_from_config(ctx.cfg["score"])[profile_id]
    sp = params_from_config(ctx.cfg["score"])
    mission = pipeline._mission(ctx, prof.mission_profile_id)
    names = [sc.name for sc in res.uncertainty.scenarios]
    scen = {n: round(compute_score(i, prof, sp, mission).score, 2) for n, i in zip(names, res.score_scenarios)}
    lo, hi = res.score.score_min, res.score.score_max
    mr = {"f_sun": res.uncertainty.ranges["solar_fraction"], "d_max_h": res.uncertainty.ranges["max_darkness_s"]}
    out = dict(
        score_fine=round(float(res.score.score), 2), score_range_uncertainty=[round(float(lo), 2), round(float(hi), 2)],
        scenario_scores=scen, scenarios_run=names,
        coverage_ub_applicable="coverage_ub" in names,   # H_ub solo existe si algún azimut queda sin cobertura del DEM
        metric_ranges=dict(f_sun=[round(mr["f_sun"].lo, 4), round(mr["f_sun"].hi, 4)],
                           d_max_h=[round(mr["d_max_h"].lo / 3600.0, 2), round(mr["d_max_h"].hi / 3600.0, 2)]),
        gate_status_fine=res.score.status.value if hasattr(res.score.status, "value") else str(res.score.status),
        uncertainty_model="pipeline.run_analysis(with_uncertainty=True): escenarios H_ub, ±σz (TOPERR), ΔA 0,5° en la mejor fecha; cotas de sensibilidad, no estadística",
        slope_r50=dataclasses.asdict(res.slope_r50) if res.slope_r50 else None,
        slope_r100=dataclasses.asdict(res.slope_r100) if res.slope_r100 else None,
        footprint_touches_dem_edge=res.footprint_touches_dem_edge)
    if "link_fraction" in res.uncertainty.ranges:
        r = res.uncertainty.ranges["link_fraction"]
        out["metric_ranges"]["link_fraction"] = [round(r.lo, 4), round(r.hi, 4)]
    out["note"] = ("el score no se mueve con la incertidumbre (puerta/escalón saturado); mira metric_ranges" if hi - lo < 0.05 else
                   f"rango real {lo:.1f}–{hi:.1f} entre {len(scen)} escenarios")
    return out


# ----------------------------------------------------------------------------------------------- validación frente al modelo fino
def validation_points(m: SuitabilityMap, k: int) -> list[tuple[float, float]]:
    """(lat, lon) del TOP-N y de nodos repartidos uniformemente por el ranking de score (determinista), hasta ``k``."""
    pts = [(s.lat_deg, s.lon_deg_e) for s in m.top]
    sc = m.layers["score"]
    rr, cc = np.nonzero(np.isfinite(sc))
    if len(rr) == 0 or k <= len(pts):
        return pts[:k]
    order = np.lexsort((m.x_m[cc], -m.y_m[rr], -sc[rr, cc]))
    lat, lon = m.lat_lon
    for i in np.linspace(0, len(order) - 1, k - len(pts) + 2).astype(int)[1:-1]:
        r, c = rr[order[i]], cc[order[i]]
        pts.append((float(lat[r, c]), float(lon[r, c])))
    return pts


def fine_check(ctx, m: SuitabilityMap, lat: float, lon: float) -> dict:
    """Modelo fino de referencia (``pipeline.run_analysis``: az 0.25°, 5 m, ½ píxel lejano, 600 s con refinamiento) en
    el mismo periodo y perfil, y valores gruesos del nodo más cercano. Devuelve las dos series y su diferencia."""
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    p = m.params
    et0 = spice_engine.utc_to_et(p.start_utc)
    end = spice_engine.et_to_utc(et0 + p.days * 86400.0)[:19]
    res = pipeline.run_analysis(ctx, AnalysisRequest(lat, lon, p.start_utc, end, observer_height_m=p.observer_height_m,
                                                     step_s=600.0, score_profile_id=m.profile_id,
                                                     link_network=p.link_network, min_earth_elevation_deg=p.min_earth_elevation_deg,
                                                     link_station_min_elevation_deg=p.link_station_min_elevation_deg,
                                                     link_direction=p.link_direction))
    xx, yy = np.meshgrid(m.x_m, m.y_m)
    from lsi.astronomy.coordinates import stereo_forward
    x, y = (float(v) for v in stereo_forward(lat, lon))
    r, c = np.unravel_index(int(np.argmin((xx - x) ** 2 + (yy - y) ** 2)), xx.shape)
    coarse = {k: float(m.layers[k][r, c]) for k in ("f_sun", "f_earth", "d_max_h", "score")}
    fine = dict(f_sun=res.metrics.solar_fraction,
                f_earth=res.metrics.earth_fraction if res.metrics.link_fraction is None else res.metrics.link_fraction,
                d_max_h=res.metrics.max_darkness_s / 3600.0, score=res.score.score)
    return dict(lat=lat, lon=lon, node=(int(r), int(c)), node_dist_m=float(math.hypot(xx[r, c] - x, yy[r, c] - y)),
                coarse=coarse, fine=fine, diff={k: coarse[k] - fine[k] for k in coarse})
