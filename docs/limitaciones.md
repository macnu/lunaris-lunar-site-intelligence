# Limitaciones

LSI es un prototipo de apoyo a decisiones para comparar lugares y fechas. **No es un sistema certificado de selección de sitio de aterrizaje.** Este documento reúne lo que la herramienta no hace o hace con reservas, con la fuente de cada cifra.

## 1. Lo que LSI no afirma

| Tentación | Lo que LSI dice en realidad |
|---|---|
| «Se ve el Sol, luego hay energía» | **Visibilidad geométrica ≠ potencia.** La potencia es una estimación relativa con supuestos declarados (§3). |
| «Se ve la Tierra, luego hay comunicaciones» | **Visibilidad geométrica ≠ enlace RF.** `f_Tierra` es la fracción de tiempo con ≥ 50 % del disco terrestre sobre el horizonte (criterio de LSI, a calibrar). |
| «ENLACE POSIBLE: se puede comunicar» | **Enlace posible = geometría + cobertura de estación, no un presupuesto de enlace RF ni una garantía.** Significa que la Tierra se ve con un margen de antena y que alguna estación de la red ve la Luna por encima de su elevación mínima. No hay potencia, frecuencia, ganancia, ruido, ocupación de la red ni máscara de terreno de la antena (§3b). |
| «APTO» | No significa «seguro» ni «aterrizable»: no se modelan rocas, plumas, navegación ni incertidumbre de aterrizaje; solo pendiente del DEM. |
| «Recomendado» | Los mejores puntos son una ordenación geométrica con umbrales por calibrar: **zonas candidatas a inspeccionar**, no sitios validados. |
| «La nota es 98» | El score ordena y explica; el veredicto lo deciden las puertas y los escenarios de incertidumbre. Pesos y umbrales son convenciones de LSI sin calibrar con un experto de misión. |

## 2. Datos

- **Resolución efectiva ≈ 30 m, no 5 m.** El 90–92 % de los píxeles del DEM no tiene retorno LOLA propio (`ldec = 0`); la distancia al píxel observado más cercano es de 7 m (mediana), 15–16 m (p90) y 25–29 m (p99). La textura de alta frecuencia es 20–100 veces menor en píxeles interpolados (`docs/science/terreno-geologia.md` §2.1). «30 m» es una heurística de LSI (2 × p90), a verificar frente a la literatura de PGDA.
- **Rocas y cráteres pequeños no se ven.** Rocas (≲ 5 m): sin información. Cráteres de 10–100 m: invisibles o suavizados. Regolito, capacidad de carga y espesor: fuera de alcance. El caso real que el DEM no resuelve: Odysseus (IM-1, 2024) volcó apoyado en una roca; su pendiente local de ~12° proviene de una sola fuente de prensa y **no está verificada** (la inclinación final de ~30° sí consta en prensa).
- **Rugosidad.** Por debajo de ~50 m es artefacto de interpolación, no rugosidad de regolito.
- **Cobertura del DEM de 5 m.** 16×16 km (Shackleton, de Gerlache) y 21×21 km (Malapert). Más allá, el DEM polar de 80 m (estimación del horizonte lejano; difiere del 5 m con RMS 1,2 m en el solape de Site04). Donde se agota el dato, el horizonte es una cota inferior y el resultado es optimista en iluminación; el azimut se marca como limitado.
- **Los centros de los rasgos no son puntos de aterrizaje.** Los centros USGS de Shackleton y de Gerlache caen **fuera** del recorte de 5 m (Shackleton −89,67°, 129,78°E → x = 7690 m, límite 7000 m). Si el centro queda fuera del DEM, la app evalúa el **mejor punto del mapa de idoneidad limitado al entorno del rasgo** (≤ radio·1,15 + 1 km del centro; Shackleton cae a ~0,34 km dentro de su borde, de Gerlache en su margen, 0,20 km fuera) y lo dice en el aviso; sin ninguno dentro, el punto cubierto más cercano. Los resultados valen para ese punto, no para el centro, y un punto elegido por optimización es optimista.
- **Horizonte cercano.** Con el observador a 2 m, el horizonte lo fija a menudo el terreno a 7–100 m del punto, justo la escala interpolada. La altura del observador cambia mucho el resultado.
- **Intervalo temporal.** 1900–2050 (kernel de orientación lunar). Fuera, la interfaz rechaza la fecha.

