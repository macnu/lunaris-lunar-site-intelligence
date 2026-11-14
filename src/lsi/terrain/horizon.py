"""Horizonte local con curvatura lunar EXACTA (matematica.md §2, arquitectura.md §5.5).

el(s) = atan2((R+z)·cosψ − (R+z0), (R+z)·sinψ), ψ = s/R. Se maximiza tan(el) y se hace UN arctan por azimut.
Muestra inválida (fuera del DEM o con vecino NaN) ⇒ −inf: nunca obstáculo falso ni cielo despejado falso.
Un azimut cuyo rayo sale del DEM / toca nodata antes de r_max queda ``limited`` y H_lb es COTA INFERIOR;
H_ub supone terreno a ``z_up`` en todo s ≥ r_cov (cota superior muy pesimista, diagnóstico).

Multirresolución (``far=``, DEM polar LOLA 80 m como campo lejano): en cada muestra se usa el DEM de 5 m si es
válido; si no, el de 80 m; solo si ninguno lo es la muestra es inválida (⇒ ``limited``). Paso radial: ``radial_step_m``
mientras algún rayo del bloque pueda estar aún en la ventana de 5 m; después ``far_step_m`` (por defecto ½ píxel
lejano = 40 m). Un máximo entre dos muestras de una superficie bilineal de celda p se pierde como mucho por
curvatura transversal (cuadrática en la celda): con paso p/2 el error de altura es ≤ ¼ del de paso p y a 20 km
1 m de altura ≈ 0.003°, ≪ el disco solar (0.53°). Sin ``far`` el comportamiento es el de siempre.
"""
from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Optional

import numpy as np

from lsi.contracts import (
    MOON_RADIUS_M as R, BoolArray, DemWindow, FloatArray, HorizonMode, HorizonParams, HorizonResult,
    NodataAtObserverError, ObserverPoint,
)
from lsi.data import cache
from lsi.terrain.sampling import sample_bilinear

_KIND = "horizons"


def smooth_sphere_horizon_deg(height_m: float) -> float:
    """−acos(R/(R+h)) en grados (esfera lisa)."""
    return -math.degrees(math.acos(R / (R + height_m)))


def _az_grid(step_deg: float) -> FloatArray:
    n = max(1, round(360.0 / step_deg))
    return np.arange(n) * (360.0 / n)


def smooth_sphere_result(observer: ObserverPoint, params: HorizonParams) -> HorizonResult:
    """Resultado con H ≡ H_esfera(h), r_cov=∞, limited=False (modo SMOOTH_SPHERE). H_ub = H_lb (nada desconocido)."""
    az = _az_grid(params.az_step_deg)
    hs = smooth_sphere_horizon_deg(params.observer_height_m)
    h = np.full(az.shape, hs + params.conservative_bias_deg)
    return HorizonResult(
        az_deg=az, h_lb_deg=h, r_cov_m=np.full(az.shape, np.inf), limited=np.zeros(az.shape, bool),
        mode=HorizonMode.SMOOTH_SPHERE, observer=observer, params=params, h_sphere_deg=hs,
        cache_key=cache.horizon_key(None, HorizonMode.SMOOTH_SPHERE, observer.x_m, observer.y_m, params),
        h_ub_deg=h.copy() if params.compute_upper_bound else None, dem_sha256=None,
        cov_min_m=float("inf"), cov_median_m=float("inf"))


def _ray_exit_m(window: DemWindow, x0: float, y0: float, dx: FloatArray, dy: FloatArray) -> FloatArray:
    """Distancia (m) a la que cada rayo sale del rectángulo de centros de píxel [0,W-1]x[0,H-1] (solo para recortar N)."""
    h, w = window.data.shape
    px = window.pixel_size_m
    c0, r0 = (x0 - window.x0_m) / px, (window.y0_m - y0) / px
    dc, dr = dx / px, -dy / px
    with np.errstate(divide="ignore", invalid="ignore"):
        tx = np.where(dc > 0, (w - 1 - c0) / dc, np.where(dc < 0, -c0 / dc, np.inf))
        ty = np.where(dr > 0, (h - 1 - r0) / dr, np.where(dr < 0, -r0 / dr, np.inf))
    return np.maximum(np.minimum(tx, ty), 0.0)


