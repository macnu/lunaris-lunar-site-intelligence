"""Ventanas temporales de Sol/Tierra, eventos y cuenta atrás (matematica.md §5, arquitectura.md §5.10).

Rejilla gruesa (600 s) → transiciones de ``f > thr`` → refinamiento por bisección vectorizada (todos los cruces a la vez,
~10 llamadas a ``f_fn`` hasta 1 s). Álgebra de intervalos reutilizada de ``analysis.metrics``.
Límite conocido: un hueco/evento más corto que el paso de rejilla no se detecta (diseño: paso ≤ 14 min con ΔA=0.25°).
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from lsi.analysis import metrics as mt
from lsi.astronomy import ground_stations as gs
from lsi.astronomy import spice_engine
from lsi.contracts import (
    Body, Countdown, Event, EventKind, FloatArray, HorizonResult, LinkResult, SkySeries, StationLinkSummary,
    TimelineParams, TimelineResult, VisibilityParams, VisibilitySeries, WindowSet,
)
from lsi.simulation.visibility import body_visibility, link_fraction, make_fraction_fn, visibility_series
from lsi.terrain.horizon import unknown_relevant_mask


def refine_crossings(f_fn: Callable[[FloatArray], FloatArray], et_lo: FloatArray, et_hi: FloatArray, thr: float,
                     xtol_s: float = 1.0) -> FloatArray:
    """Bisección vectorizada (misma iteración para todos los eventos): ET de cada cruce de ``f > thr`` en [lo, hi].

    Supone un único cruce por intervalo y estados distintos en los extremos. Devuelve el punto medio del último
    intervalo (error ≤ xtol/2).
    """
    lo, hi = np.array(et_lo, dtype=np.float64), np.array(et_hi, dtype=np.float64)
    if lo.size == 0:
        return lo
    s_lo = np.asarray(f_fn(lo)) > thr
    while np.max(hi - lo) > xtol_s:
        mid = 0.5 * (lo + hi)
        same = (np.asarray(f_fn(mid)) > thr) == s_lo
        lo, hi = np.where(same, mid, lo), np.where(same, hi, mid)
    return 0.5 * (lo + hi)


def _crossings(et, f, thr, f_fn, xtol_s):
    """(t, is_rise, up_at_start, up_at_end): cruces en orden temporal; sin f_fn interpola f linealmente en la rejilla."""
    mask = np.asarray(f) > thr   # NaN → False
    idx = np.flatnonzero(mask[:-1] != mask[1:])
    lo, hi = et[idx], et[idx + 1]
    if f_fn is not None:
        t = refine_crossings(f_fn, lo, hi, thr, xtol_s)
    else:
        t = lo + (thr - f[idx]) / (f[idx + 1] - f[idx]) * (hi - lo)
    return t, ~mask[idx], bool(mask[0]), bool(mask[-1])


def _windows(cr, et0, et1, label, criterion, merge_tol_s) -> WindowSet:
    t, is_rise, up0, up1 = cr
    starts = np.concatenate(([et0] if up0 else [], t[is_rise]))
    ends = np.concatenate((t[~is_rise], [et1] if up1 else []))
    iv = mt.merge(np.column_stack((starts, ends)), merge_tol_s)
    return mt.window_set(iv, et0, et1, label, criterion)


def find_windows(et, f, thr: float, label: str, criterion: str, *,
                 f_fn: Callable[[FloatArray], FloatArray] | None = None, xtol_s: float = 1.0,
                 merge_tol_s: float = 1.0) -> WindowSet:
    """Ventanas f>thr; con f_fn refina cada transición por bisección vectorizada hasta xtol_s; trunca en bordes."""
    et, f = np.asarray(et, dtype=np.float64), np.asarray(f, dtype=np.float64)
    return _windows(_crossings(et, f, thr, f_fn, xtol_s), et[0], et[-1], label, criterion, merge_tol_s)


def union_windows(a: WindowSet, b: WindowSet, tol_s: float = 1.0, label: str = "union") -> WindowSet:
    """Unión: fusiona si el hueco ≤ tol_s."""
    return mt.window_set(mt.union(mt.intervals(a), mt.intervals(b), tol_s), a.t0_et, a.t1_et, label)


def intersect_windows(a: WindowSet, b: WindowSet, label: str = "overlap") -> WindowSet:
    """Intersección O(n+m); queda truncada la que toca un borde del periodo."""
    return mt.window_set(mt.intersection(mt.intervals(a), mt.intervals(b)), a.t0_et, a.t1_et, label,
                         f"{a.label} ∩ {b.label}")


def complement_windows(ws: WindowSet, label: str = "dark") -> WindowSet:
    """Complemento sobre [t0, t1]; marca truncadas las que tocan los bordes."""
    return mt.window_set(mt.complement(mt.intervals(ws), ws.t0_et, ws.t1_et), ws.t0_et, ws.t1_et, label,
                         f"no {ws.label}")


def _thr(body: Body, p: VisibilityParams) -> float:
    return p.sun_f_thr if body == Body.SUN else p.earth_f_thr


def _events(body, t, is_rise, lat, lon, h) -> list[Event]:
    if len(t) == 0:
        return []
    az = spice_engine.body_track(t, lat, lon, body, h).az_deg
    return [Event(float(ti), body, EventKind.RISE if r else EventKind.SET, float(a))
            for ti, r, a in zip(t, is_rise, az)]


def build_link(link: gs.LinkContext, sky: SkySeries, horizon: HorizonResult, vis: VisibilitySeries,
               vis_params: VisibilityParams, params: TimelineParams, earth: WindowSet, *, contacts: bool = True
               ) -> LinkResult:
    """Enlace DTE = Tierra visible con margen de elevación ∧ alguna estación ve la Luna (y por estación).

    Con margen 0 las ventanas geométricas son las ya refinadas de ``earth``; con margen > 0 se refinan igual por bisección
    con el horizonte elevado. La cobertura de red viene de ``link.coverage`` (UNA vez por rejilla, común a todos los sitios).
    """
    et, et0, et1 = sky.et, float(sky.et[0]), float(sky.et[-1])
    cov, margin = link.coverage, link.min_earth_elevation_deg
    if margin:
        thr = vis_params.earth_f_thr
        f = link_fraction(sky.earth, horizon, vis_params, margin)
        fn = make_fraction_fn(Body.EARTH, sky.lat_deg, sky.lon_deg_e, sky.height_m, horizon, vis_params, margin_deg=margin)
        earth = _windows(_crossings(et, f, thr, fn, params.refine_xtol_s), et0, et1, "earth_margin",
                         f"f_earth(H+{margin:g}°) > {thr:g}", params.merge_tol_s)
    geo = mt.intervals(earth)
    st_iv = cov.station_intervals()
    net_iv = cov.any_intervals()   # fusiona los huecos espurios de traspaso (B2): ground_stations.handoff_merge_tol_s
    ws = lambda iv, label, crit: mt.window_set(iv, et0, et1, label, crit)   # noqa: E731
    by = {s.id: ws(mt.intersection(geo, iv), f"link_{s.id}", f"Tierra con margen ∧ {s.id} ve la Luna ≥ {s.min_elevation_deg:g}°")
          for s, iv in zip(cov.network.stations, st_iv)}
    link_ws = ws(mt.intersection(geo, net_iv), "link", f"Tierra con margen {margin:g}° ∧ red {cov.network.id}")
    T = et1 - et0
    sums = []
    for s, iv, el in zip(cov.network.stations, st_iv, cov.el_deg):
        w = by[s.id]
        d = [x.duration_s for x in w.windows]
        sums.append(StationLinkSummary(
            s.id, s.name, s.complex, s.tz, s.min_elevation_deg, s.confidence,
            mt.total_duration(mt.intervals(w), et0, et1) / T, mt.total_duration(iv, et0, et1) / T,
            mt.total_duration(mt.intervals(w), et0, et1) / T * 24.0, len(d), max(d, default=0.0)))
    cw = tuple(gs.contact_windows(cov, geo, sky.earth.el_deg, t0=et0, t1=et1)) if contacts else ()
    return LinkResult(cov.network.id, cov.network.label, float(margin), earth, link_ws,
                      ws(net_iv, "network", f"alguna estación de {cov.network.id} ve la Luna"), by, cw, tuple(sums),
                      cov.network.notes)


def _union_all(ivs) -> FloatArray:
    out = mt._EMPTY
    for iv in ivs:
        out = mt.union(out, iv)
    return out


def run_timeline(sky: SkySeries, horizon: HorizonResult, vis_params: VisibilityParams,
                 params: TimelineParams, vis: VisibilitySeries | None = None,
                 link: gs.LinkContext | None = None) -> TimelineResult:
    """Ventanas Sol/Tierra/solape/oscuridad con refinamiento, eventos con az, y variante pesimista (H_ub).

    ``link`` (opcional): añade ``TimelineResult.link`` (enlace DTE, ``build_link``); None = solo geometría.
    """
    vis = vis or visibility_series(sky, horizon, vis_params)
    et, et0, et1 = sky.et, float(sky.et[0]), float(sky.et[-1])
    args = (sky.lat_deg, sky.lon_deg_e, sky.height_m)
    out, events, pess = {}, [], {}
    for body, bv, key in ((Body.SUN, vis.sun, "sun"), (Body.EARTH, vis.earth, "earth")):
        thr = _thr(body, vis_params)
        cr = _crossings(et, bv.f, thr, make_fraction_fn(body, *args, horizon, vis_params), params.refine_xtol_s)
        out[key] = _windows(cr, et0, et1, key, f"f_{key} > {thr:g}", params.merge_tol_s)
        events += _events(body, cr[0], cr[1], *args)
        if bv.f_pess is not None:
            crp = _crossings(et, bv.f_pess, thr, make_fraction_fn(body, *args, horizon, vis_params, "ub"),
                             params.refine_xtol_s)
            pess[key] = _windows(crp, et0, et1, f"{key}_pess", f"f_{key}(H_ub) > {thr:g}", params.merge_tol_s)
    events.sort(key=lambda e: e.et)
    lk = None if link is None else build_link(link, sky, horizon, vis, vis_params, params, out["earth"])
    return TimelineResult(
        et0=et0, et1=et1, params=params, sun=out["sun"], earth=out["earth"],
        overlap=intersect_windows(out["sun"], out["earth"]), dark=complement_windows(out["sun"]),
        events=tuple(events), series=vis, sun_pess=pess.get("sun"), earth_pess=pess.get("earth"), link=lk)


def countdown(now_et: float, body: Body, lat_deg: float, lon_deg_e: float, height_m: float,
              horizon: HorizonResult, vis_params: VisibilityParams, params: TimelineParams) -> Countdown:
    """Próxima transición del cuerpo en ≤ countdown_search_days: puesta si está arriba, salida si no."""
    body = Body(body)
    thr = _thr(body, vis_params)
    days = params.countdown_search_days
    et = spice_engine.et_grid(now_et, now_et + days * 86400.0, params.step_s)
    track = spice_engine.body_track(et, lat_deg, lon_deg_e, body, height_m)
    bv = body_visibility(track, horizon, vis_params)
    t, is_rise, up, _ = _crossings(
        et, bv.f, thr, make_fraction_fn(body, lat_deg, lon_deg_e, height_m, horizon, vis_params),
        params.refine_xtol_s)
    if len(t) == 0:
        return Countdown(body, float(now_et), up, None, None, False, float(days))
    ev = _events(body, t[:1], is_rise[:1], lat_deg, lon_deg_e, height_m)[0]
    i = int(np.searchsorted(et, t[0], side="right")) - 1   # nodos de rejilla [i, i+1] que enmarcan el evento
    sl = slice(i, i + 2)
    approx = bool(unknown_relevant_mask(horizon, track.az_deg[sl], track.el_deg[sl], track.radius_deg[sl]).any())
    return Countdown(body, float(now_et), up, ev, ev.et - float(now_et), approx, float(days))
