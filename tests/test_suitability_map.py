"""Mapa de idoneidad: DEM sintético (meseta plana + muro), prefiltro, separación mínima, determinismo, caché."""
import dataclasses
import json
import math
import sys

import numpy as np
import pytest

from lsi.analysis import suitability_map as sm
from lsi.astronomy import spice_engine
from lsi.contracts import Body, MissionProfile, Threshold
from lsi.data import catalog
from lsi.terrain.slope import footprint_slope

pytestmark = pytest.mark.needs_spice

@pytest.fixture(autouse=True)
def _spawn_safe_main(monkeypatch):
    """``streamlit.testing.AppTest.from_function`` (tests de páginas de UI) deja ``sys.modules['__main__']`` apuntando a un
    script temporal. Un ``ProcessPoolExecutor`` con *spawn* (Windows) lo re-ejecuta en cada hijo: el hijo muere en el arranque y
    el padre se queda bloqueado escribiendo en la tubería (suite completa colgada en ``test_deterministic_and_parallel_equal``).
    Sin ``__file__`` el hijo no re-importa nada: el aislamiento queda en el test, sin tocar ``ui/``."""
    main = sys.modules.get("__main__")
    if main is not None and getattr(main, "__file__", None) and "pytest" not in str(main.__file__).lower():
        monkeypatch.delattr(main, "__file__", raising=False)
        monkeypatch.setattr(main, "__spec__", None, raising=False)


WALL_Y = 3000.0          # el muro empieza en y = 3000 m y sube con pendiente 0.5 (26.6°) sin meseta superior


@pytest.fixture(scope="module")
def cfg():
    from conftest import ROOT
    return catalog.load_simulation_config(ROOT / "config" / "simulation.json")


@pytest.fixture(scope="module")
def surf():
    """20x20 km a 10 m/px cerca del polo: meseta z=0 y un muro hacia +y (el horizonte mejora al alejarse de él)."""
    from lsi.contracts import DemLayer, DemWindow
    n = 2000
    ys = 10000.0 - 10.0 * np.arange(n)
    z = np.maximum(0.5 * (ys - WALL_Y), 0.0)[:, None] * np.ones((1, n))
    return DemWindow(data=z.astype(np.float32), x0_m=10000.0, y0_m=10000.0, pixel_size_m=10.0, layer=DemLayer.SURF)


@pytest.fixture(scope="module")
def setup(cfg, surf):
    params = sm.SuitabilityParams(step_m=1000.0, margin_m=3500.0, days=365.0, step_s=3600.0, top_n=3,
                                  min_separation_m=2500.0, az_step_deg=2.0, radial_step_m=20.0)
    et = sm.time_grid(params)
    eph = sm.ephemeris(et)
    profile = catalog.score_profiles(cfg)["lander_solar_no_rhu"]
    mission = MissionProfile("t", "t", {"max_landing_slope_deg": Threshold(10.0, "hard", "publicado")})
    hp = dataclasses.replace(catalog.horizon_params(cfg, 2.0), r_max_m=3000.0)
    kw = dict(dem_key="synt", profile=profile, mission=mission, score_params=catalog.score_params(cfg), hp=hp,
              vp=catalog.visibility_params(cfg), tp=catalog.timeline_params(cfg), params=params, eph=eph, et=et)
    return kw


@pytest.fixture(scope="module")
def result(surf, setup):
    return sm.compute_map(surf, None, None, workers=1, **setup)


def test_top1_on_flat_zone_far_from_wall(result):
    top = result.top
    assert len(top) == 3
    assert all(s.y_m < WALL_Y for s in top)                      # zona plana
    assert top[0].score == pytest.approx(np.nanmax(result.layers["score"]), abs=1e-4)
    ev = result.aptitude == sm.APT_EVAL
    y_ev = np.broadcast_to(result.y_m[:, None], ev.shape)[ev]
    # el mejor horizonte está en el tercio más alejado del muro
    assert top[0].y_m <= y_ev.min() + (WALL_Y - y_ev.min()) / 3.0
    # y la fracción solar crece al alejarse del muro (medida independiente: correlación negativa con y)
    f = result.layers["f_sun"][ev]
    assert np.corrcoef(y_ev, f)[0, 1] < -0.5


