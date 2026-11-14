"""Desglose del score del emplazamiento: radar o barras, pesos, puertas/penalizaciones y rango [min, max]."""
from __future__ import annotations

import numpy as np

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from lsi.contracts import GateStatus, SiteScoreResult, WarningCode
from lsi.visualization import theme

GATE_SYMBOL = {GateStatus.PASS: "✔ apto", GateStatus.FAIL: "✖ no apto", GateStatus.NO_DATA: "? sin datos suficientes", GateStatus.NOT_APPLICABLE: "– no aplica"}
NOTE = theme.warning_text(WarningCode.SCORE_UNCALIBRATED) + " " + theme.GEOMETRIC_NOTE


def _nodata(s) -> bool:
    """Subindicador no evaluable (p. ej. terreno sin DEM: s = NaN): se pinta «sin datos», nunca un número."""
    return not np.isfinite(s.s)


def _headline(r: SiteScoreResult) -> str:
    t = f"S = {r.score:.0f} (rango {r.score_min:.0f}–{r.score_max:.0f})"
    return t + (" · PARCIAL: sin " + ", ".join(r.missing_keys) if r.partial else "") + (" · atenuado por puertas" if r.attenuated else "")


def _gates_text(r: SiteScoreResult) -> str:
    return "<br>".join(f"{g.id}{'' if g.hard else ' (blanda)'}: {GATE_SYMBOL[g.status]} — {g.reason}" for g in r.gates)


def _banner(fig: go.Figure, r: SiteScoreResult):
    if r.partial or not r.terrain_data:
        fig.add_annotation(text="Sin datos de terreno — score parcial y optimista", xref="paper", yref="paper", x=0.5, y=1.07, showarrow=False,
                           font=dict(color=theme.WARN, size=13), bgcolor=theme.PANEL, bordercolor=theme.WARN, borderwidth=1)


def score_radar(r: SiteScoreResult) -> go.Figure:
    """Radar de s_i (0–100 %) con el peso de cada subindicador en la etiqueta y las puertas al pie."""
    labels = [f"{s.label}<br>" + ("sin datos" if _nodata(s) else f"peso {s.weight:.0%}") for s in r.subscores]
    vals = [0.0 if _nodata(s) else 100.0 * s.s for s in r.subscores]
    fig = go.Figure(go.Scatterpolar(theta=labels + labels[:1], r=vals + vals[:1], fill="toself", fillcolor="rgba(86,180,233,0.25)",
                                    mode="lines+markers+text", text=["sin datos" if _nodata(s) else f"{v:.0f}" for s, v in zip(r.subscores, vals)] + [""], textposition="top center",
                                    line=dict(color=theme.EARTH, width=2.5), marker=dict(symbol="diamond", size=9, color=theme.EARTH),
                                    name="s_i (0–100)"))
    fig.update_layout(polar=dict(bgcolor=theme.PANEL, radialaxis=dict(range=[0, 100], gridcolor=theme.GRID, color=theme.MUTED),
                                 angularaxis=dict(gridcolor=theme.GRID, color=theme.TEXT)), showlegend=False)
    fig.add_annotation(text=_gates_text(r), xref="paper", yref="paper", x=0, y=-0.1, showarrow=False, xanchor="left", yanchor="top",
                       align="left", font=dict(size=11, color=theme.TEXT))
    _banner(fig, r)
    return theme.apply_theme(fig, _headline(r), height=620, note=NOTE)


def score_bars(r: SiteScoreResult) -> go.Figure:
    """Barras horizontales de s_i con peso y penalización, y debajo el rango [min, max] con el valor nominal."""
    fig = make_subplots(rows=2, cols=1, row_heights=[0.75, 0.25], vertical_spacing=0.18)
    subs = list(r.subscores)
    pats = ["", "/", "x", "."]
    ok = [s for s in subs if not _nodata(s)]
    nd = [s for s in subs if _nodata(s)]
    fig.add_trace(go.Bar(
        y=[s.label for s in ok], x=[100.0 * s.s for s in ok], orientation="h", name="s_i",
        marker=dict(color=[theme.SERIES_COLORS[subs.index(s) % 6] for s in ok],
                    pattern=dict(shape=[pats[subs.index(s) % 4] for s in ok], fgcolor="#0b1020", size=7, solidity=0.3)),
        text=[f"s={s.s:.2f} · peso {s.weight:.0%} · pen. {s.penalty_pct:.0f} %" + (" ◄ eslabón débil" if s.key == r.weakest_key else "") for s in ok],
        textposition="auto", insidetextfont=dict(color="#000"), outsidetextfont=dict(color=theme.TEXT),
        hovertemplate="%{y}: %{x:.0f}/100<extra></extra>"), row=1, col=1)
    if nd:   # barra vacía rayada con etiqueta: «no evaluado», no un 0 ni un NaN
        fig.add_trace(go.Bar(
            y=[s.label for s in nd], x=[100.0] * len(nd), orientation="h", name="sin datos",
            marker=dict(color="rgba(0,0,0,0)", line=dict(color=theme.MUTED, width=1.5),
                        pattern=dict(shape="/", fgcolor=theme.MUTED, size=6, solidity=0.15)),
            text=["sin datos: no evaluado (sin terreno)"] * len(nd), textposition="inside", insidetextanchor="start",
            insidetextfont=dict(color=theme.TEXT), hovertemplate="%{y}: sin datos<extra></extra>"), row=1, col=1)
    fig.update_xaxes(range=[0, 105], title_text="Subindicador (0–100)", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.add_trace(go.Scatter(x=[r.score_min, r.score_max], y=["Score", "Score"], mode="lines+markers", line=dict(color=theme.TEXT, width=4),
                             marker=dict(symbol="line-ns-open", size=14, color=theme.TEXT), name="Rango [mín, máx]",
                             hovertemplate="rango %{x:.0f}<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(x=[r.score], y=["Score"], mode="markers+text", text=[f"{r.score:.0f}"], textposition="top center",
                             marker=dict(symbol="star", size=16, color=theme.SUN), name="Nominal"), row=2, col=1)
    fig.update_xaxes(range=[0, 105], title_text="Score (0–100)", row=2, col=1)
    fig.add_annotation(text=_gates_text(r), xref="paper", yref="paper", x=0, y=-0.2, showarrow=False, xanchor="left", yanchor="top",
                       align="left", font=dict(size=11, color=theme.TEXT))
    _banner(fig, r)
    return theme.apply_theme(fig, _headline(r), height=640, note=NOTE)
