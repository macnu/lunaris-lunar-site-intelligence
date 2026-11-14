"""Pipeline (T16): extremo a extremo con SPICE y DEM reales (3 sitios), esfera lisa, snap_to_dem, potencia, score."""
import time
from pathlib import Path

import numpy as np
import pytest

from lsi import pipeline as P
from lsi.astronomy.coordinates import stereo_inverse
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, AnalysisRequest, BatteryParams, DateOutOfRangeError, GateStatus, HorizonMode, MountingSpec,
    MountingType, ObserverNearEdgeError, WarningCode,
)

pytestmark = pytest.mark.needs_spice
ROOT = Path(__file__).resolve().parents[1]
START, END30, END365 = "2026-12-01T00:00:00", "2026-12-31T00:00:00", "2027-12-01T00:00:00"
VAT = MountingSpec(MountingType.VERTICAL_AZ_TRACKING)
# observadores por defecto de los 3 recortes (config/simulation.json: dem_default_observers)
SITES = {"Site04": (-89.766811, 188.130102), "Site11": (-88.683418, 292.0679), "Site23": (-85.994785, 359.764216)}


@pytest.fixture(scope="module")
def ctx():
    return P.build_context(ROOT)


def codes(res):
    return {w.code for w in res.warnings}


# ---------------------------------------------------------------------------------------- esfera lisa y errores
def test_apollo11_smooth_sphere_partial_score_with_range_and_power(ctx):
    req = AnalysisRequest(0.6741, 23.473, START, END30, site_id="apollo11", panel_id="tj-gaas-lander-body",
                          mounting=VAT, with_uncertainty=True)
    r = P.run_analysis(ctx, req)   # sin error, sin DEM
    assert r.observer.mode is HorizonMode.SMOOTH_SPHERE and r.dem_meta is None and r.slope is None
    assert WarningCode.NO_DEM_SMOOTH_SPHERE in codes(r) and WarningCode.NO_TERRAIN_DATA_SCORE in codes(r)
    assert WarningCode.DEM_EFFECTIVE_RESOLUTION not in codes(r)   # solo en modo DEM
    s = r.score
    assert s.partial and not s.terrain_data and s.missing_keys == ("terrain",)
    # ventana de 14 d dentro del día lunar: Sol 100 %, noche 0 h, Tierra = esfera → S = 100 = score_max (terreno = 1)
    assert s.score_min < s.score <= s.score_max
    assert next(g for g in s.gates if g.id == "G3").status is GateStatus.NO_DATA
    assert s.confidence is not None and s.confidence.level.value == "baja"   # sin soporte observacional
    assert 0.0 < r.power_summary.pct_of_max <= 104.0
    assert r.f_earth_ref == pytest.approx(r.metrics.earth_fraction)   # en esfera lisa la referencia es la propia
    assert not any("29,5 d" in a for a in s.assumptions)   # 30 d ≥ 29,53 d: no se avisa


def test_short_period_and_always_shown_warnings(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, "2026-12-08T00:00:00"))
    assert any("29,5 d" in a for a in r.score.assumptions)
    assert {WarningCode.GEOMETRIC_ONLY, WarningCode.ECLIPSES_NOT_MODELED} <= codes(r)


@pytest.mark.parametrize("a,b", [("1850-01-01T00:00:00", "1850-02-01T00:00:00"), (START, "2060-01-01T00:00:00")])
def test_dates_out_of_range_raise_contract_error(ctx, a, b):
    with pytest.raises(DateOutOfRangeError):
        P.run_analysis(ctx, AnalysisRequest(0.0, 0.0, a, b))


def test_empty_period_is_invalid(ctx):
    with pytest.raises(P.InvalidParameterError):
        P.run_analysis(ctx, AnalysisRequest(0.0, 0.0, START, START))


def test_score_weights_override_matches_hand_value(ctx):
    w = (("sun", 1.0), ("night", 0.0), ("earth", 0.0), ("terrain", 0.0))
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, END30, score_weights=w, score_profile_id="custom"))
    # sin terreno y con solo peso en 'sun': S = 100·s^(1−λ)·q^λ con s = clip((f−0.2)/0.7), q = f y λ = 0,25 (config)
    f = r.metrics.solar_fraction
    assert r.score.score == pytest.approx(100 * ((f - 0.20) / 0.70) ** 0.75 * f ** 0.25, abs=1e-6)
    with pytest.raises(ValueError):
        P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, END30, score_weights=(("sol", 1.0),)))


def test_rover_inherits_lander_landing_slope(ctx):
    assert ctx.panels.profiles["rover"].thresholds["max_landing_slope_deg"].value is None
    assert P._mission(ctx, "rover").thresholds["max_landing_slope_deg"].value == 10   # diseño del lander (panels.json)
    assert P._mission(ctx, "lander_solar_no_rhu").thresholds["max_landing_slope_deg"].value == 10
    assert P._mission(ctx, "base_isru").thresholds["max_landing_slope_deg"].value == 5


def test_power_for_several_panels_and_battery(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, END30))
    assert r.power is None
    bat = BatteryParams(capacity_wh=700.0, p_nominal_w=100.0, load_w=20.0)
    runs = P.run_power(ctx, r, [("tj-gaas-lander-body", VAT), ("tj-gaas-lander-body", None),
                                ("rosa-flexible-rollout", None), ("tj-gaas-vertical-mast", None)], battery=bat)
    ok = [x for x in runs if x.error is None]
    assert [x.panel_id for x in ok] == ["tj-gaas-lander-body", "tj-gaas-lander-body", "rosa-flexible-rollout", "tj-gaas-vertical-mast"]
    assert runs[2].error is None and runs[2].panel_id == "rosa-flexible-rollout"   # antes no calculable; ahora estimado (panels.json)
    assert all(0.0 < x.summary.pct_of_max <= 104.0 for x in ok)
    assert ok[0].summary.pct_of_max > ok[1].summary.pct_of_max   # vertical con seguimiento ≫ horizontal en la Luna
    assert ok[0].battery is not None and 0.0 <= ok[0].battery.min_soc <= 1.0
    assert WarningCode.POWER_IS_ESTIMATE in {w.code for w in ok[0].warnings}
    assert len(ok[0].series.et) >= len(r.sky.et)   # nodos = rejilla + instantes de evento


