"""Capacidad del sitio: la pantalla estrella. «Según la ubicación, qué conectividad y qué energía solar tendría un lander».

Dos bloques simétricos, SOLAR y CONECTIVIDAD, cada uno con cifras clave, rango de incertidumbre (o «no calculado» con botón) y
procedencia del dato. Debajo: curva del día y comparación de paneles/montajes, sensibilidad al margen de la antena, tabla por base
terrestre (UTC, hora local civil con zona y hora solar media) y gráfico de contactos.

La página NO calcula física: pinta lo que devuelven ``ui.cache`` (``get_analysis``, ``get_power``, ``get_margin_sensitivity``) y
``lsi.visualization``. Solo agrega lo ya calculado (medias sobre días, formato de horas). Widgets propios ``_sc_*``; el estado
compartido solo se escribe desde callbacks.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import streamlit as st

from lsi.analysis.site_score import profiles_from_config
from lsi.astronomy import ground_stations as gs
from lsi.contracts import HorizonMode, MountingSpec, MountingType, PowerParams, StateKey as K, et_to_utc_datetime, \
    utc_datetime_to_et, utc_midnight_et
from lsi.energy import panels as pn
from lsi.visualization import capacity_plot, contact_plot, donut_plot, theme
from lsi.visualization.horizon_plot import horizon_cartesian
from lsi.visualization.sky_plot import sky_polar
from ui import cache, components as C, state as S

MAX_CHART_DAYS = 31


# ------------------------------------------------------------------------------------------------ utilidades
def _et(s: str) -> float:
    return utc_datetime_to_et(S.parse_utc(s))


def _hhmm(h: float) -> str:
    m = int(round(h * 60.0)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _hours(s: float | None) -> float | None:
    return None if s is None else s / 3600.0


def _mean(et, y, t0: float, t1: float) -> float:
    """Media temporal (trapecio) de ``y(et)`` en [t0, t1]; solo agrega una serie ya calculada."""
    et, y = np.asarray(et, float), np.asarray(y, float)
    m = (et > t0) & (et < t1)
    td = np.concatenate(([t0], et[m], [t1]))
    yd = np.interp(td, et, y)
    return float(np.sum(0.5 * (yd[1:] + yd[:-1]) * np.diff(td)) / (t1 - t0)) if t1 > t0 else float(yd[0])


def _tzname(local_str: str) -> str:
    return local_str.rsplit(" ", 1)[-1]


def _range_line(r, fmt) -> str | None:
    if r is None:
        return None
    if abs(r[1] - r[0]) < 1e-9:      # ancho cero: los escenarios no mueven la cifra (no es certeza)
        return f"Rango de incertidumbre: sin variación ({fmt(r[0])}; los escenarios no la mueven)"
    return f"Rango de incertidumbre: {fmt(r[0])} – {fmt(r[1])}"


def _scope_ranges(res, window: bool) -> dict:
    """{'sun','dark_h','link','gap_h'} → (lo, hi) desde los escenarios de incertidumbre ya calculados; {} si no se calcularon."""
    if window:
        inp = [res.score_inputs, *res.score_scenarios] if res.score_scenarios and res.score_inputs is not None else []
        if len(inp) < 2:
            return {}
        rng = lambda vals: (min(vals), max(vals)) if vals else None   # noqa: E731
        out = {"sun": rng([i.f_sun for i in inp]), "dark_h": rng([i.d_max_h for i in inp])}
        if all(i.link_mode for i in inp):
            out["link"] = rng([i.f_earth for i in inp])
            out["gap_h"] = rng([i.max_link_gap_h for i in inp if i.max_link_gap_h is not None])
        return {k: v for k, v in out.items() if v}
    if res.uncertainty is None:
        return {}
    r = res.uncertainty.ranges
    pick = lambda k, f=1.0: (r[k].lo * f, r[k].hi * f) if k in r else None   # noqa: E731
    out = {"sun": pick("solar_fraction"), "dark_h": pick("max_darkness_s", 1 / 3600.0),
           "link": pick("link_fraction"), "gap_h": pick("max_link_gap_s", 1 / 3600.0)}
    return {k: v for k, v in out.items() if v}


def _link_gap(link, t0: float, t1: float) -> tuple[float, float, bool]:
    """(inicio_et, fin_et, vuelve) del hueco más largo sin enlace en [t0, t1], desde la unión de ventanas ya calculada.
    ``vuelve`` = False si el hueco llega al final del periodo (el enlace no regresa dentro de él)."""
    ws = sorted((max(w.start_et, t0), min(w.end_et, t1)) for w in link.link.windows if w.end_et > t0 and w.start_et < t1)
    if not ws:
        return t0, t1, False
    gaps = [(t0, ws[0][0])] + [(a[1], b[0]) for a, b in zip(ws, ws[1:])] + [(ws[-1][1], t1)]
    a, b = max(gaps, key=lambda g: g[1] - g[0])
    return a, b, b < t1 - 1e-6


def _first_contact(link, t: float):
    """Primer contacto que termina después de ``t`` (el que recupera el enlace tras un hueco que acaba en ``t``)."""
    return min((c for c in link.contacts if c.end_et > t), key=lambda c: c.start_et, default=None)


def _utc_txt(et: float) -> str:
    return et_to_utc_datetime(et).strftime("%d/%m/%Y %H:%M")


def _direction_block(res, req) -> None:
    """Cobertura de la red por sentido del enlace (la calcula el núcleo: ``res.network_fraction_by_direction``) y cuál se usa."""
    fr = res.network_fraction_by_direction
    if not fr:
        return
    chosen = req.link_direction
    st.markdown("**Cobertura de la red según el sentido del enlace** (periodo completo)")
    st.dataframe(pd.DataFrame([{"Sentido": S.LINK_DIRECTIONS[d] + (" ← el elegido" if d == chosen else ""),
                                "La red ve la Luna (%)": C.fmt_num(100 * fr[d], 1)} for d in ("receive", "transmit", "both") if d in fr]),
                 hide_index=True, width="stretch")
    st.caption(f"Sentido elegido: **{S.LINK_DIRECTION_NAMES.get(chosen, chosen)}** (cámbialo en la barra lateral). Recibir datos de la nave "
               f"exige menos elevación de antena (6° en el DSN) que enviarle órdenes (10,1°, norma 810-005): por eso la transmisión "
               f"(comandos) tiene menos cobertura que la recepción" + (f", aquí {C.fmt_num(100 * fr['receive'], 0)} % frente a "
               f"{C.fmt_num(100 * fr['transmit'], 0)} %" if "receive" in fr and "transmit" in fr else "") + ". «Ambos» es la intersección.")


def _quick_read(m, link) -> str:
    """Lectura rápida en lenguaje llano: Sol, enlace, noche mayor, hueco mayor y estaciones NASA (DSN) que darían el enlace."""
    sun = C.fmt_pct(m.solar_fraction)
    dark = ("al menos " if m.max_darkness_truncated else "") + C.fmt_num(_hours(m.max_darkness_s), 1, "h")
    if link is None or m.link_fraction is None:
        return (f"En este punto tendrás Sol {sun} del tiempo y la Tierra a la vista {C.fmt_pct(m.earth_fraction)}; la mayor noche dura "
                f"{dark}. El enlace no se calcula (red en «solo geometría»).")
    gap = C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated)
    nasa = [s.complex or s.station_id for s in link.stations if s.station_id.startswith("DSS-") and s.link_fraction > 0]
    st_txt = ("las estaciones NASA que lo darían son " + ", ".join(nasa)) if nasa else "ninguna estación NASA (DSN) lo daría"
    return (f"En este punto tendrás Sol {sun} y enlace con la Tierra {C.fmt_pct(m.link_fraction)} del tiempo; la mayor noche dura "
            f"{dark} y el mayor hueco de comunicaciones {gap}; {st_txt}.")


def _on_panels() -> None:
    ids = list(st.session_state["_sc_panels"])
    st.session_state[S.PANEL_IDS] = ids
    st.session_state[K.PANEL_ID] = ids[0] if ids else None


def _on_sens() -> None:
    st.session_state["_sc_sens_on"] = True


def _mount_label(m: MountingSpec) -> str:
    extra = f" {m.tilt_deg:g}°" if m.type is MountingType.TILTED and m.tilt_deg is not None else ""
    return C.MOUNT_LABELS.get(m.type.value, m.type.value) + extra


# ------------------------------------------------------------------------------------------------ arranque
POLAR_LEAD = ("El polo sur de la Luna es un sitio difícil: el Sol apenas asoma sobre el horizonte y las montañas proyectan sombras "
              "larguísimas, así que unos kilómetros cambian días enteros de luz; además la Tierra puede quedar escondida tras el relieve. "
              "Aquí ves, para un lugar y unas fechas, cuánta luz y cuántas comunicaciones tendría un módulo de aterrizaje.")


def _evidence_chip(panel) -> str:
    """Chip de evidencia del panel (nivel declarado en el catálogo) para la tarjeta de potencia."""
    color, _icon, text = C.EVIDENCE_BADGE.get(getattr(panel, "evidence_level", "") or "", ("gray", "", "Evidencia: sin clasificar"))
    kind = {"green": "ok", "blue": "info", "orange": "warn", "red": "bad"}.get(color, "nodata")
    return C.chips(C.chip(text.replace("Evidencia: ", "Evidencia · "), kind, "⚗" if kind in ("warn", "bad") else "✔"))


def _mini_map(res) -> None:
    """Mini-mapa topográfico del entorno (``relief_map.relief_map_figure(..., compact=True)``, relieve sombreado + pendiente con el punto
    marcado). Sin DEM o si algo falla, un hueco explicado: nunca rompe la pantalla."""
    o = res.observer
    try:
        from lsi.visualization.relief_map import relief_map_figure
        win = cache.get_mini_window(o.dem_key, float(o.x_m), float(o.y_m)) if o.mode is HorizonMode.DEM and o.dem_key else None
        if win is not None:
            fig = relief_map_figure(win, o, layer="slope", compact=True, height=300)
            C.accessible_chart(fig, "Mapa de pendiente sobre relieve sombreado alrededor del punto elegido (rombo ámbar); "
                               "más claro es más inclinado.", key="_sc_minimap")
            return
        why = ("Aquí solo hay el DEM polar de 80 m (relieve aproximado): no hay mapa de pendiente de aterrizaje ni relieve fino que dibujar."
               if o.mode is HorizonMode.FAR_FIELD else "Sin mapa de terreno en este punto (esfera lisa): no hay relieve que dibujar.")
    except Exception as e:      # noqa: BLE001 - un mapa roto no debe tirar la página
        why = f"No se pudo dibujar el mini-mapa topográfico ({type(e).__name__})."
    st.markdown(f'<div class="lsi-card-empty"><b>Mapa del entorno</b><span>{C.esc(why)}</span></div>', unsafe_allow_html=True)


def _dashboard(res, m, link, t0: float, t1: float, scope_txt: str) -> None:
    """Panel de control: anillos de Sol y Tierra/enlace con su curva diaria, cielo polar con la trayectoria del Sol y la Tierra sobre el
    horizonte real, y el perfil del horizonte. TODO sale de ``res``; sin dato no hay tarjeta."""
    days = [d for d in res.daily if d["end_et"] > t0 and d["start_et"] < t1 and d["end_et"] - d["start_et"] >= 86399.0] or         [d for d in res.daily if d["end_et"] > t0 and d["start_et"] < t1]
    xs = [d["day_utc"][5:] for d in days]
    has_link = link is not None and m.link_fraction is not None
    ekey = "link_hours" if has_link and days and "link_hours" in days[0] else "earth_hours"
    sun_fig = donut_plot.donut(m.solar_fraction, color=theme.SUN, on="Con Sol", off="Sin Sol", center=C.fmt_pct(m.solar_fraction, 1),
                               sub="del tiempo con Sol")
    ef = m.link_fraction if has_link else m.earth_fraction
    earth_fig = donut_plot.donut(ef, color=theme.EARTH, on="Enlace posible" if has_link else "Tierra a la vista",
                                 off="Sin enlace" if has_link else "Tierra oculta", center=C.fmt_pct(ef, 1),
                                 sub="con enlace posible" if has_link else "con la Tierra a la vista")
    with st.container(key="lsi-dash"):
        c1, c2, c3 = st.columns(3, gap="small")
        with c1, st.container(border=True, key="lsi-card-sun"):
            C.card_head("☀", "Luz del Sol", f"Cifras sobre: {scope_txt}", "sun")
            if sun_fig is not None:
                C.accessible_chart(sun_fig, f"Anillo: el Sol se ve el {C.fmt_pct(m.solar_fraction, 1)} del tiempo ({scope_txt}).", key="_sc_donut_sun")
            curve = donut_plot.area_curve(xs, [d["sun_hours"] for d in days], color=theme.SUN, name="Horas de Sol", unit="h/día", x_title="Día (mes-día, UTC)")
            if curve is not None:
                C.accessible_chart(curve, "Horas de Sol por día UTC a lo largo del periodo; el eje vertical va de 0 a 24 h.", key="_sc_curve_sun")
            C.stat_rows([("Noche máxima", ("≥ " if m.max_darkness_truncated else "") + C.fmt_num(_hours(m.max_darkness_s), 1, "h")),
                         ("Ventana solar más larga", C.fmt_duration(m.longest_sun_window_s, m.longest_sun_window_truncated))], "sun")
        with c2, st.container(border=True, key="lsi-card-earth"):
            C.card_head("◍", "Comunicación con la Tierra" if has_link else "Tierra a la vista",
                        f"Cifras sobre: {scope_txt}", "earth")
            if earth_fig is not None:
                C.accessible_chart(earth_fig, f"Anillo: {'enlace posible' if has_link else 'Tierra sobre el horizonte'} el {C.fmt_pct(ef, 1)} del tiempo ({scope_txt}).",
                                   key="_sc_donut_earth")
            curve = donut_plot.area_curve(xs, [d.get(ekey, 0.0) for d in days], color=theme.EARTH,
                                          name="Horas de enlace" if ekey == "link_hours" else "Horas con Tierra", unit="h/día", x_title="Día (mes-día, UTC)")
            if curve is not None:
                C.accessible_chart(curve, f"Horas {'con enlace posible' if ekey == 'link_hours' else 'con la Tierra a la vista'} por día UTC; eje de 0 a 24 h.",
                                   key="_sc_curve_earth")
            C.stat_rows([("Hueco máximo sin enlace", C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated) if has_link else ""),
                         ("Ventana de enlace más larga", C.fmt_duration(m.longest_link_window_s, m.longest_link_window_truncated) if has_link else ""),
                         ], "earth")
        with c3, st.container(border=True, key="lsi-card-sky"):
            C.card_head("◎", "Cielo desde el punto", "Trayectoria del Sol y de la Tierra sobre el horizonte real")
            C.accessible_chart(sky_polar(res.horizon, res.sky),
                               "Vista polar del cielo, norte arriba: el terreno en gris tapa parte del cielo; el Sol (ámbar, círculos) y la Tierra (cian, rombos) "
                               f"recorren el cielo durante el periodo; en línea continua cuando se ven y punteados cuando el relieve los tapa. "
                               f"El Sol llega a {C.fmt_num(res.metrics.max_sun_elevation_deg, 1, '°')} de elevación y la Tierra a "
                               f"{C.fmt_num(res.metrics.max_earth_elevation_deg, 1, '°')}.", key="_sc_sky")
            C.stat_rows([("Elevación máxima del Sol", C.fmt_num(m.max_sun_elevation_deg, 1, "°")),
                         ("Elevación máxima de la Tierra", C.fmt_num(m.max_earth_elevation_deg, 1, "°"))])
    with st.container(key="lsi-dash2"):
        d1, d2 = st.columns([2, 1], gap="small")
        with d1, st.container(border=True, key="lsi-card-horizon"):
            C.card_head("⛰", "Perfil del horizonte", "Elevación del terreno en cada dirección (0° = Norte)")
            fig = theme.compact(horizon_cartesian(res.horizon, None, None, 0, show_band=False), 300)
            C.accessible_chart(fig, "Perfil de horizonte: elevación del terreno (relleno gris) frente al azimut de 0 a 360°; las zonas rayadas son azimutes "
                               "donde la cobertura del mapa es limitada (cota inferior).", key="_sc_horizon")
        with d2, st.container(border=True, key="lsi-card-key"):
            C.card_head("★", "Datos clave")
            sc = res.score
            rows = [("Elevación solar máxima", C.fmt_num(m.max_sun_elevation_deg, 1, "°")),
                    ("Mejor fecha", C.fmt_utc_short(sc.best_start_utc) if sc is not None and sc.best_start_utc else ""),
                    ("Nota (score)", f"{C.fmt_num(sc.score, 0)} / 100" if sc is not None else "")]
            rows += [(k, v) for k, v, _ in C.slope_facts(res)[:1]]
            C.stat_rows(rows)
            st.caption("La nota resume, no decide: el veredicto lo dan las comprobaciones mínimas.")


ctx = cache.get_context()
ss = st.session_state
req = S.request_or_stop()
st.title("Capacidad del sitio")
if S.is_public():
    st.markdown(f'<p class="lsi-lead">{C.esc(POLAR_LEAD)}</p>', unsafe_allow_html=True)
else:
    st.caption("Qué conectividad con la Tierra y qué energía solar tendría una misión en este lugar.")
unc_on = st.toggle("Mostrar rangos de incertidumbre", value=True, key="_sc_unc_on",
                   help="Repite el cálculo con escenarios de sensibilidad (terreno, discretización, altura) para dar un rango bajo cada cifra. "
                        "El primer cálculo es más lento; después queda en caché. Desactívalo para una respuesta inmediata.")
req = dataclasses.replace(req, with_uncertainty=unc_on)
res, err = cache.try_analysis(req)
if err:
    C.show_error(err)
    C.warnings_band()
    st.stop()

_cold = cache.cold_seconds(req)
if unc_on and _cold is not None and _cold >= cache.COLD_SPINNER_S:
    st.caption(f":material/timer: El primer cálculo con rangos tardó {C.fmt_num(_cold, 1, 's')}; ahora está en caché.")
o, m_all, sc = res.observer, res.metrics, res.score
profiles = profiles_from_config(ctx.cfg["score"])
prof = profiles.get(req.score_profile_id)
prof_label = prof.label if prof else req.score_profile_id
by_id = {p.id: p for p in ctx.panels.panels}
mission_days = S.effective_mission_days(ctx)

has_window = (sc is not None and sc.window_start_utc is not None and res.window_metrics is not None
              and sc.mission_days is not None and not sc.partial)
period_txt = f"{C.fmt_utc_short(req.start_utc)} → {C.fmt_utc_short(req.end_utc)} ({C.fmt_num(m_all.period_s / 86400.0, 1)} d)"
window = False
if has_window and (sc.window_start_utc != req.start_utc or sc.window_end_utc != req.end_utc):
    window = st.radio("Las cifras de abajo son sobre", ["la ventana de misión", "el periodo completo"], horizontal=True,
                      key="_sc_scope", help="La ventana de misión es el tramo (de la duración del perfil) que empieza en la mejor fecha.") \
        == "la ventana de misión"
t0, t1 = (_et(sc.window_start_utc), _et(sc.window_end_utc)) if window else (res.timeline.et0, res.timeline.et1)
scope_txt = "ventana de misión" if window else "periodo completo"
m = res.window_metrics if window else m_all
link = (res.link_window or res.link) if window else res.link
rngs = _scope_ranges(res, window)
quick = _quick_read(m, link)

# --- (A) lugar y fecha sugeridos (estado inicial positivo) + HERO
sug = ss.get(S.SUGGESTED)
if S.is_suggested():
    st.markdown(f'<div class="lsi-suggest"><span><b>Lugar y fecha sugeridos:</b> el mejor candidato del mapa de idoneidad '
                f'(nota {C.esc(C.fmt_num(sug["score"], 0))} de 100), en su mejor fecha de inicio, {C.esc(sug["start_utc"][:10])}. '
                f'Un candidato no es una certificación.</span></div>', unsafe_allow_html=True)
    C.safe_page_link(C.SEARCH_PAGE, "Cambiar de lugar (Buscador)", ":material/search:")
    C.safe_page_link(C.BEST_SPOTS_PAGE, "Ver otros candidatos y fechas", ":material/event_available:")
with st.container(key="lsi-split"):
    hero_col, map_col = st.columns([5, 3], gap="medium")
with hero_col:
    verdict_chips = []
    if sc is not None:
        verdict_chips.append(C.verdict_chip(sc))
        if sc.confidence is not None:
            lv = sc.confidence.level.value
            verdict_chips.append(C.chip(f"Confianza {lv}", {"alta": "ok", "media": "cond"}.get(lv, "bad"), "◈"))
    if sc is not None and sc.verdict != "NO APTO":
        # El jurado (15/11) leyó «APTO 98» como más firme de lo que la validación respalda: se rotula a la vez.
        verdict_chips.append(C.chip("Candidato: no validado contra el mapa publicado (±0,2-0,3)", "warn", "⚠"))
    verdict_chips.append({"dem": C.chip("Relieve real (DEM)", "info", "⛰"), "far": C.chip(C.FAR_LABEL, "warn", "⛰"),
                          "sphere": C.chip("Esfera lisa: sin terreno", "warn", "◯")}[C.terrain_kind(o.mode)])
    if has_window:
        win_line = (f"{C.fmt_utc_short(sc.window_start_utc)} → {C.fmt_utc_short(sc.window_end_utc)} ({C.fmt_num(sc.mission_days, 1)} d)")
    else:
        win_line = "sin ventana (se evalúa todo el periodo)"
    best_line = C.best_date_sentence(sc) if sc is not None else "—"
    facts_hero = []
    if sc is not None:
        rt = C.range_text(sc)
        facts_hero.append(("Nota (score)", f"{C.fmt_num(sc.score, 0)} / 100",
                           "nota de la MEJOR fecha; el rango no incluye el sesgo de haberla elegido" if "(estrecho" in rt else rt.replace("Rango ", "rango ")))
        if sc.feasible_start_fraction is not None and (sc.n_starts or 0) > 1:
            facts_hero.append(("Fechas de inicio que sirven", f"{round(sc.feasible_start_fraction * sc.n_starts)} de {sc.n_starts}",
                               "con otras fechas el veredicto puede cambiar"))
    facts_hero += C.slope_facts(res)
    if m.link_fraction is not None:
        facts_hero.append(("Hueco máx. sin enlace", C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated), ""))
    _fr = res.network_fraction_by_direction or {}
    if "receive" in _fr and "transmit" in _fr:
        facts_hero.append(("La red ve la Luna", f"{C.fmt_num(100 * _fr['receive'], 0)} % al recibir · {C.fmt_num(100 * _fr['transmit'], 0)} % al enviar",
                           "enviar órdenes exige más elevación de antena (10,1° frente a 6°)"))
    st.markdown(C.hero_html(
        kicker="Lugar y fecha sugeridos" if S.is_suggested() else "Análisis del lugar",
        title=C.place_name(o.label),
        meta=[("Punto", f"{C.fmt_num(o.lat_deg, 4)}°, {C.fmt_num(o.lon_deg_e, 4)}°E · observador a {C.fmt_num(o.height_m, 1, 'm')}"),
              ("Ventana de misión", win_line + f" · perfil {prof_label}"), ] + ([("Periodo analizado", period_txt)] if has_window and (sc.window_start_utc != req.start_utc or sc.window_end_utc != req.end_utc) or not has_window else []),
        chips_html=C.chips(*verdict_chips),
        read="" if S.is_expert() else quick,
        why=(C.verdict_sentence(sc) if sc is not None else ""), facts=facts_hero), unsafe_allow_html=True)
    st.markdown(f"**Mejor fecha:** {best_line}")
with map_col:
    _mini_map(res)

# --- (A2) panel de control + franja de informe
_dashboard(res, m, link, t0, t1, scope_txt)
if sc is not None:
    C.mission_strip(res, key="cap")
C.credit_strip()

# --- (B) cabecera técnica + avisos (UN bloque plegable) + incertidumbre
C.result_header(res)
if o.mode is HorizonMode.FAR_FIELD:
    st.warning(f"**{C.FAR_LABEL}:** fuera de los recortes de 5 m el horizonte sale del DEM polar de 80 m. " + C.far_field_note(),
               icon=":material/terrain:")
if o.mode is HorizonMode.SMOOTH_SPHERE:
    st.warning("**Esfera lisa:** aquí no hay mapa de terreno, así que se calcula con el **horizonte plano** de una Luna sin relieve. "
               "Es optimista para la luz del Sol (una montaña cercana podría taparlo) y no afecta a dónde está la Tierra en el cielo.",
               icon=":material/public:")
C.warnings_band(res, power=True, notes=C.capacity_notes_list())
if not unc_on:
    st.caption(":material/straighten: **Rangos de incertidumbre desactivados.** Actívalos arriba para verlos bajo cada cifra clave.")
elif o.mode is HorizonMode.SMOOTH_SPHERE:
    rngs = {}      # sin terreno los escenarios no varían nada: lo = hi degenerado no es un rango
    st.caption(":material/straighten: **Rango de incertidumbre: no calculado.** Causa: esfera lisa, sin mapa de terreno; no hay "
               "escenarios de terreno que variar, así que las cifras no llevan rango (no significa que sean exactas).")
elif o.mode is HorizonMode.FAR_FIELD:
    rngs = {}
    st.caption(":material/straighten: **Rango de incertidumbre: no calculado.** Causa: relieve aproximado de 80 m; no hay σ del terreno "
               "ni escenarios de DEM que variar. El error medido del horizonte (aviso de arriba) es la referencia, no un rango.")
elif not rngs:
    st.caption(":material/straighten: **Rango de incertidumbre: no calculado.** "
               + (sc.range_note if sc is not None and sc.range_note else "no hay escenarios para este ámbito."))

facts: dict = {
    "lectura_rapida": quick,
    "lugar": o.label, "lat_deg": o.lat_deg, "lon_deg_e": o.lon_deg_e, "altura_observador_m": o.height_m,
    "modo_horizonte": {"dem": "DEM (relieve real)", "far": "relieve aproximado (80 m)", "sphere": "esfera lisa (horizonte plano)"}[C.terrain_kind(o.mode)],
    "periodo": {"inicio_utc": req.start_utc, "fin_utc": req.end_utc},
    "ventana_mision": {"inicio_utc": sc.window_start_utc, "fin_utc": sc.window_end_utc, "dias": sc.mission_days,
                       "perfil": prof_label} if has_window else None,
    "mejor_fecha": C.best_date_sentence(sc) if sc is not None else None, "ambito_de_las_cifras": scope_txt,
    "avisos": [n.replace("**", "") for n in C.capacity_notes_list()],
}

# ================================================================================================ (C) dos bloques simétricos
st.header("Resumen: sol y comunicaciones")
col_sun, col_link = st.columns(2)
GEOM = C.chips(C.chip("Geometría · SPICE + relieve", "sun", "☀"))

# ------------------------------------------------------------------------------------------------ SOLAR
panel = by_id.get(req.panel_id)
ps = res.power_summary
areal = getattr(panel, "areal_power_w_m2_am0", None) if panel is not None else None
solar_f: dict = {}
with col_sun:
    with st.container(border=True):
        st.markdown('<div class="lsi-block-title sun"><span class="dot"></span>Solar</div>'
                    f'<div class="lsi-block-sub">Cifras sobre: {C.esc(scope_txt)}.</div>', unsafe_allow_html=True)
        no_sun = not m.solar_fraction > 0
        cards = [
            C.kpi_html("Sol visible", C.fmt_pct(m.solar_fraction), tone="sun", chip_html=GEOM, sub=_range_line(rngs.get("sun"), C.fmt_pct),
                       help="Fracción del tiempo con alguna parte del disco solar sobre el horizonte. Es geometría: no es potencia."),
            C.kpi_html("Noche máxima", _hours(m.max_darkness_s), unit="h", truncated=m.max_darkness_truncated, tone="sun", chip_html=GEOM,
                       sub=_range_line(rngs.get("dark_h"), lambda v: C.fmt_num(v, 1, "h")),
                       help="La noche continua más larga (el Sol, oculto). Decide cuánto tendría que aguantar la batería o el calor."),
            C.kpi_html("Ventana solar más larga", C.fmt_duration(m.longest_sun_window_s, m.longest_sun_window_truncated), tone="sun",
                       chip_html=GEOM, help="El tramo seguido más largo con Sol."),
            C.kpi_html("Elevación solar máxima", m.max_sun_elevation_deg, unit="°", nd=1, tone="sun", chip_html=GEOM,
                       help="Lo alto que llega a subir el Sol sobre el horizonte local (en los polos, muy poco)."),
        ]
        solar_f = {"sol_visible_frac": m.solar_fraction, "ventana_solar_mas_larga_h": _hours(m.longest_sun_window_s),
                   "ventana_solar_truncada": m.longest_sun_window_truncated, "noche_maxima_h": _hours(m.max_darkness_s),
                   "noche_truncada": m.max_darkness_truncated, "elevacion_solar_max_deg": m.max_sun_elevation_deg,
                   "rango": {k: v for k, v in rngs.items() if k in ("sun", "dark_h")}}
        power_notes: list = []
        if panel is None:
            C.kpi_grid(*cards)
            st.info("No hay panel elegido: elige uno en «Paneles a comparar» (más abajo) o en la barra lateral.", icon=":material/solar_power:")
        elif ps is None or areal is None:
            C.kpi_grid(*cards)
            st.warning(f"El panel «{panel.name}» no tiene la eficiencia necesaria: no se puede dar potencia eléctrica (se muestra «sin dato», "
                       "nunca 0).", icon=":material/block:")
        else:
            mnt = res.power.mounting if res.power is not None else req.mounting
            days_in = [d for d in ps.daily if d.day_start_et < t1 and d.day_start_et + 86400.0 > t0] or list(ps.daily)
            whole = len(days_in) == len(ps.daily)
            mean_rel = ps.mean_p_rel if whole else float(np.mean([d.e_rel for d in days_in]))
            peak_rel = max(d.peak_p_rel for d in days_in)
            wh = [d.e_rel * 24.0 * areal for d in days_in]
            mean_w, peak_w = mean_rel * areal, peak_rel * areal
            band = None
            if getattr(panel, "ranges", None) and res.power is not None:
                th = ctx.cfg["power"]["thermal"]
                bnd = pn.power_band(res.power, panel, PowerParams(panel.id, mnt, t_ambient_k=float(th["t_ambient_k"]),
                                                                  t_min_valid_k=float(th["t_min_valid_k"])), ctx.panels)
                if bnd is not None:
                    lo_rel = _mean(res.power.et, bnd[0], t0, t1)
                    hi_rel = _mean(res.power.et, bnd[1], t0, t1)
                    s0 = ctx.panels.solar_constant_w_m2
                    e_lo, e_hi = panel.ranges.get("eta_bol", (panel.eta_bol, panel.eta_bol))
                    band = (min(lo_rel, mean_rel) * min(e_lo, e_hi) * s0, max(hi_rel, mean_rel) * max(e_lo, e_hi) * s0)
            ev = _evidence_chip(panel)
            cards += [
                C.kpi_html("Potencia eléctrica media", mean_w, unit="W/m²", nd=0, tone="sun", chip_html=ev,
                           sub=(f"{C.fmt_num(100 * mean_rel, 1)} % de la nominal · pico {C.fmt_num(peak_w, 0)} W/m²"
                                + ("" if band is None else f" · rango del panel {C.fmt_num(band[0], 0)} – {C.fmt_num(band[1], 0)}")),
                           help="Por metro cuadrado de panel: potencia relativa media × potencia nominal por m² (eficiencia inicial × "
                                "constante solar). Es de celda, sin empaquetado."),
                C.kpi_html("Energía por día (media)", float(np.mean(wh)), unit="Wh/m²", nd=0, tone="sun", chip_html=ev,
                           sub=(f"mínima {C.fmt_num(float(np.min(wh)), 0)} Wh/m²"
                                + ("" if band is None else f" · rango del panel {C.fmt_num(band[0] * 24, 0)} – {C.fmt_num(band[1] * 24, 0)}")),
                           help="Energía eléctrica diaria por m² de panel, media de los días del ámbito elegido. La mínima es el día que "
                                "dimensiona el sistema."),
            ]
            C.kpi_grid(*cards)
            st.caption(f"{panel.name} · montaje **{_mount_label(mnt)}**")
            C.mount_fallback_notice(req, panel.id, S.wanted_mount(None, o.lat_deg), mnt, ctx)
            C.evidence_badge(panel)
            if band is not None:
                st.caption(f"Banda de incertidumbre del panel (potencia media): {C.fmt_num(band[0], 0)} – {C.fmt_num(band[1], 0)} W/m². "
                           "Sale del rango de sus parámetros estimados (eficiencia, coeficiente de temperatura, absorción y emisividades).")
            else:
                st.caption("Sin banda de incertidumbre modelada: el panel usa datos de fuente y su dispersión (lotes, montaje, polvo) "
                           "no está cuantificada.")
            if C.show_for("experto"):
                st.markdown(f"`P [W/m²] = P_rel × W_nominal` con `W_nominal = η_BOL × S₀ = {C.fmt_num(100 * panel.eta_bol, 1)} % × "
                            f"{C.fmt_num(ctx.panels.solar_constant_w_m2, 0)} W/m² = {C.fmt_num(areal, 1)} W/m²` "
                            "y `P_rel = f_sol · cosθ · IAM · η_rel(T) · (UA/d)² · (1−degradación) · (1−polvo)` (matematica §6). "
                            "Energía diaria `Wh/m² = e_rel_día × 24 h × W_nominal`.")
            solar_f["panel"] = {"id": panel.id, "nombre": panel.name, "montaje": _mount_label(mnt), "grupo_evidencia": panel.evidence_group,
                                "nivel_evidencia": panel.evidence_level or None, "w_m2_nominal": areal,
                                "potencia_media_frac": mean_rel, "potencia_pico_frac": peak_rel, "w_m2_medio": mean_w, "w_m2_pico": peak_w,
                                "wh_m2_dia_medio": float(np.mean(wh)), "wh_m2_dia_min": float(np.min(wh)),
                                "banda_w_m2_medio": band}
        if no_sun:
            C.empty_state("No hay Sol visible en ningún momento de este periodo desde este punto: no habría energía solar. "
                          "Prueba otra fecha o busca el mejor punto.")
facts["solar"] = solar_f

# ------------------------------------------------------------------------------------------------ CONECTIVIDAD
link_f: dict = {}
link_gap_f = None
g7 = next((g for g in (sc.gates if sc is not None else ()) if g.id == "G7"), None)
LINKCHIP = C.chips(C.chip("Geometría + cobertura de la red", "earth", "◍"))
GEOCHIP = C.chips(C.chip("Solo geometría (Tierra sobre el horizonte)", "earth", "◍"))
with col_link:
    with st.container(border=True):
        st.markdown('<div class="lsi-block-title earth"><span class="dot"></span>Conectividad</div>'
                    f'<div class="lsi-block-sub">Cifras sobre: {C.esc(scope_txt)}.</div>', unsafe_allow_html=True)
        if link is None or m.link_fraction is None:
            C.kpi_grid(C.kpi_html("Tierra visible (geometría)", C.fmt_pct(m.earth_fraction), tone="earth", chip_html=GEOCHIP,
                                  help="Fracción del tiempo con la Tierra sobre el horizonte local. SOLO geometría: no es capacidad de comunicar."),
                       C.kpi_html("Enlace posible", "no calculado", tone="earth", help="La red está en «Solo geometría»."))
            st.info("Red de estaciones: **solo geometría**. No se calcula el enlace posible; cambia la red en la barra lateral "
                    "(modo Planificador).", icon=":material/satellite_alt:")
            link_f = {"red": "solo geometría", "tierra_visible_frac": m.earth_fraction, "enlace_posible_frac": None}
        else:
            net = link.network_label
            C.kpi_grid(
                C.kpi_html("Tierra visible (geometría)", C.fmt_pct(m.earth_fraction), tone="earth", chip_html=GEOCHIP,
                           help="Fracción del tiempo con la Tierra sobre el horizonte local. SOLO geometría: no es capacidad de comunicar."),
                C.kpi_html("ENLACE POSIBLE", C.fmt_pct(m.link_fraction), tone="earth", chip_html=LINKCHIP,
                           sub=_range_line(rngs.get("link"), C.fmt_pct),
                           help="Tierra visible con margen de antena Y al menos una estación viendo la Luna. Es una condición geométrica y de "
                                "cobertura, no un presupuesto de enlace RF."),
                C.kpi_html("Horas de contacto por día (media)", m.link_hours_per_day_mean, unit="h", nd=1, tone="earth", chip_html=LINKCHIP,
                           sub=f"mínima {C.fmt_num(m.link_hours_per_day_min, 1, 'h')}",
                           help="Horas al día con enlace posible, media de los días. La mínima es el día UTC completo con menos horas; «—» si "
                                "el periodo no contiene ningún día completo."),
                C.kpi_html("HUECO MÁXIMO sin enlace", C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated), tone="earth", chip_html=LINKCHIP,
                           sub=_range_line(rngs.get("gap_h"), lambda v: C.fmt_num(v, 1, "h")),
                           help="El tramo seguido más largo sin enlace posible."),
                C.kpi_html("Ventana de enlace más larga", C.fmt_duration(m.longest_link_window_s, m.longest_link_window_truncated), tone="earth",
                           chip_html=LINKCHIP, help="El tramo seguido más largo con enlace posible (con traspasos entre estaciones)."),
                C.kpi_html("Red de estaciones", net, tone="earth", chip_html=C.chips(C.chip(f"Margen de antena {C.fmt_num(link.min_earth_elevation_deg, 1, '°')}", "info", "∠")),
                           help="Procedencia: posiciones y elevación mínima en config/ground_stations.json (DSN 810-005 módulo 301 Rev. P; ESTRACK: "
                                "coordenadas NAIF, elevación mínima supuesta). El margen de antena del lander es una suposición."))
            gap_h = _hours(m.max_link_gap_s)
            limit = g7.limit if g7 is not None else None
            gate_txt = "Comprobación del hueco máximo" if S.is_public() else f"Puerta G7 ({'dura' if g7 is not None and g7.hard else 'blanda'})"
            if gap_h is not None and limit is not None and gap_h > limit:
                st.error(f"**El hueco máximo ({C.fmt_num(gap_h, 1, 'h')}{' o más' if m.max_link_gap_truncated else ''}) supera el tolerado por el "
                         f"perfil «{prof_label}» ({C.fmt_num(limit, 0, 'h')}).** {gate_txt}: no superada.", icon=":material/error:")
            elif gap_h is not None and limit is not None:
                st.success(f"Hueco máximo dentro de lo tolerado por el perfil ({C.fmt_num(limit, 0, 'h')}): "
                           f"{'comprobación superada' if S.is_public() else 'puerta G7 superada'}.", icon=":material/check_circle:")
            g0, g1, back = _link_gap(link, t0, t1) if m.link_fraction > 0 else (0.0, 0.0, False)
            if m.link_fraction > 0 and ((m.max_link_gap_s or 0.0) <= 0.0 or g1 - g0 < 1.0):
                st.caption("Sin huecos de comunicación en esta ventana: el enlace posible no se interrumpe.")
                link_gap_f = {"sin_huecos": True}
            elif m.link_fraction > 0:
                c0 = _first_contact(link, g1) if back else None
                gtxt = (f"**Hueco máximo sin enlace:** del {_utc_txt(g0)} al {_utc_txt(g1)} UTC, "
                        f"{C.fmt_duration(g1 - g0, m.max_link_gap_truncated)}. ")
                gtxt += (f"El enlace vuelve el {_utc_txt(g1)} UTC y lo recupera primero **{c0.complex or c0.station_id}** "
                         f"({c0.start_local[11:16]} {c0.start_local.rsplit(' ', 1)[-1]}, hora local)." if c0 is not None else
                         "No termina dentro del periodo: el enlace no vuelve antes de su final.")
                if (gap_h or 0) >= 24.0:
                    st.warning(gtxt, icon=":material/signal_disconnected:")
                else:
                    st.caption(gtxt)
                link_gap_f = {"inicio_utc": _utc_txt(g0), "fin_utc": _utc_txt(g1), "vuelve": back,
                              "primera_estacion": None if c0 is None else (c0.complex or c0.station_id)}
            if m.network_fraction is not None:
                st.caption(f"La red ve la Luna el {C.fmt_pct(m.network_fraction)} del tiempo (no depende del sitio lunar). "
                           f"Tierra visible (geometría) {C.fmt_pct(m.earth_fraction)} frente a enlace posible {C.fmt_pct(m.link_fraction)}.")
            bad = [s for s in link.stations if "verificar" in (s.confidence or "") or "sup" in (s.confidence or "")]
            if bad:
                st.caption("Elevación mínima **supuesta, no publicada**, para: " + ", ".join(s.complex or s.station_id for s in bad) + ".")
            for n in link.notes:
                st.caption(":material/info: " + n)
            if m.link_fraction == 0:
                reason = ("la Tierra no se ve en ningún momento desde este punto" if m.earth_fraction == 0 else
                          "la Tierra se ve, pero nunca a la vez que una estación vea la Luna con ese margen de antena")
                C.empty_state(f"No hay enlace posible en todo el periodo: {reason}. Ninguna estación lo recupera dentro del periodo "
                              "analizado (el hueco máximo es todo el periodo): alarga el periodo, cambia la red o baja el margen de antena.")
            link_f = {"red": link.network_label, "margen_elevacion_antena_deg": link.min_earth_elevation_deg,
                      "tierra_visible_frac": m.earth_fraction, "enlace_posible_frac": m.link_fraction,
                      "red_ve_luna_frac": m.network_fraction, "sentido_enlace": req.link_direction,
                      "cobertura_red_por_sentido": res.network_fraction_by_direction, "horas_contacto_dia_media": m.link_hours_per_day_mean,
                      "horas_contacto_dia_min": m.link_hours_per_day_min,
                      "ventana_enlace_mas_larga_h": _hours(m.longest_link_window_s), "ventana_truncada": m.longest_link_window_truncated,
                      "hueco_max_h": gap_h, "hueco_truncado": m.max_link_gap_truncated,
                      "hueco_tolerado_h": limit, "puerta_g7": None if g7 is None else g7.status.value,
                      "hueco_max_detalle": link_gap_f, "rango": {k: v for k, v in rngs.items() if k in ("link", "gap_h")}}
facts["conectividad"] = link_f

# ================================================================================================ (D) contactos: el gráfico protagonista
st_rows, ct_rows = [], []
cons = list(link.contacts) if link is not None else []
days_all = [d for d in res.daily if d["end_et"] > t0 and d["start_et"] < t1]
day_defs = [(d["day_utc"], utc_midnight_et(d["start_et"] + 0.05)) for d in days_all]
day_defs = [(lab, d0, d0 + 86400.0) for lab, d0 in day_defs]
if link is not None and m.link_fraction is not None:
    cfg_st = gs.load_config()["stations"]
    for s in link.stations:
        cs = [c for c in cons if c.station_id == s.station_id]
        best = max(cs, key=lambda c: c.duration_s) if cs else None
        meta = cfg_st.get(s.station_id, {})
        assumed = "verificar" in (s.confidence or "") or "sup" in (s.confidence or "")
        st_rows.append({
            "Estación": f"{s.complex or s.station_id} ({s.station_id})", "Zona horaria": s.tz,
            "% del tiempo con enlace": C.fmt_num(100 * s.link_fraction, 1), "Horas de contacto por día": C.fmt_num(s.link_hours_per_day, 1),
            "Ventanas": s.n_windows, "Ventana más larga": C.fmt_duration(s.longest_window_s),
            "La estación ve la Luna (%)": C.fmt_num(100 * s.moon_visible_fraction, 1),
            "Elevación mínima de la antena": f"{C.fmt_num(s.min_elevation_deg, 1, '°')} " + ("(SUPUESTA)" if assumed else f"({s.confidence})"),
            "Elevación máxima de la Luna": "—" if not cs else C.fmt_num(max(c.max_moon_el_deg for c in cs), 0, "°"),
            "Contacto más largo, UTC": "—" if best is None else f"{best.start_utc[5:16].replace('T', ' ')} → {best.end_utc[11:16]}",
            "Contacto más largo, hora local civil": "—" if best is None else
            f"{best.start_local[11:16]}–{best.end_local[11:16]} {_tzname(best.start_local)}",
            "Hora solar local media": "—" if best is None else f"{_hhmm(best.start_solar_h)}–{_hhmm(best.end_solar_h)}",
            "Origen de la posición": "personalizada" if not meta else ("publicada" if meta.get("verified") else "NAIF (coordenadas), elevación supuesta")})
    st.header("Contactos por estación: cuándo habría enlace (hora local)")
    if not cons:
        C.empty_state("Ninguna estación tiene contacto con este punto en el ámbito elegido: no hay ventanas que dibujar.", quiet=True)
    else:
        cc1, cc2 = st.columns([1, 1])
        clock = cc1.radio("Eje horizontal", ["Hora UTC", "Hora local de cada estación"], horizontal=True, key="_sc_clock", index=1,
                          help="En hora local cada estación usa su propio reloj civil: las bandas de estaciones distintas no están alineadas "
                               "en el tiempo, así que los traspasos solo se leen en UTC.")
        local = clock != "Hora UTC"
        view = day_defs
        if len(day_defs) > MAX_CHART_DAYS:
            first = cc2.slider("Mostrar desde el día número", 1, len(day_defs) - MAX_CHART_DAYS + 1, 1, key="_sc_first",
                               help=f"Se dibujan {MAX_CHART_DAYS} días a la vez para que el gráfico se lea.")
            view = day_defs[first - 1:first - 1 + MAX_CHART_DAYS]
        fig = contact_plot.contact_chart(cons, view, local=local, to_local=gs.et_to_local,
                                         union=[(w.start_et, w.end_et) for w in link.link.windows],
                                         station_order=[s.station_id for s in link.stations],
                                         title="Contactos por estación (hora local de cada una)" if local else "Contactos por estación (UTC)")
        if fig is None:
            C.empty_state("Ninguna estación tiene contacto en los días mostrados.", quiet=True)
        else:
            C.accessible_chart(fig, "Barras horizontales: una banda por estación (cada una con su color y su patrón de relleno) para cada día. "
                               "La banda «Enlace posible (red)», solo en UTC, es la unión: los huecos son tiempo sin ninguna estación y las "
                               "barras simultáneas de varias estaciones son traspasos. "
                               + " ".join(f"{r['Estación']}: {r['% del tiempo con enlace']} % del tiempo." for r in st_rows),
                               key="_sc_contacts", details=[f"{r['Estación']}: contacto más largo {r['Contacto más largo, UTC']} UTC, "
                                                            f"{r['Contacto más largo, hora local civil']}." for r in st_rows])
    facts["conectividad"]["estaciones"] = st_rows

# ================================================================================================ detalle solar
st.header("Solar en detalle")
all_ids = list(by_id)
cur = [p for p in ss[S.PANEL_IDS] if p in by_id][:3] or ([req.panel_id] if req.panel_id in by_id else [])
if ss.get("_sc_panels") != cur:
    ss["_sc_panels"] = cur
st.multiselect("Paneles a comparar (el primero es el principal)", all_ids, key="_sc_panels", on_change=_on_panels, max_selections=3,
               format_func=lambda i: by_id[i].name + (" · EXPERIMENTAL" if by_id[i].evidence_group != "respaldado" else ""),
               help="Hasta 3. Los paneles experimentales sin datasheet llevan siempre su etiqueta.")
specs, labels, seen = [], [], set()


def _add(pid: str, mnt: MountingSpec, suffix: str = "") -> None:
    key = (pid, mnt.type, mnt.tilt_deg, mnt.azimuth_deg)
    if key not in seen:
        seen.add(key)
        specs.append((pid, mnt))
        labels.append(f"{by_id[pid].name} · {_mount_label(mnt)}{suffix}")


for pid in cur:
    mm = S.mounting_for(ctx, pid)
    if mm is not None:
        _add(pid, mm)
if cur:
    _add(cur[0], MountingSpec(MountingType.HORIZONTAL), "")
    _add(cur[0], MountingSpec(MountingType.VERTICAL_AZ_TRACKING), "")
runs = cache.get_power(req, specs, req.battery, req.degradation, req.dust_loss) if specs else []
rows, curves, bands, hv = [], [], {}, {}
th = ctx.cfg["power"]["thermal"]
for run, lab in zip(runs, labels):
    pid = run.panel_id
    if run.error is not None:
        rows.append({"Panel y montaje": lab, "Potencia media (W/m²)": "no calculable", "Pico (W/m²)": "—", "Energía/día media (Wh/m²)": "—",
                     "Energía/día mínima (Wh/m²)": "—", "Evidencia": run.error[:80]})
        continue
    p = by_id[pid]
    ar = p.areal_power_w_m2_am0
    sm = run.summary
    dn = [d for d in sm.daily if d.day_start_et < t1 and d.day_start_et + 86400.0 > t0] or list(sm.daily)
    mean_rel = sm.mean_p_rel if len(dn) == len(sm.daily) else float(np.mean([d.e_rel for d in dn]))
    peak_rel = max(d.peak_p_rel for d in dn)
    whs = [d.e_rel * 24.0 * ar for d in dn] if ar is not None else None
    rows.append({"Panel y montaje": lab,
                 "Potencia media (W/m²)": "sin dato" if ar is None else C.fmt_num(mean_rel * ar, 0),
                 "Pico (W/m²)": "sin dato" if ar is None else C.fmt_num(peak_rel * ar, 0),
                 "Energía/día media (Wh/m²)": "sin dato" if ar is None else C.fmt_num(float(np.mean(whs)), 0),
                 "Energía/día mínima (Wh/m²)": "sin dato" if ar is None else C.fmt_num(float(np.min(whs)), 0),
                 "Evidencia": (p.evidence_level or "sin clasificar") + (" · EXPERIMENTAL" if p.evidence_group != "respaldado" else "")})
    if ar is not None:
        curves.append((lab, run.series.et, run.series.p_rel, ar))
        hv[(pid, run.mounting.type)] = mean_rel
        if len(curves) == 1 and getattr(p, "ranges", None):
            bnd = pn.power_band(run.series, p, PowerParams(pid, run.mounting, t_ambient_k=float(th["t_ambient_k"]),
                                                           t_min_valid_k=float(th["t_min_valid_k"])), ctx.panels)
            e_lo, e_hi = p.ranges.get("eta_bol", (p.eta_bol, p.eta_bol))
            s0 = ctx.panels.solar_constant_w_m2
            if bnd is not None:
                bands[0] = (np.minimum(bnd[0], run.series.p_rel) * min(e_lo, e_hi) * s0, np.maximum(bnd[1], run.series.p_rel) * max(e_lo, e_hi) * s0)
if rows:
    C.public_note("Cada fila es un panel y una forma de colocarlo. «W/m²» es la potencia eléctrica por metro cuadrado de panel; "
                  "«Wh/m²» es la energía de un día.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if cur and (cur[0], MountingType.VERTICAL_AZ_TRACKING) in hv and (cur[0], MountingType.HORIZONTAL) in hv:
        v, h = hv[(cur[0], MountingType.VERTICAL_AZ_TRACKING)], hv[(cur[0], MountingType.HORIZONTAL)]
        notrec = [t for t in (MountingType.HORIZONTAL, MountingType.VERTICAL_AZ_TRACKING) if t not in by_id[cur[0]].mounting_allowed]
        txt = (f"**Factor vertical/horizontal para {by_id[cur[0]].name}:** el vertical con seguimiento rinde "
               + (f"**{C.fmt_num(v / h, 1)}×** lo que el horizontal en este lugar." if h > 1e-6 else "mucho más: el horizontal casi no produce."))
        if notrec:
            txt += " (Algún montaje de la comparación no es el recomendado para este panel.)"
        st.markdown(txt)
        facts["solar"]["factor_vertical_horizontal"] = None if h <= 1e-6 else v / h
    if curves:
        days_sun = [d for d in res.daily if d["end_et"] > t0 and d["start_et"] < t1]
        opts = {d["day_utc"]: utc_midnight_et(d["start_et"] + 0.05) for d in days_sun}
        if opts:
            if ss.get("_sc_pday") not in opts:
                ss["_sc_pday"] = next((d["day_utc"] for d in days_sun if d["sun_hours"] > 0), next(iter(opts)))
            st.selectbox("Día de la curva", list(opts), key="_sc_pday")
            fig = capacity_plot.day_power_curve(curves, opts[ss["_sc_pday"]], bands=bands)
            C.accessible_chart(fig, "Potencia eléctrica en W por m² de panel a lo largo del día UTC elegido, para cada panel y montaje comparado. "
                               + " ".join(f"{r['Panel y montaje']}: media {r['Potencia media (W/m²)']} W/m²." for r in rows[:3]),
                               key="_sc_curve")
            if bands:
                st.caption("Sombra = rango de incertidumbre de los parámetros estimados del panel principal.")
for r_ in runs:
    if r_.error is not None:
        st.caption(f":material/block: {by_id[r_.panel_id].name}: {r_.error}")

# ================================================================================================ detalle conectividad
st.header("Conectividad en detalle: bases terrestres")
if link is None or m.link_fraction is None:
    st.info("Sin red de estaciones (solo geometría): no hay tabla por base terrestre.", icon=":material/satellite_alt:")
else:
    _direction_block(res, req)
    # --- sensibilidad al margen de elevación
    st.subheader("Sensibilidad al margen de elevación de la antena")
    margins = [float(x) for x in ctx.cfg["score"]["link"]["sensitivity_min_earth_elevation_deg"]]
    st.caption("Cuánto cambia el enlace si la antena del lander necesita ver la Tierra más alta sobre el horizonte. Repite el análisis "
               f"con {', '.join(f'{x:g}°' for x in margins)} (periodo completo, con la caché compartida).")
    if not ss.get("_sc_sens_on"):
        st.button(f"Calcular la sensibilidad ({len(margins)} análisis)", key="_sc_sens", on_click=_on_sens, icon=":material/tune:")
    else:
        sens = cache.get_margin_sensitivity(req, margins)
        srows = [{"Margen de elevación": f"{mg:g}°" + (" (el elegido)" if abs(mg - link.min_earth_elevation_deg) < 1e-9 else ""),
                  "Enlace posible (%)": C.fmt_num(None if r_.metrics.link_fraction is None else 100 * r_.metrics.link_fraction, 1),
                  "Horas de contacto por día": C.fmt_num(r_.metrics.link_hours_per_day_mean, 1),
                  "Ventana más larga": C.fmt_duration(r_.metrics.longest_link_window_s, r_.metrics.longest_link_window_truncated),
                  "Hueco máximo": C.fmt_duration(r_.metrics.max_link_gap_s, r_.metrics.max_link_gap_truncated)} for mg, r_ in sens.items()]
        st.dataframe(pd.DataFrame(srows), hide_index=True, width="stretch")
        facts["conectividad"]["sensibilidad_margen"] = [{k: v for k, v in r_.items()} for r_ in srows]

    # --- tabla por estación (los datos ya se calcularon arriba, junto al gráfico de contactos)
    st.subheader("Qué bases terrestres tendrían enlace y cuándo")
    st.dataframe(pd.DataFrame(st_rows), hide_index=True, width="stretch")
    st.caption("Hora local civil = la de la estación con su horario de verano (p. ej. PST, CET, AEDT). Hora solar local media = UTC + longitud/15, "
               "sin ecuación del tiempo. La elevación de la Luna es la del centro, sin refracción. No se modela la máscara de terreno de cada antena.")

    # --- día elegido
    if not cons:
        C.empty_state("Ninguna estación tiene contacto con este punto en el ámbito elegido: no hay ventanas que listar.", quiet=True)
    else:
        labs = [d[0] for d in day_defs]
        link_hours = {d["day_utc"]: d.get("link_hours", 0.0) for d in days_all}
        if ss.get("_sc_day") not in labs:
            ss["_sc_day"] = next((lab for lab in labs if link_hours.get(lab, 0) > 0), labs[0])
        st.selectbox("Día para el detalle de contactos (UTC)", labs, key="_sc_day")
        # ventanas REALES enteras que entrega el núcleo (``daily_contact_table``): la UI no parte ni une ventanas por día UTC
        row_day = next(r for r in gs.daily_contact_table(cons, res.timeline.et0, res.timeline.et1) if r["day_utc"] == ss["_sc_day"])
        by_key = {(c.station_id, c.start_utc): c for c in cons}
        lines = []
        for sid, sv in row_day["stations"].items():
            for w in sv["windows"]:
                c = by_key[(sid, w["start_utc"])]
                ct_rows.append({"Estación": f"{c.complex or c.station_id} ({c.station_id})", "Día UTC": ss["_sc_day"],
                                "UTC": f"{w['start_utc'][5:16].replace('T', ' ')} → {w['end_utc'][5:16].replace('T', ' ')}",
                                "Hora local civil": w["text"],
                                "Hora solar local media": f"{_hhmm(c.start_solar_h)}–{_hhmm(c.end_solar_h)}",
                                "Duración": C.fmt_duration(c.duration_s), "Horas dentro de este día": C.fmt_num(w["hours_in_day"], 1),
                                "Elevación máxima de la Luna": C.fmt_num(c.max_moon_el_deg, 0, "°"),
                                "Continúa": ("viene del día anterior" if w["continues_prev"] else "")
                                + (" · sigue al día siguiente" if w["continues_next"] else "")})
                lines.append((c.complex or c.station_id, w["text"], w["start_utc"][11:16], w["end_utc"][11:16]))
        st.markdown(f"**Contactos del {ss['_sc_day']}**")
        if ct_rows:
            st.dataframe(pd.DataFrame(ct_rows), hide_index=True, width="stretch")
        else:
            C.empty_state(f"El {ss['_sc_day']} no hay enlace con ninguna estación: es un hueco sin conectividad.", quiet=True)
        if S.is_public():
            if lines:
                st.info("**En lenguaje llano:** el " + ss["_sc_day"] + " habría enlace con " + "; con ".join(
                    f"**{n}** {lt} (hora local; {u0}–{u1} UTC)" for n, lt, u0, u1 in lines) + ".", icon=":material/chat:")
            else:
                st.info(f"En lenguaje llano: el {ss['_sc_day']} ninguna base terrestre podría hablar con este punto.", icon=":material/chat:")
            quiet = [s["Estación"] for s in st_rows if s["Ventanas"] == 0]
            if quiet:
                st.caption("Sin ningún contacto en el ámbito elegido: " + ", ".join(quiet) + ".")


# ================================================================================================ (D) ficha
st.header("Ficha del sitio")
st.caption("Resumen descargable de esta pantalla. El JSON incluye además el análisis completo de `analysis.export`; ese export todavía NO "
           "contiene el enlace DTE, así que las estaciones y los contactos viajan en la ficha (y en `estaciones.csv` / `contactos.csv`).")
all_contacts = [{"estacion": c.station_id, "nombre": c.station_name, "zona": c.tz, "inicio_utc": c.start_utc, "fin_utc": c.end_utc,
                 "inicio_local": c.start_local, "fin_local": c.end_local, "hora_solar_inicio": round(c.start_solar_h, 3),
                 "hora_solar_fin": round(c.end_solar_h, 3), "duracion_h": round(c.duration_s / 3600.0, 3),
                 "elevacion_max_luna_deg": round(c.max_moon_el_deg, 2),
                 "trunca_inicio": c.left_truncated, "trunca_fin": c.right_truncated} for c in (link.contacts if link is not None else ())]
facts["conectividad"]["contactos"] = all_contacts
base = f"lsi_ficha_{C._slug(o.label)}_{req.start_utc[:10]}"
d1_, d2_ = st.columns(2)
d1_.download_button("Descargar ficha (JSON)", data=lambda: C.ficha_json_bytes(res, facts), file_name=f"{base}.json", mime="application/json",
                    on_click="ignore", key="_sc_dl_json", icon=":material/download:")
d2_.download_button("Descargar ficha (CSV, zip)", data=lambda: C.ficha_csv_zip_bytes(res, facts, st_rows, all_contacts),
                    file_name=f"{base}_csv.zip", mime="application/zip", on_click="ignore", key="_sc_dl_csv", icon=":material/download:")

if C.show_for("planificador"):
    C.glossary_expander()
