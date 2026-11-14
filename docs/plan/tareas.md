# LSI — EDT/WBS, plan de ejecución y control de calidad

Versión 1.0 · 14/11/2026 · Senior Project Manager. Fuente de datos estructurada: `docs/plan/tasks.json` (mismas tareas, mismos IDs). Requisitos: `docs/plan/requisitos.md`.

## 1. Resumen

- **80 tareas** en 7 fases; esfuerzo total **346 h** (estimación de esfuerzo-persona/agente, no tiempo de reloj).
- **Ruta crítica: 91 h** (19 tareas). Ventana del evento: sáb 14/11 09:00 → dom 15/11 23:59 Madrid = 39 h de reloj; el documento base presupone 24 h efectivas. La ruta crítica cabe en la ventana solo si las 19 olas se ejecutan en paralelo real y la ventana de correcciones no se agota; **riesgo de calendario R-01**.
- Hito 1 respetado: **ninguna tarea que escribe código de UI empieza antes de la puerta G1 (T-020)**. Solo `T-042` (UX) y `T-043` (diseño), que no son código científico ni de pantalla, pueden empezar antes.
- Regla de ficheros: dos tareas de la misma ola nunca comparten fichero (verificado por el comprobador, §9). Los ficheros compartidos (`requirements.txt`, `config/*`, `app.py`, `horizons_cases.json`, `horizon.py`, `cache.py`) solo los toca una cadena de tareas con dependencia explícita.
- Cada tarea implementada deja su test (`tests/`) con valor esperado independiente; los validadores (matemático, geólogo, expertos) aportan casos y revisiones en `docs/validation/`.
- El contrato de datos (`src/lsi/contracts.py`, incluida `GazetteerEntry`) y `docs/plan/arquitectura.md` son del Software Architect y **no están en este plan**: las tareas los consumen.

## 2. Convenciones

Roles: Backend Architect, AI Engineer, Data Engineer, Frontend Developer, UI Designer, UX Researcher, Technical Writer, Code Reviewer, API Tester, Evidence Collector, Reality Checker, Test Results Analyzer; validadores/consultores: `matematico`, `experto-proyectos-espaciales`, `geologo-planetario`, `experto-luna`. Estimaciones en horas con ±30 % de incertidumbre. «Holgura» = horas que puede retrasarse sin mover el fin del proyecto. Marcas: ★ = en la ruta crítica.

## 3. EDT / WBS por fase

### F0 — Entorno y datos (7 tareas, 20 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-001 ★ | Entorno Python 3.11, dependencias y paquete instalable | Data Engineer | 2 | — | 1 | 0 | RNF-04, RNF-09, RNF-13 |
| T-002 ★ | Smoke de entorno y fijado de versiones | Data Engineer | 2 | T-001 | 2 | 0 | RNF-04 |
| T-003 | Script de descarga reproducible con manifiesto y checksums | Data Engineer | 3 | T-001 | 2 | 67 | RF-02, RNF-04, RNF-13 |
| T-004 ★ | Cargador GeoTIFF y metadatos del DEM | Data Engineer | 4 | T-002 | 3 | 0 | RF-01, RF-04, RNF-11 |
| T-005 | Catálogo de sitios: corregir rutas y cargador | Data Engineer | 3 | T-001 | 2 | 45 | RF-15, RF-16 |
| T-006 | Revisión del catálogo de sitios por experto Luna | experto-luna | 3 | T-005 | 3 | 83 | RF-15, RNF-05 |
| T-007 | Hito H0: inspección e integridad de los datos reales | Data Engineer | 3 | T-004 | 4 | 69 | RF-01, RF-05, RNF-10 |

### F1 — Núcleo científico (19 tareas, 87 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-008 | Proyección estereográfica polar sur | Backend Architect | 4 | T-001 | 2 | 2 | RF-03, RNF-08 |
| T-009 ★ | Ventana, muestreo bilineal y máscara nodata | Data Engineer | 4 | T-004, T-008 | 4 | 0 | RF-04, RF-03 |
| T-010 | Pendiente y aptitud en disco r_pie | Data Engineer | 3 | T-009 | 5 | 21 | RF-05, RF-13 |
| T-011 ★ | Horizonte 360° con curvatura (núcleo) | Backend Architect | 8 | T-009 | 5 | 0 | RF-06, RNF-08, RNF-10 |
| T-012 | Horizonte truncado: estado ABIERTO/CERRADO y cota inferior | Backend Architect | 4 | T-011 | 6 | 11 | RF-07, RNF-05 |
| T-013 | Horizonte de esfera lisa y puntos fuera de DEM | Backend Architect | 3 | T-008 | 3 | 33 | RF-08, RF-16 |
| T-014 | Motor SPICE: kernels, rango y tiempos | Backend Architect | 4 | T-002 | 3 | 6 | RF-09, RNF-11 |
| T-015 | Coordenadas topocéntricas ENU y azimut/elevación | Backend Architect | 4 | T-001 | 2 | 8 | RF-09, RNF-08 |
| T-016 | Efemérides Sol/Tierra: az/el, distancia, tamaño angular | Backend Architect | 6 | T-015, T-014 | 4 | 6 | RF-09, RNF-03, RNF-08 |
| T-017 | Referencias JPL Horizons: script y casos fijos | Data Engineer | 3 | T-001 | 2 | 33 | RF-09, RNF-08, RNF-10 |
| T-018 | Test de contraste con Horizons (Sol y Tierra) | API Tester | 3 | T-016, T-017 | 5 | 24 | RF-09, RNF-08 |
| T-019 | HITO H1: coordenada real de extremo a extremo (Site04) | Backend Architect | 4 | T-016, T-012, T-011, T-018, T-010 | 7 | 17 | RF-03, RF-06, RF-09, RF-10 |
| T-020 | Puerta de calidad G1 (H1): revisión independiente | Reality Checker | 2 | T-019 | 8 | 17 | RNF-05, RNF-08 |
| T-021 ★ | Visibilidad geométrica y disco finito | Backend Architect | 6 | T-016, T-011 | 6 | 0 | RF-10, RF-11 |
| T-022 ★ | Ventanas temporales, refinamiento por raíz y eventos sunset/Earthset | Backend Architect | 9 | T-021 | 7 | 0 | RF-12, RF-14, RNF-03 |
| T-023 | Métricas de salida del documento base | Data Engineer | 4 | T-010, T-022 | 8 | 1 | RF-13, RF-14 |
| T-024 | Data Confidence (g90, e90, ABIERTO) | Data Engineer | 4 | T-009, T-012 | 7 | 12 | RF-31, RNF-05 |
| T-025 ★ | Escenarios de incertidumbre (cobertura, σz, discretización, clones) | Backend Architect | 7 | T-012, T-022 | 8 | 0 | RF-30, RF-34, RNF-05 |
| T-026 ★ | Orquestador de simulación, caché y metadatos | Backend Architect | 5 | T-024, T-023, T-013, T-022, T-025 | 9 | 0 | RF-16, RF-17, RNF-03, RNF-11 |

### F2 — Energía y paneles (10 tareas, 39 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-027 | Catálogo de paneles: verificar y completar | experto-proyectos-espaciales | 5 | T-001 | 2 | 27 | RF-18, RF-23, RNF-05 |
| T-028 | Cargador y validador de esquema de paneles | Backend Architect | 3 | T-027 | 3 | 27 | RF-18, RF-19 |
| T-029 | Ángulo de incidencia por montaje, IAM y distancia solar | Backend Architect | 5 | T-015 | 3 | 26 | RF-19, RF-20, RNF-08 |
| T-030 | Modelo térmico estacionario y f_T | Backend Architect | 4 | T-001 | 2 | 31 | RF-22, RNF-05 |
| T-031 | Potencia relativa P_rel por panel y montaje | Backend Architect | 6 | T-016, T-029, T-028, T-030 | 5 | 23 | RF-19, RF-20, RF-21, RF-23, RNF-08 |
| T-032 | Potencia con horizonte local (sombras y disco parcial) | Backend Architect | 4 | T-031, T-021 | 7 | 17 | RF-21, RF-11 |
| T-033 | Integrador de batería y % de carga | Backend Architect | 3 | T-032 | 8 | 17 | RF-24, RNF-08 |
| T-034 | Perfiles de misión y umbrales | experto-proyectos-espaciales | 3 | T-027 | 3 | 27 | RF-26, RNF-05 |
| T-035 | Cargador de perfiles y evaluación de umbrales | Backend Architect | 3 | T-034 | 4 | 27 | RF-26 |
| T-036 | Comparación de paneles y de sitios | Backend Architect | 3 | T-033, T-032 | 9 | 17 | RF-25 |

### F3 — Score y confianza (5 tareas, 26 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-037 | Score: subindicadores, gates, agregación geométrica y desglose explicable | AI Engineer | 9 | T-024, T-023, T-035 | 9 | 1 | RF-27, RF-28, RF-29, RF-32, RF-48, RNF-08 |
| T-038 | Score con rango [S_min, S_max] y etiqueta de confianza | AI Engineer | 4 | T-037, T-025 | 10 | 1 | RF-30, RF-31 |
| T-039 | Score ligado a la potencia efectiva del panel | AI Engineer | 3 | T-032, T-037 | 10 | 3 | RF-33, RF-20 |
| T-040 | Revisión geológica: terreno, confianza y horizonte | geologo-planetario | 6 | T-024, T-012, T-010 | 8 | 20 | RF-06, RF-07, RF-31, RNF-05 |
| T-041 | Calibración de umbrales y pesos del score | experto-proyectos-espaciales | 4 | T-039, T-040, T-037, T-038 | 11 | 2 | RF-27, RF-28, RF-29, RNF-05 |

### F4 — Interfaz de usuario (y buscador) (19 tareas, 89 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-042 | Investigación UX: personas, flujos y criterios de usabilidad | UX Researcher | 4 | — | 1 | 39 | RF-42, RNF-06 |
| T-043 | Sistema de diseño y paleta accesible | UI Designer | 4 | T-042 | 2 | 39 | RNF-06, RF-44 |
| T-044 ★ | Esqueleto de la app, navegación, estado e i18n | Frontend Developer | 7 | T-043, T-020, T-026 | 10 | 0 | RF-42, RNF-07, RNF-09 |
| T-045 | Validación de entradas: coordenadas y fechas | Data Engineer | 3 | T-020, T-008, T-005, T-014 | 9 | 21 | RF-16, RF-17 |
| T-046 | Componentes de selección de sitio, coordenadas y fecha | Frontend Developer | 4 | T-045, T-044 | 11 | 0 | RF-15, RF-16, RF-17 |
| T-047 ★ | Modos de usuario, glosario y avisos de alcance | Frontend Developer | 4 | T-044, T-042 | 11 | 0 | RF-42, RF-44, RNF-05 |
| T-048 | Visualización: terreno 3D y mapa 2D | Frontend Developer | 6 | T-009, T-043, T-020, T-010 | 9 | 23 | RF-35, RF-36, RF-05 |
| T-049 | Visualización: perfil de horizonte polar y cartesiano | Frontend Developer | 5 | T-043, T-020, T-012, T-021 | 9 | 24 | RF-37, RF-07, RNF-06 |
| T-050 | Visualización: timeline y curva de potencia | Frontend Developer | 5 | T-033, T-043, T-020, T-032, T-022 | 9 | 18 | RF-38, RF-21, RF-24, RF-14 |
| T-051 | Visualización: comparación, score y paneles | Frontend Developer | 5 | T-043, T-020, T-036, T-037, T-038 | 11 | 1 | RF-41, RF-25, RF-32 |
| T-052 | Exportación CSV/JSON | Data Engineer | 3 | T-037, T-026 | 10 | 7 | RF-43, RNF-11 |
| T-053 | Página Lunar Explorer (pantalla A) | Frontend Developer | 4 | T-047, T-046, T-048 | 12 | 1 | RF-35, RF-36, RF-44 |
| T-054 | Página Horizon & Visibility (pantalla B) | Frontend Developer | 4 | T-047, T-026, T-046, T-049 | 12 | 1 | RF-37, RF-44 |
| T-055 | Página Mission Timeline con animación (pantalla C) | Frontend Developer | 5 | T-047, T-046, T-050 | 12 | 0 | RF-38, RF-39, RF-14, RF-44 |
| T-056 | Página Paneles y potencia | Frontend Developer | 5 | T-047, T-028, T-046, T-051, T-050 | 12 | 0 | RF-40, RF-19, RF-20, RF-21, RF-23, RF-24, RF-25, RF-44 |
| T-057 ★ | Página Comparación y Score (pantalla D) | Frontend Developer | 5 | T-041, T-052, T-047, T-046, T-051 | 12 | 0 | RF-41, RF-29, RF-30, RF-31, RF-32, RF-43, RF-44 |
| T-058 | Gazetteer: descarga, carga, búsqueda difusa y sitio evaluable | Data Engineer | 9 | T-009, T-001, T-005 | 5 | 38 | RF-02, RF-16, RF-47, RF-48, RNF-10, RNF-13 |
| T-059 | Pantalla Buscador (ui/search.py) | Frontend Developer | 4 | T-020, T-058, T-047, T-044 | 12 | 1 | RF-47, RF-48, RF-44, RNF-06 |
| T-060 ★ | Integración final: app.py, caché y rendimiento percibido | Frontend Developer | 3 | T-057, T-053, T-054, T-056, T-055, T-059 | 13 | 0 | RNF-02, RF-35, RF-37, RF-38, RF-40, RF-41 |

