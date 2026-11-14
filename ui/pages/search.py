"""Buscador de cráteres y rasgos lunares por nombre (RF-10, RF-47, RF-48; arquitectura §11.2).

Búsqueda difusa sin acentos ni mayúsculas sobre el gazetteer oficial USGS/IAU, filtros por tipo y región, tabla ordenable,
ficha del rasgo, mini-mapa y «Evaluar este lugar» (DEM / mejor punto o punto más cercano del DEM / esfera lisa). Esta página no calcula: usa
``lsi.data.gazetteer`` (búsqueda), ``ui.cache.get_snap`` (modo de evaluación) y ``ui.state.set_point``.
"""
from __future__ import annotations

import difflib

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lsi import pipeline
from lsi.contracts import GazetteerQuery, StateKey as K
from lsi.data import gazetteer as gz
from lsi.visualization import theme
from ui import cache, components as C, state as S

TARGET_PAGE = "ui/pages/horizon_visibility.py"
RESULT_LIMIT = 200
EXAMPLES = ("Shackleton", "Apolo 11", "Malapert", "Tycho", "Mar de la Tranquilidad")
REGION_ES = {"polo_sur": "Polo sur (< −80°)", "sur": "Sur (−80° a −30°)", "ecuatorial": "Ecuatorial (−30° a 30°)",
             "norte": "Norte (30° a 80°)", "polo_norte": "Polo norte (> 80°)"}
TYPE_ES = {"Crater": "cráter", "Satellite Feature": "cráter satélite", "Sitio de misión": "alunizaje, impacto o candidato", "Mons": "monte", "Rima": "grieta sinuosa",
           "Dorsum": "cresta", "Mare": "mar", "Lacus": "lago", "Catena": "cadena de cráteres", "Vallis": "valle",
           "Sinus": "bahía", "Promontorium": "promontorio", "Rupes": "escarpe", "Statio": "lugar de alunizaje",
           "Palus": "pantano", "Planitia": "llanura", "Oceanus": "océano", "Astronaut-named features": "rasgo con nombre de astronauta",
           "Albedo Feature": "rasgo de albedo"}
CONF_COLOR = {"publicado": "green", "aprox": "orange", "a verificar": "red"}
CONF_HELP = {"publicado": "coordenada publicada por la agencia o por una fuente de referencia",
             "aprox": "coordenada aproximada: puede distar varios km del punto real",
             "a verificar": "coordenada sin verificar"}
PLAIN_NO_DEM = ("No todos los lugares tienen relieve porque solo se dispone de mapas de altura de alta resolución en unas pocas "
                "zonas del polo sur. En el resto la Luna se trata como una bola lisa: la curvatura cuenta, las montañas no, "
                "y el resultado es solo una referencia optimista, no comparable con los lugares con relieve.")


# ------------------------------------------------------------------------------------------------ estado y callbacks
def _sync(canon: str, wkey: str) -> None:
    st.session_state[canon] = st.session_state[wkey]


def _pick_text(text: str) -> None:
    """Ejemplos y sugerencias: fijan texto y quitan filtros."""
    st.session_state.update({"_s_q": text, K.SEARCH_QUERY: text, "_s_types": [], K.SEARCH_TYPES: [],
                             "_s_regions": [], K.SEARCH_REGIONS: [], "_s_dem": False})


def _evaluate(fid: int, lat: float, lon: float, label: str, relief: bool, choose: bool = False,
              best_start: str | None = None, days: float | None = None) -> None:
    """Fija punto, preferencia de snap y, si se eligió el mejor punto, su mejor fecha de inicio (conservando la duración)."""
    prefer = st.session_state.get("_s_opt", "best") if choose else None
    S.set_point(lat, lon, gazetteer_id=fid, label=label, snap_prefer=prefer)
    if relief:
        S.set_state(K.FORCE_SPHERE, False)       # la insignia promete relieve: no puede quedar «esfera lisa» forzada
    if prefer == "best" and best_start:
        S.set_period(S.parse_utc(best_start), max(S.period_days(), days or 0.0))
    st.session_state["_s_go"] = True


