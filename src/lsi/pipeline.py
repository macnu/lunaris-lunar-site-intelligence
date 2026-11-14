"""Orquestación de LSI (arquitectura §5.18, D3): ÚNICO módulo que cablea terreno, astronomía, simulación, energía y análisis.

Flujo de ``run_analysis``: observador (DEM / snap_to_dem / esfera lisa) → horizonte (DEM 5 m + campo lejano LOLA 80 m si
existe; esfera lisa si no hay DEM) → Sol y Tierra (SPICE) → visibilidad y ventanas → métricas (+ rangos de incertidumbre)
→ pendiente y confianza del DEM (c_sup = min(c_gap, c_err, c_hz), con los dos horizontes DEM ± toterr) → potencia
(uno o varios paneles, batería opcional) → score con perfil de misión y rango → cuenta atrás → avisos científicos (§9.3).
Sin streamlit y sin reloj (el «ahora» entra en la petición).

**Ventana de misión** (revision-espacial §2): el score y las puertas se evalúan sobre [inicio, inicio + mission_days]
(``AnalysisRequest.mission_days`` o la del perfil), no sobre todo el periodo. Si el periodo es mayor que la misión se barren
las fechas de inicio (rejilla ``window_step_h``) con ``mission_window_metrics`` y el nominal es la mejor fecha; si es menor,
el estado es SIN DATOS (o NO APTO si ya falla una puerta dura). Las métricas de la ventana elegida se recalculan exactas
(``run_timeline`` sobre el tramo, con refinamiento de eventos); el barrido va a la resolución de la rejilla (``step_s``).
"""
from __future__ import annotations

import dataclasses
import math
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from lsi.analysis import metrics as mt
from lsi.analysis.confidence import dem_confidence, horizon_sigma_p90, support_confidence
from lsi.analysis.metrics import compute_metrics
from lsi.analysis.site_score import (
    choose_start, compute_score, effective_energy, hard_fails, max_sustainable, params_from_config, pick_windows,
    profiles_from_config, score_with_range,
)
from lsi.analysis import suitability_map
from lsi.analysis.suitability_map import mission_window_metrics
from lsi.astronomy import ground_stations as gs
from lsi.astronomy import spice_engine
from lsi.astronomy.coordinates import normalize_lon, stereo_forward, stereo_inverse
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, MOON_RADIUS_KM, STANDARD_WARNINGS_ES, UTC_MAX, AnalysisRequest, AnalysisResult, AppContext,
    BatteryParams, BatteryResult, Body, BodyTrack, Countdown, DateOutOfRangeError, DemLayer, DemNotFoundError,
    DemRef, DemWindow, HorizonMode, LSIError, MissionProfile, MountingSpec,
    NodataAtObserverError, ObserverNearEdgeError, ObserverOutsideDemError, ObserverPoint, PanelNotCalculableError,
    PowerParams, PowerSeries, PowerSummary, ScientificWarning, ScoreInputs, Severity, SkySeries, SustainableDays,
    SlopeScale, SnapRankEntry, WarningCode, WindowScore,
)
from lsi.data import cache as cache_mod
from lsi.data import catalog
from lsi.data import loader
from lsi.energy import panels as pn
from lsi.simulation.timeline import countdown, find_windows, run_timeline
from lsi.simulation.uncertainty import run_uncertainty
from lsi.simulation.visibility import disc_fraction, link_fraction, visibility_series
from lsi.terrain import horizon as hz_mod
from lsi.terrain import slope as slope_mod
from lsi.terrain.sampling import sample_bilinear

SNAP_MAX_KM = 10.0     # [sup] un rasgo del buscador se «engancha» al DEM si este queda a ≤ 10 km de su centro
SNAP_INSET_M = 100.0   # [sup] el punto de snap se mete 100 m (+ margen de borde) hacia dentro del recorte
SHORT_PERIOD_D = 29.53  # §5.9.6: por debajo de un mes sinódico D_max y f_sol no son representativos
SNAP_DEFAULT_PROFILE = "lander_solar_no_rhu"   # perfil del mejor punto cuando la petición no dice cuál

_LOCK = threading.Lock()
_F_EARTH_REF: dict = {}

# Error MEDIDO del horizonte de 80 m frente al de 5 m (docs/validation/horizonte-campo-lejano.md; lo regenera
# scripts/validate_far_field.py: 120 puntos de Site23, Site11 y Site04, 30 días). Entra en el aviso de la UI: nunca una cifra genérica.
FAR_FIELD_VALIDATION = {"n_points": 120, "horizon_rms_deg": 0.68, "horizon_max_deg": 5.8, "sun_fraction_abs_p95": 0.040,
                        "earth_fraction_abs_p95": 0.038, "verdict_change_pct": 10.0}
FAR_FIELD_LAT_MAX = -80.0   # el DEM polar LOLA 80 m cubre de 80°S al polo (±304 km); más al norte sigue la esfera lisa


FAR_FIELD_SCORE_TEXT = ("Terreno fino sin datos: el score es PARCIAL (sin pendiente de aterrizaje: la de 80 m no vale para aterrizar) y "
                        "la confianza es baja. Sol y Tierra sí usan el horizonte con relieve de 80 m (aproximado). No es comparable con sitios "
                        "con DEM de 5 m.")
# textos de site_score que hablan de «esfera lisa» y en el modo de 80 m serían falsos (hay relieve, aunque grueso)
_FAR_TEXT_FIXES = (
    ("sin datos de terreno (esfera lisa)", "terreno fino sin datos (el DEM de 80 m no sirve para decidir un aterrizaje)"),
    ("provisional, cota optimista sobre esfera lisa", "provisional, con terreno fino sin datos"),
    ("solo refleja el terreno no evaluable (esfera lisa)", "solo refleja el terreno fino no evaluable (80 m)"),
)


def far_field_warning_text() -> str:
    """Aviso científico del modo de 80 m con el error medido (docs/validation/horizonte-campo-lejano.md)."""
    v = FAR_FIELD_VALIDATION
    base = "Resolución 80 m: horizonte aproximado; no sirve para decidir un aterrizaje fino."
    if v.get("horizon_rms_deg") is None:
        return base + " Error frente al DEM de 5 m: sin medir."
    return (f"{base} Medido frente al DEM de 5 m en {v['n_points']} puntos: el horizonte difiere {v['horizon_rms_deg']:.2f}° "
            f"(RMS) y hasta {v['horizon_max_deg']:.1f}° (máx.); la fracción de Sol cambia ±{100 * v['sun_fraction_abs_p95']:.0f} puntos "
            f"y la de Tierra ±{100 * v['earth_fraction_abs_p95']:.0f} puntos (percentil 95); el veredicto cambia en el "
            f"{v['verdict_change_pct']:.0f} % de los puntos.")


def effective_step_s(cfg: dict, step_s: float) -> float:
    """Paso de rejilla INTERNO para un paso pedido (M1). Hasta ``timeline.max_step_s`` es el pedido; por encima se divide en
    n partes iguales (n mínimo con paso ≤ max): 900 → 450 s, 1800 → 600 s, 3600 → 720 s. Así la serie pedida (15/30/60 min) es un
    submuestreo exacto de la interna y no se pierden transiciones cortas (el límite existe por eso). Pasos ≤ 0 o NaN se
    devuelven tal cual para que ``catalog.timeline_params`` los rechace con su mensaje."""
    mx = cfg["timeline"].get("max_step_s")
    if mx is None or not step_s > mx:
        return step_s
    return float(step_s) / math.ceil(float(step_s) / float(mx) - 1e-9)


class InvalidParameterError(catalog.InvalidParameterError):
    """Petición inválida (periodo vacío, perfil desconocido...)."""


# ----------------------------------------------------------------------------------------------- contexto
def build_context(root: Path) -> AppContext:
    """Carga config, kernels, DEM descubiertos, paneles y sitios una sola vez; no falla si no hay DEM (RF-02)."""
    root = Path(root)
    cfg = catalog.load_simulation_config(root / "config" / "simulation.json")
    kernels = spice_engine.load_kernels(root / "kernels")
    refs = loader.discover_dems(root / "data" / "raw")
    try:  # purga LRU SOLO de la caché de horizontes (A1: suitability/ no se toca); best effort: no debe impedir arrancar
        cache_mod.purge(root / cfg["cache"]["dir"], int(cfg["cache"]["max_bytes"]), (cfg["cache"].get("horizons_subdir", "horizons"),))
    except OSError:
        pass
    return AppContext(root=str(root), cfg=cfg, kernels=kernels, dem_refs=refs,
                      panels=pn.load_panel_catalog(root / "config" / "panels.json"),
                      sites=catalog.load_sites(root / "config" / "sites.json"))


def _raw(ctx: AppContext) -> Path:
    return Path(ctx.root) / "data" / "raw"


def _cache_dir(ctx: AppContext) -> Path:
    return Path(ctx.root) / ctx.cfg["cache"]["dir"]


@lru_cache(maxsize=4)
def _layer(ref: DemRef, layer: DemLayer) -> DemWindow:
    """Capa completa en memoria (arquitectura §6: lru_cache(maxsize=4)). Solo lectura."""
    return loader.read_window(ref, layer)


@lru_cache(maxsize=4)
def _far(raw: str, x_m: float, y_m: float, r_max_m: float) -> Optional[DemWindow]:
    """Ventana ±r_max del campo lejano LOLA 80 m alrededor del observador; None si el fichero no existe."""
    if loader.discover_far_field(Path(raw)) is None:
        return None
    return loader.load_far_field(Path(raw), x_m, y_m, r_max_m)


