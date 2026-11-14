"""Precalcula el mapa de idoneidad (caché por hash en data/processed/suitability/) y lista el TOP-N por sitio.

Uso: python scripts/precompute_suitability.py [Site04 Site11 Site23] [--profile lander_solar_no_rhu --profile rover]
         [--step-m 250] [--days 365] [--step-s 1800] [--top 5] [--min-sep-m 1000] [--validate 12] [--no-cache]
         [--duration 7 --duration 14 --duration 30] [--window-step-days 1]

``--duration D`` (repetible) evalúa ventanas de misión de D días en lugar de solo el año: el score, las puertas y la
oscuridad máxima se calculan DENTRO de cada ventana deslizante y se busca la mejor fecha de inicio por punto. ``--days`` es
entonces el rango de fechas de inicio (365 = todo un año); se simula ``days + max(D)`` para que también quepan las últimas
ventanas. Escribe ``windows_<Site>_<perfil>_<hash10>.json`` (``schema_version`` ``lsi.suitability.windows/1``; resultados
con clave ``"<sitio>|<perfil>|<D>d"``).

``--link-network`` (defecto DSN) hace que ``f_earth``/``f_Tierra`` sea la fracción de ENLACE posible (Tierra con margen de
elevación ∧ alguna estación de la red viendo la Luna), no la Tierra geométrica; ``none`` recupera el comportamiento anterior.
``--link-direction`` (defecto ``receive``) elige el sentido del enlace: ``receive`` (elevación mínima de recepción, 6° DSN), ``transmit``
(10,1°) o ``both`` (intersección). Con enlace, s_earth lleva la continuidad absoluta (hueco máximo y horas por día) y la mejor fecha de
inicio de cada punto prefiere las que cumplen G7; cada candidato lleva ``gap_h`` (hueco máximo de su mejor ventana).

``--validate K`` compara K nodos (TOP-N + repartidos por el ranking) con el modelo fino (``pipeline.run_analysis``:
az 0.25°, 5 m, 600 s con refinamiento) y reporta la diferencia máxima de f_sol, f_Tierra, D_max y score.
Escribe además data/processed/suitability/<Site>_<perfil>_<hash10>.json con el TOP-N, tiempos y validación.
Idempotente: un mapa ya en caché no se recalcula.

**Incertidumbre REAL (``schema_revision`` 2; ``schema_version`` sigue en ``windows/1``).** Para el TOP-N (``--unc-top``, defecto = ``--top``) de cada sitio/duración/perfil se ejecuta
``pipeline.run_analysis(with_uncertainty=True)`` en la mejor fecha y cada entrada de ``top`` guarda, con nombres distintos:
``score_range_resolution`` = [score_min, score_max] del mapa (solo ±1 paso temporal en D_max: puede tener ancho cero) y
``score_range_uncertainty`` = rango entre escenarios H_ub, ±σz y ΔA del modelo fino, más ``score_fine``, ``scenario_scores`` y
``metric_ranges`` (f_sol, D_max, enlace). ``score_min``/``score_max`` se conservan como alias de la resolución (compatibilidad).
``--no-uncertainty`` los omite (solo el rango de resolución).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lsi import pipeline  # noqa: E402
from lsi.analysis import suitability_map as sm  # noqa: E402
from lsi.data import catalog  # noqa: E402

SITES = ("Site04", "Site11", "Site23")
WINDOWS_SCHEMA = sm.WINDOWS_SCHEMA   # schema_version /1 + schema_revision 2: score_range_resolution / score_range_uncertainty (ver suitability_map)


def top_table(m: sm.SuitabilityMap) -> str:
    rows = ["  #   lat (°)     lon (°E)    f_sol  f_enlace  D_max (h)  pend p90  score  puertas  eslabón débil"]
    rows += [f"  {s.rank}  {s.lat_deg:9.4f}  {s.lon_deg_e:9.4f}  {s.f_sun:6.3f}  {s.f_earth:7.3f}  {s.d_max_h:9.1f}  "
             f"{s.slope_p90_deg:7.1f}  {s.score:6.1f}  {s.gate_status:7s}  {s.weakest_key}" for s in m.top]
    return "\n".join(rows)


def window_table(sites: tuple) -> str:
    rows = ["  #   lat (°)     lon (°E)    inicio UTC           f_sol  f_enlace  D_max (h)  score [min-max]      puertas  días aptos"]
    rows += [f"  {s.rank}  {s.lat_deg:9.4f}  {s.lon_deg_e:9.4f}  {s.best_start_utc}  {s.f_sun:6.3f}  {s.f_earth:7.3f}  "
             f"{s.d_max_h:9.1f}  {s.score:5.1f} [{s.score_min:5.1f}-{s.score_max:5.1f}]  {s.gate_status:7s}  "
             f"{s.apt_start_days:g}/{s.n_starts}" for s in sites]
    return "\n".join(rows)


def add_uncertainty(ctx, top: list[dict], profile_id: str, params: sm.SuitabilityParams, n: int, log=print) -> None:
    """Añade a cada entrada de ``top`` el rango de resolución (renombrado) y, a las ``n`` primeras, la incertidumbre real."""
    for i, t in enumerate(top):
        t["score_range_resolution"] = [t["score_min"], t["score_max"]]
        t["score_range_resolution_note"] = "solo ±1 paso de rejilla en D_max (resolución temporal); NO es incertidumbre física"
        if i < n:
            t.update(sm.candidate_uncertainty(ctx, t, profile_id, params))
            lo, hi = t["score_range_uncertainty"]
            log(f"   TOP-{t['rank']} ({t['lat_deg']:.4f}, {t['lon_deg_e']:.4f}) {t['best_start_utc']}: score mapa {t['score']:.1f} "
                f"resolución [{t['score_min']:.1f}-{t['score_max']:.1f}] | fino {t['score_fine']:.1f} incertidumbre [{lo:.1f}-{hi:.1f}] "
                f"f_sol {t['metric_ranges']['f_sun']} D_max {t['metric_ranges']['d_max_h']} h")


def window_record(m: sm.SuitabilityMap, wm: sm.WindowMap, site: str, prof: str, night_limit_h, utc_of) -> dict:
    """Resumen JSON de una duración: TOP-N, recuentos y tabla columnar de todos los candidatos con su mejor inicio."""
    b = wm.best
    lat, lon = m.lat_lon
    la, lo = lat[wm.rows, wm.cols], lon[wm.rows, wm.cols]
    lim = np.inf if night_limit_h is None else night_limit_h
    r = lambda a, nd=4: [round(float(v), nd) for v in a]   # noqa: E731
    return dict(
        site=site, profile=prof, duration_days=wm.duration_days, step_days=wm.step_days, n_starts=wm.n_starts,
        first_start_utc=utc_of(wm.start_et[0]), last_start_utc=utc_of(wm.start_et[-1]), n_candidates=len(wm.rows),
        night_limit_h=night_limit_h,
        n_points_pass_night_at_best=int((b["d_max_h"] <= lim).sum()), n_points_all_gates_at_best=int((b["gate"] == 0).sum()),
        n_points_any_apt_start=int((b["apt_days"] > 0).sum()),
        apt_start_days=dict(median=float(np.median(b["apt_days"])), max=float(b["apt_days"].max())),
        top=[dataclasses.asdict(s) for s in wm.top],
        candidates=dict(lat_deg=r(la), lon_deg_e=r(lo), best_start_utc=[utc_of(t) for t in b["start_et"]],
                        score=r(b["score"], 2), score_min=r(b["score_min"], 2), score_max=r(b["score_max"], 2),
                        f_sun=r(b["f_sun"]), f_earth=r(b["f_earth"]), d_max_h=r(b["d_max_h"], 2),
                        gate=[int(g) for g in b["gate"]], apt_start_days=r(b["apt_days"], 2),
                        night_ok_start_days=r(b["night_ok_days"], 2),
                        gap_h=[None if not np.isfinite(v) else round(float(v), 2) for v in b["gap_h"]]))


def run(root: Path, sites, profiles, params: sm.SuitabilityParams, workers: int | None, validate: int, use_cache: bool,
        log=print, unc_top: int = 0) -> list[dict]:
    ctx = pipeline.build_context(root)
    out = []
    for site in sites:
        for prof in profiles:
            t0 = time.perf_counter()
            m = sm.suitability_map(ctx, site, prof, params, workers=workers, use_cache=use_cache, log=log)
            wall = time.perf_counter() - t0
            log(f"{site} [{prof}] {'caché' if m.cached else 'calculado'} en {wall:.1f} s (cálculo original {m.seconds:.1f} s); "
                f"{m.n_candidates} candidatos de {m.n_grid} nodos (límite de pendiente {m.slope_limit_deg:g}°)")
            if m.windows:
                from lsi.astronomy import spice_engine
                from lsi import pipeline as _p
                mission = _p._mission(ctx, catalog.score_profiles(ctx.cfg)[prof].mission_profile_id)
                t4 = mission.thresholds.get("max_dark_h_no_nuclear") if mission is not None else None
                lim = None if t4 is None or t4.value is None else float(t4.value)
                utc_of = lambda et: spice_engine.et_to_utc(float(et))   # noqa: E731
                res = {}
                for d, wm in m.windows.items():
                    rec = window_record(m, wm, site, prof, lim, utc_of)
                    add_uncertainty(ctx, rec["top"], prof, m.params, unc_top, log)
                    res[f"{site}|{prof}|{d:g}d"] = rec
                    log(f"-- {site} [{prof}] misión {d:g} d: {wm.n_starts} inicios ({rec['first_start_utc']} .. "
                        f"{rec['last_start_utc']}); puntos con D_max ≤ {lim} h en su mejor ventana: "
                        f"{rec['n_points_pass_night_at_best']}/{rec['n_candidates']}; con todas las puertas: "
                        f"{rec['n_points_all_gates_at_best']}")
                    log(window_table(wm.top))
                d_ = root / ctx.cfg["cache"]["dir"] / sm.KIND
                d_.mkdir(parents=True, exist_ok=True)
                (d_ / f"windows_{site}_{prof}_{m.cache_key[:10]}.json").write_text(
                    json.dumps(dict(schema_version=WINDOWS_SCHEMA, schema_revision=sm.WINDOWS_REVISION, module_version=sm.MODULE_VERSION, key=m.cache_key, params=dataclasses.asdict(m.params),
                                    seconds=m.seconds, wall_s=wall, cached=m.cached, results=res), indent=1, default=float),
                    encoding="utf-8")
                out.append(dict(site=site, profile=prof, results=res, wall_s=wall, seconds=m.seconds))
                continue
            log(top_table(m))
            rec = dict(site=site, profile=prof, key=m.cache_key, seconds=m.seconds, wall_s=wall, cached=m.cached,
                       n_grid=m.n_grid, n_candidates=m.n_candidates, slope_limit_deg=m.slope_limit_deg,
                       params=dataclasses.asdict(m.params), top=[dataclasses.asdict(s) for s in m.top])
            if validate:
                checks = [sm.fine_check(ctx, m, la, lo) for la, lo in sm.validation_points(m, validate)]
                rec["validation"] = checks
                rec["max_abs_diff"] = {k: max(abs(c["diff"][k]) for c in checks) for k in checks[0]["diff"]}
                log(f"  validación fina ({len(checks)} puntos): diferencia máxima "
                    + ", ".join(f"{k} {v:.4f}" for k, v in rec["max_abs_diff"].items()))
            d = root / ctx.cfg["cache"]["dir"] / sm.KIND
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{site}_{prof}_{m.cache_key[:10]}.json").write_text(json.dumps(rec, indent=1, default=float), encoding="utf-8")
            out.append(rec)
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    d = sm.SuitabilityParams()
    ap.add_argument("sites", nargs="*", default=list(SITES))
    ap.add_argument("--profile", action="append", help="perfil de score/misión (repetible); defecto lander_solar_no_rhu")
    ap.add_argument("--step-m", type=float, default=d.step_m)
    ap.add_argument("--days", type=float, default=d.days)
    ap.add_argument("--step-s", type=float, default=d.step_s)
    ap.add_argument("--start-utc", default=d.start_utc)
    ap.add_argument("--top", type=int, default=d.top_n)
    ap.add_argument("--min-sep-m", type=float, default=d.min_separation_m)
    ap.add_argument("--slope-limit", type=float, default=None, help="umbral de pendiente p90 (°); defecto = diseño del perfil")
    ap.add_argument("--duration", type=float, action="append", help="duración de misión en días (repetible)")
    ap.add_argument("--window-step-days", type=float, default=d.window_step_days)
    ap.add_argument("--unc-top", type=int, default=None, help="candidatos por duración con incertidumbre real (defecto = --top)")
    ap.add_argument("--no-uncertainty", action="store_true", help="no ejecutar la incertidumbre real (solo rango de resolución)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--validate", type=int, default=0, help="nº de nodos a comparar con el modelo fino")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--link-network", default=d.link_network or "none",
                    help="red terrestre del enlace DTE (DSN | ESTRACK | DSN+ESTRACK | none = solo geometría); f_Tierra = enlace posible")
    ap.add_argument("--min-earth-elevation", type=float, default=None,
                    help="margen de elevación de la Tierra en el lander (°); defecto = el del perfil (0°)")
    ap.add_argument("--station-min-elevation", type=float, default=None, help="fuerza la elevación mínima de las estaciones (°)")
    ap.add_argument("--link-direction", default=d.link_direction, choices=("receive", "transmit", "both"),
                    help="sentido del enlace: receive (6° DSN) | transmit (10,1°) | both (intersección)")
    a = ap.parse_args(argv)
    dur = tuple(sorted(set(a.duration or ())))
    p = dataclasses.replace(d, step_m=a.step_m, days=a.days + (max(dur) if dur else 0.0), step_s=a.step_s,
                            start_utc=a.start_utc, top_n=a.top, min_separation_m=a.min_sep_m, slope_limit_deg=a.slope_limit,
                            window_durations_days=dur, window_step_days=a.window_step_days,
                            window_start_days=a.days if dur else None,
                            link_network=None if a.link_network.lower() == "none" else a.link_network,
                            min_earth_elevation_deg=a.min_earth_elevation, link_station_min_elevation_deg=a.station_min_elevation,
                            link_direction=a.link_direction)
    t0 = time.perf_counter()
    run(ROOT, a.sites, a.profile or ["lander_solar_no_rhu"], p, a.workers, a.validate, not a.no_cache,
        unc_top=0 if a.no_uncertainty else (a.top if a.unc_top is None else a.unc_top))
    print(f"Total: {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
