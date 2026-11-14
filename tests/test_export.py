"""Tests de analysis.export con AnalysisResult sintéticos (sin SPICE, sin DEM, sin pipeline)."""
import copy
import csv
import json
import math
from dataclasses import replace

import numpy as np
import pytest

from lsi.analysis.export import (
    ExportSchemaError, comparison_to_csv, et_to_utc_str, result_to_dict, validate_export, write_csv_bundle,
    write_json,
)
from lsi.analysis.metrics import comparison_table
from lsi.analysis.site_score import DEFAULT_PROFILES, compute_score
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, CSV_COMPARISON_COLUMNS, CSV_HORIZON_COLUMNS, CSV_METRICS_COLUMNS,
    CSV_TIMESERIES_COLUMNS, CSV_WINDOWS_COLUMNS, EXPORT_SCHEMA_VERSION, STANDARD_WARNINGS_ES, AnalysisRequest,
    AnalysisResult, Body, BodyTrack, BodyVisibility, DemMetadata, DemLayer, Event, EventKind, HorizonMode,
    HorizonParams, HorizonResult, KernelInfo, MountingSpec, MountingType, ObserverPoint, PowerSeries, PowerSummary,
    DayPower, Range, ScientificWarning, ScoreInputs, ScoreParams, Severity, SiteMetrics, SkySeries, TimelineParams,
    TimelineResult, UncertaintyResult, VisibilitySeries, Window, WindowSet, WarningCode,
)

N = 5
ET = 1000.0 + 600.0 * np.arange(N)


def _ws(label, wins):
    return WindowSet(label, tuple(Window(*w) for w in wins), ET[0], ET[-1], f"crit_{label}")


def make_result(sphere=False, with_power=True, with_score=True, site_id="siteA") -> AnalysisResult:
    az = np.arange(0.0, 360.0, 90.0)
    horizon = HorizonResult(
        az_deg=az, h_lb_deg=np.array([0.5, 1.0, np.nan, 2.0]), r_cov_m=np.array([100.0, 200.0, 300.0, 400.0]),
        limited=np.array([False, True, False, False]),
        mode=HorizonMode.SMOOTH_SPHERE if sphere else HorizonMode.DEM,
        observer=None, params=HorizonParams(), h_sphere_deg=-0.0316, cache_key="hk",
        h_ub_deg=None if sphere else np.array([0.6, 1.5, 1.0, 2.5]), cov_min_m=100.0, cov_median_m=250.0)
    obs = ObserverPoint(-89.5, 123.4567891, 1.5, 2.5, 2.0, horizon.mode, None if sphere else 12.3456,
                        site_id=site_id)
    horizon.observer = obs

    def track(body, off):
        return BodyTrack(body, np.linspace(10 + off, 50 + off, N), np.linspace(-1.0, 2.0, N),
                         np.full(N, 1.496e8 + off), np.full(N, 0.27))

    sky = SkySeries(ET, -89.5, 123.4567891, 2.0, track(Body.SUN, 0), track(Body.EARTH, 5), kernel_hash="kh")
    vis = VisibilitySeries(ET, BodyVisibility(Body.SUN, np.array([0, 0.5, 1, 1, 0.2]), np.array([0, 1, 2, 2, 1], np.int8),
                                              np.array([0, 0, 0, 1, 0], bool)),
                           BodyVisibility(Body.EARTH, np.array([1, 1, 0, 0, 0.0]), np.array([2, 2, 0, 0, 0], np.int8),
                                          np.zeros(N, bool)))
    tl = TimelineResult(
        ET[0], ET[-1], TimelineParams(), _ws("sun", [(1000.0, 2000.0, True, False), (2500.0, 3400.0)]),
        _ws("earth", [(1000.0, 1800.0, True)]), _ws("overlap", [(1000.0, 1800.0, True)]),
        _ws("dark", [(2000.0, 2500.0)]), (Event(2000.0, Body.SUN, EventKind.SET, 270.0),), vis)
    metrics = SiteMetrics(2400.0, 0.7, 0.55, 0.3, 0.2, 1000.0, True, 500.0, False, 800.0, 800.0, 2, 1, 5.5, 2.0, 0.1, 0.0)
    power = summary = None
    if with_power:
        power = PowerSeries(ET, np.array([0, 0.3, 0.9, 0.8, 0.1]), *(np.zeros(N) for _ in range(7)),
                            np.array([0, 0, 0, 0, 1], bool), "panel_x", MountingSpec(MountingType.TILTED, 10.0, 0.0))
        summary = PowerSummary(0.4, 40.0, 100.0, None, 0.4, 0.9, 1.5, 0.05,
                               (DayPower(ET[0], 0.4, 0.9, 1.5),))
    score = None
    if with_score:
        score = compute_score(
            ScoreInputs(0.78, 60.0, 0.4, 0.47, None if sphere else 8.0, 0.0, not sphere, has_dem=not sphere),
            DEFAULT_PROFILES["lander_solar_no_rhu"], ScoreParams())
    dem = None if sphere else DemMetadata("Site04", DemLayer.SURF, 10, 10, 5.0, (0, 0, 50, 50), (5, 0, 0, 0, -5, 0),
                                          "wkt", -32767.0, "float32", "ab" * 32, 100)
    return AnalysisResult(
        AnalysisRequest(-89.5, 123.4567891, "2026-01-01T00:00:00", "2026-01-02T00:00:00", site_id=site_id,
                        mounting=MountingSpec(MountingType.TILTED, 10.0, 0.0)),
        obs, horizon, sky, tl, metrics, (ScientificWarning(WarningCode.NOT_RF_LINK, Severity.INFO, "x", "ctx"),),
        dem_meta=dem, uncertainty=UncertaintyResult((), {"solar_fraction": Range(0.7, 0.6, 0.8)}),
        power=power, power_summary=summary, score=score,
        kernels=KernelInfo("kdir", ("a.tls", "b.bsp"), "khash", 0.0, 1.0, "u0", "u1", "8.4.0"))


