# Metodología

Este documento resume cómo calcula LSI cada resultado. La especificación completa, con casos de prueba numéricos, está en `docs/science/matematica.md`; las convenciones fijas en `docs/science/convenciones.md`; los parámetros en `config/simulation.json`, `config/panels.json` y `config/ground_stations.json` (estaciones terrestres). Donde una cifra es convención de LSI y no dato publicado, se dice. Lo no verificado lleva «a verificar» o «a calibrar».

## 0. Convenciones

| Magnitud | Convención |
|---|---|
| Azimut | Desde el Norte local hacia el Este, sentido horario visto desde arriba, 0°–360°: `az = atan2(E, N) mod 360`. |
| Elevación | 0° = horizonte local plano de la esfera, +90° = cenit: `el = asin(U/|v|)`. Sin refracción (no hay atmósfera). |
| Ejes locales (ENU) en MOON_ME | E = (−sin λ, cos λ, 0); N = (−sin φ cos λ, −sin φ sin λ, cos φ); U = (cos φ cos λ, cos φ sin λ, sin φ). |
| Longitud | Este-positiva. Latitud: sur negativa; esfera, así que planetocéntrica = geodésica. |
| Esfera de referencia | R = 1737,4 km (la del DEM LOLA y la de Horizons). |
| Marco | `MOON_ME` (media Tierra / eje polar, DE421), ID 31001. No `MOON_PA` ni `IAU_MOON`: usar `MOON_PA` desplaza todo ~0,87 km (103,85″). |
| Tiempo | UTC en la interfaz; ET (TDB) interno en SPICE. Rango válido 1900-2050 (cobertura del kernel de orientación lunar). |
| Ángulos y longitudes | Grados en API y UI; metros en el DEM; kilómetros en SPICE. |

## 1. Transformación de coordenadas

### 1.1 Proyección estereográfica polar sur (DEM)

Los DEM de PGDA están en proyección estereográfica polar sur sobre la esfera de R = 1 737 400 m, tangente en el polo, con píxel centrado. Directa e inversa (φ en grados, resultado en metros):

```
ρ = 2·R·cos φ / (1 − sin φ)          x = ρ·sin λ     y = ρ·cos λ
ρ = hypot(x, y)     φ = −90° + 2·atan(ρ / 2R)     λ = atan2(x, y) mod 360°
```

`+y` apunta a λ = 0° y `+x` a λ = 90°E. Un rayo de azimut A parte en el plano con dirección `(sin(λ+A), cos(λ+A))`. Dentro del DEM (ρ ≤ 17,5 km) el factor de escala difiere de 1 en ≤ 2,5·10⁻⁵, así que se miden distancias en el plano. Comprobado contra `pyproj` con el CRS del GeoTIFF: diferencia < 1 mm (`docs/validation/revision-matematica.md` §4).

### 1.2 Posición de Sol y Tierra: SPICE, MOON_ME y LT+S

1. UTC → ET con `naif0012.tls`.
2. Posición del cuerpo respecto al observador con `spkcpo`/`spkpos` en el marco `MOON_ME`, corrección `LT+S` (tiempo luz más aberración estelar). El observador está fijo en la superficie: `georec(lon, lat, 0, R)`; el relieve se añade aparte como altura, para no contarlo dos veces.
3. El vector observador→cuerpo incluye el paralaje (para la Tierra, R/d ≈ 0,259°).
4. Se proyecta en la base ENU: `az`, `el` y distancia.

`LT+S` coincide con la posición «aparente» de Horizons (diferencia ≤ 0,05″); sin la aberración estelar el Sol se desplaza ~20,3″ (0,0056°). El tamaño angular es `ρ = asin(R_cuerpo/d)` con R☉ = 695 700 km y radio ecuatorial terrestre 6378,137 km (`convenciones.md`). El conjunto mínimo de kernels, probado quitando cada uno, está en `kernels/README.md`.

## 2. Horizonte con curvatura y campo lejano

Para cada azimut se lanzan rayos sobre el DEM (por defecto cada 0,25° de azimut y 5 m radiales, hasta 30 km; `config/simulation.json`, bloque `horizon`). Con el observador a radio `R + z0` (`z0` = altura del DEM + altura del observador, 2 m por defecto) y una muestra a distancia `s` con altura `z` sobre la esfera, el ángulo central es `ψ = s/R` y

