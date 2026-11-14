"""terrain.sampling: bilineal centrada con máscara de validez (DEM sintético + real Shackleton)."""
import numpy as np
import pytest

from lsi.contracts import DemLayer
from lsi.data.loader import discover_dems, read_window
from lsi.terrain.sampling import pixel_coords, sample_bilinear

PLANE = lambda x, y: 100.0 + 0.3 * x - 0.7 * y   # noqa: E731  (el plano se reproduce exacto con bilineal)


def test_pixel_coords_centered(make_dem_window):
    w = make_dem_window(PLANE, pixel_size_m=5.0, x0_m=-8997.5, y0_m=997.5, shape=(10, 10))
    col, row = pixel_coords(w, np.array([-8997.5, -8992.5]), np.array([997.5, 992.5]))
    assert col.tolist() == [0.0, 1.0] and row.tolist() == [0.0, 1.0]
    c, r = pixel_coords(w, np.array([-9000.0]), np.array([1000.0]))   # esquina del raster = -0.5 px
    assert (c[0], r[0]) == (-0.5, -0.5)


def test_plane_exact_and_nodes(make_dem_window):
    w = make_dem_window(PLANE, pixel_size_m=5.0, x0_m=-100.0, y0_m=50.0, shape=(20, 30))
    rng = np.random.default_rng(1)
    x = rng.uniform(-100, -100 + 5 * 29, 500)
    y = rng.uniform(50 - 5 * 19, 50, 500)
    v, ok = sample_bilinear(w, x, y)
    assert ok.all()
    np.testing.assert_allclose(v, PLANE(x, y), atol=1e-3)   # float32 en memoria
    v, ok = sample_bilinear(w, np.array([-100.0, -100 + 5 * 29]), np.array([50.0, 50 - 5 * 19]))   # centros de borde
    assert ok.all()


def test_midpoint_of_four_pixels(make_dem_window):
    w = make_dem_window(np.array([[0.0, 10.0], [20.0, 30.0]]), pixel_size_m=5.0, x0_m=0.0, y0_m=0.0)
    v, ok = sample_bilinear(w, np.array([2.5]), np.array([-2.5]))
    assert ok[0] and v[0] == pytest.approx(15.0)


def test_outside_is_invalid_minus_inf(make_dem_window):
    w = make_dem_window(PLANE, x0_m=0.0, y0_m=0.0, shape=(10, 10))
    v, ok = sample_bilinear(w, np.array([-0.1, 45.1, 10.0, np.nan, np.inf]), np.array([0.0, 0.0, 0.1, 0.0, 0.0]))
    assert not ok.any() and np.all(v == -np.inf)


def test_nan_neighbour_invalidates_and_never_zero(make_dem_window):
    z = np.full((6, 6), 50.0)
    z[2, 3] = np.nan
    w = make_dem_window(z, pixel_size_m=5.0, x0_m=0.0, y0_m=0.0)
    # (col 2.5,row 2.5) toca el NaN; (col 0.5,row 0.5) no
    v, ok = sample_bilinear(w, np.array([12.5, 2.5, 15.0]), np.array([-12.5, -2.5, -10.0]))
    assert ok.tolist() == [False, True, False]
    assert v[0] == -np.inf and v[1] == pytest.approx(50.0) and v[2] == -np.inf
    assert not np.any(v == 0.0)


def test_shapes_and_scalars(make_dem_window):
    w = make_dem_window(PLANE, x0_m=0.0, y0_m=0.0, shape=(10, 10))
    xs, ys = np.meshgrid([5.0, 12.0], [-5.0, -9.0])
    v, ok = sample_bilinear(w, xs, ys)
    assert v.shape == ok.shape == (2, 2)
    v0, ok0 = sample_bilinear(w, 7.5, -7.5)
    assert v0.shape == () and bool(ok0)


@pytest.mark.needs_dem
def test_real_shackleton_pole(raw_dir):
    ref = discover_dems(raw_dir).get("Site04")
    if ref is None:
        pytest.skip("Site04 no está en data/raw")
    w = read_window(ref, DemLayer.SURF)
    assert (w.x0_m, w.y0_m) == (-8997.5, 997.5)            # matematica.md P8
    v, ok = sample_bilinear(w, np.array([0.0, 2.5]), np.array([0.0, -2.5]))
    assert ok.all()
    assert v[0] == pytest.approx(1289.36, abs=0.01)         # P7: polo en la esquina de 4 píxeles
    assert v[1] == pytest.approx(float(w.data[200, 1800]), abs=1e-3)   # centro del píxel (200, 1800)
    v, ok = sample_bilinear(w, np.array([-9000.0]), np.array([0.0]))   # medio píxel fuera del último centro
    assert not ok[0] and v[0] == -np.inf