def test_daily_table_uses_real_utc_days(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, "2026-12-01T06:00:00", "2026-12-04T12:00:00"))
    d = r.daily
    assert [x["day_utc"] for x in d] == ["2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]
    assert d[0]["end_et"] - d[0]["start_et"] == pytest.approx(18 * 3600.0, abs=1)   # primer día parcial
    assert d[-1]["end_et"] - d[-1]["start_et"] == pytest.approx(12 * 3600.0, abs=1)
    assert sum(x["sun_hours"] for x in d) == pytest.approx(r.metrics.solar_fraction * r.metrics.period_s / 3600.0, abs=1e-6)
    assert all(0.0 <= x["mean_illumination"] <= 1.0 for x in d)


def test_comparison_keys(ctx):
    a = AnalysisRequest(0.6741, 23.473, START, END30, site_id="apollo11")
    out = P.run_comparison(ctx, [a, a, AnalysisRequest(-3.0124, -23.4216, START, END30)])
    assert list(out) == ["apollo11", "apollo11#2", "-3.0124,-23.4216"]


# ---------------------------------------------------------------------------------------- 3 sitios con DEM
@pytest.mark.needs_dem
@pytest.mark.parametrize("key", list(SITES))
def test_three_dem_sites_30_days(ctx, key):
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    lat, lon = SITES[key]
    req = AnalysisRequest(lat, lon, START, END30, panel_id="tj-gaas-lander-body", mounting=VAT, with_uncertainty=True)
    t0 = time.perf_counter()
    r = P.run_analysis(ctx, req)
    dt = time.perf_counter() - t0
    assert r.observer.mode is HorizonMode.DEM and r.observer.dem_key == key and r.observer.snap_distance_km is None
    assert r.horizon.far_sha256 is not None and r.dem_meta.sha256   # campo lejano LOLA 80 m en uso por defecto
    assert set(ALWAYS_SHOWN_WARNINGS) <= codes(r)
    m = r.metrics
    assert 0.0 <= m.solar_fraction <= 1.0 and 0.0 <= m.earth_fraction <= 1.0
    for k in ("solar_fraction", "earth_fraction", "longest_sun_window_s", "max_darkness_s"):
        rg = r.uncertainty.ranges[k]
        assert rg.lo <= rg.nominal <= rg.hi
    s = r.score
    assert 0.0 <= s.score_min <= s.score <= s.score_max <= 100.0 and not s.partial and s.terrain_data
    assert s.mission_days == 14.0 and s.verdict in ("APTO", "CONDICIONAL", "NO APTO") and s.verdict_reason   # DEM: nunca provisional
    assert not s.verdict_provisional and s.n_starts == 17 and s.window_start_utc < s.window_end_utc
    assert r.window_metrics.period_s == pytest.approx(14 * 86400.0, abs=1.0)
    assert [(g.id, g.status) for g in s.gates][0][0] == "G0"
    assert r.slope is not None and r.dem_confidence is not None and s.confidence is not None
    assert 0.0 < r.power_summary.pct_of_max <= 104.0
    assert len(r.daily) == 30 and r.daily[0]["day_utc"] == "2026-12-01"
    assert [c.body.value for c in r.countdowns] == ["SUN", "EARTH"]
    assert dt < ctx.cfg["performance"]["budget_30d_10min_s"] + 3.0   # + horizonte en frío (≤ ~2 s)


@pytest.mark.needs_dem
@pytest.mark.slow
@pytest.mark.parametrize("key", list(SITES))
def test_three_dem_sites_one_year_within_budget(ctx, key):
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    lat, lon = SITES[key]
    t0 = time.perf_counter()
    r = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END365, panel_id="tj-gaas-lander-body", mounting=VAT))
    dt = time.perf_counter() - t0
    assert dt < ctx.cfg["performance"]["budget_1y_10min_s"]
    assert len(r.daily) == 365 and abs(r.metrics.period_s - 365 * 86400.0) < 2.0
    assert r.score.score_min <= r.score.score <= r.score.score_max
    assert r.score.n_starts == 365 - 14 and r.score.mission_days == 14.0     # 351 fechas de inicio con ventana completa


# ---------------------------------------------------------------------------------------- snap_to_dem
@pytest.mark.needs_dem
@pytest.mark.parametrize("fid,lat,lon,key,dmin,dmax", [
    (5450, -89.67, 129.78, "Site04", 0.3, 1.5),       # Shackleton: centro ~0.8 km fuera del recorte (solo el borde)
    (1439, -88.4849, 271.6553, "Site11", 4.0, 7.0),   # de Gerlache: centro a ~5.9 km
])
def test_gazetteer_feature_outside_dem_snaps_to_nearest_dem_point(ctx, fid, lat, lon, key, dmin, dmax):
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    # prefer="nearest": comportamiento anterior (el defecto del buscador es ahora "best": ver los tests de snap al final)
    r = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, gazetteer_id=fid, snap_prefer="nearest"))
    o = r.observer
    assert o.mode is HorizonMode.DEM and o.dem_key == key and o.ground_z_m is not None and o.snap_kind == "nearest"
    assert dmin < o.snap_distance_km < dmax and o.snapped_from == (lat, pytest.approx(lon))
    assert "snap_to_dem" in o.label and f"{o.snap_distance_km:.2f} km" in o.label
    w = next(w for w in r.warnings if w.context and w.context.startswith("snap_to_dem"))
    assert w.code is WarningCode.CURATED_COORDS_OUTSIDE_DEM and "km" in w.text_es
    assert WarningCode.GAZETTEER_COORDS_APPROX in codes(r)
    x0, y0, x1, y1 = ctx.dem_refs[key].bounds_xy_m   # el punto ajustado queda dentro del recorte con margen
    assert x0 + 100 <= o.x_m <= x1 - 100 and y0 + 100 <= o.y_m <= y1 - 100
    r2 = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, gazetteer_id=fid, snap_to_dem=False))
    assert r2.observer.mode is HorizonMode.FAR_FIELD and r2.observer.snap_distance_km is None   # desactivable: sin snap, el 80 m


@pytest.mark.needs_dem
def test_feature_far_from_recortes_uses_far_field_and_custom_point_is_not_snapped(ctx):
    far = P.resolve_observer(ctx, -84.9998, 11.4031, 2.0, gazetteer_id=3603)   # cráter Malapert, ~26 km del recorte, dentro del DEM de 80 m
    assert far[0].mode is HorizonMode.FAR_FIELD and far[1][0].code is WarningCode.FAR_FIELD_80M and far[0].ground_z_m is not None
    free = P.resolve_observer(ctx, -89.67, 129.78, 2.0)   # sin gazetteer/sitio: el usuario eligió ese punto
    assert free[0].mode is HorizonMode.FAR_FIELD and free[0].snap_distance_km is None
    assert P.snap_candidate(ctx, 0.6741, 23.473) is None   # Apolo 11: ningún DEM razonable
    assert P.snap_candidate(ctx, 0.6741, 23.473, prefer="best") is None


@pytest.mark.needs_dem
def test_far_field_mode_only_inside_polar_domain(ctx):
    inside = P.resolve_observer(ctx, -84.0, 30.0, 2.0)[0]
    assert inside.mode is HorizonMode.FAR_FIELD
    for lat in (-79.5, -60.0, 0.6741):   # fuera del DEM polar (> 80°S): esfera lisa
        o, w = P.resolve_observer(ctx, lat, 30.0, 2.0)
        assert o.mode is HorizonMode.SMOOTH_SPHERE and w[0].code is WarningCode.NO_DEM_SMOOTH_SPHERE
    assert P.resolve_observer(ctx, -84.0, 30.0, 2.0, force_smooth_sphere=True)[0].mode is HorizonMode.SMOOTH_SPHERE
    assert P.resolve_observer(ctx, *SITES["Site23"], 2.0)[0].mode is HorizonMode.DEM          # dentro del recorte manda el 5 m
    assert P.resolve_observer(ctx, *SITES["Site23"], 2.0, force_far_field=True)[0].mode is HorizonMode.FAR_FIELD