```
el(s) = atan2( (R+z)·cos ψ − (R+z0) ,  (R+z)·sin ψ )        H(az) = max_s el(s)
```

Equivale a `atan2(z − z0, s) − s/(2R)`. El horizonte plano del documento base sobrestima la elevación en `s/(2R)`: 0,13° a 8 km, 0,26° a 16 km, 0,49° a 30 km, frente a un disco solar de 0,53° (`matematica.md` §2). Para una esfera lisa el horizonte es `−acos(R/(R+h))` (−0,087° con h = 2 m).

**Campo lejano.** El DEM de 5 m cubre unos 16×16 km (21×21 km en Malapert). Más allá, cada muestra usa el DEM polar LOLA de 80 m (±304 km); si tampoco hay dato, el azimut se marca *limitado* y se devuelve una cota inferior `H_lb` y una superior `H_ub`. El campo lejano es una estimación: el 80 m difiere del 5 m (media −0,15 m, RMS 1,2 m en el solape de Site04; `docs/plan/arquitectura.md`, addendum).

**Precisión medida.** Frente a un rayo 3D independiente, el horizonte tiene RMS 0,007°–0,023° y máximo 0,13°; el motor queda por debajo (optimista) por la discretización radial de 5 m (`revision-matematica.md` §3). La estereográfica frente a la geodésica añade ≤ 0,002° a 30 km.

## 3. Disco finito del Sol y la Tierra

Un astro no es un punto: con el centro a menos de su radio angular del horizonte se ve solo parte del disco. Con horizonte plano y `t = (e − H)/ρ`, la fracción de área visible es

```
f(t) = 1/2 + ( t·sqrt(1−t²) + asin t ) / π     (|t| ≤ 1);   f = 0 si t ≤ −1;   f = 1 si t ≥ 1
```

Con horizonte variable sobre el disco se integra en 64 franjas: `f = (1/(π ρ²)) ∫ clip(e + c(x) − H(A + x/cos e), 0, 2c(x)) dx`, con `c(x) = sqrt(ρ² − x²)` (válido para elevaciones pequeñas, e ≲ 8° en el polo). Clasificación con ε = 10⁻³: *oculto* (f ≤ ε), *parcial*, *visible* (f ≥ 1 − ε).

Criterio de ventana: **Sol** visible si `f > 0,001` (basta una rendija); **Tierra** si `f ≥ 0,5` (el valor 0,5 es convención de LSI, a calibrar con un experto en comunicaciones). «Tierra visible» es solo geometría; la capacidad de comunicar se llama **enlace posible** y se define en el §9. Por eso `f_sol` es «tiempo con alguna parte del Sol», mayor que la «iluminación media» de la literatura (media de `f`, que LSI también calcula como `effective_illumination`). El oscurecimiento de limbo está desactivado por defecto.

## 4. Ventanas temporales con refinamiento

1. Rejilla de 600 s con efemérides vectorizadas.
2. En cada instante, `(az, el, ρ)` y `f` por §3; estado = `f > umbral`.
3. Cada transición se refina por bisección vectorizada hasta 1 s.
4. Ventana = intervalo maximal con estado verdadero; oscuridad = complemento. Los eventos más cortos que el paso solo existirían con huecos del horizonte más estrechos que lo que el Sol recorre en 10 min (0,085°), por debajo del muestreo azimutal de 0,25°.

Métricas: fracción de tiempo, ventana más larga y oscuridad máxima, solape Sol∩Tierra. Las ventanas que tocan el borde del periodo se marcan *truncadas* y su duración es una cota inferior («≥ X»). «Oscuridad» significa «sin Sol por el relieve»: **no incluye eclipses** (la Tierra tapando al Sol). Frente a una rejilla de 5 s, el refinamiento difiere ≤ 3 s (`revision-matematica.md` §3).

## 5. Modelo de potencia

Estimación **relativa** a la potencia nominal del propio panel. Los 8 paneles del catálogo son calculables y se dividen en dos grupos (`evidence_group` en `config/panels.json`; registro parámetro a parámetro, con página de cada fuente, en `docs/validation/datos-paneles.md`):

