# Guía de usuario

Cómo usar LSI según quién seas y qué necesites. Arranque: `python -m streamlit run app.py` (instalación y datos en el [README](../README.md)).

Esta guía describe la rama **`main`** (versión funcional). La identidad visual LUNARIS (navegación superior, panel de control con anillos) y el **visor 3D con foto, Sol y Tierra reales y vista del observador** están en la rama `feat/lunaris-ui`, no en `main`; cómo cambiar de rama, en el README.

## Los tres modos

El selector **Modo de usuario** está en la barra lateral. El modo cambia cuánto detalle ves, no el cálculo.

| Modo | Para quién | Qué cambia |
|---|---|---|
| **Público** (por defecto) | Educación y curiosidad | Cuadros «en llano» en cada pantalla, textos con frases completas, pocas columnas, 3 puntos recomendados. |
| **Planificador** | Quien compara sitios y fechas | Más columnas (f_sol, f_Tierra, oscuridad máxima, inicios aptos, puertas), TOP-N ajustable. |
| **Experto** | Ingeniería y ciencia | Parámetros del cálculo, pendiente p90, panel «Avanzado» (paso de la serie, incertidumbre, esfera lisa, degradación, polvo), detalle técnico de puertas y temperatura del panel. |

## La barra lateral (común a todas las pantallas)

- **Sitio**: Shackleton, de Gerlache o Mons Malapert con DEM de 5 m (el punto por defecto es Mons Malapert), otros sitios del catálogo o coordenadas propias (latitud sur negativa, longitud este 0–360).
- **Altura del observador** (m): 2 m por defecto.
- **Inicio** (UTC, `AAAA-MM-DD HH:MM`) y **duración** (1 día, 7 días, día lunar ≈ 29,5 d, 30 días, 1 año o personalizada). Rango válido 1900–2050.
- **Panel(es)**, **montaje** (horizontal, inclinado, vertical fijo, vertical con seguimiento azimutal) y **perfil de misión**; opcionalmente una duración de misión propia.
- **Conectividad** (modos Planificador y Experto; en Público se muestra la elección sin poder cambiarla): **red de estaciones** (DSN por defecto, ESTRACK, DSN+ESTRACK, personalizada o «Solo geometría», que ignora las estaciones), **sentido del enlace** (recepción, 6° en el DSN; transmisión, 10,1°; o ambos) y **margen mínimo de elevación de la antena** del lander (0° por defecto). En modo Experto puedes forzar la elevación mínima de todas las estaciones como sensibilidad. La red NSN de NASA no está en la lista porque no se pudo verificar.
- Panel «Avanzado» (modo Experto): paso de la serie, incertidumbre, «ignorar el DEM», degradación y polvo.

Arriba de cada pantalla con resultados hay una **banda de avisos científicos** que no se puede ocultar (visibilidad geométrica, eclipses no modelados, resolución efectiva del DEM). Léela: es parte del resultado.

## Recorrido por pantallas

La app tiene 11 pantallas, en este orden.

