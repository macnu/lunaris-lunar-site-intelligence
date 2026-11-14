"""Barra lateral común (arquitectura §11.1): sitio/punto, altura, periodo, paneles, perfil de misión y modo de usuario.

Patrón de estado: el estado canónico son las claves de ``contracts.StateKey`` (ver ``ui.state``); los widgets usan claves
``_w_*``. Al inicio de cada ejecución se copia estado → widgets (así una página puede cambiar el punto y hacer rerun) y
cada ``on_change`` copia widget → estado. Si un dato es inválido se muestra el mensaje y NO se pisa el estado válido.
"""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from lsi.contracts import AppContext, HorizonMode, MountingType, StateKey as K
from ui import cache, components as C, state as S

PERIOD_PRESETS: dict[str, float | None] = {
    "1 día": 1.0, "7 días": 7.0, "Día lunar (≈ 29,5 d)": 29.53, "30 días": 30.0, "1 año (365 d)": 365.0,
    "Personalizado": None,
}
_MOUNT_LABELS = C.MOUNT_LABELS
_CUSTOM, _SEARCH = "@custom", "@search"


# ------------------------------------------------------------------------------------------------ callbacks
def _push(canon: str, wkey: str) -> None:
    st.session_state[canon] = st.session_state[wkey]


def _on_mode() -> None:
    st.session_state[K.LANG_MODE] = S.MODE_LABELS_INV[st.session_state["_w_mode"]]


def _on_site(ctx: AppContext) -> None:
    tok = st.session_state["_w_site"]
    ss = st.session_state
    if tok == _CUSTOM:
        ss.update({K.SITE_ID: None, S.ORIGIN: "custom"})
    elif tok == _SEARCH and S.gaz_point():
        _, lat, lon, _ = S.gaz_point()
        S.set_point(lat, lon, gazetteer_id=S.gaz_point()[0], label=S.gaz_point()[3])
    else:
        S.set_site(tok, ctx)


def _on_mission() -> None:
    ss = st.session_state
    ss[S.MISSION_DAYS] = float(ss["_w_mdays"]) if ss["_w_mdays_custom"] else None


def _on_panels(ctx: AppContext) -> None:
    ids = list(st.session_state["_w_panels"])
    st.session_state[S.PANEL_IDS] = ids
    st.session_state[K.PANEL_ID] = ids[0] if ids else None


def _on_link_net() -> None:
    st.session_state[S.LINK_NETWORK] = st.session_state["_w_lnet"]


def _on_link_dir() -> None:
    st.session_state[S.LINK_DIRECTION] = st.session_state["_w_ldir"]


def _on_link_margin() -> None:
    st.session_state[S.LINK_MARGIN] = float(st.session_state["_w_lmargin"])


def _on_link_custom() -> None:
    ss = st.session_state
    n = int(ss["_w_lcn"])
    ss[S.LINK_CUSTOM] = [[float(ss[f"_w_lc{i}_lat"]), float(ss[f"_w_lc{i}_lon"]), float(ss[f"_w_lc{i}_el"])] for i in range(n)]


def _on_link_station_el() -> None:
    ss = st.session_state
    ss[S.LINK_STATION_EL] = float(ss["_w_lsel"]) if ss["_w_lsel_on"] else None


def _on_period() -> None:
    ss = st.session_state
    try:
        start = S.parse_utc(ss["_w_start"])
        preset = PERIOD_PRESETS[ss["_w_preset"]]
        days = float(preset if preset is not None else ss.get("_w_days", S.period_days()))
        msg = S.validate_period(start, start + timedelta(days=days))
    except ValueError as e:
        msg = str(e)
    if msg:
        S.set_error("period", msg)  # el estado válido anterior no se pisa; la barra lateral muestra el mensaje
        return
    S.set_period(start, days)       # también borra los errores previos
    ss[K.CURSOR_UTC] = ss[K.START_UTC]


