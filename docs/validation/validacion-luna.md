# T62: validación física del motor frente a valores publicados (experto Luna)

Fecha: 14/11/2026. Motor: `pipeline.run_analysis`, DEM LOLA 5 m (PGDA, MOON_ME, DE421) + campo lejano LOLA 80 m, paso 840 s, SPICE `LT+S`, disco solar finito (sin oscurecimiento de limbo). Estado de cada fuente: **LEÍDA** (texto completo o resumen oficial obtenido y leído) o **SECUNDARIA** (solo vista en una página que la cita; no contrastada).

## 1. Conclusión

La sospecha («96–400 h frente a ~1,5 d») **no apunta a un error del motor: es una diferencia de definición y de población de puntos.** Con las definiciones de cada paper, el motor reproduce lo publicado:

| Magnitud publicada | Motor (mismos puntos y periodo) | Veredicto |
|---|---|---|
| Barker 2021, 7 RoI de la Connecting Ridge, 2024-26, z=1 m: iluminación media > 70 % | 75,5–90,0 % | cuadra |
| Barker 2021, z=5 m: iluminación media, percentil 1 de clones 82,8–89,3 % | 88,4–94,3 % | cuadra (nominal ≥ pesimista) |
| Barker 2021, z=5 m: LCIP percentil 1: 216–231 d (RoI 1–6), 119 d (RoI 7) | 233–265 d (RoI 1–6), 146 d (RoI 7) | cuadra; RoI 7 es la corta en ambos |
| Barker 2021, z=5 m: LCSP percentil 99: 4,0–8,4 d | 3,5–6,1 d | cuadra (nominal ≤ pesimista) |
| Barker 2021, z=1 m: LCSP percentil 99: 12,7–22,2 d | 5,2–16,1 d | cuadra |
| Gläser 2014, 19 años, 2 m: 92,27 % del tiempo iluminado, noche más larga «típicamente 3-5 d» | 92,1 % y 94,1 %; noche 5,06 y 4,89 d | cuadra (borde alto de 5 d) |
| Mazarico 2011: «240 d continuos al año», noche máxima «~1,5 d» en un punto del borde de Shackleton | a 10 m: noche 1,3–1,8 d/año y Sol continuo hasta 294–322 d; a 2 m: noche 4,7–5,1 d y Sol continuo 250 d | coherente **si** esa cifra corresponde a una altura de decenas de metros (a verificar) |

Por qué 1,5 d y 96–400 h no se contradicen:
1. **Es el mejor píxel de todo el polo.** Mazarico 2011 da la cifra de *una* ubicación (la mejor), a 240 m/px. Nuestro TOP-N sale de un score multiobjetivo (Sol 40 %, noche 25 %, Tierra 15 %, terreno 20 %), con puerta de pendiente p90 ≤ 10° en huella de 50 m, malla de 250 m y **sin** la Connecting Ridge: la ventana Site04 abarca x ∈ [-9, 7] km, y las RoI de Barker están en x ≈ -11,6…-10,2 km (fuera). El mejor f_sun de Site04 es 0,75, no el óptimo del polo.
2. **La altura manda.** En la misma RoI 4 la noche máxima baja de 5,0 d (2 m) a 1,3–1,8 d (10 m). El resumen de Mazarico dice que «small height gains (≲10 m) can dramatically improve average illumination and reduce night duration». La altura de la cifra de 1,5 d no figura en el resumen: **a verificar** en el artículo completo.
3. **«Noche máxima» está bien definida en el motor y coincide con LCSP de Barker:** periodo continuo más largo sin ninguna parte del Sol (`f ≤ 1e-3`) dentro del periodo analizado. La noche máxima casi no depende del año (4,84–5,06 d en 19 años a 2 m, RoI 4), así que elegir un año de 365 d (JSON: desde 2026-12-01) no la sesga. Sí sesga el **Sol continuo** (ver 3.4).
4. **`f_sun` del JSON no es «iluminación media» de Barker.** `f_sun` = fracción de tiempo con *cualquier* parte del Sol (`solar_fraction`); Barker promedia la fracción de *disco* visible (`effective_illumination` en el motor). `f_sun` ≥ iluminación media: 3–7 puntos más en las RoI (p. ej. RoI 1 a 1 m: 0,859 frente a 0,832). Gläser/Mazarico («sunlit») se acercan a la definición de `f_sun`. `f_Tierra` es la fracción con ≥ 50 % del disco terrestre sobre el horizonte (`earth_f_thr = 0.5`), no «cualquier parte».
5. Los 1,5 d no son un criterio de aptitud general: el JSON cubre la rejilla apta del recorte, que incluye zonas peores que la cresta.

