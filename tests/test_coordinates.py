"""Pruebas de astronomy.coordinates: casos P1-P8 y E1-E10 de docs/science/matematica.md."""
import numpy as np
import pytest
from pyproj import CRS, Transformer

from lsi.astronomy.coordinates import (
    enu_basis, normalize_lon, observer_position_km, ray_direction, stereo_forward,
    stereo_inverse, stereo_scale, vector_to_azel,
)
from lsi.contracts import DEM_PROJ4, MOON_RADIUS_KM

STERE = CRS.from_proj4(DEM_PROJ4)
GEO = CRS.from_proj4("+proj=longlat +R=1737400 +no_defs")


def test_p1_p3_forward():
    x, y = stereo_forward(-89.9, 0.0)
    assert abs(x) < 1e-6 and y == pytest.approx(3032.335812, abs=1e-6)
    x, y = stereo_forward(-89.9, 90.0)
    assert x == pytest.approx(3032.335812, abs=1e-6) and abs(y) < 1e-6
    x, y = stereo_forward(-89.9, 180.0)
    assert abs(x) < 1e-6 and y == pytest.approx(-3032.335812, abs=1e-6)


def test_p4_inverse():
    lat, lon = stereo_inverse(3000.0, 4000.0)
    assert lat == pytest.approx(-89.835111, abs=1e-6)
    assert lon == pytest.approx(36.869898, abs=1e-6)


def test_p5_p6_pole_and_scale():
    x, y = stereo_forward(-90.0, 123.0)
    assert abs(x) < 1e-9 and abs(y) < 1e-9
    assert stereo_scale(-90.0) == pytest.approx(1.0)
    assert stereo_scale(-89.9) == pytest.approx(1.0000007615, abs=1e-10)
    lat, lon = stereo_inverse(0.0, 0.0)
    assert (lat, lon) == (-90.0, 0.0)


def test_p7_p8_pixel_centres():
    # Geotransform (5,0,-9000,0,-5,1000): centro del píxel (fila, col) → (x, y); fórmula de contracts.DemWindow
    def cx(c): return -9000 + 5 * (c + 0.5)
    def cy(r): return 1000 - 5 * (r + 0.5)
    assert (cx(1800), cy(200)) == (2.5, -2.5)
    assert (cx(0), cy(0)) == (-8997.5, 997.5)
    assert (cx(3199), cy(3199)) == (6997.5, -14997.5)


def test_vs_pyproj_and_roundtrip():
    rng = np.random.default_rng(0)
    lat = rng.uniform(-90, -80, 5000)
    lon = rng.uniform(0, 360, 5000)
    x, y = stereo_forward(lat, lon)
    px, py = Transformer.from_crs(GEO, STERE, always_xy=True).transform(lon, lat)
    assert np.max(np.abs(x - px)) <= 1e-6 and np.max(np.abs(y - py)) <= 1e-6
    lat2, lon2 = stereo_inverse(x, y)
    assert np.max(np.abs(lat2 - lat)) <= 1e-9
    assert np.max(np.abs(((lon2 - lon + 180) % 360) - 180)) <= 1e-9
    assert lon2.min() >= 0 and lon2.max() < 360


def test_normalize_lon():
    assert normalize_lon(-171.8699) == pytest.approx(188.1301)
    assert normalize_lon(10.0, west_positive=True) == 350.0
    assert normalize_lon(360.0) == 0.0


@pytest.mark.parametrize("lat,lon", [(0, 0), (-90, 0), (-89.9, 129.78), (35, -200)])
def test_enu_orthonormal_right_handed(lat, lon):
    b = enu_basis(lat, lon)
    assert np.allclose(b @ b.T, np.eye(3), atol=1e-12)
    assert np.allclose(np.cross(b[0], b[1]), b[2], atol=1e-12)


# (nombre, lat, lon, v, az esperado | None = cenit/nadir, el esperado)
C5 = np.radians(5)
E_CASES = [
    ("E1", 0, 0, (1, 0, 0), None, 90), ("E2", 0, 0, (-1, 0, 0), None, -90),
    ("E3", 0, 0, (0, 1, 0), 90, 0), ("E4", 0, 0, (0, 0, 1), 0, 0),
    ("E5", -90, 0, (0, 0, -1), None, 90),
    ("E6", -90, 0, (np.cos(C5), 0, -np.sin(C5)), 0, 5),
    ("E7", -90, 0, (0, 1, 0), 90, 0), ("E8", -90, 90, (0, 1, 0), 0, 0),
    ("E9", -90, 180, (1, 0, 0), 180, 0),
]


@pytest.mark.parametrize("name,lat,lon,v,az_e,el_e", E_CASES)
def test_e1_e9(name, lat, lon, v, az_e, el_e):
    az, el, d = vector_to_azel(np.array([v], float), lat, lon)
    assert el[0] == pytest.approx(el_e, abs=1e-9)
    if az_e is None:
        assert az[0] == 0.0  # cenit/nadir documentado
    else:
        assert az[0] == pytest.approx(az_e, abs=1e-9)
    assert d[0] == pytest.approx(np.linalg.norm(v))


def test_e10_parallax():
    p = observer_position_km(0.0, 0.0)
    assert np.allclose(p, [MOON_RADIUS_KM, 0, 0])
    v = np.array([[0.0, 384400.0, 0.0]]) - p
    az, el, _ = vector_to_azel(v, 0.0, 0.0)
    assert az[0] == pytest.approx(90.0, abs=1e-4)
    assert el[0] == pytest.approx(-0.258962, abs=1e-6)


def test_observer_height_and_batch():
    assert np.linalg.norm(observer_position_km(-89.9, 40.0, 2000.0)) == pytest.approx(MOON_RADIUS_KM + 2.0)
    az, el, d = vector_to_azel(np.array([[0, 1, 0], [0, 0, 1.0]]), 0.0, 0.0)
    assert az.shape == el.shape == d.shape == (2,)


def test_ray_direction_matches_plane_north_east():
    dx, dy = ray_direction(0.0, np.array([0.0, 90.0]))
    assert np.allclose(dx, [0, 1], atol=1e-12) and np.allclose(dy, [1, 0], atol=1e-12)
    # Coherente con la proyección: un paso al Norte local aleja del polo conservando la longitud.
    lat, lon, step = -89.9, 40.0, 100.0
    x0, y0 = stereo_forward(lat, lon)
    dx, dy = ray_direction(lon, 0.0)
    lat1, lon1 = stereo_inverse(x0 + step * dx, y0 + step * dy)
    assert lat1 > lat and lon1 == pytest.approx(lon, abs=1e-9)
    # Y un paso al Este (az=90) conserva la latitud (curvatura del paralelo: ~5e-5°) y aumenta la longitud.
    dx, dy = ray_direction(lon, 90.0)
    lat2, lon2 = stereo_inverse(x0 + step * dx, y0 + step * dy)
    assert lon2 > lon and lat2 == pytest.approx(lat, abs=1e-4)
