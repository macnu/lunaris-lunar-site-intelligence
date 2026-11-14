"""Ventana de misión: métricas deslizantes frente a una implementación ingenua, score/puertas vectorizados frente a
``site_score`` y mejor fecha de inicio. Sin SPICE ni DEM (series sintéticas)."""
import dataclasses

import numpy as np
import pytest

from lsi.analysis import suitability_map as sm
from lsi.analysis.site_score import compute_score
from lsi.contracts import MissionProfile, ScoreInputs, ScoreParams, ScoreProfile, Threshold

DT = 1800.0


def naive(sun, earth, ref, n, stride):
    """Bucle explícito: para cada inicio, recorre las muestras de la ventana y cuenta rachas a mano."""
    out = {k: [] for k in ("f_sun", "f_earth", "f_overlap", "longest_sun_h", "max_dark_h", "f_ref")}
    for i in range(0, len(sun) - n + 1, stride):
        w_s, w_e, w_r = sun[i:i + n], earth[i:i + n], ref[i:i + n]
        run = {True: 0, False: 0}
        best = {True: 0, False: 0}
        prev = None
        for v in w_s:
            run[v] = run[v] + 1 if prev == v else 1
            run[not v] = 0
            best[v] = max(best[v], run[v])
            prev = v
        out["f_sun"].append(w_s.mean())
        out["f_earth"].append(w_e.mean())
        out["f_overlap"].append((w_s & w_e).mean())
        out["f_ref"].append(w_r.mean())
        out["longest_sun_h"].append(best[True] * DT / 3600)
        out["max_dark_h"].append(best[False] * DT / 3600)
    return {k: np.array(v) for k, v in out.items()}


def series(rng, N, p_stay):
    """Serie booleana con rachas largas (cambia de estado con prob. 1-p_stay en cada muestra)."""
    flips = rng.random(N) > p_stay
    return (np.cumsum(flips) % 2).astype(bool)


@pytest.mark.parametrize("seed,N,p_stay,dur,step", [(0, 2000, 0.98, 3.0, 0.5), (1, 3000, 0.995, 14.0, 1.0),
                                                    (2, 1500, 0.9, 1.0, 0.25), (3, 4000, 0.999, 30.0, 2.0),
                                                    (4, 800, 0.95, 5.0, 1.0)])
def test_window_metrics_equal_naive(seed, N, p_stay, dur, step):
    rng = np.random.default_rng(seed)
    sun, earth, ref = (series(rng, N, p_stay) for _ in range(3))
    t = 1e8 + DT * np.arange(N + 1)       # N intervalos
    m = sm.mission_window_metrics(np.append(sun, False), np.append(earth, False), t, dur, step,
                                  series_ref_earth=np.append(ref, False))
    n, stride = int(round(dur * 86400 / DT)), int(round(step * 86400 / DT))
    ref_m = naive(sun, earth, ref, n, stride)
    assert len(m.start_et) == len(ref_m["f_sun"]) > 1
    np.testing.assert_allclose(m.start_et, t[0] + DT * stride * np.arange(len(m.start_et)))
    for k, v in ref_m.items():
        np.testing.assert_allclose(getattr(m, k), v, atol=1e-12, err_msg=k)


def test_window_metrics_edge_cases():
    N = 600
    t = DT * np.arange(N + 1)
    z, o = np.zeros(N + 1, bool), np.ones(N + 1, bool)
    m = sm.mission_window_metrics(z, o, t, 2.0, 1.0)
    assert (m.f_sun == 0).all() and (m.f_earth == 1).all() and (m.f_overlap == 0).all()
    assert (m.max_dark_h == 48.0).all() and (m.longest_sun_h == 0).all()    # toda la ventana a oscuras: 2 d
    m = sm.mission_window_metrics(o, z, t, 2.0, 1.0)
    assert (m.max_dark_h == 0).all() and (m.longest_sun_h == 48.0).all()
    # una noche de 10 h en mitad de la serie: ventanas que la cortan solo cuentan lo de dentro
    s = np.ones(N + 1, bool)
    s[100:120] = False                                                       # 20 muestras = 10 h
    m = sm.mission_window_metrics(s, z, t, 1.0, 0.25)                        # ventana 48 muestras, paso 12
    i0 = np.arange(len(m.start_et)) * 12
    expect = np.clip(np.minimum(120, i0 + 48) - np.maximum(100, i0), 0, None) * DT / 3600
    np.testing.assert_allclose(m.max_dark_h, expect)
    with pytest.raises(ValueError):
        sm.mission_window_metrics(s, z, t, 400.0, 1.0)                       # más larga que la serie
    with pytest.raises(ValueError):
        sm.mission_window_metrics(s, z, t[:-1], 1.0, 1.0)                    # longitudes distintas


