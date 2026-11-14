"""Pruebas de las figuras Plotly con datos sintéticos (los motores reales aún no existen)."""
import ast
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import pytest

from lsi.contracts import (
    AnalysisRequest, AnalysisResult, ContactWindow, et_to_utc_datetime, Body, BodyTrack, BodyVisibility, Countdown, DemWindow, Event, EventKind,
    GateResult, GateStatus, HorizonMode, HorizonParams, HorizonResult, MountingSpec, MountingType, ObserverPoint,
    PowerSeries, SiteMetrics, SiteScoreResult, SkySeries, SubScore, TimelineParams, TimelineResult,
    VisibilitySeries, VisibilityState, Window, WindowSet, BatteryResult,
)
from lsi.visualization import (capacity_plot, comparison_plot, contact_plot, horizon_plot, power_plot, score_plot, terrain3d, theme,
                               timeline_plot)

N = 289          # 2 días a 10 min
ET0 = 8.0e8
HERE = Path(__file__).resolve().parents[1] / "src" / "lsi" / "visualization"


def observer(mode=HorizonMode.DEM):
    return ObserverPoint(lat_deg=-89.5, lon_deg_e=10.0, x_m=100.0, y_m=-50.0, height_m=2.0, mode=mode,
                         ground_z_m=120.0 if mode == HorizonMode.DEM else None, label="Sitio A")


def horizon(limited_from=100, limited_to=140):
    az = np.arange(0, 360, 1.0)
    h = 2 + 3 * np.sin(np.radians(az))
    lim = np.zeros(az.size, bool)
    lim[limited_from:limited_to] = True
    return HorizonResult(az_deg=az, h_lb_deg=h, r_cov_m=np.full(az.size, 5000.0), limited=lim, mode=HorizonMode.DEM,
                         observer=observer(), params=HorizonParams(), h_sphere_deg=-0.02, cache_key="k",
                         h_ub_deg=h + np.where(lim, 4.0, 0.0))


def track(body, el0, az0):
    t = np.linspace(0, 4 * np.pi, N)
    return BodyTrack(body=body, az_deg=(az0 + 10 * t) % 360, el_deg=el0 + 6 * np.sin(t), dist_km=np.full(N, 1.5e8),
                     radius_deg=np.full(N, 0.267 if body == Body.SUN else 0.9 * 0.0 + 1.0))


def sky():
    et = ET0 + 600.0 * np.arange(N)
    return SkySeries(et=et, lat_deg=-89.5, lon_deg_e=10.0, height_m=2.0, sun=track(Body.SUN, 3.0, 90.0), earth=track(Body.EARTH, 5.0, 200.0))


def windows(label, spans):
    return WindowSet(label=label, windows=tuple(Window(ET0 + a * 3600, ET0 + b * 3600, left_truncated=(a == 0)) for a, b in spans),
                     t0_et=ET0, t1_et=ET0 + 48 * 3600, criterion="f>0")


def timeline():
    s = sky()
    z = np.zeros(N)
    vis = VisibilitySeries(et=s.et, sun=BodyVisibility(Body.SUN, z, np.full(N, 2, np.int8), z.astype(bool)),
                           earth=BodyVisibility(Body.EARTH, z, np.full(N, 1, np.int8), z.astype(bool)))
    ev = (Event(ET0 + 10 * 3600, Body.SUN, EventKind.SET, 120.0), Event(ET0 + 20 * 3600, Body.EARTH, EventKind.RISE, 200.0, truncated=True))
    return TimelineResult(et0=ET0, et1=ET0 + 48 * 3600, params=TimelineParams(), sun=windows("sun", [(0, 10), (22, 34)]),
                          earth=windows("earth", [(5, 25)]), overlap=windows("overlap", [(5, 10), (22, 25)]),
                          dark=windows("dark", [(10, 22)]), events=ev, series=vis, sun_pess=windows("sun", [(0, 8)]))


def power(i, clamp=False):
    et = ET0 + 600.0 * np.arange(N)
    p = np.clip(np.sin(np.linspace(0, 4 * np.pi, N)) * (1 - 0.2 * i), 0, 1)
    z = np.zeros(N)
    return PowerSeries(et=et, p_rel=p, f_sun=z, cos_inc=z, theta_deg=z, iam=z, t_panel_k=z, eta_rel=z, dist_factor=z,
                       t_clamped=(p == 0) if clamp else np.zeros(N, bool), panel_id=f"P{i}",
                       mounting=MountingSpec(MountingType.TILTED, tilt_deg=10.0 * i, azimuth_deg=0.0))