1. **Buscador**: escribe un nombre (p. ej. «Malapert», «Tycho», «Shackleton», «Apolo 11») entre 9119 lugares (9087 rasgos USGS + 32 sitios: misiones, las tres zonas con DEM y 13 regiones Artemis III aproximadas; 56 alias es/en). Filtra por tipo y región. «Evaluar este lugar» fija el punto. Si el centro cae fuera del DEM de 5 m, LSI evalúa el **mejor punto del mapa limitado al entorno del rasgo** (Shackleton: ~0,34 km dentro del borde) y el aviso `snap_to_dem` da la distancia al centro y al borde; si no hay mapa, el punto cubierto más cercano. El resultado es del punto elegido, no del centro.
2. **Capacidad del sitio** (la siguiente, tras el buscador): responde «según la ubicación, qué energía solar y qué conectividad tendría un lander». Ver el apartado siguiente.
3. **Explorador 3D**: el terreno real del DEM de 5 m alrededor de tu punto como **mapa topográfico 2D** (relieve sombreado, curvas de nivel, nombres, escala y norte; un clic sobre el mapa fija otro punto) y como **superficie 3D**, con capas de elevación, pendiente, incertidumbre vertical, muestreo y **iluminación (Sol y sombras)**. Ver «El Explorador: mapa topográfico e iluminación».
4. **Mapa del polo sur**: el polo entero (de 80°S al polo, ±304 km) como mapa navegable, con nombres, los tres recortes de 5 m y capas reales (PSR, temperatura, iluminación publicada). Un clic elige un punto y «Evaluar este punto» lo lleva a «Capacidad del sitio». Ver «El Mapa del polo sur».
5. **Mejores puntos y fechas**: elige sitio, perfil y duración; el mapa muestra los mejores puntos y la tabla la mejor fecha de inicio (que respeta la puerta G7 de huecos de comunicaciones). «Evaluar este punto y fecha» lo abre con el modelo detallado. Necesita el precálculo.
6. **Horizonte y visibilidad**: horizonte 360°, Sol y Tierra con su disco, cursor temporal (con animación) y cuenta atrás hasta puesta/salida de Sol y Tierra. Una «≈» indica que el evento depende de un tramo de horizonte limitado por cobertura.
7. **Línea temporal**: bandas de Sol, Tierra (y enlace), solape y oscuridad. Vistas: periodo actual, comparar fechas, año y estaciones, animación. «Zona de duda» = horizonte pesimista (activa la incertidumbre). Exporta CSV/JSON.
8. **Comparación de sitios**: hasta 5 sitios o puntos lado a lado. **Por defecto cada sitio se compara en su mejor candidato** (el TOP-1 del mapa de idoneidad del perfil y la duración elegidos, en su mejor fecha de inicio); una opción cambia a «Punto por defecto de cada sitio», que puede ser un marcador (pared de cráter, zona en sombra) y dar 0 % de Sol. Los puntos propios se comparan siempre tal cual. No hay «ganador» automático: cada medida se ve por separado.
9. **Potencia y paneles**: compara paneles y montajes en % de su potencia nominal. Los 8 paneles son calculables y están en dos grupos: 5 **respaldados** (GaAs 3J en tres versiones, 4J, ROSA) y 3 **experimentales sin datasheet** (silicio, CIGS, perovskita-silicio), que salen siempre etiquetados y con banda de incertidumbre. En el polo el montaje por defecto es vertical con seguimiento.
10. **Score del sitio**: perfil, pesos editables, puertas (de G0 a G7), desglose y confianza. El score depende del panel y el montaje elegidos: un montaje que no da potencia útil falla la puerta G5 y baja el veredicto; un hueco de comunicaciones largo falla G7.
11. **Acerca de y límites**: fuentes, convenciones, validación y créditos.

## La pantalla «Capacidad del sitio»

Qué ves, de arriba abajo:

- **Cabecera**: el lugar y el punto exacto, el periodo analizado, la ventana de misión y la mejor fecha. Si la ventana de misión es más corta que el periodo, un selector te deja ver las cifras «sobre la ventana de misión» o «sobre el periodo completo». Un interruptor activa los **rangos de incertidumbre** bajo cada cifra clave (el primer cálculo es más lento; si no se calculan, la pantalla dice «no calculado»). En Público y Planificador hay una «lectura rápida» en lenguaje llano.
- **Solar**: Sol visible (fracción del tiempo), noche máxima, ventana solar más larga y elevación solar máxima. Para el panel y el montaje elegidos: **potencia eléctrica media y pico en W/m²** (con el % de la potencia nominal), **energía por día en Wh/m²** (media y mínima: el día peor es el que dimensiona el sistema) y la banda de incertidumbre del panel. Es potencia de celda por metro cuadrado, sin empaquetado; sin panel elegido o sin eficiencia, la pantalla lo dice y nunca muestra 0.
- **Conectividad**: la **Tierra visible (geometría)** junto al **ENLACE POSIBLE**. El enlace posible exige la Tierra visible con el margen de antena **y** alguna estación de la red viendo la Luna: nunca es mayor que la Tierra visible. Debajo: **horas de contacto por día** (media y mínima), **ventana de enlace más larga** y **hueco máximo sin enlace** con sus fechas, quién recupera el enlace después y si supera lo que tolera el perfil (puerta G7: «superada» o «no superada»). Un «≥» o «al menos» indica que el tramo toca el borde del periodo y la cifra es una cota inferior.
- **Solar en detalle**: tabla de hasta 3 paneles en el montaje elegido más horizontal y vertical con seguimiento (potencia media y pico, Wh/m² medio y mínimo, nivel de evidencia y la etiqueta EXPERIMENTAL), el factor vertical/horizontal y la curva de potencia de un día.
- **Conectividad en detalle: bases terrestres** (solo con red): la **sensibilidad al margen de antena** (botón «Calcular la sensibilidad»; repite el análisis con 0°, 3° y 5°); la **tabla de bases terrestres** (% de tiempo con enlace, horas por día, ventanas, ventana más larga, % del tiempo que la estación ve la Luna, elevación mínima de la antena —con «SUPUESTA» en ESTRACK—, contacto más largo en **UTC, hora local civil con su zona y hora solar local media**); los **contactos de un día** que eliges (ventanas reales, con «continúa del día anterior / al día siguiente») y un gráfico de contactos en UTC o en hora local de cada estación.
- **Ficha del sitio**: descarga de las cifras de la pantalla en JSON o en CSV (zip).
- Arriba, una nota fija recuerda que **enlace posible no es un presupuesto de enlace RF**, que Sol visible no es potencia garantizada, que ESTRACK usa una elevación supuesta y que la red NSN no está incluida.

