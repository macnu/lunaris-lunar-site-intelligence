"""Tests del buscador (T07). CSV sintético sin red; un test slow contra el CSV real si existe."""
import io
from pathlib import Path

import pytest

from lsi.contracts import GazetteerNotFoundError, GazetteerQuery
from lsi.data.gazetteer import (get_entry, list_feature_types, load_gazetteer, normalize_text, region_of, search,
                                to_request)

CSV = """feature_id,name,name_ascii,feature_type,lat_deg,lon_deg_e,diameter_km,origin,approval_year,region,has_dem,dem_key,quad
5450,Shackleton,shackleton,Crater,-89.67,129.78,20.9,Antarctic explorer,1994,polo_sur,False,,LAC-144
16338,Mons Malapert,mons malapert,Mons,-85.98,358.33,67.0,Named for nearby crater,2024,polo_sur,False,,LAC-144
3603,Malapert,malapert,Crater,-85.0,11.4,72.4,Belgian astronomer,1935,polo_sur,False,,LAC-144
11081,Malapert A,malapert a,Satellite Feature,-80.18,356.2,33.3,,2006,polo_sur,False,,LAC-144
1,Schrödinger,schrodinger,Crater,-75.0,132.4,312.0,Physicist,1964,sur,False,,LAC-132
2,Sinus Medii,sinus medii,Sinus,0.8,1.4,,Bay,1976,ecuatorial,False,,LAC-59
3,Na,na,Crater,10.0,10.0,5.0,,2006,ecuatorial,False,,LAC-1
"""


