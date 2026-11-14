# Revisión geológica de lo que afirma LSI (T40)

Autor: geólogo planetario (agente). Fecha: 14/11/2026. Datos: `data/raw/{shackleton,de_gerlache,malapert}/` (LOLA/PGDA 5 m/px) y `data/processed/suitability/*.json` (TOP-5 del perfil `lander_solar_no_rhu`; los del `rover` se midieron igual y solo añaden 4 puntos distintos en Site11/Site23). Todas las cifras de las tablas están **medidas** con scripts propios sobre esos ficheros (horizontes con `lsi.terrain.horizon.compute_horizon`, observador a 2 m, campo lejano LOLA 80 m, paso azimutal 1°). Lo que no se midió lleva `a verificar`. No se ha modificado `src/`.

## Resumen

1. **La etiqueta «baja» constante tiene una causa matemática, no física.** `pipeline._dem_extras` calcula `c_sup = fracción de píxeles con ldec>0 en 2 km` (medido 5–16 %) y `data_confidence` exige `C = min(c_cov, c_sup, c_rango) ≥ 0,75` para «alta»: con ~9 % de píxeles observados en todo el DEM, `c_sup` no pasa de ≈ 0,17 (percentil 99). Salir de «baja» es estructuralmente imposible.
2. **La densidad de retornos casi no discrimina** (f_obs a 500 m, p5–p95: 6,6–11,9 % Shackleton, 5,5–13,6 % de Gerlache, 5,8–15,9 % Malapert). Discriminan la distancia al retorno (`g90`), `toterr` (`e90`) y la **inestabilidad del horizonte** `σh`, casi independiente de las otras dos (correlación 0,0–0,14).
3. **Propuesta calibrada (§2):** `c_sup := min(c_gap, c_err, c_hz)`, reutilizando los umbrales 0,75/0,5 vigentes. Sobre 1200 puntos de los tres DEM da 45 % alta / 47 % media / 8 % baja; sobre los 15 TOP de lander, 10 alta, 4 media, 1 baja.
4. **Geología:** los TOP son terreno alto (TPI500 +14…+46 m) en cresta/borde/meseta, pero a la escala de aterrizaje de NASA (radio 100 m) 7 de 15 tienen p90 de pendiente > 10° y 6 de 15 tienen píxeles > 20°; ninguna huella está libre de pendientes locales de 9–26°. Rocas y cráteres < 30 m no se ven. **Los 55 TOP de los 11 ficheros tienen `gate_status = FAIL` (peor subscore: `night`)**: «recomendado» no equivale a «pasa las puertas».
5. **Coordenadas:** ida y vuelta `stereo_forward/inverse` exacta (< 1 mm) y posiciones coherentes con los rasgos (§3), con un matiz: el rank 1 de Shackleton no está en el borde sino a 16 km del centro.

---

## 1. Por qué «baja» siempre (medido)

| | Shackleton | de Gerlache | Malapert |
|---|---|---|---|
| f_obs 500 m, p5 / p50 / p95 (%) | 6,6 / 8,8 / 11,9 | 5,5 / 7,4 / 13,6 | 5,8 / 9,8 / 15,9 |
| g90 (100 m), p5 / p50 / p95 (m) | 11,2 / 14,1 / 20,6 | 11,2 / 15,8 / 25,0 | 11,2 / 15,0 / 22,4 |
| e90 (100 m), p5 / p50 / p95 (m) | 0,37 / 0,64 / 0,91 | 0,42 / 0,57 / 0,83 | 0,50 / 0,73 / 1,05 |
| σh p90 (°), p5 / p50 / p95 (n = 400) | 0,003 / 0,032 / 0,241 | 0,004 / 0,041 / 0,248 | 0,005 / 0,059 / 0,260 |
| corr(σh p90, e90) / corr(σh p90, g90) | 0,14 / 0,00 | 0,14 / −0,03 | 0,10 / 0,01 |

(Rejilla de paso 100 m: 24 649 / 24 649 / 42 849 discos de 100 m; σh sobre 400 nodos aleatorios por sitio, semilla 7. σh = p90 sobre azimuts de |h(z+σz) − h(z−σz)|/2, es decir, el horizonte desplazado ±1 `toterr` en todo el terreno a la vez: hipótesis conservadora de error totalmente correlado.)

