"""T62: revisión independiente del enlace DTE y de las bases terrestres (informe: docs/validation/revision-enlace.md).

Camino alternativo (NO se importa geometría del motor; el motor/pipeline solo sirven para COMPARAR):
* Tierra: ``J2000`` aparente (spkpos LT+S desde el centro de la Tierra) rotada con ``ITRF93`` de los PCK binarios de NAIF
  (``earth_latest_high_prec.bpc`` + ``earth_2026_260806_2126_predict.bpc``: nutación, movimiento polar y UT1 incluidos; el motor usa
  ``IAU_EARTH``, que no los lleva). Se descargan a ``data/raw/earth/`` (5 + 19 MB; los tests se omiten si faltan). Una rotación
  a mano con GMST sin precesión-nutación erraría ~0,36° en 2026: peor que lo que se quiere medir.
* Estación: DMS escritos a mano de DSN 810-005/301 Rev. P, Tabla 5 (WGS 84) y geodésicas→cartesianas propias.
* Enlace: rayo 3D lander→Tierra (spkpos LT+S, MOON_ME) contra el DEM (rasterio), como ``test_independent_visibility.py``; el
  margen de elevación m baja la elevación del rayo m grados a azimut constante (= subir H(A) m). Paso 120 s.
* Hora local: reglas de verano escritas a mano (último domingo, etc.), sin ``zoneinfo``.
"""
from __future__ import annotations

import calendar
import glob
import json
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest
import rasterio
import spiceypy as sp
from rasterio.windows import Window
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
R = 1737400.0                       # m, radio de referencia del DEM LOLA (convenciones.md)
H_OBS = 2.0
S_GRID = np.concatenate([np.arange(2.5, 2000.0, 2.5), np.arange(2000.0, 5000.0, 5.0), np.arange(5000.0, 30000.0 + 1, 20.0)])
KERN = ("naif0012.tls", "pck00011.tpc", "moon_080317.tf", "moon_assoc_me.tf", "moon_pa_de421_1900-2050.bpc", "de421.bsp")
EARTH_DIR = ROOT / "data" / "raw" / "earth"
BPC = (EARTH_DIR / "earth_2026_260806_2126_predict.bpc", EARTH_DIR / "earth_latest_high_prec.bpc")   # el último cargado manda
RX_MIN = 6.0                        # DSN 810-005/301 Rev. P §2.2.2/§2.2.4 (recepción)
TX_MIN = 10.1                       # ibid. (transmisión de baja potencia, 10,0° + 0,1° de incertidumbre)

needs_bpc = pytest.mark.skipif(not all(p.exists() for p in BPC),
                               reason="faltan los PCK de ITRF93 en data/raw/earth/ (ver docstring del módulo)")
pytestmark = [pytest.mark.needs_spice]


# ---------------------------------------------------------------------------------------------- kernels y estaciones
def _furnish() -> None:
    """Idempotente y a prueba de ``kclear`` del motor: carga lo que falte en el pool."""
    loaded = {Path(sp.kdata(i, "ALL")[0]).name for i in range(sp.ktotal("ALL"))}
    for p in [ROOT / "kernels" / k for k in KERN] + list(BPC):
        if p.name not in loaded:
            sp.furnsh(str(p))


def _dms(d, m, s, neg=False):
    v = d + m / 60.0 + s / 3600.0
    return -v if neg else v


# DSN 810-005/301 Rev. P, Tabla 5 (WGS 84), transcritos a mano del PDF: lat, lon E, h elipsoidal (m). Sur: todo negativo (nota 3).
TABLE5 = {"DSS-14": (_dms(35, 25, 33.24312), _dms(243, 6, 37.66244), 1001.390),
          "DSS-43": (_dms(35, 24, 8.72724, True), _dms(148, 58, 52.56231), 688.867),
          "DSS-63": (_dms(40, 25, 52.35510), _dms(355, 45, 7.16924), 864.816)}
# Tabla 6 (geocéntricas): latitud geocéntrica (°) y radio geocéntrico (m)
TABLE6 = {"DSS-14": (35.2443523, 6371993.267), "DSS-43": (-35.2209189, 6371688.998)}
WGS84_A, WGS84_F = 6378.137, 1 / 298.257223563
NAMES = ("DSS-14", "DSS-63", "DSS-43")


def st_xyz(lat, lon, h_m):
    la, lo = math.radians(lat), math.radians(lon)
    e2 = WGS84_F * (2 - WGS84_F)
    n = WGS84_A / math.sqrt(1 - e2 * math.sin(la) ** 2)
    h = h_m / 1e3
    return np.array([(n + h) * math.cos(la) * math.cos(lo), (n + h) * math.cos(la) * math.sin(lo), (n * (1 - e2) + h) * math.sin(la)])


def st_up(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])


def moon_el(et, sid, *, via="itrf93"):
    """Elevación (°) de la Luna (centro, aparente, sin refracción) sobre el horizonte geodésico de la estación."""
    _furnish()
    lat, lon, h = TABLE5[sid]
    et = np.atleast_1d(np.asarray(et, dtype=np.float64))
    xyz, up = st_xyz(lat, lon, h), st_up(lat, lon)
    if via == "spkcpo":          # topocéntrico (LT+S con el observador en la estación): la forma «de libro» de SPICE
        out = []
        for e in et:
            s, _ = sp.spkcpo("MOON", e, "ITRF93", "OBSERVER", "LT+S", xyz, "EARTH", "ITRF93")
            out.append(math.degrees(math.asin(s[:3] @ up / np.linalg.norm(s[:3]))))
        return np.array(out)
    if via == "pxform":          # J2000 aparente + rotación J2000→ITRF93 compuesta a mano
        pos, _ = sp.spkpos("MOON", et, "J2000", "LT+S", "EARTH")
        v = np.array([sp.pxform("J2000", "ITRF93", e) @ p for e, p in zip(et, pos)]) - xyz
    else:                        # spkpos directo en ITRF93 (vectorizado)
        pos, _ = sp.spkpos("MOON", et, "ITRF93", "LT+S", "EARTH")
        v = np.asarray(pos) - xyz
    return np.degrees(np.arcsin(np.clip(v @ up / np.linalg.norm(v, axis=1), -1, 1)))


def network_any(et, thr=RX_MIN):
    return np.any([moon_el(et, s) >= thr for s in NAMES], axis=0)


