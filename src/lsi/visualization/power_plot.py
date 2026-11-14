"""Curvas de % de potencia nominal para varios paneles/montajes, elevación solar y carga de batería."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lsi.contracts import BatteryResult, MountingType, PowerSeries, SkySeries, WarningCode
from lsi.visualization import theme

NOTE = theme.warning_text(WarningCode.POWER_IS_ESTIMATE) + " " + theme.GEOMETRIC_NOTE


def series_label(s: PowerSeries) -> str:
    """Etiqueta «panel · montaje (inclinación)»."""
    m = s.mounting
    extra = f" {m.tilt_deg:g}°" if m.type == MountingType.TILTED and m.tilt_deg is not None else ""
    return f"{s.panel_id} · {m.type.value}{extra}"


def power_curves(series: Sequence[PowerSeries], sky: Optional[SkySeries] = None, battery: Optional[BatteryResult] = None,
                 labels: Optional[Sequence[str]] = None) -> go.Figure:
    """% de la potencia nominal vs tiempo (varias series superpuestas, cada una con color, trazo y símbolo).

    Eje secundario: elevación solar (si se da ``sky``). Con ``battery`` se añade un panel inferior de % de carga.
    Los puntos con extrapolación en frío (``t_clamped``) se marcan con «x».
    """
    rows = 2 if battery is not None else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.7, 0.3] if rows == 2 else [1.0],
                        specs=[[{"secondary_y": True}]] + ([[{}]] if rows == 2 else []))
    for i, s in enumerate(series):
        name = labels[i] if labels else series_label(s)
        c, d, sym = (theme.SERIES_COLORS[i % 6], theme.SERIES_DASH[i % 6], theme.SERIES_SYMBOLS[i % 6])
        t = theme.et_to_datetimes(s.et)
        fig.add_trace(go.Scatter(x=t, y=100.0 * s.p_rel, mode="lines", name=name, line=dict(color=c, dash=d, width=2.2),
                                 hovertemplate=name + "<br>%{y:.1f} % de la nominal<extra></extra>"), row=1, col=1)
        step = max(len(t) // 12, 1)           # símbolos escasos para identificar la serie sin saturar
        fig.add_trace(go.Scatter(x=t[::step], y=100.0 * s.p_rel[::step], mode="markers", marker=dict(symbol=sym, size=7, color=c),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)
        if s.t_clamped.any():
            idx = np.flatnonzero(s.t_clamped)
            fig.add_trace(go.Scatter(x=[t[j] for j in idx], y=100.0 * s.p_rel[idx], mode="markers", name="Extrapolación en frío",
                                     legendgroup="cold", showlegend=(i == 0), marker=dict(symbol="x-thin", size=6, color=theme.WARN, opacity=0.55,
                                                                                           line=dict(color=theme.WARN, width=1.5))), row=1, col=1)
    if sky is not None:
        fig.add_trace(go.Scatter(x=theme.et_to_datetimes(sky.et), y=sky.sun.el_deg, mode="lines", name="Elevación solar (eje der.)",
                                 line=dict(color=theme.SUN, width=1.3, dash="dot")), row=1, col=1, secondary_y=True)
        fig.update_yaxes(title_text="Elevación solar (°)", secondary_y=True, showgrid=False, row=1, col=1)
    fig.update_yaxes(title_text="% de potencia nominal", range=[0, 105], row=1, col=1, secondary_y=False)
    if battery is not None:
        fig.add_trace(go.Scatter(x=theme.et_to_datetimes(battery.et), y=100.0 * battery.soc, mode="lines", name="Carga de batería",
                                 line=dict(color=theme.OVERLAP, width=2.2, dash="dashdot"), fill="tozeroy", fillcolor="rgba(139,226,139,0.12)"),
                      row=2, col=1)
        fig.update_yaxes(title_text="Carga (%)", range=[0, 105], row=2, col=1)
    fig.update_xaxes(title_text="Tiempo (UTC)", row=rows, col=1)
    fig = theme.apply_theme(fig, "Potencia relativa por montaje (% de la nominal)", height=580 if rows == 2 else 500, note=NOTE)
    fig.update_layout(margin=dict(b=110))      # el pie no debe pisar la etiqueta del eje X
    for a in fig.layout.annotations:
        if a.text == NOTE:
            a.y = -0.26
    return fig
