# Datos térmicos (Diviner) y regiones permanentemente sombreadas (PSR)

Fecha: 14/11/2026. Código: `src/lsi/data/thermal.py`, `src/lsi/data/psr.py`; descarga: `scripts/fetch_thermal_psr.py` (`--help` no descarga; reanudable; rechaza HTML con código 200; verifica tamaño; SHA-256 en `data/raw/<dir>/SHA256SUMS.json`; rechaza todo fichero de más de `--max-mb`, 500 por defecto). Tests: `tests/test_thermal_psr.py` (9, se omiten sin datos). **No se ha tocado el motor ni `panels.json`.**

## 1. Temperatura de superficie: LRO Diviner, mapas estacionales del polo sur

| Campo | Valor |
|---|---|
| Producto elegido | Williams et al. (2019) «Seasonal polar temperatures on the Moon», mapas derivados `polar_south_80_{summer,winter}_{avg,max,min}-float.tif` |
| URL oficial | http://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar/additional_maps/ (descripción: `.../level4_polar/aareadme.txt`); los datos de base están en el PDS Geosciences Node, bundle `urn:nasa:pds:lro_diviner_derived1` |
| Qué mide | Temperatura de brillo **bolométrica** de la superficie, radiancias nadir del RDR 2009-07-05 a 2019-02-17, agrupadas por hora local y longitud subsolar, en dos épocas del año: «summer»/«winter» = latitud subsolar por encima/por debajo del ecuador (no son estaciones del hemisferio sur). Máximo, mínimo y medio del ciclo diurno |
| Malla | 2533 × 2533 px, **240,036 m/px**, cubre ±304 km (≥ 80°S), float32, NaN = sin dato (21 % del raster). Estereográfica polar sur, esfera de 1737,4 km, `lat_ts = −90`: la misma que el DEM de LSI (se comprobó en el cráter Shackleton, PSR fría, y en Malapert, caliente: orientación correcta) |
| Formato | GeoTIFF float32 (lectura por ventana con rasterio; los `.grd` originales de GMT no hacen falta) |
| Tamaño real descargado | 6 ficheros × 25 686 193 B = **154 117 158 B (147 MiB)**, comprobado el tamaño antes (listado del servidor: 24 M cada uno). SHA-256 en `data/raw/diviner/SHA256SUMS.json` |
| Licencia | La página no declara condiciones propias. Datos de la misión NASA LRO (política general de NASA, ver `docs/fuentes-datos.md`). **A verificar** |
| Cita | Williams, J.-P., Greenhagen, B. T., Paige, D. A., Schorghofer, N., Sefton-Nash, E., Hayne, P. O., Lucey, P. G., Siegler, M. A., Aye, K.-M. (2019), J. Geophys. Res. Planets 124, 2505-2521, doi:10.1029/2019JE006028 |

Descartados (leídos): los mapas de radiancia de 24×6 bins (`24x6_240m`, Schorghofer y Williams 2020) son radiancia en bins subsolares, no temperatura máxima/mínima; el GDR_L2 del PDS (`DGDR_*_POLS`) llega solo a 75°S, en temperaturas de brillo por canal y ciclo de mapeo; el Level 3 de 240 m (anuncio de 2022) es un binning de radiancias por canal, más trabajoso de convertir. El producto elegido es el único hallado que da max/min/medio ya como temperatura, en GeoTIFF y con la proyección del DEM.

### API: `thermal_window(site_key, center_x_m, center_y_m, half_size_m, max_px, kind='mean'|'max'|'min') -> dict | None`

Malla de `n×n` píxeles (`n = min(max_px, ceil(2·half/240 m))`, paso `2·half/n`), centrada en (x, y), convención `DemWindow` (`x0_m, y0_m` = centro del píxel [0, 0], filas hacia y negativa). Interpolación bilineal; `data` float32 en **K**, NaN = nodata; claves `units`, `nodata`, `attribution`, `definition`, `native_pixel_m`. `max` = máximo de los máximos de las dos épocas, `min` = mínimo de los mínimos, `mean` = media de los dos promedios (pesos iguales: aproximación, cada época dura ≈ medio año). `thermal_at(x, y, kind)` da el valor puntual. Devuelve `None` si faltan los datos o no hay solape.

### Temperaturas en los puntos clave (K)

«TOP-1» = primer puesto del mapa de idoneidad `lander_solar_no_rhu` (365 d, 2 m, malla de 250 m) de `data/processed/suitability`; es el «mejor punto» de cada recorte. Para Shackleton, de Gerlache y Malapert coinciden con los TOP-1 de Site04, Site11 y Site23.

