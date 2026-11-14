"""Carga de DEM LOLA/PGDA (GeoTIFF 5 mpp): descubrimiento, CRS, ventanas, metadatos, validez, sha256.

Convención de píxel centrado (``DemWindow``): (x0_m, y0_m) = centro del píxel [0, 0] de la ventana.
Nodata declarado → NaN (nunca 0). Capas siempre float32 en memoria.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Mapping, Optional, Tuple

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.windows import Window

from lsi.contracts import (
    DEM_PROJ4,
    BoolArray,
    DemCrsMismatchError,
    DemLayer,
    DemMetadata,
    DemNotFoundError,
    DemRef,
    DemWindow,
    ObserverOutsideDemError,
)

_NAME_RE = re.compile(r"^(?P<key>[A-Za-z]+\d+)_final_adj_5mpp_(?P<layer>surf|slp|ldec|toterr)\.tif$")
_CRS_KEYS = ("proj", "lat_0", "lon_0", "x_0", "y_0", "R", "units")
_EXPECTED = CRS.from_string(DEM_PROJ4).to_dict()


def _check_crs(crs: Optional[CRS], path: object) -> None:
    """Compara PARÁMETROS (no igualdad de objetos: Malapert/toterr nombra el CRS distinto)."""
    got = crs.to_dict() if crs else {}
    for k in _CRS_KEYS:
        a, b = got.get(k), _EXPECTED.get(k)
        if isinstance(b, (int, float)) and not isinstance(b, bool) and a is not None:
            same = math.isclose(float(a), float(b), abs_tol=1e-9)
        else:
            same = a == b
        if not same:
            raise DemCrsMismatchError(f"CRS de {path}: parámetro '{k}' = {a!r}, se esperaba {b!r}.")


def _open(path: str):
    if not os.path.exists(path):
        raise DemNotFoundError(f"No existe el GeoTIFF {path}.")
    src = rasterio.open(path)
    try:
        _check_crs(src.crs, path)
        t = src.transform
        if t.b != 0 or t.d != 0 or t.e >= 0 or abs(t.a) != abs(t.e):
            raise DemCrsMismatchError(f"{path}: geotransform no es norte-arriba con píxel cuadrado.")
    except Exception:
        src.close()
        raise
    return src


def discover_dems(raw_dir: Path) -> dict[str, DemRef]:
    """Busca data/raw/*/SiteNN_final_adj_5mpp_{surf,slp,ldec,toterr}.tif; clave 'SiteNN'. Vacío si no hay."""
    found: dict[str, dict[str, str]] = {}
    for p in sorted(Path(raw_dir).glob("*/*_final_adj_5mpp_*.tif")):
        m = _NAME_RE.match(p.name)
        if m:
            found.setdefault(m["key"], {})[m["layer"]] = str(p)
    refs: dict[str, DemRef] = {}
    for key, paths in found.items():
        if DemLayer.SURF.value not in paths:   # sin elevación no hay DEM utilizable
            continue
        with _open(paths[DemLayer.SURF.value]) as src:
            b = src.bounds
        refs[key] = DemRef(key=key, directory=str(Path(paths["surf"]).parent), paths=paths,
                           bounds_xy_m=(b.left, b.bottom, b.right, b.top))
    return refs


FAR_FIELD_KEY = "LOLA80S"
_FAR_GLOB = "*/LDEM_80S_80MPP_ADJ.TIF"


def discover_far_field(raw_dir: Path) -> Optional[DemRef]:
    """DEM polar LOLA 80 m (PGDA 90) en data/raw/*/LDEM_80S_80MPP_ADJ.TIF; None si no está. Valida el CRS por parámetros."""
    for p in sorted(Path(raw_dir).glob(_FAR_GLOB)):
        with _open(str(p)) as src:
            b = src.bounds
        return DemRef(key=FAR_FIELD_KEY, directory=str(p.parent), paths={DemLayer.SURF.value: str(p)},
                      bounds_xy_m=(b.left, b.bottom, b.right, b.top))
    return None


def load_far_field(raw_dir: Path, x_m: Optional[float] = None, y_m: Optional[float] = None,
                   r_max_m: Optional[float] = None, *, margin_px: int = 2) -> DemWindow:
    """Campo lejano como DemWindow (NaN = sin dato; ``validity_mask`` aplica). Con (x_m, y_m, r_max_m) lee solo la
    ventana cuadrada ±r_max alrededor del observador (≈ 0.75 k² px en vez de los 230 MB); sin ellos, el raster entero.
    ``meta.sha256`` es el del fichero entero (sidecar). ``DemNotFoundError`` si falta el TIF."""
    ref = discover_far_field(raw_dir)
    if ref is None:
        raise DemNotFoundError(f"No existe el DEM de campo lejano {_FAR_GLOB} bajo {raw_dir} (python scripts/fetch_data.py).")
    bounds = None if x_m is None else (x_m - r_max_m, y_m - r_max_m, x_m + r_max_m, y_m + r_max_m)
    return read_window(ref, DemLayer.SURF, bounds, margin_px=margin_px)


