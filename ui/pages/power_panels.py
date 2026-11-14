"""Paneles y potencia (RF-18..RF-25, RF-40): % de potencia nominal y de carga de batería según el panel, el montaje y el lugar.

La página NO calcula: pinta lo que devuelven ``ui.cache`` (``get_analysis``/``get_power``) y ``lsi.visualization``.
Única excepción declarada: la demostración «la orientación pesa más que la tecnología» llama a ``lsi.energy.panels``
(``incidence_cos`` e ``iam``) para obtener sus razones; no están escritas a mano.
Los widgets de la página usan claves ``_pp_*``; el estado compartido (paneles, montaje, polvo, degradación) solo se
escribe desde callbacks, de modo que la barra lateral y esta página quedan siempre de acuerdo.
"""
from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lsi.contracts import (
    BatteryParams, HorizonMode, LSIError, MountingSpec, MountingType, PowerParams, PowerSeries, StateKey as K,
)
from lsi.energy import panels as pn
from lsi.visualization import power_plot, theme
from ui import cache, components as C, state as S

MOUNT_LABELS = {
    "horizontal": "Horizontal (tumbado)", "tilted": "Inclinado", "vertical_fixed": "Vertical fijo (con azimut)",
    "vertical_az_tracking": "Vertical con seguimiento azimutal", "two_axis": "Dos ejes (cota ideal)",
    "terrain_normal": "Paralelo al suelo",
}
CONF_BADGE = {"publicado": ("green", ":material/verified:", "publicado"), "estimado": ("orange", ":material/rule:", "estimado"),
              "suposicion": ("blue", ":material/edit_note:", "suposición"), "a_verificar": ("red", ":material/help:", "a verificar")}
_CONF_ORDER = ("publicado", "estimado", "suposicion", "a_verificar")
DEMO_ELEVATIONS = (1.0, 1.5, 3.0)
TRIO = ("tj-gaas-lander-body", "tj-gaas-vertical-mast", "mj-4j-high-eff")
MAX_PLOT_POINTS = 6000


# ------------------------------------------------------------------------------------------------ callbacks
def _on_panels() -> None:
    ids = list(st.session_state["_pp_panels"])
    st.session_state[S.PANEL_IDS] = ids
    st.session_state[K.PANEL_ID] = ids[0] if ids else None


def _on_trio(ids: list[str]) -> None:
    st.session_state[S.PANEL_IDS] = ids
    st.session_state[K.PANEL_ID] = ids[0]


def _push(canon: str, wkey: str, scale: float | None = None) -> None:
    v = st.session_state[wkey]
    st.session_state[canon] = v if scale is None else v * scale


# ------------------------------------------------------------------------------------------------ datos de la ficha
@st.cache_data(max_entries=1, show_spinner=False)
def _raw_catalog() -> dict:
    """panels.json tal cual (solo para mostrar misiones y fuentes, que ``PanelSpec`` no lleva)."""
    return {p["id"]: p for p in json.loads((cache.ROOT / "config" / "panels.json").read_text(encoding="utf-8"))["panels"]}


def _overall_conf(panel) -> str:
    """Etiqueta global del dato: la peor entre la eficiencia y el coeficiente de temperatura (los dos que mueven el %)."""
    got = [panel.confidence.get(k, "a_verificar") for k in ("eta_bol", "temp_coeff_per_k")]
    return max(got, key=lambda c: _CONF_ORDER.index(c) if c in _CONF_ORDER else 3)


EST_LABEL = "estimación sin datasheet"
DOC_EVIDENCE = "docs/validation/datos-paneles.md"
EVID_LABEL = {"datasheet": "datasheet leído", "paper": "paper/informe de agencia leído", "derivado": "derivado de fuente (con fórmula)",
              "investigacion": "investigación, sin datasheet"}
GROUP_TITLE = {"respaldado": "Paneles respaldados (datasheet, paper o derivado)",
               "experimental_sin_datasheet": "Experimental sin datasheet (η o γ_T sin fuente primaria)"}


def _estimated(panel) -> bool:
    return getattr(panel, "uses_estimates", False)


def _fmt_range(panel, name: str, scale: float = 1.0, nd: int = 2, unit: str = "") -> str:
    r = getattr(panel, "ranges", {}).get(name)
    if not r:
        return ""
    lo, hi = sorted(v * scale for v in r)
    return f" (rango {C.fmt_num(lo, nd)} a {C.fmt_num(hi, nd)}{unit and ' ' + unit})"


