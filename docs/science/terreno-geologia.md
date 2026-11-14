# Terreno y geología del DEM — LSI

Autor: geólogo planetario (agente). Fecha de medición: 14/11/2026. Datos: `data/raw/{shackleton,de_gerlache,malapert}/` (LOLA/PGDA, 5 m/px, `*_final_adj_5mpp_{surf,slp,ldec,toterr}.tif`). Las **cifras de este documento están medidas** con el script de la sección 5 (se ejecutó sin errores para los tres sitios); lo que no se ha medido lleva la etiqueta **a verificar**. Etiquetas de los criterios externos: *publicado* (hay fuente citable), *convención* (práctica de la comunidad o decisión de LSI, no requisito de una misión), *a verificar* (de memoria; comprobar antes de citar en la entrega).

> Las referencias bibliográficas están citadas de memoria (autor, revista, año). Comprobar volumen y páginas antes de incluirlas en la presentación.

## Resumen para el equipo

1. **El 90–92 % de los píxeles no tiene ningún retorno LOLA** (`ldec = 0`); la distancia al píxel observado más cercano es de 7 m (mediana), 15–16 m (p90) y 25–29 m (p99). La información independiente llega cada ~15–30 m, no cada 5 m. La textura de alta frecuencia lo confirma: es 20–100 veces menor en los píxeles interpolados que en los observados (sección 2.1).
2. **`slp` es exactamente una diferencia central con baseline de 10 m** (RMSE frente a mi recálculo: 0,0002–0,0008°, es decir, redondeo float32). Se calcula en el plano estereográfico, no sobre la esfera, con error de escala ≤ 0,12 % (sección 3.1).
3. **Con el observador a nivel del suelo el horizonte lo fija el terreno a 7–100 m del punto**, justo la escala interpolada y menos fiable. Subir el observador de 0 a 2 m baja el horizonte medio entre 0,5° y 2,8° en los puntos de ejemplo. LSI necesita un parámetro explícito `altura_observador` y una exclusión de campo cercano (sección 2.4).
4. **Los recortes miden 16×16 km (Shackleton, de Gerlache) y 21×21 km (Malapert).** En Shackleton, desde el centro del recorte, el 41 % de los acimuts tiene el horizonte todavía subiendo en el borde del DEM (la pared opuesta del cráter): el horizonte es una cota inferior y el error de DEM finito es siempre optimista para la iluminación (sección 6).
5. `toterr` es pequeña (mediana 0,36–0,47 m) y **no incluye el error de interpolación entre trazas**. No debe usarse sola como «confianza».

---

## 1. Inventario medido por capa y sitio

### 1.1 Malla, CRS y coherencia

| | Shackleton (Site04) | de Gerlache (Site11) | Malapert (Site23) |
|---|---|---|---|
| Dimensiones (px) | 3200 × 3200 | 3200 × 3200 | 4200 × 4200 |
| Extensión | 16 × 16 km | 16 × 16 km | 21 × 21 km |
| X (m) | −9000 … 7000 | −45000 … −29000 | −11000 … 10000 |
| Y (m) | −15000 … 1000 | 7000 … 23000 | 111000 … 132000 |
| Latitud del centro (esfera R = 1737,4 km) | −89,767° | −88,684° | −85,995° |
| Mismas transformación y CRS en las 4 capas | sí | sí | sí (*) |
| NaN (nodata declarado = NaN) en las 4 capas | 0 % | 0 % | 0 % |

(*) En Malapert `toterr` declara el CRS con otro **nombre** (`unknown` en vez de `unnamed`), pero los parámetros son idénticos (polar estereográfica, latitud de origen −90°, meridiano central 0, esfera de 1737400 m). Una comparación `crs == crs` de rasterio da `False`; comparar parámetros, no igualdad de objetos (el script lo hace con `crs_key`).

- Todas las capas son `float32`, 5,0 m/px, polar estereográfica sur, esfera de 1737,4 km, unidades: `surf` m (elevación respecto a R = 1737,4 km), `slp` grados, `ldec` número de retornos por píxel (entero 0–5), `toterr` m.
- Los metadatos GMT traen `AREA_OR_POINT = Area` y `node_offset = 1`: el origen de la transformación es la esquina del píxel; el centro del píxel está 2,5 m dentro. Usar `transform * (col + 0.5, fila + 0.5)` para obtener X/Y del centro (CLAUDE.md fija «píxel centrado»).
- El polo sur (0, 0) cae **dentro** del recorte de Shackleton (fila 200, columna 1800; z = 1289 m). Los tres recortes no se tocan: los bordes más próximos de Shackleton y de Gerlache distan ~21 km (20 km en X, 6 km en Y); Malapert está a ~121 km del polo.

### 1.2 Elevación (`surf`, m)

| | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| mín / máx | −2847,9 / 1805,1 | −805,2 / 1816,0 | 902,0 / 5173,6 |
| relieve total | 4653 m | 2621 m | 4272 m |
| p1 / p5 | −2735,7 / −2428,7 | −634,8 / −346,2 | 1303,8 / 1811,2 |
| p25 / **p50** / p75 | −482,9 / **668,2** / 1250,6 | 199,1 / **694,4** / 1044,2 | 2708,7 / **3618,4** / 4458,5 |
| p95 / p99 | 1582,9 / 1685,5 | 1559,7 / 1743,2 | 4941,0 / 5107,0 |
| % del recorte por debajo de −1000 m / por encima de +1000 m | 18,8 % / 37,9 % | 0 % / 28,0 % | 0 % / 99,9 % |

### 1.3 Pendiente (`slp`, grados)

| | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| media | 20,66 | 14,39 | 17,39 |
| p50 / p90 / p99 | 20,55 / 33,16 / 37,35 | 14,38 / 21,85 / 27,41 | 17,87 / 26,22 / 30,93 |
| máx | 69,6 | 62,5 | 76,2 |
| % del recorte con pendiente < 5° / < 10° / < 15° | 4,7 / 18,8 / 37,0 | 5,0 / 22,7 / 54,3 | 4,3 / 16,8 / 36,6 |

El recorte entero es un terreno duro: sólo el 17–23 % tiene menos de 10°. Hay que buscar parches, no esperar zonas llanas amplias.

### 1.4 Conteo de retornos (`ldec`) y distancia a observación

| | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| fracción de píxeles con **0 retornos** | **90,85 %** | **91,86 %** | **89,84 %** |
| mediana de retornos | 0 | 0 | 0 |
| histograma 0 / 1 / 2 / 3 / 4 / 5 retornos (píxeles) | 9 302 619 / 892 370 / 43 528 / 1447 / 34 / 2 | 9 406 690 / 795 875 / 36 164 / 1230 / 40 / 1 | 15 847 725 / 1 689 376 / 98 532 / 4231 / 133 / 3 |
| distancia al píxel observado más cercano, p50 / p90 / p99 / máx (m) | 7,1 / 15,0 / 25,0 / 64,0 | 7,1 / 15,8 / 29,2 / 90,1 | 7,1 / 15,8 / 26,9 / 71,1 |

