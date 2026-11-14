"""T13: fracción de disco, clasificación y unknown_relevant (matematica.md §4.2-§4.5, casos §4.3)."""
import numpy as np
import pytest

from lsi.contracts import (
    HorizonMode, HorizonParams, HorizonResult, ObserverPoint, VisibilityParams, VisibilityState,
)
from lsi.simulation.visibility import (
    _slice_fraction, classify, disc_fraction, disc_fraction_flat, visibility_series,
)

RHO = 0.26649


def make_horizon(h_fn, limited=None, ub=None):
    az = np.arange(1440) * 0.25
    h = np.asarray(h_fn(az), dtype=float)
    lim = np.zeros(az.shape, bool) if limited is None else limited(az)
    obs = ObserverPoint(-89.7, 10.0, 0.0, 0.0, 2.0, HorizonMode.DEM)
    return HorizonResult(az_deg=az, h_lb_deg=h, r_cov_m=np.full(az.shape, 1e4), limited=lim, mode=HorizonMode.DEM,
                         observer=obs, params=HorizonParams(), h_sphere_deg=-0.04, cache_key="k",
                         h_ub_deg=None if ub is None else np.asarray(ub(az), dtype=float))


@pytest.mark.parametrize("t,exp", [(-1, 0.0), (-0.5, 0.195501), (0, 0.5), (0.5, 0.804499), (1, 1.0), (-3, 0.0), (3, 1.0)])
def test_flat_table_4_2(t, exp):
    assert disc_fraction_flat(t) == pytest.approx(exp, abs=1e-6)


def test_flat_near_limb_exponent():
    t = -1 + 1e-4  # f ≈ (4√2/(3π))(1+t)^{3/2}
    assert disc_fraction_flat(t) == pytest.approx(4 * np.sqrt(2) / (3 * np.pi) * 1e-4 ** 1.5, rel=1e-3)


def test_constant_horizon_uses_analytic_and_nonzero_h():
    hz = make_horizon(lambda a: np.full_like(a, 0.3))
    e = np.array([0.3 - RHO, 0.3, 0.3 + 0.5 * RHO])
    np.testing.assert_allclose(disc_fraction(e, 10.0, RHO, hz), disc_fraction_flat((e - 0.3) / RHO), atol=1e-12)


@pytest.mark.parametrize("t,exp", [(-0.5, 0.195493), (0.5, 0.804507), (0.0, 0.5)])
def test_slices_reproduce_flat_n64(t, exp):
    f = _slice_fraction(np.array([t * RHO]), 50.0, RHO, lambda a: np.zeros_like(a), 64)
    assert f[0] == pytest.approx(exp, abs=2e-5)


def test_vertical_wall_half_disc_4_3():
    ac = 120.0
    f = _slice_fraction(np.array([10.0]), ac, RHO, lambda a: np.where(a < ac, 89.0, 0.0), 64)
    assert f[0] == pytest.approx(0.5, abs=1e-9)


def test_inclined_horizon_through_centre_4_3():
    e, ac = 3.0, 180.0
    hz = make_horizon(lambda a: e + 0.3 * (a - ac))
    f = disc_fraction(np.array([e]), np.array([ac]), np.array([RHO]), hz)
    assert f[0] == pytest.approx(0.5, abs=1e-6)


@pytest.mark.parametrize("t,exp,tol", [(-0.5, 0.17588, 1e-4), (0.0, 0.5, 1e-5), (0.5, 0.82412, 1e-4), (-0.9, 0.01299, 3e-4)])
def test_limb_darkening_4_5(t, exp, tol):
    hz = make_horizon(lambda a: np.zeros_like(a))
    f = disc_fraction(np.array([t * RHO]), np.array([40.0]), np.array([RHO]), hz, limb_darkening_u=0.6)
    assert f[0] == pytest.approx(exp, abs=tol)


