"""Pantalla A «Explorador 3D» con AppTest: Malapert (DEM), Apolo 11 (esfera lisa), cambio de capa/modo, y selección por clic."""
import importlib.util
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem]


@pytest.fixture
def at(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "explorer.py", tmp_path / "explorer.py")   # única página: es la de arranque
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


def all_text(at: AppTest) -> str:
    els = (*at.markdown, *at.caption, *at.warning, *at.error, *at.info, *at.title)
    return " ".join(e.value for e in els)


def test_malapert_dem_loads_3d_and_metadata(at):
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 2                       # 3D + mapa polar
    txt = all_text(at)
    assert "Explorador 3D" in txt and "Alcance y límites" in txt   # título y banda de avisos
    assert "sin datos de terreno" not in txt.lower()
    assert at.button(key="_x_go_site23") is not None               # marcadores / acceso a los 3 candidatos


def test_apollo11_smooth_sphere_shows_notice_not_empty_3d(at):
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception
    assert any("Sin datos de terreno" in w.value for w in at.warning)
    assert len(at.get("plotly_chart")) == 1                        # solo el mapa global, nunca un 3D vacío


def test_layer_change_and_modes_do_not_raise(at):
    for layer in ("pendiente", "incertidumbre", "muestreo", "elevacion"):
        at.radio(key="_x_layer").set_value(layer).run()
        assert not at.exception, layer
        assert at.session_state[K.LAYER] == layer
    at.slider(key="_x_exag").set_value(4.0).run()
    at.selectbox(key="_x_radius").set_value("Todo el recorte (≈ 21 km)").run()
    assert not at.exception
    for modo in ("Planificador", "Experto", "Público"):
        at.sidebar.selectbox(key="_w_mode").set_value(modo).run()
        assert not at.exception, modo
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert any("WKT" in e.label for e in at.expander)              # modo experto: CRS completo


def test_height_control_updates_shared_state(at):
    at.number_input(key="_x_height").set_value(5.0).run()
    assert not at.exception and at.session_state[K.OBS_HEIGHT] == 5.0


def test_point_from_selection_is_pure():
    import ast
    src = (ROOT / "ui" / "pages" / "explorer.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "point_from_selection")
    ns = {"Optional": __import__("typing").Optional, "stereo_inverse": __import__("lsi.astronomy.coordinates", fromlist=["x"]).stereo_inverse}
    exec(compile(ast.Module([fn], []), "explorer", "exec"), ns)
    f = ns["point_from_selection"]
    lat, lon = f({"selection": {"points": [{"x": 0.0, "y": 0.0}]}})
    assert lat == pytest.approx(-90.0)
    lat, lon = f({"selection": {"points": [{"x": 0.0, "y": 10000.0}]}})        # +y = lon 0°
    assert lon == pytest.approx(0.0) and lat > -90.0
    assert f({"selection": {"points": []}}) is None and f(None) is None


def test_site04_muestra_mapa_topografico_y_3d(at):
    at.sidebar.selectbox(key="_w_site").set_value("site04").run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 2                                  # mapa topográfico 2D + 3D
    txt = " ".join(c.value for c in at.caption)
    assert "mapa topográfico 2D" in txt and "sin datos de terreno" not in all_text(at).lower()


def test_named_features_prioriza_diametro_y_evita_solapes():
    import numpy as np
    import pandas as pd
    from lsi.astronomy.coordinates import stereo_inverse
    from lsi.contracts import DemWindow
    spec = importlib.util.spec_from_file_location("explorer_page", ROOT / "ui" / "pages" / "explorer.py")
    src = (ROOT / "ui" / "pages" / "explorer.py").read_text(encoding="utf-8").replace("\nmain()\n", "\n")   # sin ejecutar la página
    ns: dict = {"__name__": "explorer_page"}
    exec(compile(src, str(spec.origin), "exec"), ns)
    win = DemWindow(np.zeros((100, 100)), 0.0, 100000.0, 100.0)             # 10 × 10 km en x∈[0, 10 000], y∈[90 000, 100 000]
    pts = [("Grande", 5000, 95000, "Crater", 4.0), ("Pegado", 5200, 95100, "Crater", 1.0),    # solapa con Grande → se descarta
           ("Lejano", 1000, 91000, "Mons", 2.0), ("Fuera", 50000, 95000, "Crater", 9.0),
           ("Sitio", 8000, 98000, "Sitio de misión", 9.0)]
    lat, lon = stereo_inverse(np.array([p[1] for p in pts], float), np.array([p[2] for p in pts], float))
    df = pd.DataFrame({"name": [p[0] for p in pts], "lat_deg": lat, "lon_deg_e": lon, "feature_type": [p[3] for p in pts],
                       "diameter_km": [p[4] for p in pts]})
    out = ns["named_features"](win, df)
    assert [o[0] for o in out] == ["Grande", "Lejano"]                       # por diámetro, sin solape, sin «Fuera» ni sitios curados
    assert ns["named_features"](win, None) == []


def _page_ns():
    src = (ROOT / "ui" / "pages" / "explorer.py").read_text(encoding="utf-8").replace("\nmain()\n", "\n")
    ns: dict = {"__name__": "explorer_page"}
    exec(compile(src, "explorer.py", "exec"), ns)
    return ns


def test_capa_iluminacion_muestra_sol_y_porcentaje_en_ambas_vistas(at):
    at.radio(key="_x_layer").set_value("iluminacion").run()
    assert not at.exception
    assert any(m.value.startswith("**Sol: acimut") and "% del recorte iluminado" in m.value for m in at.markdown)
    assert at.slider(key="_x_t") is not None
    assert len(at.get("plotly_chart")) >= 2                                      # mapa 2D y 3D con la misma capa


def test_sun_at_interpola_y_avisa_fuera_de_periodo():
    from datetime import datetime
    from types import SimpleNamespace as NS
    import numpy as np
    ns = _page_ns()
    res = NS(request=NS(start_utc="2026-12-16T00:00:00", step_s=3600.0),
             sky=NS(et=np.arange(5.0), sun=NS(az_deg=np.array([350.0, 10.0, 30.0, 50.0, 70.0]), el_deg=np.array([0.0, 1.0, 2.0, 3.0, 4.0]))))
    az, el, ok = ns["sun_at"](res, datetime(2026, 12, 16, 0, 30))
    assert ok and az == pytest.approx(0.0, abs=1e-6) and el == pytest.approx(0.5)      # 350°→10° cruza el norte
    assert ns["sun_at"](res, datetime(2026, 12, 17))[2] is False


def test_lighting_payload_es_serializable_y_coherente():
    import json
    import numpy as np
    from lsi.astronomy.coordinates import stereo_forward
    from lsi.contracts import DemWindow
    ns = _page_ns()
    x, y = (float(v) for v in stereo_forward(-85.98, 2.6))
    z = np.zeros((40, 50))
    z[:, 30:] = 300.0                                            # muro con el Sol rasante: parte del recorte queda en sombra
    win = DemWindow(z, x - 1000, y + 1000, 40.0)
    p = ns["lighting_payload"](win, -85.98, 2.6, 90.0, 2.0)
    json.dumps(p)
    import base64
    sh = np.frombuffer(base64.b64decode(p["shadow_u8"]), np.uint8).reshape(p["shape"])
    assert p["shape"] == [40, 50] and sh.min() == 0 and sh.max() == 255 and 0.0 < p["shadow_pct"] < 100.0
    assert len(base64.b64decode(p["hillshade_u8"])) == 40 * 50 and set(p["sun"]) == {"az_deg", "el_deg", "grid_az_deg"}
