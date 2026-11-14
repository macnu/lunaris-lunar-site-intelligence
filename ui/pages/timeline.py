"""Pantalla C «Línea temporal» (Mission Timeline, arquitectura §11.2).

Bandas Sol / Tierra / solape (con zona de duda), ventanas, zoom a transiciones (refinadas a ~1 s por el motor), tabla
diaria por día UTC, comparación de dos fechas del mismo sitio, vista anual y animación Sol/Tierra. No calcula: llama a
``ui.cache`` y pinta con ``lsi.visualization``; solo da formato y resta/agrupa lo ya calculado.
"""
from __future__ import annotations

import bisect
import dataclasses
from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lsi.analysis import metrics as M
from lsi.contracts import Body, EventKind, StateKey as K
from lsi.visualization import theme
from lsi.visualization.horizon_plot import body_state, horizon_cartesian
from lsi.visualization.timeline_plot import timeline_bands, zoom_around
from ui import cache, components as C, state as S

V_PER, V_CMP, V_YEAR, V_ANIM = "Periodo actual", "Comparar fechas", "Año y estaciones", "Animación"
SYNODIC_D = 29.53                      # mes sinódico (glosario «Día lunar»)
_EV_NAME = {(Body.SUN, EventKind.RISE): "Salida del Sol", (Body.SUN, EventKind.SET): "Puesta de Sol",
            (Body.EARTH, EventKind.RISE): "Earthrise (sale la Tierra)", (Body.EARTH, EventKind.SET): "Earthset (se pone la Tierra)"}


# ------------------------------------------------------------------------------------------------ utilidades
def _utc(et: float) -> str:
    return theme.et_to_datetimes([et])[0].strftime("%Y-%m-%d %H:%M:%S")


def _trunc(w) -> bool:
    return bool(w.left_truncated or w.right_truncated)


def _dur_total(ws) -> float:
    return M.total_duration(M.intervals(ws))


def _longest_dark(res):
    ds = res.timeline.dark.windows
    return max(ds, key=lambda w: w.duration_s) if ds else None


def _story(res, prefix: str = "") -> str:
    """Relato llano: noche más larga y cuándo vuelve el Sol (o por qué no se sabe)."""
    w = _longest_dark(res)
    if w is None:
        return prefix + "En este periodo el Sol no llega a ponerse: siempre está sobre el horizonte del punto."
    txt = (f"{prefix}La noche más larga dura {'al menos ' if _trunc(w) else ''}"
           f"{C.fmt_num(w.duration_s / 86400.0, 1, 'días')} ({C.fmt_duration(w.duration_s)}). ")
    if w.right_truncated:
        return txt + "El periodo termina sin que el Sol vuelva: amplía el periodo para saber cuándo regresa."
    return txt + f"El Sol vuelve el {_utc(w.end_et)} UTC."


def _cursor_et(res):
    """ET del cursor compartido si cae dentro del periodo (desfase UTC→ET constante: sin segundos intercalares hasta 2050)."""
    try:
        cur, t0 = S.parse_utc(S.get_str(K.CURSOR_UTC)), S.parse_utc(res.request.start_utc)
    except ValueError:
        return None
    et = res.timeline.et0 + (cur - t0).total_seconds()
    return et if res.timeline.et0 <= et <= res.timeline.et1 else None


def _alt(res) -> str:
    m = res.metrics
    return (f"Sol visible el {C.fmt_pct(m.solar_fraction)} del periodo en {m.n_sun_windows} ventanas; Tierra visible el "
            f"{C.fmt_pct(m.earth_fraction)} en {m.n_earth_windows}; ambos a la vez el {C.fmt_pct(m.overlap_fraction)}. "
            f"Oscuridad máxima {C.fmt_duration(m.max_darkness_s, m.max_darkness_truncated)}."
            + ("" if m.link_fraction is None else f" Enlace posible el {C.fmt_pct(m.link_fraction)} del periodo."))


