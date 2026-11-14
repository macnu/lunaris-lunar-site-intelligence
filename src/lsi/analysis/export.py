"""Export de resultados (arquitectura §5.16 y §7): JSON, bundle CSV y validador de esquema.

Decisiones:

- **NaN / inf -> ``null``** en JSON y celda vacía en CSV; jamás ``NaN`` literal (no es JSON válido).
  ``null`` significa «sin dato / no evaluado»: en el score parcial (sin DEM) el terreno lleva
  ``SubScore.s = NaN`` y sale como ``"s": null`` junto con ``"terrain" in missing_keys``. Nunca 0.
- **Determinista**: orden de claves fijo, floats redondeados, ``allow_nan=False``, UTF-8, ``\\n``.
  La única fuente no determinista es ``generated_utc``: por defecto ``null``; el llamador pasa la hora.
- **UTC sin SPICE**: ET (TDB) -> UTC con TT-UTC = 32.184 s + TAI-UTC (tabla de segundos intercalares
  desde 1972; antes de 1972 se extrapola 9 s, como el LSK; ``contracts.et_to_utc_datetime``). TDB-TT (<2 ms) se ignora; salida al segundo.
  El propio segundo intercalar (23:59:60) no es representable y cae en 23:59:59/00:00:00.
- Las ventanas/eventos van en UTC ISO 8601 (``...Z``). ``SubScore``/``Range`` NaN -> null.
- **Enlace DTE (esquema 1.1.0)**: bloque ``link`` (red, márgenes, métricas del periodo y resumen por estación) y lista
  ``contacts`` (ventanas por estación con hora UTC y LOCAL ISO 8601 con offset, ``tz`` IANA y offset en horas, más hora solar
  media). ``link=None`` -> ``link.network = null`` y listas vacías. La hora local se deriva del UTC ya redondeado al segundo.
- **Seguridad CSV**: los textos de terceros (nombres de rasgos/estaciones) se neutralizan si empiezan por ``= + - @``,
  tab o CR (prefijo ``'``); los números nunca se tocan.
- Huecos del contrato (``AnalysisResult`` no guarda VisibilityParams, PowerParams ni ScoreParams): en
  ``provenance.params`` se vuelcan los criterios de ``WindowSet`` y el panel/montaje de ``PowerSeries``;
  el pipeline puede pasar los objetos completos con el argumento ``params``.
"""
from __future__ import annotations

import csv
import dataclasses
import enum
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from lsi import __version__ as LSI_VERSION
from lsi.analysis.metrics import comparison_table
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS,
    CSV_COMPARISON_COLUMNS,
    CSV_HORIZON_COLUMNS,
    CSV_LINK_CONTACTS_COLUMNS,
    CSV_LINK_DAILY_COLUMNS,
    CSV_LINK_STATIONS_COLUMNS,
    CSV_METRICS_COLUMNS,
    CSV_TIMESERIES_COLUMNS,
    CSV_WINDOWS_COLUMNS,
    EXPORT_SCHEMA_VERSION,
    LINK_DIRECTIONS,
    MOON_RADIUS_M,
    SPICE_ABCORR,
    SPICE_FRAME,
    STANDARD_WARNINGS_ES,
    AnalysisResult,
    HorizonMode,
    ScientificWarning,
    Severity,
    WarningCode,
    et_to_utc_datetime,
)

# Decimales por magnitud (valores de config/simulation.json: export.float_decimals; resto: elección propia).
DECIMALS = {"deg": 4, "s": 1, "fraction": 5, "power_rel": 5, "km": 3, "m": 1, "h": 4, "count": 0}
_METRIC_DECIMALS = {"s": 1, "deg": 4, "fraction": 5, "count": 0, "bool": 0, "h": 4}
_WINDOW_KINDS = ("sun", "earth", "overlap", "dark")
_TRUNC_PARENT = {"longest_sun_window_truncated": "longest_sun_window_s", "max_darkness_truncated": "max_darkness_s"}


class ExportSchemaError(ValueError):
    """El diccionario exportado no cumple el esquema del §7 (el mensaje lista todos los fallos)."""


# --------------------------------------------------------------------------------------
# Utilidades: números, tiempo, conversión genérica
# --------------------------------------------------------------------------------------
def _num(x, nd: Optional[int] = None):
    """float redondeado, o None si x es None/NaN/inf. ``-0.0`` se normaliza a ``0.0``."""
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    if nd is not None:
        v = round(v, nd)
    return v + 0.0


def et_to_utc_str(et: float) -> Optional[str]:
    """ET (s TDB desde J2000) -> ``YYYY-MM-DDTHH:MM:SSZ`` (redondeado al segundo); None si no finito.
    La conversión vive en ``contracts.et_to_utc_datetime`` (única fuente de verdad)."""
    if et is None or not math.isfinite(float(et)):
        return None
    utc = (et_to_utc_datetime(et) + timedelta(microseconds=500_000)).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _plain(o):
    """Dataclass/enum/numpy/Mapping/secuencia -> tipos JSON; NaN/inf -> None. Sin redondear."""
    if o is None or isinstance(o, (str, bool)):
        return o
    if isinstance(o, enum.Enum):
        return _plain(o.value)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return _num(o)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _plain(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, Mapping):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, np.ndarray):
        return [_plain(v) for v in o.tolist()]
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    raise TypeError(f"no exportable: {type(o).__name__}")


