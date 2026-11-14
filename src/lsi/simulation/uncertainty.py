"""Propagación de incertidumbre como RANGO por métrica (arquitectura §5.11, matematica.md §7.5).

Cotas de sensibilidad, no estadística. Escenarios, cada uno = una pasada de ``run_timeline`` con otro horizonte:

- ``coverage_ub``: H_lb := H_ub (el terreno no cubierto sube hasta ``z_up``): extremo pesimista por cobertura.
- ``sigma_plus`` / ``sigma_minus``: z ± k·σz (TOTERR) en muestras y suelo del observador (solo con DEM y σ).
- ``az_step_<ΔA>``: la rejilla azimutal original submuestreada a ΔA (por defecto 0.5°; es exactamente lo que
  daría recalcular a ΔA porque la rejilla de 0.25° contiene a la de 0.5°).
- ``height_plus`` / ``height_minus``: altura del observador ± Δ (solo si ``observer_height_delta_m`` > 0).

El escenario nominal usa H_lb (optimista); el rango es [min, max] sobre nominal y escenarios.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

import numpy as np

from lsi.analysis.metrics import compute_metrics
from lsi.contracts import (
    DemWindow, HorizonParams, HorizonResult, ObserverPoint, Range, ScenarioResult, SiteMetrics, SkySeries,
    TimelineParams, UncertaintyParams, UncertaintyResult, VisibilityParams,
)
from lsi.simulation.timeline import run_timeline
from lsi.terrain.horizon import compute_horizon, smooth_sphere_result

RANGE_METRICS = ("solar_fraction", "effective_illumination", "earth_fraction", "overlap_fraction",
                 "longest_sun_window_s", "max_darkness_s", "longest_earth_window_s")


LINK_RANGE_METRICS = ("link_fraction", "longest_link_window_s", "max_link_gap_s")   # solo con enlace DTE


def _metrics(sky: SkySeries, horizon: HorizonResult, vp: VisibilityParams, tp: TimelineParams,
             link=None) -> SiteMetrics:
    """Métricas con un horizonte alternativo (sin H_ub: no hace falta la variante pesimista). ``link`` = LinkContext:
    el enlace se recalcula con el mismo horizonte alternativo (la cobertura de red no cambia: es del cielo, no del terreno)."""
    h = dataclasses.replace(horizon, h_ub_deg=None)
    return compute_metrics(run_timeline(sky, h, vp, tp, link=link), sky, h, vp)


def _decimate(h: HorizonResult, k: int) -> HorizonResult:
    sl = slice(None, None, k)
    return dataclasses.replace(h, az_deg=h.az_deg[sl], h_lb_deg=h.h_lb_deg[sl], r_cov_m=h.r_cov_m[sl],
                               limited=h.limited[sl], h_ub_deg=None)


def run_uncertainty(ctx_window: Optional[DemWindow], sigma_window: Optional[DemWindow], observer: ObserverPoint,
                    horizon_nominal: HorizonResult, sky: SkySeries, vis_params: VisibilityParams,
                    tl_params: TimelineParams, hz_params: HorizonParams, params: UncertaintyParams,
                    metrics_nominal: SiteMetrics, *, far: Optional[DemWindow] = None,
                    cache_dir: Optional[Path] = None, link=None) -> UncertaintyResult:
    """Recalcula escenarios (H_ub, z±kσz, ΔA, altura±Δ) y devuelve ``Range`` por métrica; sin DEM solo altura.

    ``far``/``cache_dir`` se pasan a ``compute_horizon`` (mismo campo lejano que el nominal).
    """
    scen: list[ScenarioResult] = []
    run = lambda name, desc, hor: scen.append(  # noqa: E731
        ScenarioResult(name, desc, _metrics(sky, hor, vis_params, tl_params, link)))
    hz = dataclasses.replace(hz_params, compute_upper_bound=False)
    dem = ctx_window is not None and horizon_nominal.mode.value == "dem"

    if params.use_coverage_bound and horizon_nominal.h_ub_deg is not None and horizon_nominal.limited.any():
        run("coverage_ub", "Terreno fuera de cobertura a z_up (H_ub): cota pesimista",
            dataclasses.replace(horizon_nominal, h_lb_deg=horizon_nominal.h_ub_deg))

    if dem and params.use_sigma_z and sigma_window is not None and params.k_sigma > 0:
        for sign, name in ((+1, "sigma_plus"), (-1, "sigma_minus")):
            run(name, f"z {'+' if sign > 0 else '−'} {params.k_sigma:g}·σz (TOTERR)",
                compute_horizon(ctx_window, observer, hz, sigma_window, sign, params.k_sigma, cache_dir, far=far))

    if params.use_discretization:
        k = max(1, round(params.alt_az_step_deg / (360.0 / len(horizon_nominal.az_deg))))
        if k > 1 and np.ptp(horizon_nominal.h_lb_deg) > 0:   # con H constante la discretización no cambia nada
            run(f"az_step_{params.alt_az_step_deg:g}", f"Rejilla azimutal submuestreada a {params.alt_az_step_deg:g}°",
                _decimate(horizon_nominal, k))

    d = params.observer_height_delta_m
    if d > 0:
        for sign, name in ((+1, "height_plus"), (-1, "height_minus")):
            hp = dataclasses.replace(hz, observer_height_m=max(0.0, hz.observer_height_m + sign * d))
            hor = (compute_horizon(ctx_window, observer, hp, cache_dir=cache_dir, far=far) if dem
                   else smooth_sphere_result(observer, hp))
            run(name, f"Altura del observador {sign * d:+g} m", hor)

    ranges = {}
    for m in RANGE_METRICS + (LINK_RANGE_METRICS if metrics_nominal.link_fraction is not None else ()):
        nom = float(getattr(metrics_nominal, m))
        vals = [nom] + [float(getattr(s.metrics, m)) for s in scen]
        ranges[m] = Range(nom, min(vals), max(vals))
    return UncertaintyResult(scenarios=tuple(scen), ranges=ranges)