| Grupo | Paneles | Qué significa |
|---|---|---|
| **Respaldado** (5) | GaAs 3J lander, GaAs 3J mástil, GaAs 3J rover, 4J de alta eficiencia, ROSA flexible | η y γ_T proceden de datasheet o paper, o se derivan de ellos con fórmula. En mástil, rover y ROSA, «respaldado» se refiere a la **celda de referencia** modelada (3J, 29,5 %): ni VSAT, ni los rovers ni la manta ROSA publican su eficiencia de conjunto. |
| **Experimental sin datasheet** (3) | silicio legado, CIGS flexible, perovskita-silicio | Falta η o γ_T en fuente primaria espacial. Llevan `uses_estimates`, se etiquetan «estimación sin datasheet / EXPERIMENTAL», llevan banda de incertidumbre (rangos mín/máx del catálogo) y no se mezclan con los respaldados en los rankings por defecto. |

La potencia relativa es:

```
P_rel(t) = f(t) · max(0, cos θ) · IAM(θ) · η_rel(T) · (UA/d)² · (1 − degradación) · (1 − polvo)
```

- `cos θ = ŝ · n̂_panel`, con `ŝ = (cos e sin A, cos e cos A, sin e)`. Horizontal: `sin e`. Inclinado (β, γ): `sin β cos e cos(A−γ) + cos β sin e`. Vertical fijo: `cos e cos(A−γ)`. Vertical con seguimiento azimutal: `cos e`.
- `IAM`: transmisión de Fresnel de una interfaz vacío/vidrio con índice de cubierta 1,526 por defecto (el valor del panel prevalece), normalizada a incidencia normal. A incidencia rasante (> 80°) es la parte más incierta.
- `η_rel(T) = clip(1 + γ_T (T − T_ref), …)`, con `T` de un balance radiativo estacionario (T_amb = 100 K, a verificar), tope de ganancia en frío por panel (1,15 en el catálogo; 1,35 de reserva) y sin extrapolar por debajo de 173,15 K.
- `G0 = 1361 W/m²`; el factor `(UA/d)²` usa la distancia de SPICE (≈ 0,96–1,04 en 2026).
- Energía: integral trapezoidal sobre la rejilla y los instantes de evento. `% del máximo teórico = 100·E_rel` (máximo = panel de dos ejes, 1 UA, siempre iluminado, 25 °C). Puede superar 100 % en el perihelio y por frío: no se recorta.
- **Potencia por área.** Con la potencia nominal por m² del panel, `P [W/m²] = P_rel × areal_power_w_m2_am0`, donde `areal_power_w_m2_am0 = η_BOL × 1361 W/m²` (`config/panels.json`, cada valor con fórmula y nota). Valores: GaAs 3J 401,5 W/m² (η 29,5 %, celda de datasheet Azur), 4J 426,0 (31,3 %, Z4J+), ROSA 401,5 (cota superior: hereda la celda 3J), silicio 236,8 (17,4 %), CIGS 213,7 (15,7 %, nota de prensa), perovskita-silicio 261,3 (19,2 %, laboratorio). Es potencia **de celda/CIC**, sin empaquetado, cableado ni estructura. La energía diaria es `Wh/m² = e_rel_día × 24 h × areal_power_w_m2_am0`. Es lo que muestra la pantalla «Capacidad del sitio»; no se dan vatios sin área.

**Montaje por defecto.** La interfaz propone vertical con seguimiento azimutal en el polo (|lat| > 70°) y horizontal en latitudes bajas (`ui/state.py`).

Por qué importa el montaje: en el polo el Sol queda a pocos grados del horizonte, así que un panel horizontal recibe `sin e` (≈ 2–5 % a 1–3°) y uno vertical orientado `cos e` (≈ 1). La orientación cambia la potencia en un orden de magnitud; la tecnología de célula, ~8 % (`paneles-y-misiones.md` §3.1). No se modelan polvo (parámetro de sensibilidad), albedo, sombra propia ni eclipses.

## 6. Score por ventana de misión

El score **ordena y explica**; el veredicto lo deciden las puertas y los escenarios, no la nota (`docs/validation/revision-espacial.md` §4).