def _arr(a, nd: int):
    return None if a is None else [_num(v, nd) for v in np.asarray(a, dtype=float).ravel()]


# --------------------------------------------------------------------------------------
# Bloques del JSON
# --------------------------------------------------------------------------------------
def _warnings_block(r: AnalysisResult) -> list[dict]:
    """Avisos del resultado + los siempre visibles (§9.3) + los de modo esfera/sin terreno si faltan."""
    ws = list(r.warnings)
    have = {w.code for w in ws}
    sphere = r.horizon.mode == HorizonMode.SMOOTH_SPHERE
    need = [c for c in ALWAYS_SHOWN_WARNINGS if not (c == WarningCode.DEM_EFFECTIVE_RESOLUTION and sphere)]
    if sphere:
        need.append(WarningCode.NO_DEM_SMOOTH_SPHERE)
    if r.score is not None and not r.score.terrain_data:
        need.append(WarningCode.NO_TERRAIN_DATA_SCORE)
    for c in need:
        if c not in have:
            ws.append(ScientificWarning(c, Severity.WARNING, STANDARD_WARNINGS_ES[c]))
            have.add(c)
    return [{"code": w.code.value, "severity": w.severity.value, "text_es": w.text_es, "context": w.context}
            for w in ws]


def _metrics_block(r: AnalysisResult) -> dict[str, dict]:
    """``{metric: {value, unit, lo, hi, truncated}}``; los flags ``*_truncated`` se pliegan en su métrica."""
    rows = comparison_table({"v": r.metrics})
    flags = {row["metric"]: bool(row["v"]) for row in rows if row["unit"] == "bool"}
    ranges = r.uncertainty.ranges if r.uncertainty is not None else {}
    out = {}
    for row in rows:
        name, unit = row["metric"], row["unit"]
        if unit == "bool":
            continue
        nd = _METRIC_DECIMALS[unit]
        rg = ranges.get(name)
        val = _num(row["v"], nd)
        out[name] = {
            "value": int(val) if unit == "count" and val is not None else val,
            "unit": unit,
            "lo": _num(rg.lo, nd) if rg is not None else None,
            "hi": _num(rg.hi, nd) if rg is not None else None,
            "truncated": any(flags.get(k, False) for k, p in _TRUNC_PARENT.items() if p == name),
        }
    return out


def _windows_block(r: AnalysisResult) -> dict[str, list[dict]]:
    tl = r.timeline
    return {kind: [{"start_utc": et_to_utc_str(w.start_et), "end_utc": et_to_utc_str(w.end_et),
                    "duration_h": _num(w.duration_s / 3600.0, DECIMALS["h"]),
                    "left_truncated": bool(w.left_truncated), "right_truncated": bool(w.right_truncated)}
                   for w in getattr(tl, kind).windows] for kind in _WINDOW_KINDS}


def _power_block(r: AnalysisResult) -> Optional[dict]:
    if r.power is None:
        return None
    ps, sm = r.power, r.power_summary
    notes = [STANDARD_WARNINGS_ES[WarningCode.POWER_IS_ESTIMATE]]
    if bool(np.any(ps.t_clamped)):
        notes.append(STANDARD_WARNINGS_ES[WarningCode.COLD_EXTRAPOLATION])
    summary = daily = None
    if sm is not None:
        summary = {k: v for k, v in _plain(sm).items() if k != "daily"}
        daily = [{"day_utc": et_to_utc_str(d.day_start_et), "e_rel": _num(d.e_rel, DECIMALS["power_rel"]),
                  "peak_p_rel": _num(d.peak_p_rel, DECIMALS["power_rel"]),
                  "hours_above_useful": _num(d.hours_above_useful, DECIMALS["h"])} for d in sm.daily]
    return {"panel_id": ps.panel_id, "mounting": _plain(ps.mounting), "summary": summary,
            "daily": daily or [], "assumptions": notes}


def _slope_block(r: AnalysisResult) -> Optional[dict]:
    """Pendiente en huella a r = 50 y 100 m junto al veredicto (``slope_r50``/``slope_r100``) y borde del DEM (esquema 1.3.0)."""
    if r.slope_r50 is None and r.slope_r100 is None:
        return None
    return {"slope_r50": _plain(r.slope_r50), "slope_r100": _plain(r.slope_r100),
            "dem_edge_distance_m": _num(r.dem_edge_distance_m, DECIMALS["m"]),
            "footprint_touches_dem_edge": r.footprint_touches_dem_edge}