La fracción observada es uniforme dentro y fuera de las depresiones (Shackleton: 9,1 % en z < −1000 m, 9,5 % en z > +1000 m), de modo que LOLA, al ser activo, cubre igual el interior en sombra.

### 1.5 Incertidumbre vertical total (`toterr`, m)

| | p1 | p5 | p25 | **p50** | p75 | p95 | p99 | máx |
|---|---|---|---|---|---|---|---|---|
| Shackleton | 0,130 | 0,168 | 0,260 | **0,360** | 0,504 | 0,826 | 1,197 | 7,64 |
| de Gerlache | 0,138 | 0,184 | 0,275 | **0,366** | 0,483 | 0,714 | 0,954 | 6,17 |
| Malapert | 0,151 | 0,213 | 0,337 | **0,465** | 0,621 | 0,908 | 1,208 | 15,94 |

Los valores `toterr > 1,5 m` ocupan el 0,09–0,33 % del área y `> 3 m` el 0,002–0,016 %; están en pendientes de 34–60° (p. ej. el máximo de Shackleton, 7,6 m, está a 48° de pendiente). La correlación `toterr`–pendiente en Shackleton es 0,42.

### 1.6 Relieve en una frase por sitio

- **Shackleton (Site04):** relieve de 4,65 km con el polo sur dentro del recorte a z = 1289 m; la cresta/meseta (z ≈ 1,2–1,65 km, medias por bloques de 2 km) ocupa la franja centro-occidental (X ≈ −5000 … −1000 m), el interior del cráter (z < −1500 m, centroide en X = 5196, Y = −6466 m) queda en el este-sureste y el centro geométrico (z = 768 m) está sobre la pared interna con 32° de pendiente; el máximo (1805 m) cae en la esquina noroeste del recorte, es decir, el relieve alto continúa fuera del DEM.
- **de Gerlache (Site11):** relieve de 2,62 km sin nada por debajo de −805 m; una cresta de 1,4–1,8 km cruza el recorte en diagonal desde el oeste-noroeste (X ≈ −44 km, Y ≈ 18 km) hacia el centro-sur (el máximo, 1816 m, está en X = −37 668, Y = 14 923 m, prácticamente el centro del recorte), y el terreno cae hacia el suroeste (−650 m de media en esa esquina) y hacia el noreste.
- **Malapert (Site23):** relieve de 4,27 km; la cima del macizo (z ≈ 4,5–5,2 km) es una franja este-oeste alrededor de Y ≈ 121–123 km con el máximo (5174 m) en X = 4393 m, y el terreno desciende hacia el norte (1,3–3,4 km en el borde superior) y hacia el sur (1,9–3,1 km en el borde inferior); no hay depresiones cerradas dentro del recorte.

---

## 2. Resolución efectiva y confianza

### 2.1 Qué dicen los datos sobre la resolución efectiva

- Sólo el 8–10 % de los píxeles tiene retorno. El resto es interpolación entre trazas (el método exacto de PGDA es **a verificar**; aquí se trata «sin retorno» = «interpolado»).
- La separación típica entre observaciones es 15–16 m (p90 de la distancia a observación). Heurística LSI: **resolución efectiva ≈ 2 × p90 de la distancia a observación ≈ 30 m** (convención LSI, **a verificar** frente a la literatura de PGDA; Barker et al. 2021, *Planet. Space Sci.* 203, describen el error de estos mapas).
- **Prueba directa en el DEM:** RMS de la textura de alta frecuencia (`Z − media 3×3`) según la distancia al píxel observado más cercano:

| distancia a observación (m) | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| 0 (píxel con retorno) | 0,490 m | 0,361 m | 0,459 m |
| 5–8 | 0,102 | 0,075 | 0,099 |
| 10–13 | 0,025 | 0,017 | 0,023 |
| 14–20 | 0,015 | 0,005 | 0,006 |
| ≥ 20 | 0,021 | 0,003 | 0,005 |

La textura cae 20–100 veces al alejarse 10–20 m de un retorno: el DEM es suave por construcción donde no hay datos. **Consecuencia:** la rugosidad calculada a escalas ≤ 25 m (RMS a 10 m de 0,03–0,2 m en los puntos de ejemplo) es un artefacto de interpolación, no una medida de regolito. Usar rugosidad sólo a ≥ 50 m (sección 3.3).

### 2.2 Qué es y qué no es `toterr`

- Es la incertidumbre vertical total de LOLA tras el ajuste (mediana 0,36–0,47 m, p99 ≈ 1,0–1,2 m). **No** incluye el error entre trazas (relieve no muestreado).
- Crece con el hueco: mediana de `toterr` por distancia a observación (m):

| distancia (m) | 0–5 | 5–10 | 10–25 | 25–50 | 50–100 |
|---|---|---|---|---|---|
| Shackleton | 0,357 | 0,299 | 0,403 | 0,647 | 0,952 |
| de Gerlache | 0,289 | 0,289 | 0,439 | 0,757 | 1,246 |
| Malapert | 0,327 | 0,365 | 0,596 | 1,049 | 1,672 |

  La correlación global `toterr`–distancia es 0,16 (Shackleton), 0,59 (de Gerlache) y 0,65 (Malapert): varía mucho entre sitios, así que **no sustituye** al mapa de distancia a observación.
- Efecto angular de un error vertical σ_z a distancia d: δθ ≈ σ_z / d. Con σ_z = 1 m: 0,057° a 1 km, 0,57° a 100 m, 1,9° a 30 m. Es irrelevante para crestas lejanas (el disco solar mide ~0,53°, semidiámetro 0,27°, **a verificar**) y dominante en campo cercano.

### 2.3 Regla propuesta de **Data Confidence** (convención LSI, a calibrar)

Se evalúa sobre un **disco de radio 100 m** centrado en el punto de observación (el mismo disco que la aptitud de aterrizaje; usar 50 m para la huella). Estadísticos:

| símbolo | definición |
|---|---|
| `g90` | percentil 90 de la distancia a observación (m) en el disco |
| `e90` | percentil 90 de `toterr` (m) en el disco |
| `f_obs` | fracción de píxeles con `ldec > 0` en el disco (informativo; mediana del recorte 0,076–0,097) |
| `gmax` | máximo de la distancia a observación en el disco (informativo) |

Clase:

- **ALTA:** `g90 ≤ 15 m` y `e90 ≤ 0,6 m`.
- **MEDIA:** `g90 ≤ 25 m` y `e90 ≤ 1,0 m`.
- **BAJA:** en otro caso.

Valor continuo: `DC = min( clip((40 − g90)/30, 0, 1), clip((1,5 − e90)/1,1, 0, 1) )`. Los anclajes salen de lo medido: `g90 = 10 m` ≈ la mediana del hueco más un píxel, `g90 = 40 m` > p99; `e90 = 0,4 m` ≈ mediana de `toterr`, `e90 = 1,5 m` > p99.

**Calibración medida** (rejilla de paso 100 m sobre todo el recorte, discos de 100 m; 24 964 discos en Shackleton y de Gerlache, 43 264 en Malapert):

