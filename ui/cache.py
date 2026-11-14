"""Envoltorios de caché de Streamlit sobre ``lsi.pipeline`` (D2/D4): la UI NO calcula, solo llama aquí.

- ``get_context``: kernels SPICE, DEM descubiertos, paneles y sitios; una vez por proceso (``cache_resource``).
- Resultados: ``cache_resource`` (sin copiar/pickle; se tratan como SOLO LECTURA) con clave = ``repr`` de la
  petición (dataclass congelado: repr determinista y completo), tope de entradas para acotar memoria.
- Las excepciones (``LSIError``) no se cachean y suben al llamador: ``try_analysis`` las traduce a mensaje.
"""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Optional, Sequence

import streamlit as st

from lsi import pipeline
from lsi.contracts import (
    AnalysisRequest, AnalysisResult, AppContext, BatteryParams, Countdown, LSIError, MountingSpec, ObserverPoint,
    ScientificWarning,
)

ROOT = Path(__file__).resolve().parents[1]
MAX_ANALYSES = 24
TTL_S = 3600      # 1 h: acota memoria y refresca si se regeneran los mapas de idoneidad o el DEM


@st.cache_resource(show_spinner="Cargando kernels SPICE y catálogos…")
def get_context() -> AppContext:
    """Contexto del pipeline (config, kernels, DEM, paneles, sitios). Lanza ``KernelsMissingError`` si faltan kernels."""
    return pipeline.build_context(ROOT)


@st.cache_resource(show_spinner=False)
def get_gazetteer():
    """Gazetteer anotado con cobertura DEM, o None si no está generado (el resto de la app funciona; RNF-07)."""
    from lsi.contracts import GazetteerNotFoundError
    from lsi.data import gazetteer
    ctx = get_context()
    try:
        df = gazetteer.load_gazetteer()
    except GazetteerNotFoundError:
        return None
    return gazetteer.annotate_dem_coverage(df, ctx.dem_refs, float(ctx.cfg["gazetteer"]["dem_cover_margin_m"]))


COLD_SPINNER_S = 6.0      # por encima de esto el primer cálculo en frío se avisa con su tiempo medido
_COLD_S: dict[str, float] = {}     # clave de petición -> segundos del primer cálculo (proceso entero, para avisar y medir)


@st.cache_resource(max_entries=MAX_ANALYSES, ttl=TTL_S, show_spinner=False)
def _analysis(key: str, _req: AnalysisRequest) -> AnalysisResult:
    return pipeline.run_analysis(get_context(), _req)


def get_analysis(req: AnalysisRequest) -> AnalysisResult:
    """``pipeline.run_analysis`` cacheado por petición. Solo lectura. Puede lanzar ``LSIError``.

    La primera vez (en frío) muestra un spinner con texto claro y mide el tiempo (``cold_seconds``)."""
    key = repr(req)
    if key in _COLD_S:
        return _analysis(key, req)
    t = time.perf_counter()
    txt = ("Calculando Sol, Tierra, enlace y sus rangos de incertidumbre: el primer cálculo puede tardar unos segundos; "
           "después queda en caché." if req.with_uncertainty else "Calculando horizonte, Sol y Tierra…")
    with st.spinner(txt):
        res = _analysis(key, req)
    _COLD_S[key] = time.perf_counter() - t
    return res


def cold_seconds(req: AnalysisRequest) -> Optional[float]:
    """Segundos que tardó el primer cálculo de ``req`` en este proceso (None si aún no se calculó)."""
    return _COLD_S.get(repr(req))


def try_analysis(req: AnalysisRequest) -> tuple[Optional[AnalysisResult], Optional[str]]:
    """``(resultado, None)`` o ``(None, mensaje en español)`` ante un ``LSIError``/parámetro inválido (nunca un traceback)."""
    from ui.components import friendly_error
    try:
        return get_analysis(req), None
    except (LSIError, ValueError) as e:
        return None, friendly_error(e)


def get_comparison(reqs: Sequence[AnalysisRequest]) -> dict[str, AnalysisResult]:
    """Como ``pipeline.run_comparison`` (mismas claves) pero cada sitio pasa por ``get_analysis``: comparte caché con las
    demás páginas (comparar tres sitios ya vistos no recalcula nada)."""
    out: dict[str, AnalysisResult] = {}
    for r in reqs:
        base = r.site_id or f"{r.lat_deg:g},{r.lon_deg_e:g}"
        key, n = base, 1
        while key in out:
            n += 1
            key = f"{base}#{n}"
        out[key] = get_analysis(r)
    return out


@st.cache_resource(max_entries=MAX_ANALYSES, ttl=TTL_S, show_spinner="Calculando potencia…")
def _power(key: str, _req: AnalysisRequest, _specs, _battery, degradation, dust_loss):
    return pipeline.run_power(get_context(), get_analysis(_req), _specs, _battery, degradation, dust_loss)


def get_power(req: AnalysisRequest, specs: Sequence[tuple[str, Optional[MountingSpec]]],
              battery: Optional[BatteryParams] = None, degradation: Optional[float] = None,
              dust_loss: Optional[float] = None) -> list:
    """``pipeline.run_power`` cacheado: varios paneles/montajes sobre el análisis de ``req`` (reutiliza Sol y horizonte)."""
    specs = tuple((p, m) for p, m in specs)
    return _power(repr((req, specs, battery, degradation, dust_loss)), req, specs, battery, degradation, dust_loss)


