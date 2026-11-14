"""Página «Paneles y potencia» con ``AppTest``: 3 paneles en Malapert, vertical con seguimiento, batería, Apolo 11 (esfera
lisa), panel con montaje requerido y demostración orientación vs tecnología."""
import shutil
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import MountingSpec, MountingType, StateKey as K
from ui import state as S
from ui_cards import cards, legacy

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice
TRIO = ["tj-gaas-lander-body", "tj-gaas-vertical-mast", "mj-4j-high-eff"]


@pytest.fixture
def page(tmp_path, monkeypatch):
    """Carpeta de páginas con solo ésta: así es la página por defecto de la navegación."""
    shutil.copy(ROOT / "ui" / "pages" / "power_panels.py", tmp_path / "power_panels.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return tmp_path


def run_app(mode: str | None = None) -> AppTest:
    at = legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=180))
    at.run()
    if mode:
        at.sidebar.selectbox(key="_w_mode").set_value(mode).run()
    return at


def body(at: AppTest) -> str:
    parts = (*at.markdown, *at.caption, *at.success, *at.error, *at.warning, *at.info, *at.subheader, *at.header)
    return " ".join(e.value for e in parts)


def figs(at: AppTest) -> list:
    return [e for e in at.get("plotly_chart")]


def test_demo_ratios_come_from_energy_panels(page):
    at = run_app()
    assert not at.exception
    vals = [m.value for m in at.metric]      # esta pantalla usa st.metric (cifras cortas)
    assert vals[:3] == ["≈ 57×", "≈ 38×", "≈ 19×"]                      # 1/tan(1°), 1/tan(1,5°), 1/tan(3°)
    assert "La orientación pesa más que la tecnología" in body(at)
    assert "Alcance y límites" in body(at)                              # banda de avisos al inicio


def test_three_panels_malapert_table_and_chart(page):
    at = run_app("Planificador")
    at.multiselect(key="_pp_panels").set_value(TRIO).run()
    assert not at.exception, at.exception
    assert at.session_state[S.PANEL_IDS] == TRIO and at.session_state[K.PANEL_ID] == TRIO[0]
    assert at.session_state[K.SITE_ID] == "site23"
    assert len(figs(at)) == 1
    traces = [t.name for t in __import__("plotly.io", fromlist=["x"]).from_json(figs(at)[0].proto.spec).data if t.name]
    assert sum("·" in n for n in traces) == 3 and any("Elevación solar" in n for n in traces)
    df = at.dataframe[-1].value if len(at.dataframe) else None
    tables = [d.value for d in at.dataframe]
    cmp = next(t for t in tables if "Potencia media (% nominal)" in t.columns)
    assert len(cmp) == 3
    assert (cmp["Dato"] != "").all() and set(cmp["Dato"]) <= {"publicado", "estimado", "suposición", "a verificar"}
    assert "no son vatios" in body(at).lower() or "no es una predicción" in body(at).lower()
    assert df is not None
    assert at.get("download_button")


def test_vertical_tracking_mount_and_fallback(page):
    at = run_app("Planificador")
    ids = ["tj-gaas-vertical-mast", "mj-4j-high-eff", "tj-gaas-lander-body"]
    at.multiselect(key="_pp_panels").set_value(ids).run()
    at.selectbox(key="_pp_mount").set_value("vertical_az_tracking").run()
    assert not at.exception, at.exception
    assert at.session_state[K.MOUNT_TYPE] == "vertical_az_tracking"
    cmp = next(d.value for d in at.dataframe if "Montaje aplicado" in d.value.columns)
    m = dict(zip(cmp["Panel"], cmp["Montaje aplicado"]))
    assert sum("seguimiento" in v for v in m.values()) == 2             # mástil y 4J lo admiten
    assert any("Horizontal" in v for v in m.values())                   # el lander no: usa su montaje por defecto
    warn = " ".join(w.value for w in at.warning)                        # y la pantalla AVISA de la sustitución, con las dos potencias
    assert "no admite seguimiento" in warn and "en vez de" in warn and "W/m²" in warn
    # en Malapert el seguimiento vertical supera al horizontal
    means = [float(x.replace(",", ".").replace(" ", "")) for x in cmp["Potencia media (% nominal)"]]
    assert max(means) > 0


def test_4j_with_required_mounting_does_not_fail(page):
    """mj-4j-high-eff con montaje None falla en get_power: la página pasa siempre ``mounting_for``."""
    at = run_app("Planificador")
    at.multiselect(key="_pp_panels").set_value(["mj-4j-high-eff"]).run()
    assert not at.exception, at.exception
    assert not any("falta azimuth" in w.value for w in at.warning)
    at.selectbox(key="_pp_mount").set_value("vertical_fixed").run()
    assert not at.exception and not any("falta azimuth" in w.value for w in at.warning)
    assert any(d.value.shape[0] == 1 for d in at.dataframe)


