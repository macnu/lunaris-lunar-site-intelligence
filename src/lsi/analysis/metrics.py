"""Métricas del periodo y álgebra de intervalos (matematica.md §5.3, arquitectura.md §5.13).

Un conjunto de intervalos es un array ``(n, 2)`` float64 de pares ``[a, b)`` ordenados y disjuntos.
Sin SPICE ni terreno: solo NumPy. Las operaciones son deterministas y vectorizadas.
"""
from __future__ import annotations

import dataclasses
from typing import Mapping, Optional

import numpy as np

from lsi.contracts import (
    FloatArray,
    LinkResult,
    SiteMetrics,
    SkySeries,
    TimelineResult,
    VisibilityParams,
    Window,
    WindowSet,
    HorizonResult,
)

_EMPTY = np.empty((0, 2), dtype=np.float64)


# --------------------------------------------------------------------------------------
# Álgebra de intervalos
# --------------------------------------------------------------------------------------
def _as_iv(iv) -> FloatArray:
    a = np.asarray(iv, dtype=np.float64)
    return _EMPTY if a.size == 0 else a.reshape(-1, 2)


def merge(iv, tol: float = 0.0) -> FloatArray:
    """Ordena, descarta vacíos y fusiona intervalos con hueco <= ``tol`` (hueco < xtol = ruido numérico)."""
    a = _as_iv(iv)
    a = a[a[:, 1] > a[:, 0]]
    if len(a) == 0:
        return _EMPTY
    a = a[np.argsort(a[:, 0], kind="stable")]
    cmax = np.maximum.accumulate(a[:, 1])
    new = np.empty(len(a), dtype=bool)
    new[0] = True
    new[1:] = a[1:, 0] > cmax[:-1] + tol
    first = np.flatnonzero(new)
    last = np.append(first[1:] - 1, len(a) - 1)
    return np.column_stack((a[first, 0], cmax[last]))


def union(a, b, tol: float = 0.0) -> FloatArray:
    """A ∪ B fusionando huecos <= tol."""
    return merge(np.vstack((_as_iv(a), _as_iv(b))), tol)


def intersection(a, b) -> FloatArray:
    """A ∩ B (barrido por eventos, O((n+m) log(n+m))); descarta solapes de longitud 0."""
    a, b = merge(a), merge(b)
    if len(a) == 0 or len(b) == 0:
        return _EMPTY
    pts = np.concatenate((a[:, 0], a[:, 1], b[:, 0], b[:, 1]))
    delta = np.concatenate((np.ones(len(a)), -np.ones(len(a)), np.ones(len(b)), -np.ones(len(b))))
    order = np.argsort(pts, kind="stable")
    pts, cover = pts[order], np.cumsum(delta[order])
    ok = (cover[:-1] == 2) & (pts[1:] > pts[:-1])
    return np.column_stack((pts[:-1][ok], pts[1:][ok]))


def clip(iv, t0: float, t1: float) -> FloatArray:
    """Recorta a [t0, t1] y descarta lo vacío."""
    a = np.clip(_as_iv(iv), t0, t1)
    return a[a[:, 1] > a[:, 0]]


def complement(iv, t0: float, t1: float) -> FloatArray:
    """[t0, t1] \\ A."""
    a = merge(clip(iv, t0, t1))
    starts = np.concatenate(([t0], a[:, 1]))
    stops = np.concatenate((a[:, 0], [t1]))
    ok = stops > starts
    return np.column_stack((starts[ok], stops[ok]))


def total_duration(iv, t0: Optional[float] = None, t1: Optional[float] = None) -> float:
    """Σ(b−a), opcionalmente recortada a [t0, t1]."""
    a = _as_iv(iv) if t0 is None else clip(iv, t0, t1)
    return float(np.sum(a[:, 1] - a[:, 0]))


def windows_from_mask(t: FloatArray, mask, t1: Optional[float] = None) -> FloatArray:
    """Ventanas ``[t_i, t_j)`` de las rachas True de ``mask`` sobre la rejilla ``t``.

    El fin es el primer instante False (o ``t1``, por defecto ``t[-1]``, si la racha llega al final).
    La resolución es la de la rejilla; el refinamiento sub-paso es cosa de ``simulation.timeline``.
    """
    t = np.asarray(t, dtype=np.float64)
    m = np.asarray(mask, dtype=bool)
    if t.shape != m.shape:
        raise ValueError("t y mask deben tener la misma forma")
    if len(t) == 0:
        return _EMPTY
    t1 = float(t[-1]) if t1 is None else float(t1)
    d = np.diff(np.concatenate(([False], m, [False])).astype(np.int8))
    i, j = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    ends = np.where(j < len(t), t[np.minimum(j, len(t) - 1)], t1)
    return np.column_stack((t[i], ends))


