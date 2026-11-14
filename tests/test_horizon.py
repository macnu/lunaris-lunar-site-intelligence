"""terrain.horizon: casos H1–H7 de matematica.md §2.3, plano vs curvo, nodata, cobertura, caché y Site04 real."""
import math
import time

import numpy as np
import pytest

from lsi.contracts import DemLayer, HorizonMode, HorizonParams, MOON_RADIUS_M as R, NodataAtObserverError, ObserverPoint
from lsi.terrain.horizon import (
    compute_horizon, horizon_at, limited_fraction, smooth_sphere_horizon_deg, smooth_sphere_result,
    unknown_relevant_mask,
)


def obs(x=0.0, y=0.0, lon=0.0, h=2.0, mode=HorizonMode.DEM):
    return ObserverPoint(lat_deg=-89.0, lon_deg_e=lon, x_m=x, y_m=y, height_m=h, mode=mode)


def params(**kw):
    kw.setdefault("observer_height_m", 2.0)
    kw.setdefault("r_max_m", 6000.0)
    return HorizonParams(**kw)


def north_strip(make_dem_window, z, y_max, nx=5):
    """Franja estrecha hacia +y (az 0 con lon 0). Centros de píxel en múltiplos de 5 m, x ∈ [-10, 10]."""
    rows = int(y_max / 5) + 21
    return make_dem_window(z, pixel_size_m=5.0, x0_m=-10.0, y0_m=y_max + 100.0, shape=(rows, nx))


def crest(y_crest, height):
    return lambda x, y: np.where(y >= y_crest, height, 0.0)


def exact_el_deg(s, z, z0):
    psi = s / R
    return math.degrees(math.atan2((R + z) * math.cos(psi) - (R + z0), (R + z) * math.sin(psi)))


# ------------------------------------------------------------------ esfera lisa (H1–H4)
@pytest.mark.parametrize("h,exp", [(1, -0.061473), (2, -0.086937), (5, -0.137459), (100, -0.614720), (1000, -1.943496)])
def test_smooth_sphere_H1_H4(h, exp):
    assert smooth_sphere_horizon_deg(h) == pytest.approx(exp, abs=1e-6)
    assert smooth_sphere_horizon_deg(h) == pytest.approx(-math.degrees(math.sqrt(2 * h / R)), rel=2e-3)


def test_smooth_sphere_result_shape_and_flags():
    r = smooth_sphere_result(obs(mode=HorizonMode.SMOOTH_SPHERE), params())
    assert r.az_deg.shape == (1440,) and r.az_deg[0] == 0 and r.az_deg[-1] == pytest.approx(359.75)
    assert np.allclose(r.h_lb_deg, -0.086937, atol=1e-6) and not r.limited.any() and np.isinf(r.r_cov_m).all()
    assert r.mode == HorizonMode.SMOOTH_SPHERE and r.h_sphere_deg == pytest.approx(-0.086937, abs=1e-6)
    assert limited_fraction(r, 2.0, 0.27) == 0.0


def test_dem_flat_plane_reproduces_smooth_sphere_H2(make_dem_window):
    """DEM z=0 con h=2 m: el máximo de el(s) es el horizonte de esfera lisa (alcanzado en s*≈2636 m)."""
    w = north_strip(make_dem_window, lambda x, y: 0 * x, 6000)
    r = compute_horizon(w, obs(), params())
    assert r.h_lb_deg[0] == pytest.approx(-0.086937, abs=1e-5)


# ------------------------------------------------------------------ cresta artificial (H5, H6) y plano vs curvo
def test_crest_H5_5km(make_dem_window):
    w = north_strip(make_dem_window, crest(5000, 100.0), 6000)
    r = compute_horizon(w, obs(), params())
    assert r.h_lb_deg[0] == pytest.approx(1.040375, abs=2e-6)
    flat = math.degrees(math.atan2(98.0, 5000.0))
    assert flat == pytest.approx(1.122854, abs=1e-6) and flat - r.h_lb_deg[0] == pytest.approx(0.082478, abs=3e-6)