def _tan_el(s: FloatArray, z: FloatArray, z0: float) -> FloatArray:
    psi = s / R
    return ((R + z) * np.cos(psi) - (R + z0)) / ((R + z) * np.sin(psi))


def _upper_bound_tan(s_lo: FloatArray, s_hi: float, z_up: float, z0: float) -> FloatArray:
    """max_{s∈[s_lo,s_hi]} tan el con z=z_up. d/dψ ∝ (b/a)cosψ−1: decreciente si z_up≥z0; si no, máximo en ψ*=acos(a/b)."""
    a, b = R + z_up, R + z0
    cands = [_tan_el(s_lo, np.full_like(s_lo, z_up), z0), _tan_el(np.full_like(s_lo, s_hi), np.full_like(s_lo, z_up), z0)]
    if a < b:
        s_star = np.clip(R * math.acos(a / b), s_lo, s_hi)
        cands.append(_tan_el(s_star, np.full_like(s_lo, z_up), z0))
    return np.max(cands, axis=0)


def compute_horizon(window: DemWindow, observer: ObserverPoint, params: HorizonParams,
                    sigma_window: Optional[DemWindow] = None, sigma_sign: int = 0, k_sigma: float = 0.0,
                    cache_dir: Optional[Path] = None, far: Optional[DemWindow] = None,
                    far_step_m: Optional[float] = None, mode: HorizonMode = HorizonMode.DEM) -> HorizonResult:
    """Horizonte exacto con curvatura (H_lb, r_cov, limited, opcional H_ub); sigma_sign=±1 aplica z±k·σz (TOTERR).

    La altura del observador es ``params.observer_height_m`` (entra en la clave de caché). El suelo z0 se muestrea del
    DEM; si no hay dato válido en el punto, ``NodataAtObserverError``. El σ (z±k·σz) se aplica a muestras y a suelo del observador (error localmente correlado).

    ``far``: DEM lejano (p. ej. LOLA 80 m, ``loader.load_far_field``) usado donde ``window`` no tiene dato válido; si
    el observador no está en ``window`` el suelo z0 sale de ``far``. El σ solo corrige las muestras de ``window``.
    ``r_cov_m`` es el alcance combinado (primera muestra sin dato en ninguno de los dos DEM).
    ``mode``: etiqueta del resultado y de la clave de caché (``FAR_FIELD`` lo usa ``compute_horizon_far_field``).
    """
    use_sigma = sigma_sign != 0 and k_sigma != 0.0
    if use_sigma and sigma_window is None:
        raise ValueError("sigma_sign≠0 requiere sigma_window")
    sha = window.meta.sha256 if window.meta is not None else None
    key = cache.horizon_key(sha, mode, observer.x_m, observer.y_m, params)
    # La ventana recortada limita la cobertura: forma parte de la clave (sha es del fichero entero).
    ext = (window.x0_m, window.y0_m, window.pixel_size_m, *window.data.shape)
    sig = (sigma_window.meta.sha256 if sigma_window is not None and sigma_window.meta else None, sigma_sign, k_sigma) if use_sigma else None
    fsha = far.meta.sha256 if far is not None and far.meta is not None else None
    fstep = float(far_step_m if far_step_m is not None else far.pixel_size_m / 2.0) if far is not None else None
    if far is None:
        key = cache.digest(key, ext, sig)   # misma clave que antes de existir el campo lejano
    else:   # la clave incluye sha del campo lejano, su ventana (limita r_cov) y su paso
        key = cache.digest(key, ext, sig, ("far", fsha, far.x0_m, far.y0_m, far.pixel_size_m, *far.data.shape, fstep))
    cacheable = (cache_dir is not None and sha is not None and (not use_sigma or sig[0] is not None)
                 and (far is None or fsha is not None))
    hs = smooth_sphere_horizon_deg(params.observer_height_m)

    if cacheable:
        hit = cache.load_npz(cache_dir, _KIND, key)
        if hit is not None:
            return _build(hit, observer, params, hs, key, sha, fsha, mode)

    x0, y0 = observer.x_m, observer.y_m
    g0, ok0 = sample_bilinear(window, np.array([x0]), np.array([y0]))
    if not ok0[0] and far is not None:
        g0, ok0 = sample_bilinear(far, np.array([x0]), np.array([y0]))
    if not ok0[0]:
        raise NodataAtObserverError(f"Sin dato válido del DEM en ({x0:.1f}, {y0:.1f}) m ni en sus vecinos.")
    z0 = float(g0[0]) + params.observer_height_m
    if use_sigma:   # error vertical localmente correlado: el suelo del observador se desplaza igual que las muestras
        s0, oks0 = sample_bilinear(sigma_window, np.array([x0]), np.array([y0]))
        if not oks0[0]:
            raise NodataAtObserverError(f"Sin σz válido (TOTERR) en ({x0:.1f}, {y0:.1f}) m.")
        z0 += sigma_sign * k_sigma * float(s0[0])

    az = _az_grid(params.az_step_deg)
    dstep = params.radial_step_m
    k_min, k_max = max(1, math.ceil(params.r_min_m / dstep - 1e-9)), int(math.floor(params.r_max_m / dstep + 1e-9))
    nk = k_max - k_min + 1
    dxa, dya = _dir(observer, az)
    r_exit = _ray_exit_m(window, x0, y0, dxa, dya)
    z_up = params.z_up_m if params.z_up_m is not None else float(np.nanmax(window.data))
    if far is not None and params.z_up_m is None:
        z_up = max(z_up, float(np.nanmax(far.data)))

    h_lb = np.empty(az.shape)
    limited = np.empty(az.shape, bool)
    r_cov = np.empty(az.shape)
    r_top = k_max * dstep
    for a0 in range(0, len(az), max(1, int(params.block_azimuths))):
        sl = slice(a0, a0 + max(1, int(params.block_azimuths)))
        nb = int(min(nk, math.floor(r_exit[sl].max() / dstep) - k_min + 3))   # +2 de holgura; la validez manda
        nb = max(nb, 1)
        s = (k_min + np.arange(nb)) * dstep
        if far is not None and nb < nk:   # campo lejano: rejilla fina hasta salir de la ventana de 5 m y gruesa hasta r_max
            s_c = np.arange(s[-1] + fstep, r_top, fstep)
            s = np.concatenate([s, s_c, [r_top]]) if r_top > s[-1] else s
        xs, ys = x0 + s[None, :] * dxa[sl, None], y0 + s[None, :] * dya[sl, None]
        z, ok = sample_bilinear(window, xs, ys)
        if use_sigma:
            sg, oks = sample_bilinear(sigma_window, xs, ys)
            ok &= oks
            z = z + sigma_sign * k_sigma * np.where(oks, sg, 0.0)
        if far is not None:   # donde el 5 m no vale, el 80 m
            miss = ~ok
            if miss.any():
                zf, okf = sample_bilinear(far, xs[miss], ys[miss])
                z[miss], ok[miss] = zf, okf
        z = np.where(ok, z, 0.0)
        tn = np.where(ok, _tan_el(s[None, :], z, z0), -np.inf)
        tmax = tn.max(axis=1)
        h_lb[sl] = np.where(np.isneginf(tmax), np.nan, np.degrees(np.arctan(np.where(np.isneginf(tmax), 0.0, tmax))))  # un arctan por azimut
        bad = ~ok
        fb = np.where(bad.any(axis=1), bad.argmax(axis=1), len(s))  # primera inválida (len(s) = ninguna en lo muestreado)
        if far is None:
            fb = np.where(fb < nb, fb, np.where(nb < nk, nb, nk))   # recortado ⇒ más allá hay fuera de DEM
            lim = fb < nk
            limited[sl], r_cov[sl] = lim, np.where(lim, np.maximum(k_min + fb - 1, 0) * dstep, r_top)
        else:   # la rejilla llega a r_top: limitado = alguna muestra sin dato en ningún DEM
            lim = fb < len(s)
            s_ext = np.concatenate([[max(k_min - 1, 0) * dstep], s])
            limited[sl], r_cov[sl] = lim, np.where(lim, s_ext[np.minimum(fb, len(s))], r_top)

    # sin ninguna muestra válida: el suelo analítico (cota inferior honesta), nunca −90° ni cielo despejado
    h_lb = np.where(np.isnan(h_lb), hs, h_lb)
    arrays = {"az_deg": az, "h_lb_deg": h_lb + params.conservative_bias_deg, "r_cov_m": r_cov, "limited": limited}
    if params.compute_upper_bound:
        h_ub = arrays["h_lb_deg"].copy()
        if limited.any():
            s_lo = np.minimum(r_cov[limited] + dstep, params.r_max_m)
            tn = _upper_bound_tan(s_lo, params.r_max_m, z_up, z0)
            h_ub[limited] = np.maximum(h_ub[limited], np.degrees(np.arctan(tn)) + params.conservative_bias_deg)
        arrays["h_ub_deg"] = h_ub
    if cacheable:
        cache.save_npz(cache_dir, _KIND, key, arrays)
    return _build(arrays, observer, params, hs, key, sha, fsha, mode)


