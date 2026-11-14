"""Comparación lado a lado de varios sitios (métricas, horizontes y score). Recibe ``AnalysisResult``."""
from __future__ import annotations

from typing import Mapping

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lsi.contracts import AnalysisResult, WarningCode
from lsi.visualization import theme

# clave de SiteMetrics → (etiqueta, factor, unidad, clave de truncado o None)
METRICS = (
    ("solar_fraction", "Fracción con Sol", 100.0, "%", None),
    ("earth_fraction", "Tierra visible (geometría)", 100.0, "%", None),
    ("overlap_fraction", "Sol y Tierra a la vez", 100.0, "%", None),
    ("longest_sun_window_s", "Ventana solar más larga", 1 / 3600.0, "h", "longest_sun_window_truncated"),
    ("max_darkness_s", "Oscuridad máxima", 1 / 3600.0, "h", "max_darkness_truncated"),
    ("max_sun_elevation_deg", "Elevación solar máxima", 1.0, "°", None),
)
# solo si TODOS los sitios tienen enlace DTE calculado (``SiteMetrics.link_fraction``): la Tierra visible NO es el enlace posible
LINK_METRICS = (
    ("link_fraction", "ENLACE POSIBLE", 100.0, "%", None),
    ("max_link_gap_s", "Hueco máximo sin enlace", 1 / 3600.0, "h", "max_link_gap_truncated"),
)
_PATTERNS = ("", "/", "x", ".", "+", "-")
NOTE = "Sin fusionar en un solo número: cada métrica por separado. " + theme.GEOMETRIC_NOTE


def comparison_bars(results: Mapping[str, AnalysisResult], cols: int = 3) -> go.Figure:
    """Una gráfica de barras por métrica, un sitio por barra (color + trama); «≥» si la ventana está truncada."""
    metrics = METRICS + (LINK_METRICS if results and all(r.metrics.link_fraction is not None for r in results.values()) else ())
    rows = -(-len(metrics) // cols)
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=[f"{m[1]} ({m[3]})" for m in metrics], vertical_spacing=0.18)
    names = list(results)
    for k, (key, _label, f, unit, trunc) in enumerate(metrics):
        r, c = divmod(k, cols)
        for i, n in enumerate(names):
            m = results[n].metrics
            if getattr(m, key) is None:
                continue
            v = getattr(m, key) * f
            ge = "≥ " if trunc and getattr(m, trunc) else ""
            fig.add_trace(go.Bar(
                x=[n], y=[v], name=n, legendgroup=n, showlegend=(k == 0), text=[f"{ge}{v:.1f}"], textposition="outside",
                marker=dict(color=theme.SERIES_COLORS[i % 6], pattern=dict(shape=_PATTERNS[i % 6], fgcolor="#0b1020", size=7, solidity=0.3),
                            line=dict(color=theme.TEXT, width=1)),
                hovertemplate=f"{n}<br>{ge}%{{y:.2f}} {unit}<extra></extra>"), row=r + 1, col=c + 1)
    fig.update_layout(showlegend=True)
    return theme.apply_theme(fig, "Comparación de sitios", height=330 * rows + 60, note=NOTE)


def comparison_horizons(results: Mapping[str, AnalysisResult]) -> go.Figure:
    """Perfiles de horizonte H_lb superpuestos (color + trazo) y marcas «x» donde está limitado por cobertura."""
    fig = go.Figure()
    for i, (n, res) in enumerate(results.items()):
        h = res.horizon
        c, d = theme.SERIES_COLORS[i % 6], theme.SERIES_DASH[i % 6]
        fig.add_trace(go.Scatter(x=h.az_deg, y=h.h_lb_deg, mode="lines", name=n, line=dict(color=c, dash=d, width=2.2)))
        if h.limited.any():
            fig.add_trace(go.Scatter(x=h.az_deg[h.limited], y=h.h_lb_deg[h.limited], mode="markers", name=f"{n}: limitado por cobertura",
                                     marker=dict(symbol="x", size=5, color=c), legendgroup=n))
    fig.update_xaxes(title="Azimut (° desde el Norte hacia el Este)", range=[0, 360], dtick=45)
    fig.update_yaxes(title="Elevación del horizonte (°)")
    return theme.apply_theme(fig, "Horizontes comparados", note=theme.GEOMETRIC_NOTE)


def comparison_scores(results: Mapping[str, AnalysisResult]) -> go.Figure:
    """Score nominal con barra de rango [mín, máx] por sitio; los parciales (sin terreno) se rotulan como tales."""
    fig = go.Figure()
    for i, (n, res) in enumerate(results.items()):
        s = res.score
        if s is None:
            continue
        lab = n + (" (parcial)" if s.partial else "")
        fig.add_trace(go.Scatter(x=[s.score], y=[lab], mode="markers", name=lab,
                                 error_x=dict(type="data", symmetric=False, array=[s.score_max - s.score], arrayminus=[s.score - s.score_min],
                                              color=theme.TEXT, thickness=2.5),
                                 marker=dict(symbol=theme.SERIES_SYMBOLS[i % 6], size=13, color=theme.SERIES_COLORS[i % 6],
                                             line=dict(color=theme.TEXT, width=1)),
                                 hovertemplate=f"{lab}<br>S=%{{x:.0f}} [{s.score_min:.0f}–{s.score_max:.0f}]<extra></extra>"))
    fig.update_xaxes(range=[0, 105], title="Score (0–100) con rango")
    fig.update_yaxes(autorange="reversed")
    return theme.apply_theme(fig, "Score comparado (con rango)", height=120 + 70 * max(len(results), 2),
                             note=theme.warning_text(WarningCode.SCORE_UNCALIBRATED))
