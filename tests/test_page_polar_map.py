"""Pantalla «Mapa del polo sur» con AppTest: carga, capas, buscador, selección de punto y modos de usuario."""
import shutil
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem]


@pytest.fixture
def at(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "polar_map.py", tmp_path / "polar_map.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()


def text(at) -> str:
    return " ".join(e.value for e in (*at.markdown, *at.caption, *at.warning, *at.error, *at.info, *at.title))


def test_loads_with_map_description_and_card(at):
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    t = text(at)
    assert "Mapa del polo sur" in t and "Descripción de la figura" in t and "Punto elegido" in t
    assert "Relieve detallado" in t                                      # el punto por defecto (Malapert) está en un recorte de 5 m
    assert at.button(key="_pm_eval") is not None


def test_warm_reload_is_fast(at):
    t0 = time.perf_counter()
    at.run()
    assert time.perf_counter() - t0 < 4.0                                # caché caliente


def test_search_centers_map_and_public_mode_has_no_jargon(at):
    at.text_input(key="_pm_q").set_value("Shackleton").run()
    assert not at.exception and at.session_state["_pm_zoom"] > 1
    assert not any(j in text(at) for j in ("PSR", "FAR_FIELD", "DEM de"))   # modo Público: sin jerga propia de la pantalla
    assert "Shackleton" in text(at)


def test_search_with_html_is_escaped(at):
    at.text_input(key="_pm_q").set_value("<script>alert(1)</script>").run()
    assert not at.exception
    assert "<script>" not in " ".join(e.value for e in (*at.markdown, *at.caption))


def test_point_outside_recortes_uses_far_field_and_layers_toggle(at):
    from ui import state as S
    at.session_state[K.OBS_LAT], at.session_state[K.OBS_LON] = -84.4392, 135.0
    at.session_state[S.ORIGIN] = "custom"
    at.session_state["_pm_color"], at.session_state["_pm_psr"] = "temp_mean", True
    at.run()
    assert not at.exception
    t = text(at)
    assert "Relieve aproximado" in t and "no sirve para decidir un aterrizaje fino" in t
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert not at.exception and "FAR_FIELD" in text(at) and "RMS" in text(at)