def _profile_mission(dark=12.0, slope=10.0):
    prof = ScoreProfile("t", "t", {"sun": 0.4, "night": 0.25, "earth": 0.15, "terrain": 0.2}, mission_profile_id="t")
    mis = MissionProfile("t", "t", {"max_dark_h_no_nuclear": Threshold(dark, "hard", "x"),
                                    "max_landing_slope_deg": Threshold(slope, "hard", "x")})
    return prof, mis


@pytest.mark.parametrize("solar_gate,lam,floor,pov", [
    (True, 0.0, 0.0, {}), (False, 0.0, 0.0, {}),
    (True, 0.25, 0.25, {}), (False, 0.25, 0.25, {"earth_floor": 0.5}),            # mínimo útil global y por perfil
    (True, 0.5, 0.25, {"g4_limit_h": 50.0, "g4_type": "soft"}),                   # rover: G4 blanda propia
    (True, 0.25, 0.25, {"g4_na": True}),                                          # RHU: sin límite de noche
    (True, 0.25, 0.25, {"g4_limit_h": 8.0, "g4_type": "hard"})])
def test_vectorized_score_and_gates_equal_site_score(solar_gate, lam, floor, pov):
    rng = np.random.default_rng(7)
    sp_ = ScoreParams(resolution_weight=lam, earth_floor=floor)
    prof, mis = _profile_mission()
    prof = dataclasses.replace(prof, uses_solar_gate=solar_gate, **pov)
    n, S = 6, 40
    f_sun, f_earth = rng.random((n, S)), rng.random((n, S))
    f_sun[:, :3] = rng.random((n, 3)) * 0.05                                  # fuerza G1 FAIL
    f_ref = 0.05 + 0.95 * rng.random((n, S))                                  # incluye refs < earth_floor
    d = rng.random((n, S)) * 30
    slope = np.array([2.0, 6.0, 9.9, 12.0, 8.0, 4.0])                         # el 4º rompe G2
    unk = np.array([0, 0, 0, 0, 0.7, 0.1])                                    # el 5º rompe G3
    score, rank = sm.window_scores(f_sun, d, f_earth, f_ref, slope, unk, prof, sp_, mis)
    for p in range(n):
        for i in range(S):
            r = compute_score(ScoreInputs(f_sun[p, i], d[p, i], f_earth[p, i], f_ref[p, i], slope[p], unk[p], True), prof, sp_, mis)
            assert score[p, i] == pytest.approx(r.score, rel=1e-12)
            assert rank[p, i] == {"PASS": 0, "NO_DATA": 1, "FAIL": 2}[r.status.name]
    assert {0, 1, 2} <= set(rank.ravel().tolist()) or not solar_gate


