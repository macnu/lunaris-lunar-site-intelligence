# Contraste de la iluminación de LSI con mapas LOLA publicados (Site04, Site11, Site23)

Fecha: 14/11/2026. Cubre la carencia «no hay cifras publicadas de contraste para los 3 sitios del demo». Código: `src/lsi/data/illum_ref.py`; datos: `scripts/fetch_thermal_psr.py`. **No se ha modificado el motor.**

## 1. El producto publicado

| Campo | Valor |
|---|---|
| Producto | Mapas de **iluminación media del Sol**, LRO LOLA, PGDA producto 69 «Lunar Polar Illumination» (PDS: GDRVIS, `LRO-L-LOLA-4-GDR-V1.0`) |
| Página | https://pgda.gsfc.nasa.gov/products/69 ; PDS: https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/LRO/LOLA/GDR/GDRVIS.htm |
| Ficheros usados | `AVGVISIB_85S_060M_201608.TIF` (≥ 85°S, **60 m/px**, ±151,74 km, 5058², 33 994 464 B) y `AVGVISIB_75S_120M_201608.TIF` (≥ 75°S, 120 m/px, ±457,44 km, 7624², 83 052 039 B), de https://pgda.gsfc.nasa.gov/data/MoonIllumination/ . Total descargado **117 046 503 B (112 MiB)**, comprobado con HEAD antes. SHA-256 en `data/raw/illum_ref/SHA256SUMS.json` |
| Formato | GeoTIFF int16, valor = DN × 4·10⁻⁵ (fracción 0-1), nodata −32768; estereográfica polar sur R = 1737,4 km, `lat_ts = −90` (la del DEM de LSI) |
| Definición (página PGDA 69, leída) | Media de la fracción visible del disco solar «averaged over hourly timesteps spanning 18.6 years» (ciclo de nutación); **superficie, sin altura de observador** (la página dice que la altura para rovers o hábitats exige análisis adicional); disco solar finito; las etiquetas internas del TIFF dan START_TIME 2009-07-13 y STOP_TIME 2013-07-18 (periodo de los datos LOLA, no el del cálculo). Oscurecimiento de limbo: no declarado |
| Licencia | La página no declara condiciones; pide citar a Mazarico et al. (2011). **A verificar** |
| Cita | Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011), Illumination conditions of the lunar polar regions using LOLA topography, Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030 |

Los enlaces COG de la página de PGDA (`..._COG.TIF`) devuelven HTML con código 200 (rutas que no existen en el servidor el 14/11/2026): el script los evita y rechaza HTML. Hay además mapas de visibilidad de la Tierra del mismo producto (no usados aquí: son de la familia del enlace).

### API
`illum_ref_window(site_key, center_x_m, center_y_m, half_size_m, max_px) -> dict | None` (misma malla y convención que `thermal_window`; `units='fraction'`, producto de 60 m si cabe y, si no, 120 m) e `illum_ref_at(x, y)` (bilineal más mínimo y máximo de la vecindad 3×3 px).

## 2. Búsquedas hechas sobre otros productos

- «PGDA LOLA illumination south pole average»: dio el producto 69 (usado), el 78 (DEM de 5 m; iluminación publicada solo de Site01 en 2024-26, ver `validacion-luna.md`) y el 104 (topografía mejorada con shape-from-shading, sin mapa de iluminación por sitio).
- Mazarico et al. 2011: el artículo completo (Table 3 por sitio) **no se ha leído**; no se han tomado cifras de él.
- Mapas LROC WAC de iluminación (`WAC_POLE_ILL_PCT_*`) existen en LROC pero son imágenes de iluminación por porcentaje de unos pocos meses; no se han descargado (no son un promedio de 18,6 años).
- **No existe, en lo hallado, una tabla publicada de iluminación media para Site04, Site11 y Site23 con altura de observador.** Lo que existe es el **mapa raster** de superficie; de él se leen valores en cualquier punto, y eso es el contraste independiente de esta página. Las cifras Kaguya de la tabla de Wikipedia (Bussey et al. 2010) siguen sin contrastar.

