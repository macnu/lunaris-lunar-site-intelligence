"""Manifiesto de SHA-256 de los datos descargados (``config/data_manifest.json``) y su verificación.

Solo contiene lo que ya estaba descargado y verificado en este repositorio (DEM LOLA 5 m de Site04/11/23, campo lejano LOLA 80 m,
kernels SPICE y el zip del gazetteer USGS). Los scripts de descarga llaman a ``check`` tras cada descarga; también sirve en solitario:

    python scripts/data_manifest.py            # verifica todo lo presente (sale con 1 si algo no coincide)
    python scripts/data_manifest.py --regenerate   # REESCRIBE el manifiesto con los ficheros actuales (decisión consciente)

Un desajuste significa una de dos cosas: fichero corrupto (vuelve a descargarlo) o el ORIGEN cambió (PGDA/NAIF/USGS reeditaron el
producto o su tamaño): revisa el cambio y, solo si es lo esperado, regenera el manifiesto con ``--regenerate`` y commitea el diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT =Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "data_manifest.json"
GLOBS = ("data/raw/shackleton/*_5mpp_*.tif", "data/raw/de_gerlache/*_5mpp_*.tif", "data/raw/malapert/*_5mpp_*.tif",
         "data/raw/lola80s/LDEM_80S_80MPP_ADJ.TIF", "kernels/*.tls", "kernels/*.tpc", "kernels/*.tf", "kernels/*.bpc", "kernels/*.bsp")
GAZETTEER_KEY = "gazetteer/MOON_nomenclature_center_pts.zip"   # el zip vive en un directorio temporal dl_*/: se identifica por clave fija


class DataMismatchError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _key(path: Path) -> str:
    # abspath normaliza sin resolver enlaces simbólicos ni uniones: en un worktree, data/ puede ser un enlace
    # al directorio de datos de otra copia y la clave debe seguir siendo relativa a la raíz del repo.
    p = Path(os.path.abspath(path))
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def load() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def check(path: Path, key: str | None = None) -> bool:
    """True si ``path`` coincide con el manifiesto; False si no está en él (nada que comparar); lanza ``DataMismatchError`` si difiere."""
    key = key or _key(path)
    exp = load().get("files", {}).get(key)
    if exp is None:
        return False
    size, digest = Path(path).stat().st_size, sha256(path)
    if size != exp["bytes"] or digest != exp["sha256"]:
        raise DataMismatchError(
            f"{key}: no coincide con config/data_manifest.json (tamaño {size} B, esperado {exp['bytes']} B; SHA-256 {digest[:16]}…, "
            f"esperado {exp['sha256'][:16]}…). O bien la descarga está corrupta (bórrala y repite), o el origen cambió de versión: "
            f"si es esperado, regenera conscientemente con `python scripts/data_manifest.py --regenerate` y revisa el diff del manifiesto.")
    return True


def tracked() -> dict[str, Path]:
    out = {_key(p): p for g in GLOBS for p in sorted(ROOT.glob(g))}
    zips = sorted(ROOT.glob("data/raw/gazetteer/*/gazetteer.zip"))
    if zips:
        out[GAZETTEER_KEY] = zips[-1]
    return out


def regenerate() -> dict:
    files = {k: {"bytes": p.stat().st_size, "sha256": sha256(p)} for k, p in tracked().items()}
    doc = {"_nota": "SHA-256 de lo descargado y verificado el 14/11/2026. Regenerar solo de forma consciente: scripts/data_manifest.py --regenerate",
           "files": files}
    MANIFEST.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regenerate", action="store_true", help="reescribe el manifiesto con los ficheros actuales")
    a = ap.parse_args(argv)
    if a.regenerate:
        print(f"{len(regenerate()['files'])} ficheros -> {MANIFEST}")
        return 0
    bad = 0
    for k, p in tracked().items():
        try:
            print("ok  " if check(p, k) else "sin hash", k)
        except DataMismatchError as e:
            bad += 1
            print("FALLA", e)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
