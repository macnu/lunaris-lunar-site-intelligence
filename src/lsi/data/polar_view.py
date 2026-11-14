"""Datos del mapa navegable del polo sur: vistas sombreadas del DEM polar LOLA de 80 m (±304 km), base cacheada, capas REALES y rotulado.

Sin Streamlit ni Plotly (la figura está en ``lsi.visualization.polar_map``). Tres piezas:

* **Base cacheada** (``build_base``): el DEM de 80 m (7600² px) se sombrea y se promedia por bloques a ≈ 1270 px (≈ 480 m/celda);
  se guarda en ``data/processed/polar_map/<hash>.npz`` con clave = sha256 del DEM + versión del algoritmo.
* **Vista** (``view_from_window``): para un zoom se lee SOLO la ventana pedida del DEM a 80 m y se sombrea en el momento.
* **Capas** (todas ya descargadas; si faltan, ``layer_array`` devuelve ``None`` y la UI las oculta con aviso: nunca se inventa nada):
  PSR (Mazarico 2011, ``data.psr``), temperatura Diviner (Williams 2019, ``data.thermal``) e iluminación media publicada AVGVISIB
  (``data.illum_ref``). Coordenadas del plano estereográfico polar sur en metros.
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path
from typing import Optional

import numpy as np

from lsi.astronomy.coordinates import stereo_forward
from lsi.contracts import DemLayer, DemNotFoundError, DemWindow
from lsi.data import cache, loader
from lsi.visualization.relief_map import HS_SCALE, colorscale_lut, hillshade

KIND = "polar_map"
ALGORITHM = "pm1"                   # sube si cambia el sombreado o el promediado: invalida las cachés
FAR_HALF_M = 304_000.0              # radio del DEM polar de 80 m (80°S)
SHADE_CAP_PX = 3800                 # el sombreado se calcula a ≥ 160 m/px (7600² px en float64 serían ≈ 0,5 GB por matriz)
TARGET_PX = 1300                    # tamaño objetivo de la imagen mostrada (se redondea al divisor entero más cercano)
ZOOMS = (1, 2, 4, 8, 16, 32, 64)
LAYER_SCALE = {"temp": "Inferno", "illum": "Viridis"}
SHADE_AZ, SHADE_EL, SHADE_EXAG = 315.0, 6.0, 2.0
PSR_RGB = (70.0, 140.0, 255.0)      # relleno y borde de las PSR (azul frío, distinto del ámbar y del cian de los nombres)


# ------------------------------------------------------------------------------------------------ vista
class View:
    """Rejilla de la imagen mostrada: ``z`` (m) y ``shade`` (0..1), filas de arriba (y mayor) a abajo; (x0, y0) = centro del píxel [0, 0]."""

    def __init__(self, z: np.ndarray, shade: np.ndarray, x0: float, y0: float, px: float):
        self.z, self.shade, self.x0, self.y0, self.px = z, shade, float(x0), float(y0), float(px)

    @property
    def n(self) -> tuple[int, int]:
        return self.z.shape

    @property
    def extent(self) -> tuple[float, float, float, float]:
        """(xlo, xhi, ylo, yhi) en m, bordes exteriores de la imagen."""
        ny, nx = self.z.shape
        return (self.x0 - self.px / 2, self.x0 + (nx - 0.5) * self.px, self.y0 - (ny - 0.5) * self.px, self.y0 + self.px / 2)

    def z_at(self, x_m: float, y_m: float) -> Optional[float]:
        """Elevación (m) de la celda que contiene el punto; None si cae fuera o sin dato."""
        c, r = int(round((x_m - self.x0) / self.px)), int(round((self.y0 - y_m) / self.px))
        if 0 <= r < self.z.shape[0] and 0 <= c < self.z.shape[1] and np.isfinite(self.z[r, c]):
            return float(self.z[r, c])
        return None


def _blockmean(a: np.ndarray, f: int) -> np.ndarray:
    """Promedio por bloques f×f ignorando NaN (float32, por franjas para acotar la memoria); recorta el resto del final."""
    if f <= 1:
        return np.asarray(a, dtype=np.float32)
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    out = np.empty((h // f, w // f), np.float32)
    step = max(1, 400 // f) * f
    for r0 in range(0, h, step):
        blk = np.asarray(a[r0:min(r0 + step, h), :w], dtype=np.float32)
        b = blk.reshape(blk.shape[0] // f, f, w // f, f)
        ok = np.isfinite(b)
        s = np.where(ok, b, 0.0).sum(axis=(1, 3), dtype=np.float64)
        n = ok.sum(axis=(1, 3))
        out[r0 // f:r0 // f + blk.shape[0] // f] = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    return out


def view_from_window(win: DemWindow, target_px: int = TARGET_PX) -> View:
    """Vista de un ``DemWindow`` del DEM de 80 m: sombrea a ≤ 3800 px y promedia a ≈ ``target_px`` (divisor entero)."""
    f1 = max(1, math.ceil(max(win.data.shape) / SHADE_CAP_PX))
    z1 = _blockmean(win.data, f1)
    px1 = win.pixel_size_m * f1
    sh1 = hillshade(z1, px1, SHADE_AZ, SHADE_EL, SHADE_EXAG).astype(np.float32)
    f2 = max(1, round(max(z1.shape) / target_px))
    z, sh = _blockmean(z1, f2), _blockmean(sh1, f2)
    off = (f1 * f2 - 1) / 2.0 * win.pixel_size_m
    return View(z, sh, win.x0_m + off, win.y0_m - off, win.pixel_size_m * f1 * f2)


def far_ref(raw_dir: Path):
    ref = loader.discover_far_field(Path(raw_dir))
    if ref is None:
        raise DemNotFoundError("Falta el DEM polar LOLA de 80 m (data/raw/lola80s/LDEM_80S_80MPP_ADJ.TIF). "
                               "Descárgalo con: python scripts/fetch_data.py")
    return ref


def build_base(raw_dir: Path, cache_dir: Path) -> View:
    """Vista del polo entero, cacheada en ``<cache_dir>/polar_map/<hash>.npz`` (clave = sha256 del DEM + algoritmo + tamaño).
    ``DemNotFoundError`` con el comando de descarga si falta el DEM."""
    ref = far_ref(raw_dir)
    key = cache.digest(ALGORITHM, loader.dem_sha256(ref), TARGET_PX)
    hit = cache.load_npz(cache_dir, KIND, key)
    if hit is not None:
        return View(hit["z"], hit["shade"], float(hit["geo"][0]), float(hit["geo"][1]), float(hit["geo"][2]))
    v = view_from_window(loader.read_window(ref, DemLayer.SURF))
    cache.save_npz(cache_dir, KIND, key, {"z": v.z, "shade": v.shade, "geo": np.array([v.x0, v.y0, v.px])})
    return v


def view_for(raw_dir: Path, cx: float, cy: float, half_m: float) -> View:
    """Vista de un zoom: ventana cuadrada de lado 2·half centrada en (cx, cy) (desplazada si se saldría del DEM)."""
    ref = far_ref(raw_dir)
    half = min(float(half_m), FAR_HALF_M)
    cx, cy = (float(np.clip(c, -FAR_HALF_M + half, FAR_HALF_M - half)) for c in (cx, cy))
    return view_from_window(loader.read_window(ref, DemLayer.SURF, (cx - half, cy - half, cx + half, cy + half)))


def half_for_zoom(zoom: int) -> float:
    return FAR_HALF_M / float(zoom)


# ------------------------------------------------------------------------------------------------ capas
def layer_available(layer: str) -> bool:
    """``psr`` | ``temp_mean|max|min`` | ``illum``: ¿están los ficheros descargados?"""
    from lsi.data import illum_ref, psr, thermal
    if layer == "psr":
        return psr.psr_available()
    if layer.startswith("temp"):
        return thermal.thermal_available()
    if layer == "illum":
        return illum_ref.illum_ref_available()
    raise ValueError(f"capa desconocida: {layer!r}")


def _match(a: Optional[np.ndarray], shape: tuple[int, int]) -> Optional[np.ndarray]:
    """Remuestrea (vecino más próximo) una rejilla ``a`` a ``shape`` (los productos de 240/120 m son más gruesos que un zoom)."""
    if a is None or a.shape == shape:
        return a
    r = np.minimum((np.arange(shape[0]) * a.shape[0] / shape[0]).astype(int), a.shape[0] - 1)
    c = np.minimum((np.arange(shape[1]) * a.shape[1] / shape[1]).astype(int), a.shape[1] - 1)
    return a[np.ix_(r, c)]


def layer_array(layer: str, v: View) -> Optional[np.ndarray]:
    """Capa real sobre la rejilla de ``v`` (NaN = sin dato) o None si faltan los ficheros. ``psr`` devuelve bool."""
    if not layer_available(layer):
        return None
    from lsi.data import illum_ref, psr, thermal
    ny, nx = v.n
    xlo, xhi, ylo, yhi = v.extent
    cx, cy, half = (xlo + xhi) / 2, (ylo + yhi) / 2, max(xhi - xlo, yhi - ylo) / 2
    if layer == "psr":
        w = psr.psr_mask_window("polar", cx, cy, half, max(ny, nx))
    elif layer.startswith("temp"):
        w = thermal.thermal_window("polar", cx, cy, half, max(ny, nx), layer.split("_")[1])
    else:
        w = illum_ref.illum_ref_window("polar", cx, cy, half, max(ny, nx))
    if w is None:
        return None
    a = _match(w["data"], (max(ny, nx),) * 2)
    return a[:ny, :nx]


def layer_info(layer: str) -> dict:
    """Rótulo científico OBLIGATORIO de cada capa (qué es y qué NO es) y su atribución."""
    from lsi.data import illum_ref, psr, thermal
    return {
        "psr": {"title": "Regiones permanentemente sombreadas (PSR)", "note": "PSR de 18,6 años, no sombra de un periodo",
                "attribution": psr.ATTRIBUTION},
        "temp_mean": {"title": "Temperatura media de la superficie", "note": "Williams et al. 2019, estacional", "unit": "K",
                      "attribution": thermal.ATTRIBUTION},
        "temp_max": {"title": "Temperatura máxima de la superficie", "note": "Williams et al. 2019, estacional", "unit": "K",
                     "attribution": thermal.ATTRIBUTION},
        "temp_min": {"title": "Temperatura mínima de la superficie", "note": "Williams et al. 2019, estacional", "unit": "K",
                     "attribution": thermal.ATTRIBUTION},
        "illum": {"title": "Iluminación media publicada (AVGVISIB)", "note": "superficie, 18,6 años", "unit": "fracción del disco solar",
                  "attribution": illum_ref.ATTRIBUTION},
    }[layer]


def compose_rgb(v: View, color: Optional[np.ndarray] = None, color_kind: str = "temp", psr_mask: Optional[np.ndarray] = None,
                alpha: float = 0.62) -> tuple[np.ndarray, Optional[tuple[float, float]]]:
    """(RGB uint8, (vmin, vmax) de la capa de color o None). Relieve gris + capa de color (alpha) + relleno y borde de las PSR."""
    sh = np.clip(np.nan_to_num(v.shade, nan=0.0), 0.0, 1.0)
    out = colorscale_lut(HS_SCALE)[(sh * 255).astype(np.uint8)].astype(np.float32)
    out[~np.isfinite(v.z)] = (7, 11, 20)                       # fuera del DEM: fondo del mapa
    rng = None
    if color is not None:
        fin = np.isfinite(color)
        if fin.any():
            lo, hi = (float(x) for x in np.percentile(color[fin], [1, 99]))
            hi = hi if hi > lo else lo + 1e-6
            idx = np.clip(np.nan_to_num((color - lo) / (hi - lo)) * 255, 0, 255).astype(np.uint8)
            col = colorscale_lut(LAYER_SCALE[color_kind])[idx].astype(np.float32)
            out = np.where(fin[..., None], alpha * col + (1 - alpha) * out, out)
            rng = (lo, hi)
    if psr_mask is not None and psr_mask.any():
        from scipy.ndimage import binary_erosion
        edge = psr_mask & ~binary_erosion(psr_mask, iterations=1)
        rgb = np.array(PSR_RGB, np.float32)
        out = np.where(psr_mask[..., None], 0.62 * out + 0.38 * rgb, out)
        out = np.where(edge[..., None], 0.2 * out + 0.8 * rgb, out)
    return np.clip(out, 0, 255).astype(np.uint8), rng


def jpeg_uri(rgb: np.ndarray, quality: int = 88) -> str:
    """Imagen como data URI JPEG (la figura de Plotly la lleva en el diseño: no pasa por el array de datos)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ------------------------------------------------------------------------------------------------ nombres