def _alt_details(res) -> list[str]:
    tl, out = res.timeline, []
    for name, ws in (("Sol", tl.sun), ("Tierra visible (geometría)", tl.earth), ("Sol y Tierra", tl.overlap),
                     *((("Enlace posible", tl.link.link),) if tl.link is not None else ())):
        for w in ws.windows[:12]:
            out.append(f"{name}: {_utc(w.start_et)} → {_utc(w.end_et)} UTC, {C.fmt_duration(w.duration_s, _trunc(w))}")
    return out


def _bands(res, *, key: str, zoom=None, cursor=None, doubt=True, events=True, alt=None, stations=False) -> None:
    if C.no_visibility(res):
        return
    fig = timeline_bands(res.timeline, cursor_et=cursor, zoom_et=zoom, show_pessimistic=doubt, show_events=events,
                         show_stations=stations)
    C.accessible_chart(fig, alt or _alt(res), key=key, details=_alt_details(res))


def _cards(m) -> None:
    c = st.columns(3)
    with c[0]:
        C.metric_card("Sol visible", C.fmt_pct(m.solar_fraction), help_term="Ventana de visibilidad")
    with c[1]:
        C.metric_card("Ventana de Sol más larga", C.fmt_duration(m.longest_sun_window_s, m.longest_sun_window_truncated),
                      help_term="≥ (ventana truncada)")
    with c[2]:
        C.metric_card("Oscuridad máxima", C.fmt_duration(m.max_darkness_s, m.max_darkness_truncated),
                      help_term="≥ (ventana truncada)")
    if S.is_public():
        return
    c = st.columns(3)
    with c[0]:
        C.metric_card("Tierra visible (geometría)", C.fmt_pct(m.earth_fraction),
                      help="Geometría: la Tierra sobre el horizonte local. NO es capacidad de comunicar; mira «Enlace posible».")
    with c[1]:
        C.metric_card("Ventana de Tierra más larga", C.fmt_duration(m.longest_earth_window_s))
    with c[2]:
        C.metric_card("Sol y Tierra a la vez", C.fmt_pct(m.overlap_fraction), help=f"Más larga: {C.fmt_duration(m.longest_overlap_s)}.")
    if m.link_fraction is None:
        st.caption("Sin red de estaciones elegida: solo se muestra la visibilidad geométrica de la Tierra.")
        return
    c = st.columns(4)
    with c[0]:
        C.metric_card("ENLACE POSIBLE", C.fmt_pct(m.link_fraction),
                      help="Tierra visible con margen de elevación Y alguna estación de la red viendo la Luna. Sigue siendo geometría (sin presupuesto de enlace).")
    with c[1]:
        C.metric_card("Horas de enlace al día", f"{C.fmt_num(m.link_hours_per_day_mean, 1, 'h')} de media",
                      help="Mínimo entre días UTC completos: " + ("no hay días completos" if m.link_hours_per_day_min is None
                                                                  else C.fmt_num(m.link_hours_per_day_min, 1, "h")))
    with c[2]:
        C.metric_card("Ventana de enlace más larga", C.fmt_duration(m.longest_link_window_s, m.longest_link_window_truncated))
    with c[3]:
        C.metric_card("Hueco máximo sin enlace", C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated),
                      help="Es lo que mide la puerta G7 del score (hueco máximo tolerado según el perfil).")


def _doubt_note(res) -> None:
    tl = res.timeline
    if tl.sun_pess is None:
        if not S.is_public():
            st.caption("Zona de duda no disponible: activa «incertidumbre» en la barra lateral para ver el horizonte pesimista.")
        return
    earth = (f"; la Tierra, entre {C.fmt_num(_dur_total(tl.earth_pess) / 3600.0, 1, 'h')} y "
             f"{C.fmt_num(_dur_total(tl.earth) / 3600.0, 1, 'h')}." if tl.earth_pess is not None else ".")
    st.caption(f":material/help: **Zona de duda (cota superior del horizonte):** el Sol visible dura entre "
               f"{C.fmt_num(_dur_total(tl.sun_pess) / 3600.0, 1, 'h')} (pesimista) y "
               f"{C.fmt_num(_dur_total(tl.sun) / 3600.0, 1, 'h')} (nominal)" + earth)


