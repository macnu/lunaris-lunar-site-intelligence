# Reto NASA Space Apps 2026 — Lunar Landing Site Navigator

Fuente: https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/ (leído el 14/11/2026 desde el navegador).
Dificultad: Advanced/Intermediate. Temas: Human Exploration, Moon, Software, Space Exploration.

## Enunciado
Crear una herramienta intuitiva que permita a planificadores de misión, educadores y público **comparar
sitios de aterrizaje y fechas** rápidamente, visualizando posiciones del Sol y la Tierra respecto al
horizonte para evaluar **potencial de generación de energía** y **ventanas de comunicación directa con la Tierra**.

## Objetivos sugeridos por el reto (el "Your solution may include")
1. Selección y comparación de sitios: lista curada (Apolo, CLPS, otras misiones comerciales, programas de otros países) **y coordenadas personalizadas**; comparación lado a lado o secuencial.
2. Fecha y hora flexibles; explorar días lunares/estaciones.
3. Visualización de Sol y Tierra respecto al horizonte; **tiempo restante hasta puesta de Sol / Earthset**.
4. Métricas de potencia y comunicación: **elevación solar**, duración de luz solar, ventanas de visibilidad de la Tierra.
5. Varias visualizaciones: mapas 2D, superficie 3D, etc.
6. Dinámica temporal: animaciones/timelines sobre un día lunar o varios.
7. Accesibilidad para distintos niveles (planificador técnico ↔ público/educación).

## Consideraciones técnicas del reto
- Efemérides: JPL Horizons o datasets precalculados (nosotros: SPICE + contraste con Horizons).
- Topografía LOLA para horizontes precisos.
- **Sin atmósfera**: horizonte = terreno + borde de la esfera lunar (curvatura). Sin refracción.
- Considerar **libración** y variaciones orbitales de la Luna.
- Polo sur: pendientes fuertes y cráteres profundos con sombras extremas.
- Comunicar claramente el tiempo hasta sunset/Earthset.

## Recursos de la pestaña "Resources"
- Quickmap (ASU LROC): https://quickmap.lroc.asu.edu/
- Moon Trek (NASA): https://trek.nasa.gov/moon/
- JPL Horizons: https://ssd.jpl.nasa.gov/horizons/
- CSA Moon Exploration: https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/