Cómo leer el **sentido** del enlace: «recepción» responde a «¿puedo recibir los datos del lander?» (el DSN necesita ver la Luna a ≥ 6° de elevación); «transmisión» responde a «¿puedo enviarle órdenes?» y exige ≥ 10,1°, así que su cobertura es algo menor; «ambos» exige las dos cosas a la vez.

## El Mapa del polo sur

Úsalo para situarte **antes** de elegir un punto: qué hay alrededor, dónde están las zonas permanentemente sombreadas y qué recortes de 5 m existen. Es un relieve sombreado del DEM polar de 80 m (celdas de ≥ 80 m; la vista completa, a ≈ 480 m), no la iluminación de una fecha.

1. **Navega.** El zoom va de 1 (polo entero, ±304 km) a 64 y se desplaza con los botones «Desplazar». Hay paralelos y meridianos, curvas de nivel, escala y norte; los **nombres del gazetteer** salen por diámetro, sin solaparse, y los **tres recortes de 5 m** (Shackleton, de Gerlache, Malapert) aparecen marcados. El buscador por nombre centra el mapa en un rasgo (p. ej. «Shackleton» y sus vecinos Sverdrup, Faustini o de Gerlache).
2. **Activa capas** («Sin capa de color», temperatura media, máxima, mínima, o iluminación media publicada) y el contorno de las **PSR**. Cada capa lleva su rótulo: la temperatura es la del **regolito** (Diviner, estacional) y la iluminación publicada es la de **superficie a lo largo de 18,6 años**. Si falta un fichero, la capa se oculta con un aviso y el comando para bajarlo (`python scripts/fetch_thermal_psr.py`): nunca se dibuja nada inventado.
3. **Elige un punto con un clic.** La precisión es la de la celda del mapa mostrado (la pantalla la indica en km): acércate para afinar. Un botón usa el centro de un rasgo como punto, pero **el centro de un cráter es su suelo**, normalmente en sombra permanente: el borde y las crestas son otra cosa.
4. **«Evaluar este punto»** abre «Capacidad del sitio» con ese punto. Si cae dentro de un recorte de 5 m, el cálculo usa el DEM de 5 m; si cae en otra parte de 80°S al polo, usa el **relieve aproximado de 80 m** (ver más abajo).

Lectura honesta de las capas: una PSR publicada es sombra en 18,6 años a nivel de superficie, no la sombra del año que simulas; el mapa de iluminación media no es comparable con el `f_sol` de un punto a 2 m (en los TOP-1 difieren 0,2-0,3, `docs/limitaciones.md` §6); y la temperatura no es la de un panel.

## El Explorador: mapa topográfico e iluminación

Con un punto dentro de un recorte de 5 m, el Explorador dibuja primero el **mapa topográfico** y debajo la superficie 3D. Controles: **Capa** (elevación, pendiente, incertidumbre vertical, calidad de muestreo, **iluminación**), **Alcance del recorte** (3 km, 6 km o todo el recorte; el cálculo científico usa siempre el DEM entero), **Exageración vertical** y **Altura del observador**. Un clic en el mapa fija otro punto.