@pytest.mark.needs_dem
def test_far_field_analysis_partial_score_low_confidence_and_measured_warning(ctx):
    req = AnalysisRequest(-84.0, 30.0, START, END30)
    r = P.run_analysis(ctx, req)
    assert r.observer.mode is HorizonMode.FAR_FIELD and r.horizon.mode is HorizonMode.FAR_FIELD and r.horizon.far_sha256
    assert r.horizon.h_lb_deg.max() > 5.0 and r.slope is None and r.dem_meta is None      # hay relieve, pero no pendiente de aterrizaje
    s = r.score
    assert s.partial and not s.terrain_data and s.confidence.level.value == "baja"
    txt = " ".join(w.text_es for w in r.warnings) + " ".join(s.assumptions) + s.verdict_reason + " ".join(g.reason for g in s.gates)
    assert "Resolución 80 m: horizonte aproximado; no sirve para decidir un aterrizaje fino" in txt
    assert "RMS" in txt and f"{P.FAR_FIELD_VALIDATION['horizon_rms_deg']:.2f}°" in txt         # el error MEDIDO, no uno genérico
    assert "esfera lisa)" not in " ".join(g.reason for g in s.gates) and "cota optimista sobre esfera lisa" not in s.verdict_reason
    assert {WarningCode.FAR_FIELD_80M, WarningCode.NO_TERRAIN_DATA_SCORE} <= codes(r) and WarningCode.NO_DEM_SMOOTH_SPHERE not in codes(r)
    r2 = P.run_analysis(ctx, req)   # determinismo
    assert np.array_equal(r.horizon.h_lb_deg, r2.horizon.h_lb_deg) and r.metrics.solar_fraction == r2.metrics.solar_fraction


@pytest.mark.needs_dem
@pytest.mark.parametrize("key", list(SITES))
def test_far_field_horizon_matches_5m_within_measured_tolerance(ctx, key):
    lat, lon = SITES[key]
    d = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30))
    f = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, force_far_field=True))
    assert d.horizon.mode is HorizonMode.DEM and f.horizon.mode is HorizonMode.FAR_FIELD
    e = f.horizon.h_lb_deg - d.horizon.h_lb_deg
    assert np.sqrt(np.mean(e ** 2)) < 2.0 and np.abs(e).max() < 8.0                           # holgura sobre el RMS 0,68° / máx. 5,8° medidos
    assert abs(f.metrics.solar_fraction - d.metrics.solar_fraction) < 0.25   # el punto por defecto de Site23 está en una cresta: 0,19 (peor caso medido)


@pytest.mark.needs_dem
def test_curated_site_outside_its_recorte_uses_its_own_dem(ctx):
    o, w = P.resolve_observer(ctx, -89.67, 129.78, 2.0, site_id="site04")   # coordenadas curadas fuera del recorte
    assert o.mode is HorizonMode.DEM and o.dem_key == "Site04" and o.snap_distance_km > 0 and o.site_id == "site04"
    assert w[0].code is WarningCode.CURATED_COORDS_OUTSIDE_DEM
    assert "Site04" in o.label


@pytest.mark.needs_dem
def test_near_edge_without_snap_raises(ctx):
    x0, y0, x1, y1 = ctx.dem_refs["Site23"].bounds_xy_m
    lat, lon = (float(v) for v in stereo_inverse(np.float64(x0 + 5.0), np.float64((y0 + y1) / 2)))   # 5 m del borde
    with pytest.raises(ObserverNearEdgeError):
        P.resolve_observer(ctx, lat, lon, 2.0)


@pytest.mark.needs_dem
def test_interior_point_is_dem_mode_without_snap(ctx):
    o, w = P.resolve_observer(ctx, *SITES["Site23"], 2.0)
    assert o.mode is HorizonMode.DEM and o.snap_distance_km is None and w == ()


# ---------------------------------------------------------------------------------------- ventana de misión y estados
APOLLO = (0.6741, 23.473)
SUNRISE = "2026-12-15T00:00:00"      # amanecer en Apolo 11: el día lunar (14,77 d) dura hasta ~12-29 18 h


def test_apollo11_30d_window_best_start_and_sin_datos(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, site_id="apollo11", with_uncertainty=True))
    s = r.score
    assert s.mission_days == 14.0 and s.verdict == "SIN DATOS" and not s.verdict_provisional   # G2/G3 no evaluables
    assert s.best_start_utc == SUNRISE and s.best_window_end_utc == "2026-12-29T00:00:00"
    assert (s.window_start_utc, s.window_end_utc) == (s.best_start_utc, s.best_window_end_utc)
    wm = r.window_metrics
    assert wm.solar_fraction == pytest.approx(1.0) and wm.max_darkness_s == 0.0      # día lunar entero dentro de la ventana
    assert r.metrics.max_darkness_s / 3600.0 > 300.0                                  # el periodo sí contiene la noche (327 h)
    assert s.n_starts == 17 and 0.0 < s.feasible_start_fraction <= 3 / 17            # solo caben al amanecer (día 14,77 d)
    tw = s.top_windows
    assert 1 <= len(tw) <= 3 and tw[0].start_utc == s.best_start_utc and tw[0].score == pytest.approx(s.score)
    assert all(b.start_utc >= a.end_utc for a, b in zip(tw, tw[1:]))                  # no solapadas
    ms = s.max_sustainable_days                                                       # G4 = 12 h: noche letal 12 h tras el ocaso
    assert ms.limit_h == 12.0 and 14.0 < ms.best_days < 16.0 and ms.best_start_utc == SUNRISE and ms.censored_fraction == 0.0
    assert next(g for g in s.gates if g.id == "G0").status is GateStatus.PASS
    assert r.score_inputs.sun_at_start and len(r.score_scenarios) == len(r.uncertainty.scenarios)


def test_apollo11_window_equals_direct_run_on_that_window(ctx):
    """La ventana elegida por el barrido se recalcula exacta: igual que analizar directamente esas fechas."""
    a = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, site_id="apollo11"))
    b = P.run_analysis(ctx, AnalysisRequest(*APOLLO, a.score.best_start_utc, a.score.best_window_end_utc, site_id="apollo11"))
    for k in ("solar_fraction", "earth_fraction", "max_darkness_s", "longest_earth_window_s"):
        assert getattr(a.window_metrics, k) == pytest.approx(getattr(b.metrics, k), abs=0.01)   # ± 10 ms (ET↔UTC)
    assert a.score.score == pytest.approx(b.score.score, abs=1e-9)
    assert b.score.n_starts == 1 and b.score.best_start_utc == b.score.window_start_utc   # periodo = misión: una sola fecha


def test_apollo11_exactly_14_days_gives_sin_datos_or_provisional_no_apto_by_rule(ctx):
    # amanece y la ventana cabe en el día lunar: nada falla sobre esfera lisa → SIN DATOS (nunca APTO/CONDICIONAL)
    ok = P.run_analysis(ctx, AnalysisRequest(*APOLLO, SUNRISE, "2026-12-29T00:00:00", site_id="apollo11"))
    assert ok.score.verdict == "SIN DATOS" and ok.score.partial and ok.score.best_start_utc == SUNRISE
    # empieza de noche: G0 y G4 fallan ya con esfera lisa → NO APTO provisional, etiquetado, sin fecha válida
    bad = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, "2026-12-15T00:00:00", site_id="apollo11"))
    s = bad.score
    assert s.verdict == "NO APTO" and s.verdict_provisional and "provisional" in s.verdict_reason
    assert s.best_start_utc is None and s.feasible_start_fraction == 0.0 and s.top_windows == ()
    assert {g.id for g in s.gates if g.hard and g.status is GateStatus.FAIL} >= {"G0", "G4"}


