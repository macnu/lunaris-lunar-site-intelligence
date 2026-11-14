"""Estado compartido de la UI (arquitectura §11.3): claves de ``st.session_state``, valores por defecto y ``current_request``.

Reglas para las páginas:
- Las claves son las constantes de ``contracts.StateKey`` (+ ``PANEL_IDS``, ``ORIGIN``). Solo este módulo las crea.
- Escribir con ``set_state`` / ``set_site`` / ``set_point`` / ``set_period`` DENTRO de un ``on_click``/``on_change``
  o seguido de ``st.rerun()``/``st.switch_page()``: la barra lateral ya se ha pintado en esa ejecución y se
  resincroniza (estado → widgets) al inicio de la siguiente.
- Los resultados pesados no van aquí: ``ui.cache.get_analysis(current_request())``.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional

import streamlit as st

from lsi.contracts import (
    UTC_MAX, UTC_MIN, AnalysisRequest, AppContext, BatteryParams, MountingSpec, MountingType, StateKey as K,
)

PANEL_IDS = "panel_ids"          # list[str]: paneles a comparar; ``panel_id`` = el primero
ORIGIN = "point_origin"          # "site" (curado) | "search" (buscador) | "custom" (lat/lon libres)
MODES = ("publico", "planificador", "experto")
MODE_LABELS = {"publico": "Público", "planificador": "Planificador", "experto": "Experto"}
MODE_LABELS_INV = {v: k for k, v in MODE_LABELS.items()}
ORIGINS = ("site", "search", "custom")

_GAZ = "_ui_gaz"                 # (feature_id, lat, lon, etiqueta) del último rasgo enviado desde el buscador
_ERRORS = "_ui_errors"           # dict[str, str]: problemas de entrada (periodo, observador); bloquean current_request
_DAYS = "_ui_days"               # duración del periodo en días
SUGGESTED = "ui_suggested"       # dict | None: lugar y fecha sugeridos al abrir la app (mejor candidato del mapa de idoneidad)
SNAP_PREFER = "ui_snap_prefer"   # "best" | "nearest" | None: punto del DEM elegido en el buscador (solo origen "search")
MISSION_DAYS = "ui_mission_days"  # duración de misión personalizada (d); None = la del perfil de score
DEFAULT_SITE = "site23"          # Mons Malapert: el curado con DEM cuyas coordenadas caen dentro de su recorte (§0)
MOUNT_AUTO = "ui_mount_auto"     # True = el montaje sale de la latitud (vertical con seguimiento en el polo); False = lo eligió el usuario
POLAR_LAT_DEG = 70.0             # |lat| mayor: el Sol queda a pocos grados del horizonte y un panel horizontal casi no produce
SUN_MAX_DECL_DEG = 1.54          # inclinación del eje lunar respecto a la eclíptica: el Sol nunca sube más de esto sobre el ecuador lunar
LINK_NETWORK = "ui_link_network"      # 'DSN' | 'ESTRACK' | 'DSN+ESTRACK' | 'custom' | 'geometry' (= link_network None)
LINK_MARGIN = "ui_link_margin_deg"    # margen mínimo de elevación de la Tierra en la antena del lander (°, 0-10)
LINK_CUSTOM = "ui_link_custom"        # list[[lat, lon_E, min_el]] de la red personalizada (1-3 estaciones)
LINK_STATION_EL = "ui_link_station_el"  # None | °: fuerza la elevación mínima de TODAS las estaciones (sensibilidad, experto)
LINK_DIRECTION = "ui_link_direction"  # 'receive' (recibir datos, 6° DSN) | 'transmit' (enviar órdenes, 10,1°, norma 810-005) | 'both'
LINK_DIRECTIONS = {
    "receive": "Recepción (recibir datos de la nave) · 6° DSN",
    "transmit": "Transmisión (enviar órdenes a la nave) · 10,1°, norma 810-005",
    "both": "Ambos (el enlace de ida y vuelta)",
}
LINK_DIRECTION_NAMES = {"receive": "recepción", "transmit": "transmisión", "both": "ambos sentidos"}
LINK_NETWORKS = {
    "DSN": "NASA DSN (Goldstone, Madrid, Canberra)", "ESTRACK": "ESA ESTRACK (elevación mínima supuesta)",
    "DSN+ESTRACK": "DSN + ESTRACK", "custom": "Personalizada (lat/lon)", "geometry": "Solo geometría (sin estaciones)",
}
LINK_MARGIN_MAX = 10.0
MAX_PERIOD_DAYS = 366.0
STEP_CHOICES_MIN = (5, 10, 15, 30, 60)


# ------------------------------------------------------------------------------------------------ fechas
def fmt_utc(dt: datetime) -> str:
    """datetime → 'AAAA-MM-DDTHH:MM:SS' (formato de ``AnalysisRequest``)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_utc(s: str) -> datetime:
    """'AAAA-MM-DD[ T]HH:MM[:SS]' (UTC) → datetime. ``ValueError`` con mensaje en español."""
    t = str(s).strip().replace("T", " ").rstrip("Zz").strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    raise ValueError(f"No entiendo la fecha «{s}». Usa el formato AAAA-MM-DD HH:MM (hora UTC), por ejemplo 2026-12-01 00:00.")


