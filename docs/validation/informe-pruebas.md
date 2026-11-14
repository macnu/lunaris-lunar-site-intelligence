# Informe de pruebas de la versión funcional (§12.3)

Fecha: 2026-11-14. Python 3.11.9, Windows 11. Kernels DE421 y DEM Site04/Site11/Site23 + campo lejano LOLA 80 m reales.
Se excluye `tests/test_independent_visibility.py` por indicación del encargo (contraste independiente, aparte).

## 1. Resultados

| Ejecución | Comando | Resultado | Tiempo |
|---|---|---|---|
| Entorno actual + cobertura | `python -m pytest -q --ignore=tests/test_independent_visibility.py --cov=src/lsi --cov=ui` | **536 passed, 38 skipped, 0 failed** | 122 s |
| **Entorno limpio** (venv nuevo fuera del repo) | mismo, sin cobertura, desde el venv | **536 passed, 38 skipped, 0 failed** | 94 s (+ 91 s de `pip install`, 10 s de `venv`) |
| `streamlit run app.py --server.headless true` (venv limpio, puerto 8765) | `GET /_stcore/health` y `GET /` | **HTTP 200 (`ok`)** en ≈ 1 s; proceso detenido | — |

Presupuesto RNF-10 (suite < 5 min sin red): cumplido (≈ 2 min).

Versiones del venv limpio (idénticas a `requirements.txt`): numpy 2.4.2, scipy 1.17.1, pandas 2.3.3, pyarrow 23.0.1,
rasterio 1.4.4, pyproj 3.7.2, spiceypy 8.4.0, plotly 6.8.0, pydeck 0.9.2, streamlit 1.58.0, requests 2.34.2, pytest 9.0.2,
pytest-cov 7.0.0, pyshp 3.1.8. `pip install -r requirements.txt` sin errores ni conflictos.

**Dependencias ocultas: ninguna.** Todo `import` de terceros en `src/`, `ui/`, `app.py`, `scripts/` y `tests/` está en
`requirements.txt`. Único opcional no declarado: `kaleido`, usado en `ui/pages/comparison.py:595` detrás de
`importlib.util.find_spec("kaleido")` (si falta, la página muestra cómo instalarlo). Diff solo si se quiere el botón PNG:

```diff
 pyshp==3.1.8
+kaleido==<versión a fijar tras verificarla>   # opcional: descarga PNG en «Comparación de sitios»
```

No es necesario para el criterio de salida.

## 2. Pruebas nuevas de esta fase (26 tests, todos en verde)

| Fichero | Tests | Qué cubre | Tiempo |
|---|---|---|---|
| `tests/test_e2e.py` | 5 | §12.3 (5) y (7). Buscar por nombre → «Evaluar este lugar» → horizonte DEM → timeline 30 d → cuenta atrás → panel `tj-gaas-lander-body`/`vertical_az_tracking` → score con veredicto y rango → JSON + CSV + `validate_export`. Site04 (Shackleton, snap 0,3–1,5 km), Site11 (de Gerlache, snap 4–7 km), Site23 (Mons Malapert, DEM directo). Esfera lisa: Apolo 11 (SIN DATOS) y Tycho (rasgo del buscador sin cobertura). | ≈ 1 s por sitio |
| `tests/test_ui_smoke.py` | 11 | `AppTest` recorre las 9 páginas × 3 modos (Público/Planificador/Experto) sin `exception` ni error de barra lateral; app con navegación completa sin páginas pendientes. | ≈ 10 s |
| `tests/test_perf.py` (marca `perf`) | 5 | Presupuestos §10 con umbral ×2 y tiempo impreso (ver §4). | ≈ 13 s |
| `tests/test_determinism.py` | 2 | JSON y 4 CSV + metadata byte a byte idénticos entre 3 ejecuciones: SPICE reabierto (`build_context`) y caché de horizontes en frío (directorio vacío). DEM Site23 y esfera Apolo 11. | ≈ 7 s |
| `tests/test_golden_regression.py` + `tests/golden/site{04,11,23}.json` | 3 | Valores de referencia con tolerancias; el fallo indica cómo regenerar (`LSI_REGEN_GOLDEN=1`). Verificado que falla al alterar un valor. | ≈ 3 s |

