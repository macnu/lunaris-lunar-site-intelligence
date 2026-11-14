"""SDEM de 5 m (shape-from-shading) y ortomosaico LROC NAC de las regiones Artemis III (NASA PGDA, Zenodo 17954508).

Solo LECTURA de lo que descarga ``scripts/fetch_sdem.py`` en ``data/raw/sdem/<región>/``. No toca el motor científico:
el relieve LOLA sigue siendo el que usan horizonte, pendiente y puntuación; esto alimenta la visualización 3D.

Cobertura (verificada con los datos, ``docs/validation/datos-sdem.md``): Site23 ⇒ Malapert Massif (A311) y
Site11 ⇒ de Gerlache Rim (A309), ambos con la MISMA malla de 5 m y la misma extensión que el recorte LOLA.
Site04 (Shackleton rim) NO está entre las 13 regiones: ``None``. Site07 (Peak Near Shackleton, A308) no es de este proyecto.

Convenciones: píxel centrado; ``y0_m`` es la y de la FILA 0 (norte arriba, y decrece hacia abajo), como ``DemWindow``.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage as ndi

from lsi.data.loader import _check_crs

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
SDEM_DIR = RAW_DIR / "sdem"
NATIVE_PX_M = 5.0

# clave de sitio (sites.json: 'site23' o 'Site23') -> (carpeta de región, prefijo de capas)
_REGIONS = {"site23": ("Malapert_Massif", "A311"), "site11": ("deGerlache_Rim", "A309")}
_ALL_REGIONS = {"Malapert_Massif": "A311", "deGerlache_Rim": "A309", "Peak_Near_Shackleton": "A308"}

# Ortomosaico GLDOMOS: float32, factor de reflectancia relativo (rango real 0,0002-0,18; p99,9 ≈ 0,061-0,067).
# Normalización FIJA (no por recorte, para que los teselas casen): u8 = 255·clip(x/ORTHO_HI, 0, 1)^(1/ORTHO_GAMMA).
ORTHO_HI = 0.065
ORTHO_GAMMA = 2.2

ATTRIBUTION = (
    "Bertone, S., McKenna, T. E., Barker, M. K., Mazarico, E., Beyer, R. A., and Petro, N., Enhanced Topography Models "
    "for selected Lunar South Pole regions with Shape-from-Shading, The Planetary Science Journal, doi: 10.3847/PSJ/ae5b70. "
    "Datos: Bertone, S., Barker, M., Mazarico, E., McKenna, T., and Petro, N., 2025, Zenodo, doi: 10.5281/zenodo.17954508 "
    "(CC-BY-4.0). NASA PGDA, https://pgda.gsfc.nasa.gov/products/104")


def sdem_region_for(site_key: str) -> Optional[str]:
    """Carpeta de región SDEM del sitio ('Site23' → 'Malapert_Massif', 'Site11' → 'deGerlache_Rim'); None si no hay.
    Site04 (Shackleton rim) no está en las 13 regiones Artemis III. No comprueba que los datos estén en disco."""
    r = _REGIONS.get(str(site_key).strip().lower())
    return None if r is None else r[0]


def _path(region: str, layer: str, sdem_dir: Path) -> Path:
    return sdem_dir / region / f"{_ALL_REGIONS[region]}_{layer}.tif"


_LAYERS = ("GLDELEV_005", "GLDOMOS_005", "GLDMASK_005")


def available_regions(*, sdem_dir: Optional[Path] = None) -> tuple[str, ...]:
    """Regiones con elevación, ortomosaico y máscara presentes en disco (incluye Peak_Near_Shackleton si se descargó)."""
    d = Path(sdem_dir) if sdem_dir else SDEM_DIR
    return tuple(r for r in _ALL_REGIONS if all(_path(r, l, d).is_file() for l in _LAYERS))


def _resample(path: Path, xs: np.ndarray, ys: np.ndarray, order: int, px_out: float) -> Optional[np.ndarray]:
    """Muestrea la capa en la malla (xs, ys) (centros de píxel, m): float32, NaN donde el píxel o algún vecino no tiene dato.

    Lee solo la ventana necesaria. Si se reduce la resolución (px_out > 1,5·nativo) filtra antes con una gaussiana
    normalizada por validez (σ = 0,5·factor) para no aliasar. None si la ventana no toca el raster.
    """
    with rasterio.open(path) as s:
        _check_crs(s.crs, path)
        t, px = s.transform, float(s.transform.a)
        if t.b != 0 or t.d != 0 or t.e >= 0 or abs(t.a) != abs(t.e):
            raise ValueError(f"{path}: geotransform no es norte-arriba con píxel cuadrado")
        f = max(px_out / px, 1.0)
        sg = 0.5 * f if f > 1.5 else 0.0
        mg = int(3 * sg) + 3
        c0 = max(math.floor((xs.min() - t.c) / px - 0.5) - mg, 0)
        c1 = min(math.ceil((xs.max() - t.c) / px - 0.5) + mg + 1, s.width)
        r0 = max(math.floor((t.f - ys.max()) / px - 0.5) - mg, 0)
        r1 = min(math.ceil((t.f - ys.min()) / px - 0.5) + mg + 1, s.height)
        if c1 <= c0 or r1 <= r0:
            return None
        a = s.read(1, window=Window(c0, r0, c1 - c0, r1 - r0)).astype(np.float32)
        nd = s.nodata
    good = np.isfinite(a) & (a > -1e30)             # nodata de float32 (≈ -3,4e38), también el de GLDOMOS
    if nd is not None and np.isfinite(nd):
        good &= a != np.float32(nd)
    if not good.any():
        return None
    lo, hi = float(a[good].min()), float(a[good].max())
    gf = good.astype(np.float32)
    a = np.where(good, a, 0.0).astype(np.float32)
    if sg:
        w = ndi.gaussian_filter(gf, sg)
        a = np.where(w > 1e-6, ndi.gaussian_filter(a, sg) / np.maximum(w, 1e-6), 0.0).astype(np.float32)
    col = (xs - t.c) / px - 0.5 - c0
    row = (t.f - ys) / px - 0.5 - r0
    cc, rr = np.meshgrid(col, row)
    coords = np.stack([rr, cc])
    val = ndi.map_coordinates(a, coords, order=order, mode="nearest")
    ok = ndi.map_coordinates(gf, coords, order=min(order, 1), mode="constant", cval=0.0) >= 0.999
    val = np.clip(val, lo, hi)                       # el spline cúbico rebasa en los bordes de sombra
    return np.where(ok, val, np.nan).astype(np.float32)


def _grid(cx: float, cy: float, half: float, max_px: int, ref: Path) -> tuple[np.ndarray, np.ndarray, float]:
    """Malla de salida. Si cabe a 5 m (≤ max_px píxeles por lado) usa EXACTAMENTE la retícula nativa del SDEM (la misma
    que la del DEM LOLA de 5 m: coincide píxel a píxel con un recorte LOLA del mismo centro); si no, px = 2·half/max_px."""
    if half <= 0 or max_px < 2:
        raise ValueError("half_size_m debe ser > 0 y max_px >= 2")
    if 2 * half / NATIVE_PX_M <= max_px:
        with rasterio.open(ref) as s:
            t = s.transform
        j0, j1 = math.floor((cx - half - t.c) / NATIVE_PX_M), math.ceil((cx + half - t.c) / NATIVE_PX_M)
        i0, i1 = math.floor((t.f - (cy + half)) / NATIVE_PX_M), math.ceil((t.f - (cy - half)) / NATIVE_PX_M)
        xs = t.c + NATIVE_PX_M * (np.arange(j0, j1) + 0.5)
        ys = t.f - NATIVE_PX_M * (np.arange(i0, i1) + 0.5)
        return xs, ys, NATIVE_PX_M
    px = 2 * half / max_px
    return cx - half + px * (np.arange(max_px) + 0.5), cy + half - px * (np.arange(max_px) + 0.5), px


def terrain_texture_pack(site_key: str, center_x_m: float, center_y_m: float, half_size_m: float, max_px: int,
                         *, sdem_dir: Optional[Path] = None, raw_dir: Optional[Path] = None) -> Optional[dict]:
    """Relieve SDEM y ortomosaico alineados en UNA malla (centrada en el punto pedido, lado ≈ 2·half_size_m).

    None si el sitio no tiene SDEM, faltan los ficheros o el recorte no toca el SDEM (el llamador cae al relieve LOLA).
    Claves (arrays de forma (ny, nx), fila 0 = norte):
      heights        float32 m (MOON_ME, R=1737,4 km): SDEM; donde el SDEM no tiene dato, LDEM LOLA 5 m; NaN si tampoco.
      height_source  uint8: 1 = SDEM, 2 = relleno LDEM, 0 = sin dato.
      valid          bool: altura procedente del SDEM (cobertura del SDEM).
      ortho          uint8: ortomosaico normalizado, ver ORTHO_HI / ORTHO_GAMMA. Donde ``texture_valid`` es False vale 0
                     y NO debe usarse como foto: nunca se inventa textura.
      texture_valid  bool: hay ortomosaico válido Y al menos una imagen NAC iluminada contribuyó (GLDMASK > 0).
                     Las zonas en sombra permanente salen False (sin fotografía).
      px_m, x0_m, y0_m  tamaño de píxel y coordenadas (x, y) del CENTRO del píxel [0, 0] (y decrece con la fila).
      region, site_key, ortho_norm, attribution, notes
    Remuestreo: altura bilineal; ortomosaico bicúbico (spline cúbico, recortado al rango observado; su retícula está
    desplazada medio píxel respecto al SDEM, por eso siempre se interpola); máscara GLDMASK (15 m) por vecino más cercano.
    Si se reduce la resolución se filtra antes con una gaussiana (σ = 0,5·factor) normalizada por validez.
    """
    region = sdem_region_for(site_key)
    sd = Path(sdem_dir) if sdem_dir else SDEM_DIR
    if region is None or region not in available_regions(sdem_dir=sd):
        return None
    elev, omos, mask = (_path(region, l, sd) for l in _LAYERS)
    xs, ys, px = _grid(float(center_x_m), float(center_y_m), float(half_size_m), int(max_px), elev)
    z_s = _resample(elev, xs, ys, 1, px)
    if z_s is None:
        return None
    notes = [f"SDEM {region} (shape-from-shading, 5 m, Bertone et al.); relieve bilineal, ortomosaico bicúbico."]
    site = str(site_key).strip().capitalize()
    lola = next(iter(sorted((Path(raw_dir) if raw_dir else RAW_DIR).glob(f"*/{site}_final_adj_5mpp_surf.tif"))), None)
    z_l = _resample(lola, xs, ys, 1, px) if lola else None
    if z_l is None:
        z_l = np.full_like(z_s, np.nan)
        notes.append("Sin LDEM LOLA para rellenar huecos del SDEM.")
    fin_s, fin_l = np.isfinite(z_s), np.isfinite(z_l)
    heights = np.where(fin_s, z_s, z_l).astype(np.float32)
    source = np.where(fin_s, 1, np.where(fin_l, 2, 0)).astype(np.uint8)
    o = _resample(omos, xs, ys, 3, px)
    n = _resample(mask, xs, ys, 0, px)
    tv = np.zeros(z_s.shape, bool) if o is None else np.isfinite(o)
    if n is None:
        tv[:] = False
    else:
        tv &= np.nan_to_num(n, nan=0.0) > 0
    ortho = np.zeros(z_s.shape, np.uint8)
    if o is not None:
        ortho[tv] = np.round(255 * np.clip(o[tv] / ORTHO_HI, 0, 1) ** (1 / ORTHO_GAMMA)).astype(np.uint8)
    if not tv.all():
        notes.append(f"{100 * (1 - tv.mean()):.1f} % del recorte sin textura válida (fuera del SDEM o sin imagen NAC "
                     "iluminada); no se rellena.")
    if (source == 2).any():
        notes.append(f"{100 * (source == 2).mean():.1f} % de las alturas viene del LDEM LOLA (el SDEM no cubre ese píxel).")
    if (source == 0).any():
        notes.append(f"{100 * (source == 0).mean():.1f} % del recorte sin altura (fuera de SDEM y LDEM): NaN, no se inventa.")
    return dict(site_key=str(site_key), region=region, heights=heights, height_source=source, valid=fin_s,
                ortho=ortho, texture_valid=tv, px_m=float(px), x0_m=float(xs[0]), y0_m=float(ys[0]),
                ortho_norm=f"u8 = 255·clip(x/{ORTHO_HI}, 0, 1)^(1/{ORTHO_GAMMA}); x = GLDOMOS (factor de reflectancia relativo)",
                attribution=ATTRIBUTION, notes=tuple(notes))
