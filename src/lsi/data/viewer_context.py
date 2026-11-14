"""Terreno de CONTEXTO y suelo cercano para el visor 3D (solo geometría y sombras; sin UI).

* ``context_terrain``: el DEM polar LOLA de 80 m (``loader.load_far_field``) alrededor del recorte, en una malla de ≤ ``CTX_N`` × ``CTX_N``
  vértices (±20-25 km), con la iluminación calculada por ``shadows.illumination`` sobre el DEM de 80 m con su propio ``px`` y el
  Sol dado. Dentro del recorte las alturas son las del recorte y hasta ``FEATHER_M`` fuera se mezclan con él: sin costura.
* ``fine_patch``: parche de ≈ 700 m alrededor del observador a 2,5 m/celda, interpolando (bicúbica) las alturas NATIVAS de 5 m.
  No añade información: suaviza la retícula. El microrrelieve que se ve encima es solo sombreado procedural en el visor.

Todo es determinista y devuelve arrays NumPy; ``context_payload``/``patch_payload`` los cuantizan (uint16/uint8 en base64).
"""
from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import ndimage as ndi

CTX_N = 160                    # vértices por lado del contexto (≤ 160 × 160 = 25 600)
CTX_HALF_MIN, CTX_HALF_MAX = 20000.0, 25000.0
FEATHER_M = 2000.0             # mezcla de alturas fuera del recorte
PATCH_HALF_M, PATCH_PX_M = 350.0, 2.5
MAX_EXTRA_BYTES = 1_500_000    # cota del JSON del contexto + el parche
FAR_PX_M = 80.0


def _fill_nearest(a: np.ndarray) -> np.ndarray:
    ok = np.isfinite(a)
    if ok.all() or not ok.any():
        return a
    idx = ndi.distance_transform_edt(~ok, return_distances=False, return_indices=True)
    return a[idx[0], idx[1]]


