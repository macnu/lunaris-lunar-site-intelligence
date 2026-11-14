"""T04: modelo de potencia de paneles. Valores esperados de matematica.md §6.7/§6.8 y paneles-y-misiones.md §3.1."""
import dataclasses
from pathlib import Path

import numpy as np
import pytest

from lsi.contracts import (
    AU_KM, BatteryParams, Body, BodyTrack, IamSpec, MountingSpec, MountingType as M, PanelNotCalculableError,
    PanelSpec, PowerParams,
)
from lsi.energy import panels as P

CAT = None


@pytest.fixture(scope="module")
def cat(repo_root):
    return P.load_panel_catalog(repo_root / "config" / "panels.json")


def math_panel(**kw):
    """Panel de los ejemplos de matematica §6.5 (η_ref 0.30, T_ref 25 °C, γ_T −0.0025/K, n 1.526)."""
    d = dict(id="t", name="t", cell_technology="", mounting_default=M.HORIZONTAL, mounting_allowed=(M.HORIZONTAL,),
             eta_bol=0.30, temp_coeff_per_k=-0.0025, temp_valid_range_c=None, ref_temperature_c=25.0,
             alpha_front=0.91, emissivity_front=0.85, emissivity_back=0.80,
             iam=IamSpec("fresnel_1_interface", n_coverglass=1.526), cold_gain_cap=None, confidence={})
    d.update(kw)
    return PanelSpec(**d)


def track(el, az=100.0, dist_km=AU_KM):
    el, az = np.atleast_1d(np.asarray(el, float)), np.atleast_1d(np.asarray(az, float))
    n = max(len(el), len(az))
    return BodyTrack(Body.SUN, np.broadcast_to(az, n).copy(), np.broadcast_to(el, n).copy(),
                     np.full(n, float(dist_km)), np.full(n, 0.27))


def prm(mount, **kw):
    kw.setdefault("t_ambient_k", 100.0)
    kw.setdefault("eta_max", 1.35)
    kw.setdefault("t_min_valid_k", 173.15)
    return PowerParams("t", mount, **kw)


def p_rel(cat, mount, el, az=100.0, dist=AU_KM, panel=None, **kw):
    t = track(el, az, dist)
    s = P.relative_power(np.arange(len(t.el_deg)) * 60.0, t, np.ones(len(t.el_deg)), panel or math_panel(),
                         prm(mount, **kw), cat)
    return s


def test_catalog_loading(cat):
    assert len(cat.panels) == 8 and "_note" not in cat.profiles and "lander_solar_no_rhu" in cat.profiles
    p = P.get_panel(cat, "tj-gaas-lander-body")
    assert p.eta_bol == pytest.approx(0.295) and p.temp_coeff_per_k == pytest.approx(-0.0023)
    assert p.alpha_front == 0.91 and p.mounting_default is M.HORIZONTAL and p.iam.n_coverglass == 1.46
    assert cat.cold_gain_cap_default == 1.15 and cat.solar_constant_w_m2 == 1361.0
    assert cat.profiles["lander_solar_no_rhu"].thresholds["min_useful_power_fraction"].value == 0.25
    with pytest.raises(KeyError, match="tj-gaas"):
        P.get_panel(cat, "nope")


def test_null_is_not_calculable_not_zero(cat):
    """null en un parámetro imprescindible sigue siendo «no calculable», nunca 0 (ya ningún panel del catálogo lo es)."""
    si = P.get_panel(cat, "si-legacy")
    gone = dataclasses.replace(si, alpha_front=None)
    assert P.panel_status(gone) == "no_calculable"
    with pytest.raises(PanelNotCalculableError):
        p_rel(cat, MountingSpec(M.HORIZONTAL), 1.5, panel=gone)
    with pytest.raises(PanelNotCalculableError):
        P.eta_rel(np.array([300.0]), dataclasses.replace(si, temp_coeff_per_k=None), prm(MountingSpec(M.HORIZONTAL)), cat)
    assert not [p.id for p in cat.panels if P.panel_status(p) == "no_calculable"]


ESTIMATED = ["si-legacy", "cigs-thin-film-flex", "perovskite-si-tandem-demo"]   # grupo experimental_sin_datasheet (ROSA pasó a «derivado» de datasheets)


