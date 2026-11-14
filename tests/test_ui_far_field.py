"""Modo FAR_FIELD (relieve aproximado de 80 m, fuera de los recortes de 5 m) en la UI: ninguna pantalla lo llama «esfera lisa»,
todas rotulan «Relieve aproximado (80 m)» con el error MEDIDO (leído de ``lsi.pipeline``), y DEM / esfera lisa siguen igual."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import HorizonMode, StateKey as K
from lsi.pipeline import FAR_FIELD_VALIDATION
from ui import state as S

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice
POLAR_FAR = (-88.0, 40.0)           # al sur de 80°S y fuera de Site04/Site11/Site23
PAGES = ["site_capacity", "horizon_visibility", "power_panels", "site_score", "explorer", "comparison"]


TEXT_TYPES = {"markdown", "caption", "warning", "info", "success", "error", "alert", "badge", "heading", "subheader", "header", "title",
              "metric", "text", "html", "expander", "button", "exception"}


def alltext(node) -> str:
    """Texto visible de un bloque (incluye expanders, insignias y ayudas; no selectores ni gráficas, que listan los sitios curados)."""
    out = []
    for ch in getattr(node, "children", {}).values():
        if hasattr(ch, "children"):
            out.append(alltext(ch))
        elif ch.type in TEXT_TYPES:
            t = str(getattr(ch, "proto", ""))
            if "Modo de horizonte sin DEM: H constante" not in t:        # la entrada del glosario DEFINE «esfera lisa»: es legítima
                out.append(t)
    return " ".join(out)


def run_page(tmp_path, monkeypatch, page: str, lat: float, lon: float) -> tuple[AppTest, str]:
    shutil.copy(ROOT / "ui" / "pages" / f"{page}.py", tmp_path / f"{page}.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240)
    at.session_state[K.OBS_LAT], at.session_state[K.OBS_LON] = lat, lon
    at.session_state[K.LANG_MODE] = "planificador"
    at.session_state[S.ORIGIN] = "custom"          # punto exacto: sin ajuste al recorte de un sitio curado
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at, alltext(at.main) + " " + alltext(at.sidebar)


@pytest.mark.parametrize("page", PAGES)
def test_far_field_never_says_smooth_sphere(tmp_path, monkeypatch, page):
    at, text = run_page(tmp_path, monkeypatch, page, *POLAR_FAR)
    low = text.lower()
    assert "esfera lisa" not in low and "sin mapa de terreno" not in low and "cota optimista sobre" not in low
    assert "relieve aproximado (80 m)" in low
    if page != "comparison":       # la comparación calcula los sitios curados, no el punto de la barra lateral
        assert f"{FAR_FIELD_VALIDATION['horizon_rms_deg']:.2f}°" in text          # el error medido sale de lsi.pipeline, no de la UI


def test_site_capacity_far_field_degrades_with_right_message(tmp_path, monkeypatch):
    at, text = run_page(tmp_path, monkeypatch, "site_capacity", *POLAR_FAR)
    assert "optimista cerca de crestas" in text and "DEM polar de 80 m" in text
    assert "no hay mapa de pendiente de aterrizaje ni relieve fino" in text
    assert "relieve aproximado de 80 m; no hay σ del terreno" in text


def test_smooth_sphere_and_dem_unchanged(tmp_path, monkeypatch):
    _, text = run_page(tmp_path, monkeypatch, "site_capacity", 0.6741, 23.4730)       # Apolo 11: fuera del polo
    assert "Esfera lisa" in text and "esfera lisa, sin mapa de terreno" in text and "Relieve aproximado (80 m)" not in text
    _, text = run_page(tmp_path, monkeypatch, "site_capacity", -89.45, 222.0)          # dentro de un recorte de 5 m (si lo cubre)
    assert "Relieve aproximado (80 m)" not in text or "Relieve real (DEM)" not in text


def test_observer_modes_of_the_test_points():
    from lsi.pipeline import resolve_observer
    from ui import cache
    o, _ = resolve_observer(cache.get_context(), *POLAR_FAR, 2.0)
    assert o.mode is HorizonMode.FAR_FIELD