def far_field_for(raw: Path, x_m: float, y_m: float, r_max_m: float) -> Optional[DemWindow]:
    """Campo lejano del observador (x, y) tal como lo usa ``run_analysis`` (mismo redondeo → misma clave de caché de horizontes).
    ``scripts/precompute_horizons.py`` lo reutiliza para que su caché acierte (M4)."""
    return _far(str(raw), round(x_m, 3), round(y_m, 3), r_max_m)


def _far_ground(raw: Path, lat_deg: float, x_m: float, y_m: float, r_max_m: float) -> Optional[float]:
    """Elevación del suelo (m) del DEM de 80 m en (x, y); None si el punto está al norte de 80°S, no hay fichero o no hay dato."""
    if lat_deg > FAR_FIELD_LAT_MAX:
        return None
    far = far_field_for(raw, x_m, y_m, r_max_m)
    if far is None:
        return None
    z, ok = sample_bilinear(far, np.array([x_m]), np.array([y_m]))
    return float(z[0]) if ok[0] else None


def _small(ref: DemRef, layer: DemLayer, x_m: float, y_m: float, r_m: float) -> DemWindow:
    return loader.read_window(ref, layer, (x_m - r_m, y_m - r_m, x_m + r_m, y_m + r_m))


# ----------------------------------------------------------------------------------------------- observador
def _gc_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de círculo máximo sobre la esfera lunar (km)."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MOON_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _w(code: WarningCode, sev: Severity, context: Optional[str] = None, text: Optional[str] = None) -> ScientificWarning:
    return ScientificWarning(code, sev, text or STANDARD_WARNINGS_ES[code], context)


def _project(lat: float, lon: float) -> tuple[float, float]:
    x, y = stereo_forward(np.float64(lat), np.float64(normalize_lon(lon)))
    return float(x), float(y)


def _ground(ref: DemRef, x: float, y: float) -> Optional[float]:
    """z del DEM en (x, y) o None si el punto o algún vecino bilineal no tiene dato."""
    z, ok = sample_bilinear(_small(ref, DemLayer.SURF, x, y, 30.0), np.array([x]), np.array([y]))
    return float(z[0]) if ok[0] else None


@dataclass(frozen=True)
class SnapCandidate:
    """Punto del DEM al que se puede enganchar una petición cuyo punto cae fuera (ajuste 'snap_to_dem')."""
    lat_deg: float
    lon_deg_e: float
    x_m: float
    y_m: float
    dem_key: str
    distance_km: float      # distancia (círculo máximo) al punto pedido (= centro del rasgo si viene del gazetteer)
    kind: str               # "best" (TOP-1 del mapa de idoneidad) | "nearest" | "default_observer"
    reason: str = ""        # por qué este punto (español, para la etiqueta y el aviso)
    best_start_utc: Optional[str] = None            # kind "best": mejor fecha de inicio sugerida de este punto
    ranking: tuple = ()                             # kind "best": TOP-N del mapa (``SnapRankEntry``), el primero es este punto
    nearest: Optional["SnapCandidate"] = None       # kind "best": la ALTERNATIVA, el punto cubierto más cercano
    duration_days: Optional[float] = None           # kind "best": duración del mapa usado (la más cercana a la misión pedida)
    feature_radius_km: Optional[float] = None       # radio del rasgo con el que se acotó el snap (None = sin acotar)
    edge_offset_km: Optional[float] = None          # distancia al borde: >0 fuera, <0 dentro (distancia al centro − radio)
    inside_feature: Optional[bool] = None           # False = ningún punto recomendable dentro del rasgo (se usa el más cercano)
    map_rank: Optional[int] = None                  # kind "best": rango del punto elegido en el mapa


def _nearest_snap(ctx: AppContext, lat_deg: float, lon_deg_e: float, site_id: Optional[str], max_km: float) -> Optional[SnapCandidate]:
    """Punto del DEM más cercano al pedido (o el ``dem_default_observer`` si ese no tiene dato válido)."""
    x, y = _project(lat_deg, lon_deg_e)
    site = next((s for s in ctx.sites if s.id == site_id), None)
    paired = site is not None and site.dem_prefix in ctx.dem_refs
    inset = SNAP_INSET_M + float(ctx.cfg["observer"].get("edge_margin_px", 2)) * 5.0
    best = None
    for key, ref in ctx.dem_refs.items():
        if paired and key != site.dem_prefix:
            continue
        x0, y0, x1, y1 = ref.bounds_xy_m
        cx, cy = min(max(x, x0 + inset), x1 - inset), min(max(y, y0 + inset), y1 - inset)
        d = math.hypot(cx - x, cy - y)
        if best is None or d < best[0]:
            best = (d, key, ref, cx, cy)
    if best is None:
        return None
    _, key, ref, cx, cy = best
    mx, my = (ref.bounds_xy_m[0] + ref.bounds_xy_m[2]) / 2, (ref.bounds_xy_m[1] + ref.bounds_xy_m[3]) / 2
    pts, kind = [], "nearest"
    n = max(math.hypot(mx - cx, my - cy), 1.0)
    pts += [(cx + (mx - cx) / n * t, cy + (my - cy) / n * t) for t in range(0, 2001, 50)]   # hacia dentro hasta dar con dato
    dflt = catalog.default_observer(ctx.cfg, key)
    for px, py in pts:
        if _ground(ref, px, py) is not None:
            break
    else:
        if dflt is None:
            return None
        px, py = _project(*dflt)
        kind = "default_observer"
        if _ground(ref, px, py) is None:
            return None
    lat2, lon2 = (float(v) for v in stereo_inverse(np.float64(px), np.float64(py)))
    dist = _gc_km(lat_deg, float(normalize_lon(lon_deg_e)), lat2, lon2)
    if not paired and dist > max_km:
        return None
    why = ("observador por defecto del recorte (marcador, no punto óptimo)" if kind == "default_observer"
           else "punto cubierto más cercano al pedido (no optimizado)")
    return SnapCandidate(lat2, lon2, px, py, key, dist, kind, reason=why)


def _snap_limit_km(ctx: AppContext, radius_km: float) -> float:
    c = ctx.cfg.get("snap", {})
    return radius_km * float(c.get("radius_factor", 1.15)) + float(c.get("margin_km", 1.0))


@lru_cache(maxsize=1)
def _gazetteer_df():
    from lsi.data import gazetteer as gz   # import perezoso: solo el snap lo necesita
    return gz.load_gazetteer()


def feature_radius_km(ctx: AppContext, gazetteer_id: Optional[int] = None, site_id: Optional[str] = None,
                      explicit: Optional[float] = None) -> float:
    """Radio (km) del rasgo para acotar el snap «best»: ``explicit``; si no, diámetro/2 del gazetteer; si no, el del sitio curado
    (``simulation.json: snap.site_radius_km``) o ``snap.default_radius_km`` (10 km, [sup])."""
    if explicit is not None and explicit > 0:
        return float(explicit)
    if gazetteer_id is not None:
        try:
            d = float(_gazetteer_df().loc[lambda df: df["feature_id"] == gazetteer_id, "diameter_km"].iloc[0])
            if math.isfinite(d) and d > 0:
                return d / 2.0
        except Exception:   # sin gazetteer o id desconocido: el defecto, nunca un fallo del análisis
            pass
    c = ctx.cfg.get("snap", {})
    v = c.get("site_radius_km", {}).get(site_id)
    return float(v) if isinstance(v, (int, float)) and v > 0 else float(c.get("default_radius_km", 10.0))


