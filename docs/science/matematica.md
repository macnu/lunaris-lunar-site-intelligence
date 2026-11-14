# LSI — Especificación matemática (v1.0, 14/11/2026)

Autor: rol «matemático aplicado». Destinatarios: ingenieros que implementan `src/` (terreno, efemérides,
visibilidad, potencia, score). Cada sección da fórmula, convención, unidades, dominio, error esperado y
**caso de prueba numérico**. Los valores marcados `[V]` se han **calculado y ejecutado** con Python
(NumPy, SciPy, rasterio, pyproj, SpiceyPy y los kernels de `kernels/`). Los marcados `[SPICE-reg]` son
valores de regresión de nuestro propio SPICE (no independientes: contrastar con Horizons, §8). Todo lo que
no tiene fuente verificable lleva `a verificar` o `a calibrar con experto`.

Notación: φ = latitud selenocéntrica (sur negativa), λ = longitud este positiva en [0°, 360°), R = 1 737 400 m,
A = azimut, e = elevación, z = altura del DEM sobre la esfera R.

---

## 0. Resumen de decisiones que afectan al código

1. El DEM real **no declara un CRS «bonito»**: es una proj a medida (esfera R = 1 737 400 m, estereográfica
   polar sur, lat_ts = −90). `pyproj` no la considera `==` a la nuestra por los nombres, pero transforma idéntico
   (§1.4). Usar siempre `always_xy=True`.
2. El horizonte plano `atan2(z−z₀, r)` del documento base **sobrestima** el horizonte en `s/(2R)` radianes
   (0.13° a 8 km, 0.26° a 16 km, 0.49° a 30 km). Usar la fórmula exacta con curvatura (§2). Es barata.
3. Muestreo radial **uniforme a 5 m** (paso de píxel), no adaptativo grueso: el adaptativo (0.5 % de r) subestimó
   el horizonte hasta 0.14° en el DEM real (§2.5). Azimut cada **0.25°** (error de interpolación angular ≤ 0.05°).
4. Cobertura del DEM ≈ 16 km × 16 km y **el punto de observación suele estar cerca de un borde**: el horizonte más
   allá es desconocido. Se entrega `H` como **cota inferior** + bandera por azimut (§2.6).
5. Potencia: por defecto, panel **vertical con seguimiento azimutal** y **vertical fijo** son los montajes
   relevantes en el polo (el Sol nunca pasa de ~1.6° de elevación; un panel horizontal da < 1 %). §6.
6. Score: **media geométrica ponderada** con puertas duras y rango por incertidumbre (§7).

---

## 1. Proyección estereográfica polar sur (PGDA/LOLA)

### 1.1 Definición

Esfera R = 1 737 400 m (radio de referencia lunar 1737.4 km, el mismo de PGDA; no hay achatamiento).
Proyección estereográfica polar sur con punto de tangencia/escala verdadera en el polo (lat_ts = −90°, k₀ = 1),
meridiano central 0°, falsos este/norte 0.

Directa (φ, λ → x, y), φ en grados, resultado en metros:

    ρ = 2·R·cos φ / (1 − sin φ)          (equivale a 2·R·tan((90° + φ)/2))
    x = ρ · sin λ
    y = ρ · cos λ

Inversa (x, y → φ, λ):

    ρ = hypot(x, y)
    φ = −90° + 2·atan(ρ / (2R))
    λ = atan2(x, y)  mod 360°           ← OJO: argumentos (x, y), no (y, x)

Factor de escala (puntual, isótropo — la proyección es conforme):

    k(φ) = 2 / (1 − sin φ)   =  1 / cos²((90° + φ)/2)

### 1.2 Convención de ejes y de signo (verificada con PROJ)

- Vista **desde fuera, mirando al polo sur**. `+y` apunta a λ = 0° (meridiano de Greenwich lunar, ME),
  `+x` apunta a λ = +90° E. λ crece en sentido antihorario en la imagen.
  - (φ = −89.9°, λ = 0°) → (0, +3032.336 m); λ = 90° → (+3032.336, 0); λ = 180° → (0, −3032.336); λ = 270° → (−3032.336, 0) [V].
- Relación con MOON_ME cartesiano: `x_plano = Y_ME`, `y_plano = X_ME` (cerca del polo).
- **Norte/Este locales en el plano** en un punto de longitud λ: Norte local = `(sin λ, cos λ)` (hacia fuera
  del polo), Este local = `(cos λ, −sin λ)`. Por tanto un rayo de azimut A (desde el Norte hacia el Este) tiene
  dirección en el plano:

      (dx, dy) = ( sin(λ + A),  cos(λ + A) )         ← «azimut de cuadrícula» = λ + A

  Esto es lo que usa el horizonte (§2). En el polo exacto (ρ = 0) λ es indeterminado: convención **λ = 0**.
- Distorsión en la zona del DEM: k(−89.9°) = 1.00000076; k(−85°) = 1.0019; k(−80°) = 1.0077 [V].
  Dentro del DEM (ρ ≤ 17.5 km) k − 1 ≤ 2.5·10⁻⁵ → **se puede medir distancias directamente en el plano**
  (error ≤ 0.4 m a 16 km). Una recta del plano se desvía del círculo máximo ≈ κL²/8 con κ = ρ/(2R²):
  0.04 m a 16 km [V]. Despreciable.

### 1.3 Geometría real del GeoTIFF (`data/raw/shackleton/Site04_final_adj_5mpp_surf.tif`) [V]

| Propiedad | Valor |
|---|---|
| Tamaño | 3200 × 3200 px, 1 banda, float32 |
| Geotransform (affine) | (5, 0, −9000, 0, −5, +1000) |
| Extensión X | −9000 … +7000 m |
| Extensión Y | −15000 … +1000 m |
| Registro | **píxel** (`AREA_OR_POINT=Area`, GMT `node_offset=1`): el origen es la esquina del píxel; el centro del píxel (0,0) es x = −8997.5, y = +997.5 |
| nodata | `nan` declarado; **0 NaN en `surf`** (10 240 000 válidos) |
| z (m, sobre la esfera R) | mín −2847.88, máx +1805.07, media 245.3 |
| CRS declarado | WKT sin autoridad: `PROJCS["unnamed", ... SPHEROID["unnamed",1737400,0] ... Polar_Stereographic, latitude_of_origin −90, central_meridian 0, false_easting/northing 0`, ejes (Easting, Northing) ambos etiquetados NORTH |
| Equivalente proj | `+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs` |
| Productos hermanos | `ldec` (cuenta de retornos 0–5), `slp` (pendiente 0–69.6°), `toterr` (σz total) con la misma malla |

Índice de píxel **centrado** (fórmula obligatoria para muestrear con interpolación bilineal):

    col = (x − (−9000)) / 5 − 0.5          fila = (1000 − y) / 5 − 0.5
    x   = −9000 + 5·(col + 0.5)            y   = 1000 − 5·(fila + 0.5)

`rasterio.index(x, y)` devuelve la **celda que contiene** el punto (floor), válido solo para lectura de valor
más cercano. Para bilineal usar las fórmulas de arriba (coordenadas de píxel continuas, centros en enteros).

Lat/lon del DEM (inversa propia = pyproj a 1e-9 m) [V]:

| Punto | x, y (m) | φ (°) | λ (° E, 0–360) |
|---|---|---|---|
| Polo sur | 0, 0 | −90 | 0 (convención) |
| Centro del DEM | −1000, −7000 | −89.766811 | 188.130102 (= −171.8699) |
| Esquina NO | −9000, +1000 | −89.701373 | 276.340192 |
| Esquina NE | +7000, +1000 | −89.766811 | 81.869898 |
| Esquina SO | −9000, −15000 | −89.423127 | 210.963757 |
| Esquina SE | +7000, −15000 | −89.454123 | 154.983107 |

Hallazgos que importan al producto:
- El **polo sur cae dentro del DEM**, en el píxel (fila 200, col 1800), z = 1289.1 m. El DEM va del polo hasta
  φ ≈ −89.42°; **no cubre λ ≈ 0° a 3 km del polo** (y = +3032 m queda fuera, y_max = +1000 m).
