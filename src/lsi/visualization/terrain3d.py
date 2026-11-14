"""Superficie 3D del recorte del DEM (relieve sombreado) y mapa 2D del plano polar. Figuras puras."""
from __future__ import annotations

import warnings
from typing import Mapping, Optional, Sequence, Tuple

import numpy as np
import plotly.graph_objects as go

from lsi.contracts import DemWindow, HorizonMode, ObserverPoint
from lsi.visualization import theme
from lsi.visualization.relief_map import AMBER, CYAN, hillshade, km_text, shade_rgb

# Rampa hipsométrica sobria (azul noche → azul acero → arena pálida); el relieve se lee sobre todo por la iluminación.
ELEV_SCALE = [[0.0, "#14203a"], [0.3, "#2f4b73"], [0.6, "#6f93ad"], [0.85, "#c4cfbc"], [1.0, "#f2e3b5"]]
# clave → (etiqueta, escala de color, unidad)
LAYERS = {
    "elevation": ("Elevación", ELEV_SCALE, "m"),
    "slope": ("Pendiente", "Inferno", "°"),
    "uncertainty": ("Incertidumbre vertical", "Magma", "m"),
    "sampling": ("Confianza de muestreo (retornos LOLA)", "Teal", ""),
}
CAM_YAW_DEG = 12.0   # la cámara mira desde el norte, girada 12° al este (evita el encuadre frontal plano)
CAM_ELEV_DEG = 30.0  # elevación de la cámara sobre el horizonte: vista oblicua BAJA, el relieve se lee en perfil
HS_AZ, HS_EL, HS_EXAG = 300.0, 14.0, 2.0   # luz que hornea la textura (azimut de rejilla, elevación, exageración del gradiente)
NOTE = "Resolución efectiva del DEM ≈ 30 m (5 m/píxel nominal). " + theme.GEOMETRIC_NOTE