@st.cache_data(max_entries=64, ttl=TTL_S, show_spinner=False)
def get_snap(lat_deg: float, lon_deg_e: float, site_id: Optional[str] = None, prefer: str = "nearest",
             profile_id: Optional[str] = None, mission_days: Optional[float] = None):
    """``pipeline.snap_candidate`` cacheado (None si no hay DEM razonable). Para OFRECER el ajuste en el buscador.
    Pasar el mismo ``profile_id``/``mission_days`` que la petición: si no, snap y análisis usarían perfiles distintos."""
    return pipeline.snap_candidate(get_context(), lat_deg, lon_deg_e, site_id=site_id, prefer=prefer,
                                   profile_id=profile_id, mission_days=mission_days)


@st.cache_data(max_entries=128, ttl=TTL_S, show_spinner=False)
def _observer(lat: float, lon: float, h: float, site_id, force: bool, gaz_id, prefer, profile_id, mission_days):
    """(observador, avisos, error). El error de borde/nodata se devuelve como texto, no se lanza."""
    from ui.components import friendly_error
    try:
        o, w = pipeline.resolve_observer(get_context(), lat, lon, h, site_id=site_id, force_smooth_sphere=force,
                                         gazetteer_id=gaz_id, prefer=prefer, profile_id=profile_id,
                                         mission_days=mission_days)
        return o, w, None
    except LSIError as e:
        return None, (), friendly_error(e)


def get_observer(req: AnalysisRequest) -> tuple[Optional[ObserverPoint], tuple[ScientificWarning, ...], Optional[str]]:
    """Resolución barata y cacheada del punto de ``req`` (modo DEM/esfera lisa, snap_to_dem) sin calcular el análisis.
    Mismos argumentos que ``run_analysis`` (preferencia de snap, perfil y duración): el punto coincide con el del análisis."""
    return _observer(req.lat_deg, req.lon_deg_e, req.observer_height_m, req.site_id, req.force_smooth_sphere,
                     req.gazetteer_id, req.snap_prefer, req.score_profile_id, req.mission_days)


@st.cache_resource(max_entries=256, ttl=TTL_S, show_spinner=False)
def _countdowns(key: str, _req: AnalysisRequest, now_utc: str) -> tuple[Countdown, ...]:
    from lsi.data import catalog
    ctx, res = get_context(), get_analysis(_req)
    r2 = dataclasses.replace(_req, now_utc=now_utc)
    # ponytail: usa el helper privado del pipeline; evita recalcular el análisis solo por mover el cursor.
    return pipeline._countdowns(r2, res.observer, res.horizon, catalog.visibility_params(ctx.cfg),
                                catalog.timeline_params(ctx.cfg, _req.step_s))


def countdowns_at(req: AnalysisRequest, now_utc: str) -> tuple[Countdown, ...]:
    """Cuentas atrás (Sol, Tierra) desde ``now_utc`` sin repetir el análisis (``req.now_utc`` se ignora)."""
    return _countdowns(repr((req, now_utc)), req, now_utc)


def get_margin_sensitivity(req: AnalysisRequest, margins: Sequence[float]) -> dict[float, AnalysisResult]:
    """Un análisis por margen de elevación de la Tierra (sensibilidad del enlace). Sin panel, sin incertidumbre: solo el enlace,
    así que cada uno es barato y todos pasan por ``get_analysis`` (caché compartida; el margen de la petición ya calculado se reutiliza
    si coincide con la clave)."""
    return {float(m): get_analysis(dataclasses.replace(req, min_earth_elevation_deg=float(m), panel_id=None, mounting=None,
                                                       battery=None, with_uncertainty=False)) for m in margins}


@st.cache_data(max_entries=8, ttl=TTL_S, show_spinner=False)
def get_mini_window(dem_key: str, cx: float, cy: float, radius_m: float = 3000.0, max_px: int = 110):
    """Recorte pequeño del DEM alrededor del punto (desplazado hacia dentro si el borde del recorte lo cortaría; promedio por bloques a ≤ ``max_px``²) para el mini-mapa topográfico; None sin DEM.
    Misma técnica que el Explorador (``terrain3d.downsample``); la UI no calcula física, solo recorta para dibujar."""
    from lsi.contracts import DemLayer, DemNotFoundError, DemWindow
    from lsi.data import loader
    from lsi.visualization import terrain3d as T
    ref = get_context().dem_refs.get(dem_key)
    if ref is None:
        return None
    xmin, ymin, xmax, ymax = ref.bounds_xy_m
    radius_m = min(radius_m, (xmax - xmin) / 2.0, (ymax - ymin) / 2.0)
    cx = min(max(cx, xmin + radius_m), xmax - radius_m)    # si el recorte no cubre la miniatura centrada en el punto, se desplaza
    cy = min(max(cy, ymin + radius_m), ymax - radius_m)    # hacia dentro: el punto sigue marcado, pero el mapa no queda medio vacío
    try:
        w = loader.read_window(ref, DemLayer.SURF, (cx - radius_m, cy - radius_m, cx + radius_m, cy + radius_m))
    except DemNotFoundError:
        return None
    z, f = T.downsample(w.data, max_px)
    off = (f - 1) / 2.0 * w.pixel_size_m
    return DemWindow(z, w.x0_m + off, w.y0_m - off, w.pixel_size_m * f, DemLayer.SURF, w.meta)