def validate_period(start: datetime, end: datetime) -> Optional[str]:
    """None si el periodo es válido; si no, mensaje claro (rango de kernels 1900-2050, orden, duración)."""
    lo, hi = parse_utc(UTC_MIN), parse_utc(UTC_MAX)
    rango = f"{lo:%d/%m/%Y} – {hi:%d/%m/%Y}"
    if not lo <= start <= hi:
        return f"La fecha de inicio {start:%Y-%m-%d} está fuera del rango válido ({rango}): ahí llegan las efemérides (SPICE)."
    if not end > start:
        return "El periodo debe tener una duración positiva."
    if end > hi:
        return (f"El periodo termina el {end:%Y-%m-%d}, fuera del rango válido ({rango}). "
                "Adelanta el inicio o reduce la duración.")
    if (end - start).total_seconds() / 86400.0 > MAX_PERIOD_DAYS + 1e-9:
        return f"El periodo máximo es de {MAX_PERIOD_DAYS:g} días."
    return None


# ------------------------------------------------------------------------------------------------ montaje por latitud
def is_polar(lat_deg: float) -> bool:
    return abs(float(lat_deg)) > POLAR_LAT_DEG


def default_mount(panel, lat_deg: float) -> MountingType:
    """Montaje por defecto de ``panel`` a la latitud dada: vertical con seguimiento azimutal en el polo (|lat|>70°), si el
    panel lo admite; si no, su vertical por defecto o el vertical fijo; horizontal solo a latitudes bajas."""
    allowed = panel.mounting_allowed
    if is_polar(lat_deg):
        if MountingType.VERTICAL_AZ_TRACKING in allowed:
            return MountingType.VERTICAL_AZ_TRACKING
        if panel.mounting_default in (MountingType.VERTICAL_FIXED, MountingType.VERTICAL_AZ_TRACKING):
            return panel.mounting_default
        return MountingType.VERTICAL_FIXED if MountingType.VERTICAL_FIXED in allowed else panel.mounting_default
    return MountingType.HORIZONTAL if MountingType.HORIZONTAL in allowed else panel.mounting_default


def polar_penalty(lat_deg: float) -> tuple[float, float]:
    """(elevación máxima del Sol en °, cuántas veces menos recibe un panel horizontal que uno vertical con seguimiento).
    Geometría: horizontal ∝ sen h, vertical con seguimiento ∝ cos h → cociente 1/tan h, con h = (90−|lat|) + 1,54° como cota."""
    h = max((90.0 - abs(float(lat_deg))) + SUN_MAX_DECL_DEG, 0.1)
    return h, 1.0 / math.tan(math.radians(h))


