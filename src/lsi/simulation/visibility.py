"""Visibilidad de Sol y Tierra: fracción de disco sobre el horizonte (matematica.md §4, arquitectura.md §5.9).

Fracción de ÁREA (disco uniforme) o de flujo (oscurecimiento de limbo solo para el Sol). Con horizonte constante y
sin limbo es la fórmula analítica del segmento circular; con relieve, cuadratura de punto medio en n rebanadas
(x = ρ·sin φ_i). La aproximación ΔA = x/cos e solo vale en e ≲ 60° (en el polo e ≤ 8°).
"""
from __future__ import annotations

import dataclasses
from typing import Callable

import numpy as np

from lsi.astronomy import spice_engine
from lsi.contracts import (
    Body, BodyTrack, BodyVisibility, FloatArray, HorizonResult, IntArray, SkySeries, VisibilityParams,
    VisibilitySeries, VisibilityState,
)
from lsi.terrain.horizon import horizon_at, unknown_relevant_mask

_BLOCK = 8192
_COS_E_MIN = 0.1   # ponytail: e>84° no tiene sentido aquí; evita dividir por ~0 en ΔA = x/cos e


def disc_fraction_flat(t) -> FloatArray:
    """f(t)=½+(t√(1−t²)+asin t)/π con t=(e−H)/ρ; 0 si t≤−1, 1 si t≥1."""
    t = np.asarray(t, dtype=np.float64)
    c = np.clip(t, -1.0, 1.0)
    return 0.5 + (c * np.sqrt(1.0 - c * c) + np.arcsin(c)) / np.pi


def _slice_fraction(el_deg, az_deg, radius_deg, h_fn: Callable[[FloatArray], FloatArray],
                    n_slices: int = 64, u: float = 0.0) -> FloatArray:
    """Cuadratura de §4.3 con ``h_fn(az_deg)`` → H en grados. ``u``≠0: integral de flujo con limbo (exacta en y)."""
    el = np.atleast_1d(np.asarray(el_deg, dtype=np.float64))
    az = np.broadcast_to(np.asarray(az_deg, dtype=np.float64), el.shape)
    rho = np.broadcast_to(np.asarray(radius_deg, dtype=np.float64), el.shape)
    n = int(n_slices)
    phi = -np.pi / 2 + (np.arange(n) + 0.5) * np.pi / n
    x = rho[:, None] * np.sin(phi)
    c = rho[:, None] * np.cos(phi)
    dx = c * (np.pi / n)
    cose = np.maximum(np.cos(np.radians(el)), _COS_E_MIN)
    h = h_fn((az[:, None] + x / cose[:, None]).ravel()).reshape(x.shape)
    if u == 0.0:
        num = np.sum(np.clip(el[:, None] + c - h, 0.0, 2.0 * c) * dx, axis=1)
        return np.clip(num / (np.pi * rho ** 2), 0.0, 1.0)   # clip: redondeo ~1e-16 por encima de 1
    y_lo = np.clip(h - el[:, None], -c, c)        # parte visible del cuerdón: y ∈ [y_lo, c]
    g = lambda y: 0.5 * (y * np.sqrt(np.maximum(c * c - y * y, 0.0)) + c * c * np.arcsin(np.clip(y / c, -1, 1))) / rho[:, None]  # noqa: E731
    flux = (1.0 - u) * (c - y_lo) + u * (g(c) - g(y_lo))   # ∫ [1−u+u·μ] dy, μ=√(c²−y²)/ρ
    return np.clip(np.sum(flux * dx, axis=1) / (np.pi * rho ** 2 * (1.0 - u / 3.0)), 0.0, 1.0)


def disc_fraction(el_deg, az_deg, radius_deg, horizon: HorizonResult, kind: str = "lb",
                  n_slices: int = 64, limb_darkening_u: float = 0.0) -> FloatArray:
    """Fracción de disco visible con H(A) variable (rebanadas, matematica §4.3); analítica si H es constante."""
    h_arr = horizon.h_lb_deg if kind == "lb" else horizon.h_ub_deg
    if h_arr is None:
        raise ValueError("el resultado no tiene H_ub (compute_upper_bound=False)")
    el = np.asarray(el_deg, dtype=np.float64)
    if limb_darkening_u == 0.0 and np.ptp(h_arr) == 0.0:
        return disc_fraction_flat((el - h_arr[0]) / np.asarray(radius_deg, dtype=np.float64))
    f = _slice_fraction(el, az_deg, radius_deg, lambda a: horizon_at(horizon, a, kind), n_slices, limb_darkening_u)
    return f.reshape(el.shape)


