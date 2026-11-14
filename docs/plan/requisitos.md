# LSI — Especificación de requisitos (SRS)

Versión 1.0 · 14/11/2026 · Responsable: Senior Project Manager. Documento vivo: cualquier cambio de alcance se registra aquí y en `tareas.md`/`tasks.json`.

Fuentes: `docs/documento-base.txt` (DB), `docs/reto-nasa.md` (Reto), `CLAUDE.md`, informes de expertos en `docs/science/` (Mat. = matematica, Paneles = paneles-y-misiones, Geo. = terreno-geologia, Luna = luna-spice-sitios) y las tres peticiones del usuario: (1) selección de paneles y % de potencia/carga según ubicación, (2) algoritmo de score de la ubicación, (3) buscador por nombre de cráteres y zonas (gazetteer).

## 1. Propósito y alcance

Lunar Site Intelligence (LSI) es una aplicación científica para el reto NASA Space Apps 2026 *Lunar Landing Site Navigator*: compara emplazamientos y fechas del polo sur lunar mostrando horizonte topográfico, Sol y Tierra (SPICE), ventanas de visibilidad, **potencia relativa de varios tipos de panel solar** y un **score explicable de calidad del emplazamiento**, con un **buscador** de cráteres y zonas cartografiadas.

**Principio rector (DB §1):** transparencia. La visibilidad es geométrica; la potencia es una estimación con supuestos declarados; el score nunca se presenta sin su desglose, su rango y su confianza.

