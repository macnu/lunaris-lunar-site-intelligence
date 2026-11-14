"""Tests del score de idoneidad. Valores esperados de docs/science/matematica.md §7.7 (hechos a mano)."""
import itertools
import math
from dataclasses import replace

import pytest

import numpy as np

from lsi.analysis.site_score import (
    APTO, CONDICIONAL, DEFAULT_PROFILES, KEYS, NO_APTO, SIN_DATOS, aggregate, blend, choose_start, compute_score,
    decide_verdict, evaluate_gates, max_sustainable, normalize_weights, params_from_config, pick_windows,
    profiles_from_config, score_with_range, subscores,
)
from lsi.analysis.suitability_map import mission_window_metrics
from lsi.contracts import GateStatus, MissionProfile, ScoreInputs, ScoreParams, Threshold

P = ScoreParams()
LANDER = DEFAULT_PROFILES["lander_solar_no_rhu"]


def site(f_sun=0.78, d=60.0, f_e=0.40, slope=8.0, **kw):
    """Sitio A de §7.7 por defecto."""
    base = dict(f_sun=f_sun, d_max_h=d, f_earth=f_e, f_earth_ref=0.47, slope_p90_deg=slope,
                unknown_fraction=0.0, observer_in_dem=True, has_dem=slope is not None)
    base.update(kw)
    return ScoreInputs(**base)


# ---- ejemplo §7.7 ---------------------------------------------------------------------
def test_subscores_ejemplo_a_mano():
    s = subscores(site(), LANDER, P)
    assert s["sun"] == pytest.approx(0.82857, abs=1e-5)
    assert s["night"] == pytest.approx(0.42045, abs=1e-5)
    assert s["earth"] == pytest.approx(0.85106, abs=1e-5)
    assert s["terrain"] == pytest.approx(0.70000, abs=1e-9)


def test_ejemplo_numerico_perfiles():
    r = compute_score(site(), LANDER, P)
    assert r.score == pytest.approx(67.9, abs=0.05)
    assert compute_score(site(), DEFAULT_PROFILES["rover"], P).score == pytest.approx(70.2, abs=0.05)
    comms = compute_score(site(), DEFAULT_PROFILES["dte_comms"], P)
    # DTE lleva earth_floor = 0,5 (> f_E,ref = 0,47): s_earth = 0,40/0,5 = 0,8 en vez de 0,851 → 73,9 (antes 76,7)
    assert comms.score == pytest.approx(73.9, abs=0.05)
    assert r.weakest_key == "night"
    pen = {s.key: s.penalty_pct for s in r.subscores}
    assert pen["night"] == pytest.approx(55.9, abs=0.05)
    assert sum(pen.values()) == pytest.approx(100.0)
    one = {s.key: s.score_if_one for s in r.subscores}
    assert one == pytest.approx({"sun": 73.2, "night": 84.3, "earth": 69.5, "terrain": 72.9}, abs=0.05)
    assert (r.status, r.attenuated, r.partial, r.terrain_data) == (GateStatus.PASS, False, False, True)
    assert r.score_min == r.score_max == r.score and r.missing_keys == ()


def test_rango_por_escenarios():
    pes, opt = site(0.74, 72, 0.38, 9), site(0.81, 50, 0.42, 7)
    r = score_with_range(site(), [pes, opt], LANDER, P)
    assert r.score_min == pytest.approx(60.8, abs=0.05)
    assert r.score_max == pytest.approx(74.3, abs=0.05)
    assert r.score_min < r.score < r.score_max
    # sin escenarios, el rango se reduce al nominal
    r0 = score_with_range(site(), [], LANDER, P)
    assert r0.score_min == r0.score_max == r0.score


# ---- tests i-v de matematica.md §7.7 --------------------------------------------------
W = LANDER.weights


def test_i_todo_uno_da_100():
    assert aggregate({k: 1.0 for k in KEYS}, W, P.eps_s) == pytest.approx(100.0)


def test_ii_un_indicador_cero_da_eps_a_w():
    s = {"sun": 0.0, "night": 0.5, "earth": 0.8, "terrain": 0.9}
    esperado = 100 * P.eps_s ** 0.40 * 0.5 ** 0.25 * 0.8 ** 0.15 * 0.9 ** 0.20
    assert aggregate(s, W, P.eps_s) == pytest.approx(esperado)
    assert 100 * P.eps_s ** 0.40 == pytest.approx(15.8, abs=0.05)


def test_iii_pesos_y_s_iguales_da_100_s():
    assert aggregate({k: 0.37 for k in KEYS}, {k: 0.25 for k in KEYS}, P.eps_s) == pytest.approx(37.0)


def test_iv_invariancia_al_orden():
    s = {"sun": 0.3, "night": 0.9, "earth": 0.6, "terrain": 0.5}
    ref = aggregate(s, W, P.eps_s)
    for perm in itertools.permutations(KEYS):
        assert aggregate({k: s[k] for k in perm}, {k: W[k] for k in perm}, P.eps_s) == pytest.approx(ref)


def test_v_pesos_se_renormalizan():
    assert compute_score(site(), LANDER, P, weights_override={k: 2 * v for k, v in W.items()}).score == \
        pytest.approx(67.9, abs=0.05)
    assert normalize_weights({"sun": 1, "earth": 3}) == {"sun": 0.25, "night": 0.0, "earth": 0.75, "terrain": 0.0}
    with pytest.raises(ValueError):
        normalize_weights({"sun": 1, "foo": 1})
    with pytest.raises(ValueError):
        normalize_weights({"sun": -1, "earth": 2})


def test_pesos_editables_cambian_el_resultado():
    solo_tierra = compute_score(site(), LANDER, P, weights_override={"earth": 1.0}).score
    assert solo_tierra == pytest.approx(100 * 0.85106, abs=0.01)