def test_period_shorter_than_mission_is_sin_datos_and_hard_fail_still_rejects(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(*APOLLO, SUNRISE, "2026-12-25T00:00:00", site_id="apollo11"))   # 10 d < 14 d
    assert r.score.verdict == "SIN DATOS" and "periodo más corto" in r.score.verdict_reason
    assert r.score.best_start_utc is None and r.score.n_starts is None
    night = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, "2026-12-08T00:00:00", site_id="apollo11"))   # 7 d de noche
    assert night.score.verdict == "NO APTO"


def test_mission_days_is_editable_and_custom_profile_has_no_window(ctx):
    r = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, mission_days=5.0))
    assert r.score.mission_days == 5.0 and r.window_metrics.period_s == pytest.approx(5 * 86400.0, abs=1.0)
    c = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, score_profile_id="custom"))
    assert c.score.mission_days is None and c.score.best_start_utc is None and c.window_metrics is c.metrics
    assert "G0" not in {g.id for g in c.score.gates}                     # sin ventana: puertas sobre el periodo, como antes
    with pytest.raises(P.InvalidParameterError):
        P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, mission_days=0.0))


def test_profiles_have_window_duration_from_config(ctx):
    profs = P.profiles_from_config(ctx.cfg["score"])
    got = {pid: profs[pid].mission_days for pid in ("lander_solar_no_rhu", "lander_with_batteries", "lander_rhu", "rover",
                                                    "base_isru")}
    assert got == {"lander_solar_no_rhu": 14.0, "lander_with_batteries": 30.0, "lander_rhu": 90.0, "rover": 100.0,
                   "base_isru": 365.0}
    r = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, score_profile_id="lander_rhu"))
    assert r.score.mission_days == 90.0 and r.score.verdict in ("SIN DATOS", "NO APTO")   # 30 d < 90 d
    assert next(g for g in r.score.gates if g.id == "G4").status is GateStatus.NOT_APPLICABLE   # RHU: sin límite de noche


# ---------------------------------------------------------------------------------------- DEM: confianza que discrimina
SITE04_TOP5 = [(-89.562569, 215.472401), (-89.623088, 188.541301), (-89.822243, 207.004774),
               (-89.873564, 210.528056), (-89.670324, 197.148027)]   # TOP-5 lander de data/processed/suitability (Site04)


@pytest.mark.needs_dem
def test_data_confidence_discriminates_site04_top5(ctx):
    if "Site04" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site04")
    rs = [P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, with_uncertainty=True)) for lat, lon in SITE04_TOP5]
    levels = {r.score.confidence.level.value for r in rs}
    assert len(levels) >= 2 and {"alta", "media"} <= levels                # antes: los 15 TOP salían «baja» sin excepción
    for r in rs:
        c, d = r.score.confidence, r.dem_confidence
        assert c.c_sup == pytest.approx(min(d.dc, d.c_hz)) and d.sigma_h90_deg is not None
        assert c.c == pytest.approx(min(c.c_cov, c.c_sup, c.c_range))
    # σh90 medido por la revisión geológica para el rank 1 (0,074°) y el 2 (0,016°) con los mismos parámetros gruesos
    assert rs[0].dem_confidence.sigma_h90_deg == pytest.approx(0.074, abs=0.01)
    assert rs[1].dem_confidence.sigma_h90_deg == pytest.approx(0.016, abs=0.01)
    assert rs[0].score.confidence.level.value == "alta" and rs[0].score.confidence.c_sup == pytest.approx(0.96, abs=0.02)


@pytest.mark.needs_dem
def test_site04_top1_window_state_comes_from_gates_not_from_score(ctx):
    if "Site04" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site04")
    r = P.run_analysis(ctx, AnalysisRequest(*SITE04_TOP5[0], START, END30, with_uncertainty=True))
    s = r.score
    assert s.mission_days == 14.0 and s.verdict in ("APTO", "CONDICIONAL")         # 14 d: ya no «noche anual 206 h → FAIL»
    assert r.window_metrics.max_darkness_s / 3600.0 <= 12.0 < r.metrics.max_darkness_s / 3600.0
    assert s.feasible_start_fraction is not None and 0.0 < s.feasible_start_fraction <= 1.0
    assert s.best_start_utc is not None and 1 <= len(s.top_windows) <= 3


def test_rescore_from_result_inputs_reproduces_pipeline_score(ctx):
    """API para la UI: ``res.score_inputs``/``score_scenarios`` + las funciones puras reproducen el score del pipeline."""
    from lsi.analysis.site_score import params_from_config, score_with_range
    r = P.run_analysis(ctx, AnalysisRequest(*APOLLO, START, END30, with_uncertainty=True))
    prof = P.profiles_from_config(ctx.cfg["score"])[r.request.score_profile_id]
    again = score_with_range(r.score_inputs, r.score_scenarios, prof, params_from_config(ctx.cfg["score"]),
                             P._mission(ctx, prof.mission_profile_id), c_sup=r.score.confidence.c_sup,
                             dem=r.dem_confidence, feasible_fraction=r.score.feasible_start_fraction)
    assert (again.score, again.score_min, again.score_max, again.verdict) == \
        (r.score.score, r.score.score_min, r.score.score_max, r.score.verdict)
    assert [g.id for g in again.gates] == [g.id for g in r.score.gates]


# ---------------------------------------------------------------------------------------- M1: pasos de serie > max_step_s
def test_effective_step_is_exact_divisor_below_max():
    mx = 840.0
    cfg = {"timeline": {"max_step_s": mx}}
    for asked, want in ((300.0, 300.0), (600.0, 600.0), (840.0, 840.0), (900.0, 450.0), (1800.0, 600.0), (3600.0, 720.0)):
        got = P.effective_step_s(cfg, asked)
        assert got == pytest.approx(want) and got <= mx and (asked / got) == pytest.approx(round(asked / got))
    assert P.effective_step_s({"timeline": {}}, 3600.0) == 3600.0   # sin tope configurado
    assert not P.effective_step_s(cfg, 0.0) > 0                    # inválido: lo rechaza catalog con su mensaje


@pytest.mark.parametrize("step_min", [15, 30, 60])
def test_ui_steps_15_30_60_min_run_and_lose_no_transition(ctx, step_min):
    """M1: la UI ofrece 15/30/60 min; antes fallaban con InvalidParameterError. Ahora el muestreo interno baja al paso
    máximo permitido (divisor exacto del pedido), se anota en los supuestos y las ventanas son las del paso interno."""
    kw = dict(site_id="apollo11")
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, "2026-12-11T00:00:00", step_s=step_min * 60.0, **kw))
    eff = P.effective_step_s(ctx.cfg, step_min * 60.0)
    assert eff <= ctx.cfg["timeline"]["max_step_s"] and float(r.sky.et[1] - r.sky.et[0]) == pytest.approx(eff)
    assert any("se muestrea internamente" in a for a in r.score.assumptions)
    ref = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, "2026-12-11T00:00:00", step_s=eff, **kw))
    assert [(w.start_et, w.end_et) for w in r.timeline.sun.windows] == [(w.start_et, w.end_et) for w in ref.timeline.sun.windows]
    assert r.metrics.solar_fraction == pytest.approx(ref.metrics.solar_fraction)
    assert not any("se muestrea internamente" in a for a in ref.score.assumptions)   # paso válido: nada que anotar
    with pytest.raises(P.catalog.InvalidParameterError):
        P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, START, "2026-12-11T00:00:00", step_s=-5.0, **kw))