@st.cache_data(max_entries=64, ttl=cache.TTL_S, show_spinner=False)
def _snap(fid: int, lat: float, lon: float, prefer: str, profile_id, mission_days):
    """Como ``cache.get_snap`` pero acotado al entorno del rasgo (radio = diámetro/2 del gazetteer), igual que el análisis:
    así el punto, su posición respecto al borde y la fecha sugerida que se muestran son los que se evaluarán."""
    ctx = cache.get_context()
    rad = pipeline.feature_radius_km(ctx, fid) if prefer == "best" else None
    return pipeline.snap_candidate(ctx, lat, lon, prefer=prefer, profile_id=profile_id, mission_days=mission_days,
                                   feature_radius_km=rad)


@st.cache_data(show_spinner=False)
def _suggest(names: tuple[str, ...], q: str) -> list[str]:
    return difflib.get_close_matches(q, names, n=5, cutoff=0.4)


# ------------------------------------------------------------------------------------------------ piezas
def _badge(has_dem: bool) -> str:
    return "DEM disponible" if has_dem else "sin relieve"


def _type(t: str) -> str:
    return f"{t} ({TYPE_ES[t]})" if t in TYPE_ES else t


def _table(entries, conf: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Nombre": e.name, "Tipo": _type(e.feature_type), "Coordenada": conf.get(e.feature_id) or "oficial IAU",
        "Diámetro (km)": e.diameter_km, "Latitud (°)": e.lat_deg, "Longitud E (°)": e.lon_deg_e,
        "Relieve": ("✔ " if e.has_dem else "○ ") + _badge(e.has_dem), "ID": e.feature_id} for e in entries])


def _minimap(entries, sel_id: int) -> None:
    fig = go.Figure()
    for has, name, color, sym in ((True, "DEM disponible", theme.OVERLAP, "diamond"), (False, "sin relieve", theme.EARTH, "circle")):
        es = [e for e in entries if e.has_dem is has and e.feature_id != sel_id]
        fig.add_scatter(x=[e.lon_deg_e for e in es], y=[e.lat_deg for e in es], mode="markers", name=name,
                        text=[e.name for e in es], marker=dict(color=color, symbol=sym, size=9),
                        hovertemplate="%{text}<br>%{y:.2f}°, %{x:.2f}°E<extra></extra>")
    s = next(e for e in entries if e.feature_id == sel_id)
    fig.add_scatter(x=[s.lon_deg_e], y=[s.lat_deg], mode="markers", name="Seleccionado", text=[s.name],
                    marker=dict(color=theme.SUN, symbol="star", size=17, line=dict(color=theme.TEXT, width=1)),
                    hovertemplate="%{text}<br>%{y:.2f}°, %{x:.2f}°E<extra></extra>")
    theme.apply_theme(fig, "Dónde están los resultados", height=340)
    fig.update_xaxes(title="Longitud Este (°)")
    fig.update_yaxes(title="Latitud (°)")
    alt = (f"Mapa plano de la Luna con {len(entries)} resultado(s); {sum(e.has_dem for e in entries)} con relieve (rombos). "
           f"Seleccionado: {s.name}, a {s.lat_deg:.2f}° de latitud y {s.lon_deg_e:.2f}° de longitud Este (estrella).")
    C.accessible_chart(fig, alt, key="_s_map")


def _detail(e, row) -> None:
    with st.container(border=True):
        st.subheader(e.name)
        st.badge(_badge(e.has_dem), icon=":material/terrain:" if e.has_dem else ":material/public:",
                 color="green" if e.has_dem else "orange")
        site = e.feature_type == gz.SITE_TYPE
        if site:
            conf = str(row.get("confianza", "") or "a verificar")
            st.badge(f"Coordenada: {conf}", icon=":material/pin_drop:", color=CONF_COLOR.get(conf, "red"))
            st.caption(CONF_HELP.get(conf, ""))
        C.metric_card("Tipo", _type(e.feature_type) if e.feature_type in TYPE_ES else f"{e.feature_type} (rasgo)")  # fila propia: no se trunca
        a, b = st.columns(2)
        with a:
            C.metric_card("Diámetro", e.diameter_km, unit="km", nd=1)
        with b:
            C.metric_card("Coordenadas", f"{e.lat_deg:.3f}°, {e.lon_deg_e:.3f}°E")
        status = str(row.get("approval_status", "") or "—")
        yr = f" ({e.approval_year})" if e.approval_year else ""
        st.markdown(f"**Estado de aprobación:** {status}{yr}  \n**Región:** {REGION_ES.get(e.region, e.region)}"
                    + (f"  \n**Cuadrángulo:** {e.quad}" if e.quad else ""))
        st.markdown(f"**{'Programa y fuente' if site else 'Origen del nombre'}:** {e.origin or 'no consta en el gazetteer.'}")
        if not site:
            st.link_button("Ficha oficial (USGS, IAU)", f"https://planetarynames.wr.usgs.gov/Feature/{e.feature_id}",
                           icon=":material/open_in_new:")


