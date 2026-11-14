"""Catálogo de sitios y parámetros tipados desde config/ (arquitectura.md §5.2)."""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Mapping, Optional

from lsi.analysis.site_score import params_from_config, profiles_from_config
from lsi.contracts import (
    ErrorCode, HorizonParams, LSIError, ScoreParams, ScoreProfile, SiteSpec,
    TimelineParams, UncertaintyParams, VisibilityParams,
)

_REQUIRED = ("horizon", "visibility", "timeline", "uncertainty", "score", "observer", "cache")


class InvalidParameterError(LSIError):
    code = ErrorCode.INVALID_PARAMETER


def _bad(msg: str) -> InvalidParameterError:
    return InvalidParameterError(msg)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise _bad(f"No existe el fichero de configuración: {path}") from e
    except json.JSONDecodeError as e:
        raise _bad(f"JSON inválido en {path}: {e}") from e


def _num(v: Any, name: str, lo: float | None = None, hi: float | None = None,
         lo_open: bool = False) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise _bad(f"Parámetro '{name}' debe ser numérico, recibido {v!r}")
    if lo is not None and (v < lo or (lo_open and v == lo)):
        raise _bad(f"Parámetro '{name}'={v} fuera de rango (mínimo {lo}{' excluido' if lo_open else ''})")
    if hi is not None and v > hi:
        raise _bad(f"Parámetro '{name}'={v} fuera de rango (máximo {hi})")
    return float(v)


def _section(cfg: Mapping, name: str) -> Mapping:
    s = cfg.get(name)
    if not isinstance(s, Mapping):
        raise _bad(f"Falta la sección obligatoria '{name}' en simulation.json")
    return s


def _pick(sec: Mapping, cls, rules: Mapping[str, tuple], prefix: str, overrides: Mapping | None = None):
    """Construye ``cls`` con las claves de ``sec`` que existan (el resto, default del contrato)."""
    names = {f.name for f in fields(cls)}
    kw = {k: v for k, v in {**sec, **(overrides or {})}.items() if k in names and v is not None}
    for k, v in kw.items():
        if k in rules:
            lo, hi, open_ = rules[k]
            kw[k] = _num(v, f"{prefix}.{k}", lo, hi, open_)
    return cls(**kw)


def load_sites(path: Path) -> tuple[SiteSpec, ...]:
    data = _read_json(path)
    rows = data.get("sites") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise _bad(f"{path}: se esperaba la clave 'sites' con una lista")
    out, seen = [], set()
    for i, r in enumerate(rows):
        r = {k: v for k, v in r.items() if not k.startswith("_")}
        for req in ("id", "nombre", "lat", "lon", "confianza", "has_dem"):
            if req not in r:
                raise _bad(f"sites[{i}] ({r.get('id', '?')}): falta '{req}'")
        if r["id"] in seen:
            raise _bad(f"id de sitio duplicado: {r['id']}")
        seen.add(r["id"])
        lat = None if r["lat"] is None else _num(r["lat"], f"{r['id']}.lat", -90, 90)
        lon = None if r["lon"] is None else _num(r["lon"], f"{r['id']}.lon", -360, 360)
        out.append(SiteSpec(
            id=r["id"], name=r["nombre"], program=r.get("programa", ""), lat_deg=lat, lon_deg_e=lon,
            source=r.get("fuente", ""), confidence=r["confianza"], has_dem=bool(r["has_dem"]),
            date=r.get("fecha"), dem_prefix=r.get("dem_prefix"), note=r.get("nota")))
    return tuple(out)


def load_simulation_config(path: Path) -> dict:
    cfg = _read_json(path)
    if not isinstance(cfg, dict):
        raise _bad(f"{path}: se esperaba un objeto JSON")
    for k in _REQUIRED:
        _section(cfg, k)
    # construir cada bloque valida claves y rangos: se falla al cargar, no a mitad de análisis
    horizon_params(cfg); visibility_params(cfg); timeline_params(cfg)
    uncertainty_params(cfg); score_params(cfg); score_profiles(cfg)
    _num(cfg["cache"].get("max_bytes"), "cache.max_bytes", 0)
    _num(cfg["cache"].get("coord_round_m"), "cache.coord_round_m", 0, lo_open=True)
    return cfg


def horizon_params(cfg: Mapping, observer_height_m: Optional[float] = None) -> HorizonParams:
    o = _section(cfg, "observer")
    h = observer_height_m if observer_height_m is not None else o.get("height_m", 2.0)
    h = _num(h, "observer.height_m", o.get("height_min_m", 0.0), o.get("height_max_m", 100.0))
    p = _pick(_section(cfg, "horizon"), HorizonParams, {
        "az_step_deg": (0, 360, True), "radial_step_m": (0, None, True),
        "r_min_m": (0, None, False), "r_max_m": (0, None, True)}, "horizon",
        {"observer_height_m": h})
    if p.r_max_m <= p.r_min_m:
        raise _bad(f"horizon.r_max_m ({p.r_max_m}) debe superar r_min_m ({p.r_min_m})")
    if int(p.block_azimuths) != p.block_azimuths or p.block_azimuths < 1:
        raise _bad("horizon.block_azimuths debe ser un entero >= 1")
    return p