- El anillo φ = −89.9° (ρ = 3032.3 m) está dentro: z entre −339 y +1506 m. El mínimo suavizado (−2.8 km,
  suelo profundo) está en el **borde este** (x ≈ 7 km, λ ≈ 120°, φ ≈ −89.73°): el suelo de Shackleton queda
  cortado por la cobertura. Coordenada IAU del centro de Shackleton: `a verificar` (no usar sin cotejar).
- Máximo (1805 m) en x = −8997.5, y = −11087.5 → φ −89.529°, λ 219.06°: pegado al borde oeste.
- Huella del DEM = diagonal máxima polo–esquina 17.5 km; desde un punto cualquiera el alcance disponible suele ser
  4–16 km según el azimut (§2.6).
- `ldec == 0` en el **90.8 %** de los píxeles (interpolados, sin retorno propio); pendiente (`slp`): mediana
  20.6°, p95 34.6°, p99 37.4°; `toterr`: mediana 0.36 m, p95 0.83 m, máx 7.6 m [V]. Un 5 m/px **no** es
  resolución efectiva de 5 m (advertencia ya en el documento base §2.1).
- (Al empezar esta tarea `toterr` era un `.part`; ya está completo y se lee bien.)

### 1.4 Cómo construir el `pyproj` equivalente

```python
from pyproj import CRS, Transformer
R = 1737400.0
STERE = CRS.from_proj4("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs")
GEO   = CRS.from_proj4("+proj=longlat +R=1737400 +no_defs")
fwd = Transformer.from_crs(GEO, STERE, always_xy=True)   # (lon, lat) -> (x, y)
inv = Transformer.from_crs(STERE, GEO, always_xy=True)   # (x, y) -> (lon, lat)  lon en (-180, 180]
```

- `CRS.from_wkt(src.crs.to_wkt()) == STERE` da **False** (nombres de datum/esfera distintos) pero el
  `Transformer` construido con el CRS del archivo da el mismo resultado: (0, −3032.3358) → lon 180, lat −89.9 [V].
- Diferencia entre `pyproj` y las fórmulas §1.1 en 100 000 puntos aleatorios (φ ∈ [−90,−80]): ≤ 4·10⁻¹⁰ m en
  directa; ida y vuelta ≤ 1.4·10⁻¹⁴° [V].
- pyproj devuelve λ en (−180, 180]: normalizar con `% 360`.
- No usar `rasterio` `crs.to_epsg()` (devuelve `None`). Guardar la cadena proj como constante del proyecto y
  **comprobar al cargar** que el WKT del archivo contiene `Polar_Stereographic`, `latitude_of_origin −90`,
  `1737400` (fallar si no).

### 1.5 Casos de prueba (tolerancias en §8)

| # | Entrada | Salida esperada |
|---|---|---|
| P1 | φ=−89.9°, λ=0° | x=0, y=+3032.335812 m |
| P2 | φ=−89.9°, λ=90° | x=+3032.335812, y≈0 |
| P3 | φ=−89.9°, λ=180° | x≈0, y=−3032.335812 |
| P4 | x=3000, y=4000 (ρ=5000 m) | φ=−89.835111°, λ=36.869898° (= atan2(3,4)) |
| P5 | φ=−90° | ρ=0, k=1 |
| P6 | φ=−89.9° | k = 1.0000007615 |
| P7 | Centro del píxel (fila 200, col 1800) | x = −9000+5·1800.5 = +2.5, y = 1000−5·200.5 = −2.5 (el polo está en la esquina común de 4 píxeles) |
| P8 | `d.index(0,0)` | (200, 1800); `d.xy(0,0)` = (−8997.5, 997.5); `d.xy(3199,3199)` = (6997.5, −14997.5) |

(P7: el polo exacto x=y=0 está en la esquina compartida de los píxeles (199,1799), (199,1800), (200,1799),
(200,1800); su z interpolado bilineal es 1289.36 m [V].)

---

## 2. Horizonte local con curvatura lunar

### 2.1 Por qué cambia el documento base

El documento base usa `H(A) = max_r atan2(z(r,A) − z₀, r)`: asume plano tangente. La Luna cae bajo el plano
tangente en `s²/(2R)`: 18.4 m a 8 km, 73.7 m a 16 km, 259 m a 30 km [V]. En ángulo, el plano **sobrestima la
elevación** (horizonte más alto → menos Sol) en `s/(2R)` rad: **0.132° a 8 km, 0.264° a 16 km, 0.495° a 30 km**
[V], frente a un disco solar de 0.533° de diámetro. En el DEM real (observador en Shackleton rim, 2 m), plano −
curvo: media 0.086°, máx 0.23° [V].

### 2.2 Fórmula exacta

Observador a radio `R + z₀` (z₀ = z_DEM(x₀,y₀) + h_obs, h_obs = 1, 2 o 5 m), muestra del terreno a distancia
horizontal `s` (a lo largo de la superficie ≈ distancia en el plano, §1.2) y altura `z` sobre la esfera.
Ángulo central ψ = s/R. En el plano vertical que contiene al observador, al centro y a la muestra, con el
observador en `(0, R+z₀)` y la muestra en `((R+z)·sin ψ, (R+z)·cos ψ)`:

    el(s) = atan2( (R+z)·cos ψ − (R+z₀) ,  (R+z)·sin ψ )         [elevación sobre el plano horizontal local]
    H(A)  = max_s el(s)         (sobre las muestras con dato válido)

Aproximación equivalente (error < 10⁻⁶ rad si |z−z₀| ≪ R y ψ ≪ 1; en la cresta de prueba coincide a 1e-7°):

    el(s) ≈ atan2(z − z₀, s) − s/(2R)

Recomendación: implementar la **exacta** (coste idéntico en NumPy).

Horizonte de esfera lisa (suelo de todo horizonte; todo `z = 0`, observador a altura h sobre la esfera):

    H_esfera(h) = −acos( R / (R + h) ) ≈ −sqrt(2h/R)          (se alcanza en s* = R·acos(R/(R+h)) ≈ sqrt(2Rh))

### 2.3 Casos analíticos de prueba [V]

| # | Caso | Esperado |
|---|---|---|
| H1 | Esfera lisa, h = 1 m | −0.061473° |
| H2 | Esfera lisa, h = 2 m | −0.086937° (s* = 2636 m); aproximación −sqrt(2h/R) = −0.086937° |
| H3 | Esfera lisa, h = 5 m | −0.137459° |
| H4 | Esfera lisa, h = 100 m / 1000 m | −0.614720° / −1.943496° |
| H5 | Cresta de 100 m a 5 km sobre esfera lisa, h_obs = 2 m (z₀ = 2) | exacta **1.040375°**; plana 1.122854° (error del plano 0.082478°); aprox `atan2(98,5000) − s/2R` = 1.040375° |
| H6 | Cresta idéntica (100 m, h_obs 2 m) a 16 km | exacta **0.087096°**; plana 0.350932° (error 0.263836°) |
| H7 | Suelo `z = z₀` en todo el DEM (h = 0) | `el(s) = −ψ/2`; el máximo es la primera muestra: H = −5/(2R) rad = −8.24·10⁻⁵° |

Validar H1–H5 con `max` sobre una malla fina de ψ (el test muestrea ψ ∈ (0, 0.01] con 2·10⁶ puntos y coincide
con `−acos(R/(R+h))` a 1e-12°).

### 2.4 Algoritmo y vectorización (NumPy)

Entrada: DEM `Z` (float64), observador (x₀, y₀), h_obs, r_max, ΔA, Δr.

1. `λ₀ = atan2(x₀, y₀)` (0 si ρ=0). `z₀ = bilineal(x₀,y₀) + h_obs`.
2. Azimutes `A_j = j·ΔA`, j = 0 … 360/ΔA − 1. **ΔA = 0.25°** (1440 rayos).
3. Distancias `r_k = k·Δr`, k = 1 … N, **Δr = 5 m** (= píxel), `r_max` = min(lo pedido, alcance de cobertura).
4. Muestra: `γ_j = λ₀ + A_j`; `x = x₀ + r_k·sin γ_j`, `y = y₀ + r_k·cos γ_j` (§1.2).
5. Bilineal con la indexación centrada de §1.3 (4 vecinos). Una muestra es **inválida** si cae fuera del
   DEM o alguno de los 4 vecinos es NaN/nodata. **Nunca** convertir nodata a 0 (obstáculo falso).
