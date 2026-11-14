# Fuentes de datos

Todo dato externo se descarga con los scripts de `scripts/`; ninguno va al repositorio (`.gitignore`: `data/raw/`, `data/processed/`, `kernels/*` salvo `kernels/README.md`). Tamaños y hashes medidos el 14/11/2026 sobre los ficheros de este equipo. «Condiciones de uso» distingue lo **verificado en la fuente** de lo **a verificar**.

> Nota sobre licencias. Verificado en la política oficial (14/11/2026): NASA, «generalmente no sujeto a copyright en EE. UU.», con la salvedad de que el logotipo e identificadores no son de dominio público y de que hay material de terceros con copyright; pide reconocer a NASA como fuente (https://www.nasa.gov/nasa-brand-center/images-and-media/). USGS: sus datos e información son de dominio público de EE. UU.; pide crédito; hay material de terceros marcado con copyright (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). NAIF: ver §3 (verificada). Es **política general**: las páginas de PGDA (producto 78 y su README) y del Gazetteer **no declaran en el texto leído condiciones propias**, y la nomenclatura es trabajo del IAU WGSN. Por eso las condiciones específicas de PGDA 78/90, del gazetteer, de Horizons, del documento DSN 810-005 y de los datasheets de fabricantes siguen **a verificar** (las de NAIF sí están verificadas, §3). LSI atribuye las fuentes y no redistribuye ningún dato.

## 1. DEM LOLA de 5 m (sitios)

| Campo | Valor |
|---|---|
| Producto | PGDA producto 78, DEM LOLA de 5 m/píxel de los sitios de aterrizaje del polo sur (`Site*_final_adj_5mpp_*`) |
| Página | https://pgda.gsfc.nasa.gov/products/78 · README: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README |
| URLs de datos | `https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/<Site>/<Site>_final_adj_5mpp_<capa>.tif` |
| Sitios usados | Site04 (Shackleton, `data/raw/shackleton/`), Site11 (de Gerlache, `data/raw/de_gerlache/`), Site23 (Mons Malapert, `data/raw/malapert/`). La numeración sigue a Mazarico et al. (2011) |
| Capas | `surf` (elevación, m), `slp` (pendiente, °; diferencia central con baseline de 10 m), `ldec` (conteo de retornos LOLA), `toterr` (incertidumbre vertical total, m) |
| Versión | Producto «final_adj» tal como se sirve; fecha de publicación **a verificar** |
| Tamaño | Site04: 4 ficheros de 40 980 7xx bytes (≈ 41 MB, 157 MB en total); Site11: igual; Site23: 4 de 70 586 8xx bytes (≈ 70,6 MB, 270 MB en total) |
| Hash | SHA-256 de las capas `surf` en `data/processed/dem_hash.json`: Site04 `38ff70db…ce758`, Site11 `58f3372c…136e5`, Site23 `12d280a5…c94cf` (el fichero completo guarda también las demás capas) |
| Cobertura | Shackleton y de Gerlache ≈ 16×16 km; Malapert ≈ 21×21 km |
| Condiciones de uso | No declaradas en la página ni en el README leídos; el README pide citar Barker et al. (2021) y Mazarico et al. (2011). **A verificar** |
| Cómo se usa | Horizonte (campo cercano y medio), pendiente y rugosidad, confianza de datos, Explorador 3D, mapa de idoneidad |
| Advertencia | 5 m es el tamaño de celda, no la resolución efectiva: ~90 % de los píxeles no tiene retorno LOLA propio (`ldec = 0`); resolución efectiva ≈ 30 m (heurística de LSI, a verificar) |

## 2. DEM polar LOLA de 80 m (campo lejano)

| Campo | Valor |
|---|---|
| Producto | PGDA producto 90, `LDEM_80S_80MPP_ADJ.TIF` (80°S–90°S, 80 m/píxel) |
| URL | https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF |
| Ruta local | `data/raw/lola80s/LDEM_80S_80MPP_ADJ.TIF` |
| Tamaño | 189 158 392 bytes (≈ 181 MiB) |
| Hash | No calculado en el repositorio (el cargador guarda su SHA-256 en la caché de horizontes). **Pendiente** |
| Condiciones de uso | No verificadas (ver nota). **A verificar** |
| Cómo se usa | Completa el horizonte más allá del recorte de 5 m (±304 km alrededor del polo, mismo CRS y marco vertical) |
| Advertencia | Difiere del 5 m (media −0,15 m, RMS 1,2 m en el solape de Site04; en el polo ~7 m); es una estimación del horizonte lejano |

## 3. Kernels SPICE (NAIF)

Seis kernels en `kernels/`; procedencia, cobertura y hash de cada uno en [`kernels/README.md`](../kernels/README.md). Servidor: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/.

Condiciones de uso (**verificadas** en https://naif.jpl.nasa.gov/naif/rules.html el 14/11/2026): los kernels «pueden ser descargados y usados por cualquiera»; su redistribución se permite **si no se han modificado** (si se modifican hay que cambiar la atribución y el nombre); NAIF **solicita** reconocer el uso de SPICE y de los recursos NAIF/PDS. LSI no redistribuye los kernels (se descargan) y los agradece en el README y en la pantalla «Acerca de».

## 4. Gazetteer lunar (USGS / IAU)

| Campo | Valor |
|---|---|
| Producto | Gazetteer of Planetary Nomenclature, Moon, puntos centrales (IAU WGSN) |
| Página | https://planetarynames.wr.usgs.gov/ |
| URL de datos | https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.zip |
| Versión | Descarga de 2026 (la fecha exacta no se registra); el zip es el vigente en el servidor. **A verificar** si se quiere fijar versión |
| Tamaño | zip 23 845 070 bytes; `.dbf` 23 481 450; `.shp` 254 536 |
| Resultado | `data/processed/gazetteer.csv` (1,56 MB) y `.parquet` (0,50 MB): **9087 rasgos** (7064 *Satellite Feature*, 1615 *Crater*, 112 *Rima*, 81 *Astronaut-named features*, 58 *Mons*, …) |
| Condiciones de uso | No declaradas en el texto leído. El sitio indica que el trabajo se realiza en nombre del IAU WGSN. **A verificar** |
| Cómo se usa | Solo el buscador, que añade en memoria los 19 sitios de misión con coordenadas de `config/sites.json`: **9106 lugares** en total, con 56 alias es/en de `config/aliases.json`. Posición = centro del rasgo (longitud ya este-positiva 0–360), no un punto de aterrizaje: aviso `GAZETTEER_COORDS_APPROX` |
| Seguridad | `fetch_gazetteer.py` rechaza entradas del zip con rutas y valida que existan las columnas esperadas y que lat/lon estén en rango |

## 5. JPL Horizons (solo contraste)

https://ssd.jpl.nasa.gov/horizons/ (API `https://ssd.jpl.nasa.gov/api/horizons.api`). No se descarga ningún dato en la app. Se usó el 14/11/2026 para contrastar azimut/elevación aparentes de Sol y Tierra (24 casos; diferencia máxima 0,05″, `docs/science/luna-spice-sitios.md` §2) y la elevación de la Luna vista desde DSS-14/-63/-43 (`CENTER=coord@399`, `QUANTITIES=4`, AIRLESS; ver §8). Horizons usa efemérides DE441; LSI, DE421. Condiciones de uso: **a verificar**. **Aviso:** `scripts/fetch_horizons_stations.py` **no tiene `--help`**: ejecutarlo con cualquier argumento llama a la API de Horizons y reescribe `tests/golden/horizons_stations_2026-12.json`.

## 6. Catálogos de LSI

| Fichero | Contenido | Estado |
|---|---|---|
| `config/sites.json` | 32 entradas, 19 con coordenadas (3 zonas con DEM y 16 misiones, buscables); el resto, regiones Artemis III | Coordenadas de misiones tomadas de la lista de Wikipedia de objetos artificiales en la Luna (fuente secundaria); las regiones Artemis III **sin coordenadas verificadas** (`null`) |
| `config/panels.json` | 8 paneles: 5 `respaldado` (3J ×3, 4J, ROSA) y 3 `experimental_sin_datasheet` (silicio, CIGS, perovskita-silicio, con banda de incertidumbre); 4 montajes; perfiles de misión; `areal_power_w_m2_am0` de cada panel (η × 1361 W/m²) | Cada parámetro lleva etiqueta de confianza (`publicado`, `estimado`, `a_verificar`…); registro fuente a fuente en `docs/validation/datos-paneles.md` (14/11/2026); varias fuentes son secundarias |
| `config/ground_stations.json` | 6 estaciones (DSS-14, DSS-63, DSS-43 verificadas; NNO-1, CEB-1, MLG-1 de ESTRACK con elevación mínima SUPUESTA), 3 redes (DSN, ESTRACK, DSN+ESTRACK), sentidos de enlace (recepción 6,0°, transmisión 10,1°), `networks_not_available.NSN` | Posiciones y elevaciones de DSN **verificadas** en DSN 810-005/301 Rev. P; ESTRACK: coordenadas NAIF y elevación **a verificar [sup]**; NSN **sin estaciones** (§8) |
| `config/aliases.json` | 56 alias es/en → nombre oficial, palabras y zonas del buscador | Cada valor debe existir en el gazetteer o en `sites.json` (lo comprueba `tests/test_gazetteer.py`) |
| `config/simulation.json` | Parámetros del motor | Etiquetas `[pub]`, `[cal]`, `[ver]`, `[sup]` en `_etiquetas` |

## 7. Literatura usada para validar

Mazarico et al. 2011 (Icarus 211, 1066-1081); Barker et al. 2021 (Planetary and Space Science 203, 105119); Gläser et al. 2014 (Icarus 243, 78-90); Mazarico, Barker y Nicholas 2018 (IllumNG). Estado de lectura de cada una en `docs/validation/validacion-luna.md` §2. No leídos y **a verificar**: Mazarico 2011 completo (Table 3), Gläser et al. 2017, Bussey et al. 2010, Speyerer y Robinson 2013.

## 8. Estaciones terrestres, orientación de la Tierra y enlace

Fuente de `config/ground_stations.json`. Solo figuran números verificados en fuente oficial; lo demás queda «a verificar» y la estación no se usa por defecto. Verificado el 14/11/2026.

| Dato | Fuente | Estado |
|---|---|---|
| Posición WGS 84 de DSS-14, DSS-63, DSS-43 | DSN 810-005, módulo 301 «Coverage and Geometry», Rev. P (22/05/2026), Tabla 5 (https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf; copia local `data/raw/earth/301P.pdf`, no versionada). Contrastada con la Tabla 6 (geocéntricas) y con las coordenadas ITRF93 de NAIF `earth_topo_260814.tf`: coinciden a < 1 m | Verificada. Las alturas son elipsoidales WGS 84 (nota 1 del PDF) |
| Elevación mínima de **recepción** DSN, 6,0° | 301 Rev. P §2.2.2 y §2.2.4 (límite mecánico ≈ 6° en antenas az-el); límites mecánicos medidos 5,923° (34 m) y 5,962° (70 m) en NTRS 20120004035 | Verificada. La máscara de terreno real de cada antena (figuras 10-25) puede ser mayor y **no se modela** |
| Elevación mínima de **transmisión** DSN, 10,1° | 301 Rev. P §2.2.1 (sin transmisión por debajo de 10,1° con ninguna antena a ninguna potencia; genéricos 10,0° baja potencia y 13,5° alta) | Verificada. **No modelado:** alta potencia 13,6° (13,5° + 0,1°) ni DSS-43 a 17,6° (> 20 kW) |
| Posición de New Norcia, Cebreros, Malargüe (ESTRACK) | Kernel NAIF `ndosl_190716_v02.tf` (NDOSL NN1D, CB1D, MG1D), planetodéticas WGS 84 / ITRF93 (https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/ndosl_190716_v02.tf) | Posición publicada |
| Elevación mínima de ESTRACK | No se localizó fuente oficial de ESA (el ESTRACK Facilities Manual no es accesible) | **A verificar.** Se usa 6° **SUPUESTO [sup]**, igualado al DSN; la interfaz avisa; la red no es la de por defecto |
| Near Space Network (NSN) de NASA | NASA anuncia LEGS-1 en White Sands | **No incluida**: ni ubicación, ni elevación, ni fecha de operación verificadas en fuente oficial. No se ha inventado ninguna estación |
| Zonas horarias | Base IANA (`tzdata` en `requirements.txt`) | Goldstone `America/Los_Angeles`, Madrid `Europe/Madrid`, Canberra `Australia/Canberra` |
| Orientación de la Tierra del motor | `pck00011.tpc` (`IAU_EARTH`) | Sin nutación, movimiento polar ni UT1−UTC: 0,072° frente a Horizons |
| Orientación de la Tierra de la validación | `earth_latest_high_prec.bpc` (5,2 MB, hasta 2027-02-09) y `earth_2026_260806_2126_predict.bpc` (19,2 MB) de https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/ , en `data/raw/earth/` (no versionados) | Solo para `tests/test_independent_link.py`; las pruebas se omiten si faltan. Reglas de NAIF: §3 |

Los PCK y el FK de estaciones son kernels NAIF: se aplican las condiciones verificadas del §3. El documento DSN 810-005 es una publicación de JPL/DSN; sus condiciones específicas de reutilización **no se han verificado** (LSI cita y enlaza, no lo redistribuye). Lo que contrastó el enlace frente a esas fuentes está en `docs/validation/revision-enlace.md` y en `docs/metodologia.md` §9.4.

## 9. Datasheets y fuentes de paneles

`docs/validation/datos-paneles.md` registra, parámetro a parámetro, la fuente primaria de cada panel con página (lectura del 14/11/2026): Spectrolab XTJ Prime, Azur Space 3G30-Advanced, Rocket Lab SolAero Z4J+/Z4J/IMM-α, Sharp (silicio), Redwire ROSA y ELSA, Ascent Solar y MiaSolé (CIGS), Lang et al. (Joule 2020, perovskita-silicio) y el informe NASA/JPL D-101316. Los PDF y sus extractos de texto están en `data/raw/datasheets/` (fuera de git: son documentos de sus fabricantes y no se redistribuyen). Condiciones de uso de esos documentos: **a verificar**; LSI solo toma valores numéricos y los atribuye. Niveles de evidencia: `datasheet`, `paper`, `derivado`, `investigación`, `no disponible`.