def _intervals(b, t):
    """Intervalos [a, c) de ``b`` True con bordes en el punto medio entre nodos (recortados a [t[0], t[-1]])."""
    b = np.asarray(b, bool)
    mid = 0.5 * (t[1:] + t[:-1])
    d = np.diff(np.r_[0, b.astype(int), 0])
    s, e = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    a = np.where(s == 0, t[0], mid[np.maximum(s - 1, 0)])
    c = np.where(e == len(t), t[-1], mid[np.minimum(e - 1, len(mid) - 1)])
    return np.column_stack((a, c)) if len(s) else np.empty((0, 2))


def _gaps(b, t):
    return _intervals(~np.asarray(b, bool), t)


HORIZONS = {  # JPL Horizons API, 301 Moon, CENTER coord@399, SITE_COORD geodético, QUANTITIES=4, AIRLESS (descargado 14/11/2026)
    '2026-12': {
        'utc': ['2026-12-01 03:45', '2026-12-02 17:00', '2026-12-04 16:15', '2026-12-05 01:30', '2026-12-07 22:30', '2026-12-09 15:00', '2026-12-09 19:00', '2026-12-10 06:15', '2026-12-10 09:15', '2026-12-11 14:00', '2026-12-15 11:30', '2026-12-16 10:30', '2026-12-18 19:30', '2026-12-20 05:30', '2026-12-22 01:15', '2026-12-24 21:30', '2026-12-25 15:45', '2026-12-26 06:45', '2026-12-26 09:15', '2026-12-26 16:30', '2026-12-27 23:15', '2026-12-28 15:00', '2026-12-29 04:15', '2026-12-30 01:30'],
        'DSS-14': [-39.07312, 41.22044, 40.67927, -45.52544, 7.84231, -6.80706, 23.70514, -58.98663, -79.72852, -35.19646, -60.8255, -42.23857, -10.867, 62.52769, 32.36956, -28.72892, 8.63154, 43.34824, 69.83849, 8.46808, -44.63538, 39.22522, -25.45673, -57.35539],
        'DSS-43': [-26.62187, 23.00818, 3.54176, 47.8233, 56.01641, -27.20459, -1.66189, 46.39467, 11.91462, -23.97127, 20.30045, 36.53285, -57.01754, 3.34354, -70.5918, -21.79688, 30.75645, -55.25516, -26.18239, 35.69865, -0.48181, 26.49301, -43.29767, -0.80717],
        'DSS-63': [42.81858, -40.89565, -26.66284, -27.66317, -73.07395, 13.35882, -21.04616, -27.71349, 1.61397, 23.45332, -1.4075, -16.59194, 58.99477, -19.61629, 47.98192, 41.63091, -22.69606, 32.27199, 4.94052, -28.41978, 19.94643, -39.43342, 50.62006, 18.49674],
    },
    '2027-03': {
        'utc': ['2027-03-01 08:45', '2027-03-02 02:15', '2027-03-02 08:15', '2027-03-04 00:00', '2027-03-05 08:30', '2027-03-06 23:00', '2027-03-08 15:30', '2027-03-09 05:15', '2027-03-12 17:15', '2027-03-14 15:00', '2027-03-14 16:15', '2027-03-15 08:45', '2027-03-16 08:30', '2027-03-16 20:30', '2027-03-16 21:00', '2027-03-20 10:00', '2027-03-22 10:30', '2027-03-25 22:15', '2027-03-26 09:45', '2027-03-28 08:00', '2027-03-29 06:45', '2027-03-30 21:30', '2027-03-31 00:15', '2027-03-31 17:15'],
        'DSS-14': [-15.7342, -74.773, -30.46963, -28.3185, -51.17521, 15.39017, 15.55074, -32.10398, 12.70068, -21.53134, -12.51185, 1.64919, 14.74102, 7.95324, 13.29805, 31.66254, 34.79462, -76.48612, 27.41945, -1.1131, -23.36369, -24.43678, -56.22525, 25.33391],
        'DSS-43': [-27.64051, 29.86273, -24.71773, 72.85464, -16.70266, 50.54802, -50.58873, 37.91161, -75.68578, -38.12084, -52.59507, 24.80298, 26.4658, -76.4062, -80.02199, 32.01386, 30.36748, 18.64591, -3.59095, -25.91655, -26.79846, 76.85349, 46.57429, 31.78937],
        'DSS-63': [17.55747, -13.25867, 21.50343, -52.6091, 25.10248, -60.24206, 31.48746, -18.69183, 60.85528, 57.66916, 70.22165, -13.2123, -20.33445, 70.90294, 66.47429, -39.8749, -46.6276, -2.54542, -19.45994, 9.88992, 20.25398, -57.27247, -27.34866, -53.54139],
    },
}


# ---------------------------------------------------------------------------------------------- DEM y rayo 3D
def unit_n(lat, lon):
    p, l = math.radians(lat), math.radians(lon)
    return np.array([math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)])


def xy_of_unit(u):
    """Estereográfica desde el polo norte sobre el plano z=−R (derivación propia, contrastada con pyproj en test_independent_visibility)."""
    t = 2.0 * R / (1.0 - u[..., 2])
    return t * u[..., 1], t * u[..., 0]


class Raster:
    """GeoTIFF con rasterio; bilineal (NaN si hay nodata o cae fuera)."""

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
            self.px, self.x0, self.y0 = t.a, t.c + (c0 + 0.5) * t.a, t.f - (r0 + 0.5) * t.a
        if nd is not None and not np.isnan(nd):
            self.a[self.a == nd] = np.nan
        self.a[~np.isfinite(self.a)] = np.nan

    def z(self, x, y):
        col, row = (np.asarray(x) - self.x0) / self.px, (self.y0 - np.asarray(y)) / self.px
        return map_coordinates(self.a, [row.ravel(), col.ravel()], order=1, mode="constant", cval=np.nan,
                               prefilter=False).reshape(np.shape(x))


@lru_cache(maxsize=None)
def _fine(prefix):
    return Raster(glob.glob(str(ROOT / "data" / "raw" / "*" / f"{prefix}_final_adj_5mpp_surf.tif"))[0])


@lru_cache(maxsize=None)
def _far(xr, yr):
    return Raster(glob.glob(str(ROOT / "data" / "raw" / "lola80s" / "LDEM_80S_80MPP_ADJ.TIF"))[0],
                  (xr - 32000, yr - 32000, xr + 32000, yr + 32000))