def test_limb_darkening_full_disc_is_one_and_u0_matches():
    hz = make_horizon(lambda a: np.full_like(a, -5.0))
    assert disc_fraction(np.array([1.0]), np.array([0.0]), np.array([RHO]), hz, limb_darkening_u=0.6)[0] == pytest.approx(1.0, abs=1e-6)
    assert _slice_fraction(np.array([0.1]), 0.0, RHO, lambda a: np.zeros_like(a), 64, 0.0)[0] == pytest.approx(
        disc_fraction_flat(0.1 / RHO), abs=2e-5)


def test_fraction_bounds_and_monotonic_in_elevation():
    rng = np.random.default_rng(1)
    hz = make_horizon(lambda a: 2.0 + 1.5 * np.sin(np.radians(a * 7)))
    e = np.linspace(-1, 6, 400)
    f = disc_fraction(e, np.full_like(e, 77.0), np.full_like(e, RHO), hz)
    assert (f >= 0).all() and (f <= 1).all() and (np.diff(f) >= -1e-12).all() and f[0] == 0 and f[-1] == 1


def test_classify():
    s = classify(np.array([0, 1e-3, 2e-3, 0.5, 1 - 2e-3, 1 - 1e-3, 1.0, np.nan]))
    H, P, V = VisibilityState.HIDDEN, VisibilityState.PARTIAL, VisibilityState.VISIBLE
    assert list(s) == [H, H, P, P, P, V, V, H] and s.dtype == np.int8


def test_unknown_relevant_and_f_pess(monkeypatch):
    """Sector limitado 90-180°: ub sube; unknown solo si el disco toca la banda [H_lb, H_ub] y el az es limitado."""
    from lsi.contracts import Body, BodyTrack, SkySeries
    from lsi.simulation.visibility import body_visibility
    hz = make_horizon(lambda a: np.zeros_like(a), limited=lambda a: (a >= 90) & (a < 180),
                      ub=lambda a: np.where((a >= 90) & (a < 180), 5.0, 0.0))
    az = np.array([45.0, 135.0, 135.0, 135.0, 135.0])
    el = np.array([1.0, 1.0, 5.0, 7.0, -3.0])
    tr = BodyTrack(Body.SUN, az, el, np.full(5, 1.5e8), np.full(5, RHO))
    bv = body_visibility(tr, hz, VisibilityParams())
    assert list(bv.unknown_relevant) == [False, True, True, False, False]   # 7° > H_ub+ρ ; −3° < H_lb−ρ
    assert bv.f[:4].tolist() == [1.0, 1.0, 1.0, 1.0] and bv.f_pess[1] == 0.0 and bv.f_pess[2] == pytest.approx(0.5, abs=1e-4)
    assert bv.f_pess[3] == 1.0 and (bv.f_pess <= bv.f + 1e-12).all()


@pytest.mark.needs_spice
def test_visibility_series_smooth_sphere(kernels_dir):
    from lsi.astronomy import spice_engine as se
    from lsi.terrain.horizon import smooth_sphere_result
    se.load_kernels(kernels_dir)
    et = se.et_grid(se.utc_to_et("2026-12-01T00:00:00"), se.utc_to_et("2026-12-11T00:00:00"), 600.0)
    sky = se.sky_series(et, -85.0, 20.0, 2.0)
    hz = smooth_sphere_result(ObserverPoint(-85.0, 20.0, 0.0, 0.0, 2.0, HorizonMode.SMOOTH_SPHERE), HorizonParams())
    vs = visibility_series(sky, hz, VisibilityParams())
    for bv in (vs.sun, vs.earth):
        assert bv.f.shape == et.shape and 0 <= bv.f.min() and bv.f.max() <= 1 and not bv.unknown_relevant.any()
        np.testing.assert_array_equal(bv.f, bv.f_pess)   # esfera lisa: H_ub = H_lb
    h0 = hz.h_lb_deg[0]
    exp = disc_fraction_flat((sky.sun.el_deg - h0) / sky.sun.radius_deg)
    np.testing.assert_allclose(vs.sun.f, exp, atol=1e-12)
    assert 0 < vs.sun.f.mean() < 1
