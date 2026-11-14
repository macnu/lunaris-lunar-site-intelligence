"""Figura del mapa navegable del polo sur (ejes en km): imagen JPEG del relieve bajo curvas de nivel opcionales, paralelos y
meridianos, recortes de 5 m, nombres sin solapes, escala y rejilla invisible para recibir clics. Figura PURA (plotly y numpy);
los datos (vistas, capas, imagen) los prepara ``lsi.data.polar_view``. Coordenadas de entrada en metros del plano estereográfico.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import MOON_RADIUS_M
from lsi.visualization.relief_map import AMBER, BG, CYAN, GRID, INK, MUTED, _contour_step

FAR_HALF_M = 304_000.0              # radio del DEM polar de 80 m (= lsi.data.polar_view.FAR_HALF_M)
NICE_KM = (1, 2, 5, 10, 20, 50, 100, 200)
PARALLELS = (-82.0, -84.0, -86.0, -88.0)


def parallels_m() -> list[tuple[float, float]]:
    """[(latitud, radio_m)] de los paralelos dibujados: ρ = 2R·cosφ/(1−sinφ)."""
    return [(p, float(2 * MOON_RADIUS_M * np.cos(np.radians(p)) / (1 - np.sin(np.radians(p))))) for p in PARALLELS]


def nice_km(width_m: float) -> float:
    return float(min(NICE_KM, key=lambda k: abs(k * 1000.0 - width_m / 5.0)))


def _decimate(z: np.ndarray, max_px: int) -> tuple[np.ndarray, int]:
    """Promedio por bloques (ignora NaN) hasta ≤ ``max_px`` por lado."""
    f = max(1, int(np.ceil(max(z.shape) / max_px)))
    if f == 1:
        return np.asarray(z, float), 1
    h, w = (z.shape[0] // f) * f, (z.shape[1] // f) * f
    b = np.asarray(z[:h, :w], float).reshape(h // f, f, w // f, f)
    ok = np.isfinite(b)
    return np.where(ok.any(axis=(1, 3)), np.where(ok, b, 0.0).sum(axis=(1, 3)) / np.maximum(ok.sum(axis=(1, 3)), 1), np.nan), f


# ------------------------------------------------------------------------------------------------ figura
def polar_map_figure(v, image_uri: str, *, labels: Sequence = (), recortes: Sequence[tuple[str, tuple]] = (),
                     observer: Optional[tuple[float, float, str]] = None, grid: bool = True, contours: bool = False,
                     color_bar: Optional[tuple[str, str, float, float]] = None, click_n: int = 90, height: int = 700,
                     psr_legend: bool = False) -> go.Figure:
    """Figura del mapa (ejes en km). ``recortes``: [(nombre, (xmin, ymin, xmax, ymax) m)]; ``observer``: (x_m, y_m, etiqueta);
    ``color_bar``: (título, escala, vmin, vmax) de la capa de color; ``click_n``: lado de la rejilla invisible de clics."""
    xlo, xhi, ylo, yhi = (e / 1000.0 for e in v.extent)
    W = xhi - xlo
    fig = go.Figure()
    fig.add_layout_image(dict(source=image_uri, xref="x", yref="y", x=xlo, y=yhi, sizex=xhi - xlo, sizey=yhi - ylo,
                              xanchor="left", yanchor="top", sizing="stretch", layer="below"))
    if contours and np.isfinite(v.z).any():
        z, f = _decimate(v.z, 260)
        zf = z[np.isfinite(z)]
        step = _contour_step(float(zf.min()), float(zf.max()))
        xs = (v.x0 + v.px * (f - 1) / 2 + v.px * f * np.arange(z.shape[1])) / 1000.0
        ys = (v.y0 - v.px * (f - 1) / 2 - v.px * f * np.arange(z.shape[0])) / 1000.0
        fig.add_trace(go.Contour(x=xs, y=ys[::-1], z=z[::-1], showscale=False, hoverinfo="skip", name=f"Curvas cada {step:g} m",
                                 contours=dict(coloring="none", start=np.ceil(zf.min() / step) * step, end=zf.max(), size=step),
                                 line=dict(color="rgba(230,235,245,0.45)", width=0.6)))
        fig.add_annotation(text=f"Curvas cada {step:g} m", x=xlo + 0.02 * W, y=ylo + 0.03 * (yhi - ylo), showarrow=False,
                           xanchor="left", yanchor="bottom", font=dict(color=INK, size=11), bgcolor="rgba(7,11,20,0.7)")
    if grid:
        t = np.linspace(0, 2 * np.pi, 181)
        for lat, rho in parallels_m():
            r = rho / 1000.0
            fig.add_trace(go.Scatter(x=r * np.sin(t), y=r * np.cos(t), mode="lines", hoverinfo="skip", showlegend=False,
                                     line=dict(color="rgba(200,210,230,0.35)", width=0.7, dash="dot")))
            if xlo < r * 0.707 < xhi and ylo < r * 0.707 < yhi:
                fig.add_annotation(x=r * 0.707, y=r * 0.707, text=f"{abs(lat):g}°S", showarrow=False, font=dict(color=MUTED, size=10))
        far = FAR_HALF_M / 1000.0 * 1.5
        for lon, lbl in ((0, "0°E"), (90, "90°E"), (180, "180°E"), (270, "270°E")):
            ex, ey = far * np.sin(np.radians(lon)), far * np.cos(np.radians(lon))
            fig.add_trace(go.Scatter(x=[0, ex], y=[0, ey], mode="lines", hoverinfo="skip", showlegend=False,
                                     line=dict(color="rgba(200,210,230,0.22)", width=0.6)))
            rx, ry = 0.97 * FAR_HALF_M / 1000.0 * np.sin(np.radians(lon)), 0.97 * FAR_HALF_M / 1000.0 * np.cos(np.radians(lon))
            if xlo < rx < xhi and ylo < ry < yhi:
                fig.add_annotation(x=rx, y=ry, text=lbl, showarrow=False, font=dict(color=MUTED, size=10), bgcolor="rgba(7,11,20,0.6)")
    # recortes de 5 m
    for name, (x0, y0, x1, y1) in recortes:
        fig.add_trace(go.Scatter(x=[x0 / 1000, x1 / 1000, x1 / 1000, x0 / 1000, x0 / 1000], y=[y0 / 1000, y0 / 1000, y1 / 1000, y1 / 1000, y0 / 1000],
                                 mode="lines", line=dict(color=AMBER, width=1.6), hoverinfo="skip", showlegend=False))
        fig.add_annotation(x=(x0 + x1) / 2000, y=y1 / 1000, text=f"<b>{name}</b> (5 m)", showarrow=False, yshift=9, yanchor="bottom",
                           font=dict(color=AMBER, size=11), bgcolor="rgba(7,11,20,0.78)", borderpad=2)
    # nombres
    if labels:
        t = np.linspace(0, 2 * np.pi, 73)
        for n, x, y, typ, dk in labels:
            if dk and 0.05 * W <= dk <= 0.8 * W and str(typ).lower().startswith("crater"):
                fig.add_trace(go.Scatter(x=x / 1000 + dk / 2 * np.cos(t), y=y / 1000 + dk / 2 * np.sin(t), mode="lines", hoverinfo="skip",
                                         showlegend=False, line=dict(color=CYAN, width=1, dash="dot"), opacity=0.6))
        sym = {"crater": "circle-open", "mons": "triangle-up-open"}
        fig.add_trace(go.Scatter(
            x=[l[1] / 1000 for l in labels], y=[l[2] / 1000 for l in labels], mode="markers+text", text=[l[0] for l in labels],
            textposition="top center", textfont=dict(color=CYAN, size=11), name="Nombres",
            marker=dict(size=7, color=CYAN, line=dict(width=1.4, color=CYAN),
                        symbol=[sym.get(str(l[3]).lower().split()[0], "diamond-open") for l in labels]),
            customdata=[[l[3], "" if not l[4] else f"{l[4]:.0f} km"] for l in labels],
            hovertemplate="%{text}<br>%{customdata[0]} %{customdata[1]}<extra></extra>"))
    # barra de color de la capa
    if color_bar is not None:
        title, scale, lo, hi = color_bar
        fig.add_trace(go.Scatter(x=[xlo], y=[ylo], mode="markers", hoverinfo="skip", showlegend=False,
                                 marker=dict(size=0.1, color=[lo], colorscale=scale, cmin=lo, cmax=hi, showscale=True,
                                             colorbar=dict(title=dict(text=title, side="top", font=dict(color=INK, size=11)),
                                                           tickfont=dict(color=MUTED, size=10), thickness=9, len=0.5, orientation="h",
                                                           x=0.5, xanchor="center", y=1.0, yanchor="bottom", outlinewidth=0))))
    if psr_legend:
        fig.add_annotation(text="<span style='color:rgb(70,140,255)'>■</span> PSR de 18,6 años", xref="paper", yref="paper", x=0.01, y=0.99,
                           xanchor="left", yanchor="top", showarrow=False, font=dict(color=INK, size=11), bgcolor="rgba(7,11,20,0.7)")
    # escala gráfica (km) abajo a la derecha
    km = nice_km(W * 1000.0)
    sx1, sx0, sy = xhi - 0.05 * W, xhi - 0.05 * W - km, ylo + 0.06 * (yhi - ylo)
    for wd, col in ((6, "#000"), (3, INK)):
        fig.add_trace(go.Scatter(x=[sx0, sx1], y=[sy, sy], mode="lines", line=dict(color=col, width=wd), hoverinfo="skip", showlegend=False))
    fig.add_annotation(x=(sx0 + sx1) / 2, y=sy, text=f"{km:g} km", showarrow=False, yshift=11, font=dict(color=INK, size=12),
                       bgcolor="rgba(7,11,20,0.6)")
    # norte: en esta proyección el norte local apunta hacia FUERA del polo (radial)
    fig.add_annotation(text="<b>N</b> ↑ hacia fuera del centro<br>el centro es el polo sur · 0°E arriba", xref="paper", yref="paper",
                       x=0.99, y=0.99, xanchor="right", yanchor="top", showarrow=False, align="right",
                       font=dict(color=INK, size=11), bgcolor="rgba(7,11,20,0.7)")
    if observer is not None:
        ox, oy, olabel = observer
        if xlo <= ox / 1000 <= xhi and ylo <= oy / 1000 <= yhi:
            fig.add_trace(go.Scatter(x=[ox / 1000], y=[oy / 1000], mode="markers", name="Punto de observación",
                                     marker=dict(size=15, symbol="diamond", color=AMBER, line=dict(color="#000", width=1.5)),
                                     customdata=[olabel], hovertemplate="%{customdata}<br>x=%{x:.1f} km · y=%{y:.1f} km<extra></extra>"))
            fig.add_annotation(x=ox / 1000, y=oy / 1000, text=f"<b>{olabel}</b>", showarrow=False, yshift=-22, yanchor="top",
                               font=dict(color=AMBER, size=12), bgcolor="rgba(7,11,20,0.78)", borderpad=3)
    # rejilla invisible: Plotly no deja seleccionar una imagen, así que los clics se reciben en puntos transparentes
    gx, gy = np.meshgrid(np.linspace(xlo, xhi, click_n), np.linspace(ylo, yhi, click_n))
    fig.add_trace(go.Scatter(x=gx.ravel(), y=gy.ravel(), mode="markers", marker=dict(size=10, opacity=0), hoverinfo="none",
                             showlegend=False, name="clic"))
    ticks = np.arange(np.ceil(xlo / 100.0) * 100, xhi + 1e-6, 100) if W > 250 else None
    axis = dict(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED, size=11), color=MUTED, fixedrange=True)
    fig.update_xaxes(range=[xlo, xhi], title="x estereográfica (km)", constrain="domain", **axis)
    fig.update_yaxes(range=[ylo, yhi], title="y estereográfica (km)", scaleanchor="x", scaleratio=1, constrain="domain", **axis)
    if ticks is not None:
        fig.update_xaxes(tickvals=list(ticks))
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, height=height, showlegend=False, dragmode="pan", clickmode="event+select",
                      font=dict(color=INK, family="Inter, Segoe UI, Arial, sans-serif", size=12),
                      margin=dict(l=60, r=20, t=60, b=50), hoverlabel=dict(bgcolor="#0d1424", font=dict(color=INK)))
    return fig


def click_precision_km(v, click_n: int = 90) -> float:
    """Lado de la celda de la rejilla de clics (km): la precisión declarada del punto elegido en el mapa."""
    xlo, xhi, _, _ = v.extent
    return (xhi - xlo) / 1000.0 / (click_n - 1)