| | % ALTA | % MEDIA | % BAJA | `DC` p5 / p50 / p95 | `g90` p5 / p50 / p95 (m) | `e90` p5 / p50 / p95 (m) | correlación `g90`–`e90` |
|---|---|---|---|---|---|---|---|
| Shackleton | 34,9 | 63,1 | 2,0 | 0,51 / 0,73 / 0,96 | 11,2 / 14,1 / 20,6 | 0,37 / 0,64 / 0,91 | 0,25 |
| de Gerlache | 40,7 | 54,8 | 4,5 | 0,50 / 0,81 / 0,96 | 11,2 / 15,8 / 25,0 | 0,42 / 0,57 / 0,82 | 0,78 |
| Malapert | 19,0 | 73,5 | 7,6 | 0,41 / 0,70 / 0,91 | 11,2 / 15,0 / 22,4 | 0,50 / 0,73 / 1,05 | 0,89 |

Lectura: el producto es muy homogéneo (la mayoría cae en MEDIA); la clasificación sirve para **comparar sitios y detectar parches malos**, no para certificar. **«ALTA» no significa resolución de 5 m**: significa huecos de ~15 m. La interfaz debe mostrar siempre «resolución efectiva ≈ 30 m» junto a la clase.

### 2.4 Señalar interpolación y su efecto en el horizonte

- **Por píxel:** interpolado = `ldec == 0`. **Hueco extenso** = distancia a observación `> 25 m` (≈ p99 del recorte). Capa de aviso recomendada: resaltar los píxeles con distancia `> 25 m` y los de `toterr > 1,5 m`.
- **Por horizonte:** para cada punto, informar (a) el percentil 95 de la distancia a observación en los píxeles que fijan el horizonte, (b) la fracción de acimuts cuyo píxel de horizonte tiene distancia `> 25 m`. En los 9 puntos de ejemplo la mediana de (a) es 5–10 m, su p95 10–25 m y (b) vale ≤ 2,2 %: **los píxeles de horizonte no están peor muestreados que el resto**. Regla: si (b) > 10 %, bajar una clase la confianza del horizonte.
- **Sensibilidad a la resolución efectiva** (horizonte recalculado con el DEM degradado a 20 m: promedio por bloques de 4×4 y bilineal, frente al DEM de 5 m; altura del observador 0 m; diferencia en grados de elevación del horizonte sobre 360 acimuts):

| punto | RMS | p95 \|Δ\| | máx \|Δ\| |
|---|---|---|---|
| Shackleton, centro | 0,20° | 0,50° | 0,87° |
| Shackleton, cota alta | 1,27° | 2,37° | 3,47° |
| Shackleton, parche llano | 0,99° | 2,44° | 2,83° |
| de Gerlache, centro | 0,49° | 1,11° | 1,99° |
| de Gerlache, cota alta | 0,86° | 1,58° | 1,59° |
| de Gerlache, parche llano | 0,51° | 1,26° | 1,87° |
| Malapert, centro | 0,20° | 0,46° | 0,70° |
| Malapert, cota alta | 1,14° | 1,81° | 2,08° |
| Malapert, parche llano | 0,58° | 1,36° | 1,72° |

  La incertidumbre del horizonte sólo por resolución es de 0,2–1,3° RMS (hasta 3,5°). Para el Sol polar (elevación máxima del orden de 1,5° por la oblicuidad de 1,54°, **a verificar**) **es del mismo tamaño que la señal**. Tolerancia de referencia: el semidiámetro solar (~0,27°).
- **Efecto de la altura del observador** (media del horizonte sobre 360 acimuts, en grados; la distancia mediana a la que se fija el horizonte en la última columna):

| punto | h = 0 m | h = 2 m | h = 10 m | d. mediana del horizonte (h = 0) |
|---|---|---|---|---|
| Shackleton, centro (pared interna) | 7,81 | 7,34 | 7,00 | 4678 m (horizonte lejano) |
| Shackleton, cota alta | 4,06 | 1,27 | −3,05 | 35 m |
| Shackleton, parche llano | 1,08 | −0,91 | −3,11 | 10 m |
| de Gerlache, cota alta | 0,68 | −1,59 | −4,07 | 15 m |
| Malapert, centro | 3,00 | 1,57 | −0,24 | 98 m |
| Malapert, cota alta | 1,10 | −1,62 | −2,88 | 8 m |

  **Recomendación:** `altura_observador` es un parámetro explícito de la interfaz (valor por defecto 2 m, **a verificar** según el vehículo o mástil de la misión) y el rayo debe empezar a ≥ 15 m del punto (exclusión del campo cercano, que es donde el DEM está interpolado). Mostrar la banda de sensibilidad horizonte(h = 0) – horizonte(h = 2 m).

---

## 3. Pendiente

### 3.1 Escala y baseline de `slp` (verificado contra `surf`)

Recálculo con diferencia central sobre `surf` y comparación con `slp` (interior, 20 px de margen), RMSE en grados:

| método | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| diferencia central, baseline **10 m** (píxel ±1) | **0,0002** | **0,0002** | **0,0008** |
| diferencia central, baseline 20 m (±2 px) | 1,19 | 0,97 | 1,30 |
| diferencia central, baseline 50 m (±5 px) | 2,08 | 1,73 | 2,20 |
| Horn 3×3 (sólo Shackleton) | 0,47 | — | — |

**`slp = atan( √(gx² + gy²) )`, con `gx = (z[i,j+1] − z[i,j−1]) / 10 m`** (y análogo en `gy`): baseline de 10 m (dos píxeles), sin suavizado de Horn. Notas:
- Se calcula en el plano estereográfico con píxel de 5 m. El factor de escala es k = 1 + (ρ/2R)²: 1,0001 en Shackleton y de Gerlache, 1,0012 en Malapert (ρ ≈ 121 km): despreciable (< 0,02° a 10° de pendiente).
- La pendiente es respecto a la normal local de la superficie ajustada, no respecto a la vertical del geoide (diferencia ~ d/R ≈ 3·10⁻⁴°).
- La capa no tiene NaN ni ceros espurios en el borde; **el tratamiento exacto del borde no está verificado**: excluir 2 px (10 m) en los bordes.
- Dependencia de la escala (p90 de la pendiente en el disco de 100 m para el parche llano de cada sitio, según baseline): Shackleton 11,4 / 11,0 / 10,5 / 10,8° (10 / 20 / 50 / 100 m); de Gerlache 8,75 / 8,43 / 8,21 / 7,84°; Malapert 7,83 / 7,46 / 6,97 / 6,65°. En la cota alta de Shackleton (relieve más suave pero con cráteres de ~100 m) cae de 12,2° a 5,3° al pasar de 10 m a 100 m. Conclusión: **evaluar a 10 m (la capa `slp`) y comprobar a 20 m**; a 10 m hay algo de ruido de interpolación (a 10–20 m la diferencia es < 1°), y los baselines ≥ 50 m ocultan cráteres de decenas de metros.

### 3.2 Receta de aptitud en un disco de 50–100 m

Entrada: píxel `(fila, col)`, radio `R` ∈ {50 m (huella más margen), 100 m (elipse de precisión del orden de 100 m, **a verificar** según misión)}.