@pytest.fixture
def df(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text(CSV, encoding="utf-8")
    return load_gazetteer(p)


def names(res):
    return [e.name for e in res]


def test_normalize_text():
    assert normalize_text("  SHACKLETÓN  ") == "shackleton"
    assert normalize_text("Schrödinger-Crater, ") == "schrodinger crater"


@pytest.mark.parametrize("lat,reg", [(-89.67, "polo_sur"), (-80.0, "sur"), (-30.0, "ecuatorial"), (0.0, "ecuatorial"),
                                     (30.0, "norte"), (80.0, "polo_norte"), (90.0, "polo_norte"), (-90.0, "polo_sur")])
def test_region_of(lat, reg):
    assert region_of(lat) == reg


def test_load_missing(tmp_path):
    with pytest.raises(GazetteerNotFoundError):
        load_gazetteer(tmp_path / "no.csv")


def test_load_keeps_na_name_and_empty_origin(df):
    assert get_entry(df, 3).name == "Na"
    assert get_entry(df, 11081).origin == ""
    assert get_entry(df, 2).diameter_km is None


def test_search_shackleton_case_and_accents(df):
    r = search(df, GazetteerQuery(text="Shackleton"))
    assert names(r) == ["Shackleton"] and r[0].feature_id == 5450
    assert r == search(df, GazetteerQuery(text="shackleton")) == search(df, GazetteerQuery(text="SHACKLETÓN"))


def test_search_fuzzy_typo(df):
    assert names(search(df, GazetteerQuery(text="shakleton")))[0] == "Shackleton"


def test_search_ranking_exact_prefix_substring_then_diameter(df):
    assert names(search(df, GazetteerQuery(text="malapert"))) == ["Malapert", "Malapert A", "Mons Malapert"]
    # prefijo "malapert" (Malapert 72 km antes que Malapert A 33 km) y subcadena al final
    assert names(search(df, GazetteerQuery(text="mala"))) == ["Malapert", "Malapert A", "Mons Malapert"]


def test_search_filter_type_and_region(df):
    assert names(search(df, GazetteerQuery(text="malapert", feature_types=("Mons",)))) == ["Mons Malapert"]
    assert names(search(df, GazetteerQuery(feature_types=("Mons",)))) == ["Mons Malapert"]
    assert set(names(search(df, GazetteerQuery(regions=("ecuatorial",))))) == {"Sinus Medii", "Na"}


def test_search_nonexistent_empty(df):
    assert search(df, GazetteerQuery(text="zzzzqqqq")) == []


def test_search_empty_text_orders_by_diameter_nulls_last_and_limit(df):
    r = search(df, GazetteerQuery(limit=3))
    assert names(r) == ["Schrödinger", "Malapert", "Mons Malapert"]
    assert names(search(df, GazetteerQuery()))[-1] == "Sinus Medii"  # diámetro nulo, aceptado al final


def test_search_diameter_and_dem_filters(df):
    assert names(search(df, GazetteerQuery(min_diameter_km=100))) == ["Schrödinger"]
    assert names(search(df, GazetteerQuery(max_diameter_km=6))) == ["Na"]
    assert search(df, GazetteerQuery(only_with_dem=True)) == []


def test_list_feature_types(df):
    t = list_feature_types(df)
    assert t[0] == ("Crater", 4) and ("Mons", 1) in t and sum(n for _, n in t) == 7


def test_get_entry_and_keyerror(df):
    e = get_entry(df, 16338)
    assert e.feature_type == "Mons" and e.region == "polo_sur" and e.approval_year == 2024 and not e.has_dem
    with pytest.raises(KeyError):
        get_entry(df, 999999)


def test_to_request(df):
    req = to_request(get_entry(df, 5450), "2027-01-01T00:00:00", "2027-01-31T00:00:00", observer_height_m=3.0,
                     panel_id="x")
    assert (req.lat_deg, req.lon_deg_e, req.gazetteer_id, req.observer_height_m, req.panel_id) == \
           (-89.67, 129.78, 5450, 3.0, "x")


@pytest.mark.slow
def test_real_gazetteer_rf10():
    try:
        real = load_gazetteer()
    except GazetteerNotFoundError:
        pytest.skip("data/processed/gazetteer.* no existe (python scripts/fetch_gazetteer.py)")
    r = search(real, GazetteerQuery(text="Shackleton"))
    assert r[0].name == "Shackleton" and r[0].feature_type == "Crater" and r[0].region == "polo_sur"
    assert r == search(real, GazetteerQuery(text="SHACKLETÓN"))
    assert search(real, GazetteerQuery(text="shakleton"))[0].feature_id == r[0].feature_id
    mons = search(real, GazetteerQuery(text="malapert", feature_types=("Mons",)))
    assert any(e.feature_id == 16338 for e in mons)
    assert search(real, GazetteerQuery(text="zzzqqqxx")) == []
    assert get_entry(real, 16338).name == "Mons Malapert"
    assert real["feature_id"].is_unique and real["lon_deg_e"].between(0, 360).all()


def _refs():
    from lsi.contracts import DemRef
    # huella sintética 20 km x 20 km centrada en Mons Malapert proyectado
    from lsi.astronomy.coordinates import stereo_forward
    x, y = (float(v) for v in stereo_forward(-85.98, 358.33))
    return {"Site23": DemRef(key="Site23", directory="", paths={}, bounds_xy_m=(x - 1e4, y - 1e4, x + 1e4, y + 1e4))}


def test_annotate_dem_coverage_synthetic(df):
    import pandas as pd
    from lsi.data.gazetteer import annotate_dem_coverage
    extra = pd.DataFrame([dict(df.iloc[0].to_dict(), feature_id=99, name="Polo norte", name_ascii="polo norte",
                               lat_deg=90.0, lon_deg_e=0.0, region="polo_norte")])
    d = annotate_dem_coverage(pd.concat([df, extra], ignore_index=True), _refs())
    got = d.set_index("feature_id")
    assert got.loc[16338, "has_dem"] and got.loc[16338, "dem_key"] == "Site23"
    assert d["has_dem"].sum() == 1 and not got.loc[99, "has_dem"] and not got.loc[2, "has_dem"]
    # el margen excluye el borde: con margen mayor que la mitad de la huella nada cae dentro
    assert not annotate_dem_coverage(df, _refs(), margin_m=1.5e4)["has_dem"].any()
    assert not df["has_dem"].any()  # no muta la entrada


def test_to_request_mode_follows_coverage(df):
    """Rasgo ecuatorial -> sin DEM (esfera lisa en resolve_observer); punto en Site23 -> DEM."""
    from lsi.data.gazetteer import annotate_dem_coverage
    d = annotate_dem_coverage(df, _refs())
    eq, mal = get_entry(d, 2), get_entry(d, 16338)
    assert not eq.has_dem and eq.dem_key is None and mal.has_dem and mal.dem_key == "Site23"
    r = to_request(mal, "2027-01-01T00:00:00", "2027-01-31T00:00:00")
    assert (r.lat_deg, r.lon_deg_e, r.gazetteer_id, r.force_smooth_sphere) == (-85.98, 358.33, 16338, False)


@pytest.mark.slow
def test_real_dem_coverage():
    from lsi.data.gazetteer import ROOT, annotate_dem_coverage
    from lsi.data.loader import discover_dems
    refs = discover_dems(ROOT / "data" / "raw")
    if len(refs) < 3:
        pytest.skip("faltan los GeoTIFF de data/raw")
    d = annotate_dem_coverage(load_gazetteer(), refs)
    assert d.loc[d["feature_id"] == 16338, "dem_key"].iloc[0] == "Site23"
    assert set(d.loc[d["has_dem"], "dem_key"]) <= {"Site04", "Site11", "Site23"}


# ---- sitios de misión + alias (config/sites.json, config/aliases.json) ----
@pytest.fixture(scope="module")
def full():
    return load_gazetteer()


def first(df, text, **kw):
    return [e.name for e in search(df, GazetteerQuery(text=text, limit=5, **kw))]


@pytest.mark.slow
@pytest.mark.parametrize("q", ["Apolo 11", "apollo 11", "APOLO 11", "Apolo XI", "apólo 11"])
def test_apollo11_mission_site_before_apollo_crater(full, q):
    assert first(full, q)[0] == "Apolo 11 (Eagle)"
    assert "Apollo" in first(full, "apollo")[0]  # «Apollo» a secas sigue siendo el cráter (coincidencia exacta)


@pytest.mark.slow
def test_mission_entries_total_and_fields(full):
    sites = full[full["feature_type"] == "Sitio de misión"]
    assert len(sites) == 36 and len(full) == 9087 + 36      # las 36 de sites.json, ya todas con coordenadas (4 de la lista 2024 digitalizadas de la figura NASA)
    a = full[full["name"] == "Apolo 11 (Eagle)"].iloc[0]
    assert (a["confianza"], a["fecha"], a["programa"]) == ("publicado", "1969-07-20", "Apollo")
    assert a["lat_deg"] == pytest.approx(0.6741) and not a["has_dem"]
    assert full[full["name"] == "Apolo 17 (Challenger)"].iloc[0]["lon_deg_e"] == pytest.approx(30.7717)
    assert full[full["name"] == "Site11 de Gerlache rim"].iloc[0]["lon_deg_e"] == pytest.approx(360 - 87.1)  # lon negativa -> 0..360
    assert not full["feature_id"].duplicated().any()
    assert set(sites["confianza"]) <= {"publicado", "aprox", "a verificar"}


@pytest.mark.slow
def test_aliases_point_to_existing_official_names(full):
    import json
    al = json.loads((Path(__file__).resolve().parents[1] / "config" / "aliases.json").read_text(encoding="utf-8"))
    assert all(v in set(full["name_ascii"]) for v in al["alias"].values())
    assert all(normalize_text(k) == k for k in al["alias"])
    assert {v for v in al["zonas"].values()} <= set(full["region"])


@pytest.mark.slow
def test_spanish_aliases_and_zone(full):
    assert first(full, "Mar de la Tranquilidad")[0] == "Mare Tranquillitatis"
    assert first(full, "mar de la serenidad")[0] == "Mare Serenitatis"
    assert first(full, "Montes Apeninos")[0] == "Montes Apenninus"
    assert first(full, "Océano de las Tormentas")[0] == "Oceanus Procellarum"
    assert first(full, "Cráter Shackleton")[0] == "Shackleton"
    assert first(full, "Shackleton")[0] == "Shackleton"
    assert first(full, "change 3")[0] == "Chang'e 3"
    zona = search(full, GazetteerQuery(text="Polo Sur", limit=50))
    assert zona and all(e.region == "polo_sur" for e in zona)


@pytest.mark.slow
def test_nonexistent_empty_with_full_catalogue(full):
    assert first(full, "Zzqwxv Kolbert") == []