def test_estimated_panels_are_labelled_and_have_ranges(cat):
    for pid in ESTIMATED:
        p = P.get_panel(cat, pid)
        assert P.panel_status(p) == "estimado" and p.uses_estimates and p.estimate_note
        assert set(p.ranges) == {"eta_bol", "temp_coeff_per_k", "alpha_front", "emissivity_front", "emissivity_back"}
        for name, (lo, hi) in p.ranges.items():
            v = getattr(p, name)
            assert min(lo, hi) <= v <= max(lo, hi), (pid, name)          # el valor central está dentro de su rango
        assert p.evidence_group == "experimental_sin_datasheet" and p.evidence_level == "investigacion"
        assert p.confidence["temp_coeff_per_k"] in ("suposicion", "a_verificar")   # γ_T sin fuente primaria espacial: nunca «publicado»
        assert p.confidence["alpha_front"] in ("suposicion", "a_verificar")
    for pid in ("tj-gaas-lander-body", "mj-4j-high-eff", "rosa-flexible-rollout"):
        assert P.panel_status(P.get_panel(cat, pid)) == "calculable" and not P.get_panel(cat, pid).ranges


@pytest.mark.parametrize("pid", ESTIMATED + ["tj-gaas-lander-body", "tj-gaas-vertical-mast", "mj-4j-high-eff", "tj-gaas-rover-body"])
def test_all_panels_calculable_p_rel_in_range_and_band_contains_center(cat, pid):
    p = P.get_panel(cat, pid)
    mnt = MountingSpec(p.mounting_default, azimuth_deg=100.0 if "vertical_fixed" in p.mounting_default.value else None)
    el = np.array([0.0, 1.0, 3.0, 10.0, 30.0, 60.0, 89.0])
    t = track(el)
    pr = prm(mnt)
    s = P.relative_power(np.arange(len(el)) * 60.0, t, np.ones(len(el)), p, pr, cat)
    assert np.all(s.p_rel >= 0) and np.all(s.p_rel <= 1.04) and s.p_rel.max() > 0
    band = P.power_band(s, p, pr, cat)
    if pid in ESTIMATED:
        lo, hi = band
        assert np.all(lo <= s.p_rel + 1e-12) and np.all(s.p_rel <= hi + 1e-12) and np.all(lo >= 0)
        assert np.any(hi > lo + 1e-6 * hi.max())                          # la banda tiene anchura real
    else:
        assert band is None


def test_band_matches_brute_force_corners(cat):
    """La banda por 4 esquinas coincide con recalcular relative_power en las 32 esquinas de los 5 rangos."""
    import itertools
    p = P.get_panel(cat, "cigs-thin-film-flex")
    mnt = MountingSpec(M.TWO_AXIS)
    el = np.array([5.0, 40.0, 85.0])
    pr, t, f = prm(mnt), track(el), np.ones(3)
    et = np.arange(3) * 60.0
    s = P.relative_power(et, t, f, p, pr, cat)
    lo, hi = P.power_band(s, p, pr, cat)
    names = list(p.ranges)
    vals = []
    for c in itertools.product(*(p.ranges[n] for n in names)):
        q = dataclasses.replace(p, **dict(zip(names, c)))
        vals.append(P.relative_power(et, t, f, q, pr, cat).p_rel)
    np.testing.assert_allclose(lo, np.minimum(np.min(vals, axis=0), s.p_rel), rtol=1e-9)
    np.testing.assert_allclose(hi, np.maximum(np.max(vals, axis=0), s.p_rel), rtol=1e-9)


@pytest.mark.parametrize("h,ratio", [(1.0, 57.3), (1.5, 38.2), (3.0, 19.1)])
def test_vertical_vs_horizontal_geometry(h, ratio):          # paneles-y-misiones §3.1 (cos pura)
    az = np.array([100.0])
    v = P.incidence_cos(az, np.array([h]), MountingSpec(M.VERTICAL_AZ_TRACKING))[0]
    hz = P.incidence_cos(az, np.array([h]), MountingSpec(M.HORIZONTAL))[0]
    assert hz == pytest.approx(np.sin(np.radians(h))) and v / hz == pytest.approx(ratio, abs=0.1)


