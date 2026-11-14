# Lunar Site Intelligence (LSI)

> Compara emplazamientos del polo sur lunar y fechas de misión: horizonte real del terreno, Sol y Tierra sobre él, capacidad solar (W/m² y Wh/m² por día), enlace posible con las estaciones de la Tierra y un veredicto explicable. Proyecto para el reto NASA Space Apps 2026 *Lunar Landing Site Navigator*.

**Aviso de alcance.** LSI es una herramienta de apoyo para comparar y entender, no un sistema certificado de selección de sitio. Calcula **visibilidad geométrica** (terreno + curvatura + efemérides SPICE). Ver el Sol o la Tierra **no garantiza potencia ni enlace de radio**, y el «enlace posible» es geometría más cobertura de estación, no un presupuesto de enlace RF. Véase [`docs/limitaciones.md`](docs/limitaciones.md).

## El problema y la solución

Un planificador de misión, un educador o una persona curiosa quieren saber, para un punto concreto del polo sur lunar y unas fechas concretas: ¿se ve el Sol?, ¿se ve la Tierra?, ¿durante cuánto tiempo?, ¿cuánto falta para la puesta de Sol o el *Earthset*?, ¿cuánta energía daría un panel?, ¿y habría alguna antena terrestre que pudiera hablar con el lander, con qué huecos? En el polo el Sol da la vuelta casi pegado al horizonte (el eje lunar está inclinado ~1,54° respecto a la eclíptica, `docs/science/paneles-y-misiones.md` §3.1), así que **cualquier relieve manda** y la respuesta cambia metros más allá y días después.

LSI responde combinando:

1. **Topografía real**: DEM LOLA de 5 m de tres zonas (Shackleton, de Gerlache, Mons Malapert) completado con el DEM polar LOLA de 80 m como campo lejano.
2. **Efemérides reales**: SPICE (NAIF) con el marco lunar `MOON_ME` y aberración `LT+S`, contrastado con JPL Horizons (diferencia máxima 0,05″, [`docs/science/luna-spice-sitios.md`](docs/science/luna-spice-sitios.md) §2).
3. **Horizonte con curvatura**, disco finito del Sol y la Tierra, ventanas refinadas al segundo.
4. **Modelo de potencia** por tipo de panel y montaje (relativa al panel y, con su potencia nominal por área, en W/m² y Wh/m² por día), con 8 paneles en dos grupos: 5 respaldados por datasheet o paper y 3 experimentales sin datasheet.
5. **Enlace posible con la Tierra**: la Tierra se ve sobre el horizonte con un margen de antena **y** alguna estación de la red DSN (DSS-14, DSS-63, DSS-43, coordenadas de DSN 810-005) ve la Luna por encima de su elevación mínima (6° para recibir, 10,1° para transmitir). Con horas de contacto por día, hueco máximo sin enlace y hora local de cada estación.
6. Un **score por ventana de misión** ligado al panel y al montaje elegidos, con puertas (G0–G7, incluidas la de potencia útil G5 y la del hueco máximo sin enlace G7), veredicto (APTO / CONDICIONAL / NO APTO / SIN DATOS), rango (o «no calculado» si no se pidió la incertidumbre) y confianza de los datos.

## Qué hace (10 pantallas)

La app Streamlit tiene tres modos (**Público**, **Planificador**, **Experto**; selector en la barra lateral) y diez pantallas (`ui/__init__.py`, `PAGE_SPECS`):

