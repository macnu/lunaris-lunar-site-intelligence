# Imagen fotográfica del polo sur y coordenadas de las regiones Artemis III

Medido el 14/11/2026. Código: `scripts/fetch_imagery.py` (descarga), `src/lsi/data/imagery.py` (lectura y combinación), `tests/test_imagery.py`. **El motor científico no se ha tocado**: la imagen solo alimenta la visualización 3D. Datos en `data/raw/imagery/` (fuera de git).

## 1. Imagen para Site04 (Shackleton rim), que no está en las 13 regiones SDEM

### Elegida: mosaico controlado promedio LROC NAC del polo sur (`NAC_POLE_SOUTH_CM_AVG`)

| Campo | Valor |
|---|---|
| Fuente oficial | LROC Data Node del PDS (ASU/NASA). Página: https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_POLE_SOUTH_CM_AVG · ficheros: `https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/BROWSE/NAC_POLE/NAC_POLE_SOUTH_CM_AVG/NAC_POLE_SOUTH_CM_AVG_P###S????.PYR.TIF` (redirige a `pds.mcp.nasa.gov`) |
| Cobertura | 84°S–90°S en 40 teselas polares (cuatro bandas de 1,5° desde el polo: 4, 8, 12 y 16 teselas) |
| Resolución | **1 m/píxel nativo** (LROC NAC, 0,5–1,5 m según la imagen). Mosaico PROMEDIO: mezcla imágenes de distinto Sol; no corresponde a una fecha |
| Proyección | Estereográfica polar sur sobre esfera de 1737,4 km. La cabecera trae el CRS con otro nombre; los parámetros coinciden con los del DEM (comprobado con `_check_crs`) |
| Formato | GeoTIFF uint8 en teselas de 256×256 (probado: lectura por ventana con HTTP Range; la compresión de las teselas CM_AVG no se comprobó, la cota de bytes supone sin comprimir). No hay overviews utilizables: se lee a 1 m y se reduce en local |
| Tamaño | Cada tesela es de varios GB (p. ej. los TIF de otros productos NAC_POLE: 2,5–6,6 GB); **no se descarga ninguna entera** |
| Licencia | Los productos «available through the LROC Data Node of the PDS» son de **dominio público**; crédito pedido: «NASA/GSFC/Arizona State University» (o «NASA/GSFC/ASU»). Verificado en https://lroc.im-ldi.com/about/terms (14/11/2026). Las imágenes de la web de LROC, en cambio, tienen copyright; LSI usa solo PDS |
| Cita | Archinal, B., Weller, L., Richie, J., Lee, E., Bennett, K., Speyerer, E., Tyburczy, T. (2023), Controlled High-Resolution LROC NAC Polar Mosaics, LPSC 54, abstract #2333 |

**Qué se descargó.** Una ventana de ±3000 m (6 km × 6 km, 6001×6001 píxeles de 1 m) alrededor del centro de la huella del DEM LOLA de cada sitio, por lecturas con HTTP Range de teselas (pausa de 1,5 s, User-Agent genérico, destino ya resuelto para no repetir redirecciones, parada ante un 429):

| Sitio | Teselas NAC | Recorte | Peticiones |
|---|---|---|---|
| Site04 (principal) | P892S1350, P892S2250 | 18,2 MB (deflate) | 26 |
| Site11 (respaldo) | P892S3150 | 26,2 MB | 39 entre Site11 y Site23 |
| Site23 (respaldo) | P863S0150, P863S3450 | 28,2 MB | (ídem) |

Bytes recibidos: **≈ 110 MB** (cota estimada 123 MB: 6001² píxeles sin comprimir por sitio más el relleno hasta la tesela; GDAL no informa del contador exacto). Muy por debajo de 500 MB. Más 7,95 MB leídos de Zenodo para las regiones (§3).

**Incidente a recordar.** Una primera exploración con ≈ 80 `HEAD` seguidos para listar las teselas hizo que el servidor de NASA (`pds.mcp.nasa.gov`) respondiera **429 con `Retry-After: 3600`**. Se esperó a que se levantara y el script descarga ya con pausas. No lanzar sondeos masivos contra ese servidor.

### Resolución real: lo que la interfaz puede decir

