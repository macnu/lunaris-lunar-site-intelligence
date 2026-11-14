"""Sombras del relieve para un Sol dado: barrido del ángulo de horizonte máximo hacia el Sol. NumPy puro, sin UI.

Para cada celda se marcha hacia el Sol y se queda con el mayor ángulo de elevación del terreno visto desde ella (curvatura
lunar exacta, la misma fórmula que ``terrain.horizon``)::

    tan(h) = ((R + z)·cos ψ − (R + z0)) / ((R + z)·sin ψ),   ψ = s / R

La celda está en sombra si ``h`` ≥ elevación del Sol. El bucle es sobre los PASOS del rayo (≈ 100-200, espaciados cada
``max(px, 3 % de s)``), no sobre los píxeles: cada paso es una operación vectorizada sobre todo el recorte.

Dirección hacia el Sol (convenio del proyecto: azimut desde el Norte local hacia el Este, ``docs/science/convenciones.md``):

* Sin ``origin_xy_m``: ``sun_az_deg`` es un azimut de REJILLA (desde +y hacia +x del plano) y ``sun_el_deg`` la elevación,
  iguales para todas las celdas. Solo vale donde el «norte local» no gira dentro del recorte.
* Con ``origin_xy_m = (x0, y0)`` (centro del píxel [0, 0], como ``DemWindow``): az/el son los vistos en el CENTRO del recorte
  y cada celda recibe su azimut y elevación exactos. Se reconstruye el vector hacia el Sol en MOON_ME (base ENU del centro) y
  se proyecta en la base ENU de cada celda; la dirección del rayo en el plano es ``(sin(λ+A), cos(λ+A))``
  (``astronomy.coordinates.ray_direction``). Hace falta porque junto al polo el norte local gira con la longitud: a 10 km
  del polo (Shackleton) un único azimut se equivoca decenas de grados en el borde del recorte; a 122 km (Malapert), ≈ 5°.

Simplificaciones declaradas: distancia = metros del plano (la escala estereográfica k vale 1,000 en el polo y 1,001 a 85° S, ≪ 1 %);
no hay sombra de relieve que quede FUERA del recorte (los rayos que salen de él dejan de contar); el nodata (NaN) no
tapa nunca el Sol; el disco solar se trata con una rampa lineal en ``illumination`` (no es el área exacta del segmento).
"""
from __future__ import annotations

import numpy as np

from lsi.astronomy.coordinates import stereo_inverse

SUN_RADIUS_DEG = 0.267      # radio angular medio del Sol visto desde la Luna (≈ 1 UA); a verificar si importa la estación
_STEP_FRAC = 0.03           # paso radial relativo (por encima de 1 píxel): una cresta de ancho w se pierde como mucho si w < 3 % de s