def auto_mounting(ctx: AppContext, panel_id: Optional[str], lat_deg: float) -> Optional[MountingSpec]:
    """``MountingSpec`` automático (por latitud) de un panel; el vertical fijo lleva azimut 0° (Norte)."""
    panel = next((p for p in ctx.panels.panels if p.id == panel_id), None)
    if panel is None:
        return None
    t = default_mount(panel, lat_deg)
    return MountingSpec(t, None, 0.0 if t is MountingType.VERTICAL_FIXED else None)


def sync_auto_mount(ctx: AppContext) -> None:
    """Con montaje automático, ``MOUNT_TYPE`` sigue a la latitud y al panel principal (no pisa la elección del usuario)."""
    ss = st.session_state
    if not ss.get(MOUNT_AUTO, True):
        return
    panel = next((p for p in ctx.panels.panels if p.id == ss.get(K.PANEL_ID)), None)
    if panel is not None and K.OBS_LAT in ss:
        ss[K.MOUNT_TYPE] = default_mount(panel, float(ss[K.OBS_LAT])).value


def choose_mount(widget_key: str) -> None:
    """``on_change`` del selector de montaje: la elección del usuario desactiva el automático."""
    ss = st.session_state
    ss[K.MOUNT_TYPE] = ss[widget_key]
    ss[MOUNT_AUTO] = False


def use_auto_mount() -> None:
    st.session_state[MOUNT_AUTO] = True


# ------------------------------------------------------------------------------------------------ defaults
def _first_site(ctx: AppContext):
    ok = [s for s in ctx.sites if s.lat_deg is not None and s.lon_deg_e is not None]
    return next((s for s in ok if s.id == DEFAULT_SITE), ok[0] if ok else None)


def suggested_start(ctx: AppContext, site=None, profile_id: str = "lander_solar_no_rhu") -> Optional[dict[str, Any]]:
    """Mejor CANDIDATO precalculado del sitio por defecto (``windows_*.json`` de ``scripts/precompute_suitability.py``, vía
    ``suitability_map.best_points``): punto y fecha de inicio con el score más alto que supera las puertas. None si no hay mapa
    (la app arranca entonces en el punto y la fecha por defecto de la configuración). Un candidato no es una certificación."""
    site = site or _first_site(ctx)
    if site is None or not getattr(site, "dem_prefix", None):
        return None
    try:
        from lsi.analysis import suitability_map as sm
        env = os.environ.get("LSI_SUITABILITY_DIR")
        cache_dir = Path(env).parent if env else Path(ctx.root) / ctx.cfg["cache"]["dir"]
        doc = sm.best_points(cache_dir, site.dem_prefix, profile_id, profile_mission_days(ctx, profile_id) or 14.0)
        top = (doc or {}).get("top") or []
        pick = next((t for t in top if t.get("gate_status") == "PASS" and t.get("best_start_utc")), None)
        if pick is None:
            return None
        return {"site_id": site.id, "lat": float(pick["lat_deg"]), "lon": float(pick["lon_deg_e"]) % 360.0,
                "start_utc": str(pick["best_start_utc"])[:19], "score": float(pick["score"]), "rank": int(pick.get("rank", 1))}
    except Exception:       # noqa: BLE001 - la sugerencia es opcional: cualquier fallo del mapa cae al comportamiento anterior
        return None


def best_candidate(ctx: AppContext, dem_prefix: Optional[str], profile_id: str, mission_days: Optional[float]) -> Optional[dict[str, Any]]:
    """TOP-1 PRECALCULADO del recorte ``dem_prefix`` para el perfil y la duración (``suitability_map.best_points``) con su mejor fecha
    de inicio: ``{lat, lon, start_utc, days, score, rank}``. None si no hay mapa precalculado (el llamador cae al punto por defecto)."""
    if not dem_prefix:
        return None
    try:
        from lsi.analysis import suitability_map as sm
        env = os.environ.get("LSI_SUITABILITY_DIR")
        cache_dir = Path(env).parent if env else Path(ctx.root) / ctx.cfg["cache"]["dir"]
        doc = sm.best_points(cache_dir, dem_prefix, profile_id, mission_days or profile_mission_days(ctx, profile_id) or 14.0)
        top = (doc or {}).get("top") or []
        if not top or not top[0].get("best_start_utc"):
            return None
        t = top[0]
        return {"lat": float(t["lat_deg"]), "lon": float(t["lon_deg_e"]) % 360.0, "start_utc": str(t["best_start_utc"])[:19],
                "days": float(doc["duration_days"]), "score": float(t["score"]), "rank": int(t.get("rank", 1))}
    except Exception:       # noqa: BLE001 - opcional: sin mapa, la comparación usa los puntos por defecto
        return None