def _score_block(r: AnalysisResult) -> Optional[dict]:
    s = r.score
    if s is None:
        return None
    return {
        "profile_id": s.profile_id, "score": _num(s.score, 4), "score_min": _num(s.score_min, 4),
        "score_max": _num(s.score_max, 4), "partial": bool(s.partial), "terrain_data": bool(s.terrain_data),
        "missing_keys": list(s.missing_keys), "status": s.status.value, "attenuated": bool(s.attenuated),
        "weakest_key": s.weakest_key,
        "subscores": [{"key": x.key, "label": x.label, "value": _num(x.value), "unit": x.unit,
                       "s": _num(x.s, 4), "weight": _num(x.weight, 4), "penalty_pct": _num(x.penalty_pct, 2),
                       "score_if_one": _num(x.score_if_one, 4)} for x in s.subscores],
        "gates": [{"id": g.id, "status": g.status.value, "reason": g.reason} for g in s.gates],
        "confidence": _plain(s.confidence), "assumptions": list(s.assumptions),
    }


def _provenance(r: AnalysisResult, params: Optional[Mapping[str, object]]) -> dict:
    h, tl = r.horizon, r.timeline
    k = r.kernels
    kernels = ({"files": list(k.files), "kernel_hash": k.kernel_hash, "spiceypy_version": k.spiceypy_version}
               if k is not None else
               {"files": [], "kernel_hash": r.sky.kernel_hash, "spiceypy_version": None})
    dm = r.dem_meta
    dem = None if dm is None else {
        "key": dm.key, "sha256": dm.sha256, "pixel_size_m": _num(dm.pixel_size_m),
        "bounds_xy_m": [_num(v) for v in dm.bounds_xy_m], "effective_resolution_m": _num(dm.effective_resolution_m)}
    p = {
        "visibility": {w: getattr(tl, w).criterion for w in _WINDOW_KINDS},
        "timeline": _plain(tl.params),
        "power": None if r.power is None else {"panel_id": r.power.panel_id, "mounting": _plain(r.power.mounting),
                                               "useful_threshold": _num(r.power_summary.useful_threshold)
                                               if r.power_summary is not None else None},
        "score": None,
    }
    p.update({k2: _plain(v) for k2, v in (params or {}).items()})
    return {
        "frame": SPICE_FRAME, "abcorr": SPICE_ABCORR, "moon_radius_m": MOON_RADIUS_M,
        "kernels": kernels, "dem": dem,
        "horizon": {"cache_key": h.cache_key, "mode": h.mode.value, "params": _plain(h.params),
                    "cov_min_m": _num(h.cov_min_m, DECIMALS["m"]), "cov_median_m": _num(h.cov_median_m, DECIMALS["m"]),
                    "limited_fraction": _num(np.mean(h.limited), DECIMALS["fraction"]),
                    "h_sphere_deg": _num(h.h_sphere_deg, DECIMALS["deg"]),
                    "dem_sha256": h.dem_sha256, "far_sha256": h.far_sha256},
        "params": p,
    }


def _observer_block(r: AnalysisResult) -> dict:
    o = r.observer
    return {"lat_deg": _num(o.lat_deg, 6), "lon_deg_e": _num(o.lon_deg_e, 6), "x_m": _num(o.x_m, 3),
            "y_m": _num(o.y_m, 3), "height_m": _num(o.height_m, 3), "mode": o.mode.value,
            "ground_z_m": _num(o.ground_z_m, 3), "site_id": o.site_id if o.site_id is not None else r.request.site_id,
            "gazetteer_id": r.request.gazetteer_id}


def _txt(x) -> str:
    """Texto CSV de origen externo: neutraliza la inyección de fórmulas (``= + - @``, tab, CR iniciales) con un ``'``."""
    t = "" if x is None else str(x)
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


def _local(utc: str, tz: str) -> tuple[str, float]:
    """UTC ``...Z`` -> (hora local ISO 8601 con offset, offset en horas) en la zona IANA ``tz`` (horario de verano incluido)."""
    from zoneinfo import ZoneInfo
    dt = datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
    return dt.isoformat(), dt.utcoffset().total_seconds() / 3600.0


def _contact_rows(contacts) -> list[dict]:
    rows = []
    for c in contacts:
        su, eu = et_to_utc_str(c.start_et), et_to_utc_str(c.end_et)
        (sl, so), (el, eo) = _local(su, c.tz), _local(eu, c.tz)
        rows.append({
            "station_id": c.station_id, "start_utc": su, "end_utc": eu, "start_local": sl, "end_local": el, "tz": c.tz,
            "start_utc_offset_h": _num(so, 2), "end_utc_offset_h": _num(eo, 2),
            "start_solar_h": _num(c.start_solar_h, DECIMALS["h"]), "end_solar_h": _num(c.end_solar_h, DECIMALS["h"]),
            "duration_h": _num(c.duration_s / 3600.0, DECIMALS["h"]),
            "max_moon_el_deg": _num(c.max_moon_el_deg, DECIMALS["deg"]),
            "max_earth_el_deg": _num(c.max_earth_el_deg, DECIMALS["deg"]),
            "left_truncated": bool(c.left_truncated), "right_truncated": bool(c.right_truncated)})
    return rows


