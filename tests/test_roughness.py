"""T09: rugosidad RMS detrendada."""
import numpy as np
import pytest

from lsi.contracts import DemLayer, DemWindow
from lsi.data.loader import discover_dems, read_window
from lsi.terrain.roughness import roughness_by_scale_m, roughness_rms_m

PX = 5.0
X0, Y0 = 400.0, -400.0  # centro (fila 80, col 80) de una ventana 161x161 con (x0,y0)=(0,0)


def _win(z):
    return DemWindow(data=np.asarray(z, dtype=np.float64), x0_m=0.0, y0_m=0.0, pixel_size_m=PX)


def test_flat_and_tilted_plane_have_zero_roughness():
    i, j = np.mgrid[0:161, 0:161]
    tilted = 0.3 * j * PX - 0.1 * i * PX + 50.0
    assert roughness_rms_m(_win(np.full((161, 161), 5.0)), X0, Y0, 50.0) == pytest.approx(0.0, abs=1e-9)
    assert roughness_rms_m(_win(tilted), X0, Y0, 50.0) == pytest.approx(0.0, abs=1e-8)
    assert roughness_rms_m(_win(tilted), X0, Y0, 50.0, detrend=False) == pytest.approx(0.3162 * 50 / 2, rel=0.02)  # std de un plano en disco: |g|·r/2;   # sin detrend ve la inclinación


def test_known_noise_sigma_on_top_of_tilt():
    sigma = 0.5
    j = np.arange(161)[None, :] * np.ones((161, 1))
    z = 0.2 * j * PX + np.random.default_rng(42).normal(0.0, sigma, (161, 161))
    assert roughness_rms_m(_win(z), X0, Y0, 100.0) == pytest.approx(sigma, rel=0.03)
    s = roughness_by_scale_m(_win(z), X0, Y0, (50.0, 100.0))
    assert set(s) == {50.0, 100.0} and s[50.0] == pytest.approx(sigma, rel=0.10)


def test_checkerboard_amplitude():
    i, j = np.mgrid[0:161, 0:161]
    z = np.where((i + j) % 2 == 0, 1.0, -1.0)
    assert roughness_rms_m(_win(z), X0, Y0, 100.0) == pytest.approx(1.0, abs=0.01)


def test_nodata_excluded_and_insufficient_is_nan():
    z = np.random.default_rng(0).normal(0, 0.5, (161, 161))
    z[::2, ::2] = np.nan
    assert np.isfinite(roughness_rms_m(_win(z), X0, Y0, 50.0))
    assert np.isnan(roughness_rms_m(_win(np.full((161, 161), np.nan)), X0, Y0, 50.0))   # nunca 0
    assert np.isnan(roughness_rms_m(_win(z), 10.0, -10.0, 50.0))                        # disco fuera


@pytest.mark.needs_dem
@pytest.mark.parametrize("x,y,r50,r100", [(-998.0, -7003.0, 0.82, 1.18), (-2773.0, -6143.0, 1.51, 2.32),
                                          (-1628.0, -11198.0, 1.06, 2.81)])
def test_measured_roughness_site04(raw_dir, x, y, r50, r100):
    refs = discover_dems(raw_dir)
    if "Site04" not in refs:
        pytest.skip("falta Site04")
    surf = read_window(refs["Site04"], DemLayer.SURF, (x - 150, y - 150, x + 150, y + 150))
    got = roughness_by_scale_m(surf, x, y, (50.0, 100.0))
    assert got[50.0] == pytest.approx(r50, abs=0.01) and got[100.0] == pytest.approx(r100, abs=0.01)