def _best_snap(ctx: AppContext, near: SnapCandidate, lat_deg: float, lon_deg_e: float, profile_id: Optional[str],
               mission_days: Optional[float], radius_km: Optional[float] = None) -> SnapCandidate:
    """Mejor punto del mapa de idoneidad precalculado del DEM de ``near`` para el perfil y la duración, LIMITADO AL ENTORNO DEL
    RASGO si se da ``radius_km``: el mejor (por rango del mapa) a ≤ radio·1,15 + 1 km del centro (``simulation.json: snap``).
    Si ninguno cae dentro, el punto cubierto más cercano CON AVISO («ningún punto recomendable dentro del rasgo»). Sin mapa (o
    sin duración de misión) devuelve ``near`` con el motivo y SIN inventar nada."""
    pid = profile_id or SNAP_DEFAULT_PROFILE
    prof = profiles_from_config(ctx.cfg["score"]).get(pid)
    days = mission_days if mission_days is not None else (prof.mission_days if prof is not None else None)
    bp = None if days is None or not days > 0 else suitability_map.best_points(_cache_dir(ctx), near.dem_key, pid, days)
    fall = lambda why: dataclasses.replace(near, reason=f"{why}; se usa el {near.reason}")   # noqa: E731
    if bp is None:
        return fall(f"sin mapa de idoneidad precalculado para {near.dem_key} · «{pid}»"
                    + ("" if days else " (el perfil no tiene duración de misión)")
                    + f" (python scripts/precompute_suitability.py --profile {pid} --duration 14)")
    ref = ctx.dem_refs[near.dem_key]
    lon0 = float(normalize_lon(lon_deg_e))
    ranking, chosen = [], None
    lim = None if radius_km is None else _snap_limit_km(ctx, radius_km)
    top1_d = None
    for t in bp["top"]:
        px, py = float(t["x_m"]), float(t["y_m"])
        if _ground(ref, px, py) is None:
            continue   # el mapa no se corresponde con este DEM (p. ej. cambió): no se usa un punto sin dato
        e = SnapRankEntry(int(t["rank"]), float(t["lat_deg"]), float(t["lon_deg_e"]), str(t["best_start_utc"]), float(t["f_sun"]),
                          float(t["d_max_h"]), float(t["score"]), str(t["gate_status"]),
                          _gc_km(lat_deg, lon0, float(t["lat_deg"]), float(t["lon_deg_e"])))
        ranking.append(e)
        top1_d = e.distance_km if top1_d is None else top1_d
        if chosen is None and (lim is None or e.distance_km <= lim):
            chosen = (t, e)
    if not ranking:
        return fall(f"el mapa precalculado de {near.dem_key} no coincide con el DEM")
    if chosen is None:   # ningún candidato del mapa dentro del rasgo: el más cercano, avisando
        off = near.distance_km - radius_km
        return dataclasses.replace(
            near, feature_radius_km=radius_km, edge_offset_km=off, inside_feature=False, ranking=tuple(ranking),
            reason=(f"ningún punto recomendable dentro del rasgo (radio {radius_km:.2f} km; el mejor punto del mapa queda a "
                    f"{top1_d:.2f} km del centro, {top1_d - radius_km:.2f} km fuera del borde, y se descarta); se usa el "
                    f"{near.reason}, a {near.distance_km:.2f} km del centro ({abs(off):.2f} km {'dentro del' if off < 0 else 'fuera del'} borde)"))
    t, e = chosen
    dur = bp["duration_days"]
    same = abs(dur - days) < 1e-9
    off = None if radius_km is None else e.distance_km - radius_km
    where = ("" if radius_km is None else
             f" DENTRO del rasgo: a {e.distance_km:.2f} km del centro (radio {radius_km:.2f} km), {abs(off):.2f} km dentro del borde"
             if off < 0 else
             f" DENTRO del entorno del rasgo (en el borde, dentro del margen): a {e.distance_km:.2f} km del centro (radio "
             f"{radius_km:.2f} km), {off:.2f} km fuera del borde")
    skipped = ("" if e.rank == ranking[0].rank or radius_km is None else
               f"; el TOP-{ranking[0].rank} del mapa queda a {top1_d:.2f} km del centro ({top1_d - radius_km:.2f} km fuera del borde) "
               f"y se descarta por estar fuera del rasgo")
    why = (f"mejor punto{where or ' del DEM'} {near.dem_key} para «{pid}» y {days:g} d"
           + ("" if same else f" (mapa precalculado de {dur:g} d, el más cercano)")
           + f": TOP-{e.rank} del mapa de idoneidad (score {e.score:.0f}, f_sol {e.f_sun:.2f}, D_max {e.d_max_h:.0f} h, puertas {e.gate_status}); "
           f"mejor inicio {e.best_start_utc}{skipped}. Alternativa: punto cubierto más cercano, a {near.distance_km:.2f} km del pedido")
    return SnapCandidate(e.lat_deg, e.lon_deg_e, float(t["x_m"]), float(t["y_m"]), near.dem_key, e.distance_km, "best", reason=why,
                         best_start_utc=e.best_start_utc, ranking=tuple(ranking), nearest=near, duration_days=dur,
                         feature_radius_km=radius_km, edge_offset_km=off, inside_feature=None if radius_km is None else True,
                         map_rank=e.rank)


def snap_candidate(ctx: AppContext, lat_deg: float, lon_deg_e: float, *, site_id: Optional[str] = None,
                   max_km: float = SNAP_MAX_KM, prefer: str = "nearest", profile_id: Optional[str] = None,
                   mission_days: Optional[float] = None, feature_radius_km: Optional[float] = None) -> Optional[SnapCandidate]:
    """Punto del DEM al que enganchar una petición cuyo punto cae fuera. None si no hay DEM razonable.

    ``prefer="nearest"`` (defecto, comportamiento anterior): el punto cubierto más cercano (o el ``dem_default_observer``).
    ``prefer="best"``: el MEJOR PUNTO del DEM para ``profile_id`` (defecto ``lander_solar_no_rhu``) y ``mission_days`` (defecto
    la del perfil): TOP-1 del mapa de idoneidad precalculado en ``data/processed/suitability/``, con su mejor fecha de inicio
    (``best_start_utc``), el ranking (``ranking``) y el punto más cercano como alternativa (``nearest``). Sin mapa precalculado
    cae al más cercano con el motivo en ``reason`` (nunca falla ni inventa). Sitio curado con ``dem_prefix`` → solo su DEM y
    sin límite de distancia; en otro caso cualquier DEM a ≤ ``max_km``. La UI puede llamarla para OFRECER el ajuste.
    ``feature_radius_km`` (km, con ``prefer="best"``): acota el mejor punto al entorno del rasgo (≤ radio·1,15 + 1 km del centro;
    ver ``feature_radius_km()`` para el radio de un rasgo/sitio); None = TOP-1 de todo el mapa (comportamiento anterior).
    ``resolve_observer`` usa "best" solo para rasgos del buscador y sitios curados (no para coordenadas exactas del usuario).
    """
    if prefer not in ("best", "nearest"):
        raise ValueError(f"prefer debe ser 'best' o 'nearest', no {prefer!r}")
    near = _nearest_snap(ctx, lat_deg, lon_deg_e, site_id, max_km)
    if near is None or prefer == "nearest":
        return near
    return _best_snap(ctx, near, lat_deg, lon_deg_e, profile_id, mission_days, feature_radius_km)


def _label(ctx: AppContext, site_id: Optional[str], lat: float, lon: float) -> str:
    site = next((s for s in ctx.sites if s.id == site_id), None)
    return site.name if site else f"{lat:.4f}°, {lon:.4f}°E"


def resolve_observer(ctx: AppContext, lat_deg: float, lon_deg_e: float, height_m: float, *,
                     site_id: Optional[str] = None, force_smooth_sphere: bool = False,
                     gazetteer_id: Optional[int] = None, snap_to_dem: Optional[bool] = None,
                     snap_max_km: float = SNAP_MAX_KM, prefer: Optional[str] = None,
                     profile_id: Optional[str] = None, mission_days: Optional[float] = None,
                     feature_radius_km_: Optional[float] = None, force_far_field: bool = False
                     ) -> tuple[ObserverPoint, tuple[ScientificWarning, ...]]:
    """DEM si hay cobertura (con margen de borde); si no, 'snap_to_dem' (rasgo del buscador o sitio curado cuyo punto
    queda fuera pero hay DEM cerca), ETIQUETADO (``snapped_from``, ``snap_distance_km``, ``snap_kind``, ``snap_reason``,
    ``best_start_utc``, ``snap_ranking``, ``snap_alternative``) y con aviso; si no hay DEM razonable, esfera lisa con aviso.

    ``snap_to_dem``: None = auto (solo gazetteer/sitio curado), False = nunca. ``prefer``: "best" = mejor punto del DEM para
    ``profile_id`` y ``mission_days`` (TOP-1 del mapa de idoneidad; ver ``snap_candidate``), "nearest" = el más cercano;
    None = "best" para rasgos del buscador/sitios curados y "nearest" para coordenadas personalizadas exactas.
    El mejor punto se limita al entorno del rasgo (radio = diámetro/2 del gazetteer, ``feature_radius_km_`` o el del sitio
    curado; ``simulation.json: snap``): ``snap_feature_radius_km``, ``snap_edge_offset_km``, ``snap_inside_feature`` y
    ``snap_map_rank`` del ``ObserverPoint`` lo describen y ``snap_reason`` lo dice en español.
    Lanza ``ObserverNearEdgeError`` (borde, sin snap) y ``NodataAtObserverError`` (nodata en el punto).
    """
    lon = float(normalize_lon(lon_deg_e))
    label = _label(ctx, site_id, lat_deg, lon)
    x, y = _project(lat_deg, lon)

    def sphere() -> tuple[ObserverPoint, tuple[ScientificWarning, ...]]:
        o = ObserverPoint(lat_deg, lon, x, y, height_m, HorizonMode.SMOOTH_SPHERE, site_id=site_id, label=label)
        return o, (_w(WarningCode.NO_DEM_SMOOTH_SPHERE, Severity.WARNING),)

    def far_or_sphere() -> tuple[ObserverPoint, tuple[ScientificWarning, ...]]:
        """Dentro del DEM polar de 80 m (lat ≤ 80°S): FAR_FIELD; fuera (o sin el fichero): esfera lisa."""
        z = _far_ground(_raw(ctx), lat_deg, x, y, ctx.cfg["horizon"]["r_max_m"])
        if z is None:
            return sphere()
        o = ObserverPoint(lat_deg, lon, x, y, height_m, HorizonMode.FAR_FIELD, ground_z_m=z, site_id=site_id, label=label)
        return o, (_w(WarningCode.FAR_FIELD_80M, Severity.WARNING, "far_field_80m", far_field_warning_text()),)

    if force_smooth_sphere:
        return sphere()
    if force_far_field or not ctx.dem_refs:
        return far_or_sphere()
    margin = float(ctx.cfg["observer"].get("edge_margin_px", 2)) * 5.0
    ref = loader.find_dem_for_point(ctx.dem_refs, x, y, margin)
    if ref is not None:
        z = _ground(ref, x, y)
        if z is None:
            raise NodataAtObserverError(f"Sin dato válido del DEM {ref.key} en ({lat_deg:.4f}°, {lon:.4f}°E).")
        return ObserverPoint(lat_deg, lon, x, y, height_m, HorizonMode.DEM, ground_z_m=z, dem_key=ref.key,
                             site_id=site_id, label=label), ()
    site = next((s for s in ctx.sites if s.id == site_id), None)
    feature = gazetteer_id is not None or (site is not None and site.has_dem)
    auto = snap_to_dem if snap_to_dem is not None else feature
    eff = prefer or ("best" if feature else "nearest")
    rad = feature_radius_km(ctx, gazetteer_id, site_id, feature_radius_km_) if auto and eff == "best" else None
    cand = snap_candidate(ctx, lat_deg, lon, site_id=site_id, max_km=snap_max_km, prefer=eff, profile_id=profile_id,
                          mission_days=mission_days, feature_radius_km=rad) if auto else None
    if cand is None:
        if loader.find_dem_for_point(ctx.dem_refs, x, y, 0.0) is not None:
            raise ObserverNearEdgeError(f"El punto ({lat_deg:.4f}°, {lon:.4f}°E) está a < {margin:g} m del borde del DEM.")
        return far_or_sphere()
    sref = ctx.dem_refs[cand.dem_key]
    z = _ground(sref, cand.x_m, cand.y_m)
    what = "centro del rasgo" if gazetteer_id is not None else "punto pedido"
    tag = ("mejor punto dentro del rasgo, a " if cand.inside_feature else "mejor punto del DEM, a ") if cand.kind == "best" else ""
    alt = None if cand.nearest is None else (cand.nearest.lat_deg, cand.nearest.lon_deg_e, cand.nearest.distance_km)
    obs = ObserverPoint(cand.lat_deg, cand.lon_deg_e, cand.x_m, cand.y_m, height_m, HorizonMode.DEM, ground_z_m=z,
                        dem_key=cand.dem_key, site_id=site_id,
                        label=f"{label} [snap_to_dem: {tag}{cand.distance_km:.2f} km del {what}]",
                        snap_distance_km=cand.distance_km, snapped_from=(lat_deg, lon), snap_kind=cand.kind,
                        snap_reason=cand.reason, best_start_utc=cand.best_start_utc, snap_ranking=cand.ranking,
                        snap_alternative=alt, snap_feature_radius_km=cand.feature_radius_km,
                        snap_edge_offset_km=cand.edge_offset_km, snap_inside_feature=cand.inside_feature,
                        snap_map_rank=cand.map_rank)
    txt = (f"Ajuste snap_to_dem: el {what} ({lat_deg:.4f}°, {lon:.4f}°E) queda fuera del DEM {cand.dem_key}; se evalúa "
           f"({cand.lat_deg:.4f}°, {cand.lon_deg_e:.4f}°E), a {cand.distance_km:.2f} km del {what}: {cand.reason}. Los resultados "
           f"valen para ESE punto, no para el centro del rasgo.")
    ws = [_w(WarningCode.CURATED_COORDS_OUTSIDE_DEM, Severity.WARNING, f"snap_to_dem;distance_km={cand.distance_km:.3f}", txt)]
    if gazetteer_id is not None:
        ws.append(_w(WarningCode.GAZETTEER_COORDS_APPROX, Severity.INFO))
    return obs, tuple(ws)


