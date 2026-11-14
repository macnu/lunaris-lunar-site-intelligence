"""Vista polar del cielo (az–el) con la trayectoria del Sol y de la Tierra sobre el horizonte real. Figura PURA (plotly).

Centro = elevación más alta mostrada; borde exterior = unos grados bajo el horizonte plano. Norte arriba, azimut creciente en
sentido horario (convención del proyecto). El terreno se rellena desde su perfil ``H(az)`` hasta el borde: lo que queda dentro
del anillo claro es cielo abierto. Los tramos en que el astro está TAPADO (por debajo del horizonte en su azimut) van punteados
y tenues; los visibles, continuos: la información no depende del color.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import HorizonResult, SkySeries
from lsi.visualization import theme

MAX_POINTS = 600
EDGE_MARGIN_DEG = 2.0


def _thin(n: int) -> slice:
    return slice(None, None, max(1, n // MAX_POINTS))


def _path(fig: go.Figure, h: HorizonResult, az, el, top: float, *, name: str, color: str, symbol: str) -> None:
    az, el = np.asarray(az, float) % 360.0, np.asarray(el, float)
    hz = np.array([theme.periodic_interp(a, h.az_deg, h.h_lb_deg) for a in az])
    vis = el >= hz
    r = top - el
    for mask, dash, width, op, label, show in ((vis, "solid", 2.6, 1.0, f"{name} (a la vista)", True),
                                               (~vis, "dot", 1.4, 0.55, f"{name} (tapado por el relieve)", True)):
        if not mask.any():
            continue
        fig.add_trace(go.Scatterpolar(theta=np.where(mask, az, np.nan), r=np.where(mask, r, np.nan), mode="markers" if dash == "dot" else "lines+markers",
                                      name=label, showlegend=show, opacity=op, connectgaps=False,
                                      line=dict(color=color, width=width), marker=dict(color=color, size=3.5 if dash == "dot" else 4.5, symbol=symbol),
                                      customdata=el, hovertemplate=name + "<br>az %{theta:.1f}°<br>el %{customdata:.2f}°<extra></extra>"))


def sky_polar(h: HorizonResult, sky: SkySeries, *, height: int = 340) -> go.Figure:
    """Cielo visto desde el punto: horizonte (terreno) + trayectoria del Sol y de la Tierra durante el periodo analizado."""
    sl = _thin(len(sky.et))
    top = float(np.ceil(max(np.nanmax(h.h_lb_deg), np.nanmax(sky.sun.el_deg), np.nanmax(sky.earth.el_deg), 2.0))) + 1.0
    bot = -EDGE_MARGIN_DEG
    rmax = top - bot
    th = np.append(h.az_deg, 360.0)
    close = lambda a: np.append(a, a[0])
    r_lb = np.clip(top - h.h_lb_deg, 0, rmax)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(theta=th, r=np.full(len(th), rmax), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatterpolar(theta=th, r=close(r_lb), mode="lines", name="Horizonte real (terreno)", fill="tonext",
                                  fillcolor="rgba(154,164,184,0.50)", line=dict(color=theme.TERRAIN, width=2.2),
                                  hovertemplate="Horizonte<br>az %{theta:.0f}°<extra></extra>"))
    _path(fig, h, sky.sun.az_deg[sl], sky.sun.el_deg[sl], top, name="Sol", color=theme.SUN, symbol="circle")
    _path(fig, h, sky.earth.az_deg[sl], sky.earth.el_deg[sl], top, name="Tierra", color=theme.EARTH, symbol="diamond")
    step = 1 if top - bot <= 6 else 2 if top - bot <= 14 else 5
    els = [e for e in np.arange(np.floor(bot), top + 0.01, step)]
    fig.update_layout(
        polar=dict(bgcolor="rgba(8,12,28,0.65)", radialaxis=dict(range=[0, rmax], tickvals=[top - e for e in els], ticktext=[f"{e:g}°" for e in els],
                                                                  gridcolor=theme.GRID, color=theme.MUTED, angle=22, tickfont=dict(size=10)),
                   angularaxis=dict(rotation=90, direction="clockwise", tickmode="array", tickvals=[0, 90, 180, 270], ticktext=["N", "E", "S", "O"],
                                    gridcolor=theme.GRID, color=theme.TEXT, tickfont=dict(size=14))))
    theme.apply_theme(fig, "", height=height)
    return theme.compact(fig, height)
