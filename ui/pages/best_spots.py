"""Pantalla «Mejores puntos y fechas»: dónde y CUÁNDO aterrizar dentro de un recorte DEM (reto NASA: comparar sitios y fechas).

No calcula física: lee los mapas de ventana de misión PRECALCULADOS por ``scripts/precompute_suitability.py``
(``windows_<Site>_<perfil>_<hash>.json`` + el ``.npz`` con la caché por hash) y reutiliza funciones puras de
``lsi.analysis.suitability_map`` (``build_window_top``). Sin esos ficheros muestra cómo generarlos.
"""
from __future__ import annotations

import dataclasses
import glob
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lsi.analysis import suitability_map as sm
from lsi.contracts import LSIError, StateKey as K
from lsi.data import cache as cache_mod, catalog
from lsi.visualization import theme
from ui import cache, components as C, state as S

TARGET_PAGE = "ui/pages/horizon_visibility.py"
PRECOMPUTE_CMD = ("python scripts/precompute_suitability.py Site04 Site11 Site23 --profile lander_solar_no_rhu "
                  "--profile rover --duration 7 --duration 14 --duration 30 --top 10")
LAYERS = {"score": "Mejor score alcanzable", "f_sun": "Fracción de Sol (f_sol)", "f_earth": "Tierra visible (geometría)",
          "d_max_h": "Oscuridad máxima (h)"}
LINK_LAYER = "ENLACE POSIBLE (f_enlace: Tierra con margen y red)"   # mapas con ``params.link_network``; los antiguos son geometría


def _link_net(doc: dict) -> str | None:
    """Red del enlace con la que se precalculó el mapa (None = mapa antiguo o sin red: ``f_earth`` es solo geometría)."""
    return (doc.get("params") or {}).get("link_network")
PROFILE_LABEL = {"lander_solar_no_rhu": "Lander solar sin RHU", "rover": "Rover"}
GATE_TEXT = {"PASS": "✔ Apto", "FAIL": "✖ No apto", "NO_DATA": "? Sin datos suficientes"}
GRAY = "#7c8498"


# ------------------------------------------------------------------------------------------------ datos precalculados
def _dir() -> Path:
    """Carpeta de mapas precalculados (``LSI_SUITABILITY_DIR`` la redirige: pruebas)."""
    env = os.environ.get("LSI_SUITABILITY_DIR")
    return Path(env) if env else Path(cache.get_context().root) / cache.get_context().cfg["cache"]["dir"] / sm.KIND


def available() -> dict[tuple[str, str], str]:
    """{(sitio, perfil): ruta del JSON de ventanas más reciente}."""
    out: dict[tuple[str, str], tuple[float, str]] = {}
    for f in glob.glob(str(_dir() / "windows_*.json")):
        try:
            head = json.loads(Path(f).read_text(encoding="utf-8"))
            if head.get("schema_version") != "lsi.suitability.windows/1":
                continue
            first = next(iter(head["results"].values()))
            k = (first["site"], first["profile"])
        except (OSError, ValueError, StopIteration, KeyError):
            continue
        t = os.path.getmtime(f)
        if k not in out or t > out[k][0]:
            out[k] = (t, f)
    return {k: v[1] for k, v in sorted(out.items())}