def visibility_params(cfg: Mapping) -> VisibilityParams:
    p = _pick(_section(cfg, "visibility"), VisibilityParams, {
        "eps": (0, 0.5, True), "sun_f_thr": (0, 1, False), "earth_f_thr": (0, 1, False),
        "limb_darkening_u": (0, 1, False)}, "visibility")
    if int(p.n_slices) != p.n_slices or p.n_slices < 1:
        raise _bad("visibility.n_slices debe ser un entero >= 1")
    return p


def timeline_params(cfg: Mapping, step_s: Optional[float] = None) -> TimelineParams:
    sec = _section(cfg, "timeline")
    rules = {k: (0, None, True) for k in ("step_s", "refine_xtol_s", "countdown_search_days")}
    rules["merge_tol_s"] = (0, None, False)
    p = _pick(sec, TimelineParams, rules, "timeline",
              {"step_s": step_s} if step_s is not None else None)
    mx = sec.get("max_step_s")
    if mx is not None and p.step_s > _num(mx, "timeline.max_step_s", 0, lo_open=True):
        raise _bad(f"timeline.step_s={p.step_s} supera max_step_s={mx} (se perderían eventos)")
    return p


def uncertainty_params(cfg: Mapping) -> UncertaintyParams:
    return _pick(_section(cfg, "uncertainty"), UncertaintyParams, {
        "k_sigma": (0, None, False), "alt_az_step_deg": (0, None, True),
        "observer_height_delta_m": (0, None, False)}, "uncertainty")


def score_params(cfg: Mapping) -> ScoreParams:
    """Delega en ``site_score.params_from_config`` (única fuente de la semántica); aquí solo se valida."""
    s = _section(cfg, "score")
    try:
        p = params_from_config(s)
    except (TypeError, ValueError, KeyError) as e:
        raise _bad(f"score inválido: {e}") from e
    for name, lo, hi in (("f0", 0, 1), ("f1", 0, 1), ("sigma0_deg", 0, None), ("sigma1_deg", 0, None),
                         ("eps_s", 0, None), ("earth_floor", 0, 1), ("resolution_weight", 0, 1),
                         ("g1_min_sun_fraction", 0, 1), ("g2_max_slope_deg", 0, 90),
                         ("g3_max_unknown_fraction", 0, 1), ("conf_high", 0, 1), ("conf_medium", 0, 1)):
        _num(getattr(p, name), f"score.{name}", lo, hi)
    for name in ("d_half_h", "conf_range_scale"):
        _num(getattr(p, name), f"score.{name}", 0, lo_open=True)
    if p.f0 >= p.f1:
        raise _bad(f"score.f0 ({p.f0}) debe ser menor que f1 ({p.f1})")
    if p.sigma0_deg >= p.sigma1_deg:
        raise _bad(f"score.sigma0_deg ({p.sigma0_deg}) debe ser menor que sigma1_deg ({p.sigma1_deg})")
    if p.conf_medium >= p.conf_high:
        raise _bad("score.confidence: medium debe ser menor que high")
    return p


def score_profiles(cfg: Mapping) -> dict[str, ScoreProfile]:
    """Valida pesos y delega en ``site_score.profiles_from_config``."""
    raw = _section(cfg, "score").get("profiles")
    if not isinstance(raw, Mapping) or not raw:
        raise _bad("Falta score.profiles en simulation.json")
    for pid, p in raw.items():
        w = p.get("weights")
        if not isinstance(w, Mapping) or set(w) != {"sun", "night", "earth", "terrain"}:
            raise _bad(f"score.profiles.{pid}.weights debe tener exactamente sun, night, earth, terrain")
        w = {k: _num(v, f"score.profiles.{pid}.weights.{k}", 0) for k, v in w.items()}
        if sum(w.values()) <= 0:
            raise _bad(f"score.profiles.{pid}: la suma de pesos debe ser > 0")
        if p.get("d_half_h") is not None:
            _num(p["d_half_h"], f"score.profiles.{pid}.d_half_h", 0, lo_open=True)
    return profiles_from_config(_section(cfg, "score"))


def default_observer(cfg: Mapping, dem_key: str) -> tuple[float, float] | None:
    e = cfg.get("dem_default_observers", {}).get(dem_key)
    if not isinstance(e, Mapping):
        return None
    return (_num(e.get("lat_deg"), f"dem_default_observers.{dem_key}.lat_deg", -90, 90),
            _num(e.get("lon_deg_e"), f"dem_default_observers.{dem_key}.lon_deg_e", -360, 360))