# ----------------------------------------------------------------------------------------------- tiempo
def _utc_et(s: str) -> float:
    return spice_engine.utc_to_et(s)   # DateOutOfRangeError fuera de 1900-02…2050-12-30


def _midnights(et0: float, et1: float) -> list[float]:
    """ET de las medianoches UTC estrictamente dentro de (et0, et1). 86400 s no vale con segundos intercalares."""
    d = date.fromisoformat(spice_engine.et_to_utc(et0)[:10]) + timedelta(days=1)
    out = []
    while True:
        try:
            e = spice_engine.utc_to_et(d.isoformat() + "T00:00:00")
        except DateOutOfRangeError:
            break
        if e >= et1:
            break
        out.append(e)
        d += timedelta(days=1)
    return out


def daily_table_utc(tl) -> list[dict]:
    """Por día UTC REAL (medianoche a medianoche; el primero y el último pueden ser parciales): iluminación media y horas
    de Sol / Tierra / solape. Sustituye a ``metrics.daily_table`` (que agrupa en bloques de 86400 s desde ``tl.et0``)."""
    edges = np.array([tl.et0, *_midnights(tl.et0, tl.et1), tl.et1])
    lo, hi = edges[:-1], edges[1:]

    def hours(ws) -> np.ndarray:
        w = mt.intervals(ws)
        if len(w) == 0:
            return np.zeros(len(lo))
        cov = np.minimum(w[None, :, 1], hi[:, None]) - np.maximum(w[None, :, 0], lo[:, None])
        return np.clip(cov, 0.0, None).sum(axis=1) / 3600.0

    t, f = tl.series.et, tl.series.sun.f
    cum = np.concatenate(([0.0], np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(t))))
    illum = (np.interp(hi, t, cum) - np.interp(lo, t, cum)) / (hi - lo)
    hs, he, ho = hours(tl.sun), hours(tl.earth), hours(tl.overlap)
    hl = hours(tl.link.link) if tl.link is not None else None   # horas de ENLACE (distintas de ``earth_hours`` = geometría)
    return [{"day": i, "day_utc": spice_engine.et_to_utc(lo[i])[:10], "start_et": float(lo[i]), "end_et": float(hi[i]),
             "mean_illumination": float(illum[i]), "sun_hours": float(hs[i]), "earth_hours": float(he[i]),
             "overlap_hours": float(ho[i]), **({} if hl is None else {"link_hours": float(hl[i])})} for i in range(len(lo))]


# ----------------------------------------------------------------------------------------------- potencia
@dataclass(eq=False)
class PowerRun:
    """Potencia de un panel+montaje sobre un ``AnalysisResult`` ya calculado (varios por análisis: ``run_power``)."""
    panel_id: str
    mounting: Optional[MountingSpec]
    series: Optional[PowerSeries] = None
    summary: Optional[PowerSummary] = None
    battery: Optional[BatteryResult] = None
    warnings: tuple = ()
    error: Optional[str] = None      # PanelNotCalculableError / montaje incompleto: panel no calculable, no un 0


def _mission(ctx: AppContext, profile_id: Optional[str]) -> Optional[MissionProfile]:
    """Perfil de misión de panels.json. Sin pendiente de aterrizaje propia (rover) se hereda la del lander solar
    (la nota del JSON: «el rover llega en un lander»). ``max_landing_slope_deg.value`` ya lleva el ``design``."""
    mp = ctx.panels.profiles.get(profile_id) if profile_id else None
    if mp is None:
        return None
    t = mp.thresholds.get("max_landing_slope_deg")
    lander = ctx.panels.profiles.get("lander_solar_no_rhu")
    if (t is None or t.value is None) and lander is not None and "max_landing_slope_deg" in lander.thresholds \
            and mp.id not in ("dte_comms",):
        return MissionProfile(mp.id, mp.label, {**mp.thresholds, "max_landing_slope_deg": lander.thresholds["max_landing_slope_deg"]})
    return mp


def _day0(et0: float) -> float:
    return spice_engine.utc_to_et(spice_engine.et_to_utc(et0)[:10] + "T00:00:00")


@dataclass(eq=False)
class _SunNodes:
    et: np.ndarray
    track: object
    f: np.ndarray


def _sun_nodes(ctx: AppContext, res: AnalysisResult, vp) -> _SunNodes:
    """Sol y f_sun en la rejilla + los instantes de evento refinados (la integración no pierde los bordes de ventana)."""
    nodes = pn.integration_nodes(res.sky.et, [res.timeline.sun])
    o = res.observer
    tr = spice_engine.body_track(nodes, o.lat_deg, o.lon_deg_e, Body.SUN, o.height_m)
    f = disc_fraction(tr.el_deg, tr.az_deg, tr.radius_deg, res.horizon, "lb", vp.n_slices, vp.limb_darkening_u)
    return _SunNodes(nodes, tr, f)


