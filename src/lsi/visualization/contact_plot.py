"""Gráfico de contactos con estaciones terrestres: horas del día (UTC o locales) × días, una banda por estación.

Cada estación lleva color, patrón de relleno y posición propios (ningún significado depende solo del color). En modo UTC se
añade una banda «Enlace posible (red)» con la unión de ventanas: los traspasos (dos estaciones a la vez) se ven como barras
simultáneas y los huecos sin ninguna estación, como la banda de la red vacía. En hora local cada estación usa SU reloj civil
(zona IANA), así que las bandas de estaciones distintas no están alineadas en el tiempo: los solapes solo se leen en UTC.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

import plotly.graph_objects as go

from lsi.contracts import ContactWindow
from lsi.visualization import theme

PATTERNS = ("/", "\\", "x", "+", ".", "-")
UNION_NAME = "Enlace posible (red)"


def _utc_segments(a: float, b: float, days: Sequence[tuple[str, float, float]]):
    """[(día, hora_inicio, ancho_h)] del tramo [a, b] repartido por días UTC (``days`` = (etiqueta, inicio_et, fin_et))."""
    for lab, d0, d1 in days:
        lo, hi = max(a, d0), min(b, d1)
        if hi > lo:
            yield lab, (lo - d0) / 3600.0, (hi - lo) / 3600.0


def _local_segments(a: float, b: float, tz: str, to_local: Callable):
    """[(fecha local, hora_inicio, ancho_h)] del tramo [a, b] partido en la medianoche civil de la zona ``tz``."""
    cur = a
    while cur < b - 1e-6:
        loc = to_local(cur, tz)
        sod = loc.hour * 3600 + loc.minute * 60 + loc.second + loc.microsecond / 1e6
        end = min(b, cur + 86400.0 - sod)
        yield loc.strftime("%Y-%m-%d"), sod / 3600.0, (end - cur) / 3600.0
        cur = end


def contact_chart(contacts: Sequence[ContactWindow], days: Sequence[tuple[str, float, float]], *, local: bool = False,
                  union: Optional[Sequence[tuple[float, float]]] = None, station_order: Optional[Sequence[str]] = None,
                  to_local: Optional[Callable] = None, title: str = "Contactos con las estaciones terrestres") -> Optional[go.Figure]:
    """Figura de contactos o ``None`` si no hay ninguno en los días dados (el llamador pinta el estado vacío).

    ``days``: [(etiqueta 'AAAA-MM-DD', inicio_et, fin_et)] días UTC a mostrar; ``union``: intervalos ET del enlace de la red.
    ``to_local(et, tz)`` → datetime civil con zona (``ground_stations.et_to_local``); obligatorio con ``local=True`` (la figura no
    importa el núcleo astronómico).
    """
    if not days:
        return None
    if local and to_local is None:
        raise ValueError("local=True necesita to_local(et, tz)")
    t0, t1 = days[0][1], days[-1][2]
    cs = [c for c in contacts if c.end_et > t0 and c.start_et < t1]
    if not cs:
        return None
    ids = list(station_order) if station_order else sorted({c.station_id for c in cs})
    fig = go.Figure()
    rows: set = {d[0] for d in days} if not local else set()
    for i, sid in enumerate(ids):
        mine = [c for c in cs if c.station_id == sid]
        if not mine:
            continue
        xs, bases, ys, hov = [], [], [], []
        for c in mine:
            a, b = max(c.start_et, t0), min(c.end_et, t1)
            segs = _local_segments(a, b, c.tz, to_local) if local else _utc_segments(a, b, days)
            for lab, x0, w in segs:
                ys.append(lab)
                bases.append(x0)
                xs.append(w)
                rows.add(lab)
                hov.append(f"{c.station_name}<br>UTC {c.start_utc[5:16].replace('T', ' ')} → {c.end_utc[5:16].replace('T', ' ')}"
                           f"<br>Local {c.start_local[11:16]} {c.start_local.rsplit(' ', 1)[-1]} → {c.end_local[11:16]} {c.end_local.rsplit(' ', 1)[-1]}"
                           f"<br>Ventana entera de {c.duration_s / 3600.0:.1f} h (se dibuja repartida por días: una ventana que cruza "
                           f"la medianoche aparece en dos filas, «continúa» en la siguiente)"
                           f"<br>Luna hasta {c.max_moon_el_deg:.0f}° en la estación")
        name = f"{mine[0].complex or sid} ({sid})"
        col = theme.SERIES_COLORS[i % 6]
        fig.add_trace(go.Bar(
            y=ys, x=xs, base=bases, orientation="h", name=name, offsetgroup=sid, hovertext=hov, hoverinfo="text",
            marker=dict(color=col, pattern=dict(shape=PATTERNS[i % 6], fgcolor=theme.BG, size=6, solidity=0.35),
                        line=dict(color=col, width=1))))
    if union is not None and not local:
        ys, bases, xs = [], [], []
        for a, b in union:
            for lab, x0, w in _utc_segments(max(a, t0), min(b, t1), days):
                ys.append(lab)
                bases.append(x0)
                xs.append(w)
        if xs:
            fig.add_trace(go.Bar(y=ys, x=xs, base=bases, orientation="h", name=UNION_NAME, offsetgroup="union",
                                 marker=dict(color=theme.OVERLAP, line=dict(color=theme.TEXT, width=1)),
                                 hovertemplate=UNION_NAME + "<extra></extra>"))
    n_lanes = len(fig.data)
    order = sorted(rows)
    fig.update_layout(barmode="group", bargap=0.12, bargroupgap=0.04,
                      yaxis=dict(autorange="reversed", categoryorder="array", categoryarray=order, type="category",
                                 title="Día (hora local de cada estación)" if local else "Día UTC"),
                      xaxis=dict(range=[0, 24], title="Hora local civil de cada estación" if local else "Hora del día (UTC)",
                                 tickvals=list(range(0, 25, 3)), ticktext=[f"{h:02d}:00" for h in range(0, 25, 3)]),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom"))
    height = int(min(1400, max(440, 140 + len(order) * max(n_lanes, 1) * 11)))
    fig = theme.apply_theme(fig, title, height=height,
                            note="Enlace posible = Tierra visible con margen y estación viendo la Luna. No es presupuesto de enlace RF.")
    fig.update_layout(margin=dict(l=60, r=30, t=105, b=70), legend=dict(orientation="h", y=1.0, yanchor="bottom"))   # la leyenda no pisa el título
    return fig