**Capa «Iluminación (Sol y sombras)».** Pide una fecha y una hora (deslizador de 1 h dentro del periodo analizado) y pinta qué celdas del recorte ven el Sol y cuáles están en sombra del propio relieve, con penumbra. La posición del Sol sale de SPICE, como en el resto de la app.

- La luz y las sombras son **las del relieve del DEM dentro del recorte mostrado**: una montaña fuera del recorte no proyecta sombra; la penumbra es aproximada.
- **Sin foto en `main`.** El Explorador de `main` pinta relieve sombreado y capas, no fotografía. La foto (mosaico LROC NAC promedio de pasadas, ortomosaico SDEM de máxima iluminación) la pone el visor 3D de la rama `feat/lunaris-ui`, y allí las sombras de la foto **no son las de tu fecha**.
- Es una capa de visualización: no cambia el score.
- Sin la capa de iluminación el mapa sale con relieve sombreado fijo. Los detalles de cómo se calcula, en [`metodologia.md`](metodologia.md) §2.2.
- Un punto sin recorte de 5 m **no tiene 3D**: se muestra el mapa global plano con el aviso «Relieve aproximado (80 m)», y el horizonte, el Sol y la Tierra se calculan con el DEM de 80 m. Para el relieve de la zona, usa el Mapa del polo sur.

## Qué significa «Relieve aproximado (80 m)»

Es el modo de cualquier punto de 80°S al polo **fuera de los tres recortes de 5 m**: el horizonte sale solo del DEM de 80 m. Verás una etiqueta naranja y un aviso con el error medido frente al de 5 m (120 puntos reales): el horizonte difiere **0,68° (RMS) y hasta 5,8°**, siempre con tendencia a quedar **más bajo** (sesgo −0,25°: optimista, sobreestima la luz); la fracción de Sol cambia ±4 puntos y la de Tierra ±4 puntos (percentil 95); y el **veredicto por puertas no terrenales cambia en el 10 % de los puntos**. En crestas, cimas y bordes de cráter el error es mayor. Además, el score es **parcial**: sin pendiente de aterrizaje, con confianza baja y sin rango, y el veredicto es SIN DATOS o NO APTO provisional, **nunca APTO**. Sirve para comparar zonas del polo entre sí; no para decidir un aterrizaje. No lo compares con un sitio de 5 m.

## Cómo leer los resultados

| Término | Qué significa |
|---|---|
| **f_sol** | Fracción de tiempo con *alguna parte* del Sol sobre el horizonte. |
| **f_Tierra** (Tierra visible) | Fracción de tiempo con al menos la mitad del disco terrestre visible. Geometría, no enlace. |
| **Enlace posible** | Fracción de tiempo con la Tierra visible con el margen de antena **y** una estación de la red viendo la Luna. Geometría y cobertura; **no** presupuesto de enlace RF ni garantía. |
| **Hueco máximo sin enlace** | El tramo seguido más largo sin enlace posible. Se compara con el hueco que tolera el perfil (G7: 48 h lander sin RHU, 96 h con RHU, 24 h rover, 12 h base; suposiciones). «≥ X» = toca el borde. |
| **Horas de contacto por día** | Media: 24 × enlace posible. Mínima: el día UTC completo con menos horas. |
| **Margen de antena** | Cuánto más alta que el horizonte debe verse la Tierra desde el lander (0° por defecto; la sensibilidad usa 3° y 5°). |
| **Hora local civil / hora solar local media** | Civil: el reloj de la estación con su horario de verano (PST, CET, AEDT). Solar media: UTC + longitud/15, sin ecuación del tiempo. |
| **Oscuridad máxima** | Noche continua más larga (sin Sol por el relieve; sin eclipses). «≥ X» = la ventana toca el borde del periodo y el valor es una cota inferior. |
| **Veredicto** | APTO / CONDICIONAL / NO APTO / SIN DATOS, decidido por puertas y escenarios, no por la nota. «Apto» no es «seguro». |
| **Score** | 0–100, resume y ordena; se muestra con rango y desglose. Pesos y umbrales sin calibrar. «Rango no calculado» = no se pidió la incertidumbre; un rango estrecho en puntos saturados es normal. |
| **Inicios aptos** | Cuántas fechas de inicio del año superan todas las puertas: poca cifra = ventana frágil. |
| **Confianza** | Alta / media / baja según huecos del DEM, error vertical e inestabilidad del horizonte. «Alta» no significa 5 m: significa resolución efectiva ≈ 30 m. |
| **% de potencia** | Relativa a la potencia nominal del propio panel, bajo supuestos declarados; puede superar 100 % por perihelio y frío. |