def is_suggested() -> bool:
    """True si el punto y la fecha de inicio actuales siguen siendo los sugeridos al abrir (no los ha cambiado el usuario)."""
    ss, sug = st.session_state, st.session_state.get(SUGGESTED)
    return bool(sug) and abs(float(ss.get(K.OBS_LAT, 0.0)) - sug["lat"]) < 1e-6 and abs(float(ss.get(K.OBS_LON, 0.0)) - sug["lon"]) < 1e-6         and str(ss.get(K.START_UTC, ""))[:10] == sug["start_utc"][:10]


def default_state(ctx: AppContext) -> dict[str, Any]:
    cfg = ctx.cfg
    start = parse_utc(cfg["time"]["default_start_utc"])
    days = float(cfg["time"]["default_period_days"])
    site = _first_site(ctx)
    sug = suggested_start(ctx, site)
    if sug:         # estado inicial positivo: el mejor candidato y su mejor fecha, no un punto cualquiera
        start = parse_utc(sug["start_utc"])
        days = float(profile_mission_days(ctx, "lander_solar_no_rhu") or days)   # periodo = ventana de misión (como en el guion de demo)
    lat0 = sug["lat"] if sug else (float(site.lat_deg) if site else -89.9)
    panels = ctx.panels.panels
    # en el polo el panel de partida es el primero que admite seguimiento vertical (un panel plano da <1 % allí)
    panel = next((p for p in panels if is_polar(lat0) and MountingType.VERTICAL_AZ_TRACKING in p.mounting_allowed), None)         or (panels[0] if panels else None)
    return {
        K.SITE_ID: site.id if site else None,
        K.OBS_LAT: lat0,
        K.OBS_LON: sug["lon"] if sug else (float(site.lon_deg_e) % 360.0 if site else 0.0),
        K.OBS_HEIGHT: float(cfg["observer"]["height_m"]),
        K.FORCE_SPHERE: False,
        K.START_UTC: fmt_utc(start),
        K.END_UTC: fmt_utc(start + timedelta(days=days)),
        K.STEP_MIN: int(round(float(cfg["timeline"]["step_s"]) / 60.0)),
        K.CURSOR_UTC: fmt_utc(start),
        K.PANEL_ID: panel.id if panel else None,
        K.MOUNT_TYPE: default_mount(panel, lat0).value if panel else MountingType.HORIZONTAL.value,
        MOUNT_AUTO: True,
        K.MOUNT_TILT: 15.0,        # valor de partida editable (solo se usa con montaje inclinado)
        K.MOUNT_AZ: 0.0,
        K.DEGRADATION: 0.0,
        K.DUST_LOSS: 0.0,
        K.BATTERY_ON: False,
        K.BATTERY_CFG: {},
        K.SCORE_PROFILE: "lander_solar_no_rhu",
        LINK_NETWORK: str(cfg["score"]["link"].get("default_network", "DSN")),
        LINK_MARGIN: 0.0,
        LINK_DIRECTION: "receive",
        LINK_CUSTOM: [[40.0, 4.0, 6.0]],
        LINK_STATION_EL: None,
        MISSION_DAYS: None,
        SNAP_PREFER: None,
        K.SCORE_WEIGHTS: {},
        K.SCORE_PARAMS: {},
        K.COMPARE_SITES: [s.id for s in ctx.sites if s.has_dem and s.lat_deg is not None],
        K.WITH_UNCERTAINTY: False,
        K.LAYER: "elevacion",
        K.SEARCH_QUERY: "",
        K.SEARCH_TYPES: [],
        K.SEARCH_REGIONS: [],
        K.SEARCH_SELECTED: None,
        K.LANG_MODE: "publico",
        PANEL_IDS: [panel.id] if panel else [],
        ORIGIN: "site" if site else "custom",
        SUGGESTED: sug,
        _GAZ: None,
        _ERRORS: {},
        _DAYS: days,
    }


