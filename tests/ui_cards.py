"""Ayudante de pruebas: lee las tarjetas KPI propias (HTML con ``data-kpi-label`` / ``data-kpi-value``) de un ``AppTest``.

Sustituye a ``at.metric`` (la UI ya no usa ``st.metric``, que trunca las cifras con «…»). ``value`` es el TEXTO COMPLETO de la cifra."""
import html
import re
from collections import namedtuple

Card = namedtuple("Card", "label value")
_CARD = re.compile(r'data-kpi-label="([^"]*)" data-kpi-value="([^"]*)"')


def parse_cards(html_texts) -> list:
    return [Card(html.unescape(a), html.unescape(b)) for t in html_texts for a, b in _CARD.findall(t)]


def cards(at) -> list:
    """Tarjetas KPI de la página, en orden de aparición."""
    return parse_cards(m.value for m in at.markdown)


def legacy(at):
    """Pre-siembra el periodo de referencia de las cifras históricas (inicio 2026-12-01, 30 d) en lugar del sugerido al abrir."""
    at.session_state["start_utc"] = "2026-12-01T00:00:00"
    at.session_state["end_utc"] = "2026-12-31T00:00:00"
    at.session_state["cursor_utc"] = "2026-12-01T00:00:00"
    at.session_state["_ui_days"] = 30.0
    at.session_state["obs_lat_deg"], at.session_state["obs_lon_deg_e"] = -85.98, (-1.67) % 360.0   # centro del sitio, como antes
    return at
