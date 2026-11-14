"""Modelo de potencia de paneles solares lunares (matematica.md §6, arquitectura.md §5.12).

Estimación de potencia RELATIVA (P/P_nominal) con supuestos declarados. No depende de SPICE ni del terreno:
recibe el Sol topocéntrico (``BodyTrack``) y la fracción visible ya calculados. Todo vectorizado NumPy.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np

from lsi.contracts import (
    AU_KM, STEFAN_BOLTZMANN, BatteryParams, BatteryResult, BodyTrack, DayPower, IamSpec, LSIError,
    MissionProfile, MountingSpec, MountingType, PanelCatalog, PanelNotCalculableError, PanelSpec,
    PowerParams, PowerSeries, PowerSummary, Threshold, utc_datetime_to_et, utc_midnight_et,
)

F = np.ndarray
N_COVERGLASS_DEFAULT = 1.526
ETA_MAX_FALLBACK = 1.35
# Origen de día UTC sin SPICE: tabla de segundos intercalares de contracts (única fuente). Compatibilidad: ET de 2000-01-01 00:00 UTC.
DAY_ORIGIN_ET = utc_datetime_to_et(datetime(2000, 1, 1))


# ----------------------------------------------------------------------------- catálogo
@dataclasses.dataclass(eq=False)
class PanelSpecEx(PanelSpec):
    """``PanelSpec`` + metadatos de estimación (retrocompatible: es un ``PanelSpec``).

    ``uses_estimates``: el panel es calculable con parámetros ESTIMADOS sin datasheet (se etiqueta «estimación sin datasheet»).
    ``ranges``: campo → (mín, máx) en las mismas unidades que el campo (fracción, fracción/K); solo para paneles estimados.
    """
    uses_estimates: bool = False
    ranges: Mapping[str, tuple] = dataclasses.field(default_factory=dict)
    estimate_note: str = ""
    # Evidencia (datos-paneles.md): grupo, nivel del eslabón más débil de η/γ_T, resumen del documento leído y W/m² AM0 de celda.
    evidence_group: str = "respaldado"            # 'respaldado' | 'experimental_sin_datasheet' (siempre visible y etiquetado)
    evidence_level: str = ""                      # datasheet | paper | derivado | investigacion
    evidence_summary: str = ""
    areal_power_w_m2_am0: Optional[float] = None  # η_bol · constante solar (1361 W/m²); celda/CIC, sin empaquetado
    iam_model: str = "fresnel_1_interface"        # modelo de IAM que el código USA (= ``iam.model`` de panels.json, sin forzar)


_RANGE_FIELDS = {"eta_bol": ("efficiency_bol_pct", None, 0.01), "temp_coeff_per_k": ("temp_coeff_pmax_pct_per_K", None, 0.01),
                 "alpha_front": ("thermal", "absorptivity_front", 1.0), "emissivity_front": ("thermal", "emissivity_front", 1.0),
                 "emissivity_back": ("thermal", "emissivity_back", 1.0)}


def _ranges(p: dict) -> dict:
    out = {}
    for name, (blk, sub, k) in _RANGE_FIELDS.items():
        d = p.get(blk) or {}
        d = d.get(sub) or {} if sub else d
        if d.get("min") is not None and d.get("max") is not None:
            out[name] = (float(d["min"]) * k, float(d["max"]) * k)
    return out


def panel_status(panel: PanelSpec) -> str:
    """'no_calculable' (faltan η, γ_T, α o ε y no hay estimación) | 'estimado' (calculable con etiqueta) | 'calculable'."""
    if None in (panel.eta_bol, panel.temp_coeff_per_k, panel.alpha_front, panel.emissivity_front, panel.emissivity_back):
        return "no_calculable"
    return "estimado" if getattr(panel, "uses_estimates", False) else "calculable"


IAM_MODELS = ("fresnel_1_interface", "cosine_only", "ashrae")
EVIDENCE_GROUPS = ("respaldado", "experimental_sin_datasheet")
EVIDENCE_LEVELS = ("datasheet", "paper", "derivado", "investigacion")


def split_by_evidence_group(catalog: PanelCatalog) -> dict:
    """{'respaldado': [...], 'experimental_sin_datasheet': [...]}: para rankings sin mezclar ni ocultar el grupo experimental."""
    return {g: [p for p in catalog.panels if getattr(p, "evidence_group", "respaldado") == g] for g in EVIDENCE_GROUPS}


def _val(d: Optional[dict], scale: float = 1.0) -> Optional[float]:
    v = None if d is None else d.get("value")
    return None if v is None else float(v) * scale


def load_panel_catalog(path: Path) -> PanelCatalog:
    """Parsea panels.json: % → fracción, null → None (no calculable, no 0), ignora claves que empiezan por '_'.

    Paneles con ``estimate_without_datasheet`` → ``PanelSpecEx.uses_estimates`` + ``ranges`` (min/max de cada parámetro estimado)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    md = raw.get("model_defaults", {})
    cap_default = _val(md.get("f_T", {}).get("cold_gain_cap")) or 1.15
    panels = []
    for p in raw["panels"]:
        eff, tc, th = p.get("efficiency_bol_pct") or {}, p.get("temp_coeff_pmax_pct_per_K") or {}, p.get("thermal") or {}
        rng = tc.get("valid_range_C")
        n = _val((p.get("iam") or {}).get("coverglass_refractive_index"))
        conf = {"eta_bol": eff.get("confidence", "a_verificar"),
                "temp_coeff_per_k": tc.get("confidence", "a_verificar")}
        for k, f in (("alpha_front", "absorptivity_front"), ("emissivity_front", "emissivity_front"),
                     ("emissivity_back", "emissivity_back")):
            conf[k] = (th.get(f) or {}).get("confidence", "a_verificar")
        # El modelo de IAM es el que declara panels.json (iam.model); sin declarar, Fresnel 1 interfaz (arquitectura §0).
        # El n del panel prevalece sobre el de simulation.json si existe.
        iam_model = (p.get("iam") or {}).get("model", "fresnel_1_interface")
        if iam_model not in IAM_MODELS:
            raise LSIError(f"panel '{p['id']}': iam.model {iam_model!r} no es uno de {IAM_MODELS}")
        est = bool((p.get("estimate_without_datasheet") or {}).get("value"))
        grp, lvl = p.get("evidence_group", "respaldado"), p.get("evidence_level", "")
        if grp not in EVIDENCE_GROUPS or (lvl and lvl not in EVIDENCE_LEVELS):
            raise LSIError(f"panel '{p['id']}': evidence_group/evidence_level inválido ({grp!r}, {lvl!r})")
        panels.append(PanelSpecEx(
            id=p["id"], name=p["name"], cell_technology=p.get("cell_technology", ""),
            mounting_default=MountingType(p["mounting_default"]),
            mounting_allowed=tuple(MountingType(m) for m in p["mounting_allowed"]),
            eta_bol=_val({"value": eff.get("default")}, 0.01),
            temp_coeff_per_k=_val(tc, 0.01),
            temp_valid_range_c=None if rng is None else (float(rng[0]), float(rng[1])),
            ref_temperature_c=float(p.get("ref_temperature_C", 28.0)),
            alpha_front=_val(th.get("absorptivity_front")),
            emissivity_front=_val(th.get("emissivity_front")),
            emissivity_back=_val(th.get("emissivity_back")),
            iam=IamSpec(model=iam_model, n_coverglass=n, b0=_val((p.get("iam") or {}).get("b0"))), iam_model=iam_model,
            cold_gain_cap=None, confidence=conf, description=p.get("description", ""),
            uses_estimates=est, ranges=_ranges(p) if est else {},
            evidence_group=grp, evidence_level=lvl, evidence_summary=p.get("evidence_summary", ""),
            areal_power_w_m2_am0=None if eff.get("default") is None else float(eff["default"]) * 0.01 * _val(raw["reference"]["solar_constant_W_m2"]),
            estimate_note=(p.get("estimate_without_datasheet") or {}).get("note", "")))
    profiles = {}
    for pid, pr in raw.get("mission_profiles", {}).items():
        if pid.startswith("_"):
            continue
        thr = {k: Threshold(v.get("value", v.get("design")), v.get("type", "info"), v.get("confidence", ""),
                            v.get("note", ""))
               for k, v in pr.items() if isinstance(v, dict) and not k.startswith("_")}
        profiles[pid] = MissionProfile(pid, pr.get("label", pid), thr)
    return PanelCatalog(
        panels=tuple(panels), profiles=profiles,
        solar_constant_w_m2=_val(raw["reference"]["solar_constant_W_m2"]),
        cold_gain_cap_default=cap_default,
        f_rad_default=_val(md.get("f_rad_default")) or 1.0, f_dust_default=_val(md.get("f_dust_default")) or 1.0,
        schema_version=raw.get("schema_version", ""))