## 3. Método y definiciones

LSI: `pipeline.run_analysis`, `observer_height_m = 0,0` (definición del mapa: superficie), periodo **2024-01-01 a 2042-08-01 (6786 d = 18,58 años)**, `step_s = 3600` (paso interno de 720 s), SPICE `LT+S`, disco solar finito sin oscurecimiento de limbo (`limb_darkening_u = 0`), DEM LOLA de 5 m + campo lejano de 80 m, `snap_to_dem=False`, `link_network=None`. Magnitud comparada: `metrics.effective_illumination` (media de la fracción de disco visible), que es la definición de Mazarico/Barker y **no** `solar_fraction` (cualquier parte del Sol, 0,01-0,05 mayor en estos puntos).

Puntos: por cada recorte, el TOP-1 del mapa de idoneidad y una rejilla 3×3 en el 20/50/80 % de cada eje del recorte (27 puntos con h = 0; el TOP-1 también a h = 2 m). Publicado: bilineal de la malla de 60 m en el mismo (x, y).

**Diferencias de definición que no se pueden eliminar:** (1) el mapa promedia 60 m y usa un DTM de 60-240 m, LSI evalúa un punto con un DEM de 5 m, en el que ~90 % de los píxeles es interpolación (resolución efectiva ≈ 30 m, `docs/fuentes-datos.md`): el contraste a nivel de punto mezcla escalas; (2) periodos distintos (18,58 años contra «18,6 años»); (3) el mapa no declara oscurecimiento de limbo; (4) en LSI el horizonte de más de 30 km se cierra con el DEM de 80 m, el mapa no tiene ese límite.

## 4. Resultados

Iluminación media, fracción 0-1 (pub = mapa publicado; LSI = `effective_illumination`, h = 0):

| Punto | pub | pub mín–máx 3×3 | LSI h = 0 | LSI − pub |
|---|---|---|---|---|
| Site04 g00 | 0,176 | 0,085-0,197 | 0,178 | +0,002 |
| Site04 g01 | 0,172 | 0,169-0,174 | 0,178 | +0,006 |
| Site04 g02 | 0,263 | 0,261-0,266 | 0,308 | +0,045 |
| Site04 g10 | 0,286 | 0,006-0,403 | 0,294 | +0,008 |
| Site04 g11 | 0,111 | 0,100-0,122 | 0,089 | −0,022 |
| Site04 g12 | 0,327 | 0,314-0,354 | 0,283 | −0,044 |
| Site04 g20, g21, g22 | 0,000 | 0,000 | 0,000 (oscuridad todo el periodo) | 0 (PSR de Shackleton: coincide) |
| Site11 g00 | 0,222 | 0,217-0,224 | 0,191 | −0,031 |
| Site11 g01 | 0,372 | 0,367-0,375 | 0,369 | −0,003 |
| Site11 g02 | 0,058 | 0,036-0,084 | 0,046 | −0,012 |
| Site11 g10 | 0,297 | 0,276-0,312 | 0,272 | −0,025 |
| Site11 g11 | 0,540 | 0,437-0,643 | 0,248 | **−0,292** |
| Site11 g12 | 0,248 | 0,227-0,257 | 0,315 | +0,067 |
| Site11 g20 | 0,288 | 0,254-0,307 | 0,268 | −0,020 |
| Site11 g21 | 0,289 | 0,279-0,294 | 0,412 | +0,123 |
| Site11 g22 | 0,372 | 0,350-0,376 | 0,466 | +0,094 |
| Site23 g00 | 0,236 | 0,228-0,238 | 0,350 | +0,114 |
| Site23 g01 | 0,388 | 0,388-0,438 | 0,314 | −0,074 |
| Site23 g02 | 0,425 | 0,424-0,425 | 0,320 | −0,105 |
| Site23 g10 | 0,172 | 0,159-0,187 | 0,245 | +0,073 |
| Site23 g11 | 0,180 | 0,056-0,387 | 0,073 | −0,107 |
| Site23 g12 | 0,416 | 0,416-0,417 | 0,413 | −0,003 |
| Site23 g20 | 0,358 | 0,227-0,375 | 0,455 | +0,097 |
| Site23 g21 | 0,397 | 0,294-0,484 | 0,333 | −0,064 |
| Site23 g22 | 0,409 | 0,406-0,415 | 0,405 | −0,004 |