# ---- monotonía ------------------------------------------------------------------------
def test_monotonia_mas_sol_no_baja_el_score():
    prev = -1.0
    for f in [i / 20 for i in range(21)]:
        sc = compute_score(site(f_sun=f), LANDER, P).score
        assert sc >= prev - 1e-12
        prev = sc


@pytest.mark.parametrize("campo,mejor,peor", [("d", 10.0, 100.0), ("f_e", 0.47, 0.1), ("slope", 2.0, 18.0)])
def test_monotonia_otros_indicadores(campo, mejor, peor):
    assert compute_score(site(**{campo: mejor}), LANDER, P).score > compute_score(site(**{campo: peor}), LANDER, P).score


def test_f_earth_satura_en_la_referencia():
    assert compute_score(site(f_e=0.9), LANDER, P).score == compute_score(site(f_e=0.47), LANDER, P).score


# ---- puertas --------------------------------------------------------------------------
def mission(**thr):
    return MissionProfile("m", "m", {k: Threshold(v, t, "suposicion") for k, (v, t) in thr.items()})


def status_of(gates):
    return {g.id: g.status for g in gates}


def test_g1_sin_energia_falla_pero_no_da_cero():
    r = compute_score(site(f_sun=0.04), LANDER, P)
    assert status_of(r.gates)["G1"] == GateStatus.FAIL and "energía solar" in r.gates[0].reason
    assert r.status == GateStatus.FAIL and r.attenuated and r.score > 0


def test_g1_no_aplica_a_comunicaciones():
    r = compute_score(site(f_sun=0.0), DEFAULT_PROFILES["dte_comms"], P)
    assert status_of(r.gates)["G1"] == GateStatus.NOT_APPLICABLE


def test_g2_pendiente_por_defecto_y_de_perfil():
    assert status_of(evaluate_gates(site(slope=21), LANDER, P, None))["G2"] == GateStatus.FAIL
    assert status_of(evaluate_gates(site(slope=15), LANDER, P, None))["G2"] == GateStatus.PASS
    m = mission(max_landing_slope_deg=(10.0, "hard"))   # diseño del perfil prevalece sobre 20°
    assert status_of(evaluate_gates(site(slope=15), LANDER, P, m))["G2"] == GateStatus.FAIL


def test_g3_datos():
    g = lambda **kw: status_of(evaluate_gates(site(**kw), LANDER, P, None))["G3"]  # noqa: E731
    assert g() == GateStatus.PASS
    assert g(unknown_fraction=0.51) == GateStatus.NO_DATA
    assert g(unknown_fraction=0.5) == GateStatus.PASS
    assert g(observer_in_dem=False) == GateStatus.NO_DATA


def test_g4_noche_dura_del_perfil():
    m = mission(max_dark_h_no_nuclear=(12.0, "hard"))
    assert status_of(evaluate_gates(site(d=13), LANDER, P, m))["G4"] == GateStatus.FAIL
    assert status_of(evaluate_gates(site(d=12), LANDER, P, m))["G4"] == GateStatus.PASS
    # una noche máxima BLANDA ya no se ignora: se evalúa, pero su fallo no rechaza (hard=False; ver tests de estados)
    soft = {g.id: g for g in evaluate_gates(site(d=99), LANDER, P, mission(max_dark_h_no_nuclear=(12.0, "soft")))}["G4"]
    assert soft.status == GateStatus.FAIL and not soft.hard and soft.limit == 12.0 and soft.value == 99.0
    assert status_of(evaluate_gates(site(d=99), LANDER, P, mission(max_dark_h_no_nuclear=(None, "n/a"))))["G4"] \
        == GateStatus.NOT_APPLICABLE
    assert status_of(evaluate_gates(site(d=99), LANDER, P, None))["G4"] == GateStatus.NOT_APPLICABLE


def test_estado_peor_entre_puertas_fail_gana_a_no_data():
    r = compute_score(site(f_sun=0.01, unknown_fraction=0.9), LANDER, P)
    assert r.status == GateStatus.FAIL


# ---- modo parcial (RF-11, §5.9) --------------------------------------------------------
def test_modo_parcial_sin_terreno():
    sin = site(slope=None)
    r = compute_score(sin, LANDER, P)
    assert r.partial and not r.terrain_data and r.missing_keys == ("terrain",)
    assert r.status == GateStatus.NO_DATA and r.attenuated
    assert r.score_min < r.score < r.score_max
    st = status_of(r.gates)
    assert st["G3"] == GateStatus.NO_DATA and st["G2"] == GateStatus.NO_DATA  # G2 nunca PASS sin datos
    assert "esfera lisa" in r.gates[2].reason
    terr = next(s for s in r.subscores if s.key == "terrain")
    assert math.isnan(terr.s) and terr.value is None and terr.weight == 0.0 and terr.penalty_pct == 0.0
    # nominal = media geométrica renormalizada sobre los 3 restantes
    s = subscores(site(), LANDER, P)
    w3 = {"sun": 0.40 / 0.8, "night": 0.25 / 0.8, "earth": 0.15 / 0.8}
    assert r.score == pytest.approx(100 * math.prod(s[k] ** w for k, w in w3.items()))
    # extremos: terreno = ε_s y = 1 sin renormalizar
    full = compute_score(site(slope=5.0), LANDER, P)      # s_terreno = 1
    assert r.score_max == pytest.approx(full.score)
    assert r.score_min == pytest.approx(full.score * P.eps_s ** 0.20)
    assert r.weakest_key == "night"
    assert any("PARCIAL" in a for a in r.assumptions)