**Ventana.** Se evalúa en `[inicio, inicio + mission_days]`, con fechas de inicio cada 24 h. La **mejor fecha** respeta G7: entre las fechas que superan las puertas duras se prefieren las que cumplen G7 y, entre ellas, la de mayor score; si ninguna cumple G7, la de menor hueco (a igual hueco, mayor score). Antes desempataba por la fecha más temprana aunque otra con el mismo score tuviera enlace continuo (defecto B1 de `docs/validation/revision-enlace.md`, corregido). Días de misión por perfil (`config/simulation.json`): lander solar sin RHU 14, lander con baterías 30, lander RHU 90, rover 100, base/ISRU 365, comunicaciones 365. Son convención o suposición de LSI (con apoyo en misiones reales para 14 y 100 d, ver el informe citado). Una noche que cruza el borde de la ventana cuenta solo lo de dentro.

**Subindicadores** en [0,1] (valores por defecto, todos **a calibrar**):

| Indicador | Función |
|---|---|
| `s_sol` | rampa `clip((f_sol − 0,20)/(0,90 − 0,20), 0, 1)` |
| `s_noche` | `2^(−D_max/48 h)` con `D_max` la oscuridad continua máxima en la ventana |
| `s_tierra` (`s_earth`) | Sin red: `min(1, f_E / max(f_E,ref, f_E,min))`; `f_E,ref` = fracción de Tierra sobre el horizonte de esfera lisa; `f_E,min` = 0,25 (0,5 en comunicaciones). Con red y ventana de misión (el caso por defecto), `f_E` es la fracción de **enlace** y se multiplica por dos factores de continuidad **absolutos** (§9.5) |
| `s_terreno` | `1 − clip((σ_p − 5°)/(15° − 5°), 0, 1)`, con `σ_p` el percentil 90 de pendiente en un disco de 50 m |

**Puertas** (G0 llegada con Sol visible; G1 `f_sol ≥ 0,05`; G2 pendiente ≤ valor de diseño del perfil, 20° si no hay; G3 datos suficientes; G4 oscuridad máxima ≤ límite del perfil: 12 h lander sin RHU, 50 h blanda en rover, no aplica con RHU; G5 potencia útil: con panel elegido, la fracción de la ventana con `P_rel` ≥ la potencia mínima útil debe ser ≥ 0,5 (blanda; 0,75 y dura en base/ISRU; suposición de LSI, `config/simulation.json`); G6 ventana continua mínima de Tierra, o de enlace si hay red: 2 h, 8 h en base/ISRU; G7 hueco máximo sin enlace tolerado por el perfil, blanda, solo con red y ventana de misión: 48 h lander sin RHU y con baterías, 96 h con RHU, 24 h rover y comunicaciones, 12 h base; todos [sup], sin fuente publicada). Una puerta **dura** que falla rechaza la fecha; una **blanda** rebaja el veredicto. Una puerta no pone la nota a cero.

**Ligado al panel.** Con panel y montaje elegidos, `s_sol` usa la energía efectiva `(1−w)·P_rel medio + w·duty útil` sobre la ventana (el resultado lo rotula `energy_basis = "panel"`); sin panel usa la fracción de Sol geométrica y lo dice. Por eso el mismo punto y fecha puntúa distinto con montaje vertical con seguimiento que horizontal.

**Agregación: media geométrica ponderada, no compensatoria.**

```
A = Π max(s_i, 0,01)^{w_i}      Q = Π max(q_i, 0,01)^{w_i}      S = 100 · A^(1−λ) · Q^λ,   λ = 0,25
```

`A` conserva el significado de umbral; `Q` usa indicadores sin saturar (`f_sol` bruta, `s_noche`, `s_tierra`, `1 − σ_p/15°`) para romper empates en 100. Pesos por defecto del lander solar: Sol 0,40, noche 0,25, Tierra 0,15, terreno 0,20 (rover 0,30/0,15/0,15/0,40; comunicaciones 0,15/0,10/0,60/0,15). Editables en la app; se renormalizan. λ, pesos y umbrales son convenciones sin calibrar con un experto de misión.

**Estados.**

