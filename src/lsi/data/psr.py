"""Regiones permanentemente sombreadas (PSR) del polo sur: polígonos LOLA de Mazarico et al. 2011 digitalizados por LROC.

Fichero: ``data/raw/psr/NAC_POLE_PSR_SOUTH/LOLA_PSR_75S_120M_82S_060M_5KM2_FINAL.shp`` (653 polígonos > 5 km², estereográfica
polar sur R=1737.4 km, la misma que el DEM de LSI; ``scripts/fetch_thermal_psr.py``).

CIENCIA: una PSR publicada es sombra PERMANENTE en el ciclo de precesión de 18,6 años (horizonte con el DTM de 60/120 m,
Sol de disco finito, altura = superficie). NO equivale a «sombra» en un año simulado por LSI: un píxel que LSI ve oscuro
todo un año puede recibir luz en otro año del ciclo, y a 2 m de altura o con un DEM de 5 m el límite se desplaza. Úsese como
contraste/contexto, no como máscara de iluminación.
"""
from __future__ import annotations

import functools
import math
from pathlib import Path
from typing import Optional

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[3]
PSR_SHP = ROOT / "data" / "raw" / "psr" / "NAC_POLE_PSR_SOUTH" / "LOLA_PSR_75S_120M_82S_060M_5KM2_FINAL.shp"
ATTRIBUTION = ("PSR del polo sur: LROC/ASU, digitalización de las PSR > 5 km² de Mazarico, E. et al. (2011), Illumination "
               "conditions of the lunar polar regions using LOLA topography, Icarus 211, 1066-1081, "
               "doi:10.1016/j.icarus.2010.10.030. Producto: Brown, H. M. et al. (2022), LROC PSR Atlas and Mosaics, Lunar Polar "
               "Volatiles Conf. #5033. https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_PSR_SOUTH")


def psr_available() -> bool:
    return PSR_SHP.exists()


@functools.lru_cache(maxsize=1)
def _geoms() -> list:
    import shapefile  # pyshp
    return [s.__geo_interface__ for s in shapefile.Reader(str(PSR_SHP)).shapes()]


@functools.lru_cache(maxsize=1)
def _segments() -> tuple[np.ndarray, np.ndarray]:
    """Segmentos (a→b) de todos los anillos, shape (N, 2) cada uno. Even-odd entre anillos ⇒ los huecos funcionan solos."""
    A, B = [], []
    for g in _geoms():
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            for ring in poly:
                r = np.asarray(ring, dtype=float)
                A.append(r[:-1]); B.append(r[1:])
    return np.vstack(A), np.vstack(B)


def psr_mask_window(site_key: str, center_x_m: float, center_y_m: float, half_size_m: float, max_px: int,
                    pixel_size_m: Optional[float] = None) -> Optional[dict]:
    """Máscara bool (True = dentro de una PSR publicada) sobre la malla de n×n píxeles de un recorte (lado 2·half,
    n = max_px salvo que ``pixel_size_m`` fije el paso). None si faltan los datos."""
    if not psr_available():
        return None
    n = max_px if pixel_size_m is None else max(1, math.ceil(2 * half_size_m / pixel_size_m))
    step = 2 * half_size_m / n
    tr = from_origin(center_x_m - half_size_m, center_y_m + half_size_m, step, step)
    m = rasterize(_geoms(), out_shape=(n, n), transform=tr, fill=0, default_value=1, dtype="uint8").astype(bool)
    return {"data": m, "x0_m": center_x_m - half_size_m + step / 2, "y0_m": center_y_m + half_size_m - step / 2,
            "pixel_size_m": step, "site_key": site_key, "units": "bool", "nodata": None, "attribution": ATTRIBUTION,
            "definition": "PSR LOLA (Mazarico 2011), ciclo de 18,6 años, superficie; NO es la sombra de un año simulado"}


def psr_distance_m(x_m, y_m) -> np.ndarray:
    """Distancia con signo (m) de (x, y) al borde de la PSR más cercana: NEGATIVA dentro de una PSR, positiva fuera.
    NaN si faltan los datos. Exacta (distancia a segmentos); ponytail: O(N_segmentos) por punto, sin índice espacial."""
    x = np.atleast_1d(np.asarray(x_m, dtype=float)); y = np.atleast_1d(np.asarray(y_m, dtype=float))
    if not psr_available():
        return np.full(x.shape, np.nan)
    a, b = _segments()
    d = b - a
    L2 = np.maximum((d ** 2).sum(1), 1e-12)
    out = np.empty(x.shape)
    for i, (px, py) in enumerate(zip(x.ravel(), y.ravel())):
        t = np.clip(((px - a[:, 0]) * d[:, 0] + (py - a[:, 1]) * d[:, 1]) / L2, 0.0, 1.0)
        dist = np.hypot(px - (a[:, 0] + t * d[:, 0]), py - (a[:, 1] + t * d[:, 1])).min()
        cross = ((a[:, 1] > py) != (b[:, 1] > py)) & (px < a[:, 0] + (py - a[:, 1]) * d[:, 0] / np.where(d[:, 1] == 0, 1, d[:, 1]))
        out.flat[i] = -dist if cross.sum() % 2 else dist
    return out.reshape(np.shape(x_m)) if np.ndim(x_m) else out[0:1].reshape(())
