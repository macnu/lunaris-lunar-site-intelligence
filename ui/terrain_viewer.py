"""Visor 3D del terreno lunar en three.js, embebido en Streamlit (``st.components.v1.html``): terreno real (≤ 512 × 512 vértices),
foto LROC donde la hay, sombras de ``lsi.terrain.shadows``, Sol y Tierra en su acimut/elevación reales, vista del observador.

Dos capas:

* ``build_scene`` / ``viewer_html``: PURAS (numpy + PIL, sin streamlit; testeables). Arman un único JSON y un HTML AUTOCONTENIDO:
  three.js r147 y OrbitControls vendorizados (``ui/static/vendor``, ver su MANIFEST.json), CSS y JS en línea: cero peticiones de red.
* ``render_terrain_viewer``: pinta ese HTML con Streamlit.

Además (``lsi.data.viewer_context``): un TERRENO DE CONTEXTO (DEM LOLA de 80 m, ±20-25 km, ≤ 160 × 160 vértices, sin foto, con sus propias
sombras y degradado a negro en el borde) y un PARCHE FINO de ≈ 700 m alrededor del observador (alturas nativas de 5 m interpoladas a 2,5 m).
El microrrelieve de ese parche es solo sombreado procedural en el shader, rotulado «no es dato».

Datos que viajan (todo en un JSON dentro de ``<script type="application/json">``, con ``<`` escapado):
alturas uint16 cuantizadas entre mín y máx (paso < 0,1 m en recortes de 5 km), UN PNG RGB de textura (R = foto con los huecos rellenos
por el vecino más cercano para que no haya halos, G = máscara de foto 0/255, B = iluminación calculada 0 sombra … 255 Sol), nombres
del gazetteer y el horizonte calculado. Sin foto (G = 0) el visor NO inventa textura.
"""
from __future__ import annotations

import base64
import io
import json
import math
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from lsi.data import viewer_context as VC

STATIC = Path(__file__).resolve().parent / "static"
MAX_SIDE = 512                  # vértices por lado: 262 144 vértices, ≈ 520 000 triángulos; WebGL medio los mueve (hay reintento con menos)
MAX_PAYLOAD_BYTES = 4_000_000   # cota del JSON (≈ 1 MB típico); ``build_scene`` falla si se supera
R_MOON_M = 1737400.0
_NODATA = 65535