# ---- tiempo ---------------------------------------------------------------------------
def test_et_to_utc_valores_conocidos():
    # J2000 = 2000-01-01 12:00:00 TT = 11:58:55.816 UTC (redondeo al segundo: :56)
    assert et_to_utc_str(0.0) == "2000-01-01T11:58:56Z"
    assert et_to_utc_str(float("nan")) is None


def test_et_to_utc_2026():
    from datetime import datetime
    days = (datetime(2026, 1, 1) - datetime(2000, 1, 1)).days  # 9497
    assert et_to_utc_str(days * 86400.0) == "2026-01-01T11:58:51Z"  # 12:00 TT - 69.184 s = 11:58:50.816 -> :51
    assert et_to_utc_str(days * 86400.0 - 1.0) == "2026-01-01T11:58:50Z"


# ---- JSON -----------------------------------------------------------------------------
def test_json_ida_y_vuelta_y_esquema(tmp_path):
    r = make_result()
    p = write_json(r, tmp_path / "r.json", generated_utc="2026-11-14T00:00:00Z")
    txt = p.read_text(encoding="utf-8")
    d = json.loads(txt, parse_constant=lambda c: pytest.fail(f"constante no JSON: {c}"))
    validate_export(d)
    assert d == json.loads(json.dumps(result_to_dict(r, "2026-11-14T00:00:00Z")))
    assert d["schema_version"] == EXPORT_SCHEMA_VERSION and d["generated_utc"] == "2026-11-14T00:00:00Z"
    m = d["metrics"]
    assert m["solar_fraction"] == {"value": 0.7, "unit": "fraction", "lo": 0.6, "hi": 0.8, "truncated": False}
    assert m["longest_sun_window_s"]["truncated"] is True and m["max_darkness_s"]["truncated"] is False
    assert m["n_sun_windows"]["value"] == 2 and m["period_s"]["lo"] is None
    assert not any(k.endswith("_truncated") for k in m)
    w = d["windows"]["sun"][0]
    assert w["start_utc"].endswith("Z") and w["left_truncated"] is True and w["duration_h"] == round(1000 / 3600, 4)
    assert d["events"][0]["kind"] == "set" and d["events"][0]["body"] == "SUN"
    assert d["observer"]["site_id"] == "siteA" and d["observer"]["mode"] == "dem"
    assert d["provenance"]["dem"]["sha256"] == "ab" * 32 and d["provenance"]["kernels"]["files"] == ["a.tls", "b.bsp"]
    assert d["provenance"]["horizon"]["limited_fraction"] == 0.25
    assert d["provenance"]["params"]["visibility"]["sun"] == "crit_sun"
    pw = d["power"]
    assert pw["panel_id"] == "panel_x" and pw["summary"]["e_el_wh_m2"] is None and "daily" not in pw["summary"]
    assert len(pw["daily"]) == 1 and len(pw["assumptions"]) == 2  # incluye extrapolación en frío
    assert d["request"]["mounting"]["type"] == "tilted"
    codes = {x["code"] for x in d["warnings"]}
    assert {c.value for c in ALWAYS_SHOWN_WARNINGS} <= codes and "not_rf_link" in codes