## Para un educador

Objetivo: que el alumnado entienda por qué en el polo sur lunar manda el relieve.

1. Modo **Público**. Abre **Horizonte y visibilidad** con el punto por defecto (Mons Malapert).
2. Pide predecir antes de mirar: ¿se ve la Tierra? ¿cuándo se pone el Sol? Arrastra el cursor o activa la animación.
3. Pasa a **Línea temporal** con «Día lunar (≈ 29,5 d)»: se ve la alternancia de Sol y noche.
4. En **Potencia y paneles** compara «Horizontal» con «Vertical con seguimiento»: el Sol queda a pocos grados del horizonte, así que un panel plano apenas recibe luz.
5. Abre **Capacidad del sitio** y pide que comparen «Tierra visible» con «ENLACE POSIBLE»: la Tierra puede verse y, aun así, no haber ninguna antena terrestre que vea la Luna a esa hora. Mira la tabla de bases terrestres con su hora local.
6. Cierra con **Acerca de y límites**: qué se modela y qué no. Insiste en que ver el Sol no garantiza energía y ver la Tierra o tener enlace posible no garantiza comunicación.

## Para un planificador de misión

Objetivo: elegir dónde y cuándo mirar más de cerca.

Si aún no sabes dónde mirar, empieza por el **Mapa del polo sur**: sitúa el rasgo, mira las PSR y la iluminación publicada y elige un punto (en modo de 80 m el resultado es solo orientativo).

1. Modo **Planificador**. **Mejores puntos y fechas**: sitio, perfil (lander sin RHU o rover) y duración (7, 14 o 30 d). Anota los TOP, su mejor fecha y los «inicios aptos».
2. «Evaluar este punto y fecha». En **Horizonte y visibilidad** comprueba el horizonte y la cuenta atrás hasta *sunset* y *Earthset*: ¿cabe tu misión antes de la puesta?
3. **Línea temporal** → «Comparar fechas»: retrasa el inicio y mira cómo cambian Sol, Tierra y oscuridad. Una ventana que solo funciona unos días es frágil.
4. **Comparación de sitios**: pon dos o tres puntos candidatos bajo el mismo periodo y perfil (por defecto se comparan los mejores candidatos de cada sitio, no sus puntos por defecto). Fíjate en el veredicto por puertas, la confianza y los rangos.
5. **Score del sitio**: ajusta los pesos a tu misión y comprueba qué cambia la conclusión («¿Qué cambiaría el resultado?»).
6. En **Capacidad del sitio** mira el hueco máximo sin enlace frente a lo que tolera tu perfil, la sensibilidad al margen de antena (0°/3°/5°) y, si vas a comandar el lander, cambia el sentido a «transmisión» o «ambos» en la barra lateral.
7. Exporta CSV/JSON (o la ficha del sitio) para tu análisis.
8. Recuerda: el mapa de mejores puntos es grueso (malla de 250 m); confirma siempre en el modelo detallado. Es una ayuda para priorizar, no una selección de sitio.

## Para un ingeniero

Objetivo: auditar el cálculo y dimensionar con supuestos explícitos.