Aserciones del flujo: metadatos (marco, abcorr, radio, hash de kernels, `cache_key`, sha256 del DEM, `generated_utc`); avisos
siempre visibles en el export (`DEM_EFFECTIVE_RESOLUTION` solo en modo DEM; en esfera, `NO_DEM_SMOOTH_SPHERE` y
`NO_TERRAIN_DATA_SCORE`); `limited` bool de 1440 azimuts, fracción exportada = media, sin truncado en esfera; % de potencia en
[0, 104]; score en [0, 100] con `score_min ≤ score ≤ score_max`; ventana de misión de 14 d dentro del periodo con 17 inicios;
cabeceras CSV = `CSV_*_COLUMNS`; esfera: `partial`, `terrain_data=False`, `missing_keys==("terrain",)`, veredicto SIN DATOS o NO APTO
provisional.

### Valores dorados (30 d desde 2026-12-01, `tj-gaas-lander-body`, perfil lander sin RHU)

| Sitio | Punto evaluado | f_sol | f_Tierra | Ventana sol más larga | Oscuridad máx. | Score [min–max] | Veredicto | % potencia |
|---|---|---|---|---|---|---|---|---|
| Site04 | snap Shackleton (0,80 km) | 0,0000 | 0,0000 | 0,0 h | 720,0 h | 2,18 [2,18–2,18] | NO APTO | 0,0 |
| Site11 | snap de Gerlache (5,87 km) | 0,1514 | 0,0000 | 66,2 h | 546,5 h | 13,27 [13,26–13,28] | NO APTO | 7,9 |
| Site23 | Mons Malapert (DEM) | 0,4268 | 0,8945 | 264,8 h | 304,7 h | 58,07 [57,86–58,28] | NO APTO | 40,8 |

Tolerancias: fracciones 5e-4, ventanas 60 s, score ≤ 0,05 (RNF-08), snap 0,01 km; veredicto y fechas exactos.

## 3. Hallazgos de las pruebas (no son fallos de test; conviene que lo sepa quien use el producto)

1. **Site04 por el flujo del buscador cae en oscuridad permanente.** El centro de Shackleton queda ≈ 0,8 km fuera del recorte; el
   snap elige el punto cubierto más cercano, que no recibe Sol en el periodo: f_sol = 0 → potencia 0 %, score 2,18 y rango
   degenerado. Es un resultado físicamente correcto y está etiquetado con la distancia, pero un usuario que busque «Shackleton» verá
   un sitio «muerto» (el borde iluminado es otro punto, el `dem_default_observer` usado por `test_pipeline`, f_sol ≈ 0,36). Los
   tests lo toleran a propósito (potencia ≥ 0; rango estricto solo si f_sol > 0).
2. El horizonte puede quedar por debajo del suelo de la esfera lisa (terreno bajo el plano local); no es un error, se probó
   |h| < 90° en lugar de h ≥ h_esfera.
3. Los tres sitios con DEM dan NO APTO en el periodo de prueba (dic-2026, misión de 14 d, perfil lander sin RHU): ninguna fecha
   de inicio supera las puertas duras (Site23: `best_start_utc = null`). Es coherente con las noches de 300–720 h, no un fallo.

## 4. Rendimiento (Site23, máquina de desarrollo, mejor de 3)

| Operación | Medido | Presupuesto §10 | Umbral del test (×2) |
|---|---|---|---|
| Horizonte de un punto, caché en frío (1440 az, DEM 5 m + lejano) | 0,51 s | 2 s | 4 s |
| 30 días a 10 min (horizonte en caché; incluye potencia y score por ventana) | 0,43 s | 3 s | 6 s |
| 30 días con incertidumbre (escenarios en caché) | 0,56 s | 20 s (RNF-01; §10 no fija uno) | 40 s |
| 1 año a 10 min (horizonte en caché, mejor de 2) | 1,98 s | 20 s | 40 s |