def test_prefilter_excludes_walls_and_edges(result, surf):
    ys = result.y_m
    wall_rows = ys > WALL_Y + 100.0
    assert wall_rows.any() and (result.aptitude[wall_rows] == sm.APT_STEEP).all()
    assert np.isnan(result.layers["score"][wall_rows]).all()     # sin cómputo de horizonte en las paredes
    assert (result.aptitude[~wall_rows & (ys < WALL_Y - 100.0)] == sm.APT_EVAL).all()
    # el margen: ningún nodo a menos de margin_m del borde
    assert result.x_m.min() >= surf.x0_m + result.params.margin_m - 1e-9
    assert result.y_m.min() >= surf.y0_m - 1999 * 10.0 + result.params.margin_m - 1e-9


def test_footprint_p90_matches_terrain_slope(make_dem_window):
    rng = np.random.default_rng(1)
    z = np.cumsum(rng.normal(0, 0.6, (120, 120)), axis=1) + np.cumsum(rng.normal(0, 0.6, (120, 120)), axis=0)
    w = make_dem_window(z, 5.0, 0.0, 0.0)
    xs, ys = np.array([150.0, 300.0]), np.array([-200.0, -420.0, -300.0])
    p90, frac = sm.footprint_slope_p90(np.asarray(sm.slope_map_deg(w), np.float64), w, xs, ys, 50.0, 90.0)
    for i, y in enumerate(ys):
        for j, x in enumerate(xs):
            ref = footprint_slope(w, x, y, 50.0, 90.0, None, 10.0).percentile_deg
            assert p90[i, j] == pytest.approx(ref, abs=1e-9)
    assert (frac == 1.0).all()


def test_slope_limit_from_profile(cfg):
    mission = MissionProfile("t", "t", {"max_landing_slope_deg": Threshold(7.5, "hard", "publicado")})
    sp_ = catalog.score_params(cfg)
    assert sm.slope_limit(sm.SuitabilityParams(), mission, sp_) == 7.5
    assert sm.slope_limit(sm.SuitabilityParams(slope_limit_deg=12.0), mission, sp_) == 12.0
    assert sm.slope_limit(sm.SuitabilityParams(), None, sp_) == sp_.g2_max_slope_deg


def test_select_top_min_separation_and_clusters():
    x, y = np.arange(10) * 100.0, 900.0 - np.arange(10) * 100.0
    s = np.full((10, 10), np.nan)
    s[2, 2], s[2, 3], s[3, 2] = 90.0, 89.0, 88.0         # un racimo de vecinos
    s[7, 8], s[7, 7] = 70.0, 69.0                       # otro racimo, peor
    s[9, 0] = 10.0
    g = np.zeros_like(s)
    picks = sm.select_top(s, g, x, y, 3, 300.0)
    assert picks == [(2, 2), (7, 8), (9, 0)]            # un punto por racimo
    for a in range(3):
        for b in range(a):
            (r1, c1), (r2, c2) = picks[a], picks[b]
            assert math.hypot(x[c1] - x[c2], y[r1] - y[r2]) >= 300.0
    assert sm.select_top(s, g, x, y, 2, 0.0) == [(2, 2), (2, 3)]   # sin separación, los dos mejores
    # puertas primero: un FAIL no desplaza a un PASS aunque tenga más score
    g[2, 2] = 2
    assert sm.select_top(s, g, x, y, 1, 300.0) == [(2, 3)]
    assert sm.select_top(s, g, x, y, 1, 300.0, rank_by_gates=False) == [(2, 2)]
    assert sm.select_top(np.full((3, 3), np.nan), np.zeros((3, 3)), x[:3], y[:3], 3, 1.0) == []