def classify(f, eps: float = 1e-3) -> IntArray:
    """VisibilityState int8: HIDDEN f≤eps, VISIBLE f≥1−eps, PARTIAL resto (NaN → HIDDEN)."""
    f = np.asarray(f, dtype=np.float64)
    out = np.full(f.shape, VisibilityState.PARTIAL, dtype=np.int8)
    out[~(f > eps)] = VisibilityState.HIDDEN
    out[f >= 1.0 - eps] = VisibilityState.VISIBLE
    return out


def _fraction_blocks(track: BodyTrack, horizon: HorizonResult, kind: str, params: VisibilityParams) -> FloatArray:
    u = params.limb_darkening_u if track.body == Body.SUN else 0.0   # el limbo solo aplica al Sol
    out = np.empty(len(track.el_deg))
    for i in range(0, len(out), _BLOCK):
        s = slice(i, i + _BLOCK)
        out[s] = disc_fraction(track.el_deg[s], track.az_deg[s], track.radius_deg[s], horizon, kind, params.n_slices, u)
    return out


def _unknown(track: BodyTrack, horizon: HorizonResult) -> np.ndarray:
    """Azimut limitado por cobertura y disco dentro de la banda [H_lb, H_ub] (si no hay H_ub: H_lb < e+ρ)."""
    m = unknown_relevant_mask(horizon, track.az_deg, track.el_deg, track.radius_deg)
    if horizon.h_ub_deg is not None:
        m &= horizon_at(horizon, track.az_deg, "ub") > track.el_deg - track.radius_deg
    return m


def body_visibility(track: BodyTrack, horizon: HorizonResult, params: VisibilityParams) -> BodyVisibility:
    """f (H_lb), estado, unknown_relevant y f_pess (H_ub) de un cuerpo."""
    f = _fraction_blocks(track, horizon, "lb", params)
    f_pess = _fraction_blocks(track, horizon, "ub", params) if horizon.h_ub_deg is not None else None
    return BodyVisibility(track.body, f, classify(f, params.eps), _unknown(track, horizon), f_pess)


def visibility_series(sky: SkySeries, horizon: HorizonResult, params: VisibilityParams) -> VisibilitySeries:
    """f, estado, unknown_relevant y f_pess (H_ub) de Sol y Tierra; por bloques de 8192 instantes."""
    return VisibilitySeries(sky.et, body_visibility(sky.sun, horizon, params),
                            body_visibility(sky.earth, horizon, params), horizon.cache_key)


def link_fraction(track: BodyTrack, horizon: HorizonResult, params: VisibilityParams, margin_deg: float = 0.0,
                  kind: str = "lb") -> FloatArray:
    """Fracción del disco por encima de H(A) + ``margin_deg`` (margen de elevación de la antena del lander).

    Exacto: subir el horizonte un margen equivale a bajar la elevación del cuerpo ese margen (las rebanadas usan e − H).
    Con margen 0 es ``body_visibility(...).f``.
    """
    tr = track if not margin_deg else dataclasses.replace(track, el_deg=track.el_deg - margin_deg)
    return _fraction_blocks(tr, horizon, kind, params)


def make_fraction_fn(body: Body, lat_deg: float, lon_deg_e: float, height_m: float, horizon: HorizonResult,
                     params: VisibilityParams, kind: str = "lb",
                     margin_deg: float = 0.0) -> Callable[[FloatArray], FloatArray]:
    """f(et) vectorizado (SPICE + disc_fraction) para refinar eventos; ``kind='ub'`` da la variante pesimista;
    ``margin_deg`` eleva el horizonte (enlace con margen de elevación)."""
    def f_fn(et):
        tr = spice_engine.body_track(et, lat_deg, lon_deg_e, body, height_m)
        return link_fraction(tr, horizon, params, margin_deg, kind)
    return f_fn
