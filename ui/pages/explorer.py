"""Pantalla A «Explorador 3D» (arquitectura §11.2, RF-35): terreno real del DEM como MAPA TOPOGRÁFICO 2D (relieve sombreado,
curvas de nivel, nombres del gazetteer, escala y norte; selección por clic) y como superficie 3D iluminada, con la misma capa
(elevación, pendiente, incertidumbre, muestreo), marcadores de los sitios candidatos, panel de coordenadas y metadatos.

No calcula: pinta ``visualization.relief_map`` y ``visualization.terrain3d`` con recortes ligeros leídos (y cacheados) aquí;
el punto sale de ``ui.cache``. Los nombres se proyectan aquí (``data.gazetteer`` + ``astronomy.coordinates``).
Sin DEM en el punto (o «esfera lisa» forzada) NO se dibuja un 3D vacío: mapa global plano y aviso «sin datos de terreno».

Vista 3D principal: ``ui.terrain_viewer`` (three.js autocontenido): terreno SDEM/LOLA, foto LROC, sombras de ``shadows`` en el instante
del cursor y Sol/Tierra en su acimut/elevación reales. El 3D de Plotly queda como «Vista alternativa» (expander).
"""
from __future__ import annotations

import base64
import dataclasses
import re
from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from scipy.ndimage import zoom

from lsi.astronomy.coordinates import stereo_forward, stereo_inverse
from lsi.terrain import shadows
from lsi.contracts import (
    MOON_RADIUS_KM, DemLayer, DemNotFoundError, DemWindow, HorizonMode, Severity, StateKey as K,
)
from lsi.data import catalog, gazetteer, imagery, loader, sdem, viewer_context as VC
from lsi.visualization import terrain3d as T, theme
from lsi.visualization.relief_map import hillshade, relief_map_figure
from ui import cache, components as C, state as S, terrain_viewer as TV

MAX_PX = 400      # ≤ 400×400 puntos en 3D (el recorte de 3 km de radio sale a 15 m/celda); el cálculo científico usa el DEM completo
ILLUM_PX = 250    # las sombras se calculan en una rejilla ≤ 250² (≈ 30 m, la resolución efectiva del DEM) y se amplían a la malla del 3D
RADII = {"3 km": 3000.0, "6 km": 6000.0, "Todo el recorte (≈ 21 km)": None}
LAYERS = {"elevacion": "elevation", "pendiente": "slope", "incertidumbre": "uncertainty", "muestreo": "sampling",
          "iluminacion": "illumination"}
LAYER_LABEL = {"elevacion": "Elevación", "pendiente": "Pendiente", "incertidumbre": "Incertidumbre vertical (TOTERR)",
               "muestreo": "Calidad de muestreo (LDEC)", "iluminacion": "Iluminación (Sol y sombras)"}
_T = "_x_t"       # slider de fecha y hora de la capa Iluminación
VIEWER_H = 660    # alto del visor three.js (px)
CLICK_GRID = 80   # rejilla de puntos invisibles del mapa 2D (ver relief_map; Plotly no deja seleccionar un mapa de calor)
MAX_LABELS = 12   # nombres de gazetteer rotulados en el mapa 2D (los de mayor diámetro que no se solapen)
MIN_PHOTO_PCT = 30.0   # por debajo, el marcador por defecto de un sitio se cambia en el visor por su candidato (si éste tiene más foto)


# ------------------------------------------------------------------------------------------------ datos cacheados
@st.cache_data(max_entries=6, ttl=1800, show_spinner="Leyendo el recorte del terreno…")
def _terrain(dem_key: str, cx: float, cy: float, radius_m: Optional[float], max_px: int):
    """(DemWindow submuestreado, capas auxiliares del mismo tamaño). Promedio por bloques de ``terrain3d.downsample``.
    Lee solo la ventana pedida; un recorte entero de 4200 px² baja a ≤ 300² (celdas de 70 m)."""
    ctx = cache.get_context()
    ref = ctx.dem_refs[dem_key]
    bounds = None if radius_m is None else (cx - radius_m, cy - radius_m, cx + radius_m, cy + radius_m)
    base, extra, f = None, {}, 1
    for lyr, name in ((DemLayer.SURF, "elevation"), (DemLayer.TOTERR, "uncertainty"), (DemLayer.LDEC, "sampling")):
        try:
            w = loader.read_window(ref, lyr, bounds)
        except DemNotFoundError:
            if lyr is DemLayer.SURF:
                raise
            continue
        a, f = T.downsample(w.data, max_px)
        if lyr is DemLayer.SURF:
            base, z = w, a
        else:
            extra[name] = a
    off = (f - 1) / 2.0 * base.pixel_size_m          # el centro del bloque, como en terrain3d._axes
    win = DemWindow(z, base.x0_m + off, base.y0_m - off, base.pixel_size_m * f, DemLayer.SURF, base.meta)
    return win, {k: v for k, v in extra.items() if v.shape == z.shape}


@st.cache_data(max_entries=1, show_spinner=False)
def _far_meta():
    """Metadatos del campo lejano LOLA 80 m, o None si el GeoTIFF no está."""
    ref = loader.discover_far_field(Path(cache.get_context().root) / "data" / "raw")
    return loader.read_metadata(ref) if ref else None


def _body_at(res, track, utc) -> tuple[float, float, float, bool]:
    """(azimut N→E, elevación, radio angular °, dentro_del_periodo) de un cuerpo (``res.sky.sun`` / ``res.sky.earth``) en ``utc``: interpola
    linealmente la rejilla uniforme desde ``request.start_utc`` cada ``request.step_s``; el azimut se interpola desenrollado.
    Fuera del periodo devuelve el extremo más cercano y ``False``."""
    n = len(res.sky.et)
    pos = (utc - S.parse_utc(res.request.start_utc)).total_seconds() / float(res.request.step_s)
    inside = 0.0 <= pos <= n - 1
    pos = min(max(pos, 0.0), n - 1.0)
    i = np.arange(n)
    az = float(np.degrees(np.interp(pos, i, np.unwrap(np.radians(np.asarray(track.az_deg, float))))) % 360.0)
    return (az, float(np.interp(pos, i, np.asarray(track.el_deg, float))),
            float(np.interp(pos, i, np.asarray(getattr(track, "radius_deg", np.zeros(n)), float))), inside)


