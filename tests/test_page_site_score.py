"""Página «Idoneidad del emplazamiento»: Malapert (DEM) con rango, Apolo 11 (parcial), perfil y pesos."""
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import StateKey as K
from ui_cards import cards, legacy

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.fixture
def only_page(tmp_path, monkeypatch):
    shutil.copy(ROOT / "ui" / "pages" / "site_score.py", tmp_path / "site_score.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))


def run_app() -> AppTest:
    return legacy(AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)).run()


def body(at: AppTest) -> str:
    return " ".join(e.value for e in (*at.markdown, *at.caption, *at.info, *at.warning, *at.error, *at.subheader))


def score_of(at: AppTest) -> float:
    return float(at.metric[0].value.split()[0])


def planner(at: AppTest) -> AppTest:
    return at.sidebar.selectbox(key="_w_mode").set_value("Planificador").run()


def test_malapert_public_has_range_and_honest_message(only_page):
    at = run_app()
    assert not at.exception, at.exception
    assert at.session_state[K.SITE_ID] == "site23"
    # montaje por defecto en el polo: vertical con seguimiento (un panel plano daría <1 % y el rango colapsaría a [x, x])
    assert at.session_state[K.MOUNT_TYPE] == "vertical_az_tracking" and at.session_state["ui_mount_auto"] is True
    b = body(at)
    assert "no una certificación" in b and "Alcance y límites" in b
    assert "Rango" in b and "Semáforo" in b and "Confianza" in b
    assert "Rango no calculado" not in b
    lo, hi = [float(x.replace(",", ".")) for x in b.split("Rango ")[1].split("·")[0].replace("–", " ").split()[:2]]
    assert lo < hi                                   # DEM + incertidumbre activada + montaje correcto: rango no degenerado


def test_energy_panel_and_mount_always_shown(only_page):
    at = run_app()
    b = body(at)
    assert "Energía del score" in b and "Vertical con seguimiento azimutal" in b
    assert "Panel «" in b                            # energy_note del pipeline: panel y montaje usados
    assert "plano casi no produce" not in b          # el montaje correcto no avisa


def test_horizontal_in_polar_site_warns_and_range_is_narrow(only_page):
    at = planner(run_app())
    at.sidebar.multiselect(key="_w_panels").set_value(["tj-gaas-lander-body"]).run()    # admite horizontal pero no seguimiento
    assert at.session_state[K.MOUNT_TYPE] == "vertical_fixed"                           # automático: el mejor vertical que admite
    assert "no admite seguimiento" in " ".join(w.value for w in at.warning)             # y lo avisa (Idoneidad)
    at.sidebar.selectbox(key="_w_mount").set_value("horizontal").run()
    assert not at.exception, at.exception
    assert at.session_state["ui_mount_auto"] is False and at.session_state[K.MOUNT_TYPE] == "horizontal"
    b = body(at)
    assert "plano casi no produce" in b and "menos luz que uno vertical" in b
    assert "Horizontal" in b                         # el score dice qué montaje usó
    assert "estrecho" in b or "Rango no calculado" in b    # nunca [x, x] como si fuera un resultado
    at.sidebar.button(key="_w_mount_auto").click().run()
    assert at.session_state[K.MOUNT_TYPE] == "vertical_fixed" and "plano casi no produce" not in body(at)


def test_g5_gate_explained_when_present(only_page):
    at = planner(run_app())
    b = body(at)
    assert "Potencia útil del panel (G5)" in b and "potencia útil" in b
    assert "G5, potencia útil" in b


def test_estimated_panel_badge_in_score(only_page):
    at = planner(run_app())
    at.sidebar.multiselect(key="_w_panels").set_value(["perovskite-si-tandem-demo"]).run()
    assert not at.exception, at.exception
    assert "Panel estimado" in " ".join(badges(at))
    at.sidebar.multiselect(key="_w_panels").set_value(["tj-gaas-vertical-mast"]).run()
    assert "Panel estimado" not in " ".join(badges(at))


def test_range_text_never_shows_collapsed_range_as_result():
    from types import SimpleNamespace as NS
    from ui import components as C
    nc = NS(range_computed=False, score_min=9.5, score_max=9.5, partial=False)
    assert C.range_text(nc) == "Rango no calculado" and C.range_label(nc) == "no calculado"
    narrow = NS(range_computed=True, score_min=9.5, score_max=9.5, partial=False)
    assert "estrecho" in C.range_text(narrow)
    wide = NS(range_computed=True, score_min=6.0, score_max=10.0, partial=False)
    assert C.range_text(wide) == "Rango 6 – 10" and C.range_label(wide) == "6 – 10"
    part = NS(range_computed=False, score_min=20.0, score_max=80.0, partial=True)
    assert "no calculado" in C.range_text(part) and "terreno no evaluable" in C.range_text(part)