- Cada píxel del recorte mide 1 m, pero **el detalle útil depende de la iluminación**: la imagen es un promedio de pasadas con Sol distinto. La luz y las sombras que se ven NO son las de la fecha simulada.
- `imagery_window` devuelve `px_m` **efectivo** = `max(2·half/n, 1 m)`: nunca presenta más resolución de la nativa. Para una escena de 6 km en 600 px son 10 m/px; la textura SDEM (5 m) es más fina en las regiones que la tienen solo si el recorte cabe en 5 m.
- Zonas sin iluminación: el mosaico trae valores casi negros (< 10/255) en vez de «sin dato» (en Site04 ≈ 4 % del recorte de 6 km; la parte más oscura del interior de Shackleton queda fuera del recorte). El módulo lo avisa en `notes` cuando supera el 5 %. No hay fotografía en sombra permanente (el mosaico PSR estirado que sí la intenta es otro producto, §1.1).
- La posición absoluta es la del control de LROC; **verificado contra el ortomosaico SDEM** (correlación de fase de las dos imágenes a 5 m en 4 km × 4 km): Site23 desfase ≤ 5 m, Site11 ≈ 15 m (3 píxeles de 5 m); Pearson 0,67 → 0,80 y 0,33 → 0,74 tras alinear. La textura NAC del recorte de LSI está en la retícula del DEM, pero puede estar corrida hasta ~15 m respecto al relieve.

### 1.1 Candidatas descartadas

| Candidata | Por qué no |
|---|---|
| `NAC_POLE_PSR_SOUTH(_STRETCH)`: mosaico NAC de regiones en sombra permanente, 80°S–90°S, píxel real 11,74 m (nominal 10 m), uint8, tesela 256 (`.PYR.TIF`, 3,6 GB; `.TIF` 2,7 GB sin teselar) | **Solo cubre PSR**: medido en los recortes de LSI, con dato (>0) en 20,6 % de Site04, 3,6 % de Site11 y **0 %** de Site23. Útil para el interior de Shackleton, no como textura del borde. La versión «stretched» además deforma el brillo |
| Mosaico LROC + ShadowCam de Shackleton (NASA, ago-2023) | Solo un **JPEG sin georreferenciar** (`shadowcam_shackleton_crater_mosaic_072823.jpeg`); la página no da resolución ni licencia. No sirve para textura alineada |
| `NAC_POLE_SOUTH_CM_<lon>_P###S????` (controlados por longitud subsolar, 1 m) | Teselas de 5–20 GB por bin de longitud; el promedio `CM_AVG` cubre lo mismo en una sola capa |
| `NAC_ROI_SHKLTNPKLO1/O2` (ROI Shackleton, 1 m, 16 bits, precisión posicional 5–20 m) | Son de ROI «candidata Artemis III»; no se localizó la URL de su GeoTIFF; `CM_AVG` es suficiente |
| Moon Trek WMTS `LRO_WAC_Mosaic_Global_303ppd_v02` (`trek.nasa.gov/tiles/Moon/EQ/...`) | Equirrectangular de ≈ 100 m/px: inútil en el polo (distorsión y 100 m ≫ 5 m). El capabilities de la variante polar devuelve 404 |
| Quickmap (ASU) | Visor web; no se encontró un servicio de teselas citable y documentado para uso programático |
| Mosaico WAC polar LROC (≈ 100 m/px) | Resolución insuficiente para textura de 5 m; no se descargó |

## 2. API de Python

```python
from lsi.data.imagery import imagery_window, combine_with_sdem
w = imagery_window("Site04", cx_m, cy_m, half_size_m, max_px)   # dict | None
# image uint8 (0 = sin dato) · coverage bool · px_m EFECTIVO (>= 1 m) · x0_m, y0_m (centro del píxel [0,0], fila 0 = norte)
# native_px_m · source · source_url · attribution · fetched · notes
out = combine_with_sdem("Site23", sdem_pack)   # sdem_pack = dict de sdem.terrain_texture_pack (se pasa; no se importa)
# texture uint8 · texture_valid · texture_source (0 nada, 1 SDEM, 2 NAC) · atribución de ambas fuentes
```

`None` ⇒ sin recorte descargado o ventana fuera: el llamador cae al hillshade; nunca se inventa textura. Mostrar `attribution` y `px_m` en la interfaz.

## 3. Regiones candidatas Artemis III y coordenadas

**La lista de 13 que se pidió mezcla dos listas de NASA.** Verificado en NASA:

- **13 regiones, 19/08/2022** (release 22-089, actualizada 08/01/2024): Faustini Rim A, Peak Near Shackleton, Connecting Ridge, Connecting Ridge Extension, de Gerlache Rim 1, de Gerlache Rim 2, de Gerlache-Kocher Massif, Haworth, Malapert Massif, Leibnitz Beta Plateau, Nobile Rim 1, Nobile Rim 2, Amundsen Rim. Cada una de ≈ 15 × 15 km, sitios de 100 m de radio; **sin coordenadas**. Coincide exactamente con los 13 zips SDEM `A3CLR22_*` (el zip `deGerlache_Rim` es el «de Gerlache Rim 1»; identificación por nombre, a verificar).
- **9 regiones, 28/10/2024** (RELEASE24-136): Peak Near Cabeus B, Haworth, Malapert Massif, Mons Mouton Plateau, Mons Mouton, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2, Slater Plain; **sin coordenadas**. Cuatro (Peak Near Cabeus B, Mons Mouton, Mons Mouton Plateau, Slater Plain) no están en la de 2022 ni tienen SDEM. «Cabeus B» a secas no es una región.