def window_set(iv, t0: float, t1: float, label: str, criterion: str = "") -> WindowSet:
    """Convierte intervalos en ``WindowSet``; marca como truncada la que toca t0 (izq.) o t1 (der.)."""
    a = clip(merge(iv), t0, t1)
    wins = tuple(Window(float(s), float(e), bool(s <= t0), bool(e >= t1)) for s, e in a)
    return WindowSet(label=label, windows=wins, t0_et=float(t0), t1_et=float(t1), criterion=criterion)


def intervals(ws: WindowSet) -> FloatArray:
    """``WindowSet`` → array (n, 2)."""
    return _as_iv([(w.start_et, w.end_et) for w in ws.windows])


def longest_window(ws: WindowSet) -> tuple[float, bool]:
    """(duración s, truncada) de la ventana más larga (la primera si hay empate); (0, False) si no hay."""
    if not ws.windows:
        return 0.0, False
    d = np.array([w.duration_s for w in ws.windows])
    w = ws.windows[int(np.argmax(d))]
    return float(d.max()), bool(w.left_truncated or w.right_truncated)


# --------------------------------------------------------------------------------------
# Métricas del periodo
# --------------------------------------------------------------------------------------
def _mean_trapz(t: FloatArray, f: FloatArray) -> float:
    span = t[-1] - t[0]
    return float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(t)) / span) if len(t) > 1 and span > 0 else float("nan")


def _nanmax(x: FloatArray) -> float:
    return float(np.nanmax(x)) if np.any(np.isfinite(x)) else float("nan")


def compute_metrics(tl: TimelineResult, sky: SkySeries, horizon: HorizonResult,
                    vis_params: VisibilityParams) -> SiteMetrics:
    """Fracciones, ventana más larga, oscuridad máxima (con flag truncada), solape y fracciones desconocidas.
    Si ``tl.link`` existe añade las métricas de enlace DTE (``link_metrics``); ``earth_fraction`` sigue siendo la geometría.

    ``horizon`` y ``vis_params`` no intervienen: los umbrales ya están en ``tl`` (firma por contrato).
    """
    T = tl.et1 - tl.et0
    if not T > 0:
        raise ValueError("periodo vacío")
    frac = lambda ws: total_duration(intervals(ws), tl.et0, tl.et1) / T  # noqa: E731
    ls, ls_t = longest_window(tl.sun)
    md, md_t = longest_window(tl.dark)
    vis = tl.series
    return SiteMetrics(
        period_s=float(T),
        solar_fraction=frac(tl.sun),
        effective_illumination=_mean_trapz(vis.et, vis.sun.f),
        earth_fraction=frac(tl.earth),
        overlap_fraction=frac(tl.overlap),
        longest_sun_window_s=ls,
        longest_sun_window_truncated=ls_t,
        max_darkness_s=md,
        max_darkness_truncated=md_t,
        longest_earth_window_s=longest_window(tl.earth)[0],
        longest_overlap_s=longest_window(tl.overlap)[0],
        n_sun_windows=len(tl.sun.windows),
        n_earth_windows=len(tl.earth.windows),
        max_sun_elevation_deg=_nanmax(sky.sun.el_deg),
        max_earth_elevation_deg=_nanmax(sky.earth.el_deg),
        unknown_fraction_sun=float(np.mean(vis.sun.unknown_relevant)),
        unknown_fraction_earth=float(np.mean(vis.earth.unknown_relevant)),
        **({} if tl.link is None else link_metrics(tl.link, tl.et0, tl.et1)),
    )


def _utc_day_edges(et0: float, et1: float) -> FloatArray:
    """[et0, medianoches UTC dentro de (et0, et1), et1] (sin SPICE: tabla de segundos intercalares de contracts; tolerancia
    de 50 ms porque la conversión pura ignora TDB−TT < 2 ms)."""
    from datetime import timedelta
    from lsi.contracts import et_to_utc_datetime, utc_datetime_to_et
    tol = 0.05
    d = et_to_utc_datetime(et0 + tol).replace(hour=0, minute=0, second=0, microsecond=0)
    edges = [et0]
    while True:
        d += timedelta(days=1)
        e = utc_datetime_to_et(d)
        if e >= et1 - tol:
            break
        edges.append(e)
    return np.array(edges + [et1])