def _daily_rows(contacts, et0: float, et1: float) -> list[dict]:
    """Tabla diaria de contactos por día UTC: horas de enlace de red (unión), solape, hueco y horas por estación."""
    from lsi.astronomy.ground_stations import daily_contact_table
    return [{"day_utc": r["day_utc"], "link_hours": _num(r["link_hours"], DECIMALS["h"]),
             "overlap_hours": _num(r["overlap_hours"], DECIMALS["h"]), "gap_hours": _num(r["gap_hours"], DECIMALS["h"]),
             "stations": [{"station_id": sid, "hours": _num(v["hours"], DECIMALS["h"])}
                          for sid, v in sorted(r["stations"].items())]}
            for r in daily_contact_table(contacts, et0, et1)]


def _link_blocks(r: AnalysisResult) -> tuple[dict, list[dict]]:
    """(bloque ``link``, lista ``contacts``). Sin red de enlace: ``network`` null, métricas null y listas vacías.
    ``station_min_elevation_deg`` = elevación mínima FORZADA para todas las estaciones (null = la propia de cada una);
    ``max_moon_el_deg`` por estación = máximo sobre sus ventanas de contacto."""
    lk, m, q = r.link, r.metrics, r.request
    if lk is None:
        return ({"network": None, "direction": None, "network_fraction_by_direction": None,
                 "min_earth_elevation_deg": None, "station_min_elevation_deg": None,
                 "link_fraction": None, "network_fraction": None, "hours_per_day_mean": None, "hours_per_day_min": None,
                 "longest_window_h": None, "longest_window_truncated": False, "max_gap_h": None,
                 "max_gap_truncated": False, "stations": [], "daily": [], "notes": []}, [])
    from lsi.astronomy.ground_stations import get_network
    try:  # coordenadas: ``StationLinkSummary`` no las lleva; se recuperan de la misma red que usó el pipeline
        geo = {s.id: s for s in get_network(lk.network_id, custom=q.link_custom,
                                           min_elevation_deg=q.link_station_min_elevation_deg,
                                           link_direction=q.link_direction).stations}
    except (ValueError, KeyError):
        geo = {}
    rows = _contact_rows(lk.contacts)
    el: dict = {}
    for c in rows:
        if c["max_moon_el_deg"] is not None:
            el[c["station_id"]] = max(el.get(c["station_id"], -math.inf), c["max_moon_el_deg"])

    def hrs(s):
        return None if s is None else _num(s / 3600.0, DECIMALS["h"])

    stations = []
    for s in lk.stations:
        g = geo.get(s.station_id)
        stations.append({
            "station_id": s.station_id, "name": s.name, "complex": s.complex,
            "lat_deg": _num(g.lat_deg, 6) if g else None, "lon_deg_e": _num(g.lon_deg_e, 6) if g else None, "tz": s.tz,
            "min_elevation_deg": _num(s.min_elevation_deg, DECIMALS["deg"]), "confidence": s.confidence,
            "link_fraction": _num(s.link_fraction, DECIMALS["fraction"]),
            "moon_visible_fraction": _num(s.moon_visible_fraction, DECIMALS["fraction"]),
            "link_hours_per_day": _num(s.link_hours_per_day, DECIMALS["h"]), "n_windows": int(s.n_windows),
            "longest_window_h": hrs(s.longest_window_s), "max_moon_el_deg": el.get(s.station_id)})
    block = {
        "network": {"id": lk.network_id, "label": lk.network_label},
        "direction": q.link_direction,   # 1.2.0: sentido del enlace (receive | transmit | both); fija la elevación mínima de las estaciones
        "network_fraction_by_direction": (None if r.network_fraction_by_direction is None else
                                          {k: _num(v, DECIMALS["fraction"]) for k, v in r.network_fraction_by_direction.items()}),
        "min_earth_elevation_deg": _num(lk.min_earth_elevation_deg, DECIMALS["deg"]),
        "station_min_elevation_deg": _num(q.link_station_min_elevation_deg, DECIMALS["deg"]),
        "link_fraction": _num(m.link_fraction, DECIMALS["fraction"]),
        "network_fraction": _num(m.network_fraction, DECIMALS["fraction"]),
        "hours_per_day_mean": _num(m.link_hours_per_day_mean, DECIMALS["h"]),
        "hours_per_day_min": _num(m.link_hours_per_day_min, DECIMALS["h"]),
        "longest_window_h": hrs(m.longest_link_window_s), "longest_window_truncated": bool(m.longest_link_window_truncated),
        "max_gap_h": hrs(m.max_link_gap_s), "max_gap_truncated": bool(m.max_link_gap_truncated),
        "stations": stations, "daily": _daily_rows(lk.contacts, r.timeline.et0, r.timeline.et1),
        "notes": list(lk.notes)}
    return block, rows


