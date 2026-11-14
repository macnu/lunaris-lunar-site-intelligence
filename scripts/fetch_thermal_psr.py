"""Descarga reproducible de datos térmicos (LRO Diviner), PSR (LROC/LOLA) e iluminación publicada (LOLA/PGDA).

Reanudable (Range sobre .part), rechaza HTML con código 200, verifica tamaño esperado y registra SHA-256 en
``data/raw/<dir>/SHA256SUMS.json`` (primera descarga: se registra; después: se compara). No baja nada que supere --max-mb.
"""
import argparse, hashlib, json, pathlib, sys, zipfile
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIV = "http://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar/additional_maps"
PGDA = "https://pgda.gsfc.nasa.gov/data/MoonIllumination"
LROC = "https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_PSR_SOUTH"
# (carpeta, nombre, URL, bytes esperados medidos el 14/11/2026)
FILES = [("diviner", f"polar_south_80_{s}_{k}-float.tif", f"{DIV}/polar_south_80_{s}_{k}-float.tif", 25686193)
         for s in ("summer", "winter") for k in ("avg", "max", "min")]
FILES += [("illum_ref", "AVGVISIB_85S_060M_201608.TIF", f"{PGDA}/AVGVISIB_85S_060M_201608.TIF", 33994464),
          ("illum_ref", "AVGVISIB_75S_120M_201608.TIF", f"{PGDA}/AVGVISIB_75S_120M_201608.TIF", 83052039),
          ("psr", "NAC_POLE_PSR_SOUTH.ZIP", f"{LROC}/NAC_POLE_PSR_SOUTH.ZIP", 1121858),
          ("psr", "NAC_POLE_PSR_SOUTH_README.TXT", f"{LROC}/NAC_POLE_PSR_SOUTH_README.TXT", 6283)]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def register(dest):
    side = dest.parent / "SHA256SUMS.json"
    sums = json.loads(side.read_text()) if side.exists() else {}
    h = sha256(dest)
    if dest.name in sums and sums[dest.name] != h:
        raise RuntimeError(f"SHA-256 distinto del registrado para {dest.name}: {h} != {sums[dest.name]}")
    sums[dest.name] = h
    side.write_text(json.dumps(sums, indent=1))
    return h


def get(url, dest, expected, max_bytes):
    if expected > max_bytes:
        raise RuntimeError(f"{dest.name}: {expected/1e6:.0f} MB supera --max-mb; no se descarga.")
    if dest.exists() and dest.stat().st_size == expected:
        print("ok  ", dest.name, register(dest)[:12]); return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    hdr = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, timeout=60, headers=hdr) as r:
        r.raise_for_status()
        if "text/html" in r.headers.get("content-type", ""):   # PGDA devuelve 200 con HTML en rutas erróneas
            raise RuntimeError(f"HTML en lugar de datos: {url}")
        if have and r.status_code != 206:
            have = 0                                            # el servidor ignoró Range: se empieza de cero
        with open(tmp, "ab" if have else "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)
    if tmp.stat().st_size != expected:
        raise RuntimeError(f"{dest.name}: {tmp.stat().st_size} bytes, se esperaban {expected}.")
    tmp.replace(dest)
    print("baja", dest.name, dest.stat().st_size, register(dest)[:12])


def unzip_psr(zpath):
    out = zpath.with_suffix("")
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        if any("/" in n or "\\" in n or ".." in n for n in names):
            raise RuntimeError("entradas con ruta en el zip; no se extrae")
        z.extractall(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] + " Reanudable.")
    ap.add_argument("--only", choices=["diviner", "psr", "illum_ref"], help="solo una familia")
    ap.add_argument("--max-mb", type=float, default=500, help="rechaza ficheros mayores (por defecto 500 MB)")
    a = ap.parse_args()                                         # --help sale aquí: no descarga nada
    for d, name, url, size in FILES:
        if a.only in (None, d):
            get(url, ROOT / "data/raw" / d / name, size, a.max_mb * 1e6)
    if a.only in (None, "psr"):
        unzip_psr(ROOT / "data/raw/psr/NAC_POLE_PSR_SOUTH.ZIP")