### F5 — Validación (14 tareas, 63 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-061 | Revisión matemática independiente del núcleo, potencia y score | matematico | 6 | T-015, T-011, T-031, T-008, T-037, T-022, T-021 | 10 | 16 | RNF-08, RNF-10, RF-03, RF-06, RF-10, RF-12, RF-20, RF-29 |
| T-062 | Casos de validación del experto en la Luna | experto-luna | 5 | T-016, T-013, T-022 | 8 | 35 | RF-09, RF-12, RF-14, RNF-08 |
| T-063 | Contraste completo con Horizons y informe | API Tester | 4 | T-019, T-018 | 8 | 43 | RF-09, RNF-08, RNF-11 |
| T-064 | Regresión dorada de los tres sitios | Test Results Analyzer | 4 | T-037, T-026 | 10 | 23 | RNF-03, RF-13, RF-29, RNF-10 |
| T-065 ★ | Benchmarks de rendimiento | API Tester | 4 | T-032, T-026, T-060 | 14 | 0 | RNF-01, RNF-02, RNF-12 |
| T-066 ★ | Optimización condicional del rendimiento | Backend Architect | 5 | T-065 | 15 | 0 | RNF-01, RNF-02, RNF-03 |
| T-067 | Determinismo y reproducibilidad en entorno limpio | API Tester | 3 | T-002, T-003, T-026 | 10 | 25 | RNF-03, RNF-04 |
| T-068 | Pruebas E2E de la app (AppTest) | API Tester | 4 | T-060 | 14 | 5 | RF-35, RF-37, RF-38, RF-40, RF-41, RNF-10 |
| T-069 | QA visual y de accesibilidad con capturas | Evidence Collector | 5 | T-060 | 14 | 4 | RNF-06, RF-35, RF-36, RF-37, RF-38, RF-40, RF-41, RF-42 |
| T-070 | Revisión de código del núcleo y de la UI | Code Reviewer | 5 | T-061, T-060 | 14 | 4 | RNF-09, RNF-10, RNF-05 |
| T-071 | Revisión final por experto en proyectos espaciales: potencia y textos UI | experto-proyectos-espaciales | 4 | T-033, T-032, T-060 | 14 | 5 | RNF-05, RF-44, RF-20 |
| T-072 ★ | Ventana de correcciones tras revisiones (2–3 ciclos) | Frontend Developer | 8 | T-067, T-071, T-040, T-063, T-062, T-061, T-066, T-064, T-070, T-068, T-069 | 16 | 0 | RNF-10, RNF-05, RNF-08 |
| T-073 ★ | Informe consolidado de pruebas y cobertura | Test Results Analyzer | 3 | T-072 | 17 | 0 | RNF-10 |
| T-074 ★ | Puerta final G5: Reality Check | Reality Checker | 3 | T-073 | 18 | 0 | RNF-05, RNF-04 |

### F6 — Documentación y entrega (6 tareas, 22 h)

| ID | Tarea | Rol | h | Depende de | Ola | Holgura | Requisitos |
|---|---|---|---|---|---|---|---|
| T-075 | Documento de metodología | Technical Writer | 5 | T-012, T-032, T-037, T-022 | 10 | 32 | RF-44, RNF-05 |
| T-076 | Fuentes de datos, licencias y limitaciones conocidas | Technical Writer | 5 | T-041, T-007, T-003, T-012, T-032, T-027 | 12 | 24 | RF-44, RNF-05, RNF-13 |
| T-077 | Guion de demostración de 3 minutos | Technical Writer | 3 | T-071, T-060 | 15 | 13 | RF-44, RF-42 |
| T-078 | README del proyecto | Technical Writer | 4 | T-067, T-076, T-075, T-069 | 15 | 14 | RNF-04, RNF-05, RF-44 |
| T-079 | Capturas finales reales y guion de vídeo | Evidence Collector | 3 | T-077, T-072 | 17 | 3 | RF-44, RNF-05 |
| T-080 ★ | Checklist de entrega y envío | Reality Checker | 2 | T-067, T-078, T-074, T-079 | 19 | 0 | RNF-04, RNF-13, RNF-05 |

## 4. Fichas de tarea (descripción, ficheros exactos, aceptación)

### F0 — Entorno y datos

#### T-001 · Entorno Python 3.11, dependencias y paquete instalable ★

- **Rol:** Data Engineer · **Horas:** 2 · **Ola:** 1 · **Prioridad:** Must
- **Depende de:** —
- **Descripción:** Crea el esqueleto de paquetes (con `__init__.py`), pyproject y requirements con dependencias sin fijar versión todavía (se fijan en la tarea siguiente). No toca `contracts.py` ni `arquitectura.md`.
- **Ficheros que crea/modifica:** `requirements.txt`, `pyproject.toml`, `.gitignore`, `src/lsi/__init__.py`, `src/lsi/data/__init__.py`, `src/lsi/terrain/__init__.py`, `src/lsi/astronomy/__init__.py`, `src/lsi/simulation/__init__.py`, `src/lsi/energy/__init__.py`, `src/lsi/analysis/__init__.py`, `src/lsi/visualization/__init__.py`, `ui/__init__.py`, `ui/components/__init__.py`, `tests/conftest.py`
- **Criterio de aceptación:** En un venv limpio: `pip install -r requirements.txt && pip install -e .` termina sin error; `python -c "import lsi.data, lsi.terrain, lsi.astronomy, lsi.simulation, lsi.energy, lsi.analysis, lsi.visualization"` funciona; `pytest --collect-only` no falla; `.gitignore` excluye `data/raw/`, `data/processed/`, `kernels/`, `*.npy`.
- **Cubre:** RNF-04, RNF-09, RNF-13

#### T-002 · Smoke de entorno y fijado de versiones ★

- **Rol:** Data Engineer · **Horas:** 2 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Resuelve primero los conflictos de GDAL/rasterio en Windows (riesgo del documento base) y congela versiones.
- **Ficheros que crea/modifica:** `requirements.txt`, `scripts/check_env.py`, `tests/test_environment.py`
- **Criterio de aceptación:** `python scripts/check_env.py` imprime versiones de rasterio, pyproj, spiceypy, numpy, scipy, plotly, streamlit; carga los 6 kernels sin error; lee un GeoTIFF de `data/raw/`; `requirements.txt` queda con versiones `==` probadas; `tests/test_environment.py` pasa.
- **Cubre:** RNF-04

#### T-003 · Script de descarga reproducible con manifiesto y checksums

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Extiende el `fetch_data.py` existente con manifiesto, verificación y modo sin red. Registra la procedencia de cada fichero.
- **Ficheros que crea/modifica:** `scripts/fetch_data.py`, `config/data_manifest.json`, `tests/test_fetch_manifest.py`
- **Criterio de aceptación:** `python scripts/fetch_data.py --verify` informa OK para los 12 GeoTIFF y 6 kernels existentes comparando SHA-256 con el manifiesto; es idempotente (no re-descarga lo válido); con `--offline` no falla y lista lo ausente; el manifiesto registra URL de origen y fecha.
- **Cubre:** RF-02, RNF-04, RNF-13

#### T-004 · Cargador GeoTIFF y metadatos del DEM ★

- **Rol:** Data Engineer · **Horas:** 4 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-002 (envcheck)
- **Descripción:** No compara `crs == crs` (nombres distintos en Malapert `toterr`); compara parámetros de proyección.
- **Ficheros que crea/modifica:** `src/lsi/data/loader.py`, `src/lsi/data/metadata.py`, `tests/test_loader.py`
- **Criterio de aceptación:** `load_layer(site, 'surf'|'slp'|'ldec'|'toterr')` devuelve array, transform, CRS, nodata y unidades; las 4 capas comparten malla y forma; `transform*(col+0.5,fila+0.5)` en el píxel del polo de Shackleton (fila 200, col 1800) da (0,0) ± 2,5 m; los metadatos incluyen fuente y referencia MOON_ME/DE421.
- **Cubre:** RF-01, RF-04, RNF-11

#### T-005 · Catálogo de sitios: corregir rutas y cargador

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Corrige una discrepancia real detectada entre `sites.json` y la estructura de `data/raw/`.
- **Ficheros que crea/modifica:** `config/sites.json`, `src/lsi/data/sites.py`, `tests/test_sites.py`
- **Criterio de aceptación:** `dem_dir` de los 3 sitios apunta a `data/raw/shackleton|de_gerlache|malapert` (el JSON actual apunta a `data/raw/dem/siteNN`, que no existe); se cargan las 32 entradas; las de lat/lon `null` no son seleccionables; lon oeste-positiva se convierte a este-positiva; test con valor esperado independiente para 3 sitios.
- **Cubre:** RF-15, RF-16

#### T-006 · Revisión del catálogo de sitios por experto Luna

- **Rol:** experto-luna · **Horas:** 3 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-005 (sites)
- **Descripción:** Consultor/validador: el fichero de configuración lo edita el responsable de la tarea predecesora para evitar escrituras concurrentes.
- **Ficheros que crea/modifica:** `docs/validation/rev-catalogo.md`
- **Criterio de aceptación:** Informe con la comprobación de coordenadas de cada misión (fuente, marco, lon E/O), corrección de entradas dudosas (p. ej. IM-1) y marca `aprox` o `verificado`; cualquier corrección se aplica a `config/sites.json` mediante PR al responsable de T-sites.
- **Cubre:** RF-15, RNF-05

#### T-007 · Hito H0: inspección e integridad de los datos reales

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 4 · **Prioridad:** Must
- **Depende de:** T-004 (loader)
- **Descripción:** Cierra el hito H0 del documento base (datos descargados, metadatos y CRS documentados).
- **Ficheros que crea/modifica:** `scripts/inspect_dem.py`, `tests/test_data_integrity.py`, `docs/validation/hito0-datos.md`
- **Criterio de aceptación:** Reproduce las cifras del geólogo: `ldec = 0` en 90–92 % de píxeles; distancia a observación p90 15–16 m; 4 capas con la misma malla y 0 NaN; `slp` frente a diferencia central de 10 m con RMSE < 0,01°; informe H0 con CRS, extensión y estadísticos por sitio.
- **Cubre:** RF-01, RF-05, RNF-10

### F1 — Núcleo científico

#### T-008 · Proyección estereográfica polar sur

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Implementa la proyección a medida (esfera R=1737400 m, lat_ts=−90) y su equivalente pyproj.
- **Ficheros que crea/modifica:** `src/lsi/terrain/projection.py`, `tests/test_projection.py`
- **Criterio de aceptación:** Casos de Mat. §1.5: directa vs fórmula/pyproj ≤ 1e-6 m; ida y vuelta lat/lon ≤ 1e-9°; píxel↔x,y exacto en enteros; `always_xy=True`; error claro fuera del hemisferio sur.
- **Cubre:** RF-03, RNF-08

#### T-009 · Ventana, muestreo bilineal y máscara nodata ★

- **Rol:** Data Engineer · **Horas:** 4 · **Ola:** 4 · **Prioridad:** Must
- **Depende de:** T-004 (loader), T-008 (proj)
- **Descripción:** Es la base de horizonte, pendiente y confianza.
- **Ficheros que crea/modifica:** `src/lsi/terrain/dem.py`, `tests/test_dem.py`
- **Criterio de aceptación:** Bilineal en el centro de píxel = valor del píxel a 1e-6 m; punto fuera de cobertura devuelve estado explícito (no 0 ni montaña); distancia al borde del DEM por azimut calculada; recorte alrededor de un punto con radio configurable.
- **Cubre:** RF-04, RF-03