# ------------------------------------------------------------------------------------------------ render
def _site_options(ctx: AppContext) -> tuple[list[str], dict[str, str], list[str]]:
    ok = [s for s in ctx.sites if s.lat_deg is not None and s.lon_deg_e is not None]
    ok.sort(key=lambda s: not s.has_dem)          # con DEM primero (destacados)
    labels = {s.id: f"{s.name} — {'con relieve real (DEM)' if s.has_dem else 'sin DEM: esfera lisa'}" for s in ok}
    opts = [s.id for s in ok]
    gaz = S.gaz_point()
    if gaz:
        opts.append(_SEARCH)
        labels[_SEARCH] = f"Del buscador: {gaz[3] or gaz[0]}"
    opts.append(_CUSTOM)
    labels[_CUSTOM] = "Coordenadas personalizadas"
    unavailable = [s.name for s in ctx.sites if s.lat_deg is None or s.lon_deg_e is None]
    return opts, labels, unavailable


def _period_text() -> str:
    return S.parse_utc(st.session_state[K.START_UTC]).strftime("%Y-%m-%d %H:%M")


def _sync_widgets(ctx: AppContext) -> None:
    """Estado → widgets (antes de instanciarlos; se permite escribir su clave)."""
    ss = st.session_state
    origin = ss[S.ORIGIN]
    ss["_w_site"] = ss[K.SITE_ID] if origin == "site" else (_SEARCH if origin == "search" and S.gaz_point() else _CUSTOM)
    ss["_w_mode"] = S.MODE_LABELS[S.mode()]
    ss["_w_lat"], ss["_w_lon"] = float(ss[K.OBS_LAT]), float(ss[K.OBS_LON])
    ss["_w_height"] = float(ss[K.OBS_HEIGHT])
    ss["_w_panels"] = [p for p in ss[S.PANEL_IDS] if any(p == x.id for x in ctx.panels.panels)]
    ss["_w_mount"] = ss[K.MOUNT_TYPE]
    ss["_w_tilt"], ss["_w_maz"] = float(ss[K.MOUNT_TILT]), float(ss[K.MOUNT_AZ])
    ss["_w_profile"] = ss[K.SCORE_PROFILE]
    md = ss.get(S.MISSION_DAYS)
    ss["_w_mdays_custom"] = md is not None
    ss["_w_mdays"] = min(max(float(md or S.profile_mission_days(ctx, ss[K.SCORE_PROFILE]) or 14.0), 0.5), S.MAX_PERIOD_DAYS)
    ss["_w_step"] = int(ss[K.STEP_MIN]) if int(ss[K.STEP_MIN]) in S.STEP_CHOICES_MIN else 10
    ss["_w_unc"], ss["_w_sphere"] = bool(ss[K.WITH_UNCERTAINTY]), bool(ss[K.FORCE_SPHERE])
    ss["_w_deg"], ss["_w_dust"] = float(ss[K.DEGRADATION]), float(ss[K.DUST_LOSS])
    ss["_w_ldir"] = ss[S.LINK_DIRECTION]
    ss["_w_lnet"], ss["_w_lmargin"] = ss[S.LINK_NETWORK], float(ss[S.LINK_MARGIN])
    rows = [list(r) for r in (ss[S.LINK_CUSTOM] or [[40.0, 4.0, 6.0]])][:3]
    ss["_w_lcn"] = len(rows)
    for i, (la, lo, el) in enumerate(rows):
        ss[f"_w_lc{i}_lat"], ss[f"_w_lc{i}_lon"], ss[f"_w_lc{i}_el"] = float(la), float(lo), float(el)
    sel = ss.get(S.LINK_STATION_EL)
    ss["_w_lsel_on"], ss["_w_lsel"] = sel is not None, float(6.0 if sel is None else sel)
    if "period" not in S.errors():  # con un error de fecha se conserva lo escrito por el usuario para que lo corrija
        ss["_w_start"] = _period_text()
        days = S.period_days()
        match = next((k for k, v in PERIOD_PRESETS.items() if v is not None and abs(v - days) < 1e-6), "Personalizado")
        ss["_w_preset"], ss["_w_days"] = match, min(max(float(days), 0.5), S.MAX_PERIOD_DAYS)


