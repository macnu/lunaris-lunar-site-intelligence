"""Buscador de rasgos lunares por nombre (USGS Gazetteer of Planetary Nomenclature, IAU WGSN). Arquitectura §5.17.

Núcleo sin UI. Longitud ESTE-positiva 0..360 (convenio del fichero procesado).
`annotate_dem_coverage` (T12) rellena has_dem/dem_key proyectando lat/lon contra las huellas DEM
(stereo_forward + DemRef.bounds_xy_m); sin ella has_dem=False y dem_key=None.
"""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from lsi.astronomy.coordinates import stereo_forward
from lsi.contracts import AnalysisRequest, DemRef, GazetteerEntry, GazetteerQuery, GazetteerNotFoundError

ROOT = Path(__file__).resolve().parents[3]
FUZZY_CUTOFF = 0.62  # config/simulation.json: gazetteer.fuzzy_cutoff (supuesto, ver config)
_STR_COLS = ("name", "name_ascii", "feature_type", "origin", "region", "quad", "dem_key")
SITE_TYPE = "Sitio de misión"
SITE_ID0 = 900_000   # feature_id de los sitios curados: > máximo USGS (16505), nunca chocan


def normalize_text(s: str) -> str:
    """Minúsculas, sin diacríticos, sin puntuación sobrante y con espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(s)).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _regions() -> tuple[tuple[str, float, float], ...]:
    cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
    return tuple((k, v[0], v[1]) for k, v in cfg["gazetteer"]["regions"].items())


def region_of(lat_deg: float) -> str:
    """'polo_sur' < −80°, 'sur', 'ecuatorial', 'norte', 'polo_norte' (config simulation.json: gazetteer.regions)."""
    regs = _regions()
    for name, lo, hi in regs:
        if lo <= lat_deg < hi:
            return name
    return regs[-1][0] if lat_deg >= regs[-1][2] else regs[0][0]  # +90° exacto / valores fuera de rango


@lru_cache(maxsize=1)
def _aliases() -> dict:
    """config/aliases.json: alias (normalizado) -> nombre oficial normalizado; palabras sueltas; zonas -> región."""
    return json.loads((ROOT / "config" / "aliases.json").read_text(encoding="utf-8"))


def _site_rows() -> pd.DataFrame:
    """Sitios curados de config/sites.json CON coordenadas como filas del gazetteer (sin DEM: lo anota annotate_dem_coverage).
    Los sin coordenadas (regiones Artemis III, 'a verificar') no son buscables. Confianza/programa/fecha van en columnas extra."""
    sites = json.loads((ROOT / "config" / "sites.json").read_text(encoding="utf-8"))["sites"]
    rows = []
    for s in sites:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        lat, lon = float(s["lat"]), float(s["lon"]) % 360.0
        fecha = s.get("fecha") or ""
        rows.append({
            "feature_id": SITE_ID0 + len(rows) + 1, "name": s["nombre"], "name_ascii": normalize_text(s["nombre"]),
            "feature_type": SITE_TYPE, "lat_deg": lat, "lon_deg_e": lon, "diameter_km": np.nan,
            "origin": f"{s['programa']}{', ' + fecha if fecha else ''}. Fuente: {s.get('fuente', 'config/sites.json')}",
            "approval_year": int(fecha[:4]) if fecha else np.nan, "approval_status": "Sitio curado (config/sites.json)",
            "region": region_of(lat), "has_dem": False, "dem_key": "", "quad": "",
            "programa": s["programa"], "fecha": fecha, "confianza": s.get("confianza", "a verificar")})
    return pd.DataFrame(rows)


def load_gazetteer(path: Path | None = None) -> pd.DataFrame:
    """Lee data/processed/gazetteer.parquet (o .csv) y, con la ruta por defecto, le añade los sitios de misión de
    config/sites.json (tipo 'Sitio de misión'). GazetteerNotFoundError si no existe."""
    base = ROOT / "data" / "processed"
    cands = [Path(path)] if path else [base / "gazetteer.parquet", base / "gazetteer.csv"]
    for p in cands:
        if p.exists():
            if p.suffix == ".parquet":
                df = pd.read_parquet(p)
            else:
                df = pd.read_csv(p, keep_default_na=False, na_values=[""], dtype={c: str for c in _STR_COLS})
            for c in _STR_COLS:  # "Na", "NA"... son nombres válidos: nunca NaN en texto
                df[c] = df[c].fillna("") if c in df else ""
            if "has_dem" not in df:
                df["has_dem"] = False
            df["has_dem"] = df["has_dem"].astype(bool)
            for c in ("programa", "fecha", "confianza"):
                df[c] = df[c].fillna("") if c in df else ""
            if path is None:
                df = pd.concat([df, _site_rows()], ignore_index=True)
                df[list(_STR_COLS) + ["programa", "fecha", "confianza"]] = df[list(_STR_COLS) + ["programa", "fecha", "confianza"]].fillna("")
                df["has_dem"] = df["has_dem"].astype(bool)
            return df.reset_index(drop=True)
    raise GazetteerNotFoundError(f"No existe {cands[0]}. Ejecuta: python scripts/fetch_gazetteer.py")


def annotate_dem_coverage(df: pd.DataFrame, refs: Mapping[str, DemRef], margin_m: float = 10.0) -> pd.DataFrame:
    """Copia de df con has_dem/dem_key según la huella de cada DEM menos un margen interior (margin_m =
    edge_margin_px · píxel = 2 · 5 m). Vectorizado; hemisferio norte y +90° quedan fuera sin error."""
    out = df.copy()
    lat = out["lat_deg"].to_numpy(float)
    south = lat < 0.0  # ponytail: la proyección polar sur diverge en +90° y no hay DEM al norte
    x = np.full(len(out), np.nan)
    y = np.full(len(out), np.nan)
    x[south], y[south] = stereo_forward(lat[south], out["lon_deg_e"].to_numpy(float)[south])
    key = np.full(len(out), "", dtype=object)
    for k, ref in refs.items():  # solapes: gana el primero por orden de refs
        x0, y0, x1, y1 = ref.bounds_xy_m
        inside = (key == "") & (x >= x0 + margin_m) & (x <= x1 - margin_m) & (y >= y0 + margin_m) & (y <= y1 - margin_m)
        key[inside] = k
    out["dem_key"] = key
    out["has_dem"] = key != ""
    return out


def _num(x) -> Optional[float]:
    return None if pd.isna(x) else float(x)


def _entry(r) -> GazetteerEntry:
    yr = r.get("approval_year")
    return GazetteerEntry(
        feature_id=int(r["feature_id"]), name=r["name"], name_ascii=r["name_ascii"], feature_type=r["feature_type"],
        lat_deg=float(r["lat_deg"]), lon_deg_e=float(r["lon_deg_e"]), diameter_km=_num(r["diameter_km"]),
        origin=r["origin"], approval_year=None if yr is None or pd.isna(yr) else int(yr),
        region=r["region"] or region_of(float(r["lat_deg"])), has_dem=bool(r["has_dem"]),
        dem_key=r["dem_key"] or None, quad=r["quad"])


_ROMAN = {"xi": "11", "xii": "12", "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17"}


def _variants(q: str) -> list[str]:
    """q + equivalencias: alias bilingüe -> nombre oficial, 'apollo'->'apolo' y 'Apolo XI'->'apolo 11'."""
    al = _aliases()
    out = [q]
    if q in al["alias"]:
        out.append(al["alias"][q])
    toks = [al["palabras"].get(t, t) for t in q.split()]
    if len(toks) > 1 and toks[0] == "apolo":
        toks[1] = _ROMAN.get(toks[1], toks[1])
    v = " ".join(toks)
    if v not in out:
        out.append(v)
    return out


def search(df: pd.DataFrame, query: GazetteerQuery) -> list[GazetteerEntry]:
    """Prefiltro por tipo/región/diámetro/DEM; coincidencia exacta > prefijo > subcadena > difusa (con alias/equivalencias);
    a igualdad, los sitios de misión antes que los rasgos IAU; orden estable."""
    q = normalize_text(query.text)
    zone = _aliases()["zonas"].get(q)  # 'polo sur' = filtro de región (sin polígonos inventados), no un nombre
    m = pd.Series(True, index=df.index)
    if zone:
        m &= df["region"] == zone
        q = ""
    if query.feature_types:
        m &= df["feature_type"].isin(query.feature_types)
    if query.regions:
        m &= df["region"].isin(query.regions)
    if query.min_diameter_km is not None:
        m &= df["diameter_km"] >= query.min_diameter_km
    if query.max_diameter_km is not None:
        m &= df["diameter_km"] <= query.max_diameter_km
    if query.only_with_dem:
        m &= df["has_dem"]
    d = df[m].copy()
    d["_site"] = (d["feature_type"] != SITE_TYPE).astype(int)
    if q:
        names = d["name_ascii"]
        tier = pd.Series(4, index=d.index)
        ratio = pd.Series(0.0, index=d.index)
        for v in _variants(q):
            t = pd.Series(4, index=d.index)
            t[names.str.contains(v, regex=False)] = 3
            t[names.str.startswith(v)] = 2
            t[names == v] = 1
            r = pd.Series(0.0, index=d.index)
            for i in d.index[t == 4]:  # ponytail: O(n) con difflib; suficiente para ~9 k nombres
                s = difflib.SequenceMatcher(None, v, names[i])
                if s.real_quick_ratio() >= FUZZY_CUTOFF and s.quick_ratio() >= FUZZY_CUTOFF and s.ratio() >= FUZZY_CUTOFF:
                    r[i] = s.ratio()
            tier, ratio = tier.where(tier <= t, t), ratio.where(ratio >= r, r)
        d["_tier"], d["_ratio"] = tier, ratio
        d = d[(d["_tier"] < 4) | (d["_ratio"] > 0)]
        d = d.sort_values(["_tier", "_ratio", "_site", "diameter_km", "name_ascii"], ascending=[True, False, True, False, True],
                          na_position="last", kind="mergesort")
    else:
        d = d.sort_values(["_site", "diameter_km", "name_ascii"] if zone else ["diameter_km", "name_ascii"],
                          ascending=[True, False, True] if zone else [False, True], na_position="last", kind="mergesort")
    return [_entry(r) for _, r in d.head(query.limit).iterrows()]


def list_feature_types(df: pd.DataFrame) -> list[tuple[str, int]]:
    """(tipo, nº de rasgos) por frecuencia descendente (desempate alfabético)."""
    vc = df["feature_type"].value_counts()
    return sorted(((str(t), int(n)) for t, n in vc.items()), key=lambda x: (-x[1], x[0]))


def get_entry(df: pd.DataFrame, feature_id: int) -> GazetteerEntry:
    """Entrada por ID; KeyError si no existe."""
    sel = df[df["feature_id"] == feature_id]
    if sel.empty:
        raise KeyError(feature_id)
    return _entry(sel.iloc[0])


def to_request(entry: GazetteerEntry, start_utc: str, end_utc: str, observer_height_m: float = 2.0,
               **kw) -> AnalysisRequest:
    """AnalysisRequest con lat/lon del centro del rasgo y gazetteer_id (DEM o esfera lisa lo decide pipeline)."""
    return AnalysisRequest(lat_deg=entry.lat_deg, lon_deg_e=entry.lon_deg_e, start_utc=start_utc, end_utc=end_utc,
                           observer_height_m=observer_height_m, gazetteer_id=entry.feature_id, **kw)