def get_panel(catalog: PanelCatalog, panel_id: str) -> PanelSpec:
    for p in catalog.panels:
        if p.id == panel_id:
            return p
    raise KeyError(f"panel '{panel_id}' no existe; ids válidos: {[p.id for p in catalog.panels]}")


# ----------------------------------------------------------------------------- geometría
def incidence_cos(az_deg: F, el_deg: F, mounting: MountingSpec,
                  ground_normal_enu: Optional[tuple] = None) -> F:
    """cos θ_inc = ŝ·n̂_p (matematica §6.3), SIN recortar (negativo = Sol detrás del panel)."""
    az, el = np.radians(np.asarray(az_deg, float)), np.radians(np.asarray(el_deg, float))
    t = mounting.type
    if t is MountingType.HORIZONTAL:
        return np.sin(el) + 0.0 * az
    if t is MountingType.VERTICAL_AZ_TRACKING:
        return np.cos(el) + 0.0 * az
    if t is MountingType.TWO_AXIS:
        return np.ones(np.broadcast(az, el).shape)
    if t is MountingType.TERRAIN_NORMAL:
        if ground_normal_enu is None:
            raise LSIError("TERRAIN_NORMAL requiere ground_normal_enu")
        n = np.asarray(ground_normal_enu, float)
        n = n / np.linalg.norm(n)
        return np.cos(el) * np.sin(az) * n[0] + np.cos(el) * np.cos(az) * n[1] + np.sin(el) * n[2]
    if mounting.azimuth_deg is None or (t is MountingType.TILTED and mounting.tilt_deg is None):
        raise LSIError(f"montaje {t.value}: faltan azimuth_deg" + (" / tilt_deg" if t is MountingType.TILTED else ""))
    g = np.radians(mounting.azimuth_deg)
    if t is MountingType.VERTICAL_FIXED:
        return np.cos(el) * np.cos(az - g)
    if t is MountingType.TILTED:
        b = np.radians(mounting.tilt_deg)
        return np.sin(b) * np.cos(el) * np.cos(az - g) + np.cos(b) * np.sin(el)
    raise LSIError(f"montaje no soportado: {t}")


