"""Incertidumbre (T15): escenarios -> Range por métrica. DEM sintético con cobertura limitada y SPICE real."""
import numpy as np
import pytest

from lsi.analysis.metrics import compute_metrics
from lsi.astronomy import spice_engine
from lsi.astronomy.coordinates import stereo_forward
from lsi.contracts import (
    DemLayer, HorizonMode, HorizonParams, ObserverPoint, TimelineParams, UncertaintyParams, VisibilityParams,
)
from lsi.simulation.timeline import run_timeline
from lsi.simulation.uncertainty import RANGE_METRICS, run_uncertainty
from lsi.simulation.visibility import visibility_series
from lsi.terrain.horizon import compute_horizon, smooth_sphere_result

pytestmark = pytest.mark.needs_spice

LAT, LON = -89.9, 0.0
VP, TP = VisibilityParams(), TimelineParams()


@pytest.fixture(scope="module")
def sky():
    spice_engine.load_kernels()
    et0 = spice_engine.utc_to_et("2026-12-01T00:00:00")
    et = spice_engine.et_grid(et0, et0 + 15 * 86400.0, 600.0)
    return spice_engine.sky_series(et, LAT, LON, 2.0)


def _obs(mode=HorizonMode.DEM):
    x, y = (float(v) for v in stereo_forward(np.float64(LAT), np.float64(LON)))
    return ObserverPoint(LAT, LON, x, y, 2.0, mode, ground_z_m=0.0 if mode is HorizonMode.DEM else None)


def _dem(make_dem_window, obs, wall_m=300.0):
    """Llano a z=0 de 1 km x 1 km con UN píxel de pared en la esquina: el DEM no cubre más allá y z_up = wall_m."""
    z = np.zeros((201, 201))
    z[0, 0] = wall_m
    w = make_dem_window(z, 5.0, obs.x_m - 500.0, obs.y_m + 500.0)
    sg = make_dem_window(np.full((201, 201), 0.5), 5.0, obs.x_m - 500.0, obs.y_m + 500.0, layer=DemLayer.TOTERR)
    return w, sg


def test_dem_coverage_scenario_lowers_sun_and_orders_ranges(make_dem_window, sky):
    obs, hp = _obs(), HorizonParams(r_max_m=3000.0)
    w, sg = _dem(make_dem_window, obs)
    hor = compute_horizon(w, obs, hp)
    assert hor.limited.all() and hor.h_ub_deg is not None and hor.h_ub_deg.min() > 20.0   # pared a ~500 m, 300 m de alto
    m0 = compute_metrics(run_timeline(sky, hor, VP, TP), sky, hor, VP)
    assert m0.solar_fraction > 0.2   # el nominal (H_lb ≈ esfera) ve el Sol buena parte de los 15 d
    res = run_uncertainty(w, sg, obs, hor, sky, VP, TP, hp, UncertaintyParams(), m0)
    names = [s.name for s in res.scenarios]
    assert {"coverage_ub", "sigma_plus", "sigma_minus"} <= set(names)
    cov = next(s for s in res.scenarios if s.name == "coverage_ub")
    assert cov.metrics.solar_fraction == 0.0 and cov.metrics.max_darkness_s > m0.max_darkness_s   # H_ub tapa el Sol
    assert set(res.ranges) == set(RANGE_METRICS)
    for k, r in res.ranges.items():
        assert r.lo <= r.nominal <= r.hi, k
        assert r.nominal == pytest.approx(getattr(m0, k))
    r = res.ranges["solar_fraction"]
    assert r.lo == 0.0 and r.hi == pytest.approx(m0.solar_fraction)   # el nominal es la cota optimista (H_lb)
    assert res.ranges["max_darkness_s"].hi == pytest.approx(m0.period_s)   # con H_ub: oscuridad todo el periodo


def test_sigma_scenario_equals_manual_horizon(make_dem_window, sky):
    """Escenario σ+ == compute_horizon(..., +1, k) + timeline a mano (valor esperado independiente del módulo)."""
    obs, hp = _obs(), HorizonParams(r_max_m=3000.0, compute_upper_bound=False)
    w, _ = _dem(make_dem_window, obs, wall_m=5.0)
    z = np.zeros((201, 201))
    z[:, 100:] = 0.0
    xx = np.arange(201)[None, :] * np.ones((201, 1))
    sg = make_dem_window(0.02 * xx, 5.0, w.x0_m, w.y0_m, layer=DemLayer.TOTERR)   # σ crece hacia +x
    hor = compute_horizon(w, obs, hp)
    m0 = compute_metrics(run_timeline(sky, hor, VP, TP), sky, hor, VP)
    res = run_uncertainty(w, sg, obs, hor, sky, VP, TP, hp, UncertaintyParams(k_sigma=2.0, use_coverage_bound=False,
                                                                              use_discretization=False), m0)
    hp_ = compute_horizon(w, obs, hp, sg, +1, 2.0)
    mp = compute_metrics(run_timeline(sky, hp_, VP, TP), sky, hp_, VP)
    got = next(s for s in res.scenarios if s.name == "sigma_plus").metrics
    assert got.solar_fraction == pytest.approx(mp.solar_fraction) and got.max_darkness_s == pytest.approx(mp.max_darkness_s)
    assert [s.name for s in res.scenarios] == ["sigma_plus", "sigma_minus"]


def test_discretization_scenario_decimates_azimuth_grid(make_dem_window, sky):
    obs, hp = _obs(), HorizonParams(r_max_m=3000.0)
    w, sg = _dem(make_dem_window, obs, wall_m=0.0)
    z = np.zeros((201, 201))
    z[:, 150:] = 20.0 * np.sin(np.arange(51))[None, :]**2   # relieve para que H no sea constante
    w = make_dem_window(z, 5.0, w.x0_m, w.y0_m)
    hor = compute_horizon(w, obs, hp)
    m0 = compute_metrics(run_timeline(sky, hor, VP, TP), sky, hor, VP)
    res = run_uncertainty(w, None, obs, hor, sky, VP, TP, hp, UncertaintyParams(use_coverage_bound=False), m0)
    assert [s.name for s in res.scenarios] == ["az_step_0.5"]   # sin σ: no hay escenarios σ


def test_smooth_sphere_only_height_scenarios():
    et0 = spice_engine.utc_to_et("2027-02-06T00:00:00")   # el Sol se pone: la altura del mástil mueve la puesta
    sky = spice_engine.sky_series(spice_engine.et_grid(et0, et0 + 12 * 86400.0, 600.0), LAT, LON, 2.0)
    obs, hp = _obs(HorizonMode.SMOOTH_SPHERE), HorizonParams()
    hor = smooth_sphere_result(obs, hp)
    m0 = compute_metrics(run_timeline(sky, hor, VP, TP), sky, hor, VP)
    none = run_uncertainty(None, None, obs, hor, sky, VP, TP, hp, UncertaintyParams(), m0)
    assert none.scenarios == () and all(r.lo == r.nominal == r.hi for r in none.ranges.values())
    res = run_uncertainty(None, None, obs, hor, sky, VP, TP, hp, UncertaintyParams(observer_height_delta_m=2.0), m0)
    assert [s.name for s in res.scenarios] == ["height_plus", "height_minus"]
    r = res.ranges["effective_illumination"]
    assert r.lo <= r.nominal <= r.hi and r.hi > r.lo   # más alto ⇒ horizonte más bajo ⇒ más disco visible