def test_determinista_mismos_bytes(tmp_path):
    a = write_json(make_result(), tmp_path / "a.json").read_bytes()
    b = write_json(make_result(), tmp_path / "b.json").read_bytes()
    assert a == b and b"\r" not in a
    assert write_csv_bundle(make_result(), tmp_path / "c1")["timeseries"].read_bytes() == \
        write_csv_bundle(make_result(), tmp_path / "c2")["timeseries"].read_bytes()


def test_nan_a_null_score_parcial(tmp_path):
    r = make_result(sphere=True)
    assert r.score.partial and any(math.isnan(s.s) for s in r.score.subscores)
    txt = write_json(r, tmp_path / "s.json").read_text(encoding="utf-8")
    assert "NaN" not in txt and "Infinity" not in txt
    d = json.loads(txt)
    validate_export(d)
    sc = d["score"]
    assert sc["partial"] is True and sc["terrain_data"] is False and sc["missing_keys"] == ["terrain"]
    ter = next(x for x in sc["subscores"] if x["key"] == "terrain")
    assert ter["s"] is None and ter["value"] is None and ter["score_if_one"] is not None
    assert all(isinstance(x["s"], float) for x in sc["subscores"] if x["key"] != "terrain")
    codes = {x["code"] for x in d["warnings"]}
    assert {"no_terrain_data_score", "no_dem_smooth_sphere"} <= codes and "dem_effective_resolution" not in codes
    assert d["provenance"]["dem"] is None and d["horizon"]["h_ub_deg"] is None
    assert d["horizon"]["h_lb_deg"][2] is None  # NaN del horizonte -> null


def test_sin_power_ni_score():
    d = result_to_dict(make_result(with_power=False, with_score=False))
    validate_export(d)
    assert d["power"] is None and d["score"] is None


def test_params_extra_en_provenance():
    from lsi.contracts import VisibilityParams
    d = result_to_dict(make_result(), params={"visibility": VisibilityParams()})
    assert d["provenance"]["params"]["visibility"]["n_slices"] == 64


# ---- validador ------------------------------------------------------------------------
def test_validador_rechaza_con_mensaje_claro():
    good = result_to_dict(make_result())
    bad = copy.deepcopy(good)
    del bad["metrics"]
    bad["schema_version"] = "9.9.9"
    bad["warnings"] = [w for w in bad["warnings"] if w["code"] != "geometric_only"]
    bad["horizon"]["limited"].pop()
    bad["score"]["subscores"][0]["s"] = float("nan")
    with pytest.raises(ExportSchemaError) as ei:
        validate_export(bad)
    msg = str(ei.value)
    for frag in ("falta la clave obligatoria 'metrics'", "schema_version='9.9.9'", "geometric_only",
                 "horizon: longitudes distintas", "no finito"):
        assert frag in msg, msg
    with pytest.raises(ExportSchemaError, match="se esperaba dict"):
        validate_export([])
    sph = result_to_dict(make_result(sphere=True))
    sph["score"]["subscores"][-1]["s"] = 0.0  # terreno no evaluado nunca puede ser 0
    with pytest.raises(ExportSchemaError, match="no evaluado, s debe ser null"):
        validate_export(sph)


def test_write_json_no_escribe_si_invalido(tmp_path, monkeypatch):
    r = replace(make_result(), warnings=())
    monkeypatch.setattr("lsi.analysis.export._warnings_block", lambda _r: [])
    with pytest.raises(ExportSchemaError):
        write_json(r, tmp_path / "x.json")
    assert not (tmp_path / "x.json").exists()