def _ranking_table(snap) -> pd.DataFrame:
    return pd.DataFrame([{"Puesto": r.rank, "Latitud (°)": r.lat_deg, "Longitud E (°)": r.lon_deg_e, "Mejor inicio (UTC)": r.best_start_utc,
                          "Sol visible (fracción)": r.f_sun, "Noche máx. (h)": r.d_max_h, "Score": r.score, "Puertas": r.gate_status,
                          "Distancia al rasgo (km)": r.distance_km} for r in snap.ranking])


def _evaluate_panel(e) -> None:
    """Dice CLARAMENTE cómo se evaluará el lugar y ofrece el botón. El modo lo decide el DEM; si el rasgo cae fuera del DEM
    se ofrecen DOS puntos: el mejor del DEM para el perfil y la duración elegidos (candidato propuesto) y el más cercano al rasgo."""
    st.markdown("#### Evaluar este lugar")
    ctx = cache.get_context()
    pid, days = S.get_str(K.SCORE_PROFILE) or None, S.effective_mission_days(ctx)
    snap = None if e.has_dem else _snap(e.feature_id, e.lat_deg, e.lon_deg_e, "best", pid, days)
    best = snap if snap is not None and snap.kind == "best" else None
    near = None if snap is None else (best.nearest if best else snap)
    relief = e.has_dem or snap is not None
    what = "cráter" if e.feature_type in ("Crater", "Satellite Feature") else "rasgo"
    choose = best is not None and near is not None
    if e.has_dem:
        st.success(f"**Se evaluará con relieve (modo DEM {e.dem_key})** en el centro del rasgo.", icon=":material/terrain:")
        label = "Evaluar este lugar con relieve"
    elif snap is None:
        st.warning("**Se evaluará en esfera lisa: sin datos de terreno.** No hay mapa de relieve cerca; solo cuenta la curvatura "
                   "lunar, el score será parcial y no es comparable con los lugares con relieve.", icon=":material/public:")
        label = "Evaluar en esfera lisa (sin datos de terreno)"
    else:
        st.info(f"**El centro de {e.name} queda fuera del mapa de terreno ({snap.dem_key}).** Se evaluará con relieve en un punto "
                "del DEM; elige cuál:", icon=":material/near_me:")
        if best is not None:
            r = best.ranking[0] if best.ranking else None
            res = (f" · Sol visible {C.fmt_num(r.f_sun * 100, 0, '%')} · noche máx. {C.fmt_num(r.d_max_h, 0, 'h')} · "
                   f"score {C.fmt_num(r.score, 0)} ({r.gate_status})") if r else ""
            with st.container(border=True):
                st.markdown(f"**A · Mejor punto del DEM para este perfil y {days:g} d (candidato propuesto)**" if days else
                            "**A · Mejor punto del DEM para este perfil (candidato propuesto)**")
                st.markdown(f"{C.fmt_num(best.lat_deg, 4)}°, {C.fmt_num(best.lon_deg_e, 4)}°E · a "
                            f"**{C.fmt_num(best.distance_km, 1, 'km')}** del centro del rasgo{res}  \n"
                            f"**Mejor fecha de inicio sugerida:** {best.best_start_utc} UTC")
                phrase = C.snap_phrase(best.edge_offset_km, best.inside_feature, best.map_rank, what)
                if phrase:
                    st.markdown(f"**Posición respecto al rasgo:** {phrase}.")
                st.caption(best.reason)
        if near is not None:
            with st.container(border=True):
                st.markdown("**B · Punto más cercano al rasgo**" if choose else "**Punto del DEM más cercano al rasgo**")
                st.markdown(f"{C.fmt_num(near.lat_deg, 4)}°, {C.fmt_num(near.lon_deg_e, 4)}°E · a "
                            f"**{C.fmt_num(near.distance_km, 2, 'km')}** del centro. Puede caer en una pared sin Sol: el resultado "
                            "describe ese punto, no el centro del rasgo.")
                nphrase = C.snap_phrase(near.edge_offset_km, None, None, what)
                if nphrase:
                    st.caption(f"Posición respecto al rasgo: {nphrase}.")
                if best is None and snap.reason:
                    st.caption(snap.reason)
        if choose:
            st.radio("Punto a evaluar", ("best", "nearest"), key="_s_opt", horizontal=True,
                     format_func=lambda k: "A · Mejor punto (candidato propuesto)" if k == "best" else "B · Más cercano al rasgo")
        label = "Evaluar este lugar"
        if best is not None and C.show_for("planificador") and best.ranking:
            with st.expander("Ranking de mejores puntos del DEM (mapa de idoneidad)"):
                st.dataframe(_ranking_table(best), hide_index=True, width="stretch",
                             column_config={"Latitud (°)": st.column_config.NumberColumn(format="%.4f"),
                                            "Longitud E (°)": st.column_config.NumberColumn(format="%.4f"),
                                            "Sol visible (fracción)": st.column_config.NumberColumn(format="%.2f"),
                                            "Noche máx. (h)": st.column_config.NumberColumn(format="%.0f"),
                                            "Score": st.column_config.NumberColumn(format="%.0f"),
                                            "Distancia al rasgo (km)": st.column_config.NumberColumn(format="%.1f")})
    if not e.has_dem:
        C.public_note(PLAIN_NO_DEM)
    if C.show_for("planificador"):
        mode = "DEM" if e.has_dem else "esfera lisa" if snap is None else "snap_to_dem"
        st.caption(f"Modo previsto: {mode} · gazetteer_id={e.feature_id}" + (f" · tipo de ajuste: {snap.kind}" if snap else ""))
    st.button(label, type="primary", icon=":material/rocket_launch:", key="_s_eval", on_click=_evaluate,
              args=(e.feature_id, e.lat_deg, e.lon_deg_e, e.name, relief, choose, best.best_start_utc if best else None,
                    best.duration_days if best else None))


