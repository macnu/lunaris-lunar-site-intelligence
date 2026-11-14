"""data.loader: descubrimiento, CRS por parámetros, ventanas, nodata, sha256 (sintético + real Site04)."""
import hashlib

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from lsi.contracts import (
    DEM_PROJ4,
    DemCrsMismatchError,
    DemLayer,
    DemNotFoundError,
    ObserverOutsideDemError,
)
from lsi.data import loader
from lsi.data.loader import (
    dem_sha256,
    discover_dems,
    discover_far_field,
    find_dem_for_point,
    load_far_field,
    read_metadata,
    read_window,
    validity_mask,
)

WKT_UNNAMED = (  # como Site04/surf
    'PROJCS["unnamed",GEOGCS["unnamed ellipse",DATUM["unknown",SPHEROID["unnamed",1737400,0]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Polar_Stereographic"],'
    'PARAMETER["latitude_of_origin",-90],PARAMETER["central_meridian",0],PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],UNIT["metre",1]]'
)
WKT_UNKNOWN = (  # mismo CRS que Malapert/toterr: otro NOMBRE, mismos parámetros
    'PROJCS["unknown",GEOGCS["unknown",DATUM["unknown",SPHEROID["unknown",1737400,0]],'
    'PRIMEM["Reference meridian",0],UNIT["degree",0.0174532925199433]],PROJECTION["Polar_Stereographic"],'
    'PARAMETER["latitude_of_origin",-90],PARAMETER["central_meridian",0],PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],UNIT["metre",1]]'
)


def _write(path, data, crs=None, nodata=np.nan, x0=-100.0, y0=50.0, px=5.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    crs = crs or CRS.from_string(DEM_PROJ4)
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype="float32", crs=crs, transform=Affine(px, 0, x0, 0, -px, y0), nodata=nodata) as d:
        d.write(data.astype(np.float32), 1)


@pytest.fixture
def raw(tmp_path):
    z = (np.arange(40 * 60, dtype=np.float32).reshape(40, 60)) / 10
    _write(tmp_path / "raw" / "sitio" / "Site99_final_adj_5mpp_surf.tif", z,
           crs=CRS.from_wkt(WKT_UNNAMED))
    _write(tmp_path / "raw" / "sitio" / "Site99_final_adj_5mpp_toterr.tif", z * 0 + 0.3, crs=CRS.from_wkt(WKT_UNKNOWN))
    return tmp_path / "raw", z


def test_discover(raw, tmp_path):
    raw_dir, _ = raw
    refs = discover_dems(raw_dir)
    assert list(refs) == ["Site99"]
    assert set(refs["Site99"].paths) == {"surf", "toterr"}
    assert refs["Site99"].bounds_xy_m == (-100.0, 50.0 - 200.0, -100.0 + 300.0, 50.0)
    assert discover_dems(tmp_path / "no_existe") == {}


def test_crs_compared_by_parameters(raw):
    ref = discover_dems(raw[0])["Site99"]
    t, s = rasterio.open(ref.paths["toterr"]), rasterio.open(ref.paths["surf"])
    assert t.crs != s.crs   # el nombre difiere (como Malapert)...
    assert read_metadata(ref, DemLayer.TOTERR).dtype == "float32"   # ...y aun así se acepta


def test_crs_mismatch_and_missing_layer(tmp_path):
    _write(tmp_path / "raw" / "x" / "Site98_final_adj_5mpp_surf.tif", np.zeros((4, 4)),
           crs=CRS.from_string("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737401 +units=m +no_defs"))
    with pytest.raises(DemCrsMismatchError):
        discover_dems(tmp_path / "raw")
    _write(tmp_path / "raw2" / "x" / "Site97_final_adj_5mpp_surf.tif", np.zeros((4, 4)), crs=CRS.from_epsg(4326))
    with pytest.raises(DemCrsMismatchError):
        discover_dems(tmp_path / "raw2")


def test_missing_layer_raises(raw):
    ref = discover_dems(raw[0])["Site99"]
    with pytest.raises(DemNotFoundError):
        read_window(ref, DemLayer.LDEC)