# ---------------------------------------------------------------------------------------- M3 en el pipeline
@pytest.mark.needs_dem
def test_cold_warning_cites_panel_range_and_only_with_power(ctx):
    if "Site23" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site23")
    r = P.run_analysis(ctx, AnalysisRequest(*SITES["Site23"], START, "2026-12-15T00:00:00", panel_id="tj-gaas-lander-body",
                                            mounting=MountingSpec(MountingType.HORIZONTAL)))
    cold = [w for w in r.warnings if w.code is WarningCode.COLD_EXTRAPOLATION]
    assert bool(cold) == bool(r.power.t_clamped.any())
    if cold:
        assert "[15, 125]" in cold[0].text_es and "°C" in cold[0].text_es
        assert (r.power.p_rel[r.power.t_clamped] > 0).all()           # nunca sin potencia
        t = r.power.t_panel_k[r.power.t_clamped] - 273.15
        assert ((t < 15.0) | (t > 125.0)).all()


# ---------------------------------------------------------------------------------------- SNAP AL MEJOR PUNTO
GAZ = {"Shackleton": (5450, -89.67, 129.78, "Site04"), "de Gerlache": (1439, -88.4849, 271.6553, "Site11")}


def _end(start: str, days: float) -> str:
    from lsi.astronomy import spice_engine
    return spice_engine.et_to_utc(spice_engine.utc_to_et(start) + days * 86400.0)[:19]


@pytest.mark.needs_dem
def test_shackleton_snaps_to_best_point_and_is_viable_on_its_best_date(ctx):
    """Antes (informe-pruebas hallazgo 1): «Shackleton» por el buscador caía en un punto SIN Sol (f_sol 0, score 2,18). Ahora,
    por defecto, va al TOP-1 del mapa de idoneidad (lander sin RHU, 14 d) y en su mejor fecha tiene Sol y veredicto viable."""
    fid, lat, lon, key = GAZ["Shackleton"]
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    o, w = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, profile_id="lander_solar_no_rhu", mission_days=14.0)
    near, _ = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, prefer="nearest")
    assert o.snap_kind == "best" and o.dem_key == key and o.best_start_utc and o.snapped_from == (lat, pytest.approx(lon))
    assert near.snap_kind == "nearest" and near.best_start_utc is None and near.snap_ranking == () and 0.3 < near.snap_distance_km < 1.5
    assert o.snap_alternative == (pytest.approx(near.lat_deg), pytest.approx(near.lon_deg_e), pytest.approx(near.snap_distance_km))
    # CAMBIO INTENCIONADO (snap limitado al rasgo): el elegido es el mejor DENTRO del entorno del rasgo, no necesariamente el rango 1
    ch = next(e for e in o.snap_ranking if e.rank == o.snap_map_rank)
    assert (ch.lat_deg, ch.lon_deg_e) == (o.lat_deg, o.lon_deg_e) and ch.best_start_utc == o.best_start_utc
    assert len(o.snap_ranking) >= 3 and o.snap_ranking[0].rank == 1
    assert o.snap_distance_km == pytest.approx(ch.distance_km) and (o.lat_deg, o.lon_deg_e) != (near.lat_deg, near.lon_deg_e)
    assert "snap_to_dem" in o.label and "mejor punto" in o.label and f"{o.snap_distance_km:.2f} km" in o.label
    assert f"TOP-{o.snap_map_rank}" in o.snap_reason and "Alternativa" in o.snap_reason and "DENTRO" in o.snap_reason
    assert w[0].code is WarningCode.CURATED_COORDS_OUTSIDE_DEM and o.snap_reason in w[0].text_es
    # en su mejor fecha de inicio, con run_analysis completo (el mapa es grueso: se comprueba con el modelo fino)
    req = AnalysisRequest(lat, lon, o.best_start_utc, _end(o.best_start_utc, 14.0), gazetteer_id=fid,
                          score_profile_id="lander_solar_no_rhu", mission_days=14.0)
    best = P.run_analysis(ctx, req)
    assert best.observer.snap_kind == "best" and (best.observer.lat_deg, best.observer.lon_deg_e) == (o.lat_deg, o.lon_deg_e)
    assert best.metrics.solar_fraction > 0.9 and best.score.verdict in ("APTO", "CONDICIONAL"), (best.metrics.solar_fraction, best.score.verdict)
    # prefer="nearest" mantiene el comportamiento anterior: el punto sin Sol del informe de pruebas
    old = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, gazetteer_id=fid, snap_prefer="nearest"))
    assert old.observer.snap_kind == "nearest" and old.observer.snap_distance_km == pytest.approx(0.80, abs=0.02)
    assert old.metrics.solar_fraction == 0.0 and old.score.verdict == "NO APTO"


@pytest.mark.needs_dem
@pytest.mark.parametrize("name", ["Shackleton", "de Gerlache"])
def test_best_snap_is_default_for_features_but_not_for_custom_coordinates(ctx, name):
    fid, lat, lon, key = GAZ[name]
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    feat, _ = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid)                     # buscador: mejor punto por defecto
    cur, _ = P.resolve_observer(ctx, lat, lon, 2.0, site_id={"Site04": "site04", "Site11": "site11"}[key])   # sitio curado
    assert feat.snap_kind == "best" and cur.snap_kind == "best"
    custom, _ = P.resolve_observer(ctx, lat, lon, 2.0, snap_to_dem=True)                    # coordenadas exactas del usuario
    assert custom.snap_kind == "nearest" and custom.best_start_utc is None
    # ...salvo que lo pida; sin rasgo, el radio es el defecto (10 km): de Gerlache (radio 16,4 km) no tiene ningún punto
    # recomendable en ese entorno y cae al más cercano CON AVISO; con el radio del rasgo sí hay mejor punto
    forced, _ = P.resolve_observer(ctx, lat, lon, 2.0, snap_to_dem=True, prefer="best")
    assert forced.snap_kind == ("best" if key == "Site04" else "nearest")
    if key == "Site11":
        assert forced.snap_inside_feature is False and "ningún punto recomendable dentro del rasgo" in forced.snap_reason
    assert P.resolve_observer(ctx, lat, lon, 2.0, snap_to_dem=True, prefer="best", feature_radius_km_=16.35)[0].snap_kind == "best"
    with pytest.raises(ValueError):
        P.snap_candidate(ctx, lat, lon, prefer="mejor")


@pytest.mark.needs_dem
def test_best_snap_without_precomputed_map_falls_back_to_nearest_with_reason(ctx, tmp_path):
    import copy
    import dataclasses
    fid, lat, lon, key = GAZ["Shackleton"]
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    cfg = copy.deepcopy(ctx.cfg)
    cfg["cache"]["dir"] = str(tmp_path)                                  # sin suitability/: no hay mapa
    empty = dataclasses.replace(ctx, cfg=cfg)
    o, w = P.resolve_observer(empty, lat, lon, 2.0, gazetteer_id=fid)
    assert o.snap_kind == "nearest" and o.best_start_utc is None and o.snap_ranking == ()
    assert "sin mapa de idoneidad precalculado" in o.snap_reason and "precompute_suitability" in o.snap_reason
    assert "sin mapa de idoneidad" in w[0].text_es
    # perfil sin duración de misión (custom): tampoco hay mejor punto
    c, _ = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, profile_id="custom")
    assert c.snap_kind == "nearest" and "duración" in c.snap_reason