def compute_horizon_far_field(far: DemWindow, observer: ObserverPoint, params: HorizonParams,
                              cache_dir: Optional[Path] = None) -> HorizonResult:
    """Horizonte con el DEM polar de 80 m como ÚNICA fuente (puntos fuera de los recortes de 5 m). El suelo del observador sale
    del propio 80 m y el paso radial es ½ píxel (40 m): un paso de 5 m no añade información a un DEM de 80 m y multiplica el
    coste por 8. Es un horizonte APROXIMADO (80 m suaviza paredes de cráter; ver docs/validation/horizonte-campo-lejano.md);
    ``mode = FAR_FIELD`` y la clave de caché es distinta de la del modo DEM."""
    p = dataclasses.replace(params, radial_step_m=far.pixel_size_m / 2.0)
    h = compute_horizon(far, observer, p, cache_dir=cache_dir, mode=HorizonMode.FAR_FIELD)
    return dataclasses.replace(h, far_sha256=h.dem_sha256)


def _dir(observer: ObserverPoint, az: FloatArray) -> tuple[FloatArray, FloatArray]:
    from lsi.astronomy.coordinates import ray_direction
    return ray_direction(observer.lon_deg_e, az)


def _build(a, observer, params, hs, key, sha, far_sha=None, mode=HorizonMode.DEM) -> HorizonResult:
    r = np.asarray(a["r_cov_m"], float)
    return HorizonResult(
        az_deg=np.asarray(a["az_deg"], float), h_lb_deg=np.asarray(a["h_lb_deg"], float), r_cov_m=r,
        limited=np.asarray(a["limited"], bool), mode=mode, observer=observer, params=params,
        h_sphere_deg=hs, cache_key=key, h_ub_deg=np.asarray(a["h_ub_deg"], float) if "h_ub_deg" in a else None,
        dem_sha256=sha, cov_min_m=float(r.min()), cov_median_m=float(np.median(r)), far_sha256=far_sha)