def _blocks(a: np.ndarray, f: int, how: str = "mean") -> np.ndarray:
    """Reduce por bloques f × f (recorta el resto). ``mean`` ignora NaN; ``all`` = verdadero si todo el bloque lo es."""
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    b = a[:h, :w].reshape(h // f, f, w // f, f)
    if how == "all":
        return b.all(axis=(1, 3))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # bloques todo-NaN → NaN
        return np.nanmean(b.astype(float), axis=(1, 3))


def _png(a: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(a)).save(buf, format="PNG", compress_level=6)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _fill_nearest(img: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Rellena los píxeles sin foto con el valor del válido más cercano (solo para que el filtrado bilineal no deje halos
    oscuros: la máscara G sigue diciendo que ahí NO hay foto)."""
    if valid.all() or not valid.any():
        return img
    idx = ndi.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def _interp_periodic(az: np.ndarray, vals: np.ndarray, step: float = 1.0) -> tuple[list[float], list[float]]:
    """Horizonte a rejilla regular cada ``step`` ° (periódico), redondeado: ≤ 360 valores."""
    order = np.argsort(az)
    a, v = np.asarray(az, float)[order], np.asarray(vals, float)[order]
    g = np.arange(0.0, 360.0, step)
    return [round(float(x), 2) for x in g], [round(float(x), 2) for x in np.interp(g, np.r_[a, a[0] + 360.0], np.r_[v, v[0]], period=None)]


def _fmt(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


PSR_TEXT = "Sin foto: región permanentemente sombreada; la cámara LROC NAC no puede verla; ShadowCam no está integrada."


def photo_notice(source: str, native_px_m: float, shown_px_m: float, nophoto_pct: float, psr_pct: Optional[float] = None) -> tuple[str, str]:
    """(aviso corto siempre visible, detalle de límites) de la foto: fuente y resolución REAL. ``source``: 'sdem' | 'nac' | 'mixed' | 'none'.
    ``psr_pct``: % de las celdas sin foto que caen en una región permanentemente sombreada (``data.psr``); ≥ 50 % lo explica."""
    in_psr = psr_pct is not None and psr_pct >= 50.0 and nophoto_pct >= 3.0
    if source == "none":
        return (("Sin foto en este recorte: relieve sombreado gris (no se inventa textura). " + (PSR_TEXT + " " if in_psr else "") +
                 "La luz, las sombras y el relieve sí son los calculados para este instante."),
                "No hay ortomosaico LROC válido en esta zona (sombra permanente o fuera de la cobertura).")
    shown = f"{_fmt(shown_px_m, 0)} m/px en pantalla"
    short = (f"Foto real de la Luna (cámara LROC de la NASA), ≈{_fmt(native_px_m, 0)} m/px de origen ({shown}); mezcla de varias pasadas: no es la luz de esta fecha."
             + (f" {_fmt(nophoto_pct, 0)} % del recorte sin foto." if nophoto_pct >= 1 else "")
             + (" " + PSR_TEXT if in_psr else ""))
    det = ["La foto es un promedio de pasadas con Sol distinto: sus sombras no son las de esta fecha (las del visor sí).",
           "Zonas sin foto: gris con granulosidad, sin textura inventada."]
    if in_psr:
        det.append(f"El {_fmt(psr_pct, 0)} % de la zona sin foto está dentro de una PSR de Mazarico et al. 2011 (LROC/ASU).")
    if source in ("sdem", "mixed"):
        det.append("Foto del modelo de relieve de 5 m (ortomosaico SDEM, Bertone et al. 2025): su retícula está desplazada ≈ 2,5 m respecto al relieve.")
    if source in ("nac", "mixed"):
        det.append("Mosaico LROC NAC de 1 m/px: puede estar corrido hasta ≈ 15 m respecto al relieve.")
    return short, " ".join(det)


def describe_scene(label: str, ext_km: float, z_min: float, z_max: float, sun: dict, earth: dict, hz_sun: float, hz_earth: float,
                   lit_pct: float, when_utc: str, photo_short: str, n_names: int, has_ctx: bool = False, has_patch: bool = False) -> str:
    """Descripción textual de la escena (modo lectura y lector de pantalla)."""
    def state(el, hz):
        return "bajo el horizonte local" if el < 0 else (f"tapado por el horizonte calculado, que ahí está a {_fmt(hz, 1)}°" if el <= hz else "visible sobre el horizonte")
    return (f"Visor 3D del terreno lunar real de {label}: recorte de {_fmt(ext_km, 1)} km de lado con alturas de {_fmt(z_min, 0)} a {_fmt(z_max, 0)} m. "
            f"Instante: {when_utc} UTC. El Sol está a {_fmt(sun['el_deg'], 1)}° de elevación y {_fmt(sun['az_deg'], 0)}° de acimut ({state(sun['el_deg'], hz_sun)}); "
            f"la Tierra, a {_fmt(earth['el_deg'], 1)}° y {_fmt(earth['az_deg'], 0)}° ({state(earth['el_deg'], hz_earth)}). "
            f"Un {_fmt(lit_pct, 0)} % del recorte recibe luz directa; el resto está en sombra calculada del relieve. "
            f"Cielo negro con estrellas. Un marcador luminoso con haz vertical señala al observador"
            + (f" y {n_names} nombres de rasgos del gazetteer flotan sobre sus posiciones" if n_names else "") + ". "
            + ("Alrededor del recorte continúa el terreno lejano (modelo LOLA de 80 m, sin foto, con las mismas sombras y un degradado a negro en el borde). " if has_ctx else "")
            + ("Junto al observador hay un parche de alta resolución (5 m nativos interpolados a 2,5 m) con un microrrelieve procedural que es solo sombreado y no es dato. " if has_patch else "") +
            f"Vistas: cenital, oblicua, orbital amplia y del observador (mirando al acimut elegido). {photo_short} "
            "Controles: arrastrar para orbitar, rueda para acercar, botón derecho o Mayús para desplazar, doble clic para reiniciar; "
            "en la vista del observador, flechas izquierda y derecha giran la mirada.")


def build_scene(*, heights: np.ndarray, x0_m: float, y0_m: float, px_m: float, illum: np.ndarray,
                photo: Optional[np.ndarray], photo_valid: Optional[np.ndarray], photo_source: str, photo_native_px_m: float,
                obs: dict, sun: dict, earth: dict, horizon_az: Sequence[float], horizon_el: Sequence[float],
                names: Sequence[tuple], when_utc: str, lit_pct: float, view_az: Optional[float] = None, exag0: float = 1.5,
                context: Optional[dict] = None, patch: Optional[dict] = None, psr_pct: Optional[float] = None) -> dict:
    """Escena serializable del visor (determinista: mismas entradas ⇒ mismo JSON).

    ``heights`` (ny, nx) m, fila 0 = norte, NaN = sin dato; (``x0_m``, ``y0_m``) centro del píxel [0, 0], ``px_m``.
    ``illum`` fracción iluminada [0, 1] de la misma malla (``shadows.illumination``; NaN = sin dato → se pinta iluminado).
    ``photo`` uint8 y ``photo_valid`` bool de la misma malla (None = sin foto). ``obs``: x, y (plano), lat, lon, h (altura del
    observador), label, north_deg (azimut de rejilla del norte local = atan2(x, y)). ``sun``/``earth``: az_deg, el_deg, radius_deg (+ para el
    Sol grid_az_deg y el_c_deg: dirección en el CENTRO del recorte, la de las sombras). ``names``: (nombre, x, y, tipo, diámetro_km).
    ``context``/``patch``: salidas de ``viewer_context.context_terrain``/``fine_patch`` (opcionales); ``psr_pct``: ver ``photo_notice``.
    """
    z = np.asarray(heights, float)
    ny, nx = z.shape
    ph = None if photo is None else np.asarray(photo, np.uint8)
    pv = np.zeros(z.shape, bool) if photo_valid is None else np.asarray(photo_valid, bool).copy()
    il = np.nan_to_num(np.asarray(illum, float), nan=1.0)
    if max(ny, nx) > MAX_SIDE:                                  # submuestreo por bloques (promedio): conserva el recorte entero, pierde detalle fino
        f = math.ceil(max(ny, nx) / MAX_SIDE)
        z, il = _blocks(z, f), _blocks(il, f)
        if ph is not None:
            pvf = pv.astype(float)
            ph = np.rint(np.nan_to_num(_blocks(np.where(pv, ph, np.nan), f))).astype(np.uint8)
            pv = _blocks(pvf, f) >= 0.5
        else:
            pv = _blocks(pv, f, "all")
        off = (f - 1) / 2.0 * px_m
        x0_m, y0_m, px_m = x0_m + off, y0_m - off, px_m * f
        ny, nx = z.shape
    ok = np.isfinite(z)
    zmin, zmax = (float(np.nanmin(z)), float(np.nanmax(z))) if ok.any() else (0.0, 1.0)
    span = max(zmax - zmin, 1e-6)
    q = np.full(z.shape, _NODATA, np.uint16)
    q[ok] = np.rint((z[ok] - zmin) / span * 65534.0).astype(np.uint16)
    pv &= ok
    photo_r = _fill_nearest(ph if ph is not None else np.zeros(z.shape, np.uint8), pv)
    tex = np.stack([photo_r, np.where(pv, 255, 0).astype(np.uint8), np.rint(np.clip(il, 0, 1) * 255).astype(np.uint8)], axis=-1)
    nophoto = ok & ~pv
    nophoto_pct = 100.0 * float(nophoto.sum()) / max(int(ok.sum()), 1)
    nxz = None
    if 3.0 <= nophoto_pct <= 97.0:                              # rótulo «sin foto» en el centroide de la zona sin foto (coords de escena respecto al observador)
        r, c = (float(v) for v in ndi.center_of_mass(nophoto))
        nxz = [round(x0_m + c * px_m - obs["x"], 1), round(obs["y"] - (y0_m - r * px_m), 1)]
    shown = max(px_m, photo_native_px_m)
    src = photo_source if pv.any() else "none"
    short, det = photo_notice(src, photo_native_px_m, shown, nophoto_pct, psr_pct)
    haz, hel = _interp_periodic(np.asarray(horizon_az), np.asarray(horizon_el)) if len(horizon_az) else ([], [])
    hzs = float(np.interp(sun["az_deg"] % 360, haz, hel, period=360)) if haz else -90.0
    hze = float(np.interp(earth["az_deg"] % 360, haz, hel, period=360)) if haz else -90.0
    label = obs["label"]
    scene = {
        "v": 1, "nx": int(nx), "ny": int(ny), "px_m": round(float(px_m), 4), "x0_m": round(float(x0_m), 3), "y0_m": round(float(y0_m), 3),
        "R_m": R_MOON_M,
        "z": {"min": round(zmin, 3), "max": round(zmax, 3), "b64": base64.b64encode(q.astype("<u2").tobytes()).decode("ascii")},
        "tex_png": _png(tex),
        "photo": {"source": src, "native_px_m": float(photo_native_px_m), "shown_px_m": round(float(shown), 2), "nophoto_pct": round(nophoto_pct, 1),
                  "notice": short, "detail": det, "nophoto_xz": nxz,
                  "psr_pct": None if psr_pct is None else round(float(psr_pct), 1), "photo_pct": round(100.0 - nophoto_pct, 1)},
        "obs": {"x": round(float(obs["x"]), 2), "y": round(float(obs["y"]), 2), "z": round(float(obs.get("z") or zmin), 2), "h": float(obs["h"]),
                "label": label, "pos_text": f"{_fmt(obs['lat'], 3)}°, {_fmt(obs['lon'], 3)}°E"},
        "north_deg": round(float(obs["north_deg"]), 4),
        "sun": {k: round(float(sun[k]), 4) for k in ("az_deg", "el_deg", "grid_az_deg", "el_c_deg", "radius_deg")},
        "earth": {k: round(float(earth[k]), 4) for k in ("az_deg", "el_deg", "radius_deg")},
        "horizon": {"az": haz, "el": hel},
        "names": [[str(n[0]), round(float(n[1]), 1), round(float(n[2]), 1), str(n[3]), (None if n[4] is None else round(float(n[4]), 2))] for n in names],
        "when_utc": when_utc, "lit_pct": round(float(lit_pct), 1),
        "view_az": round(float(sun["az_deg"] if view_az is None else view_az), 1), "exag0": float(exag0),
    }
    scene["description"] = describe_scene(label, max(nx, ny) * px_m / 1000.0, zmin, zmax, sun, earth, hzs, hze, lit_pct, when_utc, short, len(names),
                                          context is not None, patch is not None)
    n = len(json.dumps(scene, separators=(",", ":")))
    if n > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload del visor demasiado grande: {n} bytes (máx. {MAX_PAYLOAD_BYTES})")
    extra = 0
    if context is not None:
        scene["ctx"] = VC.context_payload(context)
    if patch is not None:
        scene["patch"] = VC.patch_payload(patch)
    if context is not None or patch is not None:
        extra = len(json.dumps({k: scene[k] for k in ("ctx", "patch") if k in scene}, separators=(",", ":")))
        if extra > VC.MAX_EXTRA_BYTES:
            raise ValueError(f"payload del terreno lejano y del parche demasiado grande: {extra} bytes (máx. {VC.MAX_EXTRA_BYTES})")
    scene["_bytes"], scene["_bytes_crop"], scene["_bytes_extra"] = n + extra, n, extra
    return scene


def _json_for_html(obj: dict) -> str:
    """JSON seguro dentro de ``<script type="application/json">``: ``<``, ``>``, ``&`` y los separadores U+2028/9 escapados."""
    s = json.dumps({k: v for k, v in obj.items() if not k.startswith("_")}, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


@lru_cache(maxsize=1)
def _assets() -> tuple[str, str, str, str, str]:
    r = lambda p: (STATIC / p).read_text(encoding="utf-8")   # noqa: E731
    three, orbit = r("vendor/three.min.js"), r("vendor/OrbitControls.js")
    # un literal «</script» dentro de un <script> en línea cerraría la etiqueta; las librerías no lo traen, pero se blinda
    return r("terrain_viewer.css"), three.replace("</script", "<\\/script"), orbit.replace("</script", "<\\/script"), r("terrain_viewer.js"), ""


_BODY = """<div id="v" role="region" aria-label="Visor 3D del terreno lunar">
<div id="stage">
 <canvas id="gl" tabindex="0" role="img" aria-label="Escena 3D del terreno lunar; arrastra para orbitar" aria-describedby="sr-desc"></canvas>
 <div id="labels" aria-hidden="true"></div>
 <div id="p-layers" class="panel"><details open><summary>Capas y vistas</summary>
  <h4>Capas</h4>
  <label><input type="checkbox" id="l-relief"> Relieve</label>
  <label><input type="checkbox" id="l-photo"> Foto</label>
  <label><input type="checkbox" id="l-shadow"> Sombras</label>
  <label><input type="checkbox" id="l-slope"> Pendiente</label>
  <label><input type="checkbox" id="l-names"> Nombres</label>
  <label><input type="checkbox" id="l-stars"> Estrellas</label>
  <label><input type="checkbox" id="l-ctx"> Terreno lejano</label>
  <label title="Sombreado procedural muy sutil sobre el suelo cercano (sin geometría): NO es dato del terreno."><input type="checkbox" id="l-micro"> Microrrelieve</label>
  <label><input type="checkbox" id="l-horizon"> Horizonte lejano</label>
  <label title="La Tierra mide ≈ 1,9° en el cielo: se ve muy pequeña. Esto la agranda 7 veces."><input type="checkbox" id="l-big"> Agrandar la Tierra</label>
  <h4>Vista</h4>
  <div class="btnrow"><button id="m-top" aria-pressed="false">Cenital</button><button id="m-oblique" aria-pressed="false">Oblicua</button><button id="m-wide" aria-pressed="false" title="Cámara lejana: recorte y terreno lejano">Orbital amplia</button><button id="m-observer" aria-pressed="false">Observador</button></div>
  <div id="obs-ctl" hidden><h4>Mirar al acimut</h4>
   <input type="range" id="az" min="0" max="360" step="1" aria-label="Acimut de la mirada del observador, grados desde el norte hacia el este"><div class="small" id="az-val"></div>
   <div class="btnrow"><button id="az-sun">Al Sol</button><button id="az-earth">A la Tierra</button></div></div>
  <div id="exag-ctl"><h4>Exageración vertical</h4>
   <input type="range" id="exag" min="1" max="8" step="0.5" aria-label="Exageración vertical del relieve"><div class="small" id="exag-val"></div></div>
  <div class="btnrow" style="margin-top:8px"><button id="reset" title="Reiniciar la vista (también doble clic)">Reiniciar</button><button id="read" aria-pressed="false">Leer escena</button></div>
  <div class="small legend" id="legend"></div>
  <div class="small" style="margin-top:6px" id="mesh-info"></div><div class="small" id="perf-info"></div>
 </details></div>
 <div id="p-info" class="panel" aria-label="Detalles del punto">
  <h3 id="i-name"></h3><div class="small" id="i-pos"></div><div class="small" id="i-when"></div>
  <div class="row"><span>Sol</span><b id="i-sun"></b></div><div class="small" id="sun-state" style="text-align:right"></div>
  <div class="row"><span>Tierra</span><b id="i-earth"></b></div><div class="small" id="earth-state" style="text-align:right"></div>
  <div class="row"><span>Iluminado</span><b id="i-lit"></b></div>
  <div class="small" style="margin-top:4px" id="photo-detail"></div>
 </div>
 <div id="hud-top"></div><div id="chip" role="status"></div>
 <div id="desc" class="panel" hidden><b>Descripción de la escena</b><p id="desc-txt" style="margin:4px 0 0"></p></div>
 <div id="hud-bl"><div id="north" aria-label="Flecha del norte"><i id="north-i"></i><span>N</span></div>
  <div id="scale"><div id="scale-bar"></div><span id="scale-txt"></span></div></div>
 <div id="notice" role="note"></div>
</div>
<div id="fallback" hidden role="alert"><p id="fallback-msg"></p></div>
<p id="sr-desc" class="sr-only"></p>
</div>"""


def viewer_html(scene: dict) -> str:
    """HTML autocontenido del visor (sin <link>, sin src/href externos, sin fetch): three.js, CSS, JS y datos en línea."""
    css, three, orbit, app, _ = _assets()
    return ("<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>Visor 3D del terreno lunar</title><style>{css}</style></head><body>{_BODY}"
            f"<script type=\"application/json\" id=\"lsi-data\">{_json_for_html(scene)}</script>"
            f"<script>{three}</script><script>{orbit}</script><script>{app}</script></body></html>")


def render_terrain_viewer(scene: dict, *, height: int = 640) -> None:
    """Pinta el visor en la página de Streamlit (iframe de ``height`` px)."""
    import streamlit.components.v1 as components
    components.html(viewer_html(scene), height=height, scrolling=False)