## 3. Modelo de potencia

- Es una estimación **relativa** (% de la potencia nominal del propio panel). No son vatios de misión; no se dan vatios sin área.
- **Sin polvo** (solo un parámetro de sensibilidad, sin valor físico por defecto), **sin albedo, sin sombra propia, sin eclipses de la Tierra sobre el Sol.** Los eclipses (~2 al año, hasta ~3,5 h, estimado) pueden hacer que una noche supere el límite de supervivencia.
- **IAM** (pérdida a incidencia rasante): a más de 80° es la parte más incierta. **Temperatura**: balance estacionario simple con T_amb = 100 K (a verificar); probablemente subestima la temperatura real y es optimista en eficiencia.
- **Catálogo de paneles.** Los 8 paneles son calculables y están en dos grupos (`docs/validation/datos-paneles.md` registra cada parámetro con su fuente y página, leída el 14/11/2026):
  - **Respaldados (5)**: GaAs 3J (lander, mástil, rover), 4J de alta eficiencia y ROSA flexible. η y γ_T vienen de datasheet o paper, o se derivan de ellos. «Respaldado» se refiere a la **celda de referencia** modelada: ni VSAT, ni los rovers ni la manta ROSA publican la eficiencia de su conjunto, así que su potencia por área (401,5 W/m² para 3J, 426,0 para 4J) es de **celda/CIC**, una cota superior sin empaquetado, cableado ni estructura.
  - **Experimentales sin datasheet (3)**: silicio legado (γ_T no disponible), CIGS flexible y perovskita-silicio (laboratorio, sin medida espacial). Salen siempre etiquetados «EXPERIMENTAL», con banda de incertidumbre, y no se mezclan con los respaldados en los rankings por defecto. Perovskita-silicio es solo una demostración.
  - Si falta un parámetro sin estimación, la app devuelve «no calculable» o «sin dato», nunca un 0. Muchos parámetros siguen «a verificar» (`PANEL_UNVERIFIED`): absortividad y emisividad de varios paneles, γ_T de los experimentales, η de manta de ROSA. ROSA, VSAT y 4J no deben presentarse como «usados en la Luna» salvo donde el catálogo lo diga como publicado.
- **W/m² y Wh/m² son de celda y por área**: `P = P_rel × areal_power_w_m2_am0`. No se dan vatios de misión: faltan el área real, el empaquetado y la degradación del conjunto.
- **Valores superiores a 100 %.** Son posibles en el perihelio y por frío; no se recortan.
- **Supervivencia nocturna.** No se promete. El límite de 12 h del lander sin RHU es una estimación con una carga supuesta (50 W), apoyada en una fuente secundaria.

## 3b. Conectividad (enlace posible)