def downsample(a: np.ndarray, max_px: int = 400) -> Tuple[np.ndarray, int]:
    """Promedio por bloques (ignora NaN) hasta ≤ ``max_px`` por lado. Devuelve (array, factor)."""
    f = int(np.ceil(max(a.shape) / max_px))
    if f <= 1:
        return np.asarray(a, dtype=float), 1
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    blocks = np.asarray(a[:h, :w], dtype=float).reshape(h // f, f, w // f, f)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)     # bloques todo-NaN → NaN
        out = np.nanmean(blocks, axis=(1, 3))
    return out, f


def slope_deg(z: np.ndarray, pixel_m: float) -> np.ndarray:
    """Pendiente (°) por diferencias centrales; NaN donde falta dato."""
    gy, gx = np.gradient(z, pixel_m)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def _layer_arrays(win: DemWindow, extra: Optional[Mapping[str, np.ndarray]], max_px: int):
    z, f = downsample(win.data, max_px)
    arrays = {"elevation": z, "slope": slope_deg(z, win.pixel_size_m * f)}
    for k, a in (extra or {}).items():
        if k in ("uncertainty", "sampling") and a is not None and np.shape(a) == win.data.shape:
            arrays[k] = downsample(np.asarray(a), max_px)[0]
    return arrays, f


def _axes(win: DemWindow, shape, f: int):
    ps = win.pixel_size_m * f
    off = (f - 1) / 2.0 * win.pixel_size_m          # centro del bloque
    x = win.x0_m + off + ps * np.arange(shape[1])
    y = win.y0_m - off - ps * np.arange(shape[0])
    return x, y


def _observer_z(win: DemWindow, obs: ObserverPoint) -> float:
    if obs.ground_z_m is not None:
        return obs.ground_z_m + obs.height_m
    c = int(round((obs.x_m - win.x0_m) / win.pixel_size_m))
    r = int(round((win.y0_m - obs.y_m) / win.pixel_size_m))
    if 0 <= r < win.data.shape[0] and 0 <= c < win.data.shape[1] and np.isfinite(win.data[r, c]):
        return float(win.data[r, c]) + obs.height_m
    return float(np.nanmean(win.data))


def _colorbar(k: str):
    label, _, unit = LAYERS[k]
    # Barra a la derecha, estrecha y de poco más de media altura: la escena 3D manda, la barra acompaña.
    return dict(title=dict(text=f"{label} ({unit})" if unit else label, font=dict(color=theme.TEXT, size=12), side="right"),
                tickfont=dict(color=theme.MUTED, size=11), thickness=12, len=0.55, x=1.0, xanchor="left", y=0.5, yanchor="middle")


def _legend_inside(fig: go.Figure) -> None:
    fig.update_layout(legend=dict(x=0.01, y=0.99, xanchor="left", yanchor="top", orientation="v"))


def _nice(x: float) -> float:
    """Mayor paso «redondo» (1, 2, 5 × 10^k) que no pase de x."""
    x = max(float(x), 1e-9)
    e = 10.0 ** np.floor(np.log10(x))
    return float(max(m * e for m in (1, 2, 5) if m * e <= x))


def _km_ticks(lo: float, hi: float, centre: float, n: int = 5) -> Tuple[list, list]:
    """Marcas en coordenadas locales (m desde ``centre``) con texto en km ABSOLUTOS del plano estereográfico."""
    step = _nice((hi - lo) / n)  # n = nº máximo de marcas aprox.
    vals = np.arange(np.ceil((lo + centre) / step) * step, hi + centre + 1e-6, step)
    return list((vals - centre) / 1000.0), [km_text(v) for v in vals]


def _palette_surface(rgb: np.ndarray, n_colors: int = 256):
    """RGB (H, W, 3) → (índices, escala de color discreta, índice máximo): ``go.Surface`` solo colorea con un escalar, así que se
    cuantiza la textura a ≤ 256 colores por corte por la mediana (NumPy, sin tramado) y se usa la paleta como colorscale."""
    px = rgb.reshape(-1, 3).astype(float)
    boxes = [np.arange(len(px))]
    while len(boxes) < n_colors:
        new = []
        for idx in boxes:
            if len(idx) < 2:
                new.append(idx)
                continue
            c = px[idx]
            order = idx[np.argsort(c[:, int(np.argmax(np.ptp(c, axis=0)))], kind="stable")]
            new += [order[:len(order) // 2], order[len(order) // 2:]]
        if len(new) == len(boxes):
            break
        boxes = new
    index = np.zeros(len(px))
    pal = []
    for k, idx in enumerate(boxes):
        index[idx] = k
        pal.append(np.rint(px[idx].mean(axis=0)).astype(int))
    nmax = max(len(pal) - 1, 1)
    scale = [[k / nmax, f"rgb({r},{g},{b})"] for k, (r, g, b) in enumerate(pal)]
    if len(scale) == 1:
        scale.append([1.0, scale[0][1]])
    return index.reshape(rgb.shape[:2]), scale, nmax


def _place(a: np.ndarray, xs: np.ndarray, ys: np.ndarray, x: float, y: float) -> Optional[float]:
    """Elevación del array (ejes xs ascendente, ys descendente) más cercana a (x, y); None fuera o sin dato."""
    c, r = int(round(np.interp(x, xs, np.arange(len(xs)), left=-1, right=-1))), int(round(np.interp(-y, -ys, np.arange(len(ys)), left=-1, right=-1)))
    if c < 0 or r < 0:
        return None
    v = a[r, c]
    return float(v) if np.isfinite(v) else None


def terrain_surface_3d(win: DemWindow, observer: Optional[ObserverPoint] = None,
                       layers: Optional[Mapping[str, np.ndarray]] = None, layer: str = "elevation",
                       max_px: int = 400, z_exaggeration: float = 1.0, *, buttons: bool = True,
                       markers: Sequence[Tuple[str, float, float, Optional[float]]] = (),
                       north_deg: float = 0.0, height: int = 600,
                       illumination: Optional[np.ndarray] = None, sun_az_deg: float = HS_AZ, sun_el_deg: float = HS_EL,
                       labels: Sequence[Tuple[str, float, float, str, Optional[float]]] = (), max_labels: int = 8,
                       observer_label: str = "") -> go.Figure:
    """Superficie 3D iluminada y texturizada del recorte.

    Textura: el color de cada celda es el HILLSHADE del mapa 2D (``relief_map.hillshade``) mezclado con el color de la capa
    (``relief_map.shade_rgb``, misma estética que el mapa), horneado en una paleta de 255 colores; además Plotly aplica su propia
    iluminación suave. Sin cuadrícula ni contornos. Con ``layer="illumination"`` y ``illumination`` (fracción [0, 1] del tamaño de
    ``win.data``, ver ``terrain.shadows``) la textura se hace con el Sol dado (``sun_az_deg`` de REJILLA, ``sun_el_deg``): cálido
    donde da el Sol y azul muy oscuro en sombra.

    Causa raíz del colapso (P1-1): Plotly 3D centra la cámara en el ORIGEN de los datos, no en el centro de la caja. Con x, y
    en metros estereográficos absolutos (y ≈ 122 000 m frente a un recorte de 12 000 m) la escena quedaba a ~10 unidades de
    la cámara y se veía como un punto. Ahora x, y van en km LOCALES (centro del recorte = 0) con marcas que rotulan los km
    absolutos, y rangos y proporción de la caja son explícitos (1 : h/w : relieve·exageración).

    ``layer``: capa activa (``elevation``, ``slope``, ``uncertainty``, ``sampling``, ``illumination``). Con ``buttons=False`` solo se
    dibuja esa capa; con ``buttons=True`` (compatibilidad) hay una traza por capa y botones sobre la escena. ``markers``: candidatos
    (etiqueta, x_m, y_m, z_m|None) absolutos, numerados 1..n. ``labels``: nombres del gazetteer (nombre, x, y, tipo, diámetro km),
    los ``max_labels`` de mayor diámetro flotan sobre su posición con la z real del terreno. ``north_deg``: giro del norte local
    respecto al +y del plano (° horario); la cámara mira desde el norte. ``layers``: arrays del tamaño de ``win.data``.
    """
    arrays, f = _layer_arrays(win, layers, max_px)
    x, y = _axes(win, arrays["elevation"].shape, f)
    z = arrays["elevation"]
    ill = None
    if illumination is not None and np.shape(illumination) == win.data.shape:
        ill = downsample(np.asarray(illumination, float), max_px)[0]
    cx, cy = float((x.min() + x.max()) / 2), float((y.min() + y.max()) / 2)
    xl, yl = (x - cx) / 1000.0, (y - cy) / 1000.0
    keys = [k for k in LAYERS if k in arrays] + (["illumination"] if ill is not None else [])
    active = keys.index(layer) if layer in keys else 0
    zf = z[np.isfinite(z)]
    z0, z1 = (float(zf.min()), float(zf.max())) if zf.size else (0.0, 1.0)
    span = max(z1 - z0, 1.0)
    lit = keys[active] == "illumination"
    shade = hillshade(z, win.pixel_size_m * f, sun_az_deg if lit else HS_AZ, sun_el_deg if lit else HS_EL, HS_EXAG)
    fig = go.Figure()
    for k in (keys if buttons else [keys[active]]):
        if k == "illumination":
            rgb, label, scale0, unit = shade_rgb(shade, illum=ill), "Iluminación", None, ""
        else:
            label, scale0, unit = LAYERS[k]
            rgb = shade_rgb(shade, arrays[k], scale0)
        idx, pal, nmax = _palette_surface(rgb)
        extra = arrays[k] if k != "illumination" else ill
        fig.add_trace(go.Surface(
            x=xl, y=yl, z=z, surfacecolor=idx, colorscale=pal, cmin=0, cmax=nmax, showscale=False, name=label, colorbar=_colorbar(k) if k in LAYERS else None,
            visible=(k == keys[active]), customdata=extra, contours=dict(x=dict(show=False), y=dict(show=False), z=dict(show=False)),
            # la textura ya lleva el relieve sombreado: la luz de Plotly solo suaviza la forma global (ambient alto, sin brillo)
            lighting=dict(ambient=0.5, diffuse=0.7, specular=0.04, roughness=0.95, fresnel=0.02),
            lightposition=dict(x=-60000, y=40000, z=30000),
            hovertemplate="x=%{x:.2f} km · y=%{y:.2f} km (local)<br>elevación=%{z:.0f} m<extra></extra>"))
    if not buttons and not lit and scale0 is not None:    # barra de color de la capa (la textura horneada no la lleva): traza vacía con colorbar
        k = keys[active]
        zz = arrays[k][np.isfinite(arrays[k])]
        fig.add_trace(go.Scatter3d(x=[None], y=[None], z=[None], mode="markers", showlegend=False, hoverinfo="skip", visible=True,
                                   marker=dict(color=[float(zz.min()), float(zz.max())] if zz.size else [0, 1], colorscale=LAYERS[k][1],
                                               showscale=True, colorbar=_colorbar(k), size=0.01)))
    unit_z = max(span * 0.02, 5.0)           # separación de rótulos sobre el terreno
    if observer is not None:
        ox, oy, oz = (observer.x_m - cx) / 1000.0, (observer.y_m - cy) / 1000.0, _observer_z(win, observer)
        gz = oz - observer.height_m
        name = observer_label or (observer.label or "Observador").split(" [")[0]
        top = gz + 0.22 * span
        fig.add_trace(go.Scatter3d(x=[ox, ox], y=[oy, oy], z=[gz, top], mode="lines", showlegend=False, hoverinfo="skip",
                                   line=dict(color=AMBER, width=4)))
        fig.add_trace(go.Scatter3d(x=[ox], y=[oy], z=[top], mode="markers", showlegend=False, hoverinfo="skip",
                                   marker=dict(size=20, color=AMBER, opacity=0.18)))       # halo
        fig.add_trace(go.Scatter3d(
            x=[ox], y=[oy], z=[top], mode="markers+text", text=[name], textposition="top center",
            textfont=dict(color=AMBER, size=12), name="Observador", customdata=[[name]],
            marker=dict(size=8, color="#fff4cf", symbol="diamond", line=dict(color=AMBER, width=3)),
            hovertemplate="%{customdata[0]}<br>z=%{z:.0f} m<extra></extra>"))
    cand = [m for m in markers if m[3] is not None]
    if cand:
        fig.add_trace(go.Scatter3d(
            x=[(m[1] - cx) / 1000.0 for m in cand], y=[(m[2] - cy) / 1000.0 for m in cand], z=[m[3] + unit_z for m in cand],
            mode="markers+text", text=[str(i + 1) for i in range(len(cand))], textposition="middle center",
            textfont=dict(color="#000", size=11), name="Candidatos", customdata=[m[0].split(" (")[0] for m in cand],
            marker=dict(size=11, symbol="circle", color="#e6ebf5", line=dict(color="#070b14", width=1)),
            hovertemplate="%{customdata}<extra></extra>"))
    named = []
    for n, lx, ly, typ, d in sorted(labels, key=lambda t: -(t[4] or 0.0)):
        zz = _place(z, x, y, lx, ly)
        if zz is not None and len(named) < max_labels:
            named.append((n, lx, ly, zz, typ, d))
    if named:
        fig.add_trace(go.Scatter3d(
            x=[(t[1] - cx) / 1000.0 for t in named], y=[(t[2] - cy) / 1000.0 for t in named], z=[t[3] + 2 * unit_z for t in named],
            mode="markers+text", text=[t[0] for t in named], textposition="top center", textfont=dict(color=CYAN, size=10),
            name="Nombres", customdata=[[t[4], "" if not t[5] else f"{t[5]:.1f} km"] for t in named],
            marker=dict(size=3, color=CYAN, symbol="circle"), hovertemplate="%{text}<br>%{customdata[0]} %{customdata[1]}<extra></extra>"))
    if buttons:
        n_extra = len(fig.data) - len(keys)
        btn = [dict(label=(LAYERS[k][0] if k != "illumination" else "Iluminación").split(" (")[0].replace("Incertidumbre vertical", "Incertidumbre")
                    .replace("Confianza de muestreo", "Muestreo"), method="update",
                    args=[{"visible": [j == i for j in range(len(keys))] + [True] * n_extra}]) for i, k in enumerate(keys)]
        fig.update_layout(updatemenus=[dict(type="buttons", direction="right", buttons=btn, x=0, xanchor="left", y=1.1,
                                            yanchor="bottom", bgcolor=theme.PANEL, font=dict(color=theme.TEXT), active=active)])
    ex, ey = max((x.max() - x.min()) / 1000.0, 1e-3), max((y.max() - y.min()) / 1000.0, 1e-3)
    tx, tx_txt = _km_ticks(float(x.min() - cx), float(x.max() - cx), cx)
    ty, ty_txt = _km_ticks(float(y.min() - cy), float(y.max() - cy), cy)
    th = np.radians(north_deg + CAM_YAW_DEG)
    ce = np.radians(CAM_ELEV_DEG)
    zr = max(span / (ex * 1000.0) * z_exaggeration, 0.05)
    dist = 1.4 + 1.2 * max(0.0, zr - 0.5)                                                      # distancia de la cámara al centro, en unidades de la caja
    # ejes discretos: sin paneles ni rejilla, solo marcas pequeñas en km (x, y) y m (z)
    ax = dict(showbackground=False, showgrid=False, zeroline=False, showline=False, color=theme.MUTED, showspikes=False,
              tickfont=dict(size=9, color=theme.MUTED), title_font=dict(size=10, color=theme.MUTED))
    fig.update_layout(scene=dict(
        aspectmode="manual", aspectratio=dict(x=1.0, y=ey / ex, z=zr),
        xaxis=dict(title="x (km)", range=[float(xl.min()), float(xl.max())], tickvals=tx, ticktext=tx_txt, **ax),
        yaxis=dict(title="y (km)", range=[float(yl.min()), float(yl.max())], tickvals=ty, ticktext=ty_txt, **ax),
        zaxis=dict(title="m", range=[z0, z1 + 0.25 * span], nticks=4, **ax), bgcolor="#05070d",
        camera=dict(center=dict(x=0, y=0, z=-0.12 * zr),
                    eye=dict(x=dist * float(np.cos(ce) * np.sin(th)), y=dist * float(np.cos(ce) * np.cos(th)), z=dist * float(np.sin(ce)))),
        domain=dict(x=[0, 1], y=[0, 1])))
    fig = theme.apply_theme(fig, "Relieve 3D del recorte del DEM" if buttons else "", height=height, note=NOTE)
    _legend_inside(fig)
    fig.update_layout(paper_bgcolor="#05070d", showlegend=False)
    fig.update_layout(margin=dict(l=0, r=0, t=100 if buttons else 10, b=60), uirevision="lsi-3d")
    return fig


def terrain_polar_map(win: Optional[DemWindow], observer: ObserverPoint, layers: Optional[Mapping[str, np.ndarray]] = None,
                      layer: str = "elevation", max_px: int = 400,
                      rings_m: Tuple[float, ...] = (500.0, 1000.0, 2000.0)) -> go.Figure:
    """Mapa 2D en el plano estereográfico polar sur con el observador y anillos de distancia.

    Sin DEM (esfera lisa) muestra solo el punto y el aviso «sin relieve».
    """
    fig = go.Figure()
    if win is not None:
        arrays, f = _layer_arrays(win, layers, max_px)
        k = layer if layer in arrays else "elevation"
        x, y = _axes(win, arrays[k].shape, f)
        fig.add_trace(go.Heatmap(x=x, y=y, z=arrays[k], colorscale=LAYERS[k][1], name=LAYERS[k][0], colorbar=_colorbar(k)))
    t = np.linspace(0, 2 * np.pi, 121)
    for i, r in enumerate(rings_m):
        fig.add_trace(go.Scatter(x=observer.x_m + r * np.cos(t), y=observer.y_m + r * np.sin(t), mode="lines",
                                 line=dict(color=theme.TEXT, width=1, dash=theme.SERIES_DASH[i % 6]),
                                 name=f"{r / 1000:g} km", hoverinfo="name"))
    fig.add_trace(go.Scatter(x=[observer.x_m], y=[observer.y_m], mode="markers+text", text=[observer.label or "Observador"],
                             textposition="top center", textfont=dict(color=theme.TEXT),
                             marker=dict(size=13, color=theme.SUN, symbol="diamond", line=dict(color="#000", width=1.5)),
                             name="Observador"))
    fig.update_yaxes(scaleanchor="x", title="y (m)")
    fig.update_xaxes(title="x (m)")
    if win is None or observer.mode == HorizonMode.SMOOTH_SPHERE:
        fig.add_annotation(text="Sin relieve: esfera lisa (sin DEM en este punto)", xref="paper", yref="paper", x=0.5, y=0.97,
                           showarrow=False, font=dict(color=theme.WARN, size=14), bgcolor=theme.PANEL)
    fig = theme.apply_theme(fig, "Mapa polar del recorte (plano estereográfico polar sur)", height=520, note=NOTE)
    _legend_inside(fig)
    return fig
