"""Curva del día de potencia eléctrica absoluta (W por m² de panel) para varios paneles/montajes."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import plotly.graph_objects as go

from lsi.visualization import theme


def day_power_curve(curves: Sequence[tuple], day_start_et: float, *, bands: Optional[dict] = None,
                    title: str = "Potencia eléctrica a lo largo del día") -> go.Figure:
    """``curves``: [(etiqueta, et, p_rel, W/m² nominales del panel)]. Eje X = hora UTC del día que empieza en ``day_start_et``.

    P (W/m²) = P_rel · W/m² nominales (η BOL · constante solar). ``bands``: {índice: (lo_W, hi_W)} con el rango de incertidumbre
    del panel ya en W/m² sobre la misma ``et`` de su curva.
    """
    fig = go.Figure()
    grid = np.linspace(day_start_et, day_start_et + 86400.0, 289)
    x = (grid - day_start_et) / 3600.0
    for i, (name, et, p, w) in enumerate(curves):
        et, p = np.asarray(et, float), np.asarray(p, float)
        c = theme.SERIES_COLORS[i % 6]
        if bands and i in bands:
            lo, hi = bands[i]
            h = c.lstrip("#")
            fig.add_trace(go.Scatter(x=x, y=np.interp(grid, et, lo), mode="lines", line=dict(width=0), showlegend=False,
                                     hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=x, y=np.interp(grid, et, hi), mode="lines", line=dict(width=0), fill="tonexty",
                                     showlegend=False, fillcolor="rgba(%d,%d,%d,0.22)" % tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)),
                                     hovertemplate=name + "<br>máx. del rango: %{y:.0f} W/m²<extra></extra>"))
        fig.add_trace(go.Scatter(x=x, y=np.interp(grid, et, p) * w, mode="lines+markers", name=name,
                                 line=dict(color=c, dash=theme.SERIES_DASH[i % 6], width=2.2),
                                 marker=dict(symbol=theme.SERIES_SYMBOLS[i % 6], size=6, color=c), marker_maxdisplayed=13,
                                 hovertemplate=name + "<br>%{x:.1f} h UTC · %{y:.0f} W/m²<extra></extra>"))
    fig.update_xaxes(title="Hora (UTC)", range=[0, 24], dtick=3)
    fig.update_yaxes(title="Potencia eléctrica (W por m² de panel)", rangemode="tozero")
    return theme.apply_theme(fig, title, height=430, note="Estimación con supuestos declarados; no es potencia garantizada.")