- **No es un presupuesto de enlace RF.** Sin potencia de transmisión, frecuencia, ganancia ni apuntamiento de antena, ruido, pérdidas, ocupación de la red DSN (las tres antenas de 70 m las comparten todas las misiones) ni máscara de terreno de la antena terrestre (figuras 10-25 del módulo 301, que puede subir la elevación mínima en algunos azimuts). Es la condición necesaria geométrica y de cobertura.
- **Solo recepción a 6° por defecto.** El sentido por defecto es `receive`. Comandar exige transmitir: con 10,1° la red DSN cubre el 97,992 % del tiempo (frente al 99,929 % en recepción; dic-2026). La app lo modela (sentido «transmisión» o «ambos»), pero **no** la transmisión de alta potencia (13,6°) ni DSS-43 a 17,6° (> 20 kW), que bajarían más la cobertura (94,2 % a 13,6° en la revisión).
- **Margen de antena del lander: 0° por defecto, suposición.** La sensibilidad a 3° y 5° baja mucho el enlace (p. ej. Shackleton, punto del demo, 14 d desde el 12-dic: 100 % a 0°, 84,1 % a 3°, 73,6 % a 5°). Ninguno de los márgenes está publicado.
- **ESTRACK: elevación mínima SUPUESTA (6°), no publicada**, y la red no es la de por defecto. La interfaz lo avisa. **La red NSN de NASA no está incluida**: anuncia LEGS-1 (White Sands), pero no se pudo verificar ni su ubicación ni su elevación ni su fecha de operación, así que no se inventó ninguna estación. Una red personalizada es responsabilidad del usuario.
- **Orientación de la Tierra simplificada** (`IAU_EARTH`, sin nutación ni movimiento polar): 0,072° frente a JPL Horizons (0,0002–0,0007° con ITRF93 en la revisión independiente). Mueve cada cruce ~20 s; en la cobertura de red es invisible a 5 cifras.
- **El criterio «≥ 50 % del disco terrestre»** (no el centro) mueve los bordes del enlace hasta ~17 min respecto a un lander con antena de haz estrecho apuntada al centro (|Δ enlace| ≤ 8e-4 en 14 d). Y la rejilla de 600 s con refinamiento deja errores de borde de segundos a minutos.
- **G7 y sus umbrales (12–96 h) son suposiciones** sin fuente publicada; `c_hueco` y `c_día` del score también ([sup]). Un valor cerca del límite pide leer el hueco y no solo PASS/FAIL. G7 cuenta el hueco truncado del borde inicial (llegar sin enlace).
- **Horas locales**: hora civil con horario de verano y hora solar local media (`UTC + longitud/15`, sin ecuación del tiempo). Los textos de contactos salen de `daily_contact_table`; un informe previo contenía ventanas inexistentes («Canberra 09:34-22:11 AEDT», «Goldstone 10:21-18:12 PST») por partir las ventanas por día UTC y unir sus trozos con mínimo-máximo. Está corregido (`revision-enlace.md`, B3); no se deben reconstruir a mano.
- **Cobertura común**: la máscara de red usa el centro de la Luna para todos los sitios; el error por sitio es ≤ 0,28° de elevación y ≤ 0,07 puntos porcentuales de cobertura.

## 4. Score, puertas y veredicto

- Todos los umbrales (0,20/0,90 de Sol, 48 h de semivida de la noche, 5°/15° de pendiente, mínimo de Tierra 0,25, λ = 0,25, 10 % de fechas factibles) son **convenciones de LSI, a calibrar**.
- Los límites por perfil son suposiciones o convenciones salvo donde se dice «publicado»: 14 d (IM-1 ~14 d, IM-2 ~10 d, Blue Ghost ~14 d: prensa), 100 d y 50 h del rover (VIPER, NASA, NTRS 20220008301), 12 h y 36 h (suposición). La pendiente de 10° de diseño del lander es una declaración del CTO de Intuitive Machines en prensa, no una especificación.
- **`s_earth` mide enlace con continuidad absoluta** (relativo a la esfera lisa × `c_hueco` × `c_día`): ya no satura con un hueco largo, pero `k`, el hueco tolerado y las horas mínimas por día son suposiciones de LSI. Un APTO sigue exigiendo que G7 no falle en el nominal ni en los escenarios; un hueco de 127 h hace CONDICIONAL aunque haya Sol el 100 % del tiempo.
- **El score depende del panel y del montaje elegidos** (la subpuntuación de Sol usa la potencia efectiva) y la **puerta G5** (potencia útil) solo se evalúa con panel: un montaje horizontal en el polo suele fallar G5 aunque el Sol sea visible. Sigue sin ser un predictor validado. El **rango** es «no calculado» si no se pidió el análisis de incertidumbre, y puede tener ancho cero en puntos saturados.
- **El estado depende del periodo analizado** (ver `metodologia.md` §6): con un periodo mayor que la misión se prueban varias fechas y la fracción factible puede bajar del 10 %, lo que convierte un APTO en CONDICIONAL.
- **Los 55 mejores puntos del mapa anual (365 d) fallan una puerta** (`gate_status = FAIL`, peor subindicador: noche), según `docs/validation/revision-geologica.md`. En ventanas de 7 y 14 días hay puntos que pasan todas las puertas; en 30 días, con el perfil lander, ninguno en Shackleton y pocos en de Gerlache y Malapert (ver `data/processed/suitability/windows_*.json`). La fecha manda.
- **La pendiente se mide a escala de huella** (disco de 50 m, baseline 10 m). A la escala de 100 m que usa NASA para un sitio, los mejores puntos tienen píxeles de 9–26° (7 de 15 con p90 > 10°). No hay huella totalmente llana: habría que elegir un parche dentro del disco.
- **Regiones permanentemente sombreadas (PSR).** No se modelan en detalle; la distancia a una PSR «estricta» es una cota y no está validada contra mapas publicados (a verificar).