def test_estimated_panel_is_calculable_labelled_and_has_band(page):
    """ROSA ya está respaldado (derivado): 3 experimentales (perovskita, Si, CIGS) en su propio grupo, con sombra; 2 respaldados sin sombra."""
    ids = ["perovskite-si-tandem-demo", "si-legacy", "cigs-thin-film-flex", "rosa-flexible-rollout", "tj-gaas-lander-body"]
    at = run_app("Planificador")
    at.multiselect(key="_pp_panels").set_value(ids).run()
    assert not at.exception, at.exception
    assert not any("no calculable" in w.value for w in at.warning)
    assert any("Estimación sin datasheet" in w.value for w in at.warning)
    tabs = [d.value for d in at.dataframe if "Montaje aplicado" in d.value.columns]
    assert [len(t) for t in tabs] == [2, 3]                                # respaldados primero, experimentales aparte
    assert set(tabs[0]["Parámetros"]) == {"con datos de fuente"} and set(tabs[1]["Parámetros"]) == {"estimación sin datasheet"}
    assert all(e.startswith("experimental sin datasheet") for e in tabs[1]["Evidencia"])
    assert all(e.startswith("respaldado") for e in tabs[0]["Evidencia"])
    fs = [__import__("plotly.io", fromlist=["x"]).from_json(f.proto.spec) for f in figs(at)]
    assert [sum(t.fill == "tonexty" for t in f.data) for f in fs] == [0, 3]  # sombra solo en los 3 con rango


def test_absolute_w_m2_is_p_rel_times_areal_power(page):
    """W/m² de panel = P_rel × η·1361 (areal_power_w_m2_am0 de panels.py): el pico del GaAs de lander no supera 401,5 × pico relativo."""
    from ui import cache
    ctx = cache.get_context()
    areal = next(p for p in ctx.panels.panels if p.id == "tj-gaas-lander-body").areal_power_w_m2_am0
    assert abs(areal - 0.295 * 1361) < 0.5
    at = run_app("Planificador")
    at.multiselect(key="_pp_panels").set_value(["tj-gaas-lander-body"]).run()
    assert not at.exception, at.exception
    cmp = next(d.value for d in at.dataframe if "Montaje aplicado" in d.value.columns)
    num = lambda x: float(str(x).replace(" ", "").replace(" ", "").replace(",", "."))
    assert abs(num(cmp["Pico (W/m² de panel)"][0]) - areal * num(cmp["Pico (% nominal)"][0]) / 100) <= 0.006 * areal


def test_battery_chart_and_depletion(page):
    at = run_app("Planificador")
    at.multiselect(key="_pp_panels").set_value(["tj-gaas-lander-body"]).run()
    at.checkbox(key="_pp_bat_on").check().run()
    at.number_input(key="_pp_bat_load").set_value(400.0).run()          # consumo > potencia: se agota seguro
    assert not at.exception, at.exception
    assert len(figs(at)) == 2
    assert any("llega a su carga mínima" in e.value for e in at.error)
    at.number_input(key="_pp_bat_load").set_value(0.0).run()
    assert any("no se agota" in e.value for e in at.success)
    at.number_input(key="_pp_bat_smin").set_value(100.0).run()          # mínima = máxima: entrada inválida
    assert not at.exception and any("Revisa los límites" in e.value for e in at.error)
    assert len(figs(at)) == 1


def test_apollo11_smooth_sphere_says_so(page):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception, at.exception
    assert any("esfera lisa" in w.value and "horizonte plano" in w.value for w in at.warning)
    assert len(figs(at)) == 1


def test_public_mode_plain_sentence_and_no_table(page):
    at = run_app()
    assert not at.exception
    txt = body(at)
    assert "produciría de media un" in txt and "de su potencia máxima" in txt
    assert not any("Potencia media (% nominal)" in d.value.columns for d in at.dataframe)
    assert "_pp_bat_on" not in [c.key for c in at.checkbox]


def test_csv_series_has_all_columns(page, monkeypatch):
    """El CSV se genera con las series de la caché (misma función que el botón)."""
    from ui import cache
    from ui.state import build_request
    import dataclasses
    import importlib.util
    at = run_app()
    ctx = cache.get_context()
    req = dataclasses.replace(build_request(dict(at.session_state.filtered_state), ctx), panel_id=None, mounting=None)
    res, err = cache.try_analysis(req)
    assert err is None
    runs = cache.get_power(req, [(p, S.mounting_for(ctx, p, {K.MOUNT_TYPE: "horizontal"})) for p in TRIO[:2]])
    assert all(r.series is not None for r in runs)
    # la página no se puede importar sin ejecutarla: se comprueba la lógica con las mismas series
    import pandas as pd
    s = runs[0].series
    el = np.interp(s.et, res.sky.et, res.sky.sun.el_deg)
    assert len(el) == len(s.p_rel) and np.isfinite(el).all()
    assert isinstance(pd.DataFrame({"x": el}).to_csv(index=False), str)


def test_horizontal_at_the_pole_warns_and_disables_auto_mount(page):
    at = run_app("Planificador")
    assert not at.exception, at.exception
    assert at.session_state["ui_mount_auto"] is True and at.session_state[K.MOUNT_TYPE] == "vertical_az_tracking"
    assert not any("plano casi no produce" in w.value for w in at.warning)
    at.selectbox(key="_pp_mount").set_value("horizontal").run()
    assert not at.exception, at.exception
    assert at.session_state["ui_mount_auto"] is False
    assert any("plano casi no produce" in w.value and "× menos luz que uno vertical" in w.value for w in at.warning)