def test_window_full_and_subwindow_centered(raw):
    raw_dir, z = raw
    ref = discover_dems(raw_dir)["Site99"]
    full = read_window(ref)
    assert full.data.dtype == np.float32 and full.data.shape == (40, 60)
    assert (full.x0_m, full.y0_m) == (-97.5, 47.5)
    # sub-ventana: el centro de su píxel [0,0] debe coincidir con el centro del píxel (r,c) global
    sub = read_window(ref, bounds_xy_m=(-50.0, -20.0, 0.0, 0.0), margin_px=1)
    r, c = sub.row_offset, sub.col_offset
    assert (sub.x0_m, sub.y0_m) == (-97.5 + 5 * c, 47.5 - 5 * r)
    np.testing.assert_array_equal(sub.data, z[r:r + sub.data.shape[0], c:c + sub.data.shape[1]])
    assert sub.data.shape == (4 + 2, 10 + 2) and sub.meta.key == "Site99"
    with pytest.raises(ObserverOutsideDemError):
        read_window(ref, bounds_xy_m=(1000.0, 1000.0, 1100.0, 1100.0))
    clip = read_window(ref, bounds_xy_m=(-5000.0, -5000.0, 5000.0, 5000.0))   # recorte al raster
    assert clip.data.shape == (40, 60) and clip.col_offset == 0


def test_nodata_numeric_becomes_nan_not_zero(tmp_path):
    z = np.full((6, 6), 7.0, dtype=np.float32)
    z[1, 1] = -9999.0
    z[2, 2] = 0.0   # un cero real es dato válido
    _write(tmp_path / "raw" / "s" / "Site96_final_adj_5mpp_surf.tif", z, nodata=-9999.0)
    ref = discover_dems(tmp_path / "raw")["Site96"]
    w = read_window(ref)
    assert np.isnan(w.data[1, 1]) and w.data[2, 2] == 0.0
    m = validity_mask(w)
    assert not m[1, 1] and m[2, 2] and m.sum() == 35
    assert read_metadata(ref).nodata == -9999.0


def test_validity_mask_synthetic(make_dem_window):
    z = np.ones((3, 3))
    z[0, 0], z[1, 1] = np.nan, np.inf
    m = validity_mask(make_dem_window(z))
    assert m.sum() == 7 and not m[0, 0] and not m[1, 1]


def test_sha256_and_sidecar(raw):
    raw_dir, _ = raw
    ref = discover_dems(raw_dir)["Site99"]
    expected = hashlib.sha256(open(ref.paths["surf"], "rb").read()).hexdigest()
    assert dem_sha256(ref) == expected
    sidecar = raw_dir.parent / "processed" / "dem_hash.json"
    assert sidecar.exists()
    sidecar.write_text(sidecar.read_text().replace(expected, "0" * 64))   # prueba que el acierto de caché se usa
    assert dem_sha256(ref) == "0" * 64
    m = read_metadata(ref)
    assert m.sha256 == "0" * 64 and m.size_bytes > 0 and m.pixel_size_m == 5.0
    assert m.transform == (5.0, 0.0, -100.0, 0.0, -5.0, 50.0) and (m.width_px, m.height_px) == (60, 40)


def test_sha256_invalidated_on_change(raw):
    raw_dir, z = raw
    ref = discover_dems(raw_dir)["Site99"]
    h1 = dem_sha256(ref)
    _write(raw_dir / "sitio" / "Site99_final_adj_5mpp_surf.tif", z + 1)
    assert dem_sha256(ref) != h1


def test_find_dem_for_point(raw):
    refs = discover_dems(raw[0])
    assert find_dem_for_point(refs, 0.0, 0.0).key == "Site99"
    assert find_dem_for_point(refs, 0.0, 0.0, margin_m=10.0).key == "Site99"
    assert find_dem_for_point(refs, -95.0, 0.0, margin_m=10.0) is None
    assert find_dem_for_point(refs, 500.0, 0.0) is None
    assert find_dem_for_point({}, 0.0, 0.0) is None


# ---- DEM real ---------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def site04(request):
    raw_dir = request.config.rootpath / "data" / "raw"
    ref = discover_dems(raw_dir).get("Site04") if raw_dir.exists() else None
    if ref is None:
        pytest.skip("Site04 no está en data/raw")
    return ref


@pytest.mark.needs_dem
def test_real_site04_metadata(site04):
    m = read_metadata(site04)
    assert (m.width_px, m.height_px, m.pixel_size_m) == (3200, 3200, 5.0)
    assert m.transform == (5.0, 0.0, -9000.0, 0.0, -5.0, 1000.0)
    assert m.bounds_xy_m == (-9000.0, -15000.0, 7000.0, 1000.0)
    assert m.dtype == "float32" and len(m.sha256) == 64
    assert m.sha256 == dem_sha256(site04)
    assert "Polar_Stereographic" in m.crs_wkt and "1737400" in m.crs_wkt


