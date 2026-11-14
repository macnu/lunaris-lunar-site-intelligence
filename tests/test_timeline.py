"""T14: ventanas, refinamiento, eventos y cuenta atrás (matematica.md §5, casos §5.4) + hito H1 real (Site04)."""
import time

import numpy as np
import pytest

from lsi.contracts import (
    Body, EventKind, HorizonMode, HorizonParams, HorizonResult, ObserverPoint, TimelineParams, VisibilityParams, Window,
    WindowSet,
)
from lsi.simulation.timeline import (
    complement_windows, countdown, find_windows, intersect_windows, refine_crossings, run_timeline, union_windows,
)
from lsi.simulation.visibility import disc_fraction_flat

RHO = 0.26649
H = 3600.0


def f_synth(et):
    """§5.4: horizonte plano H=0, e(t)=1.5°·sin(2πt/24h)."""
    return disc_fraction_flat(1.5 * np.sin(2 * np.pi * np.asarray(et) / (24 * H)) / RHO)


def synth_windows(t0_h, t1_h, step_s=600.0, **kw):
    et = np.arange(t0_h * H, t1_h * H + 1e-6, step_s)
    return find_windows(et, f_synth(et), 1e-3, "sun", "f>eps", f_fn=f_synth, **kw)


def test_refine_crossings_exact_root_and_tolerance():
    root = np.array([123.4, 2000.7, 5999.1])
    # un cruce por intervalo: f(t) = (t - r)/1000 con r distinto por evento (se evalúa elemento a elemento)
    lo, hi = np.array([0.0, 1800.0, 5400.0]), np.array([600.0, 2400.0, 6000.0])
    got = refine_crossings(lambda t: (np.asarray(t) - root) / 1000.0, lo, hi, 0.0, 1.0)
    assert np.abs(got - root).max() <= 0.5 + 1e-9


def test_case_5_4_rise_set_and_duration():
    ws = synth_windows(-2, 14)
    assert len(ws.windows) == 1
    w = ws.windows[0]
    assert w.start_et / H == pytest.approx(-0.672530, abs=1.0 / H)
    assert w.end_et / H == pytest.approx(12.672530, abs=1.0 / H)
    assert w.duration_s / H == pytest.approx(13.345060, abs=1.5 / H)
    assert not w.left_truncated and not w.right_truncated


def test_case_5_4_upper_limb_criterion_differs_35s():
    et = np.arange(-2 * H, 14 * H, 600.0)
    ws = find_windows(et, 1.5 * np.sin(2 * np.pi * et / (24 * H)) + RHO, 0.0, "x", "e+rho>0",
                      f_fn=lambda t: 1.5 * np.sin(2 * np.pi * np.asarray(t) / (24 * H)) + RHO)
    assert ws.windows[0].start_et / H == pytest.approx(-0.682233, abs=1.0 / H)


def test_case_5_4_truncated_borders():
    ws = synth_windows(0, 6)
    assert len(ws.windows) == 1
    w = ws.windows[0]
    assert (w.start_et, w.end_et) == (0.0, 6 * H) and w.left_truncated and w.right_truncated
    assert w.duration_s >= 6 * H


def test_step_5_vs_10_min_same_events():
    a, b = synth_windows(-2, 14, 300.0).windows[0], synth_windows(-2, 14, 600.0).windows[0]
    assert abs(a.start_et - b.start_et) <= 1.0 and abs(a.end_et - b.end_et) <= 1.0


def test_without_f_fn_linear_interpolation_is_coarser_but_close():
    et = np.arange(-2 * H, 14 * H + 1, 600.0)
    w = find_windows(et, f_synth(et), 1e-3, "sun", "x").windows[0]
    assert abs(w.start_et / H + 0.672530) < 600 / H


def mk(label, ivs, t0=0.0, t1=30.0):
    return WindowSet(label, tuple(Window(a, b, a <= t0, b >= t1) for a, b in ivs), t0, t1, "")


def test_case_5_4_overlap_and_union():
    A, B = mk("sun", [(0, 10), (20, 30)]), mk("earth", [(5, 25)])
    ov = intersect_windows(A, B)
    assert [(w.start_et, w.end_et) for w in ov.windows] == [(5, 10), (20, 25)]
    assert not any(w.left_truncated or w.right_truncated for w in ov.windows)
    un = union_windows(A, B)
    assert [(w.start_et, w.end_et) for w in un.windows] == [(0, 30)]
    assert un.windows[0].left_truncated and un.windows[0].right_truncated


