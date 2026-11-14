# Revisión matemática independiente del motor de visibilidad (T61)

Autor: rol matemático. Fecha: 2026-11-14. Código: `tests/test_independent_visibility.py` (26 pruebas, todas en verde, ~2 min).
Resultado en una línea: **el motor coincide con una formulación 3D cartesiana independiente; no se han encontrado errores de signo, marco ni curvatura; no hay bugs que documentar con `xfail`.** Hay una discretización conocida (§3) y una precisión de semántica (§4).

## 1. Método independiente (sin reutilizar geometría del motor)

Solo se usan: GeoTIFF con `rasterio`, kernels con `spiceypy`, `scipy.ndimage.map_coordinates` para la bilineal, `pyproj` como contraste de la proyección y `pipeline.run_analysis` **únicamente para comparar**.

1. Observador: `P0 = (R + z_dem + h)·n(lat,lon)` en MOON_ME, R = 1 737 400 m, h = 2 m. `z_dem` = bilineal propia del DEM de 5 m (igual al suelo del motor a < 0,05 m en los 6 puntos).
2. Dirección al cuerpo: `spkpos(cuerpo, et, 'MOON_ME', 'LT+S', 'MOON') − P0` (vector 3D directo, sin az/el). Contraste con `spkcpo`: < 1e-5°.
3. Línea de vista: el rayo `P0 + s·d` se muestrea (2,5 m hasta 2 km, 5 m hasta 5 km, 20 m hasta 30 km). Cada punto `Q` se proyecta a la esfera (`Q/|Q|`, estereográfica derivada a mano, comprobada contra `pyproj` con el CRS del GeoTIFF: < 1 mm) y se compara `|Q| − R` con `z` interpolado (5 m donde cubre; 80 m LOLA fuera; sin dato en ambos = sin obstáculo, contado: **0 muestras sin dato en todos los casos**). La curvatura aparece sola: no hay fórmula de horizonte.
4. Visible por el **centro del disco** (sin disco finito) y, aparte, por 300 rayos repartidos uniformemente en área sobre el disco (patrón de girasol sobre el casquete esférico).

Puntos (6): centro de los tres recortes (Site04 pared interna, Site11, Site23), TOP-1 del mapa de idoneidad de Site04 (borde alto, lat −89,563, lon 215,47) y de Site23, y un punto de pared de Site04 (pendiente 30° de la capa `slp`, lat −89,823). Ventanas (3 × 30 días, motor a 600 s, rayo 3D cada 30 min = 1 441 instantes por ventana): 2026-12-01, 2027-04-01, 2027-09-01. Total 36 series Sol/Tierra, 38 907 instantes.

## 2. Resultados: fracción de tiempo visible

Diferencia esperada entre ambos caminos: el motor usa disco finito (Sol ρ ≈ 0,27°, Tierra ρ ≈ 0,9°) y paso de 10 min con transiciones refinadas a 1 s; el test usa el centro. Solo pueden discrepar los instantes «parciales» (0 < f < 1): el centro está visible con f < 0,5 (o al revés) únicamente si el horizonte es inclinado dentro del disco. Por tanto:

| Comprobación | Resultado |
|---|---|
| Contradicciones duras (motor f ≤ 1e-3 y centro visible, o f ≥ 1−1e-3 y centro oculto) | **0 de 38 907 instantes** |
| Centro visible ⇔ f > 0,5 | 40 desacuerdos de 38 907 (0,10 %), todos en instantes parciales |
| Fracción de tiempo, centro vs `f > 0,5` | diferencia máxima 0,0090 (Site23 centro, Sol, ventana 1); la cota teórica es la fracción parcial (hasta 0,16) |
| Fracción de tiempo, centro vs `f` media (área) | máx. 0,016 en el Sol (media +0,0004); Tierra media −0,0013 |
| Centro dentro de [f ≥ 1−ε, f > ε] | cumplido en las 36 series (con tolerancia 0,004) |
| Métrica del motor (`solar_fraction`, `earth_fraction`) vs fracción por rejilla del mismo umbral | máx. 0,0006 (refinamiento a 1 s coherente con la rejilla de 30 min) |

Ejemplos (centro / motor f>0,5 / motor f>0,001 / motor f media): Site04 centro, 2026-12, Sol: 0,2727 / 0,2727 / 0,2831 / 0,2683. Site11 centro, 2026-12, Tierra: 0,6995 / 0,6995 / 0,7835 / 0,7011. Site04 TOP-1, 2027-04, Tierra: 0,7516 / 0,7453 / 0,8078 / 0,7469 (la mayor diferencia centro–`f>0,5`, 0,006: 9 instantes de 233 parciales).

## 3. Horizonte por azimut y disco finito con rayos 3D

**Perfil de horizonte.** Bisección en elevación del rayo 3D cada 5° de azimut (72 azimutes × 6 puntos) frente a `H_lb` del motor. Sin sesgo: media de la diferencia 3D − motor entre +0,0017° y +0,0071°. RMS 0,007°–0,023°. Máximos: 0,13° (Site11 centro, banda ≤ 10°), 0,09° (pared de Site04, solo a 20–34° de elevación, irrelevante para Sol/Tierra), resto < 0,075°. Todas las diferencias tienen el mismo signo: el motor queda por debajo del rayo 3D (optimista).