def _power_one(ctx: AppContext, res: AnalysisResult, sn: _SunNodes, panel_id: str, mounting: Optional[MountingSpec],
               degradation: float, dust_loss: float, battery: Optional[BatteryParams], profile_id: str) -> PowerRun:
    cfg = ctx.cfg
    panel = pn.get_panel(ctx.panels, panel_id)
    mnt = mounting or MountingSpec(panel.mounting_default)
    th = cfg["power"]["thermal"]
    pp = PowerParams(panel_id=panel_id, mounting=mnt, degradation=degradation, dust_loss=dust_loss,
                     f_shadow=float(cfg["power"].get("f_shadow", 1.0)), t_ambient_k=float(th["t_ambient_k"]),
                     t_min_valid_k=float(th["t_min_valid_k"]), limb_darkening_u=float(cfg["visibility"]["limb_darkening_u"]))
    series = pn.relative_power(sn.et, sn.track, sn.f, panel, pp, ctx.panels)
    mp = _mission(ctx, profile_id)
    thr = mp.thresholds.get("min_useful_power_fraction") if mp else None
    useful = float(thr.value) if thr is not None and thr.value is not None else float(cfg["power"]["useful_power_fraction_default"])
    summary = pn.summarize_power(series, panel, useful, ctx.panels, day_origin_et=_day0(res.timeline.et0))
    # banda a incidencia rasante (IAM × T_amb × parámetros estimados; regla en ``panels.BAND_RULE``): media sobre el periodo
    rng = th.get("t_ambient_range_k")
    det = pn.power_band_detail(series, panel, pp, ctx.panels, t_ambient_range_k=None if rng is None else tuple(rng))
    span = float(series.et[-1] - series.et[0])
    mean = lambda b: (pn._trapz(series.et, b[0]) / span, pn._trapz(series.et, b[1]) / span) if span > 0 else None   # noqa: E731
    summary = dataclasses.replace(
        summary, e_rel_band=mean(det["combined"]),
        e_rel_band_components={k: mean(v) for k, v in det.items() if k != "combined" and v is not None},
        band_note=pn.BAND_RULE + f" T_amb nominal {pp.t_ambient_k:g} K «a verificar»; modelo de IAM usado: {summary.iam_model}.")
    ws = [_w(WarningCode.POWER_IS_ESTIMATE, Severity.WARNING)]
    if any(v == "a_verificar" for v in panel.confidence.values()):
        ws.append(_w(WarningCode.PANEL_UNVERIFIED, Severity.WARNING, panel_id))
    if series.t_clamped.any():   # solo con potencia > 0 y fuera del rango de validez del coeficiente (panels.json)
        rng = panel.temp_valid_range_c
        t_ext = series.t_panel_k[series.t_clamped]
        what = (f"fuera de [{rng[0]:g}, {rng[1]:g}] °C" if rng is not None else f"por debajo de {pp.t_min_valid_k - 273.15:.0f} °C")
        ws.append(_w(WarningCode.COLD_EXTRAPOLATION, Severity.WARNING,
                     f"t_panel {t_ext.min() - 273.15:.0f}..{t_ext.max() - 273.15:.0f} °C",
                     f"Coeficiente térmico del panel extrapolado {what} (T del panel entre {t_ext.min() - 273.15:.0f} y "
                     f"{t_ext.max() - 273.15:.0f} °C con potencia > 0): la eficiencia está acotada por el tope de frío y no hay datos de "
                     f"validación fuera de ese rango; la potencia en esos instantes es una estimación sin respaldo."))
    if np.any((series.theta_deg > 80.0) & (series.theta_deg < 90.0) & (series.f_sun > 0)):
        ws.append(_w(WarningCode.IAM_GRAZING_UNCERTAIN, Severity.INFO))
    bat = pn.simulate_battery(series.et, series.p_rel, battery) if battery is not None else None
    return PowerRun(panel_id, mnt, series, summary, bat, tuple(ws))


def run_power(ctx: AppContext, result: AnalysisResult,
              specs: Sequence[tuple[str, Optional[MountingSpec]]], battery: Optional[BatteryParams] = None,
              degradation: Optional[float] = None, dust_loss: Optional[float] = None) -> list[PowerRun]:
    """Potencia para VARIOS paneles/montajes del catálogo sobre un análisis ya hecho (reutiliza Sol, horizonte y ventanas).

    Un panel no calculable (α/ε/η a verificar) o un montaje incompleto devuelve ``PowerRun.error``, no un 0.
    """
    sn = _sun_nodes(ctx, result, catalog.visibility_params(ctx.cfg))
    deg = result.request.degradation if degradation is None else degradation
    dust = result.request.dust_loss if dust_loss is None else dust_loss
    out = []
    for pid, mnt in specs:
        try:
            out.append(_power_one(ctx, result, sn, pid, mnt, deg, dust, battery, result.request.score_profile_id))
        except (PanelNotCalculableError, LSIError) as e:
            out.append(PowerRun(pid, mnt, error=str(e)))
    return out


# ----------------------------------------------------------------------------------------------- análisis
def _earth_ref_f(observer, sky, hp, vp, horizon, vis, margin_deg: float = 0.0) -> np.ndarray:
    """f_Tierra con H ≡ H_esfera(h) sobre la rejilla (mismo motor, §7.1). En esfera lisa es la propia serie.
    ``margin_deg`` = margen de elevación del enlace DTE (horizonte elevado ese margen, también en la referencia).

    Se mide sobre la rejilla gruesa (sin refinar): la referencia no necesita 1 s. Serie y no escalar porque cada ventana
    de misión necesita su propia referencia (``_ref_fraction``). Caché en memoria por (punto, periodo, parámetros).
    """
    if horizon.mode is HorizonMode.SMOOTH_SPHERE:
        return vis.earth.f if not margin_deg else link_fraction(sky.earth, horizon, vp, margin_deg)
    key = (round(observer.lat_deg, 6), round(observer.lon_deg_e, 6), hp, float(sky.et[0]), float(sky.et[-1]),
           len(sky.et), vp.earth_f_thr, vp.n_slices, sky.kernel_hash, float(margin_deg))
    with _LOCK:
        if key in _F_EARTH_REF:
            return _F_EARTH_REF[key]
    sph = hz_mod.smooth_sphere_result(observer, hp)
    f = disc_fraction(sky.earth.el_deg - margin_deg, sky.earth.az_deg, sky.earth.radius_deg, sph, "lb", vp.n_slices, 0.0)
    with _LOCK:
        if len(_F_EARTH_REF) > 32:
            _F_EARTH_REF.clear()
        _F_EARTH_REF[key] = f
    return f


def _ref_fraction(et: np.ndarray, f: np.ndarray, thr: float) -> float:
    """Fracción de [et[0], et[-1]] con la Tierra de la serie ``f`` sobre ``thr`` (ventanas con cruce interpolado)."""
    ws = find_windows(et, f, thr, "earth_ref", "f_earth(H_esfera)")
    return mt.total_duration(mt.intervals(ws), et[0], et[-1]) / (et[-1] - et[0])


def _link_context(req: AnalysisRequest, profile, et: np.ndarray) -> Optional["gs.LinkContext"]:
    """Contexto de enlace (red + margen + cobertura UNA vez por rejilla) o None si ``req.link_network`` es None (geometría)."""
    if req.link_network is None:
        return None
    margin = req.min_earth_elevation_deg
    if margin is None:
        margin = profile.min_earth_elevation_deg if profile.min_earth_elevation_deg is not None else 0.0
    if margin < 0:
        raise InvalidParameterError(f"min_earth_elevation_deg debe ser ≥ 0, recibido {margin!r}")
    try:
        return gs.make_link_context(et, req.link_network, float(margin), custom=req.link_custom,
                                    station_min_elevation_deg=req.link_station_min_elevation_deg,
                                    link_direction=req.link_direction)
    except ValueError as e:
        raise InvalidParameterError(str(e)) from e


def _sigma_h90(ctx, observer, hp, far) -> float:
    """σh90 (°): p90 del movimiento del horizonte al desplazar el DEM ±toterr (k=1, error totalmente correlado, hipótesis
    conservadora). Dos horizontes con rejilla gruesa (``score.confidence.sigma_h``: 1°, 10 m, campo lejano 80 m: la de la
    calibración de revision-geologica §2), con caché en disco. NaN si no hay toterr."""
    c = ctx.cfg["score"]["confidence"].get("sigma_h", {})
    ref = ctx.dem_refs[observer.dem_key]
    try:
        sigma = _layer(ref, DemLayer.TOTERR)
    except DemNotFoundError:
        return math.nan
    hz = dataclasses.replace(hp, az_step_deg=float(c.get("az_step_deg", 1.0)), radial_step_m=float(c.get("radial_step_m", 10.0)),
                             compute_upper_bound=False)
    fs = float(c.get("far_step_m", 80.0)) if far is not None else None
    surf, k = _layer(ref, DemLayer.SURF), float(c.get("k_sigma", 1.0))
    hp_, hm_ = (hz_mod.compute_horizon(surf, observer, hz, sigma, sg, k, _cache_dir(ctx), far=far, far_step_m=fs)
                for sg in (+1, -1))
    return horizon_sigma_p90(hp_.h_lb_deg, hm_.h_lb_deg)


def _dem_extras(ctx, observer, horizon, window, far, hp):
    """Pendiente en la huella (slp del PGDA), DemConfidence (con σh90 y c_hz) y soporte c_sup = min(c_gap, c_err, c_hz)
    (revision-geologica §2: sustituye a la fracción de píxeles ldec>0, ~9 % en todo el DEM y por tanto sin poder de
    discriminación: «alta» era inalcanzable)."""
    t, dc = ctx.cfg["terrain"], ctx.cfg["terrain"]["dem_confidence"]
    ref, x, y = ctx.dem_refs[observer.dem_key], observer.x_m, observer.y_m
    r_foot = float(t["footprint_radius_m"])
    slope, ws = None, []
    try:
        try:
            slp = _small(ref, DemLayer.SLP, x, y, r_foot + 30.0)
        except DemNotFoundError:
            slp = None
        slope = slope_mod.footprint_slope(window, x, y, r_foot, float(t["slope_percentile"]), slp, float(t["slope_baseline_m"]))
    except ObserverOutsideDemError:
        ws.append(_w(WarningCode.OBSERVER_NEAR_EDGE, Severity.WARNING, "la huella de pendiente no cabe en el DEM"))
    dem_c, c_sup = None, 0.0
    try:
        rs = float(dc["support_radius_m"])
        ldec, toterr = (_small(ref, lyr, x, y, rs + 100.0) for lyr in (DemLayer.LDEC, DemLayer.TOTERR))
        dem_c = dem_confidence(ldec, toterr, x, y, horizon, ctx.cfg)
        sh = _sigma_h90(ctx, observer, hp, far)
        cs = ctx.cfg["score"]["confidence"].get("sigma_h", {})
        c_sup, c_hz = support_confidence(dem_c, sh, float(cs.get("hi_deg", 0.5)), float(cs.get("lo_deg", 0.1)))
        dem_c = dataclasses.replace(dem_c, sigma_h90_deg=None if sh != sh else sh, c_hz=c_hz)
    except DemNotFoundError:
        pass   # sin ldec/toterr: confianza del DEM no evaluable (c_sup = 0: nunca un valor plausible inventado)
    return slope, dem_c, c_sup, ws