#### T-010 · Pendiente y aptitud en disco r_pie

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 5 · **Prioridad:** Must
- **Depende de:** T-009 (dem)
- **Descripción:** No evalúa la pendiente al píxel de 5 m (contiene interpolación); la evalúa a escala del vehículo.
- **Ficheros que crea/modifica:** `src/lsi/terrain/slope.py`, `tests/test_slope.py`
- **Criterio de aceptación:** Pendiente por diferencia central (baseline 10 m) reproduce `slp` con RMSE < 0,01°; percentil 90 de pendiente en disco de 50 m; Terrain Slope listo para el score.
- **Cubre:** RF-05, RF-13

#### T-011 · Horizonte 360° con curvatura (núcleo) ★

- **Rol:** Backend Architect · **Horas:** 8 · **Ola:** 5 · **Prioridad:** Must
- **Depende de:** T-009 (dem)
- **Descripción:** Muestreo radial uniforme a 5 m (no adaptativo), vectorizado con NumPy; usa la fórmula exacta con curvatura, no `atan2(z−z0, r)`.
- **Ficheros que crea/modifica:** `src/lsi/terrain/horizon.py`, `tests/test_horizon.py`
- **Criterio de aceptación:** Terreno plano: elevación = −D/(2R) en grados (−0,0165° a 1 km) con error ≤ 1e-4°; cresta sintética en un azimut: pico solo en ese sector; nodata no es obstáculo; casos H1–H5 de Mat. §2.3 ≤ 1e-4°; ΔA 0,125° vs 0,25° ≤ 0,06° en DEM real; altura de observador 1/2/5 m y radio configurables.
- **Cubre:** RF-06, RNF-08, RNF-10

#### T-012 · Horizonte truncado: estado ABIERTO/CERRADO y cota inferior

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 6 · **Prioridad:** Must
- **Depende de:** T-011 (horizon)
- **Descripción:** Implementa la señalización de truncado propuesta por el geólogo (§6.2).
- **Ficheros que crea/modifica:** `src/lsi/terrain/horizon_coverage.py`, `tests/test_horizon_coverage.py`
- **Criterio de aceptación:** DEM sintético con pared en el borde → azimut ABIERTO; desde el centro de Shackleton ≈ 41,9 % de azimuts ABIERTOS (± 2 pp); devuelve fracción abierta, distancia mínima/mediana al borde y marca `cota_inferior`.
- **Cubre:** RF-07, RNF-05

#### T-013 · Horizonte de esfera lisa y puntos fuera de DEM

- **Rol:** Backend Architect · **Horas:** 3 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-008 (proj)
- **Descripción:** Permite coordenadas personalizadas fuera de los 3 DEM y calcular la fracción de Tierra sobre horizonte liso para normalizar `s_tierra`.
- **Ficheros que crea/modifica:** `src/lsi/terrain/sphere_horizon.py`, `tests/test_sphere_horizon.py`
- **Criterio de aceptación:** Observador a h m sobre esfera lisa: elevación del horizonte = −acos(R/(R+h)) con error ≤ 1e-6°; devuelve siempre la etiqueta `modo=esfera_lisa`; coincide con `horizon.py` sobre un DEM plano (test cruzado cuando exista T-horizon).
- **Cubre:** RF-08, RF-16

#### T-014 · Motor SPICE: kernels, rango y tiempos

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-002 (envcheck)
- **Descripción:** Ningún cálculo con MOON_PA ni IAU_MOON: el marco de trabajo es MOON_ME (riesgo nº 1).
- **Ficheros que crea/modifica:** `src/lsi/astronomy/spice_engine.py`, `tests/test_spice_engine.py`
- **Criterio de aceptación:** Carga idempotente de los 6 kernels desde `kernels/`; UTC→ET con `str2et`; fecha fuera de 1900–2050 lanza excepción propia con mensaje claro; MOON_ME vs MOON_PA = 103,85″ ± 0,5″; devuelve versión/lista de kernels para metadatos.
- **Cubre:** RF-09, RNF-11

#### T-015 · Coordenadas topocéntricas ENU y azimut/elevación

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Función pura vectorial; sin dependencia de SPICE.
- **Ficheros que crea/modifica:** `src/lsi/astronomy/coordinates.py`, `tests/test_coordinates.py`
- **Criterio de aceptación:** Base ENU ortonormal ≤ 1e-12; casos de Mat. §3.2 sin SPICE; azimut N→E horario 0–360°; elevación asin(U/|v|); signo de λ comprobado con casos Este/Oeste.
- **Cubre:** RF-09, RNF-08

#### T-016 · Efemérides Sol/Tierra: az/el, distancia, tamaño angular

- **Rol:** Backend Architect · **Horas:** 6 · **Ola:** 4 · **Prioridad:** Must
- **Depende de:** T-015 (coords), T-014 (spice)
- **Descripción:** Series vectorizadas para rejillas de tiempo; paralaje de la Tierra incluido.
- **Ficheros que crea/modifica:** `src/lsi/astronomy/ephemeris.py`, `tests/test_ephemeris.py`
- **Criterio de aceptación:** Regresión Mat. §3.3 `[SPICE-reg]`; Sol a −89,9° con elevación −1,625°…+1,627° ± 0,01°; tamaño angular Sol 0,5228–0,5434° ± 0,0005°; LT+S vs NONE ≈ 20,3″ ± 1″; continuidad entre instantes; observador con `spkcpo` y `georec`.
- **Cubre:** RF-09, RNF-03, RNF-08

#### T-017 · Referencias JPL Horizons: script y casos fijos

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Los tests nunca usan la red: leen el JSON versionado.
- **Ficheros que crea/modifica:** `scripts/fetch_horizons.py`, `tests/data/horizons_cases.json`
- **Criterio de aceptación:** Los 24 casos de `luna-spice-sitios.md` §2 quedan en JSON con az/el/rango/instante/sitio; `fetch_horizons.py` documenta parámetros (`CENTER=coord@301`, `APPARENT=AIRLESS`, `QUANTITIES=4,20`) y falla con mensaje claro sin red.
- **Cubre:** RF-09, RNF-08, RNF-10

#### T-018 · Test de contraste con Horizons (Sol y Tierra)

- **Rol:** API Tester · **Horas:** 3 · **Ola:** 5 · **Prioridad:** Must
- **Depende de:** T-016 (ephem), T-017 (hzcases)
- **Descripción:** Primer contraste independiente de la cadena de marcos.
- **Ficheros que crea/modifica:** `tests/test_validation_horizons.py`
- **Criterio de aceptación:** Sol: error az/el ≤ 0,01° (aceptable 0,02°); Tierra ≤ 0,02° (0,05°); distancias ≤ 1e-5 relativa; para elevación > 80° se admite 0,02°; el test falla con mensaje que sugiere signo de λ o paralaje.
- **Cubre:** RF-09, RNF-08

#### T-019 · HITO H1: coordenada real de extremo a extremo (Site04)

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 7 · **Prioridad:** Must
- **Depende de:** T-016 (ephem), T-012 (hcover), T-011 (horizon), T-018 (hzval), T-010 (slope)
- **Descripción:** Cumple la regla de ejecución del documento base: validar UNA coordenada real antes de construir pantallas.
- **Ficheros que crea/modifica:** `scripts/validate_h1_site04.py`, `docs/validation/hito1-site04.md`
- **Criterio de aceptación:** Un solo script lee el DEM de Shackleton, convierte el punto, calcula horizonte y az/el de Sol y Tierra para ≥ 5 instantes y contrasta con Horizons; informe con CRS, kernels, marcos, tabla de errores y decisión GO/NO-GO para empezar la UI.
- **Cubre:** RF-03, RF-06, RF-09, RF-10

#### T-020 · Puerta de calidad G1 (H1): revisión independiente

- **Rol:** Reality Checker · **Horas:** 2 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-019 (h1)
- **Descripción:** Por defecto NEEDS WORK hasta ver pruebas.
- **Ficheros que crea/modifica:** `docs/validation/gate-h1.md`
- **Criterio de aceptación:** Veredicto GO / NEEDS WORK con evidencias reproducibles (comandos y salidas); toda tarea de F4 que escribe código de UI depende de este GO.
- **Cubre:** RNF-05, RNF-08

#### T-021 · Visibilidad geométrica y disco finito ★

- **Rol:** Backend Architect · **Horas:** 6 · **Ola:** 6 · **Prioridad:** Must
- **Depende de:** T-016 (ephem), T-011 (horizon)
- **Descripción:** Modelo `geometric_center` por defecto y `disc` opcional.
- **Ficheros que crea/modifica:** `src/lsi/simulation/visibility.py`, `tests/test_visibility.py`
- **Criterio de aceptación:** Cuerpo sobre/bajo horizonte → visible/oculto; fracción visible de disco plano vs analítico ≤ 1e-4 (n=64); pared inclinada por el centro = 0,5 ± 1e-6; clasificación completo/parcial/oculto; interpolación de H en el azimut del cuerpo; zonas ABIERTO marcan «cota superior de iluminación».
- **Cubre:** RF-10, RF-11

#### T-022 · Ventanas temporales, refinamiento por raíz y eventos sunset/Earthset ★

- **Rol:** Backend Architect · **Horas:** 9 · **Ola:** 7 · **Prioridad:** Must
- **Depende de:** T-021 (vis)
- **Descripción:** Serie sintética que cruza el horizonte (prueba obligatoria del documento base).
- **Ficheros que crea/modifica:** `src/lsi/simulation/timeline.py`, `src/lsi/simulation/events.py`, `tests/test_timeline.py`, `tests/test_events.py`
- **Criterio de aceptación:** Paso 5 vs 10 min: mismo conjunto de ventanas ± 2 s; eventos vs analítico ≤ 1 s; duración vs fuerza bruta a 1 min ≤ 2 min; álgebra de solape Sol∩Tierra; `next_event(t)` devuelve tiempo restante hasta sunset/Earthset/sunrise/Earthrise y los casos «siempre visible», «siempre oculto», «ya oculto».
- **Cubre:** RF-12, RF-14, RNF-03

#### T-023 · Métricas de salida del documento base

- **Rol:** Data Engineer · **Horas:** 4 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-010 (slope), T-022 (timeline)
- **Descripción:** Cada métrica por separado, sin ranking.
- **Ficheros que crea/modifica:** `src/lsi/analysis/metrics.py`, `tests/test_metrics.py`
- **Criterio de aceptación:** Calcula Solar Visibility, Longest Solar Window, Max Darkness, Earth Visibility, Longest Earth Window, Overlap, Terrain Slope, elevación solar mín/máx y duración de luz; casos sintéticos con resultado calculado a mano; salida en h:min y %.
- **Cubre:** RF-13, RF-14

#### T-024 · Data Confidence (g90, e90, ABIERTO)

- **Rol:** Data Engineer · **Horas:** 4 · **Ola:** 7 · **Prioridad:** Must
- **Depende de:** T-009 (dem), T-012 (hcover)
- **Descripción:** toterr no se usa sola como confianza.
- **Ficheros que crea/modifica:** `src/lsi/analysis/confidence.py`, `tests/test_confidence.py`
- **Criterio de aceptación:** Clases ALTA/MEDIA/BAJA y valor continuo DC de Geo. §2.3; la calibración sobre rejilla de 100 m reproduce %ALTA de Shackleton 34,9 / de Gerlache 40,7 / Malapert 19,0 (± 1 pp); prueba negativa: g90 > 25 m nunca sale ALTA; resta un nivel si ABIERTO > 10 %; muestra «resolución efectiva ≈ 30 m».
- **Cubre:** RF-31, RNF-05

#### T-025 · Escenarios de incertidumbre (cobertura, σz, discretización, clones) ★

- **Rol:** Backend Architect · **Horas:** 7 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-012 (hcover), T-022 (timeline)
- **Descripción:** Los clones son opcionales: la parte Could no bloquea nada aguas abajo.
- **Ficheros que crea/modifica:** `src/lsi/simulation/uncertainty.py`, `src/lsi/simulation/clones.py`, `tests/test_uncertainty.py`, `tests/test_clones.py`
- **Criterio de aceptación:** Devuelve escenarios nominal/pesimista/optimista con H_ub ≥ H_lb; perturbación σz con k=1; marca como «incierto» el azimut cuya dispersión supera 0,27°; con clones (si existen) K ≥ 5 y percentiles P5–P95, y sin clones degrada con aviso (Could).
- **Cubre:** RF-30, RF-34, RNF-05