# ---- CSV ------------------------------------------------------------------------------
def _read(p):
    raw = p.read_bytes()
    assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(raw.decode("utf-8").splitlines()))


def test_csv_bundle_un_sitio(tmp_path):
    paths = write_csv_bundle(make_result(), tmp_path)
    assert set(paths) == {"timeseries", "windows", "horizon", "metrics", "metadata"}
    ts = _read(paths["timeseries"])
    assert tuple(ts[0]) == CSV_TIMESERIES_COLUMNS and len(ts) == 1 + N
    row = dict(zip(ts[0], ts[1]))
    assert row["utc"].endswith("Z") and row["sun_state"] == "0" and row["unknown_relevant_sun"] == "false"
    assert dict(zip(ts[0], ts[4]))["unknown_relevant_sun"] == "true"
    assert row["p_rel"] == "0.00000" and dict(zip(ts[0], ts[2]))["p_rel"] == "0.30000"
    assert row["sun_az_deg"] == "10.0000"
    # horizonte en el azimut del Sol: 10° entre h(0)=0.5 y h(90)=1.0 -> 0.5556
    assert row["horizon_at_sun_deg"] == "0.5556"
    # Sol en 60°->índice final az=50: interpolación con el NaN de az=180 NO interviene (50 entre 0 y 90)
    assert dict(zip(ts[0], ts[5]))["horizon_at_sun_deg"] != ""
    wi = _read(paths["windows"])
    assert tuple(wi[0]) == CSV_WINDOWS_COLUMNS and wi[1][0] == "sun" and wi[1][4] == "true" and len(wi) == 1 + 2 + 1 + 1 + 1
    hz = _read(paths["horizon"])
    assert tuple(hz[0]) == CSV_HORIZON_COLUMNS and hz[3][1] == "" and hz[2][4] == "true"  # NaN -> vacío
    me = _read(paths["metrics"])
    assert tuple(me[0]) == CSV_METRICS_COLUMNS
    by = {r[0]: r for r in me[1:]}
    assert by["solar_fraction"] == ["solar_fraction", "0.70000", "fraction", "0.60000", "0.80000", "false"]
    assert by["longest_sun_window_s"][5] == "true" and by["n_sun_windows"][1] == "2"
    meta = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert meta["provenance"]["frame"] == "MOON_ME" and meta["warnings"]
    assert not any(line.startswith("#") for p in paths.values() if p.suffix == ".csv"
                   for line in p.read_text(encoding="utf-8").splitlines())


def test_csv_sin_potencia_ni_hub(tmp_path):
    ts = _read(write_csv_bundle(make_result(sphere=True, with_power=False), tmp_path)["timeseries"])
    assert all(r[-1] == "" for r in ts[1:])
    hz = _read(tmp_path / "horizon.csv")
    assert all(r[2] == "" for r in hz[1:])


def test_csv_longitudes_incoherentes(tmp_path):
    r = make_result()
    r.sky.et = ET[:-1]
    with pytest.raises(ValueError, match="distinta longitud"):
        write_csv_bundle(r, tmp_path)


def test_comparison_csv_varios_sitios(tmp_path):
    a, b = make_result().metrics, replace(make_result().metrics, solar_fraction=0.5, longest_sun_window_truncated=False)
    p = comparison_to_csv(comparison_table({"siteA": a, "siteB": b}), tmp_path / "comparison.csv")
    rows = _read(p)
    assert rows[0] == [*CSV_COMPARISON_COLUMNS, "siteA", "siteB"]
    by = {r[0]: r for r in rows[1:]}
    assert by["solar_fraction"] == ["solar_fraction", "fraction", "0.7", "0.5"] or \
        by["solar_fraction"][2:] == ["0.700000", "0.500000"]
    assert by["longest_sun_window_truncated"][2:] == ["true", "false"] and by["n_sun_windows"][2:] == ["2", "2"]
    # un solo sitio
    one = _read(comparison_to_csv(comparison_table({"solo": a}), tmp_path / "one.csv"))
    assert one[0] == [*CSV_COMPARISON_COLUMNS, "solo"] and len(one) == 1 + len(by)