6. `el_{jk}` exacta (§2.2); inválidas → `−inf`. `H_j = max_k el_{jk}`.
7. Procesar por bloques de azimut (p. ej. 120 rayos × N muestras) para acotar memoria: arrays de
   `120 × 6000 × 8 B ≈ 6 MB` por temporal.

Complejidad: O(N_az · N_r) = 1440 × 6000 = 8.6·10⁶ muestras bilineales por observador. **≈ 1 s** en un núcleo
con NumPy puro (medido 1.0–1.15 s para r_max 16 km/30 km) [V]. Memoria por bloques: < 100 MB.

Interpolación de H para azimut arbitrario: lineal **circular** sobre `H_j` (`np.interp` con periodo 360°).

### 2.5 Paso radial y azimutal: medidas en el DEM real [V]

- Paso radial adaptativo (5 m hasta 1 km, luego 0.5 % de r; 881 muestras en vez de 6000) **subestima** H hasta
  **0.14°** (media 0.013°) respecto al uniforme a 5 m. → **Usar Δr = 5 m uniforme.** Optimización permitida
  solo si se demuestra, con este mismo test, error < 0.01°.
- Interpolación angular: tomando como verdad ΔA = 0.125°, el error máximo de interpolar con ΔA = 1° es
  0.25° (media 0.011°), con 0.5° es 0.12°, con 0.25° es **0.053°** (media 0.002°). Todos son
  subestimaciones (el máximo entre rayos se pierde). → **ΔA = 0.25°.**
- Sesgo conservador opcional: sumar a H el error de interpolación estimado (0.05°) en modo «prudente».
- Si se permite elegir altura de observador distinta de 2 m, el cambio de horizonte por h_obs 1→5 m es de orden
  `Δz/s` (5 m/1 km = 0.29°): exponerlo como parámetro, no constante.

### 2.6 Cobertura limitada del DEM («horizonte limitado por cobertura»)

El DEM cubre ~16 km × 16 km y el observador raramente está centrado: la distancia de cobertura por azimut
`r_cov(A)` (último r válido) varía de ~1 km (observador cerca del borde, como el polo y el borde oeste) a 16 km;
en observadores medios la media es ~8.5–9 km y ~40–50 % de los azimutes tienen cobertura < 30 km [V].

Definiciones por azimut:

- `H_lb(A)` = `H` calculado (**cota inferior**: el terreno más allá de `r_cov` puede subirlo).
- `limitado(A) = True` si el rayo sale del DEM (o toca nodata) antes de `r_max`.
- `H_ub(A) = max( H_lb, max_{s ≥ r_cov} el(s; z = z_up) )`, con `z_up` = `z_max` del DEM (parámetro,
  `a calibrar`): cota superior **muy pesimista** (altura máxima del DEM a todo r ≥ r_cov). En el DEM real da brechas
  medias de 0.5–8.6° entre H_lb y H_ub: sirve como **diagnóstico**, no como valor central.
- **`desconocido_relevante(A) = limitado(A) AND H_lb(A) < e_max_cuerpo + ρ_cuerpo`**, con `e_max_cuerpo` la
  elevación máxima del cuerpo en el periodo (se calcula de la propia serie SPICE; en el polo sur: Sol ≈ 1.6°,
  Tierra ≈ 6.9° + libración, `[V]` ±1.58° / ±6.85° en 2026). Solo estos azimutes pueden cambiar el resultado de ese
  cuerpo.

Salidas obligatorias del motor de horizonte: `H_lb[ΔA]`, `r_cov[ΔA]`, `limitado[ΔA]`, `H_ub[ΔA]` (opcional),
`fraccion_azimut_desconocido_relevante` (para Sol y para Tierra), y la etiqueta de la UI **«horizonte limitado
por cobertura»** cuando esa fracción > 0.

Efecto sobre la visibilidad: con `H_lb` se obtiene la fracción **máxima** de visibilidad (optimista); con `H_ub`
la **mínima** (pesimista). Reportar `[f(H_ub), f(H_lb)]` como rango (alimenta §7.5). Estados de visibilidad en
un instante: «oculto seguro» (e + ρ < H_lb), «visible» (e − ρ > H_ub) o «visible sujeto a cobertura» (resto).

Observador a menos de 2 px del borde: rechazar (error `observer_outside_dem`).

---

## 3. Orientación topocéntrica: de MOON_ME a (azimut, elevación)

### 3.1 Cadena

1. Tiempo UTC → ET: `spice.str2et` (kernel `naif0012.tls`).
2. `spkezr(cuerpo, et, 'MOON_ME', 'LT+S', 'MOON')` → vector selenocéntrico `v_c` (km) en el marco fijo MOON_ME
   (kernels `moon_080317.tf`, `moon_assoc_me.tf`, `moon_pa_de421_1900-2050.bpc`, `de421.bsp`; marco en el que
   están el DEM y las coordenadas). `cuerpo` = `'SUN'`, `'EARTH'` (399, centro de la Tierra).
3. Posición del observador: `p = (R + z₀)·Û(φ, λ)` con Û abajo.
4. **Vector desde el observador**: `v = v_c − p` (¡paralaje! imprescindible para la Tierra: R/d = 0.0045 rad =
   **0.259°**; para el Sol 4.7·10⁻⁵ rad = 9.9″, no despreciable solo a nivel de tolerancia).
5. Base ENU en MOON_ME para (φ, λ):

       Este   Ê = (−sin λ,           cos λ,           0      )
       Norte  N̂ = (−sin φ·cos λ,    −sin φ·sin λ,     cos φ  )
       Arriba Û = ( cos φ·cos λ,     cos φ·sin λ,     sin φ  )

   Orto-normal y diestra: Ê × N̂ = Û. En φ = −90°: Ê = (−sin λ, cos λ, 0), N̂ = (cos λ, sin λ, 0), Û = (0,0,−1).
6. Componentes `e = v·Ê`, `n = v·N̂`, `u = v·Û`:

       A  = atan2(e, n)  mod 360°           (0 = Norte, 90 = Este, sentido horario visto desde arriba)
       el = atan2(u, hypot(e, n))           (sin refracción: no hay atmósfera)

Dominio: φ ∈ [−90°, 90°], λ cualquiera. En el cenit/nadir (`hypot(e,n) = 0`) A está indefinido: devolver A = 0
(documentado). Coherencia con el plano del DEM (§1.2): en φ = −90° y λ = 0, `N̂ = +X_ME = +y_plano`, `Ê = +Y_ME = +x_plano`.

### 3.2 Casos de prueba (sin SPICE; vectores en MOON_ME, observador sobre la superficie)

| # | Observador (φ, λ) | Vector `v` | az, el esperados |
|---|---|---|---|
| E1 | (0°, 0°) | (1, 0, 0) | el = +90° (cenit) |
| E2 | (0°, 0°) | (−1, 0, 0) | el = −90° |
| E3 | (0°, 0°) | (0, 1, 0) | az = 90°, el = 0° |
| E4 | (0°, 0°) | (0, 0, 1) | az = 0°, el = 0° |
| E5 | (−90°, 0°) | (0, 0, −1) | el = +90° (cenit en el polo sur) |
| E6 | (−90°, 0°) | (cos 5°, 0, −sin 5°) | az = 0°, el = 5° |
| E7 | (−90°, 0°) | (0, 1, 0) | az = 90°, el = 0° |
| E8 | (−90°, 90°) | (0, 1, 0) | az = 0°, el = 0° (N̂ = (cos 90°, sin 90°, 0) = +Y) |
| E9 | (−90°, 180°) | (1, 0, 0) | az = 180°, el = 0° (N̂ = (−1,0,0)) |
| E10 | Paralaje: (0°,0°), `p=(R,0,0)`, Tierra a `v_c = (0, 384400, 0)` km | topo: `v = (−1737.4, 384400, 0)` | az = 90°, **el = −0.258962°** (= −atan(R/d)) |

Los casos E1–E9 se calculan a mano con la base ENU; E10 [V]: atan(1737.4/384400) = 0.2589620°.

### 3.3 Regresión SPICE `[SPICE-reg]` (kernels del repo)

Observador φ = −89.9°, λ = 129.78° E, z₀ = 0, 2026-12-01T00:00:00 UTC (valores de nuestra implementación; no
independientes):