#### T-026 · Orquestador de simulación, caché y metadatos ★

- **Rol:** Backend Architect · **Horas:** 5 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-024 (conf), T-023 (metrics), T-013 (sphere), T-022 (timeline), T-025 (unc)
- **Descripción:** Punto de entrada único del núcleo para la UI; no importa streamlit.
- **Ficheros que crea/modifica:** `src/lsi/simulation/runner.py`, `src/lsi/simulation/cache.py`, `config/simulation.json`, `tests/test_runner.py`
- **Criterio de aceptación:** `run(site|punto, t0, t1, config)` devuelve horizonte, series, ventanas y métricas con metadatos (kernels, DEM, marco, parámetros, modo); segunda llamada idéntica sale de caché con resultado igual; punto sin DEM usa esfera lisa etiquetada; fecha fuera de rango → error claro.
- **Cubre:** RF-16, RF-17, RNF-03, RNF-11

### F2 — Energía y paneles

#### T-027 · Catálogo de paneles: verificar y completar

- **Rol:** experto-proyectos-espaciales · **Horas:** 5 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Parámetros a verificar según el experto: IAM, emisividades, eficiencia de celdas de VSAT/ROSA/CIGS/perovskita, polvo.
- **Ficheros que crea/modifica:** `config/panels.json`, `docs/validation/rev-paneles.md`
- **Criterio de aceptación:** ≥ 6 tipos con montaje permitido; cada parámetro con `confidence` ∈ {publicado, estimado, suposicion, a_verificar} y fuente; ningún valor sin fuente ni etiqueta; informe con lo verificado, lo no encontrado y la lista «qué decir / qué NO decir».
- **Cubre:** RF-18, RF-23, RNF-05

#### T-028 · Cargador y validador de esquema de paneles

- **Rol:** Backend Architect · **Horas:** 3 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-027 (panelcfg)
- **Descripción:** Validación en la frontera de confianza (fichero de configuración editable).
- **Ficheros que crea/modifica:** `src/lsi/energy/panels.py`, `tests/test_panels.py`
- **Criterio de aceptación:** Carga `panels.json`; rechaza entradas con parámetro sin `confidence`; `get(id)` y listado ≥ 6; expone `confidence` para que la UI la muestre; test con JSON roto.
- **Cubre:** RF-18, RF-19

#### T-029 · Ángulo de incidencia por montaje, IAM y distancia solar

- **Rol:** Backend Architect · **Horas:** 5 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-015 (coords)
- **Descripción:** Panel horizontal en el polo da < 1 %; el montaje vertical con seguimiento es la cota superior.
- **Ficheros que crea/modifica:** `src/lsi/energy/incidence.py`, `src/lsi/energy/iam.py`, `tests/test_incidence.py`, `tests/test_iam.py`
- **Criterio de aceptación:** cos θ para horizontal, inclinado, vertical fijo y vertical con seguimiento; casos Mat. §6.7 con ≤ 1e-4; recorte a ≥ 0; IAM coseno puro y opción Fresnel; factor S(d)/S_ref con 1361 W/m² y distancia SPICE.
- **Cubre:** RF-19, RF-20, RNF-08

#### T-030 · Modelo térmico estacionario y f_T

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-001 (env)
- **Descripción:** Cota inferior de T para paneles casi horizontales; limitación declarada.
- **Ficheros que crea/modifica:** `src/lsi/energy/thermal.py`, `tests/test_thermal.py`
- **Criterio de aceptación:** Balance (α − η)·G = σT⁴(ε_f + ε_b) con sumidero 3 K; f_T = 1 + k(T − T_ref) con tope 1,15; aviso fuera de `valid_range_C`; casos de Mat. §6.5.
- **Cubre:** RF-22, RNF-05

#### T-031 · Potencia relativa P_rel por panel y montaje

- **Rol:** Backend Architect · **Horas:** 6 · **Ola:** 5 · **Prioridad:** Must
- **Depende de:** T-016 (ephem), T-029 (incid), T-028 (panels), T-030 (thermal)
- **Descripción:** Serie temporal por panel; el resultado lleva la lista de supuestos y confianzas.
- **Ficheros que crea/modifica:** `src/lsi/energy/power.py`, `tests/test_power.py`
- **Criterio de aceptación:** Aplica P_rel = IAM·cosθ·(S/S_ref)·f_T·f_rad·f_polvo·f_sombra para uno o varios paneles a la vez; casos Mat. §6.7 ≤ 1e-4 absoluto; horizontal < 1 % en el polo; vertical con seguimiento = cos(h); polvo y radiación editables.
- **Cubre:** RF-19, RF-20, RF-21, RF-23, RNF-08

#### T-032 · Potencia con horizonte local (sombras y disco parcial)

- **Rol:** Backend Architect · **Horas:** 4 · **Ola:** 7 · **Prioridad:** Must
- **Depende de:** T-031 (power), T-021 (vis)
- **Descripción:** Une visibilidad con potencia sin mezclar sus supuestos.
- **Ficheros que crea/modifica:** `src/lsi/energy/illumination.py`, `tests/test_illumination.py`
- **Criterio de aceptación:** P = 0 con el Sol oculto; fracción de disco visible escala la potencia; integración por eventos vs rejilla de 1 min ≤ 0,5 %; energía relativa acumulada por día.
- **Cubre:** RF-21, RF-11

#### T-033 · Integrador de batería y % de carga

- **Rol:** Backend Architect · **Horas:** 3 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-032 (illum)
- **Descripción:** Responde a «% de potencia/carga en cada momento del día».
- **Ficheros que crea/modifica:** `src/lsi/energy/battery.py`, `tests/test_battery.py`
- **Criterio de aceptación:** Caso Mat. §6.8 con error ≤ 0,1 Wh; carga siempre en 0–100 %; capacidad, consumo y profundidad de descarga configurables; indica horas hasta agotamiento.
- **Cubre:** RF-24, RNF-08

#### T-034 · Perfiles de misión y umbrales

- **Rol:** experto-proyectos-espaciales · **Horas:** 3 · **Ola:** 3 · **Prioridad:** Must
- **Depende de:** T-027 (panelcfg)
- **Descripción:** Alimenta score y paneles.
- **Ficheros que crea/modifica:** `config/mission_profiles.json`, `docs/validation/rev-perfiles.md`
- **Criterio de aceptación:** Perfiles lander solar, lander con baterías, rover, base/ISRU y comunicaciones con potencia mínima, noche máxima, ventana de Tierra mínima y pendiente máxima; cada umbral con confianza (p. ej. 12 h estimado, 36 h suposición).
- **Cubre:** RF-26, RNF-05

#### T-035 · Cargador de perfiles y evaluación de umbrales

- **Rol:** Backend Architect · **Horas:** 3 · **Ola:** 4 · **Prioridad:** Must
- **Depende de:** T-034 (profcfg)
- **Descripción:** Código sin lógica de UI.
- **Ficheros que crea/modifica:** `src/lsi/energy/profiles.py`, `tests/test_profiles.py`
- **Criterio de aceptación:** Carga perfiles, valida esquema y evalúa un resultado contra umbrales (cumple/incumple con motivo); umbrales sobrescribibles desde la UI; test con perfil inválido.
- **Cubre:** RF-26

#### T-036 · Comparación de paneles y de sitios

- **Rol:** Backend Architect · **Horas:** 3 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-033 (battery), T-032 (illum)
- **Descripción:** Base de la pantalla de paneles y de la comparación.
- **Ficheros que crea/modifica:** `src/lsi/analysis/panel_compare.py`, `tests/test_panel_compare.py`
- **Criterio de aceptación:** Dado un conjunto de paneles y sitios devuelve tabla con potencia media, energía relativa, horas sobre umbral y hora de agotamiento; orden estable; test con caso sintético de 2 paneles × 2 sitios.
- **Cubre:** RF-25

### F3 — Score y confianza

#### T-037 · Score: subindicadores, gates, agregación geométrica y desglose explicable

- **Rol:** AI Engineer · **Horas:** 9 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-024 (conf), T-023 (metrics), T-035 (profiles)
- **Descripción:** Media geométrica ponderada no compensatoria; todas las constantes son configuración. Transparencia: sin ranking opaco.
- **Ficheros que crea/modifica:** `src/lsi/analysis/ranking.py`, `config/score.yaml`, `tests/test_ranking.py`, `src/lsi/analysis/explain.py`, `tests/test_explain.py`
- **Criterio de aceptación:** Ejemplo Mat. §7.7: lander_solar = 67,9 (± 0,05), rover 70,2, comunicaciones 76,7; s_i ≡ 1 → 100; s_i = 0 → 100·ε^w; reordenar indicadores no cambia S; gates producen estado y motivo sin anular el score; parámetros leídos de `score.yaml`; si el resultado viene de modo esfera lisa el score lleva la etiqueta «sin datos de terreno» y el gate G3 se activa. En el ejemplo §7.7 el eslabón débil es `s_noche` (55,9 %); «S si s_noche = 1» = 84,3; la tabla incluye valor medido, s_i, peso, contribución y gates; lista de supuestos incluida.
- **Cubre:** RF-27, RF-28, RF-29, RF-32, RF-48, RNF-08

#### T-038 · Score con rango [S_min, S_max] y etiqueta de confianza

- **Rol:** AI Engineer · **Horas:** 4 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-037 (rank), T-025 (unc)
- **Descripción:** La confianza no multiplica a S.
- **Ficheros que crea/modifica:** `src/lsi/analysis/score_range.py`, `tests/test_score_range.py`
- **Criterio de aceptación:** Ejemplo de Mat. §7.7 devuelve «68 (61–74)»; C = min(c_cov, c_sup, c_rango) con etiqueta alta/media/baja; el rango usa los escenarios de T-unc.
- **Cubre:** RF-30, RF-31

#### T-039 · Score ligado a la potencia efectiva del panel

- **Rol:** AI Engineer · **Horas:** 3 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-032 (illum), T-037 (rank)
- **Descripción:** Une las dos funcionalidades nuevas del usuario.
- **Ficheros que crea/modifica:** `src/lsi/analysis/solar_effective.py`, `tests/test_solar_effective.py`
- **Criterio de aceptación:** f_sol efectiva = fracción de tiempo con P_rel ≥ umbral del perfil; cambiar de panel cambia s_sol de forma monótona; el modo «geométrico» sigue disponible y se etiqueta.
- **Cubre:** RF-33, RF-20

#### T-040 · Revisión geológica: terreno, confianza y horizonte

- **Rol:** geologo-planetario · **Horas:** 6 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-024 (conf), T-012 (hcover), T-010 (slope)
- **Descripción:** Valida desde la geología lo que el matemático validó desde el cálculo.
- **Ficheros que crea/modifica:** `docs/validation/rev-geologo.md`, `tests/test_horizon_los.py`
- **Criterio de aceptación:** Horizonte vs segundo algoritmo de línea de vista en 5 puntos reales con diferencia < 0,1°; sensibilidad a altura de observador 0/2/10 m y DEM 20 m; fracción de azimuts que cambian > 0,25° al recortar a la mitad; pruebas negativas (interior de Shackleton no es «buen sitio solar»).
- **Cubre:** RF-06, RF-07, RF-31, RNF-05

#### T-041 · Calibración de umbrales y pesos del score

- **Rol:** experto-proyectos-espaciales · **Horas:** 4 · **Ola:** 11 · **Prioridad:** Must
- **Depende de:** T-039 (effsol), T-040 (georev), T-037 (rank), T-038 (scrange)
- **Descripción:** Mat. §9.3: los umbrales requieren experto de misión.
- **Ficheros que crea/modifica:** `config/score.yaml`, `docs/validation/calibracion-score.md`
- **Criterio de aceptación:** Cada umbral y peso con justificación o etiqueta `a calibrar`; los 3 sitios con perfil lander_solar dan resultados defendibles (el interior de Shackleton no puntúa como buen sitio solar); informe de lo que sigue sin calibrar.
- **Cubre:** RF-27, RF-28, RF-29, RNF-05

### F4 — Interfaz de usuario (y buscador)

#### T-042 · Investigación UX: personas, flujos y criterios de usabilidad

