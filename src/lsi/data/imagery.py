"""Imagen fotográfica LROC NAC como TEXTURA donde no hay ortomosaico SDEM (Site04, Shackleton rim).

Solo LECTURA de lo que descarga ``scripts/fetch_imagery.py`` en ``data/raw/imagery/``: un recorte GeoTIFF uint8 por sitio
(estereográfica polar sur de LSI, píxel de 1 m, 0 = sin dato) extraído del mosaico controlado «LROC NAC South Pole
Controlled Average Mosaic» (NAC_POLE_SOUTH_CM_AVG, LROC/ASU, PDS). Detalle y alternativas descartadas:
``docs/validation/datos-imagen-artemis.md``.

HONESTIDAD DE LA RESOLUCIÓN: el píxel nativo es de 1 m, pero es un mosaico PROMEDIO de imágenes NAC con Sol distinto: la
iluminación (sombras) que se ve es una mezcla, no la de una fecha. Sin dato en las sombras permanentes: ``coverage`` False;
nunca se inventa textura. Este módulo NO importa ``lsi.data.sdem``: el llamador decide si combina (``combine_with_sdem``).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy import ndimage as ndi

from lsi.data.loader import _check_crs

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
IMAGERY_DIR = RAW_DIR / "imagery"
NATIVE_PX_M = 1.0
DARK_U8 = 10     # por debajo, el mosaico NAC es ruido de sombra: no hay detalle (medido en Site04, docs/validation/datos-imagen-artemis.md)
SOURCE_ID = "lroc_nac_pole_south_cm_avg"
SOURCE_URL = ("https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/"
              "NAC_POLE_SOUTH_CM_AVG/")
SOURCE_PAGE = "https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG"
ATTRIBUTION = (
    "Imagen: LROC NAC, mosaico polar sur controlado (promedio), NASA/GSFC/Arizona State University (LROC). "
    "Archinal, B., Weller, L., Richie, J., Lee, E., Bennett, K., Speyerer, E., and Tyburczy, T. (2023), Controlled "
    "High-Resolution LROC NAC Polar Mosaics, LPSC 54, abstract #2333. Fuente: NASA PDS Cartography and Imaging Sciences "
    "Node / LROC RDR (https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG).")


def clip_path(site_key: str, imagery_dir: Optional[Path] = None) -> Path:
    """Ruta del recorte de un sitio ('site04' o 'Site04' → ``Site04_nac_avg_1m.tif``)."""
    return (Path(imagery_dir) if imagery_dir else IMAGERY_DIR) / f"{str(site_key).strip().capitalize()}_nac_avg_1m.tif"


def available_sites(*, imagery_dir: Optional[Path] = None) -> tuple[str, ...]:
    d = Path(imagery_dir) if imagery_dir else IMAGERY_DIR
    return tuple(sorted(p.name.split("_")[0] for p in d.glob("Site*_nac_avg_1m.tif")))


def _manifest(imagery_dir: Optional[Path]) -> dict:
    try:
        return json.loads(((Path(imagery_dir) if imagery_dir else IMAGERY_DIR) / "MANIFEST.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _resample(path: Path, xs: np.ndarray, ys: np.ndarray, px_out: float) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Muestrea el recorte en la malla (xs, ys) (centros de píxel, m): (valor float32, cobertura float32 0..1).

    Lee solo la ventana necesaria. Si se reduce la resolución (px_out > 1,5·nativo) promedia antes con una gaussiana
    normalizada por validez (σ = 0,5·factor, sin aliasing). ``cobertura`` = fracción de vecindad con dato (0 = sin dato).
    None si la ventana no toca el recorte.
    """
    with rasterio.open(path) as s:
        _check_crs(s.crs, path)
        t, px = s.transform, float(s.transform.a)
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
    good = (a > 0).astype(np.float32)           # 0 = sin dato en el mosaico NAC (nodata declarado)
    if not good.any():
        return None
    if sg:
        w = ndi.gaussian_filter(good, sg)
        a = np.where(w > 1e-6, ndi.gaussian_filter(a * good, sg) / np.maximum(w, 1e-6), 0.0).astype(np.float32)
    else:
        w = good
    cc, rr = np.meshgrid((xs - t.c) / px - 0.5 - c0, (t.f - ys) / px - 0.5 - r0)
    co = np.stack([rr, cc])
    val = ndi.map_coordinates(a, co, order=1, mode="nearest")
    cov = ndi.map_coordinates(w if sg else good, co, order=1, mode="constant", cval=0.0)
    return val.astype(np.float32), cov.astype(np.float32)