def iam(theta_deg: F, spec: IamSpec, n_default: float = N_COVERGLASS_DEFAULT) -> F:
    """Fresnel una interfaz normalizado a T(0); 'cosine_only' → 1; 'ashrae' → 1−b0(1/cosθ−1); IAM(θ≥90°)=0."""
    th = np.asarray(theta_deg, float)
    inside = th < 90.0
    if spec.model == "cosine_only":
        out = np.ones_like(th)
    elif spec.model == "ashrae":
        c = np.cos(np.radians(np.where(inside, th, 0.0)))
        out = np.clip(1.0 - (spec.b0 or 0.05) * (1.0 / c - 1.0), 0.0, 1.0)
    else:
        n = spec.n_coverglass or n_default
        ti = np.radians(np.where(inside, th, 0.0))
        c, ct = np.cos(ti), np.sqrt(1.0 - (np.sin(ti) / n) ** 2)
        rs = ((c - n * ct) / (c + n * ct)) ** 2
        rp = ((n * c - ct) / (n * c + ct)) ** 2
        t0 = 1.0 - ((1.0 - n) / (1.0 + n)) ** 2
        out = (1.0 - (rs + rp) / 2.0) / t0
    return np.where(inside, out, 0.0)


# ----------------------------------------------------------------------------- térmica y eficiencia
def panel_temperature_k(g_inc_w_m2: F, panel: PanelSpec, t_ambient_k: float, eta_ref: Optional[float] = None) -> F:
    """Balance radiativo estacionario (matematica §6.5). PanelNotCalculableError si faltan α/ε/η."""
    eta = panel.eta_bol if eta_ref is None else eta_ref
    if None in (panel.alpha_front, panel.emissivity_front, panel.emissivity_back, eta):
        raise PanelNotCalculableError(f"panel '{panel.id}': faltan α/ε/η (a verificar); temperatura no calculable")
    g = np.asarray(g_inc_w_m2, float)
    q = (panel.alpha_front - eta) * g / ((panel.emissivity_front + panel.emissivity_back) * STEFAN_BOLTZMANN)
    return (q + t_ambient_k ** 4) ** 0.25