SLOPE_SCALES_M = (50.0, 100.0)   # huella de LSI y escala de sitio de NASA (revision-geologica §2)


def _landing_limit(ctx: AppContext, profile_id: str) -> Optional[float]:
    mp = _mission(ctx, profile_id)
    t = None if mp is None else mp.thresholds.get("max_landing_slope_deg")
    return None if t is None or t.value is None else float(t.value)


def _slope_scales(ctx: AppContext, observer: ObserverPoint, profile_id: str) -> tuple[dict, float, bool]:
    """Pendiente en huella a r = 50 y 100 m (mismo ``footprint_slope`` que el veredicto), distancia al borde del DEM y si la
    huella de 100 m lo roza. Ventana pequeña de ``slp`` (o de ``surf`` si falta): no deriva la pendiente de todo el recorte."""
    t = ctx.cfg["terrain"]
    ref, x, y = ctx.dem_refs[observer.dem_key], observer.x_m, observer.y_m
    x0, y0, x1, y1 = ref.bounds_xy_m
    edge_d = float(min(x - x0, x1 - x, y - y0, y1 - y))
    base, lim, out = float(t["slope_baseline_m"]), _landing_limit(ctx, profile_id), {}
    for r in SLOPE_SCALES_M:
        touches = edge_d < r + base
        try:
            surf = _small(ref, DemLayer.SURF, x, y, r + 30.0)
            try:
                slp = _small(ref, DemLayer.SLP, x, y, r + 30.0)
            except DemNotFoundError:
                slp = None
            st = slope_mod.footprint_slope(surf, x, y, r, float(t["slope_percentile"]), slp, base)
            above = None
            if lim is not None and st.n_pixels:
                above = 100.0 - slope_mod.footprint_area_below_pct(surf, x, y, (lim,), r, slp, base)[lim]
            ok = st.n_pixels > 0
            out[r] = SlopeScale(r, st.mean_deg if ok else None, st.percentile_deg if ok else None, st.max_deg if ok else None,
                                above, lim, st.n_pixels, st.source, touches)
        except (ObserverOutsideDemError, DemNotFoundError):
            out[r] = SlopeScale(r, None, None, None, None, lim, 0, "none", True)
    return out, edge_d, edge_d < SLOPE_SCALES_M[-1] + base


def run_analysis(ctx: AppContext, req: AnalysisRequest) -> AnalysisResult:
    """Flujo completo §2; solo calcula lo que pide la petición (panel_id / with_uncertainty). Score siempre."""
    cfg = ctx.cfg
    hp = catalog.horizon_params(cfg, req.observer_height_m)
    vp = catalog.visibility_params(cfg)
    step_eff = effective_step_s(cfg, req.step_s)
    tp = catalog.timeline_params(cfg, step_eff)
    et0, et1 = _utc_et(req.start_utc), _utc_et(req.end_utc)
    if not et1 > et0:
        raise InvalidParameterError(f"Periodo vacío o invertido: {req.start_utc} → {req.end_utc}")
    profiles = profiles_from_config(cfg["score"])   # con mission_days, límite de noche propio y earth_floor del perfil
    if req.score_profile_id not in profiles:
        raise InvalidParameterError(f"Perfil de score desconocido '{req.score_profile_id}'; válidos: {sorted(profiles)}")

    obs, warns = resolve_observer(ctx, req.lat_deg, req.lon_deg_e, req.observer_height_m, site_id=req.site_id,
                                  force_smooth_sphere=req.force_smooth_sphere, force_far_field=req.force_far_field,
                                  gazetteer_id=req.gazetteer_id,
                                  snap_to_dem=req.snap_to_dem, prefer=req.snap_prefer, profile_id=req.score_profile_id,
                                  feature_radius_km_=req.feature_radius_km,
                                  mission_days=req.mission_days if req.mission_days is not None
                                  else profiles[req.score_profile_id].mission_days)
    warns = list(warns)
    cdir, raw = _cache_dir(ctx), _raw(ctx)

    # --- horizonte
    window = far = None
    if obs.mode is HorizonMode.DEM:
        window = _layer(ctx.dem_refs[obs.dem_key], DemLayer.SURF)
        far = far_field_for(raw, obs.x_m, obs.y_m, hp.r_max_m)
        horizon = hz_mod.compute_horizon(window, obs, hp, cache_dir=cdir, far=far)
    elif obs.mode is HorizonMode.FAR_FIELD:   # fuera de los recortes de 5 m: SOLO el 80 m (horizonte aproximado, sin terreno fino)
        far = far_field_for(raw, obs.x_m, obs.y_m, hp.r_max_m)
        horizon = hz_mod.compute_horizon_far_field(far, obs, hp, cache_dir=cdir)
    else:
        horizon = hz_mod.smooth_sphere_result(obs, hp)

    # --- cielo, visibilidad, ventanas, métricas
    et = spice_engine.et_grid(et0, et1, tp.step_s)
    if et1 - et[-1] > 1e-6:
        et = np.append(et, et1)   # el periodo pedido se cubre entero aunque no sea múltiplo del paso
    sky = spice_engine.sky_series(et, obs.lat_deg, obs.lon_deg_e, obs.height_m)
    vis = visibility_series(sky, horizon, vp)
    link_ctx = _link_context(req, profiles[req.score_profile_id], et)
    tl = run_timeline(sky, horizon, vp, tp, vis, link=link_ctx)
    metrics = compute_metrics(tl, sky, horizon, vp)

    res = AnalysisResult(request=req, observer=obs, horizon=horizon, sky=sky, timeline=tl, metrics=metrics,
                         warnings=(), kernels=ctx.kernels, daily=tuple(daily_table_utc(tl)), link=tl.link)
    if link_ctx is not None:   # cobertura de red por sentido (recepción / transmisión / ambos): misma elevación de la Luna, otro umbral
        res.network_fraction_by_direction = link_ctx.coverage.fraction_by_direction()
    if window is not None:
        res.dem_meta = window.meta

    # --- incertidumbre
    if req.with_uncertainty and obs.mode is not HorizonMode.FAR_FIELD:   # en 80 m no hay σz (TOTERR) ni escenarios de DEM
        sigma = None
        if window is not None:
            try:
                sigma = _layer(ctx.dem_refs[obs.dem_key], DemLayer.TOTERR)
            except DemNotFoundError:
                sigma = None
        res.uncertainty = run_uncertainty(window, sigma, obs, horizon, sky, vp, tp, hp,
                                          catalog.uncertainty_params(cfg), metrics, far=far, cache_dir=cdir, link=link_ctx)

    # --- terreno
    c_sup = 0.0
    if window is not None:
        res.slope, res.dem_confidence, c_sup, ws = _dem_extras(ctx, obs, horizon, window, far, hp)
        warns += ws
        sc_, res.dem_edge_distance_m, res.footprint_touches_dem_edge = _slope_scales(ctx, obs, req.score_profile_id)
        res.slope_r50, res.slope_r100 = sc_[50.0], sc_[100.0]

    # --- potencia
    if req.panel_id:
        run = _power_one(ctx, res, _sun_nodes(ctx, res, vp), req.panel_id, req.mounting, req.degradation, req.dust_loss,
                         req.battery, req.score_profile_id)
        res.power, res.power_summary, res.battery = run.series, run.summary, run.battery
        warns += run.warnings
    elif req.battery is not None:
        raise InvalidParameterError("La batería necesita panel_id")

    # --- score (sobre la ventana de misión)
    profile = profiles[req.score_profile_id]
    if req.mission_days is not None and not req.mission_days > 0:
        raise InvalidParameterError(f"mission_days debe ser > 0, recibido {req.mission_days!r}")
    sp = params_from_config(cfg["score"])
    e_max = max(metrics.max_sun_elevation_deg, metrics.max_earth_elevation_deg)
    lim_frac = hz_mod.limited_fraction(horizon, e_max, float(np.max(sky.sun.radius_deg)))
    slope90 = None if res.slope is None or not np.isfinite(res.slope.percentile_deg) else res.slope.percentile_deg
    sigma_w = None
    if req.with_uncertainty and window is not None:
        try:
            sigma_w = _layer(ctx.dem_refs[obs.dem_key], DemLayer.TOTERR)
        except DemNotFoundError:
            pass

    def unc_on(sky_w, m_w, link_w=None):   # escenarios recalculados sobre el tramo de la ventana (los horizontes salen de la caché)
        return run_uncertainty(window, sigma_w, obs, horizon, sky_w, vp, tp, hp, catalog.uncertainty_params(cfg), m_w,
                               far=far, cache_dir=cdir, link=link_w)
    _score_window(ctx, req, res, profile, sp, vp, tp, hp, vis, c_sup, lim_frac, slope90, unc_on, link_ctx)
    if obs.mode is HorizonMode.FAR_FIELD:
        _far_field_score_texts(res.score)
        if req.with_uncertainty:
            res.score.assumptions += ("Rango de incertidumbre no calculado en el modo de 80 m: no hay σz (TOTERR) a esa resolución; "
                                      "el error medido del horizonte está en el aviso de resolución.",)
    if step_eff != req.step_s:
        res.score.assumptions += (f"Paso pedido {req.step_s:g} s > máximo {float(cfg['timeline']['max_step_s']):g} s (se perderían "
                                  f"eventos cortos): la serie se muestrea internamente a {step_eff:g} s.",)
    if (metrics.period_s / 86400.0) < SHORT_PERIOD_D:
        res.score.assumptions += (f"Periodo de {metrics.period_s / 86400.0:.1f} d < 29,5 d: D_max y f_sol no son "
                                  f"representativos (recomendado ≥ 1 mes sinódico; un año para el polo).",)

    # --- cuenta atrás
    res.countdowns = _countdowns(req, obs, horizon, vp, tp)

    # --- avisos científicos (§9.3): los siempre-visibles van siempre
    res.warnings = _warnings(res, warns, lim_frac)
    return res


