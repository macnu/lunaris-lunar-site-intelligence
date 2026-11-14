"""scripts/precompute_horizons: un DEM sintético pequeño, segunda ejecución sale de caché."""
import importlib.util

import numpy as np


def _load(repo_root):
    spec = importlib.util.spec_from_file_location("precompute_horizons", repo_root / "scripts" / "precompute_horizons.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_idempotente(repo_root, tmp_path, make_dem_window):
    m = _load(repo_root)
    from lsi.astronomy.coordinates import stereo_forward
    from lsi.contracts import DemLayer, DemMetadata
    from lsi.data.catalog import default_observer, load_simulation_config
    x, y = (float(v) for v in stereo_forward(*default_observer(load_simulation_config(repo_root / "config" / "simulation.json"), "Site04")))
    x0, y0 = x - 500.0, y + 500.0   # DEM plano de 1 km centrado en el observador: todos los azimuts quedan limitados por cobertura
    w = make_dem_window(lambda xx, yy: np.zeros_like(xx), pixel_size_m=5.0, x0_m=x0, y0_m=y0, shape=(200, 200))
    w.meta = DemMetadata(key="Site04", layer=DemLayer.SURF, width_px=200, height_px=200, pixel_size_m=5.0,
                         bounds_xy_m=(x0, y0 - 1000, x0 + 1000, y0), transform=(5.0, 0, x0, 0, -5.0, y0), crs_wkt="",
                         nodata=None, dtype="float32", sha256="ab" * 32, size_bytes=0)  # sin sha no se cachea
    kw = dict(root=repo_root, sites=("Site04",), heights=(2.0,), cache_dir=tmp_path, windows={"Site04": w}, log=lambda s: None)
    a = m.precompute(**kw)
    b = m.precompute(**kw)
    assert [r["cached"] for r in a] == [False] and [r["cached"] for r in b] == [True]
    assert a[0]["n_limited"] == b[0]["n_limited"] > 0
    assert "Casos: 1" in m.summary(b)


import pytest  # noqa: E402


@pytest.mark.needs_spice
@pytest.mark.needs_dem
def test_precompute_acierta_la_cache_de_run_analysis(repo_root, tmp_path):
    """M4: tras ``precompute`` (DEM real Site23, observador por defecto, 2 m), ``run_analysis`` del observador por defecto
    encuentra su horizonte YA en caché (misma clave: mismo DEM y mismo campo lejano LOLA). Antes las claves diferían."""
    import copy
    from lsi import pipeline as P
    from lsi.contracts import AnalysisRequest
    from lsi.data.catalog import default_observer
    m = _load(repo_root)
    ctx = P.build_context(repo_root)
    if "Site23" not in ctx.dem_refs:
        pytest.skip("falta el DEM Site23")
    ctx.cfg = copy.deepcopy(ctx.cfg)
    ctx.cfg["cache"]["dir"] = str(tmp_path)               # caché aislada (ruta absoluta: Path(root) / abs = abs)
    rows = m.precompute(root=repo_root, sites=("Site23",), heights=(2.0,), cache_dir=tmp_path, log=lambda s: None)
    assert len(rows) == 1 and rows[0]["n_limited"] == 0   # con campo lejano ningún azimut queda limitado en Site23
    before = {f.stem for f in (tmp_path / "horizons").glob("*.npz")}
    assert rows[0]["cache_key"] in before
    lat, lon = default_observer(ctx.cfg, "Site23")
    r = P.run_analysis(ctx, AnalysisRequest(lat, lon, "2026-12-01T00:00:00", "2026-12-04T00:00:00", observer_height_m=2.0,
                                            score_profile_id="custom"))
    assert r.horizon.cache_key == rows[0]["cache_key"], "el horizonte nominal del pipeline NO acertó la caché del precompute"