**Causa del residuo (aislada, no es un error de marco).** Con la rejilla radial de 5 m del motor, el rayo 3D reproduce su horizonte a < 0,01° (Site11 az 40°: motor −1,3283°, rayo 5 m −1,3239°; az 20°: 0,4461 / 0,4450; Site23 az 205°: −2,6175 / −2,6257). Con paso de 1 m el máximo sube (−1,1686°, 0,5533°, −2,5299°). El horizonte lo fija un relieve a 48–57 m del observador, donde la altura aumenta 0,14 m entre muestras de 5 m (≈ 0,13–0,16° a esa distancia): discretización radial del motor, de magnitud ≪ σ vertical del DEM. Esto contradice la cota de la cabecera de `horizon.py` («≈ 0,003° a 20 km») solo en campo muy cercano; a 0,15° el efecto sobre `f` solar es ≤ 0,08 en instantes parciales. No requiere corrección; se documenta.

**Estereográfica vs geodésica.** El motor traza rayos rectos en el plano estereográfico y los trata como arco de círculo máximo con `ψ = s/R`. Error teórico: factor de escala k − 1 = c²/4 (c = colatitud), ≈ 1,2e-3 en Site23 (lat −86°): ≤ 1 m de altura a 30 km (≈ 0,002°). Confirmado en Site23 (diferencia con rayo 3D de 5 m ≤ 0,008° en az 205°). Despreciable.

**Disco finito.** (a) Segmento circular `disc_fraction_flat` vs conteo de píxeles (4001²): error máximo 1,6e-4. (b) Horizonte ondulado, e = 0,5°, ρ = 0,27°: rebanadas del motor 0,69161 vs fuerza bruta 2D 0,69162. (c) 300 rayos 3D sobre el disco vs `f` del motor en ~64 instantes parciales por caso (5 casos): con la rejilla radial del motor, sesgo ≤ 0,003, RMS ≤ 0,011, máx. 0,026; con rejilla fina, sesgo ≤ 0,005, RMS ≤ 0,014, máx. 0,070 (Tierra ρ ≈ 0,9° incluida, máx. 0,024). La aproximación ΔA = x/cos e del motor es irrelevante a e ≤ 8°.

**Refinamiento temporal.** Cruces `f = 0,5` de un Sol real (horizonte plano a media altura del rango de elevación, 60 días, ≥ 2 cruces): bisección a 1 s del motor frente a rejilla de 5 s: diferencia ≤ 3 s (2,5 s de celda + 0,5 s de xtol); en cada cruce el centro está en el horizonte a < 0,01°.

## 4. Marcos, signos y semántica

- **Azimut.** Control por rumbos 0/90/180/270° a 10 km sobre círculo máximo desde (−89°, 37°E): az = 0°, 90°, 180°, 270° con tolerancia 0,01°; el destino al Este tiene λ mayor y el del Norte φ mayor. `sky.az/el` del motor = az/el con base ENU propia (E×N=U, N = U×E): < 1e-6° en 2 cuerpos × 100 instantes. Convención «Norte→Este, horario» correcta, sin inversión.
- **Proyección.** `x = ρ sin λ`, `y = ρ cos λ` (motor) = `pyproj` con el CRS del GeoTIFF (Polar_Stereographic, origen −90°, R = 1 737 400 m): < 1 mm, ida y vuelta de lat/lon < 1e-9°. El píxel centrado (`x0 = c + 0,5·px`) es consistente.
- **MOON_ME + LT+S.** Mismo vector que `spkcpo` (< 1e-5°); los resultados no dependen de MOON_PA ni de IAU_MOON.
- **Semántica (no es bug).** `solar_fraction` cuenta el Sol con `f > 1e-3` (basta una rendija) y `earth_fraction` con `f > 0,5`. Por eso `solar_fraction` supera la fracción «centro visible» hasta 0,076 (Site04 centro, 2027-09: 0,2295 vs 0,1534) y la iluminación efectiva (`effective_illumination`, media de `f`) está más cerca del centro (0,1565). Conviene que la UI no presente `solar_fraction` como «horas con el disco entero», sino «con alguna parte visible».
- **Cobertura.** Ningún rayo tocó nodata en los 6 puntos (r_max 30 km cubierto por 5 m + 80 m): `limited = 0` en todos los horizontes; la comparación es de límite inferior = valor real.

## 5. Límites de esta revisión

Seis puntos y tres ventanas de 30 días son una muestra, no una prueba exhaustiva. No se han revisado: modelo de potencia, score, incertidumbre ni la modalidad esfera lisa (cubierta por H1–H4 en `tests/test_horizon.py`). La comparación usa el mismo DEM y los mismos kernels que el motor: no valida los datos (LOLA/PGDA), solo la matemática que los usa. Altura del observador fija en 2 m.

## 6. Reproducir

`python -m pytest tests/test_independent_visibility.py -q` (≈ 2 min; marcadas `slow` las comparaciones con pipeline, que usan la caché de horizontes de `data/processed/horizons`).
