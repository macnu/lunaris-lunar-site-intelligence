"""Anillo (donut) de una fracción y curva de área compacta para las tarjetas del panel de control. Figuras PURAS (plotly).

Nada depende solo del color: el centro lleva la cifra y la leyenda nombra cada tramo con su porcentaje.
"""
from __future__ import annotations

import numpy as np
from typing import Optional, Sequence

import plotly.graph_objects as go

from lsi.visualization import theme

OFF = "#26325a"


def _rgba(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    return "rgba(%d,%d,%d,%g)" % (*(int(h[k:k + 2], 16) for k in (0, 2, 4)), a)


def donut(fraction: Optional[float], *, color: str, on: str, off: str, center: str, sub: str = "", height: int = 230) -> Optional[go.Figure]:
    """Anillo de ``fraction`` (0–1): tramo ``on`` en ``color`` y resto ``off``. ``center``/``sub`` van en el hueco.
    Sin dato (None/NaN) devuelve None: no hay tarjeta si el motor no dio la cifra."""
    if fraction is None or not np.isfinite(fraction):
        return None
    f = min(max(float(fraction), 0.0), 1.0)
    fig = go.Figure(go.Pie(values=[f, 1.0 - f], labels=[f"{on} {100 * f:.1f} %".replace(".", ","), f"{off} {100 * (1 - f):.1f} %".replace(".", ",")],
                           hole=0.74, sort=False, direction="clockwise", rotation=0, textinfo="none", marker=dict(
                               colors=[color, OFF], line=dict(color=theme.BG, width=2), pattern=dict(shape=["", "/"], fgcolor=theme.MUTED, size=4, solidity=0.15)),
                           hovertemplate="%{label}<extra></extra>"))
    fig.add_annotation(text=f"<b>{center}</b>", x=0.5, y=0.56 if sub else 0.5, showarrow=False, font=dict(size=30, color=theme.TEXT), xref="paper", yref="paper")
    if sub:
        fig.add_annotation(text=sub, x=0.5, y=0.40, showarrow=False, font=dict(size=12, color=theme.MUTED), xref="paper", yref="paper")
    fig.update_layout(paper_bgcolor=theme.CLEAR, plot_bgcolor=theme.CLEAR, height=height, margin=dict(l=8, r=8, t=6, b=44),
                      font=dict(color=theme.TEXT, family="Segoe UI Variable Text, Segoe UI, Inter, system-ui, Arial, sans-serif"),
                      legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5, font=dict(color=theme.TEXT, size=12), bgcolor=theme.CLEAR),
                      hoverlabel=dict(bgcolor=theme.PANEL, font=dict(color=theme.TEXT)))
    return fig


def area_curve(x: Sequence, y: Sequence[float], *, color: str, name: str, unit: str, y_range: tuple[float, float] = (0, 24), x_title: str = "",
               height: int = 190) -> Optional[go.Figure]:
    """Curva de área (p. ej. horas de luz por día). Vacía → None."""
    if len(x) == 0:
        return None
    fig = go.Figure(go.Scatter(x=list(x), y=list(y), mode="lines+markers", name=name, line=dict(color=color, width=2.4, shape="spline", smoothing=0.6),
                               marker=dict(size=4, color=color), fill="tozeroy", fillcolor=_rgba(color, 0.16),
                               hovertemplate="%{x}<br>%{y:.1f} " + unit + "<extra></extra>"))
    theme.apply_theme(fig, "", height=height)
    fig.update_layout(title=dict(text=""), showlegend=False, margin=dict(l=44, r=12, t=8, b=34 if x_title else 28))
    fig.update_yaxes(range=list(y_range), title=unit, title_font=dict(size=11), dtick=(y_range[1] - y_range[0]) / 4, gridcolor=theme.GRID)
    fig.update_xaxes(title=x_title or None, nticks=5, gridcolor=theme.GRID)
    return fig