def earth_dirs(et, p0, margin_deg):
    """Unitarios lander→Tierra (MOON_ME, spkpos LT+S) con la elevación bajada ``margin_deg`` a azimut constante."""
    _furnish()
    pos, _ = sp.spkpos("EARTH", et, "MOON_ME", "LT+S", "MOON")
    v = np.asarray(pos) - p0 / 1000.0
    v /= np.linalg.norm(v, axis=1)[:, None]
    if not margin_deg:
        return v
    n = p0 / np.linalg.norm(p0)
    e = np.array([-n[1], n[0], 0.0]) / math.hypot(n[0], n[1])
    nn = np.cross(n, e)
    el, az = np.arcsin(v @ n), np.arctan2(v @ e, v @ nn)
    el2 = el - math.radians(margin_deg)
    return (np.cos(el2)[:, None] * (np.sin(az)[:, None] * e + np.cos(az)[:, None] * nn) + np.sin(el2)[:, None] * n)


def line_of_sight(p0, dirs, fine=None, far=None, chunk=24):
    """True = ningún punto del rayo 3D queda bajo el suelo (DEM 5 m; LOLA 80 m fuera; sin DEM = esfera lisa de radio R)."""
    vis = np.empty(len(dirs), bool)
    for i in range(0, len(dirs), chunk):
        d = dirs[i:i + chunk]
        q = p0[None, None, :] + S_GRID[None, :, None] * d[:, None, :]
        r = np.linalg.norm(q, axis=2)
        if fine is None:
            z = np.zeros_like(r)
        else:
            x, y = xy_of_unit(q / r[..., None])
            z = fine.z(x, y)
            m = np.isnan(z)
            if m.any():
                z[m] = far.z(x[m], y[m])
        vis[i:i + chunk] = ~((r - R) < np.where(np.isnan(z), -np.inf, z)).any(axis=1)
    return vis


# ---------------------------------------------------------------------------------------------- casos de enlace (14 d)
# Mejor punto de la rejilla de idoneidad (data/processed/suitability, perfil lander_solar_no_rhu, top-1) y mejor fecha del motor
# (barrido 2026-12-01..2027-01-01, misión 14 d). Las fechas se fijan aquí para que el método independiente no dependa del motor.
SITES = {"Shackleton": ("Site04", -89.56256875269997, 215.47240065149862, "2026-12-06T00:00:00"),
         "deGerlache": ("Site11", -88.45298231373764, 292.1625756877026, "2026-12-16T00:00:00"),
         "Malapert": ("Site23", -85.96854722720089, 357.68148998571974, "2026-12-13T00:00:00")}
STEP = 120.0


@lru_cache(maxsize=None)
def _ground(site):
    pre, lat, lon, start = SITES[site]
    n = unit_n(lat, lon)
    x, y = xy_of_unit(n)
    fine, far = _fine(pre), _far(round(float(x)), round(float(y)))
    p0 = (R + float(fine.z(np.array([x]), np.array([y]))[0]) + H_OBS) * n
    _furnish()
    t0 = sp.str2et(start)
    et = t0 + STEP * np.arange(0, int(14 * 86400 / STEP) + 1)
    return fine, far, p0, et


@lru_cache(maxsize=None)
def independent_link(site, margin):
    """Mi enlace: LOS 3D del centro de la Tierra (con margen) ∧ alguna estación DSN ve la Luna ≥ 6°."""
    fine, far, p0, et = _ground(site)
    geo = line_of_sight(p0, earth_dirs(et, p0, margin), fine, far)
    net = network_any(et)
    lk = geo & net
    w, g = _intervals(lk, et), _gaps(lk, et)
    return dict(et=et, geo=geo, net=net, link=lk, link_fraction=float(lk[:-1].mean()), geo_fraction=float(geo[:-1].mean()),
                net_fraction=float(net[:-1].mean()), windows=w, gaps=g,
                max_gap_h=float((g[:, 1] - g[:, 0]).max() / 3600.0) if len(g) else 0.0)


@lru_cache(maxsize=1)
def _context():
    from lsi import pipeline
    return pipeline.build_context(ROOT)


@lru_cache(maxsize=None)
def engine_link(site, margin):
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    _, lat, lon, start = SITES[site]
    end = sp.et2utc(sp.str2et(start) + 14 * 86400.0, "ISOC", 0)
    return pipeline.run_analysis(_context(), AnalysisRequest(lat_deg=lat, lon_deg_e=lon, start_utc=start, end_utc=end,
                                                              observer_height_m=H_OBS, snap_to_dem=False,
                                                              min_earth_elevation_deg=margin))


def dem(f):
    """Marca un test que necesita DEM + kernels de ITRF93 y es lento."""
    for m in (needs_bpc, pytest.mark.needs_dem, pytest.mark.slow):
        f = m(f)
    return f


# ============================================================================================ (1) Luna desde cada complejo
def _utc_et(s):
    _furnish()
    return sp.str2et(s.replace(" ", "T") + ":00" if len(s) == 16 else s.replace(" ", "T"))


def test_config_stations_match_810_005_table5_and_table6():
    """Coordenadas y alturas de config/ground_stations.json = Tabla 5 (DMS a mano, WGS 84, h elipsoidal; nota 1: restar la
    separación geoidal para altitud MSL). La Tabla 6 (geocéntricas) es una segunda fuente del mismo PDF."""
    cfg = json.loads((ROOT / "config" / "ground_stations.json").read_text(encoding="utf-8"))
    for sid, (lat, lon, h) in TABLE5.items():
        s = cfg["stations"][sid]
        assert s["lat_deg"] == pytest.approx(lat, abs=1e-8) and s["lon_deg_e"] == pytest.approx(lon, abs=1e-8), sid
        assert s["alt_m"] == h and s["min_elevation_deg"] == RX_MIN and s["tx_min_elevation_deg"] == TX_MIN
        assert s["verified"] and s["default_enabled"]
    for sid, (glat, gr) in TABLE6.items():
        xyz = st_xyz(*TABLE5[sid]) * 1000.0
        assert np.linalg.norm(xyz) == pytest.approx(gr, abs=0.05), sid                  # radio geocéntrico (Tabla 6)
        assert math.degrees(math.asin(xyz[2] / np.linalg.norm(xyz))) == pytest.approx(glat, abs=2e-6), sid


