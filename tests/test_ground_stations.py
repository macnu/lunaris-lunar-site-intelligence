"""Estaciones terrestres, cobertura de red, ventanas de contacto y hora local (conectividad DTE).

Verdad independiente: JPL Horizons (``tests/golden/horizons_stations_2026-12.json``, guardado con
``scripts/fetch_horizons_stations.py``; los tests NO usan la red salvo ``test_live_horizons`` que se salta si falla) y los
valores publicados (DSN 810-005/301 Rev. P; NAIF earth_topo_260814.tf) escritos aquí a mano.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from lsi.astronomy import ground_stations as gs
from lsi.astronomy import spice_engine
from lsi.contracts import MOON_RADIUS_KM, ContactWindow

ROOT = Path(__file__).resolve().parents[1]
H = json.loads((ROOT / "tests" / "golden" / "horizons_stations_2026-12.json").read_text(encoding="utf-8"))
DSN = ("DSS-14", "DSS-43", "DSS-63")
# Tolerancia frente a Horizons (ITRF93): IAU_EARTH da ≤ 0,072° medido en 36 casos (docs/science/luna-spice-sitios.md);
# 0,1° deja margen sin ocultar un fallo de signo/longitud (que daría grados) y mueve una salida/puesta < 30 s.
TOL_EL_DEG = 0.10
TOL_CROSSING_S = 120.0


def _et(utc: str) -> float:
    return spice_engine.utc_to_et(utc.replace(" ", "T") + ":00" if len(utc) == 16 else utc)


@pytest.fixture(scope="module")
def net():
    spice_engine.load_kernels()
    return gs.get_network("DSN")


# ---------------------------------------------------------------------------------------- configuración verificada
def test_config_dsn_matches_published_values_and_is_default():
    cfg = gs.load_config()
    assert cfg["default_network"] == "DSN"
    n = gs.get_network("DSN", cfg=cfg)
    assert [s.id for s in n.stations] == ["DSS-14", "DSS-63", "DSS-43"]
    s14 = cfg["stations"]["DSS-14"]   # 810-005/301 Rev. P tabla 5: 35°25'33.24312" N, 243°06'37.66244" E, h 1001.390 m
    assert s14["lat_deg"] == pytest.approx(35 + 25 / 60 + 33.24312 / 3600, abs=1e-8)
    assert s14["lon_deg_e"] == pytest.approx(243 + 6 / 60 + 37.66244 / 3600, abs=1e-8)
    assert s14["alt_m"] == 1001.390
    assert {s.min_elevation_deg for s in n.stations} == {6.0}   # 810-005/301 §2.2.4: receive ≈ 6° [pub]
    for sid in DSN:
        assert cfg["stations"][sid]["verified"] and cfg["stations"][sid]["source_position"].startswith("DSN 810-005")


# posiciones ITRF93 época 2003.0 de NAIF earth_topo_260814.tf (tabla 2 de 810-005/301): fuente independiente de la tabla 5
NAIF_XYZ_M = {"DSS-14": (-2353621.420, -4641341.472, 3677052.318), "DSS-43": (-4460894.917, 2682361.507, -3674748.152),
              "DSS-63": (4849092.518, -360180.3480, 4115109.251)}


@pytest.mark.parametrize("sid", DSN)
def test_station_geodetic_agrees_with_naif_cartesian(sid):
    st = gs.get_network("DSN").stations[[s.id for s in gs.get_network("DSN").stations].index(sid)]
    d = np.linalg.norm(gs.station_position_km(st) * 1000.0 - np.array(NAIF_XYZ_M[sid]))
    assert d < 1.0, f"{sid}: geodésicas y cartesianas de NAIF difieren {d:.3f} m"   # medido: ~cm


def test_estrack_positions_ok_but_elevation_is_flagged_unverified():
    n = gs.get_network("ESTRACK")
    assert {s.id for s in n.stations} == {"NNO-1", "CEB-1", "MLG-1"}
    assert all(s.min_elevation_deg == 6.0 and not s.verified for s in n.stations)
    assert any("SUPUESTA" in x for x in n.notes)
    cfg = gs.load_config()
    assert all(not cfg["stations"][i]["default_enabled"] for i in ("NNO-1", "CEB-1", "MLG-1"))
    assert "NSN" not in cfg["networks"] and cfg["networks_not_available"]["NSN"]["status"] == "a verificar"
    ceb = cfg["stations"]["CEB-1"]   # NAIF NDOSL_CB1D: 40.4526908333 N, -4.3675472778 E
    assert (ceb["lat_deg"], ceb["lon_deg_e"] - 360.0) == pytest.approx((40.4526908333, -4.3675472778), abs=1e-8)


def test_custom_network_and_none():
    n = gs.get_network("custom", custom=[(40.0, -4.0, 10.0, "Europe/Madrid")])
    assert n.stations[0].min_elevation_deg == 10.0 and n.stations[0].tz == "Europe/Madrid"
    with pytest.raises(ValueError):
        gs.get_network("custom")
    with pytest.raises(ValueError):
        gs.get_network("NOPE")
    assert gs.make_link_context(np.array([0.0, 1.0]), None) is None   # network=None → conectividad geométrica


# ---------------------------------------------------------------------------------------- contraste con Horizons
@pytest.mark.needs_spice
@pytest.mark.parametrize("sid", DSN)
def test_moon_elevation_matches_horizons_at_12_instants(net, sid):
    st = next(s for s in net.stations if s.id == sid)
    et = np.array([_et(t) for t in H["instants_utc"]])
    ours = gs.moon_elevation_deg(et, st)
    diff = np.abs(ours - np.array(H["stations"][sid]["instants_el_deg"]))
    assert len(diff) >= 10
    assert diff.max() < TOL_EL_DEG, f"{sid}: diferencia máxima {diff.max():.4f}° frente a Horizons"


@pytest.mark.needs_spice
@pytest.mark.parametrize("sid", DSN)
def test_station_windows_one_day_match_horizons_crossings(net, sid):
    """Ventanas de la estación (Luna ≥ 6°) el 2026-12-11 frente a los cruces de 6° de la serie de Horizons a 10 min."""
    st = next(s for s in net.stations if s.id == sid)
    day = H["stations"][sid]
    t = np.array([_et(_horizons_utc(u)) for u in day["day_utc"]])
    el = np.array(day["day_el_deg"])
    ref = gs.cross_intervals(t, el - st.min_elevation_deg)               # misma interpolación sobre la serie de Horizons
    ours = gs.cross_intervals(t, gs.moon_elevation_deg(t, st) - st.min_elevation_deg)
    assert len(ours) == len(ref) >= 1
    inner = lambda iv: [x for x in iv.ravel() if t[0] < x < t[-1]]       # noqa: E731  (los extremos del día no son cruces)
    assert len(inner(ours)) == len(inner(ref)) >= 2
    assert np.max(np.abs(np.array(inner(ours)) - np.array(inner(ref)))) < TOL_CROSSING_S


def _horizons_utc(u: str) -> str:
    mon = {"Dec": "12"}[u[5:8]]
    return f"{u[:4]}-{mon}-{u[9:11]}T{u[12:17]}:00"


@pytest.mark.needs_spice
def test_live_horizons_single_instant(net):
    """Contraste en vivo (se salta sin red): mismo instante que el primer caso guardado."""
    requests = pytest.importorskip("requests")
    st = next(s for s in net.stations if s.id == "DSS-14")
    p = {"format": "json", "COMMAND": "'301'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
         "CENTER": "'coord@399'", "COORD_TYPE": "'GEODETIC'", "SITE_COORD": f"'{st.lon_deg_e},{st.lat_deg},{st.alt_m / 1000}'",
         "TLIST": "'2026-12-11 17:00'", "QUANTITIES": "'4'", "ANG_FORMAT": "'DEG'"}
    try:
        r = requests.get("https://ssd.jpl.nasa.gov/api/horizons.api", params=p, timeout=30)
        r.raise_for_status()
        el = float(r.json()["result"].split("$$SOE")[1].split("$$EOE")[0].split()[-1])
    except Exception as e:   # noqa: BLE001  (sin red o formato distinto: no es un fallo del motor)
        pytest.skip(f"JPL Horizons no disponible: {e}")
    assert abs(gs.moon_elevation_deg(np.array([_et("2026-12-11 17:00")]), st)[0] - el) < TOL_EL_DEG


# ---------------------------------------------------------------------------------------- IAU_EARTH, paralaje de sitio
def test_cross_intervals_synthetic():
    t = np.arange(0.0, 100.0, 10.0)
    iv = gs.cross_intervals(t, np.sin(t / 15.0) - 0.5)   # g ≥ 0 en un tramo central, cruces interpolados
    assert iv.shape == (1, 2) and 0 < iv[0, 0] < iv[0, 1] < 100
    assert gs.cross_intervals(t, np.ones_like(t)).tolist() == [[0.0, 90.0]]   # todo visible: truncada a la rejilla
    assert gs.cross_intervals(t, -np.ones_like(t)).shape == (0, 2)


@pytest.mark.needs_spice
@pytest.mark.parametrize("lat,lon", [(-89.5626, 215.4724), (-85.98, 2.6), (0.0, 90.0)])
def test_same_mask_for_all_lunar_sites_error_is_below_lunar_angular_radius(net, lat, lon):
    """La cobertura se calcula con el centro de la Luna. Para un punto de la superficie la elevación desde la estación
    cambia como mucho el radio angular lunar (asin(R/d) ≤ 0,29° en el perigeo): MEDIDO 0,283° y ≤ 0,08 puntos
    porcentuales de cobertura (docs/science/luna-spice-sitios.md)."""
    import spiceypy as sp
    et = spice_engine.et_grid(_et("2026-12-01T00:00:00"), _et("2026-12-15T00:00:00"), 600.0)
    la, lo = np.radians(lat), np.radians(lon)
    lander_me = MOON_RADIUS_KM * np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    with spice_engine.SPICE_LOCK:
        rot = np.array([sp.pxform("MOON_ME", "IAU_EARTH", e) for e in et])
    pos = gs.moon_position_earth_fixed(et) + rot @ lander_me
    worst, fc, fl = 0.0, [], []
    for s in net.stations:
        v = pos - gs.station_position_km(s)
        el = np.degrees(np.arcsin((v @ gs.station_up(s)) / np.linalg.norm(v, axis=1)))
        el0 = gs.moon_elevation_deg(et, s)
        worst = max(worst, float(np.abs(el - el0).max()))
        fc.append(np.mean(el0 >= s.min_elevation_deg))
        fl.append(np.mean(el >= s.min_elevation_deg))
    assert worst < 0.30
    assert np.abs(np.array(fc) - np.array(fl)).max() < 0.005


# ---------------------------------------------------------------------------------------- hora local
@pytest.mark.parametrize("utc,tz,abbr,off_h", [
    ("2026-10-24T12:00:00", "Europe/Madrid", "CEST", 2),     # antes del cambio del 25/10/2026
    ("2026-10-26T12:00:00", "Europe/Madrid", "CET", 1),
    ("2027-03-27T12:00:00", "Europe/Madrid", "CET", 1),      # antes del cambio del 28/03/2027
    ("2027-03-29T12:00:00", "Europe/Madrid", "CEST", 2),
    ("2026-10-03T12:00:00", "Australia/Canberra", "AEST", 10),   # DST de Australia empieza el 04/10/2026
    ("2026-10-05T12:00:00", "Australia/Canberra", "AEDT", 11),
    ("2027-04-03T12:00:00", "Australia/Canberra", "AEDT", 11),   # termina el 04/04/2027
    ("2027-04-05T12:00:00", "Australia/Canberra", "AEST", 10),
    ("2026-10-31T12:00:00", "America/Los_Angeles", "PDT", -7),   # termina el 01/11/2026
    ("2026-11-02T12:00:00", "America/Los_Angeles", "PST", -8),
])
def test_local_time_follows_dst(utc, tz, abbr, off_h):
    loc = gs.et_to_local(spice_engine.utc_to_et(utc), tz)
    assert loc.tzname() == abbr and loc.utcoffset().total_seconds() == off_h * 3600
    back = loc.astimezone(timezone.utc).replace(tzinfo=None)
    assert abs((back - datetime.fromisoformat(utc)).total_seconds()) < 0.01   # TDB−TT < 2 ms


def test_station_time_zones_are_the_official_ones():
    cfg = gs.load_config()["stations"]
    assert cfg["DSS-14"]["tz"] == "America/Los_Angeles" and cfg["DSS-63"]["tz"] == "Europe/Madrid"
    assert cfg["DSS-43"]["tz"] in ("Australia/Canberra", "Australia/Sydney")   # ACT = AEST/AEDT, como Sydney


def test_local_mean_solar_hours():
    et = spice_engine.utc_to_et("2026-12-11T12:00:00")
    circ = lambda a, b: abs((a - b + 12.0) % 24.0 - 12.0)   # noqa: E731  (distancia en el reloj de 24 h)
    assert circ(gs.local_mean_solar_hours(et, 0.0), 12.0) < 1e-3
    assert circ(gs.local_mean_solar_hours(et, 180.0), 0.0) < 1e-3
    assert circ(gs.local_mean_solar_hours(et, -75.0), 7.0) < 1e-3


# ---------------------------------------------------------------------------------------- ventanas de contacto
@pytest.mark.needs_spice
def test_contact_windows_fields_local_time_and_sum_of_stations_covers_network(net):
    et = spice_engine.et_grid(_et("2026-12-10T00:00:00"), _et("2026-12-14T00:00:00"), 600.0)
    cov = gs.network_coverage(et, net)
    cw = gs.contact_windows(cov)                       # sin restricción del lander: solo Luna vista desde la estación
    assert cw and all(isinstance(c, ContactWindow) for c in cw)
    assert [c.start_et for c in cw] == sorted(c.start_et for c in cw)
    c = next(c for c in cw if c.station_id == "DSS-63" and c.start_utc.startswith("2026-12-11"))
    assert c.start_local.endswith("CET") and c.tz == "Europe/Madrid"
    assert c.start_local[11:16] == f"{(int(c.start_utc[11:13]) + 1) % 24:02d}:{c.start_utc[14:16]}"   # CET = UTC+1 en diciembre
    assert c.duration_s == pytest.approx(c.end_et - c.start_et) and 3 * 3600 < c.duration_s < 16 * 3600
    assert c.max_moon_el_deg > 6.0 and 0.0 <= c.start_solar_h < 24.0
    # suma de coberturas por estación ≥ cobertura de la red (unión)
    T = et[-1] - et[0]
    per = [sum(x.duration_s for x in cw if x.station_id == s.id) / T for s in net.stations]
    union = gs.mt.total_duration(cov.any_intervals(), et[0], et[-1]) / T
    assert sum(per) >= union - 1e-9 and union > 0.99


@pytest.mark.needs_spice
def test_daily_table_hours_overlap_and_gaps(net):
    et = spice_engine.et_grid(_et("2026-12-10T00:00:00"), _et("2026-12-13T00:00:00"), 600.0)
    cov = gs.network_coverage(et, net)
    geo = np.array([[et[0], et[0] + 30 * 3600.0]])   # el lander solo ve la Tierra las primeras 30 h
    cw = gs.contact_windows(cov, geo, np.zeros(len(et)))
    rows = gs.daily_contact_table(cw, et[0], et[-1])
    assert [r["day_utc"] for r in rows] == ["2026-12-10", "2026-12-11", "2026-12-12"]
    for r in rows:
        assert r["link_hours"] + r["gap_hours"] == pytest.approx(24.0, abs=1e-6)
        assert 0.0 <= r["overlap_hours"] <= r["link_hours"] + 1e-9
    assert rows[0]["gap_hours"] == pytest.approx(0.0, abs=0.5) and rows[2]["link_hours"] == 0.0
    assert rows[2]["text"] == "sin enlace" and any(z in rows[0]["text"] for z in ("PST", "CET", "AEDT"))
    assert sum(r["link_hours"] for r in rows) == pytest.approx(30.0, abs=0.3)


# ---------------------------------------------------------------------------------------- B2: huecos espurios de traspaso
def test_handoff_gap_of_a_few_seconds_is_merged_and_real_gaps_survive():
    """Dos estaciones a ~6° en traspaso: los cruces lineales de la rejilla de 600 s dejan un hueco de 3 s que no existe (revision-enlace B2,
    2-feb-2027 05:41:28 UTC). ``any_intervals`` lo fusiona (tolerancia ``handoff_merge_tol_s``); un hueco real (> tolerancia) se conserva."""
    tol = gs.handoff_merge_tol_s()
    assert 3.4 < tol < 44.0                       # entre el artefacto mayor medido (3,4 s) y el hueco real más corto medido (44 s)
    t = np.arange(0.0, 6001.0, 600.0)
    # A baja por 6° en 3000,0 s y B sube por 6° en 3003,4 s (elevaciones lineales de 0,01°/s): hueco de 3,4 s
    a = 6.0 - 0.01 * (t - 3000.0)
    b = 6.0 + 0.01 * (t - 3003.4)
    cov = gs.NetworkCoverage(t, gs.Network("x", "x", (gs.Station("A", "A", 0, 0, 0, 6.0), gs.Station("B", "B", 0, 0, 0, 6.0))),
                             np.vstack((a, b)))
    raw = gs.mt.union(*[iv for iv in cov.station_intervals()])
    assert len(raw) == 2 and raw[1, 0] - raw[0, 1] == pytest.approx(3.4, abs=0.05)      # el hueco espurio existe sin fusionar
    merged = cov.any_intervals()
    assert len(merged) == 1 and merged[0, 0] == pytest.approx(0.0)
    assert merged[-1, 1] == pytest.approx(t[-1], abs=1e-6)
    # hueco real de 60 s (> tolerancia): sigue siendo un hueco
    b2 = 6.0 + 0.01 * (t - 3060.0)
    cov2 = gs.NetworkCoverage(t, cov.network, np.vstack((a, b2)))
    real = cov2.any_intervals()
    assert len(real) == 2 and real[1, 0] - real[0, 1] == pytest.approx(60.0, abs=0.05)
    assert len(cov2.any_intervals(0.0)) == 2 and len(cov.any_intervals(0.0)) == 2 and len(cov.any_intervals(10.0)) == 1


@pytest.mark.needs_spice
def test_dsn_dec_2026_to_jun_2027_handoff_gaps_are_real_only(net):
    """1-dic-2026 → 1-jun-2027 a 600 s: ya no hay huecos de red < tolerancia (antes 0,4 y 3,4 s); los reales (≥ 44 s medidos con verdad a 2 s) quedan."""
    et = spice_engine.et_grid(_et("2026-12-01T00:00:00"), _et("2027-06-01T00:00:00"), 600.0)
    cov = gs.network_coverage(et, net)
    raw, merged = cov.any_intervals(0.0), cov.any_intervals()
    g_raw, g = raw[1:, 0] - raw[:-1, 1], merged[1:, 0] - merged[:-1, 1]
    assert (g_raw < gs.handoff_merge_tol_s()).sum() == 2 and (g >= gs.handoff_merge_tol_s()).all()
    assert len(g) == len(g_raw) - 2 and g.min() > 40.0


# ---------------------------------------------------------------------------------------- sentido del enlace
def test_link_direction_elevations_from_config_and_default_is_receive():
    rx, tx, both = (gs.get_network("DSN", link_direction=d) for d in ("receive", "transmit", "both"))
    assert gs.get_network("DSN").direction == "receive"
    assert [s.min_elevation_deg for s in rx.stations] == [6.0] * 3
    assert [s.min_elevation_deg for s in tx.stations] == [10.1] * 3                    # 810-005/301 Rev. P §2.2.1 [pub]
    assert [s.min_elevation_deg for s in both.stations] == [10.1] * 3                  # intersección = la mayor
    assert all(s.rx_min_elevation_deg == 6.0 and s.tx_min_elevation_deg == 10.1 for s in tx.stations)
    assert not rx.notes and any("10,1°" in n and "NO se modelan" in n for n in tx.notes)
    est = gs.get_network("ESTRACK", link_direction="transmit")                         # sin límite de transmisión publicado: el de recepción [sup]
    assert [s.min_elevation_deg for s in est.stations] == [6.0] * 3 and any("sin elevación mínima de transmisión" in n for n in est.notes)
    forced = gs.get_network("DSN", min_elevation_deg=8.0, link_direction="transmit")   # la sensibilidad del usuario manda sobre el sentido
    assert [s.min_elevation_deg for s in forced.stations] == [8.0] * 3
    with pytest.raises(ValueError, match="link_direction"):
        gs.get_network("DSN", link_direction="up")


@pytest.mark.needs_spice
def test_network_coverage_by_direction_dec_2026():
    """Cobertura de red dic-2026 por sentido: recepción 99,93 % (revision-enlace §2), transmisión ~97,99 % (10,1°); ambos = transmisión."""
    spice_engine.load_kernels()
    et = spice_engine.et_grid(_et("2026-12-01T00:00:00"), _et("2027-01-01T00:00:00"), 600.0)
    d = gs.network_coverage(et, gs.get_network("DSN")).fraction_by_direction()
    assert set(d) == {"receive", "transmit", "both"}
    assert d["receive"] == pytest.approx(0.99929, abs=3e-4) and d["transmit"] == pytest.approx(0.9799, abs=3e-3)
    assert d["both"] == pytest.approx(d["transmit"]) and d["transmit"] < d["receive"]
    # el mismo número sale de construir la red en transmisión (cobertura propia) y de la de recepción con otro umbral
    tx = gs.network_coverage(et, gs.get_network("DSN", link_direction="transmit"))
    assert gs.mt.total_duration(tx.any_intervals(), et[0], et[-1]) / (et[-1] - et[0]) == pytest.approx(d["transmit"], abs=1e-9)
    forced = gs.network_coverage(et, gs.get_network("DSN", min_elevation_deg=10.1)).fraction_by_direction()
    assert forced["receive"] == pytest.approx(forced["transmit"]) == pytest.approx(d["transmit"], abs=1e-9)


# ---------------------------------------------------------------------------------------- B3: tabla diaria con ventanas REALES
def _cw(sid, tz, utc0, utc1):
    """Ventana de contacto a partir de dos instantes UTC (las de revision-enlace §4 para el 11-13 dic 2026)."""
    a, b = spice_engine.utc_to_et(utc0), spice_engine.utc_to_et(utc1)
    lo, hi = gs.et_to_local(a, tz), gs.et_to_local(b, tz)
    return ContactWindow(sid, sid, sid, tz, a, b, utc0, utc1, lo.strftime("%Y-%m-%d %H:%M:%S ") + lo.tzname(),
                         hi.strftime("%Y-%m-%d %H:%M:%S ") + hi.tzname(), 0.0, 0.0, b - a, 30.0, None)


@pytest.mark.needs_spice
def test_daily_table_day12_shows_real_windows_not_fused_pieces():
    """Canberra y Goldstone, 12-dic-2026: la tabla ya NO une el final de una ventana con el inicio de la siguiente («Canberra 09:34-22:11
    AEDT», «Goldstone 10:21-18:12 PST» no existen). Muestra las ventanas reales, enteras, con «continúa…» y las horas del día aparte."""
    spice_engine.load_kernels()
    cw = [_cw("DSS-43", "Australia/Canberra", "2026-12-11T21:37:09", "2026-12-12T11:11:57"),
          _cw("DSS-43", "Australia/Canberra", "2026-12-12T22:34:50", "2026-12-13T11:45:31"),
          _cw("DSS-14", "America/Los_Angeles", "2026-12-11T17:48:05", "2026-12-12T02:12:50"),
          _cw("DSS-14", "America/Los_Angeles", "2026-12-12T18:21:59", "2026-12-13T03:13:58"),
          _cw("DSS-63", "Europe/Madrid", "2026-12-12T11:00:20", "2026-12-12T19:06:06")]
    t0, t1 = spice_engine.utc_to_et("2026-12-11T00:00:00"), spice_engine.utc_to_et("2026-12-14T00:00:00")
    row = next(r for r in gs.daily_contact_table(cw, t0, t1) if r["day_utc"] == "2026-12-12")
    cbr, gold, mad = (row["stations"][s] for s in ("DSS-43", "DSS-14", "DSS-63"))
    assert cbr["local"] == ["08:37-22:12 AEDT (continúa del día anterior)", "13/12 09:35-22:46 AEDT (continúa al día siguiente)"]
    assert gold["local"] == ["11/12 09:48-18:13 PST (continúa del día anterior)", "10:22-19:14 PST (continúa al día siguiente)"]
    assert mad["local"] == ["12:00-20:06 CET"]
    for bad in ("09:34-22:11", "09:34-22:12", "10:21-18:12", "10:21-18:13", "10:22-18:13"):    # las ventanas fusionadas que no existen
        assert bad not in row["text"], bad
    # minutos REDONDEADOS, no truncados: 22:11:57 → 22:12 (antes 22:11); 18:12:50 → 18:13 (antes 18:12)
    assert [w["continues_prev"] for w in cbr["windows"]] == [True, False] and [w["continues_next"] for w in cbr["windows"]] == [False, True]
    # horas por estación DENTRO del día, como número aparte (no la duración de la ventana entera)
    assert cbr["hours"] == pytest.approx((40317 + 5110) / 3600.0, abs=1e-3)   # 00:00-11:11:57 + 22:34:50-24:00 = 12,62 h
    assert mad["hours"] == pytest.approx((19 * 3600 + 6 * 60 + 6 - 11 * 3600 - 20) / 3600.0, abs=1e-3)
    assert row["link_hours"] + row["gap_hours"] == pytest.approx(24.0, abs=1e-6)
    # los dos días vecinos: la misma ventana aparece enteras y etiquetada (no recortada)
    r13 = next(r for r in gs.daily_contact_table(cw, t0, t1) if r["day_utc"] == "2026-12-13")
    assert r13["stations"]["DSS-43"]["local"][0].startswith("09:35-22:46 AEDT (continúa del día anterior)")


# ---------------------------------------------------------------------------------------- estaciones adicionales (14/11/2026)
# Valores leídos en documentos oficiales (data/raw/stations_docs/, docs/validation/estaciones-adicionales.md); escritos a mano.
EFM_COORDS = {   # ESTRACK Facilities Manual DOPS-ESTR-OPS-MAN-1001-OPS-ONN iss.1 rev.1 (19/09/2008), Tablas 2 (p. 21) y 8 (p. 77), GRS80
    "CEB-1": (40 + 27 / 60 + 9.68 / 3600, -(4 + 22 / 60 + 3.18 / 3600), 794.095),
    "NNO-1": (-(31 + 2 / 60 + 53.61 / 3600), 116 + 11 / 60 + 29.40 / 3600, 252.2558)}
EFM_MASK_MAX_DEG = {"CEB-1": 5.5, "NNO-1": 8.5}      # figuras 7 (p. 21) y 35 (p. 78): máscara por acimut, máximo leído a ojo ±0,3°
NAIF_WS1S = (32 + 32 / 60 + 26.7178 / 3600, 253 + 23 / 60 + 16.4417 / 3600, 1456.545)   # ndosl_190716_v02.tf, fila WS1S


def test_estrack_positions_match_efm_and_mask_exceeds_assumed_6deg_only_at_nno():
    cfg = gs.load_config()["stations"]
    for sid, (la, lo, h) in EFM_COORDS.items():
        assert cfg[sid]["lat_deg"] == pytest.approx(la, abs=3e-5)                   # 3e-5° ≈ 3 m: EFM redondea a 0,01"
        assert cfg[sid]["lon_deg_e"] % 360.0 == pytest.approx(lo % 360.0, abs=3e-5)
        assert cfg[sid]["alt_m"] == pytest.approx(h, abs=0.05)
        assert cfg[sid]["horizon_mask_max_deg_read"] == EFM_MASK_MAX_DEG[sid]
    assert cfg["CEB-1"]["horizon_mask_max_deg_read"] < 6.0 < cfg["NNO-1"]["horizon_mask_max_deg_read"]
    # decisión documentada: la máscara es por acimut, no un escalar publicado; ESTRACK sigue con 6° [sup] (resultados sin cambio)
    assert all(s.min_elevation_deg == 6.0 and not s.verified for s in gs.get_network("ESTRACK").stations)
    assert "MÁSCARA DE HORIZONTE POR ACIMUT" in cfg["NNO-1"]["source_elevation"]


def test_unverified_stations_are_outside_every_network_and_never_default():
    cfg = gs.load_config()
    un = {k: v for k, v in cfg["stations_unverified"].items() if not k.startswith("_")}
    assert set(un) == {"WS1", "LEGS-1", "LEGS-2", "UDSC-64"}
    in_networks = {sid for n in cfg["networks"].values() for sid in n["stations"]}
    assert not in_networks & set(un) and not set(un) & set(cfg["stations"])
    assert cfg["default_network"] == "DSN" and all(not s["verified"] and not s["default_enabled"] and s["min_elevation_deg"] is None for s in un.values())
    assert set(cfg["networks"]) == {"DSN", "ESTRACK", "DSN+ESTRACK"}           # sin elevación verificada no hay red NSN
    for sid in un:
        with pytest.raises(ValueError):
            gs.get_network(sid)
    assert cfg["networks_not_available"]["NSN"]["status"] == "a verificar"


def test_unverified_station_coordinates_match_sources():
    un = gs.load_config()["stations_unverified"]
    assert (un["WS1"]["lat_deg"], un["WS1"]["lon_deg_e"], un["WS1"]["alt_m"]) == pytest.approx(NAIF_WS1S, abs=1e-6)
    assert (un["WS1"]["lat_deg"], un["WS1"]["lon_deg_e"] - 360.0) == pytest.approx((32 + 32 / 60 + 27 / 3600, -(106 + 36 / 60 + 44 / 3600)), abs=2e-3)  # NEN UG §9.2 (a 1")
    assert (un["LEGS-1"]["lat_deg"], un["LEGS-1"]["lon_deg_e"] - 360.0) == (32.544863, -106.612504)     # LEGS Brochure r20
    assert (un["LEGS-2"]["lat_deg"], un["LEGS-2"]["lon_deg_e"]) == (-33.231224, 20.58163)               # LEGS Brochure r20 (TBD)
    assert (un["UDSC-64"]["lat_deg"], un["UDSC-64"]["lon_deg_e"], un["UDSC-64"]["alt_m"]) == pytest.approx((36 + 7 / 60 + 54 / 3600, 138 + 21 / 60 + 54 / 3600, 1456.0))  # JAXA/ISAS
    assert un["LEGS-1"]["alt_m"] is None and "FUTURA" in un["LEGS-1"]["lunar_dte"]


def test_all_station_time_zones_are_valid_iana_and_dst_at_a_change_date():
    from zoneinfo import ZoneInfo
    cfg = gs.load_config()
    zones = {s["tz"] for s in cfg["stations"].values()} | {s["tz"] for k, s in cfg["stations_unverified"].items() if not k.startswith("_")}
    for z in zones:
        ZoneInfo(z)
    # White Sands (America/Denver): DST termina el 01/11/2026; Matjiesfontein sin DST; Usuda sin DST
    for utc, tz, abbr in (("2026-10-31T12:00:00", "America/Denver", "MDT"), ("2026-11-02T12:00:00", "America/Denver", "MST"),
                          ("2026-11-02T12:00:00", "Africa/Johannesburg", "SAST"), ("2026-11-02T12:00:00", "Asia/Tokyo", "JST")):
        assert gs.et_to_local(spice_engine.utc_to_et(utc), tz).tzname() == abbr


@pytest.mark.needs_spice
def test_default_network_unchanged_and_estrack_and_combined_networks_compute_local_windows():
    spice_engine.load_kernels()
    et = spice_engine.et_grid(_et("2026-12-01T00:00:00"), _et("2027-01-01T00:00:00"), 600.0)
    dsn = gs.network_coverage(et, gs.get_network("DSN"))
    assert gs.mt.total_duration(dsn.any_intervals(), et[0], et[-1]) / (et[-1] - et[0]) == pytest.approx(0.99929, abs=3e-4)
    comb = gs.network_coverage(et, gs.get_network("DSN+ESTRACK"))
    cw = gs.contact_windows(comb)
    assert {c.station_id for c in cw} >= {"DSS-14", "NNO-1"} and all(c.start_local and c.tz for c in cw)
    c = next(c for c in cw if c.station_id == "NNO-1")
    assert c.start_local.endswith("AWST") and c.tz == "Australia/Perth"
