"""Visor 3D three.js (ui/terrain_viewer.py): payload determinista y acotado, HTML autocontenido (cero red), escape de etiquetas,
librería vendorizada íntegra y el Explorador con el visor (AppTest: Malapert, Site04, Apolo 11)."""
import hashlib
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from ui import terrain_viewer as TV

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ui" / "static"
EVIL = '</script><img src=x onerror=alert(1)>" &'


def _scene(n=64, names=(("Shackleton", 100.0, -50.0, "Crater", 21.0),), seed=3, photo=True):
    rng = np.random.default_rng(seed)
    z = np.cumsum(np.cumsum(rng.normal(size=(n, n)), 0), 1) * 0.5
    z[0, 0] = np.nan
    ph = rng.integers(1, 255, size=(n, n)).astype(np.uint8) if photo else None
    pv = np.ones((n, n), bool)
    pv[:, : n // 4] = False
    return TV.build_scene(
        heights=z, x0_m=-100.0, y0_m=100.0, px_m=5.0, illum=rng.random((n, n)), photo=ph, photo_valid=pv if photo else None,
        photo_source="sdem", photo_native_px_m=5.0,
        obs=dict(x=0.0, y=0.0, lat=-85.9, lon=2.6, h=2.0, z=0.0, label="Punto", north_deg=0.0),
        sun=dict(az_deg=95.0, el_deg=1.0, grid_az_deg=97.0, el_c_deg=1.0, radius_deg=0.267),
        earth=dict(az_deg=350.0, el_deg=5.7, radius_deg=0.95), horizon_az=np.arange(0, 360, 2.0), horizon_el=np.full(180, 1.5),
        names=names, when_utc="2026-12-16 00:00", lit_pct=47.0)


def test_payload_es_determinista():
    a, b = _scene(), _scene()
    assert TV._json_for_html(a) == TV._json_for_html(b)
    assert TV._json_for_html(a) != TV._json_for_html(_scene(seed=4))


def test_payload_acotado_y_submuestreado():
    s = _scene(n=700)                                   # > 512: se submuestrea por bloques y sigue acotado
    assert max(s["nx"], s["ny"]) <= TV.MAX_SIDE and s["px_m"] == pytest.approx(10.0)
    assert s["_bytes"] < TV.MAX_PAYLOAD_BYTES
    import base64
    assert len(base64.b64decode(s["z"]["b64"])) == s["nx"] * s["ny"] * 2


def test_sin_foto_no_se_inventa_textura():
    s = _scene(photo=False)
    assert s["photo"]["source"] == "none" and "no se inventa" in s["photo"]["notice"]
    import base64, io
    from PIL import Image
    t = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["tex_png"]))))
    assert t[..., 1].max() == 0                        # máscara de foto vacía
    s2 = _scene()
    assert "≈5 m/px de origen" in s2["photo"]["notice"] and "no es la luz de esta fecha" in s2["photo"]["notice"]
    assert s2["photo"]["nophoto_xz"] is not None       # un cuarto del recorte sin foto: rótulo en su centroide


def _extras():
    from lsi.data import viewer_context as VC
    n = VC.CTX_N
    ctx = dict(heights=np.random.default_rng(1).normal(size=(n, n)).astype(np.float32) * 50, lit=np.random.default_rng(2).random((n, n)).astype(np.float32),
               x0_m=-20000.0, y0_m=20000.0, step_m=40000.0 / (n - 1), half_m=20000.0, n=n)
    z = np.random.default_rng(3).normal(size=(281, 281)).astype(np.float32)
    patch = dict(heights=z, x0_m=-350.0, y0_m=350.0, step_m=2.5, half_m=350.0, n=281, native_px_m=5.0)
    return ctx, patch


def test_payload_con_contexto_y_parche_acotado():
    ctx, patch = _extras()
    rng = np.random.default_rng(3)
    s = TV.build_scene(heights=rng.normal(size=(64, 64)), x0_m=-100.0, y0_m=100.0, px_m=5.0, illum=rng.random((64, 64)), photo=None, photo_valid=None,
                       photo_source="none", photo_native_px_m=5.0, obs=dict(x=0.0, y=0.0, lat=-85.9, lon=2.6, h=2.0, z=0.0, label="P", north_deg=0.0),
                       sun=dict(az_deg=95.0, el_deg=1.0, grid_az_deg=97.0, el_c_deg=1.0, radius_deg=0.267),
                       earth=dict(az_deg=350.0, el_deg=5.7, radius_deg=0.95), horizon_az=[], horizon_el=[], names=(), when_utc="x", lit_pct=1.0,
                       context=ctx, patch=patch, psr_pct=80.0)
    assert s["_bytes_crop"] < TV.MAX_PAYLOAD_BYTES and 0 < s["_bytes_extra"] < 1_500_000
    assert s["_bytes"] == s["_bytes_crop"] + s["_bytes_extra"]
    assert "permanentemente sombreada" in s["photo"]["notice"] and "ShadowCam no está integrada" in s["photo"]["notice"]
    assert s["ctx"]["n"] <= 160 and s["patch"]["step_m"] == 2.5
    html = TV.viewer_html(s)
    assert "http" not in TV._BODY and not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert "Microrrelieve" in TV._BODY and "microrrelieve procedural: no es dato" in TV._assets()[3]


