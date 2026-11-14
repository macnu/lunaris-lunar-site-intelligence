# Datos SDEM de 5 m con ortomosaico LROC NAC (Artemis III)

Medido el 14/11/2026 sobre los ficheros descargados en este equipo. Código: `scripts/fetch_sdem.py` (descarga), `src/lsi/data/sdem.py` (lectura), `tests/test_sdem.py`. **El motor científico no se ha tocado**: horizonte, pendiente y puntuación siguen usando el DEM LOLA; esto solo alimenta la visualización 3D.

## 1. Procedencia, licencia y cita

| Campo | Valor |
|---|---|
| Producto | Shape-from-Shading Products for the 2022 Artemis III Candidate Landing Regions (NASA PGDA, producto 104) |
| Página | https://pgda.gsfc.nasa.gov/products/104 |
| Archivo | Zenodo, doi 10.5281/zenodo.17954508, versión 1.0.0 (https://zenodo.org/records/17954508) |
| Licencia | CC-BY-4.0 (la de Zenodo; el registro la declara así) |
| Descarga | `https://zenodo.org/api/records/17954508/files/<zip>/content` con HTTP Range |
| Creación | README de cada región: S. Bertone (creador), R. A. Beyer (revisor), 2025-12-17 |

**Cita exacta** (texto de «Data Usage Policy» de la página del producto 104, leída el 14/11/2026):

> Bertone, S., McKenna, T. E., Barker, M. K., Mazarico, E., Beyer, R. A., and Petro, N., Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading, The Planetary Science Journal, doi: 10.3847/PSJ/ae5b70.

La página **no da año** para este artículo; el README de cada región escribe «Bertone S. et al. (2026) … doi:XYZ» (marcador sin resolver). LSI cita tal como figura en la página y no añade año.

Archivo de datos (misma página): Bertone, S., Barker, M., Mazarico, E., McKenna, T., and Petro, N., 2025, Archived geospatial products for manuscript «Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading», Zenodo, doi: 10.5281/zenodo.17954508.

La página también cita Barker et al. (2021, Planetary and Space Science, 203, 105119), Barker et al. (2023, The Planetary Science Journal, 4, 183) y Alexandrov y Beyer (2018, Earth and Space Science, 5, 652).

## 2. Qué cubre y qué NO cubre

Los zip contienen las 13 regiones Artemis III. LSI usa tres:

| Región (zip) | ID | Extensión (m, x / y) | Sitio LSI |
|---|---|---|---|
| `A3CLR22_11_Malapert_Massif` | A311 | x −11000…10000, y 111000…132000 (21×21 km) | **Site23** (Malapert) |
| `A3CLR22_9_deGerlache_Rim` | A309 | x −45000…−29000, y 7000…23000 (16×16 km) | **Site11** (de Gerlache) |
| `A3CLR22_8_Peak_Near_Shackleton` | A308 | x 22000…38000, y −28000…−12000 (16×16 km) | ninguno: no coincide con Site04 |

- **Site04 (Shackleton rim) NO está** en las 13 regiones. Su recorte LOLA (x −9000…7000, y −15000…1000) no solapa con A308 (x ≥ 22000): `sdem_region_for("Site04")` devuelve `None` y el 3D de Site04 sigue con el relieve LOLA. «Peak Near Shackleton» (A308) es otro lugar y no se le atribuye a Site04. (El nombre «Site07» no es de este proyecto.)
- Solo hay SDEM de Malapert y de Gerlache en la misma retícula que el LOLA. Fuera de esos recortes no hay textura.
- El ortomosaico es «maximum-illumination»: por píxel, el valor más brillante de las imágenes NAC. **No es una foto de una sola hora**: las sombras reales de una fecha concreta no aparecen y los azimuts de iluminación se mezclan. No es calibración radiométrica absoluta.
- Las zonas en sombra permanente no tienen fotografía (ver §5).

## 3. Descarga (bytes reales)

Cada zip pesa 2 213 137 537 B (Malapert), 1 340 667 387 B (de Gerlache) y 1 360 387 336 B (Peak Near Shackleton): 4,9 GB en total, **no descargados**. `fetch_sdem.py` lee el directorio central por Range y extrae solo `README.txt`, `GLDOMOS_005`, `GLDELEV_005`, `GLDMASK_005`, `GLDHILL_005_315_45` y `GLDDIFF_005` (pesa < 60 MB en las tres). Cada miembro se comprueba (longitud, CRC32 del zip, cabecera TIFF o no-HTML) antes de renombrarlo; nada del zip se ejecuta.

| Región | Rangos | Bytes leídos |
|---|---|---|
| Malapert Massif | 30 | 144 828 189 B en total acumulado (≈ 144,7 MB en la primera ejecución) |
| de Gerlache Rim | 23 | ≈ 92,8 MB |
| Peak Near Shackleton | 23 | ≈ 91,8 MB |
| **Total, primera ejecución** | 76 | **329 343 711 B (329,3 MB)**, el 6,7 % de los 4,9 GB de los tres zip |

Una segunda ejecución con `--yes` omitió los 18 ficheros (longitud + SHA-256 de `MANIFEST.json`) y leyó solo los tres directorios centrales (182 582 B); `MANIFEST.json` acumula ambas lecturas (329 526 293 B). Las capas están guardadas casi sin comprimir en el zip, de ahí que los bytes leídos ≈ bytes extraídos.

`data/raw/sdem/MANIFEST.json` guarda, por fichero, SHA-256, tamaño, miembro del zip, URL y fecha UTC, y a nivel global doi, versión y licencia. Ejemplos (SHA-256 truncado): Malapert `GLDELEV` e71f9466…, `GLDOMOS` ad0026f1…; de Gerlache `GLDELEV` 641532d0…, `GLDOMOS` 641b0c79….

| Capa (Malapert) | Bytes | Rejilla |
|---|---|---|
| `A311_GLDOMOS_005.tif` ortomosaico, float32 | 54 106 188 | 4201×4201, 5 m |
| `A311_GLDELEV_005.tif` SDEM, float32 | 31 171 558 | 4200×4200, 5 m |
| `A311_GLDDIFF_005.tif` SDEM − LOLA, float32 | 44 948 749 | 4200×4200, 5 m |
| `A311_GLDHILL_005_315_45.tif` sombreado, uint8 | 14 185 301 | 4200×4200, 5 m |
| `A311_GLDMASK_005.tif` recuento, uint8 | 504 129 | **1400×1400, 15 m** |

## 4. Inspección con datos reales

**CRS.** El de los GeoTIFF SDEM y el del LOLA coinciden parámetro a parámetro (`proj=stere, lat_0=−90, lat_ts=−90, lon_0=0, x_0=0, y_0=0, R=1737400, units=m`), comparado con `loader._check_crs` (el WKT lleva otro nombre: «Moon (2015) - Sphere / Ocentric / South Polar»). Geotransform norte-arriba, píxel cuadrado de 5 m.

**Dos desviaciones respecto al README** («common grid»), que `sdem.py` absorbe y hay que conocer:

1. `GLDMASK` está a **15 m**, no a 5 m (se remuestrea por vecino más cercano).
2. `GLDOMOS` tiene **una fila y columna más** y su retícula está **desplazada medio píxel (2,5 m)** respecto al SDEM (origen −11002,5 / 132002,5 frente a −11000 / 132000). Por eso se interpola siempre (bicúbico) y no se indexa píxel a píxel.

**Nodata.** SDEM y ortomosaico: ≈ −3,4·10³⁸ (float32; los dos valores difieren en los decimales). Sin nodata declarado en DIFF, HILL y MASK.

**Solape con los DEM LOLA.** La rejilla del SDEM es **idéntica** a la del recorte LOLA en Site23 y Site11 (mismo origen, tamaño y píxel): el SDEM cubre el **100 %** del recorte LOLA (17 640 000 y 10 240 000 píxeles, todos con dato en ambos).

| Punto | Dentro del SDEM | Ortomosaico válido | Recuento MASK (15 m) |
|---|---|---|---|
| Site23 observador por defecto (−500; 121 500) | sí | sí (0,0039) | 2 |
| Site23 TOP-1 mapa de idoneidad (rover) (−4697,5; 122 197,5) | sí | sí | 5 |
| Site23 TOP-1 lander (−4947,5; 122 197,5) | sí | sí | 18 |
| Site23 punto ajustado (sitio curado, sin snap) | sí | sí | 5 |
| Site11 observador por defecto (−37 000; 15 000) | sí | **solo píxel casi negro (0,0012)** | **0** |
| Site11 TOP-1 (−43 447,5; 17 697,5) | sí | sí | 9 |
| Site11 punto ajustado «de Gerlache» (snap `best`, −34 697,5; 17 697,5) | sí | **casi negro (0,0019)** | **0** |
| Site04 TOP-1 y punto ajustado «Shackleton» (snap, lat −89,94°) | **no hay SDEM** | no | no |

Cobertura del recorte con fotografía (MASK > 0): Malapert 98,5 %, de Gerlache 96,9 %. En de Gerlache, **el observador por defecto y el punto ajustado caen en sombra permanente**: el SDEM da altura, pero esos píxeles no tienen imagen iluminada y la textura sale oscura/sin dato. `terrain_texture_pack` los marca con `texture_valid = False` y no inventa textura.

**SDEM − LDEM** (en el solape, por píxel, alturas sobre R = 1737,4 km):

| Región | Sesgo | RMS | p95 \|d\| | p99 \|d\| |
|---|---|---|---|---|
| Malapert (Site23) | +0,006 m | 0,85 m | 1,66 m | 2,54 m |
| de Gerlache (Site11) | +0,016 m | 0,98 m | 1,96 m | 3,02 m |

La capa `GLDDIFF` del propio producto da lo mismo (RMS 0,82 y 0,96 m; correlación 0,995 y 0,998 con mi diferencia; el máximo de la discrepancia entre ambas es 11,4 y 5,8 m, localizado). Por zona (recuento de retornos LOLA `ldec`): RMS 0,98 m con retornos (10,2 % de Malapert, 8,1 % de Gerlache) y 0,83 m sin ellos (Gerlache 1,09 y 0,97 m). Pendiente (diferencias centrales a 5 m): percentiles p50/p90/p99 casi iguales (Malapert 17,9/26,0/30,6° SDEM frente a 17,9/26,2/30,9° LDEM; Gerlache 14,4/21,9/27,6° frente a 14,4/21,9/27,4°).

**Mejora de detalle** (cociente de energía de alta frecuencia SDEM/LDEM; alta frecuencia = altura − gaussiana de σ dado; sin 30 px de borde):

| Zona | σ 5 m | σ 15 m | σ 30 m | σ 60 m |
|---|---|---|---|---|
| Malapert, con retornos (`ldec>0`) | 0,06 | 0,22 | 0,47 | 0,74 |
| Malapert, `ldec=0` (89,8 %) | 1,49 | 0,97 | 1,00 | 1,01 |
| Malapert, sin retorno a ≤ 30 m (0,15 %) | 1983 | 258 | 23 | 4,0 |
| de Gerlache, con retornos | 0,09 | 0,29 | 0,58 | 0,84 |
| de Gerlache, `ldec=0` (91,9 %) | 2,44 | 1,37 | 1,22 | 1,10 |
| de Gerlache, sin retorno a ≤ 30 m (0,24 %) | 2352 | 296 | 17 | 2,6 |

Lectura honesta: en el 90 % de los píxeles sin retorno LOLA propio el LDEM de 5 m **ya** contiene detalle del mismo orden que el SDEM (cociente ≈ 1 a 15-60 m), así que el SDEM **no cambia** la pendiente ni el relieve a escala de decenas de metros salvo en parches pequeños. Hay mucho detalle nuevo solo donde el LDEM es una interpolación plana (< 0,25 % del recorte; cociente ≫ 1 incluso a 30 m). Donde sí hay retornos, el LDEM tiene más energía de alta frecuencia que el SDEM (cociente < 1): coherente con ruido puntual de los retornos, no medido aquí. No se ha investigado por qué el LDEM de 5 m trae ese detalle fuera de los retornos.

**Ortomosaico** (float32, factor de reflectancia relativo; el producto no declara escala): 

| | Malapert | de Gerlache |
|---|---|---|
| Mín / máx | 0,00056 / 0,177 | 0,00017 / 0,121 |
| p1 / p50 / p99 / p99,9 | 0,0012 / 0,0305 / 0,0578 / 0,0666 | 0,0010 / 0,0272 / 0,0511 / 0,0611 |
| Nodata (NaN) | 0,19 % | 0,25 % |
| Píxeles < 0,001 | 0,41 % | 0,78 % |
| Sin imagen iluminada (MASK = 0, a 15 m) | 1,5 % | 3,1 % |
| `GLDHILL` (uint8) | 23-254 | 20-254 |

Ningún píxel es ≤ 0. «Negro» no es 0 sino ≈ 0,001: las sombras permanentes son las colas del histograma, no un valor reservado.

**Normalización documentada para textura** (`sdem.ORTHO_HI = 0,065`, `ORTHO_GAMMA = 2,2`): `u8 = 255·clip(x/0,065, 0, 1)^(1/2,2)`. Constantes fijas (no por recorte) para que teselas contiguas casen; 0,065 ≈ p99,9. Un píxel típico (0,03) queda en ≈ 180. Donde `texture_valid` es `False`, `ortho` vale 0 y no es fotografía.

## 5. API de `lsi.data.sdem`

- `sdem_region_for(site_key)`: `Site23` → `Malapert_Massif`, `Site11` → `deGerlache_Rim`, `Site04` y cualquier otro → `None` (admite `site23` o `Site23`).
- `available_regions()`: regiones con elevación, ortomosaico y máscara en disco.
- `terrain_texture_pack(site_key, center_x_m, center_y_m, half_size_m, max_px)`: `heights` (float32; SDEM, relleno LDEM), `height_source` (1 SDEM, 2 LDEM, 0 sin dato → NaN), `valid`, `ortho` (uint8), `texture_valid`, `px_m`, `x0_m`, `y0_m` (centro del píxel [0,0]; la y decrece con la fila), `ortho_norm`, `attribution`, `notes`. `None` sin SDEM, sin ficheros o sin solape. Si el recorte sale del SDEM, devuelve la parte cubierta con las máscaras en `False`: nunca inventa textura ni altura.
- Remuestreo: altura **bilineal**; ortomosaico **bicúbico** (recortado al rango observado, porque el spline rebasa en los bordes de sombra); recuento **vecino**. Si cabe a 5 m (`2·half/5 ≤ max_px`) usa la retícula nativa, que coincide píxel a píxel con un recorte LOLA del mismo centro; si no, `px = 2·half/max_px` con filtro gaussiano previo (σ = 0,5·factor). Lectura por ventana: un recorte de 2 km tarda ≈ 0,1 s.

## 6. Oportunidad (solo medida; sin cambios en el motor)

1. **Uso visual (seguro):** textura fotográfica real sobre el relieve en Malapert y de Gerlache, con el aviso de «máxima iluminación» y la atribución CC-BY-4.0.
2. **Ciencia:** el SDEM podría mejorar horizonte y pendiente **solo en parches** de interpolación plana (0,15-0,24 % del recorte) y en puntos con retornos LOLA ruidosos; en el 90 % del terreno la mejora medida es ≈ 0. Por tanto **no justifica por sí solo** retirar la limitación «resolución efectiva ≈ 30 m» (heurística de LSI, a verificar): esa heurística debería contrastarse con este resultado antes de repetirla, porque aquí el LDEM de 5 m ya tiene detalle fino. Recomendación: no cambiar el horizonte; si se quiere, medir primero el efecto en f_sol y D_max con el SDEM en un caso (p. ej. TOP-1 de Site23) y documentarlo como sensibilidad.
3. **Incertidumbre:** el SDEM trae `GLDSIGM`, no descargada; cabe valorarla si el SDEM entra algún día en el motor.
4. **Limitación 3D:** en de Gerlache el observador por defecto y el punto ajustado están en sombra permanente: la vista fotográfica será oscura ahí. El 3D debería decirlo en lugar de rellenarlo.
