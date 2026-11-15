# Lunar Site Intelligence (LSI)

> Compara emplazamientos del polo sur lunar y fechas de misión: horizonte real del terreno, Sol y Tierra sobre él, capacidad solar (W/m² y Wh/m² por día), enlace posible con las estaciones de la Tierra y un veredicto explicable. Proyecto para el reto NASA Space Apps 2026 *Lunar Landing Site Navigator*.

**Aviso de alcance.** LSI es una herramienta de apoyo para comparar y entender, no un sistema certificado de selección de sitio. Calcula **visibilidad geométrica** (terreno + curvatura + efemérides SPICE). Ver el Sol o la Tierra **no garantiza potencia ni enlace de radio**, y el «enlace posible» es geometría más cobertura de estación, no un presupuesto de enlace RF. Véase [`docs/limitaciones.md`](docs/limitaciones.md).

## El problema y la solución

Un planificador de misión, un educador o una persona curiosa quieren saber, para un punto concreto del polo sur lunar y unas fechas concretas: ¿se ve el Sol?, ¿se ve la Tierra?, ¿durante cuánto tiempo?, ¿cuánto falta para la puesta de Sol o el *Earthset*?, ¿cuánta energía daría un panel?, ¿y habría alguna antena terrestre que pudiera hablar con el lander, con qué huecos? En el polo el Sol da la vuelta casi pegado al horizonte (el eje lunar está inclinado ~1,54° respecto a la eclíptica, `docs/science/paneles-y-misiones.md` §3.1), así que **cualquier relieve manda** y la respuesta cambia metros más allá y días después.

LSI responde combinando:

1. **Topografía real**: DEM LOLA de 5 m de tres zonas (Shackleton, de Gerlache, Mons Malapert) completado con el DEM polar LOLA de 80 m como campo lejano y, **fuera de esos recortes y hasta 80°S**, como relieve aproximado de 80 m (modo `FAR_FIELD`, con su error medido: ver «Estado y reservas»).
2. **Efemérides reales**: SPICE (NAIF) con el marco lunar `MOON_ME` y aberración `LT+S`, contrastado con JPL Horizons (diferencia máxima 0,05″, [`docs/science/luna-spice-sitios.md`](docs/science/luna-spice-sitios.md) §2).
3. **Horizonte con curvatura**, disco finito del Sol y la Tierra, ventanas refinadas al segundo.
4. **Modelo de potencia** por tipo de panel y montaje (relativa al panel y, con su potencia nominal por área, en W/m² y Wh/m² por día), con 8 paneles en dos grupos: 5 respaldados por datasheet o paper y 3 experimentales sin datasheet.
5. **Enlace posible con la Tierra**: la Tierra se ve sobre el horizonte con un margen de antena **y** alguna estación de la red DSN (DSS-14, DSS-63, DSS-43, coordenadas de DSN 810-005) ve la Luna por encima de su elevación mínima (6° para recibir, 10,1° para transmitir). Con horas de contacto por día, hueco máximo sin enlace y hora local de cada estación.
6. Un **score por ventana de misión** ligado al panel y al montaje elegidos, con puertas (G0–G7, incluidas la de potencia útil G5 y la del hueco máximo sin enlace G7), veredicto (APTO / CONDICIONAL / NO APTO / SIN DATOS), rango (o «no calculado» si no se pidió la incertidumbre) y confianza de los datos.

## Qué hace (11 pantallas)

La app Streamlit tiene tres modos (**Público**, **Planificador**, **Experto**; selector en la barra lateral) y once pantallas (`ui/__init__.py`, `PAGE_SPECS`):