| Estado | Significado |
|---|---|
| **APTO** | La mejor fecha supera todas las puertas duras en el nominal y en todos los escenarios de incertidumbre, sin puertas blandas fallidas, y la fracción de fechas de inicio factibles es ≥ 10 %. |
| **CONDICIONAL** | Existe una fecha válida, pero pasa solo en el nominal, falla una puerta blanda, o menos del 10 % de las fechas de inicio son factibles (ventana frágil). |
| **NO APTO** | Ninguna fecha supera las puertas duras. Sin terreno (esfera lisa) es «provisional»: cota optimista. |
| **SIN DATOS** | Falta un dato imprescindible (sin terreno, observador fuera del DEM, periodo más corto que la misión). Nunca APTO con datos incompletos. |

Consecuencia que conviene saber: el estado depende del periodo que se analice. Con un periodo igual a la misión solo hay una fecha de inicio; con un periodo más largo se prueban varias y la fracción factible puede bajar de 10 %.

**Incertidumbre.** El score se recalcula en escenarios (horizonte pesimista con `H_ub`, error vertical ±1·`toterr`, discretización de azimut 0,25° → 0,5°) y se muestra `S [S_min – S_max]`. Es una cota de sensibilidad, no un intervalo estadístico. Si no se pidió el análisis (`with_uncertainty=False`) el rango se marca **«no calculado»** (`range_computed = False`) en lugar de mostrar `[S, S]` como resultado; en puntos saturados un rango calculado puede tener ancho cero. Los escenarios con clones del DEM no están activos (`clones_enabled: false`).

## 7. Confianza calibrada de los datos

Sobre un disco de 100 m alrededor del punto:

```
g90 = percentil 90 de la distancia (m) al retorno LOLA más cercano        e90 = percentil 90 de toterr (m)
σh90 = percentil 90 sobre azimutes de |H(z+toterr) − H(z−toterr)|/2 (°)
c_gap = clip((40 − g90)/30, 0, 1)   c_err = clip((1,5 − e90)/1,1, 0, 1)   c_hz = clip((0,5 − σh90)/0,4, 0, 1)
c_sup = min(c_gap, c_err, c_hz)      C = min(c_cov, c_sup, c_rango)
```

`c_cov = 1 − fracción de azimutes con horizonte desconocido relevante`; `c_rango = 1 − clip((S_max − S_min)/25, 0, 1)`. Etiqueta: **alta** C ≥ 0,75, **media** ≥ 0,5, **baja** < 0,5. Equivalencias físicas: alta ⇔ g90 ≤ 17,5 m, e90 ≤ 0,675 m, σh90 ≤ 0,20°. Se calibró porque la métrica anterior (fracción de píxeles observados) daba «baja» siempre: ~91 % de los píxeles son interpolados de forma uniforme (`docs/validation/revision-geologica.md` §1-2). Sobre 1200 puntos de los tres DEM resulta 45 % alta, 47 % media, 8 % baja. **«Alta» no significa resolución de 5 m**: significa huecos ≲ 17 m y resolución efectiva ≈ 30 m (heurística de LSI, a verificar).

## 8. Mapa de idoneidad (modelo grueso)

La pantalla «Mejores puntos y fechas» usa un cálculo precalculado y más grueso que el análisis detallado: malla de 250 m, horizonte cada 1° de azimut y 10 m radiales, serie cada 30 min sin refinar, solo puntos con pendiente p90 ≤ límite del perfil (10° para el lander). Su diferencia con el modelo fino se mide con `--validate` (ver README, Validación). «Evaluar este punto y fecha» abre el modelo fino en el punto y la fecha elegidos. El mapa también usa el **enlace** y no la Tierra geométrica (red DSN, recepción 6°, margen 0°, `--link-network`, `--link-direction`, `--min-earth-elevation`, `--station-min-elevation` en `scripts/precompute_suitability.py`): su `s_earth` lleva la continuidad absoluta del §9.5 y la mejor fecha de cada punto respeta G7 (cada punto guarda `max_link_gap_h` y `g7_ok`). Cambiar la red, el sentido o el margen exige regenerar el mapa.

## 9. Enlace con la Tierra (conectividad)

«Tierra visible» (§3) no es capacidad de comunicar. LSI separa dos magnitudes: **Tierra visible** (geometría: la Tierra sobre el horizonte del lander) y **enlace posible**. La conectividad es una condición geométrica y de cobertura; no es un presupuesto de enlace RF (§9.6). La pantalla «Capacidad del sitio» las muestra una al lado de otra. Detalle y tests: `docs/science/luna-spice-sitios.md` §7 y `docs/validation/revision-enlace.md`.