@pytest.mark.parametrize("solar_gate", [True, False])
def test_g0_sun_at_start_in_window_scores_equals_site_score(solar_gate):
    """M2: la puerta G0 (Sol visible al inicio de la ventana) del mapa es la de ``site_score``/pipeline: dura en perfiles
    solares, no aplicable en los demás; sin ``sun_start`` no se evalúa (como antes)."""
    rng = np.random.default_rng(11)
    sp_ = ScoreParams()
    prof, mis = _profile_mission()
    prof = dataclasses.replace(prof, uses_solar_gate=solar_gate)
    n, S = 4, 30
    f_sun, f_earth, f_ref = 0.3 + 0.7 * rng.random((n, S)), rng.random((n, S)), 0.2 + 0.8 * rng.random((n, S))
    d, slope, unk = rng.random((n, S)) * 8, np.array([2.0, 3.0, 4.0, 5.0]), np.zeros(n)
    sun0 = rng.random((n, S)) > 0.4
    score, rank = sm.window_scores(f_sun, d, f_earth, f_ref, slope, unk, prof, sp_, mis, sun0)
    _, rank_no_g0 = sm.window_scores(f_sun, d, f_earth, f_ref, slope, unk, prof, sp_, mis)
    for p in range(n):
        for i in range(S):
            r = compute_score(ScoreInputs(f_sun[p, i], d[p, i], f_earth[p, i], f_ref[p, i], slope[p], unk[p], True,
                                          sun_at_start=bool(sun0[p, i])), prof, sp_, mis)
            assert score[p, i] == pytest.approx(r.score, rel=1e-12)
            assert rank[p, i] == {"PASS": 0, "NO_DATA": 1, "FAIL": 2}[r.status.name]
    if solar_gate:
        assert ((rank == 2) & ~sun0).sum() == (~sun0).sum() and (rank_no_g0 < rank).any()
    else:
        assert (rank == rank_no_g0).all()


def test_mission_window_metrics_reports_sun_at_start():
    t = 5e8 + DT * np.arange(101)
    sun = np.arange(100) % 20 < 10
    w = sm.mission_window_metrics(np.append(sun, True), np.append(sun, True), t, 1.0, 0.25)   # 1 d = 48 muestras de 30 min
    i0 = np.rint((w.start_et - t[0]) / DT).astype(int)
    assert (w.sun_start == sun[i0]).all() and w.sun_start.dtype == bool


def test_best_start_per_point_and_rasters():
    """Un punto con una noche corta solo en unos días de inicio: la mejor fecha cae ahí y la puerta G4 lo confirma."""
    sp_ = ScoreParams()
    prof, mis = _profile_mission(dark=12.0)
    N, dur = 80 * 48, 14.0
    t = 5e8 + DT * np.arange(N + 1)
    rng = np.random.default_rng(3)
    wins = []
    for p in range(3):
        sun = np.ones(N, bool)
        if p == 0:                                    # noches de 20 h cada 10 d salvo entre los días 30 y 55
            for k in range(0, 80, 10):
                if not 30 <= k <= 55:
                    sun[k * 48:k * 48 + 40] = False
        elif p == 1:                                  # noche de 30 h cada 10 d en todo el periodo: nunca apto
            for k in range(0, 80, 10):
                sun[k * 48:k * 48 + 60] = False
        else:
            sun[:] = rng.random(N) > 0.5
        earth = np.ones(N, bool)
        wins.append(sm.mission_window_metrics(np.append(sun, True), np.append(earth, True), t, dur, 1.0,
                                              series_ref_earth=np.append(earth, True)))
    rows, cols = np.array([0, 0, 1]), np.array([0, 1, 0])
    wm = sm.build_window_map(dur, wins, rows, cols, (2, 2), np.array([3.0, 3.0, 3.0]), np.zeros(3), prof, mis, sp_, 0.5)
    b = wm.best
    assert b["gate"].tolist()[:2] == [0, 2]
    assert b["start_idx"][0] == 21 and b["d_max_h"][0] == 0.0     # primera ventana de 14 d sin noche (la del d 20 acaba en 20,83)
    assert b["apt_days"][0] == 26                                 # inicios 21..46: acaban antes de la noche del d 60
    assert b["apt_days"][0] == (wm.cube["gate"][0] == 0).sum() and 0 < b["apt_days"][0] < wm.n_starts
    assert b["apt_days"][1] == 0 and b["night_ok_days"][1] == 0
    assert b["score_min"][0] <= b["score"][0] <= b["score_max"][0]
    # el score de la mejor fecha es el máximo del cubo entre las fechas con las mejores puertas
    assert b["score"][0] == pytest.approx(wm.cube["score"][0].max(), rel=1e-5)
    # rasters: NaN fuera de candidatos, valores del cubo en candidatos
    r = wm.raster("score", int(b["start_idx"][0]))
    assert np.isnan(r[1, 1]) and r[0, 0] == pytest.approx(b["score"][0], rel=1e-5)
    assert wm.best_raster("apt_days")[0, 1] == 0.0


