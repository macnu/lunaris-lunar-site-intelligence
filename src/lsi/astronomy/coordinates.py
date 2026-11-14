"""Coordenadas lunares de LSI: estereográfica polar sur, base ENU, az/el y direcciones de rayo.

Sin SPICE. Fórmulas y convenciones: ``docs/science/matematica.md`` §1 y §3 y
``docs/science/convenciones.md``. Longitud ESTE-positiva; azimut N→E 0-360°.
"""
from __future__ import annotations

import numpy as np

from lsi.contracts import MOON_RADIUS_KM, MOON_RADIUS_M

FloatArray = np.ndarray


def stereo_forward(lat_deg, lon_deg_e) -> tuple[FloatArray, FloatArray]:
    """(lat, lon_E) → (x, y) en m; estereográfica polar sur, R=1737.4 km: ρ = 2R·cosφ/(1−sinφ)."""
    phi = np.radians(np.asarray(lat_deg, dtype=float))
    lam = np.radians(np.asarray(lon_deg_e, dtype=float))
    rho = 2.0 * MOON_RADIUS_M * np.cos(phi) / (1.0 - np.sin(phi))
    return rho * np.sin(lam), rho * np.cos(lam)


def stereo_inverse(x_m, y_m) -> tuple[FloatArray, FloatArray]:
    """(x, y) en m → (lat, lon_E en 0..360). En ρ=0 devuelve lon=0 (convención)."""
    x = np.asarray(x_m, dtype=float)
    y = np.asarray(y_m, dtype=float)
    rho = np.hypot(x, y)
    lat = -90.0 + 2.0 * np.degrees(np.arctan(rho / (2.0 * MOON_RADIUS_M)))
    lon = np.degrees(np.arctan2(x, y)) % 360.0  # (x, y), no (y, x)
    return lat, lon


def stereo_scale(lat_deg) -> FloatArray:
    """Factor de escala puntual k(φ) = 2/(1−sinφ) (proyección conforme, isótropa)."""
    return 2.0 / (1.0 - np.sin(np.radians(np.asarray(lat_deg, dtype=float))))


def normalize_lon(lon_deg, west_positive: bool = False) -> FloatArray:
    """Lleva la longitud a este-positiva en 0..360 (si ``west_positive``, se invierte el signo)."""
    lon = np.asarray(lon_deg, dtype=float)
    return (-lon if west_positive else lon) % 360.0


def enu_basis(lat_deg: float, lon_deg_e: float) -> np.ndarray:
    """Matriz 3×3 con filas E, N, U expresadas en MOON_ME (ortonormal y diestra)."""
    p, l = np.radians(lat_deg), np.radians(lon_deg_e)
    sp, cp, sl, cl = np.sin(p), np.cos(p), np.sin(l), np.cos(l)
    return np.array([
        [-sl, cl, 0.0],             # Este
        [-sp * cl, -sp * sl, cp],   # Norte
        [cp * cl, cp * sl, sp],     # Arriba
    ])


def vector_to_azel(v_km, lat_deg: float, lon_deg_e: float) -> tuple[FloatArray, FloatArray, FloatArray]:
    """v (N,3) en MOON_ME relativo al observador → (az 0-360, el, distancia). En cenit/nadir az=0."""
    v = np.atleast_2d(np.asarray(v_km, dtype=float))
    e, n, u = (v @ enu_basis(lat_deg, lon_deg_e).T).T
    h = np.hypot(e, n)
    # cenit/nadir: h ~ ruido de redondeo (cos(-90°) = 6e-17), no un 0 exacto
    az = np.where(h > 1e-12 * np.linalg.norm(v, axis=1), np.degrees(np.arctan2(e, n)) % 360.0, 0.0)
    return az, np.degrees(np.arctan2(u, h)), np.linalg.norm(v, axis=1)


def observer_position_km(lat_deg: float, lon_deg_e: float, height_m: float = 0.0) -> FloatArray:
    """Posición (3,) del observador en MOON_ME: (R+h)·Û, en km."""
    return (MOON_RADIUS_KM + height_m / 1000.0) * enu_basis(lat_deg, lon_deg_e)[2]


def ray_direction(lon_deg_e: float, az_deg) -> tuple[FloatArray, FloatArray]:
    """(dx, dy) = (sin(λ+A), cos(λ+A)) en el plano estereográfico (azimut de cuadrícula λ+A)."""
    g = np.radians(lon_deg_e + np.asarray(az_deg, dtype=float))
    return np.sin(g), np.cos(g)