def test_aviso_psr_solo_si_la_falta_de_foto_es_psr():
    assert "permanentemente" not in TV.photo_notice("sdem", 5.0, 12.0, 40.0, 10.0)[0]
    assert "permanentemente" not in TV.photo_notice("sdem", 5.0, 12.0, 1.0, 90.0)[0]     # casi todo con foto: no se explica nada
    assert "permanentemente" in TV.photo_notice("nac", 1.0, 15.0, 40.0, 90.0)[0]


def test_html_autocontenido_sin_red():
    html = TV.viewer_html(_scene())
    assert "<link" not in html and not re.search(r"<script[^>]+src=", html)
    for own in (TV.STATIC / "terrain_viewer.js", TV.STATIC / "terrain_viewer.css"):
        assert "http" not in own.read_text(encoding="utf-8"), own.name        # nada de URLs en nuestro código
    assert "http" not in TV._BODY
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert not re.search(r"url\(\s*['\"]?https?:", html) and "@import" not in html
    for api in ("fetch(", "XMLHttpRequest", "WebSocket(", "importScripts", "sendBeacon"):
        assert api not in TV._assets()[3], api
    assert "THREE.WebGLRenderer" in html and 'id="lsi-data"' in html


def test_escape_de_nombre_malicioso():
    s = _scene(names=((EVIL, 1.0, 2.0, "Crater", 5.0),))
    html = TV.viewer_html(s)
    assert "</script><img" not in html and "onerror=alert(1)>" not in html.split('id="lsi-data">')[1].split("</script>")[0]
    data = html.split('id="lsi-data">')[1].split("</script>")[0]
    assert json.loads(data)["names"][0][0] == EVIL                              # se recupera íntegro, como TEXTO
    js = TV._assets()[3]
    assert "innerHTML" not in js and "textContent" in js                        # las etiquetas se pintan con textContent


def test_vendor_integro_y_con_licencia():
    m = json.loads((STATIC / "vendor" / "MANIFEST.json").read_text("utf-8"))
    assert m["version"] == "0.147.0" and "MIT" in m["license"]
    for name, info in m["files"].items():
        raw = (STATIC / "vendor" / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == info["sha256"] and len(raw) == info["bytes"], name
    assert "MIT License" in (STATIC / "vendor" / "LICENSE").read_text("utf-8")


# ------------------------------------------------------------------------------------------------ Explorador con el visor
@pytest.fixture
def at(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    shutil.copy(ROOT / "ui" / "pages" / "explorer.py", tmp_path / "explorer.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()


@pytest.mark.needs_spice
@pytest.mark.needs_dem
def test_explorador_malapert_site04_degerlache_y_apolo11(at):
    assert not at.exception
    txt = " ".join(e.value for e in (*at.markdown, *at.caption))
    assert "Visor 3D" in txt and "Visor three.js" in txt                       # Malapert (SDEM + foto)
    assert any("Vista alternativa" in e.label for e in at.expander)
    at.sidebar.selectbox(key="_w_site").set_value("site04").run()               # LOLA + mosaico NAC
    assert not at.exception
    assert "Visor three.js" in " ".join(e.value for e in at.caption)
    assert any("Punto cambiado en este visor" in e.value for e in at.info)       # marcador con < 30 % de foto → candidato con foto
    assert any(b.label == "Volver al marcador del sitio" for b in at.button)
    at.sidebar.selectbox(key="_w_site").set_value("site11").run()               # de Gerlache: SDEM + foto
    assert not at.exception
    assert "Terreno lejano: modelo LOLA de 80 m" in " ".join(e.value for e in at.caption)
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()             # esfera lisa: sin visor, aviso de siempre
    assert not at.exception
    assert any("Sin datos de terreno" in w.value for w in at.warning)
    assert "Visor three.js" not in " ".join(e.value for e in at.caption)