def label_features(df, extent_m: tuple[float, float, float, float], max_n: int = 28, min_diam_frac: float = 0.02):
    """Rasgos con nombre del gazetteer dentro de ``extent_m`` = (xlo, xhi, ylo, yhi): [(nombre, x, y, tipo, diámetro_km|None)].
    Prioridad por diámetro; descarta los que se solaparían con uno ya elegido (la caja crece con la longitud del nombre) y los
    menores que ``min_diam_frac`` del ancho de la vista (a poco zoom, solo los grandes; al acercarse caben más)."""
    if df is None or len(df) == 0:
        return []
    from lsi.data import gazetteer
    xlo, xhi, ylo, yhi = extent_m
    W, H = xhi - xlo, yhi - ylo
    d = df[(df["lat_deg"] < -79.0) & (df["feature_type"] != gazetteer.SITE_TYPE)]
    x, y = stereo_forward(d["lat_deg"].to_numpy(float), d["lon_deg_e"].to_numpy(float))
    m = (x >= xlo) & (x <= xhi) & (y >= ylo) & (y <= yhi)
    d, x, y = d[m], x[m], y[m]
    diam = d["diameter_km"].fillna(0.0).to_numpy(float)
    names = d["name"].astype(str).to_numpy()
    out = []
    for i in np.argsort(-diam, kind="stable"):
        if len(out) >= max_n:
            break
        if diam[i] * 1000.0 < min_diam_frac * W:
            continue
        bw, bh = (0.012 * len(names[i]) + 0.012) * W, 0.04 * H
        if all(abs(x[i] - o[1]) > (bw + o[5]) / 2 or abs(y[i] - o[2]) > (bh + o[6]) / 2 for o in _boxed(out, W, H)):
            out.append((str(names[i]), float(x[i]), float(y[i]), str(d["feature_type"].iloc[i]), float(diam[i]) if diam[i] > 0 else None))
    return out


def _boxed(items, W, H):
    """Los elegidos con su caja (w, h) como columnas 5 y 6 (se recalcula; son pocos)."""
    return [(n, x, y, t, dk, (0.012 * len(n) + 0.012) * W, 0.04 * H) for n, x, y, t, dk in items]