1. `mk` = máscara del disco (píxeles con distancia ≤ R/5).
2. `s = slp[mk]`: **área bajo umbral** `A_θ = 100·mean(s < θ)` para θ = 5, 8, 10, 15°; `p90 = percentil90(s)`; `s_max`.
3. **Ajuste de plano** por mínimos cuadrados a `Z[mk]`: inclinación del plano (°) y **RMS de residuos** (rugosidad detrendada). Repetir con discos de 10, 25, 50, 100 m para ver la rugosidad por escala (usar sólo ≥ 50 m, sección 2.1).
4. **Data Confidence** (sección 2.3) con el mismo disco.
5. **Veredicto de ejemplo** (convención LSI, no requisito de misión): *apto* si `A_10 ≥ 90 %` y `p90 ≤ 10°` y `inclinación del plano ≤ 5°`; en otro caso *no apto*, y se muestra cuál de las tres condiciones falla.

El código está en `evalpoint()` del script de la sección 5. Los puntos de ejemplo no son recomendaciones de sitio; son una definición reproducible, igual para los tres recortes:
- `centro`: píxel central del recorte;
- `cota_alta`: máximo de `Z` suavizada con gaussiana de 100 m entre los píxeles no deprimidos (`Z ≥ media de 105 m`), a ≥ 3 km del borde;
- `parche_llano_alto`: máxima fracción de `slp < 10°` en una caja de ~105 m, entre los píxeles por encima del p70 de elevación y a ≥ 3 km del borde.

### 3.3 Resultados medidos en los puntos de ejemplo

Disco de 100 m (X, Y en m de la malla; latitud sobre la esfera de 1737,4 km, la longitud la debe fijar el módulo de coordenadas del proyecto):

| sitio / punto | X, Y (m) | lat | z (m) | `A_5` / `A_10` / `A_15` (%) | `p90` (°) | inclin. plano (°) | RMS detr. 50 m / 100 m | `g90` / `e90` | DC | veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| Shackleton, centro | −998, −7003 | −89,767 | 768 | 0 / 0 / 0 | 35,5 | 31,9 | 0,82 / 1,18 m | 14,1 / 0,94 | MEDIA | no apto |
| Shackleton, cota alta | −2773, −6143 | −89,778 | 1733 | 53,2 / 77,4 / 98,7 | 12,2 | 1,3 | 1,51 / 2,32 m | 11,2 / 0,58 | ALTA | no apto (`A_10`, `p90`) |
| Shackleton, parche llano | −1628, −11198 | −89,627 | 1547 | 25,2 / 82,1 / 99,5 | 11,4 | 3,7 | 1,06 / 2,81 m | 14,1 / 0,48 | ALTA | no apto con R = 100 m (`A_10` 82 %, `p90`) |
| de Gerlache, centro | −36998, 14998 | −88,684 | 1794 | 54,6 / 97,7 / 99,8 | 7,05 | 4,0 | 0,42 / 0,92 m | 15,8 / 0,52 | MEDIA | apto |
| de Gerlache, cota alta | −37513, 14928 | −88,669 | 1813 | 94,0 / 100 / 100 | 4,47 | 1,6 | 0,44 / 0,84 m | 18,0 / 0,55 | MEDIA | apto |
| de Gerlache, parche llano | −33863, 17693 | −88,740 | 1041 | 36,3 / 93,5 / 99,0 | 8,75 | 2,2 | 0,80 / 2,66 m | 25,0 / 0,78 | MEDIA | apto |
| Malapert, centro | −498, 121498 | −85,995 | 4784 | 49,4 / 96,6 / 100 | 8,40 | 3,4 | 0,66 / 1,80 m | 15,0 / 0,66 | MEDIA | apto |
| Malapert, cota alta | 4408, 121628 | −85,988 | 5173 | 91,4 / 100 / 100 | 4,69 | 0,4 | 0,28 / 0,86 m | 15,8 / 0,72 | MEDIA | apto |
| Malapert, parche llano | 5708, 121103 | −86,003 | 5141 | 54,7 / 98,8 / 100 | 7,83 | 4,6 | 0,36 / 0,94 m | 20,6 / 0,92 | MEDIA | apto |

Con disco de 50 m los dos puntos «no aptos» de Shackleton cambian de forma instructiva: el parche llano pasa a `A_10 = 100 %`, `p90 = 7,4°`, inclinación 3,0° (**apto**), la cota alta sigue sin serlo (`A_10 = 68,5 %`, `p90 = 11,9°`; hay un cráter de ~100 m y ~11 m de profundidad en la zona). **El resultado depende del radio**, y por eso la interfaz debe mostrar siempre el radio evaluado.

Observaciones: (a) en una meseta con RMS de 0,3–2,8 m a 50–100 m la rugosidad **crece** con la escala (la ley de potencias típica de un terreno natural); (b) la pendiente media a 10 m incluye la inclinación regional (inclinación del plano ≈ pendiente media), no sólo la rugosidad; (c) un cráter de ~100 m (20 píxeles) sí queda resuelto en el DEM.

---

## 4. Criterios de aptitud de aterrizaje y sombra

### 4.1 Pendientes máximas usadas y qué etiqueta llevan

| criterio | valor | alcance | fuente | etiqueta |
|---|---|---|---|---|
| LM de Apolo, tolerancia de pendiente del tren | ≈ 12° | diseño del vehículo | Documentación del LM / Apollo Operations Handbook | publicado; **cita exacta a verificar** |
| Selección de sitios de Apolo | pendientes < 2° (aproximación) y < 5° (zona de aterrizaje) | requisito de programa | Apollo Site Selection (varios informes NASA) | **a verificar** |
| Candidatas Artemis III (13 regiones, NASA 2022) | del orden de 5–10° a escala de decenas de metros | requisito de misión | NASA, anuncio de regiones candidatas; Artemis III Science Definition Team | **a verificar** (valor exacto y baseline) |
| IM-1 *Odysseus* (feb. 2024, cerca de Malapert A) | aterrizó y volcó en una pendiente reportada de ~12° | evento real | comunicados de Intuitive Machines y NASA | **a verificar** |
| Umbrales LSI 5° / 10° / 15° con baseline de 10 m (capa `slp`), radio 50–100 m | «benigno» < 5°, «límite» 10°, «excluido» > 15° | herramienta de apoyo a decisiones | este documento | **convención** (no es requisito de ninguna misión) |

LSI debe presentar la pendiente como **indicador** con su baseline y radio, no como «apto/no apto» oficial (alcance honesto del documento base, sección de límites). Un vehículo concreto (Starship HLS, Blue Moon, Griffin, etc.) tiene su propio requisito, que **hay que verificar en la fuente de la misión**.

### 4.2 Rocas y cráteres pequeños: lo que el DEM no ve

