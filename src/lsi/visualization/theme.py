"""Tema oscuro espacial y utilidades comunes de las figuras Plotly (sin Streamlit).

Paleta con contraste AA sobre ``BG``; ningún significado depende solo del color: cada cuerpo/estado
lleva además símbolo, trazo o patrón propio.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import STANDARD_WARNINGS_ES, VisibilityState, WarningCode, et_to_utc_datetime

BG = "#0b1020"
PANEL = "#0f1733"
GRID = "#26325a"
TEXT = "#e8ecf5"          # contraste 15:1 sobre BG
MUTED = "#a9b4d0"         # contraste ~8:1 sobre BG
SUN = "#ffc247"            # ámbar solar: Sol y energía (mismo tono que ui/styles.css)
EARTH = "#5cc2f5"          # cian: Tierra y enlace
OVERLAP = "#8be28b"
DARK = "#8a93b2"
WARN = "#ff9f43"
BAD = "#ff6b6b"
TERRAIN = "#9aa4b8"
# Serie categórica (paleta Okabe-Ito adaptada a fondo oscuro) + trazo y símbolo para no depender del color
SERIES_COLORS = ("#5cc2f5", "#ffc247", "#8be28b", "#f28fd0", "#d4c5ff", "#ff9f43")
SERIES_DASH = ("solid", "dash", "dot", "dashdot", "longdash", "longdashdot")
SERIES_SYMBOLS = ("circle", "square", "diamond", "triangle-up", "cross", "x")

# Símbolos por cuerpo y estado (además del color)
SUN_SYMBOL = "star"
EARTH_SYMBOL = "circle-cross"
STATE_TEXT = {
    VisibilityState.VISIBLE: "● visible",
    VisibilityState.PARTIAL: "◐ parcial",
    VisibilityState.HIDDEN: "○ oculto",
}

GEOMETRIC_NOTE = "Visibilidad geométrica ≠ potencia ni enlace garantizados."


def warning_text(code: WarningCode) -> str:
    """Texto estándar de un aviso científico."""
    return STANDARD_WARNINGS_ES[code]


def et_to_datetimes(et: Iterable[float]) -> List[datetime]:
    """ET (s desde J2000) → datetimes UTC (naive, para ejes de Plotly)."""
    return [et_to_utc_datetime(e) for e in np.atleast_1d(et)]   # tabla de segundos intercalares (contracts)


def apply_theme(fig: go.Figure, title: str = "", height: int = 480, note: str | None = None) -> go.Figure:
    """Aplica el tema espacial; ``note`` añade un aviso al pie de la figura."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color=TEXT)),
        paper_bgcolor=BG, plot_bgcolor=PANEL, height=height,
        font=dict(color=TEXT, family="Segoe UI Variable Text, Segoe UI, Inter, system-ui, Arial, sans-serif", size=13),
        legend=dict(bgcolor="rgba(15,23,51,0.85)", bordercolor=GRID, borderwidth=1, font=dict(color=TEXT)),
        margin=dict(l=60, r=30, t=70, b=70 if note else 50),
        hoverlabel=dict(bgcolor=PANEL, font=dict(color=TEXT)),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=MUTED, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=MUTED, tickfont=dict(color=MUTED))
    if note:
        fig.add_annotation(text=note, xref="paper", yref="paper", x=0, y=-0.14 if height > 400 else -0.2,
                           showarrow=False, xanchor="left", align="left", font=dict(size=11, color=MUTED))
    return fig


def runs(mask: Sequence[bool]) -> List[Tuple[int, int]]:
    """Tramos contiguos [i0, i1] (inclusive) donde ``mask`` es True."""
    m = np.asarray(mask, dtype=bool)
    if not m.any():
        return []
    d = np.diff(np.concatenate(([0], m.astype(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1))


def periodic_interp(x: float, az_deg: np.ndarray, y: np.ndarray) -> float:
    """Interpolación circular de ``y`` (definida en ``az_deg``) en el azimut ``x``."""
    return float(np.interp(x % 360.0, np.asarray(az_deg), np.asarray(y), period=360.0))