def _layer_path(ref: DemRef, layer: DemLayer) -> str:
    try:
        return ref.paths[layer.value]
    except KeyError:
        raise DemNotFoundError(f"{ref.key}: falta la capa '{layer.value}'.") from None


def dem_sha256(ref: DemRef, layer: DemLayer = DemLayer.SURF) -> str:
    """Hash del fichero (sidecar data/processed/dem_hash.json por (ruta, tamaño, mtime_ns))."""
    path = _layer_path(ref, layer)
    st = os.stat(path)
    sidecar = Path(ref.directory).parent.parent / "processed" / "dem_hash.json"
    sig = [st.st_size, st.st_mtime_ns]
    try:
        cache = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    hit = cache.get(path)
    if isinstance(hit, dict) and hit.get("sig") == sig:
        return hit["sha256"]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    cache[path] = {"sig": sig, "sha256": digest}
    try:  # el sidecar es solo una optimización: si no se puede escribir, se sigue
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError:
        pass
    return digest


def read_metadata(ref: DemRef, layer: DemLayer = DemLayer.SURF) -> DemMetadata:
    """Lee cabecera, valida CRS (parámetros; DemCrsMismatchError) y calcula sha256 (cacheado en sidecar)."""
    path = _layer_path(ref, layer)
    with _open(path) as src:
        b = src.bounds
        return DemMetadata(
            key=ref.key, layer=layer, width_px=src.width, height_px=src.height,
            pixel_size_m=float(src.transform.a), bounds_xy_m=(b.left, b.bottom, b.right, b.top),
            transform=tuple(float(v) for v in tuple(src.transform)[:6]), crs_wkt=src.crs.to_wkt(),
            nodata=None if src.nodata is None else float(src.nodata), dtype=src.dtypes[0],
            sha256=dem_sha256(ref, layer), size_bytes=os.path.getsize(path))


def read_window(ref: DemRef, layer: DemLayer = DemLayer.SURF,
                bounds_xy_m: Optional[Tuple[float, float, float, float]] = None, *, margin_px: int = 0) -> DemWindow:
    """Lee una ventana (None = capa completa) como DemWindow float32 con NaN en nodata; no carga el raster entero si hay ventana."""
    path = _layer_path(ref, layer)
    with _open(path) as src:
        t, px = src.transform, float(src.transform.a)
        if bounds_xy_m is None:
            c0, r0, c1, r1 = 0, 0, src.width, src.height
        else:
            xmin, ymin, xmax, ymax = bounds_xy_m
            c0 = math.floor((xmin - t.c) / px) - margin_px
            c1 = math.ceil((xmax - t.c) / px) + margin_px
            r0 = math.floor((t.f - ymax) / px) - margin_px
            r1 = math.ceil((t.f - ymin) / px) + margin_px
            c0, c1, r0, r1 = max(c0, 0), min(c1, src.width), max(r0, 0), min(r1, src.height)
            if c1 <= c0 or r1 <= r0:
                raise ObserverOutsideDemError(f"{ref.key}: la ventana {bounds_xy_m} no intersecta el DEM.")
        data = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float32, copy=False)
        nodata = src.nodata
    if nodata is not None and not math.isnan(nodata):
        data = np.where(data == np.float32(nodata), np.float32(np.nan), data)
    data[~np.isfinite(data)] = np.nan   # ±inf tampoco es dato
    return DemWindow(data=data, x0_m=t.c + px * (c0 + 0.5), y0_m=t.f - px * (r0 + 0.5), pixel_size_m=px,
                     layer=layer, meta=read_metadata(ref, layer), col_offset=c0, row_offset=r0)


def validity_mask(window: DemWindow) -> BoolArray:
    """True donde el píxel es finito y distinto de nodata."""
    ok = np.isfinite(window.data)
    nd = window.meta.nodata if window.meta else None
    if nd is not None and np.isfinite(nd):
        ok &= window.data != nd
    return ok


def find_dem_for_point(refs: Mapping[str, DemRef], x_m: float, y_m: float, margin_m: float = 0.0) -> Optional[DemRef]:
    """DEM cuya huella contiene el punto con margen interior de margin_m; None si ninguno."""
    for ref in refs.values():
        xmin, ymin, xmax, ymax = ref.bounds_xy_m
        if xmin + margin_m <= x_m <= xmax - margin_m and ymin + margin_m <= y_m <= ymax - margin_m:
            return ref
    return None
