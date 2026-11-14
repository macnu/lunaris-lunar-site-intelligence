"""Contratos de datos de LSI (Lunar Site Intelligence).

Fuente de verdad de TIPOS compartidos entre subpaquetes. Solo contiene constantes, enums,
excepciones (sin lógica), y dataclasses. Sin dependencias fuera de numpy/stdlib. Las FIRMAS de las
funciones de cada módulo están en ``docs/plan/arquitectura.md`` §5.

Reglas de uso:

- Convenciones físicas en ``docs/science/convenciones.md``. Azimut N→E 0-360°, elevación sobre el
  plano tangente de la esfera, longitud ESTE-positiva, marco MOON_ME, UTC en interfaz y ET interno.
- Sufijos de unidad obligatorios: ``_deg``, ``_rad``, ``_m``, ``_km``, ``_s``, ``_h``, ``_k`` (kelvin),
  ``_w_m2``. Un campo sin sufijo es adimensional.
- Las dataclasses de PARÁMETROS son ``frozen=True`` (hashables, aptas como clave de caché).
  Las de RESULTADOS llevan ``eq=False`` porque contienen arrays NumPy.
- Los arrays de resultados son 1-D salvo que se indique; ``NaN`` = «sin dato», nunca ``0``.
- Cambiar un campo exige avisar a todos los implementadores y subir ``CACHE_ALGORITHM_VERSION``
  si altera resultados cacheados.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int8]

# --------------------------------------------------------------------------------------
# Constantes físicas y de convención (fuente: docs/science/convenciones.md)
# --------------------------------------------------------------------------------------
MOON_RADIUS_M: float = 1_737_400.0          # radio de referencia del DEM LOLA y de Horizons
MOON_RADIUS_KM: float = 1737.4
SUN_RADIUS_KM: float = 695_700.0            # IAU 2015 B3
EARTH_RADIUS_EQ_KM: float = 6378.137        # ecuatorial; fija el radio angular de la Tierra
AU_KM: float = 149_597_870.7                # IAU 2012
SOLAR_CONSTANT_W_M2: float = 1361.0         # IAU 2015 B3 (a verificar en fuente primaria)
STEFAN_BOLTZMANN: float = 5.670374419e-8    # W m^-2 K^-4
SPICE_FRAME: str = "MOON_ME"
SPICE_ABCORR: str = "LT+S"
DEM_PROJ4: str = "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
DEM_CRS_MUST_CONTAIN: Tuple[str, ...] = ("Polar_Stereographic", "1737400")
EXPORT_SCHEMA_VERSION: str = "1.3.0"   # 1.3.0: + ``slope_footprint`` (slope_r50/slope_r100, borde del DEM) y ``power.summary.iam_model/band`` (opcionales); 1.2.0: + ``link.direction`` y ``link.network_fraction_by_direction`` (opcionales); 1.1.0 (``link``/``contacts``) y 1.0.0 siguen siendo válidos
LINK_DIRECTIONS: Tuple[str, ...] = ("receive", "transmit", "both")   # sentido del enlace DTE: elevación mínima de recepción, de transmisión o la intersección
CACHE_ALGORITHM_VERSION: int = 1            # subir al cambiar cualquier algoritmo cacheado

# Rango temporal válido del motor (BPC lunar). Margen de 1 día por light-time; a verificar.
UTC_MIN: str = "1900-01-02T00:00:00"
UTC_MAX: str = "2050-12-30T00:00:00"

# --------------------------------------------------------------------------------------
# ET (TDB) <-> UTC aproximado, SIN SPICE: ÚNICA fuente de verdad pura (export, theme y panels la reutilizan).
# ET-UTC = 32,184 s (TT-TAI) + TAI-UTC; se ignora TDB-TT (< 2 ms): exacto al segundo. Verificado contra el LSK naif0012
# (tests/test_contracts_time.py). Antes de 1972 el LSK da 9 s (no 10): ET-UTC = 41,184 s. Tabla IERS/IANA: añadir una
# fila al publicarse un segundo intercalar nuevo (hasta entonces vale hasta 2050, el rango del motor).
# --------------------------------------------------------------------------------------
LEAP_SECONDS: Tuple[Tuple[int, int, int], ...] = (   # (año, mes, TAI-UTC en s desde el día 1 de ese mes)
    (1972, 1, 10), (1972, 7, 11), (1973, 1, 12), (1974, 1, 13), (1975, 1, 14), (1976, 1, 15), (1977, 1, 16),
    (1978, 1, 17), (1979, 1, 18), (1980, 1, 19), (1981, 7, 20), (1982, 7, 21), (1983, 7, 22), (1985, 7, 23),
    (1988, 1, 24), (1990, 1, 25), (1991, 1, 26), (1992, 7, 27), (1993, 7, 28), (1994, 7, 29), (1996, 1, 30),
    (1997, 7, 31), (1999, 1, 32), (2006, 1, 33), (2009, 1, 34), (2012, 7, 35), (2015, 7, 36), (2017, 1, 37))
TT_MINUS_TAI_S: float = 32.184
TAI_MINUS_UTC_PRE_1972_S: float = 9.0          # extrapolación del LSK naif0012 antes de 1972-01-01
J2000_TT = datetime(2000, 1, 1, 12, 0, 0)      # ET = 0 (como etiqueta de reloj en TT)
_LEAP_UTC = tuple(datetime(y, m, 1) for y, m, _ in LEAP_SECONDS)
_LEAP_DAT = (TAI_MINUS_UTC_PRE_1972_S,) + tuple(float(d) for _, _, d in LEAP_SECONDS)
_LEAP_ET = np.array([(u + timedelta(seconds=TT_MINUS_TAI_S + d) - J2000_TT).total_seconds()
                     for u, (_, _, d) in zip(_LEAP_UTC, LEAP_SECONDS)])   # ET en que entra cada fila


def et_minus_utc_s(et):
    """ET (TDB, s desde J2000) -> ET-UTC en s (escalar o array). 64,184 en 2000, 66,184 en 2010, 69,184 desde 2017."""
    a = np.asarray(et, dtype=np.float64)
    off = TT_MINUS_TAI_S + np.asarray(_LEAP_DAT)[np.searchsorted(_LEAP_ET, a, side="right")]
    return float(off) if a.ndim == 0 else off


def et_to_utc_datetime(et: float) -> datetime:
    """ET -> datetime UTC naive (microsegundos; sin redondear; sin segundo 60)."""
    return J2000_TT + timedelta(seconds=float(et) - et_minus_utc_s(float(et)))


def utc_datetime_to_et(utc: datetime) -> float:
    """datetime UTC naive -> ET aproximado (inversa de ``et_to_utc_datetime``)."""
    k = sum(1 for u in _LEAP_UTC if u <= utc)
    return (utc - J2000_TT).total_seconds() + TT_MINUS_TAI_S + _LEAP_DAT[k]


def utc_midnight_et(et: float) -> float:
    """ET de la medianoche UTC (inicio del día UTC) que contiene a ``et``."""
    d = et_to_utc_datetime(et)
    return utc_datetime_to_et(d.replace(hour=0, minute=0, second=0, microsecond=0))


# --------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------
class Body(str, enum.Enum):
    """Cuerpo celeste observado. El valor es el nombre SPICE."""
    SUN = "SUN"
    EARTH = "EARTH"


class DemLayer(str, enum.Enum):
    """Capa de un producto PGDA 5 mpp: elevación, pendiente, retornos LOLA, error vertical total."""
    SURF = "surf"
    SLP = "slp"
    LDEC = "ldec"
    TOTERR = "toterr"


class HorizonMode(str, enum.Enum):
    """Origen del horizonte: DEM real o esfera lisa (sitio sin DEM, sin relieve)."""
    DEM = "dem"
    SMOOTH_SPHERE = "smooth_sphere"


class VisibilityState(enum.IntEnum):
    """Estado del disco respecto al horizonte (se guarda como int8)."""
    HIDDEN = 0
    PARTIAL = 1
    VISIBLE = 2


class EventKind(str, enum.Enum):
    """Tipo de transición de una ventana (sunrise/sunset, earthrise/earthset)."""
    RISE = "rise"
    SET = "set"


class MountingType(str, enum.Enum):
    """Montaje del panel. Los cuatro primeros son los de ``config/panels.json``."""
    HORIZONTAL = "horizontal"
    TILTED = "tilted"
    VERTICAL_FIXED = "vertical_fixed"
    VERTICAL_AZ_TRACKING = "vertical_az_tracking"
    TWO_AXIS = "two_axis"            # cota ideal de referencia (no está en panels.json)
    TERRAIN_NORMAL = "terrain_normal"  # plano sobre el suelo (normal del DEM en el punto)


class ConfidenceLevel(str, enum.Enum):
    """Etiqueta de confianza de datos (umbrales a calibrar)."""
    HIGH = "alta"
    MEDIUM = "media"
    LOW = "baja"


class GateStatus(str, enum.Enum):
    """Resultado de una puerta dura del score."""
    PASS = "apto"
    FAIL = "no_apto"
    NO_DATA = "sin_datos_suficientes"
    NOT_APPLICABLE = "no_aplica"


class Severity(str, enum.Enum):
    """Severidad de un aviso científico."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class WarningCode(str, enum.Enum):
    """Códigos de aviso científico (texto estándar en ``STANDARD_WARNINGS_ES``)."""
    GEOMETRIC_ONLY = "geometric_only"
    NOT_RF_LINK = "not_rf_link"
    POWER_IS_ESTIMATE = "power_is_estimate"
    ECLIPSES_NOT_MODELED = "eclipses_not_modeled"
    NO_DEM_SMOOTH_SPHERE = "no_dem_smooth_sphere"
    DEM_EFFECTIVE_RESOLUTION = "dem_effective_resolution"
    HORIZON_TRUNCATED = "horizon_truncated"
    HORIZON_LOWER_BOUND = "horizon_lower_bound"
    OBSERVER_NEAR_EDGE = "observer_near_edge"
    NEAR_FIELD_UNRELIABLE = "near_field_unreliable"
    WINDOW_TRUNCATED = "window_truncated"
    PANEL_UNVERIFIED = "panel_unverified"
    COLD_EXTRAPOLATION = "cold_extrapolation"
    IAM_GRAZING_UNCERTAIN = "iam_grazing_uncertain"
    SCORE_UNCALIBRATED = "score_uncalibrated"
    ROCKS_NOT_MODELED = "rocks_not_modeled"
    CURATED_COORDS_OUTSIDE_DEM = "curated_coords_outside_dem"
    DATE_TRUNCATED = "date_truncated"
    NO_TERRAIN_DATA_SCORE = "no_terrain_data_score"
    GAZETTEER_COORDS_APPROX = "gazetteer_coords_approx"