## 5. Mapa de idoneidad y búsqueda

- El mapa precalculado es **grueso**: malla de 250 m, horizonte cada 1° y serie cada 30 min sin refinar. Usa el **enlace** de la red DSN en recepción con margen de 0° (no la Tierra geométrica); otra red, sentido o margen exige regenerarlo con `--link-network`, `--link-direction` o `--min-earth-elevation`. La **mejor fecha** de cada punto respeta G7, por lo que puede cambiar entre regeneraciones (el punto de de Gerlache del demo pasó de 2026-12-16 a 2027-06-21). Frente al modelo fino (12 nodos del TOP en el perfil lander, año completo) difiere hasta 0,0098 en f_sol, 0,0039 en f_Tierra y 0,44 puntos de score; la oscuridad máxima difiere hasta 2,3 h (Site04), 2,7 h (Site11) y **50,2 h (Site23)** en un nodo (el nodo concreto no se ha analizado). Estas diferencias se midieron con una versión anterior del mapa (antes de la continuidad del enlace): **hay que repetir `--validate 12` con el mapa actual**. Siempre hay que confirmar en el modelo fino con «Evaluar este punto y fecha».
- La malla de 250 m **no encuentra todos los puntos**: un punto a 100 m de un nodo puede ser mejor o peor.
- Solo se precalculan los perfiles «lander solar sin RHU» y «rover», y duraciones de 7, 14 y 30 días, para las fechas de inicio de 2026-12-01 a 2027-11-30. Otros perfiles y fechas necesitan regenerar con `python scripts/precompute_suitability.py`.
- Las cifras de los JSON precalculados pueden cambiar si se regeneran con otros parámetros (hay varios JSON por sitio y perfil; la app usa el más reciente).
- **Un punto no es una zona.** Un punto y una altura (2 m por defecto); unos metros más allá o días después puede cambiar mucho.
- No es una búsqueda exhaustiva de todos los emplazamientos del polo sur: solo tres zonas con DEM de 5 m.
- **Buscador:** 9106 lugares (9087 rasgos USGS + 19 sitios de misión, 56 alias). El 78 % de los rasgos USGS son «Satellite Feature» (7064); la búsqueda difusa mete ruido (Shackleton devuelve también Appleton y Hamilton). Las regiones Artemis III no tienen coordenadas y no son buscables.

## 6. Validación: qué no se pudo contrastar