# ---- enlace DTE (esquema 1.1.0) ---------------------------------------------------------
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from lsi.analysis.export import _contact_rows, _txt  # noqa: E402
from lsi.contracts import (  # noqa: E402
    CSV_LINK_CONTACTS_COLUMNS, CSV_LINK_DAILY_COLUMNS, CSV_LINK_STATIONS_COLUMNS, ContactWindow, GazetteerQuery,
    LinkResult, StationLinkSummary, utc_datetime_to_et,
)

ROOT = Path(__file__).resolve().parents[1]


def _cw(sid, tz, a, b, **kw):
    return ContactWindow(sid, sid, "x", tz, a, b, "", "", "", "", 0.0, 0.0, b - a, kw.pop("moon", 30.0), 12.0, **kw)


def make_link_result(station_name="Goldstone"):
    """Resultado sintético con enlace: DSS-14 (Los Ángeles) y DSS-63 (Madrid) en enero de 2000 (sin horario de verano)."""
    r = make_result()

    def ws(lab):
        return WindowSet(lab, (), ET[0], ET[-1], "c")
    cs = (_cw("DSS-14", "America/Los_Angeles", 1000.0, 2000.0, left_truncated=True, moon=40.0),
          _cw("DSS-63", "Europe/Madrid", 2500.0, 3400.0, right_truncated=True, moon=25.0))
    sts = (StationLinkSummary("DSS-14", station_name, "Goldstone", "America/Los_Angeles", 6.0, "publicado", 0.2, 0.5, 4.8, 1, 1000.0),
           StationLinkSummary("DSS-63", "Madrid", "Madrid", "Europe/Madrid", 6.0, "publicado", 0.25, 0.5, 6.0, 1, 900.0))
    lk = LinkResult("DSN", "DSN (3 complejos)", 5.0, ws("e"), ws("l"), ws("n"), {"DSS-14": ws("a"), "DSS-63": ws("b")}, cs, sts, ("nota",))
    m = replace(r.metrics, link_fraction=0.45, network_fraction=0.9, link_hours_per_day_mean=10.8, link_hours_per_day_min=None,
                longest_link_window_s=1000.0, longest_link_window_truncated=True, max_link_gap_s=500.0)
    return replace(r, link=lk, metrics=m)


def test_link_json_bloque_y_contactos(tmp_path):
    d = json.loads(write_json(make_link_result(), tmp_path / "l.json").read_text(encoding="utf-8"))
    validate_export(d)
    assert d["schema_version"] == "1.3.0" and d["link"]["direction"] == "receive"
    lk = d["link"]
    assert lk["network"] == {"id": "DSN", "label": "DSN (3 complejos)"} and lk["min_earth_elevation_deg"] == 5.0
    assert lk["station_min_elevation_deg"] is None and lk["link_fraction"] == 0.45 and lk["network_fraction"] == 0.9
    assert lk["hours_per_day_mean"] == 10.8 and lk["hours_per_day_min"] is None
    assert lk["longest_window_h"] == round(1000 / 3600, 4) and lk["longest_window_truncated"] is True
    assert lk["max_gap_h"] == round(500 / 3600, 4) and lk["notes"] == ["nota"]
    s0 = lk["stations"][0]
    assert s0["station_id"] == "DSS-14" and s0["tz"] == "America/Los_Angeles" and s0["max_moon_el_deg"] == 40.0
    assert s0["lat_deg"] == pytest.approx(35.4, abs=0.1) and s0["lon_deg_e"] == pytest.approx(243.11, abs=0.01)
    c0, c1 = d["contacts"]
    # enero: Los Ángeles UTC-8, Madrid UTC+1; la misma hora instantánea en UTC y local
    assert c0["start_utc_offset_h"] == -8.0 and c0["start_local"].endswith("-08:00") and c1["end_local"].endswith("+01:00")
    assert datetime.fromisoformat(c0["start_local"]) == datetime.fromisoformat(c0["start_utc"].replace("Z", "+00:00"))
    assert int(c0["start_local"][11:13]) == (int(c0["start_utc"][11:13]) - 8) % 24
    assert c0["left_truncated"] is True and c1["right_truncated"] is True and c0["duration_h"] == round(1000 / 3600, 4)
    day, = lk["daily"]
    assert day["link_hours"] == round((1000 + 900) / 3600, 4) and [x["station_id"] for x in day["stations"]] == ["DSS-14", "DSS-63"]
    assert day["gap_hours"] == round((2400 - 1900) / 3600, 4) and day["overlap_hours"] == 0.0