def test_parcial_con_rango_de_escenarios_se_ensancha():
    r = score_with_range(site(slope=None), [site(0.74, 72, 0.38, None)], LANDER, P)
    assert r.partial and r.score_min < r.score < r.score_max


def test_con_terreno_no_es_parcial():
    r = compute_score(site(), LANDER, P)
    assert not r.partial and r.terrain_data and "PARCIAL" not in " ".join(r.assumptions)


# ---- validación de entradas ------------------------------------------------------------
@pytest.mark.parametrize("kw", [dict(f_sun=float("nan")), dict(f_sun=1.2), dict(d=-1.0), dict(f_e=-0.1),
                                dict(unknown_fraction=2.0), dict(f_earth_ref=0.0), dict(slope=-3.0)])
def test_entradas_invalidas_lanzan(kw):
    with pytest.raises(ValueError):
        compute_score(site(**kw), LANDER, P)


def test_pendiente_sin_dem_es_incoherente():
    with pytest.raises(ValueError):
        compute_score(site(has_dem=False), LANDER, P)


def test_determinista():
    a, b = compute_score(site(), LANDER, P), compute_score(site(), LANDER, P)
    assert (a.score, a.score_min, a.score_max, a.gates, a.subscores) == (b.score, b.score_min, b.score_max, b.gates, b.subscores)


# ---- parámetros y perfiles desde config -------------------------------------------------
def test_perfiles_por_defecto_coinciden_con_config(simulation_cfg):
    cfg = simulation_cfg["score"]
    # los defectos de ScoreParams son «comportamiento antiguo» (earth_floor = λ = 0); la config activa la corrección
    assert params_from_config(cfg) == replace(P, earth_floor=0.25, resolution_weight=0.25, link_gap_half_factor=1.0)
    assert profiles_from_config(cfg) == dict(DEFAULT_PROFILES)
    assert {k: v.mission_days for k, v in profiles_from_config(cfg).items()} == {
        "lander_solar_no_rhu": 14.0, "lander_with_batteries": 30.0, "lander_rhu": 90.0, "rover": 100.0,
        "base_isru": 365.0, "dte_comms": 365.0, "custom": None}   # revision-espacial §6


def test_umbrales_vienen_de_params():
    # cambiar f0/f1 mueve s_sun; cambiar la puerta G1 cambia el estado
    p2 = replace(P, f0=0.0, f1=1.0, g1_min_sun_fraction=0.9)
    assert subscores(site(f_sun=0.5), LANDER, p2)["sun"] == pytest.approx(0.5)
    assert status_of(evaluate_gates(site(f_sun=0.8), LANDER, p2, None))["G1"] == GateStatus.FAIL


def test_d_half_del_perfil_prevalece():
    pr = replace(LANDER, d_half_h=24.0)
    assert subscores(site(d=24.0), pr, P)["night"] == pytest.approx(0.5)


def test_confianza_con_rango():
    r = score_with_range(site(), [site(0.74, 72, 0.38, 9), site(0.81, 50, 0.42, 7)], LANDER, P, c_sup=0.9)
    assert r.confidence.c_range == pytest.approx(1 - (r.score_max - r.score_min) / 25)
    assert r.confidence.c == pytest.approx(min(1.0, 0.9, r.confidence.c_range))


# ====================================================================================================
# Ronda de correcciones: estado por puertas y escenarios, ventana de misión, saturación
# ====================================================================================================
PC = replace(P, earth_floor=0.25, resolution_weight=0.25)        # parámetros de config/simulation.json
M_LANDER = mission(max_landing_slope_deg=(10.0, "hard"), max_dark_h_no_nuclear=(12.0, "hard"),
                   min_contiguous_earth_window_h=(2.0, "soft"))


def good(**kw):
    """Sitio que supera todas las puertas del lander: Sol al inicio, noche 0 h, pendiente 4°, Tierra 100 h continua."""
    base = dict(f_sun=0.95, d=0.0, f_e=0.47, slope=4.0, sun_at_start=True, longest_earth_h=100.0)
    base.update(kw)
    return site(**base)


def verdict(nom, scen=(), profile=LANDER, m=M_LANDER, **kw):
    r = score_with_range(nom, list(scen), profile, PC, m, **kw)
    return r.verdict, r


def test_estado_apto_supera_todo_en_nominal_y_escenarios():
    v, r = verdict(good(), [good(f_sun=0.9, d=3.0)])
    assert v == APTO and not r.verdict_provisional and r.status == GateStatus.PASS
    assert [g.id for g in r.gates] == ["G0", "G1", "G2", "G3", "G4", "G6"]


def test_el_estado_no_depende_de_la_nota():
    # mismas puertas, notas muy distintas: el estado es el mismo (no existe APTO_MIN; el score solo ordena)
    a = score_with_range(good(), [], LANDER, PC, M_LANDER)
    b = score_with_range(good(f_sun=0.06, f_e=0.1), [], LANDER, PC, M_LANDER)   # f_sol mínima: nota bajísima, G1 pasa
    c = score_with_range(good(), [], LANDER, PC, M_LANDER, weights_override={"earth": 1.0})
    assert a.score - b.score > 30 and {a.verdict, b.verdict, c.verdict} == {APTO}
    import lsi.analysis.site_score as ss
    assert not hasattr(ss, "APTO_MIN")