def eta_rel(t_k: F, panel: PanelSpec, params: PowerParams, catalog: PanelCatalog) -> tuple[F, np.ndarray]:
    """1+γ_T·(T−T_ref), T acotada por abajo a t_min_valid_k y tope de frío (params > panel > catálogo).

    El indicador devuelto (``t_clamped`` en la serie) marca la EXTRAPOLACIÓN del coeficiente: T fuera de
    ``panel.temp_valid_range_c`` (rango de validez de panels.json); sin rango declarado, T < ``t_min_valid_k``.
    """
    if panel.temp_coeff_per_k is None:
        raise PanelNotCalculableError(f"panel '{panel.id}': coeficiente de temperatura a verificar; no calculable")
    t = np.asarray(t_k, float)
    if panel.temp_valid_range_c is None:
        clamped = t < params.t_min_valid_k
    else:
        lo, hi = (c + 273.15 for c in panel.temp_valid_range_c)
        clamped = (t < lo) | (t > hi)
    cap = next((c for c in (params.eta_max, panel.cold_gain_cap, catalog.cold_gain_cap_default) if c is not None),
               ETA_MAX_FALLBACK)
    eta = 1.0 + panel.temp_coeff_per_k * (np.maximum(t, params.t_min_valid_k) - (panel.ref_temperature_c + 273.15))
    return np.minimum(eta, cap), clamped


def relative_power(et: F, sun: BodyTrack, f_sun: F, panel: PanelSpec, params: PowerParams,
                   catalog: PanelCatalog, ground_normal_enu=None) -> PowerSeries:
    """P_rel = f·max(0,cosθ)·IAM·η_rel·(UA/d)²·(1−deg)·(1−polvo)·f_shadow. Sin recortar a 1.

    ponytail: ``limb_darkening_u`` no se aplica (f_sun ya llega calculado); añadir si §4.5 se activa.
    """
    mnt = params.mounting
    if params.use_ground_normal and mnt.type is MountingType.HORIZONTAL and ground_normal_enu is not None:
        mnt = MountingSpec(MountingType.TERRAIN_NORMAL)
    cos_inc = incidence_cos(sun.az_deg, sun.el_deg, mnt, ground_normal_enu)
    theta = np.degrees(np.arccos(np.clip(cos_inc, -1.0, 1.0)))
    f_iam = iam(theta, panel.iam)
    dist = (AU_KM / np.asarray(sun.dist_km, float)) ** 2
    g_inc = catalog.solar_constant_w_m2 * dist * np.maximum(cos_inc, 0.0) * f_iam
    t_k = panel_temperature_k(g_inc, panel, params.t_ambient_k)
    eta, clamped = eta_rel(t_k, panel, params, catalog)
    f = np.asarray(f_sun, float)
    p = (f * np.maximum(cos_inc, 0.0) * f_iam * eta * dist
         * (1.0 - params.degradation) * (1.0 - params.dust_loss) * params.f_shadow)
    clamped = clamped & (p > 0.0)   # sin potencia no hay nada que extrapolar (de noche T es el ambiente, no la del panel)
    return PowerSeries(et=np.asarray(et, float), p_rel=p, f_sun=f, cos_inc=cos_inc, theta_deg=theta, iam=f_iam,
                       t_panel_k=t_k, eta_rel=eta, dist_factor=dist, t_clamped=clamped,
                       panel_id=panel.id, mounting=params.mounting)