def imagery_on_grid(site_key: str, x0_m: float, y0_m: float, px_m: float, ny: int, nx: int, *,
                    imagery_dir: Optional[Path] = None, min_coverage: float = 0.999) -> Optional[dict]:
    """Imagen NAC en una malla dada (centro del píxel [0, 0] = (x0_m, y0_m); y decrece con la fila). None si no hay recorte
    del sitio o no toca la malla. ``coverage`` exige ≥ ``min_coverage`` de la vecindad con dato (sin halos en los bordes)."""
    p = clip_path(site_key, imagery_dir)
    if not p.is_file():
        return None
    xs = x0_m + px_m * np.arange(nx)
    ys = y0_m - px_m * np.arange(ny)
    r = _resample(p, xs, ys, px_m)
    if r is None:
        return None
    val, cov = r
    ok = cov >= min_coverage
    if not ok.any():
        return None
    img = np.zeros(val.shape, np.uint8)
    img[ok] = np.clip(np.rint(val[ok]), 1, 255).astype(np.uint8)     # 0 reservado a «sin dato»
    m = _manifest(imagery_dir)
    px_eff = max(float(px_m), NATIVE_PX_M)
    notes = [f"Mosaico NAC promedio de {NATIVE_PX_M:g} m/píxel; salida a {px_eff:g} m/píxel."
             " Iluminación promediada de varias fechas: no es la luz de una fecha concreta."]
    if not ok.all():
        notes.append(f"{100 * (1 - ok.mean()):.1f} % del recorte sin imagen (fuera del recorte descargado o sin dato NAC, "
                     "p. ej. sombra permanente); no se rellena.")
    dark = float((img[ok] < DARK_U8).mean())
    if dark > 0.05:
        notes.append(f"{100 * dark:.0f} % de los píxeles con imagen son casi negros (< {DARK_U8}/255): sombra permanente o sin "
                     "iluminación, sin detalle fotográfico aunque el mosaico tenga valor.")
    return dict(site_key=str(site_key), image=img, coverage=ok, px_m=px_eff, x0_m=float(x0_m), y0_m=float(y0_m),
                source=SOURCE_ID, source_url=SOURCE_URL, native_px_m=NATIVE_PX_M, attribution=ATTRIBUTION,
                fetched=m.get("fetched"), notes=tuple(notes))


def imagery_window(site_key: str, center_x_m: float, center_y_m: float, half_size_m: float, max_px: int, *,
                   imagery_dir: Optional[Path] = None) -> Optional[dict]:
    """Imagen NAC de la ventana cuadrada de lado 2·half_size_m centrada en (center_x_m, center_y_m), alineada con ese recorte.

    Malla: n = min(max_px, ⌈2·half/1 m⌉) píxeles por lado, px = 2·half/n; centros en cx − half + px·(i + ½) (fila 0 = norte),
    la misma convención que ``sdem.terrain_texture_pack`` cuando se pide con max_px menor que 2·half/5 m.
    Claves (arrays (ny, nx)): image uint8 (0 = sin dato), coverage bool (True = hay imagen real), px_m (EFECTIVO, ≥ 1 m),
    x0_m, y0_m (centro del píxel [0, 0]), native_px_m, source, source_url, attribution, fetched, notes.
    None si el sitio no tiene recorte descargado o la ventana no lo toca (el llamador cae a hillshade): sin textura inventada.
    """
    if half_size_m <= 0 or max_px < 2:
        raise ValueError("half_size_m debe ser > 0 y max_px >= 2")
    n = int(min(max_px, math.ceil(2 * half_size_m / NATIVE_PX_M)))
    px = 2 * half_size_m / n
    return imagery_on_grid(site_key, center_x_m - half_size_m + px / 2, center_y_m + half_size_m - px / 2, px, n, n,
                           imagery_dir=imagery_dir)


def combine_with_sdem(site_key: str, sdem_pack: Optional[dict], *, imagery_dir: Optional[Path] = None) -> Optional[dict]:
    """Textura combinada sobre la malla de un paquete SDEM (``terrain_texture_pack``; se pasa el dict, aquí NO se importa).

    Donde el SDEM tiene fotografía (``texture_valid``) manda el SDEM (5 m); donde no, y hay NAC, se rellena con la imagen
    NAC igualando su tono al del SDEM en la zona común (cuantiles 2-98 %, solo si hay ≥ 1000 px comunes). Devuelve
    ``texture`` uint8, ``texture_valid`` bool, ``texture_source`` uint8 (0 nada, 1 SDEM, 2 NAC), ``px_m``/``x0_m``/``y0_m``
    del SDEM y ``native_px_m`` por fuente. None si no hay paquete SDEM o no hay NAC (queda el SDEM tal cual).
    """
    if not sdem_pack:
        return None
    ny, nx = sdem_pack["ortho"].shape
    im = imagery_on_grid(site_key, sdem_pack["x0_m"], sdem_pack["y0_m"], sdem_pack["px_m"], ny, nx, imagery_dir=imagery_dir)
    if im is None:
        return None
    sv, nv = sdem_pack["texture_valid"], im["coverage"]
    tex = np.where(sv, sdem_pack["ortho"], 0).astype(np.uint8)
    nac = im["image"].astype(np.float32)
    both = sv & nv
    notes = list(im["notes"])
    if both.sum() >= 1000:
        q = np.array([2, 25, 50, 75, 98])
        src_q, dst_q = np.percentile(nac[both], q), np.percentile(sdem_pack["ortho"][both].astype(np.float32), q)
        if np.all(np.diff(src_q) > 0):
            nac = np.interp(nac, src_q, dst_q)
            notes.append("Tono NAC igualado al del SDEM por cuantiles en la zona común.")
    else:
        notes.append("Sin zona común suficiente: tono NAC sin igualar al del SDEM.")
    fill = nv & ~sv
    tex[fill] = np.clip(np.rint(nac[fill]), 1, 255).astype(np.uint8)
    return dict(texture=tex, texture_valid=sv | nv, texture_source=np.where(sv, 1, np.where(nv, 2, 0)).astype(np.uint8),
                px_m=sdem_pack["px_m"], x0_m=sdem_pack["x0_m"], y0_m=sdem_pack["y0_m"],
                native_px_m={"sdem": 5.0, "nac": NATIVE_PX_M}, attribution=(sdem_pack.get("attribution", ""), im["attribution"]),
                notes=tuple(notes))