def test_estado_condicional_por_puerta_blanda_y_por_escenario():
    v, r = verdict(good(longest_earth_h=1.0))                      # G6 blanda falla: no rechaza, pero no es APTO
    assert v == CONDICIONAL and r.status == GateStatus.PASS and "G6" in r.verdict_reason
    assert next(g for g in r.gates if g.id == "G6").hard is False
    v, r = verdict(good(), [good(), good(d=20.0)])                  # pasa el nominal pero un escenario viola G4
    assert v == CONDICIONAL and "1 de 2 escenarios" in r.verdict_reason and "G4" in r.verdict_reason
    v, r = verdict(good(), [], feasible_fraction=0.05)             # ventana frágil (< 10 % de inicios factibles)
    assert v == CONDICIONAL and "frágil" in r.verdict_reason
    assert verdict(good(), [], feasible_fraction=0.10)[0] == APTO


def test_estado_no_apto_por_puerta_dura_nominal():
    v, r = verdict(good(d=13.0), [good()])
    assert v == NO_APTO and not r.verdict_provisional and r.status == GateStatus.FAIL and "G4" in r.verdict_reason
    v, r = verdict(good(sun_at_start=False))                       # G0: llegada de noche
    assert v == NO_APTO and "llegada de noche" in r.verdict_reason
    assert verdict(good(slope=12.0))[0] == NO_APTO                 # G2 con diseño del perfil (10°)


def test_g0_se_puede_desactivar_y_no_aplica_sin_solar():
    ev = evaluate_gates(good(sun_at_start=False), LANDER, replace(PC, g0_needs_sun=False), M_LANDER)
    assert status_of(ev)["G0"] == GateStatus.NOT_APPLICABLE
    ev = evaluate_gates(good(sun_at_start=False), DEFAULT_PROFILES["dte_comms"], PC, None)
    assert status_of(ev)["G0"] == GateStatus.NOT_APPLICABLE
    assert "G0" not in status_of(evaluate_gates(site(), LANDER, PC, None))        # sin ventana no hay G0


def test_estado_sin_datos_modo_parcial_sin_terreno():
    v, r = verdict(good(slope=None))
    assert r.partial and v == SIN_DATOS and "G2" in r.verdict_reason and r.score > 80   # nunca APTO aunque la nota sea alta
    # falla ya sobre esfera lisa → NO APTO provisional, etiquetado «cota optimista»
    v, r = verdict(good(slope=None, d=20.0))
    assert v == NO_APTO and r.verdict_provisional and "provisional" in r.verdict_reason and "optimista" in r.verdict_reason
    # horizonte desconocido > 50 % con DEM: SIN DATOS, no rechazo
    assert verdict(good(unknown_fraction=0.9))[0] == SIN_DATOS


def test_estado_periodo_corto_es_sin_datos_pero_una_puerta_dura_manda():
    v, r = verdict(good(), short_period=True)
    assert v == SIN_DATOS and "periodo más corto" in r.verdict_reason
    assert verdict(good(d=30.0), short_period=True)[0] == NO_APTO


def test_rover_noche_50h_blanda_y_rhu_sin_limite():
    rover, rhu = DEFAULT_PROFILES["rover"], DEFAULT_PROFILES["lander_rhu"]
    m_rover = mission(max_landing_slope_deg=(10.0, "hard"), max_dark_h_no_nuclear=(12.0, "hard"))   # panels.json antiguo
    assert verdict(good(d=40.0), profile=rover, m=m_rover)[0] == APTO           # 40 h ≤ 50 h (el 12 h duro ya no manda)
    v, r = verdict(good(d=60.0), profile=rover, m=m_rover)                     # 60 h > 50 h: blanda → CONDICIONAL, no NO APTO
    assert v == CONDICIONAL and r.status == GateStatus.PASS and not next(g for g in r.gates if g.id == "G4").hard
    assert verdict(good(d=500.0), profile=rhu)[0] == APTO                      # RHU: G4 no aplica
    assert status_of(evaluate_gates(good(d=500.0), rhu, PC, M_LANDER))["G4"] == GateStatus.NOT_APPLICABLE


def test_decide_verdict_directo_sin_escenarios():
    r = compute_score(good(), LANDER, PC, M_LANDER)
    assert decide_verdict(r, [], PC) == (APTO, r.verdict_reason, False)


# ---- saturación: s_earth con mínimo útil y resolución en la parte alta -------------------------------
def test_s_earth_no_satura_con_tierra_minima_en_la_referencia():
    corto = site(f_e=0.08, f_earth_ref=0.08)
    assert subscores(corto, LANDER, P)["earth"] == 1.0                       # antiguo: 0,08/0,08 → «perfecta»
    assert subscores(corto, LANDER, PC)["earth"] == pytest.approx(0.08 / 0.25)   # mínimo útil: 0,32
    assert compute_score(corto, LANDER, PC).score < compute_score(corto, LANDER, P).score
    # con referencia ≥ mínimo (≈ 0,5 en el polo) no cambia nada
    c = site(f_e=0.40, f_earth_ref=0.5)
    assert subscores(c, LANDER, PC)["earth"] == subscores(c, LANDER, P)["earth"] == pytest.approx(0.8)
    # DTE usa 0,5: 0,40 de Tierra con referencia 0,47 → 0,8
    assert subscores(site(f_e=0.40), DEFAULT_PROFILES["dte_comms"], PC)["earth"] == pytest.approx(0.8)
    assert subscores(site(f_e=0.40), replace(LANDER, earth_floor=0.0), PC)["earth"] == pytest.approx(0.40 / 0.47)