# ------------------------------------------------------------------------------------------------ página
def main() -> None:
    st.title("Buscador de lugares lunares")
    C.warnings_band()
    df = cache.get_gazetteer()
    if df is None:
        st.warning("El catálogo de nombres lunares no está generado. Ejecuta `python scripts/fetch_gazetteer.py`; el resto "
                   "de la app funciona sin él.", icon=":material/search_off:")
        return
    n_site = int((df["feature_type"] == gz.SITE_TYPE).sum())
    st.caption(f"{len(df):,} lugares: {len(df) - n_site:,} rasgos con nombre oficial (USGS Gazetteer of Planetary Nomenclature, IAU) "
               f"y {n_site} sitios de misión curados. Sin distinguir mayúsculas ni acentos; tolera erratas; entiende «Apollo»/«Apolo», "
               "nombres en español («Mar de la Tranquilidad») y «Polo sur».".replace(",", " "))

    ss = st.session_state
    for w, canon, dflt in (("_s_q", K.SEARCH_QUERY, ""), ("_s_types", K.SEARCH_TYPES, []), ("_s_regions", K.SEARCH_REGIONS, [])):
        ss.setdefault(w, ss.get(canon, dflt))
    ss.setdefault("_s_dem", False)

    st.text_input("Nombre del cráter o zona", key="_s_q", placeholder="Por ejemplo: Shackleton, Apolo 11, Mar de la Serenidad, Polo sur…",
                  on_change=_sync, args=(K.SEARCH_QUERY, "_s_q"))
    st.caption("Ejemplos:")
    for col, ex in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(ex, key=f"_s_ex_{ex}", on_click=_pick_text, args=(ex,), width="stretch")

    types = gz.list_feature_types(df)
    c1, c2, c3 = st.columns([2, 2, 1])
    c1.multiselect("Tipo de rasgo", [t for t, _ in types], key="_s_types", on_change=_sync, args=(K.SEARCH_TYPES, "_s_types"),
                   format_func=lambda t: f"{t} ({TYPE_ES.get(t, 'rasgo')}) · {dict(types)[t]}", placeholder="Todos")
    c2.multiselect("Región", list(REGION_ES), key="_s_regions", on_change=_sync, args=(K.SEARCH_REGIONS, "_s_regions"),
                   format_func=REGION_ES.get, placeholder="Todas")
    c3.checkbox("Solo con relieve (DEM)", key="_s_dem", help="Muestra solo los rasgos cuyo centro cae dentro de un mapa de terreno.")

    q = GazetteerQuery(text=ss["_s_q"], feature_types=tuple(ss["_s_types"]), regions=tuple(ss["_s_regions"]),
                       only_with_dem=bool(ss["_s_dem"]), limit=RESULT_LIMIT)
    entries = gz.search(df, q)

    if not entries:
        st.info(f"No he encontrado ningún lugar para «{ss['_s_q']}» con esos filtros. Prueba a quitar filtros o revisa la ortografía.",
                icon=":material/search_off:")
        txt = gz.normalize_text(ss["_s_q"])
        if txt:
            sug = _suggest(tuple(df["name_ascii"].unique()), txt)
            names = [df.loc[df["name_ascii"] == s, "name"].iloc[0] for s in sug]
            if names:
                st.markdown("¿Quizá buscabas…?")
                for col, n in zip(st.columns(len(names)), names):
                    col.button(n, key=f"_s_sug_{n}", on_click=_pick_text, args=(n,), width="stretch")
        C.public_note(PLAIN_NO_DEM)
        return

    n_dem = sum(e.has_dem for e in entries)
    more = f" (se muestran los {RESULT_LIMIT} más relevantes)" if len(entries) >= RESULT_LIMIT else ""
    st.markdown(f"**{len(entries)} resultado(s){more}** · {n_dem} con relieve (DEM) · ordena la tabla pulsando en una cabecera.")
    conf = dict(zip(df["feature_id"], df["confianza"]))
    st.dataframe(_table(entries, conf), hide_index=True, width="stretch", height=min(400, 38 + 35 * len(entries)),
                 column_config={"Diámetro (km)": st.column_config.NumberColumn(format="%.1f"),
                                "Latitud (°)": st.column_config.NumberColumn(format="%.3f"),
                                "Longitud E (°)": st.column_config.NumberColumn(format="%.3f")})

    ids = [e.feature_id for e in entries]
    by_id = {e.feature_id: e for e in entries}
    if ss.get("_s_sel") not in ids:
        ss["_s_sel"] = ss.get(K.SEARCH_SELECTED) if ss.get(K.SEARCH_SELECTED) in ids else ids[0]
    st.selectbox("Rasgo para ver en detalle", ids, key="_s_sel", on_change=_sync, args=(K.SEARCH_SELECTED, "_s_sel"),
                 format_func=lambda i: f"{by_id[i].name} · {by_id[i].feature_type} · {_badge(by_id[i].has_dem)}"
                 + (f" · coord. {conf[i]}" if conf.get(i) else ""))
    sel = by_id[ss["_s_sel"]]
    ss[K.SEARCH_SELECTED] = sel.feature_id
    row = df.loc[df["feature_id"] == sel.feature_id].iloc[0]

    left, right = st.columns([3, 2])
    with left:
        _detail(sel, row)
        _evaluate_panel(sel)
    with right:
        _minimap(entries, sel.feature_id)

    if ss.pop("_s_go", False):       # tras pulsar «Evaluar»: ya está el punto fijado; saltar a Horizonte y visibilidad
        try:
            st.switch_page(TARGET_PAGE)
        except st.errors.StreamlitAPIException:
            st.success(f"Punto fijado: {sel.name}. Abre «Horizonte y visibilidad» en el menú para ver el resultado.",
                       icon=":material/check_circle:")


main()