def test_engine_station_geometry_equals_mine():
    from lsi.astronomy import ground_stations as gs
    for st in gs.get_network("DSN").stations:
        lat, lon, h = TABLE5[st.id]
        assert np.abs(gs.station_position_km(st) - st_xyz(lat, lon, h)).max() < 1e-5        # 1 cm (el JSON redondea a 1e-8°≈1 mm)
        assert np.abs(gs.station_up(st) - st_up(lat, lon)).max() < 1e-9


@needs_bpc
def test_three_independent_chains_agree():
    """spkpos en ITRF93 = J2000 + pxform a mano = spkcpo topocéntrico (la estación como observador, 0,46 km/s de aberración)."""
    et = np.array([_utc_et(f"2026-12-{d:02d} {h:02d}:{m:02d}") for d, h, m in ((1, 0, 0), (7, 13, 15), (14, 6, 45), (22, 19, 30), (30, 23, 0))])
    for sid in NAMES:
        a, b, c = (moon_el(et, sid, via=v) for v in ("itrf93", "pxform", "spkcpo"))
        assert np.abs(a - b).max() < 1e-9
        assert np.abs(a - c).max() < 3e-4        # medido 1,2e-4: efecto del movimiento de la estación (aberración diurna)


@needs_bpc
@pytest.mark.parametrize("mon", ("2026-12", "2027-03"))
def test_independent_moon_elevation_vs_horizons(mon):
    """24 instantes por estación y mes (72 por mes, 144 en total) vs JPL Horizons (`HORIZONS`, descargado el 14/11/2026)."""
    et = np.array([_utc_et(u) for u in HORIZONS[mon]["utc"]])
    allerr = []
    for sid in NAMES:
        hz = np.array(HORIZONS[mon][sid])
        assert len(hz) == len(et) == 24
        allerr.append(moon_el(et, sid) - hz)
    e = np.abs(np.concatenate(allerr))
    # dic-2026: máx 1,5e-4° (EOP medidas); mar-2027: 7e-4° (EOP predichas a >3 meses). 0,0015° ≈ 0,4 s de giro terrestre.
    assert e.max() < 0.0015 and np.sqrt((e ** 2).mean()) < 0.001, (mon, e.max())


@needs_bpc
def test_engine_iau_earth_error_vs_horizons_and_vs_mine():
    """El motor (IAU_EARTH) frente a Horizons y frente a mi ITRF93: el sesgo de ≈0,07° documentado en config es real y acotado."""
    from lsi.astronomy import ground_stations as gs
    gs.spice_engine.load_kernels()
    _furnish()
    net = gs.get_network("DSN")
    worst_hz = 0.0
    for mon, v in HORIZONS.items():
        et = np.array([_utc_et(u) for u in v["utc"]])
        for st in net.stations:
            worst_hz = max(worst_hz, float(np.abs(gs.moon_elevation_deg(et, st) - np.array(v[st.id])).max()))
    assert 0.03 < worst_hz < 0.08          # medido 0,0725° (no es cero: no hay motivo para creer un resultado «perfecto»)
    et = np.arange(_utc_et("2026-12-01 00:00"), _utc_et("2027-01-01 00:00"), 600.0)
    for st in net.stations:
        d = gs.moon_elevation_deg(et, st) - moon_el(et, st.id)
        assert np.abs(d).max() < 0.08 and np.sqrt((d ** 2).mean()) < 0.06, st.id


# ============================================================================================ (2) cobertura de red
def _engine_cov(a, b, min_el=None):
    from lsi.astronomy import ground_stations as gs
    gs.spice_engine.load_kernels()
    _furnish()
    net = gs.get_network("DSN", min_elevation_deg=min_el)
    et = np.arange(_utc_et(a), _utc_et(b) + 1e-6, 600.0)
    return gs.network_coverage(et, net)


def _mine_cov(a, b, thr=RX_MIN, step=30.0):
    et = np.arange(_utc_et(a), _utc_et(b) + 1e-6, step)
    ok = network_any(et, thr)
    return et, ok, _intervals(ok, et), _gaps(ok, et)


@needs_bpc
def test_network_coverage_december_2026_vs_engine():
    """Fracción de tiempo con ≥1 DSN viendo la Luna ≥6°: 99,929 % (propio, paso 30 s) vs motor. Huecos REALES: 3, de 8-16 min, a
    las 15-17 UTC de los días 8, 9 y 10 (traspaso Madrid→Goldstone con Canberra ya bajo 6°)."""
    a, b = "2026-12-01 00:00", "2027-01-01 00:00"
    et, ok, iv, gaps = _mine_cov(a, b)
    T = et[-1] - et[0]
    mine = float((iv[:, 1] - iv[:, 0]).sum() / T)
    cov = _engine_cov(a, b)
    eiv = cov.any_intervals()
    eng = float((eiv[:, 1] - eiv[:, 0]).sum() / T)
    assert mine == pytest.approx(0.99929, abs=2e-5) and abs(mine - eng) < 2e-4
    dur = (gaps[:, 1] - gaps[:, 0]) / 60.0
    assert len(gaps) == 3 and dur == pytest.approx([8.5, 15.5, 7.8], abs=0.6)
    days = [sp.et2utc(g, "ISOC", 0) for g in gaps[:, 0]]
    assert [d[:10] for d in days] == ["2026-12-08", "2026-12-09", "2026-12-10"] and all(15 <= int(d[11:13]) <= 17 for d in days)
    egaps = np.column_stack((eiv[:-1, 1], eiv[1:, 0]))
    assert len(egaps) == 3
    assert np.abs(egaps[:, 0] - gaps[:, 0]).max() < 90.0 and np.abs((egaps[:, 1] - egaps[:, 0]) - (gaps[:, 1] - gaps[:, 0])).max() < 60.0
    for i, s in enumerate(cov.network.stations):         # fracción por estación
        m = float(np.mean(moon_el(et, s.id) >= RX_MIN))
        e = float(sum(y - x for x, y in cov.station_intervals()[i]) / T)
        assert abs(m - e) < 3e-4, s.id