- **Rol:** UX Researcher · **Horas:** 4 · **Ola:** 1 · **Prioridad:** Must
- **Depende de:** —
- **Descripción:** Puede empezar desde el minuto 0: no depende del núcleo ni de la puerta G1.
- **Ficheros que crea/modifica:** `docs/plan/ux-flujos.md`
- **Criterio de aceptación:** Personas (planificador, educador/público, ingeniero), 3 tareas de usuario por persona con criterio de éxito medible, mapa de pantallas A–D + paneles, requisitos de accesibilidad y de lenguaje; sin código.
- **Cubre:** RF-42, RNF-06

#### T-043 · Sistema de diseño y paleta accesible

- **Rol:** UI Designer · **Horas:** 4 · **Ola:** 2 · **Prioridad:** Must
- **Depende de:** T-042 (ux)
- **Descripción:** Define colores de Sol, Tierra, solape, ABIERTO, gates y confianza.
- **Ficheros que crea/modifica:** `docs/plan/ui-design.md`, `ui/theme.py`, `.streamlit/config.toml`
- **Criterio de aceptación:** Tokens de color con contraste ≥ 4,5:1 documentado; paleta apta para daltonismo para Sol/Tierra/paneles/estados; tema oscuro; ningún estado codificado solo por color; `ui/theme.py` sin lógica científica.
- **Cubre:** RNF-06, RF-44

#### T-044 · Esqueleto de la app, navegación, estado e i18n ★

- **Rol:** Frontend Developer · **Horas:** 7 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-043 (design), T-020 (gate1), T-026 (runner)
- **Descripción:** Solo `app.py` y `ui/` importan streamlit.
- **Ficheros que crea/modifica:** `app.py`, `ui/state.py`, `ui/layout.py`, `ui/i18n.py`, `ui/strings/es.json`, `ui/strings/en.json`, `tests/test_i18n.py`
- **Criterio de aceptación:** `streamlit run app.py` arranca y descubre `ui/pages/*.py`; estado compartido (sitio, punto, fechas, panel, perfil) en `ui/state.py`; `ui/i18n.py` con es por defecto; mismas claves en es y en (test); glosario ≥ 15 términos.
- **Cubre:** RF-42, RNF-07, RNF-09

#### T-045 · Validación de entradas: coordenadas y fechas

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-020 (gate1), T-008 (proj), T-005 (sites), T-014 (spice)
- **Descripción:** Lógica de validación testeable sin Streamlit.
- **Ficheros que crea/modifica:** `src/lsi/data/validation.py`, `tests/test_validation_inputs.py`
- **Criterio de aceptación:** Latitud/longitud validadas; fecha fuera de 1900–2050 → mensaje claro; punto fuera de DEM → modo esfera lisa con aviso; lat/lon `null` rechazados; intervalo máximo configurable.
- **Cubre:** RF-16, RF-17

#### T-046 · Componentes de selección de sitio, coordenadas y fecha

- **Rol:** Frontend Developer · **Horas:** 4 · **Ola:** 11 · **Prioridad:** Must
- **Depende de:** T-045 (inputs), T-044 (shell)
- **Descripción:** Reutilizado por todas las páginas.
- **Ficheros que crea/modifica:** `ui/components/site_picker.py`, `ui/components/time_controls.py`
- **Criterio de aceptación:** Selector curado + lat/lon personalizadas; fecha/hora/intervalo/paso y presets de días lunares; errores traducidos; el punto de observación se guarda en el estado compartido.
- **Cubre:** RF-15, RF-16, RF-17

#### T-047 · Modos de usuario, glosario y avisos de alcance ★

- **Rol:** Frontend Developer · **Horas:** 4 · **Ola:** 11 · **Prioridad:** Must
- **Depende de:** T-044 (shell), T-042 (ux)
- **Descripción:** Los avisos son componentes, no texto repetido a mano.
- **Ficheros que crea/modifica:** `ui/components/modes.py`, `ui/components/disclaimers.py`
- **Criterio de aceptación:** Selector de modo (público/planificador/ingeniero) que cambia nivel de detalle sin cambiar datos; avisos «visibilidad geométrica ≠ potencia ≠ enlace RF» y etiquetas `a verificar`/`suposición` reutilizables; tooltips con glosario.
- **Cubre:** RF-42, RF-44, RNF-05

#### T-048 · Visualización: terreno 3D y mapa 2D

- **Rol:** Frontend Developer · **Horas:** 6 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-009 (dem), T-043 (design), T-020 (gate1), T-010 (slope)
- **Descripción:** Submuestreo del recorte para mantener la interactividad.
- **Ficheros que crea/modifica:** `src/lsi/visualization/lunar_map.py`, `tests/test_lunar_map.py`
- **Criterio de aceptación:** Figura 3D con relieve y escala legible y marcador del observador; capas elevación/pendiente/incertidumbre/ldec; mapa 2D con hillshade; no importa streamlit; test comprueba tipo de figura, número de trazas y rangos.
- **Cubre:** RF-35, RF-36, RF-05

#### T-049 · Visualización: perfil de horizonte polar y cartesiano

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-043 (design), T-020 (gate1), T-012 (hcover), T-021 (vis)
- **Descripción:** Los marcadores no dependen solo del color.
- **Ficheros que crea/modifica:** `src/lsi/visualization/horizon_chart.py`, `tests/test_horizon_chart.py`
- **Criterio de aceptación:** Perfil polar y cartesiano con Sol y Tierra marcados y su estado (visible/parcial/bloqueado); sectores ABIERTO rayados con leyenda «horizonte truncado»; texto alternativo en cada figura; test de trazas.
- **Cubre:** RF-37, RF-07, RNF-06

#### T-050 · Visualización: timeline y curva de potencia

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 9 · **Prioridad:** Must
- **Depende de:** T-033 (battery), T-043 (design), T-020 (gate1), T-032 (illum), T-022 (timeline)
- **Descripción:** Incluye aviso de visibilidad geométrica en la propia figura.
- **Ficheros que crea/modifica:** `src/lsi/visualization/timeline_chart.py`, `tests/test_timeline_chart.py`
- **Criterio de aceptación:** Bandas Sol/Tierra/solape con duración y mayor ventana; curva de % potencia por panel y % de carga; marcador de sunset/Earthset con cuenta atrás; zoom en transiciones; test de trazas.
- **Cubre:** RF-38, RF-21, RF-24, RF-14

#### T-051 · Visualización: comparación, score y paneles

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 11 · **Prioridad:** Must
- **Depende de:** T-043 (design), T-020 (gate1), T-036 (pcompare), T-037 (rank), T-038 (scrange)
- **Descripción:** El gráfico muestra componentes, pesos y penalizaciones, no solo un número.
- **Ficheros que crea/modifica:** `src/lsi/visualization/comparison.py`, `tests/test_comparison_chart.py`
- **Criterio de aceptación:** Comparación lado a lado de 3 sitios; barras de contribución del score con rango y eslabón débil; comparación de paneles; test de trazas y de orden estable.
- **Cubre:** RF-41, RF-25, RF-32

#### T-052 · Exportación CSV/JSON

- **Rol:** Data Engineer · **Horas:** 3 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-037 (rank), T-026 (runner)
- **Descripción:** Cierra el requisito de descarga de resumen del documento base.
- **Ficheros que crea/modifica:** `src/lsi/analysis/export.py`, `tests/test_export.py`
- **Criterio de aceptación:** JSON con ida y vuelta sin pérdida; CSV con cabecera de metadatos (DEM, kernels, parámetros) y avisos de alcance; test con resultado sintético.
- **Cubre:** RF-43, RNF-11

#### T-053 · Página Lunar Explorer (pantalla A)

- **Rol:** Frontend Developer · **Horas:** 4 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-047 (modes), T-046 (sitepick), T-048 (vmap)
- **Descripción:** Primera pantalla de la demo.
- **Ficheros que crea/modifica:** `ui/pages/1_explorer.py`
- **Criterio de aceptación:** Muestra 3D, mapa 2D, capas conmutables, coordenadas y metadatos del raster, selección del punto y altura (1/2/5 m); avisos visibles; se carga sin error con los 3 sitios.
- **Cubre:** RF-35, RF-36, RF-44

#### T-054 · Página Horizon & Visibility (pantalla B)

- **Rol:** Frontend Developer · **Horas:** 4 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-047 (modes), T-026 (runner), T-046 (sitepick), T-049 (vhor)
- **Descripción:** Segunda pantalla de la demo.
- **Ficheros que crea/modifica:** `ui/pages/2_horizon.py`
- **Criterio de aceptación:** Perfil de horizonte, Sol/Tierra en az/el, estado de visibilidad, control de fecha/hora con paso; truncado señalizado.
- **Cubre:** RF-37, RF-44

#### T-055 · Página Mission Timeline con animación (pantalla C)

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-047 (modes), T-046 (sitepick), T-050 (vtime)
- **Descripción:** El reproductor es un componente reutilizable.
- **Ficheros que crea/modifica:** `ui/pages/3_timeline.py`, `ui/components/player.py`
- **Criterio de aceptación:** Bandas, ventanas, cuenta atrás hasta sunset/Earthset, zoom; reproductor play/pausa/velocidad que mueve el instante compartido; aviso geométrico visible.
- **Cubre:** RF-38, RF-39, RF-14, RF-44

#### T-056 · Página Paneles y potencia

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-047 (modes), T-028 (panels), T-046 (sitepick), T-051 (vcomp), T-050 (vtime)
- **Descripción:** Interfaz de la funcionalidad nueva 1 del usuario.
- **Ficheros que crea/modifica:** `ui/pages/4_panels.py`
- **Criterio de aceptación:** Selector multi-panel y montaje; parámetros editables con su etiqueta de confianza; curvas de % potencia y % carga a lo largo del día para el sitio elegido; comparación entre paneles; aviso «estimación con supuestos».
- **Cubre:** RF-40, RF-19, RF-20, RF-21, RF-23, RF-24, RF-25, RF-44

#### T-057 · Página Comparación y Score (pantalla D) ★

- **Rol:** Frontend Developer · **Horas:** 5 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-041 (calib), T-052 (export), T-047 (modes), T-046 (sitepick), T-051 (vcomp)
- **Descripción:** Interfaz de la funcionalidad nueva 2 del usuario.
- **Ficheros que crea/modifica:** `ui/pages/5_comparison.py`
- **Criterio de aceptación:** Tres sitios lado a lado con indicadores separados; perfil y pesos editables con efecto inmediato; score con rango, confianza, gates y desglose; descarga CSV/JSON.
- **Cubre:** RF-41, RF-29, RF-30, RF-31, RF-32, RF-43, RF-44

#### T-058 · Gazetteer: descarga, carga, búsqueda difusa y sitio evaluable

- **Rol:** Data Engineer · **Horas:** 9 · **Ola:** 5 · **Prioridad:** Must
- **Depende de:** T-009 (dem), T-001 (env), T-005 (sites)
- **Descripción:** Reutiliza proyección y cobertura de T-proj/T-dem; sin dependencias nuevas (difflib de la stdlib). Datos fuera de git. El esquema de `GazetteerEntry` lo fija el Software Architect en `contracts.py`; esta tarea lo respeta.
- **Ficheros que crea/modifica:** `src/lsi/data/gazetteer.py`, `src/lsi/data/evaluable.py`, `tests/test_gazetteer.py`, `tests/test_evaluable.py`, `scripts/fetch_gazetteer.py`, `config/gazetteer_manifest.json`, `tests/test_fetch_gazetteer.py`
- **Criterio de aceptación:** `load_gazetteer(path)`, `search(query, feature_types=None, region=None, limit=20)` y `get_by_name(name)` con normalización sin acentos y difflib: «shackelton» encuentra Shackleton, «De Gerlache» y «de gerlache» coinciden, resultados ordenados por puntuación estable y limitados; `to_evaluable_site(entry)` devuelve sitio con DEM si lat/lon→x,y cae dentro de la cobertura de un GeoTIFF (Shackleton, de Gerlache, Malapert verificados con casos dentro/fuera/borde) o sitio `esfera_lisa` con la etiqueta «sin datos de terreno». `python scripts/fetch_gazetteer.py` genera `data/processed/gazetteer.csv` (columnas name, clean_name, feature_type, lat, lon, diameter_km, origin, approval, quad) desde la fuente IAU/USGS registrada en el manifiesto; lon en este-positivo; idempotente; modo `--offline` no falla; el CSV no entra en git (`.gitignore` de T-env lo excluye); fuente y fecha de descarga quedan registradas.
- **Cubre:** RF-02, RF-16, RF-47, RF-48, RNF-10, RNF-13

#### T-059 · Pantalla Buscador (ui/search.py)

