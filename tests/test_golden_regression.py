"""Regresión dorada (§12.3): números del motor ya validado para los 3 sitios con DEM, vía el flujo del buscador.

Los valores viven en ``tests/golden/<site>.json`` (con sus tolerancias). El test FALLA si algo cambia fuera de tolerancia.
Si el cambio es INTENCIONADO (motor, DEM, kernels, config o parámetros del score), regenerar de forma consciente:

    set LSI_REGEN_GOLDEN=1 && python -m pytest tests/test_golden_regression.py -q      (cmd)
    $env:LSI_REGEN_GOLDEN=1; python -m pytest tests/test_golden_regression.py -q      (PowerShell)

y revisar ``git diff tests/golden`` explicando en el commit POR QUÉ cambian los números. No regenerar para «poner en verde».

**Regenerado el 2026-11-14 (cambio INTENCIONADO, SNAP AL MEJOR PUNTO):** el flujo del buscador ya no engancha al punto cubierto
más cercano sino al TOP-1 del mapa de idoneidad del DEM (lander sin RHU, 14 d: ``pipeline.snap_candidate(prefer="best")``).
Site04 (Shackleton: antes un punto sin Sol, f_sol 0, score 2,18) y Site11 (de Gerlache: antes f_sol 0,15, NO APTO) cambian de
punto (lat/lon, ``snap_distance_km``) y, con él, métricas, score y ventana; Site23 (dentro del DEM, sin snap) no se mueve. Se
añade ``snap_kind`` (exacto) para que un cambio de comportamiento del snap no pase inadvertido.

**Regenerado el 2026-11-14 (cierre del objetivo; dos cambios INTENCIONADOS):**
(1) SNAP LIMITADO AL RASGO: el mejor punto es el mejor candidato del mapa a ≤ radio·1,15 + 1 km del centro (radio = diámetro/2 del
gazetteer), no el TOP-1 de todo el DEM. Site04 (Shackleton): de rango 1 a 16,00 km del centro (≈5,5 km FUERA del borde) a rango 3 a
10,13 km (0,34 km DENTRO del borde, radio 10,46 km): lat/lon, ``snap_distance_km``, f_sol (0,86 → 0,66 en la ventana de 30 d), score
(97,4 → 94,7) y mejor fecha (06/12 → 12/12) cambian. Site11 (de Gerlache): de rango 1 a 21,05 km (4,7 km fuera del borde, radio 16,35)
a rango 4 a 16,55 km (0,20 km fuera, dentro del margen). Site23 (Malapert) no hace snap: su punto no se mueve.
(2) SCORE LIGADO AL PANEL (T39/RF-33): con ``panel_id`` la subpuntuación de Sol usa la energía efectiva = 0,5·P_rel medio + 0,5·duty
útil sobre la ventana de misión, y se evalúa G5. Site23: score 58,07 → 57,31 (rango 57,86-58,28 → 57,11-57,52); la potencia
(``pct_of_max``) y las métricas geométricas no cambian. Los demás campos de Site23 coinciden con el dorado anterior.
**Regenerado el 2026-11-14 (revision-enlace B1; cambio INTENCIONADO, solo Site11):** ``s_earth`` lleva la continuidad ABSOLUTA del enlace
(``site_score.continuity_factor``: ``2^(-hueco/hueco tolerado) * min(1, horas por día / mínimo útil)``). Site11 (de Gerlache, mejor fecha 16/12;
en su ventana de 14 d el enlace es 95 % con un hueco máximo de 16 h frente a 48 h tolerados: s_earth 1,00 → 0,79) baja de 98,24 a 94,97 (rango
94,62-94,97); verdicto APTO, fecha, métricas y ventana no cambian. Site04 y Site23 no se mueven (dentro de tolerancia): la mejor fecha de
Site04 (12/12) ya tiene enlace continuo (hueco 0). La mejor fecha ahora prefiere las que cumplen G7 (``choose_start``).
"""
import json
import os
from pathlib import Path

import pytest

from lsi import pipeline as P
from lsi.contracts import HorizonMode
from test_e2e import DEM_SITES, ROOT, df, ctx, find, flow_request  # noqa: F401  (fixtures ctx/df compartidos)

pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem, pytest.mark.slow]
GOLDEN = Path(__file__).parent / "golden"
REGEN = os.environ.get("LSI_REGEN_GOLDEN") == "1"
# Tolerancias absolutas (RNF-08: score ≤ 0,05 puntos; ventanas ≤ 1 s de refino → 60 s de holgura entre plataformas).
TOL = {"solar_fraction": 5e-4, "earth_fraction": 5e-4, "longest_sun_window_s": 60.0, "max_darkness_s": 60.0,
       "score": 0.05, "score_min": 0.05, "score_max": 0.05, "pct_of_max": 0.05, "snap_distance_km": 0.01,
       "lat_deg": 1e-5, "lon_deg_e": 1e-5,
       # enlace DTE (red DSN, margen 0°): cambio INTENCIONADO, valores nuevos (no alteran ningún dorado anterior)
       "link_fraction": 5e-4, "longest_link_window_s": 60.0, "max_link_gap_s": 60.0, "link_hours_per_day_mean": 0.012}
EXACT = ("verdict", "verdict_provisional", "best_start_utc", "window_start_utc", "window_end_utc", "n_starts", "dem_key", "snap_kind")


def measure(r) -> dict:
    m, s, o = r.metrics, r.score, r.observer
    return {
        "dem_key": o.dem_key, "lat_deg": o.lat_deg, "lon_deg_e": o.lon_deg_e, "snap_distance_km": o.snap_distance_km, "snap_kind": o.snap_kind,
        "solar_fraction": m.solar_fraction, "earth_fraction": m.earth_fraction,
        "longest_sun_window_s": m.longest_sun_window_s, "max_darkness_s": m.max_darkness_s,
        "score": s.score, "score_min": s.score_min, "score_max": s.score_max, "verdict": s.verdict,
        "verdict_provisional": s.verdict_provisional, "best_start_utc": s.best_start_utc,
        "window_start_utc": s.window_start_utc, "window_end_utc": s.window_end_utc, "n_starts": s.n_starts,
        "pct_of_max": r.power_summary.pct_of_max,
        "link_fraction": m.link_fraction, "longest_link_window_s": m.longest_link_window_s,
        "max_link_gap_s": m.max_link_gap_s, "link_hours_per_day_mean": m.link_hours_per_day_mean,
    }


@pytest.mark.parametrize("key", list(DEM_SITES))
def test_golden(ctx, df, key):  # noqa: F811
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    text, types, fid, _ = DEM_SITES[key]
    r = P.run_analysis(ctx, flow_request(find(df, text, types, fid)[0]))
    assert r.observer.mode is HorizonMode.DEM
    now = measure(r)
    path = GOLDEN / f"{key.lower()}.json"
    if REGEN:
        GOLDEN.mkdir(exist_ok=True)
        doc = {"_comment": "Generado por tests/test_golden_regression.py con LSI_REGEN_GOLDEN=1; ver su docstring.",
               "site": key, "request": {"gazetteer_id": fid, "start_utc": r.request.start_utc, "end_utc": r.request.end_utc,
                                        "panel_id": r.request.panel_id, "mounting": "vertical_az_tracking"},
               "dem_sha256": r.dem_meta.sha256, "kernel_hash": r.kernels.kernel_hash,
               "tolerances": TOL, "values": now}
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    assert path.exists(), f"falta {path}: genera los dorados con LSI_REGEN_GOLDEN=1 (ver docstring)"
    g = json.loads(path.read_text(encoding="utf-8"))
    bad = []
    for k, ref in g["values"].items():
        got = now[k]
        if k in EXACT or ref is None or isinstance(ref, str):
            ok = got == ref
        else:
            ok = abs(got - ref) <= g["tolerances"][k]
        if not ok:
            bad.append(f"{k}: dorado={ref!r} actual={got!r}" + ("" if k in EXACT else f" (tol {g['tolerances'][k]})"))
    note = []
    if r.dem_meta.sha256 != g["dem_sha256"]:
        note.append("el sha256 del DEM ha cambiado")
    if r.kernels.kernel_hash != g["kernel_hash"]:
        note.append("el hash de kernels ha cambiado")
    assert not bad, (f"{key}: la regresión dorada se ha movido fuera de tolerancia:\n  " + "\n  ".join(bad) +
                     ("\n  posible causa: " + "; ".join(note) if note else "") +
                     "\nSi el cambio es intencionado: LSI_REGEN_GOLDEN=1 python -m pytest tests/test_golden_regression.py "
                     "y revisa `git diff tests/golden`.")
