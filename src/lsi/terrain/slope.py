"""Pendiente: mapa por diferencia central y estadísticos en la huella de aterrizaje (disco de radio r).

Receta medida en ``docs/science/terreno-geologia.md`` §3. ``slp`` de LOLA/PGDA es exactamente la diferencia central
con baseline de 10 m (2 px de 5 m). Nodata es NaN y nunca entra en un estadístico como 0.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from lsi.contracts import DemWindow, FloatArray, ObserverOutsideDemError, SlopeStats
from lsi.terrain.sampling import pixel_coords


def slope_map_deg(window: DemWindow, baseline_m: float = 10.0) -> FloatArray:
    """Pendiente (°) = atan(|∇z|), gradiente por diferencia central con ``baseline_m`` (múltiplo par del píxel).

    Devuelve float64 con la forma de la ventana; NaN en el borde (k px) y donde algún extremo del stencil es NaN.
    """
    px = window.pixel_size_m
    k = baseline_m / (2.0 * px)
    if k < 1 or abs(k - round(k)) > 1e-9:
        raise ValueError(f"baseline_m={baseline_m} debe ser múltiplo de 2·píxel ({2 * px} m).")
    k = int(round(k))
    z = np.asarray(window.data, dtype=np.float64)
    out = np.full(z.shape, np.nan)
    if z.shape[0] > 2 * k and z.shape[1] > 2 * k:
        gx = (z[k:-k, 2 * k:] - z[k:-k, :-2 * k]) / baseline_m          # +x = columnas crecientes
        gy = (z[2 * k:, k:-k] - z[:-2 * k, k:-k]) / baseline_m          # signo irrelevante para |∇z|
        out[k:-k, k:-k] = np.degrees(np.arctan(np.hypot(gx, gy)))
    return out


def disk_view(arr: FloatArray, window: DemWindow, x_m: float, y_m: float, r_m: float) -> FloatArray:
    """Valores de ``arr`` dentro del disco (centro = píxel más cercano al punto; distancia en px ≤ r/px); incluye NaN.

    Lanza ``ObserverOutsideDemError`` si el disco no cabe entero en la ventana (no se estima con un disco recortado).
    """
    col, row = pixel_coords(window, np.float64(x_m), np.float64(y_m))
    rp = r_m / window.pixel_size_m
    n = int(np.ceil(rp))
    h, w = arr.shape
    if not (np.isfinite(col) and np.isfinite(row)):
        raise ObserverOutsideDemError(f"Punto ({x_m}, {y_m}) no finito.")
    c, r = int(np.rint(col)), int(np.rint(row))
    if r - n < 0 or c - n < 0 or r + n >= h or c + n >= w:
        raise ObserverOutsideDemError(f"El disco r={r_m} m en ({x_m}, {y_m}) no cabe en la ventana del DEM.")
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    return arr[r - n:r + n + 1, c - n:c + n + 1][(xx ** 2 + yy ** 2) <= rp ** 2]


def _footprint_values(surf: DemWindow, x_m: float, y_m: float, r_foot_m: float, slp: DemWindow | None,
                      baseline_m: float) -> tuple[FloatArray, str]:
    if slp is not None:
        v = disk_view(np.asarray(slp.data, dtype=np.float64), slp, x_m, y_m, r_foot_m)
        src = "slp"
    else:
        v = disk_view(slope_map_deg(surf, baseline_m), surf, x_m, y_m, r_foot_m)
        src = "surf_central_diff_10m" if baseline_m == 10.0 else f"surf_central_diff_{baseline_m:g}m"
    return v[np.isfinite(v)], src


def footprint_slope(surf: DemWindow, x_m: float, y_m: float, r_foot_m: float = 50.0,
                    percentile: float = 90.0, slp: DemWindow | None = None, baseline_m: float = 10.0) -> SlopeStats:
    """Percentil, media y máximo de la pendiente en el disco de la huella; ``slp`` si se da, si no deriva de ``surf``.

    Sin ningún píxel válido: estadísticos NaN y ``n_pixels=0`` (nunca 0°).
    """
    v, src = _footprint_values(surf, x_m, y_m, r_foot_m, slp, baseline_m)
    if v.size == 0:
        nan = float("nan")
        return SlopeStats(nan, percentile, nan, nan, r_foot_m, 0, src)
    return SlopeStats(float(np.percentile(v, percentile)), percentile, float(v.mean()), float(v.max()),
                      r_foot_m, int(v.size), src)


def footprint_area_below_pct(surf: DemWindow, x_m: float, y_m: float, thresholds_deg: Sequence[float] = (5, 8, 10, 15),
                             r_foot_m: float = 50.0, slp: DemWindow | None = None,
                             baseline_m: float = 10.0) -> Mapping[float, float]:
    """% del área válida del disco con pendiente < umbral (estricto, como la receta). NaN si no hay píxeles válidos."""
    v, _ = _footprint_values(surf, x_m, y_m, r_foot_m, slp, baseline_m)
    return {float(t): (float(100.0 * np.mean(v < t)) if v.size else float("nan")) for t in thresholds_deg}
