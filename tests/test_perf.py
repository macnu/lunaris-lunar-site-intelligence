"""Presupuestos de rendimiento de arquitectura §10 (presupuestos en config/simulation.json: performance).

Tolerante: umbral = presupuesto × 2 (margen de máquina), mejor de 3 mediciones, y el tiempo medido SE IMPRIME
(``pytest -m perf -s`` o ``-rP``). Si se supera el umbral pero un calibrador fijo de CPU (np.sin, ref. 0,065 s en la
máquina de desarrollo) muestra la máquina ≥ 2× más lenta/cargada, el test sale como ``xfail`` documentado en vez de
fallar en falso; si el calibrador es normal, es un fallo real. ``LSI_PERF_STRICT=1`` desactiva el xfail.
"""
import os
import time
from pathlib import Path

import numpy as np
import pytest

from lsi import pipeline as P
from lsi.contracts import AnalysisRequest, DemLayer, MountingSpec, MountingType
from lsi.data import catalog
from lsi.terrain import horizon as hz

pytestmark = [pytest.mark.perf, pytest.mark.slow, pytest.mark.needs_spice, pytest.mark.needs_dem]
ROOT = Path(__file__).resolve().parents[1]
MARGIN = 2.0
CAL_REF_S = 0.065
SITE23 = (-85.994785, 359.764216)
VAT = MountingSpec(MountingType.VERTICAL_AZ_TRACKING)
START, END30, END365 = "2026-12-01T00:00:00", "2026-12-31T00:00:00", "2027-12-01T00:00:00"
BUDGET_30D_UNC_S = 20.0     # RNF-01 (timeline 30 d con refinamiento ≤ 20 s); §10 no fija presupuesto propio para incertidumbre


@pytest.fixture(scope="module")
def ctx():
    c = P.build_context(ROOT)
    if "Site23" not in c.dem_refs:
        pytest.skip("falta el DEM Site23")
    return c


def machine_slowdown() -> float:
    x = np.linspace(0.0, 1.0, 2_000_000)
    return min(_cal(x) for _ in range(3)) / CAL_REF_S


def _cal(x) -> float:
    t = time.perf_counter()
    for _ in range(5):
        np.sin(x * 3.0).sum()
    return time.perf_counter() - t


def check(name: str, fn, budget_s: float, reps: int = 3) -> float:
    limit = budget_s * MARGIN
    best = min(_timed(fn) for _ in range(reps))
    print(f"\n[perf] {name}: {best:.2f} s (presupuesto {budget_s:g} s, umbral ×{MARGIN:g} = {limit:g} s)")
    if best > limit:
        slow = machine_slowdown()
        msg = f"{name}: {best:.2f} s > {limit:g} s; calibrador de CPU ×{slow:.1f} respecto a la referencia"
        if slow >= 2.0 and os.environ.get("LSI_PERF_STRICT") != "1":
            pytest.xfail("máquina cargada o lenta, no regresión demostrada. " + msg)
        pytest.fail(msg)
    return best


def _timed(fn) -> float:
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_horizon_one_point_cold(ctx, tmp_path):
    """Horizonte de un punto (1440 az, DEM 5 m + campo lejano), caché en frío: < 2 s."""
    obs, _ = P.resolve_observer(ctx, *SITE23, 2.0)
    hp = catalog.horizon_params(ctx.cfg, 2.0)
    window = P._layer(ctx.dem_refs[obs.dem_key], DemLayer.SURF)                 # lectura del DEM fuera del cronómetro
    far = P._far(str(P._raw(ctx)), round(obs.x_m, 3), round(obs.y_m, 3), hp.r_max_m)
    n = iter(range(100))

    def cold():
        h = hz.compute_horizon(window, obs, hp, cache_dir=tmp_path / f"c{next(n)}", far=far)   # directorio nuevo: sin caché
        assert len(h.az_deg) == 1440 and np.all(np.isfinite(h.h_lb_deg))
    check("horizonte de un punto (frío)", cold, ctx.cfg["performance"]["budget_horizon_s"])


def _run(ctx, end, **kw):
    r = P.run_analysis(ctx, AnalysisRequest(*SITE23, START, end, panel_id="tj-gaas-lander-body", mounting=VAT, **kw))
    assert r.score is not None and 0.0 <= r.score.score <= 100.0
    return r


def test_30_days_10min_horizon_cached(ctx):
    """30 días a 10 min (SPICE + visibilidad + refinamiento + potencia + score por ventana), horizonte en caché: < 3 s."""
    _run(ctx, END30)                                                              # calienta caché de horizonte/DEM
    check("30 días (horizonte en caché)", lambda: _run(ctx, END30), ctx.cfg["performance"]["budget_30d_10min_s"])


def test_30_days_with_uncertainty(ctx):
    """30 días con incertidumbre (escenarios de DEM/σz/discretización; sus horizontes salen de caché tras el primero)."""
    _run(ctx, END30, with_uncertainty=True)
    check("30 días con incertidumbre", lambda: _run(ctx, END30, with_uncertainty=True), BUDGET_30D_UNC_S)


def test_one_year_horizon_cached(ctx):
    """1 año a 10 min (52 560 pasos), horizonte en caché: < 20 s."""
    _run(ctx, END365)
    check("1 año (horizonte en caché)", lambda: _run(ctx, END365), ctx.cfg["performance"]["budget_1y_10min_s"], reps=2)


def test_calibrator_is_sane():
    """El calibrador mide algo finito y positivo (si no, el xfail de arriba no significaría nada)."""
    assert 0.0 < machine_slowdown() < 1e3