class ErrorCode(str, enum.Enum):
    """Códigos de error del núcleo (la UI los traduce a mensajes)."""
    DATE_OUT_OF_RANGE = "date_out_of_range"
    OBSERVER_OUTSIDE_DEM = "observer_outside_dem"
    OBSERVER_NEAR_EDGE = "observer_near_edge"
    NODATA_AT_OBSERVER = "nodata_at_observer"
    DEM_NOT_FOUND = "dem_not_found"
    DEM_CRS_MISMATCH = "dem_crs_mismatch"
    KERNELS_MISSING = "kernels_missing"
    SITE_WITHOUT_COORDINATES = "site_without_coordinates"
    GAZETTEER_NOT_FOUND = "gazetteer_not_found"
    INVALID_PARAMETER = "invalid_parameter"
    PANEL_NOT_CALCULABLE = "panel_not_calculable"


# --------------------------------------------------------------------------------------
# Excepciones (solo declaración; el mensaje lo pone quien lanza)
# --------------------------------------------------------------------------------------
class LSIError(Exception):
    """Base de errores del núcleo. ``code`` identifica la causa para la UI."""
    code: ErrorCode = ErrorCode.INVALID_PARAMETER


class DateOutOfRangeError(LSIError):
    """Fecha fuera de [UTC_MIN, UTC_MAX]."""
    code = ErrorCode.DATE_OUT_OF_RANGE


class ObserverOutsideDemError(LSIError):
    """El punto cae fuera de la cobertura del DEM."""
    code = ErrorCode.OBSERVER_OUTSIDE_DEM


class ObserverNearEdgeError(LSIError):
    """El punto está a menos de ``edge_margin_px`` píxeles del borde del DEM."""
    code = ErrorCode.OBSERVER_NEAR_EDGE


class NodataAtObserverError(LSIError):
    """El DEM no tiene dato válido en el punto (o en sus 4 vecinos bilineales)."""
    code = ErrorCode.NODATA_AT_OBSERVER


class DemNotFoundError(LSIError):
    """No existen los GeoTIFF esperados."""
    code = ErrorCode.DEM_NOT_FOUND


class DemCrsMismatchError(LSIError):
    """El CRS del GeoTIFF no es el estereográfico polar sur de 1737.4 km."""
    code = ErrorCode.DEM_CRS_MISMATCH


class KernelsMissingError(LSIError):
    """Falta algún kernel SPICE obligatorio."""
    code = ErrorCode.KERNELS_MISSING


class GazetteerNotFoundError(LSIError):
    """No existe el catálogo procesado (``data/processed/gazetteer.*``): ejecutar scripts/fetch_gazetteer.py."""
    code = ErrorCode.GAZETTEER_NOT_FOUND


class SiteWithoutCoordinatesError(LSIError):
    """Sitio del catálogo con lat/lon nulos (a verificar): no seleccionable."""
    code = ErrorCode.SITE_WITHOUT_COORDINATES


class PanelNotCalculableError(LSIError):
    """Faltan parámetros del panel (p. ej. α/ε para la temperatura)."""
    code = ErrorCode.PANEL_NOT_CALCULABLE


# --------------------------------------------------------------------------------------
# Catálogo de sitios y observador
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SiteSpec:
    """Entrada de ``config/sites.json``. ``lat_deg``/``lon_deg_e`` nulos = no seleccionable."""
    id: str
    name: str
    program: str
    lat_deg: Optional[float]
    lon_deg_e: Optional[float]
    source: str
    confidence: str                      # publicado | aprox | a verificar
    has_dem: bool
    date: Optional[str] = None
    dem_prefix: Optional[str] = None     # p. ej. "Site04"; ``dem_dir`` de sites.json es un marcador obsoleto
    note: Optional[str] = None


@dataclass(frozen=True)
class SnapRankEntry:
    """Un punto del ranking de mejores puntos del DEM (TOP-N precalculado de ``suitability_map``) al hacer snap."""
    rank: int
    lat_deg: float
    lon_deg_e: float
    best_start_utc: str                  # mejor fecha de inicio de ESE punto para el perfil y la duración
    f_sun: float
    d_max_h: float
    score: float
    gate_status: str                     # PASS | NO_DATA | FAIL
    distance_km: float                   # al punto pedido / centro del rasgo (círculo máximo)


