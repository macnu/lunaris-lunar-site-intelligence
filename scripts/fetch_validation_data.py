"""Descarga el DEM LOLA 5 m de Site01 (Connecting Ridge, PGDA producto 78) para ``tests/test_luna_cases.py``.

Solo las capas que necesita el cargador (surf, slp, ldec, toterr; ~41 MB cada una) en ``data/validation_raw/site01/``.
Escribe ``data/validation_raw/manifest.json`` con tamaño y SHA-256 de lo descargado.

``--help`` NO descarga nada. Sin ``--yes`` solo se hace un HEAD por capa (tamaño esperado) y se sale. Con ``--yes`` se descarga,
se comprueba el tamaño (``Content-Length`` del HEAD) y que no es HTML (PGDA devuelve 200 con una página de error en rutas
erróneas): un TIFF empieza por ``II*\\0`` o ``MM\\0*``. Reanudable: una capa ya presente con el tamaño correcto se omite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_{layer}.tif"
LAYERS = ("surf", "slp", "ldec", "toterr")
OUT = ROOT / "data" / "validation_raw"
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")   # TIFF clásico y BigTIFF


def head_size(url: str) -> int:
    r = requests.head(url, allow_redirects=True, timeout=60)
    r.raise_for_status()
    if "html" in r.headers.get("content-type", "").lower():
        raise RuntimeError(f"HTML en lugar de datos: {url}")
    return int(r.headers["Content-Length"])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def check_tiff(path: Path, expected: int) -> None:
    if path.stat().st_size != expected:
        raise RuntimeError(f"{path.name}: {path.stat().st_size} B descargados, esperados {expected} B")
    with open(path, "rb") as f:
        if f.read(4) not in TIFF_MAGIC:
            raise RuntimeError(f"{path.name}: no es un TIFF (¿página HTML de error?)")


def download(url: str, dest: Path, expected: int) -> None:
    tmp = dest.with_suffix(".tif.part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        if "html" in r.headers.get("content-type", "").lower():
            raise RuntimeError(f"HTML en lugar de datos: {url}")
        with open(tmp, "wb") as f:
            for c in r.iter_content(1 << 20):
                f.write(c)
    try:
        check_tiff(tmp, expected)
    except RuntimeError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="descargar de verdad (sin él solo se consultan los tamaños)")
    a = ap.parse_args(argv)
    sizes = {l: head_size(BASE.format(layer=l)) for l in LAYERS}
    total = sum(sizes.values())
    print(f"Tamaños (HEAD): {sizes}; total {total / 1e6:.1f} MB")
    if not a.yes:
        print("Nada descargado. Repite con --yes para descargar.")
        return 0
    d = OUT / "site01"
    d.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for l, n in sizes.items():
        dest = d / f"Site01_final_adj_5mpp_{l}.tif"
        if dest.exists() and dest.stat().st_size == n:
            check_tiff(dest, n)
            print("ok  ", dest.name)
        else:
            download(BASE.format(layer=l), dest, n)
            print("baja", dest.name, n)
        manifest[f"site01/{dest.name}"] = dict(url=BASE.format(layer=l), bytes=n, sha256=sha256(dest))
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"Manifiesto: {OUT / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
