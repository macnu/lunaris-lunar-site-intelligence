"""T19: base de la UI con ``streamlit.testing.v1.AppTest`` (app sin páginas, sidebar con/sin DEM, error de fecha) y helpers puros."""
import math
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import (
    STANDARD_WARNINGS_ES, AnalysisRequest, MountingType, StateKey as K, WarningCode,
)
from ui import PAGE_SPECS, discover_pages
from ui import state as S
from ui_cards import cards

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.needs_spice


@pytest.fixture
def no_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))     # carpeta vacía: la base se prueba sin páginas
    return tmp_path


def run_app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()


def texts(at: AppTest) -> str:
    return " ".join(e.value for e in (*at.sidebar.markdown, *at.sidebar.caption, *at.sidebar.error, *at.sidebar.success,
                                       *at.sidebar.warning))


# --------------------------------------------------------------------------------------- arranque
def test_app_starts_without_pages(no_pages):
    at = run_app()
    assert not at.exception
    assert any("páginas" in i.value for i in at.info)
    assert "Alcance y límites" in " ".join(m.value for m in at.markdown)       # banda de avisos siempre visible
    assert at.session_state[K.SITE_ID] == "site23" and at.session_state[K.LANG_MODE] == "publico"


def test_discover_pages_tolerates_missing(tmp_path):
    (tmp_path / "search.py").write_text("")
    (tmp_path / "about.py").write_text("")
    found, missing = discover_pages(tmp_path)
    assert [p.stem for p, _, _ in found] == ["search", "about"]
    assert missing == [n for n, _, _ in PAGE_SPECS if n not in ("search", "about")]
    assert discover_pages(tmp_path / "no_existe")[0] == []


# --------------------------------------------------------------------------------------- sidebar: sitios
def test_sidebar_site_with_dem_malapert(no_pages):
    at = run_app()
    assert "Modo DEM" in texts(at) and "Site23" in texts(at)
    assert not at.sidebar.error
    from ui.cache import get_context
    req = S.build_request(dict(at.session_state.filtered_state), get_context())
    assert isinstance(req, AnalysisRequest) and req.site_id == "site23" and -90 < req.lat_deg < -85


def test_sidebar_site_without_dem_apollo11(no_pages):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception and not at.sidebar.error
    assert "esfera lisa" in texts(at)
    assert at.session_state[K.SITE_ID] == "apollo11"
    assert at.session_state[K.OBS_LAT] == pytest.approx(0.6741)


def test_custom_coordinates_outside_dem_use_smooth_sphere(no_pages):
    at = run_app()
    at.sidebar.selectbox(key="_w_site").set_value("@custom").run()
    at.sidebar.number_input(key="_w_lat").set_value(10.0).run()
    assert at.session_state[S.ORIGIN] == "custom" and at.session_state[K.SITE_ID] is None
    assert at.session_state[K.OBS_LAT] == 10.0 and "esfera lisa" in texts(at)


# --------------------------------------------------------------------------------------- sidebar: fechas
@pytest.mark.parametrize("bad", ["2060-01-01 00:00", "1800-05-05 00:00", "mañana"])
def test_bad_date_is_a_message_not_a_traceback(no_pages, bad):
    at = run_app()
    start_before = at.session_state[K.START_UTC]
    at.sidebar.text_input(key="_w_start").set_value(bad).run()
    assert not at.exception
    assert at.sidebar.error and ("rango" in at.sidebar.error[0].value or "formato" in at.sidebar.error[0].value)
    assert at.session_state[K.START_UTC] == start_before            # no se pisa el estado válido
    assert at.session_state["_ui_errors"]["period"]
    assert at.sidebar.text_input(key="_w_start").value == bad       # se conserva lo escrito para corregirlo
    at.sidebar.text_input(key="_w_start").set_value("2027-01-01 12:00").run()
    assert not at.sidebar.error and at.session_state[K.START_UTC] == "2027-01-01T12:00:00"


def test_period_end_beyond_kernels_is_rejected(no_pages):
    at = run_app()
    at.sidebar.text_input(key="_w_start").set_value("2050-12-25 00:00").run()      # + 14 d pasa de 2050-12-30
    assert not at.exception and "fuera del rango" in at.sidebar.error[0].value