| Cuerpo | Distancia | az (topo) | el (topo) | el (geocéntrico, sin paralaje) |
|---|---|---|---|---|
| Sol | 147 553 142.16 km (lt 492.18 s) | 150.28503° | +1.38330° | +1.38397° |
| Tierra | 376 517.14 km (lt 1.2559 s) | 236.89153° | −1.66477° | −1.40050° |

Observaciones: la diferencia topo−geo de la Tierra es −0.2642° (≈ R/d·cos(el)); para el Sol 0.00067°. Sub-Tierra
lat/lon = +1.346°/+6.67°. Elevación de la Tierra en el polo sur a lo largo de 2026: −6.85° … +6.80°, por encima
del horizonte esférico el **47.1 %** del año; Sol: −1.59° … +1.56°, 51.4 % [V]. Distancia Tierra–Luna 356 663–406 403 km;
Sol–Luna 146.79–152.48 millones km.

Procedimiento obligatorio de validación (§8): contrastar estas cifras con JPL Horizons.

---

## 4. Disco finito: tamaño angular, fracción visible, clasificación

### 4.1 Radio angular aparente

    ρ = asin( R_cuerpo / d )

- Sol: R☉ = 695 700 km (IAU 2015 B3, nominal), d = distancia Sol–observador de SPICE. A 1 UA
  (149 597 870.700 km, IAU 2012) ρ = **0.266453°** (959.23″). Rango en 2026: 0.26142°–0.27154° (d = 152.48/146.79·10⁶ km) [V].
- Tierra: R = 6371.0 km (radio medio; achatamiento 0.3 % → error < 0.1 %; el equatorial 6378.137 km da 0.1 %
  más). A d = 384 400 km ρ = 0.9507°; rango 0.8982°–1.0235° (d = 406 403/356 663 km) [V]. Sin atmósfera terrestre
  en el limbo (visibilidad geométrica).

### 4.2 Fracción visible con horizonte plano

Sea `t = (e − H)/ρ` (centro del disco respecto al horizonte, en unidades de radio). Fracción de **área** visible
(disco uniforme, segmento circular):

    f(t) = 1/2 + ( t·sqrt(1 − t²) + asin t ) / π        para |t| ≤ 1;   f = 0 si t ≤ −1;  f = 1 si t ≥ 1

Tabla de prueba (analítica) [V]: f(−1)=0; f(−0.5)=0.195501; f(0)=0.5; f(0.5)=0.804499; f(1)=1.
Comportamiento cerca de t = −1: `f ≈ (4√2/(3π))·(1+t)^{3/2}` (crecimiento no analítico; relevante para brentq).

### 4.3 Horizonte variable sobre el ancho del disco

Con `H(A)` (interpolado) variable, coordenada tangente `x ∈ [−ρ, ρ]` (ángulo medido sobre el cielo, perpendicular a
la vertical del cuerpo), semialtura de cuerda `c(x) = sqrt(ρ² − x²)`, y diferencia de azimut `ΔA = x/cos e`:

    f = (1/(π·ρ²)) · ∫_{−ρ}^{ρ}  clip( e + c(x) − H(A_c + x/cos e) , 0 , 2·c(x) ) dx

Cuadratura: sustituir `x = ρ·sin φ_i`, φ_i = −π/2 + (i+½)π/n, `dx = ρ cos φ_i·(π/n)`, **n = 64 rebanadas**
(punto medio). Error medido contra la fórmula §4.2: 8.5·10⁻⁶ (n=64), 10⁻⁴ (n=16) en t = −0.5 [V].
Válido para e < ~60° (aproximación de campo pequeño de `x/cos e`); en el polo e ≤ 8°.

Casos de prueba [V] (ρ = 0.26649°):
- Horizonte plano y `e = t·ρ`: reproduce §4.2 (t=±0.5 → 0.195493/0.804507 con n=64).
- Pared vertical que cubre exactamente la mitad izquierda del disco (`H = 89°` para ΔA < 0, `0°` para ΔA ≥ 0), e = 10°: **f = 0.5**.
- Horizonte inclinado `H(A) = e + 0.3·(A − A_c)` (pasa por el centro del disco): **f = 0.5** por simetría.

### 4.4 Clasificación

Con ε = 10⁻³ (parámetro):

    f ≤ ε          → «oculto»
    ε < f < 1 − ε  → «parcial»
    f ≥ 1 − ε      → «visible» (disco completo)

Criterio de «ventana» por cuerpo (parámetro `f_thr`): **Sol: f > ε** (hay luz; el amanecer/ocaso es el
primer/último limbo); **Tierra para comunicaciones: f ≥ 0.5** (centro del disco con línea de vista; `a calibrar con
experto de comunicaciones`). Guardar siempre f(t) completo, no solo el booleano.

### 4.5 Oscurecimiento de limbo (opcional, solo Sol)

    I(μ)/I₀ = 1 − u·(1 − μ),   μ = sqrt(1 − (r/ρ)²),   u ≈ 0.6 (visible; `a verificar`, depende de la banda)
    f_flujo = ∫_visible I dA / ∫_disco I dA          (∫_disco I dA = π ρ² (1 − u/3))

Efecto sobre f [V] (u = 0.6, horizonte plano): t = −0.5: 0.17588 (frente a 0.19550); t = 0: 0.5; t = +0.5: 0.82412
(frente a 0.80450); t = −0.9: 0.01299 (frente a 0.01869). Corrección ≤ 2 puntos de f: **desactivado por defecto**,
activable para el modelo de potencia.

---

## 5. Ventanas temporales

### 5.1 Definiciones

Para un cuerpo, `f(t) ∈ [0,1]` (§4) continua en t si `H(A)` es continua. Estado `s(t) = [f(t) > f_thr]`. Una
**ventana** es un intervalo maximal `[a, b)` con `s = True`. Oscuridad = complemento sobre el intervalo analizado.
Nota de alcance: «oscuridad» aquí es «sin disco solar visible» (relieve); **no** incluye eclipses lunares
(Tierra tapando al Sol, ~2/año, hasta ~3.5 h; `a verificar` duración) — v1 no los modela y debe decirse.

### 5.2 Algoritmo (paso grueso + refinamiento)

1. Rejilla `t_k = t₀ + k·Δ`, Δ = 600 s (10 min), k = 0 … N. N = 52 560 para 365 d.
2. Efemérides **vectorizadas**: `spkezr(cuerpo, lista_de_et, ...)` devuelve todos los vectores en una llamada
   (medido: 52 560 instantes en 0.48 s por cuerpo [V]; las llamadas escalares cuestan ~10 µs).
3. `(A_k, e_k, ρ_k)` por §3 y §4.1; `f_k` por §4.3 (vectorizable con broadcasting `N × 64`).
4. Transiciones: índices k con `s_k ≠ s_{k+1}`.
5. Refinamiento por raíz: `brentq(lambda t: f(t) − f_thr, t_k, t_{k+1}, xtol=1.0 s)`. Cada evaluación es
   `spkezr` escalar + integral de 64 términos (~0.1 ms). Convergencia en ~10–12 evaluaciones (600 s → 1 s).
   Para `f_thr = ε` la función cerca de la raíz es `∝ (1+t)^{3/2}`: brentq converge igual (cambio de signo
   garantizado). Si se quiere «1 min o mejor» sin SPICE por raíz, bisección sobre rejilla de 1 min también vale.
6. Tiempos de evento = raíces; ventanas = pares (subida, bajada).

Regla de no-pérdida de eventos: un evento más corto que Δ solo puede existir si el horizonte tiene un hueco más
estrecho que lo que el cuerpo recorre en Δ. El Sol se mueve ≈ 12.19°/día = 0.0085°/min en azimut → **0.085° en
10 min** (la Tierra, mucho menos). Como el horizonte se muestrea a ΔA = 0.25°, estructuras más finas ya no
existen en los datos. Condición de diseño: `Δ·ω_max ≤ ΔA/2` → Δ ≤ 14 min con ΔA = 0.25° (10 min cumple).
Verificación obligatoria: el conjunto de ventanas con Δ = 5 min y Δ = 10 min debe coincidir (±1 s/evento).

Alternativa sin refinamiento: fuerza bruta a 1 min: 525 600 instantes × 64 rebanadas ≈ 3.4·10⁷ operaciones
(≈ 1 s) + 5 s de SPICE vectorizado. Es viable; el esquema 10 min + raíz se mantiene por precisión sub-minuto y
porque es lo que dice el documento base.

### 5.3 Métricas y álgebra de intervalos