1. Modo **Experto**. Revisa en **Explorador 3D** los metadatos del DEM (CRS, límites, `toterr`; la capa «Iluminación» da la sombra del relieve a la hora que elijas) y en **Horizonte y visibilidad** el «Horizonte exacto por azimut», `H_lb`/`H_ub` y los sectores limitados por cobertura.
2. En el panel «Avanzado» activa **incertidumbre** para ver el rango y la «zona de duda» en la línea temporal. Prueba el paso de la serie (5–60 min) y «ignorar el DEM» para ver cuánto aporta el relieve.
3. **Potencia y paneles**: elige el panel, el montaje (inclinación, azimut de la normal), degradación y polvo de sensibilidad; mira la temperatura del panel y los avisos (`IAM_GRAZING_UNCERTAIN`, `COLD_EXTRAPOLATION`, `PANEL_UNVERIFIED`). Los 3 paneles experimentales sin datasheet (silicio, CIGS, perovskita-silicio) salen etiquetados y con banda de incertidumbre; si faltara un parámetro sin estimación, la app lo dice en vez de mostrar un 0.
4. **Score del sitio**: tabla `indicador | valor | s_i | peso | penalización`, puertas con valor, límite y margen, y confianza con g90, e90 y σh90 (fórmulas en [metodología](metodologia.md)).
5. Reproduce o amplía el mapa de idoneidad con `python scripts/precompute_suitability.py --help` y contrástalo con el modelo fino con `--validate`.
6. Enlace: `AnalysisRequest(link_network="DSN", link_direction="receive", min_earth_elevation_deg=None)` (`link_network=None` = solo geometría). Para ver las ventanas reales de cada estación en un día usa `ground_stations.daily_contact_table(result.link.contacts, t0, t1)`; no las reconstruyas a mano (partir por día UTC fabrica ventanas inexistentes). Revisa también `docs/validation/revision-enlace.md` y `metodologia.md` §9.
7. Núcleo sin UI: `from lsi import pipeline; pipeline.run_analysis(ctx, AnalysisRequest(...))` (ver `tests/test_pipeline.py`).

## Cuando algo no sale

| Síntoma | Causa y solución |
|---|---|
| La app muestra el comando `python scripts/fetch_data.py` | Faltan kernels o datos. Ejecútalo y relanza. |
| «Mejores puntos y fechas» pide un comando | Falta el precálculo: `python scripts/precompute_suitability.py ...` (README). |
| Un rasgo del buscador no se evalúa con DEM | Está a más de 10 km de cualquier DEM de 5 m: se usa esfera lisa con aviso; el score es parcial y optimista. |
| Error de fecha | Fuera de 1900–2050. |
| «Capacidad del sitio»: «Enlace posible: no calculado» | La red está en «Solo geometría». Elige DSN u otra red en la barra lateral (modo Planificador). |
| «No hay enlace posible en todo el periodo» | O la Tierra no se ve, o nunca coincide con una estación que vea la Luna con ese margen. Alarga el periodo, cambia la red o baja el margen de antena. |
| Veredicto SIN DATOS con un periodo igual a la misión | El periodo analizado debe ser **más largo** que la duración de la misión para que haya una ventana completa que puntuar. En un caso medido (de Gerlache, inicio 2027-06-21, periodo y misión de 14 d) con 14 d sale SIN DATOS y con 15 d, APTO: alarga el periodo un día. |
| «Observador cerca del borde del DEM» | Elige un punto más hacia el interior del recorte. |
| Un panel dice «no calculable» o «sin dato» | Falta un parámetro (p. ej. la eficiencia para dar W/m²) sin estimación en el catálogo; elige otro panel. Un panel experimental sí se calcula, con etiqueta y banda. |
| El «Mapa del polo sur» dice que una capa está oculta | Faltan los ficheros de PSR, Diviner o iluminación publicada: `python scripts/fetch_thermal_psr.py` (o `--only psr`, `--only diviner`, `--only illum_ref`). El relieve necesita el DEM de 80 m: `python scripts/fetch_data.py`. |
| El Explorador no muestra foto | Es normal en `main`: la foto está en el visor 3D de la rama `feat/lunaris-ui`. Solo hace falta descargarla para esa rama: `python scripts/fetch_sdem.py --yes` (Malapert, de Gerlache) y `python scripts/fetch_imagery.py --sites Site04 Site11 Site23 --yes` (LROC NAC). En de Gerlache el observador por defecto cae en sombra permanente (sin foto iluminada); en Site04 no hay SDEM. |
| Quieres el visor 3D con foto, Sol y Tierra reales o la marca LUNARIS | Están en la rama `feat/lunaris-ui`, no en `main` (README, «Ramas»). |
| Un punto del polo sale «NO APTO» o «SIN DATOS» con Sol 0 % | Mira el mapa: si es el suelo de un cráter, es una PSR y es lo esperado. Un resultado en modo de 80 m nunca es APTO (score parcial). |