El ~91 % de píxeles interpolados es **uniforme**, así que cualquier métrica basada solo en la fracción observada es casi constante. La resolución efectiva (~30 m, `terreno-geologia.md` §2.1) tampoco cambia entre puntos. Lo que sí cambia: el hueco máximo entre trazas dentro de la huella, el error vertical local y cuánto mueve ese error al horizonte que decide la potencia solar.

## 2. Especificación: Data Confidence calibrada

Cambio mínimo: sustituir en `pipeline._dem_extras` el `c_sup` actual por el de abajo y dejar `data_confidence(c_cov, c_sup, c_range, ...)` y sus umbrales 0,75/0,5 como están.

```
g90  = p90 de la distancia (m) al retorno LOLA más cercano (ldec>0) en el disco de 100 m   [ya existe: DemConfidence.g90_m]
e90  = p90 de toterr (m) en el mismo disco                                                    [ya existe: DemConfidence.e90_m]
σh90 = p90 sobre azimuts de |H(z+toterr) − H(z−toterr)|/2 (°), k=1, mismo observador         [compute_horizon(sigma_sign=±1, k_sigma=1)]

c_gap = clip((40 − g90)/30, 0, 1)    c_err = clip((1,5 − e90)/1,1, 0, 1)    c_hz = clip((0,5 − σh90)/0,4, 0, 1)
c_sup = min(c_gap, c_err, c_hz)       C = min(c_cov, c_sup, c_range)         alta ≥ 0,75 · media ≥ 0,5 · baja < 0,5
```

Equivalencias físicas con los umbrales 0,75/0,5: **alta** ⇔ g90 ≤ 17,5 m, e90 ≤ 0,675 m, σh90 ≤ 0,20°; **media** ⇔ g90 ≤ 25 m, e90 ≤ 0,95 m, σh90 ≤ 0,30°; **baja** si alguno falla. Sin dato (g90 infinito o NaN): C = 0, nunca un valor plausible.

Respaldo de los anclajes (medidos arriba): g90 = 40 m > p99 de los tres DEM (25–30 m); e90 = 1,5 m > p99 (1,0–1,3 m); σh90 = 0,5° ≈ el diámetro solar (0,53°, `a verificar` el valor exacto) y > p99 de la muestra. 0,25° ≈ p95 y ≈ el semidiámetro solar (0,27°): un horizonte que se mueve más que el radio del disco solar cambia si el Sol se ve o no. Los límites alta/media de g90 y e90 coinciden con `terreno-geologia.md` §2.3 (convención LSI), que aquí se contrastan con la distribución real.

**Verificación en los 3 DEM (muestra de 400 nodos por sitio):**

| | % alta | % media | % baja | C p5 / p50 / p95 | factor limitante (gap / err / hz) |
|---|---|---|---|---|---|
| Shackleton | 44,5 | 49,8 | 5,8 | 0,48 / 0,73 / 0,96 | 169 / 199 / 32 |
| de Gerlache | 56,2 | 35,5 | 8,2 | 0,41 / 0,80 / 0,96 | 261 / 105 / 34 |
| Malapert | 33,8 | 55,8 | 10,5 | 0,42 / 0,69 / 0,92 | 1 / 372 / 27 |
| conjunto | 44,8 | 47,0 | 8,2 | | |

Malapert queda más en «media» porque su `toterr` es mayor (mediana 0,47 m frente a 0,36–0,37 m): propiedad real del dato, no artefacto.

**TOP-5 de cada sitio (lander_solar_no_rhu), disco de 100 m** (n/d: el disco de 2 km no cabe en el DEM):