| Punto | x, y (m) | lat, lon E | T máx | T media | T mín | Distancia al borde PSR (m; − = dentro) |
|---|---|---|---|---|---|---|
| Site04 centro del recorte | −1000, −7000 | −89,767, 188,13 | 272,9 | 91,0 | 46,8 | +754 |
| **Site04 TOP-1** (mejor punto Shackleton) | −7698, −10 802 | −89,563, 215,47 | 230,8 | 140,1 | 54,0 | +7969 |
| Site11 centro del recorte | −37 000, 15 000 | −88,683, 292,07 | 218,5 | 141,6 | 52,8 | +12 474 |
| **Site11 TOP-1** (mejor punto de Gerlache) | −43 448, 17 698 | −88,453, 292,16 | 239,9 | 148,1 | 57,9 | +9087 |
| Site23 centro del recorte | −500, 121 500 | −85,995, 359,76 | 191,2 | 102,2 | 44,2 | +27 012 |
| **Site23 TOP-1** (mejor punto Malapert) | −4948, 122 198 | −85,969, 357,68 | 228,8 | 138,8 | 53,0 | +22 859 |
| Suelo de Shackleton (gazetteer −89,67, 129,78) | 7690, −6403 | −89,67, 129,78 | 95,5 | 61,8 | 39,5 | −7860 |
| Centro de Gerlache (gazetteer −88,5, −87,1) | −45 429, 2301 | −88,5, −87,1 | 95,9 | 55,4 | 31,8 | +364 |
| Malapert (gazetteer −85,98, −1,67) | −3554, 121 898 | −85,98, −1,67 | 252,3 | 132,3 | 54,7 | +24 130 |
| Polo sur | 0, 0 | −90 | 249,0 | 124,0 | 57,0 | +1926 |

Contraste con lo publicado: el suelo de Shackleton (PSR) sale con máx. 95 K y mín. 40 K, coherente con las temperaturas muy bajas de las trampas frías (Paige et al. 2010 dan 38 K; esa cifra figura ya en `config/simulation.json`, no se ha releído aquí el artículo). Los mínimos globales del raster (6,6-6,9 K) son valores aislados fuera de los recortes y no se usan: dentro de los tres recortes el mínimo de Diviner es 30 K (PSR de Shackleton, p5).

Distribución en cada recorte (píxeles de 240 m con iluminación media publicada > 0,4, ver `contraste-iluminacion-publicada.md`; percentiles 5-50-95):

| Recorte | n px | T máx | T media | T mín |
|---|---|---|---|---|
| Site04 | 122 | 232 · 275 · 300 | 135 · 165 · 179 | 56 · 66 · 71 |
| Site11 | 458 | 232 · 260 · 291 | 130 · 146 · 156 | 55 · 67 · 78 |
| Site23 | 3021 | 237 · 291 · 312 | 133 · 162 · 173 | 61 · 77 · 82 |
| Site04, solo PSR (1541 px) | | 86 · 96 · 105 | 58 · 62 · 65 | 30 · 35 · 39 |

## 2. Propuesta para acotar T_amb de los paneles (NO aplicada)

**Qué es T_amb en el motor.** `panels.panel_temperature_k`: `T = (q + T_amb⁴)^¼` con `q = (α−η)·G / ((ε_f+ε_b)·σ)`. Es la temperatura de un sumidero radiativo común a las dos caras. Un panel vertical sobre terreno plano ve el regolito con factor de forma F ≈ 0,5 por cara y el cielo (≈ 3 K) con el resto, luego `T_amb ≈ F^¼ · T_regolito ≈ 0,84 · T_regolito` (con relieve circundante, F cambia: paredes de cráter cálidas lo suben, un fondo de PSR lo baja). **Esa conversión es una suposición geométrica de LSI [sup], no una cifra publicada**: no se ha encontrado fuente primaria de la temperatura de sumidero de un panel; Diviner solo acota la temperatura del regolito.

**Qué dice Diviner (§1) de la temperatura del regolito en terreno iluminado:** media del ciclo diurno 146-165 K (p50 de las tres zonas), máxima diurna 260-291 K (p50) y 300-312 K (p95). La media incluye la noche; durante la fase iluminada, que es cuando importa para un panel, el regolito está entre la media y el máximo.

| Escenario | T_regolito (K) | T_amb = 0,84 · T (K) |
|---|---|---|
| Entorno frío (suelo de PSR, media p50) | 62 | ≈ 52 |
| Entorno iluminado, **media diurna** (p50 de las zonas) | 146-165 | **≈ 123-139** |
| Entorno iluminado, **máximo diurno** (p95) | 291-312 | ≈ 244-262 |

