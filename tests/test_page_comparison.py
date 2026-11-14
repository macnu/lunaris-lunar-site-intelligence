"""Pantalla D «Comparación de sitios» con ``AppTest``: tres sitios DEM, sitio sin DEM, cambio de pesos y exportación."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui_cards import legacy

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "ui" / "pages" / "comparison.py"
pytestmark = pytest.mark.needs_spice


@pytest.fixture(scope="module")
def page_mod():
    for p in (str(ROOT), str(ROOT / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("lsi_page_comparison", PAGE)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m          # los dataclass lo necesitan
    spec.loader.exec_module(m)          # __name__ != "__main__": no ejecuta la página
    return m


@pytest.fixture
def run(tmp_path, monkeypatch):
    shutil.copy(PAGE, tmp_path / "comparison.py")        # carpeta con solo esta página: es la de inicio
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))

    def go(mode: str = "publico", points: str = "default", sites=None) -> AppTest:
        """``points``: «default» (puntos por defecto de cada sitio: las pruebas antiguas) o «cand» (el defecto de la página)."""
        at = legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=180))
        at.session_state[K.LANG_MODE] = mode
        at.session_state["cmp_points"] = points
        if sites:
            at.session_state[K.COMPARE_SITES] = at.session_state["cmp_pick"] = sites
        return at.run()
    return go


def table_with(at: AppTest, col: str):
    """Primera tabla que tiene la columna ``col`` (el orden de las tablas puede cambiar al añadir secciones)."""
    return next(df.value for df in at.dataframe if col in df.value.columns)


def sites_of(at: AppTest) -> list[str]:
    """Nombres de la primera tabla (Solar): una fila por sitio."""
    return list(at.dataframe[0].value["Sitio"])


def score_order(at: AppTest) -> list[str]:
    """Sitios ordenados por posición con «tus pesos» en la tabla de clasificación."""
    for df in at.dataframe:
        if "Posición (tus pesos)" in df.value.columns:
            return list(df.value.sort_values("Posición (tus pesos)")["Sitio"])
    raise AssertionError("no hay tabla de clasificación")


# --------------------------------------------------------------------------------------- tres sitios con DEM
def test_three_dem_sites_side_by_side(run):
    at = run("planificador")
    assert not at.exception
    assert "Alcance y límites" in " ".join(m.value for m in at.markdown)           # banda de avisos al inicio
    assert sites_of(at) == ["Site04", "Site11", "Site23"]
    assert len(at.dataframe) >= 5                                                  # solar, Tierra, terreno, confianza
    solar = table_with(at, "Fracción con Sol (%)")
    assert solar.loc[solar["Sitio"] == "Site23", "Fracción con Sol (%)"].iloc[0] > 30      # Malapert: ≈43 %
    assert "Pendiente p90 (°)" in table_with(at, "Modo").columns
    assert any("dentro del cráter Shackleton" in w.value for w in at.warning)      # punto por defecto de Site04 en pared
    assert any("Elegir otro punto" in b.label for b in at.button)
    assert not any("Cuál sale mejor" in s.value for s in at.subheader)           # solo en Público
    assert not any(t.key == "cmp_use_score" and t.value for t in at.toggle)        # score opcional: apagado


def test_public_mode_recommends_with_caveat(run):
    at = run("publico")
    assert not at.exception
    assert any("Cuál sale mejor con este perfil y por qué" in s.value for s in at.subheader)
    txt = " ".join(m.value for m in at.markdown)
    assert "Site23" in txt and "no un veredicto" in txt and "no significa «seguro»" in txt


def verdict_table(at: AppTest):
    for df in at.dataframe:
        if "Veredicto" in df.value.columns and "Motivo" in df.value.columns:
            return df.value
    raise AssertionError("no hay tabla de veredictos")


def test_verdict_table_matches_pipeline_and_no_apto_min(run, page_mod):
    import dataclasses
    from ui import cache, state as S
    at = run("planificador")
    assert not at.exception
    assert not hasattr(page_mod, "APTO_MIN")
    t = verdict_table(at)
    ctx = cache.get_context()
    base = S.build_request(dict(at.session_state.filtered_state), ctx)
    for e in page_mod.entries_from_tokens(ctx, ["site04", "site11", "site23"]):
        sc = cache.get_analysis(dataclasses.replace(base, lat_deg=e.lat, lon_deg_e=e.lon, site_id=e.site_id,
                                                 snap_prefer="nearest")).score
        row = t[t["Sitio"] == e.label].iloc[0]
        assert row["Veredicto"] == sc.verdict + (" (provisional)" if sc.verdict_provisional else "")
        assert row["Misión (d)"] == 14.0 and row["Motivo"] == sc.verdict_reason
    assert any("alguna parte del disco solar" in c.value for c in at.caption)


def test_uncertainty_can_be_requested_when_missing(run):
    at = run("planificador")
    assert not at.exception
    if any(b.key == "cmp_unc_btn" for b in at.button):          # solo si hay APTO/CONDICIONAL sin escenarios
        at.button(key="cmp_unc_btn").click().run()
        assert not at.exception and at.session_state["cmp_unc_force"] is True


def test_public_recommendation_has_plain_verdict_and_best_date(run):
    at = run("publico")
    assert not at.exception
    txt = " ".join(m.value for m in at.markdown)
    assert "La mejor fecha candidata para aterrizar" in txt or "Ninguna fecha" in txt or "No se puede proponer" in txt
    assert "No apto" in txt or "Candidato con reservas" in txt or "No se puede decidir" in txt or "Supera todas" in txt


# --------------------------------------------------------------------------------------- añadir un sitio sin DEM
def test_add_site_without_dem_warns_and_is_not_comparable(run):
    at = run("planificador")
    at.multiselect(key="cmp_pick").set_value(["site04", "site11", "site23", "apollo11"]).run()
    assert not at.exception
    assert "Apolo" in " ".join(sites_of(at))
    warn = " ".join(w.value for w in at.warning)
    assert "sin datos de terreno" in warn and "no es comparable" in warn
    terreno = table_with(at, "Modo")
    assert terreno.loc[terreno["Sitio"].str.startswith("Apolo"), "Modo"].iloc[0].startswith("Esfera lisa")
    assert at.session_state[K.COMPARE_SITES][-1] == "apollo11"


def test_custom_point_can_be_added_and_max_five(run):
    at = run("planificador")
    at.number_input(key="cmp_lat").set_value(-87.0)
    at.number_input(key="cmp_lon").set_value(20.0)
    at.button(key="cmp_add").click().run()
    assert not at.exception
    assert at.session_state[K.COMPARE_SITES][-1] == "@-87.0000,20.0000"
    assert len(sites_of(at)) == 4


# --------------------------------------------------------------------------------------- pesos
def test_changing_a_weight_changes_the_order(run):
    """Los pesos reordenan los sitios. El caso supone que Site04/Site11 se evalúan en su punto marcador (el cubierto más
    cercano), no en el mejor punto del DEM: con el snap al mejor punto Site11 ganaría ya con los pesos del perfil y la
    prueba no probaría el efecto de los pesos. Por eso la página comparación fija ``snap_prefer="nearest"`` (coherente con
    su aviso «se evalúa el punto marcador»)."""
    at = run("planificador")
    at.toggle(key="cmp_use_score").set_value(True).run()
    assert not at.exception
    pid = at.selectbox(key="cmp_profile").value
    before = score_order(at)
    assert before[0] == "Site23"                                                    # con los pesos del perfil
    for k, v in (("sun", 0), ("night", 0), ("earth", 0), ("terrain", 100)):
        at.slider(key=f"cmp_w_{pid}_{k}").set_value(v)
    at.run()
    assert not at.exception
    after = score_order(at)
    assert after != before and after[0] == "Site11"                                 # solo terreno: gana la pendiente
    assert any("cambia la clasificación" in s.value for s in at.success)
    assert any("Por qué cambia" in m.value for m in at.markdown)
    assert any("Desglose por sitio" in m.value for m in at.markdown)
    assert any("Pesos normalizados" in c.value and "Terreno (pendiente) 100 %" in c.value for c in at.caption)


# --------------------------------------------------------------------------------------- exportación y helpers
def test_export_csv_and_json(page_mod, run):
    from ui import cache
    at = run("planificador")
    ctx = cache.get_context()
    ents = page_mod.entries_from_tokens(ctx, ["site23", "apollo11"])
    from ui import state as S
    import dataclasses
    base = S.build_request(dict(at.session_state.filtered_state), ctx)
    res = {e.label: cache.get_analysis(dataclasses.replace(base, lat_deg=e.lat, lon_deg_e=e.lon, site_id=e.site_id)) for e in ents}
    csv = page_mod.csv_bytes(res).decode("utf-8")
    assert csv.splitlines()[0].startswith("metric,unit,Site23,Apolo 11")
    assert "solar_fraction" in csv
    d = json.loads(page_mod.json_bytes(res, {"sun": 0.5, "night": 0.5, "earth": 0.0, "terrain": 0.0}))
    assert set(d["sites"]) == set(res) and d["lsi_comparison"]["n_sites"] == 2
    assert all("metrics" in s and "warnings" in s for s in d["sites"].values())
    labels = [b.proto.label for b in at.get("download_button")]
    assert any("CSV" in l for l in labels) and any("JSON" in l for l in labels)


def test_best_names_and_ranks(page_mod):
    pool = ["a", "b", "c"]
    assert page_mod.best_names({"a": 1.0, "b": 3.0, "c": 3.0}, True, pool) == {"b", "c"}
    assert page_mod.best_names({"a": 1.0, "b": 3.0, "c": 2.0}, False, pool) == {"a"}
    assert page_mod.best_names({"a": 1.0, "b": 1.0, "c": 1.0}, True, pool) == set()            # sin diferencias: no resalta
    assert page_mod.best_names({"a": 1.0, "b": float("nan")}, True, ["a", "b"]) == set()      # un solo dato: no hay comparación
    assert page_mod.ranks({"a": 10.0, "b": 30.0, "c": 10.04}) == {"a": 2, "b": 1, "c": 2}


def test_comparison_and_score_give_same_figures_for_malapert(run, tmp_path_factory, monkeypatch):
    """P1-3: Comparación y Score leen el MISMO AnalysisResult (ventana de misión y periodo rotulados en ambas)."""
    from ui import components as C
    at = run("planificador")
    assert not at.exception
    ver = table_with(at, "Sol en la ventana de misión (%)")
    row = ver[ver["Sitio"] == "Site23"].iloc[0]
    solar = table_with(at, "Fracción con Sol (%)")
    sun_period = float(solar.loc[solar["Sitio"] == "Site23", "Fracción con Sol (%)"].iloc[0])
    assert any("Periodo analizado" in c.value and "ventana de misión del score" in c.value and "perfil" in c.value for c in at.caption)
    # Score: misma ventana y mismas cifras, rotuladas
    d = tmp_path_factory.mktemp("score_only")
    shutil.copy(ROOT / "ui" / "pages" / "site_score.py", d / "site_score.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(d))
    sc = legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=180))
    sc.session_state[K.LANG_MODE] = "planificador"
    sc.run()
    assert not sc.exception
    tab = next(df.value for df in sc.dataframe if "Ventana de misión (la del score)" in df.value.columns)
    t = tab.set_index("Medida")
    assert any("Periodo analizado" in c.value and "ventana de misión del score" in c.value for c in sc.caption)
    assert t.loc["Sol visible (%)", "Ventana de misión (la del score)"] == C.fmt_num(float(row["Sol en la ventana de misión (%)"]), 1)
    assert t.loc["Noche más larga (h)", "Ventana de misión (la del score)"] == C.fmt_num(float(row["Noche más larga en la ventana (h)"]), 1)
    assert t.loc["Sol visible (%)", "Periodo completo"] == C.fmt_num(sun_period, 1)
    # el Sol y la Tierra no se confunden: filas distintas con etiqueta propia
    assert t.loc["Tierra visible (%)", "Periodo completo"] != "" and "Tierra visible (%)" in t.index


def test_scope_figures_pure_unit():
    from types import SimpleNamespace as NS
    from ui import components as C
    m = NS(period_s=30 * 86400.0, solar_fraction=0.427, max_darkness_s=304.7 * 3600, earth_fraction=0.895)
    res = NS(metrics=m, request=NS(start_utc="2026-12-01T00:00:00", end_utc="2026-12-31T00:00:00", score_profile_id="p"),
             score=NS(window_start_utc="2026-12-16T00:00:00", window_end_utc="2026-12-30T00:00:00", mission_days=14.0),
             score_inputs=NS(f_sun=0.89, d_max_h=30.8, f_earth=0.5))
    f = C.scope_figures(res)
    assert (f["sun_period_pct"], f["sun_window_pct"], f["earth_window_pct"]) == pytest.approx((42.7, 89.0, 50.0))
    assert f["dark_period_h"] == pytest.approx(304.7) and f["dark_window_h"] == 30.8 and f["window_days"] == 14.0
    assert "30,0 d" in C.scope_caption(res, "Lander") and "14,0 d" in C.scope_caption(res, "Lander")


def test_range_not_computed_is_labelled_and_can_be_activated(run):
    at = run("planificador")
    assert not at.exception, at.exception
    t = verdict_table(at)
    assert set(t["Rango del score"]) == {"no calculado"}            # nunca [x, x] como si fuera un resultado
    body = " ".join(e.value for e in (*at.caption, *at.markdown))
    assert "Rango no calculado" in body
    at.button(key="cmp_rng_btn").click().run()
    assert not at.exception and at.session_state["cmp_unc_force"] is True
    t2 = verdict_table(at)
    assert "no calculado" not in set(t2["Rango del score"])         # activado: ahora son rangos de verdad
    assert not [b for b in at.button if b.key == "cmp_rng_btn"]


def test_panel_and_mount_used_are_listed_per_site_by_latitude(run):
    at = run("planificador")
    t = verdict_table(at)
    assert len(t) == 3 and all("Vertical con seguimiento azimutal" in v for v in t["Panel y montaje"])   # los tres son polares
    assert "plano casi no produce" not in " ".join(w.value for w in at.warning)
    assert "Panel y montaje" in " ".join(c.value for c in at.caption)


def test_link_columns_separate_from_geometric_earth(run):
    """«Tierra visible» (geometría) y «ENLACE POSIBLE» son columnas distintas; el hueco máximo sin enlace aparece con su unidad."""
    at = run("planificador")
    assert not at.exception
    t = table_with(at, "ENLACE POSIBLE (%)")
    assert "Tierra visible, geometría (%)" in t.columns and "Hueco máximo sin enlace (h)" in t.columns
    assert (t["ENLACE POSIBLE (%)"] <= t["Tierra visible, geometría (%)"] + 1e-6).all()      # el enlace es un subconjunto de la Tierra visible


# --------------------------------------------------------------------------------------- candidatos por defecto
def test_default_compares_candidates_not_markers(run):
    """Sin elegir nada, cada sitio con DEM se evalúa en su mejor candidato: Sol > 0 y la misma cifra que run_analysis en esa fecha."""
    from lsi import pipeline
    from ui import cache
    at = run("planificador", points="cand")
    assert not at.exception
    sites = sites_of(at)
    assert sites == ["Site04 (candidato)", "Site11 (candidato)", "Site23 (candidato)"]
    solar = table_with(at, "Fracción con Sol (%)")
    assert (solar["Fracción con Sol (%)"] > 0).all()
    assert any("candidato" in c.value for c in at.caption)
    assert not any("dentro del cráter Shackleton" in w.value for w in at.warning)     # ya no es el marcador de pared
    # coherencia con el motor: el veredicto de la tabla es el de run_analysis en el punto y la fecha del candidato
    ctx = cache.get_context()
    s11 = next(s for s in ctx.sites if s.id == "site11")
    from ui import state as S
    cand = S.best_candidate(ctx, s11.dem_prefix, "lander_solar_no_rhu", None)
    assert cand is not None and cand["score"] > 2
    ver = table_with(at, "Veredicto").set_index("Sitio")["Veredicto"]
    assert len(ver) == 3 and "SIN DATOS" not in set(ver)           # periodo = ventana de misión + margen: nunca «más corto que la misión»
    from datetime import datetime, timedelta
    from lsi.contracts import AnalysisRequest
    c = S.best_candidate(ctx, s11.dem_prefix, "lander_solar_no_rhu", None)
    st0 = datetime.fromisoformat(c["start_utc"])
    res = pipeline.run_analysis(ctx, AnalysisRequest(lat_deg=c["lat"], lon_deg_e=c["lon"], site_id="site11", start_utc=S.fmt_utc(st0),
                                                     end_utc=S.fmt_utc(st0 + timedelta(days=c["days"], hours=1)),
                                                     score_profile_id="lander_solar_no_rhu"))
    assert res.metrics.solar_fraction > 0 and ver["Site11 (candidato)"] == res.score.verdict


def test_far_field_point_is_not_called_sphere(run):
    """Un punto personalizado polar fuera de los recortes: «relieve aproximado (80 m)», nunca «esfera lisa»."""
    at = run("planificador", points="default", sites=["site23", "@-88.0000,40.0000"])
    assert not at.exception
    texto = " ".join([w.value for w in at.warning] + [m.value for m in at.markdown] + [str(df.value.to_dict("list")) for df in at.dataframe])
    assert "Relieve aproximado (80 m)" in texto or "relieve aproximado (80 m)" in texto
    assert "esfera lisa" not in texto.lower()


def test_recommendation_states_unit_once(page_mod, monkeypatch):
    """«Sol: 79 % del tiempo (los demás: 0 % y 0 %)»: la unidad una sola vez."""
    from types import SimpleNamespace as NS
    monkeypatch.setattr(page_mod.C, "best_date_sentence", lambda sc: "fecha")
    monkeypatch.setattr(page_mod.C, "verdict_sentence", lambda sc: "frase")

    def res(f):
        sc = NS(verdict="NO APTO", score=f * 100)
        return NS(score=sc, metrics=NS(solar_fraction=f, max_darkness_s=3600.0, link_fraction=None, earth_fraction=f, max_link_gap_s=0),
                  slope=None)
    txt = " ".join(page_mod.recommendation({"A": res(0.79), "B": res(0.0), "C": res(0.0)}, ["A", "B", "C"], "x"))
    assert "Sol: 79 % del tiempo (los demás: 0 % y 0 %)" in txt
