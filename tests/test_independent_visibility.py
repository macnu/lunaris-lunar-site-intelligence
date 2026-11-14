"""T61: revisión independiente del motor de visibilidad (3D cartesiano, sin fórmula de horizonte ni de curvatura).

Camino alternativo: observador = (R+z_dem+h)·n(lat,lon) en MOON_ME; dirección al cuerpo = spkpos(LT+S) − observador; línea de
vista = muestreo del rayo 3D observador→cuerpo (2.5 m hasta 2 km, 5 m hasta 5 km, 20 m hasta 30 km) y comparación de |Q|−R con el DEM
interpolado en el punto del rayo proyectado a la esfera (5 m donde cubre, 80 m fuera). Disco puntual (centro).
NO importa geometría del motor: solo GeoTIFF (rasterio), kernels (spiceypy) y pipeline.run_analysis para COMPARAR.
Informe: docs/validation/revision-matematica.md.
"""
from __future__ import annotations

import glob
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest
import rasterio
import spiceypy as sp
from rasterio.windows import Window
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
R = 1737400.0                     # m, radio de referencia del DEM LOLA (convenciones.md)
H_OBS = 2.0
S_ENGINE = np.arange(5.0, 30000.0 + 1, 5.0)      # rejilla radial del motor (5 m): solo para aislar la discretización
S_GRID = np.concatenate([np.arange(2.5, 2000.0, 2.5), np.arange(2000.0, 5000.0, 5.0), np.arange(5000.0, 30000.0 + 1, 20.0)])
KERN = ("naif0012.tls", "pck00011.tpc", "moon_080317.tf", "moon_assoc_me.tf", "moon_pa_de421_1900-2050.bpc", "de421.bsp")
WINDOWS = (("2026-12-01T00:00:00", 30), ("2027-04-01T00:00:00", 30), ("2027-09-01T00:00:00", 30))
STEP = 600.0                      # paso del motor (por defecto); el rayo 3D se evalúa cada 3er nodo (30 min)
SUB = 3

pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem]


# ----------------------------------------------------------------------------- utilidades independientes
def _furnish():
    if sp.ktotal("ALL") == 0:
        for k in KERN:
            sp.furnsh(str(ROOT / "kernels" / k))


def unit_n(lat, lon):
    p, l = math.radians(lat), math.radians(lon)
    return np.array([math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)])


def xy_of_unit(u):
    """Estereográfica desde el polo norte sobre el plano z=−R (derivación propia): t=2R/(1−uz); (x,y)=(t·uy, t·ux).
    (x=ρ sin λ, y=ρ cos λ es la convención del raster polar sur de PROJ; se contrasta con pyproj en un test.)"""
    t = 2.0 * R / (1.0 - u[..., 2])
    return t * u[..., 1], t * u[..., 0]


def latlon_of_xy(x, y):
    rho = math.hypot(x, y)
    c = 2.0 * math.atan(rho / (2.0 * R))             # distancia angular al polo sur
    return -90.0 + math.degrees(c), math.degrees(math.atan2(x, y)) % 360.0