**Fuera de alcance (Won't):** ver RF-46.

## 2. Prioridades (MoSCoW)

- **Must**: sin ello no hay MVP defendible ante el jurado.
- **Should**: aporta valor claro; se recorta solo si la puerta de calidad lo exige.
- **Could**: solo si sobra tiempo; no bloquea nada.
- **Won't**: excluido de esta entrega.

## 3. Requisitos funcionales

### 3.1 Datos y terreno

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-01 | Cargar un DEM lunar real (GeoTIFF `surf`, LOLA/PGDA 5 m/px) conservando CRS, transformación afín, nodata, unidades y metadatos, y mostrar fuente y referencia. | Must | DB §3.1, §8 (MVP) | T-004, T-007 |
| RF-02 | Obtener datos (3 sitios × 4 capas) y kernels SPICE con un único comando reproducible (`python scripts/fetch_data.py`), con manifiesto y comprobación de integridad (SHA-256); `data/raw/` y `kernels/` fuera de git. | Must | DB §7, §9; CLAUDE.md | T-003, T-058 |
| RF-03 | Convertir lat/lon lunares (MOON_ME, E-positivo) a coordenadas estereográficas polares sur del DEM y a índice de píxel, y viceversa, comprobando que el punto cae dentro de la cobertura válida. | Must | DB §3.1; Mat. §1 | T-008, T-009, T-019, T-061 |
| RF-04 | Recortar una ventana del DEM alrededor del punto de observación y muestrearlo con interpolación bilineal, con máscara nodata (nodata no es montaña ni cielo despejado). | Must | DB §3.1, §8; Mat. §2.4 | T-004, T-009 |
| RF-05 | Exponer capas auxiliares consultables y visualizables: pendiente (`slp`), conteo de retornos (`ldec`) e incertidumbre vertical (`toterr`). | Should | DB §2.1, §5; Geo. §1 | T-007, T-010, T-048 |
| RF-06 | Calcular el horizonte topográfico 360° desde un punto con curvatura lunar exacta (paso radial 5 m, azimut cada 0,25°, altura de observador 1/2/5 m, radio máximo configurable), sin tratar nodata como obstáculo. | Must | DB §3.2; Mat. §2 | T-011, T-019, T-040, T-061 |
| RF-07 | Señalar por azimut si el horizonte está truncado por la cobertura del DEM (ABIERTO/CERRADO), entregar H como cota inferior y publicar la fracción de azimuts abiertos y la distancia al borde. | Must | Geo. §6; Mat. §2.6 | T-012, T-040, T-049 |
| RF-08 | Ofrecer modo «esfera lisa» (horizonte solo por curvatura) para ubicaciones sin DEM o fuera de cobertura, etiquetado de forma explícita en toda salida. | Should | Reto (coordenadas personalizadas); Luna §3 | T-013 |

### 3.2 Astronomía, visibilidad y métricas

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-09 | Calcular con SPICE azimut, elevación, distancia y tamaño angular aparentes de Sol y Tierra para un observador fijo en MOON_ME (aberración LT+S), y validar el rango temporal 1900-01-01 a 2050-12-31 con mensaje claro fuera de él. | Must | DB §3.3; convenciones.md | T-014, T-015, T-016, T-017, T-018, T-019, T-062, T-063 |
| RF-10 | Decidir visibilidad geométrica en cada instante comparando elevación del cuerpo con H en su azimut (modelo centro del disco). | Must | DB §3.4 | T-019, T-021, T-061 |
| RF-11 | Modelar el disco finito: clasificar Sol/Tierra como completo, parcialmente oculto u oculto y devolver la fracción visible. | Should | DB §3.4 (stretch); Mat. §4 | T-021, T-032 |
| RF-12 | Generar ventanas de visibilidad con paso grueso (10 min) y refinamiento de transiciones por búsqueda de raíz (≤ 1 s), con álgebra de intervalos para solape Sol∩Tierra. | Must | DB §3.5; Mat. §5 | T-022, T-061, T-062 |
| RF-13 | Calcular las métricas del documento base: Solar Visibility, Longest Solar Window, Max Darkness, Earth Visibility, Longest Earth Window, Sun–Earth Overlap, Terrain Slope y Data Confidence (cada una por separado). | Must | DB §4.1 | T-010, T-023, T-064 |
| RF-14 | Informar de la elevación solar (mín/máx/actual), la duración de la luz solar y el tiempo restante hasta puesta de Sol / Earthset (y hasta salida/Earthrise), con los casos «sin evento» y «ya oculto». | Must | Reto #3, #4 | T-022, T-023, T-050, T-055, T-062 |

### 3.3 Sitios, coordenadas y tiempo

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-15 | Ofrecer un catálogo curado de emplazamientos (3 sitios con DEM y ubicaciones de misiones Apolo/CLPS/otros programas desde `config/sites.json`), con nivel de confianza de cada coordenada; los lat/lon `null` no son seleccionables. | Must | Reto #1; Luna §4 | T-005, T-006, T-046 |
| RF-16 | Aceptar coordenadas personalizadas (lat/lon) con validación; si caen fuera de todo DEM, usar modo esfera lisa con aviso. | Must | Reto #1 | T-005, T-013, T-026, T-045, T-046, T-058 |
| RF-17 | Permitir fecha/hora de inicio, intervalo y paso flexibles (UTC en la interfaz, ET interno) y presets de exploración de «días lunares» y estaciones polares. | Must | Reto #2; convenciones.md | T-026, T-045, T-046 |

### 3.4 Paneles solares y potencia (funcionalidad nueva 1)

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-18 | Mantener un catálogo de ≥ 6 tipos de panel solar usados o propuestos en proyectos lunares (3J GaAs de lander, array vertical en mástil, 4J/IMM, ROSA, silicio, CIGS, perovskita-Si, 3J de rover), con cada parámetro etiquetado publicado/estimado/suposición/a_verificar y su fuente. | Must | Usuario (1); Paneles §1 | T-027, T-028 |
| RF-19 | Permitir seleccionar uno o varios tipos de panel simultáneamente y su montaje (horizontal, inclinado, vertical fijo, vertical con seguimiento azimutal) y orientación. | Must | Usuario (1); Mat. §6.3 | T-028, T-029, T-031, T-056 |
| RF-20 | Calcular el % de potencia relativa por instante, P_rel = IAM·cos θ·(S(d)/S_ref)·f_T·f_rad·f_polvo·f_sombra, según radiación solar en la ubicación (Sol visible, ángulo de incidencia, distancia). | Must | Usuario (1); Mat. §6.1 | T-029, T-031, T-039, T-056, T-061, T-071 |
| RF-21 | Mostrar la evolución del % de potencia a lo largo del día y del periodo elegido para la ubicación (incluido sombreado por horizonte y disco parcial) y la energía relativa acumulada. | Must | Usuario (1); Mat. §6.6 | T-031, T-032, T-050, T-056 |
| RF-22 | Estimar la temperatura del panel por balance estacionario y su efecto en la eficiencia (f_T con tope de ganancia en frío), avisando fuera del rango de validez. | Should | Mat. §6.5; Paneles §3.4 | T-030 |
| RF-23 | Exponer polvo, degradación por radiación y eficiencia como parámetros editables, con la etiqueta `suposición` visible cuando no haya fuente. | Should | Paneles §3.5; CLAUDE.md | T-027, T-031, T-056 |
| RF-24 | Estimar el estado de carga de batería (% de carga) con capacidad y consumo configurables a partir de la serie de potencia. | Should | Usuario (1: «% de potencia/carga»); Mat. §6.8 | T-033, T-050, T-056 |
| RF-25 | Comparar paneles en un mismo sitio y comparar sitios con un mismo panel (potencia media, energía, horas sobre umbral). | Must | Usuario (1); Reto #1 | T-036, T-051, T-056 |
| RF-26 | Definir perfiles de misión (lander solar, lander con baterías, rover, base/ISRU, comunicaciones) con umbrales editables y etiquetados por confianza. | Must | Paneles §2 | T-034, T-035 |

### 3.5 Score de la ubicación (funcionalidad nueva 2)

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-27 | Normalizar a [0,1] los subindicadores del score: s_sol, s_noche, s_tierra, s_terreno, con parámetros en `config/score.yaml`. | Must | Usuario (2); Mat. §7.1 | T-037, T-041 |
| RF-28 | Aplicar puertas duras (sin energía, pendiente excesiva, datos insuficientes) que producen estado «no apto»/«sin datos suficientes» con motivo, sin ocultar el score. | Must | Mat. §7.2 | T-037, T-041 |
| RF-29 | Agregar con media geométrica ponderada (ε_s = 0,01) con pesos por perfil, editables por el usuario y renormalizados. | Must | Usuario (2); Mat. §7.3–7.4 | T-037, T-041, T-057, T-061, T-064 |
| RF-30 | Entregar el score como rango S_nominal [S_min, S_max] según escenarios de incertidumbre (cobertura, σz, discretización; clones si existen). | Should | DB §4.3; Mat. §7.5 | T-025, T-038, T-057 |
| RF-31 | Calcular y mostrar la etiqueta de Data Confidence (alta/media/baja) a partir de g90, e90, cobertura de horizonte y rango del score, sin entrar en el producto de S. | Must | DB §4.3; Geo. §2.3 | T-024, T-038, T-040, T-057 |
| RF-32 | Desglosar el score: valor medido, s_i, peso, contribución a la penalización, «S si s_i = 1», eslabón más débil, gates y supuestos. | Must | DB §4.4; Mat. §7.6 | T-037, T-051, T-057 |
| RF-33 | Permitir que s_sol use la potencia efectiva del panel seleccionado (fracción de tiempo con P_rel ≥ umbral del perfil) en lugar de solo visibilidad geométrica. | Should | Usuario (1)+(2) | T-039 |
| RF-34 | Evaluar sensibilidad con clones DEM de PGDA (K ≥ 5) y publicar percentiles P5–P95. | Could | DB §2.1 (stretch) | T-025 |

### 3.6 Interfaz, exportación y alcance

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-35 | Pantalla A «Lunar Explorer»: terreno 3D con relieve y escala, marcadores de sitios, selección del punto y altura del observador, capas elevación/pendiente/incertidumbre/calidad de muestreo, panel de coordenadas y metadatos. | Must | DB §5 A; Reto #5 | T-048, T-053, T-060, T-068, T-069 |
| RF-36 | Mapa 2D del recorte (hillshade + capas) coordinado con la vista 3D. | Must | Reto #5 | T-048, T-053, T-069 |
| RF-37 | Pantalla B «Horizon & Visibility»: perfil de horizonte polar y cartesiano, marcadores de Sol y Tierra, estado visible/parcial/bloqueado, sectores truncados rayados, control de fecha/hora. | Must | DB §5 B | T-049, T-054, T-060, T-068, T-069 |
| RF-38 | Pantalla C «Mission Timeline»: bandas Sol/Tierra/solape, duración y mayor ventana, zoom en transiciones, curva de potencia, tiempo hasta sunset/Earthset y aviso de visibilidad geométrica. | Must | DB §5 C; Reto #3, #6 | T-050, T-055, T-060, T-068, T-069 |
| RF-39 | Animación/reproducción del tiempo (play/pausa/velocidad) sincronizada entre horizonte, mapa y timeline. | Should | Reto #6 | T-055 |
| RF-40 | Pantalla «Paneles y potencia»: selector multi-panel, montaje, parámetros editables, curva de % potencia y de % carga a lo largo del día, comparación entre paneles. | Must | Usuario (1) | T-056, T-060, T-068, T-069 |
| RF-41 | Pantalla D «Comparación y Score»: tres sitios lado a lado con métricas solares, terrestres, terreno y confianza por separado, pesos editables, score transparente con rango. | Must | DB §5 D; Usuario (2) | T-051, T-057, T-060, T-068, T-069 |
| RF-42 | Modos de usuario (público/educador, planificador, ingeniero) con glosario y explicaciones progresivas sobre los mismos datos. | Must | Reto #7 | T-042, T-044, T-047, T-069, T-077 |
| RF-43 | Exportar resultados y score a CSV/JSON con metadatos (DEM, kernels, parámetros) y avisos de alcance. | Should | DB §5 D | T-052, T-057 |
| RF-44 | Mostrar siempre avisos de alcance (visibilidad geométrica ≠ potencia real ≠ enlace RF), etiquetas `a verificar`/`suposición` y limitaciones; figuras sintéticas marcadas como ilustrativas. | Must | DB §1, §4.2, §10; CLAUDE.md | T-043, T-047, T-053, T-054, T-055, T-056, T-057, T-059, T-071, T-075, T-076, T-077, T-078, T-079 |
| RF-45 | Usar una ventana LOLA de 20 m (±60 km) para acotar el horizonte lejano en azimuts ABIERTOS. Diferido a post-entrega: sin tarea en este plan (descarga ≈ 1,8 GB). | Won't | Geo. §6.3 | n/a (Won't) |
| RF-46 | FUERA DE ALCANCE (Won't): presupuesto de enlace RF, dimensionamiento de paneles/baterías en unidades absolutas, rutas de rover, diseño de base, modelos térmicos detallados del suelo, IA generativa en el núcleo, SDEM, backend distribuido. | Won't | DB §1 «Fuera del MVP» | n/a (Won't) |

### 3.7 Buscador de cráteres y zonas (ampliación)

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RF-47 | Buscador por nombre de cráteres y zonas lunares cartografiadas (gazetteer IAU/USGS en `data/processed/gazetteer.csv`): búsqueda sin acentos ni mayúsculas, difusa (difflib), con filtro por tipo de rasgo y región, límite de resultados y `get_by_name`; cada entrada con nombre, tipo, lat, lon, diámetro, origen/aprobación y referencia de cuadrángulo. | Must | Usuario (ampliación); coordinador | T-058, T-059 |
| RF-48 | Convertir una entrada del gazetteer en «sitio evaluable»: con DEM si lat/lon→x,y cae dentro de la cobertura válida de algún GeoTIFF y sin DEM (modo esfera lisa) en caso contrario; en este último caso el score se etiqueta «sin datos de terreno» y no se presenta como comparable con los sitios con DEM. | Must | Usuario (ampliación); coordenadas personalizadas | T-037, T-058, T-059 |

## 4. Requisitos no funcionales

| ID | Requisito | Prioridad | Fuente | Tareas |
|---|---|---|---|---|
| RNF-01 | Rendimiento del núcleo (objetivos a medir en T-benchmark, hardware de laptop): horizonte de un punto ≤ 10 s; timeline de 30 días a 10 min con refinamiento ≤ 20 s; curvas de potencia de 3 paneles ≤ 5 s adicionales. | Should | DB §8 (riesgo ray casting) | T-065, T-066 |
| RNF-02 | Interacción de la UI: respuesta ≤ 2 s al cambiar fecha, panel o pesos con resultados en caché; operaciones largas con indicador de progreso. | Should | Reto #7 | T-060, T-065, T-066 |
| RNF-03 | Determinismo: misma entrada y mismos kernels/DEM producen resultado idéntico (bit a bit en métricas); sin aleatoriedad sin semilla fija. | Must | DB §6; CLAUDE.md | T-016, T-022, T-026, T-064, T-066, T-067 |
| RNF-04 | Reproducibilidad: entorno limpio con Python 3.11 y versiones fijadas en `requirements.txt` arranca con `pip install -r requirements.txt`, `fetch_data.py` y `streamlit run app.py`. | Must | DB §9 checklist | T-001, T-002, T-003, T-067, T-074, T-078, T-080 |
| RNF-05 | Honestidad científica: ninguna cifra física sin fuente o etiqueta `a verificar`/`suposición`; no afirmar potencia real ni enlace RF; sesgo optimista del DEM finito declarado. | Must | CLAUDE.md; DB §10 | T-006, T-012, T-020, T-024, T-025, T-027, T-030, T-034, T-040, T-041, T-047, T-070, T-071, T-072, T-074, T-075, T-076, T-078, T-079, T-080 |
| RNF-06 | Accesibilidad (WCAG 2.1 AA como objetivo): contraste ≥ 4,5:1, paleta apta para daltonismo, información no codificada solo por color, texto alternativo de figuras, uso con teclado de los controles principales. | Should | Reto #7 | T-042, T-043, T-049, T-059, T-069 |
| RNF-07 | Internacionalización: interfaz en español (por defecto) con claves preparadas para inglés; paridad de claves verificada por test. | Could | Usuario (español/inglés si cabe) | T-044 |
| RNF-08 | Tolerancias de validación del matemático (Mat. §8.1): proyección ≤ 1e-6 m; horizonte vs analítico ≤ 1e-4°; Sol vs Horizons ≤ 0,01° (aceptable 0,02°); Tierra ≤ 0,02° (0,05°); eventos ≤ 1 s; potencia ≤ 1e-4 en P_rel; score ≤ 0,05 puntos. | Must | Mat. §8 | T-008, T-011, T-015, T-016, T-017, T-018, T-020, T-029, T-031, T-033, T-037, T-061, T-062, T-063, T-072 |
| RNF-09 | Arquitectura: monolito modular `src/lsi/{data,terrain,astronomy,simulation,energy,analysis,visualization}`; solo `app.py` y `ui/` importan streamlit; `visualization/` puede usar plotly pero no streamlit; el núcleo no importa ni streamlit ni plotly. | Must | DB §6; CLAUDE.md | T-001, T-044, T-070 |
| RNF-10 | Calidad: cada función con lógica deja un test pytest con valor esperado independiente; suite completa en < 5 min sin red; sin tests que dependan de resultados del propio motor como oráculo único. | Must | CLAUDE.md; DB §8 | T-007, T-011, T-017, T-058, T-061, T-064, T-068, T-070, T-072, T-073 |
| RNF-11 | Trazabilidad: cada resultado lleva metadatos (versión de kernels, DEM, marco, parámetros, modo esfera/DEM, fecha de cálculo). | Must | DB §6 (metadatos explícitos) | T-004, T-014, T-026, T-052, T-063 |
| RNF-12 | Recursos: un recorte de 16–21 km (≈ 164–282 MB por sitio) se procesa en memoria con < 4 GB de RAM de pico (objetivo a medir). | Should | Geo. §6.3 | T-065 |
| RNF-13 | Repositorio ligero: sin datos ni kernels en git; procedencia y condiciones de uso de datos/kernels documentadas; ningún remoto sin permiso del usuario. | Must | CLAUDE.md; DB §9 | T-001, T-003, T-058, T-076, T-080 |

### 4.1 Tolerancias de validación (resumen de Mat. §8.1)

| Motor / prueba | Tolerancia |
|---|---|
| Proyección directa vs fórmula/pyproj | ≤ 1·10⁻⁶ m |
| Ida y vuelta lat/lon | ≤ 1·10⁻⁹ ° |
| Horizonte vs analítico (H1–H5) | ≤ 1·10⁻⁴ ° |
| Horizonte DEM real, ΔA 0,125° vs 0,25° | ≤ 0,06 ° (documentar) |
| Sol (az, el) vs Horizons | ≤ 0,01 ° objetivo; ≤ 0,02 ° aceptable |
| Tierra (az, el) vs Horizons | ≤ 0,02 ° objetivo; ≤ 0,05 ° aceptable |
| Distancias Sol/Tierra vs Horizons | ≤ 1·10⁻⁵ relativa |
| Fracción visible de disco (plano) | ≤ 1·10⁻⁴ |
| Tiempos de evento (raíz) | ≤ 1 s |
| Ventanas Δ=5 vs Δ=10 min | mismo conjunto ± 2 s |
| Potencia P_rel (casos §6.7) | ≤ 1·10⁻⁴ absoluto |
| Integración de energía eventos vs rejilla 1 min | ≤ 0,5 % |
| Batería (caso §6.8) | ≤ 0,1 Wh |
| Score (ejemplo §7.7) | ≤ 0,05 puntos |

Los valores marcados «objetivo» se confirman en la primera comparación con Horizons (Mat. §9.1); el DEM finito, DE421 vs DE441 y el marco de coordenadas de sitio en Horizons están `a verificar`.

## 5. Restricciones

- **RC-01** Ventana del evento: sábado 14/11/2026 09:00 a domingo 15/11/2026 23:59 (Madrid); entrega con margen antes del cierre. Presupuesto de referencia del documento base: 24 h efectivas.
- **RC-02** Stack: Python 3.11, Streamlit, Plotly, rasterio/GDAL, NumPy/SciPy, SpiceyPy, pandas, pytest, pyproj (+ PyYAML para `score.yaml`). Sin microservicios, sin IA generativa en el núcleo.
- **RC-03** Convenciones físicas fijadas en `docs/science/convenciones.md` (azimut N→E, elevación 0° plano local, MOON_ME, LT+S, UTC/ET, R = 1737,4 km). Cambiarlas exige actualizar ese fichero y los tests.
- **RC-04** Ficheros disponibles: DEM de 3 sitios (Site04 Shackleton, Site11 de Gerlache, Site23 Malapert; capas surf, slp, ldec, toterr) y 6 kernels en `kernels/`.
- **RC-05** Con agentes en paralelo cada tarea escribe solo los ficheros que le asigna `tareas.md`; prohibido `git add -A`/`git add .`.
- **RC-06** Rango temporal soportado por el BPC lunar: 1900-01-01 a 2050-12-31 23:58:51; fuera de él el motor rechaza la petición.
- **RC-07** Sin acceso garantizado a red en las pruebas: los casos de JPL Horizons se versionan en `tests/data/` y la descarga en vivo es opcional.

## 6. Supuestos

- **S-01** El centro de cada sitio lo fija el código leyendo el GeoTIFF; las lat/lon de `sites.json` para Site04/11/23 son aproximadas (centro del cráter).
- **S-02** La potencia relativa se refiere a la potencia nominal con el Sol de frente (on-sun) del panel; no es potencia absoluta ni dimensionamiento (Won't RF-46).
- **S-03** Los umbrales del score y de los perfiles de misión son «a calibrar con experto» salvo los marcados como publicados; la UI los muestra editables.
- **S-04** Un DEM finito solo puede sobrestimar la iluminación (sesgo optimista de signo conocido); se declara, no se corrige salvo opción RF-45.
- **S-05** DE421 (motor) frente a DE441 (Horizons): se aceptan diferencias ≲ 0,05″; no se exige menos.
- **S-06** Los eclipses lunares y la sombra propia del lander no se modelan como pérdida de potencia por defecto; se mencionan en limitaciones.
- **S-07** Los 100 clones del DEM y el SDEM no están descargados; RF-34 se activa solo si hay tiempo.

## 7. Criterios de aceptación del MVP (DB §8, ampliados)

- La app muestra un recorte de terreno lunar real con fuente y referencia (RF-01, RF-35).
- El horizonte 360° se genera desde un punto que el usuario elige, con truncado señalizado (RF-06, RF-07, RF-37).
- Sol y Tierra salen de SPICE y se contrastan con Horizons dentro de tolerancia (RF-09, RNF-08).
- La visibilidad compara elevación y horizonte en el azimut correspondiente (RF-10).
- El timeline muestra ventanas, duraciones y cuenta atrás hasta sunset/Earthset (RF-12, RF-14, RF-38).
- La comparación presenta tres candidatos con indicadores y confianza separados (RF-13, RF-31, RF-41).
- El usuario elige uno o varios paneles y ve el % de potencia y de carga a lo largo del día en su ubicación (RF-19–RF-24, RF-40).
- El score aparece con desglose, pesos editables, rango y confianza; las ubicaciones sin DEM se etiquetan «sin datos de terreno» (RF-27–RF-32, RF-48).
- El buscador localiza cráteres por nombre con tolerancia a erratas y los convierte en sitio evaluable (RF-47, RF-48).
- Las limitaciones se explican sin exagerar la precisión (RF-44, RNF-05).

## 8. Matriz de trazabilidad requisito → tarea → prueba

Las pruebas son los ficheros `tests/` e informes `docs/validation/` de las tareas que cubren el requisito (generado desde `tasks.json`).

| Requisito | Prio. | Tareas | Pruebas / evidencia |
|---|---|---|---|
| RF-01 | Must | T-004, T-007 | `tests/test_loader.py`<br>`tests/test_data_integrity.py`<br>`docs/validation/hito0-datos.md` |
| RF-02 | Must | T-003, T-058 | `tests/test_fetch_manifest.py`<br>`tests/test_gazetteer.py`<br>`tests/test_evaluable.py`<br>`tests/test_fetch_gazetteer.py` |
| RF-03 | Must | T-008, T-009, T-019, T-061 | `tests/test_projection.py`<br>`tests/test_dem.py`<br>`docs/validation/hito1-site04.md`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py`<br>`docs/validation/rev-matematico.md` |
| RF-04 | Must | T-004, T-009 | `tests/test_loader.py`<br>`tests/test_dem.py` |
| RF-05 | Should | T-007, T-010, T-048 | `tests/test_data_integrity.py`<br>`docs/validation/hito0-datos.md`<br>`tests/test_slope.py`<br>`tests/test_lunar_map.py` |
| RF-06 | Must | T-011, T-019, T-040, T-061 | `tests/test_horizon.py`<br>`docs/validation/hito1-site04.md`<br>`tests/test_horizon_los.py`<br>`docs/validation/rev-geologo.md`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py` (+1 más) |
| RF-07 | Must | T-012, T-040, T-049 | `tests/test_horizon_coverage.py`<br>`tests/test_horizon_los.py`<br>`docs/validation/rev-geologo.md`<br>`tests/test_horizon_chart.py` |
| RF-08 | Should | T-013 | `tests/test_sphere_horizon.py` |
| RF-09 | Must | T-014, T-015, T-016, T-017, T-018, T-019, T-062, T-063 | `tests/test_spice_engine.py`<br>`tests/test_coordinates.py`<br>`tests/test_ephemeris.py`<br>`tests/test_validation_horizons.py`<br>`docs/validation/hito1-site04.md`<br>`tests/test_luna_cases.py` (+2 más) |
| RF-10 | Must | T-019, T-021, T-061 | `docs/validation/hito1-site04.md`<br>`tests/test_visibility.py`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py`<br>`docs/validation/rev-matematico.md` |
| RF-11 | Should | T-021, T-032 | `tests/test_visibility.py`<br>`tests/test_illumination.py` |
| RF-12 | Must | T-022, T-061, T-062 | `tests/test_timeline.py`<br>`tests/test_events.py`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py`<br>`docs/validation/rev-matematico.md`<br>`tests/test_luna_cases.py` (+1 más) |
| RF-13 | Must | T-010, T-023, T-064 | `tests/test_slope.py`<br>`tests/test_metrics.py`<br>`tests/test_regression_sites.py` |
| RF-14 | Must | T-022, T-023, T-050, T-055, T-062 | `tests/test_timeline.py`<br>`tests/test_events.py`<br>`tests/test_metrics.py`<br>`tests/test_timeline_chart.py`<br>`tests/test_luna_cases.py`<br>`docs/validation/rev-experto-luna.md` |
| RF-15 | Must | T-005, T-006, T-046 | `tests/test_sites.py`<br>`docs/validation/rev-catalogo.md` |
| RF-16 | Must | T-005, T-013, T-026, T-045, T-046, T-058 | `tests/test_sites.py`<br>`tests/test_sphere_horizon.py`<br>`tests/test_runner.py`<br>`tests/test_validation_inputs.py`<br>`tests/test_gazetteer.py`<br>`tests/test_evaluable.py` (+1 más) |
| RF-17 | Must | T-026, T-045, T-046 | `tests/test_runner.py`<br>`tests/test_validation_inputs.py` |
| RF-18 | Must | T-027, T-028 | `docs/validation/rev-paneles.md`<br>`tests/test_panels.py` |
| RF-19 | Must | T-028, T-029, T-031, T-056 | `tests/test_panels.py`<br>`tests/test_incidence.py`<br>`tests/test_iam.py`<br>`tests/test_power.py` |
| RF-20 | Must | T-029, T-031, T-039, T-056, T-061, T-071 | `tests/test_incidence.py`<br>`tests/test_iam.py`<br>`tests/test_power.py`<br>`tests/test_solar_effective.py`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py` (+2 más) |
| RF-21 | Must | T-031, T-032, T-050, T-056 | `tests/test_power.py`<br>`tests/test_illumination.py`<br>`tests/test_timeline_chart.py` |
| RF-22 | Should | T-030 | `tests/test_thermal.py` |
| RF-23 | Should | T-027, T-031, T-056 | `docs/validation/rev-paneles.md`<br>`tests/test_power.py` |
| RF-24 | Should | T-033, T-050, T-056 | `tests/test_battery.py`<br>`tests/test_timeline_chart.py` |
| RF-25 | Must | T-036, T-051, T-056 | `tests/test_panel_compare.py`<br>`tests/test_comparison_chart.py` |
| RF-26 | Must | T-034, T-035 | `docs/validation/rev-perfiles.md`<br>`tests/test_profiles.py` |
| RF-27 | Must | T-037, T-041 | `tests/test_ranking.py`<br>`tests/test_explain.py`<br>`docs/validation/calibracion-score.md` |
| RF-28 | Must | T-037, T-041 | `tests/test_ranking.py`<br>`tests/test_explain.py`<br>`docs/validation/calibracion-score.md` |
| RF-29 | Must | T-037, T-041, T-057, T-061, T-064 | `tests/test_ranking.py`<br>`tests/test_explain.py`<br>`docs/validation/calibracion-score.md`<br>`tests/test_math_golden.py`<br>`tests/test_score_properties.py`<br>`docs/validation/rev-matematico.md` (+1 más) |
| RF-30 | Should | T-025, T-038, T-057 | `tests/test_uncertainty.py`<br>`tests/test_clones.py`<br>`tests/test_score_range.py` |
| RF-31 | Must | T-024, T-038, T-040, T-057 | `tests/test_confidence.py`<br>`tests/test_score_range.py`<br>`tests/test_horizon_los.py`<br>`docs/validation/rev-geologo.md` |
| RF-32 | Must | T-037, T-051, T-057 | `tests/test_ranking.py`<br>`tests/test_explain.py`<br>`tests/test_comparison_chart.py` |
| RF-33 | Should | T-039 | `tests/test_solar_effective.py` |
| RF-34 | Could | T-025 | `tests/test_uncertainty.py`<br>`tests/test_clones.py` |
| RF-35 | Must | T-048, T-053, T-060, T-068, T-069 | `tests/test_lunar_map.py`<br>`tests/test_app_smoke.py`<br>`docs/validation/qa-visual.md` |
| RF-36 | Must | T-048, T-053, T-069 | `tests/test_lunar_map.py`<br>`docs/validation/qa-visual.md` |
| RF-37 | Must | T-049, T-054, T-060, T-068, T-069 | `tests/test_horizon_chart.py`<br>`tests/test_app_smoke.py`<br>`docs/validation/qa-visual.md` |
| RF-38 | Must | T-050, T-055, T-060, T-068, T-069 | `tests/test_timeline_chart.py`<br>`tests/test_app_smoke.py`<br>`docs/validation/qa-visual.md` |
| RF-39 | Should | T-055 | — |
| RF-40 | Must | T-056, T-060, T-068, T-069 | `tests/test_app_smoke.py`<br>`docs/validation/qa-visual.md` |
| RF-41 | Must | T-051, T-057, T-060, T-068, T-069 | `tests/test_comparison_chart.py`<br>`tests/test_app_smoke.py`<br>`docs/validation/qa-visual.md` |
| RF-42 | Must | T-042, T-044, T-047, T-069, T-077 | `tests/test_i18n.py`<br>`docs/validation/qa-visual.md` |
| RF-43 | Should | T-052, T-057 | `tests/test_export.py` |
| RF-44 | Must | T-043, T-047, T-053, T-054, T-055, T-056, T-057, T-059, T-071, T-075, T-076, T-077, T-078, T-079 | `docs/validation/rev-expertos-final.md` |
| RF-45 | Won't | n/a | n/a |
| RF-47 | Must | T-058, T-059 | `tests/test_gazetteer.py`<br>`tests/test_evaluable.py`<br>`tests/test_fetch_gazetteer.py` |
| RF-48 | Must | T-037, T-058, T-059 | `tests/test_ranking.py`<br>`tests/test_explain.py`<br>`tests/test_gazetteer.py`<br>`tests/test_evaluable.py`<br>`tests/test_fetch_gazetteer.py` |
| RF-46 | Won't | n/a | n/a |
| RNF-01 | Should | T-065, T-066 | `tests/test_performance.py`<br>`docs/validation/rendimiento.md` |
| RNF-02 | Should | T-060, T-065, T-066 | `tests/test_performance.py`<br>`docs/validation/rendimiento.md` |
| RNF-03 | Must | T-016, T-022, T-026, T-064, T-066, T-067 | `tests/test_ephemeris.py`<br>`tests/test_timeline.py`<br>`tests/test_events.py`<br>`tests/test_runner.py`<br>`tests/test_regression_sites.py`<br>`tests/test_determinism.py` |
| RNF-04 | Must | T-001, T-002, T-003, T-067, T-074, T-078, T-080 | `tests/conftest.py`<br>`tests/test_environment.py`<br>`tests/test_fetch_manifest.py`<br>`tests/test_determinism.py`<br>`docs/validation/reality-check.md` |
| RNF-05 | Must | T-006, T-012, T-020, T-024, T-025, T-027, T-030, T-034, T-040, T-041, T-047, T-070, T-071, T-072, T-074, T-075, T-076, T-078, T-079, T-080 | `docs/validation/rev-catalogo.md`<br>`tests/test_horizon_coverage.py`<br>`docs/validation/gate-h1.md`<br>`tests/test_confidence.py`<br>`tests/test_uncertainty.py`<br>`tests/test_clones.py` (+10 más) |
| RNF-06 | Should | T-042, T-043, T-049, T-059, T-069 | `tests/test_horizon_chart.py`<br>`docs/validation/qa-visual.md` |
| RNF-07 | Could | T-044 | `tests/test_i18n.py` |
| RNF-08 | Must | T-008, T-011, T-015, T-016, T-017, T-018, T-020, T-029, T-031, T-033, T-037, T-061, T-062, T-063, T-072 | `tests/test_projection.py`<br>`tests/test_horizon.py`<br>`tests/test_coordinates.py`<br>`tests/test_ephemeris.py`<br>`tests/test_validation_horizons.py`<br>`docs/validation/gate-h1.md` (+12 más) |
| RNF-09 | Must | T-001, T-044, T-070 | `tests/conftest.py`<br>`tests/test_i18n.py`<br>`tests/test_architecture_imports.py`<br>`docs/validation/code-review.md` |
| RNF-10 | Must | T-007, T-011, T-017, T-058, T-061, T-064, T-068, T-070, T-072, T-073 | `tests/test_data_integrity.py`<br>`docs/validation/hito0-datos.md`<br>`tests/test_horizon.py`<br>`tests/test_gazetteer.py`<br>`tests/test_evaluable.py`<br>`tests/test_fetch_gazetteer.py` (+8 más) |
| RNF-11 | Must | T-004, T-014, T-026, T-052, T-063 | `tests/test_loader.py`<br>`tests/test_spice_engine.py`<br>`tests/test_runner.py`<br>`tests/test_export.py`<br>`docs/validation/validacion-horizons.md` |
| RNF-12 | Should | T-065 | `tests/test_performance.py`<br>`docs/validation/rendimiento.md` |
| RNF-13 | Must | T-001, T-003, T-058, T-076, T-080 | `tests/conftest.py`<br>`tests/test_fetch_manifest.py`<br>`tests/test_gazetteer.py`<br>`tests/test_evaluable.py`<br>`tests/test_fetch_gazetteer.py` |