@dataclass(frozen=True)
class ObserverPoint:
    """Punto de observación resuelto. ``x_m``/``y_m`` en el plano estereográfico polar sur."""
    lat_deg: float
    lon_deg_e: float                     # 0..360
    x_m: float
    y_m: float
    height_m: float                      # altura de la antena/mástil sobre el suelo
    mode: HorizonMode
    ground_z_m: Optional[float] = None   # z del DEM (sobre la esfera R); None sin DEM
    dem_key: Optional[str] = None
    site_id: Optional[str] = None
    label: str = ""
    snap_distance_km: Optional[float] = None            # ajuste snap_to_dem: distancia (círculo máximo) al punto pedido/centro del rasgo
    snapped_from: Optional[Tuple[float, float]] = None   # (lat, lon_E) originales pedidos si hubo snap_to_dem
    # --- etiqueta del snap (None/() sin snap). Añadidos retrocompatibles (SNAP AL MEJOR PUNTO) ---
    snap_kind: Optional[str] = None                      # "best" (TOP-1 del mapa) | "nearest" (más cercano) | "default_observer"
    snap_reason: Optional[str] = None                    # por qué ese punto (texto en español)
    best_start_utc: Optional[str] = None                 # snap "best": mejor fecha de inicio sugerida de ese punto
    snap_ranking: Tuple[SnapRankEntry, ...] = ()         # snap "best": TOP-N del mapa (el primero es el elegido)
    snap_alternative: Optional[Tuple[float, float, float]] = None   # (lat, lon_E, distancia_km) del punto cubierto MÁS CERCANO
    # --- snap «best» limitado al entorno del rasgo (retrocompatibles; None sin snap o sin radio conocido) ---
    snap_feature_radius_km: Optional[float] = None       # radio del rasgo usado (diámetro/2 del gazetteer; 10 km por defecto en sitios curados)
    snap_edge_offset_km: Optional[float] = None          # distancia al BORDE: >0 fuera del borde, <0 dentro (= distancia al centro − radio)
    snap_inside_feature: Optional[bool] = None           # False = «ningún punto recomendable dentro del rasgo» (se usó el más cercano)
    snap_map_rank: Optional[int] = None                  # rango del punto elegido en el mapa de idoneidad (snap «best»)


# --------------------------------------------------------------------------------------
# Gazetteer (buscador de rasgos lunares con nombre oficial IAU/USGS)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class GazetteerEntry:
    """Rasgo con nombre oficial (USGS Gazetteer of Planetary Nomenclature). Lon ESTE-positiva 0..360."""
    feature_id: int                      # ID del gazetteer (p. ej. 16338 = Mons Malapert)
    name: str                            # nombre oficial con acentos/diacríticos originales
    name_ascii: str                      # minúsculas sin acentos (clave de búsqueda)
    feature_type: str                    # tipo oficial en inglés: Crater, Mons, Dorsum, Rima...
    lat_deg: float                       # planetocéntrica, sur negativa
    lon_deg_e: float
    diameter_km: Optional[float]
    origin: str                          # origen del nombre (texto del gazetteer; puede ser vacío)
    approval_year: Optional[int] = None
    region: str = ""                     # derivada por código: "polo_sur" (<-80°), "sur" , "ecuatorial", "norte", "polo_norte"
    has_dem: bool = False                # derivado: hay recorte DEM que cubre el centro del rasgo
    dem_key: Optional[str] = None
    quad: str = ""                       # cuadrángulo LQ (si el origen de datos lo da)


@dataclass(frozen=True)
class GazetteerQuery:
    """Consulta del buscador: texto difuso sin acentos + filtros. Resultado ordenado por relevancia."""
    text: str = ""
    feature_types: Tuple[str, ...] = ()  # vacío = todos
    regions: Tuple[str, ...] = ()
    min_diameter_km: Optional[float] = None
    max_diameter_km: Optional[float] = None
    only_with_dem: bool = False
    limit: int = 50


# --------------------------------------------------------------------------------------
# Datos: DEM
# --------------------------------------------------------------------------------------
@dataclass(eq=False)
class DemRef:
    """Referencia a un producto DEM en disco: clave ('Site04') y ruta de cada capa."""
    key: str
    directory: str
    paths: Mapping[str, str]             # clave = DemLayer.value
    bounds_xy_m: Tuple[float, float, float, float]  # xmin, ymin, xmax, ymax (borde de píxeles)


@dataclass(eq=False)
class DemMetadata:
    """Metadatos de una capa de DEM (todo lo que debe ir al export y a la clave de caché)."""
    key: str
    layer: DemLayer
    width_px: int
    height_px: int
    pixel_size_m: float
    bounds_xy_m: Tuple[float, float, float, float]
    transform: Tuple[float, float, float, float, float, float]  # orden Affine de rasterio: a,b,c,d,e,f (x=a*col+b*row+c)
    crs_wkt: str
    nodata: Optional[float]
    dtype: str
    sha256: str
    size_bytes: int
    effective_resolution_m: float = 30.0   # advertencia LOLA: 5 m/px no es resolución efectiva
    registration: str = "area"             # píxel centrado en x0+5*(col+0.5)


@dataclass(eq=False)
class DemWindow:
    """Ventana de una capa. ``data[row, col]`` en float32/64; NaN = nodata/inválido.

    Coordenadas de píxel CENTRADAS: ``col = (x - x0_m)/pixel_size_m``, ``row = (y0_m - y)/pixel_size_m``;
    (x0_m, y0_m) es el centro del píxel [0, 0]. Las filas crecen hacia y negativa.
    """
    data: NDArray[np.floating]
    x0_m: float
    y0_m: float
    pixel_size_m: float
    layer: DemLayer = DemLayer.SURF
    meta: Optional[DemMetadata] = None
    col_offset: int = 0                  # origen de la ventana dentro del raster completo
    row_offset: int = 0


@dataclass(frozen=True)
class SlopeStats:
    """Pendiente en la huella del vehículo (percentil, media, máx.)."""
    percentile_deg: float
    percentile: float
    mean_deg: float
    max_deg: float
    r_foot_m: float
    n_pixels: int
    source: str                          # "slp" | "surf_central_diff_10m"


# --------------------------------------------------------------------------------------
# Horizonte
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class HorizonParams:
    """Parámetros del horizonte (defaults en ``config/simulation.json``)."""
    observer_height_m: float = 2.0
    az_step_deg: float = 0.25
    radial_step_m: float = 5.0
    r_min_m: float = 5.0                 # exclusión de campo cercano (15 m = opción conservadora)
    r_max_m: float = 30_000.0
    block_azimuths: int = 120
    compute_upper_bound: bool = True
    z_up_m: Optional[float] = None       # None = máximo del DEM
    conservative_bias_deg: float = 0.0   # 0.05 = modo prudente (error de interpolación angular)


@dataclass(eq=False)
class HorizonResult:
    """Horizonte por azimut. ``h_lb_deg`` es COTA INFERIOR si ``limited`` (cobertura del DEM)."""
    az_deg: FloatArray                   # (A,) 0, ΔA, 2ΔA ... < 360
    h_lb_deg: FloatArray                 # (A,) horizonte con terreno conocido (valor nominal)
    r_cov_m: FloatArray                  # (A,) último r con dato válido
    limited: BoolArray                   # (A,) el rayo salió del DEM / tocó nodata antes de r_max
    mode: HorizonMode
    observer: ObserverPoint
    params: HorizonParams
    h_sphere_deg: float                  # suelo analítico -acos(R/(R+h))
    cache_key: str
    h_ub_deg: Optional[FloatArray] = None
    dem_sha256: Optional[str] = None
    cov_min_m: float = float("nan")
    cov_median_m: float = float("nan")
    sigma_h_deg: Optional[FloatArray] = None   # incertidumbre por azimut si se calculó
    far_sha256: Optional[str] = None     # sha256 del DEM de campo lejano (LOLA 80 m) si se usó; None = solo DEM local


# --------------------------------------------------------------------------------------
# Astronomía
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class KernelInfo:
    """Kernels SPICE cargados y su rango temporal válido."""
    kernel_dir: str
    files: Tuple[str, ...]
    kernel_hash: str
    et_min: float
    et_max: float
    utc_min: str
    utc_max: str
    spiceypy_version: str


@dataclass(eq=False)
class BodyTrack:
    """Serie topocéntrica de un cuerpo: az (N→E, 0-360), el (sin refracción), distancia, radio angular."""
    body: Body
    az_deg: FloatArray
    el_deg: FloatArray
    dist_km: FloatArray
    radius_deg: FloatArray


@dataclass(eq=False)
class SkySeries:
    """Sol y Tierra vistos desde un punto en una rejilla de ET (TDB, s desde J2000)."""
    et: FloatArray
    lat_deg: float
    lon_deg_e: float
    height_m: float
    sun: BodyTrack
    earth: BodyTrack
    frame: str = SPICE_FRAME
    abcorr: str = SPICE_ABCORR
    kernel_hash: str = ""


