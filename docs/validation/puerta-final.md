# Puerta de realidad final de LSI

Fecha: 2026-11-14. Todo lo de abajo lo ejecuté o leí yo en esta sesión; no me baso en los informes de otros agentes salvo donde se indica. Scripts de prueba fuera del repo (scratchpad). No se ha editado código ni se ha hecho commit.

## Veredicto: CERTIFICADO CON RESERVAS (versión funcional) / NEEDS WORK (segundo objetivo)

- **Versión funcional (§12.3):** cumple los 7 puntos con evidencia propia. Las reservas son de honestidad, de documentación desfasada y de limpieza, no de funcionamiento.
- **Objetivo declarado del usuario (buscador + algoritmo de idoneidad):** existe y funciona, pero el buscador no cubre los sitios de misión por nombre y el score es una convención sin calibrar. Para "terminar" ese segundo objetivo, NEEDS WORK (ver reservas R1-R3).
- **No certifico** "APTO" como certificación de nada, ni la potencia ni el enlace: el propio código y los textos lo dicen y los he comprobado así.

## Ejecuciones propias

| Qué | Resultado exacto |
|---|---|
| `python -m pytest -q --ignore=tests/test_independent_visibility.py` (dos veces) | **584 passed, 38 skipped, 0 failed** (116 s y 111 s). Los 38 skips son todos "falta el DEM Site01" (`tests/test_luna_cases.py`, validación contra literatura); ninguno otro. |
| `python -m pytest -q tests/test_independent_visibility.py` | **26 passed** en 105 s |
| `-m perf -s` | horizonte frío 0,49 s (presupuesto 2 s); 30 d 0,41 s (3 s); 30 d con incertidumbre 0,54 s (20 s); 1 año 1,97 s (20 s). 5 passed |
| Streamlit `--server.port 8767` | `/_stcore/health` 200 y `/` 200; proceso detenido al final (health ya no responde) |
| **Venv limpio nuevo** (scratchpad) + `pip install -r requirements.txt` | sin errores; `test_ui_smoke + test_e2e + test_perf`: **21 passed** (25 s) |
| `AppTest` sobre `app.py` | sin excepciones; buscador responde a Shackleton, Apolo 11, Apollo 11, Tycho |

Calidad de las pruebas: sin `xfail`, sin `assert True`; los skips son por datos ausentes. `tests/test_e2e.py` tiene aserciones sustanciales (rangos, esquema, `limited`, cuenta atrás, ventana de misión). Reserva: `test_perf.py` degrada a `xfail` si el calibrador de CPU dice que la máquina es lenta.

## Criterio de salida §12.3

| # | Criterio | Estado | Evidencia propia |
|---|---|---|---|
| 1 | venv + `pip install -r requirements.txt` | Cumplido | venv nuevo, instalación sin error |
| 2 | `fetch_data.py` + `fetch_gazetteer.py` | Parcial (no re-descargado) | No repetí los 0,8 GB. Comprobé que los scripts existen, URLs PGDA/NAIF/USGS, `data/raw` con 3 DEM + LOLA 80 m + gazetteer, kernels presentes, `gazetteer.parquet` 9087 filas. `precompute_horizons.py` corre idempotente. **Ninguno de los dos descarga con verificación de hash** (revision-codigo B6, sin tocar). |
| 3 | `pytest -q` en verde, `slow` incluidos | Cumplido | 584+26 passed; skips solo Site01 |
| 4 | App arranca; `test_ui_smoke` recorre las páginas | Cumplido | 9 páginas (no 8; el criterio estaba desfasado), 11 tests passed en venv limpio |
| 5 | E2E con Site04/11/23 (buscar, evaluar, horizonte DEM, 30 d, cuenta atrás, panel `tj-gaas-lander-body` con `vertical_az_tracking`, score con rango, JSON+CSV) | Cumplido | `test_e2e.py` 5 passed en venv limpio; además reproduje el flujo yo mismo: Shackleton, de Gerlache y Malapert dan modo `dem`, potencia 86,1 / 68,4 / 40,8 %, export JSON validado con `validate_export`, 0 valores no finitos |
| 6 | Presupuestos §10 | Cumplido | tiempos arriba (todos muy por debajo) |
| 7 | Sitio sin DEM y rasgo del buscador sin cobertura en esfera lisa con "sin datos de terreno" | Cumplido | Tycho y Copernicus: `smooth_sphere`, `terrain_data=False`, G2/G3 `sin_datos_suficientes`; coordenadas (-80, 10) y (0, 0): `SIN DATOS` |

## Requisitos del reto y del usuario