def render_sidebar(ctx: AppContext) -> None:
    """Pinta la barra lateral común y deja en ``st.session_state`` el estado canónico y los errores de entrada."""
    S.init_state(ctx)
    _sync_widgets(ctx)
    ss = st.session_state
    with st.sidebar:
        st.markdown("## :material/tune: Parámetros")
        st.selectbox("Modo de usuario", list(S.MODE_LABELS.values()), key="_w_mode", on_change=_on_mode,
                     help="Público: explicaciones sencillas. Planificador: más controles. Experto: todos los parámetros.")

        # --- sitio / punto
        opts, labels, unavailable = _site_options(ctx)
        st.selectbox("Sitio", opts, key="_w_site", format_func=labels.get, on_change=_on_site, args=(ctx,),
                     help="Lista curada (los de relieve real, primero), un lugar del buscador o tus coordenadas.")
        if ss[S.ORIGIN] == "custom":
            st.number_input("Latitud (°, sur negativa)", -90.0, 90.0, key="_w_lat", step=0.01, format="%.4f",
                            on_change=_push, args=(K.OBS_LAT, "_w_lat"))
            st.number_input("Longitud (°E, 0–360)", -180.0, 360.0, key="_w_lon", step=0.01, format="%.4f",
                            on_change=_push, args=(K.OBS_LON, "_w_lon"))
        else:
            st.caption(f"Lat {C.fmt_num(ss[K.OBS_LAT], 4)}° · Lon {C.fmt_num(ss[K.OBS_LON], 4)}°E")
        if unavailable:
            with st.expander(f"No disponibles ({len(unavailable)}): coordenadas a verificar"):
                st.caption("; ".join(unavailable))
        if S.mode() != "publico":
            o = ctx.cfg["observer"]
            st.number_input("Altura del observador (m)", float(o["height_min_m"]), float(o["height_max_m"]), key="_w_height",
                            step=0.5, on_change=_push, args=(K.OBS_HEIGHT, "_w_height"),
                            help="Altura de la antena o del mástil sobre el suelo.")

        # --- periodo
        st.markdown("#### Periodo (UTC)")
        st.text_input("Inicio (AAAA-MM-DD HH:MM, UTC)", key="_w_start", on_change=_on_period,
                      help="Rango válido: 2 ene 1900 – 30 dic 2050 (efemérides SPICE).")
        st.selectbox("Duración", list(PERIOD_PRESETS), key="_w_preset", on_change=_on_period)
        if ss["_w_preset"] == "Personalizado":
            st.number_input("Días", 0.5, S.MAX_PERIOD_DAYS, key="_w_days", step=1.0, on_change=_on_period)
        err = S.errors().get("period")
        if err:
            st.error(err, icon=":material/error:")
        else:
            st.caption(f"{ss[K.START_UTC].replace('T', ' ')} → {ss[K.END_UTC].replace('T', ' ')} UTC")
            md = S.effective_mission_days(ctx)
            if md and S.period_days() < md - 1e-6:
                st.warning(f"El periodo ({S.period_days():g} d) es menor que la misión ({md:g} d): no cabe una ventana completa y "
                           f"el veredicto será SIN DATOS. Alarga el periodo a {md:g} d o más (aconsejable).", icon=":material/warning:")

        # --- panel(es), montaje y perfil de misión
        if S.mode() != "publico":
            st.markdown("#### Panel solar y misión")
            panels = {p.id: p for p in ctx.panels.panels}
            st.multiselect("Panel(es)", list(panels), key="_w_panels", on_change=_on_panels, args=(ctx,),
                           format_func=lambda i: panels[i].name + (" (a verificar)" if panels[i].confidence.get("eta_bol") == "a_verificar" else ""),
                           help="El primero es el panel principal; la página de potencia puede comparar varios.")
            primary = ss[K.PANEL_ID]
            if primary in panels:
                allowed = [m.value for m in panels[primary].mounting_allowed]
                if ss["_w_mount"] not in allowed:
                    ss["_w_mount"] = panels[primary].mounting_default.value
                st.selectbox("Montaje", allowed, key="_w_mount", format_func=lambda v: _MOUNT_LABELS.get(v, v),
                             on_change=S.choose_mount, args=("_w_mount",),
                             help="Por defecto se elige según la latitud: vertical con seguimiento en el polo (|lat| > 70°), horizontal en latitudes bajas.")
                if ss.get(S.MOUNT_AUTO, True):
                    st.caption("Montaje automático: vertical en el polo, donde el Sol queda a ≤ ~1,6° del horizonte."
                               if S.is_polar(ss[K.OBS_LAT]) else "Montaje automático según la latitud.")
                else:
                    st.button("Volver al montaje automático", key="_w_mount_auto", on_click=S.use_auto_mount, icon=":material/auto_mode:")
                C.polar_horizontal_warning(ss[K.OBS_LAT], ss["_w_mount"])
                if ss["_w_mount"] == MountingType.TILTED.value:
                    st.number_input("Inclinación (°)", 0.0, 90.0, key="_w_tilt", step=1.0, on_change=_push,
                                    args=(K.MOUNT_TILT, "_w_tilt"))
                if ss["_w_mount"] in (MountingType.TILTED.value, MountingType.VERTICAL_FIXED.value):
                    st.number_input("Azimut de la normal (°)", 0.0, 360.0, key="_w_maz", step=1.0, on_change=_push,
                                    args=(K.MOUNT_AZ, "_w_maz"))
            profiles = {**{k: v.label for k, v in ctx.panels.profiles.items()}, "custom": "Personalizado (umbrales propios)"}
            st.selectbox("Perfil de misión", list(profiles), key="_w_profile", format_func=profiles.get,
                         on_change=_push, args=(K.SCORE_PROFILE, "_w_profile"),
                         help="Define los umbrales del score (editables en su página; pendientes de calibrar con un experto).")
            default_md = S.profile_mission_days(ctx, ss[K.SCORE_PROFILE])
            st.checkbox("Duración de misión personalizada", key="_w_mdays_custom", on_change=_on_mission,
                        help="Por defecto se usa la duración propia del perfil" + (f" ({default_md:g} d)." if default_md else " (este perfil no tiene ventana)."))
            if ss["_w_mdays_custom"]:
                st.number_input("Duración de la misión (días)", 0.5, S.MAX_PERIOD_DAYS, key="_w_mdays", step=1.0, on_change=_on_mission,
                                help="El score y las puertas se evalúan sobre una ventana de esta duración; el periodo debería ser al menos igual.")
            else:
                st.caption(f"Misión: {default_md:g} d (la del perfil)." if default_md else "Sin ventana de misión: se evalúa todo el periodo.")

        # --- conectividad: red de estaciones y margen de elevación (viajan en la petición)
        _link_controls()

        # --- avanzado (experto)
        if S.is_expert():
            with st.expander("Avanzado (experto)"):
                st.selectbox("Paso de la serie (min)", S.STEP_CHOICES_MIN, key="_w_step", on_change=_push,
                             args=(K.STEP_MIN, "_w_step"))
                st.checkbox("Calcular incertidumbre (rango)", key="_w_unc", on_change=_push, args=(K.WITH_UNCERTAINTY, "_w_unc"))
                st.checkbox("Ignorar el DEM (esfera lisa)", key="_w_sphere", on_change=_push, args=(K.FORCE_SPHERE, "_w_sphere"),
                            help="Fuerza el modo sin relieve aunque haya DEM.")
                st.number_input("Degradación del panel (fracción)", 0.0, 0.9, key="_w_deg", step=0.01,
                                on_change=_push, args=(K.DEGRADATION, "_w_deg"))
                st.number_input("Pérdida por polvo (fracción, sensibilidad)", 0.0, 0.9, key="_w_dust", step=0.01,
                                on_change=_push, args=(K.DUST_LOSS, "_w_dust"))

        _observer_status(ctx)
        if S.is_public():
            st.caption("Pasa el ratón por los «?» para ver qué significa cada término.")