# --------------------------------------------------------------------------------------
# Visibilidad y ventanas
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class VisibilityParams:
    """Parámetros de fracción de disco y umbrales de ventana."""
    n_slices: int = 64
    eps: float = 1e-3                    # f<=eps oculto; f>=1-eps visible
    sun_f_thr: float = 1e-3              # ventana solar: f > thr
    earth_f_thr: float = 0.5             # ventana de Tierra (comunicaciones): f >= thr (a calibrar)
    limb_darkening_u: float = 0.0        # 0 = disco uniforme; 0.6 = oscurecimiento de limbo (a verificar)


@dataclass(eq=False)
class BodyVisibility:
    """Visibilidad de un cuerpo. ``f`` usa H_lb (optimista); ``f_pess`` usa H_ub (pesimista)."""
    body: Body
    f: FloatArray
    state: IntArray                      # VisibilityState por instante
    unknown_relevant: BoolArray          # azimut limitado por cobertura y H_lb < e+ρ
    f_pess: Optional[FloatArray] = None


@dataclass(eq=False)
class VisibilitySeries:
    """Visibilidad de Sol y Tierra sobre la rejilla ``et``."""
    et: FloatArray
    sun: BodyVisibility
    earth: BodyVisibility
    horizon_cache_key: str = ""


@dataclass(frozen=True)
class Window:
    """Intervalo [start_et, end_et) con estado verdadero. Truncada = cota inferior de duración."""
    start_et: float
    end_et: float
    left_truncated: bool = False
    right_truncated: bool = False

    @property
    def duration_s(self) -> float:
        """Duración en segundos."""
        return self.end_et - self.start_et


@dataclass(eq=False)
class WindowSet:
    """Lista ordenada de ventanas disjuntas de un criterio (p. ej. Sol f>eps)."""
    label: str                           # "sun" | "earth" | "overlap" | "dark" | ...
    windows: Tuple[Window, ...]
    t0_et: float
    t1_et: float
    criterion: str                       # texto: "f_sun > 0.001"


@dataclass(frozen=True)
class Event:
    """Transición refinada (sunrise/sunset/earthrise/earthset)."""
    et: float
    body: Body
    kind: EventKind
    az_deg: float
    truncated: bool = False


@dataclass(frozen=True)
class TimelineParams:
    """Parámetros del escaneo temporal y refinamiento."""
    step_s: float = 600.0
    refine_xtol_s: float = 1.0
    merge_tol_s: float = 1.0
    countdown_search_days: float = 45.0


@dataclass(eq=False)
class TimelineResult:
    """Ventanas Sol/Tierra/solape/oscuridad de un periodo, con su rejilla gruesa."""
    et0: float
    et1: float
    params: TimelineParams
    sun: WindowSet
    earth: WindowSet
    overlap: WindowSet
    dark: WindowSet                      # complemento de ``sun``
    events: Tuple[Event, ...]
    series: VisibilitySeries
    sun_pess: Optional[WindowSet] = None     # con H_ub
    earth_pess: Optional[WindowSet] = None
    link: Optional["LinkResult"] = None      # enlace DTE (None = solo geometría)


@dataclass(frozen=True)
class Countdown:
    """Cuenta atrás hasta la próxima transición de un cuerpo desde ``now_et``."""
    body: Body
    now_et: float
    currently_up: bool                   # f > umbral del cuerpo ahora
    next_event: Optional[Event]          # None si no hay en la ventana de búsqueda
    seconds_until: Optional[float]
    approximate_due_to_coverage: bool    # el evento depende de un azimut con cobertura limitada
    searched_days: float


# --------------------------------------------------------------------------------------
# Métricas e incertidumbre
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Range:
    """Valor nominal con rango [lo, hi] entre escenarios."""
    nominal: float
    lo: float
    hi: float


@dataclass(frozen=True)
class SiteMetrics:
    """Métricas del periodo. ``*_truncated`` = la ventana ganadora toca el borde: valor es ≥ X."""
    period_s: float
    solar_fraction: float                # Σ ventanas / T
    effective_illumination: float        # media de f_sun
    earth_fraction: float
    overlap_fraction: float
    longest_sun_window_s: float
    longest_sun_window_truncated: bool
    max_darkness_s: float
    max_darkness_truncated: bool
    longest_earth_window_s: float
    longest_overlap_s: float
    n_sun_windows: int
    n_earth_windows: int
    max_sun_elevation_deg: float
    max_earth_elevation_deg: float
    unknown_fraction_sun: float          # fracción de azimutes «desconocido relevante» para el Sol
    unknown_fraction_earth: float
    # --- enlace DTE (opcionales: None = conectividad solo geométrica, ``network=None``). ``earth_fraction`` sigue siendo
    #     la geometría (Tierra sobre el horizonte); el enlace exige además margen de elevación y estación que vea la Luna ---
    link_fraction: Optional[float] = None            # fracción del periodo con enlace posible
    network_fraction: Optional[float] = None         # fracción con alguna estación viendo la Luna (independiente del sitio)
    link_hours_per_day_mean: Optional[float] = None  # horas de enlace por día UTC, media (= 24·link_fraction)
    link_hours_per_day_min: Optional[float] = None   # mínima entre los días UTC COMPLETOS del periodo (None si no hay ninguno)
    longest_link_window_s: Optional[float] = None
    longest_link_window_truncated: bool = False
    max_link_gap_s: Optional[float] = None           # hueco más largo sin enlace
    max_link_gap_truncated: bool = False
    link_by_station: Optional[Mapping[str, float]] = None   # fracción del periodo con enlace por cada estación


@dataclass(frozen=True)
class ContactWindow:
    """Ventana de contacto de UNA estación con un lander: Tierra visible desde el lander (con margen) ∧ la estación ve la Luna."""
    station_id: str
    station_name: str
    complex: str
    tz: str                                  # zona IANA de la estación
    start_et: float
    end_et: float
    start_utc: str                           # ISO, sin zona
    end_utc: str
    start_local: str                         # «AAAA-MM-DD HH:MM:SS PST» (hora civil con horario de verano)
    end_local: str
    start_solar_h: float                     # hora solar media local de la estación (UTC + lon/15), 0-24
    end_solar_h: float
    duration_s: float
    max_moon_el_deg: float                   # elevación máxima de la Luna sobre el horizonte de la estación en la ventana
    max_earth_el_deg: Optional[float]        # elevación máxima de la Tierra en el lander en la ventana
    left_truncated: bool = False
    right_truncated: bool = False


@dataclass(frozen=True)
class StationLinkSummary:
    """Resumen por estación sobre el periodo analizado."""
    station_id: str
    name: str
    complex: str
    tz: str
    min_elevation_deg: float
    confidence: str
    link_fraction: float                     # enlace posible vía esta estación
    moon_visible_fraction: float             # la estación ve la Luna (independiente del sitio lunar)
    link_hours_per_day: float
    n_windows: int
    longest_window_s: float


@dataclass(eq=False)
class LinkResult:
    """Enlace DTE sobre el periodo: ventanas de Tierra con margen, de enlace posible y por estación, y contactos."""
    network_id: str
    network_label: str
    min_earth_elevation_deg: float
    earth: WindowSet                         # Tierra visible desde el lander con el margen de elevación
    link: WindowSet                          # earth ∧ (alguna estación ve la Luna)
    network_cover: WindowSet                 # alguna estación ve la Luna (sin lander)
    by_station: Mapping[str, WindowSet]      # earth ∧ estación i
    contacts: Tuple[ContactWindow, ...] = ()
    stations: Tuple[StationLinkSummary, ...] = ()
    notes: Tuple[str, ...] = ()


@dataclass(eq=False)
class ScenarioResult:
    """Métricas de un escenario de incertidumbre (cobertura, σz, discretización, clon...)."""
    name: str
    description: str
    metrics: SiteMetrics