| Requisito | Estado | Evidencia |
|---|---|---|
| Comparar sitios y fechas, coordenadas propias | Cumplido | Comparación hasta 5; punto propio dentro de DEM (-85,984, 2,612: modo `dem`) y fuera (esfera lisa, aviso) |
| Sol/Tierra vs horizonte, cuenta atrás sunset/Earthset | Cumplido | `countdowns` SUN/EARTH con `seconds_until` en todos los casos; Malapert 2026-12-10: Sol se pone en 319 255 s, Tierra sigue visible |
| Potencia y comunicación | Cumplido con límite | Solo visibilidad geométrica; sin presupuesto de enlace (declarado) |
| 2D/3D y timeline | Presente | Páginas existen y pasan humo; el 3D se arregló según `explorer-3d-corregido.jpg` (no re-verificado en navegador) |
| Fechas fuera de 1900-2050 | Cumplido | `DateOutOfRangeError` "ET fuera del rango válido [1900-01-02, 2050-12-30]"; UI lo traduce a "Elige fechas entre 1900 y 2050". Nota: todo diciembre de 2050 falla (el rango termina el 30/12). |
| Varios paneles, % según ubicación y hora | **Parcial** | Ver D1 |
| Física vertical/horizontal | Cumplido, con matiz | cosθ: V/H = 57,3 / 38,2 / 19,1 a 1° / 1,5° / 3° (coincide, y el test lo fija). **La potencia modelada incluye IAM de Fresnel**: V/H = 491 / 246 / 61. La pantalla lo rotula ("razón con pérdida por reflexión"). Máximo % observado 101,1 (Shackleton, vertical con seguimiento, perihelio/frío); pico de serie 100,97; nunca >104 |
| Batería | Cumplido | 700 Wh/200 W/50 W en Malapert: SOC en [0,2; 1,0], sin NaN, 355 h sin servir. La batería no se exporta a JSON |
| Score con veredicto, rango, mejor fecha | Cumplido | APTO/CONDICIONAL/NO APTO/SIN DATOS con puertas y motivo; `best_start_utc`, `top_windows` |
| Mapa de mejores puntos | Cumplido | 63 ficheros en `data/processed/suitability/`; guion lo usa |
| Buscador por nombre de cráteres y zonas | **Parcial** | 9087 rasgos IAM; ver R1 |

## Defectos y reservas

### Defectos que arreglaría antes de entregar (no rompen el flujo, pero engañan o ensucian)

- **D1. Cuatro de los 8 paneles del catálogo no se pueden calcular** (`rosa-flexible-rollout`, `si-legacy`, `cigs-thin-film-flex`, `perovskite-si-tandem-demo`: `PanelNotCalculableError`, faltan α/ε/η "a verificar"). La UI muestra "no calculable", no un 0 (bien), pero el README anuncia "8 tipos de panel". Honesto: 4 calculables, de los cuales `tj-gaas-lander-body` y `tj-gaas-vertical-mast` tienen casi idéntico resultado (40,8 % ambos en Malapert). Tecnologías realmente distintas con número: GaAs 3J, 4J, rover GaAs. Cumple "≥3 tipos" por poco.
- **D2. `README.md` desfasado:** dice "399 funciones de prueba en 39 ficheros" (hay 436 `def test_` en 42 ficheros; 584+26 casos); dice "No existe un marcador `perf`" (existe en `pytest.ini` y se usa); dice "Capturas: pendiente (no existe `docs/capturas/`)" (existe, 31 JPG, 2,4 MB).
- **D3. `docs/guion-demo.md` con cifras que ya no reproduzco:** Shackleton #1 score 94,4 / f_Tierra 0,69 (ahora **97,4 / 0,63**, con `snap_prefer="nearest"` en el punto exacto); Malapert "confianza media" (ahora **alta**), vertical con seguimiento 98,8 % (ahora 99,0 %). El resto de Malapert (98,4, 2,8/67,8 %) sí coincide. Reejecutar el guion antes del vídeo.
- **D4. Ficheros sueltos sin ignorar:** `S_horn.npy` (79 MB), `fine_Site04.json`, `.coverage` en la raíz; `.gitignore` no los cubre. El repo no tiene ningún commit y todo está sin seguimiento: un `git add .` subiría 79 MB. Sin ellos el repo ocupa ~9 MB. Ya lo señaló `revision-codigo.md` B5 y sigue sin tocar.
- **D5. Entrada del núcleo sin validar:** `run_analysis` acepta latitud 95° y longitud 400° sin error (resultado de esfera lisa como si fuera válido). La UI limita los widgets a [-90, 90], así que hoy no es alcanzable; es un riesgo latente (B3 sin tocar).
- **D6. `validate_export` valida estructura, no rangos:** acepta `score=140`. Los rangos solo los vigilan los tests E2E. No es fallo del export real (0 no finitos, score en [0,100]).

### Reservas honestas (afirmaciones y alcance)

