"""Temperatura de superficie polar (LRO Diviner) por ventana alineada con la malla de un recorte.

Producto: mapas estacionales de Williams et al. 2019 (JGR Planets 124, 2505-2521), polo sur, 240 m/px, temperatura de
brillo bolométrica, estereográfica polar sur R=1737.4 km (la misma que el DEM de LSI). Seis GeoTIFF float32 en
``data/raw/diviner/`` (``scripts/fetch_thermal_psr.py``). «summer»/«winter» = épocas del año con latitud subsolar por encima/
por debajo del ecuador (no son verano/invierno del hemisferio sur).

``kind``: ``max`` = máximo de los dos máximos estacionales; ``min`` = mínimo de los dos mínimos; ``mean`` = media de los
dos promedios estacionales (pesos iguales: aproximación, las dos épocas duran ≈ medio año cada una).
Convención de ventana = ``DemWindow``: ``x0_m, y0_m`` = centro del píxel [0, 0]; filas hacia y negativa.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[3]
DIVINER_DIR = ROOT / "data" / "raw" / "diviner"
_KIND = {"mean": "avg", "max": "max", "min": "min"}
_AGG = {"mean": np.nanmean, "max": np.nanmax, "min": np.nanmin}
ATTRIBUTION = ("LRO Diviner Lunar Radiometer Experiment (NASA/UCLA). Williams, J.-P., Greenhagen, B. T., Paige, D. A., "
               "Schorghofer, N., Sefton-Nash, E., Hayne, P. O., Lucey, P. G., Siegler, M. A., Aye, K.-M. (2019), Seasonal polar "
               "temperatures on the Moon, J. Geophys. Res. Planets 124, 2505-2521, doi:10.1029/2019JE006028. "
               "Datos: http://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar/additional_maps/")


def grid_window(path: Path, cx: float, cy: float, half: float, max_px: int, resampling=Resampling.bilinear,
                scale: float = 1.0) -> Optional[dict]:
    """Remuestrea ``path`` a una malla de n×n píxeles centrada en (cx, cy), lado 2·half. Devuelve
    {data (float32, NaN = sin dato), x0_m, y0_m, pixel_size_m} o None si no hay solape / todo NaN."""
    with rasterio.open(path) as src:
        px = abs(src.transform.a)
        n = int(max(1, min(max_px, math.ceil(2 * half / px))))
        step = 2 * half / n
        col0, row0 = (cx - half - src.transform.c) / px, (src.transform.f - (cy + half)) / px
        win = Window(col0, row0, 2 * half / px, 2 * half / px)
        raw = src.read(1, window=win, out_shape=(n, n), resampling=resampling, boundless=True,
                       fill_value=src.nodata if src.nodata is not None else 0)
        nd = src.nodata
    a = raw.astype(np.float32)
    bad = ~np.isfinite(a) | (a <= -30000)            # NaN, nodata int16 y su contaminación bilineal
    if nd is not None and np.isfinite(nd):
        bad |= a == np.float32(nd)
    a = np.where(bad, np.float32(np.nan), a * np.float32(scale))
    if not np.isfinite(a).any():
        return None
    return {"data": a, "x0_m": cx - half + step / 2, "y0_m": cy + half - step / 2, "pixel_size_m": step}


def point_value(path: Path, x_m: float, y_m: float, scale: float = 1.0) -> float:
    """Interpolación bilineal (centros de píxel) en un punto; NaN si cae fuera o toca nodata."""
    with rasterio.open(path) as src:
        px = abs(src.transform.a)
        c, r = (x_m - src.transform.c) / px - 0.5, (src.transform.f - y_m) / px - 0.5
        c0, r0 = math.floor(c), math.floor(r)
        if c0 < 0 or r0 < 0 or c0 + 1 >= src.width or r0 + 1 >= src.height:
            return float("nan")
        z = src.read(1, window=Window(c0, r0, 2, 2)).astype(np.float64)
    if (z <= -30000).any() or not np.isfinite(z).all():
        return float("nan")
    fx, fy = c - c0, r - r0
    return float((z[0, 0] * (1 - fx) + z[0, 1] * fx) * (1 - fy) + (z[1, 0] * (1 - fx) + z[1, 1] * fx) * fy) * scale


def _paths(kind: str) -> list[Path]:
    if kind not in _KIND:
        raise ValueError(f"kind debe ser 'mean', 'max' o 'min' (recibido {kind!r}).")
    return [DIVINER_DIR / f"polar_south_80_{s}_{_KIND[kind]}-float.tif" for s in ("summer", "winter")]


def thermal_available() -> bool:
    return all(p.exists() for k in _KIND for p in _paths(k))


def thermal_window(site_key: str, center_x_m: float, center_y_m: float, half_size_m: float, max_px: int,
                   kind: str = "mean") -> Optional[dict]:
    """Ventana de temperatura de superficie Diviner (K) sobre la malla de un recorte. None si faltan los datos o no hay solape."""
    ps = _paths(kind)
    if not all(p.exists() for p in ps):
        return None
    ws = [grid_window(p, center_x_m, center_y_m, half_size_m, max_px) for p in ps]
    if any(w is None for w in ws):
        return None
    with np.errstate(all="ignore"):
        data = _AGG[kind](np.stack([w["data"] for w in ws]), axis=0).astype(np.float32)
    # ponytail: NaN en una época → se usa la otra (nanmax/nanmin/nanmean); píxeles sin ninguna época quedan NaN
    return {**{k: ws[0][k] for k in ("x0_m", "y0_m", "pixel_size_m")}, "data": data, "site_key": site_key, "kind": kind,
            "units": "K", "nodata": float("nan"), "native_pixel_m": 240.036, "attribution": ATTRIBUTION,
            "definition": "temperatura de brillo bolométrica de superficie, ciclo diurno, 2009-2019, épocas summer/winter por latitud subsolar"}


def thermal_at(x_m: float, y_m: float, kind: str = "mean") -> float:
    """Temperatura Diviner (K) en un punto (x, y) estereográfico; NaN si no hay dato."""
    v = [point_value(p, x_m, y_m) for p in _paths(kind)]
    v = [t for t in v if np.isfinite(t)]
    return float(_AGG[kind](v)) if v else float("nan")