@dataclass(frozen=True)
class UncertaintyParams:
    """Escenarios y magnitudes de la propagación de incertidumbre."""
    k_sigma: float = 1.0
    alt_az_step_deg: float = 0.5
    observer_height_delta_m: float = 0.0     # 0 = no variar la altura
    use_coverage_bound: bool = True
    use_sigma_z: bool = True
    use_discretization: bool = True


@dataclass(eq=False)
class UncertaintyResult:
    """Rangos por métrica entre escenarios (no estadísticos: cotas de sensibilidad)."""
    scenarios: Tuple[ScenarioResult, ...]
    ranges: Mapping[str, Range]


# --------------------------------------------------------------------------------------
# Paneles y energía
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Threshold:
    """Umbral de un perfil de misión (hard = inviable, soft = penaliza)."""
    value: Optional[float]
    type: str
    confidence: str
    note: str = ""


@dataclass(eq=False)
class MissionProfile:
    """Perfil de ``mission_profiles`` de panels.json; ``thresholds`` indexado por clave del JSON."""
    id: str
    label: str
    thresholds: Mapping[str, Threshold]


@dataclass(frozen=True)
class IamSpec:
    """Modelo de pérdida por incidencia: 'fresnel_1_interface' | 'cosine_only' | 'ashrae'."""
    model: str = "fresnel_1_interface"
    n_coverglass: Optional[float] = None     # None = valor por defecto de simulation.json
    b0: Optional[float] = None


@dataclass(eq=False)
class PanelSpec:
    """Panel del catálogo. ``None`` = a verificar: tratar como «no calculable», nunca como 0."""
    id: str
    name: str
    cell_technology: str
    mounting_default: MountingType
    mounting_allowed: Tuple[MountingType, ...]
    eta_bol: Optional[float]                 # fracción (0.295), no porcentaje
    temp_coeff_per_k: Optional[float]        # fracción/K (-0.0023), no %/K
    temp_valid_range_c: Optional[Tuple[float, float]]
    ref_temperature_c: float
    alpha_front: Optional[float]
    emissivity_front: Optional[float]
    emissivity_back: Optional[float]
    iam: IamSpec
    cold_gain_cap: Optional[float]
    confidence: Mapping[str, str]            # campo → publicado|estimado|suposicion|a_verificar
    description: str = ""


@dataclass(eq=False)
class PanelCatalog:
    """Contenido de ``config/panels.json`` ya tipado (claves que empiezan por «_» ignoradas)."""
    panels: Tuple[PanelSpec, ...]
    profiles: Mapping[str, MissionProfile]
    solar_constant_w_m2: float
    cold_gain_cap_default: float
    f_rad_default: float
    f_dust_default: float
    schema_version: str = ""


@dataclass(frozen=True)
class MountingSpec:
    """Montaje concreto. ``tilt_deg`` solo en TILTED; ``azimuth_deg`` de la normal en TILTED/VERTICAL_FIXED."""
    type: MountingType
    tilt_deg: Optional[float] = None
    azimuth_deg: Optional[float] = None


@dataclass(frozen=True)
class PowerParams:
    """Supuestos del modelo de potencia (factores a 1.0 = no modelado)."""
    panel_id: str
    mounting: MountingSpec
    degradation: float = 0.0
    dust_loss: float = 0.0
    f_shadow: float = 1.0
    t_ambient_k: float = 100.0
    t_min_valid_k: float = 173.15
    eta_max: Optional[float] = None          # None = cold_gain_cap del panel/catálogo
    limb_darkening_u: float = 0.0
    use_ground_normal: bool = False


@dataclass(eq=False)
class PowerSeries:
    """Potencia relativa P(t)/P_nominal y sus factores, sobre ``et`` (nodos de integración)."""
    et: FloatArray
    p_rel: FloatArray
    f_sun: FloatArray
    cos_inc: FloatArray
    theta_deg: FloatArray
    iam: FloatArray
    t_panel_k: FloatArray
    eta_rel: FloatArray
    dist_factor: FloatArray                  # (UA/d)^2
    t_clamped: BoolArray                     # T < t_min_valid_k (extrapolación en frío)
    panel_id: str
    mounting: MountingSpec


@dataclass(frozen=True)
class DayPower:
    """Energía relativa de un día UTC."""
    day_start_et: float
    e_rel: float
    peak_p_rel: float
    hours_above_useful: float


@dataclass(frozen=True)
class SlopeScale:
    """Pendiente en la huella a UNA escala (r = 50 m: la de LSI; r = 100 m: la que usa NASA para un sitio). Nombres para la UI:
    ``AnalysisResult.slope_r50`` y ``slope_r100``. Sin píxeles válidos o con el disco fuera del DEM: estadísticos ``None``
    (nunca 0°) y ``touches_dem_edge`` True si es por el borde."""
    r_foot_m: float
    mean_deg: Optional[float]
    p90_deg: Optional[float]
    max_deg: Optional[float]
    pct_area_above_limit: Optional[float]    # % del área válida con pendiente ≥ ``landing_limit_deg`` (None sin límite o sin píxeles)
    landing_limit_deg: Optional[float]       # umbral de aterrizaje del perfil de misión (max_landing_slope_deg)
    n_pixels: int
    source: str                              # "slp" | "surf_central_diff_10m"
    touches_dem_edge: bool                   # el disco (+ baseline de la pendiente) llega al borde del recorte DEM


@dataclass(frozen=True)
class PowerSummary:
    """Energía del periodo. ``pct_of_max`` = 100·E_rel (máx. = 2 ejes, 1 UA, siempre iluminado)."""
    e_rel: float
    pct_of_max: float
    e_inc_wh_m2: float
    e_el_wh_m2: Optional[float]              # None si eta_bol es None
    mean_p_rel: float
    peak_p_rel: float
    hours_above_useful: float
    useful_threshold: float
    daily: Tuple[DayPower, ...]
    # --- opcionales (retrocompatibles): modelo óptico usado y banda de incertidumbre a incidencia rasante (energía media relativa) ---
    iam_model: str = ""                              # modelo de IAM que el código USÓ ('fresnel_1_interface' | 'cosine_only' | 'ashrae')
    e_rel_band: Optional[Tuple[float, float]] = None   # (mín, máx) de E_rel: envolvente conjunta de parámetros × IAM × T_amb
    e_rel_band_components: Optional[Mapping[str, Tuple[float, float]]] = None   # por fuente: params | optics | thermal
    band_note: str = ""                              # regla de combinación y etiquetas [sup]/a verificar


@dataclass(frozen=True)
class BatteryParams:
    """Batería opcional (todos los valores a calibrar)."""
    capacity_wh: float
    p_nominal_w: float
    load_w: float
    soc0: float = 0.5
    soc_min: float = 0.2
    soc_max: float = 1.0
    eta_charge: float = 0.95
    eta_discharge: float = 0.95


@dataclass(eq=False)
class BatteryResult:
    """Estado de carga y energía no servida."""
    et: FloatArray
    soc: FloatArray
    unserved_wh: float
    hours_unserved: float
    min_soc: float


