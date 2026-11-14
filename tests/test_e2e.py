"""Flujo extremo a extremo (arquitectura §12.3, puntos 5 y 7): buscador → «Evaluar este lugar» → horizonte → timeline de
30 días → cuenta atrás → panel tj-gaas-lander-body (vertical_az_tracking) → score con veredicto y rango → export JSON/CSV.

Con SPICE y DEM reales. Los 3 sitios con DEM (Site04, Site11, Site23) y, en modo esfera lisa, Apolo 11 y Tycho.
"""
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from lsi import pipeline as P
from lsi.analysis import export as ex
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, CSV_HORIZON_COLUMNS, CSV_METRICS_COLUMNS, CSV_TIMESERIES_COLUMNS, CSV_WINDOWS_COLUMNS,
    AnalysisRequest, GazetteerQuery, HorizonMode, MountingSpec, MountingType, WarningCode,
)
from lsi.data import gazetteer as gz

pytestmark = pytest.mark.needs_spice
ROOT = Path(__file__).resolve().parents[1]
START, END30, NOW = "2026-12-01T00:00:00", "2026-12-31T00:00:00", "2026-12-10T00:00:00"
GEN_UTC = "2026-01-01T00:00:00Z"                      # generated_utc fijo (única fuente no determinista del export)
VAT = MountingSpec(MountingType.VERTICAL_AZ_TRACKING)
PANEL = "tj-gaas-lander-body"

# (clave DEM, texto buscado, filtro de tipo, feature_id esperado, distancia de snap mínima/máxima en km; None = sin snap)
DEM_SITES = {
    "Site04": ("Shackleton", None, 5450, (0.3, 1.5)),
    "Site11": ("de Gerlache", None, 1439, (4.0, 7.0)),
    "Site23": ("Malapert", ("Mons",), 16338, None),
}


@pytest.fixture(scope="module")
def ctx():
    return P.build_context(ROOT)


@pytest.fixture(scope="module")
def df(ctx):
    return gz.annotate_dem_coverage(gz.load_gazetteer(), ctx.dem_refs, float(ctx.cfg["gazetteer"]["dem_cover_margin_m"]))


def find(df, text, types=None, fid=None):
    """Paso 1 del flujo: buscar por nombre (como el buscador de la UI) y elegir el rasgo esperado."""
    hits = gz.search(df, GazetteerQuery(text=text, feature_types=types or (), limit=20))
    assert hits, f"el buscador no devuelve nada para {text!r}"
    return next(h for h in hits if fid is None or h.feature_id == fid), hits


def flow_request(entry, **kw) -> AnalysisRequest:
    """Paso 2, «Evaluar este lugar»: petición del rasgo (gazetteer_id → DEM / snap_to_dem / esfera lisa lo decide el pipeline)."""
    return gz.to_request(entry, START, END30, panel_id=PANEL, mounting=VAT, with_uncertainty=True, now_utc=NOW, **kw)


def codes(r):
    return {w.code for w in r.warnings}


