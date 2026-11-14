# Coordenadas de las regiones candidatas de Artemis III: registro de fuentes

Medido el 14/11/2026. Datos: `config/artemis_regions.json` (principal y auxiliares) y `config/sites.json` (entradas `artemis3_*`). Documentos descargados en `data/raw/artemis_docs/` (fuera de git).

## Conclusión

**NASA no publica latitud/longitud de ninguna región candidata de Artemis III** en ninguna fuente que se haya podido leer. Lo que hay, por orden de confianza:

1. **Figura oficial de NASA de las nueve regiones (lista de 2024)**, con barra de escala y la estrella del polo sur. Es la única fuente primaria con posición. Se digitalizó (§2): centro y caja de 9 regiones, incertidumbre ~±2 km.
2. **Huella de los SDEM** (Bertone et al., Zenodo 10.5281/zenodo.17954508) de 13 regiones de 2022: centro derivado, no publicado por NASA. Sigue siendo el valor principal de esas 13.
3. **Puntos de aterrizaje candidatos de Wueller et al. (2026)**: fuente académica secundaria, solo corroboración.
4. **Cuadrículas oficiales USGS LGRS/ACC** de las nueve regiones (el dato oficial más completo): **no se pudieron descargar** (§4).

Resultado en el catálogo: 13 regiones con centro SDEM, 5 de ellas con una segunda medida de la figura NASA; las 4 solo de 2024 pasan de `null` a coordenada digitalizada de la figura NASA (`aprox`). Ninguna es una coordenada «publicada»; lo dice cada campo `confianza`.

## 1. Registro de búsquedas y fuentes

| Fuente | Qué es | Resultado |
|---|---|---|
| NASA, release 22-089 (19/08/2022) y página SVS 5013 | 13 regiones, ~15×15 km | Solo nombres e imágenes; sin lat/lon (SVS 5013 leída) |
| NASA, RELEASE24-136 (28/10/2024) | 9 regiones | Solo nombres; sin lat/lon |
| George, Rubio, Lawrence, Curell, «Artemis III Site Selection Update: Downselection From Thirteen to Nine Candidate Regions», NTRS 20250011660 (DOCX, 560 KB) | Resumen de NASA con la figura de las nueve regiones | Sin tabla de coordenadas; la Image 1 es un mapa con escala y polo: base de §2 |
| Informe del Artemis III Science Definition Team, NASA/SP-20205009602 (PDF 28,7 MB, `pdftotext`) | Objetivos científicos (2020) | 0 menciones de «Nobile Rim»: anterior a las regiones, no sirve |
| LPSC 2025 #1410, Carton et al., peligros por región (PDF) | Comparación de 13 regiones | Sin coordenadas |
| Wueller et al. (2026), JGR Planets 131(3) e2025JE009434 | Sitios de aterrizaje dentro de 16 regiones | Página de Wiley: 403. Datos en Zenodo 10.5281/zenodo.17084058 (`Landing_Sites.zip`, 11,9 MB; shapefile de 130 puntos) |
| USGS, «Down-selected Artemis III candidate landing site navigational grids», DOI 10.5066/P1MEQ6UK | Rejillas LGRS/ACC de 1 km, 100 m y 10 m de las 9 regiones, de LROC QuickMap | La página las lista, pero los ficheros están en ScienceBase tras un desafío anti-bots (403) |
| USGS, release anterior DOI 10.5066/P13FD9ZD (nov. 2024) | LGRS de las regiones previas | Misma limitación |
| Moon Trek / LROC QuickMap | Capas de regiones | No se localizó ninguna capa pública descargable de las regiones |

Ninguna búsqueda con WebSearch devolvió lat/lon de una región.

## 2. Digitalización de la figura oficial de NASA

Figura: Image 1 del NTRS 20250011660, «The 9 candidate landing regions. Credit: NASA» (NASA/GSFC/ASU/JSC/AGDT), 709×548 px, vista polar con 0° arriba, estrella del polo, barra de escala y cajas amarillas.

Método: se detectaron las cajas amarillas en el PNG y se ajustó una transformación de semejanza (píxel a plano estereográfico polar, R = 1737,4 km) con 6 puntos de control: la estrella del polo (0, 0) y los centros SDEM de las 5 regiones comunes a la figura y al SDEM (Haworth, Malapert Massif, de Gerlache Rim 2, Nobile Rim 1, Nobile Rim 2). Resultado: **escala 1,779 px/km (la barra de escala de la figura da ~1,8), giro 0,11°, RMS de los residuos 0,77 km (máximo 1,6 km, en Nobile Rim 1 por solapamiento de cajas)**. Ese RMS más la lectura de bordes (±1 px ≈ 0,6 km) sostiene la incertidumbre de ~±2 km. El SDEM sirve de calibración, así que las 5 comunes no son independientes en la traslación; las 4 nuevas sí lo son.

### Regiones de 2024 (figura NASA)

| Región | lat (°) | lon E (°) | Caja NASA (km) | Rasgo gazetteer USGS más cercano | Wueller (centroide de sus sitios), diferencia |
|---|---|---|---|---|---|
| Peak Near Cabeus B | -83,624 | 291,222 | 20,8 × 21,3 | Cabeus B, 67 km | 4,5 km |
| Mons Mouton | -85,418 | 31,442 | 17,5 × 18,5 | Jaci (cráter), 0,8 km; el rasgo Mons Mouton queda a 25 km | 3,9 km |
| Mons Mouton Plateau | -84,296 | 30,417 | **78,3 × 57,2** | Mons Mouton, 9 km | 12,2 km (sus 11 sitios abarcan 56 × 32 km) |
| Slater Plain | -87,152 | 125,208 | 20,8 × 21,3 | Slater (cráter), 33 km | 4,7 km |