def test_malapert_planner_gates_breakdown_and_rescore_matches_pipeline(only_page):
    at = planner(run_app())
    assert not at.exception, at.exception
    b = body(at)
    assert "Puertas" in " ".join(s.value for s in at.subheader) and "dura" in b and "a calibrar" in b and "90 %" in b and "interpolados" in b


def test_rescore_equals_pipeline_score():
    import importlib.util
    import dataclasses
    import streamlit as st  # noqa: F401
    from lsi.analysis.site_score import params_from_config, profiles_from_config
    from ui import cache
    from lsi.contracts import AnalysisRequest
    spec = importlib.util.spec_from_file_location("site_score_page_mod", ROOT / "ui" / "pages" / "site_score.py")
    src = (ROOT / "ui" / "pages" / "site_score.py").read_text(encoding="utf-8").rsplit("\nmain()", 1)[0]
    ns: dict = {"__name__": "site_score_page_mod"}
    exec(compile(src, str(spec.origin), "exec"), ns)
    ctx = cache.get_context()
    req = AnalysisRequest(-85.99, 359.76, "2026-12-01T00:00:00", "2026-12-31T00:00:00", site_id="site23", with_uncertainty=True)
    res = cache.get_analysis(req)
    prof = profiles_from_config(ctx.cfg["score"])[req.score_profile_id]
    from lsi import pipeline
    mission = pipeline._mission(ctx, prof.mission_profile_id)
    g = {x.id: x for x in res.score.gates}
    cfg = {"profile": prof, "params": params_from_config(ctx.cfg["score"]), "mission": mission, "weights": None,
           "slope": g["G2"].limit, "dark": g["G4"].limit}
    r = ns["run"](res, cfg)
    assert r.score == pytest.approx(res.score.score) and r.score_min == pytest.approx(res.score.score_min)
    assert r.score_max == pytest.approx(res.score.score_max) and r.status == res.score.status
    assert (r.verdict, r.verdict_reason, r.verdict_provisional) == (res.score.verdict, res.score.verdict_reason, res.score.verdict_provisional)
    assert res.score.score_min < res.score.score_max and r.mission_days == res.score.mission_days
    # pesos distintos → otra nota
    r2 = ns["run"](res, {**cfg, "weights": {"sun": 0.1, "night": 0.1, "earth": 0.7, "terrain": 0.1}})
    assert r2.score != pytest.approx(r.score)
    assert dataclasses.is_dataclass(r2)
    # la noche máxima editada cambia la puerta G4 (límite del perfil), no se ignora
    r3 = ns["run"](res, {**cfg, "dark": 1000.0})
    assert next(x for x in r3.gates if x.id == "G4").limit == 1000.0


def test_change_profile_and_weights_changes_score(only_page):
    at = planner(run_app())
    s0 = score_of(at)
    at.selectbox[0].set_value("dte_comms").run()           # perfil Comunicaciones
    assert not at.exception, at.exception
    s_dte = score_of(at)
    assert s_dte != s0
    earth = next(s for s in at.slider if s.label.startswith("Tierra"))
    earth.set_value(0 if earth.value else 100).run()
    assert not at.exception and score_of(at) != s_dte


def test_apollo11_is_partial_with_wide_range(only_page):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception, at.exception
    b = body(at)
    assert "Modo parcial: sin datos de terreno" in b and "Sin DEM no hay datos de terreno" in b
    assert "Rango no calculado" in b and "terreno no evaluable" in b   # sin escenarios: no se presenta como rango de incertidumbre
    lo, hi = [float(x.replace(",", ".")) for x in b.split("la banda ")[1].split(" solo")[0].replace("–", " ").split()[:2]]
    assert hi - lo > 5                                    # la banda de terreno (pésimo–perfecto) sí es ancha
    planner(at)
    assert not at.exception
    assert any("¿Qué cambiaría" in s.value for s in at.subheader)


def badges(at: AppTest) -> list[str]:
    """Texto de las insignias (st.badge se pinta como markdown «:color-badge[:icono: texto]»)."""
    import re
    return [re.sub(r"^:[a-z]+-badge\[(:material/\w+: )?|\]$", "", m.value) for m in at.markdown if "-badge[" in m.value]


def test_malapert_verdict_matches_pipeline_and_window_is_shown(only_page):
    from ui import cache
    from lsi.contracts import AnalysisRequest
    at = planner(run_app())
    assert not at.exception, at.exception
    res = cache.get_analysis(AnalysisRequest(-85.99, 359.76, "2026-12-01T00:00:00", "2026-12-31T00:00:00", site_id="site23", with_uncertainty=True))
    sc = res.score
    assert sc.verdict in ("APTO", "CONDICIONAL", "NO APTO") and sc.mission_days == 14.0
    if at.session_state[K.START_UTC] == "2026-12-01T00:00:00" and at.session_state[K.END_UTC] == "2026-12-31T00:00:00":
        assert any(b.startswith(sc.verdict) for b in badges(at)), (sc.verdict, badges(at))
    b = body(at)
    assert "Ventana de misión" in " ".join(s.value for s in at.subheader)
    assert "Ventana evaluada" in b and "Mejor fecha" in " ".join(m.label for m in at.metric)
    assert any(m.label == "Duración de la misión" and m.value == "14 d" for m in at.metric)
    assert "(G0)" in b and "(G4)" in b
    assert "dura" in b and "Valor" in b and "margen" in b