| Sitio | Rank | g90 100 m (m) | gmax (m) | e90 (m) | f_obs 100 m / 500 m / 2 km | σh p90 (°) | c_gap / c_err / c_hz | C | Etiqueta |
|---|---|---|---|---|---|---|---|---|---|
| Site04 | 1 | 11.2 | 22 | 0.35 | 12.0 / 13.0 / n/d | 0.074 | 0.96 / 1.00 / 1.00 | 0.96 | alta |
| Site04 | 2 | 11.2 | 21 | 0.48 | 12.8 / 8.1 / 9.4 % | 0.016 | 0.96 / 0.92 / 1.00 | 0.92 | alta |
| Site04 | 3 | 11.2 | 25 | 0.53 | 9.2 / 7.4 / 7.6 % | 0.122 | 0.96 / 0.88 / 0.95 | 0.88 | alta |
| Site04 | 4 | 11.2 | 18 | 0.53 | 12.1 / 14.6 / n/d | 0.039 | 0.96 / 0.88 / 1.00 | 0.88 | alta |
| Site04 | 5 | 11.2 | 18 | 0.55 | 12.1 / 9.3 / 7.5 % | 0.151 | 0.96 / 0.87 / 0.87 | 0.87 | alta |
| Site11 | 1 | 11.2 | 21 | 0.41 | 11.8 / 8.6 / n/d | 0.090 | 0.96 / 0.99 / 1.00 | 0.96 | alta |
| Site11 | 2 | 15.8 | 32 | 0.59 | 7.3 / 8.6 / 7.1 % | 0.243 | 0.81 / 0.83 / 0.64 | 0.64 | media |
| Site11 | 3 | 11.2 | 25 | 0.44 | 10.6 / 7.9 / 7.4 % | 0.075 | 0.96 / 0.96 / 1.00 | 0.96 | alta |
| Site11 | 4 | 15.0 | 29 | 0.50 | 7.5 / 8.3 / n/d | 0.129 | 0.83 / 0.91 / 0.93 | 0.83 | alta |
| Site11 | 5 | 15.8 | 22 | 0.54 | 6.5 / 8.0 / 7.5 % | 0.127 | 0.81 / 0.87 / 0.93 | 0.81 | alta |
| Site23 | 1 | 14.1 | 29 | 0.71 | 15.1 / 13.4 / 10.6 % | 0.175 | 0.86 / 0.72 / 0.81 | 0.72 | media |
| Site23 | 2 | 18.0 | 29 | 0.78 | 8.5 / 10.3 / 11.0 % | 0.476 | 0.73 / 0.66 / 0.06 | 0.06 | baja |
| Site23 | 3 | 15.0 | 29 | 0.68 | 10.8 / 11.8 / 11.5 % | 0.150 | 0.83 / 0.74 / 0.87 | 0.74 | media |
| Site23 | 4 | 11.2 | 22 | 0.55 | 11.7 / 11.3 / 10.8 % | 0.216 | 0.96 / 0.86 / 0.71 | 0.71 | media |
| Site23 | 5 | 11.2 | 18 | 0.48 | 14.2 / 10.7 / 11.1 % | 0.080 | 0.96 / 0.93 / 1.00 | 0.93 | alta |

Lectura: Malapert 2 (σh90 = 0,48°) tiene un horizonte inestable pese a buena cobertura y sale «baja»; en el perfil rover, Malapert R1 (σh90 = 0,34°, C = 0,41) también, y Malapert R5 (g90 = 25 m, e90 = 1,0 m, σh90 = 0,71°, C = 0) es el peor del conjunto. Hoy los 15 salen «baja». `c_range` (incertidumbre temporal del score) se mantiene tal cual; no se evaluó aquí. «Alta» **no** significa resolución de 5 m: significa huecos ≲ 17 m y resolución efectiva ≈ 30 m; la interfaz debe mostrar esa frase junto a la etiqueta.

Código de referencia ejecutable y con test: `tests/test_geo_confidence_reference.py` (`disk_g90_e90`, `geo_confidence`; 5 pruebas, valores esperados calculados a mano). La parte `σh90` reutiliza `compute_horizon`: 2 llamadas más por punto (~0,25 s con paso de 1° y 10 m, medido).

## 3. Coordenadas: ¿caen donde dicen?

- Ida y vuelta `stereo_forward(lat, lon)` ⇄ `x, y` en los 55 TOP: error < 1 mm. Comprobación independiente: ρ ≈ R·colatitud (R = 1737,4 km); Site04 rank 1, ρ = 13,26 km da lat = −89,5627° (resultado: −89,5626°).
- Centros USGS (`config/sites.json`) proyectados: Shackleton (−89,67°, 129,78°E) → (7690, −6403) m, **fuera del recorte** (x máx. 7000 m); de Gerlache (−88,5°, 272,9°E) → (−45429, 2301) m, también fuera; Malapert (−85,98°, 358,33°E) → (−3554, 121898) m, dentro.
- Shackleton (radio ≈ 10,5 km: diámetro 21 km, Zuber et al. 2012, `a verificar`): ranks 2–5 a 10,0–10,6 km del centro, es decir, **en la cresta del borde**; el rank 1 está a 16,0 km, unos 5,5 km **fuera** del borde y a 1,3 km del límite oeste del recorte. No es «rim»: etiquetarlo «flanco externo / meseta».
- de Gerlache (≈ 30–32 km de diámetro, `a verificar`): los cinco a 14,9–16,1 km del centro = borde. Coherente.
- Malapert: ranks 1, 2, 4, 5 a 0,8–2,4 km del centro del macizo (z = 4,8–5,0 km; máximo del recorte 5174 m); rank 3 a 10,3 km, en la meseta cimera este (z = 5083 m, el máximo está en x = 4393 m). Coherente.