def test_deterministic_and_parallel_equal(surf, setup, result):
    again = sm.compute_map(surf, None, None, workers=1, **setup)
    for k in sm.FLOAT_LAYERS:
        np.testing.assert_array_equal(result.layers[k], again.layers[k])
    assert [(s.row, s.col) for s in result.top] == [(s.row, s.col) for s in again.top]
    par = sm.compute_map(surf, None, None, workers=2, **setup)
    for k in sm.FLOAT_LAYERS:
        np.testing.assert_array_equal(result.layers[k], par.layers[k])


def test_sky_from_ephemeris_equals_body_track(setup):
    et, eph = setup["et"][:50], setup["eph"]
    sky = sm.sky_from_ephemeris({**eph, Body.SUN.value: eph["SUN"][:50], Body.EARTH.value: eph["EARTH"][:50]},
                                et, -89.6, 215.5, 2.0)
    for body, tr in ((Body.SUN, sky.sun), (Body.EARTH, sky.earth)):
        ref = spice_engine.body_track(et, -89.6, 215.5, body, 2.0)
        np.testing.assert_allclose(tr.el_deg, ref.el_deg, atol=1e-9)
        np.testing.assert_allclose(tr.az_deg, ref.az_deg, atol=1e-9)
        np.testing.assert_allclose(tr.radius_deg, ref.radius_deg, atol=1e-12)


def test_cache_roundtrip_and_key_sensitivity(surf, setup, result, tmp_path):
    kw = {k: setup[k] for k in ("profile", "mission", "score_params", "hp", "vp", "tp", "params", "eph")}
    key = sm.cache_key(surf, None, None, **{**kw, "score_params": kw["score_params"]})
    result.cache_key = key
    sm._save(tmp_path, result)
    hit = sm._load(tmp_path, key, setup["profile"])
    assert hit is not None and hit.cached
    for k in sm.FLOAT_LAYERS:
        np.testing.assert_array_equal(result.layers[k], hit.layers[k])
    assert [(s.row, s.col, s.score) for s in hit.top] == [(s.row, s.col, s.score) for s in result.top]
    assert hit.params == result.params
    # otro perfil / otros parámetros / otro DEM → otra clave
    other = dataclasses.replace(kw["params"], step_s=1800.0)
    assert sm.cache_key(surf, None, None, **{**kw, "params": other}) != key
    surf2 = dataclasses.replace(surf, data=surf.data + np.float32(1.0))
    assert sm.cache_key(surf2, None, None, **kw) != key
    assert sm._load(tmp_path, "0" * 64, setup["profile"]) is None
    json.dumps(sm.dataclasses.asdict(result.top[0]))   # el TOP-N es serializable


def test_mission_windows_in_map(surf, setup, result, tmp_path):
    """Ventanas sobre el mismo DEM sintético: una ventana igual al periodo reproduce la fracción anual (±1 paso de
    rejilla, el anual interpola cruces), la mejor fecha no empeora ninguna otra y la caché devuelve lo mismo."""
    params = dataclasses.replace(setup["params"], window_durations_days=(14.0, 365.0), window_step_days=5.0)
    m = sm.compute_map(surf, None, None, workers=1, **{**setup, "params": params})
    for k in sm.FLOAT_LAYERS:                                       # el mapa anual no cambia
        np.testing.assert_array_equal(result.layers[k], m.layers[k])
    w14, wfull = m.windows[14.0], m.windows[365.0]
    assert wfull.n_starts == 1 and w14.n_starts == int((365 - 14) / 5) + 1
    f_year = m.layers["f_sun"][wfull.rows, wfull.cols]
    np.testing.assert_allclose(wfull.cube["f_sun"][:, 0], f_year, atol=2 * 3600.0 / (365 * 86400.0) * 24)
    assert (w14.best["score"] >= w14.cube["score"].min(axis=1) - 1e-3).all()
    ok = w14.best["gate"] == 0
    assert (w14.cube["score"].max(axis=1)[ok] <= w14.best["score"][ok] + 1e-3).all()
    assert len(w14.top) == 3 and all(s.duration_days == 14.0 and s.n_starts == w14.n_starts for s in w14.top)
    assert w14.top[0].best_start_utc.startswith("20")
    json.dumps([dataclasses.asdict(s) for s in w14.top])
    m.cache_key = "w" * 64
    sm._save(tmp_path, m)
    hit = sm._load(tmp_path, m.cache_key, setup["profile"])
    for d, wm in m.windows.items():
        for k in wm.cube:
            np.testing.assert_array_equal(wm.cube[k], hit.windows[d].cube[k])
        assert [(s.x_m, s.best_start_et) for s in wm.top] == \
            [(s.x_m, s.best_start_et) for s in hit.windows[d].top]