### 9.1 Definición de «enlace posible»

```
enlace(t) = [ la Tierra se ve desde el lander con margen m sobre su horizonte H(A) + m ]
            ∧ [ al menos una estación de la red ve la Luna por encima de su elevación mínima ]
```

- **Margen de antena `m`** (`min_earth_elevation_deg`, por perfil): 0° por defecto. Sube el horizonte a `H(A) + m` y se aplica de forma exacta en `link_fraction`. La app calcula la sensibilidad a 0°, 3° y 5° (`config/simulation.json`, `score.link.sensitivity_min_earth_elevation_deg`). Los márgenes de 3° y 5° son suposición.
- **Cobertura de red.** La Luna vista desde cada estación (centro de la Luna, posición aparente `LT+S`, sin refracción) menos la posición de la estación (punto geodésico WGS 84), proyectada sobre su vertical geodésica. Se calcula una sola vez por rejilla temporal, común a todos los sitios lunares: un punto de la superficie cambia la elevación vista desde la estación como mucho ~0,28° y la cobertura por estación ≤ 0,07 puntos porcentuales.
- El enlace y sus ventanas (con traspasos entre estaciones) salen de la unión de las ventanas de cada estación, fusionando huecos ≤ 20 s (`handoff_merge_tol_s`, [cal]: son artefactos de la interpolación lineal sobre la rejilla de 600 s; el hueco real más corto medido dura 44 s).
- Las ventanas y huecos que tocan el borde del periodo se marcan **truncados** (cota inferior, «≥ X»).
- `AnalysisRequest.link_network = None` (en la app, red «Solo geometría») recupera el comportamiento geométrico anterior.

### 9.2 Estaciones y elevaciones mínimas (`config/ground_stations.json`)

| Red | Estaciones | Posición | Elevación mínima | Estado |
|---|---|---|---|---|
| **DSN** (por defecto) | DSS-14 Goldstone, DSS-63 Madrid, DSS-43 Canberra (70 m) | WGS 84, DSN 810-005 módulo 301 Rev. P (22/05/2026), Tabla 5; coincide con la Tabla 6 y con las coordenadas ITRF93 de NAIF a < 1 m | Recepción **6,0°** [pub] (301 Rev. P §2.2.2 y §2.2.4); transmisión **10,1°** [pub] (§2.2.1: no se permite transmitir por debajo de 10,1° de elevación); ambas verificadas el 14/11/2026 | `verified = true`, activas por defecto |
| **ESTRACK** | New Norcia, Cebreros, Malargüe (35 m) | WGS 84, kernel NAIF `ndosl_190716_v02.tf` | **6° SUPUESTA [sup]**: no se encontró fuente oficial de ESA; se iguala a la del DSN | `verified = false`, no es red por defecto; la interfaz avisa «Elevación mínima supuesta, no publicada» |
| **NSN** (Near Space Network, NASA) | — | — | — | **No incluida**: NASA anuncia LEGS-1 (White Sands), pero no se pudo verificar en fuente oficial ni su ubicación, ni su elevación, ni su fecha de operación. No se inventa ninguna estación |

Redes disponibles en la app: DSN, ESTRACK, DSN+ESTRACK, personalizada (el usuario aporta latitud, longitud y elevación mínima, y asume los números) y «solo geometría».

**Sentido del enlace** (`link_direction`): `receive` (por defecto; elevación mínima de recepción, 6° en el DSN: recibir datos del lander), `transmit` (10,1°: enviar órdenes) y `both` (intersección). Comandar exige más elevación de antena, así que la cobertura de transmisión es menor. **No se modelan** la transmisión de alta potencia (13,6°, que es 13,5° + 0,1°), DSS-43 a 17,6° (> 20 kW), la máscara de terreno de cada antena (figuras 10-25 del módulo 301) ni la ocupación de la red DSN (las tres antenas de 70 m las comparten todas las misiones).