- **Cifras publicadas de fracción de Sol y noche máxima para Shackleton (Site 4), de Gerlache (Site 11) y Mons Malapert (Site 23).** Barker et al. (2021) solo tabula Site 1 (Connecting Ridge) y PGDA 78 confirma iluminación solo para Site 1. Mazarico et al. (2011), Table 3, no se leyó. Por eso `tests/test_luna_cases.py` no tiene casos de esos sitios.
- **«~240 d de Sol y ~1,5 d de noche»** (Mazarico 2011): coherente con LSI solo si corresponde a una altura de decenas de metros (a 10 m, la RoI 4 da 1,3–1,8 d de noche; a 2 m, 4,7–5,1 d). La altura de esa cifra **a verificar**.
- **Visibilidad de la Tierra publicada** en estos sitios: no se encontró ninguna cifra verificada. La comprobación es interna (esfera lisa a −89,9°: 47,0 % en 2026-27).
- **Malapert frente a Bussey et al. (2010)** (vía Wikipedia, secundaria): orden de magnitud coherente (70 % frente a 74 % en el mejor punto cercano), pero **no es una validación**.
- **Sol continuo anual**: depende del periodo y de la ventana (una ventana de 365 d trunca rachas de ~240 d; varía entre 125 y 250 d según el año en la RoI 4 a 2 m). Para compararlo con la literatura hay que usar ventanas ≥ 2 años. El mapa de idoneidad usa 365 d desde 2026-12-01.
- **Definiciones distintas.** `f_sol` es «tiempo con cualquier parte del Sol»; la «iluminación media» de la literatura promedia la fracción de disco y es 3–7 puntos menor. Compararlas sin esa salvedad parece una discrepancia.
- **Enlace y estaciones: sí hay validación independiente** (`docs/validation/revision-enlace.md`, 37 pruebas, 14/11/2026): posiciones de las estaciones frente a DSN 810-005/301 Rev. P, Luna desde las estaciones frente a Horizons, cobertura DSN y enlace 3D por fuerza bruta (ver `metodologia.md` §9.4). Lo que **no** se pudo contrastar: la máscara de terreno de cada antena, la ocupación del DSN, la elevación mínima de ESTRACK, ninguna estación NSN y la elevación de transmisión de alta potencia en esta versión.
- **La comprobación independiente 3D usa el mismo DEM y los mismos kernels** que el motor: valida la matemática, no los datos. Seis puntos y tres ventanas de 30 días son una muestra, no una prueba exhaustiva; no se revisaron el modelo de potencia ni la incertidumbre.
- **Misiones de referencia.** Las fechas y estados de misiones (IM-1, IM-2, Blue Ghost M1, Chandrayaan-3, VIPER, Artemis III) provienen de prensa o wikis (fuentes secundarias). Las nueve regiones vigentes de Artemis III no tienen coordenadas oficiales verificadas en `config/sites.json`; la lista oficial y su estado actual, a verificar.
- **Licencias de los datos.** Política general verificada el 14/11/2026: NASA indica que su contenido «generalmente no está sujeto a copyright en EE. UU.» (https://www.nasa.gov/nasa-brand-center/images-and-media/) y el USGS que sus datos son de dominio público (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). **No** se ha verificado la condición específica del producto PGDA 78/90, de la nomenclatura IAU WGSN ni de JPL Horizons: **a verificar** (`docs/fuentes-datos.md`). La **licencia del código** la decide el usuario: no hay fichero `LICENSE`. No hay repositorio remoto ni commits.

## 7. Qué se deja para después

Hoja de ruta del documento base (§10): sensibilidad con clones del DEM y propagación de incertidumbre, análisis espacial por polígonos y no solo por punto, orientación de paneles con almacenamiento detallado, presupuesto de enlace RF y geometría de antenas, y exportación a flujos técnicos de misión.

## Honestidad numérica añadida el 14/11/2026

- **Pendiente a dos escalas.** El veredicto usa la huella de r = 50 m; `AnalysisResult.slope_r50` y `slope_r100` dan media, p90, máximo y % de área ≥ umbral de aterrizaje a 50 y 100 m, y `footprint_touches_dem_edge` avisa si la huella de 100 m roza el borde del recorte. Esquema de exportación 1.3.0 (`slope_footprint`).
- **Rangos del mapa de idoneidad.** `score_range_resolution` (±1 paso temporal en D_max; puede tener ancho cero) NO es incertidumbre física. `score_range_uncertainty` es el rango entre escenarios ±σz y ΔA (y H_ub cuando algún azimut queda sin cobertura) del modelo fino en la mejor fecha, de 7/14/30 d. En los TOP-N de 7 y 14 d el Sol es continuo (f_sol = 1) y el rango real también es de ancho cero: es saturación real del dato, no falta de cálculo; H_ub no aplica porque ningún azimut queda sin cobertura.
- **Banda de potencia a incidencia rasante.** `panels.json` declara ahora el modelo de IAM que se usa (Fresnel de una interfaz). `power_band_detail` da la envolvente conjunta de {parámetros estimados} × {IAM: Fresnel, solo-coseno, n = 1,40/1,60 [sup], ASHRAE b0 = 0,05 [a verificar]} × {T_amb 40-200 K [sup]}. T_amb nominal = 100 K sigue **a verificar**: no se halló fuente primaria del IR del regolito iluminado a Sol rasante (Paige et al. 2010 da 38 K en una trampa fría; Fisher et al. 2017 sitúa las temperaturas máximas polares entre ~100 y ~300 K, pero no es la temperatura de un sumidero para un panel).