def check_common(r, d):
    """Aserciones comunes a TODOS los flujos (DEM y esfera): metadatos, avisos, limited, potencia, score, ventana, export."""
    # metadatos presentes (RNF-11)
    prov = d["provenance"]
    assert d["schema_version"] == ex.EXPORT_SCHEMA_VERSION and d["lsi_version"] and d["generated_utc"] == GEN_UTC
    assert prov["frame"] == "MOON_ME" and prov["abcorr"] and prov["moon_radius_m"] == 1_737_400.0
    assert prov["kernels"]["kernel_hash"] and prov["kernels"]["files"] and prov["horizon"]["cache_key"]
    assert d["request"]["panel_id"] == PANEL and d["request"]["start_utc"] == START and d["request"]["end_utc"] == END30
    # avisos científicos siempre visibles incluidos (en DEM_EFFECTIVE_RESOLUTION solo si hay DEM)
    exported = {w["code"] for w in d["warnings"]}
    sphere = r.observer.mode is HorizonMode.SMOOTH_SPHERE
    for c in ALWAYS_SHOWN_WARNINGS:
        if c is WarningCode.DEM_EFFECTIVE_RESOLUTION and sphere:
            assert c.value not in exported
        else:
            assert c.value in exported and c in codes(r)
    assert all(w["text_es"] for w in d["warnings"])
    # `limited` coherente: bool por azimut, r_cov ≥ 0, fracción exportada = media de limited, |h_lb| < 90° (el suelo puede quedar bajo la esfera)
    h = r.horizon
    assert h.limited.dtype == bool and len(h.limited) == len(h.az_deg) == len(h.h_lb_deg) == len(h.r_cov_m) == 1440
    assert np.all(np.isfinite(h.h_lb_deg)) and np.all(np.abs(h.h_lb_deg) < 90.0)
    assert prov["horizon"]["limited_fraction"] == pytest.approx(float(np.mean(h.limited)), abs=1e-6)
    assert d["horizon"]["limited"] == [bool(v) for v in h.limited]
    if sphere:
        assert not h.limited.any()                       # esfera lisa: suelo analítico, nada que truncar
    else:
        assert np.all(h.r_cov_m[~h.limited] >= 0) and h.dem_sha256
        if h.h_ub_deg is not None:
            assert np.all(h.h_ub_deg >= h.h_lb_deg - 1e-9)
    # métricas
    m = r.metrics
    assert 0.0 <= m.solar_fraction <= 1.0 and 0.0 <= m.earth_fraction <= 1.0 and 0.0 <= m.overlap_fraction <= 1.0
    assert m.period_s == pytest.approx(30 * 86400.0, abs=1.0)
    assert d["metrics"]["solar_fraction"]["value"] == pytest.approx(m.solar_fraction, abs=1e-4)
    # timeline de 30 días: tabla diaria UTC real
    assert len(r.daily) == 30 and r.daily[0]["day_utc"] == "2026-12-01" and r.daily[-1]["day_utc"] == "2026-12-30"
    # cuenta atrás Sol y Tierra
    assert [c.body.value for c in r.countdowns] == ["SUN", "EARTH"]
    for c in r.countdowns:
        assert c.searched_days > 0 and isinstance(c.currently_up, bool)
        assert (c.next_event is None) == (c.seconds_until is None)
        assert c.seconds_until is None or c.seconds_until > 0
    # potencia: % de la nominal entre 0 y ~104 (máximo físico con 1 UA en perihelio, no «vatios»)
    assert r.power_summary is not None and 0.0 <= r.power_summary.pct_of_max <= 104.0
    assert d["power"]["panel_id"] == PANEL and d["power"]["mounting"]["type"] == "vertical_az_tracking"
    assert POWER_ASSUMPTIONS(d)  # Site04 (snap en el borde de Shackleton) puede dar 0 %: oscuridad permanente, resultado válido
    # score en [0, 100] con rango, veredicto y ventana de misión
    s = r.score
    assert 0.0 <= s.score_min <= s.score <= s.score_max <= 100.0
    assert s.verdict in ("APTO", "CONDICIONAL", "NO APTO", "SIN DATOS") and s.verdict_reason
    assert s.mission_days == 14.0 and s.window_start_utc and s.window_end_utc and s.window_start_utc < s.window_end_utc
    assert START <= s.window_start_utc and s.window_end_utc <= END30 and s.n_starts == 17
    assert r.window_metrics.period_s == pytest.approx(14 * 86400.0, abs=1.0)
    assert d["score"]["score"] == pytest.approx(s.score, abs=1e-3) and d["score"]["status"] == s.status.value
    assert d["score"]["partial"] == s.partial and d["score"]["terrain_data"] == s.terrain_data
    assert r.uncertainty is not None and r.score.confidence is not None


def POWER_ASSUMPTIONS(d):
    return d["power"]["assumptions"] and d["power"]["daily"]


def export_all(r, tmp_path):
    """Último paso: exportar JSON y CSV y validar el esquema §7 (validate_export, además de la validación interna)."""
    jp = ex.write_json(r, tmp_path / "result.json", GEN_UTC)
    d = json.loads(jp.read_text(encoding="utf-8"))
    ex.validate_export(d)
    paths = ex.write_csv_bundle(r, tmp_path / "csv", GEN_UTC)
    return d, paths