def link_metrics(lk: LinkResult, et0: float, et1: float) -> dict:
    """Campos opcionales de ``SiteMetrics`` para el enlace: fracción, horas por día UTC (media y mínima de los días
    COMPLETOS), ventana más larga, hueco máximo sin enlace (con flag truncada si toca el borde) y fracción por estación."""
    T = et1 - et0
    iv = intervals(lk.link)
    total = total_duration(iv, et0, et1)
    edges = _utc_day_edges(et0, et1)
    lo, hi = edges[:-1], edges[1:]
    if len(iv):
        cov = np.clip(np.minimum(iv[None, :, 1], hi[:, None]) - np.maximum(iv[None, :, 0], lo[:, None]), 0.0, None).sum(axis=1)
    else:
        cov = np.zeros(len(lo))
    full = (hi - lo) >= 86400.0 - 2.0                  # día UTC completo (86400 s; los segundos intercalares ya no existen en el rango)
    gaps = complement(iv, et0, et1)
    k = int(np.argmax(gaps[:, 1] - gaps[:, 0])) if len(gaps) else 0
    gmax = float(gaps[k, 1] - gaps[k, 0]) if len(gaps) else 0.0
    gtr = bool(len(gaps) and (gaps[k, 0] <= et0 or gaps[k, 1] >= et1))   # el hueco toca el borde: es cota inferior
    ll, ll_t = longest_window(lk.link)
    return dict(
        link_fraction=total / T,
        network_fraction=total_duration(intervals(lk.network_cover), et0, et1) / T,
        link_hours_per_day_mean=total / T * 24.0,
        link_hours_per_day_min=float(cov[full].min() / 3600.0) if full.any() else None,
        longest_link_window_s=ll, longest_link_window_truncated=ll_t,
        max_link_gap_s=gmax, max_link_gap_truncated=gtr,
        link_by_station={sid: total_duration(intervals(w), et0, et1) / T for sid, w in lk.by_station.items()})


def daily_table(tl: TimelineResult) -> list[dict]:
    """Por día: iluminación media, horas de Sol, de Tierra y de solape.

    Los días son bloques de 86400 s desde ``tl.et0`` (= medianoche UTC si el periodo empieza a las 00:00 UTC;
    el último puede ser parcial y se reparte sobre su duración real). Sin SPICE no se convierte ET↔UTC.
    """
    edges = np.arange(tl.et0, tl.et1, 86400.0)
    edges = np.append(edges, tl.et1)
    lo, hi = edges[:-1], edges[1:]

    def hours(ws: WindowSet) -> FloatArray:
        w = intervals(ws)
        if len(w) == 0:
            return np.zeros(len(lo))
        cov = np.minimum(w[None, :, 1], hi[:, None]) - np.maximum(w[None, :, 0], lo[:, None])
        return np.clip(cov, 0.0, None).sum(axis=1) / 3600.0

    t, f = tl.series.et, tl.series.sun.f
    cum = np.concatenate(([0.0], np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(t))))
    integ = np.interp(hi, t, cum) - np.interp(lo, t, cum)
    illum = integ / (hi - lo)
    hs, he, ho = hours(tl.sun), hours(tl.earth), hours(tl.overlap)
    return [
        {"day": i, "start_et": float(lo[i]), "mean_illumination": float(illum[i]),
         "sun_hours": float(hs[i]), "earth_hours": float(he[i]), "overlap_hours": float(ho[i])}
        for i in range(len(lo))
    ]


LINK_FIELDS = ("link_fraction", "network_fraction", "link_hours_per_day_mean", "link_hours_per_day_min",
               "longest_link_window_s", "longest_link_window_truncated", "max_link_gap_s", "max_link_gap_truncated",
               "link_by_station")
_UNITS = {"period_s": "s", "longest_sun_window_s": "s", "max_darkness_s": "s", "longest_earth_window_s": "s",
          "longest_overlap_s": "s", "max_sun_elevation_deg": "deg", "max_earth_elevation_deg": "deg",
          "n_sun_windows": "count", "n_earth_windows": "count", "link_hours_per_day_mean": "h",
          "link_hours_per_day_min": "h", "longest_link_window_s": "s", "max_link_gap_s": "s"}


def comparison_table(results: Mapping[str, SiteMetrics]) -> list[dict]:
    """Filas ``{metric, unit, <site_id>: valor...}``; una fila por campo de ``SiteMetrics`` (flags = bool). Los campos de
    enlace (opcionales) solo aparecen si algún sitio los tiene calculados."""
    rows = []
    link_off = all(m.link_fraction is None for m in results.values())
    for fld in dataclasses.fields(SiteMetrics):
        if fld.name == "link_by_station" or (link_off and fld.name in LINK_FIELDS):
            continue   # enlace: filas solo si hay enlace calculado; el desglose por estación va en ``AnalysisResult.link``
        unit = "bool" if fld.name.endswith("_truncated") else _UNITS.get(fld.name, "fraction")
        row = {"metric": fld.name, "unit": unit}
        for sid, m in results.items():
            row[sid] = getattr(m, fld.name)
        rows.append(row)
    return rows
