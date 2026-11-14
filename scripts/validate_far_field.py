"""Valida el modo FAR_FIELD (DEM polar de 80 m) frente al modo DEM (5 m) en puntos REALES de los recortes de Site23, Site11 y Site04.

Para cada punto: horizonte (grados, por azimut), fracciones de Sol y de Tierra/enlace en 30 días y las puertas no
terrenales del score (G1 Sol, G4 noche, …) con los dos modos. Escribe un JSON con el detalle y un resumen.

    python scripts/validate_far_field.py --n-per-site 40 --out data/processed/far_field_validation.json

Reproducible: semilla fija. Tarda unos minutos (≈ 3 s por punto en modo 5 m).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from lsi import pipeline as P  # noqa: E402
from lsi.astronomy.coordinates import stereo_inverse  # noqa: E402
from lsi.contracts import AnalysisRequest, DemLayer, GateStatus  # noqa: E402

START, END = "2027-03-01T00:00:00Z", "2027-03-31T00:00:00Z"
MARGIN_M = 3000.0          # los puntos distan ≥ 3 km del borde del recorte (el 5 m tiene su horizonte cercano completo)
RELIEF_R_M = 500.0         # relieve local = máx − mín del DEM de 5 m en ±500 m


def _gate_map(res) -> dict:
    return {g.id: g.status.value for g in res.score.gates if g.id not in ("G2", "G3")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-site", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20260814)
    ap.add_argument("--out", default=str(ROOT / "data" / "processed" / "far_field_validation.json"))
    a = ap.parse_args()
    ctx = P.build_context(ROOT)
    rng = np.random.default_rng(a.seed)
    rows = []
    for key in ("Site23", "Site11", "Site04"):
        ref = ctx.dem_refs[key]
        surf = P._layer(ref, DemLayer.SURF)
        x0, y0, x1, y1 = ref.bounds_xy_m
        n = 0
        while n < a.n_per_site:
            x, y = rng.uniform(x0 + MARGIN_M, x1 - MARGIN_M), rng.uniform(y0 + MARGIN_M, y1 - MARGIN_M)
            if P._ground(ref, x, y) is None:
                continue
            c, r = int(round((x - surf.x0_m) / surf.pixel_size_m)), int(round((surf.y0_m - y) / surf.pixel_size_m))
            k = int(RELIEF_R_M / surf.pixel_size_m)
            patch = surf.data[max(r - k, 0):r + k + 1, max(c - k, 0):c + k + 1]
            if not np.isfinite(patch).mean() > 0.95:
                continue
            lat, lon = (float(v) for v in stereo_inverse(x, y))
            req = AnalysisRequest(lat, lon, START, END, snap_to_dem=False)
            d = P.run_analysis(ctx, req)
            f = P.run_analysis(ctx, dataclasses.replace(req, force_far_field=True))
            assert d.horizon.mode.value == "dem" and f.horizon.mode.value == "far_field"
            e = f.horizon.h_lb_deg - d.horizon.h_lb_deg
            gd, gf = _gate_map(d), _gate_map(f)
            rows.append({
                "site": key, "lat": lat, "lon": lon, "x": x, "y": y, "relief_500m": float(np.nanmax(patch) - np.nanmin(patch)),
                "dz_ground": float(f.observer.ground_z_m - d.observer.ground_z_m),
                "h_rms": float(np.sqrt(np.mean(e ** 2))), "h_max": float(np.abs(e).max()), "h_bias": float(e.mean()),
                "sun_dem": d.metrics.solar_fraction, "sun_far": f.metrics.solar_fraction,
                "earth_dem": d.metrics.earth_fraction, "earth_far": f.metrics.earth_fraction,
                "link_dem": d.metrics.link_fraction, "link_far": f.metrics.link_fraction,
                "gates_dem": gd, "gates_far": gf, "gates_change": gd != gf,
                "verdict_dem": d.score.verdict, "verdict_far": f.score.verdict,
            })
            n += 1
            print(key, n, f"h_rms={rows[-1]['h_rms']:.3f} sun {rows[-1]['sun_dem']:.3f}->{rows[-1]['sun_far']:.3f}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"start": START, "end": END, "seed": a.seed, "rows": rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