def test_crest_H6_16km(make_dem_window):
    w = north_strip(make_dem_window, crest(16000, 100.0), 16200)
    r = compute_horizon(w, obs(), params(r_max_m=16200.0))
    assert r.h_lb_deg[0] == pytest.approx(0.087096, abs=2e-6)
    assert math.degrees(math.atan2(98.0, 16000.0)) - r.h_lb_deg[0] == pytest.approx(0.263836, abs=3e-6)


@pytest.mark.parametrize("s_km,exp", [(8, 0.13), (16, 0.26), (30, 0.49)])
def test_flat_minus_curved_magnitude(make_dem_window, s_km, exp):
    s = s_km * 1000.0
    # cresta de 1000 m: a 30 km una de 100 m queda bajo el horizonte curvo (caída 259 m) y no se vería
    w = north_strip(make_dem_window, crest(s, 1000.0), s + 100)
    r = compute_horizon(w, obs(), params(r_max_m=s + 100))
    diff = math.degrees(math.atan2(998.0, s)) - r.h_lb_deg[0]
    assert diff == pytest.approx(math.degrees(s / (2 * R)), abs=0.003)
    assert diff == pytest.approx(exp, abs=0.006)


def test_h7_flat_ground_h0(make_dem_window):
    """z=z0 y h=0: el(s)=−ψ/2; el máximo = primera muestra, H = −5/(2R) rad en TODOS los azimutes."""
    w = make_dem_window(lambda x, y: 0 * x, pixel_size_m=5.0, x0_m=-100.0, y0_m=100.0, shape=(41, 41))
    r = compute_horizon(w, obs(h=0.0), params(observer_height_m=0.0, r_max_m=300.0))
    assert np.allclose(r.h_lb_deg, -math.degrees(5.0 / (2 * R)), rtol=1e-6)
    assert r.limited.all()                               # el DEM de 200 m acaba antes de r_max=300 m
    assert r.r_cov_m[0] == pytest.approx(100.0)          # az 0: último centro válido a 100 m
    assert r.cov_min_m <= 100.0 and r.cov_median_m <= 141.5


# ------------------------------------------------------------------ nodata y cobertura
def test_nodata_is_neither_mountain_nor_clear_sky(make_dem_window):
    """Suelo a −1000 m con un hueco NaN (y∈[1000,1100]): un 0 espurio sería una pared de ~45°."""
    def z(x, y):
        return np.where((y >= 1000) & (y <= 1100), np.nan, -1000.0)
    w = north_strip(make_dem_window, z, 3000)
    r = compute_horizon(w, obs(), params(r_max_m=3000.0, z_up_m=500.0))
    assert r.h_lb_deg[0] < 0.0                           # no hay montaña falsa
    assert r.limited[0] and 990 <= r.r_cov_m[0] <= 1005  # el hueco limita el azimut (r_cov = último válido)
    z0 = -998.0
    assert r.h_ub_deg[0] == pytest.approx(exact_el_deg(r.r_cov_m[0] + 5.0, 500.0, z0), abs=1e-9)   # no cielo despejado falso
    assert r.h_ub_deg[0] > 40.0 and (r.h_ub_deg >= r.h_lb_deg).all()


def test_all_nodata_ray_falls_back_to_sphere_floor_and_limited(make_dem_window):
    w = make_dem_window(lambda x, y: np.where(x > 5, np.nan, 0.0), x0_m=-100.0, y0_m=100.0, shape=(41, 41))
    r = compute_horizon(w, obs(), params(r_max_m=300.0))
    east = int(round((90.0 - 0.0) / 0.25))               # az 90° ⇒ +x
    assert r.limited[east] and np.isfinite(r.h_lb_deg).all()
    assert r.h_lb_deg[east] == pytest.approx(r.h_sphere_deg) and r.r_cov_m[east] == 0.0   # sin muestra válida: suelo analítico


