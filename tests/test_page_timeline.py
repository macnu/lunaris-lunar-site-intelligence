"""Página «Línea temporal» (ui/pages/timeline.py) con ``AppTest``: Malapert 30 d, comparación de fechas, año completo,
Apolo 11 (esfera lisa) y animación. La app se arranca solo con esta página (``LSI_PAGES_DIR`` a una carpeta temporal)."""
import shutil
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui_cards import cards, legacy

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.fixture(autouse=True)
def _restore_main():
    """``AppTest.from_function`` deja ``sys.modules['__main__']`` apuntando a un script temporal; un ``ProcessPoolExecutor``
    posterior (spawn en Windows) lo re-ejecuta en cada hijo y se cuelga. Se restaura el original al acabar cada test."""
    main = sys.modules.get("__main__")
    yield
    if main is not None:
        sys.modules["__main__"] = main
    else:
        sys.modules.pop("__main__", None)


@pytest.fixture
def page(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "timeline.py", tmp_path / "timeline.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return tmp_path


def run_app() -> AppTest:
    return legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)).run()


def body(at: AppTest) -> str:
    return " ".join(e.value for e in (*at.markdown, *at.caption, *at.success, *at.info, *at.warning, *at.error))


def set_mode(at: AppTest, label: str) -> AppTest:
    return at.sidebar.selectbox(key="_w_mode").set_value(label).run()


def test_malapert_30d_public(page):
    at = run_app()
    assert not at.exception and not at.error
    assert "Alcance y límites" in body(at)                              # banda de avisos al inicio
    assert "geometría" in body(at) and "enlace posible" in body(at).lower()    # Tierra visible ≠ enlace posible
    assert "La noche más larga dura" in body(at)                        # relato del modo Público
    assert {m.label for m in cards(at)} >= {"Sol visible", "Ventana de Sol más larga", "Oscuridad máxima"}
    assert at.radio(key="_tl_view").value == "Periodo actual"
    assert at.dataframe                                                  # tabla diaria
    assert not at.get("selectbox") or "_tl_ev" not in [s.key for s in at.selectbox]   # sin zoom en Público
    assert any(d.proto.label == "Descargar JSON" for d in at.get("download_button"))


def test_malapert_planner_zoom_and_tables(page):
    at = set_mode(run_app(), "Planificador")
    assert not at.exception
    ev = at.selectbox(key="_tl_ev")
    assert len(ev.options) >= 1 and "Zoom" in " ".join(h.value for h in at.subheader)
    ev.set_value(0).run()
    at.slider(key="_tl_zoom_h").set_value(6).run()
    assert not at.exception
    assert "bisección" in body(at)
    assert {m.label for m in cards(at)} >= {"Tierra visible (geometría)", "Sol y Tierra a la vez", "ENLACE POSIBLE", "Hueco máximo sin enlace"}
    assert "Enlace posible" in body(at)                                  # la geometría y el enlace se distinguen
    toggle = at.toggle(key="_tl_stations")                                # contactos del pipeline: enlace por estación
    toggle.set_value(True).run()
    assert not at.exception
    import plotly.io as pio
    names = [t.name for t in pio.from_json(at.get("plotly_chart")[0].proto.spec).data if t.name]
    assert any(n.startswith("Enlace posible") for n in names) and any(n.startswith("Enlace vía") for n in names)


def test_compare_two_dates(page):
    at = run_app()
    at.radio(key="_tl_view").set_value("Comparar fechas").run()
    assert not at.exception and not at.error
    assert at.number_input(key="_tl_delay").value == 30.0
    assert "la noche más larga pasa de" in body(at)
    df = next(d for d in at.dataframe if "Diferencia (B − A)" in d.value.columns)
    assert list(df.value["Métrica"])[0] == "Sol visible" and len(df.value) == 10
    assert {"Enlace posible", "Hueco máximo sin enlace"} <= set(df.value["Métrica"])
    assert any(("▲" in x or "▼" in x or "=" in x) for x in df.value["Diferencia (B − A)"])   # no solo color
    at.number_input(key="_tl_delay").set_value(0.0).run()               # retraso 0: avisa y no falla
    assert not at.exception and "coinciden" in body(at)


@pytest.mark.slow
def test_full_year(page):
    at = run_app()
    at.radio(key="_tl_view").set_value("Año y estaciones").run()
    assert not at.exception and not at.error
    mdf = next(d for d in at.dataframe if "Días sin Sol" in d.value.columns).value
    assert 12 <= len(mdf) <= 13 and int(mdf["Días"].sum()) in (365, 366)
    assert (mdf["Sol visible (%)"].between(0, 100)).all()
    assert "En un año completo" in body(at)
    set_mode(at, "Planificador")
    assert "347" in body(at) and "27,2" in body(at)                     # ciclo solar y libración


def test_apollo11_smooth_sphere(page):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception and not at.error
    assert "Sin relieve" in body(at)                                    # cabecera: modo esfera lisa
    assert "La noche más larga" in body(at) or "no llega a ponerse" in body(at)
    set_mode(at, "Experto")
    assert not at.exception
    assert "Zona de duda" in body(at)                                   # Experto: horizonte pesimista junto a las bandas


def test_animation_slider_sets_cursor(page):
    at = run_app()
    at.radio(key="_tl_view").set_value("Animación").run()
    assert not at.exception
    sl = next(s for s in at.select_slider if s.key and s.key.startswith("_tl_anim_2"))
    sl.set_value(6).run()
    assert not at.exception
    assert at.session_state[K.CURSOR_UTC] != at.session_state[K.START_UTC]
    assert "Próximo cambio" in body(at)
    assert at.toggle(key="_tl_play").value is False                     # autoplay apagado por defecto


def test_no_visibility_gives_explicit_empty_state():
    """P1-2: sin Sol ni Tierra en el periodo no hay figura con ejes vacíos: aviso explícito con enlace."""
    from types import SimpleNamespace as NS

    def app():
        from types import SimpleNamespace as NS
        from ui import components as C
        empty = NS(windows=())
        res = NS(timeline=NS(sun=empty, earth=empty))
        st_shown = C.no_visibility(res)
        import streamlit as st
        st.write("EMPTY" if st_shown else "DRAW")
    at = AppTest.from_function(app).run()
    assert not at.exception
    assert any("no es" in i.value or "no son" in i.value for i in at.info) and "ningún momento de este periodo" in at.info[0].value
    assert "Mejores puntos y fechas" in at.info[0].value
    assert at.markdown[-1].value == "EMPTY"