# --------------------------------------------------------------------------------------
# Score y confianza
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoreParams:
    """Constantes de normalización y puertas (todas «a calibrar con experto»)."""
    f0: float = 0.20
    f1: float = 0.90
    d_half_h: float = 48.0
    sigma0_deg: float = 5.0
    sigma1_deg: float = 15.0
    eps_s: float = 0.01
    g1_min_sun_fraction: float = 0.05
    g2_max_slope_deg: float = 20.0
    g3_max_unknown_fraction: float = 0.5
    conf_cov_floor: float = 0.0
    conf_range_scale: float = 25.0
    conf_high: float = 0.75
    conf_medium: float = 0.5
    # --- ronda de correcciones (valores 0 = comportamiento anterior; config/simulation.json los activa) ---
    earth_floor: float = 0.0              # s_earth = min(1, f_E / max(f_E,ref, earth_floor)): mínimo útil de Tierra [sup]
    resolution_weight: float = 0.0        # λ del mezclado S = 100·A^(1-λ)·Q^λ (Q sin saturar: resolución arriba) [sup]
    window_step_h: float = 24.0           # paso de la rejilla de fechas de inicio (convención)
    top_n_windows: int = 3                # ventanas alternativas a reportar
    min_feasible_start_fraction: float = 0.10   # por debajo, el sitio es CONDICIONAL (ventana frágil; convención)
    g0_needs_sun: bool = True             # G0: Sol visible en la fecha de inicio (convención operativa)
    g5_min_duty: float = 0.5              # G5: fracción mínima de la ventana con P_rel ≥ potencia mínima útil [sup, revision-espacial §3]
    g5_type: str = "soft"                 # G5 blanda salvo perfil (base_isru: dura) [sup]
    power_duty_weight: float = 0.5        # energía efectiva = (1-w)·P_rel medio + w·duty útil (con panel elegido) [sup]
    link_gap_half_factor: float = 0.0     # continuidad del enlace: el factor vale 1/2 con un hueco = factor × (hueco tolerado por el perfil); 0 = sin continuidad (comportamiento anterior) [sup]


@dataclass(frozen=True)
class ScoreProfile:
    """Perfil: pesos (se renormalizan a Σ=1) y vínculo con un perfil de misión de panels.json."""
    id: str
    label: str
    weights: Mapping[str, float]             # claves: sun, night, earth, terrain
    mission_profile_id: Optional[str] = None
    uses_solar_gate: bool = True
    d_half_h: Optional[float] = None         # None = ScoreParams.d_half_h
    mission_days: Optional[float] = None     # duración de la ventana de misión; None = todo el periodo (sin ventana)
    earth_floor: Optional[float] = None      # None = ScoreParams.earth_floor
    g4_limit_h: Optional[float] = None       # noche máxima propia del perfil (anula panels.json); None = la del perfil de misión
    g4_type: Optional[str] = None            # "hard" | "soft" (con g4_limit_h; None = hard)
    g4_na: bool = False                      # True = G4 no aplica (p. ej. RHU)
    g5_min_duty: Optional[float] = None      # G5 (potencia útil): duty mínimo propio del perfil; None = ScoreParams.g5_min_duty
    g5_type: Optional[str] = None            # "hard" | "soft" (None = ScoreParams.g5_type)
    min_earth_elevation_deg: Optional[float] = None   # margen de elevación de la Tierra en el lander para el enlace [sup]; None = el de la config
    max_link_gap_h: Optional[float] = None   # G7: hueco máximo sin enlace tolerado en la ventana (h); None = G7 no aplica
    max_link_gap_type: Optional[str] = None  # "hard" | "soft"
    min_link_hours_per_day: Optional[float] = None   # contacto mínimo útil por día (h) para la continuidad del enlace [sup]; None = sin ese componente


@dataclass(frozen=True)
class ScoreInputs:
    """Entradas del score ya medidas por los motores (un escenario)."""
    f_sun: float
    d_max_h: float
    f_earth: float
    f_earth_ref: float                       # fracción con Tierra sobre esfera lisa (mismo motor, H≡H_esfera)
    slope_p90_deg: Optional[float]          # None = sin datos de terreno (esfera lisa): s_terreno no se evalúa
    unknown_fraction: float
    observer_in_dem: bool
    has_dem: bool = True
    d_max_truncated: bool = False
    sun_at_start: Optional[bool] = None      # G0: Sol visible en la fecha de inicio; None = no se evalúa (sin ventana)
    longest_earth_h: Optional[float] = None  # G6: ventana de Tierra continua más larga en la ventana (h); None = no se evalúa
    max_link_gap_h: Optional[float] = None   # G7: hueco más largo sin enlace en la ventana (h); None = no se evalúa
    link_mode: bool = False                  # True: ``f_earth``/``f_earth_ref``/``longest_earth_h`` son del ENLACE (red + margen), no de la geometría
    # --- energía ligada al panel elegido (T39 / RF-33); None = Sol geométrico (sin panel) ---
    f_power_eff: Optional[float] = None      # energía efectiva en [0,1] que sustituye a f_sun en s_sun: (1-w)·p_rel_mean + w·duty_useful
    p_rel_mean: Optional[float] = None       # P_rel medio sobre la ventana de misión
    duty_useful: Optional[float] = None      # fracción de la ventana con P_rel ≥ ``useful_power_fraction`` (G5)
    useful_power_fraction: Optional[float] = None   # potencia mínima útil del perfil (fracción de la nominal)


@dataclass(frozen=True)
class SubScore:
    """Fila del desglose: valor medido, s_i en [0,1], peso, penalización y S si s_i=1."""
    key: str                                 # sun | night | earth | terrain
    label: str
    value: Optional[float]
    unit: str
    s: float
    weight: float
    penalty_pct: float
    score_if_one: float


@dataclass(frozen=True)
class GateResult:
    """Puerta dura evaluada: estado y motivo legible."""
    id: str                                  # G0 | G1 | G2 | G3 | G4 | G6 (G0 y G6 solo si se evalúan)
    status: GateStatus
    reason: str
    hard: bool = True                        # False = puerta blanda: su FAIL no rechaza, solo vuelve CONDICIONAL
    value: Optional[float] = None
    limit: Optional[float] = None
    margin_fraction: Optional[float] = None  # (límite − valor)/límite en las puertas «≤» (negativo = incumple)
    window: Optional[str] = None             # "ventana" | "periodo" | "punto"


@dataclass(frozen=True)
class DemConfidence:
    """Calidad del DEM en un disco alrededor del punto (terreno-geologia.md §2.3)."""
    level: ConfidenceLevel
    dc: float
    g90_m: float
    e90_m: float
    f_obs: float
    radius_m: float
    open_azimuth_fraction: float
    effective_resolution_m: float = 30.0
    sigma_h90_deg: Optional[float] = None    # p90 del movimiento del horizonte al desplazar el DEM ±toterr (None = no medido)
    c_hz: Optional[float] = None             # estabilidad del horizonte en [0,1] (revision-geologica §2)


@dataclass(frozen=True)
class DataConfidence:
    """Confianza global C = min(c_cov, c_sup, c_rango) (matematica.md §7.5); c_sup = min(c_gap, c_err, c_hz)."""
    level: ConfidenceLevel
    c: float
    c_cov: float
    c_sup: float
    c_range: float
    dem: Optional[DemConfidence] = None


@dataclass(frozen=True)
class WindowScore:
    """Una ventana de misión candidata [start, end] con su score (score_min/max solo en la mejor: escenarios)."""
    start_utc: str
    end_utc: str
    score: float
    d_max_h: float
    f_sun: float
    score_min: Optional[float] = None
    score_max: Optional[float] = None


@dataclass(frozen=True)
class SustainableDays:
    """Días que opera un lander desde cada fecha de inicio (con G0) hasta la primera noche que supera su límite."""
    median_days: float
    best_days: float
    best_start_utc: str
    limit_h: float
    censored_fraction: float                 # fracción de inicios sin noche letal en el periodo (valor = cota inferior)


