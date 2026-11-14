"""Precalcula los horizontes por defecto (DEM x observador por defecto x alturas) en la caché por hash de data/processed/.

Idempotente: un caso ya en caché se salta (compute_horizon lo recupera sin recalcular). Uso: python scripts/precompute_horizons.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lsi import pipeline  # noqa: E402
from lsi.astronomy.coordinates import stereo_forward  # noqa: E402
from lsi.contracts import HorizonMode, ObserverPoint  # noqa: E402
from lsi.data import cache  # noqa: E402
from lsi.data.catalog import default_observer, horizon_params, load_simulation_config  # noqa: E402
from lsi.data.loader import discover_dems, read_window  # noqa: E402
from lsi.terrain.horizon import compute_horizon  # noqa: E402

SITES = ("Site04", "Site11", "Site23")
HEIGHTS_M = (1.0, 2.0, 5.0)


def precompute(root: Path = ROOT, sites=SITES, heights=HEIGHTS_M, cache_dir: Path | None = None, windows=None, log=print) -> list[dict]:
    """Devuelve un dict por caso: site, height_m, cached, seconds, n_limited, n_az, cache_key. ``windows`` = {clave: DemWindow}
    opcional (tests; entonces sin campo lejano). Las claves son EXACTAMENTE las de ``pipeline.run_analysis`` (M4): mismo DEM, mismo
    campo lejano LOLA 80 m (``pipeline.far_field_for``) y mismos parámetros; antes se calculaba sin campo lejano y nunca acertaba."""
    cfg = load_simulation_config(root / "config" / "simulation.json")
    cache_dir = cache_dir or root / cfg["cache"]["dir"]
    use_far = windows is None
    if windows is None:
        refs = discover_dems(root / "data" / "raw")
        windows = {k: read_window(refs[k]) for k in sites if k in refs}
    rows = []
    for site in sites:
        if site not in windows:
            log(f"{site}: sin DEM, se omite")
            continue
        lat, lon = default_observer(cfg, site)
        x, y = (float(v) for v in stereo_forward(lat, lon))
        for h in heights:
            p = horizon_params(cfg, h)
            o = ObserverPoint(lat_deg=lat, lon_deg_e=lon, x_m=x, y_m=y, height_m=h, mode=HorizonMode.DEM, dem_key=site)
            before = {f.stem for f in (cache_dir / "horizons").glob("*.npz")}
            t0 = time.perf_counter()
            far = pipeline.far_field_for(root / "data" / "raw", x, y, p.r_max_m) if use_far else None
            r = compute_horizon(windows[site], o, p, cache_dir=cache_dir, far=far)
            dt = time.perf_counter() - t0
            rows.append(dict(site=site, height_m=h, cached=r.cache_key in before, seconds=dt,
                             n_limited=int(r.limited.sum()), n_az=len(r.az_deg), cache_key=r.cache_key))
            log(f"{site} h={h:g} m: {'en caché' if rows[-1]['cached'] else 'calculado'} {dt:.2f} s, "
                f"{rows[-1]['n_limited']}/{rows[-1]['n_az']} azimuts limitados")
    return rows


def summary(rows: list[dict]) -> str:
    lim = {}
    for r in rows:
        lim.setdefault(r["site"], {})[r["height_m"]] = r["n_limited"]
    lines = [f"Casos: {len(rows)} ({sum(r['cached'] for r in rows)} en caché, {sum(not r['cached'] for r in rows)} calculados); "
             f"tiempo total: {sum(r['seconds'] for r in rows):.1f} s", "Azimuts limitados por cobertura (por altura de observador):"]
    lines += [f"  {s}: " + ", ".join(f"{h:g} m={n}" for h, n in v.items()) for s, v in lim.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description='Precalcula los horizontes de los 3 DEM (alturas 1, 2 y 5 m) en la cache de data/processed/horizons.').parse_args()  # --help no ejecuta nada
    print(summary(precompute()))
