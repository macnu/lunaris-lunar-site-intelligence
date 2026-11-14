# Fuentes de datos

Todo dato externo se descarga con los scripts de `scripts/`; ninguno va al repositorio (`.gitignore`: `data/raw/`, `data/processed/`, `data/validation_raw/`, `kernels/*` salvo `kernels/README.md`). Tamaños y hashes medidos el 14/11/2026 sobre los ficheros de este equipo; los tamaños son **MB decimales** (10⁶ bytes) salvo que se diga MiB. «Condiciones de uso» distingue lo **verificado en la fuente** de lo **a verificar**.

**Hashes.** `config/data_manifest.json` guarda el SHA-256 y los bytes de 20 ficheros (12 capas de los 3 DEM de 5 m, el DEM de 80 m, los 6 kernels y el zip del gazetteer). `python scripts/data_manifest.py` los verifica (sale con 1 si algo no coincide; el 14/11/2026 dio `ok` en los 20), y `fetch_data.py` y `fetch_gazetteer.py` lo llaman tras cada descarga. `--regenerate` reescribe el manifiesto: es una decisión consciente (un desajuste es un fichero corrupto o un origen reeditado). Los datos añadidos después llevan su propio registro en `data/raw/`: `sdem/MANIFEST.json`, `imagery/MANIFEST.json`, `diviner/SHA256SUMS.json`, `psr/SHA256SUMS.json`, `illum_ref/SHA256SUMS.json` y `data/validation_raw/manifest.json` (§10-§17).

**Lo que hay en disco** (`du`, 14/11/2026): núcleo (DEM de 5 m, 80 m, kernels, gazetteer) ≈ 0,84 GB; SDEM 329,7 MB; imagen LROC NAC 94,1 MB; Diviner 154,1 MB; PSR 3,8 MB; iluminación publicada 117,0 MB; DEM Site01 163,9 MB; documentos de verificación (datasheets 27,1 MB, estaciones 21,9 MB, PCK de la Tierra y DSN 301P 27,1 MB); cachés de `data/processed/` ≈ 0,56 GB (el mapa de idoneidad, 510,5 MB, es la parte grande).

