"""Configuración común de pytest: sys.path, rutas, configs y DEM sintéticos. Sin lógica científica."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

KERNELS = (
    "naif0012.tls", "pck00011.tpc", "moon_080317.tf", "moon_assoc_me.tf",
    "moon_pa_de421_1900-2050.bpc", "de421.bsp",
)


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_spice: requiere kernels en kernels/ (se omite si faltan)")
    config.addinivalue_line("markers", "needs_dem: requiere GeoTIFF en data/raw/ (se omite si faltan)")
    config.addinivalue_line("markers", "slow: pruebas de rendimiento / año completo")


def pytest_collection_modifyitems(config, items):
    no_spice = not all((ROOT / "kernels" / k).exists() for k in KERNELS)
    no_dem = not list((ROOT / "data" / "raw").glob("*/*_surf.tif"))
    for it in items:
        if no_spice and "needs_spice" in it.keywords:
            it.add_marker(pytest.mark.skip(reason="faltan kernels SPICE (python scripts/fetch_data.py)"))
        if no_dem and "needs_dem" in it.keywords:
            it.add_marker(pytest.mark.skip(reason="faltan DEM (python scripts/fetch_data.py)"))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def kernels_dir() -> Path:
    return ROOT / "kernels"


@pytest.fixture(scope="session")
def raw_dir() -> Path:
    return ROOT / "data" / "raw"


@pytest.fixture(scope="session")
def simulation_cfg() -> dict:
    return json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def panels_json() -> dict:
    return json.loads((ROOT / "config" / "panels.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sites_json() -> dict:
    return json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))


@pytest.fixture
def make_dem_window():
    """Fábrica de DemWindow sintéticos: ``make_dem_window(z, pixel_size_m=5.0, x0_m=0.0, y0_m=0.0)``.

    ``z`` es un array 2-D (filas hacia y negativa) o un callable ``z(x_m, y_m) -> array``; si es callable
    hay que pasar ``shape=(filas, cols)``. (x0_m, y0_m) = centro del píxel [0, 0].
    """
    from lsi.contracts import DemLayer, DemWindow

    def _make(z, pixel_size_m=5.0, x0_m=0.0, y0_m=0.0, shape=None, layer=DemLayer.SURF):
        if callable(z):
            rows, cols = shape
            xx = x0_m + pixel_size_m * np.arange(cols)[None, :] * np.ones((rows, 1))
            yy = y0_m - pixel_size_m * np.arange(rows)[:, None] * np.ones((1, cols))
            data = np.asarray(z(xx, yy), dtype=np.float32)
        else:
            data = np.asarray(z, dtype=np.float32)
        return DemWindow(data=data, x0_m=x0_m, y0_m=y0_m, pixel_size_m=pixel_size_m, layer=layer)

    return _make