**Propuesta:** nominal **130 K** (0,84 × la media diurna de terreno iluminado, ≈ 155 K), banda **40-250 K** frente a la actual 40-200 K. Razones: (a) el techo de 200 K del motor, atribuido a Fisher et al. 2017, queda por debajo del 0,84 · T_máx de Diviner en terreno iluminado (244-262 K): subestima el extremo cálido, que es el pesimista para la potencia; (b) el nominal de 100 K queda por debajo de la media diurna de terreno iluminado, por lo que el nominal de 130 K es una cota inferior de lo que se espera durante la fase iluminada (entre 130 y ~250 K); (c) 40 K se mantiene: el regolito en PSR llega a 30-40 K y un panel que mira al cielo frío se acerca a ese sumidero. Efecto ilustrativo en un panel a incidencia normal (G = 1361 W/m², **α = 0,8, ε = 0,85 por cara, η = 0,30 SUPUESTOS**, no un panel del catálogo): T del panel = 289,9 K (T_amb 40 K), 290,9 (100), 292,8 (130), 305,1 (200), 323,6 K (250). Es decir, el nominal apenas mueve la temperatura del panel (+2 K sobre 100 K), pero el techo de 250 K sí (+33 K), lo que, con el coeficiente de temperatura de cada panel, abre la banda de potencia por abajo. Para decidir el nominal haría falta el factor de forma real con el horizonte del DEM (cálculo posible con los horizontes de LSI) y una medida de temperatura durante la fase iluminada, no de ciclo completo.

## 3. PSR publicadas

| Campo | Valor |
|---|---|
| Producto elegido | Polígonos de las PSR del polo sur de **Mazarico et al. (2011)** (LOLA), digitalizados por LROC/ASU: `LOLA_PSR_75S_120M_82S_060M_5KM2_FINAL.shp` dentro de `NAC_POLE_PSR_SOUTH.ZIP` |
| URL | https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_PSR_SOUTH/NAC_POLE_PSR_SOUTH.ZIP (página: https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_PSR_SOUTH; léeme guardado en `data/raw/psr/`) |
| Contenido | 653 polígonos de PSR **mayores de 5 km²**, de 75°S a 90°S; horizonte calculado con DTM polares de 60 m/px (82-90°S) y 120 m/px (81-82°S). Atributos: área (km²), ID, lat, lon, PSR_ID, perímetro. 157 793 segmentos |
| Proyección | `.prj` «Stereographic_South_Pole», esfera de 1737,4 km, `lat_ts = −90`, metros: igual que el DEM de LSI. Comprobado: el centroide de 6 polígonos reproduce la lat/lon de su registro (diferencias ≤ 0,06° en lat) |
| Tamaño real descargado | ZIP 1 121 858 B + léeme 6283 B; extraído 2,6 MB. SHA-256 en `data/raw/psr/SHA256SUMS.json` |
| Licencia | No declarada en la página; solo pide citar a Brown et al. (2022). **A verificar** |
| Cita | Brown, H. M., Boyd, A. K., Cisneros, E., Sonke, A., Huft, A., Robinson, M. S. (2022), LROC PSR Atlas and PSR Mosaics, Lunar Polar Volatiles Conf., abstract 5033; Mazarico et al. (2011), Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030 |

También existe el mosaico NAC de 10 m/px de las PSR (imágenes, no máscara) y el Atlas LROC (https://lroc.im-ldi.com/atlases/psr/psr.pdf): no se descargan, no hacen falta para una máscara. No se encontró en PGDA un producto de polígonos PSR; los mapas de PGDA 69 son raster de iluminación media (§ del documento de contraste).

### API

- `psr_mask_window(site_key, center_x_m, center_y_m, half_size_m, max_px, pixel_size_m=None) -> dict | None`: máscara **bool** (True = dentro de una PSR publicada) sobre la malla del recorte, mismas claves y convención que `thermal_window` (`units='bool'`).
- `psr_distance_m(x_m, y_m) -> ndarray`: distancia **con signo** al borde de la PSR más cercana, **negativa dentro**, positiva fuera, en metros (exacta, a segmentos; ≈ 0,03 s por punto; sin índice espacial). La máscara y el signo coinciden fuera de ±1,5 píxeles del borde (test).

### Advertencia científica: PSR publicada ≠ sombra en un año simulado

Una PSR de Mazarico et al. es una región que **no recibe ninguna luz solar directa en todo el ciclo de precesión de 18,6 años**, calculada con el DTM de 60/120 m, disco solar finito y a nivel de **superficie**. El motor de LSI simula **un periodo concreto** (30-365 d por defecto, hasta ~19 años), con DEM de 5 m y una altura de observador (2 m por defecto). Por tanto: (1) un punto fuera de toda PSR publicada puede estar a oscuras todo un año simulado (la noche máxima varía con el año y la altura); (2) un punto dentro de una PSR no recibe Sol en ningún año a nivel de superficie, pero a 2 m de altura o con un DEM de 5 m el borde se desplaza decenas de metros; (3) el polígono omite las PSR de menos de 5 km² y los micro-PSR; (4) la distancia al borde es una distancia al límite de un cálculo con otro DEM, no una distancia de seguridad. Úsese para contexto y contraste (¿está el punto cerca de una trampa fría?), no como máscara de iluminación.