def test_max_start_days_limits_starts():
    N = 400 * 48
    t = DT * np.arange(N + 1)
    o = np.ones(N + 1, bool)
    m = sm.mission_window_metrics(o, o, t, 30.0, 1.0, max_start_days=365.0)
    assert len(m.start_et) == 365 and m.start_et[-1] == 364 * 86400.0       # 365 fechas de inicio (días 0..364)
    assert len(sm.mission_window_metrics(o, o, t, 30.0, 1.0).start_et) == 371   # sin tope: todo lo que cabe


# ---------------------------------------------------------------------------------------------- continuidad del enlace y G7 en el mapa
def _naive_runs(mask, n, stride):
    """(racha True más larga, racha False más larga) en muestras de cada ventana, a mano."""
    out_t, out_f = [], []
    for i in range(0, len(mask) - n + 1, stride):
        best = {True: 0, False: 0}
        run, prev = 0, None
        for v in mask[i:i + n]:
            run = run + 1 if prev == v else 1
            best[bool(v)] = max(best[bool(v)], run)
            prev = v
        out_t.append(best[True])
        out_f.append(best[False])
    return np.array(out_t), np.array(out_f)


@pytest.mark.parametrize("seed,N,p_stay,dur,step", [(0, 2000, 0.98, 3.0, 0.5), (1, 3000, 0.995, 14.0, 1.0), (4, 800, 0.95, 5.0, 1.0)])
def test_window_gap_and_longest_earth_equal_naive(seed, N, p_stay, dur, step):
    """El hueco máximo sin enlace de cada ventana (G7) y la racha de enlace más larga (G6) = bucle explícito, recortados a la ventana."""
    rng = np.random.default_rng(seed)
    sun, earth = series(rng, N, p_stay), series(rng, N, p_stay)
    t = 1e8 + DT * np.arange(N + 1)
    m = sm.mission_window_metrics(np.append(sun, False), np.append(earth, False), t, dur, step)
    n, stride = int(round(dur * 86400 / DT)), int(round(step * 86400 / DT))
    run_t, run_f = _naive_runs(earth, n, stride)
    np.testing.assert_allclose(m.longest_earth_h, run_t * DT / 3600.0)
    np.testing.assert_allclose(m.max_gap_h, run_f * DT / 3600.0)


@pytest.mark.parametrize("pov", [{}, {"max_link_gap_h": 24.0, "max_link_gap_type": "soft", "min_link_hours_per_day": 2.0},
                                 {"max_link_gap_h": 12.0, "max_link_gap_type": "soft", "min_link_hours_per_day": 8.0, "earth_floor": 0.5},
                                 {"max_link_gap_h": 96.0, "max_link_gap_type": "soft"}])
def test_vectorized_score_with_link_gap_equals_site_score(pov):
    """El score por ventana del mapa con ``max_gap_h`` = ``compute_score`` con ``max_link_gap_h`` (misma ``continuity_factor``)."""
    rng = np.random.default_rng(23)
    sp_ = ScoreParams(resolution_weight=0.25, earth_floor=0.25, link_gap_half_factor=1.0)
    prof, mis = _profile_mission()
    prof = dataclasses.replace(prof, **pov)
    n, S = 5, 30
    f_sun, f_earth, f_ref = 0.3 + 0.7 * rng.random((n, S)), rng.random((n, S)), 0.1 + 0.9 * rng.random((n, S))
    d, gap = rng.random((n, S)) * 20, rng.random((n, S)) * 200
    slope, unk = np.array([2.0, 4.0, 6.0, 8.0, 9.0]), np.zeros(n)
    score, _ = sm.window_scores(f_sun, d, f_earth, f_ref, slope, unk, prof, sp_, mis, max_gap_h=gap)
    base, _ = sm.window_scores(f_sun, d, f_earth, f_ref, slope, unk, prof, sp_, mis)
    assert (score <= base + 1e-12).all()                               # la continuidad nunca sube el score
    for p in range(n):
        for i in range(S):
            r = compute_score(ScoreInputs(f_sun[p, i], d[p, i], f_earth[p, i], f_ref[p, i], slope[p], unk[p], True, link_mode=True,
                                          max_link_gap_h=float(gap[p, i])), prof, sp_, mis)
            assert score[p, i] == pytest.approx(r.score, rel=1e-12)


