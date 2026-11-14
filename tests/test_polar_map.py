"""visualization.polar_map: vista sombreada, base cacheada por hash, capas reales u ocultas, nombres sin solapes y figura."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lsi.astronomy.coordinates import stereo_forward
from lsi.contracts import DemNotFoundError
from lsi.data import polar_view as pv
from lsi.visualization import polar_map as pm

ROOT = Path(__file__).resolve().parents[1]


def test_view_from_window_shapes_and_extent(make_dem_window):
    win = make_dem_window(lambda x, y: x * 0.1, pixel_size_m=80.0, x0_m=-8000.0, y0_m=8000.0, shape=(200, 200))
    v = pv.view_from_window(win)
    assert v.n == (200, 200) and v.px == 80.0                       # ≤ ~1300 px: sin promediar
    assert v.extent == (-8040.0, 7960.0, -7960.0, 8040.0)
    assert v.z_at(0.0, 0.0) == pytest.approx(0.0, abs=5.0) and v.z_at(1e6, 0.0) is None
    big = make_dem_window(lambda x, y: 0 * x, pixel_size_m=80.0, shape=(2600, 2600))
    vb = pv.view_from_window(big)
    assert vb.n == (1300, 1300) and vb.px == 160.0 and np.isfinite(vb.shade).all()


def test_compose_rgb_psr_and_layer(make_dem_window):
    v = pv.view_from_window(make_dem_window(lambda x, y: x * 0.05, pixel_size_m=80.0, shape=(40, 40)))
    base, rng = pv.compose_rgb(v)
    assert base.shape == (40, 40, 3) and base.dtype == np.uint8 and rng is None
    mask = np.zeros((40, 40), bool)
    mask[10:30, 10:30] = True
    col = np.linspace(80, 120, 1600).reshape(40, 40).astype(np.float32)
    rgb, rng = pv.compose_rgb(v, col, "temp", mask)
    assert rng is not None and rng[0] < rng[1]
    assert not np.array_equal(rgb[20, 20], base[20, 20])
    assert pv.jpeg_uri(rgb).startswith("data:image/jpeg;base64,")
    only_psr, _ = pv.compose_rgb(v, None, "temp", mask)
    assert only_psr[20, 20, 2] > only_psr[20, 20, 0]               # la PSR se tiñe de azul


def _gaz(rows):
    return pd.DataFrame(rows, columns=["name", "feature_type", "lat_deg", "lon_deg_e", "diameter_km"])


def test_labels_priority_by_diameter_no_overlap_and_more_when_zoomed():
    df = _gaz([("Grande", "Crater", -85.0, 0.0, 100.0), ("Pegado", "Crater", -85.01, 0.0, 30.0),
               ("Lejos", "Crater", -85.0, 90.0, 20.0), ("Minúsculo", "Crater", -86.0, 180.0, 1.0)])
    full = (-304e3, 304e3, -304e3, 304e3)
    names = [lb[0] for lb in pv.label_features(df, full)]
    assert names[0] == "Grande" and "Pegado" not in names and "Lejos" in names and "Minúsculo" not in names
    x, y = stereo_forward(-86.0, 180.0)
    zoom = (x - 5e3, x + 5e3, y - 5e3, y + 5e3)
    assert [lb[0] for lb in pv.label_features(df, zoom)] == ["Minúsculo"]     # al acercarse aparece lo pequeño; fuera de la vista, nada


def test_base_is_cached_by_hash_and_missing_dem_gives_clear_error(tmp_path):
    with pytest.raises(DemNotFoundError, match="fetch_data.py"):
        pv.build_base(tmp_path, tmp_path)
    raw = ROOT / "data" / "raw"
    if not (raw / "lola80s" / "LDEM_80S_80MPP_ADJ.TIF").exists():
        pytest.skip("falta el DEM polar de 80 m")
    a = pv.build_base(raw, tmp_path)
    assert len(list((tmp_path / pv.KIND).glob("*.npz"))) == 1 and a.n[0] > 1000 and abs(a.extent[1] - 304000) < 1000
    b = pv.build_base(raw, tmp_path)                                         # caché caliente: mismo contenido, mismo fichero
    assert np.array_equal(a.z, b.z, equal_nan=True) and np.array_equal(a.shade, b.shade, equal_nan=True)
    assert len(list((tmp_path / pv.KIND).glob("*.npz"))) == 1


def test_layers_hidden_when_files_missing_and_labelled(monkeypatch, make_dem_window):
    from lsi.data import thermal
    v = pv.view_from_window(make_dem_window(lambda x, y: 0 * x, pixel_size_m=80.0, shape=(20, 20)))
    monkeypatch.setattr(thermal, "thermal_available", lambda: False)
    assert pv.layer_array("temp_mean", v) is None                           # nunca se inventa
    assert pv.layer_info("psr")["note"] == "PSR de 18,6 años, no sombra de un periodo"
    assert pv.layer_info("temp_max")["note"] == "Williams et al. 2019, estacional"
    assert pv.layer_info("illum")["note"] == "superficie, 18,6 años"
    with pytest.raises(ValueError):
        pv.layer_available("otra")


def test_figure_has_image_labels_click_grid_and_scale(make_dem_window):
    v = pv.view_from_window(make_dem_window(lambda x, y: x * 0.05, pixel_size_m=80.0, x0_m=-1000.0, y0_m=1000.0, shape=(26, 26)))
    fig = pm.polar_map_figure(v, "data:image/jpeg;base64,AAAA", labels=[("Cráter", 0.0, 0.0, "Crater", 1.0)],
                              recortes=[("Site", (-500, -500, 500, 500))], observer=(0.0, 0.0, "Punto"), click_n=10)
    assert fig.layout.images[0].source.startswith("data:image/jpeg") and fig.layout.xaxis.range[0] < 0
    assert sum(len(t.x) == 100 for t in fig.data if t.name == "clic") == 1
    assert pm.click_precision_km(v, 10) == pytest.approx(2.08 / 9, rel=0.02)
    assert any("km" in (a.text or "") for a in fig.layout.annotations)