- **Rol:** Frontend Developer · **Horas:** 4 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-020 (gate1), T-058 (gaz), T-047 (modes), T-044 (shell)
- **Descripción:** Comparte estado con el resto de pantallas mediante `ui/state.py` (propiedad de T-shell).
- **Ficheros que crea/modifica:** `ui/search.py`, `ui/pages/0_buscador.py`
- **Criterio de aceptación:** Caja de búsqueda con resultados (nombre, tipo, lat/lon, diámetro, origen); filtro por tipo y región; al elegir una entrada se escribe en el estado compartido (`ui/state.py`, mismo sitio/punto que usan Explorer, Horizon, Timeline, Paneles y Comparación); si es sin DEM muestra aviso «sin datos de terreno / modo esfera lisa»; sin resultados muestra sugerencias.
- **Cubre:** RF-47, RF-48, RF-44, RNF-06

#### T-060 · Integración final: app.py, caché y rendimiento percibido ★

- **Rol:** Frontend Developer · **Horas:** 3 · **Ola:** 13 · **Prioridad:** Must
- **Depende de:** T-057 (pgcomp), T-053 (pgexp), T-054 (pghor), T-056 (pgpan), T-055 (pgtime), T-059 (search)
- **Descripción:** Modifica `app.py` creado en T-shell (mismo responsable, dependencia explícita).
- **Ficheros que crea/modifica:** `app.py`
- **Criterio de aceptación:** Navegación completa A–D + paneles; `st.cache_data` en resultados del runner; cambiar fecha, panel o pesos con caché responde ≤ 2 s; indicador de progreso en cálculos largos; sin excepciones en consola.
- **Cubre:** RNF-02, RF-35, RF-37, RF-38, RF-40, RF-41

### F5 — Validación

#### T-061 · Revisión matemática independiente del núcleo, potencia y score

- **Rol:** matematico · **Horas:** 6 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-015 (coords), T-011 (horizon), T-031 (power), T-008 (proj), T-037 (rank), T-022 (timeline), T-021 (vis)
- **Descripción:** El oráculo es independiente del motor (requisito RNF-10).
- **Ficheros que crea/modifica:** `tests/test_math_golden.py`, `tests/test_score_properties.py`, `docs/validation/rev-matematico.md`
- **Criterio de aceptación:** ≥ 12 casos recalculados sin reutilizar código del motor (proyección, horizonte, fracción de disco, ventanas, P_rel, batería, score); tolerancias de Mat. §8.1; propiedades del score: monotonía, continuidad, elasticidad w_i; discrepancias documentadas.
- **Cubre:** RNF-08, RNF-10, RF-03, RF-06, RF-10, RF-12, RF-20, RF-29

#### T-062 · Casos de validación del experto en la Luna

- **Rol:** experto-luna · **Horas:** 5 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-016 (ephem), T-013 (sphere), T-022 (timeline)
- **Descripción:** Valida física del polo sur con valores independientes del código.
- **Ficheros que crea/modifica:** `tests/test_luna_cases.py`, `docs/validation/rev-experto-luna.md`
- **Criterio de aceptación:** Reproduce la tabla de `luna-spice-sitios.md` §5: Tierra sobre horizonte a −89,9° = 47,0 % ± 1 pp; periodo de libración 27,22 ± 0,3 d; rotación sinódica 29,5305 ± 0,01 d; eclipse 2026-03-03 ±10 min; fecha fuera de rango → excepción.
- **Cubre:** RF-09, RF-12, RF-14, RNF-08

#### T-063 · Contraste completo con Horizons y informe

- **Rol:** API Tester · **Horas:** 4 · **Ola:** 8 · **Prioridad:** Must
- **Depende de:** T-019 (h1), T-018 (hzval)
- **Descripción:** Amplía `horizons_cases.json` creado en T-hzcases.
- **Ficheros que crea/modifica:** `scripts/run_horizons_validation.py`, `docs/validation/validacion-horizons.md`, `tests/data/horizons_cases.json`
- **Criterio de aceptación:** ≥ 12 instantes × 3 sitios × 2 cuerpos, incluidos libración extrema (±6,8°) y Sol < 1° de elevación; tabla de error máximo/medio por sitio y cuerpo en grados; dentro de tolerancia o desviación explicada (DE421 vs DE441, marco ME vs PA de Horizons).
- **Cubre:** RF-09, RNF-08, RNF-11

#### T-064 · Regresión dorada de los tres sitios

- **Rol:** Test Results Analyzer · **Horas:** 4 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-037 (rank), T-026 (runner)
- **Descripción:** Protege contra regresiones silenciosas de marcos o de horizonte.
- **Ficheros que crea/modifica:** `tests/test_regression_sites.py`, `tests/data/golden_sites.json`
- **Criterio de aceptación:** Métricas y score de Site04/11/23 (punto, fecha y paso fijos) congelados con tolerancia declarada; un cambio fuera de tolerancia falla; se documenta cómo regenerar el oro y quién lo aprueba.
- **Cubre:** RNF-03, RF-13, RF-29, RNF-10

#### T-065 · Benchmarks de rendimiento ★

- **Rol:** API Tester · **Horas:** 4 · **Ola:** 14 · **Prioridad:** Should
- **Depende de:** T-032 (illum), T-026 (runner), T-060 (wire)
- **Descripción:** Los presupuestos son objetivos a medir, no cifras ya verificadas.
- **Ficheros que crea/modifica:** `scripts/benchmark.py`, `tests/test_performance.py`, `docs/validation/rendimiento.md`
- **Criterio de aceptación:** Mide horizonte de 1 punto, timeline de 30 y 365 días, curvas de 3 paneles, memoria de pico y respuesta de la UI con caché; compara con RNF-01/02/12 (objetivos); informe con tiempos reales y cuellos de botella.
- **Cubre:** RNF-01, RNF-02, RNF-12

#### T-066 · Optimización condicional del rendimiento ★

- **Rol:** Backend Architect · **Horas:** 5 · **Ola:** 15 · **Prioridad:** Must
- **Depende de:** T-065 (bench)
- **Descripción:** Contingencia planificada; modifica ficheros de T-horizon y T-runner (dependencia explícita).
- **Ficheros que crea/modifica:** `src/lsi/terrain/horizon.py`, `src/lsi/simulation/cache.py`
- **Criterio de aceptación:** Solo si T-bench incumple RNF-01/02: reduce tiempos hasta cumplir sin cambiar resultados (los tests de horizonte y la regresión siguen pasando); si cumple, la tarea se cierra sin cambios.
- **Cubre:** RNF-01, RNF-02, RNF-03

#### T-067 · Determinismo y reproducibilidad en entorno limpio

- **Rol:** API Tester · **Horas:** 3 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-002 (envcheck), T-003 (fetch), T-026 (runner)
- **Descripción:** Evidencia del checklist de entrega «arranca desde un entorno limpio».
- **Ficheros que crea/modifica:** `tests/test_determinism.py`, `scripts/clean_env_check.sh`
- **Criterio de aceptación:** Dos ejecuciones idénticas dan métricas iguales bit a bit; `clean_env_check.sh` crea venv limpio, instala, verifica datos, ejecuta pytest y arranca la app en modo de prueba; falla con mensaje si algo falta.
- **Cubre:** RNF-03, RNF-04

#### T-068 · Pruebas E2E de la app (AppTest)

- **Rol:** API Tester · **Horas:** 4 · **Ola:** 14 · **Prioridad:** Must
- **Depende de:** T-060 (wire)
- **Descripción:** Cubre E2E sin navegador.
- **Ficheros que crea/modifica:** `tests/test_app_smoke.py`
- **Criterio de aceptación:** Con `streamlit.testing.v1.AppTest` cada página carga sin excepción para Site04, y los flujos coordenada personalizada, cambio de panel y cambio de pesos producen resultados; fecha fuera de rango muestra error de usuario, no traza.
- **Cubre:** RF-35, RF-37, RF-38, RF-40, RF-41, RNF-10

#### T-069 · QA visual y de accesibilidad con capturas

- **Rol:** Evidence Collector · **Horas:** 5 · **Ola:** 14 · **Prioridad:** Must
- **Depende de:** T-060 (wire)
- **Descripción:** Nada se da por bueno sin captura.
- **Ficheros que crea/modifica:** `scripts/qa_screenshots.py`, `docs/validation/qa-visual.md`, `docs/assets/screenshots/README.md`
- **Criterio de aceptación:** Capturas Playwright de las 5 pantallas en ≥ 2 sitios con datos reales; lista de defectos con evidencia y severidad (mínimo 3 hallazgos buscados); checklist WCAG 2.1 AA (contraste, teclado, texto alternativo, no solo color) y 3 tareas por persona.
- **Cubre:** RNF-06, RF-35, RF-36, RF-37, RF-38, RF-40, RF-41, RF-42

#### T-070 · Revisión de código del núcleo y de la UI

- **Rol:** Code Reviewer · **Horas:** 5 · **Ola:** 14 · **Prioridad:** Must
- **Depende de:** T-061 (mathrev), T-060 (wire)
- **Descripción:** Revisión centrada en corrección, no en estilo.
- **Ficheros que crea/modifica:** `tests/test_architecture_imports.py`, `docs/validation/code-review.md`
- **Criterio de aceptación:** Test AST: nada de streamlit fuera de `app.py`/`ui/`, nada de plotly en el núcleo; informe con hallazgos P0/P1/P2 sobre corrección, mantenibilidad, seguridad y rendimiento; P0/P1 resueltos o aceptados por escrito.
- **Cubre:** RNF-09, RNF-10, RNF-05

#### T-071 · Revisión final por experto en proyectos espaciales: potencia y textos UI

- **Rol:** experto-proyectos-espaciales · **Horas:** 4 · **Ola:** 14 · **Prioridad:** Must
- **Depende de:** T-033 (battery), T-032 (illum), T-060 (wire)
- **Descripción:** Cierra el bucle con el experto que verificó el catálogo.
- **Ficheros que crea/modifica:** `docs/validation/rev-expertos-final.md`
- **Criterio de aceptación:** Ninguna afirmación de potencia o enlace sin aviso; hipótesis del modelo declaradas; parámetros `a verificar` visibles en la UI; comprobación de la lista «qué NO decir» en UI, README y guion.
- **Cubre:** RNF-05, RF-44, RF-20

#### T-072 · Ventana de correcciones tras revisiones (2–3 ciclos) ★

- **Rol:** Frontend Developer · **Horas:** 8 · **Ola:** 16 · **Prioridad:** Must
- **Depende de:** T-067 (determ), T-071 (expfinal), T-040 (georev), T-063 (hzfull), T-062 (lunrev), T-061 (mathrev), T-066 (opt), T-064 (regr), T-070 (review), T-068 (smoke), T-069 (visual)
- **Descripción:** Buffer realista: la primera implementación suele necesitar 2–3 ciclos de revisión.
- **Ficheros que crea/modifica:** ninguno fijo (los fija cada hallazgo; ventana sin paralelismo)
- **Criterio de aceptación:** Todos los hallazgos P0/P1 de las revisiones cerrados con evidencia; suite completa en verde; ficheros a tocar los fija cada hallazgo y se serializan por fichero (sin tareas paralelas en esta ventana).
- **Cubre:** RNF-10, RNF-05, RNF-08

#### T-073 · Informe consolidado de pruebas y cobertura ★

- **Rol:** Test Results Analyzer · **Horas:** 3 · **Ola:** 17 · **Prioridad:** Must
- **Depende de:** T-072 (fixes)
- **Descripción:** Entrada de la puerta final.
- **Ficheros que crea/modifica:** `docs/validation/informe-pruebas.md`
- **Criterio de aceptación:** Total de tests, fallos conocidos, cobertura por paquete y matriz requisito→prueba comprobada contra `requisitos.md`; lista de requisitos Must sin prueba (debe ser vacía).
- **Cubre:** RNF-10

#### T-074 · Puerta final G5: Reality Check ★

- **Rol:** Reality Checker · **Horas:** 3 · **Ola:** 18 · **Prioridad:** Must
- **Depende de:** T-073 (results)
- **Descripción:** Certificación basada en pruebas, no en afirmaciones.
- **Ficheros que crea/modifica:** `docs/validation/reality-check.md`
- **Criterio de aceptación:** Veredicto GO/NEEDS WORK con evidencia reproducible para los 7 criterios de aceptación del MVP del documento base y para las dos funcionalidades nuevas; NEEDS WORK por defecto.
- **Cubre:** RNF-05, RNF-04

