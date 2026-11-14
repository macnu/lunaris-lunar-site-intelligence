"""Descarga el gazetteer lunar oficial (USGS Planetary Names, puntos centrales) y escribe data/processed/gazetteer.{csv,parquet}.

Extrae el zip en un directorio NUEVO bajo data/raw/gazetteer/ (solo datos, nada se ejecuta). Falla si el formato cambia.
"""
import sys, tempfile, zipfile, pathlib, requests
import pandas as pd, shapefile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import data_manifest  # SHA-256 esperado del zip (config/data_manifest.json)

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lsi.data.gazetteer import normalize_text, region_of  # noqa: E402

URL = "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.zip"
REQUIRED = {"name", "clean_name", "approvaldt", "origin", "diameter", "center_lon", "center_lat", "type", "approval",
            "quad_code", "link"}


def convert(shp: pathlib.Path) -> pd.DataFrame:
    r = shapefile.Reader(str(shp), encoding="utf-8")
    cols = [f[0] for f in r.fields[1:]]
    missing = REQUIRED - set(cols)
    if missing:
        raise SystemExit(f"Formato del gazetteer distinto al esperado; faltan columnas {sorted(missing)}. Hay: {cols}")
    s = pd.DataFrame([x.as_dict() for x in r.iterRecords()])
    fid = s["link"].str.extract(r"/Feature/(\d+)\s*$")[0]
    if fid.isna().any() or fid.duplicated().any():
        raise SystemExit("IDs de rasgo no extraíbles/únicos desde la columna 'link'.")
    lon, lat = s["center_lon"].astype(float), s["center_lat"].astype(float)
    if not (lat.between(-90, 90).all() and lon.between(0, 360).all()):
        raise SystemExit("Latitud/longitud fuera de rango (¿cambió el convenio de longitud?).")
    diam = s["diameter"].astype(float).where(lambda x: x > 0)  # 0 = sin diámetro
    return pd.DataFrame({
        "feature_id": fid.astype(int),
        "name": s["clean_name"].str.strip(),
        "name_ascii": s["clean_name"].map(normalize_text),
        # "Crater, craters" -> "Crater"; "Satellite Feature" se conserva
        "feature_type": s["type"].str.split(",").str[0].str.strip(),
        "lat_deg": lat, "lon_deg_e": lon,  # el origen ya es ESTE-positivo 0..360 (verificado: Shackleton 129.78)
        "diameter_km": diam,
        "origin": s["origin"].fillna("").str.strip(),
        "approval_year": pd.to_numeric(s["approvaldt"].str[:4], errors="coerce").astype("Int64"),
        "approval_status": s["approval"].str.strip(),
        "region": lat.map(region_of),
        "has_dem": False, "dem_key": "",  # lo rellena annotate_dem_coverage (T12)
        "quad": s["quad_code"].fillna("").str.strip(),
    }).sort_values("feature_id").reset_index(drop=True)


def main():
    raw = ROOT / "data" / "raw" / "gazetteer"
    raw.mkdir(parents=True, exist_ok=True)
    dest = pathlib.Path(tempfile.mkdtemp(prefix="dl_", dir=raw))
    zp = dest / "gazetteer.zip"
    with requests.get(URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(zp, "wb") as f:
            for c in resp.iter_content(1 << 20): f.write(c)
    data_manifest.check(zp, data_manifest.GAZETTEER_KEY)   # USGS reedita nombres: si cambia, el mensaje dice cómo regenerar el manifiesto
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():  # solo ficheros planos de datos, sin rutas
            if n != pathlib.PurePosixPath(n).name or n.startswith("."):
                raise SystemExit(f"Entrada sospechosa en el zip: {n}")
        z.extractall(dest)
    shps = list(dest.glob("*.shp"))
    if len(shps) != 1:
        raise SystemExit(f"Se esperaba 1 .shp y hay {len(shps)}")
    df = convert(shps[0])
    out = ROOT / "data" / "processed"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "gazetteer.csv", index=False, encoding="utf-8")
    df.to_parquet(out / "gazetteer.parquet", index=False)
    print(f"{len(df)} rasgos -> {out}")
    print(df["feature_type"].value_counts().to_string())


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description='Descarga el gazetteer USGS de nomenclatura lunar y genera data/processed/gazetteer.csv.').parse_args()  # --help no ejecuta nada
    main()