def horizon_at(result: HorizonResult, az_deg: FloatArray, kind: str = "lb") -> FloatArray:
    """Interpolación lineal circular (periodo 360°) de H_lb ('lb') o H_ub ('ub')."""
    if kind == "lb":
        h = result.h_lb_deg
    elif kind == "ub":
        if result.h_ub_deg is None:
            raise ValueError("el resultado no tiene H_ub (compute_upper_bound=False)")
        h = result.h_ub_deg
    else:
        raise ValueError(f"kind debe ser 'lb' o 'ub', no {kind!r}")
    return np.interp(np.asarray(az_deg, float) % 360.0, result.az_deg, h, period=360.0)


def _limited_at(result: HorizonResult, az_deg: FloatArray) -> BoolArray:
    """Limitado si lo es cualquiera de los dos azimutes de rejilla vecinos (conservador)."""
    n = len(result.az_deg)
    f = (np.asarray(az_deg, float) % 360.0) / (360.0 / n)
    i0 = np.floor(f).astype(int) % n
    return result.limited[i0] | result.limited[(i0 + 1) % n]


def unknown_relevant_mask(result: HorizonResult, az_deg: FloatArray, el_deg: FloatArray,
                          radius_deg: FloatArray) -> BoolArray:
    """True si el azimut está limitado por cobertura y H_lb < el + radio (puede cambiar el resultado)."""
    return _limited_at(result, az_deg) & (horizon_at(result, az_deg) < np.asarray(el_deg, float) + radius_deg)


def limited_fraction(result: HorizonResult, e_max_deg: float, radius_deg: float) -> float:
    """Fracción de azimutes limitados con H_lb < e_max + ρ (alimenta G3 y 'horizonte limitado por cobertura')."""
    return float(np.mean(result.limited & (result.h_lb_deg < e_max_deg + radius_deg)))