@dataclass(eq=False)
class SiteScoreResult:
    """Score con desglose, rango, puertas, confianza y supuestos; nunca una cifra sola."""
    profile_id: str
    score: float
    score_min: float
    score_max: float
    subscores: Tuple[SubScore, ...]
    weakest_key: str
    gates: Tuple[GateResult, ...]
    status: GateStatus                       # peor estado entre puertas (FAIL > NO_DATA > PASS)
    confidence: Optional[DataConfidence]
    assumptions: Tuple[str, ...]
    attenuated: bool = False                 # True si hay puerta FAIL/NO_DATA: la UI lo atenúa
    partial: bool = False                    # True si faltan subindicadores (p. ej. sin terreno)
    missing_keys: Tuple[str, ...] = ()       # subindicadores no evaluables ("terrain" en esfera lisa)
    terrain_data: bool = True                # False = modo esfera lisa: «sin datos de terreno»
    # --- veredicto por puertas y escenarios (el score solo ordena; revision-espacial §4) ---
    verdict: str = ""                        # "APTO" | "CONDICIONAL" | "NO APTO" | "SIN DATOS"
    verdict_reason: str = ""
    verdict_provisional: bool = False        # NO APTO sobre esfera lisa: «cota optimista», provisional
    # --- ventana de misión ---
    mission_days: Optional[float] = None
    window_start_utc: Optional[str] = None   # ventana evaluada (la mejor fecha de inicio, o la del periodo)
    window_end_utc: Optional[str] = None
    best_start_utc: Optional[str] = None     # None = ninguna fecha de inicio supera las puertas duras
    best_window_end_utc: Optional[str] = None
    feasible_start_fraction: Optional[float] = None
    n_starts: Optional[int] = None
    top_windows: Tuple[WindowScore, ...] = ()
    max_sustainable_days: Optional[SustainableDays] = None
    # --- rango de incertidumbre: explícito si NO se calculó (revision final R4) ---
    range_computed: bool = False             # True = hay escenarios de incertidumbre; False = [min, max] NO es un resultado de incertidumbre
    range_note: str = ""                     # frase para la UI: «rango no calculado…» / «rango calculado y estrecho…» / «rango calculado…»
    # --- energía: sobre qué se evaluó la subpuntuación de Sol (T39) ---
    energy_basis: str = "geometric"          # "geometric" (fracción de Sol) | "panel" (potencia efectiva del panel y montaje elegidos)
    energy_panel_id: Optional[str] = None
    energy_mounting: Optional[str] = None
    energy_note: str = ""
    energy_p_rel_mean: Optional[float] = None
    energy_duty_useful: Optional[float] = None
    energy_useful_threshold: Optional[float] = None


# --------------------------------------------------------------------------------------
# Avisos científicos
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScientificWarning:
    """Aviso mostrado por la UI. ``text_es`` sale de STANDARD_WARNINGS_ES salvo contexto."""
    code: WarningCode
    severity: Severity
    text_es: str
    context: Optional[str] = None


STANDARD_WARNINGS_ES: Mapping[WarningCode, str] = {
    WarningCode.GEOMETRIC_ONLY: "Visibilidad geométrica: Sol y Tierra respecto al horizonte (terreno + curvatura). No garantiza potencia ni enlace.",
    WarningCode.NOT_RF_LINK: "La visibilidad de la Tierra no es un enlace de comunicaciones: no se calcula presupuesto de enlace, antena, DSN ni interferencias.",
    WarningCode.POWER_IS_ESTIMATE: "Potencia relativa estimada con supuestos declarados (ley del coseno, IAM, temperatura simple). No son vatios de misión; sin polvo, sombra propia ni albedo.",
    WarningCode.ECLIPSES_NOT_MODELED: "No se modelan eclipses lunares (la Tierra tapando al Sol, ~2 al año, hasta ~3,5 h): «oscuridad» solo incluye relieve.",
    WarningCode.NO_DEM_SMOOTH_SPHERE: "Sin DEM en este punto: se usa esfera lisa sin relieve. Solo el horizonte esférico; la iluminación real puede ser muy distinta.",
    WarningCode.DEM_EFFECTIVE_RESOLUTION: "El DEM LOLA tiene 5 m/píxel pero ~90 % de píxeles sin retorno propio: resolución efectiva ≈ 30 m. Rocas y cráteres menores de ~150 m no están evaluados.",
    WarningCode.HORIZON_TRUNCATED: "Horizonte limitado por cobertura: el DEM no llega más lejos en algunos azimutes; el horizonte real es ≥ al dibujado y la iluminación es una cota superior.",
    WarningCode.HORIZON_LOWER_BOUND: "El horizonte mostrado es una cota inferior en los azimutes marcados; el resultado es optimista en iluminación.",
    WarningCode.OBSERVER_NEAR_EDGE: "El punto está cerca del borde del DEM: gran parte del horizonte queda sin datos.",
    WarningCode.NEAR_FIELD_UNRELIABLE: "El horizonte cercano (< 15–30 m) depende de píxeles interpolados; la altura del observador cambia mucho el resultado.",
    WarningCode.WINDOW_TRUNCATED: "La ventana toca el borde del periodo analizado: su duración es una cota inferior (≥ X).",
    WarningCode.PANEL_UNVERIFIED: "Parámetros de este panel marcados «a verificar»: resultado orientativo.",
    WarningCode.COLD_EXTRAPOLATION: "Temperatura de panel fuera del rango de validez del coeficiente térmico: eficiencia acotada, resultado optimista.",
    WarningCode.IAM_GRAZING_UNCERTAIN: "A incidencia rasante (> 80°) el IAM es la parte más incierta del modelo.",
    WarningCode.SCORE_UNCALIBRATED: "Score = resumen explicable, no un veredicto. Umbrales y pesos son editables y están pendientes de calibrar con un experto de misión.",
    WarningCode.ROCKS_NOT_MODELED: "No se modelan rocas, plumas, navegación ni incertidumbre de aterrizaje: solo pendiente del DEM. «Apto» no significa «seguro».",
    WarningCode.CURATED_COORDS_OUTSIDE_DEM: "Las coordenadas curadas de este sitio caen fuera de su recorte de DEM: se usa un punto dentro del recorte; elige tu punto.",
    WarningCode.DATE_TRUNCATED: "Fecha ajustada al rango válido de los kernels (1900-2050).",
    WarningCode.NO_TERRAIN_DATA_SCORE: "Sin datos de terreno: el score es PARCIAL (sin pendiente ni relieve) y optimista. Sol y noche se calculan sobre esfera lisa. No es comparable con sitios con DEM.",
    WarningCode.GAZETTEER_COORDS_APPROX: "Posición del gazetteer = centro del rasgo (IAU/USGS), no un punto de aterrizaje. Elige el punto de observación dentro del rasgo.",
}

# Siempre visibles en toda pantalla con resultados (el resto, solo si procede)
ALWAYS_SHOWN_WARNINGS: Tuple[WarningCode, ...] = (
    WarningCode.GEOMETRIC_ONLY,
    WarningCode.ECLIPSES_NOT_MODELED,
    WarningCode.DEM_EFFECTIVE_RESOLUTION,
)


# --------------------------------------------------------------------------------------
# Orquestación (lsi.pipeline) y UI
# --------------------------------------------------------------------------------------
@dataclass(eq=False)
class AppContext:
    """Dependencias ya cargadas que recibe ``pipeline`` (se construye una vez con ``pipeline.build_context``)."""
    root: str                                # raíz del repo
    cfg: Mapping[str, object]                # config/simulation.json tal cual (dict anidado)
    kernels: KernelInfo
    dem_refs: Mapping[str, DemRef]           # clave 'Site04' → DemRef (vacío si no hay DEM)
    panels: PanelCatalog
    sites: Tuple[SiteSpec, ...]


