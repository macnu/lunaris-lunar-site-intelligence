"""SDEM de 5 m: script de descarga seguro y paquete de relieve+textura alineado. Los de datos se saltan si faltan."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from lsi.data import sdem

ROOT = Path(__file__).resolve().parents[1]
HAS_DATA = "Malapert_Massif" in sdem.available_regions()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="faltan datos: python scripts/fetch_sdem.py --yes")
# punto del mapa de idoneidad TOP-1 de Site23 (dentro del SDEM, con textura)
CX, CY = -4947.5, 122197.5


def _run(*args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_sdem.py"), *args],
                          capture_output=True, text=True, timeout=60)


def test_help_y_sin_yes_no_descargan():
    manifest = ROOT / "data" / "raw" / "sdem" / "MANIFEST.json"
    antes = manifest.stat().st_mtime_ns if manifest.exists() else None
    h = _run("--help")
    assert h.returncode == 0 and "--yes" in h.stdout
    s = _run()
    assert s.returncode == 0 and "Nada descargado" in s.stdout
    assert (manifest.stat().st_mtime_ns if manifest.exists() else None) == antes


def test_region_por_sitio():
    assert sdem.sdem_region_for("Site23") == "Malapert_Massif"
    assert sdem.sdem_region_for("site11") == "deGerlache_Rim"
    assert sdem.sdem_region_for("Site04") is None          # Shackleton rim no está en las 13 regiones
    assert sdem.sdem_region_for("apollo11") is None


def test_sin_region_devuelve_none():
    assert sdem.terrain_texture_pack("Site04", 0.0, 0.0, 1000.0, 100) is None


@needs_data
def test_paquete_alineado_y_finito():
    p = sdem.terrain_texture_pack("Site23", CX, CY, 1000.0, 1000)
    shape = p["heights"].shape
    assert p["px_m"] == 5.0 and shape == (401, 401)
    for k in ("height_source", "valid", "ortho", "texture_valid"):
        assert p[k].shape == shape
    assert p["heights"].dtype == np.float32 and p["ortho"].dtype == np.uint8
    assert np.isfinite(p["heights"][p["valid"]]).all() and p["valid"].all()
    assert p["texture_valid"].mean() > 0.9 and p["ortho"][p["texture_valid"]].max() > 100
    assert (p["ortho"][~p["texture_valid"]] == 0).all()
    # retícula nativa: el píxel central coincide con el valor crudo del SDEM (valor esperado independiente: rasterio)
    import rasterio
    with rasterio.open(ROOT / "data/raw/sdem/Malapert_Massif/A311_GLDELEV_005.tif") as s:
        raw = next(s.sample([(p["x0_m"] + 200 * 5.0, p["y0_m"] - 200 * 5.0)]))[0]
    assert p["heights"][200, 200] == pytest.approx(raw, abs=1e-3)


@needs_data
def test_recorte_parcial_marca_cobertura():
    # esquina NE del SDEM (x ≤ 10000, y ≤ 132000): el 75 % del recorte queda fuera
    p = sdem.terrain_texture_pack("Site23", 10000.0, 132000.0, 3000.0, 300)
    assert p["valid"].mean() == pytest.approx(0.25, abs=0.02)
    assert not p["texture_valid"][~p["valid"]].any()                 # nunca se inventa textura
    assert np.isnan(p["heights"][~p["valid"]]).all()                 # ni altura fuera de SDEM y LDEM
    assert (p["ortho"][~p["texture_valid"]] == 0).all()
    assert sdem.terrain_texture_pack("Site23", 1e6, 1e6, 1000.0, 100) is None   # sin solape


@needs_data
def test_reduccion_de_resolucion():
    p = sdem.terrain_texture_pack("Site23", CX, CY, 4000.0, 256)
    assert p["heights"].shape == (256, 256) and p["px_m"] == pytest.approx(31.25)
    assert np.isfinite(p["heights"]).all()