def test_observer_on_nodata_raises(make_dem_window):
    w = make_dem_window(lambda x, y: np.where(np.abs(x) < 20, np.nan, 0.0), x0_m=-100.0, y0_m=100.0, shape=(41, 41))
    with pytest.raises(NodataAtObserverError):
        compute_horizon(w, obs(), params(r_max_m=100.0))


def test_not_limited_when_dem_covers_r_max(make_dem_window):
    w = north_strip(make_dem_window, lambda x, y: 0 * x, 2000)
    r = compute_horizon(w, obs(), params(r_max_m=1500.0))
    assert not r.limited[0] and r.r_cov_m[0] == 1500.0 and r.h_ub_deg[0] == r.h_lb_deg[0]


def test_sigma_scenarios_move_horizon(make_dem_window):
    w = north_strip(make_dem_window, crest(5000, 100.0), 6000)
    sg = north_strip(make_dem_window, lambda x, y: np.where(y >= 5000, 10.0, 0.0), 6000)   # σ solo en la cresta
    p = params()
    nom = compute_horizon(w, obs(), p).h_lb_deg[0]
    up = compute_horizon(w, obs(), p, sigma_window=sg, sigma_sign=+1, k_sigma=2.0).h_lb_deg[0]
    assert up > nom and up == pytest.approx(exact_el_deg(5000.0, 120.0, 2.0), abs=2e-6)


def test_conservative_bias_and_blocks_invariance(make_dem_window):
    w = north_strip(make_dem_window, crest(5000, 100.0), 6000)
    a = compute_horizon(w, obs(), params(block_azimuths=1000))
    b = compute_horizon(w, obs(), params(block_azimuths=7, conservative_bias_deg=0.05))
    np.testing.assert_allclose(b.h_lb_deg, a.h_lb_deg + 0.05, atol=1e-12)
    np.testing.assert_array_equal(b.r_cov_m, a.r_cov_m)


# ------------------------------------------------------------------ interpolación y máscaras
def test_horizon_at_circular_and_masks():
    r = smooth_sphere_result(obs(mode=HorizonMode.SMOOTH_SPHERE), params())
    r.h_lb_deg = np.zeros(1440)
    r.h_lb_deg[0], r.h_lb_deg[-1] = 10.0, 0.0
    assert horizon_at(r, np.array([359.875]))[0] == pytest.approx(5.0)
    assert horizon_at(r, np.array([-0.125, 360.125]))[0] == pytest.approx(5.0)
    assert horizon_at(r, np.array([100.0]))[0] == 0.0
    with pytest.raises(ValueError):
        horizon_at(r, np.array([0.0]), kind="ub") if r.h_ub_deg is None else (_ for _ in ()).throw(ValueError)
    r.limited = np.zeros(1440, bool)
    r.limited[400] = True                                # az 100°
    az, el, rad = np.array([100.0, 100.0, 200.0]), np.array([0.5, -5.0, 0.5]), np.array([0.27] * 3)
    assert unknown_relevant_mask(r, az, el, rad).tolist() == [True, False, False]
    assert limited_fraction(r, 1.0, 0.27) == pytest.approx(1 / 1440)


# ------------------------------------------------------------------ caché
def test_cache_roundtrip(make_dem_window, tmp_path):
    w = north_strip(make_dem_window, crest(5000, 100.0), 6000)
    p = params()
    assert compute_horizon(w, obs(), p, cache_dir=tmp_path).cache_key          # sin sha ⇒ no se cachea
    assert not list(tmp_path.rglob("*.npz"))
    import dataclasses
    from lsi.contracts import DemMetadata
    w.meta = dataclasses.replace(DemMetadata(key="T", layer=DemLayer.SURF, width_px=5, height_px=1, pixel_size_m=5.0,
                                             bounds_xy_m=(0, 0, 1, 1), transform=(5, 0, 0, 0, -5, 0), crs_wkt="",
                                             nodata=None, dtype="float32", sha256="abc", size_bytes=1))
    a = compute_horizon(w, obs(), p, cache_dir=tmp_path)
    assert len(list(tmp_path.rglob("*.npz"))) == 1
    b = compute_horizon(w, obs(), p, cache_dir=tmp_path)
    for f in ("az_deg", "h_lb_deg", "r_cov_m", "limited", "h_ub_deg"):
        np.testing.assert_array_equal(getattr(a, f), getattr(b, f))
    assert a.cache_key == b.cache_key and b.dem_sha256 == "abc"
    c = compute_horizon(w, obs(), params(conservative_bias_deg=0.05), cache_dir=tmp_path)
    assert c.cache_key != a.cache_key and len(list(tmp_path.rglob("*.npz"))) == 2


