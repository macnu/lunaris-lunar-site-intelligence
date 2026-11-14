"""Confianza de datos: DemConfidence (g90/e90/DC, terreno-geologia.md §2.3) y DataConfidence (matematica.md §7.5).

Funciones puras. Umbrales «a calibrar» en ``config/simulation.json: terrain.dem_confidence`` y ``score.confidence``.
"""
from __future__ import annotations

import math
from typing import Mapping, Optional

import numpy as np
from scipy.ndimage import distance_transform_edt

from lsi.contracts import (
    ConfidenceLevel, DataConfidence, DemConfidence, DemWindow, HorizonResult, ScoreParams,
)

_ORDER = (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
# Defectos = terreno-geologia.md §2.3 (los mismos que simulation.json); cfg los sobreescribe.
_DEFAULTS = dict(radius_m=100.0, g90_high_m=15.0, e90_high_m=0.6, g90_medium_m=25.0, e90_medium_m=1.0,
                 dc_g90_lo_m=10.0, dc_g90_hi_m=40.0, dc_e90_lo_m=0.4, dc_e90_hi_m=1.5,
                 open_azimuth_downgrade_fraction=0.10)


def dem_confidence(ldec: DemWindow, toterr: DemWindow, x_m: float, y_m: float, horizon: HorizonResult,
                   cfg: Mapping) -> DemConfidence:
    """g90 (distancia al píxel con retorno), e90 (toterr), f_obs, clase ALTA/MEDIA/BAJA y DC.

    ``cfg`` = ``simulation.json`` completo o solo su bloque ``terrain.dem_confidence``. Baja un nivel si la
    fracción de azimutes con horizonte limitado por cobertura supera ``open_azimuth_downgrade_fraction``.
    La ventana debe cubrir el disco con margen (la distancia al retorno más cercano se mide dentro de ella).
    """
    terrain = cfg.get("terrain", {})
    c = {**_DEFAULTS, **(terrain.get("dem_confidence", {}) if "terrain" in cfg else cfg)}
    eff_res = float(terrain.get("effective_resolution_m", 30.0))
    if ldec.data.shape != toterr.data.shape or ldec.pixel_size_m != toterr.pixel_size_m:
        raise ValueError("ldec y toterr deben compartir malla")
    ps = ldec.pixel_size_m
    rows, cols = np.indices(ldec.data.shape)
    disk = np.hypot(ldec.x0_m + ps * cols - x_m, ldec.y0_m - ps * rows - y_m) <= c["radius_m"]
    if not disk.any():
        raise ValueError("el disco de confianza no intersecta la ventana")
    observed = np.nan_to_num(ldec.data, nan=0.0) > 0
    # Distancia (m) de cada píxel al retorno observado más cercano; inf si la ventana no tiene ninguno.
    g90 = float(np.percentile((distance_transform_edt(~observed) * ps)[disk], 90)) if observed.any() else math.inf
    err = toterr.data[disk]
    err = err[np.isfinite(err)]
    e90 = float(np.percentile(err, 90)) if err.size else math.nan
    f_obs = float(observed[disk].mean())

    if not (e90 == e90) or not math.isfinite(g90):          # sin dato: nunca un valor plausible
        level, dc = ConfidenceLevel.LOW, 0.0
    else:
        clip01 = lambda x: min(1.0, max(0.0, x))  # noqa: E731
        dc = min(clip01((c["dc_g90_hi_m"] - g90) / (c["dc_g90_hi_m"] - c["dc_g90_lo_m"])),
                 clip01((c["dc_e90_hi_m"] - e90) / (c["dc_e90_hi_m"] - c["dc_e90_lo_m"])))
        if g90 <= c["g90_high_m"] and e90 <= c["e90_high_m"]:
            level = ConfidenceLevel.HIGH
        elif g90 <= c["g90_medium_m"] and e90 <= c["e90_medium_m"]:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW
    open_frac = float(np.mean(horizon.limited))
    if open_frac > c["open_azimuth_downgrade_fraction"]:
        level = _ORDER[min(_ORDER.index(level) + 1, 2)]
    return DemConfidence(level=level, dc=dc, g90_m=g90, e90_m=e90, f_obs=f_obs, radius_m=float(c["radius_m"]),
                         open_azimuth_fraction=open_frac, effective_resolution_m=eff_res)


def horizon_sigma_p90(h_plus_deg, h_minus_deg, percentile: float = 90.0) -> float:
    """σh90 = p90 sobre azimutes de |H(z+σ) − H(z−σ)|/2 (°): cuánto mueve el error vertical del DEM al horizonte
    (revision-geologica §2). Los dos horizontes los calcula el pipeline (k=1, mismo observador). NaN si no hay dato."""
    a, b = np.asarray(h_plus_deg, dtype=np.float64), np.asarray(h_minus_deg, dtype=np.float64)
    if a.shape != b.shape or a.size == 0:
        raise ValueError("los dos horizontes deben tener la misma malla azimutal")
    d = np.abs(a - b) / 2.0
    return float(np.percentile(d, percentile)) if np.all(np.isfinite(d)) else math.nan


def support_confidence(dem: Optional[DemConfidence], sigma_h90_deg: float, hz_hi_deg: float = 0.5,
                       hz_lo_deg: float = 0.1) -> tuple[float, float]:
    """(c_sup, c_hz) con c_sup = min(c_gap, c_err, c_hz) (revision-geologica §2; sustituye a la fracción de píxeles
    observados, casi constante: ~9 % en todo el DEM, así que «alta» era inalcanzable).

    c_gap y c_err ya están en ``dem.dc`` (= min(clip((40−g90)/30), clip((1,5−e90)/1,1)), umbrales de terrain.dem_confidence);
    c_hz = clip((hi − σh90)/(hi − lo)) con hi = 0,5° (≈ diámetro solar, `a verificar`) y lo = 0,1°. Sin dato
    (sin DEM, sin toterr/ldec, σh90 NaN): c_sup = 0, nunca un valor plausible. Con los umbrales 0,75/0,5 de C: alta ⇔
    g90 ≤ 17,5 m, e90 ≤ 0,675 m, σh90 ≤ 0,20°.
    """
    ok = dem is not None and sigma_h90_deg == sigma_h90_deg
    c_hz = min(1.0, max(0.0, (hz_hi_deg - sigma_h90_deg) / (hz_hi_deg - hz_lo_deg))) if ok else 0.0
    return (min(dem.dc, c_hz) if ok else 0.0), c_hz


def data_confidence(c_cov: float, c_sup: float, c_range: float, dem: Optional[DemConfidence],
                    params: ScoreParams) -> DataConfidence:
    """C = min(c_cov, c_sup, c_rango) y etiqueta alta/media/baja (umbrales ``params.conf_high/medium``)."""
    for name, v in (("c_cov", c_cov), ("c_sup", c_sup), ("c_range", c_range)):
        if not (v == v):
            raise ValueError(f"{name} es NaN")
    c_cov, c_sup, c_range = (min(1.0, max(0.0, v)) for v in (c_cov, c_sup, c_range))
    c = min(c_cov, c_sup, c_range)
    level = (ConfidenceLevel.HIGH if c >= params.conf_high else
             ConfidenceLevel.MEDIUM if c >= params.conf_medium else ConfidenceLevel.LOW)
    return DataConfidence(level=level, c=c, c_cov=c_cov, c_sup=c_sup, c_range=c_range, dem=dem)