def _slice_sky(sky: SkySeries, a: int, b: int) -> SkySeries:
    sl = slice(a, b)
    tr = lambda t: BodyTrack(t.body, t.az_deg[sl], t.el_deg[sl], t.dist_km[sl], t.radius_deg[sl])  # noqa: E731
    return dataclasses.replace(sky, et=sky.et[sl], sun=tr(sky.sun), earth=tr(sky.earth))


def _utc(et: float) -> str:
    return spice_engine.et_to_utc(float(et))[:19]


def _power_window(pw: PowerSeries, t0: float, t1: float, thr: float) -> tuple[float, float]:
    """(P_rel medio, fracción con P_rel ≥ ``thr``) sobre [t0, t1] de la serie de potencia (trapecio, cruce exacto del umbral)."""
    if not t1 > t0:
        p = float(np.interp(t0, pw.et, pw.p_rel))
        return p, float(p >= thr)
    m = (pw.et > t0) & (pw.et < t1)
    td = np.concatenate(([t0], pw.et[m], [t1]))
    pd = np.interp(td, pw.et, pw.p_rel)
    return pn._trapz(td, pd) / (t1 - t0), pn._time_above(td, pd, thr) / (t1 - t0)


def _score_window(ctx, req, res, profile, sp, vp, tp, hp, vis, c_sup, lim_frac, slope90, unc_on, link=None) -> None:
    """Score y puertas sobre la ventana [t0, t0 + mission_days] (revision-espacial §2); rellena ``res.score`` y campos afines.

    Sin ``mission_days`` (perfil custom): todo el periodo, como antes. Periodo < misión: se evalúa el periodo entero y el
    estado es SIN DATOS (o NO APTO si ya falla una puerta dura). Periodo ≥ misión: barrido de fechas de inicio con
    ``mission_window_metrics`` (resolución = ``step_s``; G0 = Sol visible en el inicio), mejor fecha = mayor score entre las
    que superan las puertas duras, y el nominal se recalcula exacto sobre ese tramo.
    """
    obs, sky, horizon, metrics, tl = res.observer, res.sky, res.horizon, res.metrics, res.timeline
    mission = _mission(ctx, profile.mission_profile_id)
    weights = dict(req.score_weights) if req.score_weights else None
    days = req.mission_days if req.mission_days is not None else profile.mission_days
    dem = obs.mode is HorizonMode.DEM
    et = sky.et
    lm = 0.0 if link is None else link.min_earth_elevation_deg
    ref_f = _earth_ref_f(obs, sky, hp, vp, horizon, vis, lm)
    ef = vis.earth.f if not lm else link_fraction(sky.earth, horizon, vp, lm)
    earth_m, ref_m = ef > vp.earth_f_thr, ref_f > vp.earth_f_thr
    if link is not None:   # conectividad = enlace: Tierra con margen ∧ red viendo la Luna (cobertura común a todos los sitios).
        earth_m = earth_m & link.coverage.any_grid   # La referencia (esfera lisa, mismo margen) NO lleva red: la red es externa y penaliza.
    windowed, short, ff = days is not None, False, None
    best, best_ok, wm, scores_sw, feas, g7_none, gaps_sw = 0, True, None, None, None, False, None
    a, b = 0, len(et)
    sun_m = vis.sun.f > vp.sun_f_thr
    pw = res.power if res.power_summary is not None else None   # panel elegido: la energía del score es su potencia efectiva
    thr_p = None if pw is None else float(res.power_summary.useful_threshold)
    if windowed:
        dt = float(tp.step_s)
        K = int(np.floor((et[-1] - et[0]) / dt + 1e-9)) + 1          # tramo de rejilla uniforme (el último punto puede no serlo)
        n = int(round(days * 86400.0 / dt))
        short = metrics.period_s < days * 86400.0 - 1e-6 or not 1 <= n <= K - 1
        if not short:
            wm = mission_window_metrics(sun_m[:K], earth_m[:K], et[:K], days,
                                        sp.window_step_h / 24.0, series_ref_earth=ref_m[:K])
            i0 = np.rint((wm.start_et - et[0]) / dt).astype(int)
            pmean = duty = None
            if pw is not None:   # P_rel medio y duty útil por ventana (sumas acumuladas sobre la rejilla, como el Sol)
                pg = np.interp(et[:K], pw.et, pw.p_rel)
                pm = 0.5 * (pg[:-1] + pg[1:])
                cm, cd = (np.concatenate(([0.0], np.cumsum(x, dtype=np.float64))) for x in (pm, pm >= thr_p))
                pmean, duty = (cm[i0 + n] - cm[i0]) / n, (cd[i0 + n] - cd[i0]) / n
            runs = [compute_score(ScoreInputs(
                f_sun=float(wm.f_sun[j]), d_max_h=float(wm.max_dark_h[j]), f_earth=float(wm.f_earth[j]),
                f_earth_ref=max(float(wm.f_ref[j]), 1e-6), slope_p90_deg=slope90, unknown_fraction=lim_frac,
                observer_in_dem=dem, has_dem=dem, sun_at_start=bool(sun_m[i0[j]]),
                **({} if link is None else dict(link_mode=True, max_link_gap_h=float(wm.max_gap_h[j]),
                                                longest_earth_h=float(wm.longest_earth_h[j]))),
                **({} if pw is None else dict(
                    f_power_eff=effective_energy(float(pmean[j]), float(duty[j]), sp.power_duty_weight),
                    p_rel_mean=float(pmean[j]), duty_useful=float(duty[j]), useful_power_fraction=thr_p))),
                profile, sp, mission, weights)
                for j in range(len(i0))]
            scores_sw = np.array([r.score for r in runs])
            nf = np.array([len(hard_fails(r.gates)) for r in runs])
            g7_lim = profile.max_link_gap_h if link is not None and profile.max_link_gap_type in ("hard", "soft") else None
            gaps_sw = None if link is None else np.asarray(wm.max_gap_h)
            # mejor fecha: puertas duras, luego G7 (hueco ≤ tolerado por el perfil), luego score; sin ninguna que cumpla G7, la de menor hueco
            best, best_ok = choose_start(scores_sw, nf, gaps_sw, g7_lim)
            g7_none = g7_lim is not None and bool(gaps_sw[best] > g7_lim)
            feas = nf == 0
            ff = float(feas.mean())
            a = int(i0[best])
            b = a + n + 1
    full = a == 0 and b == len(et)
    sky_w, vis_w, tl_w, m_w, link_w = sky, vis, tl, metrics, link
    if not full:   # tramo exacto de la ventana elegida: visibilidad, ventanas refinadas y métricas
        sky_w = _slice_sky(sky, a, b)
        link_w = None if link is None else link.sliced(a, b)
        vis_w = visibility_series(sky_w, horizon, vp)
        tl_w = run_timeline(sky_w, horizon, vp, tp, vis_w, link=link_w)
        m_w = compute_metrics(tl_w, sky_w, horizon, vp)
    res.link_window = tl_w.link
    trunc = metrics.max_darkness_truncated if (not windowed or short) else False   # recortada a la ventana: no es cota
    # f_E,ref: Tierra sobre esfera lisa con el mismo margen (sin red). s_earth = f_enlace / max(f_ref, suelo) ⇒ una red que cubre
    # el 45 % del tiempo baja s_earth ~45 %; el DSN (≈ 99,9 % de cobertura) apenas cambia la Tierra geométrica.
    f_ref_w = m_w.earth_fraction if horizon.mode is HorizonMode.SMOOTH_SPHERE and not lm else         _ref_fraction(sky_w.et, ref_f[a:b], vp.earth_f_thr)
    sun0 = bool(sun_m[a]) if windowed else None
    lw = lambda m: ((m.longest_earth_window_s if link is None else m.longest_link_window_s) / 3600.0) if windowed else None   # noqa: E731
    fe = lambda m: m.earth_fraction if link is None else m.link_fraction   # noqa: E731
    gp = lambda m: m.max_link_gap_s / 3600.0 if windowed and link is not None else None   # noqa: E731
    nominal = ScoreInputs(
        f_sun=m_w.solar_fraction, d_max_h=m_w.max_darkness_s / 3600.0, f_earth=fe(m_w),
        f_earth_ref=max(f_ref_w, 1e-6), slope_p90_deg=slope90, unknown_fraction=lim_frac, observer_in_dem=dem, has_dem=dem,
        d_max_truncated=trunc, sun_at_start=sun0, longest_earth_h=lw(m_w), max_link_gap_h=gp(m_w), link_mode=link is not None)
    if pw is not None:   # energía efectiva exacta sobre la ventana elegida
        pmn, dty = _power_window(pw, float(sky_w.et[0]), float(sky_w.et[-1]), thr_p)
        nominal = dataclasses.replace(nominal, f_power_eff=effective_energy(pmn, dty, sp.power_duty_weight), p_rel_mean=pmn,
                                      duty_useful=dty, useful_power_fraction=thr_p)
    scen_m = []
    if res.uncertainty is not None:
        scen_m = [s_.metrics for s_ in (res.uncertainty.scenarios if full else unc_on(sky_w, m_w, link_w).scenarios)]
    def scen_inputs(m):
        kw = {}
        if pw is not None:   # el escenario escala la energía efectiva con su fracción de Sol (la serie de potencia es la nominal)
            k = m.solar_fraction / nominal.f_sun if nominal.f_sun > 0 else 1.0
            kw = dict(f_power_eff=min(1.0, nominal.f_power_eff * k), p_rel_mean=nominal.p_rel_mean * k,
                      duty_useful=min(1.0, nominal.duty_useful * k))
        return dataclasses.replace(nominal, f_sun=m.solar_fraction, d_max_h=m.max_darkness_s / 3600.0, f_earth=fe(m),
                                   d_max_truncated=m.max_darkness_truncated if not windowed or short else False,
                                   longest_earth_h=lw(m), max_link_gap_h=gp(m), **kw)
    scen = [scen_inputs(m) for m in scen_m]
    res.f_earth_ref, res.window_metrics, res.score_inputs, res.score_scenarios = nominal.f_earth_ref, m_w, nominal, tuple(scen)
    sc = score_with_range(nominal, scen, profile, sp, mission, weights, c_sup=c_sup, dem=res.dem_confidence,
                          short_period=short, feasible_fraction=ff)
    res.score = sc
    if pw is not None:
        sc.energy_panel_id, sc.energy_mounting = pw.panel_id, pw.mounting.type.value
        sc.energy_note = f"Panel «{pw.panel_id}» · montaje {pw.mounting.type.value}. " + sc.energy_note
    sc.window_start_utc, sc.window_end_utc = _utc(sky_w.et[0]), _utc(sky_w.et[-1])
    if not windowed:
        return
    if g7_none:
        sc.assumptions += (f"Ninguna fecha de inicio del periodo cumple G7: todas tienen un hueco sin comunicaciones mayor que lo tolerado por el "
                           f"perfil ({profile.max_link_gap_h:g} h). Se elige la de MENOR hueco ({gaps_sw[best]:.1f} h en el barrido), no la de mayor score.",)
    sc.mission_days = float(days)
    sc.assumptions += (f"Score y puertas sobre la ventana de misión de {days:g} d ({sc.window_start_utc} → "
                       f"{sc.window_end_utc}), no sobre todo el periodo; perfil «{profile.id}».",)
    if wm is None:
        starts, g0 = np.array([et[0]]), np.array([sun0])
    else:
        sc.n_starts, sc.feasible_start_fraction = len(wm.start_et), ff
        sc.best_start_utc = _utc(wm.start_et[best]) if best_ok else None
        sc.best_window_end_utc = _utc(sky_w.et[-1]) if best_ok else None
        tops = []
        for j in pick_windows(wm.start_et, scores_sw, feas, days * 86400.0, sp.top_n_windows):
            first = j == best
            tops.append(WindowScore(_utc(wm.start_et[j]), _utc(wm.start_et[j] + days * 86400.0),
                                    sc.score if first else float(scores_sw[j]),
                                    nominal.d_max_h if first else float(wm.max_dark_h[j]),
                                    nominal.f_sun if first else float(wm.f_sun[j]),
                                    sc.score_min if first else None, sc.score_max if first else None))
        sc.top_windows = tuple(tops)
        starts = wm.start_et
        g0 = sun_m[np.rint((wm.start_et - et[0]) / float(tp.step_s)).astype(int)]
    g4 = next((g for g in sc.gates if g.id == "G4"), None)
    if g4 is not None and g4.limit is not None and g0.any():
        d, cens = max_sustainable(starts[g0], mt.intervals(tl.dark), g4.limit, float(et[-1]))
        k = int(np.argmax(d))
        sc.max_sustainable_days = SustainableDays(float(np.median(d)), float(d[k]), _utc(starts[g0][k]), float(g4.limit),
                                                  float(cens.mean()))