> Nota sobre licencias. Verificado en la política oficial (14/11/2026): NASA, «generalmente no sujeto a copyright en EE. UU.», con la salvedad de que el logotipo e identificadores no son de dominio público y de que hay material de terceros con copyright; pide reconocer a NASA como fuente (https://www.nasa.gov/nasa-brand-center/images-and-media/). USGS: sus datos e información son de dominio público de EE. UU.; pide crédito; hay material de terceros marcado con copyright (https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits). NAIF: ver §3 (verificada). Es **política general**: las páginas de PGDA (producto 78 y su README) y del Gazetteer **no declaran en el texto leído condiciones propias**, y la nomenclatura es trabajo del IAU WGSN. Por eso las condiciones específicas de PGDA 78/90, del gazetteer, de Horizons, del documento DSN 810-005 y de los datasheets de fabricantes siguen **a verificar** (las de NAIF sí están verificadas, §3). Excepciones **verificadas** en esta ronda: el SDEM de PGDA 104 (registro de Zenodo) declara **CC-BY-4.0** (§10) y los productos del LROC Data Node del PDS son de **dominio público** con crédito pedido (§11). LSI atribuye las fuentes y no redistribuye ningún dato.

## 1. DEM LOLA de 5 m (sitios)

| Campo | Valor |
|---|---|
| Producto | PGDA producto 78, DEM LOLA de 5 m/píxel de los sitios de aterrizaje del polo sur (`Site*_final_adj_5mpp_*`) |
| Página | https://pgda.gsfc.nasa.gov/products/78 · README: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README |
| URLs de datos | `https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/<Site>/<Site>_final_adj_5mpp_<capa>.tif` |
| Sitios usados | Site04 (Shackleton, `data/raw/shackleton/`), Site11 (de Gerlache, `data/raw/de_gerlache/`), Site23 (Mons Malapert, `data/raw/malapert/`). La numeración sigue a Mazarico et al. (2011) |
| Capas | `surf` (elevación, m), `slp` (pendiente, °; diferencia central con baseline de 10 m), `ldec` (conteo de retornos LOLA), `toterr` (incertidumbre vertical total, m) |
| Versión | Producto «final_adj» tal como se sirve; fecha de publicación **a verificar** |
| Tamaño | Site04: 4 ficheros de 40 980 7xx bytes (≈ 41,0 MB, 163,9 MB en total); Site11: igual; Site23: 4 de 70 586 8xx bytes (≈ 70,6 MB, 282,3 MB en total) |
| Hash | Las 12 capas, con bytes y SHA-256 completos, en `config/data_manifest.json` (verificadas el 14/11/2026). `surf`: Site04 `38ff70db…ce758`, Site11 `58f3372c…136e5`, Site23 `12d280a5…c94cf`; `data/processed/dem_hash.json` guarda lo mismo para la caché |
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
| Tamaño | 189 158 392 bytes (189,2 MB; 180,4 MiB) |
| Hash | SHA-256 `82030dcb…beee5a` en `config/data_manifest.json` |
| Condiciones de uso | No verificadas (ver nota). **A verificar** |
| Cómo se usa | (1) Completa el horizonte más allá del recorte de 5 m (±304 km alrededor del polo, mismo CRS y marco vertical). (2) **Modo `FAR_FIELD`:** única fuente del horizonte de cualquier punto de 80°S al polo fuera de los tres recortes (paso radial de 40 m; suelo del observador tomado de este DEM). (3) Base del «Mapa del polo sur» (sombreado a ≈ 480 m por celda y ventanas de zoom). Al norte de 80°S sigue la esfera lisa |
| Advertencia | Difiere del 5 m (media −0,15 m, RMS 1,2 m en el solape de Site04; en el polo ~7 m). En modo `FAR_FIELD` el horizonte difiere del de 5 m **0,68° RMS y hasta 5,8°, con sesgo −0,25° (optimista)** y el veredicto por puertas no terrenales cambia en el 10 % de los puntos (`docs/validation/horizonte-campo-lejano.md`, 120 puntos) |

## 3. Kernels SPICE (NAIF)

Seis kernels en `kernels/` (18,7 MB); procedencia, cobertura y hash de cada uno en [`kernels/README.md`](../kernels/README.md) y en `config/data_manifest.json`. Servidor: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/.

Condiciones de uso (**verificadas** en https://naif.jpl.nasa.gov/naif/rules.html el 14/11/2026): los kernels «pueden ser descargados y usados por cualquiera»; su redistribución se permite **si no se han modificado** (si se modifican hay que cambiar la atribución y el nombre); NAIF **solicita** reconocer el uso de SPICE y de los recursos NAIF/PDS. LSI no redistribuye los kernels (se descargan) y los agradece en el README y en la pantalla «Acerca de».

## 4. Gazetteer lunar (USGS / IAU)

| Campo | Valor |
|---|---|
| Producto | Gazetteer of Planetary Nomenclature, Moon, puntos centrales (IAU WGSN) |
| Página | https://planetarynames.wr.usgs.gov/ |
| URL de datos | https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.zip |
| Versión | Descarga de 2026 (la fecha exacta no se registra); el zip es el vigente en el servidor. Su SHA-256 (`bcb1a37a…7606b`) está en `config/data_manifest.json`: si USGS reedita nombres, `fetch_gazetteer.py` avisa y dice cómo regenerar el manifiesto. **A verificar** si se quiere fijar versión |
| Tamaño | zip 23 845 070 bytes; `.dbf` 23 481 450; `.shp` 254 536 |
| Resultado | `data/processed/gazetteer.csv` (1,56 MB) y `.parquet` (0,50 MB): **9087 rasgos** (7064 *Satellite Feature*, 1615 *Crater*, 112 *Rima*, 81 *Astronaut-named features*, 58 *Mons*, …) |
| Condiciones de uso | No declaradas en el texto leído. El sitio indica que el trabajo se realiza en nombre del IAU WGSN. **A verificar** |
| Cómo se usa | El buscador, que añade en memoria los **32 sitios** con coordenadas de `config/sites.json` (3 zonas con DEM, 16 misiones y 13 regiones Artemis III aproximadas): **9119 lugares** en total, con 56 alias es/en de `config/aliases.json`; también los nombres del «Mapa del polo sur» y del mapa topográfico del Explorador. Posición = centro del rasgo (longitud ya este-positiva 0–360), no un punto de aterrizaje: aviso `GAZETTEER_COORDS_APPROX` |
| Seguridad | `fetch_gazetteer.py` rechaza entradas del zip con rutas y valida que existan las columnas esperadas y que lat/lon estén en rango |

## 5. JPL Horizons (solo contraste)

https://ssd.jpl.nasa.gov/horizons/ (API `https://ssd.jpl.nasa.gov/api/horizons.api`). No se descarga ningún dato en la app. Se usó el 14/11/2026 para contrastar azimut/elevación aparentes de Sol y Tierra (24 casos; diferencia máxima 0,05″, `docs/science/luna-spice-sitios.md` §2) y la elevación de la Luna vista desde DSS-14/-63/-43 (`CENTER=coord@399`, `QUANTITIES=4`, AIRLESS; ver §8). Horizons usa efemérides DE441; LSI, DE421. Condiciones de uso: **a verificar**. **Aviso:** `scripts/fetch_horizons_stations.py` **no tiene `--help`**: ejecutarlo con cualquier argumento llama a la API de Horizons y reescribe `tests/golden/horizons_stations_2026-12.json`.

## 6. Catálogos de LSI

| Fichero | Contenido | Estado |
|---|---|---|
| `config/sites.json` | **36 entradas, 32 con coordenadas**: 3 zonas con DEM y 16 misiones (19) más 13 regiones Artemis III `aprox`; las 4 regiones que solo figuran en la lista de 2024 (Peak Near Cabeus B, Mons Mouton, Mons Mouton Plateau, Slater Plain) siguen en `null` y no son buscables | Coordenadas de misiones tomadas de la lista de Wikipedia de objetos artificiales en la Luna (fuente secundaria). Las de las 13 regiones **no las publica NASA**: son el centro de la huella del SDEM (§15), no un punto de aterrizaje |
| `config/artemis_regions.json` | 17 regiones (13 de 2022 con coordenadas derivadas y caja; 4 solo de 2024, sin ellas), con zip SDEM, rasgo cercano del gazetteer y confianza | Reproducible con `python scripts/fetch_imagery.py --regions --yes` (§15) |
| `config/panels.json` | 8 paneles: 5 `respaldado` (3J ×3, 4J, ROSA) y 3 `experimental_sin_datasheet` (silicio, CIGS, perovskita-silicio, con banda de incertidumbre); 4 montajes; perfiles de misión; `areal_power_w_m2_am0` de cada panel (η × 1361 W/m²) | Cada parámetro lleva etiqueta de confianza (`publicado`, `estimado`, `a_verificar`…); registro fuente a fuente en `docs/validation/datos-paneles.md` (14/11/2026); varias fuentes son secundarias |
| `config/ground_stations.json` | 6 estaciones (DSS-14, DSS-63, DSS-43 verificadas; NNO-1, CEB-1, MLG-1 de ESTRACK con elevación mínima SUPUESTA y, en CEB-1 y NNO-1, la máscara máxima leída de la figura de ESA), 3 redes (DSN, ESTRACK, DSN+ESTRACK), sentidos de enlace (recepción 6,0°, transmisión 10,1°), `networks_not_available.NSN` y `stations_unverified` (WS1, LEGS-1, LEGS-2, Usuda: fuera de toda red; ninguna función las carga) | Posiciones y elevaciones de DSN **verificadas** en DSN 810-005/301 Rev. P; ESTRACK: coordenadas NAIF y elevación **a verificar [sup]**; NSN **sin estaciones** (§8) |
| `config/aliases.json` | 56 alias es/en → nombre oficial, palabras y zonas del buscador | Cada valor debe existir en el gazetteer o en `sites.json` (lo comprueba `tests/test_gazetteer.py`) |
| `config/simulation.json` | Parámetros del motor | Etiquetas `[pub]`, `[cal]`, `[ver]`, `[sup]` en `_etiquetas` |

## 7. Literatura usada para validar

Mazarico et al. 2011 (Icarus 211, 1066-1081); Barker et al. 2021 (Planetary and Space Science 203, 105119); Gläser et al. 2014 (Icarus 243, 78-90); Mazarico, Barker y Nicholas 2018 (IllumNG). Las 38 pruebas de `tests/test_luna_cases.py` usan el DEM de Site01 (§17) y **ya se ejecutan** (38 passed el 14/11/2026). Estado de lectura de cada una en `docs/validation/validacion-luna.md` §2. No leídos y **a verificar**: Mazarico 2011 completo (Table 3), Gläser et al. 2017, Bussey et al. 2010, Speyerer y Robinson 2013.

## 8. Estaciones terrestres, orientación de la Tierra y enlace

Fuente de `config/ground_stations.json`. Solo figuran números verificados en fuente oficial; lo demás queda «a verificar» y la estación no se usa por defecto. Verificado el 14/11/2026.

| Dato | Fuente | Estado |
|---|---|---|
| Posición WGS 84 de DSS-14, DSS-63, DSS-43 | DSN 810-005, módulo 301 «Coverage and Geometry», Rev. P (22/05/2026), Tabla 5 (https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf; copia local `data/raw/earth/301P.pdf`, no versionada). Contrastada con la Tabla 6 (geocéntricas) y con las coordenadas ITRF93 de NAIF `earth_topo_260814.tf`: coinciden a < 1 m | Verificada. Las alturas son elipsoidales WGS 84 (nota 1 del PDF) |
| Elevación mínima de **recepción** DSN, 6,0° | 301 Rev. P §2.2.2 y §2.2.4 (límite mecánico ≈ 6° en antenas az-el); límites mecánicos medidos 5,923° (34 m) y 5,962° (70 m) en NTRS 20120004035 | Verificada. La máscara de terreno real de cada antena (figuras 10-25) puede ser mayor y **no se modela** |
| Elevación mínima de **transmisión** DSN, 10,1° | 301 Rev. P §2.2.1 (sin transmisión por debajo de 10,1° con ninguna antena a ninguna potencia; genéricos 10,0° baja potencia y 13,5° alta) | Verificada. **No modelado:** alta potencia 13,6° (13,5° + 0,1°) ni DSS-43 a 17,6° (> 20 kW) |
| Posición de New Norcia, Cebreros, Malargüe (ESTRACK) | Kernel NAIF `ndosl_190716_v02.tf` (NDOSL NN1D, CB1D, MG1D), planetodéticas WGS 84 / ITRF93 (https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/ndosl_190716_v02.tf) | Posición publicada |
| Elevación mínima de ESTRACK | ESA publica una **máscara de horizonte por acimut**, no un escalar, y solo para CEB-1 y NNO-1 (ESTRACK Facilities Manual, 2008; §16). Máximo leído a ojo de la figura: CEB-1 ≈ 5,5°, NNO-1 ≈ 8,4–8,5° (±0,3°, **derivado**). MLG-1 no figura | **A verificar.** Se sigue usando 6° **SUPUESTO [sup]**, igualado al DSN: es optimista para NNO-1 en un sector de ≈ 60° de acimut y algo pesimista para CEB-1. **La máscara por acimut no está implementada**; la interfaz avisa; la red no es la de por defecto |
| Near Space Network (NSN) de NASA | LEGS-1 y LEGS-2: coordenadas en un folleto de NASA (LEGS Brochure r20); WS1 en el kernel NAIF NDOSL y en el NEN User's Guide (§16) | **No incluida**: hay posiciones publicadas, pero **ninguna elevación mínima ni máscara de NSN/LEGS** en documento oficial, y LEGS-1 es capacidad futura. No se crea la red `NSN` ni `DSN+NSN`; no se ha inventado ninguna estación |
| Zonas horarias | Base IANA (`tzdata` en `requirements.txt`) | Goldstone `America/Los_Angeles`, Madrid `Europe/Madrid`, Canberra `Australia/Canberra` |
| Orientación de la Tierra del motor | `pck00011.tpc` (`IAU_EARTH`) | Sin nutación, movimiento polar ni UT1−UTC: 0,072° frente a Horizons |
| Orientación de la Tierra de la validación | `earth_latest_high_prec.bpc` (5,2 MB, hasta 2027-02-09) y `earth_2026_260806_2126_predict.bpc` (19,2 MB) de https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/ , en `data/raw/earth/` (no versionados) | Solo para `tests/test_independent_link.py`; las pruebas se omiten si faltan. Reglas de NAIF: §3 |

Los PCK y el FK de estaciones son kernels NAIF: se aplican las condiciones verificadas del §3. El documento DSN 810-005 es una publicación de JPL/DSN; sus condiciones específicas de reutilización **no se han verificado** (LSI cita y enlaza, no lo redistribuye). Lo que contrastó el enlace frente a esas fuentes está en `docs/validation/revision-enlace.md` y en `docs/metodologia.md` §9.4.

## 9. Datasheets y fuentes de paneles

`docs/validation/datos-paneles.md` registra, parámetro a parámetro, la fuente primaria de cada panel con página (lectura del 14/11/2026): Spectrolab XTJ Prime, Azur Space 3G30-Advanced, Rocket Lab SolAero Z4J+/Z4J/IMM-α, Sharp (silicio), Redwire ROSA y ELSA, Ascent Solar y MiaSolé (CIGS), Lang et al. (Joule 2020, perovskita-silicio) y el informe NASA/JPL D-101316. Los PDF y sus extractos de texto están en `data/raw/datasheets/` (fuera de git: son documentos de sus fabricantes y no se redistribuyen). Condiciones de uso de esos documentos: **a verificar**; LSI solo toma valores numéricos y los atribuye. Niveles de evidencia: `datasheet`, `paper`, `derivado`, `investigación`, `no disponible`.

## 10. SDEM de 5 m y ortomosaico LROC NAC (PGDA producto 104)

Detalle medido en [`docs/validation/datos-sdem.md`](validation/datos-sdem.md). Solo alimenta la **visualización 3D**, y la consume el visor de la rama `feat/lunaris-ui`: `main` tiene el módulo (`lsi.data.sdem`) y la descarga, pero su interfaz no lo pinta. El horizonte, la pendiente y el score siguen usando el DEM LOLA.

| Campo | Valor |
|---|---|
| Producto | *Shape-from-Shading Products for the 2022 Artemis III Candidate Landing Regions*, NASA PGDA, producto 104 |
| Página | https://pgda.gsfc.nasa.gov/products/104 |
| Archivo y versión | Zenodo, doi 10.5281/zenodo.17954508, **versión 1.0.0** (https://zenodo.org/records/17954508); README de cada región fechado 2025-12-17 (S. Bertone, creador; R. A. Beyer, revisor) |
| Licencia | **CC-BY-4.0** (verificada: la declara el registro de Zenodo y el `MANIFEST.json` local) |
| **Cita que pide la página** | Bertone, S., McKenna, T. E., Barker, M. K., Mazarico, E., Beyer, R. A., and Petro, N., *Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading*, The Planetary Science Journal, doi: 10.3847/PSJ/ae5b70. **La página de PGDA no da el año de este artículo** (el README de cada región escribe «Bertone S. et al. (2026) … doi:XYZ», un marcador sin resolver): LSI cita tal como figura y no añade año. |
| Cita del archivo de datos | Bertone, S., Barker, M., Mazarico, E., McKenna, T., and Petro, N., 2025, *Archived geospatial products for manuscript «Enhanced Topography Models for selected Lunar South Pole regions with Shape-from-Shading»*, Zenodo, doi: 10.5281/zenodo.17954508. La página cita además a Barker et al. (2021, Planetary and Space Science 203, 105119), Barker et al. (2023, Planetary Science Journal 4, 183) y Alexandrov y Beyer (2018, Earth and Space Science 5, 652) |
| Qué cubre | Hay un zip por cada una de las 13 regiones Artemis III; los tres que usa LSI suman 4,9 GB y no se descargan enteros. LSI usa tres: **Malapert Massif** (= Site23, 21×21 km), **de Gerlache Rim 1** (= Site11, 16×16 km) y **Peak Near Shackleton** (A308, 16×16 km, **no** coincide con Site04). **Site04 (Shackleton, borde) no tiene SDEM.** Rejilla de 5 m idéntica a la del recorte LOLA en Site23 y Site11 |
| Qué descarga LSI | `python scripts/fetch_sdem.py --yes`: lee los directorios centrales por HTTP Range y extrae solo `README.txt` y las capas `GLDOMOS_005` (ortomosaico), `GLDELEV_005`, `GLDMASK_005`, `GLDHILL_005_315_45` y `GLDDIFF_005`; comprueba longitud, CRC32 y que no sea HTML |
| Tamaño | 18 ficheros en **329,7 MB** en disco (Malapert 144,9 MB, de Gerlache 92,9 MB, Peak Near Shackleton 91,9 MB); 329 343 711 B leídos de 4,9 GB. SHA-256 por fichero, miembro del zip, URL y fecha en `data/raw/sdem/MANIFEST.json` |
| Advertencias | El ortomosaico es de **máxima iluminación** (por píxel, el valor más brillante de las imágenes NAC): no es una foto de una hora, no tiene las sombras de una fecha y no es radiometría absoluta. Su retícula está **desplazada medio píxel (2,5 m)** respecto al SDEM y trae una fila y columna más (se interpola siempre); `GLDMASK` está a 15 m y no a 5 m. En de Gerlache el observador por defecto cae en sombra permanente (sin imagen). El SDEM no cambia la pendiente a escala de decenas de metros salvo en parches (< 0,25 % del recorte): **no retira** la limitación de la resolución efectiva |

## 11. Mosaico LROC NAC del polo sur, promedio de pasadas (imagen de Site04)

Detalle en [`docs/validation/datos-imagen-artemis.md`](validation/datos-imagen-artemis.md). Solo para la visualización 3D; como el SDEM, la consume el visor de la rama `feat/lunaris-ui` (`main` tiene `lsi.data.imagery` y la descarga, pero su interfaz no lo pinta).

| Campo | Valor |
|---|---|
| Producto | `NAC_POLE_SOUTH_CM_AVG`, mosaico controlado **promedio** LROC NAC del polo sur (84°S-90°S, 40 teselas), LROC Data Node del PDS (ASU/NASA) |
| Páginas y URL | https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG · ficheros `https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_SOUTH_CM_AVG/NAC_POLE_SOUTH_CM_AVG_P###S????.PYR.TIF` (redirige a `pds.mcp.nasa.gov`) |
| Versión | Archinal et al. (2023); sin número de versión en la página |
| Licencia | **Dominio público** (los productos «available through the LROC Data Node of the PDS»); crédito pedido: «NASA/GSFC/Arizona State University». Verificado en https://lroc.im-ldi.com/about/terms el 14/11/2026. Las imágenes de la web de LROC tienen copyright: LSI solo usa PDS |
| Cita | Archinal, B., Weller, L., Richie, J., Lee, E., Bennett, K., Speyerer, E., Tyburczy, T. (2023), *Controlled High-Resolution LROC NAC Polar Mosaics*, LPSC 54, abstract #2333 |
| Resolución | **1 m/píxel nativo** (NAC 0,5-1,5 m), pero es un **promedio de pasadas con Sol distinto**: la luz y las sombras que se ven no son las de la fecha simulada. El módulo nunca presenta más resolución que la nativa (`px_m` efectivo ≥ 1 m) |
| Qué descarga LSI | `python scripts/fetch_imagery.py --sites Site04 Site11 Site23 --yes`: una ventana de ±3 km (6001×6001 px) alrededor del centro de cada recorte, leída por HTTP Range; ninguna tesela entera (cada una pesa varios GB). Sin `--yes` solo imprime el plan |
| Tamaño | 3 recortes en **94,1 MB** en disco (Site04 18,2 MB, Site11 26,2 MB, Site23 28,2 MB, más 21,5 MB de máscaras auxiliares); ≈ 110 MB recibidos (cota estimada). SHA-256 en `data/raw/imagery/MANIFEST.json` |
| Advertencias | La posición es la del control de LROC; frente al ortomosaico SDEM la textura NAC puede estar **corrida hasta ~15 m** (Site11) o ≤ 5 m (Site23). Las zonas sin luz salen casi negras, no «sin dato». Un sondeo con ≈ 80 `HEAD` seguidos provocó un **429 con `Retry-After: 3600`** de `pds.mcp.nasa.gov`: el script espera 1,5 s entre peticiones; no lance sondeos masivos |

## 12. Temperatura de superficie: LRO Diviner (Williams et al. 2019)

Detalle en [`docs/validation/datos-termico-psr.md`](validation/datos-termico-psr.md). Contexto y capa del mapa: **no entra en el motor ni en `panels.json`**.

| Campo | Valor |
|---|---|
| Producto | Mapas estacionales del polo sur `polar_south_80_{summer,winter}_{avg,max,min}-float.tif` (6 ficheros) |
| URL | http://luna1.diviner.ucla.edu/~jpierre/diviner/level4_polar/additional_maps/ (descripción en `.../level4_polar/aareadme.txt`); datos de base en el PDS Geosciences Node, bundle `urn:nasa:pds:lro_diviner_derived1` |
| Versión | Radiancias nadir del RDR del 2009-07-05 al 2019-02-17; «summer»/«winter» = latitud subsolar por encima/por debajo del ecuador (no son estaciones del hemisferio sur) |
| Licencia | La página no declara condiciones; datos de la misión NASA LRO (política general). **A verificar** |
| Cita | Williams, J.-P., Greenhagen, B. T., Paige, D. A., Schorghofer, N., Sefton-Nash, E., Hayne, P. O., Lucey, P. G., Siegler, M. A., Aye, K.-M. (2019), J. Geophys. Res. Planets 124, 2505-2521, doi:10.1029/2019JE006028 |
| Qué cubre | Temperatura de brillo **bolométrica** del suelo (máxima, mínima y media del ciclo diurno), 80°S-90°S, **240 m/px** (2533×2533, ±304 km), misma proyección que el DEM. Es temperatura del regolito, **no** de un panel |
| Tamaño | 6 × 25 686 193 B = **154 117 158 B (154,1 MB; 147 MiB)**. SHA-256 en `data/raw/diviner/SHA256SUMS.json` |
| Descarga | `python scripts/fetch_thermal_psr.py --only diviner` (sin `--only` baja las tres familias; `--help` no descarga; reanudable; rechaza HTML con código 200 y todo fichero de más de `--max-mb`, 500 por defecto) |
| Advertencias | Es **estacional** (dos épocas), no la temperatura de una fecha. «Media» = media de los dos promedios con pesos iguales (aproximación). Temperatura media de los TOP-1: 139-148 K; máxima 229-240 K |

## 13. Regiones permanentemente sombreadas (PSR): polígonos de Mazarico et al. (2011)

| Campo | Valor |
|---|---|
| Producto | `LOLA_PSR_75S_120M_82S_060M_5KM2_FINAL.shp` dentro de `NAC_POLE_PSR_SOUTH.ZIP` (polígonos de las PSR de Mazarico et al. 2011, digitalizados por LROC/ASU) |
| URL | https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_PSR_SOUTH/NAC_POLE_PSR_SOUTH.ZIP (página: https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_PSR_SOUTH) |
| Versión | Atlas LROC PSR (Brown et al. 2022); sin número de versión |
| Licencia | La página no declara condiciones; pide citar a Brown et al. (2022). **A verificar** (la política de dominio público del LROC Data Node, §11, es general; no se ha comprobado para este producto) |
| Cita | Brown, H. M., Boyd, A. K., Cisneros, E., Sonke, A., Huft, A., Robinson, M. S. (2022), *LROC PSR Atlas and PSR Mosaics*, Lunar Polar Volatiles Conf., abstract 5033; Mazarico et al. (2011), Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030 |
| Qué cubre | **653 polígonos de más de 5 km²**, de 75°S a 90°S (horizonte calculado con DTM polares de 60 y 120 m/px), 157 793 segmentos. Las PSR menores y los micro-PSR no están |
| Tamaño | ZIP 1 121 858 B + léeme 6283 B; en disco 3,8 MB. SHA-256 en `data/raw/psr/SHA256SUMS.json` |
| Descarga | `python scripts/fetch_thermal_psr.py --only psr` |
| Advertencia | Una PSR publicada es sombra permanente en un ciclo de **18,6 años**, a nivel de superficie y con un DTM de 60-120 m; LSI simula un periodo concreto con un observador a 2 m (§12 y `docs/limitaciones.md` §4). Úsese como contexto, no como máscara de iluminación |

## 14. Iluminación media publicada (PGDA producto 69, AVGVISIB)

Detalle en [`docs/validation/contraste-iluminacion-publicada.md`](validation/contraste-iluminacion-publicada.md).

| Campo | Valor |
|---|---|
| Producto | PGDA producto 69 «Lunar Polar Illumination» (PDS: GDRVIS, `LRO-L-LOLA-4-GDR-V1.0`), mapas de **iluminación media del Sol** |
| URL | https://pgda.gsfc.nasa.gov/products/69 · datos en https://pgda.gsfc.nasa.gov/data/MoonIllumination/ · PDS: https://ode.rsl.wustl.edu/moon/pagehelp/Content/Missions_Instruments/LRO/LOLA/GDR/GDRVIS.htm |
| Ficheros y versión | `AVGVISIB_85S_060M_201608.TIF` (≥ 85°S, **60 m/px**, 33 994 464 B) y `AVGVISIB_75S_120M_201608.TIF` (≥ 75°S, 120 m/px, 83 052 039 B); «201608» = versión de agosto de 2016. Los enlaces COG de la página devuelven HTML con código 200: el script los evita |
| Licencia | La página no declara condiciones; pide citar a Mazarico et al. (2011). **A verificar** |
| Cita | Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011), *Illumination conditions of the lunar polar regions using LOLA topography*, Icarus 211, 1066-1081, doi:10.1016/j.icarus.2010.10.030 |
| Qué mide | Fracción media visible del disco solar «averaged over hourly timesteps spanning 18.6 years»; **superficie, sin altura de observador**; disco finito. GeoTIFF int16, valor = DN × 4·10⁻⁵ |
| Tamaño | **117 046 503 B (117,0 MB; 112 MiB)**. SHA-256 en `data/raw/illum_ref/SHA256SUMS.json` |
| Descarga | `python scripts/fetch_thermal_psr.py --only illum_ref` |
| Uso | Contraste del motor y capa del mapa del polo. No hay tabla publicada por altura de observador para Site04, 11 y 23; la Table 3 de Mazarico 2011 no se ha leído |

## 15. Regiones candidatas Artemis III y sus coordenadas

NASA publica **dos listas distintas**, ambas **sin coordenadas**: 13 regiones (19/08/2022, release 22-089, actualizada 08/01/2024) y 9 (28/10/2024, RELEASE24-136). Cuatro de la de 2024 (Peak Near Cabeus B, Mons Mouton, Mons Mouton Plateau, Slater Plain) no están en la de 2022 ni tienen SDEM. Fuentes: https://www.nasa.gov/news-release/nasa-identifies-candidate-regions-for-landing-next-americans-on-moon/ y https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/.

**Las coordenadas de LSI son aproximadas y derivadas, no publicadas**: son el centro de la caja (15,99-29,79 km, mayor que los 15 km oficiales) que ocupa cada `GLDMASK_005.tif` del SDEM, leído por HTTP Range (7 951 064 B de Zenodo) y convertido con `stereo_inverse`. Confianza `aprox` (±~5 km respecto al centro nominal, a verificar). **No son puntos de aterrizaje.** Las 13 están en `config/sites.json` y `config/artemis_regions.json`; las 4 solo de 2024 quedan **sin coordenadas** (`null`). Dos coinciden con recortes de LSI (Malapert Massif = Site23, de Gerlache Rim 1 = Site11, IoU > 0,9); Peak Near Shackleton **no** es Site04. Se reproduce con `python scripts/fetch_imagery.py --regions --yes`.

## 16. Estaciones terrestres adicionales (búsqueda del 14/11/2026)

Detalle y páginas en [`docs/validation/estaciones-adicionales.md`](validation/estaciones-adicionales.md); los documentos descargados están en `data/raw/stations_docs/` (fuera de git). Regla: solo entra en una red lo que tiene posición **y** elevación mínima verificadas.

| Estación / red | Posición | Elevación mínima | Estado |
|---|---|---|---|
| ESTRACK CEB-1 (Cebreros) | verificada (ESTRACK Facilities Manual, ESA, 2008, Tabla 2 = NAIF a < 1 m) | **máscara por acimut**, máx. ≈ 5,5° (derivada de la figura 7) | red ESTRACK con 6° [sup] |
| ESTRACK NNO-1 (New Norcia) | verificada (EFM Tabla 8 = NAIF a < 1 m) | **máscara por acimut**, máx. ≈ 8,4-8,5° (derivada, figura 35); supera 6° entre ≈ 175° y 235° de acimut | red ESTRACK con 6° [sup] |
| ESTRACK MLG-1 (Malargüe) | NAIF NDOSL | no localizada (no está en el EFM de 2008) | red ESTRACK con 6° [sup] |
| NASA WS1 (White Sands, 18,3 m) | NAIF NDOSL `WS1S`; NEN User's Guide §9.2 | **a verificar** | fuera de redes |
| NASA LEGS-1 (White Sands, 20 m) / LEGS-2 (Matjiesfontein, «TBD») | lat/lon en el folleto LEGS r20 (sin altura) | **a verificar** (solo rango mecánico 0-90°) | fuera de redes; LEGS es capacidad futura (NSN User's Guide §3.4.1) |
| JAXA Usuda 64 m | página JAXA/ISAS | a verificar | fuera de redes |
| IDSN, KSAT Lunar, CNSA | sin fuente oficial hallada | a verificar | no incluidas |

La copia del EFM que se leyó es de un tercero (el documento es de ESA). Los máximos de las máscaras se leyeron a ojo de la figura (±0,3°): son «derivados». **La máscara por acimut no está implementada**: los resultados de ESTRACK no cambian.

## 17. DEM LOLA de 5 m de Site01 (Connecting Ridge), solo para validar

| Campo | Valor |
|---|---|
| Producto | PGDA producto 78, `Site01_final_adj_5mpp_{surf,slp,ldec,toterr}.tif` (https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/) |
| Licencia | Igual que el §1: no declarada en la página ni en el README; **a verificar** |
| Tamaño | 4 ficheros de ≈ 41,0 MB: **163,9 MB**. Tamaño, firma TIFF (no HTML) y SHA-256 en `data/validation_raw/manifest.json` (`surf` `3ba7b97c…747e`) |
| Descarga | `python scripts/fetch_validation_data.py --yes` (sin `--yes` solo hace un HEAD por capa) → `data/validation_raw/site01/`, fuera de git |
| Para qué | Las **38 pruebas contra la literatura** de `tests/test_luna_cases.py` (Barker 2021, Gläser 2014): con el DEM puesto dieron **38 passed, 0 skipped** el 14/11/2026 (`docs/validation/validacion-luna.md` §4). El motor no lo usa; Site01 no está en la app |
