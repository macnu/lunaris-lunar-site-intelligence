"""Datos térmicos (Diviner), PSR (LROC/LOLA) e iluminación publicada (LOLA/PGDA). Se omiten si faltan los datos."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from lsi.astronomy.coordinates import stereo_forward
from lsi.data import illum_ref, psr, thermal

ROOT = Path(__file__).resolve().parents[1]
need_t = pytest.mark.skipif(not thermal.thermal_available(), reason="faltan los mapas Diviner (scripts/fetch_thermal_psr.py)")
need_p = pytest.mark.skipif(not psr.psr_available(), reason="falta el shapefile PSR (scripts/fetch_thermal_psr.py)")
need_i = pytest.mark.skipif(not illum_ref.illum_ref_available(), reason="faltan los mapas AVGVISIB (scripts/fetch_thermal_psr.py)")
CX, CY, HALF, NPX = -1000.0, -7000.0, 8000.0, 200       # recorte tipo Site04


def _aligned(w):
    n = w["data"].shape[0]
    assert w["data"].shape == (n, n)
    assert w["pixel_size_m"] * n == pytest.approx(2 * HALF)
    assert w["x0_m"] == pytest.approx(CX - HALF + w["pixel_size_m"] / 2)
    assert w["y0_m"] == pytest.approx(CY + HALF - w["pixel_size_m"] / 2)


@need_t
@pytest.mark.parametrize("kind", ["mean", "max", "min"])
def test_thermal_window_alineada_y_en_kelvin(kind):
    w = thermal.thermal_window("Site04", CX, CY, HALF, NPX, kind)
    _aligned(w)
    d = w["data"]
    assert np.isfinite(d).mean() > 0.95
    assert 20.0 < np.nanmin(d) and np.nanmax(d) < 450.0       # Diviner polar: decenas a ~300-400 K
    assert w["units"] == "K" and "Williams" in w["attribution"] and "doi" in w["attribution"]


@need_t
def test_orden_min_mean_max_y_punto_frio_shackleton():
    x, y = (float(v) for v in stereo_forward(-89.67, 129.78))     # suelo de Shackleton: PSR fría (Paige 2010: ~38 K)
    tmin, tmean, tmax = (thermal.thermal_at(x, y, k) for k in ("min", "mean", "max"))
    assert tmin <= tmean <= tmax and tmax < 120.0 and tmin < 60.0
    w = thermal.thermal_window("Site04", x, y, 3000.0, 25, "max")
    assert w["data"][12, 12] == pytest.approx(tmax, abs=15.0)     # el píxel central concuerda con el punto


@need_t
def test_thermal_fuera_de_cobertura_es_none_y_kind_invalido():
    assert thermal.thermal_window("x", 2e6, 2e6, 1000.0, 10) is None
    with pytest.raises(ValueError):
        thermal.thermal_window("x", 0.0, 0.0, 1000.0, 10, kind="medio")


@need_p
def test_psr_mascara_bool_y_distancia_coherentes():
    w = psr.psr_mask_window("Site04", CX, CY, HALF, NPX)
    _aligned(w)
    assert w["data"].dtype == bool and 0.05 < w["data"].mean() < 0.8 and "Mazarico" in w["attribution"]
    n = w["data"].shape[0]
    rows, cols = np.random.default_rng(0).integers(0, n, (2, 150))
    x = w["x0_m"] + cols * w["pixel_size_m"]
    y = w["y0_m"] - rows * w["pixel_size_m"]
    d = psr.psr_distance_m(x, y)
    lejos = np.abs(d) > 1.5 * w["pixel_size_m"]                    # lejos del borde, la máscara y el signo coinciden
    assert lejos.sum() > 50 and ((d[lejos] < 0) == w["data"][rows, cols][lejos]).all()


@need_p
def test_psr_shackleton_dentro():
    x, y = (float(v) for v in stereo_forward(-89.67, 129.78))
    assert psr.psr_distance_m(x, y) < -1000.0


@need_i
def test_illum_ref_ventana_fraccion_y_puntos_conocidos():
    w = illum_ref.illum_ref_window("Site04", CX, CY, HALF, NPX)
    _aligned(w)
    assert 0.0 <= np.nanmin(w["data"]) and np.nanmax(w["data"]) <= 1.0 and w["units"] == "fraction"
    assert "Mazarico" in w["attribution"]
    x, y = (float(v) for v in stereo_forward(-89.67, 129.78))      # PSR: sin Sol en 18,6 años
    assert illum_ref.illum_ref_at(x, y)["value"] < 0.01
    xm, ym = (float(v) for v in stereo_forward(-85.98, -1.67))     # Malapert: iluminado (cima ~40-70 %)
    assert 0.2 < illum_ref.illum_ref_at(xm, ym)["max3"] < 0.9


def test_fetch_help_no_descarga():
    side = ROOT / "data" / "raw" / "diviner" / "SHA256SUMS.json"
    before = side.stat().st_mtime_ns if side.exists() else None
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_thermal_psr.py"), "--help"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "usage" in r.stdout.lower() and "baja" not in r.stdout
    assert (side.stat().st_mtime_ns if side.exists() else None) == before