## 2. Fuentes

| Fuente | Estado | Qué aporta |
|---|---|---|
| Mazarico, E. et al. 2011, Icarus 211, 1066-1081, doi 10.1016/j.icarus.2010.10.030. Resumen: https://ntrs.nasa.gov/citations/20120010094 (API `https://ntrs.nasa.gov/api/citations/20120010094`) | resumen **LEÍDO**, artículo completo no | LOLA 240 m/px; ciclos de 18,6 años a 6 h; «Every year, a location near the Shackleton crater rim ... sunlit continuously for 240 days, and its longest continuous period in total darkness is about 1.5 days»; ganancias de altura ≲10 m mejoran mucho. Altura de observación de esa cifra: no figura en el resumen |
| PGDA producto 69, https://pgda.gsfc.nasa.gov/products/69 | **LEÍDA** | Mapas de iluminación media del Sol y de visibilidad de la Tierra, 18,6 años, paso 1 h, **superficie** (sin altura), sin cifras por sitio |
| Gläser, P. et al. 2014, Icarus 243, 78-90, doi 10.1016/j.icarus.2014.08.013. Resumen: https://elib.dlr.de/94240/ | resumen **LEÍDO** | DTM de 20 m/px; Connecting Ridge; 19 años; superficie, 2 m y 10 m; **92,27 % del tiempo a 2 m y 95,65 % a 10 m**; noches más largas típicamente 3-5 d. Tabla por altura: no leída |
| Barker, M.K. et al. 2021, Planetary and Space Science 203, 105119, doi 10.1016/j.pss.2020.105119. PDF: https://ntrs.nasa.gov/api/citations/20205009660/downloads/Mike%20Barker_%20Paper_%20Improved%20Lola.pdf | **LEÍDA** (texto completo) | Site 1 = Connecting Ridge, Site 4 = borde de Shackleton, Site 7 = pico aislado, Site 11 = borde de de Gerlache (numeración de Mazarico 2011, Table 3). Table 2 (7 RoI de Site 1, 100 clones, 2024-01-01 a 2026-01-01, paso 1 h, z = 1 m y 5 m). Definiciones: iluminación media = fracción visible del disco solar promediada; LCIP = periodo más largo con cualquier fracción del Sol; LCSP = periodo más largo sin ningún Sol. **Solo Site 1 tiene cifras**: no hay tabla para Site 4, 11 ni 23 |
| PGDA producto 78, https://pgda.gsfc.nasa.gov/products/78 | **LEÍDA** (primeros 100 000 caracteres) | LDEM 5 m de los sitios; iluminación solo de Site 1 (2024-26, 1 m y 5 m); DEM Site01 descargado de `https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/` |
| Mazarico, Barker, Nicholas 2018, Adv. Space Res. (IllumNG), https://pmc.ncbi.nlm.nih.gov/articles/PMC6398960 | **LEÍDA** | Método (trazado de rayos, disco solar, mapas de Tierra visible); sin cifras de Shackleton/de Gerlache/Malapert |
| Wikipedia, «Peak of eternal light», https://en.wikipedia.org/wiki/Peak_of_eternal_light | **SECUNDARIA** | Tabla atribuida a Bussey et al. 2010 (Kaguya, año 2020): punto A Shackleton 81 %, B 82 %, D 86 %, de Gerlache C 85 %, Malapert M1 74 %, M2 74 %; «43 h» de Speyerer y Robinson 2013. No contrastada con Bussey 2010 ni Speyerer 2013 |

No leídos y que quedan **a verificar**: Mazarico 2011 completo (Table 3: iluminación y noche por sitio, altura usada), Gläser et al. 2017 (PSS, doi 10.1016/j.pss.2017.07.006), Bussey et al. 2010 (Icarus 208, Kaguya), Speyerer y Robinson 2013 (Icarus 222, 122-136), NASA SVS «Illumination Map of the Moon's South Pole», Moon Trek/QuickMap/LROC, regiones Artemis III. Esos cuatro últimos no se consultaron.

**Visibilidad de la Tierra: no se ha encontrado ninguna cifra publicada verificada** en los sitios (solo mapas sin valores en PGDA 69 y NASA dice cualitativamente «exceptional Earth visibility» para Malapert, vista en un resultado de búsqueda, **a verificar**). La comprobación disponible es interna: el motor da `f_Tierra` 0,46–0,77 en la Connecting Ridge a 1-5 m (disco ≥ 50 %), y la esfera lisa a -89,9° da 47,0 % en 2026-27 (`luna-spice-sitios.md` §3, SPICE, no publicado). El 0,46–0,71 del TOP-N es coherente con la libración (±6,8°) y un horizonte elevado, pero no está contrastado con ninguna fuente.

