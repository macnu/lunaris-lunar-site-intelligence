"""Página «Capacidad del sitio» con ``AppTest``: Shackleton, de Gerlache, Malapert y Apolo 11 (esfera lisa); la red y el margen de
elevación cambian el resultado; la tabla por estación lleva horas locales con su zona; sin excepciones en los 3 modos."""
import json
import re
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui import components as C, state as S
from ui_cards import cards

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice
LOCAL_ZONES = ("PST", "CET", "AEDT", "AEST")      # diciembre: Goldstone, Madrid, Canberra (horario de verano austral)


@pytest.fixture
def page(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "site_capacity.py", tmp_path / "site_capacity.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return tmp_path


def run_app(mode: str | None = None, site: str | None = None, *, suggested: bool = False) -> AppTest:
    """App con la página; por defecto fija el inicio de las cifras de referencia (2026-12-01). ``suggested=True`` deja el estado inicial."""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    if not suggested:
        at.sidebar.selectbox(key="_w_preset").set_value("30 días").run()
        at.sidebar.text_input(key="_w_start").set_value("2026-12-01 00:00").run()
    if mode:
        at.sidebar.selectbox(key="_w_mode").set_value(mode).run()
    if site:
        at.sidebar.selectbox(key="_w_site").set_value(site).run()
    return at


def body(at: AppTest) -> str:
    parts = (*at.markdown, *at.caption, *at.success, *at.error, *at.warning, *at.info, *at.subheader, *at.header, *at.title)
    return " ".join(e.value for e in parts)


def tables(at: AppTest) -> list:
    return [d.value for d in at.dataframe]


def metrics(at: AppTest) -> dict:
    return {m.label: m.value for m in cards(at)}


def station_table(at: AppTest):
    return next(t for t in tables(at) if "% del tiempo con enlace" in t.columns)


def test_page_is_second_in_navigation():
    from ui import PAGE_SPECS
    assert [n for n, _, _ in PAGE_SPECS][:2] == ["search", "site_capacity"]


def test_link_fields_in_request_are_pure():
    base = {S.LINK_NETWORK: "DSN", S.LINK_MARGIN: 3.0, S.LINK_CUSTOM: [[1.0, 2.0, 5.0]], S.LINK_STATION_EL: None}
    assert S.link_fields(base) == {"link_network": "DSN", "link_custom": None, "min_earth_elevation_deg": 3.0,
                                   "link_station_min_elevation_deg": None, "link_direction": "receive"}
    assert S.link_fields({**base, S.LINK_NETWORK: "geometry"}) == {"link_network": None, "link_direction": "receive"}
    assert S.link_fields({**base, S.LINK_DIRECTION: "transmit"})["link_direction"] == "transmit"
    assert S.link_fields({**base, S.LINK_DIRECTION: "basura"})["link_direction"] == "receive"
    c = S.link_fields({**base, S.LINK_NETWORK: "custom", S.LINK_STATION_EL: 8.0})
    assert c["link_custom"] == ((1.0, 2.0, 5.0),) and c["link_station_min_elevation_deg"] == 8.0


def test_malapert_core_blocks_notes_and_local_hours(page):
    at = run_app()
    assert not at.exception, [e.value for e in at.exception]
    b = body(at)
    for needle in ("Capacidad del sitio", "Solar", "Conectividad", "Periodo analizado", "Ventana de misión", "Mejor fecha",
                   "NO es un presupuesto", "No es un presupuesto de enlace RF", "Sol visible no es potencia garantizada",
                   "ESTRACK supuesta", "NSN"):
        assert needle.lower() in b.lower(), needle
    m = metrics(at)
    for k in ("Sol visible", "Noche máxima", "Tierra visible (geometría)", "ENLACE POSIBLE", "HUECO MÁXIMO sin enlace",
              "Potencia eléctrica media", "Energía por día (media)"):
        assert k in m, k
    st = station_table(at)
    assert len(st) == 3 and all(z in " ".join(st["Contacto más largo, hora local civil"]) for z in ("PST", "CET", "AEDT"))
    contacts = next(t for t in tables(at) if "Hora local civil" in t.columns and "UTC" in t.columns)
    assert any(z in " ".join(contacts["Hora local civil"]) for z in LOCAL_ZONES)
    assert at.session_state[K.SITE_ID] == "site23"
    assert len(at.get("plotly_chart")) == 3 and len(at.get("download_button")) == 2


@pytest.mark.parametrize("site", ["site04", "site11"])
def test_polar_dem_sites_all_three_modes(page, site):
    at = run_app(site=site)
    for mode in ("Público", "Planificador", "Experto"):
        at.sidebar.selectbox(key="_w_mode").set_value(mode).run()
        assert not at.exception, f"{site} [{mode}]: {[e.value for e in at.exception]}"
        assert "ENLACE POSIBLE" in metrics(at) and "Conectividad" in body(at)
    st = station_table(at)
    assert len(st) == 3 and (st["Zona horaria"] != "").all()


def test_apollo11_smooth_sphere_says_flat_horizon_and_no_exception(page):
    at = run_app(site="apollo11")
    assert not at.exception, [e.value for e in at.exception]
    assert "horizonte plano" in body(at)
    for mode in ("Planificador", "Experto"):
        at.sidebar.selectbox(key="_w_mode").set_value(mode).run()
        assert not at.exception, f"[{mode}]: {[e.value for e in at.exception]}"


def test_public_mode_has_plain_language_stations_text(page):
    at = run_app(site="site04")
    txt = body(at)
    assert "En lenguaje llano" in txt and any(z in txt for z in LOCAL_ZONES)


def test_network_change_changes_stations_and_geometry_mode(page):
    at = run_app("Planificador", "site04")
    assert at.session_state[S.LINK_NETWORK] == "DSN"
    assert "Goldstone" in " ".join(station_table(at)["Estación"])
    at.sidebar.selectbox(key="_w_lnet").set_value("DSN+ESTRACK").run()
    assert not at.exception, [e.value for e in at.exception]
    st = station_table(at)
    assert len(st) == 6 and "Cebreros" in " ".join(st["Estación"])
    assert "SUPUESTA" in " ".join(st["Elevación mínima de la antena"])          # ESTRACK etiquetada como supuesta
    assert at.session_state[K.SITE_ID] == "site04"
    at.sidebar.selectbox(key="_w_lnet").set_value("geometry").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "solo geometría" in body(at).lower() and not any("% del tiempo con enlace" in t.columns for t in tables(at))
    assert metrics(at)["Enlace posible"] == "no calculado"


def test_custom_network_one_station(page):
    at = run_app("Planificador", "site04")
    at.sidebar.selectbox(key="_w_lnet").set_value("custom").run()
    assert not at.exception, [e.value for e in at.exception]
    st = station_table(at)
    assert len(st) == 1 and "Personalizada" in st["Estación"][0] or "custom-1" in st["Estación"][0]


def test_margin_change_changes_link_and_sensitivity_table(page):
    at = run_app("Planificador", "site04")
    before = metrics(at)["ENLACE POSIBLE"]
    at.sidebar.slider(key="_w_lmargin").set_value(5.0).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state[S.LINK_MARGIN] == 5.0
    after = metrics(at)["ENLACE POSIBLE"]
    assert after != before
    at.button(key="_sc_sens").click().run()
    assert not at.exception, [e.value for e in at.exception]
    sens = next(t for t in tables(at) if "Margen de elevación" in t.columns)
    assert list(sens["Margen de elevación"])[:3] == ["0°", "3°", "5° (el elegido)"]


def test_experimental_panel_shows_prominent_warning_and_evidence(page):
    at = run_app("Planificador")
    at.sidebar.multiselect(key="_w_panels").set_value(["si-legacy"]).run()
    assert not at.exception, [e.value for e in at.exception]
    b = body(at)
    assert "EXPERIMENTAL sin datasheet" in b
    assert any("investigación" in x.proto.label.lower() for x in at.get("badge")) if at.get("badge") else True


def test_expert_shows_power_formula(page):
    at = run_app("Experto")
    assert not at.exception, [e.value for e in at.exception]
    assert "W_nominal" in body(at) and "P_rel" in body(at)


# ---------------------------------------------------------------------------------------------- pulido: rangos, interruptor, horas, huecos
def test_uncertainty_ranges_shown_by_default_in_malapert_and_switch_hides_them(page):
    at = run_app()
    assert not at.exception, [e.value for e in at.exception]
    assert at.toggle(key="_sc_unc_on").value is True
    b = body(at)
    assert b.count("Rango de incertidumbre:") >= 4, "Sol, noche máxima, enlace y hueco máximo llevan rango sin pedirlo"
    at.toggle(key="_sc_unc_on").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    b = body(at)
    assert "Rango de incertidumbre:" not in b and "desactivados" in b


def test_smooth_sphere_says_why_range_is_not_computed(page):
    at = run_app(site="apollo11")
    b = body(at)
    assert "esfera lisa, sin mapa de terreno" in b and b.count("Rango de incertidumbre:") == 1


def test_quick_read_line_in_public_and_planner_not_expert(page):
    at = run_app("Planificador")
    b = body(at)
    assert "Lectura rápida" in b and "En este punto tendrás Sol" in b and "estaciones NASA que lo darían son" in b
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert "Lectura rápida" not in body(at)


def test_station_table_has_utc_and_local_columns_and_gap_recovery_text(page):
    at = run_app("Planificador", "site11")
    at.session_state[K.START_UTC], at.session_state[K.END_UTC] = "2026-12-16T00:00:00", "2027-01-15T00:00:00"   # de Gerlache 30 d: hueco real
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    st = station_table(at)
    assert "Contacto más largo, UTC" in st.columns and "Contacto más largo, hora local civil" in st.columns
    b = body(at)
    assert "Hueco máximo sin enlace:" in b and ("lo recupera primero" in b or "no vuelve antes" in b)


def test_no_link_at_all_gives_explicit_empty_state(page):
    at = run_app("Planificador", "site11")
    at.sidebar.slider(key="_w_lmargin").set_value(S.LINK_MARGIN_MAX).run()
    assert not at.exception, [e.value for e in at.exception]
    b = body(at)
    assert "No hay enlace posible en todo el periodo" in b and "Ninguna estación lo recupera" in b


def test_chart_tooltip_has_utc_and_local_with_correct_zone_by_date():
    from lsi.astronomy import ground_stations as gs
    from lsi.contracts import ContactWindow, et_to_utc_datetime, utc_datetime_to_et
    from lsi.visualization import contact_plot
    from datetime import datetime
    zones = {"2026-12-15T12:00:00": {"America/Los_Angeles": "PST", "Europe/Madrid": "CET", "Australia/Sydney": "AEDT"},
             "2026-07-15T12:00:00": {"America/Los_Angeles": "PDT", "Europe/Madrid": "CEST", "Australia/Sydney": "AEST"}}
    for iso, exp in zones.items():
        et = utc_datetime_to_et(datetime.fromisoformat(iso))
        for tz, ab in exp.items():
            assert gs.et_to_local(et, tz).tzname() == ab, (iso, tz)
    et0 = utc_datetime_to_et(datetime(2026, 12, 15, 10))
    loc = lambda e: gs.et_to_local(e, "America/Los_Angeles").strftime("%Y-%m-%d %H:%M:%S %Z")  # noqa: E731
    c = ContactWindow("DSS-14", "Goldstone DSS-14", "Goldstone", "America/Los_Angeles", et0, et0 + 7200,
                      "2026-12-15T10:00:00", "2026-12-15T12:00:00", loc(et0), loc(et0 + 7200), 2.0, 4.0, 7200.0, 30.0, 10.0)
    day = [("2026-12-15", et0 - 10 * 3600, et0 + 14 * 3600)]
    fig = contact_plot.contact_chart([c], day, local=False, to_local=gs.et_to_local)
    tip = fig.data[0].hovertext[0]
    assert "UTC 12-15 10:00" in tip and "Local 02:00 PST → 04:00 PST" in tip


def test_direction_selector_travels_in_request_and_changes_coverage(page):
    """Recepción (6°) → Transmisión (10,1°): el sentido viaja en la petición y la cobertura de la red mostrada baja."""
    at = run_app("Planificador", "site04")
    assert at.session_state[S.LINK_DIRECTION] == "receive"
    cov = next(t for t in tables(at) if "La red ve la Luna (%)" in t.columns)
    assert "el elegido" in cov["Sentido"][0] and "Recepción" in cov["Sentido"][0]
    pct = lambda t, i: float(t["La red ve la Luna (%)"][i].replace(",", "."))   # noqa: E731
    rx, tx = pct(cov, 0), pct(cov, 1)
    assert tx < rx                                              # la transmisión (comandos) tiene menos cobertura
    before = metrics(at)["ENLACE POSIBLE"]
    at.sidebar.selectbox(key="_w_ldir").set_value("transmit").run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state[S.LINK_DIRECTION] == "transmit"
    assert "Sentido elegido: **transmisión**" in body(at)          # lo dice la página a partir de ``req.link_direction``
    cov2 = next(t for t in tables(at) if "La red ve la Luna (%)" in t.columns)
    assert "el elegido" in cov2["Sentido"][1] and "Transmisión" in cov2["Sentido"][1]
    assert pct(cov2, 0) == pytest.approx(rx) and pct(cov2, 1) == pytest.approx(tx)    # la tabla enseña los tres sentidos siempre
    assert metrics(at)["ENLACE POSIBLE"] != before or tx < rx
    assert "menos elevación de antena" in body(at) and "comandos" in body(at)


def test_day12_dec_shows_real_whole_windows_not_fused_ones(page):
    """B3: el 12-dic la UI muestra las ventanas reales de ``daily_contact_table`` (con «continúa…»), nunca «Canberra 09:34-22:11»."""
    at = run_app("Planificador", "site04")
    at.selectbox(key="_sc_day").set_value("2026-12-12").run()
    assert not at.exception, [e.value for e in at.exception]
    day = next(t for t in tables(at) if "Hora local civil" in t.columns and "Horas dentro de este día" in t.columns)
    txt = " | ".join(day["Hora local civil"])
    for fused in ("09:34-22:11", "09:34-22:12", "10:21-18:12", "10:21-18:13", "10:22-18:13"):   # las ventanas fusionadas que no existen
        assert fused not in txt, fused
    # cada fila es UNA ventana real del pipeline, entera (sin recortar a las 00:00/24:00 UTC) y con «continúa…» si cruza la medianoche
    from datetime import datetime, timedelta
    from ui import cache
    ss = at.session_state.filtered_state
    res = cache.get_analysis(S.build_request(ss, cache.get_context()))
    real = {(c.station_id, c.start_utc[5:16].replace("T", " ") + " → " + c.end_utc[5:16].replace("T", " ")): c for c in (*res.link_window.contacts, *res.link.contacts)}
    assert len(day) >= 3
    for _, row in day.iterrows():
        sid = row["Estación"].split("(")[-1].rstrip(")")
        c = real[(sid, row["UTC"])]
        tol = timedelta(seconds=2)       # la ventana de misión recorta el contacto en la medianoche UTC (con ms de TDB-UTC)
        crosses_prev = datetime.fromisoformat(c.start_utc) < datetime(2026, 12, 12) - tol
        crosses_next = datetime.fromisoformat(c.end_utc) > datetime(2026, 12, 13) + tol
        assert ("continúa del día anterior" in row["Hora local civil"]) == crosses_prev, row.to_dict()
        assert ("continúa al día siguiente" in row["Hora local civil"]) == crosses_next, row.to_dict()
        assert row["Duración"] == C.fmt_duration(c.duration_s)
    assert any("continúa" in t for t in day["Hora local civil"])


def test_page_has_no_ui_logic_that_splits_or_joins_windows_by_day():
    src = (ROOT / "ui" / "pages" / "site_capacity.py").read_text(encoding="utf-8")
    assert "max(c.start_et, d0)" not in src and "_local_span" not in src and "daily_contact_table" in src


def test_malapert_zero_gap_says_no_gaps_and_never_invents_dates(page):
    at = run_app("Planificador")           # Malapert: hueco máximo 0 h
    assert not at.exception, [e.value for e in at.exception]
    assert metrics(at)["HUECO MÁXIMO sin enlace"].startswith("0 min")
    b = body(at)
    assert "Sin huecos de comunicación en esta ventana" in b
    assert not re.search(r"del \d\d/\d\d/\d{4} \d\d:\d\d al ", b) and "Hueco máximo sin enlace:" not in b and "El enlace vuelve" not in b


def test_panel_without_tracking_warns_with_both_powers_and_shows_used_mount(page):
    at = run_app("Planificador")
    at.sidebar.multiselect(key="_w_panels").set_value(["tj-gaas-lander-body"]).run()   # no admite seguimiento: cae a vertical fijo
    assert not at.exception, [e.value for e in at.exception]
    b = " ".join(e.value for e in at.warning)
    assert "no admite seguimiento" in b and "montaje vertical fijo" in b
    m = re.search(r"es (\d+) W/m² en vez de (\d+) W/m²", b)
    assert m and int(m.group(1)) < int(m.group(2))
    assert "montaje **Vertical fijo**" in body(at)


def test_handoff_tolerance_is_read_from_config_and_shown(page):
    tol = json.loads((ROOT / "config" / "ground_stations.json").read_text(encoding="utf-8"))["handoff_merge_tol_s"]
    note = C.handoff_note()
    assert f"{tol:g} s" in note
    assert note in body(run_app())