@needs_bpc
def test_network_coverage_tx_limit_sensitivity():
    """Reserva: el motor solo modela RECEPCIÓN (6°). Comandar exige transmitir (≥10,1° [pub]; DSS-43 en alta potencia 17,6°):
    con 10,1° la red cubre 97,99 % (37 huecos, el mayor 1,3 h) y con 13,6° 94,2 %. El motor lo permite con
    `link_station_min_elevation_deg`; coincide con mi cálculo."""
    a, b = "2026-12-01 00:00", "2027-01-01 00:00"
    et, ok, iv, gaps = _mine_cov(a, b, TX_MIN)
    T = et[-1] - et[0]
    mine = float((iv[:, 1] - iv[:, 0]).sum() / T)
    cov = _engine_cov(a, b, TX_MIN)
    eiv = cov.any_intervals()
    eng = float((eiv[:, 1] - eiv[:, 0]).sum() / T)
    assert mine == pytest.approx(0.97992, abs=3e-4) and abs(mine - eng) < 1e-3
    assert len(gaps) == 37 and (gaps[:, 1] - gaps[:, 0]).max() / 3600.0 == pytest.approx(1.30, abs=0.05)


# ============================================================================================ (3) enlace posible 3D
def _edge_err(mine_w, eng_w):
    return float(np.abs(np.asarray(mine_w) - np.asarray(eng_w)).max()) if len(mine_w) else 0.0


@dem
@pytest.mark.parametrize("margin", (0.0, 3.0, 5.0))
@pytest.mark.parametrize("site", tuple(SITES))
def test_independent_link_vs_pipeline(site, margin):
    mine, r = independent_link(site, margin), engine_link(site, margin)
    m = r.window_metrics
    assert m.link_fraction == pytest.approx(mine["link_fraction"], abs=0.002)
    assert m.link_hours_per_day_mean == pytest.approx(24 * mine["link_fraction"], abs=0.06)
    assert m.max_link_gap_s / 3600.0 == pytest.approx(mine["max_gap_h"], abs=0.4)
    ew = [(w.start_et, w.end_et) for w in r.link_window.link.windows]
    assert len(ew) == len(mine["windows"]) == 1
    assert _edge_err(mine["windows"], ew) < 1800.0         # bordes a < 30 min (medido 17,5 min máx.: el motor cruza con f_disco ≥ 0,5 y
    # rejilla de 600 s; yo con el centro; la Tierra sube ~0,1°/h cerca del horizonte polar)
    assert m.longest_link_window_s / 3600.0 == pytest.approx((mine["windows"][:, 1] - mine["windows"][:, 0]).max() / 3600.0, abs=0.4)
    # la máscara de red no restringe aquí: enlace = Tierra geométrica en ambos métodos (y la red cubre ≥ 99,8 %)
    assert mine["link_fraction"] == pytest.approx(mine["geo_fraction"], abs=1e-9)
    assert m.network_fraction == pytest.approx(mine["net_fraction"], abs=0.002) and mine["net_fraction"] > 0.998
    if margin == 0.0:
        assert m.link_fraction == pytest.approx(m.earth_fraction, abs=1e-6)     # el enlace no cae por la red


@dem
def test_shackleton_headline_numbers():
    """Tierra 62,1 %, hueco máximo 127,5 h, sin enlace del 6 al 10 de diciembre (y la mañana del 11)."""
    mine, r = independent_link("Shackleton", 0.0), engine_link("Shackleton", 0.0)
    assert mine["link_fraction"] == pytest.approx(0.6207, abs=0.001) and r.window_metrics.link_fraction == pytest.approx(0.6206, abs=0.0005)
    assert mine["max_gap_h"] == pytest.approx(127.4, abs=0.2) and r.window_metrics.max_link_gap_s / 3600.0 == pytest.approx(127.5, abs=0.1)
    et = mine["et"]
    first = sp.et2utc(mine["windows"][0, 0], "ISOC", 0)
    assert "2026-12-11T07:00:00" <= first <= "2026-12-11T08:00:00"
    assert not mine["link"][et < _utc_et("2026-12-11 07:00")].any()                      # 5 días + 7 h sin enlace
    assert mine["windows"][-1, 1] == pytest.approx(et[-1])                                 # el enlace llega al final de la ventana
    assert r.window_metrics.max_link_gap_truncated                                         # el hueco toca el inicio: cota inferior


@dem
def test_gap_threshold_distribution_over_start_dates_shackleton():
    """G7 (12-96 h, supuestos): fracción de fechas de inicio 2026-12-01..2027-03-28 (cada 6 h, misión 14 d) con hueco ≤ umbral en el
    mejor punto de Shackleton. Datos para juzgar si los umbrales discriminan algo."""
    fine, far, p0, _e = _ground("Shackleton")
    et = _utc_et("2026-12-01 00:00") + 600.0 * np.arange(0, 120 * 144 + 1)
    lk = line_of_sight(p0, earth_dirs(et, p0, 0.0), fine, far) & network_any(et)
    n = 14 * 144
    gm = []
    for i0 in range(0, len(et) - n, 36):
        g = _gaps(lk[i0:i0 + n + 1], et[i0:i0 + n + 1])
        gm.append((g[:, 1] - g[:, 0]).max() / 3600.0 if len(g) else 0.0)
    gm = np.array(gm)
    fr = {t: float(np.mean(gm <= t)) for t in (12, 24, 48, 96)}
    print("fracción de inicios con hueco <= umbral:", fr)
    assert fr[12] == pytest.approx(0.22, abs=0.06) and fr[48] == pytest.approx(0.35, abs=0.05) and fr[96] == pytest.approx(0.50, abs=0.05)
    assert np.all(np.diff(list(fr.values())) >= 0) and (gm == 0).any()      # existen ventanas de 14 d sin ningún hueco


@needs_bpc
def test_network_binds_on_a_nearside_site_and_engine_reproduces_gaps():
    """Donde la red SÍ restringe (sitio cercano a la Tierra, esfera lisa: Tierra siempre visible) el motor reproduce los huecos
    DSN reales de 4-16 min del 4, 5 y 6 de enero de 2027."""
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    a, b = "2027-01-03T00:00:00", "2027-01-07T00:00:00"
    lat, lon = -70.0, 0.0
    et = np.arange(_utc_et(a), _utc_et(b) + 1e-6, 30.0)
    p0 = (R + H_OBS) * unit_n(lat, lon)
    geo = line_of_sight(p0, earth_dirs(et, p0, 0.0))
    lk = geo & network_any(et)
    assert geo.all() and not lk.all()
    mg = _gaps(lk, et)
    r = pipeline.run_analysis(_context(), AnalysisRequest(lat_deg=lat, lon_deg_e=lon, start_utc=a, end_utc=b, snap_to_dem=False))
    assert r.metrics.link_fraction == pytest.approx(float(lk[:-1].mean()), abs=3e-4) and r.metrics.earth_fraction == 1.0
    ws = r.timeline.link.link.windows
    eg = np.array([(w0.end_et, w1.start_et) for w0, w1 in zip(ws[:-1], ws[1:])])
    assert len(mg) == len(eg) == 3
    assert np.abs(eg[:, 0] - mg[:, 0]).max() < 90.0
    assert np.abs((eg[:, 1] - eg[:, 0]) - (mg[:, 1] - mg[:, 0])).max() < 40.0