**Método.** NASA no publica coordenadas. Cada zip SDEM contiene `GLDMASK_005.tif` (≈ 0,5 MB, retícula de 15 m, solo se leyó eso por HTTP Range); su huella en el plano estereográfico polar sur da el **centro y la caja**, convertidos con `stereo_inverse` (R = 1737,4 km). Total leído de Zenodo: 7 951 064 bytes. La caja es la huella del SDEM (15,99–29,79 km), mayor que los 15 km oficiales: el centro es el de esa caja, **no un punto de aterrizaje**. Confianza: derivada de la huella del SDEM (`aprox` en `sites.json`). Datos completos: `config/artemis_regions.json`; reproducible con `python scripts/fetch_imagery.py --regions --yes`.

| Región | Listas | lat (°) | lon E (°) | Caja (km) | Rasgo con nombre más cercano (gazetteer) | DEM LOLA 5 m de LSI |
|---|---|---|---|---|---|---|
| Amundsen Rim | 2022 | -84,2288 | 69,4429 | 20,0 | Oberbeck, 21 km | no |
| Nobile Rim 2 | 2022, 2024 | -83,9540 | 58,8210 | 20,0 | Wapowski, 32 km | no |
| Haworth | 2022, 2024 | -86,7637 | 337,2214 | 29,8 | Haworth, 34 km | no |
| Faustini Rim A | 2022 | -87,8897 | 89,9978 | 20,0 | Faustini, 23 km | no |
| de Gerlache Rim 2 | 2022, 2024 | -88,2299 | 295,3728 | 20,0 | de Gerlache, 22 km | no |
| Connecting Ridge Extension | 2022 | -89,0324 | 258,0065 | 20,0 | Marvin, 7 km | no |
| Connecting Ridge | 2022 | -89,4632 | 222,5353 | 16,0 | Spudis, 14 km | no |
| Nobile Rim 1 | 2022, 2024 | -85,4381 | 37,3652 | 20,0 | Masina, 13 km | no |
| Peak Near Shackleton | 2022 | -88,8112 | 123,6879 | 16,0 | Slater, 24 km | **no** (Site04 es otro punto: Shackleton rim, -89,67°) |
| de Gerlache Rim 1 | 2022 | -88,6832 | 292,0719 | 16,0 | de Gerlache, 16 km | **sí: Site11** (misma huella, IoU > 0,9) |
| Leibnitz Beta Plateau | 2022 | -85,4265 | 31,7399 | 16,0 | Dawa, 1 km | no |
| Malapert Massif | 2022, 2024 | -85,9948 | 359,7642 | 21,0 | Mons Malapert, 3 km | **sí: Site23** (misma huella, IoU > 0,9) |
| de Gerlache-Kocher Massif | 2022 | -85,8295 | 243,6795 | 20,0 | Mons Kocher, 12 km | no |
| Peak Near Cabeus B, Mons Mouton, Mons Mouton Plateau, Slater Plain | solo 2024 | **sin coordenadas** | | | pista (no es la región): Cabeus B −82,26°/305,42°; Mons Mouton −84,6°/31,0° (también para la meseta); Slater −88,08°/111,29° | no |

Lectura: «rasgo más cercano» solo orienta; las regiones son bordes y macizos, no centros de cráter, por eso distan decenas de km. Cabeus B (−82,3°) queda fuera de «a menos de 6° del polo» de NASA: la pista de Peak Near Cabeus B es dudosa. Con SDEM (otro agente, `fetch_sdem.py`): Malapert Massif, de Gerlache Rim 1 y Peak Near Shackleton; el SDEM de las otras 10 regiones no se ha descargado.

`config/sites.json`: las 13 entradas `artemis3_*` pasan de `null` a las coordenadas anteriores (`confianza: aprox`, fuente y nota); se añaden 4 entradas con `null` para las regiones solo de 2024 (36 entradas, 32 con coordenadas ⇒ el buscador pasa de 9106 a 9119 lugares). Cambio en tests: `test_catalog` 32 → 36 entradas y `test_gazetteer` 19 → 32 sitios y `9087 + 19` → `9087 + 32` (consecuencia directa).