def _evid(panel) -> str:
    """«respaldado · datasheet leído» / «experimental sin datasheet · investigación, sin datasheet»."""
    g = "experimental sin datasheet" if getattr(panel, "evidence_group", "") == "experimental_sin_datasheet" else "respaldado"
    return f"{g} · {EVID_LABEL.get(getattr(panel, 'evidence_level', ''), 'sin nivel')}"


def _w_m2(panel, p_rel: float | None) -> str:
    """Potencia eléctrica absoluta por m² de panel (celda/CIC, sin empaquetado): P_rel × η_bol × 1361 W/m² (panels.py)."""
    a = getattr(panel, "areal_power_w_m2_am0", None)
    return C.fmt_num(None if a is None or p_rel is None else a * p_rel, 0)


def _by_group(runs, by_id) -> dict:
    return {g: [r for r in runs if getattr(by_id[r.panel_id], "evidence_group", "respaldado") == g] for g in pn.EVIDENCE_GROUPS}


def _badge(conf: str, prefix: str = "") -> None:
    color, icon, text = CONF_BADGE.get(conf, CONF_BADGE["a_verificar"])
    st.badge(f"{prefix}{text}", icon=icon, color=color)


def _short(name: str, n: int = 64) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def _fmt_conf_field(label: str, value: str, conf: str) -> str:
    return f"{label}: {value} ({CONF_BADGE.get(conf, CONF_BADGE['a_verificar'])[2]})"


def _panel_card(panel, raw: dict) -> None:
    st.markdown(f"**{panel.name}**")
    conf = _overall_conf(panel)
    _badge(conf, "Dato ")
    st.badge(_evid(panel), icon=":material/fact_check:", color="orange" if panel.evidence_group != "respaldado" else "green")
    if panel.evidence_summary:
        st.caption(f"Evidencia: {panel.evidence_summary} Fuente por parámetro y página: `{DOC_EVIDENCE}`.")
    if _estimated(panel):
        st.badge(EST_LABEL, icon=":material/science:", color="orange")
        st.caption(panel.estimate_note)
    st.caption(f"Tecnología: {panel.cell_technology}")
    eta = "sin dato" if panel.eta_bol is None else C.fmt_num(100 * panel.eta_bol, 1, "%") + _fmt_range(panel, "eta_bol", 100, 1, "%")
    st.markdown("- " + _fmt_conf_field("Eficiencia (inicio de vida)", eta, panel.confidence.get("eta_bol", "a_verificar")))
    if panel.areal_power_w_m2_am0 is not None:
        rg = panel.ranges.get("eta_bol")
        wr = "" if not rg else f" (rango {C.fmt_num(min(rg) * ctx.panels.solar_constant_w_m2, 0)} a {C.fmt_num(max(rg) * ctx.panels.solar_constant_w_m2, 0)} W/m²)"
        st.markdown(f"- Potencia eléctrica de celda en AM0 a 1 UA: {C.fmt_num(panel.areal_power_w_m2_am0, 0)} W/m² de panel (η × 1361 W/m²){wr}; "
                    "sin empaquetado, cableado ni estructura.")
    if C.show_for("planificador"):
        tc = "sin dato (no calculable)" if panel.temp_coeff_per_k is None else C.fmt_num(100 * panel.temp_coeff_per_k, 2, "%/K") + _fmt_range(panel, "temp_coeff_per_k", 100, 2, "%/K")
        st.markdown("- " + _fmt_conf_field("Coef. de temperatura", tc, panel.confidence.get("temp_coeff_per_k", "a_verificar")))
        st.markdown("- Montajes admitidos: " + ", ".join(MOUNT_LABELS.get(m.value, m.value) for m in panel.mounting_allowed))
    if panel.description:
        st.caption(panel.description)
    miss = raw.get("missions", [])
    if miss:
        st.markdown("**Misiones que lo usan o proponen**")
        for m in miss:
            c = CONF_BADGE.get(m.get("confidence", "a_verificar"), CONF_BADGE["a_verificar"])[2]
            st.markdown(f"- {m['name']} ({c}). {m.get('role', '')}")
    src = raw.get("sources", [])
    if src:
        st.markdown("**Fuentes**")
        for s in src:
            st.markdown(f"- [{s['id']}] [{s['ref']}]({s['url']})")


