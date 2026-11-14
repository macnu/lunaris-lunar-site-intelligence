"""Rugosidad RMS de alturas (detrendadas) en un disco, a una o varias escalas. Receta: terreno-geologia.md §3.2.

Advertencia científica (§2.1): a r <= 25 m el DEM es interpolación (el 90 % de los píxeles no tiene retorno LOLA);
usar la rugosidad solo a r >= 50 m.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from lsi.contracts import DemWindow
from lsi.terrain.sampling import pixel_coords


def roughness_rms_m(surf: DemWindow, x_m: float, y_m: float, r_m: float = 50.0, detrend: bool = True) -> float:
    """RMS (m) de la altura tras ajustar por mínimos cuadrados y restar un plano dentro del disco.

    ``detrend=False`` resta solo la media. Píxeles NaN excluidos; NaN si quedan < 3 píxeles válidos o el disco
    no cabe en la ventana (nunca 0 por falta de dato). Normalización 1/N, igual que la receta medida.
    """
    px = surf.pixel_size_m
    z = np.asarray(surf.data, dtype=np.float64)
    col, row = pixel_coords(surf, np.float64(x_m), np.float64(y_m))
    if not (np.isfinite(col) and np.isfinite(row)):
        return float("nan")
    c, r = int(np.rint(col)), int(np.rint(row))
    rp = r_m / px
    n = int(np.ceil(rp))
    h, w = z.shape
    if r - n < 0 or c - n < 0 or r + n >= h or c + n >= w:
        return float("nan")
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    zw = z[r - n:r + n + 1, c - n:c + n + 1]
    m = ((xx ** 2 + yy ** 2) <= rp ** 2) & np.isfinite(zw)
    if m.sum() < 3:
        return float("nan")
    zz = zw[m]
    if detrend:
        a = np.column_stack([np.ones(zz.size), xx[m] * px, -yy[m] * px])   # y crece hacia arriba (filas hacia abajo)
        coef, *_ = np.linalg.lstsq(a, zz, rcond=None)
        res = zz - a @ coef
    else:
        res = zz - zz.mean()
    return float(np.sqrt(np.mean(res ** 2)))


def roughness_by_scale_m(surf: DemWindow, x_m: float, y_m: float, radii_m: Sequence[float] = (50.0, 100.0),
                         detrend: bool = True) -> Mapping[float, float]:
    """RMS detrendado por radio de disco (m)."""
    return {float(r): roughness_rms_m(surf, x_m, y_m, r, detrend) for r in radii_m}