# Banda de incertidumbre a incidencia rasante. Ninguna cifra de aquí es una medida del vidrio de los paneles de LSI:
IAM_N_RANGE = (1.40, 1.60)     # [sup] índice del cubreobjetos ±0,1 en torno a 1,46 (sílice fundida, panels.json) y 1,526 (por defecto)
ASHRAE_B0 = 0.05               # [sup] b0 típico de vidrio de módulo FV (De Soto et al. 2006), NO leído en la fuente: a verificar
# [sup] T_amb (sumidero térmico del panel). 40 K: trampa fría (Paige et al. 2010, Science 330, 479: 38 K subsuperficial en el impacto de
# LCROSS, URL https://pubs.usgs.gov/publication/70036393). 200 K: tope de las temperaturas máximas de superficie polar iluminada (Fisher et
# al. 2017, Icarus, rupturas de reflectancia a ~110/150/200 K de temperatura máxima Diviner, https://ntrs.nasa.gov/citations/20170003782).
# El IR del regolito ILUMINADO a Sol rasante no se ha encontrado en fuente primaria: el nominal (100 K) sigue «a verificar».
T_AMBIENT_RANGE_K = (40.0, 250.0)
BAND_RULE = ("Envolvente conjunta (mín/máx) sobre el producto cartesiano {parámetros estimados} × {variantes de IAM} × {T_amb}: cada "
             "fuente se varía UNA vez dentro de la misma envolvente (no se suman anchos ni se combinan en cuadratura: sin doble conteo). "
             "Variantes de IAM: el modelo del panel, solo-coseno (cota superior), Fresnel con n=1,40 y 1,60 [sup] y ASHRAE b0=0,05 "
             "[a verificar]. T_amb en [40, 250] K [sup]; el nominal de 130 K sigue «a verificar».")


def power_band(series: PowerSeries, panel: PanelSpec, params: PowerParams, catalog: PanelCatalog, *,
               grazing: bool = False, t_ambient_range_k: Optional[tuple] = None):
    """Banda [P_min, P_max] (fracción). Sin los argumentos nuevos: solo por el rango de los parámetros ESTIMADOS (``None`` si el panel
    no tiene rangos; comportamiento histórico). Con ``grazing=True`` o ``t_ambient_range_k``: envolvente conjunta con IAM y T_amb
    (``power_band_detail``, regla en ``BAND_RULE``); nunca ``None``.

    P_rel es monótona en T (a γ_T fijo) y en γ_T (a T fijo) y T es monótona en q=(α−η)/(ε_f+ε_b): los extremos están en las
    4 esquinas {T caliente, T frío}×{γ_T mín, γ_T máx}; se recalcula solo η_rel y se reescala la serie central (sin recalcular geometría).
    """
    if grazing or t_ambient_range_k is not None:
        return power_band_detail(series, panel, params, catalog, with_iam=grazing, t_ambient_range_k=t_ambient_range_k)["combined"]
    if not getattr(panel, "ranges", None):
        return None
    return _envelope(series, params, catalog, _param_sets(panel), [None], [params.t_ambient_k])


def _param_sets(panel: PanelSpec) -> list:
    """Paneles con parámetros extremos (esquinas caliente/fría × γ_T mín/máx) de los rangos ESTIMADOS; [panel] si no hay rangos."""
    r = getattr(panel, "ranges", None)
    if not r:
        return [panel]

    def rg(name, base):
        return r.get(name, (base, base))
    a, ef, eb, eta = (rg("alpha_front", panel.alpha_front), rg("emissivity_front", panel.emissivity_front),
                      rg("emissivity_back", panel.emissivity_back), rg("eta_bol", panel.eta_bol))
    hot = dataclasses.replace(panel, alpha_front=a[1], emissivity_front=ef[0], emissivity_back=eb[0], eta_bol=eta[0])
    cold = dataclasses.replace(panel, alpha_front=a[0], emissivity_front=ef[1], emissivity_back=eb[1], eta_bol=eta[1])
    return [dataclasses.replace(th, temp_coeff_per_k=k) for th in (hot, cold) for k in rg("temp_coeff_per_k", panel.temp_coeff_per_k)]