## 3. Ejecuciones del motor

Scripts ad hoc (no versionados); DEM Site01 de PGDA en un directorio aparte para no alterar `data/raw`. Coordenadas (X, Y) estereográficas de Table 2 convertidas con `stereo_inverse`; `snap_to_dem=False`.

### 3.1 RoI de Barker (2024-01-01 a 2026-01-01, 2 años)

| RoI | lat, lon E | z | iluminación media | f_sun (cualq. parte) | noche máx. (d) | Sol continuo máx. (d) | f_Tierra |
|---|---|---|---|---|---|---|---|
| 1 | -89,4389, 222,904 | 1 m | 0,832 | 0,859 | 12,06 | 198,4 | 0,588 |
| 1 | | 5 m | 0,943 | 0,964 | 3,93 | 235,0 | 0,651 |
| 2 | -89,4387, 222,452 | 1 m | 0,805 | 0,839 | 13,66 | 198,2 | 0,484 |
| 2 | | 5 m | 0,932 | 0,951 | 4,72 | 234,2 | 0,552 |
| 3 | -89,4431, 222,240 | 1 m | 0,755 | 0,792 | 16,08 | 175,9 | 0,461 |
| 3 | | 5 m | 0,886 | 0,925 | 6,12 | 232,9 | 0,503 |
| 4 | -89,4527, 222,851 | 1 m | 0,860 | 0,896 | 6,78 | 218,3 | 0,594 |
| 4 | | 5 m | 0,929 | 0,959 | 3,51 | 264,7 | 0,649 |
| 5 | -89,4623, 222,912 | 1 m | 0,803 | 0,851 | 8,47 | 176,2 | 0,518 |
| 5 | | 5 m | 0,917 | 0,942 | 3,90 | 234,3 | 0,625 |
| 6 | -89,4739, 222,625 | 1 m | 0,900 | 0,933 | 5,21 | 205,4 | 0,696 |
| 6 | | 5 m | 0,932 | 0,956 | 3,64 | 234,4 | 0,768 |
| 7 | -89,4912, 221,519 | 1 m | 0,808 | 0,878 | 6,06 | 116,9 | 0,570 |
| 7 | | 5 m | 0,884 | 0,910 | 5,18 | 145,9 | 0,708 |

Tolerancias razonadas: Table 2 son percentiles 1/99 de 100 DEM con errores (cotas pesimistas) y el motor usa el DEM nominal, que según Barker es mejor que la media de los clones. Se afirman solo cotas: iluminación media ≥ 70 % (z=1 m) y ≥ p1 − 1 punto (z=5 m); LCIP ≥ 0,9 × p1; LCSP ≤ 1,1 × p99 y ≥ 3 d (caso C de Barker, píxel óptimo, 3,1–5,5 d). El motor está además muy cerca del caso C de LCIP a 1 m (Barker 205/205/177/233/193/206/118 d frente a 198/198/176/218/176/205/117 d).

### 3.2 Gläser 2014: 19 años a 2 m (2024-01-01 a 2043-01-01)

| RoI | f_sun (cualq. parte) | iluminación media | noche máx. (d) | Sol continuo (d) |
|---|---|---|---|---|
| 4 | 0,921 | 0,890 | 5,06 | 250,0 |
| 6 | 0,941 | 0,913 | 4,89 | 233,7 |

Publicado: 92,27 % y noches de 3-5 d (mejores puntos, DTM de 20 m). Diferencia ≤ 1,8 puntos; la noche queda en el borde de 5 d (el DEM de 5 m y el punto no son los suyos).

### 3.3 Efecto de la altura y variación entre años (RoI 4 y 6, un año cada vez, 2024-2042)

| RoI | z | noche máx. (d), mín–máx en 19 años | ciclo de 19 años: noche (d) | Sol continuo, ciclo de 19 años (d) |
|---|---|---|---|---|
| 4 | 2 m | 4,84–5,06 | 5,06 | 250,0 |
| 4 | 10 m | 1,34–1,78 | 1,78 | 322,5 |
| 6 | 2 m | 4,66–4,89 | 4,89 | 233,7 |
| 6 | 10 m | 2,74–3,03 | 3,03 | 264,2 |

A 10 m la RoI 4 da 1,3–1,8 d, que es el orden de los «~1,5 d» de Mazarico. Sin conocer la altura de su cifra no se puede afirmar más.

### 3.4 Sol continuo: depende del periodo y de la ventana

