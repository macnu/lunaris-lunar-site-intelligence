"""Imagen NAC (recortes por sitio) y regiones Artemis III. Sin red; los de datos reales se saltan si faltan."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from lsi.astronomy.coordinates import stereo_forward
from lsi.contracts import DEM_PROJ4
from lsi.data import imagery

ROOT = Path(__file__).resolve().parents[1]
REGIONS = json.loads((ROOT / "config" / "artemis_regions.json").read_text(encoding="utf-8"))["regions"]


# ---- recorte sintético: valor = 1 + columna % 200, con un hueco de ceros (sin dato) --------------------------------
@pytest.fixture()
def clip(tmp_path):
    n, x0, y0 = 400, -200.0, 200.0                       # esquina sup. izq. (-200, 200) m, píxel de 1 m
    img = (1 + np.arange(n) % 200).astype(np.uint8)[None, :].repeat(n, 0)
    img[100:140, 100:140] = 0                            # hueco = sin dato NAC
    with rasterio.open(imagery.clip_path("Site99", tmp_path), "w", driver="GTiff", dtype="uint8", count=1, width=n,
                       height=n, nodata=0, crs=CRS.from_string(DEM_PROJ4), transform=from_origin(x0, y0, 1.0, 1.0)) as d:
        d.write(img, 1)
    return tmp_path, img, x0, y0


def test_window_native_grid_alignment_and_coverage(clip):
    d, img, x0, y0 = clip
    w = imagery.imagery_window("site99", 0.0, 0.0, 50.0, 100, imagery_dir=d)        # 100 px a 1 m = nativo
    assert w["image"].shape == w["coverage"].shape == (100, 100) and w["image"].dtype == np.uint8
    assert w["px_m"] == 1.0 and w["native_px_m"] == 1.0
    # centro del píxel [0,0] = (cx - half + px/2, cy + half - px/2) y coincide con el píxel del recorte que lo contiene
    assert (w["x0_m"], w["y0_m"]) == (-49.5, 49.5)
    col0 = int((w["x0_m"] - x0) // 1.0)
    row0 = int((y0 - w["y0_m"]) // 1.0)
    assert np.array_equal(w["image"], img[row0:row0 + 100, col0:col0 + 100])        # valor esperado independiente: el recorte
    assert w["coverage"].all()                                                       # (-50..50) no toca el hueco (cols 100-140 = x -100..-60)


def test_window_hole_is_not_covered_and_never_invented(clip):
    d, img, x0, y0 = clip
    w = imagery.imagery_window("Site99", -80.0, 80.0, 40.0, 80, imagery_dir=d)      # contiene el hueco x -100..-60, y 60..100
    assert not w["coverage"].all() and w["coverage"].any()
    assert (w["image"][~w["coverage"]] == 0).all()                                   # sin dato = 0, jamás relleno
    assert (w["image"][w["coverage"]] >= 1).all()
    assert any("sin imagen" in n for n in w["notes"])


def test_window_downsample_reports_effective_px_and_attribution(clip):
    d, *_ = clip
    w = imagery.imagery_window("Site99", 0.0, 0.0, 100.0, 20, imagery_dir=d)        # 200 m en 20 px -> 10 m/px
    assert w["image"].shape == (20, 20) and w["px_m"] == pytest.approx(10.0)
    assert w["native_px_m"] == 1.0 and "no es la luz de una fecha" in " ".join(w["notes"])
    assert "NASA" in w["attribution"] and "LROC" in w["attribution"] and w["source"] == imagery.SOURCE_ID
    assert w["source_url"].startswith("https://pds.lroc")


def test_window_upsampling_request_is_clamped_to_native_resolution(clip):
    d, *_ = clip
    w = imagery.imagery_window("Site99", 0.0, 0.0, 10.0, 1000, imagery_dir=d)       # piden 2 cm/px: la imagen es de 1 m
    assert w["image"].shape == (20, 20) and w["px_m"] == 1.0


def test_window_missing_or_outside_returns_none(clip, tmp_path):
    d, *_ = clip
    assert imagery.imagery_window("Site04", 0, 0, 50, 50, imagery_dir=d) is None     # sin recorte de ese sitio
    assert imagery.imagery_window("Site99", 5000.0, 5000.0, 50.0, 50, imagery_dir=d) is None   # fuera del recorte
    with pytest.raises(ValueError):
        imagery.imagery_window("Site99", 0, 0, 0, 50, imagery_dir=d)


def test_combine_with_sdem_prefers_sdem_and_fills_gaps(clip):
    d, *_ = clip
    ny = nx = 60
    ortho = np.full((ny, nx), 200, np.uint8)
    valid = np.zeros((ny, nx), bool)
    valid[:, :30] = True                                   # el SDEM solo tiene foto en la mitad izquierda
    pack = dict(ortho=np.where(valid, ortho, 0), texture_valid=valid, px_m=1.0, x0_m=-29.5, y0_m=29.5, attribution="SDEM")
    out = imagery.combine_with_sdem("Site99", pack, imagery_dir=d)
    assert (out["texture"][:, :30] == 200).all() and (out["texture_source"][:, :30] == 1).all()
    assert (out["texture_source"][:, 30:] == 2).all() and out["texture_valid"].all() and (out["texture"][:, 30:] >= 1).all()
    assert out["attribution"][0] == "SDEM" and "LROC" in out["attribution"][1]
    assert imagery.combine_with_sdem("Site99", None, imagery_dir=d) is None
    assert imagery.combine_with_sdem("Site04", pack, imagery_dir=d) is None


# ---- script: --help y el plan sin --yes no hacen peticiones --------------------------------------------------------
def test_script_help_and_dry_run_do_not_download(tmp_path):
    before = sorted((ROOT / "data" / "raw" / "imagery").glob("*")) if (ROOT / "data" / "raw" / "imagery").exists() else []
    env = {"PATH": "", "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "SYSTEMROOT": "C:\\Windows"}
    for args, frag in ((["--help"], "--yes"), (["--sites", "Site04"], "Nada descargado"), (["--regions"], "Nada descargado")):
        r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "fetch_imagery.py"), *args], capture_output=True,
                           text=True, encoding="utf-8", timeout=60, env={**env, "PYTHONIOENCODING": "utf-8"})
        assert r.returncode == 0 and frag in r.stdout, r.stderr
    assert before == (sorted((ROOT / "data" / "raw" / "imagery").glob("*")) if (ROOT / "data" / "raw" / "imagery").exists() else [])


def test_tile_naming_against_published_lroc_products():
    sys.path.insert(0, str(ROOT / "scripts"))
    import fetch_imagery as f
    # productos reales del RDR: P863S3150 cubre lat -87..-85.5, lon 300-330; P863S3450 y P892S0450 existen
    assert f.tile_name(-86.25, 315.0).endswith("P863S3150")
    assert f.tile_name(-85.99, 359.7).endswith("P863S3450")
    assert f.tile_name(-89.9, 10.0).endswith("P892S0450")
    assert f.tile_name(-83.0, 10.0) is None and f.tile_name(-84.0, 10.0).endswith("P848S0112")
    assert f.tile_name(-84.2, 56.0).endswith("P848S0562")


# ---- regiones Artemis III -------------------------------------------------------------------------------------------
def test_thirteen_regions_in_south_pole_with_coherent_box():
    r13 = [r for r in REGIONS if "2022" in r["listas"]]
    assert len(r13) == 13 and len({r["id"] for r in REGIONS}) == len(REGIONS) == 17
    for r in r13:
        assert -90 < r["centro_lat_deg"] < -80, r["nombre"]
        assert 0 <= r["centro_lon_deg_e"] < 360
        x0, y0, x1, y1 = r["caja_xy_m"]
        assert x1 > x0 and y1 > y0 and (x1 - x0) >= 15_000 - 100        # la huella SDEM contiene los 15 km oficiales
        cx, cy = r["centro_xy_m"]
        assert x0 < cx < x1 and y0 < cy < y1
        fx, fy = (float(v) for v in stereo_forward(r["centro_lat_deg"], r["centro_lon_deg_e"]))
        assert (fx, fy) == pytest.approx((cx, cy), abs=60.0)             # lat/lon redondeados a 1e-4° (≈ 3 m)


def test_regions_known_overlaps_with_lola_dems():
    by = {r["id"]: r for r in REGIONS}
    assert by["malapert_massif"]["dem_lola_5m_sitio"] == "Site23" and by["de_gerlache_rim_1"]["dem_lola_5m_sitio"] == "Site11"
    assert by["malapert_massif"]["centro_lat_deg"] == pytest.approx(-85.98, abs=0.05)      # Mons Malapert del gazetteer
    assert by["de_gerlache_rim_1"]["centro_lat_deg"] == pytest.approx(-88.683, abs=0.01)   # observador por defecto de Site11
    assert by["de_gerlache_rim_1"]["centro_lon_deg_e"] == pytest.approx(292.068, abs=0.01)
    only24 = [r for r in REGIONS if r["listas"] == ["2024"]]
    assert {r["id"] for r in only24} == {"peak_near_cabeus_b", "mons_mouton", "mons_mouton_plateau", "slater_plain"}
    # las 4 regiones solo de 2024 salen de la figura oficial de NASA (NTRS 20250011660), no se inventan
    assert all(r["fuente_coordenadas"] == "figura_nasa_2024" and "digitalizado" in r["confianza"] for r in only24)
    assert all(-90 < r["centro_lat_deg"] < -83 for r in only24)
    mm, lbp = by["mons_mouton"], by["leibnitz_beta_plateau"]                               # misma posición, otro nombre (a verificar)
    assert float(np.hypot(mm["centro_xy_m"][0] - lbp["centro_xy_m"][0], mm["centro_xy_m"][1] - lbp["centro_xy_m"][1])) < 2_500
    for k in ("haworth", "malapert_massif", "de_gerlache_rim_2", "nobile_rim_1", "nobile_rim_2"):  # figura 2024 vs huella SDEM
        assert by[k]["centro_figura_nasa_2024"]["diferencia_con_sdem_km"] < 2.5, k


def test_sites_json_matches_regions_and_catalog_loads():
    from lsi.data import catalog
    sites = {s.id: s for s in catalog.load_sites(ROOT / "config" / "sites.json")}
    for r in REGIONS:
        s = sites["artemis3_" + r["id"]]
        assert s.lat_deg == pytest.approx(r["centro_lat_deg"]) and (s.lon_deg_e % 360) == pytest.approx(r["centro_lon_deg_e"], abs=1e-3)
        assert s.confidence == "aprox" and ("SDEM" in s.source or "figura oficial de NASA" in s.source)


# ---- datos reales (se saltan si no se han descargado) -------------------------------------------------------------
@pytest.mark.needs_dem
def test_real_site04_window_if_downloaded():
    if "Site04" not in imagery.available_sites():
        pytest.skip("falta data/raw/imagery/Site04_nac_avg_1m.tif (python scripts/fetch_imagery.py --sites Site04 --yes)")
    from lsi.data.loader import discover_dems
    ref = discover_dems(ROOT / "data" / "raw")["Site04"]
    b = ref.bounds_xy_m
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    w = imagery.imagery_window("Site04", cx, cy, 1500.0, 300)
    assert w["image"].shape == (300, 300) and w["px_m"] == pytest.approx(10.0) and w["coverage"].any()
    assert "NASA" in w["attribution"] and (w["image"][~w["coverage"]] == 0).all()
    assert (w["x0_m"], w["y0_m"]) == pytest.approx((cx - 1500 + 5, cy + 1500 - 5))