def test_validate_period_pure():
    d = datetime
    assert S.validate_period(d(2026, 12, 1), d(2026, 12, 31)) is None
    assert "rango" in S.validate_period(d(1899, 1, 1), d(1899, 2, 1))
    assert "positiva" in S.validate_period(d(2026, 12, 1), d(2026, 12, 1))
    assert "máximo" in S.validate_period(d(2026, 1, 1), d(2028, 1, 1))
    assert S.parse_utc("2026-12-01T06:30:00Z") == d(2026, 12, 1, 6, 30)
    with pytest.raises(ValueError, match="formato"):
        S.parse_utc("ayer")


# --------------------------------------------------------------------------------------- estado y petición
def test_build_request_is_pure_and_hashable(no_pages):
    at = run_app()
    ss = dict(at.session_state.filtered_state)
    from ui.cache import get_context
    ctx = get_context()
    r1, r2 = S.build_request(ss, ctx), S.build_request(ss, ctx)
    assert r1 == r2 and hash(r1) == hash(r2) and repr(r1) == repr(r2)
    assert r1.step_s == 600.0 and r1.now_utc is None and r1.gazetteer_id is None
    # panel con montaje no admitido → montaje por defecto del panel; inclinado lleva inclinación
    ss.update({K.PANEL_ID: "perovskite-si-tandem-demo", K.MOUNT_TYPE: "vertical_fixed"})
    assert S.build_request(ss, ctx).mounting.type is MountingType.HORIZONTAL
    ss.update({K.PANEL_ID: "tj-gaas-lander-body", K.MOUNT_TYPE: "tilted", K.MOUNT_TILT: 20.0, K.MOUNT_AZ: 90.0})
    m = S.build_request(ss, ctx).mounting
    assert (m.type, m.tilt_deg, m.azimuth_deg) == (MountingType.TILTED, 20.0, 90.0)
    # buscador: solo origen 'search' lleva gazetteer_id
    ss.update({S.ORIGIN: "search", "_ui_gaz": (16338, -85.9, 0.0, "Mons Malapert"), K.SITE_ID: None})
    assert S.build_request(ss, ctx).gazetteer_id == 16338
    ss[S.ORIGIN] = "custom"
    assert S.build_request(ss, ctx).gazetteer_id is None


def test_mission_days_default_custom_and_short_period_warning(no_pages):
    from ui.cache import get_context
    ctx = get_context()
    at = run_app()
    ss = dict(at.session_state.filtered_state)
    assert S.build_request(ss, ctx).mission_days is None                   # por defecto: la del perfil (14 d, lander solar)
    assert S.effective_mission_days(ctx, ss) == 14.0
    assert S.build_request({**ss, S.MISSION_DAYS: 21.0}, ctx).mission_days == 21.0
    assert S.profile_mission_days(ctx, "custom") is None
    # control de la barra lateral (Planificador): personalizada → llega a la petición; periodo < misión → aviso
    at.sidebar.selectbox(key="_w_mode").set_value("Planificador").run()
    assert not at.sidebar.warning or "menor que la misión" not in texts(at)
    at.sidebar.checkbox(key="_w_mdays_custom").set_value(True).run()
    at.sidebar.number_input(key="_w_mdays").set_value(45.0).run()          # periodo por defecto = 30 d
    assert not at.exception and at.session_state[S.MISSION_DAYS] == 45.0
    assert "menor que la misión" in texts(at) and "SIN DATOS" in texts(at)
    at.sidebar.checkbox(key="_w_mdays_custom").set_value(False).run()
    assert at.session_state[S.MISSION_DAYS] is None and "menor que la misión" not in texts(at)


def test_mode_switch_changes_detail_level(no_pages):
    at = run_app()
    assert "_w_height" not in [w.key for w in at.sidebar.number_input]       # Público: sin altura
    at.sidebar.selectbox(key="_w_mode").set_value("Experto").run()
    assert not at.exception and at.session_state[K.LANG_MODE] == "experto"
    keys = [w.key for w in at.sidebar.number_input] + [w.key for w in at.sidebar.multiselect]
    assert "_w_height" in keys and "_w_panels" in keys and "_w_dust" in keys


