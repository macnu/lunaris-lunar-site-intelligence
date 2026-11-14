"""Acerca de / Metodología y límites. No calcula física: cifras de ``config/`` y del código; lo no verificado lleva «a verificar»."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st  # noqa: E402

from lsi.contracts import (  # noqa: E402
    MOON_RADIUS_KM, SPICE_ABCORR, SPICE_FRAME, STANDARD_WARNINGS_ES, SUN_RADIUS_KM,
)
from lsi.energy import panels as pn  # noqa: E402
from ui import cache, components as C, state  # noqa: E402

ctx = cache.get_context()
cfg = ctx.cfg
num = C.fmt_num


def _count_tests() -> tuple[int, int]:
    """(ficheros test_*.py, funciones test_*) contados en ``tests/``; (0, 0) si no está disponible."""
    files = sorted((ROOT / "tests").glob("test_*.py"))
    n = sum(len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8", errors="ignore"), re.M)) for f in files)
    return len(files), n


def _gazetteer_rows() -> int | None:
    p = ROOT / str(cfg["gazetteer"]["fallback_csv_path"])
    try:
        with p.open(encoding="utf-8") as fh:
            return max(sum(1 for _ in fh) - 1, 0)
    except OSError:
        return None


st.title("Acerca de: metodología y límites")
st.caption("Lunar Site Intelligence (LSI) · reto NASA Space Apps 2026, *Lunar Landing Site Navigator*")
C.warnings_band()

# ---------------------------------------------------------------------------------------------- 1. qué es
st.header("1. Qué es LSI y a qué pregunta responde")
st.markdown("**Pregunta:** *¿qué punto del polo sur lunar y qué fechas ofrecen más Sol y mejor visibilidad de la Tierra, "
            "y con qué confianza en los datos?* LSI compara lugares y fechas mostrando el horizonte real del terreno, "
            "el Sol y la Tierra sobre él, las ventanas de visibilidad, una estimación de potencia de paneles y un score "
            "explicable. Es una ayuda para comparar, no un sistema certificado de selección de sitio.")
C.public_note("Imagina estar de pie en la Luna mirando alrededor: las montañas tapan parte del cielo. "
              "LSI calcula, hora a hora, cuándo el Sol y la Tierra asoman por encima de esas montañas.")
st.table([
    {"Objetivo del reto": "Seleccionar y comparar sitios (curados y coordenadas propias)", "Pantalla": "Buscador · Comparación de sitios"},
    {"Objetivo del reto": "Fecha y hora flexibles, días lunares", "Pantalla": "Barra lateral · Línea temporal"},
    {"Objetivo del reto": "Sol y Tierra respecto al horizonte; tiempo hasta puesta de Sol / Earthset", "Pantalla": "Horizonte y visibilidad"},
    {"Objetivo del reto": "Elevación solar, duración de luz, ventanas de visibilidad de la Tierra", "Pantalla": "Línea temporal · Potencia y paneles"},
    {"Objetivo del reto": "Varias visualizaciones (mapas 2D, superficie 3D)", "Pantalla": "Explorador 3D · Horizonte y visibilidad"},
    {"Objetivo del reto": "Dinámica temporal (animaciones/línea temporal)", "Pantalla": "Línea temporal"},
    {"Objetivo del reto": "Accesibilidad para distintos niveles", "Pantalla": "Modos Público / Planificador / Experto"},
])

# ---------------------------------------------------------------------------------------------- 2. cómo se calcula
st.header("2. Cómo se calcula")
# Solo se muestran valores que el código usa de verdad: constantes de lsi.contracts, kernels cargados (ctx.kernels), catálogo de
# paneles y las secciones horizon/visibility/timeline de config/. Las claves `frames`, `power.solar_constant_w_m2` y `time.utc_*`
# de simulation.json son informativas (el código no las lee) y por eso no se citan aquí.
hz, tl, vis = cfg["horizon"], cfg["timeline"], cfg["visibility"]
if state.is_public():
    st.markdown(
        "- **El terreno** viene de un mapa de alturas medido por láser desde un satélite. Desde tu punto miramos en todas "
        "las direcciones y anotamos la montaña más alta que tapa el cielo: eso es el horizonte.\n"
        "- **El Sol y la Tierra** se sitúan con las tablas de posiciones de la NASA, que saben dónde está cada astro en cada instante.\n"
        "- **Se ve o no se ve:** si el astro está más alto que el horizonte en esa dirección, se ve. Repetimos el cálculo "
        "cada pocos minutos y afinamos al segundo los momentos exactos en que aparece o desaparece.\n"
        "- **La potencia** es un porcentaje de lo que daría un panel de frente al Sol, no vatios de una misión real.\n"
        "- **El score** es una nota de 0 a 100 que castiga mucho que un aspecto importante sea malo (como una nota que no se compensa).")
elif not C.show_for("experto"):
    st.markdown(
        "1. Se lee el modelo digital de elevaciones (DEM) alrededor del punto y se calcula el perfil de horizonte "
        "H(azimut) en 360°, con la curvatura lunar incluida.\n"
        "2. SPICE da la dirección aparente del Sol y de la Tierra en el marco lunar del DEM; se convierte a azimut y elevación locales.\n"
        "3. Un cuerpo es visible si su elevación supera H en su azimut; se considera el disco (visible, parcial u oculto).\n"
        f"4. Se muestrea cada {num(tl['step_s'] / 60, 0, 'min')} y los cambios de estado se refinan hasta {num(tl['refine_xtol_s'], 0, 's')}.\n"
        "5. La potencia relativa combina ángulo de incidencia, distancia al Sol, temperatura y pérdidas declaradas.\n"
        "6. El score pondera subindicadores con puertas duras y muestra desglose, rango y confianza.")
else:
    st.markdown(
        f"- **Marcos:** `{SPICE_FRAME}` (DEM y SPICE coherentes con DE421); aberración `{SPICE_ABCORR}`; radio lunar de referencia "
        f"{num(MOON_RADIUS_KM, 1, 'km')}; tiempo UTC en la interfaz, ET (TDB) interno.\n"
        f"- **Horizonte:** rayos cada {num(hz['az_step_deg'], 2, '°')} de azimut y {num(hz['radial_step_m'], 0, 'm')} radiales hasta "
        f"{num(hz['r_max_m'] / 1000, 0, 'km')}; curvatura `{hz['curvature']}` (sin refracción: no hay atmósfera). Donde se agota el dato, "
        "la cota inferior se acompaña de una superior y el azimut se marca como limitado.\n"
        "- **Campo lejano:** el DEM de 5 m se completa con el polar LOLA de 80 m más allá de su recorte; el horizonte lejano es una estimación.\n"
        f"- **Disco finito:** el Sol (radio {num(SUN_RADIUS_KM, 0, 'km')}) y la Tierra se integran en {vis['n_slices']} franjas; "
        f"umbrales de disco visible Sol {num(vis['sun_f_thr'], 3)} y Tierra {num(vis['earth_f_thr'], 2)} (este último a calibrar).\n"
        f"- **Ventanas:** paso {num(tl['step_s'], 0, 's')} y bisección vectorizada con tolerancia {num(tl['refine_xtol_s'], 0, 's')}.\n"
        f"- **Potencia:** P_rel = IAM·cos θ·(S/S_ref)·f_T·pérdidas; constante solar {num(ctx.panels.solar_constant_w_m2, 0, 'W/m²')} (catálogo de paneles); "
        "montajes horizontal, inclinado y vertical; energía por trapecio sobre rejilla y eventos.\n"
        "- **Score:** media geométrica ponderada de subindicadores (Sol, noche, Tierra, terreno) con puertas duras; "
        f"confianza = mín(cobertura, soporte observacional, rango). Todos los umbrales y pesos están **por calibrar** con un experto.")

# ---- 2b. enlace con la Tierra: red de estaciones (cifras de config/ground_stations.json y simulation.json, no escritas a mano)
st.subheader("Tierra visible frente a enlace posible")
try:
    _gs = json.loads((cache.ROOT / "config" / "ground_stations.json").read_text(encoding="utf-8"))["stations"]
except (OSError, ValueError, KeyError):
    _gs = {}
_prof = cfg["score"]["profiles"]
_margins = sorted({float(v["link"]["min_earth_elevation_deg"]) for v in _prof.values() if v.get("link")})
_gaps = {k: v["link"]["max_gap_h"] for k, v in _prof.items() if v.get("link")}
st.markdown(
    "- **Tierra visible (geometría):** la Tierra está sobre el horizonte local del lander. No dice nada sobre poder comunicar.\n"
    "- **ENLACE POSIBLE:** la Tierra se ve con un **margen de elevación** sobre el horizonte del lander (margen de antena, por perfil: "
    f"{', '.join(num(m, 0, '°') for m in _margins)} por defecto, editable) **y** al menos una estación de la red ve la Luna por encima de su "
    "elevación mínima de recepción. Sigue siendo geometría: sin presupuesto de enlace, sin ocupación de la red ni máscara de terreno de la antena terrestre.\n"
    "- **Nota de Tierra (s_Tierra):** usa el ENLACE, no la Tierra visible. Es el producto de tres factores: la parte relativa mín(1, f_enlace / f_ref), con "
    "f_ref = Tierra sobre esfera lisa con el mismo margen y **sin** red; un factor de continuidad 2^(−hueco máximo / hueco tolerado por el perfil); y "
    "mín(1, horas de contacto por día / mínimo útil). Así un enlace del 62 % con un hueco de 127 h puntúa claramente por debajo de uno continuo. "
    "La forma funcional y los mínimos (2 h/día; 8 h/día en base ISRU) son suposiciones de diseño [sup]: el contacto mínimo útil vive en `config/panels.json` y el resto de parámetros en `config/simulation.json`. "
    "La red es un factor externo que penaliza igual a todos los sitios (una sola estación baja la nota; el DSN completo apenas).\n"
    "- **G6** (ventana de enlace continua mínima) y **G7 (hueco máximo sin enlace)** miden la ventana de misión sobre el enlace. G7 es blanda y su "
    "límite es un supuesto por perfil, no un dato publicado: " + ", ".join(f"{k} {num(v, 0, 'h')}" for k, v in _gaps.items()) + ".")
if _gs:
    rows = []
    for sid, d in _gs.items():
        pub = d.get("min_elevation_deg") is not None
        rows.append({"Estación": sid, "Nombre": d["name"], "Operador": d["operator"],
                     "Elevación mínima (°)": num(d["min_elevation_deg"] if pub else d.get("min_elevation_assumed_deg"), 1) + ("" if pub else " (supuesta)"),
                     "Verificada": "sí" if d.get("verified") else "no", "En la red por defecto": "sí" if d.get("default_enabled") else "no"})
    st.dataframe(rows, hide_index=True, width="stretch")
st.markdown(
    "**Redes.** **DSN** (DSS-14 Goldstone, DSS-63 Madrid, DSS-43 Canberra): coordenadas de DSN 810-005, módulo 301, Rev. P, Tabla 5, y elevación mínima de "
    "recepción de ese documento (§2.2.2 y §2.2.4); es la red por defecto. **ESTRACK** (New Norcia, Cebreros, Malargüe): posiciones de NAIF, pero la elevación "
    "mínima es un **supuesto a verificar** (no hay fuente oficial localizada), así que no es red por defecto. **NSN** (Near Space Network de NASA): "
    "**no incluida**, porque su ubicación y elevación no se han podido verificar en fuente oficial. Detalle y mediciones: `docs/science/luna-spice-sitios.md` §7.")
st.markdown(C.handoff_note())

# ---- 2c. paneles: nivel de evidencia (docs/validation/datos-paneles.md)
st.subheader("Paneles: nivel de evidencia")
_grp = pn.split_by_evidence_group(ctx.panels)
_resp, _exp = _grp["respaldado"], _grp["experimental_sin_datasheet"]
st.markdown(
    f"El catálogo separa **{len(_resp)} paneles respaldados** (η y γ_T leídos en datasheet o paper, o derivados de ellos con fórmula) de "
    f"**{len(_exp)} experimentales sin datasheet** ({', '.join(p.name for p in _exp)}), a los que les falta la eficiencia o el coeficiente de temperatura "
    "primarios. Los experimentales se muestran siempre, con su etiqueta y una banda de incertidumbre por sus parámetros con rango; no se mezclan con "
    "los respaldados. «Respaldado» describe la **celda de referencia** modelada, no una manta ni un array completo. La potencia absoluta en W/m² es la de "
    "celda en AM0 (η × 1361 W/m²), sin empaquetado. Fuente de cada cifra y página: `docs/validation/datos-paneles.md`.")

# ---------------------------------------------------------------------------------------------- 3. fuentes
st.header("3. Fuentes de datos")
n_gaz = _gazetteer_rows()
kernels = ", ".join(f"`{Path(k).name}`" for k in ctx.kernels.files)
st.markdown(
    "| Fuente | Qué aporta | Condiciones / observaciones |\n|---|---|---|\n"
    "| [LOLA / PGDA, producto 78](https://pgda.gsfc.nasa.gov/products/78) | DEM de 5 m/píxel de Site04 (Shackleton), Site11 (de Gerlache) "
    "y Site23 (Malapert), con pendiente, incertidumbre y conteos | Datos públicos de NASA Goddard; se descargan con `scripts/fetch_data.py`, no van al repositorio. "
    "La celda de 5 m no es resolución efectiva |\n"
    "| [LOLA polar 80 m, PGDA producto 90](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/) | Campo lejano 80°S–90°S a 80 m/píxel | Mismo CRS; "
    "difiere algo del DEM de 5 m (comprobado en el solape) |\n"
    f"| [NAIF SPICE](https://naif.jpl.nasa.gov/naif/) | Kernels: {kernels}; rango {ctx.kernels.utc_min[:4]}–{ctx.kernels.utc_max[:4]} | "
    "Datos públicos NAIF/JPL; versiones tal como figuran en `config/simulation.json` |\n"
    "| [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/) | Contraste independiente de azimut/elevación aparentes | Diferencia medida ≤ 0,05″ en elevación (DE421 frente a DE441) |\n"
    f"| [USGS Gazetteer of Planetary Nomenclature](https://planetarynames.wr.usgs.gov/) | Nombres de rasgos lunares para el buscador "
    f"({num(n_gaz, 0) if n_gaz else 'nº no disponible'} rasgos) | Nomenclatura IAU; coordenadas aproximadas, no de ingeniería |\n")
st.markdown(
    "**Referencias científicas.** Mazarico et al. (2011), *Icarus* 211, 1066–1081: iluminación del polo sur con LOLA. "
    "Barker et al. (2021), *Planetary and Space Science* 203: error de los mapas LOLA (cita como en el documento base; volumen y detalle **a verificar**). "
    "Porcentajes de iluminación por sitio de estas obras: **a verificar**.")
st.caption("Créditos: NASA (LOLA, PGDA, NAIF, Space Apps), USGS Astrogeology (Gazetteer), NASA/JPL (SPICE, Horizons). "
           "LSI no está afiliado ni respaldado por estas instituciones.")

# ---------------------------------------------------------------------------------------------- 4. limitaciones
st.header("4. Limitaciones")
eff = cfg["terrain"]["effective_resolution_m"]
st.markdown(
    "- **Visibilidad geométrica ≠ potencia ni enlace garantizados.** Ver el Sol o la Tierra no asegura energía suficiente ni comunicación de radio.\n"
    f"- **Resolución efectiva ≈ {num(eff, 0, 'm')}** (heurística de LSI, **a verificar**), no los 5 m nominales; la mayor parte de los píxeles del DEM son interpolados "
    "(proporción concreta **a verificar**).\n"
    "- **Un punto no es una zona.** El resultado vale para el punto y la altura elegidos; unos metros más allá puede cambiar mucho.\n"
    "- **Sin rocas, sin PSR detalladas, sin polvo detallado.** No se modelan eclipses lunares, obstáculos construidos ni geotecnia.\n"
    f"- **Paneles: {len(_exp)} experimentales sin datasheet.** Su eficiencia o coeficiente de temperatura no tiene fuente primaria; los demás conservan "
    "algunos parámetros térmicos y ópticos «a verificar». Cada uno declara su nivel de evidencia.\n"
    "- **Enlace posible ≠ enlace garantizado.** Sin presupuesto de enlace, ocupación de red, máscara de terreno de la antena terrestre ni refracción; "
    "las elevaciones mínimas de ESTRACK son supuestas y la NSN no está incluida.\n"
    "- **El score no certifica un sitio.** Sus pesos y umbrales están sin calibrar; sirve para comparar y entender, no para decidir.")
unver = [p.name for p in ctx.panels.panels if any(v == "a_verificar" for v in p.confidence.values())]
if unver:
    st.caption(f"Paneles del catálogo con algún parámetro «a verificar»: {len(unver)} de {len(ctx.panels.panels)}.")
with st.expander("Lista completa de avisos científicos"):
    for code, text in STANDARD_WARNINGS_ES.items():
        st.markdown(f"- {text}")

# ---------------------------------------------------------------------------------------------- 5. validación
st.header("5. Estado de validación")
n_files, n_tests = _count_tests()
c1, c2, c3 = st.columns(3)
with c1:
    C.metric_card("Ficheros de prueba", n_files, nd=0)
with c2:
    C.metric_card("Funciones de prueba", n_tests, nd=0, help="Contadas en `tests/` al abrir esta página (no ejecutadas aquí).")
with c3:
    C.metric_card("Contraste con Horizons", "≤ 0,05″", help="Diferencia máxima en elevación (0,04″ en azimut), medida en `docs/science/luna-spice-sitios.md`.")
st.markdown("Los casos de prueba usan valores esperados independientes (cálculos a mano, casos analíticos y Horizons). "
            "Que las pruebas pasen no convierte el modelo de potencia ni el score en datos de misión.")

# ---------------------------------------------------------------------------------------------- 6. glosario
st.header("6. Glosario")
C.glossary_expander()
with st.expander("Más términos"):
    st.markdown(
        "**Libración.** Pequeño balanceo aparente de la Luna que cambia qué lado y qué zonas polares vemos desde la Tierra; SPICE lo incluye.\n\n"
        "**PSR (región permanentemente sombreada).** Zona que nunca recibe luz solar directa; LSI no las modela en detalle.\n\n"
        "**LOLA.** Altímetro láser del orbitador LRO de NASA, fuente de los DEM.\n\n"
        "**SPICE.** Herramientas y datos de NASA/NAIF para posiciones y orientaciones de cuerpos del Sistema Solar.")

# ---------------------------------------------------------------------------------------------- 7. citar y créditos
st.header("7. Cómo citar y créditos")
st.code("Lunar Site Intelligence (LSI), 2026. Equipo LSI, NASA Space Apps Challenge 2026, "
        "«Lunar Landing Site Navigator». Documento base v1.0, 13/11/2026.", language="text")
st.markdown("**Equipo de agentes:** matemático (modelo geométrico y marcos), experto espacial (SPICE, paneles y misiones), "
            "geólogo (terreno, DEM y confianza) y experto en la Luna (sitios, nomenclatura y contexto científico).")