def _win_df(res) -> pd.DataFrame:
    rows = []
    lk = res.timeline.link
    for name, ws in (("Sol", res.timeline.sun), ("Tierra visible (geometría)", res.timeline.earth), ("Sol y Tierra", res.timeline.overlap),
                     *((("Enlace posible", lk.link),) if lk is not None else ()), ("Oscuridad", res.timeline.dark)):
        rows += [{"Criterio": name, "Inicio (UTC)": _utc(w.start_et), "Fin (UTC)": _utc(w.end_et),
                  "Duración": C.fmt_duration(w.duration_s, _trunc(w)), "Truncada": "sí (≥)" if _trunc(w) else "no"}
                 for w in ws.windows]
    return pd.DataFrame(rows)


def _contacts(res) -> None:
    """Contactos por estación tal como los entrega el pipeline (``link.contacts``); no se recalcula nada."""
    lk = res.timeline.link
    if lk is None or not lk.contacts or not C.show_for("planificador"):
        return
    with st.expander(f"Contactos con estaciones ({len(lk.contacts)}) · red {lk.network_label}"):
        st.dataframe(pd.DataFrame([{"Estación": c.station_name, "Inicio (UTC)": c.start_utc[:19].replace("T", " "), "Fin (UTC)": c.end_utc[:19].replace("T", " "),
                                    "Hora local de la estación": c.start_local, "Duración": C.fmt_duration(c.duration_s, c.left_truncated or c.right_truncated),
                                    "Elev. máx. de la Luna (°)": round(c.max_moon_el_deg, 1),
                                    "Elev. máx. de la Tierra en el lander (°)": None if c.max_earth_el_deg is None else round(c.max_earth_el_deg, 1)}
                                   for c in lk.contacts[:300]]), hide_index=True, width="stretch")
        if len(lk.contacts) > 300:
            st.caption("Se muestran los primeros 300 contactos; la exportación completa tiene todos.")
        for n in lk.notes:
            st.caption(f"• {n}")


def _csv_button(df: pd.DataFrame, label: str, name: str, key: str) -> None:
    st.download_button(label, data=lambda: df.to_csv(index=False).encode("utf-8"), file_name=name, mime="text/csv",
                       on_click="ignore", key=key, icon=":material/download:")


