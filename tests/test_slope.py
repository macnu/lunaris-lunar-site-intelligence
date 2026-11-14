"""T09: pendiente. Valores esperados independientes (geometría analítica y medidas del geólogo)."""
import numpy as np
import pytest

from lsi.contracts import DemLayer, DemWindow, ObserverOutsideDemError
from lsi.data.loader import discover_dems, read_window
from lsi.terrain.slope import footprint_area_below_pct, footprint_slope, slope_map_deg

PX = 5.0
# Píxel (fila 40, col 40) de una ventana 81x81 con (x0,y0)=(0,0): x=200, y=-200
P = (200.0, -200.0)
_I = np.arange(-10, 11)
DISK50 = (np.add.outer(_I ** 2, _I ** 2) <= 100)   # disco r=50 m = 10 px
N50 = int(DISK50.sum())


def _win(z, layer=DemLayer.SURF):
    return DemWindow(data=np.asarray(z, dtype=np.float64), x0_m=0.0, y0_m=0.0, pixel_size_m=PX, layer=layer)


def _plane(deg, axis="x", shape=(81, 81)):
    t = np.tan(np.radians(deg))
    if axis == "x":
        return np.tile(np.arange(shape[1]) * PX * t, (shape[0], 1))
    return np.tile((np.arange(shape[0]) * PX * t)[:, None], (1, shape[1]))


def test_flat_is_zero_and_borders_nan():
    s = slope_map_deg(_win(np.full((20, 20), 123.0)))
    assert np.all(s[1:-1, 1:-1] == 0.0)
    assert np.isnan(s[0]).all() and np.isnan(s[:, -1]).all()


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("deg", [3.0, 10.0, 31.9])
def test_tilted_plane_exact_angle(deg, axis):
    w = _win(_plane(deg, axis))
    assert np.nanmax(np.abs(slope_map_deg(w) - deg)) < 1e-9
    assert np.nanmax(np.abs(slope_map_deg(w, 20.0) - deg)) < 1e-9
    st = footprint_slope(w, *P, 50.0)
    assert st.percentile_deg == pytest.approx(deg, abs=1e-9) and st.mean_deg == pytest.approx(deg, abs=1e-9)
    assert st.source == "surf_central_diff_10m" and st.n_pixels == N50


def test_baseline_must_be_even_multiple():
    with pytest.raises(ValueError):
        slope_map_deg(_win(np.zeros((9, 9))), 7.0)


def test_nodata_is_excluded_not_zero():
    z = _plane(10.0)
    z[38:43, 38:43] = np.nan
    st = footprint_slope(_win(z), *P, 50.0)
    assert 0 < st.n_pixels < N50 and st.percentile_deg == pytest.approx(10.0, abs=1e-9)
    allnan = footprint_slope(_win(np.full((81, 81), np.nan)), *P, 50.0)
    assert allnan.n_pixels == 0 and np.isnan(allnan.percentile_deg)


def test_area_below_threshold_and_slp_source():
    s = np.zeros((81, 81))
    s[:, 40:] = 12.0                      # columnas < 40: 0 deg; >= 40: 12 deg
    w = _win(s, DemLayer.SLP)
    a = footprint_area_below_pct(w, *P, (5, 10, 15), 50.0, slp=w)
    assert a[5.0] == pytest.approx(100 * DISK50[:, :10].sum() / N50)
    assert a[10.0] == a[5.0] and a[15.0] == 100.0
    st = footprint_slope(w, *P, 50.0, slp=w)
    assert st.source == "slp" and st.max_deg == 12.0 and st.n_pixels == N50


def test_disk_outside_window_raises():
    with pytest.raises(ObserverOutsideDemError):
        footprint_slope(_win(np.zeros((81, 81))), 10.0, -10.0, 50.0)


# ---------------- DEM real: Site04 (Shackleton) ----------------
@pytest.fixture(scope="module")
def site04(raw_dir):
    refs = discover_dems(raw_dir)
    if "Site04" not in refs or "slp" not in refs["Site04"].paths:
        pytest.skip("falta Site04 surf/slp en data/raw")
    return refs["Site04"]


@pytest.mark.needs_dem
def test_slp_vs_recomputed_surf_site04(site04):
    surf, slp = read_window(site04, DemLayer.SURF), read_window(site04, DemLayer.SLP)
    d = (slope_map_deg(surf, 10.0) - slp.data.astype(np.float64))[20:-20, 20:-20]
    assert np.sqrt(np.nanmean(d ** 2)) <= 0.001          # geólogo: 0,0002° en Shackleton


# (x, y en m de la malla, A_10 %, p90 deg), disco de 100 m: terreno-geologia.md §3.3
_MEDIDOS = [(-998.0, -7003.0, 0.0, 35.5), (-2773.0, -6143.0, 77.4, 12.2), (-1628.0, -11198.0, 82.1, 11.4)]


@pytest.mark.needs_dem
@pytest.mark.parametrize("x,y,a10,p90", _MEDIDOS)
def test_measured_footprint_values_site04(site04, x, y, a10, p90):
    b = (x - 150, y - 150, x + 150, y + 150)
    surf, slp = read_window(site04, DemLayer.SURF, b), read_window(site04, DemLayer.SLP, b)
    st = footprint_slope(surf, x, y, 100.0, 90.0, slp=slp)
    assert st.percentile_deg == pytest.approx(p90, abs=0.06)
    assert footprint_area_below_pct(surf, x, y, (10,), 100.0, slp=slp)[10.0] == pytest.approx(a10, abs=0.15)
    assert footprint_slope(surf, x, y, 100.0, 90.0).percentile_deg == pytest.approx(st.percentile_deg, abs=0.01)