class Raster:
    """GeoTIFF leído con rasterio; bilineal con scipy (NaN si algún vecino es nodata o cae fuera)."""

    def __init__(self, path, bounds=None):
        with rasterio.open(path) as ds:
            t = ds.transform
            if bounds is None:
                c0, r0, w, h = 0, 0, ds.width, ds.height
            else:
                xmin, ymin, xmax, ymax = bounds
                c0 = max(int((xmin - t.c) // t.a) - 2, 0)
                c1 = min(int((xmax - t.c) // t.a) + 3, ds.width)
                r0 = max(int((t.f - ymax) // -t.e) - 2, 0)
                r1 = min(int((t.f - ymin) // -t.e) + 3, ds.height)
                w, h = c1 - c0, r1 - r0
            self.a = np.asarray(ds.read(1, window=Window(c0, r0, w, h)), dtype=np.float64)
            nd = ds.nodata
            self.px = t.a
            self.x0 = t.c + (c0 + 0.5) * t.a            # centro del píxel [0,0] de la ventana leída
            self.y0 = t.f - (r0 + 0.5) * t.a
        if nd is not None and not np.isnan(nd):
            self.a[self.a == nd] = np.nan
        self.a[~np.isfinite(self.a)] = np.nan

    def z(self, x, y):
        col = (np.asarray(x) - self.x0) / self.px
        row = (self.y0 - np.asarray(y)) / self.px
        return map_coordinates(self.a, [row.ravel(), col.ravel()], order=1, mode="constant", cval=np.nan,
                               prefilter=False).reshape(np.shape(x))


@lru_cache(maxsize=None)
def _fine(prefix):
    return Raster(glob.glob(str(ROOT / "data" / "raw" / "*" / f"{prefix}_final_adj_5mpp_surf.tif"))[0])


@lru_cache(maxsize=None)
def _far(xr, yr):
    p = glob.glob(str(ROOT / "data" / "raw" / "lola80s" / "LDEM_80S_80MPP_ADJ.TIF"))[0]
    return Raster(p, (xr - 32000, yr - 32000, xr + 32000, yr + 32000))


def ground(fine, far, x, y):
    z = fine.z(np.array([x]), np.array([y]))[0]
    return z if np.isfinite(z) else far.z(np.array([x]), np.array([y]))[0]


def body_dirs(et, body, p0):
    """Unitarios observador→cuerpo en MOON_ME (spkpos LT+S desde el centro lunar, menos el observador)."""
    _furnish()
    pos, _ = sp.spkpos(body, np.asarray(et), "MOON_ME", "LT+S", "MOON")
    v = np.asarray(pos) - p0 / 1000.0                     # km
    d = np.linalg.norm(v, axis=1)
    return v / d[:, None], d


def line_of_sight(p0, dirs, fine, far, chunk=24, s_grid=None):
    """True = el CENTRO del cuerpo es visible (ningún punto del rayo bajo la superficie). También nº de muestras sin dato."""
    vis = np.empty(len(dirs), bool)
    unk = np.zeros(len(dirs), int)
    for i in range(0, len(dirs), chunk):
        d = dirs[i:i + chunk]
        q = p0[None, None, :] + (S_GRID if s_grid is None else s_grid)[None, :, None] * d[:, None, :]
        r = np.linalg.norm(q, axis=2)
        x, y = xy_of_unit(q / r[..., None])
        z = fine.z(x, y)
        m = np.isnan(z)
        if m.any():
            z[m] = far.z(x[m], y[m])
        nan = np.isnan(z)
        unk[i:i + chunk] = nan.sum(axis=1)
        blocked = (r - R) < np.where(nan, -np.inf, z)
        vis[i:i + chunk] = ~blocked.any(axis=1)
    return vis, unk


# ----------------------------------------------------------------------------- puntos de prueba
def _suit_top(site):
    fs = sorted(glob.glob(str(ROOT / "data" / "processed" / "suitability" / f"{site}_lander_solar_no_rhu_*.json")))
    t = json.loads(Path(fs[-1]).read_text(encoding="utf-8"))["top"][0]
    return t["lat_deg"], t["lon_deg_e"]


def _wall_point(prefix, near_xy, target_deg=30.0, r_search=3000.0):
    """Píxel de pared: pendiente (capa slp, grados) más cercana a 30° a < 3 km del centro del recorte y a ≥ 500 m del borde."""
    s = Raster(glob.glob(str(ROOT / "data" / "raw" / "*" / f"{prefix}_final_adj_5mpp_slp.tif"))[0])
    ny, nx = s.a.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    X, Y = s.x0 + xx * s.px, s.y0 - yy * s.px
    ok = (np.hypot(X - near_xy[0], Y - near_xy[1]) < r_search) & np.isfinite(s.a)
    ok &= (xx > 100) & (xx < nx - 100) & (yy > 100) & (yy < ny - 100)
    i = np.unravel_index(np.argmin(np.where(ok, np.abs(s.a - target_deg), np.inf)), s.a.shape)
    return latlon_of_xy(float(X[i]), float(Y[i])), float(s.a[i])


def _centre(prefix):
    sim = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
    o = sim["dem_default_observers"][prefix]
    return o["lat_deg"], o["lon_deg_e"]


@lru_cache(maxsize=1)
def points():
    c4 = _centre("Site04")
    x4, y4 = xy_of_unit(unit_n(*c4))
    wall, _ = _wall_point("Site04", (float(x4), float(y4)))
    return {
        "Site04_centro": ("Site04", c4), "Site11_centro": ("Site11", _centre("Site11")),
        "Site23_centro": ("Site23", _centre("Site23")),
        "Site04_top1": ("Site04", _suit_top("Site04")), "Site23_top1": ("Site23", _suit_top("Site23")),
        "Site04_pared": ("Site04", wall),
    }


# ----------------------------------------------------------------------------- 1) marcos y proyección
def test_projection_matches_pyproj_and_raster_crs():
    """Mi estereográfica propia = pyproj con el CRS del GeoTIFF (diferencia < 1 mm)."""
    from pyproj import CRS, Transformer
    p = glob.glob(str(ROOT / "data" / "raw" / "shackleton" / "*_surf.tif"))[0]
    with rasterio.open(p) as ds:
        crs = CRS.from_wkt(ds.crs.to_wkt())
        tr = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    worst = 0.0
    for lat, lon in ((-89.7, 188.1), (-88.7, 292.07), (-86.0, 359.76), (-89.0, 10.0), (-85.5, 120.0)):
        x, y = xy_of_unit(unit_n(lat, lon))
        xp, yp = tr.transform(lon, lat)
        worst = max(worst, math.hypot(float(x) - xp, float(y) - yp))
        la, lo = latlon_of_xy(xp, yp)
        assert abs(la - lat) < 1e-9 and abs(((lo - lon + 180) % 360) - 180) < 1e-9
    assert worst < 1e-3


def test_azimuth_unit_and_sign_with_known_control_point():
    """Control: desde (−89°, 37°E) un punto 10 km al Este (λ mayor, misma φ) está a az=90°; uno 10 km hacia latitud mayor
    (alejándose del polo sur) a az=0° (Norte). Y spkpos−observador = spkcpo (estado relativo con LT+S) a < 1e-5°."""
    _furnish()
    lat, lon = -89.0, 37.0
    n = unit_n(lat, lon)
    e = np.array([-math.sin(math.radians(lon)), math.cos(math.radians(lon)), 0.0])
    nn = np.cross(n, e)                                      # N = U × E (base diestra E,N,U)
    la, lo = math.radians(lat), math.radians(lon)
    assert np.allclose(nn, [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)])
    dd = 10000.0 / R                                         # 10 km de arco de círculo máximo
    for brg, exp in ((90.0, 90.0), (0.0, 0.0), (180.0, 180.0), (270.0, 270.0)):
        b = math.radians(brg)
        tgt = math.cos(dd) * n + math.sin(dd) * (math.sin(b) * e + math.cos(b) * nn)   # destino a rumbo b
        v = tgt - n
        assert abs((math.degrees(math.atan2(v @ e, v @ nn)) % 360 - exp + 180) % 360 - 180) < 0.01
    # coherencia con coordenadas: el destino al Este (rumbo 90°) tiene λ mayor (Este-positivo) y el del Norte φ mayor
    tgt = math.cos(dd) * n + math.sin(dd) * e
    assert math.degrees(math.atan2(tgt[1], tgt[0])) > lon
    tgt = math.cos(dd) * n + math.sin(dd) * nn
    assert math.degrees(math.asin(tgt[2])) > lat
    et = sp.str2et("2026-12-10T12:00:00")
    p0 = (R + 2.0) * n / 1000.0
    pos, _ = sp.spkpos("SUN", et, "MOON_ME", "LT+S", "MOON")
    v1 = np.asarray(pos) - p0
    st, _ = sp.spkcpo("SUN", et, "MOON_ME", "OBSERVER", "LT+S", p0, "MOON", "MOON_ME")
    ang = math.degrees(math.acos(np.clip(v1 @ st[:3] / np.linalg.norm(v1) / np.linalg.norm(st[:3]), -1, 1)))
    assert ang < 1e-5


def test_engine_azimuth_elevation_match_own_enu_basis():
    """sky.az/el del motor = az/el calculados con mi base ENU y el vector 3D (control del signo y la unidad de azimut)."""
    from lsi.astronomy import spice_engine
    from lsi.contracts import Body
    _furnish()
    lat, lon = -89.766811, 188.130102
    et = sp.str2et("2026-12-01T00:00:00") + 3600.0 * np.arange(0, 24 * 30, 7)
    n = unit_n(lat, lon)
    e = np.array([-math.sin(math.radians(lon)), math.cos(math.radians(lon)), 0.0])
    nn = np.cross(n, e)
    p0 = (R + H_OBS) * n / 1000.0
    for body, b in (("SUN", Body.SUN), ("EARTH", Body.EARTH)):
        d, _ = body_dirs(et, body, p0 * 1000.0)
        az = np.degrees(np.arctan2(d @ e, d @ nn)) % 360
        el = np.degrees(np.arcsin(d @ n))
        tr = spice_engine.body_track(et, lat, lon, b, H_OBS)
        daz = np.abs((tr.az_deg - az + 180) % 360 - 180)
        assert daz.max() < 1e-6 and np.abs(tr.el_deg - el).max() < 1e-6


# ----------------------------------------------------------------------------- 2) disco finito y bisección
def test_finite_disc_flat_matches_brute_force_integration():
    """Segmento circular f(t)=½+(t√(1−t²)+asin t)/π (disc_fraction_flat) vs. conteo de píxeles en el disco unidad."""
    from lsi.simulation.visibility import disc_fraction_flat
    g = np.linspace(-1, 1, 4001)
    X, Y = np.meshgrid(g, g)
    inside = X ** 2 + Y ** 2 <= 1.0
    worst = 0.0
    for t in np.linspace(-1.2, 1.2, 25):
        brute = np.count_nonzero(inside & (Y >= -t)) / np.count_nonzero(inside)     # t=(e−H)/ρ: visible y ≥ −t
        worst = max(worst, abs(float(disc_fraction_flat(t)) - brute))
    assert worst < 3e-4


def test_finite_disc_variable_horizon_brute_force():
    """H(A) ondulado: rebanadas del motor (n=64) vs. fuerza bruta 2D en el disco (e=0.5°, ρ=0.27°)."""
    from lsi.contracts import HorizonMode, HorizonParams, HorizonResult, ObserverPoint
    from lsi.simulation.visibility import disc_fraction
    az = np.arange(0, 360, 0.25)
    h = 0.4 + 0.2 * np.sin(np.radians(az))
    obs = ObserverPoint(lat_deg=-89.0, lon_deg_e=0.0, x_m=0.0, y_m=0.0, height_m=2.0, mode=HorizonMode.DEM)
    hr = HorizonResult(az_deg=az, h_lb_deg=h, r_cov_m=np.full(az.shape, 3e4), limited=np.zeros(az.shape, bool),
                       mode=HorizonMode.DEM, observer=obs, params=HorizonParams(), h_sphere_deg=-0.087, cache_key="t61", h_ub_deg=h.copy())
    rho, el, a0 = 0.27, 0.5, 5.0
    g = np.linspace(-rho, rho, 1601)
    X, Y = np.meshgrid(g, g)
    inside = X ** 2 + Y ** 2 <= rho ** 2
    # coordenada de azimut de un punto del disco a elevación el+Y: ΔA = X/cos(el+Y) (exacto), no la aproximación X/cos e
    hh = np.interp((a0 + X / np.cos(np.radians(el + Y))) % 360, az, h, period=360)
    brute = np.count_nonzero(inside & (el + Y >= hh)) / np.count_nonzero(inside)
    eng = float(disc_fraction(np.array([el]), np.array([a0]), np.array([rho]), hr)[0])
    assert 0.0 < brute < 1.0
    assert abs(eng - brute) < 2e-3


def test_bisection_vs_5s_grid_on_real_transition():
    """Bisección a 1 s del motor vs. rejilla de 5 s sobre las transiciones f=0.5 del Sol real con un horizonte plano a media altura."""
    from lsi.astronomy import spice_engine
    from lsi.contracts import Body, HorizonMode, HorizonParams, HorizonResult, ObserverPoint
    from lsi.simulation.timeline import refine_crossings
    from lsi.simulation.visibility import disc_fraction
    _furnish()
    lat, lon = -89.766811, 188.130102
    grid = sp.str2et("2026-12-01T00:00:00") + 600.0 * np.arange(0, 60 * 144)
    e_all = spice_engine.body_track(grid, lat, lon, Body.SUN, 2.0).el_deg
    h0 = 0.5 * (e_all.min() + e_all.max())                   # horizonte plano a media altura: el Sol lo cruza varias veces
    az = np.arange(0, 360, 0.25)
    obs = ObserverPoint(lat_deg=lat, lon_deg_e=lon, x_m=0.0, y_m=0.0, height_m=2.0, mode=HorizonMode.DEM)
    hr = HorizonResult(az_deg=az, h_lb_deg=np.full_like(az, h0), r_cov_m=np.full(az.shape, 3e4),
                       limited=np.zeros(az.shape, bool), mode=HorizonMode.DEM, observer=obs, params=HorizonParams(),
                       h_sphere_deg=-0.087, cache_key="t61", h_ub_deg=np.full_like(az, h0))

    def f_fn(et):
        tr = spice_engine.body_track(et, lat, lon, Body.SUN, 2.0)
        return disc_fraction(tr.el_deg, tr.az_deg, tr.radius_deg, hr)

    f = f_fn(grid)
    idx = np.flatnonzero((f[:-1] > 0.5) != (f[1:] > 0.5))
    assert len(idx) >= 2
    t_eng = refine_crossings(f_fn, grid[idx], grid[idx + 1], 0.5, 1.0)
    for k, t in zip(idx, t_eng):
        fine = grid[k] + 5.0 * np.arange(0, 121)
        ff = f_fn(fine) > 0.5
        j = np.flatnonzero(ff[:-1] != ff[1:])
        assert len(j) == 1
        assert abs(t - (fine[j[0]] + 2.5)) <= 3.0            # 2.5 s (celda de 5 s) + 0.5 s (xtol 1 s)
    # f=0.5 con H plano ⇔ e=H (disco partido por la mitad): el centro está en el horizonte
    tr = spice_engine.body_track(t_eng, lat, lon, Body.SUN, 2.0)
    assert float(np.max(np.abs(tr.el_deg - h0))) < 0.01


# ----------------------------------------------------------------------------- 3) comparación con el pipeline
@pytest.fixture(scope="module")
def ctx():
    from lsi import pipeline
    return pipeline.build_context(ROOT)


def _run(ctx, lat, lon, start, days):
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    end = sp.et2utc(sp.str2et(start) + days * 86400.0, "ISOC", 0)
    return pipeline.run_analysis(ctx, AnalysisRequest(lat_deg=lat, lon_deg_e=lon, start_utc=start, end_utc=end,
                                                      observer_height_m=H_OBS, step_s=STEP))


RESULTS: dict = {}
_RUNS: dict = {}


def _obs_setup(name):
    prefix, (lat, lon) = points()[name]
    fine = _fine(prefix)
    x, y = xy_of_unit(unit_n(lat, lon))
    far = _far(round(float(x)), round(float(y)))
    z0 = ground(fine, far, float(x), float(y))
    return lat, lon, fine, far, z0, (R + z0 + H_OBS) * unit_n(lat, lon)


def _run_cached(ctx, name, k):
    if (name, k) not in _RUNS:
        lat, lon = points()[name][1]
        _RUNS[(name, k)] = _run(ctx, lat, lon, *WINDOWS[k])
    return _RUNS[(name, k)]


@pytest.mark.slow
@pytest.mark.parametrize("name", ["Site04_centro", "Site11_centro", "Site23_centro", "Site04_top1", "Site23_top1",
                                  "Site04_pared"])
def test_independent_line_of_sight_vs_pipeline(ctx, name):
    lat, lon, fine, far, z0, p0 = _obs_setup(name)
    rows = []
    for k, (start, days) in enumerate(WINDOWS):
        res = _run_cached(ctx, name, k)
        assert res.observer.ground_z_m == pytest.approx(z0, abs=0.05)        # mismo suelo (bilineal) que el motor
        sl = slice(None, None, SUB)
        et = res.sky.et[sl]
        out = {}
        for body, key, vis in (("SUN", "sun", res.timeline.series.sun), ("EARTH", "earth", res.timeline.series.earth)):
            dirs, _ = body_dirs(et, body, p0)
            cv, unk = line_of_sight(p0, dirs, fine, far)
            f = vis.f[sl]
            definite = (f <= 1e-3) | (f >= 1 - 1e-3)
            out[key] = dict(
                n=len(et), n_partial=int(np.count_nonzero(~definite)),
                frac_center=float(cv.mean()), frac_engine_area=float(f.mean()),
                frac_engine_gt_half=float(np.mean(f > 0.5)), frac_engine_gt_thr=float(np.mean(f > 1e-3)),
                frac_engine_full=float(np.mean(f >= 1 - 1e-3)),
                hard_a=int(np.count_nonzero(cv & (f <= 1e-3))), hard_b=int(np.count_nonzero(~cv & (f >= 1 - 1e-3))),
                center_vs_half_partial=int(np.count_nonzero(~definite & (cv != (f >= 0.5)))),
                center_vs_half_all=int(np.count_nonzero(cv != (f >= 0.5))),
                n_unk_instants=int(np.count_nonzero(unk)),
                engine_metric=float(res.metrics.solar_fraction if key == "sun" else res.metrics.earth_fraction))
        rows.append((start, out))
    RESULTS[name] = rows
    for start, out in rows:
        for key, o in out.items():
            ctxs = (name, start, key, o)
            # (a) sin contradicciones duras: motor categórico (f≈0 / f≈1) y rayo 3D en sentido contrario
            assert o["hard_a"] + o["hard_b"] <= max(2, 0.003 * o["n"]), ctxs
            # (b) la fracción de tiempo del centro queda entre la de f≈1 y la de f>ε
            assert o["frac_engine_full"] - 0.004 <= o["frac_center"] <= o["frac_engine_gt_thr"] + 0.004, ctxs
            # (c) centro ≈ f>0.5: las discrepancias solo pueden ser instantes parciales
            assert abs(o["frac_center"] - o["frac_engine_gt_half"]) <= o["n_partial"] / o["n"] + 0.004, ctxs


# ----------------------------------------------------------------------------- 4) horizonte y disco finito por rayos 3D
HORIZON_STATS: dict = {}


@pytest.mark.slow
@pytest.mark.parametrize("name", ["Site04_centro", "Site11_centro", "Site23_centro", "Site04_top1", "Site23_top1",
                                  "Site04_pared"])
def test_horizon_profile_by_3d_bisection(ctx, name):
    """Horizonte por azimut: bisección en elevación del rayo 3D (cada 5°) vs H_lb del motor interpolado.
    Detecta errores de signo/marco/curvatura en horizon.py (cuyo muestreo es en el plano estereográfico)."""
    lat, lon, fine, far, z0, p0 = _obs_setup(name)
    res = _run_cached(ctx, name, 0)
    n = unit_n(lat, lon)
    e = np.array([-math.sin(math.radians(lon)), math.cos(math.radians(lon)), 0.0])
    nn = np.cross(n, e)
    az = np.arange(0.0, 360.0, 5.0)
    horiz = np.sin(np.radians(az))[:, None] * e + np.cos(np.radians(az))[:, None] * nn
    lo, hi = np.full(len(az), -10.0), np.full(len(az), 60.0)      # lo: oculto, hi: visible (verificado abajo)
    d = lambda el: np.cos(np.radians(el))[:, None] * horiz + np.sin(np.radians(el))[:, None] * n  # noqa: E731
    assert line_of_sight(p0, d(hi), fine, far)[0].all()
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        v, _u = line_of_sight(p0, d(mid), fine, far)
        lo, hi = np.where(v, lo, mid), np.where(v, mid, hi)
    h3d = 0.5 * (lo + hi)
    eng = np.interp(az, res.horizon.az_deg, res.horizon.h_lb_deg, period=360.0)
    diff = h3d - eng
    rel = h3d < 10.0                                              # banda que importa al Sol (≤2°) y a la Tierra (≤~9°)
    HORIZON_STATS[name] = dict(
        n_az=len(az), max_abs=float(np.abs(diff).max()), rms=float(np.sqrt(np.mean(diff ** 2))), mean=float(diff.mean()),
        n_rel=int(rel.sum()), max_abs_rel=float(np.abs(diff[rel]).max()) if rel.any() else 0.0,
        rms_rel=float(np.sqrt(np.mean(diff[rel] ** 2))) if rel.any() else 0.0,
        h3d_min=float(h3d.min()), h3d_max=float(h3d.max()), limited=int(res.horizon.limited.sum()))
    # El motor (paso radial 5 m) queda por DEBAJO del máximo continuo del rayo 3D: ≤0.13° donde el horizonte lo fija un
    # relieve a ~50 m (0.14 m de altura, ≪ σ del DEM). Se aísla en test_residual_is_radial_discretization.
    assert HORIZON_STATS[name]["max_abs_rel"] < 0.2 and HORIZON_STATS[name]["rms_rel"] < 0.03, HORIZON_STATS[name]
    assert np.abs(diff).max() < 0.2 and np.sqrt(np.mean(diff ** 2)) < 0.03, HORIZON_STATS[name]
    assert abs(diff.mean()) < 0.015, HORIZON_STATS[name]       # sin sesgo sistemático (signo/curvatura/marco)


@pytest.mark.slow
@pytest.mark.parametrize("name,az0", [("Site11_centro", 40.0), ("Site11_centro", 20.0), ("Site23_centro", 205.0)])
def test_residual_is_radial_discretization(ctx, name, az0):
    """Con la MISMA rejilla radial de 5 m el rayo 3D reproduce el horizonte del motor a <0.02°: el residuo de
    test_horizon_profile_by_3d_bisection es discretización del motor, no marco/signo/curvatura."""
    lat, lon, fine, far, z0, p0 = _obs_setup(name)
    res = _run_cached(ctx, name, 0)
    n = unit_n(lat, lon)
    e = np.array([-math.sin(math.radians(lon)), math.cos(math.radians(lon)), 0.0])
    nn = np.cross(n, e)
    a = np.radians(az0)
    horiz = (math.sin(a) * e + math.cos(a) * nn)[None, :]
    d = lambda el: np.cos(np.radians(el))[:, None] * horiz + np.sin(np.radians(el))[:, None] * n  # noqa: E731
    out = {}
    for lab, sg in (("5m", S_ENGINE), ("fino", np.arange(1.0, 30001.0, 1.0))):
        lo, hi = np.array([-10.0]), np.array([60.0])
        for _ in range(26):
            mid = 0.5 * (lo + hi)
            v, _u = line_of_sight(p0, d(mid), fine, far, s_grid=sg)
            lo, hi = np.where(v, lo, mid), np.where(v, mid, hi)
        out[lab] = float(0.5 * (lo + hi)[0])
    eng = float(np.interp(az0, res.horizon.az_deg, res.horizon.h_lb_deg, period=360.0))
    HORIZON_STATS[f"resid_{name}_{az0:g}"] = dict(engine=eng, ray_5m=out["5m"], ray_1m=out["fino"])
    assert abs(out["5m"] - eng) < 0.02
    assert out["fino"] >= out["5m"] - 1e-9                      # más muestras nunca bajan el máximo


def _disc_dirs(d, rho_rad, n_pts=300):
    """Puntos de un disco (cap esférico) uniforme en ÁREA alrededor de d (K,3): patrón de girasol; devuelve (K,P,3)."""
    a = np.cross(d, [0.0, 0.0, 1.0])
    a /= np.linalg.norm(a, axis=1)[:, None]
    b = np.cross(d, a)
    k = np.arange(n_pts) + 0.5
    th = np.arccos(1.0 - (1.0 - math.cos(rho_rad)) * k / n_pts) if np.isscalar(rho_rad) else None
    ph = k * math.pi * (3.0 - math.sqrt(5.0))
    t = (np.cos(ph)[None, :, None] * a[:, None, :] + np.sin(ph)[None, :, None] * b[:, None, :])
    return np.cos(th)[None, :, None] * d[:, None, :] + np.sin(th)[None, :, None] * t


@pytest.mark.slow
@pytest.mark.parametrize("name,body,k", [("Site04_top1", "EARTH", 0), ("Site04_top1", "SUN", 1), ("Site23_top1", "SUN", 1),
                                         ("Site11_centro", "SUN", 2), ("Site23_centro", "EARTH", 0)])
def test_finite_disc_area_by_3d_rays_vs_engine(ctx, name, body, k):
    """Fracción de disco por 300 rayos 3D (muestreo uniforme en área) vs f del motor en los instantes PARCIALES.
    Cierra la brecha 'centro del disco vs disco finito': error esperado del muestreo ~1/√300·σ ≈ 0.01–0.02."""
    lat, lon, fine, far, z0, p0 = _obs_setup(name)
    res = _run_cached(ctx, name, k)
    vis = res.timeline.series.sun if body == "SUN" else res.timeline.series.earth
    et = res.sky.et
    part = np.flatnonzero((vis.f > 1e-3) & (vis.f < 1 - 1e-3))
    part = part[:: max(1, len(part) // 60)]                      # ≤ ~60 instantes parciales repartidos
    assert len(part) >= 20
    dirs, dist = body_dirs(et[part], body, p0)
    rho = math.asin((695700.0 if body == "SUN" else 6378.137) / dist.mean())    # rad (varía <1e-3 relativo en el periodo)
    pts = _disc_dirs(dirs, rho)
    cv = np.array([line_of_sight(p0, pts[i], fine, far)[0].mean() for i in range(len(part))])
    c5 = np.array([line_of_sight(p0, pts[i], fine, far, s_grid=S_ENGINE)[0].mean() for i in range(len(part))])
    diff, d5 = cv - vis.f[part], c5 - vis.f[part]
    HORIZON_STATS[f"disc_{name}_{body}"] = dict(
        n=len(part), mean=float(diff.mean()), max_abs=float(np.abs(diff).max()), rms=float(np.sqrt(np.mean(diff ** 2))),
        mean_5m=float(d5.mean()), max_abs_5m=float(np.abs(d5).max()), rms_5m=float(np.sqrt(np.mean(d5 ** 2))))
    st = HORIZON_STATS[f"disc_{name}_{body}"]
    # misma rejilla que el motor ⇒ solo queda error de disco finito + muestreo de 300 rayos
    assert abs(d5.mean()) < 0.01 and np.abs(d5).max() < 0.03 and np.sqrt(np.mean(d5 ** 2)) < 0.015, st
    # rejilla fina ⇒ además la discretización radial del motor (≤0.13° de horizonte ≈ ≤0.08 de f en el Sol)
    assert abs(diff.mean()) < 0.01 and np.abs(diff).max() < 0.09 and np.sqrt(np.mean(diff ** 2)) < 0.02, st