def test_link_horas_locales_con_y_sin_dst():
    def utc(y, m, dd, h=12):
        return utc_datetime_to_et(datetime(y, m, dd, h))
    verano, invierno = utc(2026, 7, 10), utc(2026, 1, 10)
    rows = _contact_rows([_cw("DSS-14", "America/Los_Angeles", verano, verano + 7200),
                          _cw("DSS-14", "America/Los_Angeles", invierno, invierno + 7200),
                          _cw("DSS-63", "Europe/Madrid", verano, verano + 7200),
                          _cw("DSS-63", "Europe/Madrid", invierno, invierno + 7200)])
    got = [(r["start_local"][:16], r["start_utc_offset_h"]) for r in rows]
    # el UTC exportado se redondea al segundo desde ET (TDB-UTC ~ 69 s): se compara solo hasta el minuto de la hora local
    assert [g[1] for g in got] == [-7.0, -8.0, 2.0, 1.0]
    assert [g[0][:13] for g in got] == ["2026-07-10T05", "2026-01-10T04", "2026-07-10T14", "2026-01-10T13"]
    # un contacto que cruza el cambio de horario de Madrid (2026-03-29 01:00 UTC): offset de fin distinto del de inicio
    cambio = utc(2026, 3, 29, 0)
    x, = _contact_rows([_cw("DSS-63", "Europe/Madrid", cambio, cambio + 4 * 3600)])
    assert (x["start_utc_offset_h"], x["end_utc_offset_h"]) == (1.0, 2.0)


def test_link_none_exporta_bloque_vacio_y_acepta_validacion(tmp_path):
    d = result_to_dict(make_result())
    validate_export(d)
    assert d["link"]["network"] is None and d["link"]["stations"] == [] and d["link"]["daily"] == [] and d["contacts"] == []
    assert d["link"]["link_fraction"] is None
    assert set(write_csv_bundle(make_result(), tmp_path)) == {"timeseries", "windows", "horizon", "metrics", "metadata"}
    assert not (tmp_path / "estaciones.csv").exists()
    d["link"]["stations"] = [{"station_id": "x"}]
    with pytest.raises(ExportSchemaError, match="network=null exige"):
        validate_export(d)


def test_validador_esquema_anterior_y_campos_nuevos():
    d = result_to_dict(make_link_result())
    old = copy.deepcopy(d)
    del old["link"], old["contacts"]
    old["schema_version"] = "1.0.0"
    validate_export(old)                                  # un export 1.0.0 sigue siendo válido
    new = copy.deepcopy(old)
    new["schema_version"] = EXPORT_SCHEMA_VERSION         # ...pero 1.1.0 sin link/contacts no
    with pytest.raises(ExportSchemaError) as ei:
        validate_export(new)
    assert "falta la clave obligatoria 'link'" in str(ei.value) and "falta la clave obligatoria 'contacts'" in str(ei.value)
    bad = copy.deepcopy(d)
    del bad["link"]["stations"][0]["tz"], bad["link"]["max_gap_h"], bad["contacts"][0]["end_local"]
    bad["contacts"][1]["station_id"] = "FANTASMA"
    with pytest.raises(ExportSchemaError) as ei:
        validate_export(bad)
    msg = str(ei.value)
    for frag in ("link: falta 'max_gap_h'", "link.stations[0]: faltan ['tz']", "contacts[0]: faltan ['end_local']",
                 "'FANTASMA' no está en link.stations"):
        assert frag in msg, msg
    other = copy.deepcopy(d)
    other["schema_version"] = "0.9.0"
    with pytest.raises(ExportSchemaError, match="schema_version='0.9.0'"):
        validate_export(other)