def sun_at(res, utc) -> tuple[float, float, bool]:
    """(azimut N→E, elevación, dentro_del_periodo) del Sol en el punto del análisis en el instante ``utc`` (datetime UTC)."""
    az, el, _, inside = _body_at(res, res.sky.sun, utc)
    return az, el, inside


def _illum_grid(win: DemWindow, lat: float, lon: float, az: float, el: float):
    """(fracción iluminada con la malla de ``win``, azimut de REJILLA y elevación del Sol en el centro del recorte).
    ``az``/``el``: el Sol visto desde (lat, lon). Sombras en una rejilla ≤ ILLUM_PX² y ampliadas (bilineal) a la de ``win``."""
    z, f = T.downsample(win.data, ILLUM_PX)
    px, off = win.pixel_size_m * f, (f - 1) / 2.0 * win.pixel_size_m
    h, w = z.shape
    x0, y0 = win.x0_m + off, win.y0_m - off
    latc, lonc = (float(v) for v in stereo_inverse(x0 + px * (w // 2), y0 - px * (h // 2)))
    azc, elc = shadows.sun_seen_from(az, el, lat, lon, latc, lonc)
    frac = shadows.illumination(z, px, azc, elc, origin_xy_m=(x0, y0))
    frac = np.clip(zoom(np.nan_to_num(frac, nan=1.0), (win.data.shape[0] / h, win.data.shape[1] / w), order=1), 0.0, 1.0)
    lat_w, lon_w = (float(v) for v in stereo_inverse(win.x0_m + win.pixel_size_m * (win.data.shape[1] // 2),
                                                     win.y0_m - win.pixel_size_m * (win.data.shape[0] // 2)))
    az_w, el_w = shadows.sun_seen_from(az, el, lat, lon, lat_w, lon_w)
    return np.where(np.isfinite(win.data), frac, np.nan), (lon_w + az_w) % 360.0, el_w


@st.cache_data(max_entries=24, ttl=1800, show_spinner=False)
def _illumination(dem_key: str, cx: float, cy: float, radius_m: Optional[float], max_px: int, lat: float, lon: float,
                  az: float, el: float):
    """Iluminación del recorte cacheada por (recorte, punto, az, el) con az/el ya redondeados a 0,05°: (fracción, az de rejilla, el)."""
    win, _ = _terrain(dem_key, cx, cy, radius_m, max_px)
    return _illum_grid(win, lat, lon, az, el)


@st.cache_data(max_entries=4, ttl=1800, show_spinner="Preparando el terreno del visor 3D…")
def _viewer_grid(dem_key: str, cx: float, cy: float, radius_m: Optional[float]) -> dict:
    """Malla del visor (≤ ``TV.MAX_SIDE`` por lado) con la foto alineada: SDEM de 5 m + ortomosaico (Site23, Site11; el hueco del
    ortomosaico se rellena con el mosaico NAC si lo hay) o, si no hay SDEM, relieve LOLA + mosaico NAC de 1 m (Site04).
    Misma extensión que el recorte del resto de la página. Claves: win (DemWindow), photo/valid (uint8/bool o None), source, native_px_m."""
    lo, _ = _terrain(dem_key, cx, cy, radius_m, MAX_PX)
    ny0, nx0 = lo.data.shape
    half = max(nx0, ny0) * lo.pixel_size_m / 2.0
    cxw, cyw = lo.x0_m + (nx0 - 1) / 2.0 * lo.pixel_size_m, lo.y0_m - (ny0 - 1) / 2.0 * lo.pixel_size_m
    pack = sdem.terrain_texture_pack(dem_key, cxw, cyw, half, TV.MAX_SIDE)
    if pack is not None:
        win = DemWindow(pack["heights"].astype(float), pack["x0_m"], pack["y0_m"], pack["px_m"], DemLayer.SURF, lo.meta)
        comb = imagery.combine_with_sdem(dem_key, pack)
        if comb is not None:
            src = comb["texture_source"]
            kind = "mixed" if ((src == 1).any() and (src == 2).any()) else ("nac" if (src == 2).any() else "sdem")
            return dict(win=win, photo=comb["texture"], valid=comb["texture_valid"], source=kind,
                        native_px_m=1.0 if kind == "nac" else sdem.NATIVE_PX_M)
        return dict(win=win, photo=pack["ortho"], valid=pack["texture_valid"], source="sdem", native_px_m=sdem.NATIVE_PX_M)
    win, _ = _terrain(dem_key, cx, cy, radius_m, TV.MAX_SIDE)
    ny, nx = win.data.shape
    im = imagery.imagery_on_grid(dem_key, win.x0_m, win.y0_m, win.pixel_size_m, ny, nx)
    if im is None:
        return dict(win=win, photo=None, valid=None, source="none", native_px_m=imagery.NATIVE_PX_M)
    return dict(win=win, photo=im["image"], valid=im["coverage"], source="nac", native_px_m=imagery.NATIVE_PX_M)


@st.cache_data(max_entries=12, ttl=1800, show_spinner="Calculando las sombras del visor 3D…")
def _viewer_illum(dem_key: str, cx: float, cy: float, radius_m: Optional[float], lat: float, lon: float, az: float, el: float):
    """Iluminación sobre la malla del visor (las sombras salen de ``shadows.illumination`` con el MISMO relieve que se dibuja)."""
    return _illum_grid(_viewer_grid(dem_key, cx, cy, radius_m)["win"], lat, lon, az, el)


@st.cache_data(max_entries=12, ttl=1800, show_spinner="Calculando el terreno lejano del visor 3D (DEM de 80 m)…")
def _viewer_context(dem_key: str, cx: float, cy: float, radius_m: Optional[float], lat: float, lon: float, az: float, el: float):
    """Terreno de contexto LOLA 80 m (±20-25 km) con sus sombras para el Sol dado; None si no está el campo lejano (ver ``viewer_context``)."""
    win = _viewer_grid(dem_key, cx, cy, radius_m)["win"]
    ny, nx = win.data.shape
    cxw, cyw = win.x0_m + (nx - 1) / 2.0 * win.pixel_size_m, win.y0_m - (ny - 1) / 2.0 * win.pixel_size_m
    half = VC.context_half_m(max(nx, ny) * win.pixel_size_m / 2.0)
    return VC.context_terrain(Path(cache.get_context().root) / "data" / "raw", (cxw, cyw), half,
                              dict(heights=win.data, x0_m=win.x0_m, y0_m=win.y0_m, px_m=win.pixel_size_m),
                              dict(az_deg=az, el_deg=el, lat=lat, lon_deg_e=lon))


@st.cache_data(max_entries=8, ttl=1800, show_spinner=False)
def _fine_patch(dem_key: str, ox: float, oy: float):
    """Parche de ≈ 700 m alrededor del observador a 2,5 m (bicúbica sobre las alturas NATIVAS de 5 m: SDEM si el sitio lo tiene, si no LDEM)."""
    half = VC.PATCH_HALF_M + 40.0
    pack = sdem.terrain_texture_pack(dem_key, ox, oy, half, 400)           # 2·390 m / 5 m = 156 ≤ 400: retícula nativa exacta
    if pack is not None:
        z, x0, y0, px = pack["heights"].astype(float), pack["x0_m"], pack["y0_m"], pack["px_m"]
    else:
        w = loader.read_window(cache.get_context().dem_refs[dem_key], DemLayer.SURF, (ox - half, oy - half, ox + half, oy + half), margin_px=2)
        z, x0, y0, px = np.asarray(w.data, float), w.x0_m, w.y0_m, w.pixel_size_m
    return VC.fine_patch(z, x0, y0, px, (ox, oy))


def photo_pct(g: dict) -> float:
    """% del recorte (celdas con altura) que tiene foto, de ``_viewer_grid``."""
    ok = np.isfinite(g["win"].data)
    if g["valid"] is None or not ok.any():
        return 0.0
    return 100.0 * float((np.asarray(g["valid"], bool) & ok).sum()) / float(ok.sum())


def _crop_center(obs, radius_m: Optional[float]) -> tuple[float, float]:
    return (0.0, 0.0) if radius_m is None else (round(obs.x_m / 500.0) * 500.0, round(obs.y_m / 500.0) * 500.0)


def viewer_scene(obs, res, cur, dem_key: str, cx: float, cy: float, radius_m: Optional[float], labels, exag0: float = 1.5) -> dict:
    """Escena del visor three.js para el instante ``cur`` (UTC): terreno + foto + sombras + Sol y Tierra reales (ver ``ui.terrain_viewer``)."""
    g = _viewer_grid(dem_key, cx, cy, radius_m)
    win = g["win"]
    az, el, rs, _ = _body_at(res, res.sky.sun, cur)
    az_e, el_e, re_, _ = _body_at(res, res.sky.earth, cur)
    frac, g_az, el_c = _viewer_illum(dem_key, cx, cy, radius_m, round(obs.lat_deg, 4), round(obs.lon_deg_e, 4),
                                     round(az / 0.05) * 0.05, round(el / 0.05) * 0.05)
    fin = np.isfinite(frac)
    hz = res.horizon
    h_el = np.where(np.isfinite(hz.h_lb_deg), hz.h_lb_deg, -5.0)
    az_r, el_r = round(az / 0.05) * 0.05, round(el / 0.05) * 0.05
    ctx_t = _viewer_context(dem_key, cx, cy, radius_m, round(obs.lat_deg, 4), round(obs.lon_deg_e, 4), az_r, el_r)
    patch = _fine_patch(dem_key, round(obs.x_m * 2) / 2, round(obs.y_m * 2) / 2)
    nophoto = fin & ~(np.zeros(frac.shape, bool) if g["valid"] is None else np.asarray(g["valid"], bool))
    psr_pct = VC.psr_nophoto_pct(win.x0_m, win.y0_m, win.pixel_size_m, win.data.shape, nophoto)
    return TV.build_scene(
        heights=win.data, x0_m=win.x0_m, y0_m=win.y0_m, px_m=win.pixel_size_m, illum=frac, photo=g["photo"], photo_valid=g["valid"],
        photo_source=g["source"], photo_native_px_m=g["native_px_m"],
        obs=dict(x=obs.x_m, y=obs.y_m, lat=obs.lat_deg, lon=obs.lon_deg_e, h=obs.height_m, z=obs.ground_z_m,
                 label=obs.label.split(" [")[0], north_deg=_north_deg(obs)),
        sun=dict(az_deg=az, el_deg=el, grid_az_deg=g_az, el_c_deg=el_c, radius_deg=rs),
        earth=dict(az_deg=az_e, el_deg=el_e, radius_deg=re_), horizon_az=np.asarray(hz.az_deg, float), horizon_el=h_el,
        names=labels, when_utc=f"{cur:%Y-%m-%d %H:%M}", lit_pct=100.0 * float(np.mean(frac[fin])) if fin.any() else 0.0, exag0=exag0,
        context=ctx_t, patch=patch, psr_pct=psr_pct)


def lighting_payload(win: DemWindow, lat: float, lon: float, sun_az_deg: float, sun_el_deg: float) -> dict:
    """Resultado serializable para un visor externo (p. ej. three.js) de un recorte ``win`` (sin recalcular en el visor).

    ``sun_az_deg``/``sun_el_deg``: el Sol visto desde (``lat``, ``lon``) (p. ej. ``sun_at``). Devuelve un dict JSON con:
    ``shape`` [filas, columnas]; ``x0_m``, ``y0_m``, ``pixel_m`` (centro del píxel [0, 0]; y decrece por fila); ``sun``
    {``az_deg`` N→E y ``el_deg`` en el centro del recorte, ``grid_az_deg`` azimut de rejilla λ+A}; ``hillshade_u8`` y
    ``shadow_u8`` (base64 de bytes uint8 ``[fila, col]`` en orden de filas; hillshade 0-255 con el Sol dado; sombra 0 = sombra,
    255 = pleno Sol, penumbra intermedia); ``shadow_pct`` (% iluminado de las celdas con dato, 0-100)."""
    frac, g_az, el = _illum_grid(win, lat, lon, sun_az_deg, sun_el_deg)
    hs = hillshade(win.data, win.pixel_size_m, g_az, el, 2.0)
    u8 = lambda a: base64.b64encode(np.ascontiguousarray(a, dtype=np.uint8).tobytes()).decode("ascii")   # noqa: E731
    latc, lonc = (float(v) for v in stereo_inverse(win.x0_m + win.pixel_size_m * (win.data.shape[1] // 2),
                                                   win.y0_m - win.pixel_size_m * (win.data.shape[0] // 2)))
    az_c, el_c = shadows.sun_seen_from(sun_az_deg, sun_el_deg, lat, lon, latc, lonc)
    fin = np.isfinite(frac)
    return {"shape": list(win.data.shape), "x0_m": float(win.x0_m), "y0_m": float(win.y0_m), "pixel_m": float(win.pixel_size_m),
            "sun": {"az_deg": az_c, "el_deg": el_c, "grid_az_deg": g_az},
            "hillshade_u8": u8(np.rint(np.nan_to_num(hs, nan=0.5) * 255)), "shadow_u8": u8(shadows.as_texture(frac)),
            "shadow_pct": float(100.0 * np.mean(frac[fin])) if fin.any() else float("nan")}


def _marker_key(site_id: str) -> str:
    return f"_x_marker_{site_id}"


def _toggle_marker(site_id: str) -> None:
    st.session_state[_marker_key(site_id)] = not st.session_state.get(_marker_key(site_id), False)


def candidate_request(ctx, req, obs, radius_m: Optional[float]):
    """Si el punto activo es el MARCADOR de un sitio curado y su recorte tiene < ``MIN_PHOTO_PCT`` % de foto, busca el CANDIDATO del
    sitio (``pipeline.snap_candidate`` con ``prefer='best'``, vía ``cache.get_snap``, como la comparativa). Devuelve
    ``(petición_del_candidato, % foto del marcador, % foto del candidato, puesto)`` o ``None`` si no procede (punto propio, ya hay foto, no hay
    candidato o el candidato no tiene más foto que el marcador)."""
    if S.get_str(S.ORIGIN) != "site" or not obs.site_id or obs.mode is not HorizonMode.DEM:
        return None
    try:
        p0 = photo_pct(_viewer_grid(obs.dem_key, *_crop_center(obs, radius_m), radius_m))
        if p0 >= MIN_PHOTO_PCT:
            return None
        cand = cache.get_snap(req.lat_deg, req.lon_deg_e, obs.site_id, "best", req.score_profile_id, req.mission_days)
        if cand is None or cand.kind != "best":
            return None
        pick = None                      # el mejor puesto del TOP del mapa de idoneidad cuyo recorte sí tiene foto
        for e in sorted(cand.ranking, key=lambda r: r.rank):
            x, y = (float(v) for v in stereo_forward(e.lat_deg, e.lon_deg_e))
            if np.hypot(x - obs.x_m, y - obs.y_m) < 150.0:
                continue
            p1 = photo_pct(_viewer_grid(cand.dem_key, *_crop_center(dataclasses.replace(obs, x_m=x, y_m=y), radius_m), radius_m))
            if p1 >= MIN_PHOTO_PCT:
                pick = (e, p1)
                break
    except (DemNotFoundError, KeyError, ValueError):
        return None
    if pick is None:
        return None
    return dataclasses.replace(req, lat_deg=float(pick[0].lat_deg), lon_deg_e=float(pick[0].lon_deg_e)), p0, pick[1], int(pick[0].rank)


def _plain_snap(obs) -> str:
    """Frase llana del ajuste del punto al mapa (sin jerga): «mejor punto dentro del cráter, a 0,12 km del centro»."""
    d = obs.snap_distance_km
    if d is None:
        return ""
    km = C.fmt_num(d, 2, "km")
    what = "cráter" if re.search(r"crater|cráter|rim", str(obs.label), re.I) else "lugar elegido"
    if obs.snap_kind == "best":
        return (f"mejor punto dentro del {what}, a {km} del centro" if obs.snap_inside_feature
                else f"mejor punto del mapa de alturas, a {km} del punto pedido")
    return f"punto del mapa más cercano, a {km} del pedido"


# ------------------------------------------------------------------------------------------------ callbacks
def _candidate_notice(site_id: str, using_marker: bool, p0: float, p1: float, rank: int) -> None:
    """Aviso del cambio de punto (o de que se mantiene el marcador) con el botón para alternar."""
    if using_marker:
        st.info(f"**Estás viendo el marcador del sitio**, donde solo el {C.fmt_num(p0, 0)} % del recorte tiene foto. "
                f"Su candidato (puesto {rank} del mapa de idoneidad) tiene un {C.fmt_num(p1, 0)} %.", icon=":material/photo_camera:")
        st.button("Ver el candidato del sitio", key="_x_cand_btn", on_click=_toggle_marker, args=(site_id,), icon=":material/pin_drop:")
    else:
        st.info(f"**Punto cambiado en este visor.** El marcador del sitio cae donde la cámara LROC NAC apenas llega: solo el "
                f"{C.fmt_num(p0, 0)} % de su recorte tiene foto (el resto es sombra permanente o queda fuera del mosaico). Se muestra el "
                f"**candidato del sitio** (el mejor puesto del TOP del mapa de idoneidad que sí tiene foto: el nº {rank}), con un {C.fmt_num(p1, 0)} % de foto. Un candidato no es una certificación.",
                icon=":material/swap_horiz:")
        st.button("Volver al marcador del sitio", key="_x_cand_btn", on_click=_toggle_marker, args=(site_id,), icon=":material/undo:")


def _set_layer() -> None:
    S.set_state(K.LAYER, st.session_state["_x_layer"])


def _set_height() -> None:
    S.set_state(K.OBS_HEIGHT, float(st.session_state["_x_height"]))


def _go_site(site_id: str) -> None:
    S.set_site(site_id, cache.get_context())


def point_from_selection(sel) -> Optional[tuple[float, float]]:
    """(lat, lon_E) del primer punto de una selección de Plotly (x, y estereográficas en m), o None."""
    try:
        p = sel["selection"]["points"][0]
        lat, lon = stereo_inverse(float(p["x"]), float(p["y"]))
        return float(lat), float(lon)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _set_cursor() -> None:
    S.set_state(K.CURSOR_UTC, S.fmt_utc(st.session_state[_T]))


def _on_map_select() -> None:
    pt = point_from_selection(st.session_state.get("_x_map"))
    if pt:
        S.set_point(*pt)


# ------------------------------------------------------------------------------------------------ figuras auxiliares
def _z_at(win: DemWindow, x: float, y: float) -> Optional[float]:
    c = int(round((x - win.x0_m) / win.pixel_size_m))
    r = int(round((win.y0_m - y) / win.pixel_size_m))
    if 0 <= r < win.data.shape[0] and 0 <= c < win.data.shape[1] and np.isfinite(win.data[r, c]):
        return float(win.data[r, c])
    return None


def _site_markers(ctx, win: DemWindow) -> list[tuple[str, float, float, Optional[float]]]:
    """Sitios candidatos con DEM cuyo marcador cae dentro del recorte: (etiqueta, x, y, z). Si las coordenadas curadas
    quedan fuera de su GeoTIFF (Site04/Site11) se usa el centro del recorte (``dem_default_observers``)."""
    ny, nx = win.data.shape
    xs, ys = (win.x0_m, win.x0_m + (nx - 1) * win.pixel_size_m), (win.y0_m - (ny - 1) * win.pixel_size_m, win.y0_m)
    out = []
    for s in ctx.sites:
        if not (s.has_dem and s.lat_deg is not None and s.lon_deg_e is not None and s.dem_prefix in ctx.dem_refs):
            continue
        x, y = (float(v) for v in stereo_forward(s.lat_deg, s.lon_deg_e))
        x0, y0, x1, y1 = ctx.dem_refs[s.dem_prefix].bounds_xy_m
        label = s.name
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            d = catalog.default_observer(ctx.cfg, s.dem_prefix)
            if d is None:
                continue
            x, y = (float(v) for v in stereo_forward(*d))
            label += " (centro del recorte)"
        if xs[0] <= x <= xs[1] and ys[0] <= y <= ys[1]:
            out.append((label, x, y, _z_at(win, x, y)))
    return out


def _relief_stats(win: DemWindow) -> tuple[float, float, float, float]:
    """(ancho_m, alto_m, z_min, z_max) del recorte mostrado."""
    ny, nx = win.data.shape
    z = win.data[np.isfinite(win.data)]
    return nx * win.pixel_size_m, ny * win.pixel_size_m, float(z.min()), float(z.max())


def _north_deg(obs) -> float:
    """Giro del norte local respecto al +y del plano (° horarios): en el plano polar el norte es radial, hacia fuera del polo."""
    return float(np.degrees(np.arctan2(obs.x_m, obs.y_m)))


def named_features(win: DemWindow, df, max_n: int = MAX_LABELS):
    """Rasgos con nombre del gazetteer dentro del recorte: [(nombre, x, y, tipo, diámetro_km)]. Prioriza por diámetro y
    descarta los que se solaparían con uno ya elegido (caja de ≈ 16 % × 6 % del recorte). Sin gazetteer, lista vacía."""
    if df is None or df.empty:
        return []
    ny, nx = win.data.shape
    px = win.pixel_size_m
    xlo, xhi = win.x0_m - px / 2, win.x0_m + (nx - 0.5) * px
    ylo, yhi = win.y0_m - (ny - 0.5) * px, win.y0_m + px / 2
    d = df[(df["lat_deg"] < 0) & (df["feature_type"] != gazetteer.SITE_TYPE)]
    x, y = stereo_forward(d["lat_deg"].to_numpy(float), d["lon_deg_e"].to_numpy(float))
    m = (x >= xlo) & (x <= xhi) & (y >= ylo) & (y <= yhi)
    d, x, y = d[m], x[m], y[m]
    diam = d["diameter_km"].fillna(0.0).to_numpy(float)
    out = []
    for i in np.argsort(-diam, kind="stable"):
        if len(out) >= max_n:
            break
        if all(abs(x[i] - o[1]) > 0.16 * (xhi - xlo) or abs(y[i] - o[2]) > 0.06 * (yhi - ylo) for o in out):
            out.append((str(d["name"].iloc[i]), float(x[i]), float(y[i]), str(d["feature_type"].iloc[i]),
                        float(diam[i]) if diam[i] > 0 else None))
    return out


def _fig_3d(win, extra, obs, layer_key, exag, markers, labels=(), sun=None):
    return T.terrain_surface_3d(win, obs, extra, layer=LAYERS[layer_key], max_px=MAX_PX, z_exaggeration=exag, buttons=False,
                                markers=markers, north_deg=_north_deg(obs), labels=labels, illumination=None if sun is None else sun[0],
                                sun_az_deg=315.0 if sun is None else sun[1], sun_el_deg=14.0 if sun is None else sun[2],
                                observer_label=obs.label.split(" [")[0])


def _fig_relief(win, extra, obs, layer_key, cands, labels, sun=None):
    return relief_map_figure(win, obs, layer=LAYERS[layer_key], layers=extra, candidates=[(m[0], m[1], m[2]) for m in cands], labels=labels,
                             north_deg=_north_deg(obs), selectable=True, illumination=None if sun is None else sun[0],
                             sun_azimuth_deg=315.0 if sun is None else sun[1], sun_elevation_deg=6.0 if sun is None else sun[2],
                             observer_subtitle=_plain_snap(obs) if C.show_for("planificador") else "")


def _fig_globe(ctx, obs):
    """Mapa global plano (lat/lon) sin relieve: sitios del catálogo, punto de observación y el límite de 80° S del campo lejano."""
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, x1=360, y0=-90, y1=-80, fillcolor=theme.GRID, opacity=0.5, line_width=0, layer="below")
    pts = [s for s in ctx.sites if s.lat_deg is not None and s.lon_deg_e is not None]
    fig.add_trace(go.Scatter(x=[s.lon_deg_e % 360 for s in pts], y=[s.lat_deg for s in pts], mode="markers+text",
                             text=[s.name for s in pts], textfont=dict(color=theme.TEXT, size=10),
                             # posiciones alternas para que las etiquetas cercanas (Apolo 12/14, Site23…) no se pisen
                             textposition=[("top center", "bottom center", "middle right", "middle left")[i % 4] for i in range(len(pts))],
                             marker=dict(size=9, symbol=["square" if s.has_dem else "circle" for s in pts], color=theme.EARTH,
                                         line=dict(color="#000", width=1)), name="Sitios del catálogo"))
    fig.add_trace(go.Scatter(x=[obs.lon_deg_e], y=[obs.lat_deg], mode="markers+text", text=["Punto de observación"],
                             textposition="bottom center", textfont=dict(color=theme.TEXT),
                             marker=dict(size=14, symbol="diamond", color=theme.SUN, line=dict(color="#000", width=1.5)),
                             name="Punto de observación"))
    fig.add_annotation(text="Sin recorte de 5 m: solo relieve aproximado (80 m)" if obs.mode is HorizonMode.FAR_FIELD
                       else "Sin datos de terreno: esfera lisa", xref="paper", yref="paper", x=0.5, y=0.97, showarrow=False,
                       font=dict(color=theme.WARN, size=14), bgcolor=theme.PANEL)
    fig.update_xaxes(title="Longitud (°E)", range=[0, 360], dtick=30)
    fig.update_yaxes(title="Latitud (°)", range=[-90, 90], dtick=30)
    return theme.apply_theme(fig, "Luna: mapa global (sin relieve)", height=480,
                             note="Banda gris: al sur de 80° S existe el campo lejano LOLA de 80 m. Cuadrados: sitios con DEM de 5 m.")


# ------------------------------------------------------------------------------------------------ paneles de texto
def _crs_name(wkt: str) -> str:
    m = re.search(r'(?:PROJCS|PROJCRS)\["([^"]+)"', wkt)
    return m.group(1) if m else "ver WKT"


def _meta_table(meta, *, far: bool) -> None:
    px = meta.pixel_size_m
    rows = [("Fuente", "NASA PGDA (LOLA, polo sur; GeoTIFF ajustado)" if not far else
             "NASA PGDA (LOLA, polo sur 80° S–90° S; LDEM_80S_80MPP_ADJ)"),
            ("Resolución nominal", f"{C.fmt_num(px, 0)} m/píxel"),
            ("Tamaño", f"{meta.width_px} × {meta.height_px} px ≈ {C.fmt_num(meta.width_px * px / 1000, 1)} × "
                       f"{C.fmt_num(meta.height_px * px / 1000, 1)} km"),
            ("CRS", _crs_name(meta.crs_wkt)),
            ("Referencia", f"esfera de {MOON_RADIUS_KM:g} km; píxel centrado" if meta.registration == "area" else meta.registration),
            ("Tipo / nodata", f"{meta.dtype} / {meta.nodata if meta.nodata is not None else 'ninguno'}")]
    if not far:
        rows.insert(2, ("Resolución efectiva", f"≈ {C.fmt_num(meta.effective_resolution_m, 0)} m (interpolación: el 90–92 % de los "
                                               "píxeles no tiene retorno LOLA; heurística LSI, a verificar)"))
    rows.append(("SHA-256", meta.sha256))
    st.dataframe(pd.DataFrame(rows, columns=["Campo", "Valor"]), hide_index=True, width="stretch")
    if S.is_expert():
        with st.expander("CRS completo (WKT) y límites"):
            st.code(meta.crs_wkt, language="text")
            st.caption("Límites x/y (m): " + ", ".join(C.fmt_num(b, 1) for b in meta.bounds_xy_m))


def _point_panel(obs) -> None:
    c = st.columns(3)
    with c[0]:
        C.metric_card("Latitud", f"{C.fmt_num(obs.lat_deg, 4)}°")
        C.metric_card("Longitud", f"{C.fmt_num(obs.lon_deg_e, 4)}°E")
    with c[1]:
        C.metric_card("x estereográfica", f"{C.fmt_num(obs.x_m, 1)} m", help="Plano estereográfico polar sur (R = 1737,4 km).")
        C.metric_card("y estereográfica", f"{C.fmt_num(obs.y_m, 1)} m")
    with c[2]:
        C.metric_card("Altura del suelo", C.fmt_num(obs.ground_z_m, 1, "m") if obs.ground_z_m is not None else "—",
                      help="Sobre la esfera de referencia; «—» = sin dato (nunca 0).")
        C.metric_card("Altura del observador", f"{C.fmt_num(obs.height_m, 1)} m", help="Sobre el suelo (mástil o antena).")


# ------------------------------------------------------------------------------------------------ página
def main() -> None:
    ctx = cache.get_context()
    C.warnings_band()
    st.title("Explorador 3D")
    req = S.request_or_stop()
    obs, warns, err = cache.get_observer(req)
    if err or obs is None:
        C.show_error(err or "No se pudo resolver el punto.")
        st.stop()
        return
    cand_note = None
    swap = candidate_request(ctx, req, obs, RADII[st.session_state.get("_x_radius", "3 km")])
    if swap is not None:
        sid, using_marker = obs.site_id, st.session_state.get(_marker_key(obs.site_id), False)
        cand_note = (sid, using_marker, swap[1], swap[2], swap[3])
        if not using_marker:
            o2, w2, e2 = cache.get_observer(swap[0])
            if o2 is not None and not e2:
                req, obs, warns = swap[0], o2, w2
            else:
                cand_note = None
    for w in warns:
        if w.severity is not Severity.INFO:
            st.warning(w.text_es, icon=":material/warning:")
    if cand_note is not None:
        _candidate_notice(*cand_note)
    st.caption(f"Punto: **{obs.label.split(' [')[0]}** · {C.fmt_num(obs.lat_deg, 4)}°, {C.fmt_num(obs.lon_deg_e, 4)}°E" +
               (" · candidato del sitio" if cand_note is not None and not cand_note[1] else "") +
               (f" · {_plain_snap(obs)}" if C.show_for("planificador") and _plain_snap(obs) else ""))

    C.public_note("En el polo sur lunar el Sol da la vuelta casi pegado al horizonte, así que cualquier relieve manda: una cresta "
                  "alta sigue viendo el Sol cuando el fondo de un valle o de un cráter ya está a oscuras, y una montaña cercana "
                  "puede taparlo del todo. Por eso LSI usa el terreno real y no una bola lisa para saber quién ve el Sol (y la Tierra).")

    if obs.mode is not HorizonMode.DEM:
        forced = S.get_bool(K.FORCE_SPHERE)
        far = obs.mode is HorizonMode.FAR_FIELD
        if far:
            st.warning(f"**{C.FAR_LABEL}: no hay recorte de 5 m en este punto.** El 3D del terreno necesita ese recorte, así que aquí "
                       "se muestra el mapa global plano. El horizonte, el Sol y la Tierra sí se calculan con el DEM polar de 80 m. "
                       + C.far_field_note(), icon=":material/terrain:")
        else:
            st.warning("**Sin datos de terreno.** " + ("Has forzado el modo esfera lisa." if forced else
                       "Este punto no cae en ninguno de los recortes de DEM disponibles.") +
                       " No se dibuja relieve: solo la curvatura lunar. La iluminación real puede ser muy distinta.",
                       icon=":material/terrain:")
        C.accessible_chart(_fig_globe(ctx, obs), f"Mapa global plano de la Luna con el punto de observación en {C.fmt_num(obs.lat_deg, 2)}° de "
                           f"latitud y {C.fmt_num(obs.lon_deg_e, 2)}° E, " + ("sin recorte de 5 m en ese punto (solo relieve aproximado de 80 m)." if far else
                           "sin relieve porque no hay DEM en ese punto."), key="_x_globe",
                           details=[f"{s.name}: {C.fmt_num(s.lat_deg, 2)}°, {C.fmt_num(s.lon_deg_e % 360, 2)}°E" for s in ctx.sites
                                    if s.lat_deg is not None and s.lon_deg_e is not None])
        _point_panel(obs)
        _sites_buttons(ctx)
        _metadata_section(None, ctx)
        return

    # ---- controles
    ss = st.session_state
    layer = S.get_str(K.LAYER, "elevacion")
    layer = layer if layer in LAYERS else "elevacion"
    ss["_x_layer"], ss["_x_height"] = layer, float(S.get_float(K.OBS_HEIGHT, 2.0))
    o = ctx.cfg["observer"]
    c1, c2, c3, c4 = st.columns([2.2, 1.4, 1.4, 1])
    c1.radio("Capa", list(LAYERS), format_func=LAYER_LABEL.get, key="_x_layer", on_change=_set_layer, horizontal=True)
    radius_lbl = c2.selectbox("Alcance del recorte", list(RADII), index=0, key="_x_radius",
                              help="Zona alrededor del punto que se dibuja. Más pequeña = celdas más finas (máx. 400 × 400 puntos; "
                                   "con 3 km de radio, celdas de 15 m).")
    exag = c3.slider("Exageración (vista alternativa)", 1.0, 8.0, 3.0, 0.5, key="_x_exag",
                     help="Solo para el 3D de Plotly (vista alternativa). El visor 3D tiene su propio control dentro del visor. "
                          "1 = escala real (x, y y altura en la misma proporción).")
    c4.number_input("Altura observador (m)", float(o["height_min_m"]), float(o["height_max_m"]), key="_x_height", step=0.5,
                    on_change=_set_height)

    radius = RADII[radius_lbl]
    cx, cy = _crop_center(obs, radius)
    win, extra = _terrain(obs.dem_key, cx, cy, radius, MAX_PX)
    if not np.isfinite(win.data).any():
        C.show_error("El recorte elegido no contiene datos de terreno válidos.")
        st.stop()
        return
    if layer not in ("elevacion", "pendiente", "iluminacion") and LAYERS[layer] not in extra:
        st.warning(f"La capa «{LAYER_LABEL[layer]}» no está disponible para este DEM; se muestra la elevación.")
        layer = "elevacion"
    res, cur = _time_controls(req)                                  # el instante (UTC) manda en el visor 3D y en la capa Iluminación
    sun, sun_line = None, ""
    if layer == "iluminacion":
        sun, sun_line = _sun_light(res, cur, obs, radius, cx, cy) if res is not None else (None, "")
        if sun is None:
            layer = "elevacion"
    markers = _site_markers(ctx, win)
    w_m, h_m, z0, z1 = _relief_stats(win)
    cell = win.pixel_size_m
    st.caption(f"Recorte de {C.fmt_num(w_m / 1000, 1)} × {C.fmt_num(h_m / 1000, 1)} km submuestreado a celdas de {C.fmt_num(cell, 0)} m "
               f"(promedio por bloques; resolución efectiva del DEM ≈ 30 m). La pendiente se mide a esa escala de celda. "
               f"Desnivel mostrado: {C.fmt_num(z1 - z0, 0, 'm')}.")

    # ---- figuras: una debajo de la otra (en media columna el lienzo 3D se encogía; no se usan pestañas: un 3D oculto mide 0 px)
    labels = named_features(win, cache.get_gazetteer())
    cands = [m for m in markers if np.hypot(m[1] - obs.x_m, m[2] - obs.y_m) > 150.0]
    if sun is not None:
        st.markdown(f"**{sun_line}**")
    st.markdown("#### Visor 3D")
    if res is None:
        st.warning("El visor 3D necesita la posición del Sol y de la Tierra (análisis del punto) y no está disponible; "
                   "usa la «Vista alternativa» (Plotly) de más abajo.", icon=":material/view_in_ar:")
    else:
        scene = viewer_scene(obs, res, cur, obs.dem_key, cx, cy, radius, labels)
        TV.render_terrain_viewer(scene, height=VIEWER_H)
        far = (f" Terreno lejano: modelo LOLA de 80 m (±{C.fmt_num(scene['ctx']['half_m'] / 1000, 0)} km, sin foto). " if "ctx" in scene else " ")
        fine = (f"Suelo cercano: alturas de 5 m interpoladas a {C.fmt_num(scene['patch']['step_m'], 1)} m; el microrrelieve es procedural: no es dato. "
                if "patch" in scene else "")
        st.caption(f"Visor three.js: terreno real {scene['nx']} × {scene['ny']} vértices ({C.fmt_num(scene['px_m'], 0)} m/celda), "
                   f"sombras calculadas para {scene['when_utc']} UTC y el Sol y la Tierra donde dicen los números.{far}{fine}"
                   f"{scene['photo']['notice']} Datos enviados al navegador: {C.fmt_num(scene['_bytes'] / 1e6, 2)} MB "
                   f"(recorte {C.fmt_num(scene['_bytes_crop'] / 1e6, 2)} + terreno lejano y suelo cercano {C.fmt_num(scene['_bytes_extra'] / 1e6, 2)}).")
        with st.expander("Descripción de la escena (modo lectura)"):
            st.write(scene["description"])
    st.markdown("#### Mapa topográfico")
    st.plotly_chart(_fig_relief(win, extra, obs, layer, cands, labels, sun), key="_x_map", on_select=_on_map_select,
                    selection_mode="points", width="stretch", theme=None)
    st.caption(f"Descripción de la figura: mapa topográfico 2D de {C.fmt_num(w_m / 1000, 1)} × {C.fmt_num(h_m / 1000, 1)} km con relieve "
               f"sombreado (Sol rasante desde el noroeste del mapa), curvas de nivel, la capa «{LAYER_LABEL[layer]}» en color, barra de "
               f"escala y flecha del norte local. El rombo ámbar es el observador" +
               (f"; los círculos numerados son los candidatos ({'; '.join(f'{i + 1} = {m[0]}' for i, m in enumerate(cands))})" if cands else "") +
               (f"; en cian, nombres del gazetteer ({', '.join(f'{n} ({t})' for n, _, _, t, _ in labels)})" if labels else "") +
               f". Haz clic en el mapa para mover el punto (precisión ≈ {C.fmt_num(w_m / CLICK_GRID, 0, 'm')}); para precisión fina usa la barra lateral.")
    alt3d = (f"Superficie 3D del terreno real alrededor de {obs.label.split(' [')[0]}: recorte de {C.fmt_num(w_m / 1000, 1)} por {C.fmt_num(h_m / 1000, 1)} km, "
             f"elevaciones de {C.fmt_num(z0, 0)} a {C.fmt_num(z1, 0)} m (desnivel de {C.fmt_num(z1 - z0, 0)} m), exageración vertical ×{exag:g}, "
             f"capa «{LAYER_LABEL[layer]}», vista oblicua desde el norte. Un rombo marca el punto de observación, a {obs.height_m:g} m "
             f"sobre el suelo. Se puede rotar arrastrando.")
    details = [f"Punto de observación: {C.fmt_num(obs.lat_deg, 4)}°, {C.fmt_num(obs.lon_deg_e, 4)}°E, suelo a {C.fmt_num(obs.ground_z_m, 1, 'm')}"] +               [f"{lbl}: x={C.fmt_num(x, 0)} m, y={C.fmt_num(y, 0)} m, z={C.fmt_num(z, 0, 'm')}" for lbl, x, y, z in markers] +               [f"{n} ({t}{', ' + C.fmt_num(dk, 1) + ' km' if dk else ''}): x={C.fmt_num(x, 0)} m, y={C.fmt_num(y, 0)} m" for n, x, y, t, dk in labels]
    with st.expander("Vista alternativa: relieve 3D con Plotly (sin foto ni sombras del visor)"):
        C.accessible_chart(_fig_3d(win, extra, obs, layer, exag, markers, labels, sun), alt3d, key="_x_3d", details=details)

    _point_panel(obs)
    _sites_buttons(ctx)
    _metadata_section(obs.dem_key, ctx, win.meta)


def _time_controls(req):
    """Selector de fecha y hora (cursor compartido ``CURSOR_UTC``). Devuelve (análisis, instante UTC) o (None, None) si no hay análisis
    (entonces el visor 3D no se ofrece: sin Sol ni Tierra no hay iluminación que dibujar)."""
    st.markdown("**Instante (iluminación y visor 3D)**")
    res, err = cache.try_analysis(req)
    if err or res is None:
        st.warning(f"No se pudo obtener la posición del Sol y la Tierra: {err or 'sin análisis'}.")
        return None, None
    t0, t1 = S.parse_utc(res.request.start_utc), S.parse_utc(res.request.end_utc)
    try:
        cur = S.parse_utc(S.get_str(K.CURSOR_UTC))
    except ValueError:
        cur = t0
    if not t0 <= cur <= t1:
        st.info(f"El instante guardado ({cur:%Y-%m-%d %H:%M} UTC) cae fuera del periodo analizado ({t0:%Y-%m-%d %H:%M} – "
                f"{t1:%Y-%m-%d %H:%M} UTC): se usa el más cercano. Cambia el periodo en la barra lateral para ver otras fechas.",
                icon=":material/schedule:")
        cur = min(max(cur, t0), t1)
    ss = st.session_state
    ss[_T] = cur
    st.slider("Fecha y hora (UTC)", min_value=t0, max_value=t1, step=timedelta(hours=1), format="YYYY-MM-DD HH:mm", key=_T,
              on_change=_set_cursor, help="Es el mismo instante que en Horizonte y visibilidad. Mover el cursor no repite el análisis.")
    return res, ss[_T]


def _sun_light(res, cur, obs, radius, cx, cy):
    """Iluminación del recorte LOLA para la capa «Iluminación» del mapa 2D y el 3D de Plotly: ((fracción, az rejilla, el), línea de texto)."""
    az, el, _ = sun_at(res, cur)
    az_r, el_r = round(az / 0.05) * 0.05, round(el / 0.05) * 0.05
    frac, g_az, el_c = _illumination(obs.dem_key, cx, cy, radius, MAX_PX, round(obs.lat_deg, 4), round(obs.lon_deg_e, 4), az_r, el_r)
    fin = np.isfinite(frac)
    pct = 100.0 * float(np.mean(frac[fin])) if fin.any() else float("nan")
    note = " (bajo el horizonte: todo el recorte está a oscuras)" if el < 0 else ""
    line = f"Sol: acimut {C.fmt_num(az, 0)}°, elevación {C.fmt_num(el, 1)}°{note} · {C.fmt_num(pct, 0)} % del recorte iluminado"
    st.caption(f"{cur:%Y-%m-%d %H:%M} UTC. Las sombras son las del relieve dentro del recorte mostrado; una montaña fuera de él no se cuenta "
               "(con el Sol a 1-2° una sombra puede ser muy larga: amplía el alcance para verlas mejor).")
    return (frac, g_az, el_c), line


def _sites_buttons(ctx) -> None:
    sites = [s for s in ctx.sites if s.has_dem and s.lat_deg is not None]
    if not sites:
        return
    st.markdown("**Sitios candidatos**", help="Site04 y Site11 tienen coordenadas curadas fuera de su recorte de DEM: se evalúa "
                                              "el punto cubierto más cercano y se avisa.")
    cols = st.columns(len(sites))
    for col, s in zip(cols, sites):
        col.button(f"Ir a {s.name}", key=f"_x_go_{s.id}", on_click=_go_site, args=(s.id,), icon=":material/my_location:",
                   width="stretch")


def _metadata_section(dem_key: Optional[str], ctx, meta=None) -> None:
    far = _far_meta()
    if S.is_public():
        st.markdown("**De dónde salen los datos.** El terreno viene del altímetro láser LOLA de la NASA (producto PGDA): "
                    "mide alturas cada 5 m, pero solo ~1 de cada 10 píxeles tiene medida real; el resto se interpola, así que el "
                    "detalle fiable ronda los 30 m. Más lejos se usa un mapa de 80 m.")
        return
    t1, t2 = st.tabs([f"Metadatos del DEM de 5 m ({dem_key})" if dem_key else "Metadatos del DEM de 5 m", "Campo lejano de 80 m"])
    with t1:
        if meta is not None:
            _meta_table(meta, far=False)
        else:
            st.info("Sin DEM de 5 m en este punto. Recortes disponibles: " + (", ".join(sorted(ctx.dem_refs)) or "ninguno") + ".")
    with t2:
        if far is None:
            st.info("El campo lejano LOLA de 80 m no está en data/raw (python scripts/fetch_data.py).")
        else:
            _meta_table(far, far=True)
            st.caption("Cubre del polo a 80° S: se usa donde el recorte de 5 m se acaba (horizonte lejano).")


main()