def test_resolucion_arriba_valor_a_mano_y_sin_amontonar_en_100():
    sat = dict(d=0.0, f_e=0.47, f_earth_ref=0.47)
    b = site(f_sun=1.0, slope=1.0, **sat)
    # A = 1 (todo saturado); Q = (1 − 1/15)^0,20 (solo el terreno baja de 1) → S = 100·Q^0,25 = 100·(14/15)^0,05
    assert compute_score(b, LANDER, PC).score == pytest.approx(100 * (14 / 15) ** 0.05, rel=1e-12)
    assert compute_score(site(f_sun=1.0, slope=0.0, **sat), LANDER, PC).score == pytest.approx(100.0)
    # λ = 0 reproduce el score antiguo (media geométrica de los s_i)
    assert compute_score(site(), LANDER, P).score == pytest.approx(aggregate(subscores(site(), LANDER, P), W, P.eps_s))
    s = {k: 0.5 for k in KEYS}
    assert blend(s, {k: 0.2 for k in KEYS}, W, P.eps_s, 0.0) == pytest.approx(aggregate(s, W, P.eps_s))
    # 9 sitios distintos con todo por encima de su umbral: antes TODOS 100; ahora se distinguen y solo uno llega a 100
    grid = [site(f_sun=f, slope=sl, d=0.0, f_e=0.47, f_earth_ref=0.47) for f in (0.9, 0.95, 1.0) for sl in (0.0, 2.0, 4.0)]
    old = {round(compute_score(x, LANDER, P).score, 6) for x in grid}
    new = [compute_score(x, LANDER, PC).score for x in grid]
    assert old == {100.0} and len({round(v, 3) for v in new}) == 9
    assert sum(v >= 99.995 for v in new) == 1


def test_score_mejora_estrictamente_dentro_de_lo_saturado():
    sc = [compute_score(site(f_sun=1.0, d=0.0, f_e=0.47, slope=sl), LANDER, PC).score for sl in (0, 1, 2, 3, 4, 5)]
    assert all(a > b for a, b in zip(sc, sc[1:]))
    sc0 = [compute_score(site(f_sun=1.0, d=0.0, f_e=0.47, slope=sl), LANDER, P).score for sl in (0, 1, 2, 3, 4, 5)]
    assert len({round(x, 9) for x in sc0}) == 1                                      # antiguo: plano hasta 5°


# ---- piezas puras de la ventana de misión -------------------------------------------------------------
def test_choose_start_y_pick_windows():
    assert choose_start([50, 90, 70], [0, 1, 0]) == (2, True)             # la de 90 viola una dura: gana la mejor factible
    assert choose_start([50, 90, 70], [2, 1, 1]) == (1, False)            # ninguna factible: menos violaciones, luego score
    assert choose_start([80, 80], [0, 0]) == (0, True)                    # empate: la más temprana
    t = np.arange(10) * 86400.0
    sc = np.array([10, 90, 80, 30, 85, 20, 70, 60, 50, 40.0])
    ok = np.ones(10, bool)
    assert pick_windows(t, sc, ok, 3 * 86400.0, 3) == [1, 4, 7]           # 90 (d1), 85 (d4), 60 (d7): separadas ≥ 3 d
    ok[4] = False
    assert pick_windows(t, sc, ok, 3 * 86400.0, 3) == [1, 6, 9]           # 4 no factible → 90, 70 (d6), 40 (d9)
    assert pick_windows(t, sc, np.zeros(10, bool), 86400.0, 3) == []


def test_max_sustainable_valores_a_mano():
    H = 3600.0
    dark = np.array([[100, 130], [500, 505], [800, 830.0]]) * H           # noches de 30 h, 5 h y 30 h
    d, cens = max_sustainable(np.array([0, 50, 135, 805.0]) * H, dark, 12.0, 1000.0 * H)
    # inicio 0 h: primera noche letal empieza a 100 h → muere a 112 h; 50 h → 62 h; 135 h → 812 h − 135 h; 805 h: sin más
    assert d * 24 == pytest.approx([112.0, 62.0, 812.0 - 135.0, 1000.0 - 805.0])
    assert cens.tolist() == [False, False, False, True]
    d, cens = max_sustainable(np.array([0.0]) * H, np.empty((0, 2)), 12.0, 240.0 * H)   # sin noches: todo el periodo (cota inf.)
    assert d[0] == pytest.approx(10.0) and cens[0]


def _sweep(sun_hours, days, profile, m):
    """Réplica del barrido del pipeline sobre una serie horaria: (factibles por inicio, índices de inicio)."""
    N = len(sun_hours)
    sun = np.append(sun_hours, True)
    wm = mission_window_metrics(sun, np.ones(N + 1, bool), np.arange(N + 1) * 3600.0, days, 1.0,
                                series_ref_earth=np.ones(N + 1, bool))
    i0 = np.rint((wm.start_et - wm.start_et[0]) / 3600.0).astype(int)
    ok = []
    for j in range(len(i0)):
        r = compute_score(site(f_sun=float(wm.f_sun[j]), d=float(wm.max_dark_h[j]), f_e=1.0, f_earth_ref=1.0, slope=3.0,
                               sun_at_start=bool(sun[i0[j]]), longest_earth_h=1000.0), profile, PC, m)
        ok.append(not [g for g in r.gates if g.hard and g.status == GateStatus.FAIL])
    return np.array(ok), i0


def test_barrido_una_noche_de_100h_cae_solo_en_las_ventanas_que_la_tocan():
    N = 24 * 400
    sun = np.ones(N, bool)
    sun[24 * 200:24 * 200 + 100] = False                        # una noche de 100 h el día 200
    ok, i0 = _sweep(sun, 14.0, LANDER, M_LANDER)
    # esperado independiente: ventana [t, t+336 h] solapa > 12 h con [4800, 4900) o empieza dentro de la noche (G0)
    t = i0.astype(float)
    ov = np.clip(np.minimum(t + 336.0, 4900.0) - np.maximum(t, 4800.0), 0.0, None)
    esperado = ~((ov > 12.0) | ((t >= 4800.0) & (t < 4900.0)))
    assert ok.tolist() == esperado.tolist()
    # fracción factible ≈ 1 − 17,2 d / 387 d ≈ 0,956 (no 0, como daría la regla anual de 365 d)
    assert ok.mean() == pytest.approx(0.956, abs=0.01) and ok.mean() < 1.0