def subscores():
    return tuple(SubScore(k, k.capitalize(), 0.5, "", s, w, 5.0, 90.0)
                 for k, s, w in (("sun", 0.8, 0.4), ("night", 0.5, 0.2), ("earth", 0.7, 0.2), ("terrain", 0.9, 0.2)))


def score(partial=False):
    return SiteScoreResult(profile_id="p", score=62.0, score_min=48.0, score_max=75.0, subscores=subscores(), weakest_key="night",
                           gates=(GateResult("G1", GateStatus.PASS, "ok"), GateResult("G2", GateStatus.NO_DATA, "sin pendiente")),
                           status=GateStatus.NO_DATA, confidence=None, assumptions=(), partial=partial,
                           missing_keys=("terrain",) if partial else (), terrain_data=not partial)


def metrics(f):
    return SiteMetrics(period_s=172800.0, solar_fraction=f, effective_illumination=f, earth_fraction=0.5, overlap_fraction=0.2,
                       longest_sun_window_s=36000.0, longest_sun_window_truncated=True, max_darkness_s=7200.0, max_darkness_truncated=False,
                       longest_earth_window_s=3600.0, longest_overlap_s=1800.0, n_sun_windows=2, n_earth_windows=1,
                       max_sun_elevation_deg=6.0, max_earth_elevation_deg=9.0, unknown_fraction_sun=0.1, unknown_fraction_earth=0.1)


def result(f, partial=False):
    req = AnalysisRequest(-89.5, 10.0, "2026-01-01", "2026-01-03")
    return AnalysisResult(request=req, observer=observer(), horizon=horizon(), sky=sky(), timeline=timeline(), metrics=metrics(f),
                          warnings=(), score=score(partial))


def dem():
    z = 100 + 30 * np.add.outer(np.sin(np.linspace(0, 6, 120)), np.cos(np.linspace(0, 6, 150)))
    z[0, 0] = np.nan
    return DemWindow(data=z, x0_m=-300.0, y0_m=300.0, pixel_size_m=5.0), z


def names(fig):
    return [t.name for t in fig.data if t.name]


# ---------------------------------------------------------------- tema
def test_visualization_no_importa_streamlit_ni_otros_modulos():
    permitidos = {"plotly", "numpy", "lsi", "__future__", "typing", "datetime", "warnings"}
    for f in HERE.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for m in mods:
                top = m.split(".")[0]
                assert top != "streamlit"
                if top == "lsi":
                    assert m == "lsi.contracts" or m.startswith("lsi.visualization") or m == "lsi", (f.name, m)
                elif m:
                    assert top in permitidos, (f.name, m)


def test_et_to_datetimes_j2000():
    # ET=0 es 2000-01-01 12:00 TDB = 11:58:55.816 UTC
    d = theme.et_to_datetimes([0.0])[0]
    assert (d.year, d.month, d.day, d.hour, d.minute) == (2000, 1, 1, 11, 58)


def test_runs_y_interp_periodica():
    assert theme.runs([0, 1, 1, 0, 1]) == [(1, 2), (4, 4)]
    assert theme.runs([0, 0]) == []
    az, y = np.array([0.0, 180.0]), np.array([0.0, 10.0])
    assert theme.periodic_interp(270.0, az, y) == pytest.approx(5.0)   # entre 180 y 360(=0)


# ---------------------------------------------------------------- terreno
def test_terrain_3d_layout_no_solapa_barra_y_leyenda():
    """P1-1: barra de color fuera (derecha, estrecha), leyenda dentro (izquierda), escena a todo el ancho, botones cortos."""
    win, z = dem()
    fig = terrain3d.terrain_surface_3d(win, observer(), max_px=64)
    cb = next(t for t in fig.data if isinstance(t, go.Surface)).colorbar
    assert cb.x == 1.0 and cb.xanchor == "left" and cb.thickness <= 16
    assert fig.layout.legend.x < 0.1 and fig.layout.legend.xanchor == "left"
    assert fig.layout.margin.l <= 20 and fig.layout.margin.r <= 20
    assert list(fig.layout.scene.domain.x) == [0, 1]
    assert all(len(b.label) <= 14 for b in fig.layout.updatemenus[0].buttons)
    assert fig.layout.updatemenus[0].xanchor == "left"
    pm = terrain3d.terrain_polar_map(win, observer())
    assert pm.layout.legend.x < 0.1


