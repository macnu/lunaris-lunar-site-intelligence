"""Pantalla «Mejores puntos y fechas» con AppTest: carga con Site23/14 d, cambio de duración y perfil, botón evaluar, sin JSON."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem]


@pytest.fixture
def at(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "best_spots.py", tmp_path / "best_spots.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()


def txt(at):
    return " ".join(e.value for e in (*at.markdown, *at.caption, *at.warning, *at.error, *at.info, *at.title))


def test_loads_site23_14d(at):
    assert not at.exception
    assert at.selectbox(key="_bp_site").value == "Site23" and at.selectbox(key="_bp_dur").value == 14.0
    assert len(at.get("plotly_chart")) == 2 and len(at.dataframe) == 1       # mapa + calendario, tabla TOP-N
    t = txt(at)
    assert "Alcance y límites" in t and "no es «aprobado»" in t


def test_change_duration_profile_and_layer(at):
    at.selectbox(key="_bp_dur").set_value(30.0).run()
    assert not at.exception and at.selectbox(key="_bp_dur").value == 30.0
    at.selectbox(key="_bp_profile").set_value("rover").run()
    assert not at.exception and at.selectbox(key="_bp_profile").value == "rover"
    at.selectbox(key="_bp_layer").set_value("d_max_h").run()
    assert not at.exception
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert not at.exception


def test_evaluate_sets_point_and_start(at):
    top = at.dataframe[0].value.iloc[0]
    at.button(key="_bp_eval").click().run()
    assert not at.exception
    ss = at.session_state
    assert ss[K.SITE_ID] is None and abs(ss[K.OBS_LAT] - top["Lat (°)"]) < 1e-3
    assert ss[K.START_UTC].startswith(top["Mejor inicio (UTC)"])


def test_without_json_shows_warning(tmp_path, monkeypatch):
    empty = tmp_path / "vacio"
    empty.mkdir()
    pages = tmp_path / "p"
    pages.mkdir()
    shutil.copy(ROOT / "ui" / "pages" / "best_spots.py", pages / "best_spots.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(pages))
    monkeypatch.setenv("LSI_SUITABILITY_DIR", str(empty))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception
    assert any("precalculados" in w.value for w in at.warning)
    assert any("precompute_suitability" in c.value for c in at.code)


def test_earth_layer_is_link_when_map_was_precomputed_with_a_network(at):
    """La capa «Tierra» se rotula según el mapa: ENLACE POSIBLE (con red) o aviso de geometría (mapa antiguo); nunca «Fracción de Tierra»."""
    layers = list(at.selectbox(key="_bp_layer").options)
    assert any("ENLACE POSIBLE" in o for o in layers) or "sin red de estaciones" in txt(at)
    assert "Fracción de Tierra (f_Tierra)" not in layers
