"""Página del buscador (ui/pages/search.py) con AppTest: RF-10/RF-47/RF-48."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui import state as S

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.fixture
def at(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "search.py", tmp_path / "search.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


def search(at, text):
    at.text_input(key="_s_q").set_value(text).run()
    assert not at.exception
    return at


def names(at):
    return [o for o in at.selectbox(key="_s_sel").options]


def test_shackleton_found(at):
    search(at, "Shackleton")
    assert any("Shackleton" in n for n in names(at))
    assert "Shackleton" in " ".join(m.value for m in at.subheader)


def test_case_and_accents_equivalent(at):
    a = names(search(at, "SHACKLETON"))
    b = names(search(at, "shackleton"))
    c = names(search(at, "shäckletón"))
    assert a == b == c and a


def test_type_filter_mons_includes_malapert(at):
    search(at, "malapert")
    at.multiselect(key="_s_types").set_value(["Mons"]).run()
    assert not at.exception
    assert any("Mons Malapert" in n for n in names(at)) and all(" Mons " in n for n in names(at))


def test_no_results_friendly_with_suggestions(at):
    search(at, "Zzqwxv Kolbert")          # inexistente
    assert any("No he encontrado" in i.value for i in at.info)
    search(at, "Shakleton")               # errata: la búsqueda difusa la resuelve
    assert any("Shackleton" in n for n in names(at))
    search(at, "qqqqqq")
    assert any("No he encontrado" in i.value for i in at.info)


def test_suggestions_for_misspelling_beyond_cutoff(at):
    search(at, "Shackltn")
    if any("No he encontrado" in i.value for i in at.info):
        assert any(b.label.startswith("Shackleton") for b in at.button)


def test_evaluate_malapert_dem(at):
    at.multiselect(key="_s_types").set_value(["Mons"]).run()
    search(at, "mons malapert")
    assert any("modo DEM" in s.value for s in at.success)
    at.button(key="_s_eval").click().run()
    assert not at.exception
    ss = at.session_state
    assert ss[S.ORIGIN] == "search" and ss[K.SEARCH_SELECTED] == 16338 and ss[K.SITE_ID] is None
    assert ss[K.OBS_LAT] == pytest.approx(-85.98)


def test_evaluate_tycho_smooth_sphere(at):
    search(at, "tycho")
    at.selectbox(key="_s_sel").select(6163).run()
    assert any("esfera lisa" in w.value and "sin datos de terreno" in w.value for w in at.warning)
    at.button(key="_s_eval").click().run()
    assert not at.exception
    ss = at.session_state
    assert ss[S.ORIGIN] == "search" and ss[K.SEARCH_SELECTED] == 6163
    assert ss[K.OBS_LAT] == pytest.approx(-43.2958, abs=1e-3)


def md(at):
    return " ".join(m.value for m in at.markdown)


def shackleton(at):
    search(at, "shackleton")
    assert any("Shackleton" in n for n in names(at)[:1])
    return at


def test_shackleton_offers_best_point_and_nearest(at):
    shackleton(at)
    assert any("queda fuera del mapa de terreno" in i.value for i in at.info)
    assert "Mejor punto del DEM" in md(at) and "candidato propuesto" in md(at) and "Mejor fecha de inicio sugerida" in md(at)
    assert "Punto más cercano al rasgo" in md(at) and "pared sin Sol" in md(at)
    assert at.radio(key="_s_opt").value == "best"                      # lo recomendado va por defecto
    assert not any("ajustado al punto del DEM" in w.value for w in at.warning)


def test_best_point_sets_suggested_start(at):
    from ui import cache
    shackleton(at)
    ctx = cache.get_context()
    at.button(key="_s_eval").click().run()
    assert not at.exception
    ss = at.session_state
    assert ss[S.ORIGIN] == "search" and ss[S.SNAP_PREFER] == "best" and ss[K.SITE_ID] is None
    assert ss[K.START_UTC] != "2026-12-01T00:00:00"                    # inicio por defecto del proyecto
    req = S.build_request(dict(ss.filtered_state), ctx)
    assert req.snap_prefer == "best"
    from lsi import pipeline
    # el mismo punto acotado al rasgo que evalúa el análisis (radio = diámetro/2 del gazetteer)
    snap = pipeline.snap_candidate(ctx, req.lat_deg, req.lon_deg_e, prefer="best", profile_id=req.score_profile_id,
                                   mission_days=req.mission_days, feature_radius_km=pipeline.feature_radius_km(ctx, ss[K.SEARCH_SELECTED]))
    assert snap.kind == "best" and ss[K.START_UTC][:10] == snap.best_start_utc[:10]


def test_nearest_choice_keeps_period(at):
    shackleton(at)
    start = at.session_state[K.START_UTC]
    at.radio(key="_s_opt").set_value("nearest").run()
    at.button(key="_s_eval").click().run()
    assert not at.exception
    ss = at.session_state
    assert ss[S.SNAP_PREFER] == "nearest" and ss[K.START_UTC] == start


def test_ranking_only_for_planner_and_expert(at):
    shackleton(at)
    assert not any("Ranking de mejores puntos" in e.label for e in at.expander)
    at.sidebar.selectbox(key="_w_mode").set_value("Planificador").run()
    assert not at.exception
    assert any("Ranking de mejores puntos" in e.label for e in at.expander)
    assert any("Puesto" in d.value.columns for d in at.dataframe)


def test_malapert_has_no_snap_choice(at):
    at.multiselect(key="_s_types").set_value(["Mons"]).run()
    search(at, "mons malapert")
    assert not [r for r in at.radio if r.key == "_s_opt"]
    at.button(key="_s_eval").click().run()
    assert at.session_state[S.SNAP_PREFER] is None


def test_tycho_smooth_sphere_has_no_snap(at):
    search(at, "tycho")
    at.selectbox(key="_s_sel").select(6163).run()
    assert not [r for r in at.radio if r.key == "_s_opt"]
    at.button(key="_s_eval").click().run()
    assert at.session_state[S.SNAP_PREFER] is None


def test_custom_coordinates_never_snap():
    from ui import cache
    ctx = cache.get_context()
    s = {**S.default_state(ctx), S.ORIGIN: "custom", S.SNAP_PREFER: "best", S._GAZ: (3603, -85.0, 11.4, "x")}
    assert S.build_request(s, ctx).snap_prefer is None and S.build_request(s, ctx).gazetteer_id is None


def test_mission_site_first_with_confidence_and_smooth_sphere(at):
    search(at, "Apolo 11")
    first = at.selectbox(key="_s_sel").options[0]
    assert "Apolo 11 (Eagle)" in first and "coord. publicado" in first
    assert "Apolo 11" in " ".join(m.value for m in at.subheader)
    assert any("esfera lisa" in w.value and "sin datos de terreno" in w.value for w in at.warning)
    search(at, "Mar de la Tranquilidad")
    assert "Mare Tranquillitatis" in at.selectbox(key="_s_sel").options[0]


def test_snap_position_relative_to_feature_edge_is_shown(at):
    shackleton(at)
    t = md(at) + " " + " ".join(c.value for c in at.caption)
    assert "Posición respecto al rasgo" in t and "puesto" in t and "mapa de idoneidad" in t
    assert ("dentro del borde del cráter" in t) or ("fuera, en el margen del cráter" in t) or ("ningún punto candidato dentro del cráter" in t)
    assert "Punto más cercano al rasgo" in t            # la opción del más cercano sigue ofrecida
    at.button(key="_s_eval").click().run()
    assert not at.exception
    assert at.session_state[S.SNAP_PREFER] == "best"
    # tras evaluar, la barra lateral repite dónde cae el punto elegido respecto al borde y su puesto en el mapa
    side = " ".join(c.value for c in at.sidebar.caption)
    assert "Punto elegido:" in side and "puesto" in side