def test_math_6_7a_geometry_chain(cat):
    cos = lambda m, **k: P.incidence_cos(np.array([100.0]), np.array([1.5]), m, **k)[0]
    assert cos(MountingSpec(M.HORIZONTAL)) == pytest.approx(0.026177, abs=1e-6)
    assert cos(MountingSpec(M.VERTICAL_AZ_TRACKING)) == pytest.approx(0.999657, abs=1e-6)
    assert cos(MountingSpec(M.VERTICAL_FIXED, azimuth_deg=40.0)) == pytest.approx(0.499829, abs=1e-6)
    assert cos(MountingSpec(M.TILTED, tilt_deg=45.0, azimuth_deg=100.0)) == pytest.approx(0.72537, abs=1e-5)
    assert cos(MountingSpec(M.TWO_AXIS)) == 1.0
    assert cos(MountingSpec(M.VERTICAL_FIXED, azimuth_deg=280.0)) == pytest.approx(-0.999657, abs=1e-6)
    assert cos(MountingSpec(M.TERRAIN_NORMAL), ground_normal_enu=(0, 0, 1)) == pytest.approx(0.026177, abs=1e-6)
    spec = IamSpec("fresnel_1_interface", n_coverglass=1.526)
    for th, v in [(0, 1), (30, .9984), (60, .9476), (80, .6357), (85, .4019), (88, .1882), (89.9, .0105), (90, 0)]:
        assert P.iam(np.array([float(th)]), spec)[0] == pytest.approx(v, abs=2e-4)
    assert P.iam(np.array([88.5]), spec)[0] == pytest.approx(0.1451, abs=1e-4)
    assert P.iam(np.array([45.0]), IamSpec("cosine_only"))[0] == 1.0


def test_math_6_7a_p_rel_pure_geometry(cat):
    """T=25 °C → η_rel=1: se fija T_ref a la temperatura calculada anulando γ_T (coef. 0), d = 1 UA."""
    pn = math_panel(temp_coeff_per_k=0.0)
    f = lambda m, **k: p_rel(cat, m, 1.5, panel=pn, **k).p_rel[0]
    assert f(MountingSpec(M.HORIZONTAL)) == pytest.approx(0.003798, abs=2e-6)
    assert f(MountingSpec(M.VERTICAL_AZ_TRACKING)) == pytest.approx(0.99966, abs=1e-5)
    assert f(MountingSpec(M.VERTICAL_FIXED, azimuth_deg=40.0)) == pytest.approx(0.47362, abs=1e-5)
    assert f(MountingSpec(M.TWO_AXIS)) == pytest.approx(1.0, abs=1e-9)
    assert f(MountingSpec(M.VERTICAL_FIXED, azimuth_deg=280.0)) == 0.0


def test_math_6_7b_full_chain(cat):
    d = 147_553_142.0
    s = lambda m: p_rel(cat, m, 1.38330, dist=d, **{})
    trk = s(MountingSpec(M.VERTICAL_AZ_TRACKING))
    assert trk.dist_factor[0] == pytest.approx(1.027907, abs=1e-6)
    assert trk.t_panel_k[0] - 273.15 == pytest.approx(36.71, abs=0.05)
    assert trk.eta_rel[0] == pytest.approx(0.97073, abs=2e-4) and trk.p_rel[0] == pytest.approx(0.99753, abs=2e-4)
    assert s(MountingSpec(M.TWO_AXIS)).p_rel[0] == pytest.approx(0.99776, abs=2e-4)
    hz = s(MountingSpec(M.HORIZONTAL))
    assert hz.cos_inc[0] == pytest.approx(0.024141, abs=1e-6) and hz.theta_deg[0] == pytest.approx(88.617, abs=1e-3)
    assert hz.iam[0] == pytest.approx(0.13468, abs=2e-4) and hz.t_clamped[0]
    assert hz.eta_rel[0] == pytest.approx(1.3125) and hz.p_rel[0] == pytest.approx(0.004386, abs=2e-5)
    vf = s(MountingSpec(M.VERTICAL_FIXED, azimuth_deg=40.0))
    assert vf.t_panel_k[0] - 273.15 == pytest.approx(-15.30, abs=0.1) and vf.p_rel[0] == pytest.approx(0.53593, abs=5e-4)