# ------------------------------------------------------------------ DEM real Site04
@pytest.fixture(scope="module")
def site04(raw_dir):
    from lsi.data.loader import discover_dems, read_window
    refs = discover_dems(raw_dir)
    if "Site04" not in refs:
        pytest.skip("falta el GeoTIFF Site04 (python scripts/fetch_data.py)")
    return read_window(refs["Site04"], DemLayer.SURF)


@pytest.mark.needs_dem
def test_site04_real(site04, simulation_cfg, capsys):
    from lsi.astronomy.coordinates import stereo_forward
    from lsi.data.catalog import horizon_params
    p = horizon_params(simulation_cfg)
    w = site04
    d = simulation_cfg["dem_default_observers"]["Site04"]
    x, y = (float(v) for v in stereo_forward(d["lat_deg"], d["lon_deg_e"]))
    o = ObserverPoint(lat_deg=d["lat_deg"], lon_deg_e=d["lon_deg_e"], x_m=x, y_m=y, height_m=p.observer_height_m,
                      mode=HorizonMode.DEM)
    t0 = time.perf_counter()
    r = compute_horizon(w, o, p)
    dt = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\n[T08] horizonte Site04 centro, az {p.az_step_deg}°, r {p.radial_step_m} m, r_max {p.r_max_m:.0f} m: {dt:.2f} s")
    assert r.az_deg.shape == r.h_lb_deg.shape == r.r_cov_m.shape == r.limited.shape == (1440,)
    assert np.isfinite(r.h_lb_deg).all() and r.h_lb_deg.min() > -60.0 and r.h_lb_deg.max() < 60.0
    assert r.h_lb_deg.max() > 10.0                       # la pared del cráter (~33° según terreno-geologia.md)
    assert r.limited.all() and r.cov_min_m > 3000.0 and (r.h_ub_deg >= r.h_lb_deg).all()
    assert dt < 2.0
    # determinismo
    np.testing.assert_array_equal(compute_horizon(w, o, p).h_lb_deg, r.h_lb_deg)