def result_to_dict(result: AnalysisResult, generated_utc: Optional[str] = None,
                   params: Optional[Mapping[str, object]] = None) -> dict:
    """Estructura JSON del §7 (sin numpy, NaN -> None, floats redondeados). Determinista salvo ``generated_utc``.

    ``params``: objetos de parámetros extra (p. ej. ``{"visibility": VisibilityParams, "score": ScoreParams}``)
    que sustituyen sus entradas en ``provenance.params``.
    """
    h = result.horizon
    link, contacts = _link_blocks(result)
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "generated_utc": generated_utc,
        "lsi_version": LSI_VERSION,
        "request": _plain(result.request),
        "observer": _observer_block(result),
        "provenance": _provenance(result, params),
        "metrics": _metrics_block(result),
        "windows": _windows_block(result),
        "events": [{"utc": et_to_utc_str(e.et), "body": e.body.value, "kind": e.kind.value,
                    "az_deg": _num(e.az_deg, DECIMALS["deg"]), "truncated": bool(e.truncated)}
                   for e in result.timeline.events],
        "horizon": {"az_deg": _arr(h.az_deg, DECIMALS["deg"]), "h_lb_deg": _arr(h.h_lb_deg, DECIMALS["deg"]),
                    "h_ub_deg": _arr(h.h_ub_deg, DECIMALS["deg"]), "r_cov_m": _arr(h.r_cov_m, DECIMALS["m"]),
                    "limited": [bool(v) for v in h.limited]},
        "timeseries_ref": "timeseries.csv",
        "power": _power_block(result),
        "slope_footprint": _slope_block(result),
        "score": _score_block(result),
        "warnings": _warnings_block(result),
        "link": link,
        "contacts": contacts,
    }