def test_barrido_noche_cada_30_dias_lander_si_base_no():
    N = 24 * 400
    sun = np.ones(N, bool)
    for k in range(14):
        sun[720 * k + 240:720 * k + 340] = False                # 100 h de noche cada 30 d
    lander_ok, i0 = _sweep(sun, 14.0, LANDER, M_LANDER)
    assert lander_ok.any()                                      # existe una fecha de inicio válida
    t = i0.astype(float)
    fail = np.zeros(len(t), bool)
    for k in range(14):
        lo, hi = 720.0 * k + 240.0, 720.0 * k + 340.0
        fail |= (np.clip(np.minimum(t + 336.0, hi) - np.maximum(t, lo), 0, None) > 12.0) | ((t >= lo) & (t < hi))
    assert lander_ok.tolist() == (~fail).tolist()
    m_base = mission(max_landing_slope_deg=(10.0, "hard"), max_dark_h_no_nuclear=(24.0, "hard"))
    base_ok, _ = _sweep(sun, 365.0, DEFAULT_PROFILES["base_isru"], m_base)
    assert not base_ok.any()                                    # ventana de un año: contiene noches de 100 h > 24 h → NO APTO


# ---- cierre: energía ligada al panel (T39), G5 y rango explícito ----------------------------------------
def test_effective_energy_is_monotone_and_bounded():
    from lsi.analysis.site_score import effective_energy
    assert effective_energy(0.4, 0.6, 0.5) == pytest.approx(0.5)            # a mano: 0,5·0,4 + 0,5·0,6
    assert effective_energy(0.0, 0.0, 0.5) == 0.0 and effective_energy(1.0, 1.0, 0.5) == 1.0
    assert effective_energy(0.5, 0.2, 0.5) < effective_energy(0.6, 0.2, 0.5) < effective_energy(0.6, 0.3, 0.5)
    assert effective_energy(1.2, 1.0, 0.5) == 1.0                           # P_rel puede rozar 1,01: acotado


def test_energy_subscore_uses_effective_power_when_a_panel_is_chosen():
    geo = compute_score(site(0.78), LANDER, P)
    pan = compute_score(site(0.78, f_power_eff=0.30, p_rel_mean=0.2, duty_useful=0.4, useful_power_fraction=0.25), LANDER, P)
    assert pan.energy_basis == "panel" and geo.energy_basis == "geometric"
    assert subscores(site(0.78, f_power_eff=0.30), LANDER, P)["sun"] == pytest.approx((0.30 - 0.2) / 0.7)   # rampa f0=0,2, f1=0,9
    assert pan.score < geo.score and pan.subscores[0].value == 0.30 and "panel" in pan.subscores[0].label
    assert "Sol geométrico" in " ".join(geo.assumptions) and "Sol geométrico" not in " ".join(pan.assumptions)
    # G1 sigue siendo geométrico: f_sol 0,78 pasa aunque la potencia efectiva sea baja
    assert next(g for g in pan.gates if g.id == "G1").status == GateStatus.PASS
    with pytest.raises(ValueError):
        compute_score(site(0.78, f_power_eff=1.5), LANDER, P)


def test_g5_useful_power_gate_soft_by_default_hard_in_base_and_absent_without_panel():
    ok = evaluate_gates(site(duty_useful=0.6, useful_power_fraction=0.25), LANDER, P, None)
    bad = evaluate_gates(site(duty_useful=0.3, useful_power_fraction=0.25), LANDER, P, None)
    g_ok, g_bad = (next(g for g in gs if g.id == "G5") for gs in (ok, bad))
    assert g_ok.status == GateStatus.PASS and g_bad.status == GateStatus.FAIL and g_bad.hard is False and g_bad.limit == 0.5
    assert g_bad.margin_fraction == pytest.approx((0.3 - 0.5) / 0.5)
    base = evaluate_gates(site(duty_useful=0.6), DEFAULT_PROFILES["base_isru"], P, None)
    g5 = next(g for g in base if g.id == "G5")
    assert g5.limit == 0.75 and g5.hard is True and g5.status == GateStatus.FAIL
    assert "G5" not in {g.id for g in evaluate_gates(site(), LANDER, P, None)}
    assert "G5" not in {g.id for g in evaluate_gates(site(duty_useful=0.1), DEFAULT_PROFILES["dte_comms"], P, None)}
    r = score_with_range(site(duty_useful=0.3), [], LANDER, P)             # blanda: CONDICIONAL, no NO APTO
    assert r.verdict == CONDICIONAL and "G5" in r.verdict_reason and r.status == GateStatus.PASS


def test_range_is_explicit_when_uncertainty_was_not_computed():
    none = score_with_range(site(), [], LANDER, P)
    assert none.range_computed is False and none.range_note.startswith("rango no calculado")
    same = score_with_range(site(), [site()], LANDER, P)                    # calculado y de ancho cero
    assert same.range_computed is True and "estrecho" in same.range_note and same.score_min == same.score_max
    wide = score_with_range(site(), [site(0.74, 72, 0.38, 9), site(0.81, 50, 0.42, 7)], LANDER, P)
    assert wide.range_computed is True and wide.range_note.startswith("rango calculado con 2 escenarios")
    part = score_with_range(site(slope=None), [], LANDER, P)                # sin terreno: [min,max] ≠ incertidumbre
    assert part.range_computed is False and "esfera lisa" in part.range_note and part.score_min < part.score_max