Ventanas = lista ordenada de pares disjuntos `[a_i, b_i)`.

- **Visibilidad solar** = Σ(b−a)/T (T = duración del intervalo). Métrica complementaria: **iluminación efectiva**
  = media de `f(t)` (trapecio sobre eventos refinados + rejilla).
- **Ventana más larga**: `max(b−a)`. **Max darkness**: `max` sobre el complemento.
- **Unión** de dos listas: ordenar por `a` y fusionar si `a_{i+1} ≤ b_i + tol` (tol = xtol = 1 s: un hueco
  menor que la tolerancia de raíz es ruido numérico).
- **Solape** (Sol ∩ Tierra): intersección con dos punteros, O(n+m): `[max(a_i,c_j), min(b_i,d_j))` si longitud > 0.
- **Ventana truncada**: la ventana que empieza en t₀ (s₀ = True) lleva `izq_truncada = True`; la que acaba en
  t_N, `der_truncada = True`. Su duración es una **cota inferior**: la «ventana más larga» / «max darkness» se
  reportan como `≥ X` si la ganadora está truncada, y la UI lo indica. Las estadísticas de fracción
  (Σ/T) no se ven afectadas.

Complejidad para 1 año: SPICE vectorizado 2 cuerpos ≈ 1 s; visibilidad O(N·64)·2 ≈ 7·10⁶ operaciones; refinamiento:
K eventos × ~12 evaluaciones × 0.1 ms (K ~ 10²–10³/año según el sitio) ≈ 0.1–1.5 s. **Total ≲ 5 s por sitio-año**
(+ ~1 s de horizonte, §2.4).

### 5.4 Casos de prueba [V]

Cuerpo sintético: horizonte plano H = 0, ρ = 0.26649°, `e(t) = 1.5°·sin(2π t/24 h)`, `f_thr = ε = 10⁻³`.
- Raíz de subida: t = **−0.672530 h** (analítico: `T/(2π)·asin(t*·ρ/a)` con t* = −0.985926, raíz de f(t*) = ε).
- Raíz de bajada: t = **12.672530 h**; duración de ventana **13.345060 h**.
- Con el criterio «limbo superior» (e + ρ = 0): −0.682233 h; la diferencia con el criterio f = ε es 0.0097 h = 35 s.
- Truncado: intervalo [0 h, 6 h] → una ventana con `izq_truncada = True`, `b = 6 h` (der_truncada = True), duración ≥ 6 h.
- Solape: A = {[0,10), [20,30)}, B = {[5,25)} → solape {[5,10), [20,25)}; unión A∪B = {[0,30)}.

---

## 6. Modelo de potencia de paneles (funcionalidad nueva)

Alcance honesto: es una **estimación de potencia relativa** con supuestos declarados; no sustituye un modelo
de misión (batería, degradación real, sombra propia, albedo). Parámetros de célula/panel concretos: ver
`docs/science/paneles-y-misiones.md`; los valores de aquí marcados «ejemplo» son marcadores hasta cotejarlos.

### 6.1 Ecuación

    P_rel(t) = f(t) · max(0, cos θ_inc) · IAM(θ_inc) · η_rel(T) · (UA/d)² · (1 − degradación) · (1 − polvo)

donde `P_rel = P(t)/P_nominal` y `P_nominal` = potencia a 1361 W/m², incidencia normal, T = 25 °C, a 1 UA (STC
espacial, `η_ref`). Unidades: adimensional ∈ [0, ~1.04]. `f(t)` es la fracción visible del Sol (§4; flujo si se
activa el limbo). Puede ser > 1 en el perihelio (factor distancia 1.034) y por frío (η_rel > 1): es correcto,
no recortar a 1 (sí limitar η_rel, §6.5).

### 6.2 Irradiancia y factor de distancia

    G(t) = G₀ · (UA/d)²,   G₀ = 1361 W/m² (TSI nominal, UA = 149 597 870.700 km), d = |vector Sol–Luna| de SPICE

Fuente de la constante: resolución IAU 2015 B3 (S☉ᴺ = 1361 W/m²); medición TSI 1360.8 ± 0.5 W/m² (Kopp & Lean
2011). Citadas de memoria: **`a verificar` en la fuente primaria** antes de publicar. La variación del ciclo
solar (~±0.1 %) se desprecia.
Rango en 2026 con d de SPICE (146.79–152.48·10⁶ km): factor 1.0386–0.9626, **G = 1413.5 – 1310.1 W/m²** [V].
Perihelio/afelio teóricos: factor 1.0343/0.9674.

### 6.3 Ángulo de incidencia por montaje

Vector solar en base ENU: `ŝ = ( cos e·sin A,  cos e·cos A,  sin e )`. Normal del panel `n̂_p` (unitario en ENU).
`cos θ = ŝ · n̂_p`.

| Montaje | Parámetros | `n̂_p` | `cos θ_inc` |
|---|---|---|---|
| Horizontal | – | (0,0,1) | `sin e` |
| Inclinado fijo | inclinación β desde la horizontal, azimut de la normal γ | (sin β sin γ, sin β cos γ, cos β) | `sin β·cos e·cos(A−γ) + cos β·sin e` |
| Vertical fijo | β = 90°, cualquier γ | (sin γ, cos γ, 0) | `cos e·cos(A−γ)` |
| Vertical con seguimiento azimutal | β = 90°, γ = A (sigue al Sol) | (sin A, cos A, 0) | `cos e` |
| Dos ejes | n̂_p = ŝ | ŝ | 1 |
| Sobre pendiente del terreno | normal del suelo (σ, α): n̂_s = (sin σ sin α, sin σ cos α, cos σ) | n̂_s (montaje «plano» sobre el suelo) | `ŝ · n̂_s` |

Convención de γ: igual que el azimut (0 = Norte, 90 = Este). `cos θ` negativo → el Sol está detrás del panel:
potencia 0 (recortar con `max(0, ·)`). `θ = acos(cos θ)`.

Observación física (clave del polo): como e ≤ ~1.6° (Sol) un panel horizontal tiene `cos θ = sin e ≤ 0.028`;
un vertical con seguimiento tiene `cos θ = cos e ≥ 0.9996`. Un vertical fijo apuntado a γ pierde `cos(A−γ)`:
con |A−γ| = 60° → 0.5.

### 6.4 IAM (incidencia rasante)

Modelo: transmisión de Fresnel de **una interfaz** vacío/vidrio (cubierta de la célula), n = 1.526 (valor
usual de vidrio de cubierta en modelos fotovoltaicos, De Soto et al. 2006; **`a verificar` para la cubierta
real**, véase `paneles-y-misiones.md`), luz no polarizada:

    sin θ_t = sin θ / n
    r_s = ((cos θ − n cos θ_t)/(cos θ + n cos θ_t))²,   r_p = ((n cos θ − cos θ_t)/(n cos θ + cos θ_t))²
    T(θ) = 1 − (r_s + r_p)/2
    IAM(θ) = T(θ)/T(0),    IAM(θ ≥ 90°) = 0         (T(0) = 0.956638)

Justificación: sin atmósfera, la pérdida angular dominante es la reflexión en la cubierta; no necesita
parámetros que no tenemos. Alternativa más simple (ASHRAE, `IAM = 1 − b₀(1/cos θ − 1)`, b₀ = 0.05, valor
habitual, `a verificar`) es peor cerca de 90° (se anula a θ > 87°). Los recubrimientos antirreflejo reales
suavizan la curva: el IAM a θ > 80° es **la parte más incierta** del modelo.

Valores [V] (Fresnel 1 interfaz): θ = 0°→1; 30°→0.9984; 50°→0.9811; 60°→0.9476; 70°→0.8616; 80°→0.6357;
85°→0.4019; 88°→0.1882; 88.5°→0.1451; 89.9°→0.0105.

### 6.5 Temperatura del panel y eficiencia

Balance estacionario (sin atmósfera, sin conducción al suelo, sin inercia térmica):

    G_inc = G · max(0, cos θ) · IAM(θ)
    (α_s − η_ref) · G_inc = (ε_f + ε_b) · σ · (T⁴ − T_amb⁴)
    T = [ (α_s − η_ref)·G_inc / ((ε_f + ε_b)·σ) + T_amb⁴ ]^{1/4}           σ = 5.670374419·10⁻⁸ W m⁻² K⁻⁴

