"""Identidad visual y UX de cara al jurado: tarjetas con cifra completa, escape HTML, avisos plegados pero presentes, estado inicial
positivo, chips con icono y texto, y modo Público sin jerga."""
import re
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from lsi.contracts import ALWAYS_SHOWN_WARNINGS, STANDARD_WARNINGS_ES, StateKey as K
from ui import components as C, state as S
from ui_cards import cards, parse_cards

ROOT = Path(__file__).resolve().parents[1]
EVIL = '<img src=x onerror=alert(1)><script>alert("x")</script> Cráter & "co"'
JARGON = re.compile(r"snap_to_dem|\bG[0-7]\b")


def single_page_app(page, tmp_path, monkeypatch) -> AppTest:
    shutil.copy(ROOT / "ui" / "pages" / f"{page}.py", tmp_path / f"{page}.py")
    monkeypatch.setenv("LSI_PAGES_DIR", str(tmp_path))
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()


# --------------------------------------------------------------------------------------- tarjetas KPI (puras)
def test_kpi_card_keeps_the_complete_value_and_unit():
    html = C.kpi_html("Energía por día (media)", "9 717 Wh/m²", sub="Rango: 9 000 – 10 100 Wh/m²", tone="sun",
                      chip_html=C.chips(C.chip("Evidencia · datasheet", "ok")))
    (card,) = parse_cards([html])
    assert card.label == "Energía por día (media)" and card.value == "9 717 Wh/m²"
    assert "…" not in html
    assert 'class="n">9 717</span><span class="u">Wh/m²</span>' in html          # cifra con miles sin partir y unidad pequeña
    assert "Rango: 9 000" in html and "Evidencia · datasheet" in html and 'aria-label="Energía por día (media): 9 717 Wh/m²' in html


@pytest.mark.parametrize("value,expected", [(89.5, "89,5 %"), ("≥ 375,0 h", "≥ 375,0 h"), ("3 h 25 min", "3 h 25 min"),
                                            (None, "—"), ("no calculado", "no calculado")])
def test_kpi_values_are_never_cut(value, expected):
    unit = "%" if isinstance(value, float) else ""
    (card,) = parse_cards([C.kpi_html("Etiqueta completa de la tarjeta", value, unit=unit)])
    assert card.value == expected and card.label == "Etiqueta completa de la tarjeta"


def test_kpi_truncated_prefix():
    (card,) = parse_cards([C.kpi_html("Noche máxima", 304.7, unit="h", truncated=True)])
    assert card.value == "≥ 304,7 h"


def test_styles_do_not_ellipsize_numbers_and_respect_reduced_motion():
    css = C._css()
    assert "prefers-reduced-motion" in css and ":focus-visible" in css
    assert "ellipsis" not in css
    assert "stMetricValue" in css            # st.metric de otras pantallas tampoco corta la cifra


# --------------------------------------------------------------------------------------- seguridad: nada de datos sin escapar
def test_html_helpers_escape_malicious_names():
    pieces = [C.kpi_html(EVIL, EVIL, sub=EVIL, help=EVIL, chip_html=C.chips(C.chip(EVIL, "ok"))),
              C.hero_html(kicker=EVIL, title=EVIL, meta=[(EVIL, EVIL)], chips_html=C.chip(EVIL), read=EVIL, why=EVIL,
                          facts=[(EVIL, EVIL, EVIL)]),
              C.chip(EVIL, "bad"), C.esc(EVIL)]
    for html in pieces:
        assert "<img" not in html and "<script" not in html and "onerror=alert(1)>" not in html
        assert "&lt;img" in html and "&lt;script&gt;" in html


def test_dollar_signs_are_escaped_so_markdown_does_not_start_latex():
    assert "$" not in C.kpi_html("Coste $5 y $6", "1 $")


def test_place_name_hides_internal_ids():
    assert C.place_name("Site23 Malapert massif") == "Malapert massif" and C.place_name(None) == "Punto elegido"


@pytest.mark.needs_spice
def test_malicious_search_name_never_reaches_the_page_as_html(tmp_path, monkeypatch):
    """Un punto del buscador con un nombre malicioso se pinta escapado en el hero de «Capacidad del sitio»."""
    import dataclasses
    from ui import cache
    real = cache.try_analysis

    def evil(req):
        res, err = real(req)
        return (dataclasses.replace(res, observer=dataclasses.replace(res.observer, label=EVIL)) if res else res), err
    monkeypatch.setattr(cache, "try_analysis", evil)
    at = single_page_app("site_capacity", tmp_path, monkeypatch)
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown if m.allow_html)          # lo que se pinta como HTML
    assert "&lt;img" in md and "<img" not in md and "<script" not in md
    assert "<img" in " ".join(m.value for m in at.markdown if not m.allow_html)   # el resto es texto Markdown (Streamlit lo escapa)