def test_best_start_index_prefers_g7_then_min_gap_and_hard_gates_first():
    ones = np.ones(4)
    gate0 = np.zeros(4, np.uint8)
    # empate de score: gana la fecha que cumple G7 aunque sea la última (antes: la más temprana)
    assert sm.best_start_index(gate0, 97.4 * ones, np.zeros(4), ones, np.array([127.5, 127.5, 90.0, 0.0]), 48.0) == 3
    # ninguna cumple G7: la de menor hueco (aunque tenga menos score)
    assert sm.best_start_index(gate0, np.array([99.0, 80.0, 90.0, 95.0]), np.zeros(4), ones, np.array([300.0, 100.0, 120.0, 100.0]), 48.0) == 3
    # las puertas duras mandan: la que cumple G7 pero tiene rango 2 no gana
    assert sm.best_start_index(np.array([2, 0, 0, 0], np.uint8), np.array([99.0, 70.0, 80.0, 60.0]), np.zeros(4), ones,
                               np.array([0.0, 200.0, 200.0, 200.0]), 48.0) == 2
    # sin G7 (geometría): el criterio de siempre (score, luego D_max, luego f_sol, luego la más temprana)
    assert sm.best_start_index(gate0, np.array([50.0, 90.0, 90.0, 10.0]), np.array([0.0, 5.0, 3.0, 0.0]), ones, None, None) == 2


def test_build_window_map_link_mode_picks_g7_start_and_reports_gap():
    """Un punto con dos tipos de fechas: las pares puntúan igual pero con un hueco de 120 h; las impares, enlace continuo. El mapa elige una impar,
    informa su hueco y G7 PASS; en modo geometría (sin enlace) no hay hueco ni G7."""
    S = 6
    t = 1e8 + DT * 48 * np.arange(S)
    ok = np.arange(S) % 2 == 1
    f_earth = np.where(ok, 1.0, 0.6)
    gap = np.where(ok, 0.0, 120.0)
    w = sm.WindowMetrics(14.0, 1.0, t, np.full(S, 1.0), f_earth, f_earth, np.full(S, 300.0), np.zeros(S), np.full(S, 0.5),
                         np.ones(S, bool), gap, 336.0 - gap)
    sp_ = ScoreParams(resolution_weight=0.25, earth_floor=0.25, link_gap_half_factor=1.0)
    prof, mis = _profile_mission()
    prof = dataclasses.replace(prof, max_link_gap_h=48.0, max_link_gap_type="soft", min_link_hours_per_day=2.0)
    args = ([w], np.array([0]), np.array([0]), (1, 1), np.array([3.0]), np.array([0.0]), prof, mis, sp_, 0.5)
    wm = sm.build_window_map(14.0, *args, link_mode=True)
    assert wm.best["g7_ok"][0] == 1.0 and wm.best["gap_h"][0] == 0.0 and int(wm.best["start_idx"][0]) in (1, 3, 5)
    assert wm.cube["gap_h"].shape == (1, S) and wm.cube["score"][0, 1] > wm.cube["score"][0, 0] + 5.0   # el hueco baja el score
    geo = sm.build_window_map(14.0, *args)                              # sin enlace: sin continuidad, sin G7, la más temprana por f_sol/score
    assert np.isnan(geo.best["g7_ok"][0]) and np.isnan(geo.best["gap_h"][0]) and np.allclose(geo.cube["score"][0], geo.cube["score"][0, 0])