# ---------------------------------------------------------------------------------------------- enlace DTE (G7, modo enlace)
def test_g7_solo_con_enlace_y_limite_de_perfil():
    base = site(longest_earth_h=10.0)
    assert "G7" not in [g.id for g in evaluate_gates(base, LANDER, P, None)]          # sin max_link_gap_h no se evalúa
    g = {g.id: g for g in evaluate_gates(replace(base, max_link_gap_h=100.0, link_mode=True), LANDER, P, None)}["G7"]
    assert g.status == GateStatus.FAIL and not g.hard and g.limit == 48.0 and g.value == 100.0   # lander: 48 h blanda [sup]
    assert g.margin_fraction == pytest.approx((48.0 - 100.0) / 48.0)
    ok = {g.id: g for g in evaluate_gates(replace(base, max_link_gap_h=30.0), LANDER, P, None)}["G7"]
    assert ok.status == GateStatus.PASS
    hard = {g.id: g for g in evaluate_gates(replace(base, max_link_gap_h=100.0), replace(LANDER, max_link_gap_type="hard"),
                                            P, None)}["G7"]
    assert hard.hard and hard.status == GateStatus.FAIL


def test_g7_blanda_vuelve_condicional_no_rechaza():
    r = compute_score(site(max_link_gap_h=100.0, link_mode=True, longest_earth_h=10.0), LANDER, P)
    assert r.status == GateStatus.PASS and r.verdict == CONDICIONAL and "G7" in r.verdict_reason


def test_modo_enlace_etiqueta_y_supuesto_y_modo_geometrico_intacto():
    r_l = compute_score(site(link_mode=True), LANDER, P)
    r_g = compute_score(site(), LANDER, P)
    assert next(s for s in r_l.subscores if s.key == "earth").label.startswith("Enlace")
    assert next(s for s in r_g.subscores if s.key == "earth").label == "Visibilidad de la Tierra"
    assert any("ENLACE posible" in a for a in r_l.assumptions) and not any("ENLACE posible" in a for a in r_g.assumptions)
    assert r_l.score == pytest.approx(r_g.score)            # mismos números de entrada → mismo score (solo cambia el sentido)


def test_perfiles_traen_limite_de_hueco_con_etiqueta_en_config(simulation_cfg):
    for pid, p in simulation_cfg["score"]["profiles"].items():
        if pid == "custom":
            continue
        assert p["link"]["max_gap_h"] > 0 and p["link"]["confidence"] == "suposicion" and p["link"]["min_earth_elevation_deg"] == 0.0


# ---------------------------------------------------------------------------------------------- continuidad del enlace (revision-enlace B1)
PK = replace(P, earth_floor=0.25, link_gap_half_factor=1.0)      # como la config: continuidad activa


def link_site(f, ref, gap, **kw):
    """Sitio con enlace DTE y hueco medido en la ventana (la continuidad solo actúa con ``max_link_gap_h``)."""
    return site(f_sun=1.0, d=0.0, f_e=f, slope=0.0, f_earth_ref=ref, max_link_gap_h=gap, link_mode=True, **kw)


def s_earth(f, ref, gap, profile=LANDER, params=PK):
    return subscores(link_site(f, ref, gap), profile, params)["earth"]


def test_continuidad_hueco_127h_puntua_claramente_menos_que_enlace_continuo():
    """Shackleton (6-dic, 14 d): enlace 62 % con 127,5 h sin enlace y f_ref 0,361; frente a Malapert/11-dic: 100 % sin huecos y f_ref 0,742.
    Antes ambos daban s_earth = 1 y score 97,41; ahora el primero cae muy por debajo (G7 del lander: 48 h)."""
    shk, mal = link_site(0.6206, 0.361, 127.5), link_site(1.0, 0.742, 0.0)
    assert subscores(shk, LANDER, P)["earth"] == subscores(mal, LANDER, P)["earth"] == 1.0      # sin continuidad: empate (el defecto)
    a, b = compute_score(shk, LANDER, PK), compute_score(mal, LANDER, PK)
    assert b.score == pytest.approx(compute_score(mal, LANDER, P).score)                        # sin hueco ni falta de horas nada cambia
    assert next(s for s in b.subscores if s.key == "earth").s == pytest.approx(1.0)
    se = next(s for s in a.subscores if s.key == "earth").s
    assert se == pytest.approx(2.0 ** (-127.5 / 48.0), rel=1e-12) and se < 0.2                  # 2^(-hueco/tolerado)
    assert b.score - a.score > 15.0                                                              # «claramente» por debajo (≈ 23 puntos)
    assert (b.verdict, a.verdict) == (APTO, CONDICIONAL) and "G7" in a.verdict_reason


def test_continuidad_monotona_en_hueco_y_en_fraccion():
    gaps = np.linspace(0.0, 300.0, 121)
    for f, ref in ((0.3, 0.5), (0.62, 0.361), (1.0, 0.742)):
        s = np.array([s_earth(f, ref, g) for g in gaps])
        assert (np.diff(s) <= 1e-15).all() and s[0] <= 1.0 and s.min() > 0.0                    # más hueco ⇒ nunca más s_earth
        sc = [compute_score(link_site(f, ref, g), LANDER, PK).score for g in gaps]
        assert (np.diff(sc) <= 1e-9).all()                                                      # ...ni más score
    fs = np.linspace(0.0, 1.0, 201)
    for gap in (0.0, 30.0, 127.5):
        s = np.array([s_earth(f, 0.5, gap) for f in fs])
        assert (np.diff(s) >= -1e-15).all()                                                     # más fracción ⇒ nunca menos s_earth
        sc = [compute_score(link_site(f, 0.5, gap), LANDER, PK).score for f in fs]
        assert (np.diff(sc) >= -1e-9).all()