### F6 — Documentación y entrega

#### T-075 · Documento de metodología

- **Rol:** Technical Writer · **Horas:** 5 · **Ola:** 10 · **Prioridad:** Must
- **Depende de:** T-012 (hcover), T-032 (illum), T-037 (rank), T-022 (timeline)
- **Descripción:** Parte del README exigido por el documento base.
- **Ficheros que crea/modifica:** `docs/methodology.md`
- **Criterio de aceptación:** Explica transformación de coordenadas, horizonte con curvatura, efemérides, ventanas, modelo de potencia, score y confianza con fórmulas y fuentes; cada convención enlaza a `convenciones.md`; revisado por el matemático (comentarios resueltos).
- **Cubre:** RF-44, RNF-05

#### T-076 · Fuentes de datos, licencias y limitaciones conocidas

- **Rol:** Technical Writer · **Horas:** 5 · **Ola:** 12 · **Prioridad:** Must
- **Depende de:** T-041 (calib), T-007 (datacheck), T-003 (fetch), T-012 (hcover), T-032 (illum), T-027 (panelcfg)
- **Descripción:** Checklist de entrega: procedencia y licencia verificadas. Honestidad del alcance.
- **Ficheros que crea/modifica:** `docs/data_sources.md`, `docs/limitations.md`
- **Criterio de aceptación:** URLs exactas de DEM, capas, kernels y datos de paneles; versión de kernels; condiciones de uso verificadas o marcadas `a verificar`; cómo reproducir cada descarga. Lista visibilidad geométrica ≠ potencia ≠ RF, DEM finito (sesgo optimista), resolución efectiva ≈ 30 m, eclipses lunares no modelados, parámetros de panel y umbrales de score a verificar/calibrar.
- **Cubre:** RF-44, RNF-05, RNF-13

#### T-077 · Guion de demostración de 3 minutos

- **Rol:** Technical Writer · **Horas:** 3 · **Ola:** 15 · **Prioridad:** Must
- **Depende de:** T-071 (expfinal), T-060 (wire)
- **Descripción:** Incluye las dos funcionalidades nuevas del usuario.
- **Ficheros que crea/modifica:** `docs/demo-guion.md`
- **Criterio de aceptación:** Guion cronometrado de 3:00 con acción en pantalla y mensaje: Explorer Site04 → horizonte → timeline → paneles (% de potencia) → comparación y score → incertidumbre y límites; frase de cierre; plan B si falla una pantalla.
- **Cubre:** RF-44, RF-42

#### T-078 · README del proyecto

- **Rol:** Technical Writer · **Horas:** 4 · **Ola:** 15 · **Prioridad:** Must
- **Depende de:** T-067 (determ), T-076 (dsrc), T-075 (meth), T-069 (visual)
- **Descripción:** Documentación en español con acentos.
- **Ficheros que crea/modifica:** `README.md`
- **Criterio de aceptación:** Contiene los 8 elementos del documento base (problema/solución, instalación y ejecución, fuentes, metodología, métricas y reglas, limitaciones, capturas/vídeo, créditos); las instrucciones se prueban con `clean_env_check.sh`.
- **Cubre:** RNF-04, RNF-05, RF-44

#### T-079 · Capturas finales reales y guion de vídeo

- **Rol:** Evidence Collector · **Horas:** 3 · **Ola:** 17 · **Prioridad:** Must
- **Depende de:** T-077 (demo), T-072 (fixes)
- **Descripción:** El vídeo lo graba una persona con el guion; se entrega la secuencia de capturas.
- **Ficheros que crea/modifica:** `docs/assets/screenshots/final/01-explorer.png`, `docs/assets/screenshots/final/02-horizon.png`, `docs/assets/screenshots/final/03-timeline.png`, `docs/assets/screenshots/final/04-panels.png`, `docs/assets/screenshots/final/05-comparison.png`
- **Criterio de aceptación:** 5 capturas con datos reales siguiendo el guion; ninguna figura sintética sin etiqueta; resolución legible; coherentes con la versión congelada.
- **Cubre:** RF-44, RNF-05

#### T-080 · Checklist de entrega y envío ★

- **Rol:** Reality Checker · **Horas:** 2 · **Ola:** 19 · **Prioridad:** Must
- **Depende de:** T-067 (determ), T-078 (readme), T-074 (realcheck), T-079 (shots)
- **Descripción:** Última tarea de la ruta.
- **Ficheros que crea/modifica:** `docs/entrega-checklist.md`
- **Criterio de aceptación:** Checklist firmado: arranca desde entorno limpio, repo sin archivos grandes, capturas reales, README completo, vídeo, envío realizado con ≥ 2 h de margen sobre el cierre (dom 15/11 23:59 Madrid).
- **Cubre:** RNF-04, RNF-13, RNF-05

## 5. Ruta crítica

Duración mínima del proyecto con paralelismo ilimitado: **91 h**. Cualquier retraso en estas tareas retrasa la entrega:

| # | Tarea | Rol | h | Inicio más temprano (h) | Fin (h) |
|---|---|---|---|---|---|
| 1 | T-001 Entorno Python 3.11, dependencias y paquete instalable | Data Engineer | 2 | 0 | 2 |
| 2 | T-002 Smoke de entorno y fijado de versiones | Data Engineer | 2 | 2 | 4 |
| 3 | T-004 Cargador GeoTIFF y metadatos del DEM | Data Engineer | 4 | 4 | 8 |
| 4 | T-009 Ventana, muestreo bilineal y máscara nodata | Data Engineer | 4 | 8 | 12 |
| 5 | T-011 Horizonte 360° con curvatura (núcleo) | Backend Architect | 8 | 12 | 20 |
| 6 | T-021 Visibilidad geométrica y disco finito | Backend Architect | 6 | 20 | 26 |
| 7 | T-022 Ventanas temporales, refinamiento por raíz y eventos sunset/Earthset | Backend Architect | 9 | 26 | 35 |
| 8 | T-025 Escenarios de incertidumbre (cobertura, σz, discretización, clones) | Backend Architect | 7 | 35 | 42 |
| 9 | T-026 Orquestador de simulación, caché y metadatos | Backend Architect | 5 | 42 | 47 |
| 10 | T-044 Esqueleto de la app, navegación, estado e i18n | Frontend Developer | 7 | 47 | 54 |
| 11 | T-047 Modos de usuario, glosario y avisos de alcance | Frontend Developer | 4 | 54 | 58 |
| 12 | T-057 Página Comparación y Score (pantalla D) | Frontend Developer | 5 | 58 | 63 |
| 13 | T-060 Integración final: app.py, caché y rendimiento percibido | Frontend Developer | 3 | 63 | 66 |
| 14 | T-065 Benchmarks de rendimiento | API Tester | 4 | 66 | 70 |
| 15 | T-066 Optimización condicional del rendimiento | Backend Architect | 5 | 70 | 75 |
| 16 | T-072 Ventana de correcciones tras revisiones (2–3 ciclos) | Frontend Developer | 8 | 75 | 83 |
| 17 | T-073 Informe consolidado de pruebas y cobertura | Test Results Analyzer | 3 | 83 | 86 |
| 18 | T-074 Puerta final G5: Reality Check | Reality Checker | 3 | 86 | 89 |
| 19 | T-080 Checklist de entrega y envío | Reality Checker | 2 | 89 | 91 |

Cadena: T-001 → T-002 → T-004 → T-009 → T-011 → T-021 → T-022 → T-025 → T-026 → T-044 → T-047 → T-057 → T-060 → T-065 → T-066 → T-072 → T-073 → T-074 → T-080.

**Casi críticas (holgura ≤ 4 h):** T-046 (0 h), T-055 (0 h), T-056 (0 h), T-023 (1 h), T-037 (1 h), T-038 (1 h), T-051 (1 h), T-053 (1 h), T-054 (1 h), T-059 (1 h), T-008 (2 h), T-041 (2 h), T-039 (3 h), T-079 (3 h), T-069 (4 h), T-070 (4 h).

Lectura de gestión: la cadena crítica pasa por núcleo científico → puerta G1 → visualización → páginas → integración → validación → correcciones → informe y checks finales → entrega. Para acortarla: (a) empezar `T-042` y `T-043` en la ola 1, (b) no escribir UI antes de G1 pero **diseñar** pantallas durante F1, (c) mantener `T-072` (buffer) como única tarea de su ola para no mezclarla con trabajo nuevo.

## 6. Olas de ejecución en paralelo

Una ola agrupa tareas con todas sus dependencias cumplidas (inicio más temprano por niveles). Dentro de una ola **ninguna pareja comparte fichero**. Con pocos agentes, ejecutar primero las tareas críticas (★) y las de menor holgura de cada ola.

| Ola | Tareas (ID · rol) | Máx. paralelo | h de la ola más larga |
|---|---|---|---|
| 1 | T-001★ · Data Engineer<br>T-042 · UX Researcher | 2 | 4 |
| 2 | T-002★ · Data Engineer<br>T-003 · Data Engineer<br>T-005 · Data Engineer<br>T-008 · Backend Architect<br>T-015 · Backend Architect<br>T-017 · Data Engineer<br>T-027 · experto-proyectos-espaciales<br>T-030 · Backend Architect<br>T-043 · UI Designer | 9 | 5 |
| 3 | T-004★ · Data Engineer<br>T-006 · experto-luna<br>T-013 · Backend Architect<br>T-014 · Backend Architect<br>T-028 · Backend Architect<br>T-029 · Backend Architect<br>T-034 · experto-proyectos-espaciales | 7 | 5 |
| 4 | T-007 · Data Engineer<br>T-009★ · Data Engineer<br>T-016 · Backend Architect<br>T-035 · Backend Architect | 4 | 6 |
| 5 | T-010 · Data Engineer<br>T-011★ · Backend Architect<br>T-018 · API Tester<br>T-031 · Backend Architect<br>T-058 · Data Engineer | 5 | 9 |
| 6 | T-012 · Backend Architect<br>T-021★ · Backend Architect | 2 | 6 |
| 7 | T-019 · Backend Architect<br>T-022★ · Backend Architect<br>T-024 · Data Engineer<br>T-032 · Backend Architect | 4 | 9 |
| 8 | T-020 · Reality Checker<br>T-023 · Data Engineer<br>T-025★ · Backend Architect<br>T-033 · Backend Architect<br>T-040 · geologo-planetario<br>T-062 · experto-luna<br>T-063 · API Tester | 7 | 7 |
| 9 | T-026★ · Backend Architect<br>T-036 · Backend Architect<br>T-037 · AI Engineer<br>T-045 · Data Engineer<br>T-048 · Frontend Developer<br>T-049 · Frontend Developer<br>T-050 · Frontend Developer | 7 | 9 |
| 10 | T-038 · AI Engineer<br>T-039 · AI Engineer<br>T-044★ · Frontend Developer<br>T-052 · Data Engineer<br>T-061 · matematico<br>T-064 · Test Results Analyzer<br>T-067 · API Tester<br>T-075 · Technical Writer | 8 | 7 |
| 11 | T-041 · experto-proyectos-espaciales<br>T-046 · Frontend Developer<br>T-047★ · Frontend Developer<br>T-051 · Frontend Developer | 4 | 5 |
| 12 | T-053 · Frontend Developer<br>T-054 · Frontend Developer<br>T-055 · Frontend Developer<br>T-056 · Frontend Developer<br>T-057★ · Frontend Developer<br>T-059 · Frontend Developer<br>T-076 · Technical Writer | 7 | 5 |
| 13 | T-060★ · Frontend Developer | 1 | 3 |
| 14 | T-065★ · API Tester<br>T-068 · API Tester<br>T-069 · Evidence Collector<br>T-070 · Code Reviewer<br>T-071 · experto-proyectos-espaciales | 5 | 5 |
| 15 | T-066★ · Backend Architect<br>T-077 · Technical Writer<br>T-078 · Technical Writer | 3 | 5 |
| 16 | T-072★ · Frontend Developer | 1 | 8 |
| 17 | T-073★ · Test Results Analyzer<br>T-079 · Evidence Collector | 2 | 3 |
| 18 | T-074★ · Reality Checker | 1 | 3 |
| 19 | T-080★ · Reality Checker | 1 | 2 |

Nota de concurrencia: las olas son un orden de ejecución, no calendario: una tarea puede empezar en cuanto sus predecesoras terminan, sin esperar al resto de su ola.

## 7. Puertas de calidad (criterios de salida)

### G0 — Fin de F0 (H0 datos)