@pytest.mark.needs_dem
def test_best_snap_uses_closest_precomputed_duration_and_says_so(ctx):
    fid, lat, lon, key = GAZ["Shackleton"]
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    o, _ = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, profile_id="rover", mission_days=100.0)   # mapas 7/14/30 d
    assert o.snap_kind == "best" and "mapa precalculado de 30 d" in o.snap_reason


@pytest.mark.needs_dem
@pytest.mark.slow
def test_window_map_apt_days_equal_pipeline_at_top_points(ctx):
    """M2: el mapa de ventanas aplica G0 (Sol al inicio) como el pipeline. En los TOP-3 reales de cada sitio (lander sin RHU,
    14 d) los días de inicio aptos del mapa (rejilla de 30 min, horizonte grueso) coinciden con los de ``run_analysis``
    (600 s, horizonte fino) con diferencia ≤ 1 día (antes del arreglo: 69 vs 65, 30 vs 27, 40 vs 38) y la misma mejor fecha."""
    from lsi.analysis import suitability_map as sm
    diffs = []
    for key in ("Site04", "Site11", "Site23"):
        if key not in ctx.dem_refs:
            continue
        bp = sm.best_points(Path(ctx.root) / ctx.cfg["cache"]["dir"], key, "lander_solar_no_rhu", 14.0)
        assert bp is not None and bp["duration_days"] == 14.0, "falta el mapa precalculado (scripts/precompute_suitability.py)"
        assert len(bp["top"]) >= 3
        for t in bp["top"][:3]:
            r = P.run_analysis(ctx, AnalysisRequest(t["lat_deg"], t["lon_deg_e"], "2026-12-01T00:00:00",
                                                    _end("2026-12-01T00:00:00", 378.0), score_profile_id="lander_solar_no_rhu",
                                                    mission_days=14.0))
            apt = round(r.score.feasible_start_fraction * r.score.n_starts)
            assert r.score.n_starts == 365 and r.score.best_start_utc == t["best_start_utc"]
            diffs.append(abs(apt - t["apt_start_days"]))
    assert diffs and max(diffs) <= 1 and diffs.count(0) >= len(diffs) * 2 // 3, diffs


# ---------------------------------------------------------------------------------------- snap acotado al rasgo (cierre)
@pytest.mark.needs_dem
@pytest.mark.parametrize("name,fid,lat,lon,key,radius", [
    ("Shackleton", 5450, -89.67, 129.78, "Site04", 20.924982 / 2), ("de Gerlache", 1439, -88.4849, 271.6553, "Site11", 32.705418 / 2)])
def test_best_snap_stays_in_the_feature_surroundings(ctx, name, fid, lat, lon, key, radius):
    """Antes el mejor punto era el TOP-1 de TODO el DEM: Shackleton a 16,0 km del centro (≈5,5 km FUERA del borde). Ahora es el
    mejor entre los candidatos a ≤ radio·1,15 + 1 km del centro (radio = diámetro oficial del gazetteer / 2) y la etiqueta lo dice."""
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    assert P.feature_radius_km(ctx, fid) == pytest.approx(radius, abs=1e-3)
    o, w = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, profile_id="lander_solar_no_rhu", mission_days=14.0)
    lim = radius * 1.15 + 1.0
    assert o.snap_kind == "best" and o.snap_inside_feature is True and o.snap_feature_radius_km == pytest.approx(radius, abs=1e-3)
    assert o.snap_distance_km <= lim and abs(o.snap_edge_offset_km - (o.snap_distance_km - radius)) < 1e-9
    assert abs(o.snap_distance_km - radius) < 1.5          # en el borde (≈ radio ± tolerancia), no 5 km fuera
    top1 = o.snap_ranking[0]
    assert top1.rank == 1 and top1.distance_km > lim and o.snap_map_rank > 1      # el TOP-1 global queda fuera del rasgo y se descarta
    assert (o.lat_deg, o.lon_deg_e) != (top1.lat_deg, top1.lon_deg_e)
    ch = next(e for e in o.snap_ranking if e.rank == o.snap_map_rank)
    assert ch.f_sun > 0.9 and ch.best_start_utc == o.best_start_utc               # f_sol alta y su mejor fecha
    r = o.snap_reason
    assert "DENTRO" in r and f"{o.snap_distance_km:.2f} km del centro" in r and "borde" in r and f"TOP-{o.snap_map_rank}" in r
    assert f"TOP-1 del mapa queda a {top1.distance_km:.2f} km del centro" in r and "se descarta" in r
    assert "mejor punto" in o.label and w[0].code is WarningCode.CURATED_COORDS_OUTSIDE_DEM
    assert o.snap_alternative is not None                                          # la alternativa más cercana se mantiene


@pytest.mark.needs_dem
def test_best_snap_without_candidate_inside_feature_falls_back_to_nearest_with_warning(ctx):
    fid, lat, lon, key = GAZ["Shackleton"]
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    o, w = P.resolve_observer(ctx, lat, lon, 2.0, gazetteer_id=fid, feature_radius_km_=2.0)   # rasgo «pequeño»: ningún TOP cabe
    assert o.snap_kind == "nearest" and o.snap_inside_feature is False and o.snap_map_rank is None
    assert "ningún punto recomendable dentro del rasgo" in o.snap_reason and "ningún punto recomendable" in w[0].text_es
    assert len(o.snap_ranking) >= 3 and o.snap_edge_offset_km == pytest.approx(o.snap_distance_km - 2.0)


@pytest.mark.needs_dem
def test_score_energy_follows_the_chosen_panel_and_mounting_monotonically(ctx):
    """T39/RF-33: el mismo sitio con panel horizontal, vertical fijo y vertical con seguimiento da energía y score distintos y
    monótonos (potencia efectiva: horizontal ≪ vertical fijo < vertical con seguimiento); sin panel usa el Sol geométrico y lo dice."""
    lat, lon = SITES["Site23"]
    if "Site23" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site23")
    def run(m):
        kw = {} if m is None else dict(panel_id="tj-gaas-lander-body", mounting=m)
        return P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, **kw))
    h = run(MountingSpec(MountingType.HORIZONTAL))
    vf = run(MountingSpec(MountingType.VERTICAL_FIXED, azimuth_deg=0.0))
    vt = run(VAT)
    g = run(None)
    for r in (h, vf, vt):
        assert r.score.energy_basis == "panel" and r.score.energy_panel_id == "tj-gaas-lander-body"
        assert r.score.subscores[0].label.endswith("(potencia efectiva del panel)")
        assert r.metrics.solar_fraction == g.metrics.solar_fraction            # la fracción de Sol no cambia: solo la energía
    e = [r.score.subscores[0].value for r in (h, vf, vt)]
    s = [r.score.score for r in (h, vf, vt)]
    assert e[0] < e[1] < e[2] and s[0] < s[1] < s[2], (e, s)
    assert h.score.energy_p_rel_mean < vf.score.energy_p_rel_mean < vt.score.energy_p_rel_mean
    assert h.score.energy_duty_useful < vf.score.energy_duty_useful <= vt.score.energy_duty_useful
    assert s[0] < 0.5 * s[2]                                                   # un panel horizontal en el polo rinde casi nada
    assert g.score.energy_basis == "geometric" and g.score.energy_panel_id is None and "Sol geométrico" in " ".join(g.score.assumptions)
    assert "G5" not in {x.id for x in g.score.gates}                           # sin panel no se inventa la puerta de potencia útil
    # G5 con panel: duty útil medido sobre la ventana de misión y estado coherente con el límite del perfil (blanda, 0,5)
    for r in (h, vf, vt):
        g5 = next(x for x in r.score.gates if x.id == "G5")
        assert g5.value == pytest.approx(r.score.energy_duty_useful) and g5.limit == 0.5 and g5.hard is False
        assert (g5.status is GateStatus.PASS) == (g5.value >= 0.5)
    assert next(x for x in h.score.gates if x.id == "G5").status is GateStatus.FAIL
    assert "G5" in h.score.verdict_reason or h.score.verdict == "NO APTO"      # la puerta blanda o la dura (G4) lo explican