Parámetros «ejemplo» (`a calibrar`/`a verificar` con `paneles-y-misiones.md`): α_s = 0.91, ε_f = 0.85,
ε_b = 0.80, η_ref = 0.30, **T_amb = 100 K** (suelo frío del polo; sumideros reales: sombras permanentes ≲ 110 K,
Paige et al. 2010 reportan mínimos ~38 K — `a verificar`; regolito iluminado en incidencia rasante `a verificar`).
Con estos valores: G = 1361, incidencia normal → T = 307.8 K (34.6 °C) [V]. El modelo probablemente **infravalora**
T respecto a paneles reales de unos 50–60 °C (orden de magnitud, `a verificar`) por ignorar la resistencia térmica
del panel; es un sesgo hacia eficiencia mayor (optimista), declararlo.

Eficiencia relativa:

    η_rel(T) = clip( 1 + γ_T·(T − 298.15 K) ,  η_min, η_max )         γ_T [1/K]

γ_T: silicio cristalino ≈ −0.0035 a −0.0045 /K (rango habitual, `a verificar`); triple unión (III-V)
≈ valor menor en módulo, **`a verificar`** (parámetro de entrada; ejemplo −0.0025 /K). Dominio de validez lineal:
`T ≥ T_min_valid = 173.15 K` (−100 °C, **`a calibrar`**; los datos de célula suelen acabar en −150 °C o
mucho antes) → clampear T antes de aplicar γ_T; además `η_max = 1.35` como tope de seguridad (`a calibrar`).
A T < 173 K el modelo no extrapola.

Degradación (BOL = 0) y polvo (0 por defecto): parámetros de entrada; sin valores por defecto físicos (`a verificar`).

### 6.6 Energía

    E_inc  [Wh/m²]    = ∫ G(t)·f(t)·max(0,cos θ)·IAM dt                 (irradiancia efectiva sobre el panel)
    E_rel  [adim.]    = (1/T) ∫ P_rel(t) dt                              (fracción de P_nominal·T)
    E_el   [Wh/m²]    = E_rel · T · η_ref · G₀                           (eléctrica por m² de panel; η_ref ejemplo 0.30)
    % del máximo teórico = 100·E_rel   (máximo = panel de 2 ejes, 1 UA, sol siempre visible, 25 °C)

«Diaria»: integrar por día UTC; «por periodo»: sumar. La integración debe usar **los instantes de evento
refinados** (§5) como nodos, o rejilla de 1 min: con rejilla de 10 min el error por escalón en cada ocaso es
hasta ½ Δ·P ≈ 5 min por transición; con ~10 transiciones al día supone **hasta ≈ 3 %** de error diario.

### 6.7 Casos de prueba numéricos [V]

(a) Geometría pura (T = 25 °C → η_rel = 1, d = 1 UA, f = 1, IAM Fresnel). e = 1.5°, A = 100° (cualquiera):
- Horizontal: cos θ = sin 1.5° = 0.026177; θ = 88.5°; IAM = 0.1451 → **P_rel = 0.003798**.
- Vertical con seguimiento azimutal: cos θ = cos 1.5° = 0.999657 ; IAM(1.5°) = 1.0000 → **P_rel = 0.99966**.
- Vertical fijo, |A − γ| = 60°: cos θ = cos 1.5°·cos 60° = 0.499829; θ = 60.0096°; IAM = 0.94758 → **P_rel = 0.47362**.
- Inclinado 45°, γ = A: cos θ = sin 45° cos 1.5° + cos 45° sin 1.5° = 0.72537.
- Dos ejes: **P_rel = 1.0000**.
- Sol detrás del vertical (A − γ = 180°): cos θ = −cos e → **P_rel = 0**.

(b) Cadena completa, 2026-12-01 00:00 UTC en (φ −89.9°, λ 129.78°E): e = 1.38330°, d = 147 553 142 km →
(UA/d)² = 1.027907, G = 1398.98 W/m². Parámetros §6.5 con γ_T = −0.0025/K, T_min_valid = 173.15 K:
- Vertical con seguimiento: T = 36.71 °C, η_rel = 0.97073 → **P_rel = 0.99753**.
- Dos ejes: **P_rel = 0.99776**.
- Horizontal: cos θ = 0.024141, IAM(88.617°) = 0.13468; T calculada ≪ 173 K → clamp 173.15 K, η_rel = 1.3125 →
  **P_rel = 0.004386** (0.44 %).
- Vertical fijo a 60° del Sol: T = −15.30 °C → **P_rel = 0.53593**.

(c) Energía sintética: f = 1 durante 10 h al día, e = 1.5° constante, vertical con seguimiento, 25 °C, 1 UA:
`E_inc = 1361·0.999657·10 = 13 605 Wh/m²` ; `E_rel = (10/24)·0.999657 = 0.41652` ; E_el con η_ref = 0.30 =
`0.41652·24·0.30·1361 = 4081 Wh/m²/día` ; 41.7 % del máximo teórico.

### 6.8 Integrador de batería (opcional)

Paso Δt (h), potencia de generación `P_gen = P_rel·P_nom` (W, `P_nom` del panel instalado), carga constante `P_L`
(W), capacidad `C` (Wh), rendimientos de carga/descarga η_c, η_d (ejemplo 0.95, `a calibrar`), límites
`SOC_min, SOC_max` (ejemplo 0.20 y 1.0, `a calibrar`). Estado `B` (Wh), B₀ = SOC₀·C:

    P_neta = P_gen − P_L
    si P_neta ≥ 0:  B ← min(SOC_max·C, B + P_neta·η_c·Δt)                    (el exceso se disipa)
    si P_neta < 0:  necesidad = (−P_neta)·Δt/η_d ; disponible = B − SOC_min·C
                    si necesidad ≤ disponible: B ← B − necesidad
                    si no: B ← SOC_min·C ;  E_no_servida += (necesidad − disponible)·η_d
    SOC = B/C  (reportar en %)

Caso de prueba [V]: P_nom = 100 W, P_rel = 0.8 durante 10 h seguido de 14 h a 0, P_L = 20 W, C = 100 Wh,
SOC₀ = 50 %, Δt = 1 h → SOC tras la hora 1 = 100 %; 10 h de carga: 100 %; descarga por hora 21.0526 Wh:
SOC = 78.9, 57.9, 36.8, 20.0 % (límite en la 4.ª hora) y 20 % el resto; **E_no_servida = 204.0 Wh**.
Con C = 300 Wh: SOC final 20 %, E_no_servida = 52.0 Wh.

---

## 7. Score de calidad del emplazamiento (funcionalidad nueva)

Principio de transparencia (documento base §4.4): sin ranking opaco. El score es **un resumen explicable**, siempre
acompañado de su desglose y de un rango. Todas las constantes son parámetros de configuración
(`config/score.yaml`).

### 7.1 Subindicadores y normalización a [0,1]

Entradas (de los motores): `f_sol` (visibilidad solar, 0–1; §5 o iluminación efectiva), `D_max` (oscuridad continua
máxima en horas), `f_E` (fracción de tiempo con Tierra visible, criterio §4.4), `σ_p` (pendiente local, percentil 90 en
un entorno de radio r_pie, grados).

| Subindicador | Función | Parámetros por defecto | Justificación |
|---|---|---|---|
| `s_sol` | rampa `clip((f_sol − f₀)/(f₁ − f₀), 0, 1)` | f₀ = 0.20, f₁ = 0.90 — **`a calibrar con experto`** | monótona, lineal y legible; por debajo de f₀ el sitio no sostiene operación solar; 0.90 como techo realista de sitios del polo (literatura de iluminación del polo `a verificar`) |
| `s_noche` | `2^(−D_max/D_½)` | D_½ = 48 h — **`a calibrar`** (idealmente = autonomía de la batería de referencia) | decae suave; cada D_½ la penalización se duplica; sin umbrales arbitrarios |
| `s_tierra` | `min(1, f_E / max(f_E,ref, f_E,min))` (mínimo útil, ver §7.8) | `f_E,ref` = fracción de tiempo con la Tierra sobre el horizonte esférico liso a esa latitud (calculado por el mismo motor con `H ≡ H_esfera`; en el polo sur 2026 ≈ 0.47 [V]) | normaliza lo que la libración permite en cualquier terreno; sin constantes inventadas |
| `s_terreno` | `1 − clip((σ_p − σ₀)/(σ₁ − σ₀), 0, 1)` | σ₀ = 5°, σ₁ = 15°, r_pie = 50 m — **`a calibrar con experto`** (requisito de pendiente de aterrizaje del lander concreto) | pendiente baja = 1; tolerancia depende del vehículo |

