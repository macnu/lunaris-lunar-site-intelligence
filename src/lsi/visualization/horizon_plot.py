"""Perfil de horizonte 360° (cartesiano y polar) con Sol/Tierra, banda de cota y tramos limitados."""
from __future__ import annotations

from typing import Optional

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import Body, BodyTrack, HorizonResult, SkySeries, VisibilitySeries, VisibilityState
from lsi.visualization import theme

LIMITED_LABEL = "Horizonte limitado por cobertura (cota inferior)"
_BODY = {
    Body.SUN: ("Sol", theme.SUN, theme.SUN_SYMBOL),
    Body.EARTH: ("Tierra", theme.EARTH, theme.EARTH_SYMBOL),
}


def body_state(h: HorizonResult, track: BodyTrack, i: int, vis: Optional[VisibilitySeries] = None) -> VisibilityState:
    """Estado del cuerpo en el instante ``i``: del resultado de visibilidad si existe; si no, por geometría."""
    if vis is not None:
        bv = vis.sun if track.body == Body.SUN else vis.earth
        return VisibilityState(int(bv.state[i]))
    hz = theme.periodic_interp(track.az_deg[i], h.az_deg, h.h_lb_deg)
    el, rho = float(track.el_deg[i]), float(track.radius_deg[i])
    if el - rho >= hz:
        return VisibilityState.VISIBLE
    return VisibilityState.PARTIAL if el + rho > hz else VisibilityState.HIDDEN


def _disc(az: float, el: float, rho: float, n: int = 40):
    t = np.linspace(0, 2 * np.pi, n)
    return az + rho * np.cos(t) / max(np.cos(np.radians(el)), 0.2), el + rho * np.sin(t)


