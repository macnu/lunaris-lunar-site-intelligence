"""Pantalla «Mapa del polo sur»: el DEM polar de 80 m (±304 km, de 80°S al polo) como mapa navegable, con nombres, los tres recortes
de 5 m, capas REALES opcionales (PSR, temperatura Diviner, iluminación media publicada) y selección de punto por clic.

No calcula física: pinta ``visualization.polar_map`` (base cacheada en ``data/processed/polar_map/`` y ventanas de zoom leídas del
DEM) y deja el punto elegido en el estado compartido como coordenadas personalizadas; «Evaluar este punto» abre «Capacidad del sitio»,
que usa el relieve de 5 m dentro de los recortes y el de 80 m (horizonte aproximado) fuera. Una capa sin ficheros se oculta con aviso.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import streamlit as st

from lsi.astronomy.coordinates import stereo_forward, stereo_inverse
from lsi.contracts import AnalysisRequest, DemNotFoundError, GazetteerQuery, HorizonMode, StateKey as K
from lsi.data import gazetteer
from lsi.pipeline import far_field_warning_text
from lsi.data import polar_view as pv
from lsi.visualization import polar_map as pm
from ui import cache, components as C, state as S

TARGET_PAGE = "ui/pages/site_capacity.py"
DOWNLOAD_CMD = "python scripts/fetch_data.py"
LAYERS_CMD = "python scripts/fetch_thermal_psr.py"
CLICK_N = 90
COLOR_LAYERS = {"none": "Sin capa de color", "temp_mean": "Temperatura media", "temp_max": "Temperatura máxima",
                "temp_min": "Temperatura mínima", "illum": "Iluminación media publicada"}
_Z, _CX, _CY, _COLOR, _PSR, _GRID, _CONT, _HIT, _Q, _PICK, _GO = ("_pm_zoom", "_pm_cx", "_pm_cy", "_pm_color", "_pm_psr", "_pm_grid",
                                                                   "_pm_cont", "_pm_hit", "_pm_q", "_pm_pick", "_pm_go")


def _t(public: str, tech: str) -> str:
    """Texto llano en modo Público y término técnico en los demás."""
    return public if S.is_public() else tech


# ------------------------------------------------------------------------------------------------ datos cacheados
def _paths() -> tuple[Path, Path]:
    ctx = cache.get_context()
    return Path(ctx.root) / "data" / "raw", Path(ctx.root) / ctx.cfg["cache"]["dir"]


@st.cache_resource(show_spinner="Preparando el relieve del polo (solo la primera vez)…")
def _base() -> pv.View:
    raw, cdir = _paths()
    return pv.build_base(raw, cdir)


@st.cache_resource(max_entries=6, show_spinner="Leyendo el relieve de esta zona…")
def _view(zoom: int, cx: float, cy: float) -> pv.View:
    return _base() if zoom == 1 else pv.view_for(_paths()[0], cx, cy, pv.half_for_zoom(zoom))


@st.cache_resource(max_entries=16, show_spinner="Leyendo la capa…")
def _layer(layer: str, zoom: int, cx: float, cy: float):
    return pv.layer_array(layer, _view(zoom, cx, cy))


@st.cache_data(max_entries=24, show_spinner=False)
def _image(zoom: int, cx: float, cy: float, color: str, psr: bool):
    """(imagen JPEG como texto, rango de la capa de color) de la vista con sus capas."""
    v = _view(zoom, cx, cy)
    col = None if color == "none" else _layer(color, zoom, cx, cy)
    mask = _layer("psr", zoom, cx, cy) if psr else None
    rgb, rng = pv.compose_rgb(v, col, "illum" if color == "illum" else "temp", mask)
    return pv.jpeg_uri(rgb), rng


def _recortes(ctx) -> list:
    name = {s.dem_prefix: C.place_name(s.name) for s in ctx.sites if s.dem_prefix}
    return [(name.get(k, k), r.bounds_xy_m) for k, r in ctx.dem_refs.items()]


# ------------------------------------------------------------------------------------------------ navegación
def _half() -> float:
    return pv.half_for_zoom(int(st.session_state[_Z]))


def _clamp() -> None:
    ss, h = st.session_state, _half()
    lim = max(pv.FAR_HALF_M - h, 0.0)
    ss[_CX], ss[_CY] = (float(np.clip(round(ss[k] / 100.0) * 100.0, -lim, lim)) for k in (_CX, _CY))


def _on_zoom() -> None:
    _clamp()


def _pan(dx: float, dy: float) -> None:
    ss = st.session_state
    ss[_CX], ss[_CY] = ss[_CX] + dx * _half() / 2.0, ss[_CY] + dy * _half() / 2.0
    _clamp()


def _reset() -> None:
    st.session_state.update({_Z: 1, _CX: 0.0, _CY: 0.0})


def _center_on(lat: float, lon: float, diameter_km: float = 0.0) -> None:
    ss = st.session_state
    x, y = (float(v) for v in stereo_forward(lat, lon))
    need = max(1.3 * diameter_km, 6.0)
    ss[_Z] = max(z for z in pv.ZOOMS if pv.FAR_HALF_M / 1000.0 / z >= need)
    ss[_CX], ss[_CY] = x, y
    _clamp()


def _on_hit(hits: dict) -> None:
    e = hits.get(st.session_state.get(_HIT))
    if e is not None:
        _center_on(e.lat_deg, e.lon_deg_e, e.diameter_km or 0.0)


def _on_pick() -> None:
    """Un clic fija el punto de observación (coordenadas personalizadas) en la celda del mapa mostrado."""
    sel = st.session_state.get("_pm_map")
    try:
        p = sel["selection"]["points"][0]
        x, y = float(p["x"]) * 1000.0, float(p["y"]) * 1000.0
    except (KeyError, IndexError, TypeError, ValueError):
        return
    lat, lon = (float(v) for v in stereo_inverse(x, y))
    S.set_point(lat, lon)
    st.session_state[_PICK] = {"x": x, "y": y, "prec_km": float(st.session_state.get("_pm_prec", 0.0))}


def _go() -> None:
    st.session_state[_GO] = True


# ------------------------------------------------------------------------------------------------ tarjeta del punto
def _mode_lines(obs) -> tuple[str, str]:
    """(qué relieve se usará, aviso) en el lenguaje del modo de usuario."""
    if obs.mode is HorizonMode.DEM:
        return (_t("Relieve detallado (celdas de 5 m): sirve para estudiar un aterrizaje.", f"DEM de 5 m del recorte {obs.dem_key}."),
                "")
    if obs.mode is HorizonMode.FAR_FIELD:
        return (_t("Relieve aproximado (celdas de 80 m): vale para estimar cuánta luz y cuánta Tierra se ven, no para decidir dónde posarse.",
                   "DEM polar de 80 m (modo FAR_FIELD): horizonte aproximado, score parcial."),
                far_field_warning_text() if not S.is_public() else
                "El relieve de 80 m suaviza las paredes de los cráteres, así que la luz estimada puede variar; no sirve para decidir un aterrizaje fino.")
    return (_t("Sin relieve: este punto queda fuera del mapa de alta precisión del polo.", "Esfera lisa: fuera del dominio del DEM polar (> 80°S)."), "")


def _card(ctx, base: pv.View) -> None:
    ss = st.session_state
    lat, lon = float(ss[K.OBS_LAT]), float(ss[K.OBS_LON])
    req = S.current_request() or AnalysisRequest(lat, lon, "2027-01-01T00:00:00Z", "2027-01-31T00:00:00Z",
                                                observer_height_m=S.get_float(K.OBS_HEIGHT, 2.0))
    obs, _warns, err = cache.get_observer(req)
    with st.container(border=True):
        st.markdown("#### " + _t("Punto elegido", "Punto de observación"))
        if err or obs is None:
            C.show_error(err or "No se pudo resolver el punto.")
            return
        x, y = obs.x_m, obs.y_m
        z = obs.ground_z_m if obs.ground_z_m is not None else base.z_at(x, y)
        mode, warn = _mode_lines(obs)
        c1, c2, c3 = st.columns([1.2, 1, 2.2])
        c1.metric("Latitud / longitud", f"{C.fmt_num(obs.lat_deg, 4)}°, {C.fmt_num(obs.lon_deg_e, 4)}°E")
        c2.metric(_t("Altura sobre el nivel medio", "Elevación (m)"), "sin dato" if z is None else C.fmt_num(z, 0, "m"))
        c3.markdown(f"**Relieve que se usará:** {C.esc(mode)}")
        if warn:
            st.warning(warn, icon=":material/warning:")
        pick = ss.get(_PICK)
        if pick:
            st.caption(f"Elegido en el mapa: precisión ≈ ±{C.fmt_num(pick['prec_km'] / 2, 1)} km (la celda del mapa mostrado; acércate con el "
                       f"zoom para afinar). Para un punto exacto escribe la latitud y la longitud en la barra lateral.")
        st.button("Evaluar este punto", key="_pm_eval", type="primary", icon=":material/rocket_launch:", on_click=_go,
                  help="Abre «Capacidad del sitio» con este punto: Sol, Tierra, enlace, ventanas y score.")


# ------------------------------------------------------------------------------------------------ página
def _description(zoom, v, labels, recortes, color, psr, obs_txt) -> str:
    w_km = (v.extent[1] - v.extent[0]) / 1000.0
    layers = [COLOR_LAYERS[color].lower()] if color != "none" else []
    if psr:
        layers.append("zonas de sombra permanente")
    return (f"Mapa del polo sur de la Luna de {C.fmt_num(w_km, 0)} km de lado (zoom ×{zoom}) con relieve sombreado a partir de un modelo de "
            f"elevaciones de 80 m, paralelos y meridianos de referencia, escala gráfica y el norte hacia fuera del centro (el centro es el "
            f"polo sur). Los rectángulos ámbar son los recortes de alta precisión ({', '.join(n for n, _ in recortes)}); en cian, los "
            f"nombres de los rasgos {'(' + ', '.join(l[0] for l in labels[:12]) + (', …' if len(labels) > 12 else '') + ')' if labels else ''}. "
            f"Capas activas: {', '.join(layers) if layers else 'ninguna'}. {obs_txt}")


def main() -> None:
    st.title("Mapa del polo sur")
    C.warnings_band()
    ctx = cache.get_context()
    ss = st.session_state
    for k, d in ((_Z, 1), (_CX, 0.0), (_CY, 0.0), (_COLOR, "none"), (_PSR, False), (_GRID, True), (_CONT, False)):
        ss.setdefault(k, d)
    C.public_note("Este es el mapa del polo sur de la Luna visto desde arriba, con el polo en el centro. Las zonas claras son terreno "
                  "alto y las oscuras, hondonadas. Toca el mapa para elegir un punto y pulsa «Evaluar este punto» para saber cuánta luz "
                  "del Sol y cuánta Tierra se verían desde allí.")
    try:
        base = _base()
    except DemNotFoundError as e:
        st.warning(f"{e}", icon=":material/download:")
        st.code(DOWNLOAD_CMD, language="bash")
        return

    # --- buscador por nombre
    df = cache.get_gazetteer()
    hits: dict = {}
    c0, c1 = st.columns([2, 3])
    q = c0.text_input("Buscar un cráter o monte por nombre", key=_Q, placeholder="Shackleton, Malapert, Cabeus…")
    if q.strip() and df is not None:
        for e in gazetteer.search(df, GazetteerQuery(text=q, limit=12)):
            if e.lat_deg <= -79.9:
                hits[e.feature_id] = e
        if hits:
            c1.selectbox("Resultados", list(hits), key=_HIT, on_change=_on_hit, args=(hits,), label_visibility="visible",
                         format_func=lambda i: f"{hits[i].name} · {hits[i].feature_type}" + (f" · {C.fmt_num(hits[i].diameter_km, 0)} km" if hits[i].diameter_km else ""))
            if ss.get(_HIT) in hits and ss.get("_pm_hit_done") != (q, ss[_HIT]):
                ss["_pm_hit_done"] = (q, ss[_HIT])
                _on_hit(hits)
        else:
            c1.caption(f"Ningún rasgo con nombre «{C.esc(q)}» dentro del mapa (de 80°S al polo).")
    elif df is None:
        c1.caption("El buscador no está disponible: falta el gazetteer (python scripts/fetch_gazetteer.py).")

    # --- controles
    z_col, pan_col, lay_col = st.columns([1.3, 1.3, 2.4])
    z_col.select_slider("Zoom", list(pv.ZOOMS), key=_Z, on_change=_on_zoom, format_func=lambda z: f"×{z}",
                        help="×1 = el polo entero (±304 km). Cada paso acerca el doble y afina los nombres y el relieve.")
    with pan_col:
        st.caption("Desplazar")
        b = st.columns(5)
        b[0].button("", key="_pm_l", icon=":material/arrow_back:", on_click=_pan, args=(-1, 0), help="Izquierda", disabled=ss[_Z] == 1)
        b[1].button("", key="_pm_u", icon=":material/arrow_upward:", on_click=_pan, args=(0, 1), help="Arriba", disabled=ss[_Z] == 1)
        b[2].button("", key="_pm_d", icon=":material/arrow_downward:", on_click=_pan, args=(0, -1), help="Abajo", disabled=ss[_Z] == 1)
        b[3].button("", key="_pm_r", icon=":material/arrow_forward:", on_click=_pan, args=(1, 0), help="Derecha", disabled=ss[_Z] == 1)
        b[4].button("", key="_pm_home", icon=":material/home:", on_click=_reset, help="Ver el polo entero")
    avail = {k: (True if k == "none" else pv.layer_available(k)) for k in COLOR_LAYERS}
    options = [k for k in COLOR_LAYERS if avail[k]]
    if ss[_COLOR] not in options:
        ss[_COLOR] = "none"
    lay_col.radio("Capa de color", options, key=_COLOR, horizontal=True, format_func=COLOR_LAYERS.get)
    o1, o2, o3 = st.columns(3)
    psr_ok = pv.layer_available("psr")
    o1.checkbox(_t("Zonas que nunca reciben luz", "Regiones permanentemente sombreadas (PSR)"), key=_PSR, disabled=not psr_ok)
    o2.checkbox("Curvas de nivel", key=_CONT)
    o3.checkbox("Paralelos y meridianos", key=_GRID)
    missing = [COLOR_LAYERS[k] for k in COLOR_LAYERS if not avail[k]] + ([] if psr_ok else ["Regiones permanentemente sombreadas"])
    if missing:
        st.warning("Capas ocultas: faltan sus ficheros (" + ", ".join(missing) + "). No se dibuja nada inventado. Descárgalos con:",
                   icon=":material/hide_source:")
        st.code(LAYERS_CMD, language="bash")

    # --- vista
    zoom, (cx, cy) = int(ss[_Z]), (float(ss[_CX]), float(ss[_CY]))
    try:
        v = _view(zoom, cx, cy)
        uri, rng = _image(zoom, cx, cy, ss[_COLOR], bool(ss[_PSR]) and psr_ok)
    except DemNotFoundError as e:
        C.show_error(e)
        return
    labels = pv.label_features(df, v.extent) if df is not None else []
    recortes = _recortes(ctx)
    lat, lon = float(ss[K.OBS_LAT]), float(ss[K.OBS_LON])
    ox, oy = (float(t) for t in stereo_forward(lat, lon))
    olabel = C.place_name(S.point_info(ctx).label)
    color_bar = None
    if rng is not None and ss[_COLOR] != "none":
        info = pv.layer_info(ss[_COLOR])
        color_bar = (f"{info['title']} ({info['unit']}) · {info['note']}", pv.LAYER_SCALE["illum" if ss[_COLOR] == "illum" else "temp"], *rng)
    ss["_pm_prec"] = pm.click_precision_km(v, CLICK_N)
    fig = pm.polar_map_figure(v, uri, labels=labels, recortes=recortes, observer=(ox, oy, olabel), grid=bool(ss[_GRID]),
                              contours=bool(ss[_CONT]), color_bar=color_bar, click_n=CLICK_N,
                              psr_legend=bool(ss[_PSR]) and psr_ok)
    st.plotly_chart(fig, key="_pm_map", on_select=_on_pick, selection_mode="points", width="stretch", theme=None,
                    config={"displayModeBar": False, "scrollZoom": False})
    obs_txt = f"El rombo ámbar es el punto de observación ({olabel}). Pulsa en el mapa para moverlo (precisión ≈ la celda de {C.fmt_num(ss['_pm_prec'], 1)} km)."
    st.caption("Descripción de la figura: " + _description(zoom, v, labels, recortes, ss[_COLOR], bool(ss[_PSR]) and psr_ok, obs_txt))
    with st.expander("Datos de la figura en texto"):
        for n, x0, y0, t, dk in labels:
            la, lo = (float(u) for u in stereo_inverse(x0, y0))
            st.markdown(f"- {C.esc(n)} ({C.esc(t)}{', ' + C.fmt_num(dk, 0) + ' km' if dk else ''}): {C.fmt_num(la, 2)}°, {C.fmt_num(lo, 2)}°E")
        for n, (a, b_, c_, d_) in recortes:
            st.markdown(f"- Recorte de 5 m «{C.esc(n)}»: x de {C.fmt_num(a / 1000, 0)} a {C.fmt_num(c_ / 1000, 0)} km, y de {C.fmt_num(b_ / 1000, 0)} a {C.fmt_num(d_ / 1000, 0)} km")

    # --- rótulos científicos de las capas activas (qué son y qué NO son)
    notes = []
    if ss[_PSR] and psr_ok:
        i = pv.layer_info("psr")
        notes.append(f"**{i['title']}**: {i['note']}. {i['attribution']}")
    if ss[_COLOR] != "none":
        i = pv.layer_info(ss[_COLOR])
        notes.append(f"**{i['title']}**: {i['note']}. {i['attribution']}")
    if notes:
        with st.expander("Qué muestran las capas (y qué no)", expanded=S.is_expert()):
            for n in notes:
                st.markdown(f"- {n}")
    st.caption(f"Relieve: LRO LOLA, modelo polar de 80 m (PGDA); mostrado a celdas de {C.fmt_num(v.px, 0)} m. Los recortes de 5 m "
               f"(ámbar) son los únicos con relieve fino.")

    _card(ctx, base)
    if hits and ss.get(_HIT) in hits:
        e = hits[ss[_HIT]]
        st.button(f"Usar el centro de «{e.name}» como punto", key="_pm_use", icon=":material/my_location:",
                  on_click=lambda: S.set_point(e.lat_deg, e.lon_deg_e, label=e.name),
                  help="Fija el punto en el centro del rasgo (no es un punto de aterrizaje).")

    if ss.pop(_GO, False):
        try:
            st.switch_page(TARGET_PAGE)
        except st.errors.StreamlitAPIException:
            st.success("Punto fijado. Abre «Capacidad del sitio» en el menú para ver el resultado.", icon=":material/check_circle:")


main()