**Horas locales.** La hora civil de cada estación usa su zona IANA con horario de verano (`America/Los_Angeles` PST/PDT, `Europe/Madrid` CET/CEST, `Australia/Canberra` AEDT/AEST; `tzdata` está en `requirements.txt`). La hora solar local media es `UTC + longitud/15`, sin ecuación del tiempo.

### 9.3 Orientación de la Tierra: simplificación declarada

El motor orienta la Tierra con `IAU_EARTH` (`pck00011.tpc`), que ignora nutación, movimiento polar y UT1−UTC. Desplaza un cruce de elevación mínima unos 20 s (la elevación de la Luna cambia ~0,004°/s) y no compensa descargar el PCK binario de ITRF93 (24 MB, válido hasta 2126). Corregir `IAU_EARTH` con ΔT = ET−UTC empeora el error a 0,30°, así que no se aplica.

### 9.4 Validación independiente (14/11/2026)

La revisión (`docs/validation/revision-enlace.md`; prueba `tests/test_independent_link.py`) sigue un camino distinto al del motor: ITRF93 binario (`earth_latest_high_prec.bpc` y `earth_2026_260806_2126_predict.bpc` en `data/raw/earth/`, no versionados; las pruebas se omiten si faltan), DMS de la Tabla 5 escritos a mano, rayo 3D de la Tierra contra el DEM y JPL Horizons como contraste externo.

| Comprobación | Resultado |
|---|---|
| Luna vista desde DSS-14/-63/-43 frente a Horizons, con ITRF93 (cadena independiente) | **0,0002–0,0007°** (dic-2026 máx. 0,00016°; mar-2027 máx. 0,00070°) |
| Lo mismo con la rotación simplificada del motor (`IAU_EARTH`) | **0,072°** (rms 0,056°) |
| Posiciones de las estaciones frente a la Tabla 5 | Acuerdo exacto (< 1e-8°; el motor, a 0,3 mm por el redondeo del JSON) |
| Cobertura DSN, 1-dic-2026 a 1-ene-2027, recepción 6° | **99,929 %** (propia y motor; 3 huecos reales de 8, 15 y 8 min entre el 8 y el 10 de dic) |
| Cobertura DSN, mismo periodo, transmisión 10,1° | **97,992 %** (reproducido con el motor el 14/11/2026; la revisión da 97,99 %, 37 huecos, el mayor de 1,30 h) |
| Enlace posible por fuerza bruta 3D, 9 casos (3 sitios × 0°/3°/5° × 14 d) | \|Δ link_fraction\| ≤ **8e-4**, \|Δ hueco\| ≤ 0,29 h, mismo número de ventanas |
| Horas locales con las reglas de verano de 2027 escritas a mano (7008 instantes) | Acuerdo total |

Las diferencias del enlace por fuerza bruta se explican por el criterio de borde: el motor exige ≥ 50 % del disco terrestre sobre `H(A)` y usa rejilla de 600 s; la revisión usa el centro del disco y 120 s. Cerca del horizonte polar la Tierra sube ~0,1°/h, así que 0,03° de diferencia son ~17 min de borde (máximo observado 1049 s). Un lander con antena de haz estrecho apuntada al centro verá ventanas algo distintas. La red **no restringe** los enlaces de 14 d en los polos sur (los huecos reales de la red caen en horas sin Tierra); sí restringe en puntos cercanos al centro del disco lunar visible.

Los defectos que halló la revisión (B1 selección de fecha sin G7, B2 huecos espurios de ~3 s en traspasos, B3 textos de contactos con ventanas inexistentes) están corregidos: `tests/test_independent_link.py` da **37 passed** (14/11/2026) y ya no quedan `xfail`.

### 9.5 `s_earth` con continuidad absoluta y puerta G7

```
s_earth = min(1, f_enlace / max(f_ref, suelo)) · c_hueco · c_día
```

- `f_ref`: Tierra sobre una esfera lisa con el mismo margen y **sin** red (la red es un factor externo común que penaliza); `suelo` = 0,25 (0,5 en comunicaciones).
- `c_hueco = 2^(−hueco_máx / (k · hueco_tolerado))`: vale 1 sin hueco y 1/2 cuando el hueco es `k` veces lo que tolera el perfil (G7); `k = gap_half_factor = 1` [sup]. Misma familia que `s_noche`.
- `c_día = min(1, h_contacto_por_día / mínimo útil del perfil)`: lineal hasta el mínimo (2 h; 8 h en base/ISRU; la ventana útil de G6, [sup]).
- Es un producto, no compensatorio: ni muchas horas compensan un apagón largo ni un enlace continuo compensa tener casi ninguna hora. `k = 0` desactiva el factor.