def init_state(ctx: AppContext) -> None:
    """Crea las claves que falten (idempotente; no pisa lo que el usuario ya cambió)."""
    for k, v in default_state(ctx).items():
        if k not in st.session_state:
            st.session_state[k] = v
    sync_auto_mount(ctx)


# ------------------------------------------------------------------------------------------------ helpers get/set
def get_state(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def set_state(key: str, value: Any) -> None:
    st.session_state[key] = value


def get_float(key: str, default: float = 0.0) -> float:
    return float(st.session_state.get(key, default))


def get_str(key: str, default: str = "") -> str:
    v = st.session_state.get(key, default)
    return default if v is None else str(v)


def get_bool(key: str, default: bool = False) -> bool:
    return bool(st.session_state.get(key, default))


def mode() -> str:
    """Modo de usuario: 'publico' | 'planificador' | 'experto'."""
    m = st.session_state.get(K.LANG_MODE, "publico")
    return m if m in MODES else "publico"       # tolera los valores 'tecnico'/'divulgacion' de §11.3


def is_public() -> bool:
    return mode() == "publico"


def is_expert() -> bool:
    return mode() == "experto"


def set_site(site_id: str, ctx: AppContext) -> None:
    """Selecciona un sitio curado (fija también lat/lon)."""
    s = next((x for x in ctx.sites if x.id == site_id), None)
    if s is None or s.lat_deg is None or s.lon_deg_e is None:
        return
    st.session_state.update({K.SITE_ID: s.id, K.OBS_LAT: float(s.lat_deg), K.OBS_LON: float(s.lon_deg_e) % 360.0,
                             ORIGIN: "site"})


def set_point(lat_deg: float, lon_deg_e: float, *, gazetteer_id: Optional[int] = None, label: str = "",
              snap_prefer: Optional[str] = None) -> None:
    """Fija un punto libre. Con ``gazetteer_id`` (botón «Evaluar este lugar»): origen 'search' y ``site_id=None``;
    ``snap_prefer`` ("best"/"nearest") fija qué punto del DEM se usa si el rasgo cae fuera. Coordenadas libres: sin snap."""
    ss = st.session_state
    ss.update({K.SITE_ID: None, K.OBS_LAT: float(lat_deg), K.OBS_LON: float(lon_deg_e) % 360.0,
               SNAP_PREFER: snap_prefer if gazetteer_id is not None else None})
    if gazetteer_id is None:
        ss[ORIGIN] = "custom"
    else:
        ss.update({ORIGIN: "search", K.SEARCH_SELECTED: int(gazetteer_id),
                   _GAZ: (int(gazetteer_id), float(lat_deg), float(lon_deg_e) % 360.0, label)})


def set_period(start: datetime, days: float) -> None:
    """Fija inicio y duración (sin validar: ``current_request`` seguirá bloqueado si es inválido y la barra lateral lo dirá)."""
    ss = st.session_state
    ss[K.START_UTC], ss[K.END_UTC] = fmt_utc(start), fmt_utc(start + timedelta(days=days))
    ss[_DAYS] = float(days)
    ss.pop(_ERRORS, None)


def gaz_point() -> Optional[tuple[int, float, float, str]]:
    return st.session_state.get(_GAZ)


def errors() -> dict[str, str]:
    return dict(st.session_state.get(_ERRORS) or {})


def set_error(name: str, msg: Optional[str]) -> None:
    e = dict(st.session_state.get(_ERRORS) or {})
    if msg:
        e[name] = msg
    else:
        e.pop(name, None)
    st.session_state[_ERRORS] = e


def period_days() -> float:
    return float(st.session_state.get(_DAYS, 30.0))


# ------------------------------------------------------------------------------------------------ montaje y petición
def mounting_for(ctx: AppContext, panel_id: Optional[str], s: Optional[Mapping[str, Any]] = None) -> Optional[MountingSpec]:
    """Montaje elegido en la barra lateral aplicado a ``panel_id``; si el panel no lo admite, su montaje por defecto."""
    s = st.session_state if s is None else s
    panel = next((p for p in ctx.panels.panels if p.id == panel_id), None)
    if panel is None:
        return None
    try:
        t = MountingType(s.get(K.MOUNT_TYPE))
    except ValueError:
        t = panel.mounting_default
    if t not in panel.mounting_allowed:
        t = panel.mounting_default
    tilt = float(s.get(K.MOUNT_TILT, 15.0)) if t is MountingType.TILTED else None
    az = float(s.get(K.MOUNT_AZ, 0.0)) if t in (MountingType.TILTED, MountingType.VERTICAL_FIXED) else None
    return MountingSpec(t, tilt, az)


def wanted_mount(s: Optional[Mapping[str, Any]], lat_deg: float) -> Optional[MountingType]:
    """Montaje que se PIDE (antes de comprobar si el panel lo admite): con montaje automático el ideal por latitud
    (vertical con seguimiento en el polo, horizontal fuera de él); si no, el elegido por el usuario."""
    s = st.session_state if s is None else s
    if s.get(MOUNT_AUTO, True):
        return MountingType.VERTICAL_AZ_TRACKING if is_polar(lat_deg) else MountingType.HORIZONTAL
    try:
        return MountingType(s.get(K.MOUNT_TYPE))
    except ValueError:
        return None


def mount_spec(t: MountingType, s: Optional[Mapping[str, Any]] = None) -> MountingSpec:
    """``MountingSpec`` de un tipo con la inclinación y el azimut elegidos en la sesión."""
    s = st.session_state if s is None else s
    tilt = float(s.get(K.MOUNT_TILT, 15.0)) if t is MountingType.TILTED else None
    az = float(s.get(K.MOUNT_AZ, 0.0)) if t in (MountingType.TILTED, MountingType.VERTICAL_FIXED) else None
    return MountingSpec(t, tilt, az)


def profile_mission_days(ctx: AppContext, profile_id: Optional[str]) -> Optional[float]:
    """Duración de misión (d) por defecto del perfil de score; None si no tiene ventana (perfil personalizado)."""
    from lsi.analysis.site_score import profiles_from_config
    p = profiles_from_config(ctx.cfg["score"]).get(profile_id or "")
    return None if p is None else p.mission_days


def effective_mission_days(ctx: AppContext, s: Optional[Mapping[str, Any]] = None) -> Optional[float]:
    """Duración de misión que se pedirá: la personalizada o, si no hay, la del perfil elegido."""
    s = st.session_state if s is None else s
    custom = s.get(MISSION_DAYS)
    return float(custom) if custom else profile_mission_days(ctx, s.get(K.SCORE_PROFILE))


def link_fields(s: Mapping[str, Any]) -> dict[str, Any]:
    """Campos de enlace DTE de ``AnalysisRequest`` a partir del estado (``geometry`` → ``link_network=None``)."""
    net = s.get(LINK_NETWORK, "DSN")
    direction = s.get(LINK_DIRECTION, "receive")
    direction = direction if direction in LINK_DIRECTIONS else "receive"
    if net not in LINK_NETWORKS or net == "geometry":
        return {"link_network": None, "link_direction": direction}
    custom = tuple(tuple(float(x) for x in row) for row in (s.get(LINK_CUSTOM) or ())) if net == "custom" else None
    el = s.get(LINK_STATION_EL)
    return {"link_network": net, "link_custom": custom or None, "min_earth_elevation_deg": float(s.get(LINK_MARGIN, 0.0)),
            "link_station_min_elevation_deg": None if el is None else float(el), "link_direction": direction}


def build_request(s: Mapping[str, Any], ctx: AppContext) -> AnalysisRequest:
    """``AnalysisRequest`` a partir de un mapeo de estado (función pura, testeable). Único sitio donde se construye (§11.3.4).

    ``now_utc`` queda en None a propósito: moverlo cambiaría la clave de caché y recalcularía todo; las cuentas atrás
    en ``cursor_utc`` salen de ``ui.cache.countdowns_at``.
    """
    origin = s.get(ORIGIN, "custom")
    gaz = s.get(_GAZ) if origin == "search" else None
    panel_id = s.get(K.PANEL_ID)
    battery = None
    if s.get(K.BATTERY_ON) and panel_id and s.get(K.BATTERY_CFG):
        try:
            battery = BatteryParams(**dict(s[K.BATTERY_CFG]))
        except TypeError:
            battery = None
    w = s.get(K.SCORE_WEIGHTS) or {}
    return AnalysisRequest(
        lat_deg=float(s[K.OBS_LAT]), lon_deg_e=float(s[K.OBS_LON]), start_utc=s[K.START_UTC], end_utc=s[K.END_UTC],
        observer_height_m=float(s[K.OBS_HEIGHT]), site_id=s.get(K.SITE_ID) if origin == "site" else None,
        step_s=float(s[K.STEP_MIN]) * 60.0, panel_id=panel_id, mounting=mounting_for(ctx, panel_id, s),
        score_profile_id=s.get(K.SCORE_PROFILE) or "lander_solar_no_rhu", with_uncertainty=bool(s.get(K.WITH_UNCERTAINTY)),
        force_smooth_sphere=bool(s.get(K.FORCE_SPHERE)), gazetteer_id=gaz[0] if gaz else None,
        degradation=float(s.get(K.DEGRADATION, 0.0)), dust_loss=float(s.get(K.DUST_LOSS, 0.0)), battery=battery,
        score_weights=tuple(sorted((str(k), float(v)) for k, v in w.items())) if w else None,
        mission_days=float(s[MISSION_DAYS]) if s.get(MISSION_DAYS) else None,
        snap_prefer=s.get(SNAP_PREFER) if origin == "search" else None, **link_fields(s))


def current_request() -> Optional[AnalysisRequest]:
    """Petición actual de la sesión, o None si la barra lateral tiene errores de entrada (ya mostrados al usuario)."""
    from ui.cache import get_context     # import tardío: cache importa este módulo
    if errors():
        return None
    return build_request(st.session_state, get_context())


def request_or_stop() -> AnalysisRequest:
    """``current_request`` o, si hay errores de entrada, aviso amable y ``st.stop()`` (patrón de arranque de cada página)."""
    req = current_request()
    if req is None:
        st.warning("Hay datos de entrada que corregir en la barra lateral: " + " · ".join(errors().values()))
        st.stop()
    return req


@dataclass(frozen=True)
class PointInfo:
    """Resumen del punto actual para cabeceras y etiquetas."""
    label: str
    origin: str
    lat_deg: float
    lon_deg_e: float
    height_m: float


def point_info(ctx: AppContext) -> PointInfo:
    ss = st.session_state
    origin = ss.get(ORIGIN, "custom")
    lat, lon = float(ss[K.OBS_LAT]), float(ss[K.OBS_LON])
    if origin == "site":
        s = next((x for x in ctx.sites if x.id == ss.get(K.SITE_ID)), None)
        label = s.name if s else f"{lat:.4f}°, {lon:.4f}°E"
    elif origin == "search" and ss.get(_GAZ):
        label = ss[_GAZ][3] or f"Rasgo {ss[_GAZ][0]}"
    else:
        label = f"{lat:.4f}°, {lon:.4f}°E"
    return PointInfo(label, origin, lat, lon, float(ss[K.OBS_HEIGHT]))
