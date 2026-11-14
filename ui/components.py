"""Componentes comunes de la UI: avisos científicos, tarjetas, insignias, descargas, glosario y accesibilidad.

Todo en español. Ningún significado depende solo del color: cada estado lleva icono y texto (RNF-06).
Las páginas no calculan: pintan lo que devuelve ``ui.cache``.
"""
from __future__ import annotations

import html as _html
import io
import json
import math
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import streamlit as st

from lsi.analysis import export
from lsi.contracts import (
    ALWAYS_SHOWN_WARNINGS, STANDARD_WARNINGS_ES, AnalysisResult, ConfidenceLevel, DateOutOfRangeError, DemNotFoundError,
    GateStatus, GazetteerNotFoundError, HorizonMode, KernelsMissingError, LSIError, MountingSpec, MountingType, NodataAtObserverError,
    ObserverNearEdgeError, ObserverOutsideDemError, ScientificWarning, Severity, StateKey, VisibilityState, WarningCode,
)
from lsi.energy.panels import panel_status
from lsi.visualization.theme import GEOMETRIC_NOTE, STATE_TEXT
from ui import state

# ------------------------------------------------------------------------------------------------ errores
_HINTS = {
    DateOutOfRangeError: "Elige fechas entre 1900 y 2050 (el rango de las efemérides SPICE).",
    ObserverNearEdgeError: "Elige un punto más interior del recorte de terreno (DEM) o activa «esfera lisa».",
    NodataAtObserverError: "El DEM no tiene dato en ese punto (nunca se trata como 0): mueve el punto unos metros.",
    ObserverOutsideDemError: "El punto queda fuera del DEM: se puede evaluar en modo esfera lisa.",
    KernelsMissingError: "Descarga los kernels con: python scripts/fetch_data.py",
    GazetteerNotFoundError: "Genera el buscador con: python scripts/fetch_gazetteer.py (el resto de la app funciona).",
    DemNotFoundError: "Faltan datos del DEM: python scripts/fetch_data.py",
}


def friendly_error(exc: BaseException) -> str:
    """Mensaje para el usuario a partir de una excepción del núcleo (sin traceback)."""
    hint = next((h for t, h in _HINTS.items() if isinstance(exc, t)), "")
    return f"{exc}" + (f" {hint}" if hint else "")


def show_error(exc_or_msg: Any) -> None:
    """``st.error`` con el mensaje amable de una excepción o un texto."""
    msg = friendly_error(exc_or_msg) if isinstance(exc_or_msg, BaseException) else str(exc_or_msg)
    st.error(msg, icon=":material/error:")


# ------------------------------------------------------------------------------------------------ modos y glosario
_LEVEL = {m: i for i, m in enumerate(state.MODES)}


def show_for(min_mode: str) -> bool:
    """True si el modo de usuario actual es ``min_mode`` o superior (publico < planificador < experto)."""
    return _LEVEL[state.mode()] >= _LEVEL[min_mode]


# término -> (explicación llana para el público, definición técnica). Sin cifras que no sean convención del proyecto.
GLOSSARY: Mapping[str, tuple[str, str]] = {
    "Azimut": ("La dirección en la que miras, contada desde el Norte hacia el Este: 0° Norte, 90° Este, 180° Sur, 270° Oeste.",
               "Ángulo desde el Norte local hacia el Este, sentido horario visto desde arriba, 0°–360° (convención del proyecto)."),
    "Elevación": ("Lo alto que está algo en el cielo: 0° es la línea del horizonte y 90° justo encima de tu cabeza.",
                  "Ángulo sobre el plano horizontal local; 0° horizonte plano, +90° cenit."),
    "Horizonte": ("La línea donde el terreno, o la propia curva de la Luna, tapa el cielo. En la Luna no hay aire que lo difumine.",
                  "Elevación máxima del terreno por azimut más la depresión por curvatura lunar; sin refracción (sin atmósfera)."),
    "Puesta de Sol": ("El momento en que el Sol desaparece tras el horizonte; el reloj de cuenta atrás te dice cuánto falta.",
                      "Transición del Sol de visible a oculto respecto a H(az), refinada por bisección (tolerancia 1 s)."),
    "Earthset": ("Lo mismo que la puesta de Sol, pero para la Tierra: cuándo deja de verse desde ese punto.",
                 "Transición de la Tierra de visible a oculta (umbral de fracción de disco visible del proyecto)."),
    "Ventana de visibilidad": ("Un tramo de tiempo seguido en el que el Sol (o la Tierra) se ve sin que lo tape el terreno.",
                               "Intervalo con fracción de disco visible sobre el umbral; los extremos pueden ser transiciones refinadas."),
    "Visibilidad geométrica": ("Solo dice si algo se ve desde ese punto. No garantiza que haya energía suficiente ni que se pueda comunicar con la Tierra.",
                               "Resultado de comparar la elevación del cuerpo con el horizonte. No es potencia ni presupuesto de enlace RF."),
    "Esfera lisa": ("Cuando no tenemos mapa del terreno del lugar, lo tratamos como una bola sin montañas: solo cuenta la curvatura. La luz real puede ser muy distinta.",
                    "Modo de horizonte sin DEM: H constante por curvatura. Optimista para iluminación; el score resulta parcial."),
    "DEM": ("Un mapa de alturas de la superficie lunar (altímetro láser LOLA). Con él calculamos qué montañas tapan el cielo.",
            "Modelo digital de elevaciones GeoTIFF polar estereográfico sur, 5 m/píxel nominales; la resolución efectiva es peor."),
    "Cobertura del DEM": ("El mapa de terreno solo llega hasta cierta distancia. Más allá no sabemos qué hay, y el resultado puede ser algo optimista.",
                          "Alcance radial con dato por azimut; donde se agota el horizonte es una cota inferior (marcado como limitado)."),
    "snap_to_dem": ("Si el punto pedido cae fuera del mapa, usamos el punto del mapa más cercano y te decimos a cuántos km está.",
                    "Ajuste del observador al punto cubierto más cercano; se informa la distancia de círculo máximo al punto pedido."),
    "% de potencia": ("Cuánta de la potencia máxima de ese panel se obtendría en cada momento. No son vatios reales de una misión.",
                      "P_rel = potencia relativa a la nominal con el Sol de frente (IAM, coseno, distancia, temperatura); supuestos declarados."),
    "Score": ("Una nota de 0 a 100 que resume lo bueno que es un lugar, con su desglose. Ayuda a comparar, no decide por ti.",
              "Media geométrica ponderada de subindicadores con puertas duras y rango; umbrales y pesos por calibrar con un experto."),
    "Confianza": ("Cuánto fiarse de la cifra según la calidad de los datos del lugar: alta, media o baja.",
                  "Etiqueta C = mín(cobertura, soporte observacional, rango del score); no entra en el producto del score."),
    "≥ (ventana truncada)": ("Si ves «≥», el tramo toca el borde del periodo analizado: dura al menos eso, quizá más.",
                             "Ventana/evento truncado por el inicio o fin del periodo; la duración es una cota inferior."),
    "Eclipse": ("Cuando la sombra de la Tierra tapa el Sol desde la Luna. Esta herramienta no lo modela.",
                "Eclipses lunares no modelados: «oscuridad» solo incluye el efecto del relieve."),
    "Día lunar": ("Un ciclo completo de luz y oscuridad en la Luna dura casi un mes terrestre.",
                  "Mes sinódico ≈ 29,53 d; periodos más cortos no representan bien la ventana más larga ni la máxima oscuridad."),
}


def term_help(name: str) -> str:
    """Texto de ayuda (tooltip) de un término según el modo: llano en Público, técnico en Planificador/Experto."""
    plain, tech = GLOSSARY[name]
    return plain if state.is_public() else tech


PUBLIC_TERM_NAMES = {"snap_to_dem": "Ajuste al mapa", "DEM": "Mapa de alturas (DEM)", "Score": "Nota (score)"}


def term_name(name: str) -> str:
    """Nombre del término según el modo: en Público, sin identificadores de código."""
    return PUBLIC_TERM_NAMES.get(name, name) if state.is_public() else name