**Por qué.** La parte relativa satura contra la esfera lisa *de la misma ventana*: un enlace del 62 % con 127 h sin comunicaciones puntuaba 97,41, igual que un enlace del 100 % sin huecos, porque la esfera lisa de aquella ventana también ve la Tierra solo el 36 %. Con la continuidad absoluta ya no saturan. Caso real (Shackleton, punto TOP-1 del mapa, 14 d, reproducido el 14/11/2026): la ventana del 6-dic (enlace 62,1 %, hueco 127,5 h) puntúa **73,9 y sale CONDICIONAL** por G7; la del 12-dic (enlace 100 %, sin hueco) puntúa 97,4 y sale APTO (`docs/guion-demo.md`).

**G7** (hueco máximo sin enlace, blanda): los umbrales (§6) son suposiciones, pero discriminan. Con el enlace propio de la revisión, en el mejor punto de Shackleton y con fechas de inicio cada 6 h del 1-dic al 28-mar, un hueco ≤ 12 h ocurre en el 23,5 % de las fechas, ≤ 48 h en el 34,8 % y ≤ 96 h en el 49,9 %. G7 cuenta el hueco truncado del borde inicial: se lee como «hueco inicial» (aterrizar sin enlace). Un valor cercano al límite (Malapert con margen de 3°: 47,1 h frente a 48 h) aconseja mirar el hueco y no solo PASS/FAIL.

### 9.6 Qué no es el enlace posible

No es un presupuesto de enlace RF: sin potencia de transmisión, frecuencia, ganancia de antena, ruido, ocupación de la red, pérdidas de apuntamiento ni máscara de terreno de la antena terrestre. Es la condición necesaria geométrica y de cobertura, no una garantía. Ver `docs/limitaciones.md` §3b.

## 10. Cifras de la pantalla «Capacidad del sitio»

La pantalla no calcula física propia: agrega lo que devuelven `pipeline.run_analysis` y `pipeline.run_power`.

| Cifra | Cómo sale |
|---|---|
| Sol visible, noche máxima, ventana solar más larga, elevación solar máxima | Métricas del §4 sobre la ventana de misión (o el periodo completo, a elección) |
| Potencia eléctrica media y pico (W/m²) | `P_rel` medio o máximo × `areal_power_w_m2_am0` del panel (§5); sin ese dato la app escribe «sin dato», nunca 0 |
| Energía por día (Wh/m²), media y mínima | `e_rel` de cada día UTC × 24 h × `areal_power_w_m2_am0`; la mínima es el día que dimensiona el sistema |
| Tierra visible (geometría) frente a **ENLACE POSIBLE** | `earth_fraction` frente a `link_fraction` (§9.1) |
| Horas de contacto por día | Media: `24 · link_fraction`. Mínima: el día UTC **completo** con menos horas (la app muestra «—» si el periodo no contiene ninguno) |
| Ventana de enlace más larga y **hueco máximo sin enlace** | §9.1; con «≥» si tocan el borde del periodo. El hueco se compara con el que tolera el perfil (G7, §9.5) |
| Sensibilidad al margen de antena | Repite el análisis con 0°, 3° y 5° sobre el periodo completo y muestra enlace, horas por día, ventana más larga y hueco máximo |
| Tabla por base terrestre | Por estación: % de tiempo con enlace, horas por día, número de ventanas, % del tiempo que la estación ve la Luna, elevación mínima (con «SUPUESTA» en ESTRACK), elevación máxima de la Luna, contacto más largo en UTC, en hora local civil y en hora solar local media |
| Contactos de un día | `ground_stations.daily_contact_table`: las ventanas **reales** de cada estación que tocan ese día UTC, sin partirlas ni unirlas, con su hora local completa y la etiqueta «continúa del día anterior / al día siguiente» |

Los rangos de incertidumbre bajo cada cifra clave salen de los escenarios del §6; si no se calcularon, la pantalla dice «no calculado».