@pytest.mark.needs_dem
def test_real_site04_window_matches_rasterio(site04):
    w = read_window(site04, bounds_xy_m=(-100.0, -100.0, 100.0, 100.0), margin_px=2)
    assert w.data.dtype == np.float32 and not np.isnan(w.data).any()
    with rasterio.open(site04.paths["surf"]) as d:
        full = d.read(1)
        assert d.xy(0, 0) == (-8997.5, 997.5)               # P8
    r, c = w.row_offset, w.col_offset
    np.testing.assert_array_equal(w.data, full[r:r + w.data.shape[0], c:c + w.data.shape[1]])
    # centro del píxel (200, 1800) = (+2.5, -2.5) (P7)
    col, row = (2.5 - w.x0_m) / 5.0, (w.y0_m + 2.5) / 5.0
    assert (round(row) + r, round(col) + c) == (200, 1800)
    assert validity_mask(w).all()


@pytest.mark.needs_dem
def test_real_all_layers_and_crs_for_every_site(raw_dir):
    refs = discover_dems(raw_dir)
    assert refs
    for ref in refs.values():
        for layer in DemLayer:
            if layer.value in ref.paths:
                assert read_metadata(ref, layer).pixel_size_m == 5.0   # incluye Malapert/toterr
    p = find_dem_for_point(refs, 2.5, -2.5)
    assert p is not None and p.key == "Site04"


# ------------------------------------------------------------------ campo lejano (LOLA 80 m)
def _far_raw(tmp_path, crs=None):
    z = np.arange(100 * 100, dtype=np.float32).reshape(100, 100)
    z[0, 0] = np.nan
    _write(tmp_path / "raw" / "lola80s" / "LDEM_80S_80MPP_ADJ.TIF", z, crs=crs, x0=-4000.0, y0=4000.0, px=80.0)
    return tmp_path / "raw", z


def test_far_field_absent(tmp_path):
    assert discover_far_field(tmp_path) is None
    with pytest.raises(DemNotFoundError):
        load_far_field(tmp_path)


def test_far_field_full_and_window_centered(tmp_path):
    raw_dir, z = _far_raw(tmp_path, crs=CRS.from_wkt(WKT_UNKNOWN))
    full = load_far_field(raw_dir)
    assert full.data.shape == (100, 100) and full.pixel_size_m == 80.0 and np.isnan(full.data[0, 0])
    assert full.x0_m == -4000.0 + 40.0 and full.meta.sha256 == hashlib.sha256((raw_dir / "lola80s" / "LDEM_80S_80MPP_ADJ.TIF").read_bytes()).hexdigest()
    assert not validity_mask(full)[0, 0] and validity_mask(full).sum() == 100 * 100 - 1
    w = load_far_field(raw_dir, 0.0, 0.0, 800.0, margin_px=0)          # solo ±800 m: 20 px, no el raster entero
    assert w.data.shape == (20, 20) and w.col_offset == 40 and w.row_offset == 40
    np.testing.assert_array_equal(w.data, z[40:60, 40:60])
    assert w.x0_m == full.x0_m + 80.0 * 40 and w.meta.sha256 == full.meta.sha256


def test_far_field_crs_mismatch(tmp_path):
    bad = CRS.from_string("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737401 +units=m +no_defs")
    raw_dir, _ = _far_raw(tmp_path, crs=bad)
    with pytest.raises(DemCrsMismatchError):
        discover_far_field(raw_dir)


@pytest.mark.needs_dem
def test_real_far_field(raw_dir):
    ref = discover_far_field(raw_dir)
    if ref is None:
        pytest.skip("falta LDEM_80S_80MPP_ADJ.TIF")
    full = read_metadata(ref)
    assert (full.width_px, full.height_px, full.pixel_size_m) == (7600, 7600, 80.0)
    assert full.bounds_xy_m == (-304000.0, -304000.0, 304000.0, 304000.0) and len(full.sha256) == 64
    w = load_far_field(raw_dir, 0.0, 0.0, 30000.0)
    assert w.data.size < 0.01 * 7600 * 7600 and w.data.dtype == np.float32
    assert 1100.0 < float(w.data[w.data.shape[0] // 2, w.data.shape[1] // 2]) < 1500.0   # en el polo ~1282 m
