"""Motor SPICE: Sol y Tierra vistos desde un punto de la esfera lunar (MOON_ME, LT+S).

Arquitectura §5.8; verificación en ``docs/science/luna-spice-sitios.md``. Todo acceso a spiceypy pasa por
``SPICE_LOCK`` (CSPICE no es thread-safe). El observador está solidario con la esfera de 1737.4 km (+ altura).
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import spiceypy as sp
from spiceypy.utils.exceptions import SpiceyError

from lsi.contracts import (
    EARTH_RADIUS_EQ_KM, MOON_RADIUS_KM, SPICE_ABCORR, SPICE_FRAME, SUN_RADIUS_KM, UTC_MAX, UTC_MIN,
    Body, BodyTrack, DateOutOfRangeError, FloatArray, KernelInfo, KernelsMissingError, SkySeries,
)

SPICE_LOCK = threading.Lock()  # ponytail: un lock global; CSPICE serializa de todos modos

KERNEL_FILES = ("naif0012.tls", "pck00011.tpc", "moon_080317.tf", "moon_assoc_me.tf",
                "moon_pa_de421_1900-2050.bpc", "de421.bsp")
_MOON_PA_ID = 31006
_BODY_RADIUS_KM = {Body.SUN: SUN_RADIUS_KM, Body.EARTH: EARTH_RADIUS_EQ_KM}
DEFAULT_KERNEL_DIR = Path(__file__).resolve().parents[3] / "kernels"

_info: Optional[KernelInfo] = None
_range_et: Optional[tuple] = None  # (et de UTC_MIN, et de UTC_MAX)


def load_kernels(kernel_dir: Path = DEFAULT_KERNEL_DIR) -> KernelInfo:
    """Carga idempotente de los 6 kernels; calcula et_min/et_max del BPC."""
    global _info, _range_et
    kernel_dir = Path(kernel_dir).resolve()
    with SPICE_LOCK:
        if _info is not None and _info.kernel_dir == str(kernel_dir):
            return _info
        missing = [k for k in KERNEL_FILES if not (kernel_dir / k).is_file()]
        if missing:
            raise KernelsMissingError(f"Faltan kernels SPICE en {kernel_dir}: {missing}")
        if _info is not None:
            sp.kclear()
        h = hashlib.sha256()
        for k in KERNEL_FILES:
            sp.furnsh(str(kernel_dir / k))
            h.update(k.encode())
            with open(kernel_dir / k, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        cover = sp.pckcov(str(kernel_dir / "moon_pa_de421_1900-2050.bpc"), _MOON_PA_ID, sp.stypes.SPICEDOUBLE_CELL(2000))
        et_min, et_max = sp.wnfetd(cover, 0)
        _range_et = (sp.str2et(UTC_MIN), sp.str2et(UTC_MAX))
        _info = KernelInfo(str(kernel_dir), KERNEL_FILES, h.hexdigest(), et_min, et_max, UTC_MIN, UTC_MAX,
                           sp.__version__)
        return _info


def _ensure() -> KernelInfo:
    return _info if _info is not None else load_kernels()


def utc_to_et(utc: str) -> float:
    """UTC ISO -> ET (TDB); DateOutOfRangeError si fuera de [UTC_MIN, UTC_MAX]."""
    _ensure()
    try:
        with SPICE_LOCK:
            et = sp.str2et(utc)
    except SpiceyError as e:
        raise DateOutOfRangeError(f"Fecha no interpretable: {utc!r} ({e})") from e
    _check_range(np.asarray([et]))
    return float(et)


def et_to_utc(et, fmt: str = "ISOC", prec: int = 0):
    """ET -> cadena(s) UTC ISO."""
    _ensure()
    with SPICE_LOCK:
        if np.ndim(et) == 0:
            return sp.et2utc(float(et), fmt, prec)
        return [sp.et2utc(float(t), fmt, prec) for t in np.asarray(et).ravel()]


def et_grid(et0: float, et1: float, step_s: float) -> FloatArray:
    """Rejilla ET [et0, et1]; incluye et1 solo si cae en la rejilla."""
    n = int(np.floor((et1 - et0) / step_s + 1e-9)) + 1
    return et0 + step_s * np.arange(n, dtype=np.float64)


def angular_radius_deg(dist_km, body: Body) -> FloatArray:
    """asin(R_cuerpo/d) en grados."""
    return np.degrees(np.arcsin(_BODY_RADIUS_KM[Body(body)] / np.asarray(dist_km, dtype=np.float64)))


def _check_range(et: FloatArray) -> None:
    lo, hi = _range_et
    if not np.all(np.isfinite(et)) or et.min() < lo or et.max() > hi:
        raise DateOutOfRangeError(f"ET fuera del rango válido [{UTC_MIN}, {UTC_MAX}] o no finito")


def body_track(et, lat_deg: float, lon_deg_e: float, body: Body, height_m: float = 0.0) -> BodyTrack:
    """Az/el/distancia/radio angular de ``body`` desde (lat, lon E+, h) sobre la esfera, MOON_ME, LT+S.

    Vectorizado: ``spkpos`` sobre todos los ET menos el observador fijo (paralaje). Equivale a ``spkcpo``
    (~1e-8°, ver luna-spice-sitios.md §1).
    """
    _ensure()
    body = Body(body)
    et = np.atleast_1d(np.asarray(et, dtype=np.float64))
    _check_range(et)
    la, lo = np.radians(lat_deg), np.radians(lon_deg_e)
    sla, cla, slo, clo = np.sin(la), np.cos(la), np.sin(lo), np.cos(lo)
    up = np.array([cla * clo, cla * slo, sla])
    east = np.array([-slo, clo, 0.0])
    north = np.array([-sla * clo, -sla * slo, cla])
    obs = (MOON_RADIUS_KM + height_m / 1000.0) * up
    try:
        with SPICE_LOCK:
            pos, _ = sp.spkpos(body.value, et, SPICE_FRAME, SPICE_ABCORR, "MOON")
    except SpiceyError as e:
        raise DateOutOfRangeError(f"SPICE no puede orientar MOON_ME en esas fechas: {e}") from e
    v = np.atleast_2d(np.asarray(pos)) - obs
    e_, n_, u_ = v @ east, v @ north, v @ up
    d = np.linalg.norm(v, axis=1)
    h = np.hypot(e_, n_)
    az = np.where(h > 0, np.degrees(np.arctan2(e_, n_)) % 360.0, 0.0)
    el = np.degrees(np.arctan2(u_, h))
    return BodyTrack(body, az, el, d, angular_radius_deg(d, body))


def sky_series(et, lat_deg: float, lon_deg_e: float, height_m: float = 0.0) -> SkySeries:
    """BodyTrack de Sol y Tierra sobre ``et`` con el hash de kernels."""
    info = _ensure()
    et = np.atleast_1d(np.asarray(et, dtype=np.float64))
    return SkySeries(et, float(lat_deg), float(lon_deg_e), float(height_m),
                     body_track(et, lat_deg, lon_deg_e, Body.SUN, height_m),
                     body_track(et, lat_deg, lon_deg_e, Body.EARTH, height_m),
                     kernel_hash=info.kernel_hash)