# --------------------------------------------------------------------------------------- caché y componentes
def test_get_analysis_is_cached_and_error_is_message():
    from lsi.contracts import DateOutOfRangeError
    from ui import cache
    req = AnalysisRequest(0.6741, 23.473, "2026-12-01T00:00:00", "2026-12-03T00:00:00", site_id="apollo11")
    a, err = cache.try_analysis(req)
    b, _ = cache.try_analysis(req)
    assert err is None and a is b                                   # segunda llamada: caché, sin recálculo
    bad, msg = cache.try_analysis(AnalysisRequest(0.0, 0.0, "2060-01-01T00:00:00", "2060-01-02T00:00:00"))
    assert bad is None and "1900" in msg and "2050" in msg
    assert isinstance(DateOutOfRangeError("x"), Exception)


def test_warnings_band_always_shows_core_warnings():
    def app():
        from ui import components as C
        C.warnings_band()
    at = AppTest.from_function(app).run()
    body = " ".join(m.value for m in (*at.markdown, *at.caption))
    assert "Visibilidad geométrica ≠ potencia ni enlace garantizados" in body
    for c in (WarningCode.GEOMETRIC_ONLY, WarningCode.ECLIPSES_NOT_MODELED, WarningCode.DEM_EFFECTIVE_RESOLUTION):
        assert STANDARD_WARNINGS_ES[c] in body


def test_warnings_band_with_sphere_result_shows_no_terrain_and_hides_dem_resolution():
    def app():
        from lsi.contracts import AnalysisRequest
        from ui import cache, components as C
        r = cache.get_analysis(AnalysisRequest(0.6741, 23.473, "2026-12-01T00:00:00", "2026-12-03T00:00:00", site_id="apollo11"))
        C.result_header(r)
        C.warnings_band(r)
        C.confidence_badge("baja")
        C.metric_card("Ventana más larga", 7200.0, truncated=True, unit="s")
    at = AppTest.from_function(app, default_timeout=90).run()
    assert not at.exception
    warn = " ".join(w.value for w in at.warning)
    assert STANDARD_WARNINGS_ES[WarningCode.NO_DEM_SMOOTH_SPHERE] in warn
    assert STANDARD_WARNINGS_ES[WarningCode.DEM_EFFECTIVE_RESOLUTION] not in " ".join(c.value for c in at.caption)
    assert cards(at)[0].value.startswith("≥ ")


def test_glossary_levels_and_formatters():
    from ui import components as C
    assert all(t and p and q for t, (p, q) in C.GLOSSARY.items())
    assert C.fmt_num(None) == "—" and C.fmt_num(float("nan")) == "—" and C.fmt_num(1234.5, 1) == "1 234,5"
    assert C.fmt_duration(3 * 3600 + 25 * 60) == "3 h 25 min" and C.fmt_duration(7200, truncated=True) == "≥ 2 h 00 min"
    assert C.fmt_duration(5 * 86400) == "5,0 d" and C.fmt_pct(0.256) == "25,6 %"
    assert "Elige fechas" in C.friendly_error(__import__("lsi.contracts", fromlist=["x"]).DateOutOfRangeError("fuera"))


def test_downloads_json_and_csv_zip():
    import json
    import zipfile
    import io
    from ui import cache, components as C
    r = cache.get_analysis(AnalysisRequest(0.6741, 23.473, "2026-12-01T00:00:00", "2026-12-03T00:00:00", site_id="apollo11"))
    d = json.loads(C.result_json_bytes(r))
    assert d["observer"]["mode"] == "smooth_sphere" and d["warnings"]
    names = zipfile.ZipFile(io.BytesIO(C.result_csv_zip_bytes(r))).namelist()
    assert {"timeseries.csv", "windows.csv", "horizon.csv", "metrics.csv", "metadata.json"} <= set(names)


def test_observer_and_snap_cache_use_the_request_profile():
    """``get_observer`` y ``get_analysis`` resuelven el mismo punto (misma preferencia, perfil y duración), y ``get_snap``
    con esos argumentos devuelve el mismo punto que ``resolve_observer``."""
    import dataclasses
    from ui import cache
    base = AnalysisRequest(-89.54, 129.78, "2026-12-01T00:00:00", "2026-12-03T00:00:00", gazetteer_id=3603, mission_days=14.0)
    for prefer in ("best", "nearest"):
        req = dataclasses.replace(base, snap_prefer=prefer)
        o, _w, err = cache.get_observer(req)
        assert err is None and o.snap_kind in (prefer, "default_observer")
        s = cache.get_snap(req.lat_deg, req.lon_deg_e, prefer=prefer, profile_id=req.score_profile_id, mission_days=14.0)
        assert (s.lat_deg, s.lon_deg_e) == pytest.approx((o.lat_deg, o.lon_deg_e))