# ---------------------------------------------------------------------------------------------- best_points (snap al mejor punto)
def _windows_doc(tmp_path, name, mtime, *, module_version, results, schema="lsi.suitability.windows/1"):
    import json
    import os
    d = tmp_path / sm.KIND
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text(json.dumps(dict(schema_version=schema, module_version=module_version, key="k", results=results)), encoding="utf-8")
    os.utime(p, (mtime, mtime))


def _res(site, prof, dur, lat):
    return {f"{site}|{prof}|{dur:g}d": dict(duration_days=float(dur), top=[dict(rank=1, lat_deg=lat, lon_deg_e=1.0)])}


def test_best_points_picks_newest_current_version_and_closest_duration(tmp_path):
    cur = sm.MODULE_VERSION
    _windows_doc(tmp_path, "windows_a.json", 1000, module_version=cur, results={**_res("S", "p", 7, -1.0), **_res("S", "p", 14, -2.0)})
    _windows_doc(tmp_path, "windows_b.json", 2000, module_version=cur, results={**_res("S", "p", 7, -3.0), **_res("S", "p", 30, -4.0)})
    _windows_doc(tmp_path, "windows_old.json", 3000, module_version=cur - 1, results=_res("S", "p", 14, -9.0))   # versión vieja: se ignora
    _windows_doc(tmp_path, "windows_x.json", 3000, module_version=cur, results=_res("S", "p", 14, -9.0), schema="otro/1")
    g = lambda d, s="S", p="p": sm.best_points(tmp_path, s, p, d)   # noqa: E731
    assert g(7)["top"][0]["lat_deg"] == -3.0 and g(7)["duration_days"] == 7.0            # el más reciente con la versión actual
    assert g(14)["duration_days"] == 7.0 and g(14)["requested_days"] == 14.0            # b no tiene 14 d: |7-14| < |30-14|
    assert g(20)["duration_days"] == 30.0                                               # |30-20| < |7-20|
    assert g(100)["duration_days"] == 30.0 and g(1)["duration_days"] == 7.0
    assert g(14, p="rover") is None and g(14, s="T") is None and sm.best_points(tmp_path / "no", "S", "p", 14) is None


def test_link_layer_is_below_geometric_and_single_station_is_lower(surf, setup, result):
    """f_earth del mapa = fracción de ENLACE (Tierra ∧ red): ≤ la geométrica; la red DSN la baja ≲ 0,1 %; una estación sola mucho más."""
    from lsi.astronomy import ground_stations as gs
    et = setup["et"]
    dsn = gs.make_link_context(et, "DSN", 0.0)
    m = sm.compute_map(surf, None, None, workers=1, link=dsn, **setup)
    ok = np.isfinite(result.layers["f_earth"])
    f_g, f_l = result.layers["f_earth"][ok], m.layers["f_earth"][ok]
    assert (f_l <= f_g + 1e-6).all()
    assert (f_g - f_l).max() <= (1.0 - dsn.coverage.any_grid.mean()) + 0.01
    np.testing.assert_array_equal(m.layers["f_sun"], result.layers["f_sun"])        # el Sol no cambia
    one = gs.make_link_context(et, "custom", 0.0, custom=[(40.43, -4.25, 6.0)])
    m1 = sm.compute_map(surf, None, None, workers=1, link=one, **setup)
    assert np.nanmean(m1.layers["f_earth"]) < 0.7 * np.nanmean(result.layers["f_earth"])
    m5 = sm.compute_map(surf, None, None, workers=1, link=gs.make_link_context(et, "DSN", 5.0), **setup)
    assert (m5.layers["f_earth"][ok] <= m.layers["f_earth"][ok] + 1e-6).all()      # más margen, menos enlace