# ------------------------------------------------------------------------------------------------ vista: periodo
def _view_period(res) -> None:
    tl, m = res.timeline, res.metrics
    if S.is_public():
        st.success(_story(res), icon=":material/dark_mode:")
        st.caption("«Noche» = el Sol tapado por el relieve o el horizonte lunar; los eclipses no se modelan.")
    _cards(m)
    C.public_note("Las barras muestran cuándo se ve el Sol (amarillo) y la Tierra (azul) desde este punto. "
                  "Los huecos son noche (el Sol no se ve) o Tierra fuera de vista.")
    if S.is_public() and m.link_fraction is not None:
        st.info(f"Ver la Tierra no basta para hablar con ella: hay **enlace posible** el {C.fmt_pct(m.link_fraction)} del periodo "
                f"(la Tierra se ve el {C.fmt_pct(m.earth_fraction)}); el mayor hueco sin enlace dura {C.fmt_duration(m.max_link_gap_s, m.max_link_gap_truncated)}.",
                icon=":material/satellite_alt:")
    st.subheader("Bandas temporales")
    stations = bool(tl.link is not None and tl.link.contacts and not S.is_public()
                    and st.toggle("Mostrar el enlace por estación", value=False, key="_tl_stations"))
    doubt = True
    if tl.sun_pess is not None and not S.is_public():
        doubt = st.toggle("Mostrar zona de duda (horizonte pesimista, más trama)", value=True, key="_tl_doubt")
    _bands(res, key="tl_bands", cursor=_cursor_et(res), doubt=doubt, stations=stations)
    _doubt_note(res)
    st.caption(":material/info: **Tierra visible (geometría)** = la Tierra sobre el horizonte del lander. **Enlace posible** = además con margen de "
               "elevación y con alguna estación de la red viendo la Luna. " + theme.GEOMETRIC_NOTE)
    _contacts(res)

    if C.show_for("planificador"):
        st.subheader("Zoom en una transición")
        evs = list(tl.events)
        if not evs:
            st.info("No hay transiciones (salidas ni puestas) en este periodo: el estado no cambia.", icon=":material/info:")
        else:
            c1, c2 = st.columns([3, 1])
            i = c1.selectbox("Transición", range(len(evs)), key="_tl_ev",
                             format_func=lambda j: f"{_utc(evs[j].et)} · {_EV_NAME[(evs[j].body, evs[j].kind)]}"
                                                   f"{' (truncado)' if evs[j].truncated else ''}")
            hours = c2.slider("Ventana (± horas)", 1, 48, 12, key="_tl_zoom_h")
            e = evs[i]
            _bands(res, key="tl_zoom", zoom=zoom_around(e.et, float(hours)), cursor=e.et, doubt=doubt,
                   alt=f"Zoom de ±{hours} h en {_EV_NAME[(e.body, e.kind)]}: {_utc(e.et)} UTC, azimut {C.fmt_num(e.az_deg, 0)}°.")
            st.caption(f"Instante refinado por bisección a ±{tl.params.refine_xtol_s:g} s · azimut {C.fmt_num(e.az_deg, 1)}° · "
                       f"{theme.GEOMETRIC_NOTE}")

    st.subheader("Tabla diaria (día UTC)")
    df = pd.DataFrame(res.daily)
    show = df[["day_utc", "mean_illumination", "sun_hours", "earth_hours", "overlap_hours"]
              + (["link_hours"] if "link_hours" in df else [])].rename(columns={
        "day_utc": "Día (UTC)", "mean_illumination": "Iluminación media", "sun_hours": "Horas de Sol",
        "earth_hours": "Horas de Tierra (geometría)", "overlap_hours": "Horas de Sol y Tierra", "link_hours": "Horas de enlace posible"})
    show["Iluminación media"] = show["Iluminación media"] * 100.0
    with st.expander("Ver tabla diaria", expanded=not S.is_public()):
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "Iluminación media": st.column_config.NumberColumn(format="%.1f %%"),
            "Horas de Sol": st.column_config.NumberColumn(format="%.2f"),
            "Horas de Tierra (geometría)": st.column_config.NumberColumn(format="%.2f"),
            "Horas de enlace posible": st.column_config.NumberColumn(format="%.2f"),
            "Horas de Sol y Tierra": st.column_config.NumberColumn(format="%.2f")})
        st.caption("Primer y último día pueden ser parciales (medianoche a medianoche UTC).")
    _csv_button(df.drop(columns=["start_et", "end_et"]), "Descargar tabla diaria (CSV)", "lsi_tabla_diaria.csv", "tl_daily_csv")

    if C.show_for("planificador"):
        with st.expander("Ventanas y eventos"):
            st.dataframe(_win_df(res), hide_index=True, width="stretch")
            if S.is_expert():
                st.caption(f"Criterios: Sol {tl.sun.criterion}; Tierra {tl.earth.criterion}.")
                st.dataframe(pd.DataFrame([{"UTC": _utc(e.et), "Cuerpo": "Sol" if e.body == Body.SUN else "Tierra",
                                            "Evento": _EV_NAME[(e.body, e.kind)], "Azimut (°)": round(e.az_deg, 1),
                                            "Truncado": e.truncated} for e in tl.events]), hide_index=True, width="stretch")
    st.subheader("Exportar")
    C.download_buttons(res, key="tl_dl")