@needs_bpc
# B2 CORREGIDO: ``NetworkCoverage.any_intervals`` (y ``timeline.build_link``) fusionan huecos <= ``handoff_merge_tol_s`` (20 s)
def test_no_spurious_handoff_gap_in_link_windows():
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    t = np.arange(_utc_et("2027-02-02 05:30"), _utc_et("2027-02-02 05:50"), 5.0)
    assert network_any(t).all()                                  # verdad: red continua en el traspaso
    r = pipeline.run_analysis(_context(), AnalysisRequest(lat_deg=-70.0, lon_deg_e=0.0, start_utc="2027-02-01T00:00:00",
                                                          end_utc="2027-02-04T00:00:00", snap_to_dem=False))
    ws = r.timeline.link.link.windows
    gaps = np.array([w1.start_et - w0.end_et for w0, w1 in zip(ws[:-1], ws[1:])])
    assert (gaps > 60.0).all(), gaps       # los huecos reales miden 2,3-15,5 min


# ============================================================================================ (4) hora local
def _nth_sunday(y, m, n):
    """n-ésimo domingo del mes (índice 0 = primero, -1 = último), a mano con calendar."""
    days = [d for d in range(1, calendar.monthrange(y, m)[1] + 1) if calendar.weekday(y, m, d) == 6]
    return days[n]


def manual_offset_h(tz, utc):
    """Desfase UTC→hora civil (h) y abreviatura con las reglas de 2027 escritas a mano (sin zoneinfo)."""
    y = utc.year
    if tz == "Europe/Madrid":       # CEST: último domingo de marzo 01:00 UTC → último domingo de octubre 01:00 UTC
        a = datetime(y, 3, _nth_sunday(y, 3, -1), 1, tzinfo=timezone.utc)
        b = datetime(y, 10, _nth_sunday(y, 10, -1), 1, tzinfo=timezone.utc)
        return (2, "CEST") if a <= utc < b else (1, "CET")
    if tz == "America/Los_Angeles":  # PDT: 2.º domingo de marzo 02:00 PST (10:00 UTC) → 1.er domingo de noviembre 02:00 PDT (09:00 UTC)
        a = datetime(y, 3, _nth_sunday(y, 3, 1), 10, tzinfo=timezone.utc)
        b = datetime(y, 11, _nth_sunday(y, 11, 0), 9, tzinfo=timezone.utc)
        return (-7, "PDT") if a <= utc < b else (-8, "PST")
    if tz == "Australia/Canberra":   # AEDT (UTC+11) entre el 1.er domingo de octubre 02:00 AEST y el 1.er domingo de abril 03:00 AEDT
        end = datetime(y, 4, _nth_sunday(y, 4, 0), 16, tzinfo=timezone.utc) - timedelta(days=1)       # sábado 16:00 UTC
        start = datetime(y, 10, _nth_sunday(y, 10, 0), 16, tzinfo=timezone.utc) - timedelta(days=1)   # sábado 16:00 UTC
        return (10, "AEST") if end <= utc < start else (11, "AEDT")
    raise KeyError(tz)


def test_manual_dst_rules_dates_2027():
    assert (_nth_sunday(2027, 3, -1), _nth_sunday(2027, 10, -1)) == (28, 31)       # Madrid: 28-mar y 31-oct
    assert (_nth_sunday(2027, 4, 0), _nth_sunday(2027, 10, 0)) == (4, 3)           # Canberra: 4-abr y 3-oct
    assert (_nth_sunday(2027, 3, 1), _nth_sunday(2027, 11, 0)) == (14, 7)          # Goldstone (EE. UU.): 14-mar y 7-nov
    assert all(calendar.weekday(2027, m, d) == 6 for m, d in ((3, 28), (10, 31), (4, 4), (10, 3), (3, 14), (11, 7)))


@pytest.mark.parametrize("tz", ("Europe/Madrid", "Australia/Canberra", "America/Los_Angeles"))
def test_engine_local_time_matches_manual_offsets_through_2027(tz):
    """Cada 75 min de 2027 (7 008 instantes): desfase y abreviatura del motor = reglas a mano; y los 6 cambios de DST, al segundo."""
    from lsi.astronomy import ground_stations as gs
    gs.spice_engine.load_kernels()
    t0 = sp.str2et("2027-01-01T00:00:00")
    for k in range(0, 365 * 96, 5):
        et = t0 + 900.0 * k + 1.0     # +1 s: el ET→UTC del motor ignora TDB−TT (±1,7 ms) y 01:00:00 exacto cae en el borde
        utc = datetime(2027, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=900 * k + 1)
        off, ab = manual_offset_h(tz, utc)
        loc = gs.et_to_local(et, tz)
        assert loc.utcoffset() == timedelta(hours=off) and loc.tzname() == ab, (tz, utc)
    flips = {"Europe/Madrid": ("2027-03-28T01:00:00", "2027-10-31T01:00:00"),
             "Australia/Canberra": ("2027-04-03T16:00:00", "2027-10-02T16:00:00"),
             "America/Los_Angeles": ("2027-03-14T10:00:00", "2027-11-07T09:00:00")}[tz]
    for f in flips:
        e = sp.str2et(f)
        before, after = gs.et_to_local(e - 1.0, tz), gs.et_to_local(e + 0.01, tz)   # +10 ms: ET→UTC del motor ignora TDB−TT (<2 ms)
        assert before.utcoffset() != after.utcoffset(), (tz, f)
        assert manual_offset_h(tz, datetime.fromisoformat(f).replace(tzinfo=timezone.utc))[0] * 3600 == after.utcoffset().total_seconds()


DEC_OFF = {"America/Los_Angeles": (-8, "PST"), "Europe/Madrid": (1, "CET"), "Australia/Canberra": (11, "AEDT")}