def test_union_merges_gap_within_tol_only():
    A = mk("a", [(0, 10), (10.5, 20)])
    assert len(union_windows(A, mk("b", []), tol_s=1.0).windows) == 1
    assert len(union_windows(A, mk("b", []), tol_s=0.1).windows) == 2


def test_complement_truncation_flags():
    d = complement_windows(mk("sun", [(5, 10), (20, 25)]))
    assert [(w.start_et, w.end_et, w.left_truncated, w.right_truncated) for w in d.windows] == [
        (0, 5, True, False), (10, 20, False, False), (25, 30, False, True)]


# ---------------------------------------------------------------- SPICE: cuenta atrás y H1 real
def _kernels(kernels_dir):
    from lsi.astronomy import spice_engine as se
    se.load_kernels(kernels_dir)
    return se


@pytest.mark.needs_spice
def test_countdown_matches_timeline_events_smooth_sphere(kernels_dir):
    from lsi.terrain.horizon import smooth_sphere_result
    se = _kernels(kernels_dir)
    lat, lon, h = -85.0, 20.0, 2.0
    hz = smooth_sphere_result(ObserverPoint(lat, lon, 0.0, 0.0, h, HorizonMode.SMOOTH_SPHERE), HorizonParams())
    vp, tp = VisibilityParams(), TimelineParams()
    et0 = se.utc_to_et("2026-12-01T00:00:00")
    sky = se.sky_series(se.et_grid(et0, et0 + 70 * 86400.0, tp.step_s), lat, lon, h)
    tl = run_timeline(sky, hz, vp, tp)
    for body in (Body.SUN, Body.EARTH):
        evs = [e for e in tl.events if e.body == body]
        assert len(evs) >= 2 and all(a.kind != b.kind for a, b in zip(evs, evs[1:]))   # alternan salida/puesta
        for now in (et0 + 3 * 86400.0, et0 + 11.3 * 86400.0):
            c = countdown(now, body, lat, lon, h, hz, vp, tp)
            nxt = next(e for e in evs if e.et > now)
            assert c.next_event is not None and abs(c.next_event.et - nxt.et) <= 1.0
            assert c.seconds_until == pytest.approx(c.next_event.et - now) and c.seconds_until > 0
            assert c.next_event.kind == (EventKind.SET if c.currently_up else EventKind.RISE)
            assert not c.approximate_due_to_coverage and 0 <= c.next_event.az_deg < 360
    # sin eventos en la ventana de búsqueda
    c = countdown(et0, Body.SUN, lat, lon, h, hz, vp, TimelineParams(countdown_search_days=0.5))
    assert c.next_event is None and c.seconds_until is None


@pytest.fixture(scope="module")
def site04_horizon(raw_dir, simulation_cfg):
    from lsi.astronomy.coordinates import stereo_forward
    from lsi.data.catalog import horizon_params
    from lsi.data.loader import discover_dems, read_window
    from lsi.terrain.horizon import compute_horizon
    refs = discover_dems(raw_dir)
    if "Site04" not in refs:
        pytest.skip("falta el GeoTIFF Site04 (python scripts/fetch_data.py)")
    d = simulation_cfg["dem_default_observers"]["Site04"]
    p = horizon_params(simulation_cfg)
    x, y = (float(v) for v in stereo_forward(d["lat_deg"], d["lon_deg_e"]))
    o = ObserverPoint(d["lat_deg"], d["lon_deg_e"], x, y, p.observer_height_m, HorizonMode.DEM)
    return o, compute_horizon(read_window(refs["Site04"]), o, p)


