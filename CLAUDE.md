# Lunar Site Intelligence (LSI)

App científica para el reto NASA Space Apps 2026 *Lunar Landing Site Navigator*. Compara emplazamientos
candidatos del polo sur lunar y fechas: horizonte topográfico, Sol/Tierra (SPICE), ventanas de
visibilidad, **potencia de paneles solares por tipo** y **score de calidad del emplazamiento**.

Documento base: `docs/documento-base.pdf` (Arquitectura y Plan v1.0). Reto: ver `docs/reto-nasa.md`.

## Reglas

- **Responder y documentar en español**, con acentos. Identificadores de código en inglés.
- **Corrección científica por encima de la brevedad.** Ponytail rige en la estructura (monolito modular,
  sin frameworks innecesarios), no en la física: nada de atajos en marcos de coordenadas.
- **Cifras nunca inventadas.** Todo parámetro físico lleva fuente o la etiqueta `a verificar`.
- **Honestidad del alcance:** visibilidad geométrica ≠ garantía de potencia ni de enlace RF. El modelo de
  potencia es una estimación con supuestos declarados.
- **Núcleo científico sin dependencias de UI** (`src/` no importa streamlit/plotly). Funciones deterministas.
- **Pruebas:** cada función con lógica deja un test en `tests/` (pytest) con valor esperado independiente.
- **Con varios agentes en paralelo:** cada agente escribe SOLO en los ficheros que le asigna el plan.
  Prohibido `git add -A`/`git add .`; añadir ficheros por nombre. El índice de git es compartido.
- **Datos:** `data/raw/` y `kernels/` no van a git (se reproducen con `python scripts/fetch_data.py`).
  Ningún repo remoto sin permiso del usuario.

## Convenciones físicas (fijadas; cambiarlas exige actualizar `docs/science/convenciones.md`)

- Azimut: desde el Norte local hacia el Este, sentido horario visto desde arriba, 0°–360°.
- Elevación: 0° = horizonte local plano, +90° = cenit.
- DEM: GeoTIFF polar estereográfico sur, metros, MOON_ME (DE421), píxel centrado, radio de referencia 1737.4 km.
- Tiempo: UTC en la interfaz, ET (TDB) interno en SPICE.

## Estructura

Ver `docs/plan/` (requisitos, arquitectura, tareas y dependencias). Entorno: Python 3.11, `pip install -r requirements.txt`.