- **R1. Buscador:** cobertura real = 9087 rasgos, pero 7064 son "Satellite Feature" (A, B, C... de cráteres), 1615 cráteres y ~400 de mares, rimas, montes, etc. (18 tipos). **Los sitios de misión no se encuentran por nombre**: "Apolo 11" devuelve el cráter *Apollo* (cuenca Polo Sur-Aitken) y ofrece "Evaluar en esfera lisa" sobre un lugar equivocado; "Luna 9" devuelve Lundmark; "Connecting Ridge" y las regiones Artemis III dan 0 (no son nombre IAU, y `sites.json` tiene 13 sin coordenadas). Los 19 sitios de misión con coordenadas solo se alcanzan desde la barra lateral y Comparación. Búsqueda difusa mete ruido (Shackleton, 6 resultados: Appleton, Hamilton...).
- **R2. Score sin calibrar ni validado como predictor** (declarado en README y limitaciones; lo confirmo): pesos y umbrales son convenciones. Comportamientos que el usuario puede malinterpretar: Tycho puntúa 95,6 con veredicto NO APTO (puerta G0, llegada de noche); Copernicus 4,1; un sitio sin terreno puede mostrar 100,0 con "SIN DATOS" (rango 39,8-100). El score **no cambia con el tipo de panel ni el montaje** (58,1 en Malapert con todos); la potencia por panel va aparte del score. El usuario pidió "un algoritmo que diga lo buena que es una ubicación" y paneles con % de carga: están conectados solo por la fracción de Sol.
- **R3. Sesgo de selección en el "mejor punto":** buscar Shackleton evalúa por defecto el TOP-1 del mapa a **16 km** del centro del rasgo (-89,5626°, 215,4724°E), con f_sol 1,00, confianza "alta" (0,96) y rango degenerado 97,4-97,4. Está etiquetado ("mejor punto... alternativa a 0,80 km"), pero "confianza alta" sobre un punto escogido por optimización, con DEM de resolución efectiva ~30 m y campo lejano de 80 m, es optimista. La confianza mide calidad del dato, no riesgo de selección.
- **R4. Rangos de incertidumbre a veces de ancho cero** aunque se pida `with_uncertainty=True` (Shackleton, de Gerlache, Malapert #1): el "rango" del guion no aporta información en puntos saturados.
- **R5. Procedencia/licencias:** `docs/fuentes-datos.md` declara que las licencias de PGDA y USGS **no se verificaron**; los parámetros de paneles marcados `a_verificar` son mayoría (todos los α/ε de 6 de 8 paneles). Se declara bien; no hay datos presentados como verificados que no lo estén en lo que leí. Los scripts de descarga no comprueban hash.
- **R6. Contraste con Horizons (≤0,05″):** no reproducible aquí sin red; confío en los 24 casos codificados en `test_spice_engine.py` (sí pasan). La comparación 3D independiente (26 tests) pasa, pero valida las matemáticas, no los datos LOLA.
- **R7. Validación no ejecutada por mí:** DEM Site01 ausente, así que las 38 pruebas contra literatura (Barker 2021, Glaser 2014) están omitidas; confío en `validacion-luna.md` para eso. Sin navegador: no re-verifiqué P1-1/P1-2/P1-3 de `qa-visual.md` (3D, timeline vacío, cifras Comparación vs Score). P1-3 (cifras distintas para el mismo sitio sin rotular ventana) lo he visto reproducido en espíritu: 30 d da Sol 0,86 y la ventana de 14 d 1,00 en Shackleton; si la pantalla no rotula la ventana, confunde.
- **R8. Reproducción desde cero con SOLO el README:** los comandos existen y sus argumentos son válidos (`precompute_suitability.py --help` lista `--profile`, `--duration`, `--validate`). `fetch_data.py` no tiene `--help` y descarga con cualquier argumento (el README lo avisa). Sin el precálculo de idoneidad (≈240 MB, minutos) la pantalla "Mejores puntos" queda vacía y el README lo dice. Pendiente que alguien repita las descargas reales.
- **R9. Secretos y datos personales:** `grep` de claves/tokens/rutas de usuario: nada en código ni config. Hay `.claude/agents/` (4 ficheros de prompts) en el árbol. No hay datos de terceros redistribuidos (datos y kernels fuera de git).

## Lo que debe decidir el usuario

1. **Licencia del código:** no hay `LICENSE`; el README dice "pendiente".
2. **Repositorio remoto:** ninguno, el repo ni siquiera tiene un primer commit. `CLAUDE.md` prohíbe remoto sin permiso. Antes del primer commit: ignorar `S_horn.npy`, `fine_*.json`, `.coverage`.
3. **Licencias de datos (PGDA, USGS) "a verificar"** antes de la entrega y antes de cualquier redistribución.
4. **Vídeo de demo:** reejecutar `docs/guion-demo.md` con las cifras actuales (D3); el guion tiene pasos con números viejos.
5. **Si quiere buscar misiones por nombre:** decidir si se fusionan los 19 sitios de `sites.json` en el buscador (R1). Y si el score debe depender del panel elegido (R2).

## Calificación realista

Versión funcional: **B**. Sólida ingeniería científica y de pruebas, avisos de alcance consistentes. Objetivo del buscador/idoneidad: **B-/C+** (cobertura de nombres buena para cráteres, nula para misiones; score explicable pero sin calibrar). No hay fallos que bloqueen la demo; los defectos D2-D4 deberían cerrarse antes de publicar.
