"""Imagen LROC NAC para texturas 3D (recortes por sitio) y coordenadas de las regiones Artemis III.

Dos tareas, ambas SIN --yes solo imprimen el plan (no tocan la red):
  --sites Site04 [Site11 Site23] --yes   recorta, del mosaico NAC polar sur promedio (1 m/px, LROC/ASU, PDS), una ventana
                                         de ±--half-size-m alrededor del centro de la huella del DEM LOLA de cada sitio y
                                         la guarda en data/raw/imagery/<Site>_nac_avg_1m.tif. Lee por HTTP Range SOLO las
                                         teselas necesarias, con pausa entre peticiones y User-Agent genérico. Se detiene
                                         ante un 429 (el servidor limita: Retry-After 3600 s). Aborta si superaría --max-mb.
  --regions --yes                        lee por HTTP Range el GLDMASK_005.tif (≈0,5 MB) de cada zip SDEM de Zenodo
                                         (doi 10.5281/zenodo.17954508) y reescribe config/artemis_regions.json.
Nada del zip ni de la red se ejecuta; solo se escriben ficheros de datos.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys
import time
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

OUT = ROOT / "data" / "raw" / "imagery"
UA = "lsi-fetch-imagery/1.0 (proyecto academico LSI; descarga selectiva)"
BASE = "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_SOUTH_CM_AVG/"
# bandas del mosaico (RDR NAC_POLE_SOUTH_CM_AVG): (lat. mín., lat. máx., lat. central·10, nº de teselas en longitud)
BANDS = ((-90.0, -88.5, 892, 4), (-88.5, -87.0, 878, 8), (-87.0, -85.5, 863, 12), (-85.5, -84.0, 848, 16))
PAUSE_S = 1.5        # entre peticiones
STRIP_ROWS = 512     # filas por lectura (≈ 2 teselas); una lectura = 1-3 rangos HTTP
DEFAULT_SITES = ("Site04", "Site11", "Site23")

# nombre NASA (lista de 13, ago-2022) -> (id, zip de Zenodo, en lista de 9 de oct-2024)
REGIONS13 = {
    "Amundsen Rim": ("amundsen_rim", "A3CLR22_0_Amundsen_Rim", False),
    "Nobile Rim 2": ("nobile_rim_2", "A3CLR22_1_Nobile_Rim_2", True),
    "Haworth": ("haworth", "A3CLR22_2_Haworth", True),
    "Faustini Rim A": ("faustini_rim_a", "A3CLR22_3_Faustini_Rim_A", False),
    "de Gerlache Rim 2": ("de_gerlache_rim_2", "A3CLR22_4_deGerlache_Rim_2", True),
    "Connecting Ridge Extension": ("connecting_ridge_extension", "A3CLR22_5_Connecting_Ridge_Extension", False),
    "Connecting Ridge": ("connecting_ridge", "A3CLR22_6_Connecting_Ridge", False),
    "Nobile Rim 1": ("nobile_rim_1", "A3CLR22_7_Nobile_Rim_1", True),
    "Peak Near Shackleton": ("peak_near_shackleton", "A3CLR22_8_Peak_Near_Shackleton", False),
    "de Gerlache Rim 1": ("de_gerlache_rim_1", "A3CLR22_9_deGerlache_Rim", False),   # el zip lo llama «deGerlache_Rim»
    "Leibnitz Beta Plateau": ("leibnitz_beta_plateau", "A3CLR22_10_Leibnitz_Beta_Plateau", False),
    "Malapert Massif": ("malapert_massif", "A3CLR22_11_Malapert_Massif", True),
    "de Gerlache-Kocher Massif": ("de_gerlache_kocher_massif", "A3CLR22_12_deGerlache_Kocher_Massif", False),
}
# regiones SOLO de la lista de 2024 (sin zip SDEM): NASA no da coordenadas; rasgo del gazetteer como PISTA, no como región
ONLY_2024 = {"Peak Near Cabeus B": ("peak_near_cabeus_b", "Cabeus B"), "Mons Mouton": ("mons_mouton", "Mons Mouton"),
             "Mons Mouton Plateau": ("mons_mouton_plateau", "Mons Mouton"), "Slater Plain": ("slater_plain", "Slater")}


# ---------------------------------------------------------------- regiones (Zenodo)
def build_regions() -> int:
    import numpy as np
    import requests
    import rasterio
    import fetch_sdem as fs
    from lsi.astronomy.coordinates import stereo_inverse
    from lsi.data.loader import discover_dems

    sess, rows, total = requests.Session(), [], 0
    refs = discover_dems(ROOT / "data" / "raw")
    try:
        import pandas as pd
        gz = pd.read_csv(ROOT / "data" / "processed" / "gazetteer.csv")
        near = gz[gz["feature_type"].isin(["Crater", "Mons"]) & (gz["lat_deg"] < -80)]
    except Exception:
        gz = None
    tmp = OUT / "_mask"
    tmp.mkdir(parents=True, exist_ok=True)
    for name, (rid, zname, in2024) in REGIONS13.items():
        hf = fs.HttpFile(f"{fs.BASE}/{zname}.zip/content", sess)
        with zipfile.ZipFile(hf) as z:
            zi = next(i for i in z.infolist() if i.filename.endswith("GLDMASK_005.tif"))
        dest = tmp / pathlib.Path(zi.filename).name
        fs.extract(hf, zi, dest)
        with rasterio.open(dest) as r:
            b = r.bounds
            px = float(r.transform.a)
        total += hf.bytes_read
        cx, cy = (b.left + b.right) / 2, (b.bottom + b.top) / 2
        lat, lon = (float(v) for v in stereo_inverse(cx, cy))
        pt = {}
        if gz is not None:     # rasgo con nombre más cercano (gran círculo, R = 1737,4 km)
            la, lo = np.radians(near["lat_deg"].values), np.radians(near["lon_deg_e"].values)
            c = np.sin(la) * math.sin(math.radians(lat)) + np.cos(la) * math.cos(math.radians(lat)) * np.cos(lo - math.radians(lon))
            d = np.arccos(np.clip(c, -1, 1)) * 1737.4
            i = int(np.argmin(d))
            pt = dict(nombre=str(near.iloc[i]["name"]), feature_id=int(near.iloc[i]["feature_id"]),
                      tipo=str(near.iloc[i]["feature_type"]), distancia_km=round(float(d[i]), 1))
        lola = next((k for k, ref in refs.items() if _iou(ref.bounds_xy_m, (b.left, b.bottom, b.right, b.top)) > 0.9), None)
        rows.append(dict(
            id=rid, nombre=name, listas=["2022"] + (["2024"] if in2024 else []),
            centro_lat_deg=round(lat, 4), centro_lon_deg_e=round(lon, 4), centro_xy_m=[round(cx, 1), round(cy, 1)],
            caja_xy_m=[round(v, 1) for v in (b.left, b.bottom, b.right, b.top)],
            caja_lado_km=[round((b.right - b.left) / 1000, 2), round((b.top - b.bottom) / 1000, 2)],
            tamano_oficial_nasa_km=15, sdem_zip=zname + ".zip", sdem_mascara=zi.filename, sdem_px_mascara_m=px,
            fuente="Centro y caja = huella del GLDMASK_005.tif del SDEM (Bertone et al., Zenodo 10.5281/zenodo.17954508, "
                   "CC-BY-4.0), convertida con stereo_inverse (R = 1737,4 km). NASA no publica coordenadas de las regiones.",
            confianza="derivada de la huella del SDEM; el centro oficial de la región no se publica (±~5 km de incertidumbre "
                      "respecto al centro nominal de 15 km, a verificar)",
            rasgo_cercano=pt, dem_lola_5m_sitio=lola))
        print(f"{name:28s} {lat:9.4f} {lon:9.4f}  caja {rows[-1]['caja_lado_km']}  lola={lola}  {pt.get('nombre')}")
    for name, (rid, feat) in ONLY_2024.items():
        pista = {}
        if gz is not None:
            e = gz[gz["name"] == feat].iloc[0]
            pista = dict(nombre=feat, feature_id=int(e["feature_id"]), tipo=str(e["feature_type"]),
                         lat_deg=float(e["lat_deg"]), lon_deg_e=float(e["lon_deg_e"]))
        rows.append(dict(id=rid, nombre=name, listas=["2024"], centro_lat_deg=None, centro_lon_deg_e=None, centro_xy_m=None,
                         caja_xy_m=None, tamano_oficial_nasa_km=15, sdem_zip=None,
                         fuente="Lista de nueve regiones de NASA (27-oct-2024, RELEASE24-136); sin coordenadas ni SDEM.",
                         confianza="sin coordenadas verificadas", pista_gazetteer=pista, dem_lola_5m_sitio=None))
    doc = dict(
        _nota="Regiones candidatas Artemis III. Lista de 13 (NASA, release 22-089, 19-ago-2022) + las 4 que SOLO figuran en la "
              "de nueve (RELEASE24-136, oct-2024). lon este-positiva 0..360, lat planetocéntrica, MOON_ME. caja = huella del "
              "SDEM (mayor que los 15 km oficiales). Regenerar: python scripts/fetch_imagery.py --regions --yes",
        fuentes=["https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/",
                 "https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/",
                 "https://zenodo.org/records/17954508"],
        generado=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), bytes_leidos=total, regions=rows)
    path = ROOT / "config" / "artemis_regions.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    doc = merge_regions_doc(doc, old)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(doc['regions'])} regiones escritas; {total} bytes leídos de Zenodo")
    return 0


def merge_regions_doc(new: dict, old: dict) -> dict:
    """Fusiona el JSON regenerado con el existente SIN perder lo añadido a mano.

    - Región sin coordenadas en lo generado pero con coordenadas en lo existente (las 4 solo de 2024, rellenadas desde la
      figura oficial de NASA): se conserva la entrada existente entera, con su fuente y su confianza.
    - Región con coordenadas generadas: lo generado manda en las claves que produce el script y se conservan las claves
      extra del fichero existente (p. ej. la medida sobre la figura de NASA).
    - Regiones solo presentes en lo existente se conservan; la lista de fuentes se une; la nota existente se respeta.
    """
    old_rows = {r["id"]: r for r in old.get("regions", []) if isinstance(r, dict) and "id" in r}
    out, seen = [], set()
    for r in new.get("regions", []):
        o = old_rows.get(r["id"], {})
        seen.add(r["id"])
        if r.get("centro_lat_deg") is None and o.get("centro_lat_deg") is not None:
            out.append(o)
        else:
            out.append({**o, **r})
    out += [o for i, o in old_rows.items() if i not in seen]
    fuentes = list(dict.fromkeys([*new.get("fuentes", []), *old.get("fuentes", [])]))
    merged = {**old, **new, "regions": out, "fuentes": fuentes}
    if old.get("_nota"):
        merged["_nota"] = old["_nota"]
    return merged


def _iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(w, 0) * max(h, 0)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


# ---------------------------------------------------------------- imagen NAC (PDS)
def tile_name(lat: float, lon_e: float) -> str | None:
    """Tesela del mosaico NAC_POLE_SOUTH_CM_AVG que contiene (lat, lon_E); None fuera de 84°S-90°S."""
    for lo, hi, c10, n in BANDS:
        if lo <= lat <= hi:
            k = int((lon_e % 360.0) // (360.0 / n))
            return f"NAC_POLE_SOUTH_CM_AVG_P{c10}S{int((k + 0.5) * 3600 / n):04d}"
    return None


def tiles_for(bounds, n: int = 9) -> list[str]:
    import numpy as np
    from lsi.astronomy.coordinates import stereo_inverse
    xs, ys = np.meshgrid(np.linspace(bounds[0], bounds[2], n), np.linspace(bounds[1], bounds[3], n))
    lat, lon = stereo_inverse(xs.ravel(), ys.ravel())
    return sorted({t for t in (tile_name(float(a), float(b)) for a, b in zip(lat, lon)) if t})


def fetch_sites(sites, half: float, max_mb: float) -> int:
    import numpy as np
    import requests
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.windows import Window
    from lsi.contracts import DEM_PROJ4
    from lsi.data.loader import _check_crs, discover_dems

    refs = discover_dems(ROOT / "data" / "raw")
    OUT.mkdir(parents=True, exist_ok=True)
    mpath = OUT / "MANIFEST.json"
    mf = json.loads(mpath.read_text("utf-8")) if mpath.exists() else {}
    mf.setdefault("sites", {})
    sess, est_total, n_req = requests.Session(), 0, 0
    for site in sites:
        if site not in refs:
            print(f"{site}: sin DEM LOLA en data/raw (no se sabe dónde centrar); omitido")
            continue
        b = refs[site].bounds_xy_m
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        win = (cx - half, cy - half, cx + half, cy + half)
        names = tiles_for(win)
        # coste estimado: teselas de 256x256 sin comprimir que cubre la ventana (cota superior)
        est = int(math.ceil((2 * half) / 256 + 1) ** 2 * 65536)
        if (est_total + est) / 1e6 > max_mb:
            print(f"{site}: superaría --max-mb ({max_mb}); omitido")
            continue
        grid, got, used = None, None, []
        for nm in names:
            url = BASE + nm + ".PYR.TIF"
            time.sleep(PAUSE_S)
            h = sess.head(url, allow_redirects=True, headers={"User-Agent": UA}, timeout=60)
            n_req += 1
            if h.status_code == 429:
                print("429 del servidor (Retry-After", h.headers.get("Retry-After"), "s): me detengo, reintentar más tarde")
                return 2
            if h.status_code == 404:
                url = BASE + nm + ".TIF"
                h = sess.head(url, allow_redirects=True, headers={"User-Agent": UA}, timeout=60)
            h.raise_for_status()
            final = h.url                     # destino ya resuelto: evita un 302 por cada rango que pida GDAL
            env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_USERAGENT=UA, GDAL_HTTP_MAX_RETRY="0",
                               CPL_VSIL_CURL_CHUNK_SIZE="2097152", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF",
                               CPL_VSIL_CURL_CACHE_SIZE="64000000")
            with env, rasterio.open("/vsicurl/" + final) as s:
                _check_crs(s.crs, url)
                t, px = s.transform, float(s.transform.a)
                if grid is None:
                    c0 = math.floor((win[0] - t.c) / px)
                    r0 = math.floor((t.f - win[3]) / px)
                    w_px = math.ceil((win[2] - win[0]) / px) + 1
                    grid = dict(t=t, px=px, c0=c0, r0=r0, w=w_px)
                    got = np.zeros((w_px, w_px), np.uint8)
                elif abs(px - grid["px"]) > 1e-9 or abs(((t.c - grid["t"].c) / px) % 1) > 1e-3 and \
                        abs(((t.c - grid["t"].c) / px) % 1 - 1) > 1e-3:
                    print(f"{nm}: retícula distinta de la de la primera tesela; no se combina sin remuestrear"); return 3
                # ventana de la rejilla común, en índices de ESTA tesela
                dc = round((grid["t"].c - t.c) / px)
                dr = round((t.f - grid["t"].f) / px)
                c_lo, r_lo = grid["c0"] + dc, grid["r0"] + dr
                for r_start in range(0, grid["w"], STRIP_ROWS):
                    hgt = min(STRIP_ROWS, grid["w"] - r_start)
                    wnd = Window(c_lo, r_lo + r_start, grid["w"], hgt)
                    time.sleep(PAUSE_S)
                    a = s.read(1, window=wnd, boundless=True, fill_value=0)
                    n_req += 1
                    blk = got[r_start:r_start + hgt]
                    blk[(blk == 0) & (a > 0)] = a[(blk == 0) & (a > 0)]
                used.append(nm)
        x0 = grid["t"].c + grid["c0"] * grid["px"]
        y0 = grid["t"].f - grid["r0"] * grid["px"]
        dest = OUT / f"{site}_nac_avg_1m.tif"
        prof = dict(driver="GTiff", dtype="uint8", count=1, width=grid["w"], height=grid["w"], nodata=0, tiled=True,
                    blockxsize=256, blockysize=256, compress="deflate", crs=CRS.from_string(DEM_PROJ4),
                    transform=from_origin(x0, y0, grid["px"], grid["px"]))
        with rasterio.open(dest.with_suffix(".part"), "w", **prof) as d:
            d.write(got, 1)
        dest.with_suffix(".part").replace(dest)
        est_total += est
        cov = float((got > 0).mean())
        mf["sites"][site] = dict(file=dest.name, tiles=used, source=BASE, bounds_xy_m=[x0, y0 - grid["w"] * grid["px"], x0 + grid["w"] * grid["px"], y0],
                                 px_m=grid["px"], center_xy_m=[cx, cy], half_size_m=half, coverage_fraction=round(cov, 4),
                                 sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), bytes=dest.stat().st_size,
                                 est_bytes_downloaded_upper_bound=est)
        mf["fetched"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        mpath.write_text(json.dumps(mf, indent=1), encoding="utf-8")
        print(f"{site}: {used} cobertura con dato {100 * cov:.1f} % -> {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    print(f"Peticiones: {n_req}; descarga estimada (cota) {est_total / 1e6:.0f} MB")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # --help con acentos y símbolos en consolas cp1252
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] + " Sin --yes no hace ninguna petición.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sites", nargs="+", metavar="SiteNN", help=f"sitios a recortar (p. ej. {' '.join(DEFAULT_SITES)})")
    ap.add_argument("--regions", action="store_true", help="reescribir config/artemis_regions.json desde Zenodo (≈ 8 MB)")
    ap.add_argument("--half-size-m", type=float, default=3000.0, help="semilado de la ventana (por defecto 3000 m ⇒ ≈ 36 MB sin comprimir)")
    ap.add_argument("--max-mb", type=float, default=300.0, help="tope de descarga estimada (por defecto 300 MB; no subir de 500 sin confirmar)")
    ap.add_argument("--yes", action="store_true", help="confirma las peticiones de red")
    a = ap.parse_args()
    if not (a.sites or a.regions):
        ap.print_help()
        return 0
    if not a.yes:
        print("Nada descargado.", "Sitios:", ", ".join(a.sites or []) or "-", "| regiones:", a.regions,
              f"| origen imagen: {BASE} | repetir con --yes")
        return 0
    rc = build_regions() if a.regions else 0
    return rc or (fetch_sites(a.sites, a.half_size_m, a.max_mb) if a.sites else 0)


if __name__ == "__main__":
    sys.exit(main())