def _link_controls() -> None:
    ss = st.session_state
    if S.is_public():
        st.caption(f"Conectividad: {S.LINK_NETWORKS.get(ss[S.LINK_NETWORK], ss[S.LINK_NETWORK])}, "
                   f"{S.LINK_DIRECTION_NAMES[ss[S.LINK_DIRECTION]]}. "
                   "Cámbialo en el modo Planificador.")
        return
    st.markdown("#### Conectividad (enlace con la Tierra)")
    st.selectbox("Red de estaciones terrestres", list(S.LINK_NETWORKS), key="_w_lnet", format_func=S.LINK_NETWORKS.get,
                 on_change=_on_link_net,
                 help="Qué antenas terrestres cuentan. La red NSN de NASA no está incluida porque no se ha podido verificar. "
                      "«Solo geometría» ignora las estaciones y cuenta únicamente que la Tierra se vea.")
    if ss[S.LINK_NETWORK] == "geometry":
        return
    st.selectbox("Sentido del enlace", list(S.LINK_DIRECTIONS), key="_w_ldir", format_func=S.LINK_DIRECTIONS.get,
                 on_change=_on_link_dir,
                 help="Recibir datos de la nave exige menos elevación de antena que enviarle órdenes: por eso la transmisión (comandos) "
                      "tiene menos cobertura que la recepción. «Ambos» exige que se cumplan los dos a la vez.")
    st.slider("Margen mínimo de elevación de la antena (°)", 0.0, S.LINK_MARGIN_MAX, key="_w_lmargin", step=0.5,
              on_change=_on_link_margin,
              help="Cuánto más alta que el horizonte debe verse la Tierra desde el lander. 0° = basta con que asome (supuesto por defecto).")
    if ss[S.LINK_NETWORK] == "custom":
        st.number_input("Estaciones personalizadas", 1, 3, key="_w_lcn", on_change=_on_link_custom)
        for i in range(int(ss["_w_lcn"])):
            c1, c2, c3 = st.columns(3)
            c1.number_input(f"Lat {i + 1} (°)", -90.0, 90.0, key=f"_w_lc{i}_lat", step=0.1, on_change=_on_link_custom)
            c2.number_input(f"Lon {i + 1} (°E)", -180.0, 360.0, key=f"_w_lc{i}_lon", step=0.1, on_change=_on_link_custom)
            c3.number_input(f"Elev. mín. {i + 1} (°)", 0.0, 30.0, key=f"_w_lc{i}_el", step=0.5, on_change=_on_link_custom)
    if S.is_expert():
        st.checkbox("Forzar la elevación mínima de todas las estaciones", key="_w_lsel_on", on_change=_on_link_station_el,
                    help="Sensibilidad: sustituye el 6° publicado (DSN) o supuesto (ESTRACK).")
        if ss["_w_lsel_on"]:
            st.number_input("Elevación mínima de las estaciones (°)", 0.0, 30.0, key="_w_lsel", step=0.5,
                            on_change=_on_link_station_el)


def _observer_status(ctx: AppContext) -> None:
    """Resuelve el punto (barato y cacheado), muestra el modo previsto o el error, y lo registra como error de entrada."""
    if "period" in S.errors():
        return
    req = S.build_request(st.session_state, ctx)
    obs, _warns, err = cache.get_observer(req)
    S.set_error("observer", err)
    if err:
        st.error(err, icon=":material/error:")
        return
    if obs.mode is HorizonMode.DEM:
        st.success(f"Modo DEM: relieve real ({obs.dem_key}).", icon=":material/terrain:")
    else:
        st.warning("Modo esfera lisa: sin datos de terreno en este punto.", icon=":material/public:")
    if obs.snap_distance_km is not None:
        st.caption(f"snap_to_dem: se evalúa un punto del DEM a {C.fmt_num(obs.snap_distance_km, 2)} km del pedido."
                   + (f" Punto elegido: {C.observer_snap_phrase(obs)}." if C.observer_snap_phrase(obs) else ""))