def test_cold_cap_precedence(cat):
    pn = math_panel()
    e = lambda **k: P.eta_rel(np.array([100.0]), pn, prm(MountingSpec(M.HORIZONTAL), **k), cat)[0][0]
    assert e() == pytest.approx(1.3125)                        # sin tope activo (γ·ΔT)
    assert e(eta_max=1.2) == pytest.approx(1.2)                # eta_max de params
    assert e(eta_max=None) == pytest.approx(1.15)              # catálogo (panel sin tope)
    assert P.eta_rel(np.array([100.0]), math_panel(cold_gain_cap=1.1), prm(MountingSpec(M.HORIZONTAL), eta_max=None), cat)[0][0] == pytest.approx(1.1)


def test_degradation_dust_shadow_and_no_clip(cat):
    pn = math_panel(temp_coeff_per_k=0.0)
    base = p_rel(cat, MountingSpec(M.TWO_AXIS), 1.5, panel=pn).p_rel[0]
    k = p_rel(cat, MountingSpec(M.TWO_AXIS), 1.5, panel=pn, degradation=0.1, dust_loss=0.2, f_shadow=0.5).p_rel[0]
    assert k == pytest.approx(base * 0.9 * 0.8 * 0.5)
    assert p_rel(cat, MountingSpec(M.TWO_AXIS), 1.5, panel=pn, dist=AU_KM * 0.98).p_rel[0] > 1.0   # perihelio no se recorta


def test_energy_synthetic_6_7c(cat):
    """f=1 durante 10 h/día, e=1.5°, vertical con seguimiento, 25 °C (γ_T=0), 1 UA, IAM(1.5°)≈1."""
    pn = math_panel(temp_coeff_per_k=0.0)
    t = np.arange(0, 86400.0 + 60, 60.0)
    trk = track(np.full_like(t, 1.5))
    f = (t < 10 * 3600).astype(float)
    s = P.relative_power(t, trk, f, pn, prm(MountingSpec(M.VERTICAL_AZ_TRACKING)), cat)
    out = P.summarize_power(s, pn, 0.25, cat, day_origin_et=0.0)
    assert out.e_inc_wh_m2 == pytest.approx(13605, rel=2e-3)
    assert out.e_rel == pytest.approx(0.41652, rel=3e-3) and out.pct_of_max == pytest.approx(41.65, abs=0.15)
    assert out.e_el_wh_m2 == pytest.approx(4081, rel=3e-3)
    assert out.hours_above_useful == pytest.approx(10.0, abs=0.05) and out.peak_p_rel == pytest.approx(0.99966, abs=1e-4)
    assert len(out.daily) == 1 and out.daily[0].e_rel == pytest.approx(out.e_rel)


def test_daily_split_two_days(cat):
    pn = math_panel(temp_coeff_per_k=0.0)
    t = np.arange(0, 2 * 86400.0 + 1, 600.0)
    s = P.relative_power(t, track(np.full_like(t, 1.5)), (t % 86400 < 43200).astype(float), pn,
                         prm(MountingSpec(M.TWO_AXIS)), cat)
    out = P.summarize_power(s, pn, 0.25, cat, day_origin_et=0.0)
    assert len(out.daily) == 2 and all(d.e_rel == pytest.approx(0.5, abs=0.01) for d in out.daily)


def test_battery_6_8():
    et = np.arange(25) * 3600.0
    p = np.where(np.arange(25) < 10, 0.8, 0.0)
    bp = BatteryParams(capacity_wh=100.0, p_nominal_w=100.0, load_w=20.0, soc0=0.5)
    r = P.simulate_battery(et, p, bp)
    assert r.soc[1] == pytest.approx(1.0) and r.soc[10] == pytest.approx(1.0)
    np.testing.assert_allclose(r.soc[11:15] * 100, [78.9, 57.9, 36.8, 20.0], atol=0.06)
    assert np.all(r.soc[14:] == pytest.approx(0.2)) and r.min_soc == pytest.approx(0.2)
    assert r.unserved_wh == pytest.approx(204.0, abs=0.1)
    r3 = P.simulate_battery(et, p, BatteryParams(300.0, 100.0, 20.0, soc0=0.5))
    assert r3.soc[-1] == pytest.approx(0.2) and r3.unserved_wh == pytest.approx(52.0, abs=0.1)