def read_csv(p):
    with open(p, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def check_csv(r, paths):
    for key, cols in (("timeseries", CSV_TIMESERIES_COLUMNS), ("windows", CSV_WINDOWS_COLUMNS),
                      ("horizon", CSV_HORIZON_COLUMNS), ("metrics", CSV_METRICS_COLUMNS)):
        head, rows = read_csv(paths[key])
        assert tuple(head) == tuple(cols), key
        assert all(len(x) == len(cols) for x in rows)
    assert len(read_csv(paths["timeseries"])[1]) == len(r.sky.et)
    assert len(read_csv(paths["horizon"])[1]) == 1440
    meta = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert meta["provenance"]["kernels"]["kernel_hash"] and meta["warnings"] and meta["generated_utc"] == GEN_UTC


# ---------------------------------------------------------------------------------------- 3 sitios con DEM
@pytest.mark.needs_dem
@pytest.mark.slow
@pytest.mark.parametrize("key", list(DEM_SITES))
def test_e2e_dem_site(ctx, df, key, tmp_path):
    if key not in ctx.dem_refs:
        pytest.skip(f"falta el DEM {key}")
    text, types, fid, snap = DEM_SITES[key]
    entry, hits = find(df, text, types, fid)
    assert entry.feature_id == fid and hits[0].feature_id in {h.feature_id for h in hits}
    assert entry.has_dem == (snap is None)               # Malapert (Mons) cubierto; Shackleton/de Gerlache, solo con snap
    assert gz.search(df, GazetteerQuery(text=text.upper())) == gz.search(df, GazetteerQuery(text=text.lower()))

    # «Evaluar este lugar»: la estimación previa del snap es la que luego usa el análisis. CAMBIO INTENCIONADO (SNAP AL MEJOR
    # PUNTO): el flujo del buscador va por defecto al TOP-1 del mapa de idoneidad del DEM (perfil/duración de la petición) y el
    # punto cubierto más cercano (el comportamiento anterior, con el rango `snap`) queda como alternativa.
    if snap is not None:
        cand = P.snap_candidate(ctx, entry.lat_deg, entry.lon_deg_e, prefer="best", profile_id="lander_solar_no_rhu", mission_days=14.0,
                                feature_radius_km=P.feature_radius_km(ctx, fid))   # CAMBIO INTENCIONADO: mejor punto DENTRO del rasgo
        assert cand is not None and cand.dem_key == key and cand.kind == "best" and cand.best_start_utc and cand.inside_feature
        assert snap[0] < cand.nearest.distance_km < snap[1]
    r = P.run_analysis(ctx, flow_request(entry))

    o = r.observer
    assert o.mode is HorizonMode.DEM and o.dem_key == key and o.ground_z_m is not None
    assert r.horizon.mode is HorizonMode.DEM and r.horizon.far_sha256, "campo lejano LOLA 80 m en uso"
    if snap is None:
        assert o.snap_distance_km is None and o.snapped_from is None and "snap_to_dem" not in o.label and o.snap_kind is None
        assert WarningCode.CURATED_COORDS_OUTSIDE_DEM not in codes(r)
    else:
        assert o.snap_kind == "best" and o.best_start_utc and o.snap_distance_km == pytest.approx(cand.distance_km)
        assert snap[0] < o.snap_alternative[2] < snap[1]          # el más cercano, como alternativa
        assert o.snapped_from == (entry.lat_deg, pytest.approx(entry.lon_deg_e))
        assert "snap_to_dem" in o.label and f"{o.snap_distance_km:.2f} km" in o.label   # etiqueta con la distancia
        w = next(w for w in r.warnings if w.context and w.context.startswith("snap_to_dem"))
        assert w.code is WarningCode.CURATED_COORDS_OUTSIDE_DEM and f"{o.snap_distance_km:.2f} km" in w.text_es
        assert WarningCode.GAZETTEER_COORDS_APPROX in codes(r)
        x0, y0, x1, y1 = ctx.dem_refs[key].bounds_xy_m
        assert x0 < o.x_m < x1 and y0 < o.y_m < y1       # el punto ajustado está dentro del recorte

    d, paths = export_all(r, tmp_path)
    check_common(r, d)
    check_csv(r, paths)
    # CAMBIO INTENCIONADO (enlace DTE): la conectividad del score es el ENLACE (red DSN + margen), la Tierra geométrica sigue aparte
    m, lk = r.metrics, r.link
    assert lk is not None and lk.network_id == "DSN" and m.link_fraction is not None
    assert m.link_fraction <= m.earth_fraction + 1e-9 and sum(m.link_by_station.values()) >= m.link_fraction - 1e-9
    assert d["metrics"]["link_fraction"]["value"] == pytest.approx(m.link_fraction, abs=1e-5)   # el export lleva el enlace
    s = r.score
    assert s.terrain_data and not s.partial and s.missing_keys == () and not s.verdict_provisional
    assert s.verdict in ("APTO", "CONDICIONAL", "NO APTO")          # con DEM nunca SIN DATOS ni provisional
    w = r.window_metrics   # el rango colapsa, con razón, sin Sol (snap «nearest» en oscuridad permanente) o con la ventana
    saturated = w.solar_fraction == 1.0 and w.max_darkness_s == 0.0   # saturada (Sol 100 %, sin noche: snap al mejor punto)
    assert s.range_computed and s.range_note.startswith("rango calculado")     # con incertidumbre pedida el rango SE HA calculado
    if r.metrics.solar_fraction > 0 and not saturated:
        assert s.score_min < s.score_max, "con DEM e incertidumbre activada el rango no es degenerado"
    elif s.score_max - s.score_min < 0.05:
        assert "estrecho" in s.range_note, "un rango calculado y de ancho cero se dice «estrecho», no se presenta como resultado vacío"
    assert s.energy_basis == "panel" and s.energy_panel_id == PANEL and "G5" in {g.id for g in s.gates}
    assert d["observer"]["mode"] == "dem" and d["observer"]["gazetteer_id"] == fid
    assert d["provenance"]["dem"]["key"] == key and d["provenance"]["dem"]["sha256"]
    assert r.slope is not None and r.dem_confidence is not None
    assert WarningCode.NO_DEM_SMOOTH_SPHERE not in codes(r) and WarningCode.NO_TERRAIN_DATA_SCORE not in codes(r)


# ---------------------------------------------------------------------------------------- sin DEM: esfera lisa
def _assert_sphere_flow(ctx, r, tmp_path):
    assert r.observer.mode is HorizonMode.SMOOTH_SPHERE and r.dem_meta is None and r.slope is None
    assert r.observer.snap_distance_km is None
    assert {WarningCode.NO_DEM_SMOOTH_SPHERE, WarningCode.NO_TERRAIN_DATA_SCORE} <= codes(r)
    d, paths = export_all(r, tmp_path)
    check_common(r, d)
    check_csv(r, paths)
    s = r.score
    # «sin datos de terreno»: score parcial con rango, veredicto SIN DATOS o NO APTO provisional (nunca APTO/CONDICIONAL)
    assert s.partial and not s.terrain_data and s.missing_keys == ("terrain",)
    assert s.score_min <= s.score <= s.score_max
    assert s.verdict in ("SIN DATOS", "NO APTO")
    assert s.verdict_provisional == (s.verdict == "NO APTO")
    if s.verdict == "NO APTO":
        assert "provisional" in s.verdict_reason
    assert d["score"]["terrain_data"] is False and d["score"]["missing_keys"] == ["terrain"] and d["score"]["partial"]
    assert d["observer"]["mode"] == "smooth_sphere" and d["provenance"]["dem"] is None
    assert {w["code"] for w in d["warnings"]} >= {WarningCode.NO_DEM_SMOOTH_SPHERE.value, WarningCode.NO_TERRAIN_DATA_SCORE.value}
    assert WarningCode.DEM_EFFECTIVE_RESOLUTION not in codes(r)


def test_e2e_apollo11_smooth_sphere(ctx, tmp_path):
    site = next(s for s in ctx.sites if s.id == "apollo11")
    assert not site.has_dem
    r = P.run_analysis(ctx, AnalysisRequest(site.lat_deg, site.lon_deg_e, START, END30, site_id="apollo11", panel_id=PANEL,
                                            mounting=VAT, with_uncertainty=True, now_utc=NOW))
    _assert_sphere_flow(ctx, r, tmp_path)
    assert r.score.verdict == "SIN DATOS"                 # dato conocido (test_pipeline): día lunar entero en la mejor ventana


def test_e2e_tycho_gazetteer_feature_without_coverage(ctx, df, tmp_path):
    entry, _ = find(df, "Tycho", fid=6163)
    assert not entry.has_dem and P.snap_candidate(ctx, entry.lat_deg, entry.lon_deg_e) is None   # ningún DEM razonable
    r = P.run_analysis(ctx, flow_request(entry))
    assert r.request.gazetteer_id == 6163
    _assert_sphere_flow(ctx, r, tmp_path)
