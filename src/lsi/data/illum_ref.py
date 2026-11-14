"""Iluminación media PUBLICADA del polo sur (LOLA, Mazarico et al. 2011; PGDA producto 69) para contrastar con LSI.

Mapas ``AVGVISIB_{85S_060M,75S_120M}_201608.TIF`` (int16, valor = DN × 4e-5 = fracción 0-1 del disco solar visible, media
horaria de ~18,6 años, SUPERFICIE sin altura de observador, Sol de disco finito sin oscurecimiento de limbo declarado).
Estereográfica polar sur R=1737.4 km (igual que el DEM de LSI). Se usa el de 60 m (≥ 85°S, radio 151,7 km) y, fuera de él,
el de 120 m (≥ 75°S). Definición comparable en LSI: ``effective_illumination`` a ``observer_height_m=0`` en 18,6 años.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from rasterio.enums import Resampling

from lsi.data.thermal import grid_window, point_value

ROOT = Path(__file__).resolve().parents[3]
DIR = ROOT / "data" / "raw" / "illum_ref"
SCALE = 4e-5
PRODUCTS = (("60m", DIR / "AVGVISIB_85S_060M_201608.TIF", 151_740.0), ("120m", DIR / "AVGVISIB_75S_120M_201608.TIF", 457_440.0))
ATTRIBUTION = ("LRO LOLA, mapas de iluminación media del Sol (NASA/GSFC PGDA, producto 69). Cítese Mazarico, E. et al. (2011), "
               "Illumination conditions of the lunar polar regions using LOLA topography, Icarus 211, 1066-1081, "
               "doi:10.1016/j.icarus.2010.10.030. https://pgda.gsfc.nasa.gov/products/69")
DEFINITION = ("fracción media del disco solar visible, superficie (altura 0), pasos horarios sobre ~18,6 años (ciclo de "
              "nutación), disco finito; mapa de agosto de 2016")


def illum_ref_available() -> bool:
    return all(p.exists() for _, p, _ in PRODUCTS)


def _pick(*xy_extent_m: float):
    ext = max(abs(v) for v in xy_extent_m)
    for name, path, reach in PRODUCTS:
        if path.exists() and ext <= reach - 100.0:
            return name, path
    return None, None


def illum_ref_window(site_key: str, center_x_m: float, center_y_m: float, half_size_m: float, max_px: int) -> Optional[dict]:
    """Ventana de iluminación media publicada (fracción 0-1, NaN = sin dato) sobre la malla del recorte. None si faltan datos."""
    name, path = _pick(abs(center_x_m) + half_size_m, abs(center_y_m) + half_size_m)
    if path is None:
        return None
    w = grid_window(path, center_x_m, center_y_m, half_size_m, max_px, Resampling.bilinear, SCALE)
    if w is None:
        return None
    return {**w, "site_key": site_key, "units": "fraction", "nodata": float("nan"), "product": name,
            "native_pixel_m": float(name[:-1]),
            "attribution": ATTRIBUTION, "definition": DEFINITION}


def illum_ref_at(x_m: float, y_m: float) -> dict:
    """Valor publicado en un punto: bilineal, mínimo y máximo de la vecindad 3×3 px (≈ 180 m con el de 60 m).
    La vecindad acota el efecto de que el mapa promedia píxeles de 60-240 m y LSI evalúa un punto."""
    name, path = _pick(abs(x_m), abs(y_m))
    if path is None:
        return {"value": float("nan"), "min3": float("nan"), "max3": float("nan"), "product": None}
    px = float(name[:-1])
    nb = [point_value(path, x_m + i * px, y_m + j * px, SCALE) for i in (-1, 0, 1) for j in (-1, 0, 1)]
    nb = [v for v in nb if np.isfinite(v)]
    return {"value": point_value(path, x_m, y_m, SCALE), "min3": min(nb) if nb else float("nan"),
            "max3": max(nb) if nb else float("nan"), "product": name}