## 4. Revisión geológica de los TOP

| Sitio | Rank | z (m) | pend. p90 r50, b10 / b50 m (°) | % área <10° r100 | pend. máx r100 (°) | RMS 25 / 50 / 100 / 250 m (m) | TPI 500 m / 2 km (m) | pared >25° a (m) | PSR estricta más cercana (km) | f_sol |
|---|---|---|---|---|---|---|---|---|---|---|
| Site04 | 1 | 1692 | 5.3 / 4.6 | 97 % | 15 | 0.18 / 0.41 / 1.56 / 8.6 | +28 / n/d | 251 | ≤2.5 | 0.74 |
| Site04 | 2 | 1553 | 8.7 / 5.4 | 90 % | 16 | 0.46 / 1.00 / 1.93 / 9.3 | +45 / +231 | 127 | ≤2.1 | 0.72 |
| Site04 | 3 | 1557 | 8.7 / 6.1 | 88 % | 25 | 0.24 / 0.75 / 1.57 / 13.1 | +46 / +292 | 101 | ≤2.5 | 0.75 |
| Site04 | 4 | 1359 | 7.2 / 5.9 | 85 % | 22 | 0.22 / 0.71 / 2.39 / 6.1 | +31 / n/d | 232 | ≤2.8 | 0.63 |
| Site04 | 5 | 1415 | 7.4 / 5.7 | 80 % | 23 | 0.32 / 0.56 / 1.87 / 9.4 | +32 / +271 | 110 | ≤2.2 | 0.59 |
| Site11 | 1 | 1579 | 4.5 / 3.0 | 100 % | 9 | 0.24 / 0.50 / 1.10 / 5.6 | +24 / n/d | 358 | ≤3.4 | 0.87 |
| Site11 | 2 | 1531 | 5.0 / 4.1 | 92 % | 18 | 0.13 / 0.57 / 1.55 / 9.4 | +25 / +143 | 121 | ≤3.6 | 0.72 |
| Site11 | 3 | 1740 | 5.4 / 3.9 | 99 % | 15 | 0.35 / 0.42 / 0.76 / 5.1 | +19 / +179 | 301 | ≤3.8 | 0.70 |
| Site11 | 4 | 928 | 5.1 / 4.1 | 99 % | 15 | 0.25 / 0.42 / 1.63 / 5.7 | +21 / n/d | 215 | ≤2.7 | 0.56 |
| Site11 | 5 | 1793 | 5.9 / 5.2 | 100 % | 10 | 0.32 / 0.70 / 1.36 / 3.2 | +15 / +182 | 418 | >4 (no hallada) | 0.76 |
| Site23 | 1 | 4987 | 8.9 / 8.3 | 81 % | 26 | 0.30 / 0.76 / 2.36 / 5.3 | +23 / +183 | 97 | ≤1.0 | 0.94 |
| Site23 | 2 | 4930 | 6.1 / 5.5 | 98 % | 13 | 0.14 / 0.37 / 1.22 / 4.2 | +17 / +134 | 415 | ≤3.2 | 0.79 |
| Site23 | 3 | 5083 | 8.4 / 8.1 | 83 % | 21 | 0.16 / 0.50 / 1.75 / 4.4 | +18 / +93 | 412 | ≤1.6 | 0.90 |
| Site23 | 4 | 4882 | 8.0 / 7.2 | 87 % | 18 | 0.33 / 0.71 / 1.59 / 6.9 | +19 / +139 | 186 | ≤2.5 | 0.68 |
| Site23 | 5 | 4808 | 5.4 / 4.8 | 97 % | 22 | 0.12 / 0.38 / 1.22 / 5.8 | +14 / +82 | 426 | ≤3.5 | 0.61 |