Tolerancia a carga: si se supera el umbral, un calibrador fijo de CPU (`np.sin` sobre 2 M elementos; referencia 0,065 s) decide:
máquina ≥ 2× más lenta → `xfail` documentado; calibrador normal → fallo real. `LSI_PERF_STRICT=1` desactiva el xfail. Ejecutar:
`python -m pytest -m perf -s`.

## 5. Cobertura (`--cov=src/lsi --cov=ui`, suite completa)

| Módulo | Sentencias | Sin cubrir | Cobertura |
|---|---|---|---|
| analysis/confidence | 56 | 0 | 100 % |
| analysis/export | 266 | 17 | 94 % |
| analysis/metrics | 110 | 4 | 96 % |
| analysis/site_score | 227 | 3 | 99 % |
| analysis/suitability_map | 549 | 73 | 87 % |
| astronomy/coordinates | 36 | 0 | 100 % |
| astronomy/spice_engine | 91 | 5 | 95 % |
| contracts | 712 | 0 | 100 % |
| data/cache | 85 | 10 | 88 % |
| data/catalog | 131 | 12 | 91 % |
| data/gazetteer | 105 | 1 | 99 % |
| data/loader | 134 | 5 | 96 % |
| energy/panels | 158 | 8 | 95 % |
| pipeline | 480 | 33 | 93 % |
| simulation/timeline | 78 | 0 | 100 % |
| simulation/uncertainty | 42 | 0 | 100 % |
| simulation/visibility | 68 | 1 | 99 % |
| terrain/horizon | 150 | 4 | 97 % |
| terrain/roughness · sampling · slope | 31 · 25 · 46 | 1 · 0 · 1 | 97 · 100 · 98 % |
| visualization (7 módulos) | 390 | 8 | 98 % |
| ui/cache | 70 | 13 | 81 % |
| ui/components | 200 | 29 | 86 % |
| ui/sidebar · ui/state · ui/__init__ | 155 · 164 · 9 | 9 · 18 · 0 | 94 · 89 · 100 % |
| **TOTAL medido** | **5 400** | **865** | **84 %** |

Limitación de la medición: las páginas de `ui/pages/` se ejecutan con `AppTest` (exec del script), y `coverage` solo contabiliza
`comparison.py` (20 %), `search.py` (79 %) y `site_score.py` (12 %); el resto de páginas no aparece. El 84 % total está sesgado a
la baja por esas líneas de render; el núcleo (`src/lsi`: 3 971 sentencias, 186 sin cubrir) está en 95,3 %. Su verificación real es funcional (tests `test_page_*` y el humo).

## 6. Tests omitidos (38) y excluidos

| Tests | Motivo |
|---|---|
| 38 de `tests/test_luna_cases.py` (líneas 56, 62, 67, 72, 78, 84, 99) | Falta el DEM Site01 en `data/validation_raw/site01` (validación independiente con Luna; se descarga aparte, ver docstring del fichero). Omisión limpia, no fallo. |
| `tests/test_independent_visibility.py` (excluido por el encargo) | No ejecutado en esta fase. |

## 7. Fallos y causa

Ninguno en la suite (0 failed en ambos entornos). Durante el desarrollo de los tests nuevos hubo 6 aserciones propias erróneas
(no defectos del motor), corregidas: potencia exactamente 0 % en Site04 (hallazgo 1), rango de score degenerado en Site04,
horizonte bajo el suelo de la esfera (hallazgo 2), redondeo a 5 decimales del export frente a `abs=1e-6`, y códigos de aviso
exportados en minúsculas.

## 8. Cómo reproducir

```
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
python -m pytest -q --ignore=tests/test_independent_visibility.py          # suite completa
python -m pytest -m perf -s                                                 # presupuestos con tiempos
$env:LSI_REGEN_GOLDEN=1; python -m pytest tests/test_golden_regression.py   # regenerar dorados (consciente)
```