- **Rocas:** el DEM de resolución efectiva ~30 m no resuelve rocas (≲ 5 m). La abundancia de rocas se estima con LRO Diviner (Bandfield et al. 2011, *J. Geophys. Res.* 116, E00H02; **publicado**) y la identificación individual con imágenes LROC NAC (0,5–1,5 m/px, **publicado**: Robinson et al. 2010). En zonas permanentemente en sombra sólo ShadowCam (~1,7 m/px, **a verificar**) da imagen. LSI debe declarar «no evalúa rocas».
- **Cráteres pequeños:** para identificar un cráter en un DEM hacen falta ~5–8 elementos de resolución (regla empírica, **convención**); con 30 m eso son cráteres de ≳ 150–250 m. Cráteres de 10–100 m (con paredes de 20–30° y profundidades de 1–15 m) quedan sin resolver o suavizados. Medido: un cráter de ~100 m y ~11 m de profundidad sí aparece en el DEM de Shackleton (pero su pendiente máxima en el disco de 100 m sólo llega a 16,8°).
- **Regolito y sustrato:** el DEM no informa de la capacidad de carga ni del espesor de regolito (**fuera de alcance**).

### 4.3 Regiones en sombra permanente (PSR): por qué importan y por qué no puntúan como «buen sitio solar»

- Una PSR es una región que nunca recibe luz solar directa; sus temperaturas (< ~110 K) permiten trampas frías de volátiles (Mazarico et al. 2011, *Icarus* 211, 1066; **publicado**). Hay evidencia de agua en Cabeus (LCROSS; Colaprete et al. 2010, *Science* 330, 463), de hielo superficial en las PSR (Li et al. 2018, *PNAS* 115, 8907) y de trampas frías de escala métrica a kilométrica (Hayne et al. 2021, *Nature Astronomy* 5, 462). Todo **publicado**, volumen y páginas **a verificar**.
- **Interés científico y de recursos ≠ aptitud solar.** En una PSR la potencia solar es cero por definición y las comunicaciones directas a la Tierra dependen de que la línea de vista cruce el relieve. Un único score que mezcle ambos oculta el compromiso (el documento base lo advierte). Recomendación: **ejes independientes** «Potencial solar / enlace» y «Interés de recurso (proximidad a PSR/trampa fría)», y una etiqueta «contiguo a PSR a X m» con distancia, nunca sumada al score de potencia.
- **PSR desde el DEM:** requiere horizonte hasta distancias de decenas de km (sección 6) y la elevación solar máxima de ~1,5°; con la incertidumbre de horizonte de la sección 2.4 (0,2–1,3° RMS) el borde de una PSR es una **banda**, no una línea. En Shackleton el 18,8 % del recorte está por debajo de −1000 m (interior del cráter).
- **Datos en PSR:** LOLA es activo, por lo que su cobertura es la misma dentro y fuera de las sombras (9,1 % frente a 9,5 %, medido). Los modelos shape-from-shading (SDEM) mejoran sólo las zonas iluminadas (documento base, sección 2.2), así que en una PSR el DEM LOLA es lo mejor disponible y tiene los mismos huecos.

### 4.4 Bordes de los tres cráteres/macizos desde el punto de vista geológico

- **Shackleton (≈ 21 km de diámetro y ≈ 4 km de profundidad según Zuber et al. 2012, *Nature* 486, 378; publicado, a verificar):** el borde es una cresta elevada (en el recorte, z ≈ 1,2–1,8 km) con la pared interna a 30–37° (medido: mediana 32° en el centro del recorte, p99 37°) y suelo en sombra. Lo útil para el sitio de aterrizaje son los **parches llanos de la cresta** (pendiente 3–7°) y el hecho de que están junto a una PSR; lo difícil es el relieve local (RMS de 1–3 m a 50–100 m en los parches medidos, cráteres de ~100 m, pendientes locales de 17° en discos de 100 m).
- **de Gerlache (cráter antiguo, ~30 km, **a verificar**):** relieve más suave que Shackleton (pendiente media 14°, 54 % del área con < 15°; relieve de 2,6 km). El borde es una cresta degradada de 1,4–1,8 km con pendientes bajas en su cima (en la cota alta: 94 % del disco de 100 m con < 5°). Junto con la cima de Malapert, es donde mejor sale la aptitud de pendiente en los puntos de ejemplo.
- **Malapert (macizo, ≈ 5 km de relieve respecto a su entorno; medido 4,27 km dentro del recorte):** la cima es una meseta de 4,5–5,2 km con pendientes de 1,5–5° en parches de 50–100 m; no hay depresiones cerradas en el recorte. La visibilidad directa de la Tierra y la iluminación elevada del macizo son características publicadas (**a verificar** su cuantificación), y son justamente lo que LSI debe calcular, no asumir.

---

## 5. Script reproducible

El código completo está en el anexo al final de este documento. Ejecutar desde la raíz del repositorio con Python 3.11, `rasterio`, `numpy` y `scipy`: `python lsi_terreno.py shackleton` (o `de_gerlache`, `malapert`). Imprime un JSON con todas las cifras de este documento. Tarda 6–13 s por sitio. Los **azimuts son de malla** (0° = +Y, sentido horario); la conversión a azimut respecto al norte local es responsabilidad del módulo de coordenadas.


---

## 6. Límites del dato: extensión del DEM frente a horizontes lejanos

### 6.1 El problema, medido

- Los recortes miden 16 km (Shackleton, de Gerlache) y 21 km (Malapert). Desde un punto interior la distancia disponible hasta el borde del DEM por acimut es: centro de Shackleton y de Gerlache, 8,0 / 8,7 / 11,3 km (mínimo / mediana / máximo); centro de Malapert, 10,5 / 11,4 / 14,8 km; en los puntos más cercanos al borde, 3,8–6,2 km mínimo.
- **Ejemplo de horizonte abierto:** desde el centro de Shackleton (pared interna) el 41,9 % de los acimuts tiene el máximo de elevación en el último 10 % del rayo y el 40,6 % sigue subiendo en el borde (la elevación máxima llega a 32,7°, la pared opuesta del cráter). En los demás puntos de ejemplo es 0–1,7 % porque el relieve cercano domina, pero eso no demuestra que no haya relieve más allá.
- **El Sol rasante ve crestas lejanas.** Elevación aparente de un relieve de altura `h` (sobre el observador) a distancia `D` con curvatura esférica (R = 1737,4 km, observador a h = 0):

| altura h | D = 20 km | D = 40 km | D = 80 km |
|---|---|---|---|
| 500 m | 1,10° | 0,06° | −0,96° |
| 1000 m | 2,53° | 0,77° | −0,60° |
| 2000 m | 5,38° | 2,20° | 0,11° |

  Un relieve de 1 km a 20 km oculta el Sol hasta 2,5°, más que el horizonte medio de los puntos de ejemplo (0,7–4°). **Un DEM finito sólo puede sobrestimar la iluminación** (el terreno no incluido sólo puede añadir obstáculos); el sesgo es optimista y de signo conocido.

### 6.2 Cómo señalizarlo (propuesta)

