"""Pantalla B (horizonte y visibilidad) con AppTest: Site23/Malapert (DEM), Apolo 11 (esfera lisa), cursor y fecha inválida."""
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui_cards import cards, legacy

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.fixture
def only_page(tmp_path, monkeypatch):
    """Navegación con solo esta página (copia en carpeta temporal): independiente de las demás pantallas."""
    (tmp_path / "horizon_visibility.py").write_text((ROOT / "ui" / "pages" / "horizon_visibility.py").read_text(encoding="utf-8"),
                                                    encoding="utf-8")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))


def run_app() -> AppTest:
    return legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)).run()


def body(at: AppTest) -> str:
    return " ".join(x.value for x in (*at.markdown, *at.caption, *at.warning, *at.info, *cards(at)))


def test_site23_dem_renders_cards_and_charts(only_page):
    at = run_app()
    assert not at.exception
    labels = [m.label for m in cards(at)]
    assert any(l.startswith("Tiempo hasta") and "Sol" in l for l in labels)
    assert any("Earth" in l for l in labels) and "Elevación solar actual" in labels
    assert "Alcance y límites" in body(at) and "Site23" in body(at)
    assert any("Descripción de la figura" in c.value for c in at.caption)
    assert any("-badge[" in m.value and "Sol:" in m.value for m in at.markdown)


def test_apollo11_smooth_sphere_renders_with_notice(only_page):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception
    assert any("esfera lisa" in i.value for i in at.info)
    assert any(m.label == "Elevación solar actual" for m in cards(at))


def test_changing_cursor_changes_state_without_new_analysis(only_page):
    at = run_app()
    c0, t0 = at.session_state[K.CURSOR_UTC], [m.value for m in cards(at)]
    at.slider(key="_hv_t").set_value(datetime(2026, 12, 8, 6, 0)).run()
    assert not at.exception
    assert at.session_state[K.CURSOR_UTC] == "2026-12-08T06:00:00" != c0
    assert [m.value for m in cards(at)] != t0                       # la elevación solar (y las cuentas atrás) cambian
    at.button(key="_hv_fwd").click().run()                           # paso adelante (10 min por defecto)
    assert at.session_state[K.CURSOR_UTC] == "2026-12-08T06:10:00"


def test_planner_mode_shows_numeric_table_public_shows_sentence(only_page):
    at = run_app()
    assert any("Ahora mismo" in w.value for w in at.markdown) and not at.dataframe       # Público: frase llana, sin tabla
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert not at.exception and len(at.dataframe) >= 2                                   # tabla numérica + horizonte exacto


@pytest.mark.parametrize("bad", ["2060-01-01 00:00", "1800-05-05 00:00"])
def test_date_out_of_range_shows_message(only_page, bad):
    at = run_app()
    at.sidebar.text_input(key="_w_start").set_value(bad).run()
    assert not at.exception
    assert any("rango" in e.value for e in at.sidebar.error)
    assert any("corregir" in w.value for w in at.warning)


def test_earthset_is_lander_horizon_and_link_end_is_separate(only_page):
    """Earthset se explica como puesta en el horizonte del lander; el estado del enlace (hay / fin / vuelve) sale de ``res.link``."""
    at = run_app()
    assert not at.exception
    b = body(at)
    assert "Earthset = la Tierra se pone en el horizonte del lander" in b and "red NASA DSN" in b
    assert any(k in b for k in ("**Hay enlace posible**", "Fin del enlace", "Ahora no hay enlace posible"))