@pytest.mark.needs_dem
def test_uncertainty_range_is_explicit_when_not_computed(ctx):
    lat, lon = SITES["Site23"]
    if "Site23" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site23")
    a = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30))
    assert a.score.range_computed is False and a.score.range_note.startswith("rango no calculado")
    b = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, END30, with_uncertainty=True))
    assert b.score.range_computed is True and b.score.range_note.startswith("rango calculado")
    assert b.score.score_min <= b.score.score <= b.score.score_max
    assert ("estrecho" in b.score.range_note) == (b.score.score_max - b.score.score_min < 0.05)


# ---------------------------------------------------------------------------------------- enlace DTE (red terrestre + margen)
def _req(**kw):
    return AnalysisRequest(0.6741, 23.473, START, END30, site_id="apollo11", **kw)


def test_link_none_is_the_previous_geometric_behaviour(ctx):
    g = P.run_analysis(ctx, _req(link_network=None))
    assert g.link is None and g.metrics.link_fraction is None and g.metrics.link_by_station is None
    assert not g.score_inputs.link_mode and g.score_inputs.max_link_gap_h is None
    assert "G7" not in [x.id for x in g.score.gates]
    assert g.f_earth_ref == pytest.approx(g.metrics.earth_fraction)          # esfera lisa: la referencia es la propia serie
    assert "link_hours" not in g.daily[0]
    assert next(s for s in g.score.subscores if s.key == "earth").label == "Visibilidad de la Tierra"


def test_link_dsn_separates_geometry_from_link_and_exposes_stations(ctx):
    r = P.run_analysis(ctx, _req())                                           # defecto: DSN, margen 0°
    m, lk = r.metrics, r.link
    assert lk is not None and lk.network_id == "DSN" and lk.min_earth_elevation_deg == 0.0
    assert m.link_fraction <= m.earth_fraction + 1e-9                          # el enlace nunca supera la geometría
    assert m.link_fraction >= m.earth_fraction - (1.0 - m.network_fraction) - 1e-6
    assert m.network_fraction > 0.99                                           # 3 complejos DSN cubren casi siempre la Luna
    assert set(m.link_by_station) == {"DSS-14", "DSS-63", "DSS-43"}
    assert sum(m.link_by_station.values()) >= m.link_fraction - 1e-9           # suma por estación ≥ cobertura de la red
    assert m.link_hours_per_day_mean == pytest.approx(24.0 * m.link_fraction)
    assert m.longest_link_window_s <= m.period_s and m.max_link_gap_s >= 0.0
    assert r.score_inputs.link_mode and r.score_inputs.f_earth == pytest.approx(m.link_fraction, abs=0.02)
    assert next(s for s in r.score.subscores if s.key == "earth").label.startswith("Enlace")
    assert [s.station_id for s in lk.stations] == ["DSS-14", "DSS-63", "DSS-43"]
    assert lk.contacts and all(c.start_et >= r.timeline.et0 - 1 and c.end_et <= r.timeline.et1 + 1 for c in lk.contacts)
    assert all(abs(d["link_hours"] - d["earth_hours"]) <= 24.0 for d in r.daily) and "link_hours" in r.daily[0]
    assert r.link_window is not None


def test_link_margin_is_monotone_and_reported_sensitivity(ctx):
    f = {mg: P.run_analysis(ctx, _req(min_earth_elevation_deg=mg)).metrics for mg in (0.0, 3.0, 5.0)}
    assert f[0.0].link_fraction >= f[3.0].link_fraction >= f[5.0].link_fraction
    assert f[0.0].earth_fraction == pytest.approx(f[3.0].earth_fraction)       # la geometría no cambia con el margen
    assert f[0.0].link_fraction > 0.9                                          # Apolo 11 (cara visible) ve la Tierra casi siempre


def test_single_station_custom_network_lowers_link_and_g7_uses_the_gap(ctx):
    one = P.run_analysis(ctx, _req(link_network="custom", link_custom=((40.43, -4.25, 6.0, "Europe/Madrid"),)))
    dsn = P.run_analysis(ctx, _req())
    assert one.metrics.link_fraction < 0.6 < dsn.metrics.link_fraction         # una estación ve la Luna ~45 % del tiempo
    assert one.metrics.max_link_gap_s > 6 * 3600                                # noches sin Luna sobre el horizonte de la estación
    g7 = next(g for g in one.score.gates if g.id == "G7")
    assert g7.value == pytest.approx(one.window_metrics.max_link_gap_s / 3600.0)
    assert one.score.score < dsn.score.score
    assert one.link.contacts[0].tz == "Europe/Madrid"


def test_unknown_network_and_negative_margin_are_invalid_parameters(ctx):
    with pytest.raises(P.InvalidParameterError):
        P.run_analysis(ctx, _req(link_network="NOPE"))
    with pytest.raises(P.InvalidParameterError):
        P.run_analysis(ctx, _req(min_earth_elevation_deg=-1.0))


def test_link_uncertainty_range_has_link_metrics(ctx):
    r = P.run_analysis(ctx, _req(with_uncertainty=True))
    rg = r.uncertainty.ranges["link_fraction"]
    assert rg.lo <= rg.nominal <= rg.hi and "max_link_gap_s" in r.uncertainty.ranges


# ---------------------------------------------------------------------------------------- sentido del enlace y mejor fecha por G7 (revision-enlace)
def test_link_direction_default_receive_and_transmit_lowers_network_coverage(ctx):
    rx = P.run_analysis(ctx, _req())
    assert rx.request.link_direction == "receive"
    d = rx.network_fraction_by_direction
    assert set(d) == {"receive", "transmit", "both"} and d["receive"] == pytest.approx(rx.metrics.network_fraction, abs=1e-3)
    assert d["transmit"] < d["receive"] and d["both"] == pytest.approx(d["transmit"]) and d["receive"] > 0.99
    tx = P.run_analysis(ctx, _req(link_direction="transmit"))
    assert tx.network_fraction_by_direction["receive"] == pytest.approx(d["receive"], abs=1e-9)    # el resumen por sentido no depende del elegido
    assert tx.metrics.network_fraction == pytest.approx(d["transmit"], abs=1e-3)                               # el sentido elegido manda
    assert tx.metrics.network_fraction < rx.metrics.network_fraction
    assert tx.metrics.link_fraction <= rx.metrics.link_fraction + 1e-9
    assert all(s.min_elevation_deg == 10.1 for s in tx.link.stations) and all(s.min_elevation_deg == 6.0 for s in rx.link.stations)
    assert any("TRANSMISIÓN" in n for n in tx.link.notes) and not any("TRANSMISIÓN" in n for n in rx.link.notes)
    both = P.run_analysis(ctx, _req(link_direction="both"))
    assert both.metrics.link_fraction == pytest.approx(tx.metrics.link_fraction) and all(s.min_elevation_deg == 10.1 for s in both.link.stations)