def term(name: str, label: Optional[str] = None) -> None:
    """Pinta un término en negrita con un «?» cuyo tooltip lo explica."""
    st.markdown(f"**{label or name}**", help=term_help(name))


def glossary_expander(expanded: bool = False) -> None:
    """Glosario completo con el nivel de detalle del modo de usuario."""
    with st.expander("Glosario" if not state.is_public() else "Glosario: palabras explicadas con sencillez", expanded=expanded):
        for name in GLOSSARY:
            st.markdown(f"**{term_name(name)}.** {term_help(name)}")


# ------------------------------------------------------------------------------------------------ formato
def fmt_num(x: Optional[float], nd: int = 1, unit: str = "") -> str:
    """Número con coma decimal, o «—» si no hay dato (NaN/None: «sin dato», nunca 0)."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return f"{s} {unit}".strip()


def fmt_duration(seconds: Optional[float], truncated: bool = False) -> str:
    """Duración legible: «3 h 25 min», «2,4 d». ``truncated`` antepone «≥» (cota inferior)."""
    if seconds is None or not math.isfinite(seconds):
        return "—"
    if seconds >= 2 * 86400:
        out = fmt_num(seconds / 86400.0, 1, "d")
    elif seconds >= 3600:
        h, m = divmod(int(round(seconds / 60.0)), 60)
        out = f"{h} h {m:02d} min"
    else:
        out = f"{int(round(seconds / 60.0))} min"
    return ("≥ " if truncated else "") + out


def fmt_pct(fraction: Optional[float], nd: int = 1) -> str:
    return "—" if fraction is None or not math.isfinite(fraction) else fmt_num(100.0 * fraction, nd, "%")


def esc(x: Any) -> str:
    """Escapa para HTML TODO texto que venga de datos (nombres del gazetteer, de sitios o de la petición). ``$`` también, para que
    ``st.markdown`` no lo interprete como fórmula LaTeX."""
    return _html.escape(str(x), quote=True).replace("$", "&#36;")


_NUM_UNIT = re.compile(r"^(≥\s)?([−-]?[\d\s.,]+?)\s*([^\d\s][^\d]{0,7})$")
_ICON = {"ok": "✔", "cond": "◐", "bad": "✖", "nodata": "?", "sun": "☀", "earth": "◍", "info": "ⓘ", "warn": "⚠", "": "•"}


def chip(text: str, kind: str = "", icon: Optional[str] = None, *, big: bool = False) -> str:
    """Chip HTML con icono Y texto (nunca solo color). ``kind``: ok | cond | bad | nodata | sun | earth | info | warn."""
    ic = _ICON.get(kind, "•") if icon is None else icon
    return (f'<span class="lsi-chip {esc(kind)}{" big" if big else ""}"><span class="ic" aria-hidden="true">{esc(ic)}</span>'
            f'{esc(text)}</span>')


def chips(*items: str) -> str:
    return '<div class="lsi-chips">' + "".join(items) + "</div>" if items else ""


def kpi_html(label: str, value: Any, *, unit: str = "", nd: int = 1, truncated: bool = False, sub: Optional[str] = None,
             rng: Optional[tuple[Optional[float], Optional[float]]] = None, chip_html: str = "", tone: str = "",
             help: Optional[str] = None, help_term: Optional[str] = None) -> str:
    """HTML de una tarjeta KPI GRANDE: etiqueta completa, valor (con unidad más pequeña), rango de incertidumbre/nota y chip de
    evidencia o procedencia. La cifra nunca se trunca (``overflow-wrap`` y cuadrícula fluida en ``styles.css``).
    ``data-kpi-label`` / ``data-kpi-value`` llevan el texto completo (lo leen las pruebas y los lectores de pantalla)."""
    txt = value if isinstance(value, str) else fmt_num(value, nd)
    if not isinstance(value, str) and unit and txt != "—":
        txt = f"{txt} {unit}"
    if truncated and txt != "—" and not txt.startswith("≥"):
        txt = "≥ " + txt
    tip = term_help(help_term) if help_term else help
    if rng is not None and rng[0] is not None and rng[1] is not None:
        sub = (sub + " · " if sub else "") + f"Rango: {fmt_num(rng[0], nd, unit)} – {fmt_num(rng[1], nd, unit)}"
    m = _NUM_UNIT.match(txt)
    nbsp = lambda t: t.replace(" ", " ")   # noqa: E731 - las cifras con miles no se parten entre líneas
    if m:
        body = (f'<span class="ge">≥</span>' if m.group(1) else "") + f'<span class="n">{esc(nbsp(m.group(2)))}</span><span class="u">{esc(m.group(3))}</span>'
    else:
        body = f'<span class="n">{esc(txt)}</span>'
        if len(txt) > 12:        # valor de texto largo (p. ej. nombre de la red): tamaño de texto, no de cifra
            tone = (tone + " txt").strip()
    aria = f"{label}: {txt}." + (f" {sub}." if sub else "") + (f" {tip}" if tip else "")
    info = f'<span class="lsi-info" title="{esc(tip)}" aria-hidden="true">ⓘ</span>' if tip else ""
    return (f'<div class="lsi-kpi {esc(tone)}" role="group" aria-label="{esc(aria)}" data-kpi-label="{esc(label)}" data-kpi-value="{esc(txt)}">'
            f'<div class="lsi-kpi-label">{esc(label)}{info}</div><div class="lsi-kpi-value">{body}</div>'
            + (f'<div class="lsi-kpi-range">{esc(sub)}</div>' if sub else "") + (chip_html or "") + "</div>")


def kpi_grid(*cards: str) -> None:
    """Cuadrícula fluida de tarjetas KPI (apila sola al estrechar la pantalla; ninguna cifra se corta)."""
    st.markdown('<div class="lsi-grid">' + "".join(c for c in cards if c) + "</div>", unsafe_allow_html=True)


def metric_card(label: str, value: Any, *, unit: str = "", help_term: Optional[str] = None, help: Optional[str] = None,
                truncated: bool = False, rng: Optional[tuple[Optional[float], Optional[float]]] = None, nd: int = 1,
                delta: Optional[str] = None, border: bool = True, tone: str = "", chip_html: str = "") -> None:
    """Tarjeta de métrica propia (HTML, NO ``st.metric``: ese trunca las cifras con «…»). ``value`` numérico se formatea
    (None/NaN → «—»); ``str`` se muestra tal cual. ``truncated`` añade «≥»; ``rng=(lo, hi)`` añade el rango; ``delta`` es una
    línea de nota bajo la cifra; ``help_term`` enlaza al glosario. ``border`` se ignora (compatibilidad)."""
    kpi_grid(kpi_html(label, value, unit=unit, nd=nd, truncated=truncated, sub=delta, rng=rng, chip_html=chip_html, tone=tone,
                      help=help, help_term=help_term))


# ------------------------------------------------------------------------------------------------ insignias
_CONF = {ConfidenceLevel.HIGH: ("green", ":material/verified:"), ConfidenceLevel.MEDIUM: ("orange", ":material/rule:"),
         ConfidenceLevel.LOW: ("red", ":material/help:")}
_STATUS = {GateStatus.PASS: ("green", ":material/check_circle:", "Apto según las puertas"),
           GateStatus.FAIL: ("red", ":material/cancel:", "No apto"),
           GateStatus.NO_DATA: ("orange", ":material/help:", "Sin datos suficientes"),
           GateStatus.NOT_APPLICABLE: ("gray", ":material/remove:", "No aplica")}


def confidence_badge(level: Any) -> None:
    """Insignia «Confianza alta/media/baja» con icono y texto (no solo color)."""
    lv = ConfidenceLevel(getattr(level, "value", level))
    color, icon = _CONF[lv]
    st.badge(f"Confianza {lv.value}", icon=icon, color=color, help=term_help("Confianza"))


FAR_LABEL = "Relieve aproximado (80 m)"


def far_field_note() -> str:
    """Aviso del modo de 80 m con el error MEDIDO: la única fuente es ``lsi.pipeline.far_field_warning_text`` (nunca se copia la cifra)."""
    from lsi.pipeline import far_field_warning_text
    return (far_field_warning_text() + " Es optimista cerca de crestas, cimas y bordes de cráter (el 80 m suaviza los obstáculos "
            "próximos y sobreestima la luz).")


def no_dem_label(lat_deg: Optional[float]) -> str:
    """Rótulo de un sitio sin recorte de 5 m según su latitud: al sur de 80°S el motor usa el DEM de 80 m; si no, esfera lisa."""
    from lsi.pipeline import FAR_FIELD_LAT_MAX
    return "relieve aproximado (80 m)" if lat_deg is not None and lat_deg <= FAR_FIELD_LAT_MAX else "sin DEM: esfera lisa"


def partial_score_help(mode) -> str:
    """Ayuda de la insignia «sin datos de terreno»: con 80 m, el texto del motivo del modo (``pipeline.FAR_FIELD_SCORE_TEXT``)."""
    from lsi.pipeline import FAR_FIELD_SCORE_TEXT
    return FAR_FIELD_SCORE_TEXT if mode is HorizonMode.FAR_FIELD else STANDARD_WARNINGS_ES[WarningCode.NO_TERRAIN_DATA_SCORE]


def terrain_kind(mode) -> str:
    """«dem» (relieve fino, 5 m), «far» (relieve aproximado de 80 m, ``FAR_FIELD``) o «sphere» (sin relieve: solo fuera del polo)."""
    return {HorizonMode.DEM: "dem", HorizonMode.FAR_FIELD: "far"}.get(mode, "sphere")


def score_status_badge(status: GateStatus, partial: bool = False) -> None:
    """Estado del score; con score parcial añade la insignia «Parcial: sin datos de terreno»."""
    color, icon, text = _STATUS[GateStatus(status)]
    st.badge(text, icon=icon, color=color)
    if partial:
        st.badge("Parcial: sin datos de terreno", icon=":material/terrain:", color="orange", help=STANDARD_WARNINGS_ES[WarningCode.NO_TERRAIN_DATA_SCORE])


# ------------------------------------------------------------------------------------------------ veredicto por puertas
VERDICT = {"APTO": ("green", ":material/check_circle:", "verde"), "CONDICIONAL": ("orange", ":material/rule:", "ámbar"),
           "NO APTO": ("red", ":material/cancel:", "rojo"), "SIN DATOS": ("gray", ":material/help:", "gris")}
GATE_NAME = {"G0": "Sol visible al llegar (G0)", "G1": "Energía solar mínima (G1)", "G2": "Pendiente máxima de aterrizaje (G2)",
             "G3": "Datos suficientes (G3)", "G4": "Noche demasiado larga sin calentador nuclear (G4)",
             "G5": "Potencia útil del panel (G5)", "G6": "Ventana de Tierra continua para comunicar (G6)"}
_GATE_SHORT = {"G0": "llegaría de noche, sin Sol", "G1": "casi no hay luz solar", "G2": "el suelo es demasiado inclinado",
               "G4": "las noches son demasiado largas", "G5": "el panel elegido da potencia útil solo una parte pequeña del tiempo",
               "G6": "la Tierra no se ve el tiempo seguido necesario"}
SUN_FRACTION_NOTE = ("La fracción solar cuenta el tiempo en que se ve **alguna parte del disco solar** (basta un borde): puede superar la "
                     "fracción con el centro del disco visible. No son horas de «Sol entero» ni energía.")
CERTIFY_NOTE = ("**APTO por puertas no certifica un sitio.** Solo significa que supera las comprobaciones de este modelo "
                "(sin rocas, navegación ni enlace de radio).")
G_STATUS = {GateStatus.PASS: "✔ superada", GateStatus.FAIL: "✖ NO superada", GateStatus.NO_DATA: "? sin datos",
            GateStatus.NOT_APPLICABLE: "– no aplica"}


def fmt_utc_short(s: Optional[str]) -> str:
    """'2026-12-01T00:00:00' → '2026-12-01 00:00 UTC'."""
    return "—" if not s else s[:16].replace("T", " ") + " UTC"


def short_period(sc) -> bool:
    """True si el periodo no cabe la misión (no se pudo barrer ninguna ventana): el pipeline devuelve SIN DATOS."""
    return sc is not None and sc.mission_days is not None and sc.n_starts is None


def verdict_label(sc) -> str:
    return sc.verdict + (" (provisional)" if sc.verdict_provisional else "")


def verdict_badge(sc) -> None:
    color, icon, _ = VERDICT[sc.verdict]
    st.badge(verdict_label(sc), icon=icon, color=color,
             help="Lo deciden las puertas y los escenarios de incertidumbre, no la nota. " + (
                 "Provisional: sin terreno fino el cálculo es una cota optimista." if sc.verdict_provisional else ""))


_VERDICT_CHIP = {"APTO": ("ok", "✔"), "CONDICIONAL": ("cond", "◐"), "NO APTO": ("bad", "✖"), "SIN DATOS": ("nodata", "?")}


def verdict_chip(sc, *, big: bool = True) -> str:
    """Chip HTML del veredicto con icono Y texto: ✔ APTO · ◐ CONDICIONAL · ✖ NO APTO · ? SIN DATOS (+ «provisional»)."""
    kind, icon = _VERDICT_CHIP[sc.verdict]
    return chip(verdict_label(sc), kind, icon, big=big)


def verdict_sentence(sc) -> str:
    """Frase llana del veredicto (Público y cabecera): qué es y por qué."""
    fails = [g for g in sc.gates if g.hard and g.status is GateStatus.FAIL]
    if sc.verdict == "NO APTO":
        why = " y ".join(gate_why(g) for g in fails) or "falla una comprobación mínima"
        return (f"No apto: {why}." + (" Es provisional: sin terreno fino el cálculo es una cota optimista, "
                                      "así que el relieve rara vez lo arreglaría." if sc.verdict_provisional else ""))
    if sc.verdict == "SIN DATOS":
        if short_period(sc):
            return (f"No se puede decidir: el periodo es más corto que la misión ({sc.mission_days:g} d) y no hay una ventana completa que "
                    "evaluar. Alarga el periodo.")
        return "No se puede decidir: faltan datos fiables del terreno, así que la nota es solo orientativa y probablemente optimista."
    if sc.verdict == "CONDICIONAL":
        soft = [g for g in sc.gates if not g.hard and g.status is GateStatus.FAIL]
        why = [gate_why(g) for g in soft]
        if "escenarios" in sc.verdict_reason:
            why.append("con pequeños cambios en los datos deja de cumplir alguna comprobación")
        if "ventana frágil" in sc.verdict_reason:
            why.append("solo unas pocas fechas de inicio sirven")
        return "Candidato con reservas: " + ("; ".join(why) or "revisa el motivo") + "."
    return "Supera todas las comprobaciones del modelo; es un buen candidato, no una garantía."


def gate_why(g) -> str:
    """Motivo llano de una puerta que falla (corto, para el veredicto). G7 lleva el hueco medido y el límite del perfil."""
    if g.id == "G7" and g.value is not None and g.limit is not None:
        return f"hueco sin comunicaciones de {fmt_num(g.value, 1)} h supera lo tolerado por el perfil ({g.limit:g} h)"
    return _GATE_SHORT.get(g.id, g.id)


def link_gap_line(res) -> Optional[str]:
    """«Hueco máximo sin comunicaciones: X h» de la ventana de misión evaluada, para ponerlo junto al veredicto. None si no hay enlace
    medido (red en «solo geometría» o sin ventana). Si G7 falla, añade el motivo en lenguaje llano."""
    sc = res.score
    i = res.score_inputs
    g7 = next((g for g in (sc.gates if sc is not None else ()) if g.id == "G7"), None)
    gap = g7.value if g7 is not None and g7.value is not None else (None if i is None else i.max_link_gap_h)
    if gap is None:
        return None
    t = f"Hueco máximo sin comunicaciones: {fmt_num(gap, 1)} h"
    if g7 is not None and g7.status is GateStatus.FAIL:
        t += f" (puerta G7, {'dura' if g7.hard else 'blanda'}): {gate_why(g7)}."
    elif g7 is not None and g7.limit is not None:
        t += f" (el perfil tolera {g7.limit:g} h)."
    return t


def best_date_sentence(sc) -> str:
    """Frase llana de «cuándo mejor aterrizar»."""
    if sc.mission_days is None:
        return "No hay una ventana de misión definida: se ha evaluado todo el periodo elegido."
    if short_period(sc):
        return "No se puede proponer una fecha: el periodo es más corto que la misión."
    if sc.best_start_utc is None:
        return "Ninguna fecha del periodo cumple las comprobaciones mínimas: prueba otro periodo u otro sitio."
    return (f"La mejor fecha candidata para aterrizar es el {fmt_utc_short(sc.best_start_utc)}: así la misión de {sc.mission_days:g} días acabaría el "
            f"{fmt_utc_short(sc.best_window_end_utc)}." + _feasible_starts_text(sc))


def _feasible_starts_text(sc) -> str:
    """«Sirven X de N fechas de inicio probadas»; con una sola fecha no hay porcentaje que dar (el periodo es igual a la misión)."""
    f, n = sc.feasible_start_fraction, sc.n_starts
    if f is None or not n:
        return ""
    if n == 1:
        return " Solo se probó una fecha de inicio (el periodo es igual a la misión): alarga el periodo para comparar fechas."
    return f" Sirven {round(f * n)} de {n} fechas de inicio probadas ({f:.0%})."


def plain_gate_name(name: str) -> str:
    """Nombre de puerta sin el código técnico («(G7)») cuando el modo es Público."""
    return re.sub(r"\s*\((?:puerta )?G\d\)", "", name) if state.is_public() else name


def plain_reason(text: str) -> str:
    """Motivo de un veredicto sin códigos de puerta («G0: no apto…» → «no apto…») ni símbolos de código cuando el modo es Público."""
    if not state.is_public():
        return text
    t = re.sub(r"G\d:\s*", "", text)
    return t.replace("f_sol", "fracción de Sol").replace("D_max", "noche máxima").replace("p90", "pendiente típica")


def gate_rows(gates) -> list[dict]:
    """Tabla de puertas: tipo, estado, valor, límite y margen (negativo = incumple). En modo Público sin los códigos (G0…G7)."""
    f = lambda x: "—" if x is None else fmt_num(x, 2)   # noqa: E731
    return [{"Puerta": plain_gate_name(GATE_NAME.get(g.id, g.id)), "Tipo": "dura" if g.hard else "blanda", "Estado": G_STATUS[g.status],
             "Valor": f(g.value), "Límite": f(g.limit), "Margen": "—" if g.margin_fraction is None else f"{100 * g.margin_fraction:+.0f} %",
             "Medido sobre": g.window or "—"} for g in gates]


# ------------------------------------------------------------------------------------------------ rango, energía y snap
MOUNT_LABELS = {
    "horizontal": "Horizontal", "tilted": "Inclinado", "vertical_fixed": "Vertical fijo",
    "vertical_az_tracking": "Vertical con seguimiento azimutal", "two_axis": "Dos ejes (cota ideal)",
    "terrain_normal": "Paralelo al suelo",
}
G5_NOTE = ("**G5, potencia útil:** con un panel elegido, comprueba que el panel y el montaje den potencia útil (por encima de un mínimo "
           "de su potencia nominal) durante una fracción mínima de la ventana de misión. Aparece solo cuando hay panel.")


def range_text(sc) -> str:
    """«Rango no calculado» o «Rango a – b» (+ aviso si es estrecho). Nunca [x, x] como si fuera un resultado de incertidumbre."""
    if not sc.range_computed:
        band = sc.score_max - sc.score_min >= 0.05
        return "Rango no calculado" + (f" (la banda {fmt_num(sc.score_min, 0)} – {fmt_num(sc.score_max, 0)} solo refleja el terreno no evaluable)"
                                       if sc.partial and band else "")
    lo, hi = sc.score_min, sc.score_max
    d = 0 if round(lo) != round(hi) or hi == lo else 1
    txt = f"Rango {fmt_num(lo, d)} – {fmt_num(hi, d)}"
    return txt + (" (estrecho: la incertidumbre apenas mueve la nota)" if hi - lo < 0.05 else "")


def range_label(sc) -> str:
    """Solo el rango para tablas: «no calculado» o «a – b»."""
    return "no calculado" if sc is None or not sc.range_computed else f"{fmt_num(sc.score_min, 0)} – {fmt_num(sc.score_max, 0)}"


def range_prompt(results, *, key: str, can_activate: bool = True) -> None:
    """Si algún resultado no tiene rango calculado, lo dice (con su motivo) y ofrece activar la incertidumbre."""
    miss = [r for r in results if r.score is not None and not r.score.range_computed]
    if not miss:
        return
    st.caption("**Rango no calculado:** " + (miss[0].score.range_note or "no se ejecutó el análisis de incertidumbre") + ".")
    if can_activate:
        st.button("Calcular el rango de incertidumbre", key=key, on_click=request_uncertainty_on, icon=":material/tune:",
                  help="Es más lento: repite el cálculo con los escenarios de sensibilidad.")


def snap_phrase(edge_km: Optional[float], inside: Optional[bool], rank: Optional[int], what: str = "rasgo") -> str:
    """«a 0,34 km dentro del borde del cráter» / «a 0,20 km fuera, en el margen» (+ puesto en el mapa de idoneidad). '' sin dato."""
    parts = []
    if edge_km is not None:
        if inside is False:
            parts.append(f"ningún punto candidato dentro del {what}: se usa el más cercano, a {fmt_num(abs(edge_km), 2, 'km')} "
                         f"{'fuera, en el margen' if edge_km >= 0 else 'dentro del borde'}")
        elif edge_km < 0:
            parts.append(f"a {fmt_num(-edge_km, 2, 'km')} dentro del borde del {what}")
        else:
            parts.append(f"a {fmt_num(edge_km, 2, 'km')} fuera, en el margen del {what}")
    if rank is not None:
        parts.append(f"puesto {rank} del mapa de idoneidad")
    return "; ".join(parts)


def observer_snap_phrase(o, what: str = "rasgo") -> str:
    return snap_phrase(o.snap_edge_offset_km, o.snap_inside_feature, o.snap_map_rank, what)


def polar_horizontal_warning(lat_deg: float, mount_type: Optional[str]) -> None:
    """Aviso breve y visible si se usa un panel horizontal en el polo (|lat|>70°)."""
    if mount_type != "horizontal" or not state.is_polar(lat_deg):
        return
    h, ratio = state.polar_penalty(lat_deg)
    st.warning(f"**A esta latitud un panel plano casi no produce:** el Sol no pasa de ~{fmt_num(h, 1)}° sobre el horizonte, así que "
               f"uno horizontal recibe ≈ {fmt_num(ratio, 0)}× menos luz que uno vertical con seguimiento azimutal (sen h frente a cos h). "
               "Elige un montaje vertical.", icon=":material/warning:")


def energy_summary(sc, ctx, lat_deg: float, req=None) -> None:
    """Qué panel y montaje (y sobre qué base) se usaron en la energía del score; insignia si el panel es estimado."""
    if sc is None:
        return
    if sc.energy_basis != "panel":
        st.caption(f":material/solar_power: Energía = fracción de tiempo con Sol (geométrica): no hay panel elegido. {sc.energy_note}".strip())
        return
    panel = next((p for p in ctx.panels.panels if p.id == sc.energy_panel_id), None)
    mount = MOUNT_LABELS.get(sc.energy_mounting or "", sc.energy_mounting or "—")
    with st.container(border=True):
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**:material/solar_power: Energía del score:** panel «{panel.name if panel else sc.energy_panel_id}» · montaje **{mount}** · "
                    f"potencia media {fmt_pct(sc.energy_p_rel_mean)} de la nominal · potencia útil el {fmt_pct(sc.energy_duty_useful, 0)} de la ventana.")
        if panel is not None and panel_status(panel) == "estimado":
            c2.badge("Panel estimado", icon=":material/science:", color="orange",
                     help="Sin datasheet: sus parámetros térmicos y ópticos son estimaciones de LSI con rango; el resultado es orientativo.")
        elif panel is not None and panel_status(panel) == "no_calculable":
            c2.badge("Panel no calculable", icon=":material/block:", color="red")
        st.caption(sc.energy_note)
    polar_horizontal_warning(lat_deg, sc.energy_mounting)
    if req is not None and sc.energy_mounting:
        mount_fallback_notice(req, sc.energy_panel_id, state.wanted_mount(None, lat_deg), MountingSpec(MountingType(sc.energy_mounting)), ctx)


def request_uncertainty_on() -> None:
    st.session_state[StateKey.WITH_UNCERTAINTY] = True
    st.session_state["cmp_unc"] = True
    st.session_state["cmp_unc_force"] = True


def uncertainty_note(res: AnalysisResult, *, key: str) -> None:
    """Junto al veredicto: si no se calcularon los escenarios de incertidumbre, dilo y ofrece activarlos."""
    if res.score_scenarios or (res.score is not None and res.score.verdict in ("NO APTO", "SIN DATOS")):
        return
    st.caption("Veredicto sin escenarios de incertidumbre: no se ha comprobado si cambios razonables en los datos (cobertura, σ del DEM, "
               "discretización) harían fallar alguna puerta; un APTO aquí es provisional.")
    st.button("Calcular escenarios de incertidumbre", key=key, on_click=request_uncertainty_on, icon=":material/tune:",
              help="Es más lento: repite el cálculo con los escenarios de sensibilidad.")


def state_label(vis_state: VisibilityState) -> str:
    """«● visible» / «◐ parcial» / «○ oculto»: símbolo + texto para no depender del color."""
    return STATE_TEXT[VisibilityState(vis_state)]


# ------------------------------------------------------------------------------------------------ avisos (§9.3)
def _ctx_text(w: ScientificWarning) -> str:
    return f" ({w.context})" if w.context and ";" not in w.context and "=" not in w.context else ""


_POWER_ONLY = {WarningCode.PANEL_UNVERIFIED, WarningCode.COLD_EXTRAPOLATION, WarningCode.IAM_GRAZING_UNCERTAIN}


def experimental_panels() -> int:
    """Nº de paneles del catálogo sin datasheet (evidencia «experimental»); 0 si el contexto no está disponible."""
    try:
        from ui import cache
        return sum(1 for p in cache.get_context().panels.panels if getattr(p, "evidence_group", "respaldado") != "respaldado")
    except Exception:       # noqa: BLE001 - el chip resumen no puede romper la página
        return 0


def scope_chips(n_warn: int = 0) -> str:
    """Chip resumen SIEMPRE visible del alcance: lo que la herramienta NO garantiza y cuántos paneles son experimentales."""
    items = [chip("Alcance y límites", "info"), chip("Geometría ≠ potencia/enlace garantizados", "warn"),
             chip(f"Paneles experimentales: {experimental_panels()}", "warn", "⚗")]
    if n_warn:
        items.append(chip(f"Avisos de este cálculo: {n_warn}", "warn"))
    return '<div class="lsi-scope">' + chips(*items) + "</div>"


def warnings_band(result: Optional[AnalysisResult] = None, *, power: bool = False, notes: Sequence[str] = ()) -> None:
    """UN solo bloque «Alcance y límites»: chip resumen siempre visible + desplegable con TODOS los avisos científicos (§9.3).

    El desplegable lleva: «visibilidad geométrica ≠ potencia/enlace garantizados», los de ``ALWAYS_SHOWN_WARNINGS`` (GEOMETRIC_ONLY,
    ECLIPSES_NOT_MODELED y, en modo DEM, DEM_EFFECTIVE_RESOLUTION), las ``notes`` de la pantalla y, con ``result``, los avisos
    WARNING/CRITICAL del resultado (horizonte truncado, esfera lisa, ajuste al DEM…) y los informativos. Nada se elimina: se pliega.
    """
    sphere = result is not None and result.observer.mode is HorizonMode.SMOOTH_SPHERE
    codes = [c for c in ALWAYS_SHOWN_WARNINGS if not (c is WarningCode.DEM_EFFECTIVE_RESOLUTION and sphere)]
    # Los avisos de panel solo tienen sentido en «Potencia y paneles» (``power=True``): en el resto empujaban el contenido útil.
    extra = [w for w in (result.warnings if result is not None else ())
             if w.code not in ALWAYS_SHOWN_WARNINGS and (power or w.code not in _POWER_ONLY)]
    loud = [w for w in extra if w.severity in (Severity.WARNING, Severity.CRITICAL)]
    info = [w for w in extra if w.severity is Severity.INFO]
    st.markdown(scope_chips(len(loud)), unsafe_allow_html=True)
    with st.expander(f"Alcance y límites: leer los avisos científicos ({len(codes) + len(notes) + len(extra) + 1})"):
        st.markdown(f"**:material/info: Alcance y límites.** {GEOMETRIC_NOTE}")
        for c in codes:
            st.caption(f"• {STANDARD_WARNINGS_ES[c]}")
        for n in notes:
            st.caption("• " + n)
        for w in loud:
            crit = w.severity is Severity.CRITICAL
            (st.error if crit else st.warning)(f"**{'Crítico' if crit else 'Aviso'}:** {w.text_es}{_ctx_text(w)}",
                                               icon=":material/error:" if crit else ":material/warning:")
        if info:
            st.markdown("**Más avisos aplicables**")
            for w in info:
                st.caption(f"• {w.text_es}{_ctx_text(w)}")


def result_header(result: AnalysisResult) -> None:
    """Cabecera común: punto, modo (DEM / esfera lisa), DEM y su resolución efectiva, snap_to_dem y horizonte limitado."""
    o = result.observer
    st.markdown(f"**{o.label or 'Punto'}** · {fmt_num(o.lat_deg, 4)}°, {fmt_num(o.lon_deg_e, 4)}°E · altura del observador {fmt_num(o.height_m, 1, 'm')}")
    cols = st.columns(4)
    if o.mode is HorizonMode.DEM:
        res = result.dem_confidence.effective_resolution_m if result.dem_confidence else None
        cols[0].badge(f"Modo DEM ({o.dem_key})", icon=":material/terrain:", color="green", help=term_help("DEM"))
        cols[1].caption(f"Resolución efectiva ≈ {fmt_num(res, 0, 'm')}" if res else "Resolución efectiva del DEM peor que la nominal")
    elif o.mode is HorizonMode.FAR_FIELD:
        cols[0].badge(FAR_LABEL, icon=":material/terrain:", color="orange", help=far_field_note())
        cols[1].caption("Horizonte con el DEM polar de 80 m: aproximado")
    else:
        cols[0].badge("Modo esfera lisa: sin datos de terreno", icon=":material/public:", color="orange", help=term_help("Esfera lisa"))
        cols[1].caption("Sin relieve: solo la curvatura lunar")
    if o.snap_distance_km is not None:
        cols[2].badge((f"Punto ajustado al mapa: a {fmt_num(o.snap_distance_km, 2, 'km')} del pedido" if state.is_public()
                       else f"snap_to_dem: a {fmt_num(o.snap_distance_km, 2, 'km')}"), icon=":material/near_me:", color="orange",
                      help=term_help("snap_to_dem"))
    snap = observer_snap_phrase(o) if o.snap_distance_km is not None else ""
    if snap:
        st.caption(f":material/near_me: Punto elegido: {snap}.")
    lim = float(result.horizon.limited.mean()) if o.mode is HorizonMode.DEM and result.horizon.limited.size else 0.0
    if lim > 0:
        cols[3].badge(f"Horizonte limitado: {fmt_pct(lim, 0)} de azimutes", icon=":material/warning:", color="orange",
                      help=term_help("Cobertura del DEM"))


# ------------------------------------------------------------------------------------------------ descargas
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "lsi"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def result_json_bytes(result: AnalysisResult) -> bytes:
    """JSON del §7 validado contra el esquema (UTF-8, sin NaN)."""
    d = export.result_to_dict(result, generated_utc=_stamp())
    export.validate_export(d)
    return (json.dumps(d, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def result_csv_zip_bytes(result: AnalysisResult) -> bytes:
    """ZIP con timeseries.csv, windows.csv, horizon.csv, metrics.csv y metadata.json."""
    with tempfile.TemporaryDirectory() as td:
        paths = export.write_csv_bundle(result, Path(td), generated_utc=_stamp())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in paths.values():
                z.write(p, Path(p).name)
    return buf.getvalue()


def download_buttons(result: AnalysisResult, *, key: str) -> None:
    """Botones JSON y CSV (zip) de un resultado. Los bytes se generan al pulsar (no en cada rerun) y no provocan rerun."""
    base = f"lsi_{_slug(result.observer.label)}_{result.request.start_utc[:10]}"
    c1, c2 = st.columns(2)
    c1.download_button("Descargar JSON", data=lambda: result_json_bytes(result), file_name=f"{base}.json",
                       mime="application/json", on_click="ignore", key=f"{key}_json", icon=":material/download:",
                       help="Resultado completo con metadatos y avisos de alcance.")
    c2.download_button("Descargar CSV (zip)", data=lambda: result_csv_zip_bytes(result), file_name=f"{base}_csv.zip",
                       mime="application/zip", on_click="ignore", key=f"{key}_csv", icon=":material/download:",
                       help="Series, ventanas, horizonte y métricas en CSV UTF-8, más metadata.json.")


def download_comparison(rows: list[dict], *, key: str, file_name: str = "lsi_comparacion.csv") -> None:
    """Botón CSV de la tabla de comparación (``analysis.metrics.comparison_table``)."""
    def data() -> bytes:
        with tempfile.TemporaryDirectory() as td:
            return export.comparison_to_csv(rows, Path(td) / "c.csv").read_bytes()
    st.download_button("Descargar comparación (CSV)", data=data, file_name=file_name, mime="text/csv", on_click="ignore",
                       key=key, icon=":material/download:")


# ------------------------------------------------------------------------------------------------ accesibilidad
BRAND_SVG = ('<svg class="lsi-moon" viewBox="0 0 64 64" width="52" height="52" role="img" aria-label="Luna creciente">'
             '<defs><linearGradient id="lsiMoon" x1="0.1" y1="0" x2="0.9" y2="1"><stop offset="0" stop-color="#f4faff"/>'
             '<stop offset="0.55" stop-color="#9fd8ff"/><stop offset="1" stop-color="#3aa0ff"/></linearGradient>'
             '<radialGradient id="lsiGlow" cx="0.4" cy="0.45" r="0.6"><stop offset="0" stop-color="#3aa0ff" stop-opacity=".35"/>'
             '<stop offset="1" stop-color="#3aa0ff" stop-opacity="0"/></radialGradient></defs>'
             '<circle cx="32" cy="32" r="30" fill="url(#lsiGlow)"/>'
             '<path d="M40 6a26 26 0 1 0 0 52 21 21 0 1 1 0-52z" fill="url(#lsiMoon)"/>'
             '<circle cx="50" cy="14" r="1.6" fill="#f4faff"/><circle cx="55" cy="26" r="1" fill="#9fd8ff"/></svg>')
TAGLINE = "Elegir bien el lugar. Aterrizar con datos."
DATA_CREDIT = "Datos: NASA LOLA · PGDA · USGS · JPL"


def brand_header() -> None:
    """Marca LUNARIS con una luna creciente propia en SVG (sin logotipos de terceros: no se suplanta a ninguna organización) y
    el crédito de los datos en texto."""
    st.markdown('<header class="lsi-brand">' + BRAND_SVG + '<div><div class="lsi-brand-name">LUNARIS</div>'
                '<div class="lsi-brand-sub">Lunar Site Intelligence</div></div>'
                f'<div class="lsi-brand-credit"><span class="lsi-tag">{esc(TAGLINE)}</span><span>{esc(DATA_CREDIT)}</span></div></header>',
                unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ panel de control
def card_head(icon: str, title: str, sub: str = "", tone: str = "") -> None:
    """Cabecera de tarjeta del panel de control: icono + título (+ subtítulo llano). Va dentro de ``st.container(border=True)``."""
    st.markdown(f'<div class="lsi-card-head {esc(tone)}"><span class="ic" aria-hidden="true">{esc(icon)}</span>'
                f'<h3>{esc(title)}</h3></div>' + (f'<div class="lsi-card-sub">{esc(sub)}</div>' if sub else ""), unsafe_allow_html=True)


def stat_rows(rows: Sequence[tuple[str, str]], tone: str = "") -> None:
    """Lista de datos «etiqueta · valor» bajo una figura; el valor se muestra completo (nunca truncado)."""
    items = "".join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in rows if v and v != "—")
    if items:
        st.markdown(f'<dl class="lsi-stats {esc(tone)}">{items}</dl>', unsafe_allow_html=True)


def credit_strip() -> None:
    st.markdown(f'<div class="lsi-credit"><span aria-hidden="true">ⓘ</span> {esc(DATA_CREDIT)} · geometría SPICE, relieve real (DEM) y '
                'estimaciones con supuestos declarados.</div>', unsafe_allow_html=True)


def mission_strip(res: AnalysisResult, *, key: str, link_label: str = "") -> None:
    """Franja de informe de misión: veredicto por puertas (icono + texto), su frase y el botón de descarga. Todo sale del motor."""
    sc = res.score
    if sc is None:
        return
    kind, icon = _VERDICT_CHIP[sc.verdict]
    m = res.window_metrics or res.metrics
    stats = [("Sol", fmt_pct(m.solar_fraction, 1))]
    stats.append(("Enlace" if m.link_fraction is not None else "Tierra a la vista", fmt_pct(m.link_fraction if m.link_fraction is not None else m.earth_fraction, 1)))
    stats.append(("Noche máxima", ("≥ " if m.max_darkness_truncated else "") + fmt_num(m.max_darkness_s / 3600.0, 1, "h")))
    if res.slope_r100 is not None and res.slope_r100.p90_deg is not None and math.isfinite(res.slope_r100.p90_deg):
        stats.append(("Pendiente (p90)", fmt_num(res.slope_r100.p90_deg, 1, "°")))
    with st.container(border=True, key=f"lsi-mission-{key}"):
        c1, c2, c3 = st.columns([5, 4, 2], vertical_alignment="center")
        c1.markdown(f'<div class="lsi-mission-head"><div class="lsi-kicker">Informe de misión</div>'
                    f'<div class="lsi-mission-title">{esc(place_name(res.observer.label))} {chip(verdict_label(sc), kind, icon)}</div>'
                    f'<p class="lsi-mission-read">{esc(verdict_sentence(sc))}</p></div>', unsafe_allow_html=True)
        c2.markdown('<dl class="lsi-stats row">' + "".join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in stats) + "</dl>",
                    unsafe_allow_html=True)
        c3.download_button("Descargar informe", data=lambda: result_json_bytes(res), file_name=f"lsi_informe_{_slug(res.observer.label)}_{res.request.start_utc[:10]}.json",
                           mime="application/json", on_click="ignore", key=f"lsi_dl_{key}", icon=":material/download:", width="stretch",
                           help="Resultado completo (JSON validado) con metadatos y avisos de alcance. La descarga no recalcula nada.")


@lru_cache(maxsize=1)
def _css() -> str:
    return Path(__file__).with_name("styles.css").read_text(encoding="utf-8")


# ponytail: ``<html lang>`` solo se puede fijar con JS desde un iframe del mismo origen; si el navegador lo bloquea, la app sigue
# funcionando y solo queda ``lang="en"`` (limitación conocida).
_LANG_JS = "<script>try{var d=window.parent.document.documentElement;if(d.lang!=='es'){d.lang='es';}}catch(e){}</script>"


def inject_styles() -> None:
    """Hoja de estilos de la identidad visual (un único ``ui/styles.css``) + ``<html lang="es">``. Llamar una vez por ejecución."""
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)     # st.html no registra la hoja en esta versión de Streamlit
    try:
        st.iframe(_LANG_JS, height=1)       # el iframe (mismo origen) fija el idioma del documento padre; styles.css lo oculta
    except Exception:       # noqa: BLE001 - el idioma es una mejora de accesibilidad, nunca debe romper la app
        pass


inject_accessibility_css = inject_styles       # nombre anterior (foco visible y «reducir movimiento» viven ahora en styles.css)


def accessible_chart(fig, alt: str, *, key: Optional[str] = None, details: Optional[Iterable[str]] = None) -> None:
    """Gráfico Plotly + texto alternativo visible debajo (lo que un lector de pantalla lee en lugar de la figura).
    ``alt`` resume qué muestra y la conclusión; ``details`` añade filas de datos en un desplegable."""
    st.plotly_chart(fig, width="stretch", key=key)
    st.caption(f"Descripción de la figura: {alt}")
    if details:
        with st.expander("Datos de la figura en texto"):
            for d in details:
                st.markdown(f"- {d}")


def scope_figures(res: AnalysisResult) -> dict:
    """Cifras de UN mismo AnalysisResult en sus dos ámbitos: el PERIODO completo (``res.metrics``) y la VENTANA de misión
    que puntúa el score (``res.score_inputs``). Comparación y Score leen de aquí, así que nunca se contradicen."""
    m, sc, i = res.metrics, res.score, res.score_inputs
    out = {"period_start": res.request.start_utc, "period_end": res.request.end_utc, "period_days": m.period_s / 86400.0,
           "sun_period_pct": 100.0 * m.solar_fraction, "dark_period_h": m.max_darkness_s / 3600.0,
           "earth_period_pct": 100.0 * m.earth_fraction,
           "profile": res.request.score_profile_id, "window_start": None, "window_end": None, "window_days": None,
           "sun_window_pct": None, "dark_window_h": None, "earth_window_pct": None}
    if sc is not None and i is not None:
        out.update(window_start=sc.window_start_utc, window_end=sc.window_end_utc, window_days=sc.mission_days,
                   sun_window_pct=100.0 * i.f_sun, dark_window_h=i.d_max_h, earth_window_pct=100.0 * i.f_earth)
    return out


def scope_caption(res: AnalysisResult, profile_label: str = "") -> str:
    """Rótulo de qué ventana y qué perfil dan las cifras (se muestra en Comparación y en Score)."""
    f = scope_figures(res)
    txt = (f"**Periodo analizado:** {fmt_utc_short(f['period_start'])} → {fmt_utc_short(f['period_end'])} "
           f"({fmt_num(f['period_days'], 1)} d)")
    if f["window_start"]:
        txt += (f" · **ventana de misión del score:** {fmt_utc_short(f['window_start'])} → {fmt_utc_short(f['window_end'])} "
                f"({fmt_num(f['window_days'], 1)} d)")
    return txt + (f" · **perfil:** {profile_label}." if profile_label else ".")


def scope_table(res: AnalysisResult, profile_label: str = "") -> None:
    """Rótulo + tabla periodo vs ventana (mismas cifras en Comparación y Score)."""
    f = scope_figures(res)
    st.caption(scope_caption(res, profile_label))
    if f["window_start"] is None:
        return
    st.dataframe([{"Medida": "Sol visible (%)", "Periodo completo": fmt_num(f["sun_period_pct"], 1),
                   "Ventana de misión (la del score)": fmt_num(f["sun_window_pct"], 1)},
                  {"Medida": "Noche más larga (h)", "Periodo completo": fmt_num(f["dark_period_h"], 1),
                   "Ventana de misión (la del score)": fmt_num(f["dark_window_h"], 1)},
                  {"Medida": "Tierra visible (%)", "Periodo completo": fmt_num(f["earth_period_pct"], 1),
                   "Ventana de misión (la del score)": fmt_num(f["earth_window_pct"], 1)}], hide_index=True, width="stretch")
    st.caption("Las dos columnas son del mismo análisis; difieren solo porque la ventana de misión es más corta que el periodo "
               "(y empieza en la mejor fecha).")


BEST_SPOTS_PAGE = "ui/pages/best_spots.py"
SEARCH_PAGE = "ui/pages/search.py"


def empty_state(msg: str, *, quiet: bool = False) -> None:
    """Estado vacío explícito con enlace a «Mejores puntos y fechas» (en vez de una figura con ejes vacíos)."""
    if quiet:       # st.caption no admite ``icon``
        st.caption(":material/visibility_off: " + msg)
    else:
        st.info(msg, icon=":material/visibility_off:")
    try:
        st.page_link(BEST_SPOTS_PAGE, label="Ir a Mejores puntos y fechas", icon=":material/event_available:")
    except (st.errors.StreamlitAPIException, KeyError):     # fuera de la navegación (pruebas): el texto ya orienta
        pass


def no_visibility(res: AnalysisResult, *, what: str = "visibles", need: tuple[str, ...] = ("sun", "earth")) -> bool:
    """Estado vacío explícito (nunca ejes vacíos): True si ni el Sol ni la Tierra (los de ``need``) tienen ventanas en el
    periodo; en ese caso avisa con un enlace a «Mejores puntos y fechas» y quien llama NO debe dibujar la figura.
    Si falta solo uno de los dos, lo dice en una nota y devuelve False."""
    tl = res.timeline
    missing = [(n, w) for n, w in (("sun", ("el Sol", tl.sun)), ("earth", ("la Tierra", tl.earth))) if n in need and not w[1].windows]
    names = [w[0] for _, w in missing]
    if not names:
        return False
    msg = (f"{' ni '.join(names).capitalize()} no {'es' if len(names) == 1 else 'son'} {what} en ningún momento de este periodo "
           "desde este punto; prueba otra fecha o busca el mejor punto en «Mejores puntos y fechas».")
    empty_state(msg, quiet=len(names) < len(need))
    return len(names) == len(need)


def public_note(text: str) -> None:
    """Explicación en lenguaje llano; solo se muestra en modo Público."""
    if state.is_public():
        st.info(text, icon=":material/lightbulb:")


# ------------------------------------------------------------------------------------------------ hero y tarjetas de contexto
def place_name(label: Optional[str]) -> str:
    """Nombre legible del lugar: sin el identificador interno («Site23 Malapert massif» → «Malapert massif»)."""
    return re.sub(r"^Site\d+\s+", "", label or "").strip() or "Punto elegido"


def hero_html(*, kicker: str, title: str, meta: Sequence[tuple[str, str]] = (), chips_html: str = "", read: str = "", why: str = "",
              facts: Sequence[tuple[str, str, str]] = ()) -> str:
    """Cabecera «hero»: lugar, ventana de misión, veredicto (chips ya construidos con ``chip``), lectura rápida en una frase grande
    y datos clave. TODO texto se escapa aquí (``meta``, ``title``, ``read``…): los nombres vienen de datos externos (gazetteer…)."""
    meta_html = "".join(f'<div class="lsi-hero-meta"><b>{esc(k)}</b> {esc(v)}</div>' for k, v in meta)
    facts_html = "".join(f'<div class="lsi-fact"><span class="k">{esc(k)}</span><span class="v">{esc(v)}'
                         + (f' <small>{esc(sm)}</small>' if sm else "") + "</span></div>" for k, v, sm in facts)
    return ('<section class="lsi-hero" aria-label="Resumen del sitio y la ventana de misión">'
            f'<div class="lsi-hero-kicker">{esc(kicker)}</div><h2 class="lsi-hero-title">{esc(title)}</h2>{meta_html}{chips_html}'
            + (f'<p class="lsi-hero-read"><span class="sr-only">Lectura rápida. </span>{esc(read)}</p>' if read else "")
            + (f'<div class="lsi-kpi-note">{esc(why)}</div>' if why else "")
            + (f'<div class="lsi-hero-facts">{facts_html}</div>' if facts_html else "") + "</section>")


def slope_facts(res: AnalysisResult) -> list[tuple[str, str, str]]:
    """Pendiente en la huella a r = 50 m y r = 100 m (``AnalysisResult.slope_r50`` / ``slope_r100``: p90, y % del área sobre el límite)
    con el umbral de aterrizaje, para ponerla junto al veredicto. Sin dato (esfera lisa o borde del DEM) no inventa nada."""
    out = []
    for attr, default_r in (("slope_r50", 50.0), ("slope_r100", 100.0)):
        sl = getattr(res, attr, None)
        r = getattr(sl, "r_foot_m", default_r)
        name = f"Pendiente a {r:g} m (p90)" if not state.is_public() else f"Inclinación del suelo a {r:g} m"
        deg = getattr(sl, "p90_deg", None)
        if sl is None or deg is None or not math.isfinite(deg):
            if sl is not None:
                out.append((name, "—", "sin dato" + (": el disco toca el borde del mapa" if getattr(sl, "touches_dem_edge", False) else "")))
            continue
        lim = sl.landing_limit_deg
        parts = [] if lim is None else [f"límite {fmt_num(lim, 0, '°')}", "dentro" if deg <= lim else "SUPERA el límite"]
        if sl.pct_area_above_limit is not None and not state.is_public():
            parts.append(f"{fmt_num(sl.pct_area_above_limit, 0, '%')} del área sobre el límite")
        if sl.touches_dem_edge:
            parts.append("toca el borde del mapa")
        out.append((name, fmt_num(deg, 1, "°"), " · ".join(parts)))
    return out


def safe_page_link(path: str, label: str, icon: str) -> None:
    """``st.page_link`` que no falla fuera de la navegación (pruebas)."""
    try:
        st.page_link(path, label=label, icon=icon)
    except (st.errors.StreamlitAPIException, KeyError):
        pass


# ------------------------------------------------------------------------------------------------ capacidad del sitio
EVIDENCE_BADGE = {
    "datasheet": ("green", ":material/verified:", "Evidencia: datasheet del fabricante"),
    "paper": ("blue", ":material/menu_book:", "Evidencia: paper o informe de agencia"),
    "derivado": ("orange", ":material/calculate:", "Evidencia: derivada de otros datos (con fórmula)"),
    "investigacion": ("red", ":material/science:", "Evidencia: investigación (sin datasheet ni medida espacial)"),
}
EXPERIMENTAL_TEXT = ("**Panel EXPERIMENTAL sin datasheet.** Le falta la eficiencia o el coeficiente de temperatura en una fuente primaria: "
                     "sus vatios son una estimación con rango amplio, no un dato de fabricante. No se mezcla con los paneles respaldados "
                     "en los rankings por defecto.")

CAPACITY_NOTES = (
    "**Enlace posible = condición geométrica y de cobertura** (Tierra visible con margen de antena y al menos una estación viendo la "
    "Luna). **No es un presupuesto de enlace RF ni una garantía** de comunicación: no hay ganancia de antena, potencia, ruido, "
    "ocupación de la red ni máscara de terreno de las antenas terrestres.",
    "**Sol visible no es potencia garantizada.** La potencia eléctrica es una estimación con supuestos declarados; no incluye "
    "empaquetado, cableado ni degradación real del panel.",
    "**Paneles experimentales** (sin datasheet) llevan siempre su etiqueta y un rango amplio.",
    "**Elevación mínima de ESTRACK supuesta (6°, no publicada).** La de los DSN (6°) es la publicada por la red.",
    "**La red NSN de NASA no está incluida:** no se pudo verificar ninguna de sus estaciones en fuente oficial.",
)


def evidence_badge(panel) -> None:
    """Insignia del nivel de evidencia del panel (datasheet/paper/derivado/investigación) y, si es experimental, aviso destacado."""
    lvl = getattr(panel, "evidence_level", "") or ""
    color, icon, text = EVIDENCE_BADGE.get(lvl, ("gray", ":material/help:", "Evidencia: sin clasificar"))
    st.badge(text, icon=icon, color=color, help=getattr(panel, "evidence_summary", "") or None)
    if getattr(panel, "evidence_group", "respaldado") == "experimental_sin_datasheet":
        st.error(EXPERIMENTAL_TEXT, icon=":material/science:")


def handoff_note() -> str:
    """Tolerancia de fusión de huecos en traspasos entre estaciones, leída de config/ground_stations.json (``handoff_merge_tol_s``)."""
    from lsi.astronomy.ground_stations import handoff_merge_tol_s
    tol = handoff_merge_tol_s()
    return (f"**Traspasos entre estaciones:** al unir la red se fusionan los huecos de hasta {fmt_num(tol, 0, 's')} entre ventanas de dos "
            "estaciones (valor [cal] de la configuración): están por debajo de la precisión del modelo de orientación de la Tierra y de la "
            "interpolación de los cruces, y no son pérdidas reales de enlace. Un hueco mayor sí cuenta.")


def capacity_notes_list() -> tuple[str, ...]:
    """Avisos honestos de «Capacidad del sitio» (van dentro del bloque plegable «Alcance y límites», que sigue siendo accesible)."""
    return (*CAPACITY_NOTES, handoff_note())


def mount_fallback_notice(power_req, panel_id: Optional[str], wanted: Optional[MountingType], used: Optional[MountingSpec],
                          ctx, *, who: str = "") -> None:
    """Aviso visible si el montaje pedido NO lo admite el panel y se calcula con otro (``state.mounting_for`` o el automático por
    latitud). Da la potencia media con el montaje usado frente a la que daría el pedido (W/m², sobre ``power_req``)."""
    panel = next((p for p in ctx.panels.panels if p.id == panel_id), None)
    if panel is None or wanted is None or used is None or wanted in panel.mounting_allowed or wanted is used.type:
        return
    from ui import cache
    lab = lambda t: MOUNT_LABELS.get(t.value, t.value).lower()   # noqa: E731
    what = "seguimiento" if wanted is MountingType.VERTICAL_AZ_TRACKING else f"el montaje «{lab(wanted)}»"
    txt = f"{who}**Este panel no admite {what}:** se calcula con montaje {lab(used.type)}"
    try:
        runs = cache.get_power(power_req, [(panel.id, used), (panel.id, state.mount_spec(wanted))])
        w = [None if r.error is not None or panel.areal_power_w_m2_am0 is None else r.summary.mean_p_rel * panel.areal_power_w_m2_am0
             for r in runs]
    except Exception:       # noqa: BLE001 - el aviso no puede romper la página; sin cifras se queda el texto
        w = [None, None]
    if None not in w:
        txt += f"; la potencia media es {fmt_num(w[0], 0)} W/m² en vez de {fmt_num(w[1], 0)} W/m² (con {lab(wanted)}, que este panel no admite)"
    st.warning(txt + ".", icon=":material/warning:")


def _py(o: Any) -> Any:
    """Estructura serializable: numpy → Python, NaN/inf → None, tuplas → listas."""
    if isinstance(o, Mapping):
        return {str(k): _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_py(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def ficha_json_bytes(res: AnalysisResult, facts: Mapping[str, Any]) -> bytes:
    """Ficha del sitio en JSON: cifras de solar y conectividad (con estaciones y contactos) + el análisis completo de
    ``analysis.export`` (que NO incluye el enlace DTE: por eso las estaciones y contactos van en ``ficha``)."""
    d = {"ficha": _py(facts), "analisis_export": export.result_to_dict(res, generated_utc=_stamp())}
    return (json.dumps(d, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def ficha_csv_zip_bytes(res: AnalysisResult, facts: Mapping[str, Any], stations: Sequence[Mapping], contacts: Sequence[Mapping]) -> bytes:
    """ZIP: ``ficha.csv`` (clave, valor), ``estaciones.csv``, ``contactos.csv`` y los CSV de ``analysis.export``."""
    import csv

    def table(rows: Sequence[Mapping]) -> bytes:
        buf = io.StringIO()
        cols = list(rows[0]) if rows else ["sin_datos"]
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
        return buf.getvalue().encode("utf-8")

    flat: list[dict] = []

    def walk(prefix: str, o: Any) -> None:
        if isinstance(o, Mapping):
            for k, v in o.items():
                walk(f"{prefix}.{k}" if prefix else str(k), v)
        elif isinstance(o, (list, tuple)):
            flat.append({"clave": prefix, "valor": "; ".join(str(x) for x in o)})
        else:
            flat.append({"clave": prefix, "valor": o})
    walk("", _py(facts))
    with tempfile.TemporaryDirectory() as td:
        paths = export.write_csv_bundle(res, Path(td), generated_utc=_stamp())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("ficha.csv", table(flat))
            z.writestr("estaciones.csv", table([_py(r) for r in stations]))
            z.writestr("contactos.csv", table([_py(r) for r in contacts]))
            for p in paths.values():
                z.write(p, Path(p).name)
    return buf.getvalue()