@dem
def test_contact_windows_local_text_matches_manual_offsets():
    """Todas las ventanas de contacto de Shackleton (6-20 dic): hora local del motor = UTC + desfase manual; y hora solar media."""
    r = engine_link("Shackleton", 0.0)
    cws = r.link_window.contacts
    assert len(cws) >= 10
    for c in cws:
        off, ab = DEC_OFF[c.tz]
        for utc, loc in ((c.start_utc, c.start_local), (c.end_utc, c.end_local)):
            exp = datetime.fromisoformat(utc) + timedelta(hours=off)
            assert loc == exp.strftime("%Y-%m-%d %H:%M:%S ") + ab, (c.station_id, utc, loc)
    lon = {"DSS-14": 243.11046179, "DSS-63": 355.75199146, "DSS-43": 148.98126731}
    for c in cws[:6]:
        u = datetime.fromisoformat(c.start_utc)
        exp = (u.hour + u.minute / 60 + u.second / 3600 + lon[c.station_id] / 15.0) % 24.0
        assert c.start_solar_h == pytest.approx(exp, abs=1e-3)


def _day12_pieces(r):
    """Trozos locales por estación del día UTC 12-dic: UTC recortado a [00:00, 24:00) y convertido a mano."""
    t0, t1 = sp.str2et("2026-12-12T00:00:00"), sp.str2et("2026-12-13T00:00:00")
    out = {}
    for c in r.link_window.contacts:
        a, b = max(c.start_et, t0), min(c.end_et, t1)
        if b <= a:
            continue
        off, ab = DEC_OFF[c.tz]
        out.setdefault(c.station_id, []).append(f"{_hhmm(a, off)}-{_hhmm(b, off)} {ab}")
    return out


def _hhmm(e, off):
    return (datetime.fromisoformat(sp.et2utc(e, "ISOC", 0)) + timedelta(hours=off)).strftime("%H:%M")   # truncado al minuto, como el motor


@dem
def test_daily_table_day12_shows_whole_real_windows():
    """B3 CORREGIDO: la tabla diaria ya NO parte las ventanas por día UTC (eso fabricaba «09:34-22:11 AEDT»): muestra cada ventana REAL entera,
    con «continúa…» si cruza la medianoche UTC; las horas por estación dentro del día son un número aparte (los trozos recortados de mi cadena)."""
    from lsi.astronomy import ground_stations as gs
    r = engine_link("Shackleton", 0.0)
    row = next(x for x in gs.daily_contact_table(r.link_window.contacts, float(r.sky.et[0]), float(r.sky.et[-1])) if x["day_utc"] == "2026-12-12")
    mine = _day12_pieces(r)
    assert sorted(mine) == ["DSS-14", "DSS-43", "DSS-63"]
    t0, t1 = sp.str2et("2026-12-12T00:00:00"), sp.str2et("2026-12-13T00:00:00")
    for sid in mine:
        real = [c for c in r.link_window.contacts if c.station_id == sid and c.end_et > t0 and c.start_et < t1]
        got = row["stations"][sid]["windows"]
        assert [w["start_utc"] for w in got] == [c.start_utc for c in real] and [w["end_utc"] for w in got] == [c.end_utc for c in real], sid
        assert row["stations"][sid]["hours"] == pytest.approx(sum(min(c.end_et, t1) - max(c.start_et, t0) for c in real) / 3600.0)


def _has_window(r, sid, hhmm_start, hhmm_end):
    """¿Existe UNA ventana de contacto de ``sid`` con inicio y fin locales hhmm_start-hhmm_end dentro del mismo día civil?"""
    return any(c.station_id == sid and c.start_local[11:16] == hhmm_start and c.end_local[11:16] == hhmm_end
               and c.start_local[:10] == c.end_local[:10] for c in r.link_window.contacts)


@dem
def test_report_text_madrid_12dec_is_a_real_window():
    assert _has_window(engine_link("Shackleton", 0.0), "DSS-63", "12:00", "20:06")


@dem
@pytest.mark.parametrize("sid,fused", [("DSS-43", "09:34-22:11"), ("DSS-14", "10:21-18:12")])
def test_report_text_day12_has_no_fused_windows(sid, fused):
    """B3 CORREGIDO. Antes el texto del día 12 decía «Canberra 09:34-22:11 AEDT» (final de la ventana del 12 unido al inicio de la del 13) y
    «Goldstone 10:21-18:12 PST» (inicio de la del 12 unido al final de la del 11): ventanas que no existen. Ahora cada texto es una ventana
    real (``_has_window`` sobre los contactos) y la fusionada ya no sale (ni con el minuto truncado ni con el redondeado)."""
    from lsi.astronomy import ground_stations as gs
    r = engine_link("Shackleton", 0.0)
    row = next(x for x in gs.daily_contact_table(r.link_window.contacts, float(r.sky.et[0]), float(r.sky.et[-1])) if x["day_utc"] == "2026-12-12")
    assert fused not in row["text"] and not _has_window(r, sid, *fused.split("-"))
    real = {"DSS-43": ("08:37-22:12 AEDT", "09:35-22:46 AEDT"), "DSS-14": ("09:48-18:13 PST", "10:22-19:14 PST")}[sid]
    assert all(any(x in t for t in row["stations"][sid]["local"]) for x in real), row["stations"][sid]["local"]


# ============================================================================================ (5) s_earth y G7
def _score_cfg():
    return json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))["score"]


def _inputs(f, ref, **kw):
    from lsi.contracts import ScoreInputs
    return ScoreInputs(f_sun=1.0, d_max_h=0.0, f_earth=f, f_earth_ref=ref, slope_p90_deg=0.0, unknown_fraction=0.0,
                       observer_in_dem=True, has_dem=True, link_mode=True, **kw)


def _s_earth(f, ref, profile="lander_solar_no_rhu"):
    from lsi.analysis.site_score import params_from_config, profiles_from_config, subscores
    cfg = _score_cfg()
    return subscores(_inputs(f, ref), profiles_from_config(cfg)[profile], params_from_config(cfg))["earth"]


def test_s_earth_hand_values_floor_and_saturation():
    assert _s_earth(0.30, 0.50) == pytest.approx(0.60)               # f/ref
    assert _s_earth(0.10, 0.05) == pytest.approx(0.40)               # suelo 0,25: f/0,25
    assert _s_earth(0.62, 0.361) == 1.0 and _s_earth(1.0, 0.742) == 1.0
    assert _s_earth(0.45, 0.20, "dte_comms") == pytest.approx(0.90)  # suelo del perfil 0,5
    assert _s_earth(0.0, 0.5) == 0.0