@st.cache_resource(max_entries=8, show_spinner="Cargando el mapa precalculado…")
def _load(path: str, mtime: float):
    """(SuitabilityMap | None, dict del JSON). El mapa sale de la caché por hash; None si el ``.npz`` ya no está."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    ctx = cache.get_context()
    first = next(iter(doc["results"].values()))
    profile = catalog.score_profiles(ctx.cfg)[first["profile"]]
    load = getattr(sm, "load_map", None) or sm._load      # M5: pública si el núcleo la expone
    return load(_dir().parent, doc["key"], profile), doc


@st.cache_resource(max_entries=16, show_spinner=False)
def _top(path: str, mtime: float, duration: float, n: int):
    m, _ = _load(path, mtime)
    wm = m.windows[duration]
    return sm.build_window_top(wm, m.x_m, m.y_m, m.layers, dataclasses.replace(m.params, top_n=n))


# ------------------------------------------------------------------------------------------------ figuras
def _fig_map(m: sm.SuitabilityMap, wm: sm.WindowMap, layer: str, top, sel: int, layers: dict = LAYERS) -> go.Figure:
    km = lambda a: np.asarray(a) / 1000.0   # noqa: E731
    x, y = km(m.x_m), km(m.y_m)[::-1]                       # y creciente; la fila 0 es el norte
    steep = np.where(m.aptitude == sm.APT_STEEP, 1.0, np.nan)[::-1]
    z = wm.best_raster(layer)[::-1]
    fig = go.Figure()
    fig.add_trace(go.Heatmap(x=x, y=y, z=steep, colorscale=[[0, GRAY], [1, GRAY]], showscale=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="Gris: no apto por pendiente",
                             marker=dict(size=12, symbol="square", color=GRAY)))
    fig.add_trace(go.Heatmap(x=x, y=y, z=z, colorscale="Viridis", reversescale=(layer == "d_max_h"),
                             colorbar=dict(title=dict(text=layers[layer], side="right"), tickfont=dict(color=theme.MUTED)),
                             hovertemplate="x %{x:.2f} km · y %{y:.2f} km<br>" + layers[layer] + ": %{z:.2f}<extra></extra>"))
    for s in top:
        on = s.rank - 1 == sel
        fig.add_trace(go.Scatter(
            x=[s.x_m / 1000.0], y=[s.y_m / 1000.0], mode="markers+text", text=[str(s.rank)], textposition="middle center",
            name=f"#{s.rank}", showlegend=False, textfont=dict(color="#000", size=12 if on else 10),
            marker=dict(size=26 if on else 20, symbol="diamond", color=theme.SUN, line=dict(color="#000", width=3 if on else 1.5)),
            hovertemplate=f"#{s.rank} · {C.fmt_num(s.lat_deg, 3)}°, {C.fmt_num(s.lon_deg_e, 3)}°E · score {C.fmt_num(s.score, 0)}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="◆ Puntos candidatos (número = posición)",
                             marker=dict(size=12, symbol="diamond", color=theme.SUN, line=dict(color="#000", width=1.5))))
    fig.update_xaxes(title="x polar estereográfica (km)", scaleanchor="y", constrain="domain")
    fig.update_yaxes(title="y (km)")
    theme.apply_theme(fig, f"Mapa de {m.dem_key}: {layers[layer].lower()} (mejor fecha de inicio de cada punto)", height=560)
    fig.update_layout(legend=dict(orientation="h", y=-0.15))
    return fig


def _fig_calendar(wm: sm.WindowMap, p: int, start0, best_idx: int, night_limit: Optional[float]) -> go.Figure:
    dates = [start0 + timedelta(days=float(i) * wm.step_days) for i in range(wm.n_starts)]
    score, dmax, ok = wm.cube["score"][p], wm.cube["d_max_h"][p], wm.cube["gate"][p] == 0
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4])
    fig.add_trace(go.Scatter(x=dates, y=score, mode="lines", line=dict(color=theme.MUTED, width=1), showlegend=False,
                             hoverinfo="skip"), row=1, col=1)
    for mask, name, sym, col in ((ok, "● Inicio apto (todas las puertas)", "circle", theme.OVERLAP),
                                 (~ok, "✕ Inicio no apto", "x", theme.BAD)):
        idx = np.nonzero(mask)[0]
        fig.add_trace(go.Scatter(x=[dates[i] for i in idx], y=score[idx], mode="markers", name=name,
                                 marker=dict(size=6, symbol=sym, color=col),
                                 hovertemplate="%{x|%Y-%m-%d}<br>score %{y:.1f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=[dates[best_idx]], y=[score[best_idx]], mode="markers", name="★ Mejor fecha de inicio",
                             marker=dict(size=16, symbol="star", color=theme.SUN, line=dict(color="#000", width=1))),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=dmax, mode="lines", line=dict(color=theme.EARTH, width=2), name="Oscuridad máxima en la ventana",
                             hovertemplate="%{x|%Y-%m-%d}<br>%{y:.1f} h<extra></extra>"), row=2, col=1)
    if night_limit is not None:
        fig.add_hline(y=night_limit, line=dict(color=theme.WARN, dash="dash"), row=2, col=1,
                      annotation_text=f"Límite de la puerta de noche: {night_limit:g} h", annotation_font_color=theme.WARN)
    fig.update_yaxes(title="Score (0–100)", row=1, col=1)
    fig.update_yaxes(title="Oscuridad máx. (h)", row=2, col=1)
    fig.update_xaxes(title="Fecha de inicio de la misión (UTC)", row=2, col=1)
    theme.apply_theme(fig, f"Calendario: cada fecha de inicio posible ({wm.duration_days:g} d de misión)", height=560)
    fig.update_layout(legend=dict(orientation="h", y=-0.2))
    return fig


# ------------------------------------------------------------------------------------------------ callbacks
def _evaluate(lat: float, lon: float, utc: str, days: float, profile: str) -> None:
    """Fija punto, inicio y duración en el estado compartido; la navegación se hace al final de la ejecución."""
    S.set_point(lat, lon, label=f"{C.fmt_num(lat, 4)}°, {C.fmt_num(lon, 4)}°E")
    S.set_period(S.parse_utc(utc), days)
    if profile in cache.get_context().panels.profiles:
        S.set_state(K.SCORE_PROFILE, profile)
    st.session_state["_bp_go"] = True


# ------------------------------------------------------------------------------------------------ página
def _explain() -> None:
    st.markdown(
        "**Cómo leer esto.** El score evalúa la **ventana de misión** (de la fecha de inicio a inicio + duración), no un año "
        "entero: un punto con 0 h de oscuridad lo está solo en ciertas fechas. **«Candidato» no es «aprobado»:** es una "
        "ordenación geométrica con umbrales por calibrar, no una decisión de misión. El mapa se calculó con muestreo grueso "
        "(malla de 250 m, horizonte cada 1° de azimut, serie cada 30 min sin refinar); el error frente al modelo fino se mide "
        "en la validación del mapa. El punto por defecto de la app ya no es la pared de "
        "Shackleton: esta pantalla es la forma de encontrar los mejores candidatos y luego evaluarlos con detalle.")


def main() -> None:
    st.title("Mejores puntos y fechas")
    C.warnings_band()
    ctx = cache.get_context()
    files = available()
    if not files:
        st.warning("Todavía no hay mapas de ventana de misión precalculados. Genéralos (tarda unos minutos por sitio y perfil):",
                   icon=":material/hourglass_empty:")
        st.code(PRECOMPUTE_CMD, language="bash")
        return

    C.public_note("Esta pantalla responde a dos preguntas: **dónde** aterrizar y **cuándo**. Elige un sitio y cuánto durará la "
                  "misión; el mapa pinta los mejores puntos con un número y la tabla dice qué día conviene empezar. "
                  "Es una propuesta de candidatos, geométrica, para comparar: no una aprobación.")

    sites = sorted({s for s, _ in files})
    name_of = {s.dem_prefix: s.name for s in ctx.sites if s.dem_prefix}
    c = st.columns(4)
    site = c[0].selectbox("Sitio con DEM", sites, key="_bp_site", index=sites.index("Site23") if "Site23" in sites else 0,
                          format_func=lambda s: name_of.get(s, s))
    profs = [p for s, p in files if s == site]
    want = S.get_str(K.SCORE_PROFILE)
    prof = c[1].selectbox("Perfil de misión", profs, key="_bp_profile", index=profs.index(want) if want in profs else 0,
                          format_func=lambda p: PROFILE_LABEL.get(p, p))
    path = files[(site, prof)]
    mtime = os.path.getmtime(path)
    try:
        m, doc = _load(path, mtime)
    except (LSIError, OSError, ValueError, KeyError) as e:
        C.show_error(f"No se pudo leer el mapa precalculado: {e}")
        st.code(PRECOMPUTE_CMD, language="bash")
        return
    if m is None or not m.windows:
        st.warning("Existe el resumen JSON pero falta la caché de datos del mapa (.npz). Vuelve a ejecutarlo (reaprovecha lo que quede):",
                   icon=":material/warning:")
        st.code(PRECOMPUTE_CMD, language="bash")
        return
    durs = sorted(m.windows)
    dur = c[2].selectbox("Duración de la misión", durs, key="_bp_dur", index=durs.index(14.0) if 14.0 in durs else 0,
                         format_func=lambda d: f"{d:g} días")
    net = _link_net(doc)
    layers = {**LAYERS, **({"f_earth": LINK_LAYER} if net else {})}
    layer = c[3].selectbox("Colorear el mapa por", list(layers), key="_bp_layer", format_func=layers.get)
    n = st.slider("Puntos candidatos (TOP-N)", 3, 10, 5, key="_bp_topn") if not S.is_public() else 3
    wm = m.windows[dur]
    top = _top(path, mtime, dur, n)
    if not top:
        st.warning("Ningún punto de este recorte cumple el límite de pendiente de aterrizaje del perfil.", icon=":material/warning:")
        return
    rec = doc["results"][f"{site}|{prof}|{dur:g}d"]
    if net:
        st.caption(f":material/satellite_alt: La «Tierra» de este mapa es el **ENLACE POSIBLE**: Tierra con margen de elevación del perfil Y alguna estación de la red "
                   f"{net} viendo la Luna. No es la Tierra visible (geometría) ni un presupuesto de enlace. El score usa este enlace.")
    else:
        st.warning("Este mapa se precalculó **sin red de estaciones**: la «Tierra» es solo visibilidad geométrica (la Tierra sobre el horizonte), no un enlace posible. "
                   "Vuelve a ejecutar el precálculo para obtener el enlace.", icon=":material/satellite_alt:")
    st.caption(f"{rec['n_candidates']} puntos aptos por pendiente de {m.n_grid} de la malla · {wm.n_starts} fechas de inicio "
               f"({rec['first_start_utc'][:10]} a {rec['last_start_utc'][:10]}) · pendiente máx. p90 {m.slope_limit_deg:g}°")

    # --- selección de punto (antes de pintar el mapa, que lo resalta)
    if st.session_state.get("_bp_point") not in range(len(top)):
        st.session_state["_bp_point"] = 0
    sel = st.selectbox("Punto para ver su calendario y evaluarlo", range(len(top)), key="_bp_point",
                       format_func=lambda i: f"#{top[i].rank} · {C.fmt_num(top[i].lat_deg, 3)}°, {C.fmt_num(top[i].lon_deg_e, 3)}°E · score {C.fmt_num(top[i].score, 0)}")
    s = top[sel]

    if S.is_public():
        st.markdown(f"**Dónde y cuándo aterrizar.** El mejor punto de {name_of.get(site, site)} para una misión de {dur:g} días está en "
                    f"{C.fmt_num(s.lat_deg, 2)}°, {C.fmt_num(s.lon_deg_e, 2)}°E. Lo ideal es empezar el {s.best_start_utc[:10]} (UTC), con el Sol visible el "
                    f"{C.fmt_pct(s.f_sun, 0)} del tiempo y " + (f"enlace posible con la Tierra el {C.fmt_pct(s.f_earth, 0)}. " if net else
                                                                f"la Tierra a la vista (geometría) el {C.fmt_pct(s.f_earth, 0)}. ")
                    + 
                    f"Hay {s.apt_start_days:g} de {s.n_starts} fechas de inicio al año que sirven, así que la fecha importa.")

    left, right = st.columns([3, 2])
    with left:
        fig = _fig_map(m, wm, layer, top, sel, layers)
        C.accessible_chart(fig, f"Mapa del recorte {site} coloreado por {layers[layer].lower()}; los puntos grises no cumplen la pendiente de "
                           f"aterrizaje y los rombos numerados son los {len(top)} mejores puntos.", key="_bp_map",
                           details=[f"#{t.rank}: {C.fmt_num(t.lat_deg, 3)}°, {C.fmt_num(t.lon_deg_e, 3)}°E, score {C.fmt_num(t.score, 0)}, inicio {t.best_start_utc[:10]}" for t in top])
    with right:
        rows = []
        for t in top:
            r = {"#": t.rank, "Lat (°)": round(t.lat_deg, 3), "Lon (°E)": round(t.lon_deg_e % 360, 3),
                 "Mejor inicio (UTC)": t.best_start_utc[:10],
                 "Score (rango)": f"{C.fmt_num(t.score, 0)} ({C.fmt_num(t.score_min, 0)}–{C.fmt_num(t.score_max, 0)})"}
            if not S.is_public():
                r.update({"f_sol": C.fmt_pct(t.f_sun, 0), ("f_enlace" if net else "f_Tierra (geometría)"): C.fmt_pct(t.f_earth, 0),
                          "Oscuridad máx. (h)": C.fmt_num(t.d_max_h, 1), "Inicios aptos": f"{t.apt_start_days:g} de {t.n_starts}",
                          "Puertas": GATE_TEXT.get(t.gate_status, t.gate_status)})
            if S.is_expert():
                r["Pendiente p90 (°)"] = round(t.slope_p90_deg, 1)
            rows.append(r)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("«Inicios aptos» = fechas de inicio del año con TODAS las puertas en «apto». El rango del score refleja la "
                   "resolución temporal de la rejilla, no la incertidumbre total.")

    # --- calendario del punto elegido
    pos = np.nonzero((wm.rows == int(np.argmin(abs(m.y_m - s.y_m)))) & (wm.cols == int(np.argmin(abs(m.x_m - s.x_m)))))[0]
    if pos.size:
        p = int(pos[0])
        best_idx = int(wm.best["start_idx"][p])
        start0 = S.parse_utc(rec["first_start_utc"])
        st.subheader(f"Calendario del punto #{s.rank}")
        C.accessible_chart(_fig_calendar(wm, p, start0, best_idx, rec.get("night_limit_h")),
                           f"Para cada fecha de inicio del año, score y oscuridad máxima de la ventana de {dur:g} días. La mejor fecha es "
                           f"{s.best_start_utc[:10]} y hay {s.apt_start_days:g} de {s.n_starts} fechas aptas.", key="_bp_cal")

    st.button("Evaluar este punto y fecha", key="_bp_eval", type="primary", icon=":material/rocket_launch:", on_click=_evaluate,
              args=(s.lat_deg, s.lon_deg_e, s.best_start_utc, dur, prof),
              help="Fija este punto, la fecha de inicio y la duración, y abre «Horizonte y visibilidad» con el modelo fino.")
    with st.container(border=True):
        _explain()
    if S.is_expert():
        with st.expander("Parámetros del cálculo"):
            st.json({"clave_caché": doc["key"][:16], **doc["params"]})
    if st.session_state.pop("_bp_go", False):
        try:
            st.switch_page(TARGET_PAGE)
        except st.errors.StreamlitAPIException:
            st.success(f"Punto y fecha fijados ({C.fmt_num(s.lat_deg, 3)}°, {C.fmt_num(s.lon_deg_e, 3)}°E, {s.best_start_utc[:10]}). "
                       "Abre «Horizonte y visibilidad» en el menú para ver el resultado.", icon=":material/check_circle:")


main()