El Sol continuo anual de la RoI 4 a 2 m, con ventanas de un año natural, varía de 125 d (2024) a 250 d (2032), y con 2 años (3.1) da 235 d. La causa es doble: el ciclo nodal de 18,6 años y que una ventana de 365 d **trunca** una racha de ~240 d si no cae entera dentro. El motor ya marca `longest_sun_window_truncated`. Para comparar con «240 d al año» de Mazarico hay que usar ventanas ≥ 2 años o varias fechas de inicio. El mapa de idoneidad usa 365 d desde 2026-12-01: su `longest_sun_h` es un mínimo; su noche máxima no se ve afectada.

### 3.5 Malapert (Bussey 2010 vía Wikipedia, SECUNDARIA)

Año 2020, 2 m, DEM Site23, coordenadas de Wikipedia (M1 -86,04° 2,7°E; M2 -86,00° 2,9°O). En el punto exacto: M1 iluminación media 0,18, f_sun 0,24, noche 175 d; M2 0,46 / 0,46, noche 16,5 d, Tierra 0. Buscando en ±600 m alrededor de M1 (paso 200 m), el mejor punto da f_sun 0,70 e iluminación media 0,66 (a 200 m al sur), noche 16,5 d, frente al 74 % de la tabla. Para M2 no se completó la búsqueda local. Lectura (hipótesis, no comprobada): las coordenadas de Wikipedia son aproximadas y no tienen por qué ser el píxel óptimo, y Kaguya (la fuente de Bussey) tiene resolución mucho menor; con esa salvedad el orden de magnitud (70 % frente a 74 %) es coherente, pero **no es una validación** (fuente secundaria, definición de «lit» y altura desconocidas). Sin test. El f_sun 0,94 del TOP-N de Site23 (mejor punto de la rejilla apta en 2026-27, 2 m) **no tiene cifra publicada con la que contrastarlo**: a verificar en Mazarico 2011 Table 3.

## 4. Lo que no se pudo verificar

- Cifras publicadas de f_sun y D_max para Site 4 (Shackleton), Site 11 (de Gerlache) y Site 23 (Malapert): Barker 2021 solo da Site 1 (PGDA 78 confirma «iluminación solo para Site 1»). Mazarico 2011 Table 3 no se leyó. Por eso `tests/test_luna_cases.py` no tiene casos de esos sitios.
- Altura de observación de la cifra de 1,5 d y de 240 d de Mazarico.
- Visibilidad de la Tierra publicada en cualquier sitio (ver sección 2).
- Artemis III: regiones sin coordenadas verificadas en `config/sites.json`.

## 5. Riesgos y recomendaciones

1. Etiquetar en UI y JSON qué es `f_sun` («tiempo con cualquier parte del Sol») frente a «iluminación media» de la literatura (`effective_illumination`), y `f_Tierra` (≥ 50 % del disco). Sin esto, las comparaciones con papers parecen discrepancias.
2. Indicar la altura (2 m) junto a D_max: a 10 m pasa de ~5 d a ~1,5-3 d.
3. Incluir Site01 (Connecting Ridge) en `scripts/fetch_data.py` si se quiere que esta validación corra en CI (4 ficheros de 41 MB).
4. Si se quiere reproducir los 240 d de Mazarico, usar ventanas ≥ 2 años.
5. Sin errores del motor que documentar: no hay `xfail`.

## 6. Reproducir

```
for l in surf slp ldec toterr; do curl -L -o <dir>/Site01_final_adj_5mpp_$l.tif \
  https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_$l.tif; done
LSI_SITE01_DIR=<dir> python -m pytest tests/test_luna_cases.py -q
```
36+2 tests; ~2 min. Sin el DEM se omiten.

## 4. Ejecución de `tests/test_luna_cases.py` con el DEM Site01 (14/11/2026)

DEM Site01 (surf, slp, ldec, toterr; 163,9 MB; tamaños confirmados por HEAD antes de bajar) descargado con `python scripts/fetch_validation_data.py --yes` a `data/validation_raw/site01/`; tamaño, firma TIFF (no HTML) y SHA-256 en `data/validation_raw/manifest.json`. Resultado real: **38 passed, 0 skipped, 0 failed** (97 s). Las cotas afirmadas son las de §3.1-3.2 (iluminación media ≥ p1 de Barker − 1 punto, LCIP ≥ 0,9·p1, LCSP ≤ 1,1·p99 y ≥ 3 d, Gläser 2014: f_sun 92,27 % ± 3 puntos y noche 3-5,5 d). No hay diferencias que maquillar: las 38 son cotas, no igualdades; las diferencias con las cifras publicadas son las de las tablas de §3 (nominal frente a percentil de clones; borde alto de 5 d de noche en Gläser). Sigue **a verificar**: Mazarico 2011 Table 3 y la altura de su cifra de 1,5 d; no hay contraste publicado para Site04/11/23.
