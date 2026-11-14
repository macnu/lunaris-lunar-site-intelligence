"""Humo de la UI (§12.3 punto 4): ``streamlit.testing.v1.AppTest`` recorre las 10 páginas sin ``exception`` en los 3 modos."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui import PAGE_SPECS
from ui.state import MODE_LABELS

pytestmark = [pytest.mark.needs_spice, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[1]
PAGES = [n for n, _, _ in PAGE_SPECS]


def run_app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()


def test_ten_pages_declared():
    assert PAGES == ["search", "site_capacity", "explorer", "best_spots", "horizon_visibility", "timeline", "comparison", "power_panels",
                     "site_score", "about"]
    assert all((ROOT / "ui" / "pages" / f"{n}.py").is_file() for n in PAGES)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_in_all_three_modes(page, tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / f"{page}.py", tmp_path / f"{page}.py")   # app.py solo ve esta página
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    at = run_app()
    for label in MODE_LABELS.values():                                            # Público (por defecto), Planificador, Experto
        at.sidebar.selectbox(key="_w_mode").set_value(label).run()
        assert not at.exception, f"{page} [{label}]: {[e.value for e in at.exception]}"
        assert not at.sidebar.error, f"{page} [{label}]: {[e.value for e in at.sidebar.error]}"
        assert any(len(x) for x in (at.markdown, at.title, at.header, at.subheader)), f"{page} [{label}] sin contenido"


def test_app_with_all_pages_starts_clean():
    at = run_app()                                                                # carpeta real ui/pages: navegación completa
    assert not at.exception, [e.value for e in at.exception]
    assert "pendientes" not in " ".join(c.value for c in at.sidebar.caption)      # ninguna de las 10 falta