@pytest.mark.needs_dem
@pytest.mark.needs_spice
def test_H1_site04_30_days(site04_horizon, simulation_cfg, kernels_dir, capsys):
    from lsi.analysis import metrics as mt
    from lsi.data.catalog import timeline_params, visibility_params
    se = _kernels(kernels_dir)
    o, hz = site04_horizon
    vp, tp = visibility_params(simulation_cfg), timeline_params(simulation_cfg)
    et0 = se.utc_to_et("2026-12-01T00:00:00")
    et1 = se.utc_to_et("2026-12-31T00:00:00")
    t = time.perf_counter()
    sky = se.sky_series(se.et_grid(et0, et1, tp.step_s), o.lat_deg, o.lon_deg_e, o.height_m)
    tl = run_timeline(sky, hz, vp, tp)
    dt = time.perf_counter() - t
    vis, T = tl.series, tl.et1 - tl.et0
    for bv in (vis.sun, vis.earth):
        assert np.isfinite(bv.f).all() and bv.f.min() >= 0.0 and bv.f.max() <= 1.0
        assert (bv.f_pess <= bv.f + 1e-9).all()
        assert np.bincount(bv.state, minlength=3).sum() == len(vis.et)
    # Sol visible + oculto = 1 (ventanas solares + complemento = periodo)
    sun_t = mt.total_duration(mt.intervals(tl.sun), tl.et0, tl.et1)
    dark_t = mt.total_duration(mt.intervals(tl.dark), tl.et0, tl.et1)
    assert sun_t + dark_t == pytest.approx(T, abs=1e-6)
    # el refinamiento mueve cada transición menos de un paso respecto a la rejilla gruesa
    for ws, bv, thr in ((tl.sun, vis.sun, vp.sun_f_thr), (tl.earth, vis.earth, vp.earth_f_thr)):
        coarse = mt.windows_from_mask(vis.et, bv.f > thr)
        ref = mt.intervals(ws)
        assert len(coarse) == len(ref)
        edge = lambda a: a[(a > tl.et0) & (a < tl.et1)]  # noqa: E731 (los bordes truncados no se refinan)
        d = np.abs(edge(coarse.ravel()) - edge(ref.ravel()))
        assert d.size == 0 or d.max() < tp.step_s
    # sin truncamientos falsos y eventos coherentes con las ventanas
    assert len(tl.events) == sum(len(w.windows) * 2 for w in (tl.sun, tl.earth)) - sum(
        w.left_truncated + w.right_truncated for ws in (tl.sun, tl.earth) for w in ws.windows)
    m = mt.compute_metrics(tl, sky, hz, vp)
    assert 0.0 <= m.solar_fraction <= 1.0 and 0.0 <= m.earth_fraction <= 1.0
    with capsys.disabled():
        print(f"\n[H1] Site04 centro, 30 d@{tp.step_s:.0f}s: tiempo SPICE+visibilidad+timeline = {dt:.2f} s (horizonte aparte)")
        print(f"[H1] fracción solar {m.solar_fraction:.4f} (ilum. efectiva {m.effective_illumination:.4f}); "
              f"Tierra {m.earth_fraction:.4f}; solape {m.overlap_fraction:.4f}")
        print(f"[H1] ventana solar más larga {m.longest_sun_window_s / 3600:.2f} h (trunc={m.longest_sun_window_truncated}); "
              f"Tierra {m.longest_earth_window_s / 3600:.2f} h; oscuridad máx {m.max_darkness_s / 3600:.2f} h; "
              f"n_sol={m.n_sun_windows} n_tierra={m.n_earth_windows}; unknown sol/tierra "
              f"{m.unknown_fraction_sun:.3f}/{m.unknown_fraction_earth:.3f}")
    assert dt < simulation_cfg["performance"]["budget_30d_10min_s"]


# ---------------------------------------------------------------------------------------------- enlace: margen de elevación
def test_link_fraction_margin_equals_raising_the_horizon_by_the_margin():
    """link_fraction(margen m) = fracción con el horizonte H + m: con H constante, la fórmula analítica con (e − H − m)/ρ."""
    from lsi.simulation.visibility import link_fraction
    az = np.arange(1440) * 0.25
    hz = HorizonResult(az_deg=az, h_lb_deg=np.full(az.shape, 0.3), r_cov_m=np.full(az.shape, 1e4), limited=np.zeros(az.shape, bool),
                       mode=HorizonMode.DEM, observer=ObserverPoint(-89.7, 10.0, 0.0, 0.0, 2.0, HorizonMode.DEM),
                       params=HorizonParams(), h_sphere_deg=-0.04, cache_key="k", h_ub_deg=np.full(az.shape, 0.3))
    from lsi.contracts import BodyTrack
    el = np.array([-1.0, 0.5, 3.4, 6.0])
    tr = BodyTrack(Body.EARTH, np.full(4, 10.0), el, np.full(4, 384400.0), np.full(4, RHO))
    for m in (0.0, 3.0, 5.0):
        np.testing.assert_allclose(link_fraction(tr, hz, VisibilityParams(), m), disc_fraction_flat((el - 0.3 - m) / RHO), atol=1e-12)
    np.testing.assert_allclose(link_fraction(tr, hz, VisibilityParams(), 0.0), link_fraction(tr, hz, VisibilityParams()))