def test_link_direction_invalid_and_geometry_mode(ctx):
    with pytest.raises(P.InvalidParameterError, match="link_direction"):
        P.run_analysis(ctx, _req(link_direction="up"))
    g = P.run_analysis(ctx, _req(link_network=None, link_direction="transmit"))     # sin red no hay enlace: el sentido no se usa
    assert g.link is None and g.network_fraction_by_direction is None


def test_link_windows_have_no_spurious_handoff_gap(ctx):
    """B2: 1-4 feb 2027 (hueco espurio de ~3 s el 2-feb 05:41:28 UTC antes de la fusión): ningún hueco de red < 60 s entre ventanas de enlace."""
    r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, "2027-02-01T00:00:00", "2027-02-04T00:00:00", site_id="apollo11",
                                            score_profile_id="custom"))
    ws = r.timeline.link.network_cover.windows
    gaps = np.array([w1.start_et - w0.end_et for w0, w1 in zip(ws[:-1], ws[1:])])
    assert len(ws) >= 1 and (gaps > 60.0).all(), gaps


def test_best_start_prefers_g7_or_minimises_the_gap(ctx):
    """Una sola estación (Madrid): los huecos varían con la fecha. Si alguna fecha probada cumple G7 (48 h), la elegida lo cumple; si
    ninguna, la elegida tiene el MENOR hueco y el aviso lo dice."""
    kw = dict(link_network="custom", link_custom=((40.43, -4.25, 6.0, "Europe/Madrid"),))
    best = P.run_analysis(ctx, _req(**kw))
    g = best.window_metrics.max_link_gap_s / 3600.0
    each = []
    for d in range(0, 17, 2):
        a = np.datetime64(START) + np.timedelta64(d, "D")
        r = P.run_analysis(ctx, AnalysisRequest(0.6741, 23.473, str(a), str(a + np.timedelta64(14, "D")), site_id="apollo11", link_network="custom",
                                                link_custom=kw["link_custom"]))
        each.append(r.window_metrics.max_link_gap_s / 3600.0)
    g7_ok = [x <= 48.0 for x in each]
    if any(g7_ok):
        assert g <= 48.0 and not any("Ninguna fecha de inicio del periodo cumple G7" in a for a in best.score.assumptions)
    else:
        assert g <= min(each) + 0.5                                                  # el barrido es a la rejilla de 600 s: ± unos minutos
        assert any("Ninguna fecha de inicio del periodo cumple G7" in a and "MENOR hueco" in a for a in best.score.assumptions)


def test_score_s_earth_carries_the_link_gap_and_geometry_does_not(ctx):
    """La ventana de enlace con huecos puntúa su s_earth con el factor de continuidad; con red=None (geometría) no hay factor."""
    one = P.run_analysis(ctx, _req(link_network="custom", link_custom=((40.43, -4.25, 6.0, "Europe/Madrid"),)))
    se = next(s for s in one.score.subscores if s.key == "earth").s
    gap_h = one.window_metrics.max_link_gap_s / 3600.0
    assert gap_h > 6.0 and se < 1.0 and se <= 2.0 ** (-gap_h / 48.0) + 1e-9
    assert any("continuidad ABSOLUTA" in a for a in one.score.assumptions)
    geo = P.run_analysis(ctx, _req(link_network=None))
    assert not any("continuidad ABSOLUTA" in a for a in geo.score.assumptions)


# ---------------------------------------------------------------------------------------- honestidad científica (14/11/2026)
@pytest.mark.needs_dem
def test_slope_r50_r100_next_to_verdict_and_edge_flag(ctx):
    """slope_r50/slope_r100 salen del mismo footprint_slope que el veredicto (r50 = ``res.slope``); r100 es más áspero; el borde se señala."""
    from lsi.terrain import slope as sl
    key = "Site04"
    if key not in ctx.dem_refs:
        pytest.skip("falta el DEM Site04")
    lat, lon = SITES[key]
    r = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, "2026-12-15T00:00:00", mission_days=14.0))
    a, b = r.slope_r50, r.slope_r100
    assert a.r_foot_m == 50.0 and b.r_foot_m == 100.0 and a.landing_limit_deg == b.landing_limit_deg == 10.0
    assert a.p90_deg == pytest.approx(r.slope.percentile_deg, abs=1e-9) and a.mean_deg == pytest.approx(r.slope.mean_deg)
    assert a.max_deg >= a.p90_deg >= 0 and b.max_deg >= b.p90_deg and b.n_pixels > 3 * a.n_pixels
    assert 0.0 <= a.pct_area_above_limit <= b.pct_area_above_limit + 100 and 0.0 <= b.pct_area_above_limit <= 100.0
    # valor independiente: % de píxeles ≥ 10° en el disco, a mano desde la capa slp
    x, y = r.observer.x_m, r.observer.y_m
    slp = P._small(ctx.dem_refs[key], P.DemLayer.SLP, x, y, 130.0)
    v = sl.disk_view(np.asarray(slp.data, float), slp, x, y, 100.0)
    v = v[np.isfinite(v)]
    assert b.pct_area_above_limit == pytest.approx(100.0 * np.mean(v >= 10.0), abs=1e-9)
    assert r.dem_edge_distance_m > 0 and r.footprint_touches_dem_edge is (r.dem_edge_distance_m < 100.0 + 10.0)
    # punto pegado al borde del recorte: la huella lo roza y se dice (sin inventar pendiente)
    x0, y0, x1, y1 = ctx.dem_refs[key].bounds_xy_m
    near = P._slope_scales(ctx, r.observer.__class__(**{**r.observer.__dict__, "x_m": x0 + 60.0, "y_m": (y0 + y1) / 2}), "lander_solar_no_rhu")
    assert near[2] is True and near[0][100.0].touches_dem_edge


@pytest.mark.needs_dem
def test_power_summary_declares_iam_model_and_has_grazing_band(ctx):
    key = "Site04"
    if key not in ctx.dem_refs:
        pytest.skip("falta el DEM Site04")
    lat, lon = SITES[key]
    r = P.run_analysis(ctx, AnalysisRequest(lat, lon, START, "2026-12-15T00:00:00", panel_id="tj-gaas-lander-body", mounting=VAT))
    s = r.power_summary
    assert s.iam_model == "fresnel_1_interface" == ctx.panels.panels[0].iam_model
    lo, hi = s.e_rel_band
    assert lo <= s.e_rel + 1e-9 <= hi + 1e-9 and hi > lo and set(s.e_rel_band_components) >= {"optics", "thermal"}
    assert "doble conteo" in s.band_note or "sin doble conteo" in s.band_note
    assert "a verificar" in s.band_note