| # | Pantalla | Qué ofrece |
|---|---|---|
| 1 | **Buscador** | Busca por nombre (difuso, sin acentos) entre **9106 lugares**: 9087 rasgos del gazetteer USGS/IAU (`data/processed/gazetteer.parquet`) más 19 sitios de misión con coordenadas de `config/sites.json` (Apolo 11–17, Chang'e 3–6, Chandrayaan-3, Luna-25, SLIM, IM-1, IM-2, Blue Ghost M1 y los tres recortes con DEM), con 56 alias es/en en `config/aliases.json`. «Evaluar este lugar» lleva el lugar al análisis. Si el centro cae fuera del DEM de 5 m, se evalúa el **mejor punto del mapa de idoneidad limitado al entorno del rasgo** (p. ej. Shackleton: a ~0,34 km dentro de su borde; de Gerlache: en su margen, 0,20 km fuera) y se avisa; si no hay mapa, el punto cubierto más cercano; si no hay DEM a ≤ 10 km, esfera lisa con aviso. |
| 2 | **Capacidad del sitio** | La segunda pantalla, tras el buscador: «según la ubicación, qué energía solar y qué conectividad tendría un lander». **Solar**: Sol visible, noche máxima, ventana solar más larga y, para el panel y el montaje elegidos, **potencia en W/m²** (media y pico) y **energía en Wh/m² por día** (media y mínima). **Conectividad**: **Tierra visible (geometría) frente a ENLACE POSIBLE**, **horas de contacto por día**, ventana de enlace más larga y **hueco máximo sin enlace** frente al que tolera el perfil (puerta G7), con su fecha y la estación que recupera el enlace. En detalle: **sensibilidad al margen de antena (0°, 3°, 5°)**, **tabla de bases terrestres** (% de tiempo con enlace, horas por día, elevación mínima con su procedencia, contacto más largo en UTC, **hora local civil** con su zona y hora solar local media), los contactos de un día elegido, un gráfico de contactos y una ficha descargable (JSON, CSV). El **sentido del enlace** (recepción 6° / transmisión 10,1° / ambos), la red (DSN, ESTRACK, DSN+ESTRACK, personalizada, solo geometría) y el margen se eligen en la barra lateral. |
| 3 | **Explorador 3D** | Superficie 3D y mapa polar del DEM (elevación, pendiente, incertidumbre vertical, muestreo), metadatos y CRS. |
| 4 | **Mejores puntos y fechas** | Mapa de los mejores puntos de cada zona por perfil (lander solar sin RHU, rover) y duración de misión (7, 14, 30 d), con **mejor fecha de inicio** (que respeta G7), score con rango, veredicto por puertas y calendario del año. El mapa usa el enlace de la red DSN, no la Tierra geométrica. Necesita el precálculo (ver más abajo). |
| 5 | **Horizonte y visibilidad** | Perfil de horizonte 360°, Sol y Tierra en azimut/elevación con su disco, cursor temporal con animación y **cuenta atrás** hasta puesta/salida de Sol y de la Tierra (*sunset*/*Earthset*). |
| 6 | **Línea temporal** | Bandas de Sol, Tierra, solape y oscuridad; zona de duda por incertidumbre del horizonte; comparar dos fechas; año y estaciones; tabla diaria; exportación CSV/JSON. |
| 7 | **Comparación de sitios** | Hasta 5 sitios o puntos lado a lado, métricas separadas, veredicto por puertas, horizontes superpuestos y score ponderado opcional. |
| 8 | **Potencia y paneles** | 8 tipos de panel del catálogo `config/panels.json`; **% de la potencia nominal** por montaje (horizontal, inclinado, vertical fijo, vertical con seguimiento azimutal), energía diaria, batería opcional. Los 8 paneles son calculables: **5 respaldados** (GaAs 3J en tres versiones, 4J, ROSA) y **3 experimentales sin datasheet** (silicio, CIGS, perovskita-silicio; siempre etiquetados, con banda de incertidumbre). En el polo el montaje por defecto es vertical con seguimiento. |
| 9 | **Score del sitio** | Perfil de misión, pesos editables, desglose por indicador, puertas con motivo (G5 con el panel elegido, G7 con el hueco de comunicaciones), confianza de los datos y sensibilidad. El score cambia con el panel, el montaje y la continuidad del enlace. |
| 10 | **Acerca de y límites** | Alcance, fuentes, convenciones, avisos científicos, estado de validación, créditos. |

Funciones destacadas: **capacidad del sitio** (energía solar y enlace posible en una sola pantalla), **score de idoneidad por ventana de misión** (se evalúa de la fecha de inicio a inicio + duración, no un año entero), **veredicto y mejores fechas**, **paneles solares con % de potencia y W/m² por montaje** y **mapa de mejores puntos**.

> Capturas: [`docs/capturas/`](docs/capturas/) contiene 31 JPG (30 numerados `01`–`30` del QA visual más `explorer-3d-corregido.jpg`, ≈ 2,4 MB) de la app real en los modos Público, Planificador y Experto, incluida la vista móvil de 390 px. Son del QA del 14/11/2026 y **no incluyen la pantalla «Capacidad del sitio»**; si cambia la interfaz, pueden quedar desfasadas.

## Instalación (Windows, Python 3.11)

Requisitos: Python 3.11 y unos 1,2 GB libres (datos + cachés).

```powershell
cd lunar-site-intelligence
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Dependencias fijadas en `requirements.txt` (numpy 2.4.2, scipy, pandas, pyarrow, rasterio, pyproj, spiceypy 8.4.0, plotly, pydeck, streamlit 1.58.0, requests, pyshp, tzdata para las horas locales de las estaciones, pytest). Si `rasterio` no instala en tu equipo, usa Python 3.11 de 64 bits.

## Obtener los datos

`data/raw/`, `data/processed/` y `kernels/*` **no van al repositorio** (`.gitignore`); se reproducen con estos comandos, en este orden. Son idempotentes: lo ya descargado se omite.

| Comando | Qué hace | Descarga aproximada |
|---|---|---|
| `python scripts/fetch_data.py` | DEM LOLA 5 m de 3 sitios (4 capas cada uno: `surf`, `slp`, `ldec`, `toterr`), LOLA polar 80 m y los 6 kernels SPICE. Sin opciones: no tiene `--help`, ejecutarlo con cualquier argumento descarga. | Shackleton 157 MB, de Gerlache 157 MB, Mons Malapert 270 MB, LOLA 80 m 181 MB, kernels 18 MB: **≈ 0,8 GB** |
| `python scripts/fetch_gazetteer.py` | Baja el zip del gazetteer USGS, lo extrae en `data/raw/gazetteer/dl_*/` y escribe `data/processed/gazetteer.{csv,parquet}` (9087 rasgos; el buscador añade en memoria los 19 sitios de misión). Sin `--help`: cualquier argumento lo ejecuta. Falla con mensaje claro si el formato cambia. | zip 24 MB (≈ 46 MB extraído) |
| `python scripts/precompute_horizons.py` | Precalcula los horizontes por defecto (3 sitios × alturas de 1, 2 y 5 m) en `data/processed/horizons/`. Idempotente. | ≈ 7 MB de caché |
| `python scripts/precompute_suitability.py --profile lander_solar_no_rhu --profile rover --duration 7 --duration 14 --duration 30` | Mapas de idoneidad con ventanas de misión para la pantalla «Mejores puntos y fechas» (malla de 250 m, horizonte cada 1°, serie cada 30 min). `--help` documenta todas las opciones. Con `--validate 12` compara 12 nodos con el modelo fino. | ≈ 240 MB de caché en `data/processed/suitability/`; los JSON de ventanas indican 20–34 s por sitio y perfil en la máquina de desarrollo |

Sin el precálculo de idoneidad la app funciona, salvo la pantalla «Mejores puntos y fechas», que muestra el comando necesario. El precálculo usa por defecto el enlace DSN en recepción con margen 0°; `--link-network`, `--link-direction`, `--min-earth-elevation` y `--station-min-elevation` lo cambian (y exigen regenerar).

**Solo para las pruebas de validación independiente del enlace** (`tests/test_independent_link.py`, se omiten sin ellos; `fetch_data.py` no los descarga): los dos PCK binarios de orientación de la Tierra de NAIF (ITRF93, 5,2 + 19,2 MB) en `data/raw/earth/`, con `curl -o data/raw/earth/earth_latest_high_prec.bpc https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_latest_high_prec.bpc` y lo mismo para `earth_2026_260806_2126_predict.bpc`. `scripts/fetch_horizons_stations.py` **no tiene `--help`**: ejecutarlo con cualquier argumento llama a JPL Horizons y reescribe `tests/golden/horizons_stations_2026-12.json`.

## Ejecución

```powershell
python -m streamlit run app.py
```

El tema oscuro está en `.streamlit/config.toml`. Si faltan los kernels, la app muestra el comando `python scripts/fetch_data.py` en lugar de fallar.

## Pruebas

```powershell
python -m pytest -q
```

Hay **46 ficheros** `tests/test_*.py` y 590 funciones `def test_`; `python -m pytest --collect-only -q` recoge **849 casos**, incluidos los 26 de `tests/test_independent_visibility.py` y los 37 de `tests/test_independent_link.py`. Última ejecución completa (14/11/2026, `python -m pytest -q`, 5 min): **811 passed, 38 skipped**; los 38 se omiten por falta del DEM Site01. Marcadores declarados en `pytest.ini`: `slow` (116 casos: año completo, rendimiento, UI completa, dorados), `perf` (5 casos: presupuestos de rendimiento de arquitectura §10; `python -m pytest -q -m perf -s` imprime tiempos), `needs_spice` y `needs_dem` (omiten la prueba si faltan kernels o DEM). `python -m pytest -q -m "not slow"` da una pasada rápida. Las pruebas contra la literatura de `tests/test_luna_cases.py` necesitan además el DEM Site01 y la variable `LSI_SITE01_DIR` (ver [`docs/validation/validacion-luna.md`](docs/validation/validacion-luna.md) §6); sin él se omiten.

## Estructura del repositorio

```
app.py                  punto de entrada de Streamlit
ui/                     interfaz (solo ui/ y app.py importan streamlit)
  pages/                las 10 pantallas
src/lsi/                núcleo científico determinista, sin UI
  data/                 loader DEM, catálogo, caché por hash, gazetteer
  terrain/              muestreo, horizonte, pendiente, rugosidad
  astronomy/            coordenadas (proyección, ENU), motor SPICE y estaciones terrestres (ground_stations)
  simulation/           visibilidad (disco finito), línea temporal, incertidumbre
  energy/               modelo de potencia de paneles
  analysis/             métricas, score, confianza, mapa de idoneidad, exportación
  visualization/        figuras Plotly
  pipeline.py           orquestación (run_analysis)
config/                 simulation.json, panels.json, ground_stations.json, sites.json, aliases.json
scripts/                fetch_data, fetch_gazetteer, fetch_horizons_stations, precompute_horizons, precompute_suitability
kernels/                kernels SPICE (no versionados; ver kernels/README.md)
data/raw, data/processed  datos y cachés (no versionados)
tests/                  pytest
docs/                   documentación (ver abajo)
```

Documentación: [`docs/metodologia.md`](docs/metodologia.md) · [`docs/fuentes-datos.md`](docs/fuentes-datos.md) · [`docs/limitaciones.md`](docs/limitaciones.md) · [`docs/guia-usuario.md`](docs/guia-usuario.md) · [`docs/guion-demo.md`](docs/guion-demo.md) · [`kernels/README.md`](kernels/README.md). Fuentes de diseño: `docs/plan/`, `docs/science/`, `docs/validation/`.

## Fuentes de datos

| Fuente | URL | Uso |
|---|---|---|
| LOLA / PGDA, producto 78 (DEM 5 m de los sitios) | https://pgda.gsfc.nasa.gov/products/78 · datos en https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/ | Site04 Shackleton, Site11 de Gerlache, Site23 Mons Malapert |
| LOLA polar 80 m (PGDA producto 90) | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF | Campo lejano |
| NAIF SPICE, kernels genéricos | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/ | Efemérides y marco lunar (detalle en `kernels/README.md`) |
| USGS Gazetteer of Planetary Nomenclature (IAU WGSN) | https://planetarynames.wr.usgs.gov/ · zip `https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.zip` | Buscador |
| DSN 810-005, módulo 301 Rev. P (22/05/2026) | https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf | Posición WGS 84 (Tabla 5) y elevación mínima de recepción (6,0°) y de transmisión (10,1°) de DSS-14, DSS-63 y DSS-43 |
| NAIF, FK de estaciones NDOSL (ESTRACK) y PCK de la Tierra (ITRF93) | https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/ndosl_190716_v02.tf · https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/ | Posición de New Norcia, Cebreros y Malargüe (elevación mínima SUPUESTA); los PCK solo validan |
| Datasheets y papers de paneles | Registro con fuente y página en [`docs/validation/datos-paneles.md`](docs/validation/datos-paneles.md) | η, γ_T y W/m² de los 8 paneles |
| JPL Horizons | https://ssd.jpl.nasa.gov/horizons/ | Solo contraste (no se descarga en la app) |

Tamaños, hashes y condiciones de uso en [`docs/fuentes-datos.md`](docs/fuentes-datos.md).

## Validación: qué se contrastó y con qué resultado

- **Efemérides frente a JPL Horizons**: 24 casos (3 lugares × 4 fechas × Sol/Tierra). Diferencia máxima **0,05″ en elevación y 0,04″ en azimut** (hasta 0,39″ con el cuerpo a más de 80° de elevación, donde el azimut se degenera). Horizons usa DE441 y LSI DE421; el residuo se atribuye a eso (no comprobado por separado). `docs/science/luna-spice-sitios.md` §2.
- **Comprobación independiente 3D** (`tests/test_independent_visibility.py`, 26 pruebas): una formulación cartesiana 3D sin la geometría del motor, sobre 6 puntos y 3 ventanas de 30 días (38 907 instantes). **0 contradicciones duras**; perfil de horizonte con diferencia RMS de 0,007°–0,023° y máxima de 0,13° (el motor queda por debajo, optimista; causa: discretización radial de 5 m, no error de marco); fracción de tiempo por rejilla frente a métrica del motor ≤ 0,0006. No valida los datos LOLA, solo la matemática que los usa. `docs/validation/revision-matematica.md`.
- **Enlace y estaciones** (`docs/validation/revision-enlace.md`, `tests/test_independent_link.py`: 37 pruebas, 37 passed el 14/11/2026): la Luna vista desde DSS-14/-63/-43 frente a Horizons difiere **0,0002–0,0007°** con una cadena independiente en ITRF93 y **0,072°** con la rotación simplificada del motor (`IAU_EARTH`); cobertura DSN de dic-2026 **99,929 %** en recepción (6°) y **97,992 %** en transmisión (10,1°); enlace posible por fuerza bruta 3D en 9 casos con |Δ link_fraction| ≤ **8e-4**; horas locales y horario de verano de 2027 con reglas escritas a mano, acuerdo total. Detalle en [`docs/metodologia.md`](docs/metodologia.md) §9.
- **Literatura** (`docs/validation/validacion-luna.md`): con las definiciones de cada artículo, el motor reproduce lo publicado de la Connecting Ridge:
  - Barker et al. (2021), 7 regiones, 2024-26, z = 5 m: iluminación media 88,4–94,3 % frente a percentil 1 de 82,8–89,3 %; LCIP (periodo más largo con Sol) 233–265 d (RoI 1–6) y 146 d (RoI 7) frente a 216–231 d y 119 d; LCSP (noche más larga) 3,5–6,1 d frente a 4,0–8,4 d.
  - Gläser et al. (2014), 19 años a 2 m: 92,1 % y 94,1 % del tiempo iluminado frente a 92,27 %; noche más larga 5,06 y 4,89 d frente a «típicamente 3-5 d».
  - Mazarico et al. (2011): «~240 d continuos y ~1,5 d de noche máxima» es coherente con LSI **solo si** esa cifra corresponde a una altura de decenas de metros (a 10 m: noche 1,3–1,8 d); la altura de su cifra **a verificar** en el artículo completo.
- **No hay cifras publicadas** para Site 4, 11 y 23 con las que contrastar (Barker 2021 solo da Site 1) ni para la visibilidad de la Tierra en los sitios. Quedan **a verificar**.
- **Mapa de idoneidad frente al modelo fino** (`--validate 12`, perfil lander, año completo): diferencia máxima de f_sol 0,0098, de f_Tierra 0,0039 y de score 0,44 puntos; la oscuridad máxima difiere hasta 2,3 h (Site04), 2,7 h (Site11) y 50,2 h (Site23, en un nodo con noches de decenas a cientos de horas; el nodo concreto no se ha analizado). JSON `data/processed/suitability/Site*_lander_solar_no_rhu_*.json` (bloque `validation`).

## Estado y reservas

Estado a 14/11/2026, verificado ejecutando el motor y las pruebas (no copiado de informes).

- **Validado:** geometría Sol/Tierra frente a JPL Horizons (24 casos, ≤ 0,05″); matemática del horizonte y la visibilidad frente a una formulación 3D independiente (26 pruebas); enlace y estaciones frente a una cadena independiente y Horizons (37 pruebas); 811 pruebas pasan y 38 se omiten por falta del DEM Site01; en entorno limpio la app arranca y las pantallas pasan las pruebas de humo (`docs/validation/puerta-final.md`).
- **Es estimación:** la potencia por panel (3 de 8 paneles experimentales sin datasheet, con banda de incertidumbre; los 5 respaldados lo son por su celda de referencia, y W/m² es de celda, sin empaquetado); el enlace posible (geometría y cobertura, con márgenes de antena y umbrales de huecos G7 supuestos); el score y el veredicto (pesos, umbrales y puertas son convenciones de LSI sin calibrar); la resolución efectiva (~30 m); el mapa de idoneidad (malla gruesa de 250 m). El rango de incertidumbre puede tener ancho cero en puntos saturados. **«APTO» no certifica nada**, y visibilidad geométrica no es potencia ni enlace garantizados.
- **Falta o está a verificar:** contraste con la literatura para Shackleton, de Gerlache y Malapert (solo hay cifras publicadas para Site 1, cuyo DEM no está en este equipo); elevación mínima de ESTRACK (supuesta, 6°); estaciones de la red NSN de NASA (no incluidas: no se pudieron verificar); máscara de terreno y ocupación de las antenas del DSN, y transmisión de alta potencia (13,6°); `--validate 12` del mapa de idoneidad con la versión actual del mapa (enlace); licencias de datos de PGDA 78/90, de la nomenclatura IAU y de JPL Horizons (la política general de NASA y USGS sí está verificada, ver `docs/fuentes-datos.md`); licencia del código (la decide el usuario); descarga con verificación de hash; repetir las descargas desde cero con solo este README; regrabar el vídeo de demo reconfirmando las cifras de `docs/guion-demo.md`. No hay repositorio remoto ni commits.

## Limitaciones (resumen)

- **Visibilidad geométrica ≠ potencia ≠ enlace RF.** «Enlace posible» = Tierra visible con margen de antena + cobertura de estación (DSN), **no** un presupuesto de enlace: sin potencia, frecuencia, ganancia ni ruido, y por defecto solo recepción a 6°. Sin estaciones NSN; ESTRACK con elevación supuesta.
- **Resolución efectiva ≈ 30 m**, no 5 m: ~90 % de los píxeles del DEM no tiene retorno LOLA propio. Rocas y cráteres menores de ~150 m no se evalúan.
- **Un punto no es una zona.** Resultado para un punto y una altura (2 m por defecto).
- **Potencia = estimación relativa** (W/m² de celda, sin empaquetado) con supuestos declarados; 3 de los 8 paneles son experimentales sin datasheet (etiquetados) y otros parámetros siguen «a verificar». Sin polvo, albedo ni sombra propia; sin eclipses de la Tierra sobre el Sol.
- **Score sin calibrar**: pesos y umbrales son convenciones de LSI pendientes de un experto de misión. «Apto» no significa «seguro» ni «aterrizable». Aunque el score depende del panel y el montaje elegidos, sigue sin ser un predictor validado.
- **El DEM de 5 m cubre 16×16 km (Shackleton, de Gerlache) y 21×21 km (Malapert)**; más allá se usa el DEM de 80 m (estimación, no dato de 5 m).
- Rango temporal 1900-2050 (cobertura del kernel de orientación lunar).

Detalle completo: [`docs/limitaciones.md`](docs/limitaciones.md).

## Créditos y referencias

Datos y herramientas: NASA (LOLA/LRO, PGDA, NAIF/SPICE, JPL Horizons, Space Apps), USGS Astrogeology (Gazetteer, IAU WGSN). LSI no está afiliado ni respaldado por estas instituciones. Se agradece el uso de SPICE y de los recursos NAIF, como solicita NAIF.

Referencias científicas (las marcadas «leída» se leyeron en fuente durante la validación; el resto, **a verificar** antes de citar):

- Mazarico, E. et al. (2011). *Illumination conditions of the lunar polar regions using LOLA topography*. Icarus 211, 1066-1081. doi:10.1016/j.icarus.2010.10.030 (resumen leído: https://ntrs.nasa.gov/citations/20120010094).
- Barker, M.K. et al. (2021). *Improved LOLA elevation maps for south pole landing sites: error estimates and their impact on illumination conditions*. Planetary and Space Science 203, 105119. doi:10.1016/j.pss.2020.105119 (texto completo leído).
- Gläser, P. et al. (2014). Icarus 243, 78-90. doi:10.1016/j.icarus.2014.08.013 (resumen leído: https://elib.dlr.de/94240/).
- Mazarico, E., Barker, M.K., Nicholas, J.B. (2018). Advances in Space Research (IllumNG). https://pmc.ncbi.nlm.nih.gov/articles/PMC6398960 (leída).
- Documento base: *Arquitectura y Plan v1.0* (13/11/2026), `docs/documento-base.pdf`. Reto: `docs/reto-nasa.md`.

Cómo citar: «Lunar Site Intelligence (LSI), 2026. Equipo LSI, NASA Space Apps Challenge 2026, *Lunar Landing Site Navigator*.»

**Licencia del código: pendiente de decidir por el equipo** (no hay fichero `LICENSE` en el repositorio).
