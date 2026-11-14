"""Pantalla B · Horizonte y visibilidad (arquitectura §11.2): perfil 360°, Sol y Tierra en el instante elegido y
cuentas atrás hasta puesta de Sol / Earthset.

No calcula nada: el análisis sale de ``ui.cache.try_analysis``; mover el cursor solo cambia el índice sobre las series ya
calculadas y llama a ``ui.cache.countdowns_at`` (sin repetir el análisis). El cursor vive en ``StateKey.CURSOR_UTC``.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from lsi.analysis import export
from lsi.contracts import Body, HorizonMode, LSIError, StateKey as K, VisibilityState
from lsi.visualization import horizon_plot as HP, theme
from ui import cache, components as C, state as S

_T, _STEP, _PLAY = "_hv_t", "_hv_step", "_hv_play"      # claves propias de esta página
_STEPS_MIN = (10, 30, 60, 180, 360, 720, 1440)
_NAME = {
    Body.SUN: dict(art="el Sol", Art="El Sol", up="Tiempo hasta la puesta de Sol", down="Tiempo hasta la salida del Sol",
                   set="puesta de Sol", rise="salida del Sol", term="Puesta de Sol", wait="saldrá", leave="se pondrá"),
    Body.EARTH: dict(art="la Tierra", Art="La Tierra", up="Tiempo hasta Earthset", down="Tiempo hasta Earthrise",
                     set="Earthset", rise="Earthrise", term="Earthset", wait="saldrá", leave="se pondrá"),
}
_BADGE = {VisibilityState.VISIBLE: ("green", ":material/visibility:"), VisibilityState.PARTIAL: ("orange", ":material/contrast:"),
          VisibilityState.HIDDEN: ("red", ":material/visibility_off:")}
_STATE_WORD = {VisibilityState.VISIBLE: "visible", VisibilityState.PARTIAL: "parcialmente ocult{g}", VisibilityState.HIDDEN: "bloqueado"}


def _sw(state, body) -> str:
    """Estado en palabras con el género del cuerpo (el Sol: oculto; la Tierra: oculta)."""
    return _STATE_WORD[state].replace("{g}", "a" if body is Body.EARTH else "o").replace("bloqueado", "bloqueada" if body is Body.EARTH else "bloqueado")


# ------------------------------------------------------------------------------------------------ cursor (solo callbacks)
class _Grid:
    """Rejilla del análisis: instante ↔ índice de ``sky.et`` (paso uniforme desde el inicio del periodo)."""

    def __init__(self, res):
        self.start = S.parse_utc(res.request.start_utc)
        self.base_s = float(res.request.step_s)
        self.n = len(res.sky.et)

    def idx(self, utc: str) -> int:
        off = (S.parse_utc(utc) - self.start).total_seconds()
        return max(0, min(self.n - 1, round(off / self.base_s)))

    def utc(self, i: int):
        return self.start + timedelta(seconds=i * self.base_s)


def _goto(g: _Grid, i: int) -> None:
    S.set_state(K.CURSOR_UTC, S.fmt_utc(g.utc(max(0, min(g.n - 1, i)))))


def _on_slider(g: _Grid) -> None:
    _goto(g, g.idx(S.fmt_utc(st.session_state[_T])))


def _shift(g: _Grid, sign: int) -> None:
    k = round(60 * int(st.session_state[_STEP]) / g.base_s)
    _goto(g, g.idx(S.get_str(K.CURSOR_UTC)) + sign * max(k, 1))


def _fmt_step(m: int) -> str:
    return f"{m} min" if m < 60 else (f"{m // 60} h" if m < 1440 else "1 día")


# ------------------------------------------------------------------------------------------------ tarjetas y texto
def _countdowns(req, utc: str) -> dict:
    """Cuenta atrás por cuerpo desde ``utc`` + siguiente transición posterior (sin recalcular el análisis)."""
    try:
        cds = cache.countdowns_at(req, utc)
    except (LSIError, ValueError) as e:
        C.show_error(e)
        return {}
    out = {}
    for cd in cds:
        nxt = None
        if cd.next_event is not None:
            try:
                t2 = export.et_to_utc_str(cd.next_event.et + 120.0)[:-1]
                nxt = next(c for c in cache.countdowns_at(req, t2) if c.body == cd.body).next_event
            except (LSIError, ValueError, StopIteration):
                nxt = None
        out[cd.body] = (cd, nxt)
    return out


def _card(cd, nxt) -> None:
    nm = _NAME[cd.body]
    label = nm["up"] if cd.currently_up else nm["down"]
    if cd.seconds_until is None:
        C.metric_card(label, f"más de {C.fmt_num(cd.searched_days, 0)} d", help=f"No hay transición en los próximos {C.fmt_num(cd.searched_days, 0)} días.",
                      help_term=None)
        st.caption(f"Sin {nm['set'] if cd.currently_up else nm['rise']} en los próximos {C.fmt_num(cd.searched_days, 0)} días: "
                   f"{nm['art']} {'sigue arriba' if cd.currently_up else 'sigue oculta' if cd.body is Body.EARTH else 'sigue oculto'} en todo ese tramo.")
        return
    C.metric_card(label, ("≈ " if cd.approximate_due_to_coverage else "") + C.fmt_duration(cd.seconds_until),
                  help_term=nm["term"] if nm["term"] in C.GLOSSARY else None)
    ev = cd.next_event
    st.caption(f"{nm['set' if cd.currently_up else 'rise'].capitalize()}: {export.et_to_utc_str(ev.et).replace('T', ' ')} "
               f"(az {C.fmt_num(ev.az_deg, 1)}°){' · truncada por el borde del periodo' if ev.truncated else ''}")
    if nxt is not None:
        st.caption(f"Después: {nm['rise' if cd.currently_up else 'set']} en {C.fmt_duration(nxt.et - cd.now_et)} "
                   f"({export.et_to_utc_str(nxt.et).replace('T', ' ')})")
    if cd.approximate_due_to_coverage:
        st.caption(":material/warning: Aproximado: depende de un tramo de horizonte limitado por la cobertura del DEM.")


def _in(ws, et: float):
    """Ventana de ``ws`` que contiene ``et`` (o None)."""
    return next((w for w in ws.windows if w.start_et <= et < w.end_et), None)


def _link_caption(res, et: float) -> None:
    """Fin del ENLACE (no de la Tierra) a partir de lo que entrega el pipeline (``res.link``); no recalcula física.

    Causa del fin: si la red sigue viendo la Luna justo después, es la Tierra (puesta o bajada del margen de elevación) quien lo corta;
    si no, es la cobertura de las estaciones.
    """
    lk = res.link
    if lk is None:
        st.caption("Earthset = la Tierra se pone en el horizonte del lander (geometría). Sin red de estaciones no se calcula el enlace.")
        return
    st.caption("Earthset = la Tierra se pone en el horizonte del lander (geometría). El **enlace** puede acabar antes: exige además margen de "
               f"elevación ({C.fmt_num(lk.min_earth_elevation_deg, 0, '°')}) y una estación de la red {lk.network_label} viendo la Luna.")
    w = _in(lk.link, et)
    if w is None:
        nxt = next((x for x in lk.link.windows if x.start_et > et), None)
        st.caption(":material/signal_disconnected: **Ahora no hay enlace posible.** " + (
            f"Vuelve en {C.fmt_duration(nxt.start_et - et)} ({export.et_to_utc_str(nxt.start_et).replace('T', ' ')})." if nxt is not None
            else "No vuelve en lo que queda de periodo."))
        return
    if w.right_truncated:
        st.caption(":material/satellite_alt: **Hay enlace posible** hasta el final del periodo analizado (el fin del enlace queda fuera).")
        return
    step = float(res.request.step_s)
    by_station = _in(lk.network_cover, w.end_et + step) is not None
    cause = ("la Tierra baja del margen de elevación o se pone en el horizonte del lander" if by_station
             else "ninguna estación de la red ve ya la Luna (fin de la cobertura de estación)")
    st.caption(f":material/satellite_alt: **Fin del enlace** en {C.fmt_duration(w.end_et - et)} "
               f"({export.et_to_utc_str(w.end_et).replace('T', ' ')} UTC): {cause}.")


def _sentence(res, tr, st_, cd, i) -> str:
    nm = _NAME[tr.body]
    el, rho = float(tr.el_deg[i]), float(tr.radius_deg[i])
    when = ""
    if cd is not None:
        verb = nm["leave"] if cd.currently_up else nm["wait"]
        when = (f"; {verb} en {C.fmt_duration(cd.seconds_until)}" if cd.seconds_until is not None
                else f"; no cambiará en los próximos {C.fmt_num(cd.searched_days, 0)} d")
    if st_ == VisibilityState.VISIBLE:
        return f"Ahora mismo {nm['art']} se ve completo, a {C.fmt_num(el, 1)}° sobre el horizonte{when}."
    if st_ == VisibilityState.PARTIAL:
        return f"Ahora mismo {nm['art']} está parcialmente tapad{'a' if tr.body is Body.EARTH else 'o'} por el horizonte{when}."
    behind_relief = res.observer.mode is HorizonMode.DEM and el + rho > res.horizon.h_sphere_deg + 0.01
    why = "tras una cresta del relieve" if behind_relief else "bajo el horizonte"
    return f"Ahora mismo {nm['art']} está ocult{'a' if tr.body is Body.EARTH else 'o'} {why}{when}."


# ------------------------------------------------------------------------------------------------ cuerpo animable
def _body(req, res, g: _Grid) -> None:
    if st.session_state.get(_PLAY):          # único sitio que escribe fuera de un callback: el tic de la animación
        k = max(round(60 * int(st.session_state.get(_STEP, _STEPS_MIN[0])) / g.base_s), 1)
        i = g.idx(S.get_str(K.CURSOR_UTC)) + k
        _goto(g, i if i < g.n else 0)
    i = g.idx(S.get_str(K.CURSOR_UTC))
    cur = g.utc(i)
    st.session_state[_T] = cur              # el slider refleja siempre el estado canónico

    base_min = g.base_s / 60.0
    steps = [m for m in _STEPS_MIN if m >= base_min and abs(m / base_min - round(m / base_min)) < 1e-9] or [round(base_min)]
    if st.session_state.get(_STEP) not in steps:
        st.session_state[_STEP] = steps[0]
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.button("Paso atrás", icon=":material/skip_previous:", on_click=_shift, args=(g, -1), key="_hv_back")
    c2.button("Paso adelante", icon=":material/skip_next:", on_click=_shift, args=(g, +1), key="_hv_fwd")
    c3.selectbox("Paso del cursor y de la animación", steps, format_func=_fmt_step, key=_STEP)
    st.button("Ir al inicio del periodo", on_click=_goto, args=(g, 0), key="_hv_start",
              help="El instante inspeccionado se conserva al cambiar de sitio; este botón lo devuelve al comienzo del periodo.")
    last = g.utc(g.n - 1)
    st.slider("Fecha y hora (UTC)", min_value=g.start, max_value=last, step=timedelta(minutes=int(st.session_state[_STEP])),
              format="YYYY-MM-DD HH:mm", key=_T, on_change=_on_slider, args=(g,),
              help="Mover el cursor no recalcula el análisis: usa las series ya calculadas.")

    sample_utc = export.et_to_utc_str(res.sky.et[i])
    st.markdown(f"**Instante inspeccionado:** {sample_utc.replace('T', ' ').replace('Z', ' UTC')}")
    counts = _countdowns(req, sample_utc[:-1])
    vis = res.timeline.series
    h = res.horizon

    # ---- tarjetas de cuenta atrás (lo que más pide el reto) + elevación solar
    cols = st.columns(3)
    for col, body in zip(cols[:2], (Body.SUN, Body.EARTH)):
        with col:
            if body in counts:
                _card(*counts[body])
            if body is Body.EARTH:
                _link_caption(res, float(res.sky.et[i]))
    with cols[2]:
        C.metric_card("Elevación solar actual", float(res.sky.sun.el_deg[i]), unit="°", nd=2, help_term="Elevación",
                      help="Más elevación solar suele implicar más potencia, según el panel y el montaje (ver Potencia y paneles).",
                      delta=f"máx. del periodo {C.fmt_num(res.metrics.max_sun_elevation_deg, 1, '°')}", )
        st.caption("Afecta a la potencia disponible de los paneles.")

    # ---- estado de cada cuerpo
    tracks = {Body.SUN: res.sky.sun, Body.EARTH: res.sky.earth}
    states = {b: HP.body_state(h, tr, i, vis) for b, tr in tracks.items()}
    scol = st.columns(2)
    for col, (b, tr) in zip(scol, tracks.items()):
        color, icon = _BADGE[states[b]]
        with col:
            st.markdown(f":{color}-badge[{icon} {_NAME[b]['Art']}: {_sw(states[b], b)} ({C.state_label(states[b])})]")
            bv = vis.sun if b == Body.SUN else vis.earth
            if bool(bv.unknown_relevant[i]):
                st.caption("Su estado depende de un azimut con horizonte limitado por cobertura: puede estar más tapado de lo mostrado.")
            if S.is_public():
                st.write(_sentence(res, tr, states[b], counts.get(b, (None,))[0], i))

    # ---- gráficos
    lim = float(h.limited.mean()) if res.observer.mode is HorizonMode.DEM and h.limited.size else 0.0
    if lim > 0:
        st.warning(f"{HP.LIMITED_LABEL}: {C.fmt_pct(lim, 0)} de los azimutes (tramos rayados). Ahí el horizonte real puede ser "
                   "más alto y el Sol o la Tierra, más difíciles de ver.", icon=":material/warning:")
    if res.observer.mode is HorizonMode.SMOOTH_SPHERE:
        st.info("Modo esfera lisa: la línea gris es solo la curvatura lunar, sin relieve. Es un caso optimista.", icon=":material/public:")
    sun, ea = tracks[Body.SUN], tracks[Body.EARTH]
    alt = (f"Horizonte 360° del punto con el Sol (az {C.fmt_num(sun.az_deg[i] % 360, 0)}°, elevación {C.fmt_num(sun.el_deg[i], 1)}°, "
           f"{_sw(states[Body.SUN], Body.SUN)}) y la Tierra (az {C.fmt_num(ea.az_deg[i] % 360, 0)}°, elevación {C.fmt_num(ea.el_deg[i], 1)}°, "
           f"{_sw(states[Body.EARTH], Body.EARTH)}) el {cur:%Y-%m-%d %H:%M} UTC.")
    C.no_visibility(res)
    tab1, tab2 = st.tabs(["Perfil azimut–elevación", "Vista polar del cielo"])
    with tab1:
        C.accessible_chart(HP.horizon_cartesian(h, res.sky, vis, i, show_band=not S.is_public()), alt, key="_hv_cart")
    with tab2:
        C.accessible_chart(HP.horizon_polar(h, res.sky, vis, i), alt, key="_hv_polar")

    # ---- datos numéricos (Planificador / Experto)
    if C.show_for("planificador"):
        rows = []
        for b, tr in tracks.items():
            az, el, rho = float(tr.az_deg[i]) % 360.0, float(tr.el_deg[i]), float(tr.radius_deg[i])
            hz = theme.periodic_interp(az, h.az_deg, h.h_lb_deg)
            hub = theme.periodic_interp(az, h.az_deg, h.h_ub_deg) if h.h_ub_deg is not None else float("nan")
            bv = vis.sun if b == Body.SUN else vis.earth
            rows.append({"Cuerpo": _NAME[b]["Art"].split()[-1], "Azimut (°)": C.fmt_num(az, 2), "Elevación (°)": C.fmt_num(el, 3),
                         "Radio angular (°)": C.fmt_num(rho, 3), "Distancia (km)": C.fmt_num(float(tr.dist_km[i]), 0),
                         "H_lb en ese azimut (°)": C.fmt_num(hz, 3), "H_ub (°)": C.fmt_num(hub, 3),
                         "Margen el − ρ − H_lb (°)": C.fmt_num(el - rho - hz, 3), "Fracción visible": C.fmt_pct(float(bv.f[i]), 1),
                         "Estado": C.state_label(states[b])})
        st.markdown("**Valores numéricos en el instante inspeccionado**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if C.show_for("experto"):
        with st.expander("Horizonte exacto por azimut"):
            st.dataframe(pd.DataFrame({"Azimut (°)": h.az_deg, "H_lb (°)": h.h_lb_deg,
                                       "H_ub (°)": h.h_ub_deg if h.h_ub_deg is not None else float("nan"),
                                       "Cobertura r_cov (m)": h.r_cov_m,
                                       "Limitado": ["sí" if x else "no" for x in h.limited]}), hide_index=True, width="stretch")
            st.caption(f"Esfera lisa (suelo analítico): {C.fmt_num(h.h_sphere_deg, 4)}° · cobertura mínima {C.fmt_num(h.cov_min_m, 0, 'm')} · "
                       f"mediana {C.fmt_num(h.cov_median_m, 0, 'm')}.")


# ------------------------------------------------------------------------------------------------ página
st.title("Horizonte y visibilidad")
req = S.request_or_stop()
res, err = cache.try_analysis(req)
if err:
    C.warnings_band()
    C.show_error(err)
    st.stop()
C.warnings_band(res)
C.result_header(res)
C.public_note("Aquí ves dónde están el Sol y la Tierra en el cielo del lugar elegido y cuánto falta para que se oculten "
              "tras el horizonte. Mueve el deslizador para cambiar la hora.")
st.toggle("Reproducir animación", key=_PLAY, help="Avanza el cursor un paso cada segundo; se detiene al desactivarlo.")
st.fragment(run_every=1.0 if st.session_state.get(_PLAY) else None)(_body)(req, res, _Grid(res))