def _sun_field(shape, px_m, az_deg, el_deg, origin_xy_m):
    """(dirección en índices de rejilla (dcol, drow) por celda, elevación del Sol por celda en rad)."""
    h, w = shape
    if origin_xy_m is None:
        g = np.radians(az_deg)
        return np.full(shape, np.sin(g)), np.full(shape, -np.cos(g)), np.full(shape, np.radians(el_deg))
    x0, y0 = origin_xy_m
    x = x0 + px_m * np.arange(w)[None, :] * np.ones((h, 1))
    y = y0 - px_m * np.arange(h)[:, None] * np.ones((1, w))
    lat, lon = (np.radians(a) for a in stereo_inverse(x, y))
    latc, lonc = (np.radians(a) for a in stereo_inverse(x[h // 2, w // 2], y[h // 2, w // 2]))

    def enu(la, lo):        # filas E, N, U en MOON_ME (misma base que astronomy.coordinates.enu_basis, vectorizada)
        sp, cp, sl, cl = np.sin(la), np.cos(la), np.sin(lo), np.cos(lo)
        z = np.zeros_like(sp)
        return (np.stack([-sl, cl, z], -1), np.stack([-sp * cl, -sp * sl, cp], -1), np.stack([cp * cl, cp * sl, sp], -1))

    a, e = np.radians(az_deg), np.radians(el_deg)
    Ec, Nc, Uc = (v for v in enu(np.float64(latc), np.float64(lonc)))
    s = np.sin(a) * np.cos(e) * Ec + np.cos(a) * np.cos(e) * Nc + np.sin(e) * Uc          # unitario hacia el Sol, MOON_ME
    E, N, U = enu(lat, lon)
    se, sn, su = E @ s, N @ s, U @ s
    grid_az = lon + np.arctan2(se, sn)                                                   # λ + A: azimut de rejilla
    return np.sin(grid_az), -np.cos(grid_az), np.arcsin(np.clip(su, -1.0, 1.0))


def _max_horizon_tan(z, px_m, dcol, drow, R, max_range_m):
    """tan del mayor ángulo de horizonte hacia el Sol por celda (−inf si ningún paso cae dentro del recorte)."""
    h, w = z.shape
    fin = np.isfinite(z)
    zf = np.where(fin, z, (np.nanmin(z) - 1000.0) if fin.any() else 0.0)       # nodata = foso, nunca obstáculo
    cc, rr = np.meshgrid(np.arange(w, dtype=float), np.arange(h, dtype=float))
    best = np.full(z.shape, -np.inf)
    s = px_m
    while s <= max_range_m:
        c, r = cc + dcol * (s / px_m), rr + drow * (s / px_m)
        ok = (c >= 0) & (c <= w - 1) & (r >= 0) & (r <= h - 1)
        if not ok.any():
            break
        c0 = np.clip(np.floor(np.where(ok, c, 0)), 0, max(w - 2, 0)).astype(np.intp)
        r0 = np.clip(np.floor(np.where(ok, r, 0)), 0, max(h - 2, 0)).astype(np.intp)
        fx, fy = np.where(ok, c, 0) - c0, np.where(ok, r, 0) - r0
        c1, r1 = np.minimum(c0 + 1, w - 1), np.minimum(r0 + 1, h - 1)
        zs = (zf[r0, c0] * (1 - fx) * (1 - fy) + zf[r0, c1] * fx * (1 - fy) + zf[r1, c0] * (1 - fx) * fy + zf[r1, c1] * fx * fy)
        psi = s / R
        t = ((R + zs) * np.cos(psi) - (R + zf)) / ((R + zs) * np.sin(psi))
        best = np.where(ok, np.maximum(best, t), best)
        s += max(px_m, _STEP_FRAC * s)
    return best


def _horizon_and_sun(dem_m, px_m, sun_az_deg, sun_el_deg, R, origin_xy_m, max_range_m):
    z = np.asarray(dem_m, dtype=float)
    dcol, drow, el = _sun_field(z.shape, float(px_m), float(sun_az_deg), float(sun_el_deg), origin_xy_m)
    rng = float(np.hypot(*z.shape) * px_m) if max_range_m is None else float(max_range_m)
    return z, np.degrees(np.arctan(_max_horizon_tan(z, float(px_m), dcol, drow, R, rng))), np.degrees(el)


def shadow_mask(dem_m, px_m, sun_az_deg, sun_el_deg, sphere_radius_m=1737400.0, *, origin_xy_m=None, max_range_m=None):
    """Máscara booleana ``True = en sombra`` (el centro del Sol queda bajo el horizonte de la celda). Misma forma que ``dem_m``.

    ``dem_m``: elevaciones (m) sobre la esfera de referencia, ``[fila, col]`` con y decreciente por fila (convención
    ``DemWindow``); NaN = sin dato (esa celda sale ``False``). ``px_m``: lado de celda en el plano (m). ``sun_az_deg``,
    ``sun_el_deg``: ver el docstring del módulo (con ``origin_xy_m`` son los del centro del recorte, azimut N→E).
    Sol por debajo del horizonte local (< 0°) ⇒ todo en sombra. ``max_range_m``: alcance del rayo (por defecto la diagonal).
    """
    z, h, el = _horizon_and_sun(dem_m, px_m, sun_az_deg, sun_el_deg, sphere_radius_m, origin_xy_m, max_range_m)
    return np.isfinite(z) & ((el < 0.0) | (h >= el))


def illumination(dem_m, px_m, sun_az_deg, sun_el_deg, sphere_radius_m=1737400.0, *, origin_xy_m=None, max_range_m=None):
    """Fracción iluminada [0, 1] por celda con penumbra: rampa lineal mientras el horizonte cruza el disco solar
    (± ``SUN_RADIUS_DEG`` alrededor de su centro). NaN donde no hay dato. ``True``/``False`` de ``shadow_mask`` ≈ 0,5 de esta."""
    z, h, el = _horizon_and_sun(dem_m, px_m, sun_az_deg, sun_el_deg, sphere_radius_m, origin_xy_m, max_range_m)
    f = np.clip((el - h) / (2.0 * SUN_RADIUS_DEG) + 0.5, 0.0, 1.0)
    f = np.where(el < -SUN_RADIUS_DEG, 0.0, f)
    return np.where(np.isfinite(z), f, np.nan)


def as_texture(illum_frac):
    """Fracción iluminada [0, 1] → uint8 0-255 (0 = sombra, 255 = pleno Sol), misma malla ``[fila, col]`` que el recorte, lista para
    exportar como textura (PNG de un canal o bytes crudos). Sin dato (NaN) → 255 (no se pinta sombra donde no se sabe)."""
    f = np.nan_to_num(np.asarray(illum_frac, dtype=float), nan=1.0)
    return np.rint(np.clip(f, 0.0, 1.0) * 255.0).astype(np.uint8)


def sun_seen_from(az_deg, el_deg, lat0_deg, lon0_deg_e, lat1_deg, lon1_deg_e):
    """(azimut N→E, elevación) del MISMO Sol visto desde (lat1, lon1) dado lo visto desde (lat0, lon0). Sol a distancia infinita:
    se reconstruye su dirección en MOON_ME con la base ENU del primer punto y se proyecta en la del segundo."""
    from lsi.astronomy.coordinates import enu_basis, vector_to_azel
    a, e = np.radians(az_deg), np.radians(el_deg)
    E, N, U = enu_basis(lat0_deg, lon0_deg_e)
    s = np.sin(a) * np.cos(e) * E + np.cos(a) * np.cos(e) * N + np.sin(e) * U
    az, el, _ = vector_to_azel(s[None, :], lat1_deg, lon1_deg_e)
    return float(az[0]), float(el[0])