def test_integration_nodes():
    class W:  # solo atributos usados
        def __init__(s, a, b): s.start_et, s.end_et = a, b
    class WS:
        def __init__(s, w): s.windows = w
    n = P.integration_nodes(np.array([0.0, 600.0, 1200.0]), [WS([W(250.0, 900.0)]), WS([])])
    np.testing.assert_array_equal(n, [0.0, 250.0, 600.0, 900.0, 1200.0])


def test_cold_extrapolation_uses_panel_valid_range_and_needs_power(cat):
    """M3: el indicador de extrapolación sigue el rango de validez del coeficiente térmico del panel (panels.json), no 173 K
    fijo, y no salta sin potencia. Rango [15, 125] °C → 209 K (−64 °C) con Sol SÍ es extrapolación; con rango [−100, 100]
    no; sin Sol (p = 0) nunca; sin rango declarado vale el suelo t_min_valid_k (173,15 K)."""
    sun = track(np.array([40.0, 40.0]))
    f = np.array([1.0, 0.0])                                    # Sol / noche
    mnt = MountingSpec(M.HORIZONTAL)
    # horizontal a 40°: G ≈ 1361·sin40 → T bastante por encima de −64 °C; forzamos frío con un panel muy poco absorbente
    cold = dict(eta_bol=0.05, alpha_front=0.35, emissivity_front=0.9, emissivity_back=0.9)
    pr = prm(mnt, t_ambient_k=100.0)
    s_lo = P.relative_power(np.array([0.0, 60.0]), sun, f, math_panel(temp_valid_range_c=(15.0, 125.0), **cold), pr, cat)
    t_c = s_lo.t_panel_k[0] - 273.15
    assert t_c < 15.0 and t_c > -100.0                          # entre el rango del coeficiente y el suelo antiguo
    assert s_lo.t_clamped.tolist() == [True, False]             # con potencia: sí; de noche (p=0): no
    s_wide = P.relative_power(np.array([0.0, 60.0]), sun, f, math_panel(temp_valid_range_c=(-100.0, 100.0), **cold), pr, cat)
    assert not s_wide.t_clamped.any()
    s_none = P.relative_power(np.array([0.0, 60.0]), sun, f, math_panel(temp_valid_range_c=None, **cold), pr, cat)
    assert not s_none.t_clamped.any()                           # T > 173,15 K: sin rango declarado, sin aviso
    hot = P.eta_rel(np.array([420.0]), math_panel(temp_valid_range_c=(15.0, 125.0)), pr, cat)[1]
    assert hot.tolist() == [True]                               # por arriba del rango también es extrapolación


def test_evidence_fields_groups_and_areal_power(cat):
    """datos-paneles.md: cada panel lleva grupo/nivel de evidencia; W/m² AM0 = η·1361; los respaldados tienen η y γ_T con fuente."""
    import json
    raw = {p["id"]: p for p in json.loads((Path(__file__).resolve().parents[1] / "config" / "panels.json").read_text(encoding="utf-8"))["panels"]}
    g = P.split_by_evidence_group(cat)
    assert {p.id for p in g["experimental_sin_datasheet"]} == set(ESTIMATED)           # siempre visibles, separados
    assert len(g["respaldado"]) + len(g["experimental_sin_datasheet"]) == len(cat.panels) == 8
    for p in cat.panels:
        assert p.evidence_level in P.EVIDENCE_LEVELS and p.evidence_summary
        assert p.areal_power_w_m2_am0 == pytest.approx(p.eta_bol * 1361.0)
        assert raw[p.id]["areal_power_w_m2_am0"]["value"] == pytest.approx(p.areal_power_w_m2_am0, abs=0.05)
        assert (p.evidence_group == "experimental_sin_datasheet") == p.uses_estimates
        if p.evidence_group == "respaldado":
            assert p.confidence["eta_bol"] in ("publicado", "estimado") and p.confidence["temp_coeff_per_k"] in ("publicado", "estimado")
    assert P.get_panel(cat, "tj-gaas-lander-body").areal_power_w_m2_am0 == pytest.approx(401.5, abs=0.1)
    assert P.get_panel(cat, "tj-gaas-lander-body").evidence_level == "datasheet"