Notación: b10/b50 = baseline de la pendiente (diferencia central a 10 y 50 m; la de 10 m es la capa `slp` de PGDA, verificada exacta en `terreno-geologia.md` §3.1); r50/r100 = radio del disco; TPI = cota del punto menos la media del disco de 500 m / 2 km; «PSR estricta» = distancia (rejilla de 500 m, ±4 km) al nodo más cercano cuyo horizonte mínimo (observador a 0 m, campo lejano incluido) supera la elevación solar máxima posible 1,54° + 0,27° + (90° − |lat|) (condición **suficiente, no necesaria**: subestima las PSR y sobrestima la distancia; sin ciclo de 18,6 años); `≤` indica cota superior.

**Pendiente.** Con r = 50 m y baseline 10 m (lo que usa el producto) los 15 TOP tienen p90 de 4,5–8,9°; con baseline 50 m, 3,0–8,3° (a 10 m el DEM interpolado apenas añade información). NASA define el sitio con radio de 100 m (§5) y a esa escala el p90 (b10) sube a 5,6–13,2° y la pendiente máxima a 9–26°. Shackleton 2–5 y Malapert 1, 3 y 4 tienen un 10–20 % del área > 10°. No hay huella totalmente llana: cada sitio exigiría elegir un parche dentro del disco.

**Rugosidad.** El RMS detrendado crece con la escala (0,1–0,5 m a 25 m; 0,4–1,0 m a 50 m; 0,8–2,4 m a 100 m; 3–13 m a 250 m): a 250 m ya es relieve (cráteres, ondulación), no rugosidad. **A 25 m es artefacto de interpolación** (≈ 9 % de píxeles con retorno; textura 20–100 veces menor en píxeles interpolados, `terreno-geologia.md` §2.1): no presentarla como rugosidad de regolito. Utilizable solo a ≥ 50 m y como indicador relativo.

**Posición.** Todos están por encima de su entorno (TPI500 +14…+46 m; TPI2000 +82…+292 m donde cabe): crestas, hombros y mesetas. En Shackleton 2, 3 y 5 el relieve dentro de 2 km es de 1,0–1,3 km (cota mínima 374–632 m frente a ~1550 m en el punto): son **borde de cráter**, con laderas > 25° a 101–127 m en Shackleton 2, 3 y 5 y a 97 m en Malapert 1. Gerlache 1, 3 y 5 y Malapert 2, 3 y 5 son los más holgados (laderas > 25° a ≥ 300 m).

**PSR.** 14 de los 15 TOP tienen una zona probablemente en sombra permanente a ≤ 1,0–3,8 km (Gerlache 5: ninguna a < 4 km). Es un dato útil (recursos, térmica), no un mérito del score solar. El producto da en la misma dirección: f_sol 0,56–0,94, y fracción de nodos candidatos con f_sol < 1 % de 22 % (Shackleton), 8 % (de Gerlache), 3 % (Malapert) (solo nodos candidatos, no es fracción de PSR del DEM). Límites: la PSR real exige varios años de efemérides y su borde es una banda (0,2–1° de incertidumbre de horizonte), no una línea; **no validado contra mapas PSR publicados (a verificar)**.

**Lo que el DEM no ve.** Rocas (≲ 5 m): ninguna información (Diviner/LROC NAC; cobertura en estos puntos `a verificar`). Cráteres de 10–100 m: invisibles o suavizados (resolución efectiva ≈ 30 m; identificar un cráter pide ~5–8 elementos, ≳ 150–250 m). Una pendiente máxima de 25° en un disco de 100 m (Shackleton 3) suele ser una pared que el DEM sí resuelve; los cráteres menores no. Regolito, capacidad de carga y espesor: fuera de alcance. El campo cercano (< 25 m) es interpolación pura.

**¿Son sitios de aterrizaje plausibles?** Como **zonas candidatas a inspeccionar**, sí: terreno alto, con luz y pendiente media baja a escala ≥ 50 m. Como **sitios de aterrizaje validados**, no: (a) todos tienen píxeles de 9–26° a escala de huella de 100 m; (b) rocas y cráteres pequeños sin evaluar; (c) todos fallan una puerta (`night`, perfil sin baterías ni RHU); (d) IM-1 (Odysseus) volcó apoyado en una roca con una pendiente local reportada de ~12° (§5), que es lo que este DEM no resuelve. Redacción recomendada: «zona candidata» con pendiente a r50 **y** r100, no «sitio recomendado».