1. Por acimut, calcular `estado_horizonte = ABIERTO` si el máximo de elevación cae en el último 10 % del rayo disponible **o** la elevación en el borde del DEM está a menos de 0,05° del máximo (`frac_open`, `frac_edge_rising` del script); `CERRADO` en otro caso.
2. En la gráfica de horizonte, dibujar los sectores `ABIERTO` rayados y rotular «horizonte truncado: el DEM cubre sólo X km en este acimut; el horizonte real es ≥ al dibujado».
3. En visibilidad solar y de la Tierra, si el acimut del cuerpo cae en un sector `ABIERTO` con elevación del cuerpo por debajo de `elevación del horizonte en el borde + margen`, marcar el instante como «cota superior de iluminación» (posible falso positivo), no como visibilidad confirmada.
4. En Data Confidence, restar un nivel si la fracción de acimuts `ABIERTO` es > 10 %, y publicar la fracción.
5. Mostrar la distancia mínima/mediana al borde del DEM junto al punto.

### 6.3 Opciones de datos ampliados

Los tamaños son **estimaciones por cálculo** (píxeles × bytes), no valores de catálogo; verificar en las URL oficiales PGDA/PDS antes de citarlos: <https://pgda.gsfc.nasa.gov/products/78> y <https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/>.

| opción | cobertura / resolución | tamaño aproximado | pros / contras |
|---|---|---|---|
| Recortes actuales (lo medido en `data/raw/`) | 16–21 km, 5 m, 4 capas | 164 MB por sitio de 16 km, 282 MB en Malapert (medido) | ya descargado; horizonte truncado |
| LOLA 20 m, 80°S–90°S (LDEM polar) | radio ≈ 304 km (2R·tan 5°), 20 m/px | ≈ 30 400 × 30 400 px × 2 B ≈ 1,8 GB (cálculo; **a verificar** formato y tamaño real) | cubre los tres sitios y todos sus horizontes (Malapert a ~121 km del polo); recortar una ventana de ±60 km (6000² px, ~72 MB en int16) o de ±120 km (12 000² px, ~288 MB) por sitio |
| LOLA a 10 m, ~85°S–90°S (**a verificar** si existe esta variante) | radio ≈ 152 km, 10 m/px | ≈ 30 300² px ≈ 1,8 GB | más detalle y menos extensión; cubre Malapert (ρ ≈ 121 km) con ~30 km de margen, pero con menos horizonte lejano que el de 80°S |
| SDEM shape-from-shading 5 m (13 regiones Artemis III; documento base §2.2) | recortes comparables a los actuales, 5 m (resolución efectiva mayor sólo en zonas iluminadas) | del orden de decenas a pocos cientos de MB por región y capa (**a verificar**) | mejora el detalle donde hay imagen LROC NAC; no ayuda en PSR; la diferencia SDEM−LDEM sirve como validación independiente de la interpolación |
| 100 clones del DEM (stretch) | misma malla que el DEM | 41–70 MB por clon y capa → 4–7 GB por sitio con 100 clones (cálculo) | análisis de sensibilidad; usar 5–10 clones |
| `slperr` (incertidumbre de pendiente) | misma malla | ≈ 41 MB (16 km) o ≈ 70 MB (21 km) por capa (cálculo) | alimentaría directamente Data Confidence de pendiente; **no se ha descargado** |

**Recomendación** (por coste/beneficio, hackathon):
1. Mantener los recortes de 5 m para el campo cercano (≤ 8–10 km) y las capas de confianza.
2. Añadir **una sola ventana del LOLA de 20 m** (±60 km) por sitio, sólo para el horizonte lejano: precalcular, una vez, el perfil de elevación aparente del terreno entre el borde del recorte y 60 km (360 valores por sitio) y usarlo como límite inferior del horizonte en los acimuts `ABIERTO`. Peso: unos 72 MB por sitio en origen, 360 números en la app.
3. SDEM y clones como *stretch*: SDEM primero sobre Shackleton si existe producto compatible (comprobar referencias, extensión y datum antes de mezclar; documento base).

---

## 7. Recomendaciones de validación geológica del motor

**Comprobaciones automáticas (pytest, valor esperado independiente):**
1. `slp` frente a `surf`: RMSE de la diferencia central de 10 m `< 0,01°` en el interior (medido 0,0002–0,0008°). Falla si alguien cambia el baseline o la georreferencia.
2. Las cuatro capas comparten transformación, forma y parámetros del CRS (**no** comparar `crs == crs`; Malapert `toterr` usa otro nombre) y cero NaN.
3. Georreferencia: `transform * (col + 0.5, fila + 0.5)` en el píxel del polo (fila 200, columna 1800 de Shackleton) da (0, 0) ± 2,5 m; el valor de `surf` en el polo (1289,1 m) debe contrastarse con una fuente independiente (**a verificar**).
4. Horizonte: terreno plano → elevación ≈ −D/(2R) en grados (−0,0165° a 1 km); obstáculo sintético en un acimut → pico sólo en ese sector (ya previsto en el plan); comparar con un segundo algoritmo (por ejemplo, una visibilidad por línea de vista) en 5 puntos reales con diferencia `< 0,1°`.
5. Sensibilidad del horizonte: recalcular con (a) DEM degradado a 20 m, (b) altura de observador 0 / 2 / 10 m, (c) perturbación del DEM con `toterr`, (d) clones. **Criterio sugerido:** si la dispersión del horizonte supera el semidiámetro solar (~0,27°) en algún acimut, marcar ese acimut como «incierto». Con lo medido (0,2–1,3° RMS) esto se activará con frecuencia: es un resultado, no un fallo.
6. Truncamiento: recalcular el horizonte con el DEM recortado a la mitad del radio y contar los acimuts que cambian más de 0,25°; esa fracción estima el efecto de la extensión finita (sección 6).
7. `ldec` y `toterr`: comprobar que los porcentajes de la sección 1 se reproducen (fracción de `ldec = 0` ≈ 90–92 %, distancia a observación p90 ≈ 15–16 m); una desviación indica descarga corrupta o producto distinto.
8. Enmascarar o resaltar `toterr > 1,5 m` (0,09–0,33 % del área, en pendientes de 34–60°) en vez de dejar que arrastren estadísticos.

**Comprobaciones visuales:**
1. Sombreado (hillshade) de cada recorte frente a LROC Quickmap / NASA Moon Trek en una misma región: crestas y depresiones en las mismas posiciones y misma orientación (descarta inversión de ejes X/Y, de signo de Y o de azimut).
2. Superponer el mapa de distancia a observación sobre el hillshade: buscar **rayas** en la dirección de las trazas del altímetro (artefactos de interpolación) y zonas suaves en forma de huecos.
3. Mapa de `slp` con la escala de 0–40°: las paredes internas de Shackleton (30–37°) deben verse como un anillo continuo; las mesetas, como parches de < 10°. Contrastar con el producto de pendiente publicado en PGDA para el mismo sitio (**a verificar** disponibilidad).
4. Perfil de horizonte (360°) del punto de ejemplo con las bandas de sensibilidad (h = 0 / 2 m y DEM 5 m / 20 m) y los sectores `ABIERTO` rayados.
5. Mapa de iluminación o visibilidad solar de Shackleton (con SPICE): el suelo del cráter debe quedar en 0 % y las crestas con valores altos; las crestas próximas al polo deben figurar entre las zonas más iluminadas (Mazarico et al. 2011 da cifras comparables; **a verificar**).