- **Tareas que cierran la puerta:** T-001, T-002, T-003, T-004, T-005, T-006, T-007
- **Criterios de salida (todos obligatorios):**
  - `pip install -r requirements.txt` funciona en venv limpio y los 6 kernels cargan.
  - `fetch_data.py --verify` OK; los 12 GeoTIFF con misma malla y 0 NaN por sitio.
  - `sites.json` apunta a rutas existentes; cifras de ldec reproducen las del geólogo.
  - Informe `hito0-datos.md` con CRS y extensión.
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G1 — Hito H1: una coordenada real de extremo a extremo

- **Tareas que cierran la puerta:** T-008, T-009, T-011, T-012, T-014, T-015, T-016, T-017, T-018, T-019, T-020
- **Criterios de salida (todos obligatorios):**
  - Casos analíticos de horizonte ≤ 1e-4° y de proyección ≤ 1e-6 m pasan.
  - Sol/Tierra de Site04 vs Horizons dentro de tolerancia (o desviación explicada y aprobada por experto-luna).
  - Informe H1 con convenciones y marcos documentados.
  - Reality Checker emite GO. **Sin GO no empieza código de UI ni de buscador-UI.**
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G2 — Fin de F1: núcleo completo

- **Tareas que cierran la puerta:** T-021, T-022, T-023, T-024, T-025, T-026, T-013
- **Criterios de salida (todos obligatorios):**
  - Pruebas de visibilidad, ventanas y métricas pasan (Δ5 vs Δ10 min, eventos ≤ 1 s).
  - `runner` produce resultado con metadatos para los 3 sitios y para un punto en esfera lisa.
  - Rendimiento preliminar medido (informativo).
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G3 — Fin de F2+F3: energía, paneles y score

- **Tareas que cierran la puerta:** T-027, T-028, T-029, T-030, T-031, T-032, T-033, T-034, T-035, T-036, T-037, T-038, T-039, T-040, T-041
- **Criterios de salida (todos obligatorios):**
  - P_rel ≤ 1e-4 en casos de Mat. §6.7; batería ≤ 0,1 Wh.
  - Score §7.7 = 67,9 ± 0,05 y propiedades verificadas.
  - Todo parámetro de panel con etiqueta de confianza; ningún valor sin fuente.
  - Calibración documentada; interior de Shackleton no puntúa como buen sitio solar.
  - Ubicaciones en esfera lisa salen con «sin datos de terreno».
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G4 — Fin de F4: interfaz completa

- **Tareas que cierran la puerta:** T-042, T-043, T-044, T-045, T-046, T-047, T-048, T-049, T-050, T-051, T-052, T-058, T-059, T-053, T-054, T-055, T-056, T-057, T-060
- **Criterios de salida (todos obligatorios):**
  - Las 5 pantallas + Buscador cargan con los 3 sitios y con una coordenada personalizada.
  - Buscador localiza «Shackleton» y una errata («shackelton») y el estado se comparte con las demás pantallas.
  - Cambiar fecha/panel/pesos con caché ≤ 2 s.
  - Avisos de alcance visibles en cada pantalla.
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G5 — Fin de F5: validación

- **Tareas que cierran la puerta:** T-061, T-062, T-063, T-064, T-065, T-066, T-067, T-068, T-069, T-070, T-071, T-072, T-073, T-074
- **Criterios de salida (todos obligatorios):**
  - Contraste completo con Horizons dentro de tolerancia o desviación explicada.
  - Casos del matemático y del experto en la Luna pasan; regresión dorada congelada.
  - Cero P0/P1 abiertos de revisión de código, QA visual y expertos.
  - Informe de pruebas sin requisito Must sin prueba; Reality Checker GO.
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

### G6 — Entrega

- **Tareas que cierran la puerta:** T-075, T-076, T-077, T-078, T-079, T-080
- **Criterios de salida (todos obligatorios):**
  - Arranca desde entorno limpio con `clean_env_check.sh`.
  - README con los 8 elementos; capturas reales; figuras sintéticas etiquetadas.
  - Procedencia y licencias de datos documentadas.
  - Envío realizado con ≥ 2 h de margen (dom 15/11 antes de las 21:59 Madrid).
- **Si falla:** no se abre la fase siguiente; el trabajo se redirige a la tarea responsable y se re-ejecuta el criterio fallido.

## 8. Registro de riesgos

| ID | Riesgo | Impacto | Prob. | Mitigación | Responsable |
|---|---|---|---|---|---|
| R-01 | Calendario: ruta crítica de 91 h frente a 39 h de reloj y 24 h efectivas del documento base. | Alto | Alta | Recortar por MoSCoW en este orden: RF-34, RF-45, RF-39, RF-43, RF-22, RNF-07 (inglés); congelar alcance en G2; `T-072` es el único buffer; entregar con 2 h de margen. | PM |
| R-02 | Marco de coordenadas erróneo (MOON_PA o IAU_MOON en vez de MOON_ME): desplaza ~0,87 km / 35–85 m y la UI parece correcta (riesgo nº 1 de los expertos). | Crítico | Media | Solo MOON_ME en `spice_engine`; test MOON_ME vs MOON_PA = 103,85″; contraste Horizons obligatorio en G1 (T-018, T-063). | experto-luna |
| R-03 | Truncado del DEM: recortes de 16–21 km; hasta 41,9 % de azimuts con horizonte aún subiendo en el borde (Shackleton); el error solo puede sobrestimar la iluminación. | Alto | Alta | `horizon_coverage` (ABIERTO/CERRADO, cota inferior), visualización rayada, resta de nivel de confianza si ABIERTO > 10 %, score con rango, limitación declarada; opción RF-45 (ventana LOLA 20 m). | geologo-planetario |
| R-04 | `ldec = 0` en ~91 % de píxeles: la resolución efectiva es ~15–30 m, no 5 m; se puede dar falsa precisión. | Alto | Alta | Data Confidence con g90/e90; texto «resolución efectiva ≈ 30 m» junto a toda clase ALTA; horizonte con observador a 0 m evaluado con exclusión de campo cercano y altura explícita. | geologo-planetario |
| R-05 | Rango temporal del BPC lunar 1900–2050: fuera falla con `FRAMEDATANOTFOUND`. | Medio | Media | Validación en `spice_engine` y en `validation.py`; mensaje de usuario claro; test con fecha fuera de rango (T-062). | Backend Architect |
| R-06 | Parámetros de panel `a verificar` (IAM, emisividades, eficiencia de VSAT/ROSA/CIGS/perovskita, polvo) presentados como hechos. | Alto | Alta | Etiqueta de confianza obligatoria en esquema y UI; test que rechaza parámetros sin etiqueta; revisión del experto (T-027, T-071). | experto-proyectos-espaciales |
| R-07 | Umbrales del score y de perfiles son suposiciones; un ranking parece más objetivo de lo que es. | Alto | Alta | Score siempre con desglose, rango y confianza; umbrales editables y etiquetados `a calibrar`; calibración documentada (T-041). | experto-proyectos-espaciales |
| R-08 | Rendimiento del ray casting (1440 azimuts × 5 m × radios largos) y de la UI. | Medio | Media | Vectorización NumPy, caché por (sitio, punto, altura), benchmarks tempranos (T-065) y optimización condicional (T-066). | Backend Architect |
| R-09 | Dependencias de GDAL/rasterio en Windows consumen horas. | Medio | Media | Resolver y fijar versiones en F0 (T-002) antes de escribir código; `clean_env_check.sh`. | Data Engineer |
| R-10 | Colisiones de escritura entre agentes en paralelo y `git add -A`. | Medio | Media | Ficheros exactos por tarea; comprobador de olas; añadir ficheros a git por nombre. | PM |
| R-11 | Discrepancia detectada: `sites.json` apunta a `data/raw/dem/siteNN`, que no existe (los datos están en `data/raw/<sitio>/`). | Medio | Cierta | Corregir en T-005; test que verifica la existencia de las rutas. | Data Engineer |
| R-12 | Comparación con Horizons: marco ME vs PA de las coordenadas de sitio y DE421 vs DE441 (≲ 0,05″) sin verificar; el entorno de cálculo no tenía red. | Medio | Media | Casos versionados (T-017); informe con desviaciones explicadas; no exigir tolerancias menores que 0,05″. | matematico |
| R-13 | Gazetteer: cobertura incompleta, nombres duplicados o fuente inaccesible; la mayoría de entradas no tendrá DEM. | Medio | Media | Manifiesto con fuente y fecha; `--offline` y CSV de respaldo; búsqueda difusa con desempate estable; sitios sin DEM etiquetados «sin datos de terreno» y no comparables (T-058). | Data Engineer |
| R-14 | Alcance excesivo (luxury): perovskita, ROSA, clones DEM, SDEM, inglés. | Medio | Alta | Won't/Could explícitos en RF-34, RF-45, RF-46, RNF-07; no se empiezan antes de G3. | PM |
| R-15 | Eclipses lunares y sombra propia del lander no modelados: la oscuridad se subestima en eclipses. | Bajo | Media | Documentado en limitaciones y en la UI; no se afirma potencia garantizada. | experto-luna |
| R-16 | Playwright/Streamlit en Windows inestables para QA visual. | Bajo | Media | AppTest como respaldo E2E (T-068); capturas manuales como último recurso. | Evidence Collector |

## 9. Plan de pruebas

| Nivel | Qué prueba | Oráculo independiente | Tareas | Tolerancia / criterio |
|---|---|---|---|---|
| Unitarias | Cada función con lógica: proyección, horizonte, ENU, visibilidad, ventanas, métricas, incidencia, térmico, potencia, batería, score, gazetteer | Casos analíticos o calculados a mano de los informes de expertos | T-008, T-011, T-015, T-021, T-022, T-023, T-029, T-030, T-031, T-033, T-037, T-058 | Mat. §8.1 (tabla en requisitos.md §4.1) |
| Datos | Integridad de GeoTIFF, georreferencia, `ldec`, `slp` vs `surf`, gazetteer | Cifras medidas por el geólogo | T-007, T-004, T-003 | RMSE slp < 0,01°; ldec=0 en 90–92 % |
| Regresión | Métricas y score de los 3 sitios; SPICE-reg | Oro congelado tras revisión de expertos | T-064, T-016 | Fuera de tolerancia = fallo |
| Validación contra Horizons | 24 casos + tabla completa 3 sitios × 2 cuerpos × ≥ 12 instantes | JPL Horizons | T-018, T-063, T-019 | Sol ≤ 0,01°; Tierra ≤ 0,02° |
| Validación independiente | Recálculo sin código del motor; segundo algoritmo de línea de vista; casos de la Luna | Matemático, geólogo, experto Luna | T-061, T-040, T-062 | Diferencia horizonte < 0,1° en 5 puntos |
| Propiedades | Monotonía, continuidad, invariancia del score; determinismo | Propiedades matemáticas | T-061, T-067 | Bit a bit en métricas |
| Rendimiento | Horizonte, timeline 30/365 d, curvas de paneles, memoria, UI con caché | Objetivos RNF-01/02/12 | T-065, T-066 | Objetivos del SRS (a medir) |
| E2E / UI | AppTest de las pantallas, flujos de usuario, errores de usuario | Comportamiento esperado de las historias de usuario | T-068 | Sin excepciones; mensajes claros |
| Visual y accesibilidad | Capturas, contraste, teclado, texto alternativo, no solo color | Checklist WCAG 2.1 AA y ojos humanos | T-069 | Cero P0/P1 abiertos |
| Arquitectura | Sin streamlit fuera de `ui/`/`app.py`; sin plotly en el núcleo | Escaneo AST | T-070 | Cero imports prohibidos |
| Aceptación | Criterios del MVP del documento base + 2 funcionalidades nuevas + buscador | Reality Checker | T-074, T-080 | 7+3 criterios con evidencia |

## 10. Comprobador del plan

`tasks.json` se valida con un script Python que comprueba: (1) JSON válido y campos obligatorios; (2) 50–80 tareas; (3) todas las dependencias existen; (4) el grafo no tiene ciclos; (5) la ola de cada tarea es mayor que la de sus predecesoras; (6) **ninguna pareja de tareas de la misma ola comparte fichero**; (7) cualquier fichero tocado por dos tareas pertenece a una cadena con dependencia entre ellas; (8) todos los requisitos citados existen y todo requisito Must/Should/Could está cubierto por ≥ 1 tarea. Resultado de la última ejecución: ver informe final del PM (pasa).