def iam_variants(panel: PanelSpec) -> dict:
    """Variantes de IAM de la banda rasante: {etiqueta: IamSpec}. La primera es el modelo que USA el panel."""
    return {panel.iam.model: panel.iam, "cosine_only": IamSpec("cosine_only"),
            f"fresnel_n{IAM_N_RANGE[0]:g}": IamSpec("fresnel_1_interface", IAM_N_RANGE[0]),
            f"fresnel_n{IAM_N_RANGE[1]:g}": IamSpec("fresnel_1_interface", IAM_N_RANGE[1]),
            f"ashrae_b0_{ASHRAE_B0:g}": IamSpec("ashrae", None, ASHRAE_B0)}


def _envelope(series: PowerSeries, params: PowerParams, catalog: PanelCatalog, psets, iam_specs, tambs):
    """(lo, hi) de P_rel recalculando η_rel (T depende del IAM y de T_amb) y reescalando la serie central: p·(IAM_v/IAM_c)·(η_v/η_c)."""
    cos_pos = np.maximum(series.cos_inc, 0.0)
    base_iam, base_eta = np.asarray(series.iam, float), np.asarray(series.eta_rel, float)
    lo = hi = np.asarray(series.p_rel, float)
    for sp in iam_specs:
        f_iam = base_iam if sp is None else iam(series.theta_deg, sp)
        g = catalog.solar_constant_w_m2 * series.dist_factor * cos_pos * f_iam
        r_iam = np.divide(f_iam, base_iam, out=np.zeros_like(f_iam), where=base_iam > 0)
        for ta in tambs:
            for ps in psets:
                e, _ = eta_rel(panel_temperature_k(g, ps, ta), ps, params, catalog)
                c = series.p_rel * r_iam * np.divide(e, base_eta, out=np.ones_like(base_eta), where=base_eta > 0)
                lo, hi = np.minimum(lo, c), np.maximum(hi, c)
    return lo, hi


def power_band_detail(series: PowerSeries, panel: PanelSpec, params: PowerParams, catalog: PanelCatalog, *,
                      with_iam: bool = True, t_ambient_range_k: Optional[tuple] = T_AMBIENT_RANGE_K) -> dict:
    """{'combined', 'params', 'optics', 'thermal'}: (lo, hi) de la serie por fuente (None si esa fuente no varía) y la envolvente
    conjunta ``combined`` (regla en ``BAND_RULE``). Cada componente varía SOLO su fuente, con el resto nominal."""
    t0 = params.t_ambient_k
    psets = _param_sets(panel)
    ivs = list(iam_variants(panel).values()) if with_iam else [None]
    tas = [t0] if t_ambient_range_k is None else sorted({t0, *map(float, t_ambient_range_k)})
    d = {"params": _envelope(series, params, catalog, psets, [None], [t0]) if getattr(panel, "ranges", None) else None,
         "optics": _envelope(series, params, catalog, [panel], ivs, [t0]) if with_iam else None,
         "thermal": _envelope(series, params, catalog, [panel], [None], tas) if t_ambient_range_k is not None else None}
    d["combined"] = _envelope(series, params, catalog, psets, ivs, tas)
    return d


# ----------------------------------------------------------------------------- energía
def integration_nodes(et_grid: F, windows: Sequence) -> F:
    """Unión ordenada de la rejilla y de los instantes de evento refinados (``Window.start_et/end_et``)."""
    extra = [getattr(w, a) for ws in windows for w in getattr(ws, "windows", ()) for a in ("start_et", "end_et")]
    return np.unique(np.concatenate([np.asarray(et_grid, float), np.asarray(extra, float)]))


def _trapz(t: F, y: F) -> float:
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(t))) if len(t) > 1 else 0.0


