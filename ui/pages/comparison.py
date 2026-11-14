"""Pantalla D «Comparación de sitios» (arquitectura §11.2, RF-41).

Compara sitios (curados con o sin DEM y puntos propios, hasta 5) y, opcionalmente, dos fechas. Las métricas solar, Tierra,
terreno y confianza se muestran SEPARADAS (nunca fundidas en un número); el mejor de cada una se resalta (negrita +
subrayado + lista de texto) sin imponer un ranking. El score ponderado es OPCIONAL: pesos ajustables, desglose abierto
y explicación de por qué cambia la clasificación. La página no calcula: todo sale de ``ui.cache`` (pipeline) y
``visualization``; aquí solo se ordena, se formatea y se redacta.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Mapping, Optional, Sequence

import pandas as pd
import streamlit as st

from lsi.analysis import export, metrics as metrics_mod
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, STANDARD_WARNINGS_ES, AnalysisRequest, AnalysisResult, HorizonMode, MountingSpec,
    MountingType, Severity, StateKey as K, WarningCode,
)
from lsi.analysis.site_score import profiles_from_config
from lsi.energy.panels import panel_status
from lsi.visualization import comparison_plot

from ui import cache, components as C, state as S

MAX_SITES = 5
WEIGHT_KEYS = ("sun", "night", "earth", "terrain")
WEIGHT_LABELS = {"sun": "Sol", "night": "Noche (oscuridad máxima)", "earth": "Tierra / enlace", "terrain": "Terreno (pendiente)"}
_HANDLED = {WarningCode.NO_DEM_SMOOTH_SPHERE, WarningCode.NO_TERRAIN_DATA_SCORE, WarningCode.CURATED_COORDS_OUTSIDE_DEM}
_CUSTOM_RE = re.compile(r"^@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")


# ------------------------------------------------------------------------------------------------ entradas
@dataclass(frozen=True)
class Entry:
    token: str                 # id curado o «@lat,lon»
    label: str
    site_id: Optional[str]
    lat: float
    lon: float


def custom_token(lat: float, lon: float) -> str:
    return f"@{lat:.4f},{lon % 360.0:.4f}"


def _short(name: str) -> str:
    return name.split()[0] if re.match(r"Site\d+", name) else name


def entries_from_tokens(ctx, tokens: Sequence[str]) -> list[Entry]:
    sites = {s.id: s for s in ctx.sites if s.lat_deg is not None and s.lon_deg_e is not None}
    out = []
    for t in tokens:
        if t in sites:
            s = sites[t]
            out.append(Entry(t, _short(s.name), s.id, float(s.lat_deg), float(s.lon_deg_e) % 360.0))
        elif (m := _CUSTOM_RE.match(t)):
            lat, lon = float(m[1]), float(m[2])
            out.append(Entry(t, f"{C.fmt_num(lat, 3)}°, {C.fmt_num(lon, 3)}°E", None, lat, lon))
    return out


def _option_label(ctx) -> Callable[[str], str]:
    by_id = {s.id: s for s in ctx.sites}

    def f(t: str) -> str:
        if t in by_id:
            s = by_id[t]
            return f"{s.name} — {'con relieve real (DEM)' if s.has_dem else 'sin DEM: esfera lisa'}"
        m = _CUSTOM_RE.match(t)
        return f"Punto propio {C.fmt_num(float(m[1]), 3)}°, {C.fmt_num(float(m[2]), 3)}°E" if m else t
    return f


# ------------------------------------------------------------------------------------------------ callbacks
def _on_pick() -> None:
    st.session_state[K.COMPARE_SITES] = list(st.session_state["cmp_pick"])


def _set_sites(tokens: list[str]) -> None:
    st.session_state[K.COMPARE_SITES] = tokens
    st.session_state["cmp_pick"] = tokens


def _add_custom() -> None:
    ss = st.session_state
    cur = list(ss.get(K.COMPARE_SITES, []))
    tok = custom_token(float(ss["cmp_lat"]), float(ss["cmp_lon"]))
    if len(cur) >= MAX_SITES:
        ss["cmp_msg"] = f"Máximo {MAX_SITES} sitios: quita uno antes de añadir otro."
        return
    ss.pop("cmp_msg", None)
    if tok not in cur:
        _set_sites(cur + [tok])


def _swap_point(site_id: str, lat: float, lon: float) -> None:
    """«Elegir otro punto»: quita el sitio curado y deja sus coordenadas efectivas en el formulario de punto propio."""
    ss = st.session_state
    ss["cmp_lat"], ss["cmp_lon"] = float(lat), float(lon) % 360.0
    ss["cmp_msg"] = "Ajusta latitud y longitud con un punto de cresta o de llanura y pulsa «Añadir punto»."
    _set_sites([t for t in ss.get(K.COMPARE_SITES, []) if t != site_id])


def _reset_weights(pid: str) -> None:
    for k in WEIGHT_KEYS:
        st.session_state.pop(f"cmp_w_{pid}_{k}", None)


# ------------------------------------------------------------------------------------------------ utilidades puras
def best_names(values: Mapping[str, float], higher: bool, pool: Sequence[str]) -> set[str]:
    """Nombres con el mejor valor entre ``pool`` (empates incluidos). Vacío si hay <2 comparables, ningún dato finito o
    todos iguales: resaltar entonces no informaría."""
    vals = {n: values[n] for n in pool if values.get(n) is not None and math.isfinite(values[n])}
    if len(vals) < 2 or len(set(round(v, 9) for v in vals.values())) < 2:
        return set()
    top = max(vals.values()) if higher else min(vals.values())
    return {n for n, v in vals.items() if abs(v - top) < 1e-9}


def ranks(scores: Mapping[str, float]) -> dict[str, int]:
    """Posición 1 = mayor score; empates (a 0,1) comparten posición."""
    r = {n: round(v, 1) for n, v in scores.items()}
    return {n: 1 + sum(1 for m in r.values() if m > r[n]) for n in r}


def table_rows(results: Mapping[str, AnalysisResult]) -> list[dict]:
    return metrics_mod.comparison_table({n: r.metrics for n, r in results.items()})


def csv_bytes(results: Mapping[str, AnalysisResult]) -> bytes:
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as td:
        return export.comparison_to_csv(table_rows(results), Path(td) / "c.csv").read_bytes()


def json_bytes(results: Mapping[str, AnalysisResult], weights: Optional[Mapping[str, float]]) -> bytes:
    """JSON de la comparación: cabecera + el JSON validado (§7) de cada sitio."""
    d = {"lsi_comparison": {"generated_utc": C._stamp(), "n_sites": len(results),
                            "score_weights": dict(weights) if weights else "los del perfil",
                            "note": "Cada métrica por separado; sin ranking. Visibilidad geométrica ≠ potencia ni enlace garantizados."},
         "sites": {n: json.loads(C.result_json_bytes(r)) for n, r in results.items()}}
    return (json.dumps(d, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def is_dem(res: AnalysisResult) -> bool:
    return res.observer.mode is HorizonMode.DEM


def _nan(x) -> float:
    return float("nan") if x is None else float(x)


# ------------------------------------------------------------------------------------------------ tablas por grupo
# (columna, getter, mejor=alto/bajo/None, clave de rango, factor)
def _col(label, getter, higher, rkey=None, f=1.0):
    return (label, getter, higher, rkey, f)


GROUPS: dict[str, list] = {
    "Solar": [
        _col("Fracción con Sol (%)", lambda r: r.metrics.solar_fraction, True, "solar_fraction", 100.0),
        _col("Ventana solar más larga (h)", lambda r: r.metrics.longest_sun_window_s, True, "longest_sun_window_s", 1 / 3600.0),
        _col("Oscuridad máxima (h)", lambda r: r.metrics.max_darkness_s, False, "max_darkness_s", 1 / 3600.0),
        _col("Elevación solar máxima (°)", lambda r: r.metrics.max_sun_elevation_deg, True),
    ],
    "Tierra": [
        _col("Tierra visible, geometría (%)", lambda r: r.metrics.earth_fraction, True, "earth_fraction", 100.0),
        _col("Ventana de Tierra visible más larga (h)", lambda r: r.metrics.longest_earth_window_s, True, "longest_earth_window_s", 1 / 3600.0),
        _col("Sol y Tierra a la vez (%)", lambda r: r.metrics.overlap_fraction, True, "overlap_fraction", 100.0),
        # --- enlace DTE (solo con red elegida): lo que de verdad puntúa la Tierra en el score
        _col("ENLACE POSIBLE (%)", lambda r: r.metrics.link_fraction, True, "link_fraction", 100.0),
        _col("Horas de enlace al día (media)", lambda r: r.metrics.link_hours_per_day_mean, True),
        _col("Ventana de enlace más larga (h)", lambda r: r.metrics.longest_link_window_s, True, "longest_link_window_s", 1 / 3600.0),
        _col("Hueco máximo sin enlace (h)", lambda r: r.metrics.max_link_gap_s, False, "max_link_gap_s", 1 / 3600.0),
    ],
    "Terreno": [
        _col("Pendiente p90 (°)", lambda r: r.slope.percentile_deg if r.slope else None, False),
        _col("Azimutes con horizonte limitado (%)", lambda r: float(r.horizon.limited.mean()) if is_dem(r) and r.horizon.limited.size else None, False, None, 100.0),
        _col("Resolución efectiva del DEM (m)", lambda r: r.dem_confidence.effective_resolution_m if r.dem_confidence else None, False),
    ],
    "Confianza": [
        _col("Confianza global C (0–1)", lambda r: r.score.confidence.c if r.score and r.score.confidence else None, True),
        _col("Azimutes inciertos para el Sol (%)", lambda r: r.metrics.unknown_fraction_sun, False, None, 100.0),
        _col("Azimutes inciertos para la Tierra (%)", lambda r: r.metrics.unknown_fraction_earth, False, None, 100.0),
    ],
}
_TRUNC = {"Ventana solar más larga (h)": "longest_sun_window_truncated", "Oscuridad máxima (h)": "max_darkness_truncated",
          "Ventana de enlace más larga (h)": "longest_link_window_truncated", "Hueco máximo sin enlace (h)": "max_link_gap_truncated"}
_LINK_COLS = {"ENLACE POSIBLE (%)", "Horas de enlace al día (media)", "Ventana de enlace más larga (h)", "Hueco máximo sin enlace (h)"}
G7_NAME = "Hueco máximo sin enlace (G7)"


def _gate_rows(gates) -> list[dict]:
    """``C.gate_rows`` con el nombre de la puerta G7 (hueco máximo sin enlace), que el módulo de componentes aún no rotula."""
    rows = C.gate_rows(gates)
    for g, row in zip(gates, rows):
        if g.id == "G7":
            row["Puerta"] = C.plain_gate_name(G7_NAME)
    return rows


def group_frame(group: str, results: Mapping[str, AnalysisResult], pool: Sequence[str]):
    """(DataFrame ordenable con una fila por sitio, {columna: nombres mejores}, columnas numéricas)."""
    cols = [c for c in GROUPS[group] if c[0] not in _LINK_COLS or any(c[1](r) is not None for r in results.values())]   # sin enlace: sin columnas de enlace
    ranged = any(r.uncertainty for r in results.values())
    rows, best, num = [], {}, []
    for n, r in results.items():
        row: dict = {"Sitio": n}
        if group == "Terreno":
            row["Modo"] = "DEM (relieve real)" if is_dem(r) else "Esfera lisa: sin datos de terreno"
        if group == "Confianza":
            row["Confianza global"] = f"{r.score.confidence.level.value}" if r.score and r.score.confidence else "—"
            row["Confianza del DEM"] = r.dem_confidence.level.value if r.dem_confidence else "sin DEM"
        for label, g, _h, rkey, f in cols:
            v = g(r)
            row[label] = float("nan") if v is None or not math.isfinite(float(v)) else float(v) * f
            if ranged and rkey and group in ("Solar", "Tierra"):
                rg = r.uncertainty.ranges.get(rkey) if r.uncertainty else None
                row[f"{label}: rango"] = f"{C.fmt_num(rg.lo * f, 1)} – {C.fmt_num(rg.hi * f, 1)}" if rg else "—"
        rows.append(row)
    df = pd.DataFrame(rows)
    for label, _g, higher, _rk, _f in cols:
        num.append(label)
        if higher is not None:
            best[label] = best_names(dict(zip(df["Sitio"], df[label])), higher, pool)
    return df, best, num


def styled(df: pd.DataFrame, best: Mapping[str, set], num: Sequence[str]):
    def hl(col):
        b = best.get(col.name, set())
        return ["font-weight:700;text-decoration:underline;background-color:rgba(86,180,233,0.25)" if n in b else ""
                for n in df["Sitio"]]
    sty = df.style.format({c: "{:.1f}" for c in num}, na_rep="—")
    for c in num:
        sty = sty.apply(hl, subset=[c])
    return sty


# ------------------------------------------------------------------------------------------------ avisos por sitio
def _site_warnings(ctx, entries: Sequence[Entry], base: Mapping[str, AnalysisResult]) -> None:
    dem_names = [n for n, r in base.items() if is_dem(r)]
    sphere = [n for n, r in base.items() if not is_dem(r)]
    for n in sphere:
        st.warning(f"**{n}: sin datos de terreno.** Se calcula sobre esfera lisa (sin relieve): su score es parcial y optimista "
                   f"y **no es comparable** con los sitios con DEM, por eso queda fuera de las clasificaciones.",
                   icon=":material/public:")
    if sphere and dem_names:
        st.caption("Hay sitios con y sin DEM en la misma comparación: las métricas se muestran todas, pero los resaltados "
                   "«mejor» solo se calculan entre los que tienen relieve real.")
    seen = set()
    for n, r in base.items():
        o = r.observer
        if o.snap_distance_km is None or o.site_id in seen:
            continue
        seen.add(o.site_id)
        e = next((x for x in entries if x.site_id == o.site_id), None)
        note = (ctx.cfg.get("dem_default_observers", {}).get(o.dem_key or "", {}) or {}).get("note", "")
        inside = ("**El punto por defecto de Site04 está dentro del cráter Shackleton (pared interna)**, no en una cresta. "
                  if o.site_id == "site04" else "")
        st.warning(f"**{n}.** {inside}Las coordenadas curadas caen fuera de su recorte de DEM: se evalúa el punto marcador del recorte, "
                   f"a {C.fmt_num(o.snap_distance_km, 1)} km ({note or 'marcador, no punto óptimo'}). Es un marcador, no un lugar elegido: "
                   f"la poca luz que salga es un resultado correcto, no una conclusión sobre el sitio.", icon=":material/warning:")
        if e is not None:
            st.button(f"Elegir otro punto en lugar de {n}", key=f"cmp_swap_{o.site_id}", icon=":material/edit_location_alt:",
                      on_click=_swap_point, args=(o.site_id, o.lat_deg, o.lon_deg_e),
                      help="Quita el sitio curado y rellena el formulario de punto propio con estas coordenadas para que las cambies.")
    extra = []
    for n, r in base.items():
        for w in r.warnings:
            if w.code not in ALWAYS_SHOWN_WARNINGS and w.code not in _HANDLED and w.severity in (Severity.WARNING, Severity.CRITICAL):
                extra.append(f"**{n}:** {w.text_es}")
    if extra:
        with st.expander(f"Avisos de cada sitio ({len(extra)})"):
            for t in extra:
                st.markdown(f"- {t}")


# ------------------------------------------------------------------------------------------------ recomendación (Público)
_VERDICT_RANK = {"APTO": 3, "CONDICIONAL": 2, "SIN DATOS": 1, "NO APTO": 0}


def panel_text(sc, ctx=None) -> str:
    """«panel · montaje» usado en la energía del score (+ «(estimado)» si el panel no tiene datasheet)."""
    if sc.energy_basis != "panel":
        return "sin panel (Sol geométrico)"
    p = next((x for x in ctx.panels.panels if x.id == sc.energy_panel_id), None) if ctx is not None else None
    est = " (panel estimado)" if p is not None and panel_status(p) == "estimado" else ""
    return f"{p.name if p else sc.energy_panel_id} · {C.MOUNT_LABELS.get(sc.energy_mounting or '', sc.energy_mounting)}{est}"


def verdict_rows(base: Mapping[str, AnalysisResult], ctx=None) -> list[dict]:
    """Una fila por sitio con el veredicto por puertas, su motivo y la ventana de misión."""
    rows = []
    for n, r in base.items():
        sc = r.score
        if sc is None:
            continue
        f = C.scope_figures(r)
        rows.append({"Sitio": n, "Veredicto": C.verdict_label(sc), "Motivo": C.plain_reason(sc.verdict_reason),
                     "Hueco máximo sin comunicaciones (h)": (r.score_inputs.max_link_gap_h if r.score_inputs is not None
                                                             and r.score_inputs.max_link_gap_h is not None else float("nan")),
                     "Panel y montaje": panel_text(sc, ctx), "Rango del score": C.range_label(sc),
                     "Misión (d)": sc.mission_days if sc.mission_days is not None else float("nan"),
                     "Sol en la ventana de misión (%)": f["sun_window_pct"] if f["sun_window_pct"] is not None else float("nan"),
                     "Noche más larga en la ventana (h)": f["dark_window_h"] if f["dark_window_h"] is not None else float("nan"),
                     "Mejor fecha de inicio": C.fmt_utc_short(sc.best_start_utc) if sc.best_start_utc else "ninguna",
                     "Fechas factibles": C.fmt_pct(sc.feasible_start_fraction, 0),
                     "Confianza": sc.confidence.level.value if sc.confidence else "—"})
    return rows


def recommendation(base: Mapping[str, AnalysisResult], pool: Sequence[str], profile_label: str) -> list[str]:
    """Párrafos en lenguaje llano: cuál es el mejor candidato y por qué, siempre con la salvedad."""
    cands = [n for n in pool if base[n].score is not None]
    if not cands:
        return ["No hay ningún sitio con relieve real para comparar, así que no puedo proponer ningún candidato."]
    top = max(cands, key=lambda n: (_VERDICT_RANK[base[n].score.verdict], base[n].score.score))
    r, sc = base[top], base[top].score
    others = [n for n in cands if n != top]
    out = []
    if sc.verdict == "APTO":
        out.append(f"Con el perfil «{profile_label}», el que mejor sale es **{top}** y supera todas las comprobaciones mínimas.")
    else:
        out.append(f"Con el perfil «{profile_label}», **ningún sitio supera todas las comprobaciones mínimas**. "
                   f"El que mejor sale es **{top}**: {C.verdict_sentence(sc)}")
    out.append(C.best_date_sentence(sc))
    why = []
    if others:
        def cmp(label, g, higher, fmt):
            vals = {n: g(base[n]) for n in cands}
            if all(v is not None and math.isfinite(v) for v in vals.values()) and top in best_names(vals, higher, cands):
                rest = " y ".join(fmt(vals[n]) for n in others)
                why.append(f"{label}: {fmt(vals[top])} (los demás: {rest})")
        cmp("Sol", lambda x: x.metrics.solar_fraction, True, lambda v: f"{C.fmt_num(100 * v, 0)} % del tiempo")
        cmp("Noche más larga", lambda x: x.metrics.max_darkness_s, False, lambda v: f"{C.fmt_num(v / 3600, 0)} h")
        if all(base[n].metrics.link_fraction is not None for n in cands):
            cmp("Enlace posible con la Tierra", lambda x: x.metrics.link_fraction, True, lambda v: f"{C.fmt_num(100 * v, 0)} % del tiempo")
            cmp("Hueco máximo sin enlace", lambda x: x.metrics.max_link_gap_s, False, lambda v: f"{C.fmt_num(v / 3600, 0)} h")
        else:
            cmp("Tierra visible (geometría, sin red)", lambda x: x.metrics.earth_fraction, True, lambda v: f"{C.fmt_num(100 * v, 0)} % del tiempo")
        cmp("Terreno", lambda x: x.slope.percentile_deg if x.slope else None, False, lambda v: f"pendiente típica {C.fmt_num(v, 0)}°")
    if why:
        out.append("**Por qué:** " + "; ".join(why[:3]) + ".")
    else:
        out.append("**Por qué:** su puntuación global es la mayor, pero no gana de forma clara en ninguna medida concreta.")
    out.append(f"Su puntuación es **{C.fmt_num(sc.score, 0)} de 100**: un resumen que ordena, no un veredicto (el veredicto sale de las puertas). "
               f"{STANDARD_WARNINGS_ES[WarningCode.SCORE_UNCALIBRATED]} «Apto» no significa «seguro»: no se modelan rocas ni "
               f"navegación, y la visibilidad es geométrica, no una garantía de potencia ni de enlace.")
    return out


# ------------------------------------------------------------------------------------------------ score ponderado
def _weights_of(res: AnalysisResult) -> dict[str, tuple[str, float, float, Optional[float], float]]:
    """key → (etiqueta, peso efectivo, s_i, valor, penalización %) del score del resultado."""
    return {s.key: (s.label, s.weight, s.s, s.value, s.penalty_pct) for s in res.score.subscores} if res.score else {}


def score_section(ctx, pid: str, pool: Sequence[str], base, weighted, w_new: dict[str, float], w_def: dict[str, float]) -> None:
    """Ranking (con y sin tus pesos), qué cambia y desglose abierto por sitio."""
    sphere = [n for n in base if n not in pool]
    sb = {n: base[n].score.score for n in pool if base[n].score}
    sw = {n: weighted[n].score.score for n in pool if weighted[n].score}
    rb, rw = ranks(sb), ranks(sw)
    rows = []
    for n in sorted(pool, key=lambda x: rw.get(x, 99)):
        a, b = base[n].score, weighted[n].score
        if a is None or b is None:
            continue
        rows.append({"Sitio": n, "Posición (pesos del perfil)": rb[n], "S (perfil)": a.score,
                     "Posición (tus pesos)": rw[n], "S (tus pesos)": b.score,
                     "Rango S (tus pesos)": C.range_label(b),
                     "Eslabón débil": WEIGHT_LABELS.get(b.weakest_key, b.weakest_key),
                     "Veredicto": C.verdict_label(b)})
    if rows:
        st.dataframe(pd.DataFrame(rows).style.format({"S (perfil)": "{:.1f}", "S (tus pesos)": "{:.1f}"}), hide_index=True,
                     width="stretch")
    changed = [n for n in sw if rb.get(n) != rw.get(n)]
    changed_w = [k for k in WEIGHT_KEYS if abs(w_new.get(k, 0) - w_def.get(k, 0)) > 1e-9]
    if not changed_w:
        st.info("Tus pesos coinciden con los del perfil: la clasificación es la del perfil. Mueve un deslizador para ver qué cambia.",
                icon=":material/tune:")
    elif changed:
        st.success("**Con tus pesos cambia la clasificación:** " + "; ".join(f"{n} pasa del puesto {rb[n]} al {rw[n]}" for n in changed) + ".",
                   icon=":material/swap_vert:")
    else:
        st.info("Con estos pesos la clasificación no cambia, aunque las puntuaciones sí.", icon=":material/equal:")
    if changed_w:
        up = max(changed_w, key=lambda k: w_new.get(k, 0) - w_def.get(k, 0))
        st.markdown("**Por qué cambia** (el score es una media geométrica ponderada, S = 100·Π sᵢ^wᵢ: un sᵢ bajo castiga más cuanto más pesa).")
        for n in pool:
            if base[n].score is None or weighted[n].score is None:
                continue
            wn = _weights_of(weighted[n]).get(up)
            if wn is None or math.isnan(wn[2]):
                st.markdown(f"- **{n}:** {C.fmt_num(base[n].score.score, 1)} → {C.fmt_num(weighted[n].score.score, 1)}. Sin datos de «{WEIGHT_LABELS[up]}».")
                continue
            st.markdown(f"- **{n}:** {C.fmt_num(base[n].score.score, 1)} → {C.fmt_num(weighted[n].score.score, 1)}. «{WEIGHT_LABELS[up]}» pasa a pesar "
                        f"{C.fmt_num(100 * w_new[up], 0)} % (antes {C.fmt_num(100 * w_def[up], 0)} %) y su sᵢ aquí es {C.fmt_num(wn[2], 2)}"
                        f"{' (alto: favorece)' if wn[2] >= 0.6 else ' (bajo: perjudica)' if wn[2] <= 0.3 else ''}.")
    if sphere:
        st.markdown("**No comparables (sin datos de terreno), fuera de la clasificación:** " + "; ".join(
            f"{n}: S = {C.fmt_num(base[n].score.score, 1)} (rango {C.range_label(base[n].score)}, parcial y optimista)"
            for n in sphere if base[n].score) + ".")
    st.markdown("#### Desglose por sitio")
    for n in pool:
        a, b = base[n].score, weighted[n].score
        if a is None or b is None:
            continue
        wa, wb = _weights_of(base[n]), _weights_of(weighted[n])
        with st.expander(f"{n}: S = {C.fmt_num(b.score, 1)} (rango {C.range_label(b)})", expanded=len(pool) <= 3):
            det = []
            for k in WEIGHT_KEYS:
                if k not in wb:
                    continue
                lab, w2, s2, val, pen = wb[k]
                det.append({"Indicador": lab, "Valor medido": "—" if val is None or (isinstance(val, float) and math.isnan(val)) else f"{C.fmt_num(val, 2)}",
                            "sᵢ (0–1)": s2, "Peso del perfil": wa[k][1], "Tu peso": w2, "Penalización (% del total)": pen,
                            "S si sᵢ = 1": next(x.score_if_one for x in b.subscores if x.key == k)})
            st.dataframe(pd.DataFrame(det).style.format({"sᵢ (0–1)": "{:.2f}", "Peso del perfil": "{:.0%}", "Tu peso": "{:.0%}",
                                                         "Penalización (% del total)": "{:.0f}", "S si sᵢ = 1": "{:.1f}"}, na_rep="—"),
                         hide_index=True, width="stretch")
            st.dataframe(_gate_rows(b.gates), hide_index=True, width="stretch")
            st.caption(f"Veredicto {C.verdict_label(base[n].score)}: {C.plain_reason(base[n].score.verdict_reason)}")
            gap_line = C.link_gap_line(base[n])
            if gap_line:
                st.caption(gap_line)
            if b.attenuated:
                st.caption("Score atenuado: hay puertas que no se superan o sin datos suficientes.")
    st.caption(STANDARD_WARNINGS_ES[WarningCode.SCORE_UNCALIBRATED])


# ------------------------------------------------------------------------------------------------ panel de control
def _bar(label: str, frac: Optional[float], tone: str) -> str:
    """Medida con barra (texto + cifra + longitud: no depende del color). Sin dato → nada."""
    if frac is None or not math.isfinite(frac):
        return ""
    f = min(max(frac, 0.0), 1.0)
    return (f'<div class="lsi-mbar {tone}"><div class="k"><span>{C.esc(label)}</span><b>{C.esc(C.fmt_pct(f, 1))}</b></div>'
            f'<div class="t" aria-hidden="true"><i style="width:{100 * f:.1f}%"></i></div></div>')


def best_option(base: Mapping[str, AnalysisResult], pool: Sequence[str]) -> Optional[str]:
    """Mejor opción CALCULADA por el motor: mayor veredicto por puertas y, a igualdad, mayor score. None si hay <2 comparables."""
    cands = [n for n in pool if base[n].score is not None]
    return max(cands, key=lambda n: (_VERDICT_RANK[base[n].score.verdict], base[n].score.score)) if len(cands) >= 2 else None


def _thumb(res: AnalysisResult, key: str) -> None:
    o = res.observer
    try:
        from lsi.visualization.relief_map import relief_map_figure
        win = cache.get_mini_window(o.dem_key, float(o.x_m), float(o.y_m)) if is_dem(res) and o.dem_key else None
        if win is not None:
            fig = relief_map_figure(win, o, layer="elevation", compact=True, height=190)
            st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False})
            return
        why = "Sin mapa de terreno (esfera lisa)"
    except Exception as e:      # noqa: BLE001 - una miniatura rota no debe tirar la página
        why = f"No se pudo dibujar la miniatura ({type(e).__name__})"
    st.markdown(f'<div class="lsi-card-empty" style="min-height:8rem">{C.esc(why)}</div>', unsafe_allow_html=True)


def comparison_panel(base: Mapping[str, AnalysisResult], pool: Sequence[str]) -> None:
    """Comparativa de sitios con miniaturas de relieve, barras de Sol y enlace/Tierra y la tarjeta de «mejor opción» calculada."""
    best = best_option(base, pool)
    with st.container(key="lsi-cmp"):
        cols = st.columns(len(base), gap="small")
        for i, ((n, r), col) in enumerate(zip(base.items(), cols)):
            m = r.window_metrics or r.metrics
            has_link = m.link_fraction is not None
            with col, st.container(border=True, key=f"lsi-card-cmp{i}"):
                star = " ★" if n == best else ""
                C.card_head("◍", n + star)
                _thumb(r, f"cmp_thumb_{i}")
                st.markdown(_bar("Luz solar", m.solar_fraction, "sun") + _bar("Enlace posible" if has_link else "Tierra a la vista",
                                                                              m.link_fraction if has_link else m.earth_fraction, "earth"),
                            unsafe_allow_html=True)
                sc = r.score
                if sc is not None:
                    kind, icon = C._VERDICT_CHIP[sc.verdict]
                    st.markdown(C.chips(C.chip(C.verdict_label(sc), kind, icon), C.chip(f"Nota {C.fmt_num(sc.score, 0)}/100", "info")),
                                unsafe_allow_html=True)
    if best is not None:
        sc = base[best].score
        head = f"Mejor opción: {best}" if sc.verdict in ("APTO", "CONDICIONAL") else f"Ninguno supera las comprobaciones; el que mejor sale: {best}"
        st.markdown(f'<div class="lsi-best" role="note"><span class="ic" aria-hidden="true">★</span><div><b>{C.esc(head)}</b>'
                    f'<span>{C.esc(C.verdict_sentence(sc))} Nota {C.esc(C.fmt_num(sc.score, 0))} de 100 con el perfil elegido; es una comparación, '
                    'no una certificación.</span></div></div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ página
def _controls(ctx) -> tuple[list[Entry], list[tuple[str, str, str]], bool, str]:
    ss = st.session_state
    options = [s.id for s in sorted(ctx.sites, key=lambda s: not s.has_dem) if s.lat_deg is not None and s.lon_deg_e is not None]
    options += [t for t in ss.get(K.COMPARE_SITES, []) if _CUSTOM_RE.match(t) and t not in options]
    with st.expander("Sitios y fechas a comparar", expanded=True):
        st.multiselect(f"Sitios (hasta {MAX_SITES})", options, default=[t for t in ss.get(K.COMPARE_SITES, []) if t in options],
                       key="cmp_pick", format_func=_option_label(ctx), max_selections=MAX_SITES, on_change=_on_pick,
                       help="Por defecto, los tres con relieve real (DEM). Los de esfera lisa se calculan pero no son comparables con ellos.")
        c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        c1.number_input("Latitud del punto propio (°, sur negativa)", -90.0, 90.0, -85.0, step=0.01, format="%.4f", key="cmp_lat")
        c2.number_input("Longitud (°E, 0–360)", -180.0, 360.0, 0.0, step=0.01, format="%.4f", key="cmp_lon")
        c3.button("Añadir punto", key="cmp_add", on_click=_add_custom, icon=":material/add_location:")
        if ss.get("cmp_msg"):
            st.caption(ss["cmp_msg"])
        base_start = S.parse_utc(ss[K.START_UTC])
        periods = [("", ss[K.START_UTC], ss[K.END_UTC])]
        two = st.checkbox("Comparar también con otra fecha (misma duración)", key="cmp_two",
                          help="Cada sitio se calcula en las dos fechas; las columnas llevan la fecha de inicio.")
        if two:
            b = st.text_input("Inicio de la segunda fecha (AAAA-MM-DD HH:MM, UTC)",
                              value=(base_start + timedelta(days=180)).strftime("%Y-%m-%d %H:%M"), key="cmp_start_b")
            try:
                sb = S.parse_utc(b)
                eb = sb + timedelta(days=S.period_days())
                err = S.validate_period(sb, eb)
            except ValueError as e:
                err = str(e)
            if err:
                st.error(err, icon=":material/error:")
            else:
                periods = [(f"{base_start:%Y-%m-%d}", ss[K.START_UTC], ss[K.END_UTC]), (f"{sb:%Y-%m-%d}", S.fmt_utc(sb), S.fmt_utc(eb))]
        profiles = profiles_from_config(ctx.cfg["score"])
        cur = ss.get(K.SCORE_PROFILE) if ss.get(K.SCORE_PROFILE) in profiles else next(iter(profiles))
        pid = st.selectbox("Perfil de misión", list(profiles), index=list(profiles).index(cur), key="cmp_profile",
                           format_func=lambda p: profiles[p].label,
                           help="Define umbrales y pesos de partida del score. Este selector solo afecta a esta página.")
        if S.mode() != "publico":
            st.checkbox("Calcular rangos de incertidumbre (más lento)", value=S.get_bool(K.WITH_UNCERTAINTY), key="cmp_unc",
                        help="Añade los rangos [mín, máx] entre escenarios (cobertura, σ del DEM, discretización).")
    entries = entries_from_tokens(ctx, ss.get("cmp_pick", ss.get(K.COMPARE_SITES, [])))
    return entries, periods, bool(ss.get("cmp_unc", False) or ss.get("cmp_unc_force", False)), pid


def main() -> None:
    ctx = cache.get_context()
    S.init_state(ctx)
    st.title("Comparación de sitios")
    C.warnings_band()
    if "period" in S.errors():
        st.warning("Hay un error en el periodo de la barra lateral: " + S.errors()["period"])
        st.stop()
    C.public_note("Aquí se ponen varios lugares lado a lado. No hay un «ganador» definitivo (solo se indica cuál sale mejor con el perfil elegido): cada medida (Sol, Tierra, terreno, "
                  "confianza) se muestra por separado y el mejor de cada una aparece marcado.")
    entries, periods, unc, pid = _controls(ctx)
    if not entries:
        st.info("Elige al menos un sitio para comparar.", icon=":material/info:")
        st.stop()

    base_req = dataclasses.replace(S.build_request(st.session_state, ctx), score_profile_id=pid, with_uncertainty=unc,
                                   gazetteer_id=None, score_weights=None,
                                   snap_prefer="nearest")   # marcador del recorte, como dice el aviso de abajo
    jobs: list[tuple[str, AnalysisRequest]] = []
    auto = S.get_bool(S.MOUNT_AUTO, True)
    for tag, a, b in periods:
        for e in entries:
            # montaje automático: cada sitio según SU latitud (vertical con seguimiento en el polo)
            mnt = S.auto_mounting(ctx, base_req.panel_id, e.lat) if auto else base_req.mounting
            jobs.append((f"{e.label} · {tag}" if tag else e.label,
                         dataclasses.replace(base_req, lat_deg=e.lat, lon_deg_e=e.lon, site_id=e.site_id, start_utc=a, end_utc=b,
                                             mounting=mnt or base_req.mounting)))
    base: dict[str, AnalysisResult] = {}
    for n, req in jobs:
        res, err = cache.try_analysis(req)
        if err:
            st.error(f"**{n}:** {err}", icon=":material/error:")
        else:
            base[n] = res
    if not base:
        st.stop()
    reqs = dict(jobs)
    pool = [n for n, r in base.items() if is_dem(r)] if any(is_dem(r) for r in base.values()) and not all(is_dem(r) for r in base.values()) \
        else list(base)
    profile = profiles_from_config(ctx.cfg["score"])[pid]

    st.subheader("Comparativa de emplazamientos")
    comparison_panel(base, [n for n in pool if is_dem(base[n])])

    # --- Público: recomendación
    if S.is_public():
        st.subheader("Cuál sale mejor con este perfil y por qué")
        with st.container(border=True):
            for p in recommendation(base, [n for n in pool if is_dem(base[n])], profile.label):
                st.markdown(p)

    _site_warnings(ctx, entries, base)
    if len(base) == 1:
        st.caption("Con un solo sitio no hay nada que comparar: añade otro en el selector.")

    # --- veredicto por puertas (con la ventana de misión de cada sitio)
    st.subheader("Veredicto por puertas")
    st.caption("Lo deciden las puertas y los escenarios de incertidumbre, no la nota. " + C.CERTIFY_NOTE)
    first = next(iter(base.values()))
    st.caption(C.scope_caption(first, profile.label) + " La columna «Misión (d)» y las dos «en la ventana» son las del score; las "
               "tablas de «Métricas por separado» usan el periodo completo.")
    st.dataframe(pd.DataFrame(verdict_rows(base, ctx)), hide_index=True, width="stretch")
    st.caption("«Panel y montaje» es sobre lo que se calculó la energía del score." +
               (" " + C.G5_NOTE if not S.is_public() and any(r.score and r.score.energy_basis == "panel" for r in base.values()) else ""))
    flat = next((r for r in base.values() if r.score is not None and r.score.energy_mounting == "horizontal" and S.is_polar(r.observer.lat_deg)), None)
    if flat is not None:
        C.polar_horizontal_warning(flat.observer.lat_deg, "horizontal")
    for n, r in base.items():
        if r.score is not None and r.score.energy_basis == "panel" and r.score.energy_mounting:
            C.mount_fallback_notice(r.request, r.score.energy_panel_id, S.wanted_mount(None, r.observer.lat_deg),
                                    MountingSpec(MountingType(r.score.energy_mounting)), ctx, who=f"{n}: " if len(base) > 1 else "")
    C.range_prompt(base.values(), key="cmp_rng_btn", can_activate=not unc)
    for n, r in base.items():
        if r.score is not None and C.short_period(r.score):
            st.warning(f"**{n}:** el periodo ({r.metrics.period_s / 86400:g} d) es menor que la misión ({r.score.mission_days:g} d): veredicto SIN DATOS. "
                       "Alarga el periodo en la barra lateral.", icon=":material/event_busy:")
    pending = next((r for r in base.values() if not r.score_scenarios and r.score and r.score.verdict in ("APTO", "CONDICIONAL")), None)
    if S.is_public():
        st.markdown(chr(10).join(f"- **{n}:** {C.verdict_sentence(r.score)}" for n, r in base.items() if r.score is not None))
    if pending is not None:
        C.uncertainty_note(pending, key="cmp_unc_btn")

    # --- métricas separadas
    st.subheader("Métricas por separado")
    st.caption("Una fila por sitio; pulsa el encabezado de una columna para ordenar. Resaltado (negrita, subrayado y «★» en la lista): "
               "el mejor de esa métrica entre los sitios comparables. No es un ranking global. «—» = sin dato (nunca 0). " + C.SUN_FRACTION_NOTE)
    best_lines, trunc_notes = [], []
    for group in GROUPS:
        st.markdown(f"#### {group}")
        df, best, num = group_frame(group, base, pool)
        st.dataframe(styled(df, best, num), hide_index=True, width="stretch")
        for col, names in best.items():
            if names:
                v = df.set_index("Sitio")[col]
                best_lines.append(f"{group} · {col}: ★ **{', '.join(sorted(names))}** ({C.fmt_num(float(v[sorted(names)[0]]), 1)})")
    for col, attr in _TRUNC.items():
        names = [n for n, r in base.items() if getattr(r.metrics, attr)]
        if names:
            trunc_notes.append(f"«{col}» es una cota inferior (≥, la ventana toca el borde del periodo) en: {', '.join(names)}.")
    for t in trunc_notes:
        st.caption(t)
    with st.expander("Mejor por métrica (texto)"):
        st.markdown("\n".join(f"- {t}" for t in best_lines) or "- Sin diferencias que resaltar entre los sitios comparables.")
    if any(r.uncertainty for r in base.values()):
        st.caption("Los rangos son cotas de sensibilidad entre escenarios, no intervalos estadísticos.")

    # --- gráficas
    st.subheader("Gráficas")
    fig = comparison_plot.comparison_bars(base)
    details = [f"{n}: Sol {C.fmt_pct(r.metrics.solar_fraction)}, Tierra visible {C.fmt_pct(r.metrics.earth_fraction)}, "
               + ("" if r.metrics.link_fraction is None else f"enlace posible {C.fmt_pct(r.metrics.link_fraction)}, ")
               +
               f"solape {C.fmt_pct(r.metrics.overlap_fraction)}, oscuridad máx. {C.fmt_duration(r.metrics.max_darkness_s, r.metrics.max_darkness_truncated)}"
               for n, r in base.items()]
    C.accessible_chart(fig, "barras por métrica (fracción con Sol, con Tierra, solape, ventana solar más larga, oscuridad máxima y "
                       "elevación solar máxima), un sitio por barra, cada uno con color y trama distintos. Los valores exactos están en las tablas.",
                       key="cmp_bars", details=details)
    if S.is_expert():
        with st.expander("Horizontes superpuestos"):
            C.accessible_chart(comparison_plot.comparison_horizons(base), "perfiles de horizonte (elevación frente a azimut) de cada sitio; "
                               "las marcas «x» son azimutes limitados por la cobertura del DEM.", key="cmp_hor")

    # --- score ponderado (opcional)
    w_used: Optional[dict[str, float]] = None
    weighted = base
    if not S.is_public():
        st.subheader("Score ponderado (opcional)")
        use = st.toggle("Calcular un score con pesos ajustables", key="cmp_use_score",
                        help="El score es un resumen explicable, no un veredicto. Desactivado, solo ves las métricas separadas.")
        if use:
            w_def = dict(profile.weights)
            t = sum(w_def.values())
            w_def = {k: w_def.get(k, 0.0) / t for k in WEIGHT_KEYS}
            cols = st.columns(4)
            raw = {k: cols[i].slider(WEIGHT_LABELS[k], 0, 100, int(round(100 * w_def[k])), key=f"cmp_w_{pid}_{k}",
                                     help="Peso relativo: se normaliza para que los cuatro sumen 100 %.") for i, k in enumerate(WEIGHT_KEYS)}
            tot = sum(raw.values())
            if tot <= 0:
                st.warning("Todos los pesos son 0: sube al menos uno.", icon=":material/warning:")
            else:
                w_new = {k: v / tot for k, v in raw.items()}
                st.caption("Pesos normalizados: " + " · ".join(f"{WEIGHT_LABELS[k]} {C.fmt_num(100 * w_new[k], 0)} %" for k in WEIGHT_KEYS))
                st.button("Restablecer pesos del perfil", key="cmp_reset", on_click=_reset_weights, args=(pid,), icon=":material/restart_alt:")
                same = all(abs(w_new[k] - w_def[k]) < 1e-9 for k in WEIGHT_KEYS)
                weighted, w_used = base, None
                if not same:
                    wt = tuple(sorted(w_new.items()))
                    weighted = {}
                    for n in base:
                        res, err = cache.try_analysis(dataclasses.replace(reqs[n], score_weights=wt))
                        if err:
                            st.error(f"**{n}:** {err}")
                        else:
                            weighted[n] = res
                    w_used = w_new
                if len(weighted) == len(base):
                    score_section(ctx, pid, pool, base, weighted, w_new, w_def)
                    C.accessible_chart(comparison_plot.comparison_scores({n: r for n, r in weighted.items() if n in pool}),
                                       "score nominal de cada sitio comparable con su barra de rango [mín, máx]; los parciales (sin terreno) van rotulados.",
                                       key="cmp_scores")

    # --- descargas
    st.subheader("Descargas")
    exp = weighted if len(weighted) == len(base) else base
    d1, d2, d3 = st.columns(3)
    with d1:
        C.download_comparison(table_rows(exp), key="cmp_dl_csv")
    d2.download_button("Descargar resumen (JSON)", data=lambda: json_bytes(exp, w_used), file_name="lsi_comparacion.json",
                       mime="application/json", on_click="ignore", key="cmp_dl_json", icon=":material/download:",
                       help="Cabecera de la comparación y el JSON validado de cada sitio, con sus avisos.")
    if importlib.util.find_spec("kaleido"):
        d3.download_button("Descargar captura (PNG)", data=lambda: fig.to_image(format="png", scale=2), file_name="lsi_comparacion.png",
                           mime="image/png", on_click="ignore", key="cmp_dl_png", icon=":material/image:")
    else:
        d3.caption("Para guardar la gráfica como imagen usa el icono de cámara que aparece sobre ella.")


if __name__ == "__main__":
    main()