def test_terrain_surface_capas_y_observador():
    win, z = dem()
    fig = terrain3d.terrain_surface_3d(win, observer(), layers={"uncertainty": np.abs(z) * 0.01, "sampling": np.ones_like(z)}, max_px=64)
    surf = [t for t in fig.data if isinstance(t, go.Surface)]
    assert len(surf) == 4 and sum(t.visible for t in surf) == 1
    assert surf[0].z.shape[0] <= 64 and surf[0].z.shape[1] <= 64
    assert any(isinstance(t, go.Scatter3d) and t.name == "Observador" for t in fig.data)
    assert len(fig.layout.updatemenus[0].buttons) == 4
    assert all(len(b.args[0]["visible"]) == len(fig.data) for b in fig.layout.updatemenus[0].buttons)


def test_downsample_promedio_independiente():
    a = np.arange(16, dtype=float).reshape(4, 4)
    out, f = terrain3d.downsample(a, max_px=2)
    assert f == 2 and out.tolist() == [[2.5, 4.5], [10.5, 12.5]]


def test_slope_plano_inclinado_45():
    z = np.add.outer(np.zeros(8), 5.0 * np.arange(8))          # sube 5 m cada 5 m
    assert terrain3d.slope_deg(z, 5.0)[4, 4] == pytest.approx(45.0)


def test_polar_map_con_y_sin_dem():
    win, _ = dem()
    assert any(isinstance(t, go.Heatmap) for t in terrain3d.terrain_polar_map(win, observer(), layer="slope").data)
    f2 = terrain3d.terrain_polar_map(None, observer(HorizonMode.SMOOTH_SPHERE))
    assert not any(isinstance(t, go.Heatmap) for t in f2.data)
    assert "Sin relieve" in f2.layout.annotations[0].text


# ---------------------------------------------------------------- horizonte
def test_horizon_cartesian_marca_limitados_y_cuerpos():
    s = sky()
    fig = horizon_plot.horizon_cartesian(horizon(), s, idx=0)
    assert horizon_plot.LIMITED_LABEL in names(fig)
    pat = [t for t in fig.data if t.name == horizon_plot.LIMITED_LABEL][0]
    assert pat.fillpattern.shape == "/" and pat.x[0] == 100.0
    assert any(n and n.startswith("Sol ·") for n in names(fig)) and any(n and n.startswith("Tierra ·") for n in names(fig))
    assert "Visibilidad geométrica" in fig.layout.annotations[-1].text


def test_estado_por_geometria():
    h = horizon()
    t = BodyTrack(Body.SUN, np.array([0.0] * 3), np.array([30.0, 2.0, -20.0]), np.ones(3), np.full(3, 0.267))
    assert [horizon_plot.body_state(h, t, i) for i in range(3)] == [VisibilityState.VISIBLE, VisibilityState.PARTIAL, VisibilityState.HIDDEN]


def test_horizon_polar_y_sin_h_ub():
    h = horizon()
    h.h_ub_deg = None
    fig = horizon_plot.horizon_polar(h, sky())
    assert fig.layout.polar.angularaxis.rotation == 90 and fig.layout.polar.angularaxis.direction == "clockwise"
    assert horizon_plot.LIMITED_LABEL in names(fig) and "Cota superior H_ub" not in names(fig)


def test_horizonte_sin_limitados_no_dibuja_tramos():
    assert horizon_plot.LIMITED_LABEL not in names(horizon_plot.horizon_cartesian(horizon(0, 0)))


# ---------------------------------------------------------------- línea temporal
def test_timeline_bandas_duracion_en_ms():
    tl = timeline()
    fig = timeline_plot.timeline_bands(tl, cursor_et=ET0 + 3600, zoom_et=timeline_plot.zoom_around(ET0 + 10 * 3600, 6))
    sun = [t for t in fig.data if t.name == "Sol visible"][0]
    assert list(sun.x) == [10 * 3600 * 1000.0, 12 * 3600 * 1000.0]
    assert sun.customdata[0][1] == "≥ "                       # ventana truncada por la izquierda
    assert any("pesimista" in (n or "") for n in names(fig))
    assert fig.layout.xaxis.rangeslider.visible is True and fig.layout.xaxis.range is not None
    assert len(fig.layout.shapes) == 1


def test_format_countdown():
    cd = Countdown(Body.SUN, ET0, True, None, 2 * 86400 + 3 * 3600 + 15 * 60, False, 45.0)
    assert timeline_plot.format_countdown(cd) == "2 d 03 h 15 min"
    cd2 = Countdown(Body.EARTH, ET0, False, None, None, False, 45.0)
    assert timeline_plot.format_countdown(cd2) == "—"


