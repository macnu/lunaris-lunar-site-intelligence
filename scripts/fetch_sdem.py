"""Descarga SELECTIVA de los SDEM de 5 m con ortomosaico LROC NAC (NASA PGDA, Zenodo 10.5281/zenodo.17954508).

Cada zip pesa 1,3-2,2 GB: NO se descarga entero. Se lee el directorio central por HTTP Range y se extraen solo
README.txt y unas pocas capas por región (ortomosaico, elevación, máscara, sombreado y, si pesa poco, SDEM-LDEM).
Nada del zip se ejecuta; solo se escriben ficheros de datos tras comprobar tamaño, CRC y cabecera.
Reanudable: se omite lo ya extraído cuya longitud y SHA-256 coinciden con MANIFEST.json.
Uso: python scripts/fetch_sdem.py --help | --yes [--region Malapert_Massif ...]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import pathlib
import struct
import sys
import time
import zipfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "sdem"
RECORD = "17954508"
BASE = f"https://zenodo.org/api/records/{RECORD}/files"
DOI, VERSION, LICENSE = "10.5281/zenodo.17954508", "1.0.0", "CC-BY-4.0"
# región (carpeta local) -> zip de Zenodo. Site04 (Shackleton rim) NO está entre las 13 regiones.
REGIONS = {
    "Malapert_Massif": "A3CLR22_11_Malapert_Massif.zip",
    "deGerlache_Rim": "A3CLR22_9_deGerlache_Rim.zip",
    "Peak_Near_Shackleton": "A3CLR22_8_Peak_Near_Shackleton.zip",
}
WANT = ("GLDOMOS_005.tif", "GLDELEV_005.tif", "GLDMASK_005.tif", "GLDHILL_005_315_45.tif", "README.txt")
OPTIONAL = ("GLDDIFF_005.tif",)      # solo si pesa < 60 MB (comprimido y sin comprimir)
OPTIONAL_MAX = 60e6
UA = {"User-Agent": "lsi-fetch-sdem/1.0"}
MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


class HttpFile(io.RawIOBase):
    """Fichero de solo lectura sobre HTTP Range, con lectura adelantada y contador de bytes realmente recibidos."""
    CHUNK = 1 << 20

    def __init__(self, url: str, session):
        self.s, self.pos, self.bytes_read, self.requests = session, 0, 0, 0
        r = session.head(url, allow_redirects=True, timeout=40, headers=UA)
        r.raise_for_status()
        self.url, self.size = r.url, int(r.headers["Content-Length"])   # el HEAD de Zenodo no anuncia Accept-Ranges
        self._buf, self._buf0 = b"", 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, o, w=0):
        self.pos = o if w == 0 else (self.pos + o if w == 1 else self.size + o)
        return self.pos

    def fetch(self, a: int, n: int) -> bytes:
        """Bytes [a, a+n) exigiendo 206 y longitud exacta (un 200 con el cuerpo entero se rechaza)."""
        n = min(n, self.size - a)
        for intento in range(4):
            try:
                r = self.s.get(self.url, headers={**UA, "Range": f"bytes={a}-{a + n - 1}"}, timeout=90)
                if r.status_code != 206 or len(r.content) != n:
                    raise IOError(f"Range {a}+{n}: HTTP {r.status_code}, {len(r.content)} B")
                self.requests += 1
                self.bytes_read += n
                return r.content
            except Exception:
                if intento == 3:
                    raise
                time.sleep(2 ** intento)

    def read(self, n=-1):
        n = self.size - self.pos if n < 0 else min(n, self.size - self.pos)
        if n <= 0:
            return b""
        if not (self._buf0 <= self.pos and self.pos + n <= self._buf0 + len(self._buf)):
            self._buf0, self._buf = self.pos, self.fetch(self.pos, max(n, self.CHUNK))
        o = self.pos - self._buf0
        self.pos += n
        return self._buf[o:o + n]

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def extract(hf: HttpFile, zi: zipfile.ZipInfo, dest: pathlib.Path) -> None:
    """Extrae UN miembro: lee su cabecera local, trae los datos comprimidos por tramos y descomprime con zlib."""
    if zi.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise RuntimeError(f"{zi.filename}: método de compresión {zi.compress_type} no soportado")
    hdr = hf.fetch(zi.header_offset, 30)
    if hdr[:4] != b"PK\x03\x04":
        raise RuntimeError(f"{zi.filename}: cabecera local inválida")
    nlen, elen = struct.unpack("<HH", hdr[26:30])
    start = zi.header_offset + 30 + nlen + elen
    d = zlib.decompressobj(-15) if zi.compress_type == zipfile.ZIP_DEFLATED else None
    tmp = dest.with_suffix(dest.suffix + ".part")
    crc = n_out = 0
    with open(tmp, "wb") as f:
        for off in range(0, zi.compress_size, 8 << 20):
            raw = hf.fetch(start + off, min(8 << 20, zi.compress_size - off))
            out = d.decompress(raw) if d else raw
            f.write(out)
            crc = zlib.crc32(out, crc)
            n_out += len(out)
        if d:
            out = d.flush()
            f.write(out)
            crc = zlib.crc32(out, crc)
            n_out += len(out)
    with open(tmp, "rb") as f:
        head = f.read(512)
    ok = n_out == zi.file_size and crc == zi.CRC
    if ok and dest.suffix == ".tif":
        ok = head[:4] in MAGIC
    elif ok:
        ok = b"<html" not in head.lower() and b"<!doctype" not in head.lower()
    if not ok:
        tmp.unlink()
        raise RuntimeError(f"{zi.filename}: tamaño/CRC/cabecera inválidos ({n_out} de {zi.file_size} B)")
    tmp.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] + " Sin --yes no descarga nada.")
    ap.add_argument("--yes", action="store_true", help="confirma la descarga (unos 100-150 MB por región)")
    ap.add_argument("--region", action="append", choices=sorted(REGIONS),
                    help="solo estas regiones (por defecto las 3)")
    a = ap.parse_args()
    regs = a.region or sorted(REGIONS)
    if not a.yes:
        print("Nada descargado. Regiones:", ", ".join(regs), "\nCapas:", ", ".join(WANT + OPTIONAL),
              f"\nOrigen: {BASE}/<zip>/content (Range). Repetir con --yes para descargar.")
        return 0
    import requests
    sess = requests.Session()
    mf_path = OUT / "MANIFEST.json"
    OUT.mkdir(parents=True, exist_ok=True)
    mf = json.loads(mf_path.read_text(encoding="utf-8")) if mf_path.exists() else {}
    mf.update(doi=DOI, version=VERSION, license=LICENSE, record=f"https://zenodo.org/records/{RECORD}")
    mf.setdefault("files", {})
    mf.setdefault("range_bytes", {})
    total = 0
    for reg in regs:
        zname = REGIONS[reg]
        hf = HttpFile(f"{BASE}/{zname}/content", sess)
        with zipfile.ZipFile(hf) as z:
            infos = {i.filename.split("/")[-1]: i for i in z.infolist()
                     if not i.is_dir() and ".." not in i.filename.split("/") and not i.filename.startswith("/")}
        names = [n for n in infos if n.endswith(WANT) or (n.endswith(OPTIONAL) and
                 infos[n].compress_size < OPTIONAL_MAX and infos[n].file_size < OPTIONAL_MAX)]
        for n in sorted(names):
            zi, dest = infos[n], OUT / reg / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            key = f"{reg}/{n}"
            prev = mf["files"].get(key)
            if dest.exists() and prev and dest.stat().st_size == zi.file_size and sha256(dest) == prev["sha256"]:
                print("ok  ", key)
                continue
            extract(hf, zi, dest)
            mf["files"][key] = dict(sha256=sha256(dest), bytes=zi.file_size, compressed_bytes=zi.compress_size,
                                    zip=zname, zip_member=zi.filename, url=f"{BASE}/{zname}/content",
                                    fetched=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
            mf_path.write_text(json.dumps(mf, indent=1, ensure_ascii=False), encoding="utf-8")
            print("baja", key, zi.file_size)
        mf["range_bytes"][reg] = mf["range_bytes"].get(reg, 0) + hf.bytes_read   # acumulado entre ejecuciones
        total += hf.bytes_read
        print(f"{reg}: {hf.bytes_read / 1e6:.1f} MB leídos en {hf.requests} rangos")
    mf_path.write_text(json.dumps(mf, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Total de esta ejecución: {total} bytes ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