# --------------------------------------------------------------------------------------- montaje por latitud
def test_default_mount_by_latitude_and_polar_penalty():
    from ui.cache import get_context
    by = {p.id: p for p in get_context().panels.panels}
    M = MountingType
    assert S.default_mount(by["tj-gaas-vertical-mast"], -86.0) is M.VERTICAL_AZ_TRACKING
    assert S.default_mount(by["mj-4j-high-eff"], -89.9) is M.VERTICAL_AZ_TRACKING
    assert S.default_mount(by["tj-gaas-lander-body"], -86.0) is M.VERTICAL_FIXED       # no admite seguimiento
    assert S.default_mount(by["tj-gaas-lander-body"], -30.0) is M.HORIZONTAL           # horizontal solo a latitudes bajas
    assert S.default_mount(by["tj-gaas-vertical-mast"], 0.0) is by["tj-gaas-vertical-mast"].mounting_default  # no admite horizontal
    h, ratio = S.polar_penalty(-89.9)
    assert 1.5 < h < 1.8 and 30 < ratio < 40 and abs(ratio - 1 / math.tan(math.radians(h))) < 1e-9
    assert S.polar_penalty(-86.0)[1] < S.polar_penalty(-89.9)[1]


def test_default_state_is_vertical_tracking_at_malapert(no_pages):
    at = run_app()
    ss = at.session_state
    assert ss[K.PANEL_ID] == "tj-gaas-vertical-mast" and ss[K.MOUNT_TYPE] == "vertical_az_tracking" and ss[S.MOUNT_AUTO] is True
    from ui.cache import get_context
    assert S.build_request(dict(ss.filtered_state), get_context()).mounting.type is MountingType.VERTICAL_AZ_TRACKING
    # sitio ecuatorial con el panel de lander (admite horizontal): el automático pasa a horizontal; vuelve a vertical_fixed al volver al polo
    S_ = S
    at.sidebar.selectbox(key="_w_mode").set_value("Planificador").run()
    at.sidebar.multiselect(key="_w_panels").set_value(["tj-gaas-lander-body"]).run()
    assert at.session_state[K.MOUNT_TYPE] == "vertical_fixed"
    at.sidebar.selectbox(key="_w_site").set_value("apollo11").run()
    assert not at.exception and at.session_state[K.MOUNT_TYPE] == "horizontal" and at.session_state[S_.MOUNT_AUTO] is True


def _warn_app(lat, mount):
    from ui import components as C
    C.polar_horizontal_warning(lat, mount)


def test_polar_horizontal_warning_text():
    at = AppTest.from_function(_warn_app, args=(-89.9, "horizontal")).run()
    assert any("plano casi no produce" in w.value and "× menos luz que uno vertical" in w.value for w in at.warning)
    for lat, m in ((-89.9, "vertical_az_tracking"), (-30.0, "horizontal")):
        assert not AppTest.from_function(_warn_app, args=(lat, m)).run().warning


def test_snap_phrase_inside_outside_and_rank():
    from ui import components as C
    assert C.snap_phrase(-0.34, True, 3, "cráter") == "a 0,34 km dentro del borde del cráter; puesto 3 del mapa de idoneidad"
    assert C.snap_phrase(0.2, True, None, "cráter") == "a 0,20 km fuera, en el margen del cráter"
    assert "ningún punto candidato dentro del cráter" in C.snap_phrase(1.5, False, None, "cráter")
    assert C.snap_phrase(None, None, None) == ""
    assert C.GATE_NAME["G5"].startswith("Potencia útil") and "G5" in C._GATE_SHORT


def test_best_date_sentence_does_not_give_a_percentage_for_a_single_start():
    from ui import components as C
    from types import SimpleNamespace as NS
    base = dict(mission_days=14.0, best_start_utc="2026-12-16T00:00:00", best_window_end_utc="2026-12-30T00:00:00", partial=False)
    one = C.best_date_sentence(NS(**base, feasible_start_fraction=1.0, n_starts=1))
    assert "100" not in one and "una fecha de inicio" in one
    many = C.best_date_sentence(NS(**base, feasible_start_fraction=5 / 366, n_starts=366))
    assert "5 de 366" in many