**Pruebas negativas que el motor debe superar:** un punto del interior de Shackleton no debe puntuar como «buen sitio solar»; un punto con `g90 > 25 m` o `e90 > 1 m` no puede salir con confianza ALTA; ningún resultado de rocas o de cráteres de menos de ~150 m debe presentarse como evaluado.

---

## Anexo — script de medición (`lsi_terreno.py`)

```python
"""Inventario y recetas de terreno LSI. Uso (desde la raíz del repo): python lsi_terreno.py shackleton|de_gerlache|malapert"""
import sys, re, glob, json, numpy as np, rasterio
from scipy import ndimage as ndi

site = sys.argv[1]; H = 5.0; RM = 1737400.0          # píxel (m), radio de referencia lunar (m)
def load(k):
    with rasterio.open(glob.glob(f'data/raw/{site}/*_{k}.tif')[0]) as s:
        return s.read(1).astype('float64'), s
crs_key = lambda s: (re.findall(r'PARAMETER\["[^"]+",[-0-9.]+\]', s.crs.to_wkt()), ',1737400,' in s.crs.to_wkt())   # los nombres del CRS difieren entre capas; los parámetros no
Z, sz = load('surf'); S, ss = load('slp'); D, sd = load('ldec'); E, se = load('toterr')
T = sz.transform; ny, nx = Z.shape
P = lambda a, q: np.nanpercentile(a, q).round(3).tolist()
out = {'site': site}
out['grid'] = dict(shape=Z.shape, bounds=tuple(sz.bounds), res=sz.res, same=all(
    s.transform == T and crs_key(s) == crs_key(sz) and s.shape == Z.shape for s in (ss, sd, se)),
    nan={n: float(np.isnan(a).mean()) for n, a in zip('Z S D E'.split(), (Z, S, D, E))})
out['surf'] = dict(min=float(np.nanmin(Z)), max=float(np.nanmax(Z)), pct=P(Z, [1, 5, 25, 50, 75, 95, 99]))
out['slp'] = dict(max=float(np.nanmax(S)), mean=float(np.nanmean(S)), p50_90_99=P(S, [50, 90, 99]), frac_lt_5_10_15=[round(float((S < t).mean()*100), 1) for t in (5, 10, 15)])
out['z_lt_-1000_frac'] = float((Z < -1000).mean()); out['z_gt_1000_frac'] = float((Z > 1000).mean())
rr_, cc_ = np.nonzero(Z < -1500); out['centroide_z<-1500_xy_m'] = [round(float(v), 0) for v in (T.c + T.a*(cc_.mean()+.5), T.f + T.e*(rr_.mean()+.5))] if rr_.size else None
obs = D > 0                                           # píxel con >=1 retorno LOLA
out['ldec'] = dict(frac0=float((D == 0).mean()), median=float(np.nanmedian(D)), max=float(np.nanmax(D)),
                   hist=np.bincount(D.astype(int).ravel()).tolist())
out['toterr'] = dict(pct=P(E, [1, 5, 25, 50, 75, 95, 99, 100]))
dnn = ndi.distance_transform_edt(~obs) * H            # distancia (m) al píxel observado más cercano
hp = Z - ndi.uniform_filter(Z, 3)                     # textura de alta frecuencia (Z - media 3x3)
out['hp_rms_m_por_dnn'] = {f'{a}-{b}': round(float(np.sqrt((hp[(dnn >= a) & (dnn < b)]**2).mean())), 3) for a, b in [(0, 1), (5, 8), (10, 13), (14, 20), (20, 1e9)]}
out['dnn'] = dict(p50_90_99_max=P(dnn, [50, 90, 99, 100]))

def cd(k):                                            # pendiente por diferencia central, baseline 2k píxeles
    gx = (np.roll(Z, -k, 1) - np.roll(Z, k, 1)) / (2*k*H); gy = (np.roll(Z, -k, 0) - np.roll(Z, k, 0)) / (2*k*H)
    return np.degrees(np.arctan(np.hypot(gx, gy)))
m = (slice(20, -20), slice(20, -20))
out['slp_check_rmse_deg'] = {f'{2*k*5}m': float(np.sqrt(np.nanmean(((cd(k) - S)[m])**2))) for k in (1, 2, 5)}
out['slp_edge_nan_or_zero'] = float(np.mean(S[0, :] == 0))
bins = [0, 5, 10, 25, 50, 100, 1e9]
out['toterr_mediana_por_dnn'] = [(a, b, float(np.nanmedian(E[(dnn >= a) & (dnn < b)])) if ((dnn >= a) & (dnn < b)).any() else None) for a, b in zip(bins[:-1], bins[1:])]
out['corr_toterr_dnn'] = float(np.corrcoef(E.ravel(), dnn.ravel())[0, 1])

SB = {10: S, 20: cd(2), 50: cd(5), 100: cd(10)}        # pendiente según baseline (m): 10 m = capa slp
def disk(r_m):
    n = int(round(r_m/H)); y, x = np.mgrid[-n:n+1, -n:n+1]; return (x**2 + y**2) <= (r_m/H)**2, n
def win(a, r, c, n): return a[r-n:r+n+1, c-n:c+n+1]
def detrend_rms(z, mask):                             # plano por mínimos cuadrados; devuelve (RMS residual m, inclinación °)
    n = z.shape[0]//2; y, x = np.mgrid[-n:n+1, -n:n+1]
    A = np.c_[np.ones(mask.sum()), x[mask]*H, y[mask]*H]; zz = z[mask]
    co, *_ = np.linalg.lstsq(A, zz, rcond=None); res = zz - A @ co
    return float(np.sqrt((res**2).mean())), float(np.degrees(np.arctan(np.hypot(co[1], co[2]))))
def evalpoint(r, c, R=100.0, ths=(5, 8, 10, 15)):
    mk, n = disk(R); s = win(S, r, c, n)[mk]; o = {'R_m': R}
    o['area_slope_lt_%'] = {t: round(float((s < t).mean()*100), 1) for t in ths}
    o['slope_mean_p50_p90_max'] = [round(float(v), 2) for v in (s.mean(), np.median(s), np.percentile(s, 90), s.max())]
    rms, tilt = detrend_rms(win(Z, r, c, n), mk); o['tilt_plane_deg'] = round(tilt, 2); o['rms_detr_m'] = round(rms, 3)
    o['rms_by_scale_m'] = {rr: round(detrend_rms(win(Z, r, c, disk(rr)[1]), disk(rr)[0])[0], 3) for rr in (10, 25, 50, 100) if rr <= R}
    o['p90_slope_por_baseline_m'] = {b: round(float(np.percentile(win(a, r, c, n)[mk], 90)), 2) for b, a in SB.items()}
    o['obs_frac'] = round(float(win(obs, r, c, n)[mk].mean()), 3)
    mk5, n5 = disk(500)
    o['obs_frac_500m'] = round(float(win(obs, r, c, n5)[mk5].mean()), 3) if min(r, c, ny-1-r, nx-1-c) >= n5 else None
    o['dnn_p50_p90_m'] = [round(float(v), 1) for v in np.percentile(win(dnn, r, c, n)[mk], [50, 90])]
    o['toterr_p50_p90_m'] = [round(float(v), 3) for v in np.percentile(win(E, r, c, n)[mk], [50, 90])]
    return o

def horizon(Zm, r0, c0, step=5.0, hobs=0.0):                    # azimut de MALLA (0° = +y, horario); con curvatura esférica exacta
    x0, y0 = c0, r0; z0 = Zm[r0, c0] + hobs; res = []
    for a in np.radians(np.arange(360)):
        dx, dy = np.sin(a), -np.cos(a)
        tx = (nx-1-x0)/dx if dx > 0 else (x0/-dx if dx < 0 else 1e9)
        ty = (ny-1-y0)/dy if dy > 0 else (y0/-dy if dy < 0 else 1e9)
        d = np.arange(step, min(tx, ty)*H, step)
        z = ndi.map_coordinates(Zm, [y0 + dy*d/H, x0 + dx*d/H], order=1)
        dl = d/RM; el = np.degrees(np.arctan2((RM+z)*np.cos(dl) - (RM+z0), (RM+z)*np.sin(dl)))
        k = el.argmax(); iy, ix = int(round(y0 + dy*d[k]/H)), int(round(x0 + dx*d[k]/H)); res.append((el[k], d[k], d[-1], el[-1], dnn[iy, ix], E[iy, ix]))
    return np.array(res)                              # elev. horizonte, dist. al horizonte, rango disponible, elev. en el borde

mg = 600                                              # margen 3 km al borde
zs = ndi.gaussian_filter(Z, 20); zs = np.where(Z >= ndi.uniform_filter(Z, 21), zs, -1e9)  # solo píxeles no deprimidos
sub = np.full_like(Z, -1e9); sub[mg:-mg, mg:-mg] = zs[mg:-mg, mg:-mg]
flat = ndi.uniform_filter((S < 10).astype(float), 21)  # fracción llana en ~100 m de lado
sc = np.where((Z > np.percentile(Z, 70)) & (sub > -1e8), flat, -1)
pts = {'centro': (ny//2, nx//2), 'cota_alta': np.unravel_index(sub.argmax(), Z.shape),
       'parche_llano_alto': np.unravel_index(sc.argmax(), Z.shape)}
Zc = Z[:ny//4*4, :nx//4*4].reshape(ny//4, 4, nx//4, 4).mean((1, 3))           # simula resolución efectiva 20 m
Z20 = ndi.zoom(Zc, 4, order=1)
Z20 = np.pad(Z20, ((0, ny-Z20.shape[0]), (0, nx-Z20.shape[1])), mode='edge')
out['points'] = {}
for nme, (r, c) in pts.items():
    r, c = int(r), int(c); x, y = T*(c+.5, r+.5)
    o = dict(rc=(r, c), xy_m=(float(x), float(y)), lat=round(float(-90 + 2*np.degrees(np.arctan(np.hypot(x, y)/(2*RM)))), 3),
             z=round(float(Z[r, c]), 1), edge_m=int(min(r, c, ny-1-r, nx-1-c)*H))
    o['eval100'] = evalpoint(r, c, 100.0); o['eval50'] = evalpoint(r, c, 50.0)
    h = horizon(Z, r, c)
    o['horizon'] = dict(dnn_en_horizonte_p50_p95_m=[round(float(v), 1) for v in np.percentile(h[:, 4], [50, 95])], frac_dnn_gt25=round(float(np.mean(h[:, 4] > 25)), 3), toterr_en_horizonte_p50_p95=[round(float(v), 2) for v in np.percentile(h[:, 5], [50, 95])], el_mean=round(float(h[:, 0].mean()), 2), el_p50_p95_max=[round(float(v), 2) for v in np.percentile(h[:, 0], [50, 95, 100])],
                        range_km_min_med_max=[round(float(v)/1000, 1) for v in (h[:, 2].min(), np.median(h[:, 2]), h[:, 2].max())],
                        d_horizon_med_m=float(np.median(h[:, 1])),
                        frac_open=round(float(np.mean(h[:, 1] > 0.9*h[:, 2])), 3),            # máximo en el último 10 % del rayo
                        frac_edge_rising=round(float(np.mean(h[:, 3] >= h[:, 0]-0.05)), 3))   # elevación en el borde ~ máximo
    o['horizon_vs_altura_obs'] = {hb: [round(float(v), 2) for v in (lambda q: (q[:, 0].mean(), np.percentile(q[:, 0], 95)))(horizon(Z, r, c, hobs=hb))] for hb in (0.0, 2.0, 10.0)}
    d = horizon(Z20, r, c)[:, 0] - h[:, 0]
    o['horizon_20m_vs_5m_deg'] = dict(mean=round(float(d.mean()), 3), rms=round(float(np.sqrt((d**2).mean())), 3), p95abs=round(float(np.percentile(abs(d), 95)), 3), maxabs=round(float(abs(d).max()), 3))
    out['points'][nme] = o
# ángulo que ocultaría un relieve fuera del DEM: atan2((RM+h)cos(D/RM)-RM, (RM+h)sin(D/RM)) con el observador a h=0
# --- Data Confidence por rejilla (paso 100 m): clases propuestas, disco R=100 m ---
mk, n = disk(100.0); G = []
for r in range(n, ny-n, 20):
    for c in range(n, nx-n, 20):
        g = np.percentile(win(dnn, r, c, n)[mk], 90); e = np.percentile(win(E, r, c, n)[mk], 90); G.append((g, e, win(obs, r, c, n)[mk].mean(), (win(S, r, c, n)[mk] < 10).mean()))
G = np.array(G); g, e = G[:, 0], G[:, 1]
cls = np.where((g <= 15) & (e <= 0.6), 'ALTA', np.where((g <= 25) & (e <= 1.0), 'MEDIA', 'BAJA'))
dc = np.minimum(np.clip((40-g)/30, 0, 1), np.clip((1.5-e)/1.1, 0, 1))
out['confianza_rejilla'] = dict(n=len(G), clases_pct={k: round(float((cls == k).mean()*100), 1) for k in ('ALTA', 'MEDIA', 'BAJA')},
    g90_pct=[round(float(v), 1) for v in np.percentile(g, [5, 50, 95])], e90_pct=[round(float(v), 2) for v in np.percentile(e, [5, 50, 95])],
    fobs_pct=[round(float(v), 3) for v in np.percentile(G[:, 2], [5, 50, 95])], DC_pct=[round(float(v), 2) for v in np.percentile(dc, [5, 50, 95])],
    corr_g90_e90=round(float(np.corrcoef(g, e)[0, 1]), 2), area_llana_lt10_frac_media=round(float(G[:, 3].mean()), 3))
out['angulo_cresta_lejana_deg'] = {f'h{hh}_D{Dk}km': round(float(np.degrees(np.arctan2((RM+hh)*np.cos(Dk*1e3/RM)-RM, (RM+hh)*np.sin(Dk*1e3/RM)))), 2) for hh in (500, 1000, 2000) for Dk in (20, 40, 80)}
print(json.dumps(out, indent=1, default=str))

```
