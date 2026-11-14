"""Regenera ``tests/golden/horizons_stations_2026-12.json``: elevación de la Luna vista desde cada complejo DSN según
JPL Horizons (API oficial, ``CENTER='coord@399'``, ``SITE_COORD`` geodésico, ``QUANTITIES=4``, aparente sin refracción).

Los tests (``tests/test_ground_stations.py``) usan el JSON guardado, así que NO dependen de la red; este script solo hace falta
para regenerarlo. Estaciones y coordenadas salen de ``config/ground_stations.json`` (las mismas que usa el motor).

    python scripts/fetch_horizons_stations.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "https://ssd.jpl.nasa.gov/api/horizons.api"
STATIONS = ("DSS-14", "DSS-43", "DSS-63")
# 12 instantes repartidos en 2026-12 (UTC), horas distintas para barrer el giro de la Tierra
INSTANTS = [f"2026-12-{d:02d} {h:02d}:{m:02d}" for d, h, m in
            ((1, 0, 0), (3, 5, 30), (6, 11, 0), (9, 17, 45), (12, 22, 15), (15, 3, 0), (18, 8, 30), (21, 13, 20),
             (24, 19, 0), (27, 1, 40), (29, 9, 10), (31, 15, 55))]
DAY = ("2026-12-11 00:00", "2026-12-12 00:00", "10m")   # un día completo a 10 min para las ventanas de contacto


def _query(st: dict, **time_args) -> list[tuple[str, float]]:
    p = {"format": "json", "COMMAND": "'301'", "OBJ_DATA": "'NO'", "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
         "CENTER": "'coord@399'", "COORD_TYPE": "'GEODETIC'",
         "SITE_COORD": f"'{st['lon_deg_e']},{st['lat_deg']},{st['alt_m'] / 1000.0}'", "QUANTITIES": "'4'",
         "ANG_FORMAT": "'DEG'", "CAL_FORMAT": "'CAL'", "APPARENT": "'AIRLESS'"}
    p.update(time_args)
    r = requests.get(API, params=p, timeout=90)
    r.raise_for_status()
    txt = r.json()["result"]
    rows = txt.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()
    out = []
    for ln in rows:
        c = ln.split()
        out.append((f"{c[0]} {c[1]}", float(c[-1])))   # fecha UT, elevación (°)
    return out


def main() -> None:
    cfg = json.loads((ROOT / "config" / "ground_stations.json").read_text(encoding="utf-8"))
    doc = {"_comment": "JPL Horizons API (https://ssd.jpl.nasa.gov/api/horizons.api), objetivo 301 Moon, CENTER coord@399, "
                       "QUANTITIES=4 (elevación aparente, AIRLESS). Regenerar con scripts/fetch_horizons_stations.py.",
           "instants_utc": INSTANTS, "day": {"start": DAY[0], "stop": DAY[1], "step": DAY[2]}, "stations": {}}
    for sid in STATIONS:
        st = cfg["stations"][sid]
        tl = "' '".join(INSTANTS)
        inst = _query(st, TLIST=f"'{tl}'")
        day = _query(st, START_TIME=f"'{DAY[0]}'", STOP_TIME=f"'{DAY[1]}'", STEP_SIZE=f"'{DAY[2]}'")
        doc["stations"][sid] = {"instants_el_deg": [e for _, e in inst], "day_utc": [t for t, _ in day],
                                "day_el_deg": [e for _, e in day]}
        print(sid, len(inst), len(day))
    out = ROOT / "tests" / "golden" / "horizons_stations_2026-12.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print("escrito", out)


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()  # --help no consulta Horizons ni escribe nada
    sys.exit(main())
