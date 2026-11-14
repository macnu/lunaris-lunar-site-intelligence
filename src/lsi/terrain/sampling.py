"""Interpolación bilineal centrada con máscara de validez. Nodata nunca es 0: inválido ⇒ -inf y máscara False."""
from __future__ import annotations

import numpy as np

from lsi.contracts import BoolArray, DemWindow, FloatArray


def pixel_coords(window: DemWindow, x_m: FloatArray, y_m: FloatArray) -> tuple[FloatArray, FloatArray]:
    """(col, row) continuas centradas: los centros de píxel son enteros. NO usa rasterio.index()."""
    px = window.pixel_size_m
    col = (np.asarray(x_m, dtype=np.float64) - window.x0_m) / px
    row = (window.y0_m - np.asarray(y_m, dtype=np.float64)) / px
    return col, row


def sample_bilinear(window: DemWindow, x_m: FloatArray, y_m: FloatArray) -> tuple[FloatArray, BoolArray]:
    """Valor bilineal (convención centrada) y máscara; inválido si cae fuera o algún vecino es NaN.

    El valor inválido es ``-inf`` (nunca 0). Válido solo en [0, W-1]x[0, H-1] (entre centros de píxel).
    """
    z = window.data
    h, w = z.shape
    col, row = pixel_coords(window, x_m, y_m)
    inside = (col >= 0) & (col <= w - 1) & (row >= 0) & (row <= h - 1)   # False también con NaN/inf
    cc = np.where(inside, col, 0.0)
    rr = np.where(inside, row, 0.0)
    c0 = np.clip(np.floor(cc), 0, max(w - 2, 0)).astype(np.intp)
    r0 = np.clip(np.floor(rr), 0, max(h - 2, 0)).astype(np.intp)
    fx, fy = cc - c0, rr - r0
    c1, r1 = np.minimum(c0 + 1, w - 1), np.minimum(r0 + 1, h - 1)
    z00, z01 = z[r0, c0].astype(np.float64), z[r0, c1].astype(np.float64)
    z10, z11 = z[r1, c0].astype(np.float64), z[r1, c1].astype(np.float64)
    valid = inside & np.isfinite(z00) & np.isfinite(z01) & np.isfinite(z10) & np.isfinite(z11)
    with np.errstate(invalid="ignore"):
        val = z00 * (1 - fx) * (1 - fy) + z01 * fx * (1 - fy) + z10 * (1 - fx) * fy + z11 * fx * fy
    return np.where(valid, val, -np.inf), valid