| # | Pantalla | Qué ofrece |
|---|---|---|
| 1 | **Buscador** | Busca por nombre (difuso, sin acentos) entre **9119 lugares**: 9087 rasgos del gazetteer USGS/IAU (`data/processed/gazetteer.parquet`) más 32 sitios de `config/sites.json` (19 de misión o zona con DEM: Apolo 11–17, Chang'e 3–6, Chandrayaan-3, Luna-25, SLIM, IM-1, IM-2, Blue Ghost M1 y los tres recortes; y 13 regiones Artemis III con coordenadas **aproximadas**), con 56 alias es/en en `config/aliases.json`. «Evaluar este lugar» lleva el lugar al análisis. Si el centro cae fuera del DEM de 5 m, se evalúa el **mejor punto del mapa de idoneidad limitado al entorno del rasgo** (p. ej. Shackleton: a ~0,34 km dentro de su borde; de Gerlache: en su margen, 0,20 km fuera) y se avisa; si no hay mapa, el punto cubierto más cercano; si no hay DEM de 5 m, relieve aproximado de 80 m (hasta 80°S) o esfera lisa, con aviso. |
| 2 | **Capacidad del sitio** | La segunda pantalla, tras el buscador: «según la ubicación, qué energía solar y qué conectividad tendría un lander». **Solar**: Sol visible, noche máxima, ventana solar más larga y, para el panel y el montaje elegidos, **potencia en W/m²** (media y pico) y **energía en Wh/m² por día** (media y mínima). **Conectividad**: **Tierra visible (geometría) frente a ENLACE POSIBLE**, **horas de contacto por día**, ventana de enlace más larga y **hueco máximo sin enlace** frente al que tolera el perfil (puerta G7), con su fecha y la estación que recupera el enlace. En detalle: **sensibilidad al margen de antena (0°, 3°, 5°)**, **tabla de bases terrestres** (% de tiempo con enlace, horas por día, elevación mínima con su procedencia, contacto más largo en UTC, **hora local civil** con su zona y hora solar local media), los contactos de un día elegido, un gráfico de contactos y una ficha descargable (JSON, CSV). El **sentido del enlace** (recepción 6° / transmisión 10,1° / ambos), la red (DSN, ESTRACK, DSN+ESTRACK, personalizada, solo geometría) y el margen se eligen en la barra lateral. En un punto sin recorte de 5 m rotula «Relieve aproximado (80 m)» con el error medido. |
| 3 | **Explorador 3D** | El DEM de 5 m del punto como **mapa topográfico 2D** (relieve sombreado, curvas de nivel, nombres del gazetteer, escala y norte; un clic fija el punto) y como **superficie 3D**, con capas de elevación, pendiente, incertidumbre vertical, muestreo e **iluminación**: sombras del relieve (con curvatura y penumbra) para el Sol de SPICE a la fecha y hora que elijas. Metadatos y CRS. Sin recorte de 5 m no dibuja un 3D vacío: mapa global plano y aviso. El visor 3D con foto está en la rama `feat/lunaris-ui` (ver «Ramas»). |
| 4 | **Mapa del polo sur** | El DEM polar de 80 m (de 80°S al polo, ±304 km) como mapa navegable: zoom 1-64 y desplazamiento, paralelos y meridianos, curvas de nivel, escala y norte, nombres del gazetteer, los tres recortes de 5 m marcados y capas reales rotuladas (**PSR** de Mazarico 2011, **temperatura Diviner** media/máxima/mínima, **iluminación media publicada**). Un clic fija el punto (con la precisión de la celda mostrada) y «Evaluar este punto» abre «Capacidad del sitio». Si faltan los ficheros de una capa, se oculta con aviso. |
| 5 | **Mejores puntos y fechas** | Mapa de los mejores puntos de cada zona por perfil (lander solar sin RHU, rover) y duración de misión (7, 14, 30 d), con **mejor fecha de inicio** (que respeta G7), score con rango, veredicto por puertas y calendario del año. El mapa usa el enlace de la red DSN, no la Tierra geométrica. Necesita el precálculo (ver más abajo). |
| 6 | **Horizonte y visibilidad** | Perfil de horizonte 360°, Sol y Tierra en azimut/elevación con su disco, cursor temporal con animación y **cuenta atrás** hasta puesta/salida de Sol y de la Tierra (*sunset*/*Earthset*). |
| 7 | **Línea temporal** | Bandas de Sol, Tierra, solape y oscuridad; zona de duda por incertidumbre del horizonte; comparar dos fechas; año y estaciones; tabla diaria; exportación CSV/JSON. |
| 8 | **Comparación de sitios** | Hasta 5 sitios o puntos lado a lado, métricas separadas, veredicto por puertas, horizontes superpuestos y score ponderado opcional. **Por defecto cada sitio se compara en su mejor candidato** (TOP-1 del mapa de idoneidad y su mejor fecha); una opción vuelve al punto por defecto del sitio. |
| 9 | **Potencia y paneles** | 8 tipos de panel del catálogo `config/panels.json`; **% de la potencia nominal** por montaje (horizontal, inclinado, vertical fijo, vertical con seguimiento azimutal), energía diaria, batería opcional. Los 8 paneles son calculables: **5 respaldados** (GaAs 3J en tres versiones, 4J, ROSA) y **3 experimentales sin datasheet** (silicio, CIGS, perovskita-silicio; siempre etiquetados, con banda de incertidumbre). En el polo el montaje por defecto es vertical con seguimiento. |
| 10 | **Score del sitio** | Perfil de misión, pesos editables, desglose por indicador, puertas con motivo (G5 con el panel elegido, G7 con el hueco de comunicaciones), confianza de los datos y sensibilidad. El score cambia con el panel, el montaje y la continuidad del enlace. En modo de 80 m es parcial y nunca APTO. |
| 11 | **Acerca de y límites** | Alcance, fuentes, convenciones, avisos científicos, estado de validación, créditos. |

Funciones destacadas: **capacidad del sitio** (energía solar y enlace posible en una sola pantalla), **score de idoneidad por ventana de misión** (se evalúa de la fecha de inicio a inicio + duración, no un año entero), **veredicto y mejores fechas**, **paneles solares con % de potencia y W/m² por montaje**, **mapa de mejores puntos** y **mapa navegable del polo sur**.

> Capturas: [`docs/capturas/`](docs/capturas/) tiene 67 imágenes de la app real: 31 JPG en la raíz (30 numerados `01`–`30` del QA visual más `explorer-3d-corregido.jpg`, de los modos Público, Planificador y Experto, incluida la vista móvil de 390 px; son del QA del 14/11/2026 y **no incluyen «Capacidad del sitio»**) y las subcarpetas `polo/` (6, mapa del polo y «Capacidad del sitio» en modo de 80 m), `relieve/` (7) y `mapas/` (12) del Explorador con iluminación, `correcciones/` (2) e `identidad/` (9, aspecto LUNARIS de la rama `feat/lunaris-ui`). Si cambia la interfaz, pueden quedar desfasadas.

## Ramas: `main` y `feat/lunaris-ui`

| Rama | Qué contiene |
|---|---|
| `main` | **La versión funcional**: el motor científico, las 11 pantallas, el mapa del polo, el Explorador con mapa topográfico e iluminación, los datos y la validación. Es lo que describe este README. |
| `feat/lunaris-ui` | **La identidad visual y el visor 3D**: la marca **LUNARIS**, la navegación superior, la composición de panel de control (anillos, cielo polar, comparativa con miniaturas, informe de misión) y un **visor 3D three.js** autocontenido en el Explorador con foto (LROC NAC y SDEM), Sol y Tierra reales, sombras calculadas y vista del observador. Incluye lo de `main` (a 14/11/2026 se había fusionado `main` hasta `1f489fa`). No cambia el cálculo. |

La marca, la navegación superior y el visor 3D con foto **no están en `main`**. Para verlos:

```powershell
git status                      # el árbol debe estar limpio antes de cambiar
git switch feat/lunaris-ui      # identidad LUNARIS y visor 3D
git switch main                 # versión funcional
```

`data\`, `kernels\` y `.venv` están en `.gitignore`, así que no cambian con la rama. Git no deja tener la misma rama en dos carpetas: mientras exista un árbol de trabajo con `feat/lunaris-ui`, `git switch feat/lunaris-ui` falla en esta carpeta.

**Las dos ramas a la vez** (`git worktree`): una segunda carpeta con `feat/lunaris-ui`, enlazando `data\` y copiando `kernels\` (los datos pesan GB y los kernels no van a git). El árbol hermano `lunar-site-intelligence-lunaris` está montado así; los comandos para crearlo desde cero (no se han vuelto a ejecutar al escribir este README):

```powershell
git worktree add ..\lunar-site-intelligence-lunaris feat/lunaris-ui
cmd /c mklink /J ..\lunar-site-intelligence-lunaris\data "$PWD\data"      # unión a data\ (sin copiar GB; no pide administrador)
Copy-Item kernels\* ..\lunar-site-intelligence-lunaris\kernels\ -Exclude README.md
cd ..\lunar-site-intelligence-lunaris
python -m streamlit run app.py --server.port 8502                          # otro puerto si `main` ya usa el 8501
```

Se usa el mismo entorno virtual (`.venv\Scripts\Activate.ps1`). Para retirarlo: `git worktree remove ..\lunar-site-intelligence-lunaris` (quita antes la unión `data` con `cmd /c rmdir ..\lunar-site-intelligence-lunaris\data`, que no borra los datos). Cada rama tiene sus propios commits: confirma los cambios en la carpeta donde los hagas.

## Instalación (Windows, Python 3.11)

Requisitos: Python 3.11 y espacio libre: unos **0,95 GB** para los datos del núcleo (DEM, kernels y gazetteer), otros ≈ 0,5 GB de caché si precalculas la idoneidad y **≈ 2,4 GB** con todo lo opcional descargado y las cachés actuales (medido el 14/11/2026: `data/raw` 1,67 GB, `data/processed` 0,56 GB, `data/validation_raw` 0,16 GB).

```powershell
cd lunar-site-intelligence
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Dependencias fijadas en `requirements.txt` (numpy 2.4.2, scipy, pandas, pyarrow, rasterio, pyproj, spiceypy 8.4.0, plotly, pydeck, streamlit 1.58.0, requests, pyshp, tzdata para las horas locales de las estaciones, pytest). Si `rasterio` no instala en tu equipo, usa Python 3.11 de 64 bits.

## Obtener los datos

`data/raw/`, `data/processed/`, `data/validation_raw/` y `kernels/*` **no van al repositorio** (`.gitignore`); se reproducen con estos comandos. Son idempotentes: lo ya descargado se omite. Tamaños en MB decimales, medidos el 14/11/2026; los hashes de lo básico están en `config/data_manifest.json`.

**Núcleo (necesario):**

| Comando | Qué hace | Descarga aproximada |
|---|---|---|
| `python scripts/fetch_data.py` | DEM LOLA 5 m de 3 sitios (4 capas cada uno: `surf`, `slp`, `ldec`, `toterr`), LOLA polar 80 m y los 6 kernels SPICE; comprueba el SHA-256 de cada fichero. Sin opciones: no tiene `--help`, ejecutarlo con cualquier argumento descarga. | Shackleton 163,9 MB, de Gerlache 163,9 MB, Mons Malapert 282,3 MB, LOLA 80 m 189,2 MB, kernels 18,7 MB: **≈ 0,82 GB** |
| `python scripts/fetch_gazetteer.py` | Baja el zip del gazetteer USGS, lo extrae en `data/raw/gazetteer/dl_*/` y escribe `data/processed/gazetteer.{csv,parquet}` (9087 rasgos; el buscador añade en memoria los 32 sitios de `config/sites.json`). Sin `--help`: cualquier argumento lo ejecuta. Falla con mensaje claro si el formato cambia o si el hash no coincide. | zip 23,8 MB (95,4 MB en disco con lo extraído) |
| `python scripts/precompute_horizons.py` | Precalcula los horizontes por defecto (3 sitios × alturas de 1, 2 y 5 m) en `data/processed/horizons/`. Idempotente. Esa carpeta también guarda los horizontes de cada análisis posterior. | 7 MB los precalculados; 31,9 MB con las cachés acumuladas |
| `python scripts/precompute_suitability.py --profile lander_solar_no_rhu --profile rover --duration 7 --duration 14 --duration 30` | Mapas de idoneidad con ventanas de misión para «Mejores puntos y fechas» (malla de 250 m, horizonte cada 1°, serie cada 30 min). `--help` documenta todas las opciones. Con `--validate 12` compara 12 nodos con el modelo fino. | 510 MB de caché con las regeneraciones acumuladas en `data/processed/suitability/`; los JSON de ventanas indican 20–34 s por sitio y perfil en la máquina de desarrollo |

Sin el precálculo de idoneidad la app funciona, salvo «Mejores puntos y fechas» (y la comparación por candidato, que cae al punto por defecto), que muestra el comando necesario. El precálculo usa por defecto el enlace DSN en recepción con margen 0°; `--link-network`, `--link-direction`, `--min-earth-elevation` y `--station-min-elevation` lo cambian (y exigen regenerar). La base del «Mapa del polo sur» se construye sola la primera vez que se abre (`data/processed/polar_map/`, 12,8 MB).

**Datos añadidos (opcionales; cada uno dice qué pierde la app si falta):**

| Comando | Qué hace | Descarga aproximada | Sin él |
|---|---|---|---|
| `python scripts/fetch_thermal_psr.py` (`--only diviner`, `--only psr` o `--only illum_ref`) | Temperatura Diviner (Williams 2019, 240 m), polígonos PSR (Mazarico 2011) e iluminación media publicada AVGVISIB (PGDA 69). Reanudable; `--help` **no descarga**; sin opciones baja las tres familias; `--max-mb` (500 por defecto) rechaza ficheros mayores. | Diviner 154,1 MB, PSR 3,8 MB, iluminación 117,0 MB: **≈ 275 MB** | El «Mapa del polo sur» oculta esas capas con aviso |
| `python scripts/fetch_sdem.py --yes` | SDEM de 5 m y ortomosaico LROC NAC de Malapert Massif, de Gerlache Rim 1 y Peak Near Shackleton (PGDA 104, Zenodo, **CC-BY-4.0**), leyendo solo las capas necesarias de zips de 4,9 GB por HTTP Range. Sin `--yes` no descarga nada; `--region` limita a una. | **329,7 MB** (329,3 MB leídos) | Nada en `main` (los consume el visor de `feat/lunaris-ui`) |
| `python scripts/fetch_imagery.py --sites Site04 Site11 Site23 --yes` | Recortes de ±3 km del mosaico LROC NAC promedio (1 m/px, dominio público) para el visor 3D; con `--regions --yes` reescribe `config/artemis_regions.json` (≈ 8 MB de Zenodo). Sin `--yes` solo imprime el plan; `--max-mb` (300 por defecto). **No lanzar sondeos masivos**: el servidor del PDS respondió 429. | **94,1 MB** (≈ 110 MB recibidos) | Nada en `main` (visor de `feat/lunaris-ui`) |
| `python scripts/fetch_validation_data.py --yes` | DEM LOLA 5 m de Site01 (Connecting Ridge) para `tests/test_luna_cases.py`. Sin `--yes` solo consulta tamaños (HEAD); `--help` no descarga. | **163,9 MB** | 38 pruebas se omiten |
| `python scripts/data_manifest.py` | Verifica los SHA-256 de lo básico contra `config/data_manifest.json` (20 ficheros; el 14/11/2026, 20 `ok`). `--regenerate` reescribe el manifiesto: solo como decisión consciente. | — | — |
| `python scripts/validate_far_field.py` | Repite la validación del modo de 80 m (120 puntos, semilla 20260814; `--n-per-site`, `--seed`, `--out`). Es larga y no se ha vuelto a ejecutar al escribir este README. | — | — |

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

Hay **56 ficheros** `tests/test_*.py` y 697 funciones `def test_`; `python -m pytest --collect-only -q -p no:cacheprovider` recoge **977 casos** (14/11/2026), incluidos los 26 de `tests/test_independent_visibility.py`, los 37 de `tests/test_independent_link.py` y los 38 de `tests/test_luna_cases.py`. Última ejecución completa en `feat/lunaris-ui` (15/11/2026, tras pasar `T_amb` a 130 K y regenerar los dorados): **997 passed**. Marcadores declarados en `pytest.ini`: `slow` (117 casos: año completo, rendimiento, UI completa, dorados), `perf` (5 casos: presupuestos de rendimiento de arquitectura §10; `python -m pytest -q -m perf -s` imprime tiempos), `needs_spice` (450) y `needs_dem` (165), que omiten la prueba si faltan kernels o DEM. `python -m pytest -q -m "not slow"` da una pasada rápida. Las 38 pruebas contra la literatura de `tests/test_luna_cases.py` necesitan el DEM Site01 (`python scripts/fetch_validation_data.py --yes`, en `data/validation_raw/site01/`; otra carpeta con `LSI_SITE01_DIR`; ver [`docs/validation/validacion-luna.md`](docs/validation/validacion-luna.md) §6): con él dieron **38 passed** el 14/11/2026; sin él se omiten.

## Estructura del repositorio

```
app.py                  punto de entrada de Streamlit
ui/                     interfaz (solo ui/ y app.py importan streamlit)
  pages/                las 11 pantallas
src/lsi/                núcleo científico determinista, sin UI
  data/                 loader DEM, catálogo, caché por hash, gazetteer, mapa del polo (polar_view), SDEM, imagen LROC, Diviner (thermal), PSR, iluminación publicada (illum_ref)
  terrain/              muestreo, horizonte (DEM y FAR_FIELD), pendiente, rugosidad, sombras (shadows)
  astronomy/            coordenadas (proyección, ENU), motor SPICE y estaciones terrestres (ground_stations)
  simulation/           visibilidad (disco finito), línea temporal, incertidumbre
  energy/               modelo de potencia de paneles
  analysis/             métricas, score, confianza, mapa de idoneidad, exportación
  visualization/        figuras Plotly
  pipeline.py           orquestación (run_analysis)
config/                 simulation.json, panels.json, ground_stations.json, sites.json, aliases.json, artemis_regions.json, data_manifest.json
scripts/                fetch_data, fetch_gazetteer, fetch_sdem, fetch_imagery, fetch_thermal_psr, fetch_validation_data, data_manifest, fetch_horizons_stations, precompute_horizons, precompute_suitability, validate_far_field
kernels/                kernels SPICE (no versionados; ver kernels/README.md)
data/raw, data/processed, data/validation_raw  datos y cachés (no versionados)
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
| SDEM y ortomosaico LROC NAC, PGDA 104 (Zenodo 10.5281/zenodo.17954508, v1.0.0, **CC-BY-4.0**) | https://pgda.gsfc.nasa.gov/products/104 · https://zenodo.org/records/17954508 | Malapert Massif, de Gerlache Rim 1 y Peak Near Shackleton; solo visualización 3D |
| Mosaico LROC NAC polo sur promedio, `NAC_POLE_SOUTH_CM_AVG` (PDS, **dominio público**) | https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG | Foto de Site04 (1 m/px), solo visualización 3D |
| Diviner, mapas polares estacionales (Williams et al. 2019; condiciones a verificar) | http://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar/additional_maps/ | Temperatura del regolito (240 m): capa del mapa del polo y contexto |
| PSR del polo sur (Mazarico et al. 2011, vía LROC/ASU; condiciones a verificar) | https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_PSR_SOUTH | 653 polígonos > 5 km²: capa del mapa del polo y contexto |
| Iluminación media publicada AVGVISIB, PGDA 69 (condiciones a verificar) | https://pgda.gsfc.nasa.gov/products/69 | Contraste del motor y capa del mapa del polo |
| Regiones Artemis III (NASA, 2022 y 2024) y estaciones adicionales (ESA EFM, NASA LEGS/NSN, NAIF NDOSL) | `docs/fuentes-datos.md` §15-§16 | Coordenadas aproximadas derivadas del SDEM; ninguna estación nueva entra en una red |
| DEM LOLA de Site01 (PGDA 78) | https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/ | Solo las 38 pruebas contra la literatura |

Tamaños, hashes, versiones, citas y condiciones de uso (lo verificado y lo **a verificar**) en [`docs/fuentes-datos.md`](docs/fuentes-datos.md).

## Validación: qué se contrastó y con qué resultado

- **Efemérides frente a JPL Horizons**: 24 casos (3 lugares × 4 fechas × Sol/Tierra). Diferencia máxima **0,05″ en elevación y 0,04″ en azimut** (hasta 0,39″ con el cuerpo a más de 80° de elevación, donde el azimut se degenera). Horizons usa DE441 y LSI DE421; el residuo se atribuye a eso (no comprobado por separado). `docs/science/luna-spice-sitios.md` §2.
- **Comprobación independiente 3D** (`tests/test_independent_visibility.py`, 26 pruebas): una formulación cartesiana 3D sin la geometría del motor, sobre 6 puntos y 3 ventanas de 30 días (38 907 instantes). **0 contradicciones duras**; perfil de horizonte con diferencia RMS de 0,007°–0,023° y máxima de 0,13° (el motor queda por debajo, optimista; causa: discretización radial de 5 m, no error de marco); fracción de tiempo por rejilla frente a métrica del motor ≤ 0,0006. No valida los datos LOLA, solo la matemática que los usa. `docs/validation/revision-matematica.md`.
- **Enlace y estaciones** (`docs/validation/revision-enlace.md`, `tests/test_independent_link.py`: 37 pruebas, 37 passed el 14/11/2026): la Luna vista desde DSS-14/-63/-43 frente a Horizons difiere **0,0002–0,0007°** con una cadena independiente en ITRF93 y **0,072°** con la rotación simplificada del motor (`IAU_EARTH`); cobertura DSN de dic-2026 **99,929 %** en recepción (6°) y **97,992 %** en transmisión (10,1°); enlace posible por fuerza bruta 3D en 9 casos con |Δ link_fraction| ≤ **8e-4**; horas locales y horario de verano de 2027 con reglas escritas a mano, acuerdo total. Detalle en [`docs/metodologia.md`](docs/metodologia.md) §9.
- **Literatura** (`docs/validation/validacion-luna.md`; **38 pruebas, 38 passed el 14/11/2026 con el DEM Site01**): con las definiciones de cada artículo, el motor reproduce lo publicado de la Connecting Ridge:
  - Barker et al. (2021), 7 regiones, 2024-26, z = 5 m: iluminación media 88,4–94,3 % frente a percentil 1 de 82,8–89,3 %; LCIP (periodo más largo con Sol) 233–265 d (RoI 1–6) y 146 d (RoI 7) frente a 216–231 d y 119 d; LCSP (noche más larga) 3,5–6,1 d frente a 4,0–8,4 d.
  - Gläser et al. (2014), 19 años a 2 m: 92,1 % y 94,1 % del tiempo iluminado frente a 92,27 %; noche más larga 5,06 y 4,89 d frente a «típicamente 3-5 d».
  - Mazarico et al. (2011): «~240 d continuos y ~1,5 d de noche máxima» es coherente con LSI **solo si** esa cifra corresponde a una altura de decenas de metros (a 10 m: noche 1,3–1,8 d); la altura de su cifra **a verificar** en el artículo completo.
- **Contraste con la iluminación media publicada** (PGDA 69 AVGVISIB, 60 m, 18,6 años, superficie; `docs/validation/contraste-iluminacion-publicada.md`). LSI se ejecutó con la definición del mapa (`effective_illumination`, observador a 0 m, 2024-01-01 a 2042-08-01, 18,58 años). En **24 puntos de rejilla** de los tres recortes: sesgo **−0,01**, RMS **0,09**, **19 de 24 dentro de ±0,10** (tolerancia propuesta, no publicada); Site04 RMS 0,03 (r = 0,98; la PSR de Shackleton coincide). **Los TOP-1 no validan**: difieren ±0,2–0,3 por la altura del observador (de 0 a 2 m la iluminación pasa de 0,39 a 0,85 en Site11), el periodo (18,6 años frente a 1 año) y el sesgo de selección de máximos. Valida el campo medio, no un punto óptimo.
- **Modo de 80 m (`FAR_FIELD`)** frente al DEM de 5 m (`docs/validation/horizonte-campo-lejano.md`, 120 puntos reales, 30 días): horizonte **RMS 0,68°**, máximo **5,8°**, sesgo **−0,25°** (el 80 m queda más bajo: optimista); fracción de Sol y de Tierra con error p95 **0,04**; el veredicto por puertas no terrenales cambia en el **10 %** de los puntos; en cimas (el punto por defecto de Malapert) +0,19 de Sol.
- **No hay cifras publicadas por altura de observador** para Site 4, 11 y 23 (Barker 2021 solo da Site 1) ni para la visibilidad de la Tierra en los sitios. Quedan **a verificar**.
- **Mapa de idoneidad frente al modelo fino** (`--validate 12`, perfil lander, año completo): diferencia máxima de f_sol 0,0098, de f_Tierra 0,0039 y de score 0,44 puntos; la oscuridad máxima difiere hasta 2,3 h (Site04), 2,7 h (Site11) y 50,2 h (Site23, en un nodo con noches de decenas a cientos de horas; el nodo concreto no se ha analizado). JSON `data/processed/suitability/Site*_lander_solar_no_rhu_*.json` (bloque `validation`). Se midió con una versión anterior del mapa: **hay que repetirlo** con la actual.

## Estado y reservas

Estado a 14/11/2026 en `main`, verificado ejecutando el motor y recontando las pruebas (no copiado de informes).

- **Validado:** geometría Sol/Tierra frente a JPL Horizons (24 casos, ≤ 0,05″); matemática del horizonte y la visibilidad frente a una formulación 3D independiente (26 pruebas); enlace y estaciones frente a una cadena independiente y Horizons (37 pruebas); las 38 pruebas contra la literatura de la Connecting Ridge (38 passed); los hashes de los 20 ficheros básicos (`scripts/data_manifest.py`); última ejecución completa de la suite: **997 passed** (15/11/2026, rama `feat/lunaris-ui`); en entorno limpio la app arranca y las pantallas pasan las pruebas de humo (`docs/validation/puerta-final.md`). Las cifras de los puntos de 5 m de `docs/guion-demo.md` se volvieron a ejecutar el 14/11/2026 tras los cambios del modo de 80 m y el mapa del polo, sin diferencias.
- **Es estimación:** la potencia por panel (3 de 8 paneles experimentales sin datasheet, con banda de incertidumbre; los 5 respaldados lo son por su celda de referencia, y W/m² es de celda, sin empaquetado); el enlace posible (geometría y cobertura, con márgenes de antena y umbrales de huecos G7 supuestos); el score y el veredicto (pesos, umbrales y puertas son convenciones de LSI sin calibrar); la **resolución efectiva (~30 m)**, heurística de LSI a verificar (el SDEM, medido, no la desmiente ni la confirma); el mapa de idoneidad (malla gruesa de 250 m); las coordenadas de las regiones Artemis III (derivadas de la huella del SDEM, no publicadas por NASA); la temperatura de Diviner (regolito, estacional). El rango de incertidumbre puede tener ancho cero en puntos saturados. **«APTO» no certifica nada**, y visibilidad geométrica no es potencia ni enlace garantizados.
- **El modo de 80 m es aproximado y optimista en crestas:** horizonte con RMS 0,68° y hasta 5,8° de error, sesgo −0,25° (sobreestima la luz), veredicto distinto en el 10 % de los puntos; el score es parcial y nunca APTO.
- **Los TOP-1 no validan contra el mapa publicado** (±0,2–0,3): el campo medio cuadra (sesgo −0,01, RMS 0,09), el punto óptimo elegido no se puede dar por contrastado.
- **`T_amb` de panel: 130 K con banda 40–250 K, aplicada el 15/11/2026** (propuesta de `docs/validation/datos-termico-psr.md`: factor de forma 0,84 **supuesto**, sin fuente primaria del IR del regolito iluminado; sigue «a verificar»). Mueve la potencia como mucho ≈ 0,4 puntos porcentuales; el score y el veredicto de los casos del guion no cambian.
- **Falta o está a verificar:**
  - **Licencia del código**: Apache-2.0 (fichero `LICENSE`), la que NASA Space Apps aplica por defecto; los datos de terceros conservan su propia licencia y cita (`docs/fuentes-datos.md`).
  - **Repositorio remoto**: no hay; los commits son locales (`main` y `feat/lunaris-ui`).
  - **Vídeo de demo**: grabado (≈2 min, voz es-ES; `docs/workflow-grabacion-video.md`, `scripts/record_demo.py`); el MP4 no se versiona. Publicarlo es decisión del dueño.
  - **Red NSN de NASA (LEGS)**: no incluida; hay posiciones, pero ninguna elevación mínima verificada. **ESTRACK**: elevación supuesta de 6°; ESA publica una máscara por acimut (CEB-1 ≈ 5,5°, NNO-1 ≈ 8,4–8,5°) que **no está implementada**. Máscara de terreno y ocupación de las antenas del DSN, y transmisión de alta potencia (13,6°).
  - **Condiciones de uso** de PGDA 78/90/69, Diviner, los polígonos PSR, la nomenclatura IAU y JPL Horizons (la política general de NASA y USGS, la CC-BY-4.0 del SDEM y el dominio público del LROC Data Node del PDS sí están verificados, ver `docs/fuentes-datos.md`).
  - **Contraste con la literatura** para Shackleton, de Gerlache y Malapert (solo hay cifras publicadas para Site 1; el mapa publicado de iluminación es de superficie y 18,6 años); `--validate 12` del mapa de idoneidad con la versión actual (enlace); repetir las descargas desde cero con solo este README.
  - **Ramas**: el visor 3D con foto y la marca LUNARIS están en `feat/lunaris-ui`, no en `main`.

## Limitaciones (resumen)

- **Visibilidad geométrica ≠ potencia ≠ enlace RF.** «Enlace posible» = Tierra visible con margen de antena + cobertura de estación (DSN), **no** un presupuesto de enlace: sin potencia, frecuencia, ganancia ni ruido, y por defecto solo recepción a 6°. Sin estaciones NSN; ESTRACK con elevación supuesta y máscara por acimut sin implementar.
- **Resolución efectiva ≈ 30 m**, no 5 m: ~90 % de los píxeles del DEM no tiene retorno LOLA propio. Rocas y cráteres menores de ~150 m no se evalúan.
- **Un punto no es una zona.** Resultado para un punto y una altura (2 m por defecto).
- **Potencia = estimación relativa** (W/m² de celda, sin empaquetado) con supuestos declarados; 3 de los 8 paneles son experimentales sin datasheet (etiquetados) y otros parámetros siguen «a verificar». Sin polvo, albedo ni sombra propia; sin eclipses de la Tierra sobre el Sol. `T_amb` de panel a 130 K (rango 40–250 K), a verificar.
- **Score sin calibrar**: pesos y umbrales son convenciones de LSI pendientes de un experto de misión. «Apto» no significa «seguro» ni «aterrizable».
- **El DEM de 5 m cubre 16×16 km (Shackleton, de Gerlache) y 21×21 km (Malapert)**; más allá, el de 80 m: **horizonte aproximado, RMS 0,68° (hasta 5,8°), optimista en crestas** (−0,25°), score parcial y nunca APTO.
- **PSR publicada ≠ sombra del periodo simulado**: 18,6 años a nivel de superficie frente a 1 año y un observador a 2 m; el mapa publicado de iluminación tampoco valida un TOP-1 (sesgo de selección de máximos).
- **Foto y ortomosaico** (solo en el visor de `feat/lunaris-ui`): promedio de pasadas o de máxima iluminación, no las sombras de la fecha; el ortomosaico SDEM está desplazado 2,5 m y la foto LROC puede estar corrida hasta ~15 m; sin SDEM en Site04. **Temperatura Diviner** estacional, del regolito.
- Rango temporal 1900-2050 (cobertura del kernel de orientación lunar).

Detalle completo, con las cifras de cada límite: [`docs/limitaciones.md`](docs/limitaciones.md).

## Créditos y referencias

Datos y herramientas: NASA (LOLA/LRO, LROC y Diviner, PGDA, PDS, NAIF/SPICE, JPL Horizons, Space Apps), Arizona State University (LROC), USGS Astrogeology (Gazetteer, IAU WGSN), ESA (ESTRACK). Crédito del mosaico LROC NAC: «NASA/GSFC/Arizona State University». LSI no está afiliado ni respaldado por estas instituciones. Se agradece el uso de SPICE y de los recursos NAIF, como solicita NAIF.

Referencias científicas (las marcadas «leída» se leyeron en fuente durante la validación; el resto, **a verificar** antes de citar):

- Mazarico, E. et al. (2011). *Illumination conditions of the lunar polar regions using LOLA topography*. Icarus 211, 1066-1081. doi:10.1016/j.icarus.2010.10.030 (resumen leído: https://ntrs.nasa.gov/citations/20120010094).
- Barker, M.K. et al. (2021). *Improved LOLA elevation maps for south pole landing sites: error estimates and their impact on illumination conditions*. Planetary and Space Science 203, 105119. doi:10.1016/j.pss.2020.105119 (texto completo leído).
- Gläser, P. et al. (2014). Icarus 243, 78-90. doi:10.1016/j.icarus.2014.08.013 (resumen leído: https://elib.dlr.de/94240/).
- Bertone, S., McKenna, T. E., Barker, M. K., Mazarico, E., Beyer, R. A., and Petro, N., *Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading*, The Planetary Science Journal, doi: 10.3847/PSJ/ae5b70 (cita tal como la da la página de PGDA 104, que **no indica el año**). Datos: Bertone, S., Barker, M., Mazarico, E., McKenna, T., and Petro, N., 2025, Zenodo, doi: 10.5281/zenodo.17954508 (SDEM y ortomosaico, **CC-BY-4.0**; hay que atribuirlos donde se usen).
- Archinal, B. et al. (2023). *Controlled High-Resolution LROC NAC Polar Mosaics*, LPSC 54, #2333 (mosaico LROC NAC; dominio público, crédito NASA/GSFC/ASU).
- Williams, J.-P. et al. (2019). *Seasonal polar temperatures on the Moon*, J. Geophys. Res. Planets 124, 2505-2521, doi:10.1029/2019JE006028 (Diviner).
- Brown, H. M. et al. (2022). *LROC PSR Atlas and PSR Mosaics*, Lunar Polar Volatiles Conf., #5033 (polígonos PSR de Mazarico et al. 2011).
- Mazarico, E., Barker, M.K., Nicholas, J.B. (2018). Advances in Space Research (IllumNG). https://pmc.ncbi.nlm.nih.gov/articles/PMC6398960 (leída).
- Documento base: *Arquitectura y Plan v1.0* (13/11/2026), `docs/documento-base.pdf`. Reto: `docs/reto-nasa.md`.

Cómo citar: «Lunar Site Intelligence (LSI), 2026. Equipo LSI, NASA Space Apps Challenge 2026, *Lunar Landing Site Navigator*.»

**Licencia del código: Apache-2.0** (fichero `LICENSE`). Elegida por indicación del dueño: la que fije el hackatón. Los términos de Space Apps de 2026 no pudieron leerse de la fuente primaria (fallo de certificado TLS del sitio); revisa que siguen aceptando una licencia OSI. Los datos NASA/USGS/SDEM mantienen sus licencias y citas.

## Use of AI tools / Declaración de uso de IA

**EN.** The code, tests and documentation of this repository were written with the assistance of **Claude Code (Anthropic, Claude Sonnet 5.5)** under the team's direction, and the demo narration uses a Windows text-to-speech voice. All scientific numbers come from NASA data and the code in this repository, not from a language model. No NASA logos, flags or mission identifiers are used. Screenshots in the presentation are captures of the real application; no image is AI-generated.

**ES.** El código, las pruebas y la documentación se escribieron con ayuda de **Claude Code (Anthropic, Claude Sonnet 5.5)**, dirigido por el equipo; la narración de la demo usa una voz de síntesis de Windows. Las cifras científicas salen de los datos de NASA y del código, no de un modelo de lenguaje. No se usa ningún logotipo, bandera ni identificador de misión de NASA. Las capturas de la presentación son de la aplicación real; ninguna imagen está generada por IA.