@pytest.mark.needs_dem
def test_site04_east_edge_limited(site04, simulation_cfg):
    from lsi.astronomy.coordinates import stereo_inverse
    from lsi.data.catalog import horizon_params
    w = site04
    h, wd = w.data.shape
    x_east = w.x0_m + 5.0 * (wd - 1)
    x, y = x_east - 1500.0, w.y0_m - 5.0 * (h // 2)
    lat, lon = (float(v) for v in stereo_inverse(x, y))
    p = horizon_params(simulation_cfg)
    o = ObserverPoint(lat_deg=lat, lon_deg_e=lon, x_m=x, y_m=y, height_m=2.0, mode=HorizonMode.DEM)
    r = compute_horizon(w, o, p)
    az_east = (math.degrees(math.pi / 2) - lon) % 360.0   # γ = λ + A = 90°  ⇒  rayo hacia +x
    i = int(round(az_east / 0.25)) % 1440
    assert r.limited[i] and r.r_cov_m[i] == pytest.approx(1500.0, abs=10.0)
    assert r.r_cov_m[i] < 0.5 * r.cov_median_m + 1500.0 and r.cov_min_m <= r.r_cov_m[i] + 10.0
    ra = compute_horizon(w, o, horizon_params(simulation_cfg), cache_dir=None)
    assert 0.0 < limited_fraction(ra, 1.6, 0.27) <= 1.0


# ------------------------------------------------------------------ campo lejano (multirresolución)
def _far_strip(make_dem_window, z, y_max=31000.0):
    rows = int(y_max / 80) + 3
    return make_dem_window(z, pixel_size_m=80.0, x0_m=-400.0, y0_m=y_max, shape=(rows, 11))


def test_far_field_detects_crest_at_20km_only(make_dem_window):
    near = north_strip(make_dem_window, lambda x, y: 0 * x, 6000)
    far = _far_strip(make_dem_window, crest(20000.0, 1000.0))          # nodo de la rejilla de 80 m
    p = params(r_max_m=30000.0)
    a = compute_horizon(near, obs(), p)
    b = compute_horizon(near, obs(), p, far=far)
    assert a.limited[0] and a.h_lb_deg[0] < 0                          # sin far: no ve la cresta
    assert not b.limited[0] and b.r_cov_m[0] == 30000.0                # con far: cubre r_max
    assert b.h_lb_deg[0] == pytest.approx(exact_el_deg(20000.0, 1000.0, 2.0), abs=0.02)   # ≈ 2.53°
    assert b.h_lb_deg[0] > 2.4 and b.h_ub_deg[0] == pytest.approx(b.h_lb_deg[0])
    assert b.far_sha256 is None and a.far_sha256 is None               # ventanas sintéticas sin meta


def test_far_field_fallback_only_when_both_invalid(make_dem_window):
    near = north_strip(make_dem_window, lambda x, y: 0 * x, 6000)
    far = _far_strip(make_dem_window, lambda x, y: np.where(y > 25000.0, np.nan, 0.0 * x))
    r = compute_horizon(near, obs(), params(r_max_m=30000.0), far=far)
    assert r.limited[0] and 24800.0 <= r.r_cov_m[0] <= 25000.0         # alcance combinado, no el del 5 m (6 km)
    assert r.h_ub_deg[0] >= r.h_lb_deg[0]
    # observador fuera de la ventana de 5 m: z0 sale del campo lejano
    r2 = compute_horizon(near, obs(x=300.0), params(r_max_m=3000.0), far=far)
    assert np.isfinite(r2.h_lb_deg).all()


def test_far_none_is_backward_compatible(make_dem_window):
    near = north_strip(make_dem_window, crest(5000, 100.0), 6000)
    a = compute_horizon(near, obs(), params())
    b = compute_horizon(near, obs(), params(), far=None)
    np.testing.assert_array_equal(a.h_lb_deg, b.h_lb_deg)
    assert a.cache_key == b.cache_key


def test_far_sha_in_cache_key(make_dem_window, tmp_path):
    import dataclasses
    from lsi.contracts import DemMetadata
    mk = lambda sha: DemMetadata(key="T", layer=DemLayer.SURF, width_px=5, height_px=1, pixel_size_m=5.0, bounds_xy_m=(0, 0, 1, 1),
                                 transform=(5, 0, 0, 0, -5, 0), crs_wkt="", nodata=None, dtype="float32", sha256=sha, size_bytes=1)
    near = north_strip(make_dem_window, lambda x, y: 0 * x, 6000)
    near.meta = mk("near")
    far = _far_strip(make_dem_window, crest(20000.0, 1000.0))
    p = params(r_max_m=30000.0)
    far.meta = mk("farA")
    a = compute_horizon(near, obs(), p, cache_dir=tmp_path, far=far)
    far.meta = dataclasses.replace(mk("farB"))
    b = compute_horizon(near, obs(), p, cache_dir=tmp_path, far=far)
    assert a.cache_key != b.cache_key and (a.far_sha256, b.far_sha256) == ("farA", "farB")
    assert len(list(tmp_path.rglob("*.npz"))) == 2
    c = compute_horizon(near, obs(), p, cache_dir=tmp_path, far=far)       # acierto de caché
    np.testing.assert_array_equal(b.h_lb_deg, c.h_lb_deg)
    assert c.far_sha256 == "farB"
    far.meta = None                                                        # sin sha del far ⇒ no se cachea
    compute_horizon(near, obs(), p, cache_dir=tmp_path, far=far)
    assert len(list(tmp_path.rglob("*.npz"))) == 2


@pytest.mark.needs_dem
def test_site04_far_field_real(site04, simulation_cfg, raw_dir, capsys):
    from lsi.astronomy.coordinates import stereo_forward
    from lsi.data.catalog import horizon_params
    from lsi.data.loader import discover_far_field, load_far_field
    from lsi.terrain.sampling import sample_bilinear
    if discover_far_field(raw_dir) is None:
        pytest.skip("falta LDEM_80S_80MPP_ADJ.TIF")
    p = horizon_params(simulation_cfg)
    d = simulation_cfg["dem_default_observers"]["Site04"]
    x, y = (float(v) for v in stereo_forward(d["lat_deg"], d["lon_deg_e"]))
    o = ObserverPoint(lat_deg=d["lat_deg"], lon_deg_e=d["lon_deg_e"], x_m=x, y_m=y, height_m=p.observer_height_m, mode=HorizonMode.DEM)
    far = load_far_field(raw_dir, x, y, p.r_max_m)
    # coherencia vertical 5 m − 80 m en el solape (rejilla cada 35 m)
    h, wd = site04.data.shape
    X, Y = np.meshgrid(site04.x0_m + 5.0 * np.arange(0, wd, 7), site04.y0_m - 5.0 * np.arange(0, h, 7))
    a, oka = sample_bilinear(site04, X.ravel(), Y.ravel())
    b, okb = sample_bilinear(far, X.ravel(), Y.ravel())
    dz = (a - b)[oka & okb]
    assert dz.size > 1e5
    with capsys.disabled():
        print(f"\n[far] dz(5m-80m) n={dz.size} media={dz.mean():.2f} RMS={np.sqrt((dz**2).mean()):.2f} p95|dz|={np.percentile(np.abs(dz), 95):.2f} m")
    assert abs(dz.mean()) < 3.0 and np.sqrt((dz**2).mean()) < 6.0         # mismo marco vertical (el polo difiere ~7 m, localmente)
    base = compute_horizon(site04, o, p)
    t0 = time.perf_counter()
    r = compute_horizon(site04, o, p, far=far)
    dt = time.perf_counter() - t0
    fine = compute_horizon(site04, o, p, far=far, far_step_m=20.0)         # el paso grueso no se salta crestas
    # solo terreno lejano (s ≥ 10 km): dónde está la cresta lejana más alta
    rf = compute_horizon(site04, o, HorizonParams(**{**p.__dict__, "r_min_m": 10000.0}), far=far)
    i = int(np.argmax(rf.h_lb_deg))
    with capsys.disabled():
        print(f"[far] limited sin far={int(base.limited.sum())}/1440, con far={int(r.limited.sum())}/1440, "
              f"r_cov min={r.cov_min_m:.0f} m, {dt:.2f} s; h_max={r.h_lb_deg.max():.2f}° az {r.az_deg[int(np.argmax(r.h_lb_deg))]:.2f}°; "
              f"h_max lejano(>=10 km)={rf.h_lb_deg[i]:.2f}° az {rf.az_deg[i]:.2f}°; dif paso 40 vs 20 m max={np.abs(r.h_lb_deg - fine.h_lb_deg).max():.4f}°")
    assert base.limited.all() and r.limited.sum() <= 14                    # < 1 % (queda solo lo fuera de ±304 km / NaN)
    assert r.cov_min_m > 29000.0
    assert np.abs(r.h_lb_deg - fine.h_lb_deg).max() < 0.02
    assert (r.h_lb_deg >= base.h_lb_deg - 0.2).all()                        # el 80 m no baja el horizonte salvo el sesgo vertical local
    assert dt < 2.0
