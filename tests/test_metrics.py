"""Pruebas de analysis.metrics: casos matematica.md §5.4 y propiedades del álgebra de intervalos."""
import numpy as np
import pytest

from lsi.analysis.metrics import (
    clip, complement, compute_metrics, comparison_table, daily_table, intersection, intervals,
    longest_window, merge, total_duration, union, window_set, windows_from_mask,
)
from lsi.contracts import (
    Body, BodyVisibility, SkySeries, BodyTrack, TimelineParams, TimelineResult, VisibilitySeries,
    VisibilityParams,
)

H = 3600.0
A = [[0, 10], [20, 30]]
B = [[5, 25]]


def test_solape_y_union_caso_5_4():
    assert intersection(A, B).tolist() == [[5, 10], [20, 25]]
    assert union(A, B).tolist() == [[0, 30]]


def test_merge_tolerancia():
    assert merge([[0, 1], [1.5, 2]], tol=1.0).tolist() == [[0, 2]]
    assert merge([[0, 1], [1.5, 2]], tol=0.1).tolist() == [[0, 1], [1.5, 2]]
    assert merge([[3, 3], [5, 4]]).shape == (0, 2)


def test_complemento_y_vacios():
    assert complement(A, 0, 40).tolist() == [[10, 20], [30, 40]]
    assert complement([], 0, 5).tolist() == [[0, 5]]
    assert complement([[0, 5]], 0, 5).shape == (0, 2)


def test_ventana_sintetica_5_4_raices_y_duracion():
    # e(t)=1.5°·sin(2πt/24h); f>ε ⇔ e > t*·ρ con t*=-0.985926, ρ=0.26649°
    t = np.arange(-1 * H, 13 * H + 1, 1.0)
    e = 1.5 * np.sin(2 * np.pi * t / (24 * H))
    iv = windows_from_mask(t, e > -0.985926 * 0.26649)
    assert iv.shape == (1, 2)
    assert abs(iv[0, 0] / H - (-0.672530)) < 1.5 / H
    assert abs(iv[0, 1] / H - 12.672530) < 1.5 / H
    assert abs((iv[0, 1] - iv[0, 0]) / H - 13.345060) < 3 / H


def test_truncado_6h_caso_5_4():
    t = np.arange(0, 6 * H + 1, 60.0)
    e = 1.5 * np.sin(2 * np.pi * t / (24 * H))
    ws = window_set(windows_from_mask(t, e > -0.26273), 0.0, 6 * H, "sun")
    w = ws.windows[0]
    assert len(ws.windows) == 1 and w.left_truncated and w.right_truncated and w.end_et == 6 * H
    assert longest_window(ws) == (6 * H, True)


def test_ventana_no_truncada_y_vacia():
    ws = window_set([[2, 4], [6, 9]], 0, 10, "x")
    assert longest_window(ws) == (3.0, False)
    assert longest_window(window_set([], 0, 10, "x")) == (0.0, False)


def test_mascara_racha_final_usa_t1():
    t = np.array([0.0, 1, 2, 3])
    assert windows_from_mask(t, [0, 1, 1, 1]).tolist() == [[1, 3]]
    assert windows_from_mask(t, [1, 0, 1, 0]).tolist() == [[0, 1], [2, 3]]


def _rand_iv(rng, n=8):
    p = np.sort(rng.uniform(0, 100, 2 * n))
    return p.reshape(-1, 2)[rng.permutation(n)]


@pytest.mark.parametrize("seed", range(20))
def test_propiedades(seed):
    rng = np.random.default_rng(seed)
    a, b = _rand_iv(rng), _rand_iv(rng, 5)
    assert np.allclose(intersection(a, b), intersection(b, a))
    assert np.allclose(union(a, b), union(b, a))
    assert np.allclose(complement(complement(a, 0, 100), 0, 100), merge(a))
    ca = total_duration(a, 0, 100) / 100
    assert ca + total_duration(complement(a, 0, 100)) / 100 == pytest.approx(1.0)
    # |A∪B| = |A|+|B|-|A∩B|
    assert total_duration(union(a, b)) == pytest.approx(
        total_duration(merge(a)) + total_duration(merge(b)) - total_duration(intersection(a, b)))
    # De Morgan
    lhs = complement(union(a, b), 0, 100)
    rhs = intersection(complement(a, 0, 100), complement(b, 0, 100))
    assert np.allclose(lhs, rhs)