def _far_field_score_texts(sc) -> None:
    """Sustituye en el score los textos de «esfera lisa» (falsos con un horizonte de 80 m) y pone el motivo propio del modo."""
    def fix(t: str) -> str:
        for a, b in _FAR_TEXT_FIXES:
            t = t.replace(a, b)
        return t
    sc.assumptions = tuple(
        far_field_warning_text() if a == STANDARD_WARNINGS_ES[WarningCode.NO_DEM_SMOOTH_SPHERE] else
        FAR_FIELD_SCORE_TEXT if a == STANDARD_WARNINGS_ES[WarningCode.NO_TERRAIN_DATA_SCORE] else fix(a) for a in sc.assumptions)
    sc.gates = tuple(dataclasses.replace(g, reason=fix(g.reason)) for g in sc.gates)
    sc.verdict_reason, sc.range_note = fix(sc.verdict_reason), fix(sc.range_note)


def _countdowns(req, obs, horizon, vp, tp) -> tuple[Countdown, ...]:
    now = _utc_et(req.now_utc or req.start_utc)
    days = min(tp.countdown_search_days, (_utc_et(UTC_MAX) - now) / 86400.0 - 0.01)
    if days * 86400.0 < 2 * tp.step_s:
        return ()
    tp2 = dataclasses.replace(tp, countdown_search_days=days)
    return tuple(countdown(now, b, obs.lat_deg, obs.lon_deg_e, obs.height_m, horizon, vp, tp2) for b in (Body.SUN, Body.EARTH))


def _warnings(res: AnalysisResult, extra: Sequence[ScientificWarning], lim_frac: float) -> tuple[ScientificWarning, ...]:
    W = Severity
    dem = res.observer.mode is HorizonMode.DEM
    far_mode = res.observer.mode is HorizonMode.FAR_FIELD
    out = [_w(c, W.INFO) for c in ALWAYS_SHOWN_WARNINGS if c is not WarningCode.DEM_EFFECTIVE_RESOLUTION or dem]
    if far_mode:   # el esquema de exportación exige este aviso fuera de la esfera lisa: aquí con la resolución real (80 m)
        out.append(_w(WarningCode.DEM_EFFECTIVE_RESOLUTION, W.INFO, "far_field_80m",
                      "El DEM polar LOLA de este punto tiene 80 m/píxel: cráteres y relieve menores de ~200 m no están evaluados."))
    out.append(_w(WarningCode.NOT_RF_LINK, W.INFO))
    out += list(extra)
    h = res.horizon
    if (dem or far_mode) and h.limited.any():
        out.append(_w(WarningCode.HORIZON_LOWER_BOUND, W.WARNING, f"{100 * h.limited.mean():.1f} % de azimutes limitados"))
        if lim_frac > 0:
            out.append(_w(WarningCode.HORIZON_TRUNCATED, W.WARNING, f"{100 * lim_frac:.1f} % de azimutes relevantes sin cobertura"))
    m = res.metrics
    if m.longest_sun_window_truncated or m.max_darkness_truncated or any(
            w.left_truncated or w.right_truncated for w in (*res.timeline.sun.windows, *res.timeline.earth.windows)):
        out.append(_w(WarningCode.WINDOW_TRUNCATED, W.INFO))
    if res.score is not None:
        out += [_w(WarningCode.SCORE_UNCALIBRATED, W.INFO), _w(WarningCode.ROCKS_NOT_MODELED, W.INFO)]
        if res.score.partial:
            out.append(_w(WarningCode.NO_TERRAIN_DATA_SCORE, W.WARNING, "far_field_80m", FAR_FIELD_SCORE_TEXT) if far_mode
                       else _w(WarningCode.NO_TERRAIN_DATA_SCORE, W.WARNING))
    seen, uniq = set(), []
    for w in out:   # un aviso por (código, contexto); el primero manda
        if (w.code, w.context) not in seen:
            seen.add((w.code, w.context))
            uniq.append(w)
    return tuple(uniq)


def run_comparison(ctx: AppContext, reqs: Sequence[AnalysisRequest]) -> dict[str, AnalysisResult]:
    """run_analysis por petición (clave = site_id o 'lat,lon'; repetidas llevan sufijo '#n'); comparte kernels y caché."""
    out: dict[str, AnalysisResult] = {}
    for r in reqs:
        base = r.site_id or f"{r.lat_deg:g},{r.lon_deg_e:g}"
        key, n = base, 1
        while key in out:
            n += 1
            key = f"{base}#{n}"
        out[key] = run_analysis(ctx, r)
    return out