def _dumps(d: Mapping) -> bytes:
    return (json.dumps(d, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def write_json(result: AnalysisResult, path: Path, generated_utc: Optional[str] = None,
               params: Optional[Mapping[str, object]] = None) -> Path:
    """Escribe ``result_to_dict`` con indent=2, UTF-8 y ``\\n``; valida el esquema antes de escribir."""
    d = result_to_dict(result, generated_utc, params)
    validate_export(d)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_dumps(d))
    return path


# --------------------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------------------
def _cell(x, nd: Optional[int] = None) -> str:
    """Celda CSV: vacía si None/NaN; bool en minúsculas; decimales fijos con punto."""
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "true" if x else "false"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    v = float(x)
    if not math.isfinite(v):
        return ""
    return f"{round(v, nd) + 0.0:.{nd}f}" if nd is not None else repr(v)


def _write_csv(path: Path, columns: Sequence[str], rows) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        w.writerows(rows)
    return path


def _timeseries_rows(r: AnalysisResult):
    s, vis, h = r.sky, r.timeline.series, r.horizon
    n = len(vis.et)
    if len(s.et) != n:
        raise ValueError(f"sky.et ({len(s.et)}) y timeline.series.et ({n}) tienen distinta longitud")
    az = np.asarray(h.az_deg, dtype=float)
    hz = np.asarray(h.h_lb_deg, dtype=float)
    hs = np.interp(np.asarray(s.sun.az_deg) % 360.0, az, hz, period=360.0)
    he = np.interp(np.asarray(s.earth.az_deg) % 360.0, az, hz, period=360.0)
    if r.power is not None:  # p_rel vive en los nodos de integración; si no coinciden con la rejilla, se interpola
        pe = np.asarray(r.power.et, dtype=float)
        p = np.asarray(r.power.p_rel, dtype=float)
        p_rel = p if len(pe) == n and np.array_equal(pe, vis.et) else np.interp(vis.et, pe, p)
    else:
        p_rel = np.full(n, np.nan)
    D = DECIMALS
    for i in range(n):
        yield [et_to_utc_str(vis.et[i]), _cell(vis.et[i], D["s"]),
               _cell(s.sun.az_deg[i], D["deg"]), _cell(s.sun.el_deg[i], D["deg"]), _cell(vis.sun.f[i], D["fraction"]),
               _cell(int(vis.sun.state[i])), _cell(s.sun.dist_km[i], D["km"]), _cell(hs[i], D["deg"]),
               _cell(s.earth.az_deg[i], D["deg"]), _cell(s.earth.el_deg[i], D["deg"]),
               _cell(vis.earth.f[i], D["fraction"]), _cell(int(vis.earth.state[i])),
               _cell(s.earth.dist_km[i], D["km"]), _cell(he[i], D["deg"]),
               _cell(bool(vis.sun.unknown_relevant[i])), _cell(bool(vis.earth.unknown_relevant[i])),
               _cell(p_rel[i], D["power_rel"])]


def write_csv_bundle(result: AnalysisResult, out_dir: Path, generated_utc: Optional[str] = None,
                     params: Optional[Mapping[str, object]] = None) -> dict[str, Path]:
    """timeseries.csv, windows.csv, horizon.csv, metrics.csv y metadata.json (columnas ``CSV_*_COLUMNS``); con enlace DTE
    activo además estaciones.csv, contactos.csv y contactos_diarios.csv (claves ``link_stations/contacts/daily``).

    CSV: UTF-8, coma, punto decimal, ``utc`` ISO 8601, sin filas de comentario; NaN/None = celda vacía,
    booleanos ``true``/``false``, ``*_state`` = ``VisibilityState`` entero (0 oculto, 1 parcial, 2 visible).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = result_to_dict(result, generated_utc, params)
    validate_export(d)
    paths = {"timeseries": _write_csv(out / "timeseries.csv", CSV_TIMESERIES_COLUMNS, _timeseries_rows(result))}
    paths["windows"] = _write_csv(out / "windows.csv", CSV_WINDOWS_COLUMNS, (
        [kind, w["start_utc"], w["end_utc"], _cell(w["duration_h"], DECIMALS["h"]),
         _cell(w["left_truncated"]), _cell(w["right_truncated"])]
        for kind in _WINDOW_KINDS for w in d["windows"][kind]))
    hz = d["horizon"]
    ub = hz["h_ub_deg"] or [None] * len(hz["az_deg"])
    paths["horizon"] = _write_csv(out / "horizon.csv", CSV_HORIZON_COLUMNS, (
        [_cell(a, DECIMALS["deg"]), _cell(lb, DECIMALS["deg"]), _cell(u, DECIMALS["deg"]),
         _cell(rc, DECIMALS["m"]), _cell(lim)]
        for a, lb, u, rc, lim in zip(hz["az_deg"], hz["h_lb_deg"], ub, hz["r_cov_m"], hz["limited"])))
    paths["metrics"] = _write_csv(out / "metrics.csv", CSV_METRICS_COLUMNS, (
        [name, _cell(m["value"], _METRIC_DECIMALS[m["unit"]]), m["unit"],
         _cell(m["lo"], _METRIC_DECIMALS[m["unit"]]), _cell(m["hi"], _METRIC_DECIMALS[m["unit"]]),
         _cell(m["truncated"])] for name, m in d["metrics"].items()))
    if d["link"]["network"] is not None:
        lkd = d["link"]
        paths["link_stations"] = _write_csv(out / "estaciones.csv", CSV_LINK_STATIONS_COLUMNS, (
            [_txt(s["station_id"]), _txt(s["name"]), _txt(s["complex"]), _cell(s["lat_deg"], 6), _cell(s["lon_deg_e"], 6),
             _txt(s["tz"]), _cell(s["min_elevation_deg"], DECIMALS["deg"]), _txt(s["confidence"]),
             _cell(s["link_fraction"], DECIMALS["fraction"]), _cell(s["moon_visible_fraction"], DECIMALS["fraction"]),
             _cell(s["link_hours_per_day"], DECIMALS["h"]), _cell(s["n_windows"]), _cell(s["longest_window_h"], DECIMALS["h"]),
             _cell(s["max_moon_el_deg"], DECIMALS["deg"])] for s in lkd["stations"]))
        paths["link_contacts"] = _write_csv(out / "contactos.csv", CSV_LINK_CONTACTS_COLUMNS, (
            [_txt(c["station_id"]), c["start_utc"], c["end_utc"], c["start_local"], c["end_local"], _txt(c["tz"]),
             _cell(c["start_utc_offset_h"], 2), _cell(c["end_utc_offset_h"], 2),
             _cell(c["start_solar_h"], DECIMALS["h"]), _cell(c["end_solar_h"], DECIMALS["h"]),
             _cell(c["duration_h"], DECIMALS["h"]), _cell(c["max_moon_el_deg"], DECIMALS["deg"]),
             _cell(c["max_earth_el_deg"], DECIMALS["deg"]), _cell(c["left_truncated"]), _cell(c["right_truncated"])]
            for c in d["contacts"]))
        paths["link_daily"] = _write_csv(out / "contactos_diarios.csv", CSV_LINK_DAILY_COLUMNS, (
            [x["day_utc"], _cell(x["link_hours"], DECIMALS["h"]), _cell(x["overlap_hours"], DECIMALS["h"]),
             _cell(x["gap_hours"], DECIMALS["h"]), _cell(len(x["stations"])),
             _txt(";".join(y["station_id"] for y in x["stations"])),
             _txt(";".join(f"{y['station_id']}={_cell(y['hours'], DECIMALS['h'])}" for y in x["stations"]))]
            for x in lkd["daily"]))
    meta = {k: d[k] for k in ("schema_version", "generated_utc", "lsi_version", "request", "observer",
                              "provenance", "warnings")}
    mp = out / "metadata.json"
    mp.write_bytes(_dumps(meta))
    paths["metadata"] = mp
    return paths


def comparison_to_csv(rows: list[dict], path: Path) -> Path:
    """Tabla de comparación: ``CSV_COMPARISON_COLUMNS`` + una columna por sitio (orden de aparición)."""
    sites: list[str] = []
    for row in rows:
        sites += [k for k in row if k not in CSV_COMPARISON_COLUMNS and k not in sites]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def fmt(v):
        return _cell(v) if isinstance(v, (bool, np.bool_, int, np.integer)) or v is None else _cell(v, 6)

    return _write_csv(path, [*CSV_COMPARISON_COLUMNS, *(_txt(x) for x in sites)],
                      ([row["metric"], row["unit"], *(fmt(row.get(s)) for s in sites)] for row in rows))


# --------------------------------------------------------------------------------------
# Validador de esquema (ligero, sin dependencias)
# --------------------------------------------------------------------------------------
_TOP_KEYS = ("schema_version", "generated_utc", "lsi_version", "request", "observer", "provenance", "metrics",
             "windows", "events", "horizon", "timeseries_ref", "power", "score", "warnings")
_PRE_SLOPE_VERSIONS = ("1.2.0",)   # sin ``slope_footprint`` ni ``power.summary.iam_model``: siguen siendo válidos
_LEGACY_VERSIONS = ("1.0.0",)   # exports sin ``link``/``contacts``: siguen siendo válidos
_NO_DIRECTION_VERSIONS = ("1.1.0",)   # con ``link``/``contacts`` pero sin ``link.direction``/``network_fraction_by_direction``: siguen siendo válidos
_LINK_KEYS_1_2 = ("direction", "network_fraction_by_direction")
_LINK_KEYS = ("network", "min_earth_elevation_deg", "station_min_elevation_deg", "link_fraction", "network_fraction",
              "hours_per_day_mean", "hours_per_day_min", "longest_window_h", "longest_window_truncated", "max_gap_h",
              "max_gap_truncated", "stations", "daily", "notes")
_LINK_STATION_KEYS = ("station_id", "name", "complex", "lat_deg", "lon_deg_e", "tz", "min_elevation_deg", "confidence",
                      "link_fraction", "moon_visible_fraction", "link_hours_per_day", "n_windows", "longest_window_h",
                      "max_moon_el_deg")
_LINK_CONTACT_KEYS = ("station_id", "start_utc", "end_utc", "start_local", "end_local", "tz", "start_utc_offset_h",
                      "end_utc_offset_h", "start_solar_h", "end_solar_h", "duration_h", "max_moon_el_deg",
                      "max_earth_el_deg", "left_truncated", "right_truncated")
_LINK_DAILY_KEYS = ("day_utc", "link_hours", "overlap_hours", "gap_hours", "stations")
_SCORE_KEYS = ("profile_id", "score", "score_min", "score_max", "partial", "terrain_data", "missing_keys",
               "status", "subscores", "gates", "confidence", "assumptions")


def _nonfinite(o, path: str, errs: list):
    if isinstance(o, float) and not math.isfinite(o):
        errs.append(f"{path}: valor no finito ({o}); debe ser null")
    elif isinstance(o, dict):
        for k, v in o.items():
            _nonfinite(v, f"{path}.{k}", errs)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _nonfinite(v, f"{path}[{i}]", errs)


def _validate_link(lk: dict, contacts: list, errs: list, version: str = "") -> None:
    errs += [f"link: falta '{k}'" for k in _LINK_KEYS + (() if version in _NO_DIRECTION_VERSIONS else _LINK_KEYS_1_2) if k not in lk]
    if lk.get("direction") not in (None, *LINK_DIRECTIONS):
        errs.append(f"link.direction={lk.get('direction')!r} no es uno de {LINK_DIRECTIONS}")
    for name, keys in (("stations", _LINK_STATION_KEYS), ("daily", _LINK_DAILY_KEYS)):
        rows = lk.get(name)
        if not isinstance(rows, list):
            errs.append(f"link.{name}: debe ser lista")
            continue
        for i, x in enumerate(rows):
            miss = [k for k in keys if not isinstance(x, dict) or k not in x]
            if miss:
                errs.append(f"link.{name}[{i}]: faltan {miss}")
    ids = {x.get("station_id") for x in lk.get("stations") or [] if isinstance(x, dict)}
    for i, c in enumerate(contacts):
        miss = [k for k in _LINK_CONTACT_KEYS if not isinstance(c, dict) or k not in c]
        if miss:
            errs.append(f"contacts[{i}]: faltan {miss}")
        elif c["station_id"] not in ids:
            errs.append(f"contacts[{i}]: station_id {c['station_id']!r} no está en link.stations")
    net = lk.get("network")
    if net is None:
        if lk.get("stations") or contacts or lk.get("daily"):
            errs.append("link: network=null exige stations, daily y contacts vacíos")
    elif not (isinstance(net, dict) and {"id", "label"} <= set(net)):
        errs.append("link.network: debe ser null o {id, label}")


def validate_export(d: Any) -> None:
    """Comprueba el dict del §7; lanza ``ExportSchemaError`` con TODOS los fallos encontrados."""
    errs: list[str] = []
    if not isinstance(d, dict):
        raise ExportSchemaError(f"esquema inválido: se esperaba dict, llegó {type(d).__name__}")
    legacy = d.get("schema_version") in _LEGACY_VERSIONS
    for k in _TOP_KEYS + (() if legacy else ("link", "contacts")):
        if k not in d:
            errs.append(f"falta la clave obligatoria '{k}'")
    if d.get("schema_version") not in (EXPORT_SCHEMA_VERSION, *_PRE_SLOPE_VERSIONS, *_NO_DIRECTION_VERSIONS, *_LEGACY_VERSIONS):
        errs.append(f"schema_version={d.get('schema_version')!r}, se esperaba {EXPORT_SCHEMA_VERSION!r} "
                    f"(o los anteriores {_PRE_SLOPE_VERSIONS[0]!r}, {_NO_DIRECTION_VERSIONS[0]!r}, {_LEGACY_VERSIONS[0]!r})")
    sf = d.get("slope_footprint")
    if sf is not None and d.get("schema_version") == EXPORT_SCHEMA_VERSION:
        errs += [f"slope_footprint: falta '{k}'" for k in ("slope_r50", "slope_r100", "dem_edge_distance_m",
                                                          "footprint_touches_dem_edge") if not isinstance(sf, dict) or k not in sf]
    _nonfinite(d, "$", errs)

    mode = (d.get("observer") or {}).get("mode")
    if mode not in {m.value for m in HorizonMode}:
        errs.append(f"observer.mode={mode!r} no es uno de {[m.value for m in HorizonMode]}")

    codes = {w.get("code") for w in d.get("warnings") or [] if isinstance(w, dict)}
    for c in ALWAYS_SHOWN_WARNINGS:
        if c == WarningCode.DEM_EFFECTIVE_RESOLUTION and mode == HorizonMode.SMOOTH_SPHERE.value:
            continue
        if c.value not in codes:
            errs.append(f"warnings: falta el aviso siempre visible '{c.value}'")
    for i, w in enumerate(d.get("warnings") or []):
        if not isinstance(w, dict) or not {"code", "severity", "text_es", "context"} <= set(w):
            errs.append(f"warnings[{i}]: faltan campos (code, severity, text_es, context)")

    for name, m in (d.get("metrics") or {}).items():
        if not isinstance(m, dict) or not {"value", "unit", "lo", "hi", "truncated"} <= set(m):
            errs.append(f"metrics.{name}: faltan campos (value, unit, lo, hi, truncated)")
    w = d.get("windows") or {}
    for kind in _WINDOW_KINDS:
        if not isinstance(w.get(kind), list):
            errs.append(f"windows.{kind}: debe ser lista")
            continue
        for i, x in enumerate(w[kind]):
            if not isinstance(x, dict) or not {"start_utc", "end_utc", "duration_h", "left_truncated",
                                               "right_truncated"} <= set(x):
                errs.append(f"windows.{kind}[{i}]: faltan campos")

    hz = d.get("horizon") or {}
    lens = {k: len(hz[k]) for k in ("az_deg", "h_lb_deg", "r_cov_m", "limited") if isinstance(hz.get(k), list)}
    if len(lens) < 4:
        errs.append("horizon: faltan az_deg/h_lb_deg/r_cov_m/limited")
    elif len(set(lens.values())) != 1:
        errs.append(f"horizon: longitudes distintas {lens}")
    elif isinstance(hz.get("h_ub_deg"), list) and len(hz["h_ub_deg"]) != lens["az_deg"]:
        errs.append("horizon.h_ub_deg: longitud distinta de az_deg")

    sc = d.get("score")
    if sc is not None:
        if not isinstance(sc, dict):
            errs.append("score: debe ser objeto o null")
        else:
            errs += [f"score: falta '{k}'" for k in _SCORE_KEYS if k not in sc]
            subs = sc.get("subscores") or []
            miss = set(sc.get("missing_keys") or [])
            if bool(sc.get("partial")) != bool(miss):
                errs.append("score: 'partial' debe ser true si y solo si hay missing_keys")
            if sc.get("terrain_data") is False and "terrain" not in miss:
                errs.append("score: terrain_data=false exige 'terrain' en missing_keys")
            for i, x in enumerate(subs):
                if not isinstance(x, dict) or "key" not in x or "s" not in x:
                    errs.append(f"score.subscores[{i}]: faltan key/s")
                elif x["key"] in miss:
                    if x["s"] is not None:
                        errs.append(f"score.subscores[{i}] ('{x['key']}'): no evaluado, s debe ser null")
                elif not isinstance(x["s"], (int, float)) or isinstance(x["s"], bool) or not 0.0 <= x["s"] <= 1.0:
                    errs.append(f"score.subscores[{i}] ('{x['key']}'): s={x['s']!r} fuera de [0,1]")
    pw = d.get("power")
    if pw is not None and not (isinstance(pw, dict) and {"panel_id", "mounting", "summary", "daily",
                                                         "assumptions"} <= set(pw)):
        errs.append("power: faltan campos (panel_id, mounting, summary, daily, assumptions)")

    if not legacy and isinstance(d.get("link"), dict) and isinstance(d.get("contacts"), list):
        _validate_link(d["link"], d["contacts"], errs, str(d.get("schema_version")))

    if errs:
        raise ExportSchemaError("esquema de exportación inválido:\n- " + "\n- ".join(errs))