# ------------------------------------------------------------------------------------------------ vista: comparar fechas
_CMP = (("Sol visible", "solar_fraction", "pct"), ("Ventana de Sol más larga", "longest_sun_window_s", "dur"),
        ("Oscuridad máxima", "max_darkness_s", "dur"), ("Tierra visible (geometría)", "earth_fraction", "pct"),
        ("Ventana de Tierra más larga", "longest_earth_window_s", "dur"), ("Sol y Tierra a la vez", "overlap_fraction", "pct"),
        ("Elevación máxima del Sol", "max_sun_elevation_deg", "deg"))
_CMP_LINK = (("Enlace posible", "link_fraction", "pct"), ("Ventana de enlace más larga", "longest_link_window_s", "dur"),
             ("Hueco máximo sin enlace", "max_link_gap_s", "dur"))
_TRUNC_FLAG = {"longest_sun_window_s": "longest_sun_window_truncated", "max_darkness_s": "max_darkness_truncated",
               "longest_link_window_s": "longest_link_window_truncated", "max_link_gap_s": "max_link_gap_truncated"}


def _fmt(kind: str, v: float, trunc: bool = False, delta: bool = False) -> str:
    if kind == "pct":
        return C.fmt_num(100.0 * v, 1, "pp" if delta else "%")
    if kind == "dur":
        return C.fmt_duration(v, trunc)
    return C.fmt_num(v, 1, "°")


def _cell(m, att: str, kind: str) -> str:
    return _fmt(kind, getattr(m, att), bool(getattr(m, _TRUNC_FLAG[att])) if att in _TRUNC_FLAG else False)


def _delta(kind: str, a: float, b: float) -> str:
    d = b - a
    if abs(d) < (1e-4 if kind == "pct" else 30.0 if kind == "dur" else 0.05):
        return "= sin cambio"
    return ("▲ +" if d > 0 else "▼ −") + _fmt(kind, abs(d), delta=True)


def _view_compare(res) -> None:
    req = res.request
    st.markdown("Compara el **mismo sitio y la misma duración** con otra fecha de inicio, por ejemplo «¿qué pasa si el "
                "aterrizaje se retrasa un mes?».")
    delay = st.number_input("Retraso del inicio (días; negativo = adelanto)", -365.0, 365.0, 30.0, step=1.0, key="_tl_delay")
    t0, t1 = S.parse_utc(req.start_utc), S.parse_utc(req.end_utc)
    msg = S.validate_period(t0 + timedelta(days=delay), t1 + timedelta(days=delay))
    if msg:
        C.show_error(msg)
        return
    if delay == 0:
        st.info("Con retraso 0 los dos periodos coinciden: cambia el retraso para ver diferencias.", icon=":material/info:")
    req_b = dataclasses.replace(req, start_utc=S.fmt_utc(t0 + timedelta(days=delay)),
                                end_utc=S.fmt_utc(t1 + timedelta(days=delay)), now_utc=None)
    res_b, err = cache.try_analysis(req_b)
    if err:
        C.show_error(err)
        return
    a, b = res.metrics, res_b.metrics
    if S.is_public():
        wa, wb = _longest_dark(res), _longest_dark(res_b)
        da, db = (wa.duration_s if wa else 0.0) / 86400.0, (wb.duration_s if wb else 0.0) / 86400.0
        st.success(f"Si el inicio se mueve {C.fmt_num(delay, 0, 'días')}, la noche más larga pasa de "
                   f"{C.fmt_num(da, 1, 'días')} a {C.fmt_num(db, 1, 'días')} y el Sol visible, del "
                   f"{C.fmt_pct(a.solar_fraction)} al {C.fmt_pct(b.solar_fraction)} del periodo.", icon=":material/compare:")
    cols = st.columns(2)
    for col, r, name, k in ((cols[0], res, "Periodo A (actual)", "tl_cmp_a"), (cols[1], res_b, "Periodo B (con retraso)", "tl_cmp_b")):
        with col:
            st.markdown(f"**{name}**: {r.request.start_utc[:16].replace('T', ' ')} → {r.request.end_utc[:16].replace('T', ' ')} UTC")
            _bands(r, key=k, doubt=False, events=False)
    st.dataframe(pd.DataFrame([{"Métrica": lab, "Periodo A": _cell(a, att, kind), "Periodo B": _cell(b, att, kind),
                                "Diferencia (B − A)": _delta(kind, getattr(a, att), getattr(b, att))}
                               for lab, att, kind in _CMP + (_CMP_LINK if a.link_fraction is not None and b.link_fraction is not None else ())]),
                 hide_index=True, width="stretch")
    st.caption(f"{theme.GEOMETRIC_NOTE} Las diferencias vienen de la geometría Sol–Tierra–Luna de cada fecha (libración, "
               "ciclo solar), no de cambios en el terreno.")
    C.download_comparison(M.comparison_table({"periodo_A": a, "periodo_B": b}), key="tl_cmp_csv",
                          file_name="lsi_comparacion_fechas.csv")
    with st.expander("Exportar el periodo B completo"):
        C.download_buttons(res_b, key="tl_cmp_dl_b")