# ---------------------------------------------------------------------------------------------- enlace: continuidad, G7 y sentido (revision-enlace)
def test_module_version_6_and_link_direction_default():
    assert sm.MODULE_VERSION >= 6                       # s_earth con continuidad + mejor fecha por G7 + sentido del enlace: los mapas v5 no valen
    assert sm.SuitabilityParams().link_direction == "receive"
    assert "gap_h" in sm._CUBE and {"gap_h", "g7_ok"} <= set(sm._BEST)
    assert {"max_link_gap_h", "g7_ok"} <= {f.name for f in dataclasses.fields(sm.WindowSite)}


def test_precomputed_windows_carry_gap_and_g7_for_the_best_points():
    """Los mapas precalculados (MODULE_VERSION actual): el mejor punto de cada duración trae el hueco máximo de su mejor ventana y si cumple
    G7; la mejor fecha prefiere G7 (la de Shackleton ya no es el 6-dic con 127 h de hueco). Se omite si no hay mapas precalculados."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "data" / "processed"
    bp = sm.best_points(root, "Site04", "lander_solar_no_rhu", 14.0)
    if bp is None:
        pytest.skip("sin mapa precalculado de Site04 (python scripts/precompute_suitability.py --duration 14)")
    top = bp["top"][0]
    assert top["max_link_gap_h"] == 0.0 and top["g7_ok"] is True and top["best_start_utc"].startswith("2026-12-12")
    assert all(t["max_link_gap_h"] is not None and t["g7_ok"] is not None for t in bp["top"])


def test_best_points_accepts_windows_schema_v1_and_v2(tmp_path):
    cur = sm.MODULE_VERSION
    _windows_doc(tmp_path, "windows_v1.json", 1000, module_version=cur, results=_res("S", "p", 14, -1.0))
    assert sm.best_points(tmp_path, "S", "p", 14)["top"][0]["lat_deg"] == -1.0           # /1: sigue legible
    _windows_doc(tmp_path, "windows_v2.json", 2000, module_version=cur, results=_res("S", "p", 14, -2.0), schema="lsi.suitability.windows/2")
    assert sm.WINDOWS_REVISION == 2 and sm.WINDOWS_SCHEMA.endswith("/1") and sm.best_points(tmp_path, "S", "p", 14)["top"][0]["lat_deg"] == -2.0


def test_precomputed_top_separates_resolution_from_real_uncertainty():
    """schema_revision 2: ``score_range_resolution`` (±1 paso temporal) y ``score_range_uncertainty`` (escenarios reales) son claves distintas;
    la incertidumbre real contiene al score fino y ``score_min/max`` sigue siendo alias de la resolución. Se omite sin mapas rev. 2."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "data" / "processed"
    bp = sm.best_points(root, "Site11", "lander_solar_no_rhu", 30.0)
    if bp is None or "score_range_uncertainty" not in bp["top"][0]:
        pytest.skip("sin mapa /2 (python scripts/precompute_suitability.py --duration 30)")
    for t in bp["top"]:
        assert t["score_range_resolution"] == [t["score_min"], t["score_max"]]
        lo, hi = t["score_range_uncertainty"]
        assert lo - 1e-6 <= t["score_fine"] <= hi + 1e-6 and "resolución" in t["score_range_resolution_note"]
        assert set(t["scenario_scores"]) <= {"coverage_ub", "sigma_plus", "sigma_minus", "az_step_0.5"} and t["scenarios_run"]
    t = bp["top"][0]   # Site11 30 d: el score del modelo fino se mueve con σz (rango real > rango de resolución)
    assert t["score_range_uncertainty"][1] - t["score_range_uncertainty"][0] > t["score_max"] - t["score_min"] + 1.0