def _smooth(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def context_half_m(crop_half_m: float) -> float:
    """Semilado del contexto: ≥ 20 km, ≈ 2,2 × el del recorte, ≤ 25 km."""
    return float(min(CTX_HALF_MAX, max(CTX_HALF_MIN, 2.2 * crop_half_m)))


def context_terrain(raw_dir, center_xy: tuple[float, float], half_m: float, crop: dict, sun: dict, *, n: int = CTX_N,
                    feather_m: float = FEATHER_M) -> Optional[dict]:
    """Malla de contexto (n × n, fila 0 = norte) o None si no hay campo lejano.

    ``crop``: heights (ny, nx), x0_m, y0_m, px_m del recorte dibujado (NaN = sin dato). ``sun``: az_deg, el_deg (el Sol visto desde
    el punto ``lat``, ``lon_deg_e``); se transforma al centro de la ventana con ``shadows.sun_seen_from``.
    Devuelve: heights float32, lit float32 [0, 1] (1 = Sol), x0_m/y0_m (vértice [0, 0]), step_m, half_m, sun_grid_az_deg, sun_el_deg.
    """
    from lsi.astronomy.coordinates import stereo_inverse
    from lsi.contracts import DemNotFoundError
    from lsi.data import loader
    from lsi.terrain import shadows
    cx, cy = float(center_xy[0]), float(center_xy[1])
    try:
        w = loader.load_far_field(Path(raw_dir), cx, cy, half_m + 2.0 * FAR_PX_M, margin_px=2)
    except DemNotFoundError:
        return None
    z80 = np.asarray(w.data, float)
    if not np.isfinite(z80).any():
        return None
    px = float(w.pixel_size_m)
    latc, lonc = (float(v) for v in stereo_inverse(w.x0_m + px * (z80.shape[1] // 2), w.y0_m - px * (z80.shape[0] // 2)))
    azc, elc = shadows.sun_seen_from(sun["az_deg"], sun["el_deg"], sun["lat"], sun["lon_deg_e"], latc, lonc)
    il80 = shadows.illumination(z80, px, azc, elc, origin_xy_m=(w.x0_m, w.y0_m))    # px = 80 m propio
    z80 = _fill_nearest(z80)
    il80 = np.nan_to_num(il80, nan=1.0)
    step = 2.0 * half_m / (n - 1)
    xs = cx - half_m + step * np.arange(n)
    ys = cy + half_m - step * np.arange(n)
    f = step / px
    sg = 0.5 * f if f > 1.5 else 0.0
    if sg:
        z80, il80 = ndi.gaussian_filter(z80, sg, mode="nearest"), ndi.gaussian_filter(il80, sg, mode="nearest")
    gx, gy = np.meshgrid(xs, ys)
    coords = np.stack([(w.y0_m - gy) / px, (gx - w.x0_m) / px])
    z = ndi.map_coordinates(z80, coords, order=1, mode="nearest")
    lit = np.clip(ndi.map_coordinates(il80, coords, order=1, mode="nearest"), 0.0, 1.0)
    # mezcla con el recorte: dentro, sus alturas; hasta feather_m fuera, una rampa suave de la diferencia en el borde
    ch = np.asarray(crop["heights"], float)
    cny, cnx = ch.shape
    cpx = float(crop["px_m"])
    xa, xb = float(crop["x0_m"]), float(crop["x0_m"]) + (cnx - 1) * cpx
    yb, ya = float(crop["y0_m"]) - (cny - 1) * cpx, float(crop["y0_m"])
    qx, qy = np.clip(gx, xa, xb), np.clip(gy, yb, ya)
    cs = ndi.map_coordinates(_fill_nearest(ch), np.stack([(crop["y0_m"] - qy) / cpx, (qx - crop["x0_m"]) / cpx]), order=1, mode="nearest")
    cok = ndi.map_coordinates(np.isfinite(ch).astype(float), np.stack([(crop["y0_m"] - qy) / cpx, (qx - crop["x0_m"]) / cpx]), order=1) > 0.999
    wgt = 1.0 - _smooth(np.hypot(gx - qx, gy - qy) / feather_m)
    z = z + np.where(cok, (cs - z) * wgt, 0.0)
    return dict(heights=z.astype(np.float32), lit=lit.astype(np.float32), x0_m=float(xs[0]), y0_m=float(ys[0]), step_m=float(step),
                half_m=float(half_m), sun_grid_az_deg=float((lonc + azc) % 360.0), sun_el_deg=float(elc), n=int(n))


def fine_patch(native: np.ndarray, x0_m: float, y0_m: float, px_m: float, obs_xy: tuple[float, float], *,
               half_m: float = PATCH_HALF_M, out_px_m: float = PATCH_PX_M) -> Optional[dict]:
    """Parche (n × n, n impar, centrado en el observador) a ``out_px_m`` desde alturas nativas ``native`` (fila 0 = norte, centro del
    píxel [0, 0] en (x0_m, y0_m)) con interpolación bicúbica (spline; recortada al rango local para que no rebase en los bordes).
    None si faltan datos (< 95 % de celdas finitas) o la ventana no cubre el parche."""
    z = np.asarray(native, float)
    ok = np.isfinite(z)
    if ok.sum() < 16:
        return None
    n = int(round(2.0 * half_m / out_px_m)) + 1
    n += 1 - n % 2
    ox, oy = float(obs_xy[0]), float(obs_xy[1])
    xs = ox + out_px_m * (np.arange(n) - n // 2)
    ys = oy - out_px_m * (np.arange(n) - n // 2)
    gx, gy = np.meshgrid(xs, ys)
    col, row = (gx - x0_m) / px_m, (y0_m - gy) / px_m
    inside = (col >= 0) & (col <= z.shape[1] - 1) & (row >= 0) & (row <= z.shape[0] - 1)
    zf = _fill_nearest(z)
    v = ndi.map_coordinates(zf, np.stack([row, col]), order=3, mode="nearest")
    good = ndi.map_coordinates(ok.astype(float), np.stack([row, col]), order=1, mode="nearest") > 0.999
    good &= inside
    if good.mean() < 0.95:
        return None
    lo, hi = float(zf[ok].min()), float(zf[ok].max())
    v = np.clip(v, lo, hi)
    v = np.where(good, v, np.nan)
    v = _fill_nearest(v)
    return dict(heights=v.astype(np.float32), x0_m=float(xs[0]), y0_m=float(ys[0]), step_m=float(out_px_m), half_m=float(half_m),
                n=int(n), native_px_m=float(px_m))


def _u16(a: np.ndarray) -> dict:
    lo, hi = float(np.min(a)), float(np.max(a))
    q = np.rint((a - lo) / max(hi - lo, 1e-6) * 65534.0).astype("<u2")
    return {"min": round(lo, 3), "max": round(hi, 3), "b64": base64.b64encode(q.tobytes()).decode("ascii")}


def context_payload(c: dict) -> dict:
    return {"n": c["n"], "x0_m": round(c["x0_m"], 2), "y0_m": round(c["y0_m"], 2), "step_m": round(c["step_m"], 3), "half_m": c["half_m"],
            "z": _u16(c["heights"]),
            "lit_b64": base64.b64encode(np.rint(np.clip(c["lit"], 0, 1) * 255).astype(np.uint8).tobytes()).decode("ascii"),
            "source": "LOLA 80 m (LDEM_80S_80MPP_ADJ), sin foto"}


def patch_payload(p: dict) -> dict:
    return {"n": p["n"], "x0_m": round(p["x0_m"], 3), "y0_m": round(p["y0_m"], 3), "step_m": p["step_m"], "half_m": p["half_m"],
            "native_px_m": p["native_px_m"], "z": _u16(p["heights"])}


def psr_nophoto_pct(x0_m: float, y0_m: float, px_m: float, shape: tuple[int, int], nophoto: np.ndarray) -> Optional[float]:
    """% de las celdas SIN foto que caen dentro de una PSR publicada (``data.psr``); None si no hay PSR o no hay celdas sin foto."""
    from lsi.data import psr
    if not nophoto.any() or not psr.psr_available():
        return None
    ny, nx = shape
    n = max(ny, nx)
    m = psr.psr_mask_window("viewer", x0_m + (n - 1) / 2.0 * px_m, y0_m - (n - 1) / 2.0 * px_m, n * px_m / 2.0, n)["data"][:ny, :nx]
    return 100.0 * float((m & nophoto).sum()) / float(nophoto.sum())