# ------------------------------------------------------------------------------------------------ demostración
def _demo(ctx, panel) -> None:
    """Vertical con seguimiento vs horizontal a poca elevación solar, calculado con ``energy.panels`` (no escrito a mano)."""
    hor, ver = MountingSpec(MountingType.HORIZONTAL), MountingSpec(MountingType.VERTICAL_AZ_TRACKING)
    rows = []
    for el in DEMO_ELEVATIONS:
        ch, cv = float(pn.incidence_cos(0.0, el, hor)), float(pn.incidence_cos(0.0, el, ver))
        eh = ch * float(pn.iam(np.degrees(np.arccos(ch)), panel.iam))
        ev = cv * float(pn.iam(np.degrees(np.arccos(cv)), panel.iam))
        rows.append((el, ch, cv, cv / ch, ev / eh if eh > 0 else float("inf")))
    etas = [(p.eta_bol, p.name) for p in ctx.panels.panels if p.eta_bol]
    hi, lo = max(etas), min(etas)
    tech = hi[0] / lo[0]
    with st.container(border=True):
        st.subheader(":material/explore: La orientación pesa más que la tecnología de la célula")
        cols = st.columns(len(rows) + 1)
        for col, (el, _ch, _cv, ratio, _r2) in zip(cols, rows):
            col.metric(f"Sol a {C.fmt_num(el, 1, '°')} de elevación", f"≈ {C.fmt_num(ratio, 0)}×",
                       help="Luz que recibe un panel vertical que gira hacia el Sol frente a uno horizontal (solo geometría: cos θ).")
        cols[-1].metric("Mejor vs peor tecnología (eficiencia)", f"≈ {C.fmt_num(tech, 1)}×",
                        help=f"{_short(hi[1], 30)} ({C.fmt_num(100 * hi[0], 0, '%')}) frente a {_short(lo[1], 30)} "
                             f"({C.fmt_num(100 * lo[0], 0, '%')}). Varias eficiencias están «a verificar».")
        st.markdown("Con el Sol casi rasante, como en el polo sur, un panel **vertical orientado hacia el Sol** recibe entre "
                    f"{C.fmt_num(rows[-1][3], 0)} y {C.fmt_num(rows[0][3], 0)} veces más luz que uno **horizontal**; "
                    f"cambiar la tecnología de la célula solo mejora, como mucho, {C.fmt_num(tech, 1)} veces.")
        if C.show_for("planificador"):
            df = pd.DataFrame([{"Elevación solar (°)": C.fmt_num(el, 1), "cos θ horizontal": C.fmt_num(ch, 4),
                                "cos θ vertical con seguimiento": C.fmt_num(cv, 4), "Razón solo geometría": C.fmt_num(r, 1) + "×",
                                "Razón con pérdida por reflexión (IAM)": C.fmt_num(r2, 0) + "×"} for el, ch, cv, r, r2 in rows])
            st.dataframe(df, hide_index=True, width="stretch")
        st.caption("Calculado con `energy.panels.incidence_cos` e `iam` (Fresnel, una interfaz). La razón con IAM es mayor porque "
                   "la reflexión en la cubierta penaliza aún más la incidencia rasante del panel horizontal, la parte más "
                   "incierta del modelo. Estimación, no predicción de misión.")