def test_s_earth_monotone_bounded_and_continuous():
    fs = np.linspace(0, 1, 401)
    for ref in (0.05, 0.25, 0.36, 0.5, 0.74, 1.0):
        s = np.array([_s_earth(f, ref) for f in fs])
        knee = max(ref, 0.25)
        assert (np.diff(s) >= -1e-12).all() and s.min() >= 0 and s.max() <= 1.0 + 1e-12, ref
        assert np.abs(np.diff(s)).max() <= (fs[1] - fs[0]) / knee + 1e-9                    # sin saltos (Lipschitz 1/max(ref, suelo))
        assert all(_s_earth(f, ref) == pytest.approx(1.0) for f in fs if f >= knee)
    for f in (0.2, 0.5):                                                                   # no creciente en la referencia
        s = [_s_earth(f, r) for r in np.linspace(0.05, 1.0, 96)]
        assert (np.diff(s) <= 1e-12).all()


def test_s_earth_saturation_hides_a_127h_blackout():
    """La parte RELATIVA de s_earth (sin hueco medido) sigue saturando: 62 % y 100 % dan 1 porque f_ref (0,36 / 0,74) es la esfera lisa de
    ESA ventana. Lo que ya no oculta el apagón es la continuidad absoluta, que entra cuando hay hueco medido (ver test_site_score.py:
    test_continuidad_hueco_127h_puntua_claramente_menos_que_enlace_continuo)."""
    assert _s_earth(0.6206, 0.361) == _s_earth(1.0, 0.742) == 1.0
    from dataclasses import replace as _r
    from lsi.analysis.site_score import params_from_config, profiles_from_config, subscores
    cfg = _score_cfg()
    prof, par = profiles_from_config(cfg)["lander_solar_no_rhu"], params_from_config(cfg)
    assert subscores(_inputs(0.6206, 0.361, max_link_gap_h=127.5), prof, par)["earth"] == pytest.approx(2.0 ** (-127.5 / 48.0))
    assert subscores(_inputs(1.0, 0.742, max_link_gap_h=0.0), prof, par)["earth"] == 1.0


def test_g7_limits_and_boundary():
    from lsi.analysis.site_score import evaluate_gates, params_from_config, profiles_from_config
    cfg = _score_cfg()
    prof = profiles_from_config(cfg)
    P = params_from_config(cfg)
    got = {k: prof[k].max_link_gap_h for k in ("lander_solar_no_rhu", "lander_with_batteries", "lander_rhu", "rover", "base_isru", "dte_comms")}
    assert got == {"lander_solar_no_rhu": 48, "lander_with_batteries": 48, "lander_rhu": 96, "rover": 24, "base_isru": 12, "dte_comms": 24}
    assert all(prof[k].max_link_gap_type == "soft" for k in prof if k != "custom")
    for gap, ok in ((47.9, True), (48.0, True), (48.1, False), (127.5, False)):
        g = next(x for x in evaluate_gates(_inputs(0.6, 0.4, max_link_gap_h=gap), prof["lander_solar_no_rhu"], P, None) if x.id == "G7")
        assert (g.status.name == "PASS") == ok and not g.hard


def _shackleton_run(a, b):
    from lsi import pipeline
    from lsi.contracts import AnalysisRequest
    return pipeline.run_analysis(_context(), AnalysisRequest(lat_deg=SITES["Shackleton"][1], lon_deg_e=SITES["Shackleton"][2], start_utc=a,
                                                              end_utc=b, snap_to_dem=False))


def _g7(r):
    return next(x for x in r.score.gates if x.id == "G7").status.name


@dem
def test_best_start_ties_on_score_while_gap_differs():
    """B1 CORREGIDO (s_earth): 2026-12-06 (enlace 62 %, hueco 127 h, G7 FAIL) y 2026-12-11T08 (enlace 100 %, G7 PASS) puntuaban IGUAL (97,41);
    ahora la primera cae a ~74 (73,9; continuidad ABSOLUTA del enlace) y la segunda sigue en 97,41."""
    r1, r2 = _shackleton_run("2026-12-06T00:00:00", "2026-12-20T00:00:00"), _shackleton_run("2026-12-11T08:00:00", "2026-12-25T08:00:00")
    assert r2.score.score == pytest.approx(97.41, abs=0.01) and r1.score.score == pytest.approx(73.9, abs=0.3)
    assert r2.score.score - r1.score.score > 20.0
    assert (_g7(r1), _g7(r2)) == ("FAIL", "PASS") and r2.window_metrics.link_fraction > 0.999
    assert r1.score.verdict == "CONDICIONAL" and "hueco sin comunicaciones" in r1.score.verdict_reason
    assert independent_link("Shackleton", 0.0)["max_gap_h"] > 120          # mi enlace independiente confirma el hueco de la elegida


@dem
def test_best_start_does_not_fail_soft_g7_when_a_tied_start_passes():
    """B1 CORREGIDO (selección de fecha): el barrido puntúa con el hueco, y la mejor fecha prefiere las que cumplen G7 (luego mayor score)."""
    r = _shackleton_run("2026-12-01T00:00:00", "2027-01-01T00:00:00")
    assert _g7(r) == "PASS" and r.score.best_start_utc == "2026-12-12T00:00:00" and r.window_metrics.max_link_gap_s == 0.0


@needs_bpc
def test_live_horizons_spot_check():
    """Contraste en vivo (se omite sin red): 1 instante por estación contra la API oficial."""
    requests = pytest.importorskip("requests")
    for sid in NAMES:
        lat, lon, h = TABLE5[sid]
        p = {"format": "json", "COMMAND": "'301'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'", "CENTER": "'coord@399'",
             "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{lon},{lat},{h / 1000.0}'", "QUANTITIES": "'4'", "ANG_FORMAT": "'DEG'",
             "CAL_FORMAT": "'CAL'", "APPARENT": "'AIRLESS'", "TLIST": "'2026-12-15 03:10'"}
        try:
            rr = requests.get("https://ssd.jpl.nasa.gov/api/horizons.api", params=p, timeout=60)
            rr.raise_for_status()
            el = float(rr.json()["result"].split("$$SOE")[1].split("$$EOE")[0].split()[-1])
        except Exception as e:   # noqa: BLE001 — sin red / API caída
            pytest.skip(f"Horizons no accesible: {e}")
        assert moon_el(_utc_et("2026-12-15 03:10"), sid)[0] == pytest.approx(el, abs=0.002)