def _timeline():
    et0, et1 = 0.0, 2 * 86400.0
    t = np.arange(et0, et1 + 1, 600.0)
    sun_iv = [[0, 6 * H], [20 * H, 30 * H]]
    earth_iv = [[4 * H, 25 * H], [40 * H, 48 * H]]
    f = np.zeros_like(t)
    for a, b in sun_iv:
        f[(t >= a) & (t < b)] = 1.0
    z = np.zeros_like(t)
    unk = np.zeros(len(t), bool); unk[:len(t) // 4] = True

    def vis(body, ff):
        return BodyVisibility(body, ff, np.zeros(len(t), np.int8), unk if body == Body.SUN else ~unk)

    def trk(body, el):
        return BodyTrack(body, z, el, z, z)

    sky = SkySeries(t, -89.0, 0.0, 2.0, trk(Body.SUN, np.where(f > 0, 1.5, -3.0)), trk(Body.EARTH, z + 2.0))
    series = VisibilitySeries(t, vis(Body.SUN, f), vis(Body.EARTH, z + 1.0))
    sun = window_set(sun_iv, et0, et1, "sun")
    earth = window_set(earth_iv, et0, et1, "earth")
    ov = window_set(intersection(sun_iv, earth_iv), et0, et1, "overlap")
    dark = window_set(complement(sun_iv, et0, et1), et0, et1, "dark")
    tl = TimelineResult(et0, et1, TimelineParams(), sun, earth, ov, dark, (), series)
    return tl, sky


def test_compute_metrics_y_fracciones():
    tl, sky = _timeline()
    m = compute_metrics(tl, sky, None, VisibilityParams())
    T = 48 * H
    assert m.period_s == T
    assert m.solar_fraction == pytest.approx(16 / 48)
    assert m.earth_fraction == pytest.approx(29 / 48)
    assert m.overlap_fraction == pytest.approx((2 + 5) / 48)
    assert m.longest_sun_window_s == 10 * H and not m.longest_sun_window_truncated
    # oscuridad: [6,20) 14 h, [30,48] 18 h truncada por la derecha
    assert m.max_darkness_s == 18 * H and m.max_darkness_truncated
    assert m.longest_overlap_s == 5 * H
    assert (m.n_sun_windows, m.n_earth_windows) == (2, 2)
    assert m.max_sun_elevation_deg == 1.5 and m.max_earth_elevation_deg == 2.0
    assert m.effective_illumination == pytest.approx(16 / 48, abs=2e-3)
    assert m.unknown_fraction_sun == pytest.approx(0.25, abs=0.01)
    # suma de fracciones sol + oscuridad = 1
    assert m.solar_fraction + total_duration(intervals(tl.dark)) / T == pytest.approx(1.0)


def test_daily_y_comparison():
    tl, sky = _timeline()
    d = daily_table(tl)
    assert len(d) == 2
    assert d[0]["sun_hours"] == pytest.approx(10.0) and d[1]["sun_hours"] == pytest.approx(6.0)
    assert d[0]["earth_hours"] == pytest.approx(20.0) and d[1]["earth_hours"] == pytest.approx(1 + 8)
    assert d[0]["overlap_hours"] == pytest.approx(2 + 4) and d[1]["overlap_hours"] == pytest.approx(1.0)
    assert d[0]["mean_illumination"] == pytest.approx(10 / 24, abs=5e-3)
    m = compute_metrics(tl, sky, None, VisibilityParams())
    rows = comparison_table({"a": m, "b": m})
    r = {x["metric"]: x for x in rows}
    assert r["solar_fraction"]["a"] == r["solar_fraction"]["b"] == m.solar_fraction
    assert r["max_darkness_s"]["unit"] == "s"


# ---------------------------------------------------------------------------------------------- enlace DTE
def _link(link_iv, st_iv, t0, t1):
    from lsi.analysis.metrics import link_metrics
    from lsi.contracts import LinkResult
    ws = lambda iv, lab: window_set(iv, t0, t1, lab)   # noqa: E731
    lk = LinkResult("T", "T", 0.0, ws(link_iv, "earth"), ws(link_iv, "link"), ws(link_iv, "net"),
                    {k: ws(v, k) for k, v in st_iv.items()})
    return link_metrics(lk, t0, t1)


def test_link_metrics_a_mano_dias_utc_completos_y_hueco():
    from datetime import datetime
    from lsi.contracts import utc_datetime_to_et
    t0 = utc_datetime_to_et(datetime(2026, 12, 1))
    t1 = t0 + 3 * 86400.0
    d = 86400.0
    # día 1: 6 h; día 2: 0 h; día 3: 10 h (ventana más larga 10 h, termina en el borde final)
    iv = [[t0 + 2 * H, t0 + 8 * H], [t0 + 2 * d + 14 * H, t0 + 2 * d + 24 * H]]
    m = _link(iv, {"A": [[t0 + 2 * H, t0 + 8 * H]], "B": [[t0 + 2 * d + 14 * H, t0 + 2 * d + 24 * H]]}, t0, t1)
    assert m["link_fraction"] == pytest.approx(16.0 / 72.0)
    assert m["link_hours_per_day_mean"] == pytest.approx(16.0 / 3.0)
    assert m["link_hours_per_day_min"] == pytest.approx(0.0)            # el día 2 completo no tiene enlace
    assert m["longest_link_window_s"] == pytest.approx(10 * H) and m["longest_link_window_truncated"]
    assert m["max_link_gap_s"] == pytest.approx((2 * d + 14 * H) - 8 * H) and not m["max_link_gap_truncated"]   # 8h → día 3 14h
    assert m["link_by_station"] == pytest.approx({"A": 6.0 / 72.0, "B": 10.0 / 72.0})


def test_link_metrics_sin_dias_completos_y_hueco_truncado():
    from datetime import datetime
    from lsi.contracts import utc_datetime_to_et
    t0 = utc_datetime_to_et(datetime(2026, 12, 1, 6))      # el periodo empieza a las 06:00: ningún día UTC completo
    t1 = t0 + 12 * H
    m = _link([[t0 + 3 * H, t0 + 5 * H]], {"A": [[t0 + 3 * H, t0 + 5 * H]]}, t0, t1)
    assert m["link_hours_per_day_min"] is None
    assert m["max_link_gap_s"] == pytest.approx(7 * H) and m["max_link_gap_truncated"]   # hueco final cortado por el borde


def test_comparison_table_sin_enlace_conserva_las_filas_antiguas(): 
    import dataclasses
    from lsi.analysis.metrics import LINK_FIELDS
    from lsi.contracts import SiteMetrics
    base = {f.name: 0.0 for f in dataclasses.fields(SiteMetrics)}
    for k in ("longest_sun_window_truncated", "max_darkness_truncated"):
        base[k] = False
    for k in LINK_FIELDS:
        base.pop(k)
    m = SiteMetrics(**base)
    names = [r["metric"] for r in comparison_table({"a": m})]
    assert not any(n in LINK_FIELDS for n in names) and len(names) == 17
    with_link = SiteMetrics(**base, link_fraction=0.5, link_hours_per_day_mean=12.0, link_hours_per_day_min=None,
                            link_by_station={"X": 0.2})
    rows = {r["metric"]: r for r in comparison_table({"a": with_link})}
    assert rows["link_fraction"]["unit"] == "fraction" and rows["link_hours_per_day_mean"]["unit"] == "h"
    assert "link_by_station" not in rows