## 5. Criterios de aptitud y su fuente

Búsqueda web del 14/11/2026 (los resultados son mayormente secundarios; se indica dónde consta la fuente primaria de NASA).

| Criterio | Valor | Alcance | Fuente | Estado |
|---|---|---|---|---|
| Criterios de selección de las 13 regiones candidatas Artemis III | pendiente del terreno, facilidad de comunicación con la Tierra, iluminación; luz continua durante los 6,5 días de estancia | misión (anuncio ago-2022) | NASA, anuncio de regiones (resumido en collectspace.com, khaleejtimes.com, spaceconnectonline.com.au) | **verificado (secundario)**; el anuncio no da valores de pendiente |
| Tamaño de región y de sitio | región ≈ 15 × 15 km; sitio = radio ≈ 100 m dentro de la región | misión | NASA vía americaspace.com (ago-2022) | **verificado (secundario)** |
| Inclinación máxima del lander HLS | ≤ 8° respecto a la vertical (≈ pendiente 8°); «tolerancia de pendiente de al menos 8°» | requisito del vehículo (Starship HLS) | prensa especializada y diapositiva NASA HLS (NTRS 20240009596) | **verificado (secundario)**; localizar el requisito primario |
| Pendiente en EVA | < 20° | requisito de superficie | NASA, NTRS 20240009596 (2024) | **verificado (secundario)** |
| Pendiente < 5° en área de ≥ 100 m de radio | 5° | interpretación de una presentación universitaria (cita HLS-R-0071/HLS-R-0021) | no NASA | **no verificado como requisito NASA**; no usar como tal |
| Estudio MCDM Artemis III | asume sitios con pendiente ≤ 10° | estudio académico | arXiv 2406.19863 | verificado; **convención académica**, no requisito |
| Reducción 13 → 9 regiones, priorizando área de baja pendiente | n/a | misión (2025) | NASA, NTRS 20250011660 | verificado (resumen); estado actual de Artemis III **a verificar** (`luna-spice-sitios.md` apunta reorientación en feb-2026) |
| IM-1 Odysseus, feb-2024 | volcó apoyado en una roca; pendiente local ~12° (una sola fuente, spacenexus.us, atribuida a LRO); inclinación final ~30° | evento real | Intuitive Machines/NASA vía prensa | vuelco verificado; **12° no verificado en fuente NASA** |
| LM de Apolo tolerancia ≈ 12°; sitios Apolo < 2° / < 5° | | diseño / programa | memoria (`terreno-geologia.md` §4.1) | **no verificado** |
| Umbrales LSI 5° / 10° / 15°, baseline 10 m, radio 50–100 m | | herramienta de apoyo | este proyecto | **convención LSI**; el producto debe mostrar baseline y radio |
| PSR < ~110 K; hielo en PSR (Mazarico 2011; Hayne 2021; Li 2018) | | ciencia | `terreno-geologia.md` §4.3 | **no verificado en esta sesión** |
| Fracción iluminada de Shackleton ~240 días/año (Mazarico 2011) | | publicación | `luna-spice-sitios.md` (resumen NTRS 20120010094) | verificado antes; comparar con el f_sol del producto **pendiente** |

Pendientes: citar el documento NASA primario del requisito de 8° de HLS; confirmar si el criterio de pendiente de las regiones candidatas es sobre un disco de 100 m y a qué baseline (de ello depende si `r50 + baseline 10 m` del producto es comparable); validar PSR contra un mapa publicado; contrastar f_sol de Shackleton con Mazarico 2011.

## 6. Recomendaciones (equipo de código)

1. Sustituir `c_sup` según §2 (localizado en `pipeline._dem_extras` más un helper; `data_confidence` no cambia).
2. Mostrar pendiente a **r50 y r100** y baseline 10 y 50 m, con `% área > 10°` y pendiente máxima (hoy solo r50/b10 p90).
3. No mostrar rugosidad a < 50 m como medida; marcarla «interpolada».
4. Renombrar «recomendado» a «candidato»; mostrar `gate_status` junto al rank (55/55 FAIL).
5. Etiquetar el rank 1 de Shackleton como «flanco externo» y avisar de que los centros curados de Site04/Site11 caen fuera del recorte.
6. Añadir «PSR estricta a X km (cota)» como eje aparte, nunca sumada al score solar.