def test_link_csv_bundle_y_determinismo(tmp_path):
    p1 = write_csv_bundle(make_link_result(), tmp_path / "a")
    p2 = write_csv_bundle(make_link_result(), tmp_path / "b")
    assert all(p1[k].read_bytes() == p2[k].read_bytes() for k in p1)
    st, co, da = _read(p1["link_stations"]), _read(p1["link_contacts"]), _read(p1["link_daily"])
    assert tuple(st[0]) == CSV_LINK_STATIONS_COLUMNS and tuple(co[0]) == CSV_LINK_CONTACTS_COLUMNS
    assert tuple(da[0]) == CSV_LINK_DAILY_COLUMNS and len(st) == 3 and len(co) == 3 and len(da) == 2
    r0 = dict(zip(co[0], co[1]))
    assert r0["start_utc"].endswith("Z") and r0["start_local"].endswith("-08:00") and r0["start_utc_offset_h"] == "-8.00"
    assert r0["left_truncated"] == "true" and r0["max_earth_el_deg"] == "12.0000"
    assert dict(zip(da[0], da[1]))["station_hours"] == "DSS-14=0.2778;DSS-63=0.2500"
    assert all(len(x) == len(co[0]) for x in co)
    assert not any(ln.startswith("#") for p in p1.values() if p.suffix == ".csv" for ln in p.read_text(encoding="utf-8").splitlines())