Campos del JSON: `centro_lat_deg`, `centro_lon_deg_e`, `centro_xy_m`, `caja_xy_m`, `fuente_coordenadas: figura_nasa_2024`.

### Comparación con la aproximación SDEM (5 regiones con figura 2024)

| Región | Figura NASA 2024 (lat, lon E) | Diferencia con SDEM (km) |
|---|---|---|
| Malapert Massif | -85,984, 359,724 | 0,3 |
| de Gerlache Rim 2 | -88,238, 295,582 | 0,3 |
| Haworth | -86,751, 337,193 | 0,4 |
| Nobile Rim 2 | -83,929, 58,708 | 0,8 |
| Nobile Rim 1 | -85,487, 37,580 | 1,6 |

**Diferencia máxima de la figura NASA frente a la aproximación SDEM: 1,6 km.** Las cajas de NASA (≈ 21 km; Haworth 31 km) coinciden con las huellas SDEM (20–21 km; Haworth 29,8 km): el SDEM replica los recuadros oficiales, de ahí el buen acuerdo. Las otras 8 regiones de 2022 no están en la figura de 2024; el mapa equivalente de 2022 (release 22-089) no se ha digitalizado.

## 3. Corroboración con Wueller et al. (2026)

El shapefile `LandingSites.shp` (130 puntos, polar estereográfica sur, R = 1737,4 km) agrupa los puntos de aterrizaje candidatos de los autores por región (códigos MMA, MMO, MMP, NR1, NR2, AR, FRA, PNS, CR, CRE, dGR1, dGR2, dGKM, HW, PCB, SP; sin Leibnitz Beta Plateau). **No son centros de región**: son los sitios que ellos eligieron por luz y PSR cercanas. El centroide de cada grupo se guarda como `centro_sitios_wueller2026` (auxiliar). Diferencia con el valor principal, en km: Connecting Ridge 1,4; de Gerlache Rim 1 2,0; de Gerlache-Kocher 2,1; Connecting Ridge Extension 2,8; Nobile Rim 1 3,2; Faustini Rim A 3,4; Nobile Rim 2 3,8; de Gerlache Rim 2 3,9; Peak Near Shackleton 4,0; Haworth 4,0; Malapert Massif 5,2; **Amundsen Rim 6,3 (máximo)**. Confirma el posicionamiento (las 4 regiones nuevas caen a 4-5 km, la meseta a 12 km por su tamaño); no fija el centro.

## 4. Lo que no se pudo conseguir

- **Rejillas USGS LGRS/ACC** (las coordenadas oficiales de las nueve regiones): están en ScienceBase (item 671a6fa8d34efed5620f89f8), que responde 403 con un desafío anti-bots a clientes automáticos. No se evadió. Si alguien las descarga a mano, bastan los shapefiles de 1 km de cada región para sustituir la digitalización por coordenadas oficiales.
- Mapa del release 22-089 para las 8 regiones de solo 2022.
- Wiley devuelve 403: no se leyó el texto del artículo, solo sus datos de Zenodo.

## 5. Nombres y equivalencias

- **Peak Near Cabeus B no es «Cabeus B»**: el rasgo «Cabeus B» del gazetteer USGS (id 8058, -82,26°, 305,42°) está a 67 km del centro de la región en la figura NASA. NASA dice «peak near», una referencia; no se usan las coordenadas de Cabeus B (`pista_gazetteer` queda como pista).
- **Mons Mouton (2024) y Leibnitz Beta Plateau (2022)**: el centro de la caja de Mons Mouton queda a 0,8 km del centro SDEM de Leibnitz Beta Plateau, y la lista de 2024 no incluye Leibnitz. **Coincidencia geométrica; NASA no declara la equivalencia: a verificar** (`equivale_a_2022` en el JSON). El rasgo «Mons Mouton» del gazetteer (-84,6°, 31,0°) queda a 25 km de esa caja.
- **Mons Mouton Plateau**: la caja de NASA es una meseta de ~78 × 57 km que contiene a Mons Mouton y toca Nobile Rim 1; no es de 15 km. Su centro es orientativo.
- de Gerlache Rim 1 (2022) = zip SDEM `deGerlache_Rim` (identificación por nombre, ya documentada).
- Los nombres se contrastaron con el gazetteer USGS por el rasgo más cercano (`rasgo_cercano`), que orienta pero no identifica la región.

## 6. Reproducir

Los campos añadidos (`centro_figura_nasa_2024`, `centro_sitios_wueller2026`, `fuente_coordenadas`, el relleno de las 4 regiones de 2024, `equivale_a_2022`) se aplicaron a mano sobre el JSON: **`python scripts/fetch_imagery.py --regions --yes` los sobrescribiría**. Documentos de partida en `data/raw/artemis_docs/`: `ntrs_20250011660_AIIIUpdateLPSC2026.docx`, `ntrs_img/image1.png`, `wueller_landing_sites/`, informe del SDT y LPSC 1410.