@dataclass(frozen=True)
class AnalysisRequest:
    """Petición completa: punto + periodo + panel + score. Hashable → clave de caché de la UI."""
    lat_deg: float
    lon_deg_e: float
    start_utc: str
    end_utc: str
    observer_height_m: float = 2.0
    site_id: Optional[str] = None
    step_s: float = 600.0
    panel_id: Optional[str] = None
    mounting: Optional[MountingSpec] = None
    score_profile_id: str = "lander_solar_no_rhu"
    with_uncertainty: bool = False
    force_smooth_sphere: bool = False
    gazetteer_id: Optional[int] = None       # si el punto viene del buscador
    degradation: float = 0.0                 # potencia: pérdida por degradación (fracción)
    dust_loss: float = 0.0                   # potencia: pérdida por polvo (fracción, escenario de sensibilidad)
    battery: Optional[BatteryParams] = None  # batería opcional (necesita panel_id)
    score_weights: Optional[Tuple[Tuple[str, float], ...]] = None   # pesos editables ((clave, peso), ...); None = los del perfil
    now_utc: Optional[str] = None            # instante de la cuenta atrás; None = start_utc
    snap_to_dem: Optional[bool] = None       # None = auto (solo si viene de gazetteer/sitio curado); False = nunca
    mission_days: Optional[float] = None     # duración de la ventana de misión (d); None = la del perfil de score
    snap_prefer: Optional[str] = None        # snap_to_dem: "best" (mejor punto del DEM) | "nearest"; None = auto (best solo gazetteer/sitio curado)
    feature_radius_km: Optional[float] = None   # radio del rasgo para acotar el snap «best»; None = diámetro/2 del gazetteer (o 10 km en sitios curados)
    link_network: Optional[str] = "DSN"      # red terrestre del enlace DTE: 'DSN' | 'ESTRACK' | 'DSN+ESTRACK' | 'custom' | None (= solo geometría, comportamiento anterior)
    min_earth_elevation_deg: Optional[float] = None   # margen de elevación de la Tierra en el lander; None = el del perfil de score
    link_custom: Optional[Tuple[Tuple[float, ...], ...]] = None   # red 'custom': ((lat, lon_E, min_el[, ...]), ...)
    link_station_min_elevation_deg: Optional[float] = None   # fuerza la elevación mínima de TODAS las estaciones (sensibilidad)
    link_direction: str = "receive"          # sentido del enlace: 'receive' (elev. mínima de recepción, 6° DSN) | 'transmit' (de transmisión, 10,1°) | 'both' (intersección)


@dataclass(eq=False)
class AnalysisResult:
    """Resultado integral de una petición (lo que consume la UI y exporta analysis.export)."""
    request: AnalysisRequest
    observer: ObserverPoint
    horizon: HorizonResult
    sky: SkySeries
    timeline: TimelineResult
    metrics: SiteMetrics
    warnings: Tuple[ScientificWarning, ...]
    dem_meta: Optional[DemMetadata] = None
    slope: Optional[SlopeStats] = None
    dem_confidence: Optional[DemConfidence] = None
    uncertainty: Optional[UncertaintyResult] = None
    power: Optional[PowerSeries] = None
    power_summary: Optional[PowerSummary] = None
    score: Optional[SiteScoreResult] = None
    kernels: Optional[KernelInfo] = None
    battery: Optional[BatteryResult] = None
    countdowns: Tuple[Countdown, ...] = ()   # próxima transición del Sol y de la Tierra desde now_utc
    daily: Tuple[dict, ...] = ()             # tabla diaria por día UTC real (pipeline.daily_table_utc)
    f_earth_ref: Optional[float] = None      # fracción de Tierra con H≡H_esfera (referencia del score; de la ventana evaluada)
    window_metrics: Optional[SiteMetrics] = None   # métricas de la ventana de misión evaluada (= ``metrics`` si no hay ventana)
    score_inputs: Optional[ScoreInputs] = None     # entradas nominales del score (ventana): la UI re-puntúa con ellas
    score_scenarios: Tuple[ScoreInputs, ...] = ()  # entradas de los escenarios de incertidumbre (ventana)
    link: Optional[LinkResult] = None        # enlace DTE del periodo completo (None si ``request.link_network`` es None)
    link_window: Optional[LinkResult] = None   # enlace de la ventana de misión evaluada (la del score)
    network_fraction_by_direction: Optional[dict] = None   # {'receive'|'transmit'|'both': fracción del periodo con ≥ 1 estación de la red} (None sin red)
    slope_r50: Optional[SlopeScale] = None       # pendiente en huella r = 50 m (junto al veredicto)
    slope_r100: Optional[SlopeScale] = None      # pendiente en huella r = 100 m (escala NASA de sitio)
    dem_edge_distance_m: Optional[float] = None  # distancia del punto al borde del recorte DEM (m); None sin DEM
    footprint_touches_dem_edge: Optional[bool] = None   # la huella de r = 100 m (+ baseline) roza el borde del DEM


class StateKey:
    """Claves de ``st.session_state`` (única lista permitida; se crean en ``ui/state.py``)."""
    SITE_ID = "site_id"
    OBS_LAT = "obs_lat_deg"
    OBS_LON = "obs_lon_deg_e"
    OBS_HEIGHT = "obs_height_m"
    FORCE_SPHERE = "force_smooth_sphere"
    START_UTC = "start_utc"
    END_UTC = "end_utc"
    STEP_MIN = "step_min"
    CURSOR_UTC = "cursor_utc"            # instante inspeccionado (Horizon & Visibility)
    PANEL_ID = "panel_id"
    MOUNT_TYPE = "mount_type"
    MOUNT_TILT = "mount_tilt_deg"
    MOUNT_AZ = "mount_az_deg"
    DEGRADATION = "degradation"
    DUST_LOSS = "dust_loss"
    BATTERY_ON = "battery_on"
    BATTERY_CFG = "battery_cfg"
    SCORE_PROFILE = "score_profile_id"
    SCORE_WEIGHTS = "score_weights"
    SCORE_PARAMS = "score_params_overrides"
    COMPARE_SITES = "compare_site_ids"
    WITH_UNCERTAINTY = "with_uncertainty"
    LAYER = "explorer_layer"
    SEARCH_QUERY = "search_query"
    SEARCH_TYPES = "search_types"
    SEARCH_REGIONS = "search_regions"
    SEARCH_SELECTED = "search_selected_feature_id"
    LANG_MODE = "audience_mode"          # "tecnico" | "divulgacion"


# --------------------------------------------------------------------------------------
# Esquema de exportación (docs/plan/arquitectura.md §7)
# --------------------------------------------------------------------------------------
CSV_TIMESERIES_COLUMNS: Tuple[str, ...] = (
    "utc", "et", "sun_az_deg", "sun_el_deg", "sun_f", "sun_state", "sun_dist_km", "horizon_at_sun_deg",
    "earth_az_deg", "earth_el_deg", "earth_f", "earth_state", "earth_dist_km", "horizon_at_earth_deg",
    "unknown_relevant_sun", "unknown_relevant_earth", "p_rel",
)
CSV_WINDOWS_COLUMNS: Tuple[str, ...] = (
    "kind", "start_utc", "end_utc", "duration_h", "left_truncated", "right_truncated",
)
CSV_HORIZON_COLUMNS: Tuple[str, ...] = (
    "az_deg", "h_lb_deg", "h_ub_deg", "r_cov_m", "limited",
)
CSV_METRICS_COLUMNS: Tuple[str, ...] = ("metric", "value", "unit", "lo", "hi", "truncated")
CSV_COMPARISON_COLUMNS: Tuple[str, ...] = ("metric", "unit")  # + una columna por sitio
# Enlace DTE (esquema 1.1.0): estaciones.csv, contactos.csv y contactos_diarios.csv. Horas locales en ISO 8601 con offset;
# ``*_utc_offset_h`` = offset respecto a UTC en horas (número, no texto). Solo se escriben si hay red de enlace.
CSV_LINK_STATIONS_COLUMNS: Tuple[str, ...] = (
    "station_id", "name", "complex", "lat_deg", "lon_deg_e", "tz", "min_elevation_deg", "confidence",
    "link_fraction", "moon_visible_fraction", "link_hours_per_day", "n_windows", "longest_window_h", "max_moon_el_deg",
)
CSV_LINK_CONTACTS_COLUMNS: Tuple[str, ...] = (
    "station_id", "start_utc", "end_utc", "start_local", "end_local", "tz", "start_utc_offset_h", "end_utc_offset_h",
    "start_solar_h", "end_solar_h", "duration_h", "max_moon_el_deg", "max_earth_el_deg", "left_truncated", "right_truncated",
)
CSV_LINK_DAILY_COLUMNS: Tuple[str, ...] = (
    "day_utc", "link_hours", "overlap_hours", "gap_hours", "n_stations", "stations", "station_hours",
)