def test_public_mode_plain_verdict_and_best_date(only_page):
    at = run_app()
    assert not at.exception, at.exception
    assert any("Cuándo mejor aterrizar" in s.value for s in at.subheader)
    b = body(at)
    assert "La mejor fecha candidata para aterrizar" in b or "Ninguna fecha" in b or "No se puede proponer" in b


def test_apollo11_verdict_is_no_data_or_provisional_no_apto(only_page):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception, at.exception
    lab = badges(at)
    assert any(x == "SIN DATOS" or x == "NO APTO (provisional)" for x in lab), lab
    assert not any(x in ("APTO", "CONDICIONAL") for x in lab)       # nunca apto con datos incompletos


def test_custom_mission_duration_flows_into_request(only_page):
    at = planner(run_app())
    at.sidebar.checkbox(key="_w_mdays_custom").set_value(True).run()
    at.sidebar.number_input(key="_w_mdays").set_value(7.0).run()
    assert not at.exception, at.exception
    assert at.session_state["ui_mission_days"] == 7.0
    assert any(m.label == "Duración de la misión" and m.value == "7 d" for m in at.metric)
    assert not any("menor que la misión" in w.value for w in at.sidebar.warning)


def test_period_shorter_than_mission_warns_and_is_no_data(only_page):
    at = planner(run_app())
    at.sidebar.checkbox(key="_w_mdays_custom").set_value(True).run()
    at.sidebar.number_input(key="_w_mdays").set_value(60.0).run()       # periodo por defecto = 30 d
    assert not at.exception, at.exception
    assert any("menor que la misión" in w.value for w in at.sidebar.warning)
    assert any("Alarga el periodo" in w.value for w in at.warning)
    assert any(x in ("SIN DATOS", "NO APTO") for x in badges(at))


def test_earth_score_explains_link_and_g7_gate(only_page):
    """s_Tierra usa el ENLACE (red + margen): la página lo explica con f_enlace/f_ref y muestra la puerta G7 con nombre propio."""
    at = planner(run_app())
    assert not at.exception, at.exception
    b = body(at)
    assert "usa el ENLACE posible, no la Tierra visible" in b and "f_ref" in b and "SIN red" in b
    assert "Hueco máximo sin enlace (G7)" in " ".join(m.value for m in at.markdown)
    assert "ventana continua de enlace posible" in b and "red NASA DSN" in b


def test_g7_failed_gives_conditional_with_plain_reason_and_gap_next_to_verdict(only_page):
    """Shackleton con margen de antena de 8°: el hueco sin enlace supera las 48 h del perfil (G7 blanda) → CONDICIONAL con el motivo llano."""
    at = planner(run_app())
    at.sidebar.selectbox(key="_w_site").set_value("site04").run()
    at.sidebar.slider(key="_w_lmargin").set_value(8.0).run()
    assert not at.exception, at.exception
    b = body(at)
    assert "Candidato con reservas" in b
    assert "supera lo tolerado por el perfil (48 h)" in b and "Hueco máximo sin comunicaciones:" in b
    assert "G7: puerta blanda" in b                  # el motivo del veredicto (el badge CONDICIONAL no es legible con AppTest)


def test_link_gap_line_and_gate_why_pure():
    from types import SimpleNamespace as NS

    from lsi.contracts import GateResult, GateStatus
    from ui import components as C
    g7 = GateResult("G7", GateStatus.FAIL, "x", hard=False, value=97.5, limit=48.0)
    res = NS(score=NS(gates=(g7,)), score_inputs=NS(max_link_gap_h=97.5))
    t = C.link_gap_line(res)
    assert "97,5 h" in t.replace(".", ",") and "puerta G7, blanda" in t
    assert "hueco sin comunicaciones de" in t and "supera lo tolerado por el perfil (48 h)" in t
    ok = NS(score=NS(gates=(GateResult("G7", GateStatus.PASS, "x", hard=False, value=3.0, limit=48.0),)), score_inputs=NS(max_link_gap_h=3.0))
    assert "supera" not in C.link_gap_line(ok) and "tolera 48 h" in C.link_gap_line(ok)
    assert C.link_gap_line(NS(score=NS(gates=()), score_inputs=NS(max_link_gap_h=None))) is None