def test_csv_inyeccion_de_formulas_sin_tocar_numeros(tmp_path):
    for t in ('=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"):
        assert _txt(t) == "'" + t
    assert _txt("Goldstone") == "Goldstone" and _txt("") == "" and _txt(None) == ""
    evil = "=cmd|'/C calc'!A0"
    r = make_link_result(station_name=evil)
    paths = write_csv_bundle(r, tmp_path)
    st = _read(paths["link_stations"])
    row = dict(zip(st[0], st[1]))
    assert row["name"] == "'" + evil
    # los números no se alteran: la longitud es un número puro y el offset negativo de Los Ángeles no lleva apóstrofo
    assert float(row["lon_deg_e"]) == pytest.approx(243.110462, abs=1e-6) and not row["lat_deg"].startswith("'")
    co = _read(paths["link_contacts"])
    assert dict(zip(co[0], co[1]))["start_utc_offset_h"] == "-8.00"
    cmpf = _read(comparison_to_csv(comparison_table({"=evil": make_result().metrics}), tmp_path / "c.csv"))
    assert cmpf[0][-1] == "'=evil"
    # el JSON conserva el texto original (no es una hoja de cálculo)
    assert result_to_dict(r)["link"]["stations"][0]["name"] == evil


@pytest.fixture(scope="module")
def malapert_14d():
    from lsi import pipeline as P
    from lsi.data import gazetteer as gz
    ctx = P.build_context(ROOT)
    df = gz.annotate_dem_coverage(gz.load_gazetteer(), ctx.dem_refs, float(ctx.cfg["gazetteer"]["dem_cover_margin_m"]))
    hits = gz.search(df, GazetteerQuery(text="Malapert", feature_types=("Mons",), limit=20))
    entry = next(h for h in hits if h.feature_id == 16338)
    return P.run_analysis(ctx, gz.to_request(entry, "2026-12-01T00:00:00", "2026-12-15T00:00:00", link_network="DSN"))


@pytest.mark.needs_spice
@pytest.mark.needs_dem
@pytest.mark.slow
def test_link_pipeline_real_malapert_ida_y_vuelta(malapert_14d, tmp_path):
    r = malapert_14d
    assert r.link is not None and r.link.network_id == "DSN" and r.link.contacts
    jp = write_json(r, tmp_path / "m.json", "2026-01-01T00:00:00Z")
    d = json.loads(jp.read_text(encoding="utf-8"), parse_constant=lambda c: pytest.fail(c))
    validate_export(d)
    assert d == json.loads(json.dumps(result_to_dict(r, "2026-01-01T00:00:00Z")))
    lk, m = d["link"], r.metrics
    assert lk["network"]["id"] == "DSN" and lk["link_fraction"] == pytest.approx(m.link_fraction, abs=1e-5)
    assert lk["hours_per_day_mean"] == pytest.approx(24 * m.link_fraction, abs=1e-3)
    assert [s["station_id"] for s in lk["stations"]] == [s.station_id for s in r.link.stations]
    assert all(s["lat_deg"] is not None and s["tz"] for s in lk["stations"])
    assert len(d["contacts"]) == len(r.link.contacts)
    for c in d["contacts"]:   # local e UTC son el mismo instante; el offset coincide con el de la hora local
        a = datetime.fromisoformat(c["start_local"])
        assert a == datetime.fromisoformat(c["start_utc"].replace("Z", "+00:00"))
        assert a.utcoffset().total_seconds() / 3600 == c["start_utc_offset_h"]
    assert len(lk["daily"]) == 14 and lk["daily"][0]["day_utc"] == "2026-12-01"
    assert sum(x["link_hours"] for x in lk["daily"]) == pytest.approx(24 * 14 * m.link_fraction, abs=0.05)
    p1 = write_csv_bundle(r, tmp_path / "x", "2026-01-01T00:00:00Z")
    p2 = write_csv_bundle(r, tmp_path / "y", "2026-01-01T00:00:00Z")
    assert all(p1[k].read_bytes() == p2[k].read_bytes() for k in p1)
    assert len(_read(p1["link_contacts"])) == 1 + len(r.link.contacts) and len(_read(p1["link_daily"])) == 1 + 14


def test_esquema_1_2_0_direccion_del_enlace_opcional_y_1_1_0_sigue_valido():
    """1.2.0 añade ``link.direction`` y ``link.network_fraction_by_direction``; un export 1.1.0 (sin ellos) sigue siendo válido."""
    r = make_link_result()
    r = replace(r, request=replace(r.request, link_direction="transmit"), network_fraction_by_direction={"receive": 0.99929, "transmit": 0.97991, "both": 0.97991})
    d = result_to_dict(r)
    validate_export(d)
    assert d["schema_version"] == "1.3.0" == EXPORT_SCHEMA_VERSION
    assert d["link"]["direction"] == "transmit"
    assert d["link"]["network_fraction_by_direction"] == {"receive": 0.99929, "transmit": 0.97991, "both": 0.97991}
    old = copy.deepcopy(d)
    del old["link"]["direction"], old["link"]["network_fraction_by_direction"]
    old["schema_version"] = "1.1.0"
    validate_export(old)                                   # 1.1.0: link/contacts sí, direction no
    new = copy.deepcopy(old)
    new["schema_version"] = EXPORT_SCHEMA_VERSION
    with pytest.raises(ExportSchemaError, match="link: falta 'direction'"):
        validate_export(new)                               # 1.2.0 exige los dos campos nuevos
    bad = copy.deepcopy(d)
    bad["link"]["direction"] = "sideways"
    with pytest.raises(ExportSchemaError, match="link.direction"):
        validate_export(bad)
    nolink = result_to_dict(replace(make_link_result(), link=None))
    assert nolink["link"]["direction"] is None and nolink["link"]["network_fraction_by_direction"] is None
    validate_export(nolink)


def test_esquema_1_3_0_pendiente_en_huella_y_1_2_0_sigue_valido():
    from lsi.contracts import SlopeScale
    r = make_result()
    r = replace(r, slope_r50=SlopeScale(50.0, 3.1, 5.3, 8.9, 0.0, 10.0, 317, "slp", False),
                slope_r100=SlopeScale(100.0, 4.3, 8.8, 15.2, 3.3, 10.0, 1257, "slp", False),
                dem_edge_distance_m=4321.0, footprint_touches_dem_edge=False)
    d = result_to_dict(r)
    validate_export(d)
    assert d["schema_version"] == EXPORT_SCHEMA_VERSION == "1.3.0"
    sf = d["slope_footprint"]
    assert sf["slope_r50"]["p90_deg"] == 5.3 and sf["slope_r100"]["pct_area_above_limit"] == 3.3
    assert sf["footprint_touches_dem_edge"] is False and sf["dem_edge_distance_m"] == 4321.0
    old = copy.deepcopy(d)
    del old["slope_footprint"]
    old["schema_version"] = "1.2.0"
    validate_export(old)                                   # 1.2.0 sin slope_footprint sigue siendo válido
    bad = copy.deepcopy(d)
    del bad["slope_footprint"]["slope_r100"]
    with pytest.raises(ExportSchemaError, match="slope_r100"):
        validate_export(bad)
