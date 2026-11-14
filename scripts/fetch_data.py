"""Descarga reproducible de DEM LOLA (PGDA) y kernels SPICE (NAIF). Reanudable: omite lo ya descargado."""
import sys, pathlib, requests
import data_manifest  # SHA-256 esperados de lo ya verificado (config/data_manifest.json); falla con mensaje claro si no coincide

ROOT = pathlib.Path(__file__).resolve().parents[1]
PGDA = "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp"
NAIF = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels"
SITES = {"Site04": "shackleton", "Site11": "de_gerlache", "Site23": "malapert"}
LAYERS = ["surf", "slp", "ldec", "toterr"]  # slperr/clones: stretch
KERNELS = {
    "naif0012.tls": f"{NAIF}/lsk/naif0012.tls",
    "pck00011.tpc": f"{NAIF}/pck/pck00011.tpc",
    "moon_080317.tf": f"{NAIF}/fk/satellites/moon_080317.tf",
    "moon_assoc_me.tf": f"{NAIF}/fk/satellites/moon_assoc_me.tf",
    "moon_pa_de421_1900-2050.bpc": f"{NAIF}/pck/moon_pa_de421_1900-2050.bpc",
    "de421.bsp": f"{NAIF}/spk/planets/a_old_versions/de421.bsp",
}

def get(url, dest):
    if dest.exists() and dest.stat().st_size > 4096:
        data_manifest.check(dest); print("ok  ", dest.name); return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        if "text/html" in r.headers.get("content-type", ""):  # PGDA devuelve 200 con HTML en rutas erróneas
            raise RuntimeError(f"HTML en lugar de datos: {url}")
        with open(tmp, "wb") as f:
            for c in r.iter_content(1 << 20): f.write(c)
    tmp.replace(dest); data_manifest.check(dest); print("baja", dest.name, dest.stat().st_size)

# Campo lejano: LOLA polar 80°S–90°S a 80 m/px (PGDA producto 90). Cierra el horizonte más allá del recorte de 5 m.
FAR_DEM = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF"

if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description='Descarga los DEM LOLA 5 m (Site04/11/23), el campo lejano LOLA 80 m y los kernels SPICE. Reanudable.').parse_args()  # --help no ejecuta nada
    get(FAR_DEM, ROOT / "data/raw/lola80s" / "LDEM_80S_80MPP_ADJ.TIF")
    for name, url in KERNELS.items(): get(url, ROOT / "kernels" / name)
    for s, d in SITES.items():
        for l in LAYERS: get(f"{PGDA}/{s}/{s}_final_adj_5mpp_{l}.tif", ROOT / "data/raw" / d / f"{s}_final_adj_5mpp_{l}.tif")