def test_datasheet_values_read_from_primary_sources(cat):
    """Valores leídos en los datasheets (p.1-2 de cada PDF): Z4J+ 31.3 % y Pmp' -0.1117 mW/cm²/K sobre 42.37 mW/cm² → -0.264 %/K."""
    p = P.get_panel(cat, "mj-4j-high-eff")
    assert p.eta_bol == pytest.approx(0.313) and p.temp_coeff_per_k == pytest.approx(-0.1117 / (3.31 * 12.8), abs=2e-5)
    si = P.get_panel(cat, "si-legacy")
    assert si.eta_bol == pytest.approx(0.174) and si.ref_temperature_c == 25.0       # Sharp: 17.4 % a AM0 136.7 mW/cm², 25 °C
    assert P.get_panel(cat, "perovskite-si-tandem-demo").eta_bol == pytest.approx(0.192)   # Joule 2020, AM0 1350 W/m²


# --- honestidad óptica: el JSON declara el modelo que el código usa, y la banda rasante -------------------------------------
def test_iam_model_declared_in_json_is_the_one_used(cat):
    assert all(p.iam_model == p.iam.model == "fresnel_1_interface" for p in cat.panels)   # ya no 'cosine_only' declarado con Fresnel forzado
    cos = dataclasses.replace(P.get_panel(cat, "tj-gaas-vertical-mast"), iam=IamSpec("cosine_only"))
    th = np.array([85.0])
    assert P.iam(th, cos.iam)[0] == 1.0 and P.iam(th, P.get_panel(cat, "tj-gaas-vertical-mast").iam)[0] < 0.7


def test_grazing_band_contains_center_and_is_wide_at_grazing_incidence(cat):
    p = P.get_panel(cat, "tj-gaas-lander-body")
    el = np.array([1.0, 3.0, 30.0, 85.0])
    pr, t = prm(MountingSpec(M.HORIZONTAL)), track(el)
    s = P.relative_power(np.arange(4) * 60.0, t, np.ones(4), p, pr, cat)
    d = P.power_band_detail(s, p, pr, cat)
    lo, hi = d["combined"]
    assert np.all(lo <= s.p_rel + 1e-12) and np.all(s.p_rel <= hi + 1e-12)
    assert d["params"] is None and d["optics"] is not None and d["thermal"] is not None
    # solo-coseno (IAM=1) es cota superior: a h=1° (θ=89°) la banda llega al menos hasta cos(89°)·η_rel; a h=85° casi no se abre
    assert hi[0] > 3 * s.p_rel[0] and (hi[3] - lo[3]) / s.p_rel[3] < 0.2
    # la combinada contiene a cada componente (envolvente conjunta, no suma de anchos)
    for k in ("optics", "thermal"):
        assert np.all(d["combined"][0] <= d[k][0] + 1e-12) and np.all(d[k][1] <= d["combined"][1] + 1e-12)
    assert np.all((hi - lo) <= (d["optics"][1] - d["optics"][0]) + (d["thermal"][1] - d["thermal"][0]) + 1e-12)   # sin doble conteo
    assert P.power_band(s, p, pr, cat) is None                     # histórico: panel sin rangos → None
    np.testing.assert_allclose(P.power_band(s, p, pr, cat, grazing=True)[1], d["optics"][1])   # solo IAM, sin T_amb


def test_grazing_band_of_estimated_panel_includes_parameter_band(cat):
    p = P.get_panel(cat, "cigs-thin-film-flex")
    pr, t = prm(MountingSpec(M.TWO_AXIS)), track(np.array([5.0, 40.0]))
    s = P.relative_power(np.arange(2) * 60.0, t, np.ones(2), p, pr, cat)
    d = P.power_band_detail(s, p, pr, cat)
    plo, phi = P.power_band(s, p, pr, cat)
    np.testing.assert_allclose(d["params"][0], plo)
    assert np.all(d["combined"][0] <= plo + 1e-12) and np.all(phi <= d["combined"][1] + 1e-12)