Observación de datos: las pendientes del `slp` de Site04 (5 m/px) son mediana 20.6°, p95 34.6°: con σ₁ = 15° casi
todo el DEM puntuaría 0 → la pendiente debe evaluarse a la **escala del vehículo** (promedio sobre r_pie, no el
píxel de 5 m, que además contiene interpolación; ver `ldec`).

### 7.2 Puertas duras (gates)

Un gate **no** da score 0: da estado «no apto» (o «sin datos suficientes») con motivo visible y el score se muestra
atenuado. Valores `a calibrar`:

- G1 Energía: `f_sol < 0.05` → «no apto (sin energía solar)» (solo perfiles con panel solar).
- G2 Terreno: `σ_p > 20°` en el punto de aterrizaje → «no apto (pendiente)».
- G3 Datos: fracción de azimutes con `desconocido_relevante` (§2.6) > 0.5, o observador fuera del DEM →
  «sin datos suficientes».

### 7.3 Agregación: media geométrica ponderada

    S = 100 · Π_i max(s_i, ε_s)^{w_i} ,   Σ w_i = 1,   ε_s = 0.01   (equivale a exp(Σ w_i·ln s_i))

Por qué geométrica y no aritmética:
- **No compensatoria**: un sitio sin energía no debería «compensarlo» con buenas comunicaciones. La media
  aritmética lo premia: ejemplo [V] sitio B (f_sol = 0.22, D_max = 200 h, f_E = 0.47, σ_p = 3°; s = 0.029, 0.056, 1, 1):
  perfil lander → **geométrica 11.7 vs aritmética 37.5**.
- Elasticidad constante: `∂ ln S/∂ ln s_i = w_i` (un 10 % menos en el indicador i resta `w_i·10 %`): es explicable.
- Mantiene escala 0–100 y es continua; ε_s evita `ln 0`.
- Contra: sensible a un subindicador muy bajo (es la intención) y menos intuitiva: mitigado mostrando la
  contribución de cada término y «qué pasaría si este indicador valiese 1».

### 7.4 Pesos por perfil (`a calibrar con experto`)

| Perfil | s_sol | s_noche | s_tierra | s_terreno |
|---|---|---|---|---|
| Lander solar (`lander_solar`) | 0.40 | 0.25 | 0.15 | 0.20 |
| Rover (`rover`) | 0.30 | 0.15 | 0.15 | 0.40 |
| Comunicaciones (`comunicaciones`) | 0.15 | 0.10 | 0.60 | 0.15 |

El usuario puede editar pesos (se renormalizan) y verá el efecto inmediato. Perfil «personalizado» = pesos libres.

### 7.5 Incertidumbre: rango, no cifra

Se calcula el score en varios **escenarios** y se reporta `S_nominal [S_min, S_max]`:

1. **Cobertura**: escenario pesimista con `H_ub` (§2.6) y optimista con `H_lb` (el nominal usa `H_lb`; el rango
   lo hace explícito).
2. **σz** (`toterr`): horizonte pesimista con `z + k·σ_z(r)` en el terreno y `z₀ − k·σ_z(z₀)` (k = 1) y optimista con
   el signo contrario. Cota de sensibilidad, no estadística: en Site04 σ_z mediana 0.36 m → ≈ 0.004° a 5 km,
   pequeño frente al error de interpolación.
3. **Clones DEM** (hasta 100 de PGDA, si están): K ≥ 10 realizaciones `S_k`; reportar percentiles 5–95.
4. **Discretización** (tiempo/azimut): rango por ΔA = 0.25°→0.5° (efecto de interpolación §2.5).

`S_min`, `S_max` = extremos de los escenarios (si hay clones: P5/P95 de los clones, fusionados con extremos 1–2).
**Confianza de datos** (etiqueta, no entra en el producto de S): `C = min(c_cov, c_sup, c_rango)` con
`c_cov = 1 − fracción desconocido_relevante`, `c_sup` = fracción de píxeles con `ldec ≥ 1` en radio 2 km (Site04
global: 9.2 % [V], por tanto «soporte observacional bajo» en todo Site04; umbrales **`a calibrar`**),
`c_rango = 1 − clip((S_max − S_min)/25, 0, 1)`. Etiqueta: «alta» C ≥ 0.75, «media» 0.5–0.75, «baja» < 0.5
(`a calibrar`).

### 7.6 Desglose que se muestra al usuario

Por perfil: tabla `indicador | valor medido | s_i | peso | contribución a la penalización (%) | S si s_i = 1`;
`S_nominal` con rango y etiqueta de confianza; «eslabón más débil» (el i de mayor `w_i·(−ln s_i)`); gates
activos con motivo; lista de supuestos (visibilidad geométrica ≠ potencia ≠ enlace RF, §0 del documento base) y
`horizonte limitado por cobertura` si procede.

### 7.7 Ejemplo numérico completo a mano [V]

Sitio A (hipotético): `f_sol = 0.78`, `D_max = 60 h`, `f_E = 0.40` (`f_E,ref = 0.47`), `σ_p = 8°`.

- `s_sol = (0.78 − 0.20)/(0.90 − 0.20) = 0.82857`
- `s_noche = 2^(−60/48) = 2^(−1.25) = 0.42045`
- `s_tierra = 0.40/0.47 = 0.85106`
- `s_terreno = 1 − (8 − 5)/(15 − 5) = 0.70000`

Perfil `lander_solar` (con λ = 0, la agregación de §7.3; con λ = 0.25 de §7.8 el mismo sitio da **66.1**, porque la parte alta usa `f_sol` = 0.78 sin saturar y `1 − σ_p/σ₁` = 0.467): `Σ w ln s = 0.40·ln 0.82857 + 0.25·ln 0.42045 + 0.15·ln 0.85106 + 0.20·ln 0.7 =
−0.07522 − 0.21661 − 0.02419 − 0.07133 = −0.38735` → `S = 100·e^{−0.38735} = 67.9`.
Aritmética equivalente: 70.4 (la geométrica penaliza la noche larga). Otros perfiles: rover 70.2, comunicaciones 76.7.
Eslabón débil: `s_noche` (55.9 % de la penalización). Si `s_noche = 1` → 84.3; si `s_sol = 1` → 73.2;
`s_tierra = 1` → 69.5; `s_terreno = 1` → 72.9.
Rango: pesimista (`f_sol 0.74, D 72 h, f_E 0.38, σ_p 9°`) = 60.8; optimista (`0.81, 50 h, 0.42, 7°`) = 74.3 →
se muestra **«68 (61–74)»**.

Pruebas automáticas: (i) con `s_i ≡ 1` → 100; (ii) con un `s_i = 0` → `100·ε_s^{w_i}` (p. ej. w=0.4 → 15.8·∏resto);
(iii) pesos iguales y s_i iguales → S = 100·s; (iv) invariancia a reordenar indicadores; (v) ejemplo de arriba (tolerancia 0.05).

### 7.8 Ronda de adaptación: mínimo útil de Tierra, mezcla λ y semántica de ventana y de estados

Implementación única en `site_score` (`subscores`, `_quality`, `blend`, `decide_verdict`); el mapa de idoneidad
(`suitability_map.window_scores`) la replica vectorizada y `tests/test_mission_windows.py` comprueba la igualdad
numérica contra `compute_score` (240 combinaciones con semilla fija, con λ, `earth_floor` y G4 de perfil variados).

**a) `s_tierra` con mínimo útil.** `s_tierra = min(1, f_E / max(f_E,ref, f_E,min))`, con `f_E,min` = `earth_floor`.
Problema que corrige: con `f_E = f_E,ref = 0.08` la fórmula antigua daba 1 (la esfera lisa tampoco ve la Tierra), es
decir, una Tierra visible el 8 % del tiempo puntuaba «perfecta». Con `f_E,min` = 0.25 da 0.32. Si `f_E,ref ≥ f_E,min`
(lo habitual: ≈ 0.47–0.5 en el polo) nada cambia. `f_E,min` = 0.25 por defecto y 0.5 en `dte_comms` — **a calibrar**
(convención: fracción de la ventana con Tierra que se considera comunicación plena; no sale de un requisito de enlace).