def _time_above(t: F, p: F, th: float) -> float:
    """Segundos con p ≥ th, con p lineal a tramos (cruce exacto)."""
    if len(t) < 2:
        return 0.0
    dt, a, b = np.diff(t), p[:-1] - th, p[1:] - th
    both, none = (a >= 0) & (b >= 0), (a < 0) & (b < 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(a >= 0, a / (a - b), b / (b - a))   # parte del tramo por encima del umbral
    return float(np.sum(np.where(both, dt, np.where(none, 0.0, dt * frac))))


def summarize_power(series: PowerSeries, panel: PanelSpec, useful_threshold: float, catalog: PanelCatalog,
                    day_origin_et: Optional[float] = None) -> PowerSummary:
    """E_rel, % del máximo teórico, E_inc, E_el, pico, horas útiles y tabla diaria UTC (trapecio sobre nodos).

    ``DayPower.e_rel`` = media de P_rel sobre el tramo cubierto de ese día (días parciales no se penalizan).
    ``day_origin_et`` None = medianoche UTC del primer instante (``contracts.utc_midnight_et``, con segundos intercalares).
    """
    t, p = series.et, series.p_rel
    if day_origin_et is None:
        day_origin_et = utc_midnight_et(float(t[0]))
    span = float(t[-1] - t[0])
    e_rel = _trapz(t, p) / span if span > 0 else float("nan")
    g = catalog.solar_constant_w_m2 * series.dist_factor
    e_inc = _trapz(t, g * series.f_sun * np.maximum(series.cos_inc, 0.0) * series.iam) / 3600.0
    e_el = None if panel.eta_bol is None else e_rel * (span / 3600.0) * panel.eta_bol * catalog.solar_constant_w_m2
    daily = []
    d0 = np.floor((t[0] - day_origin_et) / 86400.0)
    d1 = np.ceil((t[-1] - day_origin_et) / 86400.0)
    for d in np.arange(d0, d1):
        a, b = max(day_origin_et + d * 86400.0, t[0]), min(day_origin_et + (d + 1) * 86400.0, t[-1])
        if b <= a:
            continue
        td = np.concatenate([[a], t[(t > a) & (t < b)], [b]])
        pd = np.interp(td, t, p)
        daily.append(DayPower(day_start_et=float(day_origin_et + d * 86400.0), e_rel=_trapz(td, pd) / (b - a),
                              peak_p_rel=float(pd.max()),
                              hours_above_useful=_time_above(td, pd, useful_threshold) / 3600.0))
    return PowerSummary(iam_model=getattr(panel, "iam_model", panel.iam.model), e_rel=e_rel, pct_of_max=100.0 * e_rel, e_inc_wh_m2=e_inc, e_el_wh_m2=e_el,
                        mean_p_rel=e_rel, peak_p_rel=float(np.nanmax(p)),
                        hours_above_useful=_time_above(t, p, useful_threshold) / 3600.0,
                        useful_threshold=useful_threshold, daily=tuple(daily))


# ----------------------------------------------------------------------------- batería
def simulate_battery(et: F, p_rel: F, params: BatteryParams) -> BatteryResult:
    """Integrador de matematica §6.8. Paso i: p_rel[i] constante en [et[i], et[i+1]); soc[0]=soc0.

    ponytail: bucle Python (estado secuencial); ~1e5 pasos van en <0.3 s. Vectorizar solo si hiciera falta.
    """
    et, p_rel = np.asarray(et, float), np.asarray(p_rel, float)
    dt_h = np.diff(et) / 3600.0
    cap, lo, hi = params.capacity_wh, params.soc_min * params.capacity_wh, params.soc_max * params.capacity_wh
    b = params.soc0 * cap
    soc = np.empty(len(et))
    soc[0] = b / cap
    unserved = hours_unserved = 0.0
    for i, h in enumerate(dt_h):
        net = p_rel[i] * params.p_nominal_w - params.load_w
        if net >= 0:
            b = min(hi, b + net * params.eta_charge * h)
        else:
            need, avail = -net * h / params.eta_discharge, b - lo
            if need <= avail:
                b -= need
            else:
                b = lo
                unserved += (need - avail) * params.eta_discharge
                hours_unserved += h
        soc[i + 1] = b / cap
    return BatteryResult(et=et, soc=soc, unserved_wh=unserved, hours_unserved=hours_unserved, min_soc=float(soc.min()))
