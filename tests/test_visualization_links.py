"""Figuras con enlace DTE (fila «Enlace posible» y métricas de enlace en la comparación) con datos sintéticos."""
import dataclasses

from lsi.contracts import LinkResult, StationLinkSummary
from lsi.visualization import comparison_plot, timeline_plot

from test_visualization import ET0, metrics, result, timeline, windows


def link_result():
    return LinkResult(network_id="DSN", network_label="DSN", min_earth_elevation_deg=3.0, earth=windows("earth", [(0, 30)]),
                      link=windows("link", [(2, 12), (20, 29)]), network_cover=windows("net", [(0, 40)]),
                      by_station={"DSS-14": windows("a", [(2, 12)]), "DSS-63": windows("b", [(20, 29)])},
                      stations=(StationLinkSummary("DSS-14", "Goldstone DSS-14", "Goldstone", "America/Los_Angeles", 6.0, "publicado",
                                                   0.2, 0.3, 4.8, 1, 36000.0),))


def names(fig):
    return [t.name for t in fig.data if t.name]


def test_timeline_link_row_distinct_from_geometric_earth():
    tl = dataclasses.replace(timeline(), link=link_result())
    fig = timeline_plot.timeline_bands(tl)
    assert "Tierra visible (geometría)" in names(fig)
    bar = next(t for t in fig.data if (t.name or "").startswith("Enlace posible"))
    assert list(bar.x) == [10 * 3600 * 1000.0, 9 * 3600 * 1000.0] and "margen 3°" in bar.name
    assert not any((n or "").startswith("Enlace vía") for n in names(fig))
    fs = timeline_plot.timeline_bands(tl, show_stations=True)
    assert "Enlace vía Goldstone DSS-14" in names(fs) and "Enlace vía DSS-63" in names(fs)     # nombre si hay resumen, id si no


def test_timeline_without_link_has_no_link_row():
    assert not any("Enlace" in n for n in names(timeline_plot.timeline_bands(timeline())))


def test_comparison_bars_add_link_metrics_only_if_all_sites_have_them():
    plain = {"A": result(0.4), "B": result(0.5)}
    n0 = len(comparison_plot.comparison_bars(plain).layout.annotations)
    linked = {}
    for k, r in plain.items():
        m = dataclasses.replace(r.metrics, link_fraction=0.9, max_link_gap_s=7200.0, max_link_gap_truncated=True)
        linked[k] = dataclasses.replace(r, metrics=m)
    fig = comparison_plot.comparison_bars(linked)
    titles = [a.text for a in fig.layout.annotations]
    assert len(titles) == n0 + 2 and any("ENLACE POSIBLE" in t for t in titles) and any("Hueco máximo" in t for t in titles)
    gap = [t for t in fig.data if t.text and t.text[0].startswith("≥ ")][-1]    # la última métrica es el hueco
    assert gap.y[0] == 2.0                                                          # 7200 s → 2 h
    mixed = {"A": linked["A"], "B": plain["B"]}
    assert len(comparison_plot.comparison_bars(mixed).layout.annotations) == n0