# ------------------------------------------------------------------------------------------------ vista: año
def _monthly(res) -> pd.DataFrame:
    d = pd.DataFrame(res.daily)
    d["Mes"], d["h"] = d["day_utc"].str[:7], (d["end_et"] - d["start_et"]) / 3600.0
    d["il"], d["sin_sol"], d["sol_cont"] = d["mean_illumination"] * d["h"], d["sun_hours"] < 0.01, d["sun_hours"] >= d["h"] - 0.01
    g = d.groupby("Mes").agg(h=("h", "sum"), sol=("sun_hours", "sum"), tierra=("earth_hours", "sum"),
                             solape=("overlap_hours", "sum"), il=("il", "sum"), sin=("sin_sol", "sum"), cont=("sol_cont", "sum"),
                             dias=("day", "count"), **({"enlace": ("link_hours", "sum")} if "link_hours" in d else {}))
    return pd.DataFrame({"Mes": g.index, "Días": g["dias"].values, "Sol visible (%)": 100 * g["sol"].values / g["h"].values,
                         "Tierra visible (%)": 100 * g["tierra"].values / g["h"].values,
                         **({"Enlace posible (%)": 100 * g["enlace"].values / g["h"].values} if "enlace" in g else {}),
                         "Sol y Tierra (%)": 100 * g["solape"].values / g["h"].values,
                         "Iluminación media (%)": 100 * g["il"].values / g["h"].values,
                         "Días sin Sol": g["sin"].values, "Días con Sol continuo": g["cont"].values})


def _month_chart(mdf) -> None:
    fig = go.Figure()
    for col, color, pat in (("Sol visible (%)", theme.SUN, ""), ("Tierra visible (%)", theme.EARTH, "/"),
                            ("Enlace posible (%)", "#f28fd0", "+"), ("Sol y Tierra (%)", theme.OVERLAP, "x")):
        if col not in mdf:
            continue
        fig.add_trace(go.Bar(x=mdf["Mes"], y=mdf[col], name=col,
                             marker=dict(color=color, pattern=dict(shape=pat, fgcolor="#0b1020", size=7, solidity=0.35) if pat else {})))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="% del mes", range=[0, 100])
    fig.update_xaxes(title="Mes (UTC)")
    C.accessible_chart(theme.apply_theme(fig, "Resumen por mes", height=420, note=theme.GEOMETRIC_NOTE),
                       f"Barras por mes de Sol visible, Tierra visible y ambos; Sol visible entre {C.fmt_num(mdf['Sol visible (%)'].min(), 0)}% y "
                       f"{C.fmt_num(mdf['Sol visible (%)'].max(), 0)}% según el mes.", key="tl_year_months",
                       details=[f"{r['Mes']}: Sol {C.fmt_num(r['Sol visible (%)'], 0)}%, Tierra {C.fmt_num(r['Tierra visible (%)'], 0)}%, "
                                f"{int(r['Días sin Sol'])} días sin Sol" for _, r in mdf.iterrows()])


