"""Mapa topográfico 2D del recorte del DEM: relieve sombreado, curvas de nivel, escala, norte y nombres. Figura PURA.

Solo plotly, numpy y ``lsi.contracts``. Estética de centro de control: fondo muy oscuro, relieve en grises fríos,
observador en ámbar y etiquetas en cian. Nada depende solo del color: el observador es un rombo, los candidatos llevan
número y los rasgos con nombre llevan un símbolo por tipo (círculo = cráter, triángulo = monte, rombo = otro).

Firma (la usan Explorador 3D y, en versión ``compact=True``, otras pantallas)::

    relief_map_figure(win, observer=None, *, layer="elevation", layers=None, candidates=(), labels=(), compact=False,
                      north_deg=0.0, sun_azimuth_deg=315.0, sun_elevation_deg=6.0, exaggeration=2.0,
                      selectable=False, height=None) -> go.Figure

* ``win``: ``DemWindow`` (``win.data[fila, col]``, y decrece con la fila). Coordenadas x, y en m ABSOLUTOS del plano
  estereográfico polar sur; las marcas del eje se rotulan en km.
* ``observer``: ``ObserverPoint`` (o cualquier objeto con ``x_m``, ``y_m`` y ``label``) o ``None``.
* ``layer``: ``elevation`` | ``slope`` | ``uncertainty`` | ``sampling``. El relieve sombreado siempre va debajo; la capa
  se superpone con 55 % de opacidad y su barra de color. ``layers``: arrays del tamaño de ``win.data`` para
  ``uncertainty`` y ``sampling``. Si falta la capa pedida se usa la elevación.
* ``candidates``: ``[(etiqueta, x_m, y_m), ...]``, se numeran 1..n en el mapa (la etiqueta sale al pasar el ratón).
* ``labels``: ``[(nombre, x_m, y_m, tipo, diametro_km|None), ...]`` ya proyectados; los que caen fuera del recorte se
  ignoran. Los cráteres con diámetro conocido dibujan su contorno.
* ``compact=True``: mini-mapa (≈ 260 px, sin ejes, barra de color, curvas ni más de 3 nombres).
* ``north_deg``: giro del norte local respecto al +y del plano, en ° horarios (``atan2(x, y)`` del observador).
* ``illumination``: fracción iluminada [0, 1] del tamaño de ``win.data`` (``terrain.shadows.illumination``). Con ``layer="illumination"``
  el relieve se sombrea con el Sol dado (``sun_azimuth_deg`` de REJILLA, ``sun_elevation_deg``) y se pintan encima las zonas
  iluminadas (tono cálido) y las de sombra (azul muy oscuro), con leyenda. Sin ``illumination`` esa capa cae a la elevación.
* ``observer_subtitle``: línea en lenguaje llano bajo el nombre del punto (modos Planificador/Experto).
* ``selectable=True``: añade una rejilla invisible de puntos para recibir clics (el mapa de calor no es seleccionable).
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import DemWindow

BG = "#070b14"
PANEL = "#0d1424"
INK = "#e6ebf5"           # contraste > 15:1 sobre BG
MUTED = "#9aa7bf"         # ≈ 8:1 sobre BG
AMBER = "#ffb000"
CYAN = "#4fd8ff"
GRID = "#1c2740"

# clave → (etiqueta, escala, unidad). La elevación usa la rampa fría del 3D; el resto, escalas perceptuales.
LAYERS = {
    "elevation": ("Elevación", [[0.0, "#14203a"], [0.3, "#2f4b73"], [0.6, "#6f93ad"], [0.85, "#c4cfbc"], [1.0, "#f2e3b5"]], "m"),
    "slope": ("Pendiente", "Inferno", "°"),
    "uncertainty": ("Incertidumbre vertical", "Magma", "m"),
    "sampling": ("Confianza de muestreo", "Teal", ""),
}
WARM = (255, 190, 100)        # zonas iluminadas (tono cálido)
SHADOW = (8, 14, 50)          # zonas en sombra (azul muy oscuro)
HS_SCALE = [[0, "#05070d"], [0.5, "#4b5568"], [1, "#d5dbe6"]]       # grises fríos del relieve sombreado
SYMBOL = {"crater": "circle-open", "mons": "triangle-up-open"}
NICE_KM = (0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50)


def hillshade(z: np.ndarray, pixel_m: float, azimuth_deg: float = 315.0, elevation_deg: float = 6.0,
              exaggeration: float = 2.0) -> np.ndarray:
    """Relieve sombreado 0..1 (n·L del Sol), NaN donde falta el dato. Azimut horario desde el «arriba» del mapa.

    Sol rasante (6°): resalta cráteres y crestas. Estirado por percentiles 2–98 para que el contraste no dependa del
    recorte. Con menos de 2 filas o columnas no hay gradiente: devuelve 0,5 (plano).
    """
    z = np.asarray(z, dtype=float)
    if min(z.shape) < 2:
        return np.where(np.isfinite(z), 0.5, np.nan)
    gy, gx = np.gradient(z * exaggeration, pixel_m)       # gy: derivada por filas (hacia y negativa)
    dzdx, dzdy = gx, -gy
    az, el = np.radians(azimuth_deg), np.radians(elevation_deg)
    light = np.array([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)])
    shade = (-dzdx * light[0] - dzdy * light[1] + light[2]) / np.sqrt(dzdx ** 2 + dzdy ** 2 + 1.0)
    shade = np.clip(shade, 0.0, None)
    fin = shade[np.isfinite(shade)]
    if fin.size:
        lo, hi = np.percentile(fin, [2, 98])
        shade = np.clip((shade - lo) / (hi - lo), 0.0, 1.0) if hi > lo else np.full_like(shade, 0.5)
    return shade


def slope_deg(z: np.ndarray, pixel_m: float) -> np.ndarray:
    """Pendiente (°) por diferencias centrales; NaN donde falta dato."""
    if min(np.shape(z)) < 2:
        return np.where(np.isfinite(z), 0.0, np.nan)
    gy, gx = np.gradient(np.asarray(z, dtype=float), pixel_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def _contour_step(zmin: float, zmax: float, target: int = 10) -> float:
    raw = max((zmax - zmin) / target, 1e-9)
    e = 10.0 ** np.floor(np.log10(raw))
    return float(min((m * e for m in (1, 2, 5, 10) if m * e >= raw), default=raw))


def _scale_km(width_m: float) -> float:
    """Longitud de la barra de escala (km): la «redonda» más cercana a un quinto del ancho."""
    return float(min(NICE_KM, key=lambda k: abs(k * 1000.0 - width_m / 5.0)))


def km_text(v_m: float) -> str:
    """Metros → texto en km con coma decimal y SIN «-0,0» (el cero se escribe sin signo)."""
    t = f"{v_m / 1000:.1f}"
    return "0,0" if float(t) == 0.0 else t.replace(".", ",")


def _ticks(lo: float, hi: float) -> Tuple[list, list]:
    """Marcas «redondas» (≈ 4-8 por eje) con el texto en km."""
    q = max((hi - lo) / 4.0, 1e-9)
    e = 10.0 ** np.floor(np.log10(q))
    step = float(max(m * e for m in (1, 2, 5) if m * e <= q))
    vals = np.arange(np.ceil(lo / step) * step, hi + 1e-6, step)
    return list(vals), [km_text(v) for v in vals]


def _rgb(color: str) -> Tuple[int, int, int]:
    from plotly.colors import hex_to_rgb
    return hex_to_rgb(color) if color.startswith("#") else tuple(int(float(v)) for v in color[4:-1].split(","))


def colorscale_lut(scale, n: int = 256) -> np.ndarray:
    """Tabla (n, 3) uint8 de una escala de Plotly (nombre o lista [[pos, color]])."""
    from plotly.colors import sample_colorscale
    return np.array([_rgb(c) for c in sample_colorscale(scale, list(np.linspace(0, 1, n)))], dtype=np.uint8)


def shade_rgb(shade: np.ndarray, layer: Optional[np.ndarray] = None, scale=None, illum: Optional[np.ndarray] = None,
              layer_alpha: float = 0.55) -> np.ndarray:
    """Textura RGB (uint8, forma de ``shade`` + 3) de un relieve: gris del hillshade, con la capa encima al 55 % (igual que el mapa
    2D) o, si hay ``illum`` (fracción iluminada), tono cálido en lo iluminado y azul muy oscuro en sombra. NaN → gris medio."""
    sh = np.clip(np.nan_to_num(shade, nan=0.5), 0.0, 1.0)
    g = colorscale_lut(HS_SCALE)[(sh * 255).astype(np.uint8)].astype(float)
    if illum is not None:
        f = np.clip(np.nan_to_num(illum, nan=1.0), 0.0, 1.0)[..., None]
        lit = np.clip(g * 0.35 + np.array(WARM, float) * (0.45 + 0.75 * sh)[..., None], 0, 255)
        dark = np.array(SHADOW, float) * (1.0 + 0.9 * sh)[..., None]
        out = lit * f + dark * (1 - f)
    elif layer is not None:
        a = np.asarray(layer, float)
        fin = np.isfinite(a)
        lo, hi = (float(a[fin].min()), float(a[fin].max())) if fin.any() else (0.0, 1.0)
        idx = np.clip(np.nan_to_num((a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)) * 255, 0, 255).astype(np.uint8)
        out = layer_alpha * colorscale_lut(scale)[idx].astype(float) + (1 - layer_alpha) * g
    else:
        out = g
    return np.clip(out, 0, 255).astype(np.uint8)


def relief_map_figure(win: DemWindow, observer=None, *, layer: str = "elevation",
                      layers: Optional[Mapping[str, np.ndarray]] = None,
                      candidates: Sequence[Tuple[str, float, float]] = (),
                      labels: Sequence[Tuple[str, float, float, str, Optional[float]]] = (),
                      compact: bool = False, north_deg: float = 0.0, sun_azimuth_deg: float = 315.0,
                      sun_elevation_deg: float = 6.0, exaggeration: float = 2.0, selectable: bool = False,
                      height: Optional[int] = None, illumination: Optional[np.ndarray] = None,
                      observer_subtitle: str = "") -> go.Figure:
    """Mapa topográfico 2D del recorte (ver el docstring del módulo para la firma completa y su significado)."""
    z = np.asarray(win.data, dtype=float)
    ny, nx = z.shape
    px = float(win.pixel_size_m)
    xs = win.x0_m + px * np.arange(nx)
    ys = (win.y0_m - px * np.arange(ny))[::-1]            # y ascendente para Plotly; los arrays se voltean igual
    xlo, xhi, ylo, yhi = xs[0] - px / 2, xs[-1] + px / 2, ys[0] - px / 2, ys[-1] + px / 2
    flip = lambda a: np.asarray(a, dtype=float)[::-1]    # noqa: E731
    fig = go.Figure()
    finite = np.isfinite(z)
    if not finite.any():
        fig.add_annotation(text="Sin datos de terreno en este recorte", xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(color=AMBER, size=14))
    else:
        fig.add_trace(go.Heatmap(x=xs, y=ys, z=flip(hillshade(z, px, sun_azimuth_deg, sun_elevation_deg, exaggeration)),
                                 colorscale=HS_SCALE, showscale=False,
                                 hoverinfo="skip", name="Relieve sombreado", zsmooth=False))
        aux = {"elevation": z, "slope": slope_deg(z, px)}
        for k, a in (layers or {}).items():
            if k in ("uncertainty", "sampling") and a is not None and np.shape(a) == z.shape:
                aux[k] = np.asarray(a, dtype=float)
        lit = layer == "illumination" and illumination is not None and np.shape(illumination) == z.shape
        k = layer if layer in aux else "elevation"
        name, scale, unit = LAYERS[k]
        if lit:
            f = flip(illumination)
            fig.add_trace(go.Heatmap(x=xs, y=ys, z=f, colorscale=[[0, "rgba(255,190,100,0)"], [1, "rgba(255,190,100,0.30)"]], zmin=0, zmax=1,
                                     showscale=False, hoverinfo="skip", name="Iluminado", zsmooth=False))
            fig.add_trace(go.Heatmap(x=xs, y=ys, z=1.0 - f, colorscale=[[0, "rgba(8,14,50,0)"], [1, "rgba(8,14,50,0.84)"]], zmin=0, zmax=1,
                                     showscale=False, name="En sombra", zsmooth=False, customdata=f,
                                     hovertemplate="x=%{x:.0f} m · y=%{y:.0f} m<br>iluminado: %{customdata:.0%}<extra></extra>"))
            if not compact:
                fig.add_annotation(text="<span style='color:rgb(255,190,100)'>■</span> iluminado &nbsp; <span style='color:#5b6fd6'>■</span> en sombra",
                                   xref="paper", yref="paper", x=0.5, y=1.0, yanchor="bottom", showarrow=False,
                                   font=dict(color=INK, size=12))
        else:
            # barra horizontal sobre el mapa, centrada: sigue al mapa (equiescala) en cualquier ancho de ventana
            bar = dict(title=dict(text=f"{name} ({unit})" if unit else name, side="top", font=dict(color=INK, size=11)),
                       tickfont=dict(color=MUTED, size=10), thickness=8, len=0.45, orientation="h", x=0.5, xanchor="center",
                       y=1.0, yanchor="bottom", outlinewidth=0)
            fig.add_trace(go.Heatmap(x=xs, y=ys, z=flip(aux[k]), colorscale=scale, opacity=0.55, name=name, zsmooth=False,
                                     showscale=not compact, colorbar=bar,
                                     hovertemplate=f"x=%{{x:.0f}} m · y=%{{y:.0f}} m<br>{name}=%{{z:.1f}} {unit}<extra></extra>"))
        zf = z[finite]
        if not compact and zf.max() > zf.min():
            step = _contour_step(float(zf.min()), float(zf.max()))
            fig.add_trace(go.Contour(x=xs, y=ys, z=flip(z), showscale=False, hoverinfo="skip", name=f"Curvas cada {step:g} m",
                                     contours=dict(coloring="none", start=np.ceil(zf.min() / step) * step, end=zf.max(), size=step),
                                     line=dict(color="rgba(214,224,240,0.38)", width=0.7)))
            fig.add_annotation(text=f"Curvas cada {step:g} m", x=xlo + 0.02 * (xhi - xlo), y=ylo + 0.03 * (yhi - ylo),
                               showarrow=False, xanchor="left", yanchor="bottom", font=dict(color=INK, size=11),
                               bgcolor="rgba(7,11,20,0.7)")
    w_m, h_m = xhi - xlo, yhi - ylo
    # ---- nombres (cráteres, montes): solo los que caen dentro del recorte
    inside = [(n, x, y, t, d) for n, x, y, t, d in labels if xlo <= x <= xhi and ylo <= y <= yhi]
    inside = inside[:3] if compact else inside
    if inside:
        t = np.linspace(0, 2 * np.pi, 73)
        for n, x, y, typ, d in inside:
            if d and 0.04 * w_m <= d * 1000.0 <= 0.8 * w_m and not compact and str(typ).lower().startswith("crater"):
                r = d * 500.0
                fig.add_trace(go.Scatter(x=x + r * np.cos(t), y=y + r * np.sin(t), mode="lines", hoverinfo="skip",
                                         line=dict(color=CYAN, width=1, dash="dot"), opacity=0.55, showlegend=False))
        fig.add_trace(go.Scatter(
            x=[i[1] for i in inside], y=[i[2] for i in inside], mode="markers+text", text=[i[0] for i in inside],
            textposition="top center", textfont=dict(color=CYAN, size=9 if compact else 12),
            marker=dict(size=7 if compact else 9, color=CYAN, line=dict(width=1.5, color=CYAN),
                        symbol=[SYMBOL.get(str(i[3]).lower().split()[0], "diamond-open") for i in inside]),
            customdata=[[i[3], "" if not i[4] else f"{i[4]:.1f} km"] for i in inside], name="Nombres",
            hovertemplate="%{text}<br>%{customdata[0]} %{customdata[1]}<extra></extra>"))
    # ---- candidatos numerados y observador
    if candidates:
        fig.add_trace(go.Scatter(
            x=[c[1] for c in candidates], y=[c[2] for c in candidates], mode="markers+text",
            text=[str(i + 1) for i in range(len(candidates))], textfont=dict(color="#000", size=9 if compact else 11),
            marker=dict(size=12 if compact else 18, color=INK, line=dict(color=BG, width=1.5)), name="Candidatos",
            customdata=[c[0] for c in candidates], hovertemplate="%{customdata}<extra></extra>"))
    if observer is not None:
        name = (getattr(observer, "label", "") or "Observador").split(" [")[0]
        fig.add_trace(go.Scatter(
            x=[observer.x_m], y=[observer.y_m], mode="markers", name="Observador", customdata=[[name, observer_subtitle]],
            marker=dict(size=11 if compact else 15, symbol="diamond", color=AMBER, line=dict(color="#000", width=1.5)),
            hovertemplate="%{customdata[0]}<br>%{customdata[1]}<br>x=%{x:.0f} m · y=%{y:.0f} m<extra></extra>"))
        if not compact:
            # rótulo como anotación (con fondo, legible sobre el relieve); en la mitad superior se pone debajo del punto
            below = observer.y_m > (ylo + yhi) / 2
            txt = f"<b>{name}</b>" + (f"<br><span style='font-size:11px;color:{MUTED}'>{observer_subtitle}</span>" if observer_subtitle else "")
            fig.add_annotation(x=observer.x_m, y=observer.y_m, text=txt, showarrow=False, yshift=-24 if below else 24,
                               yanchor="top" if below else "bottom", font=dict(color=AMBER, size=12), bgcolor="rgba(7,11,20,0.78)",
                               borderpad=3)
    # ---- escala gráfica (km) abajo a la derecha
    km = _scale_km(w_m)
    sx1, sx0, sy = xhi - 0.05 * w_m, xhi - 0.05 * w_m - km * 1000.0, ylo + 0.06 * h_m
    for wd, col in ((6, "#000"), (3, INK)):
        fig.add_trace(go.Scatter(x=[sx0, sx1], y=[sy, sy], mode="lines", line=dict(color=col, width=wd), hoverinfo="skip",
                                 showlegend=False, name="Escala"))
    fig.add_annotation(x=(sx0 + sx1) / 2, y=sy, text=f"{km:g} km".replace(".", ","), showarrow=False, yshift=11,
                       font=dict(color=INK, size=10 if compact else 12), bgcolor="rgba(7,11,20,0.6)")
    # ---- norte (flecha + «N»), arriba a la derecha
    th = np.radians(north_deg)
    L = 14 if compact else 26
    dx, dy = float(np.sin(th)), float(np.cos(th))
    nx0, ny0 = xhi - 0.07 * w_m, yhi - 0.12 * h_m
    fig.add_annotation(x=nx0, y=ny0, axref="pixel", ayref="pixel", ax=-L * dx, ay=L * dy, text="", showarrow=True,
                       arrowhead=2, arrowwidth=2, arrowcolor=INK)
    fig.add_annotation(x=nx0, y=ny0, text="<b>N</b>", showarrow=False, xshift=15 * dx, yshift=15 * dy,
                       font=dict(color=INK, size=11 if compact else 13), bgcolor="rgba(7,11,20,0.6)")
    # ---- clic (selección de punto)
    if selectable:
        gx, gy = np.meshgrid(np.linspace(xlo, xhi, 80), np.linspace(ylo, yhi, 80))
        fig.add_trace(go.Scatter(x=gx.ravel(), y=gy.ravel(), mode="markers", marker=dict(size=10, opacity=0), hoverinfo="none",
                                 showlegend=False, name="clic"))
        fig.update_layout(dragmode="pan", clickmode="event+select")
    tx, tt = _ticks(xlo, xhi)
    ty, tyt = _ticks(ylo, yhi)
    axis = dict(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED, size=11), color=MUTED)
    fig.update_xaxes(range=[xlo, xhi], visible=not compact, tickvals=tx, ticktext=tt, title="x estereográfica (km)",
                     constrain="domain", **axis)
    fig.update_yaxes(range=[ylo, yhi], visible=not compact, tickvals=ty, ticktext=tyt, title="y estereográfica (km)",
                     scaleanchor="x", scaleratio=1, constrain="domain", **axis)
    fig.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG, height=height or (260 if compact else 620), showlegend=False,
        font=dict(color=INK, family="Inter, Segoe UI, Arial, sans-serif", size=12),
        margin=dict(l=4, r=4, t=4, b=4) if compact else dict(l=60, r=20, t=70, b=50),
        hoverlabel=dict(bgcolor=PANEL, font=dict(color=INK)), uirevision="lsi-relief")
    return fig
