"""RNF-03: misma entrada → mismos bytes. Export JSON/CSV idéntico entre ejecuciones con ``generated_utc`` fijo, con SPICE
reabierto (``build_context`` hace kclear + furnsh) y con la caché de horizontes en frío (directorio temporal vacío)."""
import copy
import dataclasses
from pathlib import Path

import pytest

from lsi import pipeline as P
from lsi.analysis import export as ex
from lsi.contracts import AnalysisRequest, MountingSpec, MountingType

pytestmark = pytest.mark.needs_spice
ROOT = Path(__file__).resolve().parents[1]
GEN = "2026-01-01T00:00:00Z"
VAT = MountingSpec(MountingType.VERTICAL_AZ_TRACKING)
START, END = "2026-12-01T00:00:00", "2026-12-31T00:00:00"
CASES = {   # observador por defecto de Site23 (DEM) y Apolo 11 (esfera lisa)
    "dem_site23": dict(lat_deg=-85.994785, lon_deg_e=359.764216),
    "sphere_apollo11": dict(lat_deg=0.6741, lon_deg_e=23.473, site_id="apollo11"),
}


def blobs(ctx, req, tmp):
    r = P.run_analysis(ctx, req)
    j = ex.write_json(r, tmp / "r.json", GEN).read_bytes()
    paths = ex.write_csv_bundle(r, tmp / "csv", GEN)
    return j, {k: p.read_bytes() for k, p in paths.items()}


@pytest.mark.parametrize("case", list(CASES))
def test_two_runs_identical_bytes(case, tmp_path):
    req = AnalysisRequest(**CASES[case], start_utc=START, end_utc=END, panel_id="tj-gaas-lander-body", mounting=VAT,
                          with_uncertainty=True, now_utc="2026-12-10T00:00:00")
    ctx1 = P.build_context(ROOT)
    a = blobs(ctx1, req, tmp_path / "a")
    ctx2 = P.build_context(ROOT)                               # SPICE reabierto
    assert ctx2.kernels.kernel_hash == ctx1.kernels.kernel_hash
    b = blobs(ctx2, req, tmp_path / "b")
    cfg = copy.deepcopy(ctx2.cfg)
    cfg["cache"]["dir"] = str(tmp_path / "cold_cache")         # horizontes recalculados desde cero (ruta absoluta gana a root)
    c = blobs(dataclasses.replace(ctx2, cfg=cfg), req, tmp_path / "c")
    if case.startswith("dem"):
        assert any((tmp_path / "cold_cache").rglob("*.npz")), "la caché en frío no se usó: el test no prueba lo que dice"
    assert a[0] == b[0] == c[0], "JSON exportado distinto entre ejecuciones"
    for k in a[1]:
        assert a[1][k] == b[1][k] == c[1][k], f"{k} distinto entre ejecuciones"
    assert len(a[0]) > 10_000