def _view_year(res) -> None:
    req = res.request
    t0 = S.parse_utc(req.start_utc)
    e = t0 + timedelta(days=365.0)
    msg = S.validate_period(t0, e)
    if msg:
        C.show_error(msg + " Adelanta el inicio en la barra lateral para poder analizar un año completo.")
        return
    req_y = dataclasses.replace(req, end_utc=S.fmt_utc(e), now_utc=None)
    ry, err = cache.try_analysis(req_y)
    if err:
        C.show_error(err)
        return
    st.markdown(f"Un año desde {req.start_utc[:10]} (paso {req_y.step_s / 60:g} min; transiciones refinadas a ~1 s).")
    if S.is_public():
        st.success(_story(ry, "En un año completo: "), icon=":material/calendar_month:")
    _cards(ry.metrics)
    if C.show_for("planificador"):
        st.info("El Sol se ve distinto según la época: el ciclo solar respecto a los nodos de la órbita lunar dura ≈ 347 d "
                "(año de eclipses, 346,62 d) y la libración en latitud tiene periodo ≈ 27,2 d (mes dracónico, 27,21 d). "
                "Valores astronómicos estándar; su efecto en este sitio concreto está en las cifras de abajo (a verificar con un experto).",
                icon=":material/autorenew:")
    _bands(ry, key="tl_year_bands", doubt=ry.timeline.sun_pess is not None and not S.is_public(), events=False)
    _doubt_note(ry)
    mdf = _monthly(ry)
    if not mdf[["Sol visible (%)", "Tierra visible (%)", "Sol y Tierra (%)"]].to_numpy().any():
        st.info("Gráfica mensual omitida: ni el Sol ni la Tierra son visibles en ningún mes de este año desde este punto.",
                icon=":material/visibility_off:")
    else:
        _month_chart(mdf)
    st.dataframe(mdf, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%.1f") for c in mdf.columns if c.endswith("(%)")})
    _csv_button(mdf, "Descargar resumen mensual (CSV)", "lsi_resumen_mensual.csv", "tl_year_csv")
    if C.show_for("planificador"):
        dark = sorted(ry.timeline.dark.windows, key=lambda w: -w.duration_s)[:5]
        if dark:
            st.markdown("**Las noches más largas del año**")
            st.dataframe(pd.DataFrame([{"Inicio (UTC)": _utc(w.start_et), "Vuelve el Sol (UTC)": "—" if w.right_truncated else _utc(w.end_et),
                                        "Duración": C.fmt_duration(w.duration_s, _trunc(w))} for w in dark]),
                         hide_index=True, width="stretch")
    C.download_buttons(ry, key="tl_year_dl")


# ------------------------------------------------------------------------------------------------ vista: animación
def _sync_cursor(akey: str, res) -> None:
    i = int(st.session_state[akey])
    st.session_state[K.CURSOR_UTC] = S.fmt_utc(theme.et_to_datetimes([res.sky.et[i]])[0])


def _step(akey: str, d: int, n: int, res) -> None:
    st.session_state[akey] = (int(st.session_state[akey]) + d) % n
    _sync_cursor(akey, res)


def _next_event(res, body: Body, et: float) -> str:
    evs = [e for e in res.timeline.events if e.body == body]
    j = bisect.bisect_right([e.et for e in evs], et)
    if j >= len(evs):
        return "sin más cambios en el periodo"
    e = evs[j]
    return f"{_EV_NAME[(e.body, e.kind)].lower()} en {C.fmt_duration(e.et - et)} ({_utc(e.et)} UTC)"


def _view_anim(res) -> None:
    req, et = res.request, res.sky.et
    span_d = (res.timeline.et1 - res.timeline.et0) / 86400.0
    opts = {"Un día (24 h)": 1.0, "Un día lunar (≈ 29,5 d)": SYNODIC_D, "Todo el periodo": span_d}
    c1, c2, c3 = st.columns(3)
    rng = c1.selectbox("Tramo a animar", list(opts), index=0 if span_d < 3 else 1, key="_tl_anim_rng")
    speed = int(c2.select_slider("Velocidad (pasos por avance)", [1, 3, 6, 18, 72], value=6, key="_tl_anim_speed"))
    play = c3.toggle("Reproducir", value=False, key="_tl_play",
                     help="Desactivado por defecto; la reproducción nunca recalcula, solo recorre lo ya calculado.")
    n = int(min(len(et), opts[rng] * 86400.0 / req.step_s + 1))
    akey = f"_tl_anim_{req.start_utc}_{req.end_utc}_{rng}_{n}"       # al cambiar tramo/periodo el control vuelve a 0
    if n < 2:
        st.info("El periodo es demasiado corto para animar.", icon=":material/info:")
        return

    @st.fragment(run_every=0.6 if play else None)
    def frame() -> None:
        ss = st.session_state
        if play:    # avance previo a instanciar el slider: es la única forma de moverlo sin callback
            ss[akey] = (int(ss.get(akey, 0)) + speed) % n
        b1, b2, b3 = st.columns([1, 1, 6])
        b1.button("Anterior", icon=":material/skip_previous:", key="_tl_prev", on_click=_step, args=(akey, -speed, n, res))
        b2.button("Siguiente", icon=":material/skip_next:", key="_tl_next", on_click=_step, args=(akey, speed, n, res))
        i = b3.select_slider("Instante (UTC)", options=range(n), key=akey, on_change=_sync_cursor, args=(akey, res),
                      format_func=lambda j: _utc(float(et[j])))
        cols = st.columns(2)
        for col, tr, name, body in ((cols[0], res.sky.sun, "Sol", Body.SUN), (cols[1], res.sky.earth, "Tierra", Body.EARTH)):
            with col:
                C.metric_card(f"{name}: elevación", f"{C.fmt_num(tr.el_deg[i], 1)}° · az {C.fmt_num(tr.az_deg[i], 0)}°",
                              delta=C.state_label(body_state(res.horizon, tr, i, res.timeline.series)))
                st.caption(f"Próximo cambio: {_next_event(res, body, float(et[i]))}.")
        C.accessible_chart(horizon_cartesian(res.horizon, res.sky, res.timeline.series, idx=i),
                           f"Perfil de horizonte con el Sol a {C.fmt_num(res.sky.sun.el_deg[i], 1)}° y la Tierra a {C.fmt_num(res.sky.earth.el_deg[i], 1)}° "
                           f"de elevación el {_utc(float(et[i]))} UTC.", key="tl_anim_horizon")
        if C.show_for("planificador"):
            _bands(res, key="tl_anim_bands", cursor=float(et[i]), doubt=False, events=False)
        st.caption(theme.GEOMETRIC_NOTE)

    frame()


# ------------------------------------------------------------------------------------------------ página
st.title("Línea temporal de la misión")
req = S.request_or_stop()
res, err = cache.try_analysis(req)
if err:
    C.warnings_band()
    C.show_error(err)
    st.stop()
C.warnings_band(res)
C.result_header(res)

view = st.radio("Vista", [V_PER, V_CMP, V_YEAR, V_ANIM], horizontal=True, key="_tl_view")
{V_PER: _view_period, V_CMP: _view_compare, V_YEAR: _view_year, V_ANIM: _view_anim}[view](res)