def test_countdown_figure_aproximado():
    ev = Event(ET0 + 3600, Body.SUN, EventKind.SET, 100.0)
    cds = [Countdown(Body.SUN, ET0, True, ev, 3600.0, True, 45.0), Countdown(Body.EARTH, ET0, False, None, None, False, 45.0)]
    texto = " ".join(a.text for a in timeline_plot.countdown_figure(cds).layout.annotations)
    assert "01 h 00 min" in texto and "puesta de Sol" in texto and "aproximado" in texto and "sin cambio" in texto


# ---------------------------------------------------------------- potencia
def test_power_varias_series_elevacion_y_bateria():
    ser = [power(1, clamp=True), power(2), power(3)]
    bat = BatteryResult(et=ser[0].et, soc=np.linspace(1, 0.2, N), unserved_wh=0.0, hours_unserved=0.0, min_soc=0.2)
    fig = power_plot.power_curves(ser, sky(), bat)
    lines = [t for t in fig.data if t.mode == "lines"]
    assert len({t.line.dash for t in lines[:3] + lines[-2:-1] if t.name.startswith("P")}) >= 3   # trazos distintos
    p = [t for t in fig.data if t.name == "P1 · tilted 10°"][0]
    assert max(p.y) == pytest.approx(80.0, abs=0.1)     # 100·p_rel con p_rel máx. 0.8
    assert "Extrapolación en frío" in names(fig) and "Carga de batería" in names(fig) and "Elevación solar (eje der.)" in names(fig)
    assert "No son vatios" in fig.layout.annotations[-1].text


def test_power_sin_extras():
    fig = power_plot.power_curves([power(1)])
    assert "Carga de batería" not in names(fig)


# ---------------------------------------------------------------- score
@pytest.mark.parametrize("fn", [score_plot.score_radar, score_plot.score_bars])
def test_score_figuras(fn):
    fig = fn(score(partial=True))
    textos = " ".join(a.text for a in fig.layout.annotations)
    assert "48" in fig.layout.title.text and "75" in fig.layout.title.text and "PARCIAL" in fig.layout.title.text
    assert "? sin datos suficientes" in textos and "✔ apto" in textos and "Sin datos de terreno" in textos


def test_score_bars_peso_y_eslabon():
    bars = score_plot.score_bars(score()).data[0]
    assert "peso 40%" in bars.text[0] and "◄ eslabón débil" in bars.text[1] and list(bars.x) == pytest.approx([80, 50, 70, 90])


def test_score_bars_y_radar_parcial_sin_nan():
    """Modo parcial: el terreno tiene s=NaN; se pinta «sin datos» (barra vacía rayada), nunca NaN."""
    import dataclasses
    import json
    import math
    subs = tuple(dataclasses.replace(x, s=math.nan, value=None, weight=0.0) if x.key == "terrain" else x for x in subscores())
    r = dataclasses.replace(score(partial=True), subscores=subs)
    bars = score_plot.score_bars(r)
    assert list(bars.data[0].y) == ["Sun", "Night", "Earth"] and list(bars.data[1].y) == ["Terrain"]
    assert "sin datos" in bars.data[1].text[0] and bars.data[1].marker.pattern.shape == "/"
    radar = score_plot.score_radar(r)
    assert "sin datos" in radar.data[0].text and "sin datos" in radar.data[0].theta[3]
    for fig in (bars, radar):
        assert "nan" not in json.dumps(fig.to_plotly_json(), default=str).lower().replace("\"nan\"", "")


def test_score_gates_blandas_marcadas():
    r = score()
    r.gates = (GateResult("G6", GateStatus.FAIL, "poca Tierra", hard=False),)
    assert "G6 (blanda)" in score_plot.score_bars(r).layout.annotations[0].text


# ---------------------------------------------------------------- comparación
def test_comparison_bars_truncado_y_valores():
    fig = comparison_plot.comparison_bars({"A": result(0.3), "B": result(0.6)})
    sol = [t for t in fig.data if t.name == "A"][0]
    assert sol.y[0] == pytest.approx(30.0)
    win = [t for t in fig.data if t.name == "B" and t.text[0].startswith("≥")]
    assert len(win) == 1 and win[0].y[0] == pytest.approx(10.0)         # 36000 s = 10 h, truncada
    assert len({t.marker.pattern.shape for t in fig.data}) == 2