# ------------------------------------------------------------------------------------------------ figuras y tablas
def _thin(s: PowerSeries) -> PowerSeries:
    k = -(-len(s.et) // MAX_PLOT_POINTS)
    if k <= 1:
        return s
    return dataclasses.replace(s, **{f.name: getattr(s, f.name)[::k] for f in dataclasses.fields(s) if isinstance(getattr(s, f.name), np.ndarray)})


def _battery_fig(runs, labels, bp: BatteryParams) -> go.Figure:
    fig = go.Figure()
    for i, (r, lab) in enumerate(zip(runs, labels)):
        b, k = r.battery, max(-(-len(r.battery.et) // MAX_PLOT_POINTS), 1)
        fig.add_trace(go.Scatter(x=theme.et_to_datetimes(b.et[::k]), y=100.0 * b.soc[::k], mode="lines", name=lab,
                                 line=dict(color=theme.SERIES_COLORS[i % 6], dash=theme.SERIES_DASH[i % 6], width=2.2),
                                 hovertemplate=lab + "<br>%{y:.1f} % de carga<extra></extra>"))
    fig.add_hline(y=100 * bp.soc_min, line=dict(color=theme.BAD, dash="dot"), annotation_text="Carga mínima permitida",
                  annotation_font_color=theme.MUTED)
    fig.update_yaxes(title_text="Carga de la batería (%)", range=[0, 105])
    fig.update_xaxes(title_text="Tiempo (UTC)")
    return theme.apply_theme(fig, "Carga de la batería (% de su capacidad)", height=420,
                             note="Estimación con consumo constante y supuestos editables; no es una predicción de misión.")


def _csv_bytes(runs, sky) -> bytes:
    s0 = runs[0].series
    df = pd.DataFrame({"utc": [t.strftime("%Y-%m-%dT%H:%M:%S") for t in theme.et_to_datetimes(s0.et)],
                       "sun_el_deg": np.round(np.interp(s0.et, sky.et, sky.sun.el_deg), 4)})
    for r in runs:
        df[f"{r.panel_id}__{r.mounting.type.value}__p_rel_pct"] = np.round(100.0 * r.series.p_rel, 4)
        if r.battery is not None:
            df[f"{r.panel_id}__carga_bateria_pct"] = np.round(100.0 * r.battery.soc, 4)
    return df.to_csv(index=False).encode("utf-8")


def _mount_text(m: MountingSpec) -> str:
    t = MOUNT_LABELS.get(m.type.value, m.type.value)
    if m.type is MountingType.TILTED and m.tilt_deg is not None:
        t += f" {m.tilt_deg:g}°"
    if m.azimuth_deg is not None:
        t += f", azimut {m.azimuth_deg:g}°"
    return t


# ------------------------------------------------------------------------------------------------ página
ctx = cache.get_context()
S.init_state(ctx)
st.title(":material/solar_power: Paneles y potencia")
st.caption("Cuánta potencia daría cada tipo de panel solar en este lugar y periodo, **en % de su propia potencia nominal**. "
           "Es una estimación con supuestos declarados, no una predicción de la potencia de una misión.")

req = S.current_request()
if req is None:
    C.warnings_band()
    S.request_or_stop()
# El análisis (Sol, horizonte, ventanas) no depende del panel: se normaliza para no recalcularlo al cambiar de panel,
# montaje, batería, polvo o degradación (todo eso va a ``get_power`` y reutiliza este análisis).
areq = dataclasses.replace(req, panel_id=None, mounting=None, battery=None, degradation=0.0, dust_loss=0.0)
res, err = cache.try_analysis(areq)
C.warnings_band(res, power=True)
if err:
    C.show_error(err)
    st.stop()
C.result_header(res)
if res.observer.mode is HorizonMode.FAR_FIELD:
    st.warning(f"**{C.FAR_LABEL}.** La potencia usa el horizonte del DEM de 80 m. " + C.far_field_note(), icon=":material/terrain:")
if res.observer.mode is HorizonMode.SMOOTH_SPHERE:
    st.warning("**Este lugar no tiene datos de terreno (esfera lisa).** La potencia se calcula igualmente, con horizonte plano "
               "(solo la curvatura lunar): sin montañas que den sombra, así que el resultado es optimista.", icon=":material/public:")

catalog = ctx.panels
by_id = {p.id: p for p in catalog.panels}
raw = _raw_catalog()

# --- demostración destacada
_demo(ctx, by_id.get(S.get_state(K.PANEL_ID)) or catalog.panels[0])

# --- selección de paneles y montaje
st.header("1. Elige paneles y montaje")
ss = st.session_state
ss["_pp_panels"] = [p for p in ss[S.PANEL_IDS] if p in by_id]
ss["_pp_mount"] = ss[K.MOUNT_TYPE]
ss["_pp_tilt"], ss["_pp_maz"] = float(ss[K.MOUNT_TILT]), float(ss[K.MOUNT_AZ])
ss["_pp_deg"], ss["_pp_dust"] = 100.0 * float(ss[K.DEGRADATION]), 100.0 * float(ss[K.DUST_LOSS])
st.multiselect("Tipos de panel (puedes comparar varios)", list(by_id), key="_pp_panels", on_change=_on_panels,
               format_func=lambda i: f"{_short(by_id[i].name)} — {_evid(by_id[i])}",
               help="El % de potencia es relativo a la nominal de cada panel. Las etiquetas indican cuánto fiarse de sus datos.")
trio = [i for i in TRIO if i in by_id]
if len(trio) == len(TRIO):
    st.button("Comparar tres tecnologías típicas", on_click=_on_trio, args=(trio,), icon=":material/compare:",
              help="GaAs de lander, array vertical en mástil y 4J de alta eficiencia.")
sel = [by_id[i] for i in ss["_pp_panels"]]
if not sel:
    st.info("Elige al menos un tipo de panel para ver su potencia.", icon=":material/info:")
    st.stop()

mount_opts = [m for m in ("horizontal", "tilted", "vertical_fixed", "vertical_az_tracking")]
if ss["_pp_mount"] not in mount_opts:
    mount_opts.append(ss["_pp_mount"])
c1, c2, c3 = st.columns([2, 1, 1])
c1.selectbox("Montaje", mount_opts, key="_pp_mount", format_func=lambda v: MOUNT_LABELS.get(v, v),
             on_change=S.choose_mount, args=("_pp_mount",),
             help="Cómo está orientado el panel. Los paneles que no admiten ese montaje usan el suyo por defecto (se indica en la tabla).")
C.polar_horizontal_warning(ss[K.OBS_LAT], ss["_pp_mount"])
if ss["_pp_mount"] == MountingType.TILTED.value:
    c2.number_input("Inclinación (°)", 0.0, 90.0, key="_pp_tilt", step=1.0, on_change=_push, args=(K.MOUNT_TILT, "_pp_tilt"))
if ss["_pp_mount"] in (MountingType.TILTED.value, MountingType.VERTICAL_FIXED.value):
    c3.number_input("Azimut de la normal (°)", 0.0, 360.0, key="_pp_maz", step=5.0, on_change=_push, args=(K.MOUNT_AZ, "_pp_maz"),
                    help="Hacia dónde mira el panel, desde el Norte hacia el Este: 0° N, 90° E, 180° S, 270° O.")

with st.expander("Ficha de cada panel: tecnología, eficiencia, misiones y fuentes", expanded=len(sel) == 1):
    for p in sel:
        _panel_card(p, raw.get(p.id, {}))
        st.divider()

# --- supuestos editables
degr, dust = float(ss[K.DEGRADATION]), float(ss[K.DUST_LOSS])
bat_params = None
if C.show_for("planificador"):
    with st.expander("Supuestos editables: polvo, degradación y batería"):
        a, b = st.columns(2)
        a.number_input("Degradación por radiación (%)", 0.0, 90.0, key="_pp_deg", step=1.0, on_change=_push,
                       args=(K.DEGRADATION, "_pp_deg", 0.01), help="Suposición de LSI: 0 % = inicio de vida. Sin fuente genérica para misiones lunares.")
        b.number_input("Pérdida por polvo (%)", 0.0, 90.0, key="_pp_dust", step=1.0, on_change=_push,
                       args=(K.DUST_LOSS, "_pp_dust", 0.01),
                       help="Escenario de sensibilidad (suposición): no hay cifra publicada fiable de pérdida por polvo lunar, y el polvo no está modelado por defecto.")
        cold = catalog.cold_gain_cap_default
        th = ctx.cfg["power"]["thermal"]
        st.caption(f"Supuestos fijos del modelo (suposición, no editables aquí): tope de ganancia en frío ×{C.fmt_num(cold, 2)}; "
                   f"temperatura del entorno {C.fmt_num(float(th['t_ambient_k']), 0, 'K')} y temperatura mínima de validez "
                   f"{C.fmt_num(float(th['t_min_valid_k']), 0, 'K')} (por debajo, la eficiencia queda acotada y se marca con «x»); "
                   "pérdida por reflexión de la cubierta (IAM de Fresnel, una interfaz). Sin sombra propia ni albedo.")
        st.checkbox("Calcular también la carga de una batería", key="_pp_bat_on")
        if ss.get("_pp_bat_on"):
            d1, d2, d3 = st.columns(3)
            cap = d1.number_input("Capacidad (Wh)", 1.0, 1e6, 700.0, step=50.0, key="_pp_bat_cap",
                                  help="Ejemplo: 25 Ah × 28 V = 700 Wh (Nova-C, fuente secundaria). Valor por calibrar.")
            pnom = d2.number_input("Potencia nominal del panel (W)", 1.0, 1e6, 200.0, step=10.0, key="_pp_bat_pnom",
                                   help="Potencia con el Sol de frente; el % de la gráfica se multiplica por ella. Ejemplo: 200 W (Nova-C).")
            load = d3.number_input("Consumo constante (W)", 0.0, 1e6, 50.0, step=5.0, key="_pp_bat_load",
                                   help="Ejemplo: 50 W de supervivencia (suposición de LSI).")
            e1, e2, e3 = st.columns(3)
            soc0 = e1.number_input("Carga inicial (%)", 0.0, 100.0, 50.0, step=5.0, key="_pp_bat_soc0")
            smin = e2.number_input("Carga mínima permitida (%)", 0.0, 100.0, 20.0, step=5.0, key="_pp_bat_smin")
            smax = e3.number_input("Carga máxima (%)", 1.0, 100.0, 100.0, step=5.0, key="_pp_bat_smax")
            ech = edis = 0.95
            if C.show_for("experto"):
                f1, f2 = st.columns(2)
                ech = f1.number_input("Rendimiento de carga", 0.5, 1.0, 0.95, step=0.01, key="_pp_bat_ech")
                edis = f2.number_input("Rendimiento de descarga", 0.5, 1.0, 0.95, step=0.01, key="_pp_bat_edis")
            if not (0.0 <= smin < smax <= 100.0 and smin <= soc0 <= smax):
                st.error("Revisa los límites: la carga mínima debe ser menor que la máxima y la inicial debe estar entre ambas.",
                         icon=":material/error:")
            else:
                bat_params = BatteryParams(cap, pnom, load, soc0 / 100.0, smin / 100.0, smax / 100.0, ech, edis)

# --- cálculo (cacheado; reutiliza Sol y horizonte del análisis)
specs = [(p.id, S.mounting_for(ctx, p.id)) for p in sel]
try:
    runs = cache.get_power(areq, specs, bat_params, degr, dust)
except (LSIError, ValueError) as e:
    C.show_error(e)
    st.stop()
ok = [r for r in runs if r.series is not None]
for r in runs:
    if r.error:
        st.warning(f"**{by_id[r.panel_id].name}**: no calculable (faltan datos mínimos y no hay estimación razonable). {r.error}",
                   icon=":material/block:")
for r in ok:
    C.mount_fallback_notice(areq, r.panel_id, S.wanted_mount(None, res.observer.lat_deg), r.mounting, ctx,
                            who=f"{_short(by_id[r.panel_id].name, 40)}: " if len(ok) > 1 else "")
if not ok:
    st.stop()
est_ok = [by_id[r.panel_id] for r in ok if _estimated(by_id[r.panel_id])]
if est_ok:
    st.warning("**Estimación sin datasheet.** " + ", ".join(f"«{_short(p.name, 40)}»" for p in est_ok) + ": no hay datasheet leído; sus "
               "parámetros térmicos y ópticos son estimaciones de LSI con rango (ver la ficha y las fuentes). El resultado es orientativo y la "
               "sombra de la gráfica es el rango de incertidumbre de esos parámetros, no un error estadístico.", icon=":material/science:")
labels = [f"{_short(by_id[r.panel_id].name, 48)} · {MOUNT_LABELS.get(r.mounting.type.value, r.mounting.type.value)}" for r in ok]
span_s = float(ok[0].series.et[-1] - ok[0].series.et[0])
days = span_s / 86400.0
thr = ok[0].summary.useful_threshold

# --- modo Público: frases llanas
st.header("2. Qué potencia daría")
C.public_note("El porcentaje compara cada panel consigo mismo: 100 % es su potencia nominal con el Sol de frente (con mucho frío "
              "puede superarse ligeramente). "
              "No son vatios de ninguna misión real.")
if S.is_public():
    for r, lab in zip(ok, labels):
        sm = r.summary
        pct_time = 100.0 * sm.hours_above_useful * 3600.0 / span_s
        st.markdown(f"- **{lab}** ({_evid(by_id[r.panel_id])}): produciría de media un **{C.fmt_num(100 * sm.mean_p_rel, 0)} %** de su potencia máxima en "
                    f"{res.observer.label or 'este lugar'} durante este periodo, con picos del **{C.fmt_num(100 * sm.peak_p_rel, 0)} %**, "
                    f"y estaría por encima del {C.fmt_num(100 * thr, 0)} % el {C.fmt_num(pct_time, 0)} % del tiempo.")

# --- curvas
day_opts = ["Todo el periodo"]
day_starts = {}
for d in ok[0].summary.daily:
    lab = theme.et_to_datetimes(d.day_start_et + 3600.0)[0].strftime("%Y-%m-%d")
    day_starts[lab] = d.day_start_et
    day_opts.append(lab)
if ss.get("_pp_day") not in day_opts:
    ss["_pp_day"] = day_opts[0]
if len(day_opts) > 2:
    st.selectbox("Ver", day_opts, key="_pp_day", help="Un día UTC concreto para ver la forma de la curva con detalle.")
zero_power = all(r.summary.peak_p_rel <= 0 for r in ok)
if zero_power:      # nunca una gráfica plana sin explicación
    C.empty_state("Estos paneles dan un 0 % de potencia en todo el periodo: el Sol no es visible en ningún momento desde este "
                  "punto. Prueba otra fecha o busca el mejor punto en «Mejores puntos y fechas».")
_th = ctx.cfg["power"]["thermal"]


def _curves(gruns: list, glabels: list, key: str) -> None:
    """Un gráfico por grupo de evidencia; la sombra solo en paneles con rango (los experimentales)."""
    fig = power_plot.power_curves([_thin(r.series) for r in gruns], sky=res.sky, labels=glabels)
    for i, r in enumerate(gruns):
        pnl = by_id[r.panel_id]
        ts = _thin(r.series)
        band = pn.power_band(ts, pnl, PowerParams(r.panel_id, r.mounting, t_ambient_k=float(_th["t_ambient_k"]),
                                                  t_min_valid_k=float(_th["t_min_valid_k"])), catalog) if _estimated(pnl) else None
        if band is not None:
            h = theme.SERIES_COLORS[i % 6].lstrip("#")
            x = theme.et_to_datetimes(ts.et)
            fig.add_trace(go.Scatter(x=x, y=100.0 * band[0], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"),
                          row=1, col=1, secondary_y=False)
            fig.add_trace(go.Scatter(x=x, y=100.0 * band[1], mode="lines", line=dict(width=0), fill="tonexty", showlegend=False,
                                     fillcolor="rgba(%d,%d,%d,0.22)" % tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)),
                                     hovertemplate=glabels[i] + "<br>máx. del rango: %{y:.1f} %<extra></extra>"), row=1, col=1, secondary_y=False)
    if ss.get("_pp_day") in day_starts:
        t0 = day_starts[ss["_pp_day"]]
        a, b = theme.et_to_datetimes([t0, t0 + 86400.0])
        fig.update_xaxes(range=[a, b])
    alt = "Curvas del % de potencia nominal a lo largo del tiempo, con la elevación solar en el eje derecho. " + " ".join(
        f"{lab}: media {C.fmt_num(100 * r.summary.mean_p_rel, 1)} %, pico {C.fmt_num(100 * r.summary.peak_p_rel, 1)} %." for r, lab in zip(gruns, glabels))
    C.accessible_chart(fig, alt, key=key, details=[
        f"{lab}: {C.fmt_num(100 * r.summary.mean_p_rel, 1)} % de media, {C.fmt_num(100 * r.summary.peak_p_rel, 1)} % de pico "
        f"({_w_m2(by_id[r.panel_id], r.summary.mean_p_rel)} W/m² de media), "
        f"{C.fmt_duration(r.summary.hours_above_useful * 3600.0)} por encima del umbral útil." for r, lab in zip(gruns, glabels)])


lab_of = dict(zip((r.panel_id for r in ok), labels))
groups = _by_group(ok, by_id)
if not zero_power:
    for g, gruns in groups.items():     # respaldados y experimentales SIEMPRE por separado y etiquetados
        if gruns:
            st.subheader(GROUP_TITLE[g])
            if g != "respaldado":
                st.caption("Sin datasheet primario de η o γ_T: no se mezclan con los respaldados. Origen y nivel de cada parámetro en "
                           f"`{DOC_EVIDENCE}`.")
            _curves(gruns, [lab_of[r.panel_id] for r in gruns], "_pp_curves" if g == "respaldado" else "_pp_curves_exp")
if est_ok:
    rngs = sorted({k for p in est_ok for k in p.ranges})
    nm = {"eta_bol": "eficiencia", "temp_coeff_per_k": "coeficiente de temperatura", "alpha_front": "absorción", "emissivity_front": "emisividad frontal",
          "emissivity_back": "emisividad trasera"}
    st.caption("Sombra de color = rango de incertidumbre (mín–máx) solo de los parámetros con rango en el catálogo (" + ", ".join(nm.get(k, k) for k in rngs) +
               "); la línea es el valor central. Los paneles respaldados no llevan sombra: sus parámetros no tienen rango en el catálogo. "
               "La batería usa solo el valor central.")
if len(ok[0].series.et) > MAX_PLOT_POINTS:
    st.caption("La gráfica está submuestreada para que sea fluida; la tabla y el CSV usan todos los pasos.")

# --- tabla comparativa
if C.show_for("planificador"):
    st.subheader("Comparación")
    for g, gruns in groups.items():
        if not gruns:
            continue
        st.markdown(f"**{GROUP_TITLE[g]}**")
        rows = []
        for r in gruns:
            sm, p = r.summary, by_id[r.panel_id]
            rows.append({
                "Panel": p.name, "Montaje aplicado": _mount_text(r.mounting),
                "Potencia media (% nominal)": C.fmt_num(100 * sm.mean_p_rel, 1), "Pico (% nominal)": C.fmt_num(100 * sm.peak_p_rel, 1),
                "Potencia media (W/m² de panel)": _w_m2(p, sm.mean_p_rel), "Pico (W/m² de panel)": _w_m2(p, sm.peak_p_rel),
                f"% del periodo con potencia ≥ {C.fmt_num(100 * thr, 0)} %": C.fmt_num(100.0 * sm.hours_above_useful * 3600.0 / span_s, 1),
                "Energía incidente útil (Wh/m² por día)": C.fmt_num(sm.e_inc_wh_m2 / days, 0),
                "Energía eléctrica (Wh/m² por día)": C.fmt_num(None if sm.e_el_wh_m2 is None else sm.e_el_wh_m2 / days, 0),
                "% del máximo teórico": C.fmt_num(sm.pct_of_max, 1), "Dato": CONF_BADGE.get(_overall_conf(p), CONF_BADGE["a_verificar"])[2],
                "Evidencia": _evid(p), "Parámetros": EST_LABEL if _estimated(p) else "con datos de fuente"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"Umbral útil = {C.fmt_num(100 * thr, 0)} % de la nominal (perfil de misión elegido en la barra lateral; suposición editable por perfil). "
               "W/m² de panel = % de potencia × η inicial × 1361 W/m² (potencia de celda/CIC en AM0, sin empaquetado, cableado ni estructura; "
               "un array real rinde menos). «Máximo teórico» = panel de dos ejes, a 1 UA y siempre iluminado. La energía eléctrica usa la "
               "eficiencia inicial del panel y queda en «—» si ese dato falta.")
    if C.show_for("experto"):
        with st.expander("Detalle experto: temperatura de panel y extrapolación en frío"):
            ex = []
            for r in ok:
                s = r.series
                lit = s.f_sun > 0
                ex.append({"Panel": by_id[r.panel_id].name,
                           "T panel mín–máx con Sol (°C)": "—" if not lit.any() else f"{C.fmt_num(s.t_panel_k[lit].min() - 273.15, 0)} – {C.fmt_num(s.t_panel_k[lit].max() - 273.15, 0)}",
                           "Pasos con extrapolación en frío": C.fmt_pct(float(s.t_clamped.mean()), 1),
                           "Incidencia máx. con Sol (°)": "—" if not lit.any() else C.fmt_num(float(s.theta_deg[lit].max()), 1)})
            st.dataframe(pd.DataFrame(ex), hide_index=True, width="stretch")
            day_rows = [{"Panel": lab, "Día UTC": theme.et_to_datetimes(d.day_start_et + 3600.0)[0].strftime("%Y-%m-%d"),
                         "Media (%)": C.fmt_num(100 * d.e_rel, 1), "Pico (%)": C.fmt_num(100 * d.peak_p_rel, 1),
                         "Horas ≥ umbral": C.fmt_num(d.hours_above_useful, 1)}
                        for r, lab in zip(ok, labels) for d in r.summary.daily]
            st.dataframe(pd.DataFrame(day_rows), hide_index=True, width="stretch")

# --- avisos contextuales de la potencia
seen, shown = set(), []
for r in ok:
    for w in r.warnings:
        key = (w.code, w.context)
        if key not in seen:
            seen.add(key)
            shown.append(w)
with st.container(border=True):
    st.markdown("**:material/warning: Cómo leer estas cifras**")
    for w in shown:
        st.caption(f"• {w.text_es}" + (f" ({by_id[w.context].name})" if w.context in by_id else ""))
    st.caption("• El % es relativo a la potencia nominal de cada panel; no incluye eclipses, polvo (salvo el escenario que elijas), "
               "sombra propia ni albedo.")

# --- batería
if bat_params is not None:
    st.header("3. Carga de la batería")
    bruns = [(r, lab) for r, lab in zip(ok, labels) if r.battery is not None]
    for r, lab in bruns:
        bt = r.battery
        if bt.hours_unserved > 0:
            idx = int(np.argmax(bt.soc <= bat_params.soc_min + 1e-9))
            when = theme.et_to_datetimes(bt.et[idx])[0].strftime("%Y-%m-%d %H:%M")
            st.error(f"**{lab}**: la batería llega a su carga mínima el {when} UTC y deja de poder alimentar el consumo "
                     f"durante {C.fmt_duration(bt.hours_unserved * 3600.0)} (energía no servida: {C.fmt_num(bt.unserved_wh, 0, 'Wh')}).",
                     icon=":material/battery_alert:")
        else:
            st.success(f"**{lab}**: la batería no se agota en este periodo (carga mínima alcanzada: {C.fmt_num(100 * bt.min_soc, 0)} %).",
                       icon=":material/battery_full:")
    if bruns:
        C.accessible_chart(_battery_fig([r for r, _ in bruns], [lab for _, lab in bruns], bat_params),
                           "Carga de la batería en % de su capacidad a lo largo del periodo. " + " ".join(
                               f"{lab}: mínimo {C.fmt_num(100 * r.battery.min_soc, 0)} %, horas sin suministro {C.fmt_num(r.battery.hours_unserved, 1)}."
                               for r, lab in bruns), key="_pp_battery")

# --- descarga
st.download_button("Descargar series (CSV)", data=lambda: _csv_bytes(ok, res.sky), file_name="lsi_potencia_paneles.csv",
                   mime="text/csv", on_click="ignore", key="_pp_csv", icon=":material/download:",
                   help="Una fila por instante: UTC, elevación solar, % de potencia de cada panel y, si la hay, carga de la batería.")
C.glossary_expander()