Estadísticos sobre los 24 puntos con valor publicado > 0,01 (rejilla; excluye los 3 de oscuridad y los TOP-1): sesgo −0,007; RMS 0,087; máximo |dif| 0,292; r = 0,70; 13 puntos dentro de ±0,05 y 19 dentro de ±0,10. Por sitio: Site04 RMS 0,028 (6 puntos, r = 0,98), Site11 RMS 0,114, Site23 RMS 0,081. 12 de 24 puntos caen dentro del intervalo mín–máx de la vecindad 3×3 del mapa ±0,02.

### Los TOP-1 (puntos escogidos por ser máximos)

| Sitio | pub (bilineal; 3×3) | LSI h = 0 | LSI h = 2 m | LSI h = 0, `solar_fraction` |
|---|---|---|---|---|
| Site04 TOP-1 (−7698, −10 802) | 0,224 (0,150-0,548) | 0,411 | 0,712 | 0,463 |
| Site11 TOP-1 (−43 448, 17 698) | 0,679 (0,563-0,704) | 0,391 | 0,846 | 0,443 |
| Site23 TOP-1 (−4948, 122 198) | 0,732 (0,263-0,738) | 0,440 | 0,916 | 0,479 |

Aquí **no hay acuerdo a nivel de punto**, con signo distinto: en Site04 LSI es mayor que el mapa (+0,19) y en Site11 y Site23 menor (−0,29 y −0,29). La lectura razonada: (1) el TOP-1 es el máximo de un campo ruidoso a 2 m (sesgo de selección: el punto elegido es donde el DEM de 5 m da el mejor horizonte, que no tiene por qué ser el de un píxel de 60 m); (2) a h = 0 el horizonte depende de microtopografía de menos de 30 m, bajo la resolución efectiva del DEM: pasar de 0 a 2 m cambia la iluminación de 0,39 a 0,85 en Site11. El valor publicado (0,68) cae **entre** los dos, es decir, el mapa de 60 m se parece a «un metro o dos de altura» más que al suelo exacto del DEM de 5 m. No se ha podido separar cuánto es error del DEM de 5 m y cuánto es suavizado del mapa. **Las cifras de la tabla de arriba no sirven como validación de un TOP-1 concreto**, sí del campo medio.

## 5. Tolerancia propuesta y veredicto

Con las diferencias de definición del §3, una tolerancia razonada para comparar el campo medio es **±0,10 en fracción** (≈ ±10 puntos): contrasta el 79 % de los puntos de rejilla (19/24) y el sesgo medio es −0,007. Veredicto:

- **Site04: cuadra** (RMS 0,028, r = 0,98; incluida la PSR de Shackleton: oscuridad total en LSI y 0,000 publicado).
- **Site11 y Site23: cuadra en media (sesgo ≈ −0,01) pero con dispersión 0,08-0,11 y casos de 0,12-0,29** en puntos con gradiente fuerte del mapa (p. ej. Site11 g11: el mapa varía de 0,44 a 0,64 en 3×3 px).
- **El contraste a nivel de un punto óptimo elegido (TOP-1) NO queda validado**; sensibilidad a la altura enorme (h = 0 → 2 m).
- El contraste valida iluminación **a nivel de superficie y 18,6 años**; el demo usa 2 m y 1 año: las cifras del mapa no son comparables con el `f_sun` del TOP-1 (0,74, 0,87, 0,94).

## 6. Qué sigue sin existir

No hay cifras publicadas por altura de observador para Site04, 11 y 23 (solo la de Site01 de Barker 2021); la Table 3 de Mazarico 2011 no se ha leído; los mapas LOLA de PGDA no dan incertidumbre; no hay verificación de la visibilidad de la Tierra (existe el mapa `*_EARTH.TIF` de PGDA 69, no comparado aquí).