def test_continuidad_valores_a_mano_y_horas_por_dia():
    assert s_earth(1.0, 0.5, 0.0) == 1.0 and s_earth(1.0, 0.5, 48.0) == pytest.approx(0.5)      # 1/2 con el hueco tolerado (k = 1)
    assert s_earth(1.0, 0.5, 24.0) == pytest.approx(2 ** -0.5)
    assert s_earth(1.0, 0.5, 96.0, params=replace(PK, link_gap_half_factor=2.0)) == pytest.approx(0.5)   # k = 2: mitad al doble
    # c_día = min(1, 24·f/mín): lander 2 h → f ≥ 1/12 sin penalización; f = 1/24 (1 h/día) → 1/2; base 8 h
    p0 = replace(PK, earth_floor=0.0)                                                             # sin suelo: solo la parte relativa f/f_ref = 1
    assert s_earth(1 / 24, 1 / 24, 0.0, params=p0) == pytest.approx(0.5) and s_earth(1 / 12, 1 / 12, 0.0, params=p0) == pytest.approx(1.0)
    base = DEFAULT_PROFILES["base_isru"]
    assert s_earth(0.25, 0.25, 0.0, profile=base, params=p0) == pytest.approx(0.25 * 24 / 8)      # 6 h/día frente a 8 h
    # sin hueco medido (geometría / periodo entero) o con k = 0: el factor es 1, el comportamiento anterior
    assert subscores(site(link_mode=True), LANDER, PK)["earth"] == subscores(site(), LANDER, P)["earth"]
    assert s_earth(0.6, 0.4, 500.0, params=replace(PK, link_gap_half_factor=0.0)) == 1.0
    custom = DEFAULT_PROFILES["custom"]                                                          # sin hueco tolerado ni mínimo: sin factor
    assert s_earth(0.6, 0.4, 500.0, profile=custom) == 1.0


def test_continuidad_config_k_y_minimos_por_perfil(simulation_cfg):
    cfg = simulation_cfg["score"]
    assert params_from_config(cfg).link_gap_half_factor == 1.0
    assert params_from_config({k: v for k, v in cfg.items() if k != "link"}).link_gap_half_factor == 0.0
    prof = profiles_from_config(cfg)
    assert {k: prof[k].min_link_hours_per_day for k in prof if k != "custom"} == {
        "lander_solar_no_rhu": 2, "lander_with_batteries": 2, "lander_rhu": 2, "rover": 2, "base_isru": 8, "dte_comms": 2}
    assert {k: DEFAULT_PROFILES[k].min_link_hours_per_day for k in prof} == {k: prof[k].min_link_hours_per_day for k in prof}


def test_continuidad_vectorizada_igual_que_escalar():
    from lsi.analysis.site_score import continuity_factor
    g, f = np.array([0.0, 12.0, 127.5, 300.0]), np.array([1.0, 0.5, 0.05, 0.62])
    v = continuity_factor(g, f, 48.0, 1.0, 2.0)
    for i in range(4):
        assert v[i] == pytest.approx(float(continuity_factor(g[i], f[i], 48.0, 1.0, 2.0)), rel=1e-14)


def test_g7_texto_en_lenguaje_claro_y_veredicto_condicional():
    r = compute_score(link_site(0.6206, 0.361, 127.5, longest_earth_h=200.0), LANDER, PK)
    g7 = next(g for g in r.gates if g.id == "G7")
    assert g7.status == GateStatus.FAIL and not g7.hard
    assert "hueco sin comunicaciones de 127.5 h supera lo tolerado por el perfil (48 h)" in g7.reason
    assert r.verdict == CONDICIONAL and "hueco sin comunicaciones de 127.5 h supera lo tolerado por el perfil" in r.verdict_reason
    assert r.status == GateStatus.PASS                      # blanda: no rechaza, vuelve CONDICIONAL
    hard = compute_score(link_site(0.6, 0.4, 127.5), replace(LANDER, max_link_gap_type="hard"), PK)
    assert hard.verdict == NO_APTO and "supera lo tolerado por el perfil" in hard.verdict_reason
    assert any("continuidad ABSOLUTA" in a for a in r.assumptions)


# ---- elección de la mejor fecha (revision-enlace B1) ----------------------------------------------------------
def test_choose_start_prefiere_g7_sobre_empate_temprano():
    sc, nf = [97.41, 97.41, 97.41], [0, 0, 0]
    assert choose_start(sc, nf) == (0, True)                                    # sin G7: la más temprana (comportamiento anterior)
    assert choose_start(sc, nf, [127.5, 127.5, 0.0], 48.0) == (2, True)         # con G7: la que cumple, aunque el score empate
    assert choose_start([90, 97, 80], nf, [10.0, 127.5, 40.0], 48.0) == (0, True)   # entre las que cumplen G7, la de mayor score


def test_choose_start_ninguna_cumple_g7_minimiza_el_hueco():
    assert choose_start([99, 90, 95], [0, 0, 0], [300.0, 100.0, 100.0], 48.0) == (2, True)   # menor hueco; a igual hueco, mayor score
    assert choose_start([99, 90, 95], [0, 0, 0], [336.0, 336.0, 336.0], 48.0) == (0, True)   # todos igual: mayor score


def test_choose_start_las_puertas_duras_mandan_sobre_g7():
    assert choose_start([99, 80], [1, 0], [0.0, 200.0], 48.0) == (1, True)       # la que cumple G7 pero falla una dura NO gana
    assert choose_start([99, 80], [2, 1], [0.0, 200.0], 48.0) == (1, False)      # sin factibles: menos duras fallidas
    assert choose_start([70, 80], [1, 1], [0.0, 200.0], 48.0) == (0, False)      # a igual nº de duras, G7 antes que score