# --------------------------------------------------------------------------------------- chips con icono Y texto
def test_verdict_chips_have_icon_and_text():
    class V:
        verdict_provisional = False
    for verdict, icon in (("APTO", "✔"), ("CONDICIONAL", "◐"), ("NO APTO", "✖"), ("SIN DATOS", "?")):
        v = V()
        v.verdict = verdict
        html = C.verdict_chip(v)
        assert icon in html and f"</span>{verdict}</span>" in html


# --------------------------------------------------------------------------------------- avisos plegados pero presentes
@pytest.mark.needs_spice
def test_warnings_are_collapsed_in_one_block_with_summary_chip():
    def app():
        from ui import components as C
        C.warnings_band()
    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Geometría ≠ potencia/enlace garantizados" in md and "Paneles experimentales: 3" in md       # chip siempre visible
    assert len(at.expander) == 1 and "Alcance y límites" in at.expander[0].label
    assert at.expander[0].proto.expanded is False                                                       # plegado
    inside = " ".join(c.value for c in at.expander[0].caption) + " " + " ".join(m.value for m in at.expander[0].markdown)
    for code in ALWAYS_SHOWN_WARNINGS:
        assert STANDARD_WARNINGS_ES[code] in inside, code                                                # ninguno se pierde
    assert "Visibilidad geométrica ≠ potencia ni enlace garantizados" in inside


# --------------------------------------------------------------------------------------- estado inicial positivo
@pytest.mark.needs_spice
def test_initial_state_is_the_suggested_best_candidate_and_positive(tmp_path, monkeypatch):
    at = single_page_app("site_capacity", tmp_path, monkeypatch)
    assert not at.exception, [e.value for e in at.exception]
    sug = at.session_state[S.SUGGESTED]
    assert sug and sug["site_id"] == "site23" and sug["start_utc"].startswith("2026-12-16")
    assert at.session_state[K.START_UTC].startswith("2026-12-16")
    md = " ".join(m.value for m in at.markdown if not m.value.startswith("<style>"))     # sin la hoja de estilos
    assert "Lugar y fecha sugeridos" in md and "✔" in md and "APTO" in md
    assert "Ninguna fecha" not in md and "NO APTO" not in md
    names = {c.label for c in cards(at)}
    assert {"Sol visible", "Tierra visible (geometría)", "ENLACE POSIBLE", "HUECO MÁXIMO sin enlace"} <= names
    facts = re.findall(r'class="k">([^<]+)<', md)
    assert any("Inclinación del suelo a" in k or "Pendiente a" in k for k in facts)                      # pendiente junto al veredicto
    assert "límite" in md


@pytest.mark.needs_spice
def test_suggestion_falls_back_when_there_is_no_map(monkeypatch, tmp_path):
    monkeypatch.setenv("LSI_SUITABILITY_DIR", str(tmp_path))            # carpeta sin mapas
    from lsi import pipeline
    ctx = pipeline.build_context(ROOT)
    assert S.suggested_start(ctx) is None
    assert S.default_state(ctx)["ui_suggested"] is None                  # cae al punto y la fecha por defecto de la configuración


# --------------------------------------------------------------------------------------- modo Público sin jerga
def _all_text(at: AppTest) -> str:
    parts = [e.value for k in ("markdown", "caption", "info", "warning", "error", "success", "subheader", "header", "title", "text")
             for e in getattr(at, k)]
    parts += [str(d.value.to_dict()) for d in at.dataframe]
    parts += [e.value for k in ("markdown", "caption", "warning", "error", "success") for e in getattr(at.sidebar, k)]
    return " ".join(parts)


@pytest.mark.needs_spice
@pytest.mark.parametrize("page", ["search", "site_capacity", "best_spots", "horizon_visibility", "timeline", "comparison",
                                  "power_panels", "site_score"])
def test_public_mode_has_no_jargon(page, tmp_path, monkeypatch):
    at = single_page_app(page, tmp_path, monkeypatch)
    assert not at.exception, [e.value for e in at.exception]
    txt = _all_text(at)
    assert not JARGON.search(txt), f"{page}: {sorted(set(JARGON.findall(txt)))}"


@pytest.mark.needs_spice
def test_public_site_capacity_opens_with_why_the_pole_is_hard(tmp_path, monkeypatch):
    at = single_page_app("site_capacity", tmp_path, monkeypatch)
    assert "polo sur de la Luna es un sitio difícil" in " ".join(m.value for m in at.markdown)
    at.sidebar.selectbox(key="_w_mode").set_value("Planificador").run()
    assert "polo sur de la Luna es un sitio difícil" not in " ".join(m.value for m in at.markdown)
