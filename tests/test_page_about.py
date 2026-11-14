"""Página «Acerca de»: renderiza en los 3 modos sin excepción y contiene los avisos obligatorios."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.mark.parametrize("mode", ["publico", "planificador", "experto"])
def test_about_renders(mode, tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "about.py", tmp_path / "about.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.session_state[K.LANG_MODE] = mode
    at.run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Alcance y límites" in md                      # banda de avisos siempre visible
    assert "potencia ni enlace garantizados" in md and "a verificar" in md
    assert "Traspasos entre estaciones" in md and "20 s" in md      # tolerancia de fusión leída de config/ground_stations.json
    assert "3. Fuentes" in " ".join(h.value for h in at.header)
    assert at.session_state[K.LANG_MODE] == mode


def test_about_documents_link_network_and_panel_evidence(tmp_path, monkeypatch):
    """Red de estaciones (DSN verificada, ESTRACK supuesta, NSN fuera), margen, s_earth/G7 y los 3 paneles experimentales, desde config."""
    shutil.copy(ROOT / "ui" / "pages" / "about.py", tmp_path / "about.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.session_state[K.LANG_MODE] = "experto"
    at.run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Tierra visible (geometría)" in md and "ENLACE POSIBLE" in md and "G7 (hueco máximo sin enlace)" in md
    assert "810-005" in md and "NSN" in md and "no incluida" in md and "supuesto a verificar" in md
    assert "3 experimentales sin datasheet" in md and "5 paneles respaldados" in md
    st_df = next(d.value for d in at.dataframe if "Estación" in d.value.columns)
    assert set(st_df["Estación"]) >= {"DSS-14", "DSS-63", "DSS-43", "NNO-1"}
    assert list(st_df.loc[st_df["Estación"] == "NNO-1", "Elevación mínima (°)"])[0].endswith("(supuesta)")