**b) Resolución en la parte alta (mezcla λ).** Con `s_sol` saturando en f₁ = 0.90 y `s_noche`≈1 sin noche, decenas de
sitios empataban en 100 en ventanas cortas. Se mezcla la media geométrica saturada `A` con otra de indicadores
**sin saturar** `Q` (`f_sol` bruta, `s_noche`, `s_tierra`, `1 − σ_p/σ₁` recortado a [0,1]):

    S = 100 · A^(1−λ) · Q^λ ,   A = Π max(s_i, ε_s)^{w_i} ,   Q = Π max(q_i, ε_s)^{w_i}

(forma de `blend`; con λ = 0 es §7.3). `A` conserva el significado de umbral (por encima de f₁ no hay «mejora» de
mérito), `Q` rompe empates (más Sol, menos pendiente siguen sumando). Sigue siendo no compensatoria, y la
elasticidad respecto a `s_i` pasa a ser `w_i·(1−λ)` más la de `q_i`. λ = `resolution_weight` = 0.25 — **a calibrar**
(convención: lo bastante pequeño para no desordenar el ranking de §7.3, lo bastante grande para separar el 100).
Resultado en los mapas de ventana (Site04/11/23, 7/14/30 d, lander y rover): ningún punto en 100 y TOP-1 entre 77 y 99.3.

**c) Ventana de misión.** El score, las puertas y `D_max` se evalúan sobre `[inicio, inicio + mission_days]`
(`mission_days` por perfil: 14 lander, 30 con baterías, 90 lander RHU, 100 rover, 365 base y DTE — **a calibrar**),
no sobre todo el periodo; se prueban fechas de inicio cada `start_step_h` = 24 h y se conservan las `top_n_windows` = 3
mejores. Una noche que cruza el borde cuenta solo lo de dentro. La fecha de inicio exige Sol (G0) en perfiles solares.
Con el periodo simulado más corto que la misión no hay ventana completa: estado SIN DATOS.

**d) Estado (verdict) por puertas y escenarios, no por la nota.** No existe umbral de score; el score solo ordena.
`NO APTO` = falla una puerta dura en el nominal (sobre esfera lisa: provisional, «cota optimista», porque el relieve
rara vez arregla lo que ya falla en la esfera); `SIN DATOS` = nada falla pero falta un dato (terreno, observador,
periodo < misión; nunca APTO con datos incompletos); `CONDICIONAL` = puerta blanda fallida (p. ej. G4 del rover, 50 h),
algún escenario de incertidumbre que falla, o menos de `min_feasible_start_fraction` = 10 % de fechas de inicio
factibles (**a calibrar**; ventana frágil); `APTO` = resto. G4 es por perfil: el rover tiene límite propio blando, el
lander RHU la anula (`g4.na`) y el resto hereda el del perfil de misión (`panels.json`).

---

## 8. Tolerancias de prueba recomendadas y validación contra JPL Horizons

### 8.1 Tolerancias por motor

| Motor / prueba | Tolerancia | Nota |
|---|---|---|
| Proyección directa vs fórmula/pyproj | ≤ 1·10⁻⁶ m | medido 4·10⁻¹⁰ |
| Ida y vuelta lat/lon | ≤ 1·10⁻⁹ ° (≈ 1e-4 m) | medido 1.4·10⁻¹⁴ ° |
| Índice de píxel ↔ x,y | exacto (enteros); bilineal en centro de píxel = valor del píxel a 1e-6 m | |
| Horizonte vs analítico (H1–H5) | ≤ 1·10⁻⁴ ° | la exacta coincide a 1e-9 |
| Horizonte DEM real, mismo método con ΔA = 0.125° vs 0.25° | ≤ 0.06° (documentar) | medido 0.053° |
| Horizonte plano vs curvo | **diferencia esperada**, no tolerancia: ≈ s/(2R) | test de regresión del orden de magnitud |
| ENU / ortonormalidad | ≤ 1·10⁻¹² | |
| (az, el) Sol vs Horizons (misma frecuencia, mismo observador) | ≤ **0.01°** objetivo; ≤ 0.02° aceptable | `a verificar` tras la primera comparación (DE421 vs DE441 de Horizons: dif. de libración, `a verificar`) |
| (az, el) Tierra vs Horizons | ≤ **0.02°** objetivo; ≤ 0.05° aceptable | la Tierra está a 0.26° de paralaje: error de paralaje = fallo seguro |
| Distancias Sol/Tierra vs Horizons | ≤ 1·10⁻⁵ relativa | |
| Fracción visible: plano vs analítico (n = 64) | ≤ 1·10⁻⁴ | medido 8.5·10⁻⁶ |
| Fracción visible: pared, inclinado por el centro | exacto 0.5 ± 1·10⁻⁶ | |
| Tiempos de evento (raíz) vs analítico | ≤ 1 s | xtol = 1 s |
| Ventanas: Δ = 5 min vs Δ = 10 min | mismo conjunto, ±2 s | |
| Duración de ventana vs fuerza bruta a 1 min | ≤ 2 min | |
| Integración de energía: eventos refinados vs rejilla 1 min | ≤ 0.5 % | |
| Potencia: casos §6.7 | ≤ 1·10⁻⁴ absoluto en P_rel | |
| Batería: caso §6.8 | ≤ 0.1 Wh | |
| Score: ejemplo §7.7 | ≤ 0.05 puntos | |

### 8.2 Procedimiento de validación con JPL Horizons

(No ejecutado en esta tarea: sin acceso de red desde el entorno de cálculo; todo lo de abajo está `a verificar`
en su primera ejecución.)

1. API `https://ssd.jpl.nasa.gov/api/horizons.api`, `EPHEM_TYPE='OBSERVER'`, `CENTER='coord@301'`,
   `COORD_TYPE='GEODETIC'`, `SITE_COORD='<lon_E>,<lat>,<alt_km>'` (longitud este, latitud, altitud en km;
   para la Luna el marco de las coordenadas del sitio — ME o PA — debe comprobarse en la documentación de Horizons:
   **riesgo de marco**), `COMMAND='10'` (Sol) y `'399'` (Tierra), `QUANTITIES='4,20'` (az/el aparente, distancia
   y variación), `APPARENT='AIRLESS'` (sin refracción), `ANG_FORMAT='DEG'`, `START_TIME/STOP_TIME/STEP_SIZE`,
   `TIME_TYPE='UT'`.
2. Muestra mínima: 3 sitios × 2 cuerpos × ≥ 12 instantes repartidos a lo largo de un año y en puntos de libración
   extrema (Tierra: ±6.8° de latitud sub-Tierra), incluyendo una hora con Sol a < 1° del horizonte.
3. Comparar az/el y rango con nuestros valores (aparente = `LT+S`); informar el máximo y la media del error en °.
4. Si el error de azimut supera la tolerancia pero el de elevación no, sospechar de **signo de λ** o de eje
   (§1.2); si falla la Tierra y no el Sol, sospechar de **paralaje** (§3.1 paso 4).
5. Incluir los valores de §3.3 como primera fila de la tabla de validación.
6. Guardar la tabla de comparación en `docs/science/validacion-horizons.md` (fuera del alcance de este fichero).

---

## 9. Dudas abiertas

1. **Marco de las coordenadas de sitio en Horizons** (ME vs PA) y diferencia DE421/DE441: `a verificar`.
2. **Valores de célula** (α_s, ε, γ_T, η_ref, n de cubierta, degradación, polvo): dependen de
   `paneles-y-misiones.md`; los de §6.5/6.4 son ejemplos.
3. **Umbrales del score** (f₀, f₁, D_½, σ₀, σ₁, gates, pesos): requieren experto de misión; la estructura y los
   tests no cambian.
4. **Eclipses lunares** no están en «oscuridad»; hay que mencionarlo en la UI o modelarlos.
5. **Albedo/luz difusa del regolito** y sombra propia del lander no modelados.
6. El DEM de Site04 corta el suelo de Shackleton y tiene el polo en el borde norte; para sitios cerca de
   λ ≈ 0° a ρ ≈ 3 km no hay cobertura: decidir si se descargan más teselas.
7. Coordenadas IAU del centro de Shackleton y de los sitios Site11/Site23 (Site23 sigue como `.part`).