def _body_traces(fig: go.Figure, h, sky, vis, idx, polar: bool):
    for tr in (sky.sun, sky.earth):
        name, color, sym = _BODY[tr.body]
        st = body_state(h, tr, idx, vis)
        az, el, rho = float(tr.az_deg[idx]) % 360, float(tr.el_deg[idx]), float(tr.radius_deg[idx])
        label = f"{name} · {theme.STATE_TEXT[st]} (az {az:.1f}°, el {el:.2f}°)"
        hollow = st == VisibilityState.HIDDEN
        symbol = sym if not hollow or "open" in sym else sym + "-open"
        dx, dy = _disc(az, el, rho)
        line = dict(color=color, width=2, dash="dot" if hollow else "solid")
        mk = dict(symbol=symbol, size=14, color=color, line=dict(color=color, width=2))
        if polar:
            fig.add_trace(go.Scatterpolar(theta=dx % 360, r=90 - dy, mode="lines", fill="toself", fillcolor="rgba(255,255,255,0.12)",
                                          line=line, showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatterpolar(theta=[az], r=[90 - el], mode="markers", name=label, marker=mk))
        else:
            fig.add_trace(go.Scatter(x=dx, y=dy, mode="lines", fill="toself", fillcolor="rgba(255,255,255,0.12)",
                                     line=line, showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=[az], y=[el], mode="markers", name=label, marker=mk))


def horizon_cartesian(h: HorizonResult, sky: Optional[SkySeries] = None, vis: Optional[VisibilitySeries] = None,
                      idx: int = 0, show_band: bool = True) -> go.Figure:
    """Perfil az–el (0–360°): H_lb, banda hasta H_ub, tramos limitados con trama y Sol/Tierra en el instante ``idx``."""
    fig = go.Figure()
    az = h.az_deg
    top = h.h_ub_deg if h.h_ub_deg is not None else h.h_lb_deg
    ymin = float(min(np.nanmin(h.h_lb_deg), h.h_sphere_deg)) - 1.0
    ymax = float(max(np.nanmax(top), 5.0)) + 2.0
    if sky is not None:
        ymax = max(ymax, float(max(sky.sun.el_deg[idx], sky.earth.el_deg[idx])) + 4.0)
    fig.add_trace(go.Scatter(x=az, y=np.full_like(az, ymin), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=az, y=h.h_lb_deg, mode="lines", name="Horizonte H_lb (cota inferior)", fill="tonexty",
                             fillcolor="rgba(154,164,184,0.35)", line=dict(color=theme.TERRAIN, width=2.5)))
    if show_band and h.h_ub_deg is not None:
        fig.add_trace(go.Scatter(x=az, y=h.h_ub_deg, mode="lines", name="Cota superior H_ub", fill="tonexty",
                                 fillcolor="rgba(255,159,67,0.18)", line=dict(color=theme.WARN, width=1.8, dash="dash")))
    fig.add_trace(go.Scatter(x=[0, 360], y=[h.h_sphere_deg] * 2, mode="lines", name="Esfera lisa",
                             line=dict(color=theme.MUTED, width=1, dash="dot")))
    first = True
    for i0, i1 in theme.runs(h.limited):
        x0, x1 = az[i0], az[min(i1 + 1, len(az) - 1)]
        fig.add_trace(go.Scatter(x=[x0, x1, x1, x0, x0], y=[ymin, ymin, ymax, ymax, ymin], mode="lines", fill="toself",
                                 line=dict(color=theme.WARN, width=1), fillcolor="rgba(255,159,67,0.10)",
                                 fillpattern=dict(shape="/", fgcolor=theme.WARN, size=6, solidity=0.25),
                                 name=LIMITED_LABEL, legendgroup="lim", showlegend=first,
                                 hovertemplate=f"{LIMITED_LABEL}<br>az {x0:.1f}°–{x1:.1f}°<extra></extra>"))
        first = False
    if sky is not None:
        _body_traces(fig, h, sky, vis, idx, polar=False)
    fig.update_xaxes(title="Azimut (° desde el Norte hacia el Este)", range=[0, 360], dtick=45)
    fig.update_yaxes(title="Elevación (°)", range=[ymin, ymax])
    mode = "DEM" if h.mode.value == "dem" else "esfera lisa"
    return theme.apply_theme(fig, f"Perfil de horizonte 360° · modo {mode}", note=theme.GEOMETRIC_NOTE)


def horizon_polar(h: HorizonResult, sky: Optional[SkySeries] = None, vis: Optional[VisibilitySeries] = None,
                  idx: int = 0) -> go.Figure:
    """Vista polar del cielo: cenit en el centro, Norte arriba, azimut creciente en sentido horario."""
    fig = go.Figure()
    rmax = 92.0
    th = np.append(h.az_deg, 360.0)
    close = lambda a: np.append(a, a[0])
    r_lb = np.clip(90 - h.h_lb_deg, 0, rmax)
    fig.add_trace(go.Scatterpolar(theta=th, r=np.full(len(th), rmax), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatterpolar(theta=th, r=close(r_lb), mode="lines", name="Horizonte H_lb (terreno)", fill="tonext",
                                  fillcolor="rgba(154,164,184,0.45)", line=dict(color=theme.TERRAIN, width=2.5)))
    if h.h_ub_deg is not None:
        fig.add_trace(go.Scatterpolar(theta=th, r=close(np.clip(90 - h.h_ub_deg, 0, rmax)), mode="lines", name="Cota superior H_ub",
                                      line=dict(color=theme.WARN, width=1.8, dash="dash")))
    first = True
    for i0, i1 in theme.runs(h.limited):
        sl = slice(i0, min(i1 + 2, len(h.az_deg)))
        fig.add_trace(go.Scatterpolar(theta=h.az_deg[sl], r=r_lb[sl], mode="lines+markers", name=LIMITED_LABEL, legendgroup="lim",
                                      showlegend=first, line=dict(color=theme.WARN, width=5, dash="dash"),
                                      marker=dict(symbol="x", size=5, color=theme.WARN)))
        first = False
    if sky is not None:
        _body_traces(fig, h, sky, vis, idx, polar=True)
    fig.update_layout(polar=dict(
        bgcolor=theme.PANEL,
        angularaxis=dict(rotation=90, direction="clockwise", tickmode="array", tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                         ticktext=["N", "NE", "E", "SE", "S", "SO", "O", "NO"], gridcolor=theme.GRID, color=theme.TEXT),
        radialaxis=dict(range=[0, rmax], tickvals=[0, 30, 60, 90], ticktext=["90° (cenit)", "60°", "30°", "0° (horizonte)"],
                        gridcolor=theme.GRID, color=theme.MUTED, angle=45)))
    return theme.apply_theme(fig, "Horizonte en coordenadas polares (cenit al centro)", height=560, note=theme.GEOMETRIC_NOTE)
