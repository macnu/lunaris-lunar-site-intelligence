"""Bandas temporales Sol/Tierra/solape, cuenta atrás hasta puesta de Sol/Tierra y zoom."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import plotly.graph_objects as go

from lsi.contracts import Body, Countdown, Event, EventKind, TimelineResult, WindowSet
from lsi.visualization import theme

# fila → (etiqueta, color, trama). La trama distingue las filas sin depender del color.
_ROWS = (
    ("sun", "Sol visible", theme.SUN, ""),
    ("earth", "Tierra visible (geometría)", theme.EARTH, "/"),
    ("overlap", "Sol y Tierra a la vez", theme.OVERLAP, "x"),
)
LINK_LABEL, LINK_COLOR = "Enlace posible", "#f28fd0"
NOTE = ("Tierra visible = geometría sobre el horizonte. Enlace posible = Tierra visible con margen de elevación Y alguna estación de la red "
        "viendo la Luna (sin presupuesto de enlace). " + theme.GEOMETRIC_NOTE)


def format_countdown(cd: Countdown) -> str:
    """«2 d 03 h 15 min»; ``—`` si no hay evento en la ventana de búsqueda."""
    if cd.seconds_until is None:
        return "—"
    m = int(round(cd.seconds_until / 60))
    d, rem = divmod(m, 1440)
    h, mi = divmod(rem, 60)
    return (f"{d} d " if d else "") + f"{h:02d} h {mi:02d} min"


def zoom_around(et: float, hours: float = 12.0) -> Tuple[float, float]:
    """Rango ET centrado en un evento, para ``zoom_et``."""
    return et - hours * 3600.0, et + hours * 3600.0


def _bars(fig: go.Figure, ws: WindowSet, label: str, color: str, pattern: str, row: str, showlegend: bool = True, opacity: float = 1.0):
    if not ws.windows:
        return
    starts = theme.et_to_datetimes([w.start_et for w in ws.windows])
    fig.add_trace(go.Bar(
        base=starts, x=[w.duration_s * 1000.0 for w in ws.windows], y=[row] * len(ws.windows), orientation="h", name=label,
        marker=dict(color=color, opacity=opacity, pattern=dict(shape=pattern, fgcolor="#0b1020", size=7, solidity=0.35) if pattern else {},
                    line=dict(color=color, width=1)),
        customdata=[[w.duration_s / 3600.0, "≥ " if (w.left_truncated or w.right_truncated) else ""] for w in ws.windows],
        hovertemplate=label + "<br>duración %{customdata[1]}%{customdata[0]:.1f} h<extra></extra>", showlegend=showlegend))


def timeline_bands(tl: TimelineResult, cursor_et: Optional[float] = None, zoom_et: Optional[Tuple[float, float]] = None,
                   show_pessimistic: bool = True, show_events: bool = True, show_link: bool = True,
                   show_stations: bool = False) -> go.Figure:
    """Bandas por criterio; ventanas truncadas (≥) con borde discontinuo en el hover; eventos como triángulos.

    ``sun_pess``/``earth_pess`` (si existen) se dibujan en filas propias como «con cota superior del horizonte».
    Si ``tl.link`` existe, añade la fila «Enlace posible» (y, con ``show_stations``, una fila por estación con contacto).
    No recalcula: pinta los ``WindowSet`` que entrega el pipeline.
    """
    fig = go.Figure()
    sets = {"sun": tl.sun, "earth": tl.earth, "overlap": tl.overlap}
    for key, label, color, pat in _ROWS:
        _bars(fig, sets[key], label, color, pat, label)
    lk = getattr(tl, "link", None) if show_link else None
    if lk is not None:
        _bars(fig, lk.link, f"{LINK_LABEL} (red {lk.network_label}, margen {lk.min_earth_elevation_deg:g}°)", LINK_COLOR, "+", LINK_LABEL)
        if show_stations:
            names = {st_.station_id: st_.name for st_ in lk.stations}
            for sid, ws in lk.by_station.items():
                _bars(fig, ws, f"Enlace vía {names.get(sid, sid)}", LINK_COLOR, "", f"· {names.get(sid, sid)}", opacity=0.6)
    if show_pessimistic:
        for ws, base in ((tl.sun_pess, _ROWS[0]), (tl.earth_pess, _ROWS[1])):
            if ws is not None:
                _bars(fig, ws, base[1] + " (pesimista, con H_ub)", base[2], "." , base[1] + " (pesimista)", opacity=0.55)
    if show_events:
        for kind, sym, nm in ((EventKind.RISE, "triangle-up", "Salida"), (EventKind.SET, "triangle-down", "Puesta")):
            evs = [e for e in tl.events if e.kind == kind]
            if evs:
                fig.add_trace(go.Scatter(
                    x=theme.et_to_datetimes([e.et for e in evs]), y=[_ROWS[0][1] if e.body == Body.SUN else _ROWS[1][1] for e in evs],
                    mode="markers", name=f"{nm} (Sol/Tierra)", marker=dict(symbol=sym, size=10, color=theme.TEXT, line=dict(color="#000", width=1)),
                    text=[f"{'Sol' if e.body == Body.SUN else 'Tierra'} · {'puesta' if kind == EventKind.SET else 'salida'} · az {e.az_deg:.0f}°"
                          + (" (truncado)" if e.truncated else "") for e in evs],
                    hovertemplate="%{text}<extra></extra>"))
    if cursor_et is not None:
        t = theme.et_to_datetimes([cursor_et])[0]
        fig.add_shape(type="line", x0=t, x1=t, y0=0, y1=1, yref="paper", line=dict(color=theme.TEXT, width=1.5, dash="dot"))
        fig.add_annotation(x=t, y=1, yref="paper", text="Instante", showarrow=False, yanchor="bottom", font=dict(color=theme.TEXT, size=11))
    x_range = theme.et_to_datetimes(zoom_et) if zoom_et else None
    fig.update_xaxes(title="Tiempo (UTC)", range=x_range, rangeslider=dict(visible=True, bgcolor=theme.PANEL, thickness=0.08),
                     rangeselector=dict(bgcolor=theme.PANEL, font=dict(color=theme.TEXT), activecolor=theme.GRID,
                                        buttons=[dict(count=1, label="1 d", step="day", stepmode="backward"),
                                                 dict(count=7, label="7 d", step="day", stepmode="backward"),
                                                 dict(step="all", label="Todo")]))
    fig.update_yaxes(autorange="reversed", title="")
    fig.update_layout(barmode="overlay", bargap=0.35)
    return theme.apply_theme(fig, "Bandas temporales de visibilidad", height=520, note=NOTE)


def countdown_figure(countdowns: Sequence[Countdown]) -> go.Figure:
    """Tarjetas de cuenta atrás (Sol y Tierra): texto grande con símbolo, estado actual y aviso de aproximación."""
    fig = go.Figure()
    n = max(len(countdowns), 1)
    for i, cd in enumerate(countdowns):
        sun = cd.body == Body.SUN
        name, color, sym = ("Sol", theme.SUN, "★") if sun else ("Tierra", theme.EARTH, "⊕")
        nxt = cd.next_event
        if nxt is None:
            what = "sin cambio en la ventana de búsqueda"
        else:
            if sun:
                what = "puesta de Sol" if nxt.kind == EventKind.SET else "salida del Sol"
            else:
                what = "Earthset" if nxt.kind == EventKind.SET else "Earthrise"
        state = "● sobre el horizonte" if cd.currently_up else "○ bajo el horizonte"
        approx = "<br>≈ aproximado: depende de un azimut con cobertura limitada" if cd.approximate_due_to_coverage else ""
        x0, x1 = i / n, (i + 1) / n
        fig.add_annotation(xref="paper", yref="paper", x=(x0 + x1) / 2, y=0.5, showarrow=False, align="center", bordercolor=color, borderwidth=2,
                           borderpad=14, bgcolor=theme.PANEL,
                           text=(f"<b style='color:{color}'>{sym} {name}</b> · {state}<br>"
                                 f"<span style='font-size:30px'><b>{format_countdown(cd)}</b></span><br>hasta {what}{approx}"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return theme.apply_theme(fig, "Cuenta atrás", height=240, note="Tiempos geométricos; " + theme.GEOMETRIC_NOTE)