def test_comparison_horizons_y_scores():
    res = {"A": result(0.3), "B": result(0.6, partial=True)}
    assert "A: limitado por cobertura" in names(comparison_plot.comparison_horizons(res))
    fs = comparison_plot.comparison_scores(res)
    assert [t.y[0] for t in fs.data] == ["A", "B (parcial)"]
    assert fs.data[0].error_x.array[0] == 13.0 and fs.data[0].error_x.arrayminus[0] == 14.0


# ---------------------------------------------------------------- contactos y capacidad
def contact(sid, a, b, tz="UTC"):
    u = lambda e: et_to_utc_datetime(e).strftime("%Y-%m-%dT%H:%M:%S")   # noqa: E731
    return ContactWindow(station_id=sid, station_name=f"Estación {sid}", complex=sid, tz=tz, start_et=a, end_et=b, start_utc=u(a),
                         end_utc=u(b), start_local=u(a).replace("T", " ") + " UTC", end_local=u(b).replace("T", " ") + " UTC",
                         start_solar_h=0.0, end_solar_h=1.0, duration_s=b - a, max_moon_el_deg=40.0, max_earth_el_deg=None)


DAYS = [("d1", ET0, ET0 + 86400.0), ("d2", ET0 + 86400.0, ET0 + 172800.0)]


def test_contact_chart_utc_parte_en_medianoche_y_distingue_estaciones():
    cs = [contact("A", ET0 + 82800, ET0 + 90000), contact("B", ET0 + 3600, ET0 + 7200)]
    fig = contact_plot.contact_chart(cs, DAYS, union=[(ET0 + 82800, ET0 + 90000), (ET0 + 3600, ET0 + 7200)], station_order=["A", "B"])
    a = [t for t in fig.data if "(A)" in (t.name or "")][0]
    assert list(a.y) == ["d1", "d2"] and list(a.base) == pytest.approx([23.0, 0.0]) and list(a.x) == pytest.approx([1.0, 1.0])
    patterns = {t.marker.pattern.shape for t in fig.data if t.name != contact_plot.UNION_NAME}
    colors = {t.marker.color for t in fig.data if t.name != contact_plot.UNION_NAME}
    assert len(patterns) == 2 and len(colors) == 2                      # patrón y color propios por estación
    assert contact_plot.UNION_NAME in names(fig) and fig.layout.barmode == "group"
    assert "No es presupuesto de enlace RF" in fig.layout.annotations[-1].text


def test_contact_chart_local_usa_su_reloj_y_sin_union():
    import datetime as dt

    def to_local(et, tz):                # zona ficticia UTC+2
        return et_to_utc_datetime(et).replace(tzinfo=dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=2)))
    from datetime import datetime
    from lsi.contracts import utc_datetime_to_et
    e0 = utc_datetime_to_et(datetime(2026, 12, 1))
    days = [("d1", e0, e0 + 86400.0), ("d2", e0 + 86400.0, e0 + 172800.0)]
    cs = [contact("A", e0 + 79200, e0 + 86400)]                          # 22:00-24:00 UTC = 00:00-02:00 local del día siguiente
    fig = contact_plot.contact_chart(cs, days, local=True, to_local=to_local, union=[(e0, e0 + 10)])
    t = fig.data[0]
    assert len(fig.data) == 1 and list(t.base) == pytest.approx([0.0]) and list(t.x) == pytest.approx([2.0])
    assert "local" in fig.layout.xaxis.title.text.lower()
    with pytest.raises(ValueError):
        contact_plot.contact_chart(cs, days, local=True)


def test_contact_chart_sin_contactos_es_none():
    assert contact_plot.contact_chart([], DAYS) is None
    assert contact_plot.contact_chart([contact("A", ET0 + 500000, ET0 + 600000)], DAYS) is None
    assert contact_plot.contact_chart([contact("A", ET0, ET0 + 10)], []) is None


def test_day_power_curve_vatios_son_prel_por_nominal():
    et = ET0 + np.arange(0, 86401, 600.0)
    p = np.where((et - ET0) < 43200, 0.5, 0.0)
    fig = capacity_plot.day_power_curve([("Panel X · vertical", et, p, 400.0), ("Panel Y", et, p, 200.0)], ET0,
                                        bands={0: (p * 300.0, p * 500.0)})
    lines = [t for t in fig.data if t.name in ("Panel X · vertical", "Panel Y")]
    assert max(lines[0].y) == pytest.approx(200.0) and max(lines[1].y) == pytest.approx(100.0)
    assert lines[0].line.dash != lines[1].line.dash and lines[0].marker.symbol != lines[1].marker.symbol
    assert any(t.fill == "tonexty" for t in fig.data) and fig.layout.yaxis.title.text.startswith("Potencia eléctrica")
