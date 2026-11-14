# SPICE, marcos y física del polo sur: verificación (experto Luna)

Todo lo numérico se calculó ejecutando spiceypy 8.4 (CSPICE N0067) con los kernels de `kernels/` o se obtuvo de JPL Horizons el 14/11/2026. Lo no verificado lleva la etiqueta `a verificar`. Convenciones fijas: `convenciones.md`.

## 1. Cadena de marcos

| Paso | Operación | Marco | Kernels | Ejes |
|---|---|---|---|---|
| 1 | UTC → ET | — | `naif0012.tls` (LSK) | — |
| 2 | Posición de Sol/Tierra respecto al observador | ICRF/J2000 (DE421) → MOON_ME | `de421.bsp` (SPK), `moon_pa_de421_1900-2050.bpc` (MOON_PA_DE421, ID 31006), `moon_080317.tf` (FK: MOON_ME_DE421 31007 = MOON_PA_DE421 + rotación fija; MOON_ME 31001 alias) | +Z eje polar medio, +X hacia la Tierra media (meridiano 0) |
| 3 | MOON_ME → ENU local | rotación con λ, φ | ninguno | E, N, U (ver convenciones) |

Conjunto mínimo, probado quitando cada kernel: falla sin LSK (`NOLEAPSECONDS`), sin FK (`UNKNOWNFRAME`), sin BPC (`FRAMEDATANOTFOUND`) y sin SPK (`NOLOADEDFILES`). **No hacen falta** `pck00011.tpc` (solo IAU_MOON y radios) ni `moon_assoc_me.tf` (solo asocia MOON_ME a la Luna para `et2lst`/`lspcn`; `spkcpo` recibe el marco por nombre). Se cargan igualmente; es inocuo.

**MOON_ME vs MOON_PA vs IAU_MOON.** MOON_PA = ejes principales de inercia; MOON_ME = ejes media Tierra/eje polar, usados para coordenadas cartográficas. PGDA/LOLA (DE421) usa MOON_ME (documento base y PGDA). Medido: MOON_ME−MOON_PA = 103,85″ (~0,87 km); MOON_ME−IAU_MOON = 4″–10″ (2026-2045).

**Aberración.** Sol en -89.7, 129.0, 14/11/2026 00:00 UTC: NONE az 357.622736 / el 1.856362; LT 357.622735 / 1.856362; LT+S 357.617094 / 1.856337. LT casi no cambia; la estelar mueve el azimut ~20,3″. **Recomendación: `LT+S`**: es la posición aparente de Horizons y cuesta lo mismo. Para la Tierra, NONE→LT+S cambia ≤0,0036°.

**`spkcpo` vs `spkpos` + resta del observador.** Coinciden hasta ~1e-8° con LT+S (diferencias de ~1e-4″ en el Sol). Se usa `spkcpo` por tratar correctamente al observador solidario con el marco rotante.

**Distancias.** La norma del vector (km) es la distancia; tamaño angular `2·asin(R/d)`.

**Rango de fechas.** El BPC cubre 1899-12-31T23:59:19 ET a 2050-12-31T23:58:51 ET. Probado: 1900-01-01 y 2050-12-30 funcionan; 1899-12-31, 2050-12-31 23:59 y 2051/2052 lanzan `SpiceFRAMEDATANOTFOUND` ("PCK data required to compute the orientation of the body-fixed reference frame..."). El SPK DE421 cubre hasta 2053-10-08, pero MOON_ME no. Alternativa fuera de rango: `IAU_MOON` (probado en 2052-01-01), con 4″–10″ (~35-85 m) de error respecto a MOON_ME; habría que avisar al usuario. Recomendación: limitar la UI a 1900-2050.

### Snippet verificado

```python
import numpy as np, spiceypy as sp
K = "kernels/"
for k in ["naif0012.tls", "pck00011.tpc", "moon_080317.tf", "moon_assoc_me.tf",
          "moon_pa_de421_1900-2050.bpc", "de421.bsp"]:
    sp.furnsh(K + k)
R = 1737.4  # km, esfera de referencia

def azel(utc, lat_deg, lon_deg, body="SUN", abcorr="LT+S", frame="MOON_ME"):
    """Az (N->E, 0-360), el (deg) y distancia (km) de SUN/EARTH desde (lat, lon E+) sobre la esfera."""
    et = sp.str2et(utc)                                   # UTC -> ET
    obs = sp.georec(np.radians(lon_deg), np.radians(lat_deg), 0.0, R, 0.0)
    st, _ = sp.spkcpo(body, et, frame, "OBSERVER", abcorr, obs, "MOON", frame)
    v = np.array(st[:3])
    la, lo = np.radians(lat_deg), np.radians(lon_deg)
    E = np.array([-np.sin(lo), np.cos(lo), 0])
    N = np.array([-np.sin(la)*np.cos(lo), -np.sin(la)*np.sin(lo), np.cos(la)])
    U = np.array([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
    d = np.linalg.norm(v)
    return np.degrees(np.arctan2(v@E, v@N)) % 360, np.degrees(np.arcsin(v@U/d)), d

print(azel("2026-11-14 00:00:00", -89.7, 129.0, "SUN"))
# (357.617094, 1.856337, 147784050.03 km)
```

Para series, `sp.spkpos(body, ets, "MOON_ME", "LT+S", "MOON")` acepta un vector de ET; se resta `obs` y se proyecta igual (misma precisión; se usó en la sección 3).

## 2. Validación contra JPL Horizons

La API respondió (HTTP 200): `https://ssd.jpl.nasa.gov/api/horizons.api` con `COMMAND` 10/399, `CENTER='coord@301'`, `COORD_TYPE=GEODETIC`, `SITE_COORD='lon,lat,0'` (lon este-positiva, altitud km), `QUANTITIES='4,20'`, `APPARENT=AIRLESS`, `ANG_FORMAT=DEG`.

Cabecera de Horizons: efemérides **DE441** (no DE421), centro `MEAN_ME (high precision)`, radios 1737.4 km en los tres ejes, `Atmos refraction: NO (AIRLESS)`, columnas `Azi_(a-app)`, `Elev_(a-app)` (aparente: tiempo luz, curvatura relativista y aberración estelar). Horizons lleva ME, no PA, y la misma esfera.

**Resultado: diferencia máxima 0,05″ (1,4e-5°) en elevación y 0,04″ en azimut (hasta 0,39″ cuando el cuerpo está a >80° de elevación, donde el azimut se degenera).** El residuo se atribuye a DE421 frente a DE441 (no comprobado por separado). Sin aberración (`NONE`) el Sol difiere ~20″.

Casos de prueba (SPICE−Horizons en segundos de arco; observador a altura 0 sobre la esfera):

| lat, lon (E+) | UTC | Cuerpo | Az Horizons (°) | El Horizons (°) | Az SPICE LT+S (°) | El SPICE LT+S (°) | ΔAz (″) | ΔEl (″) |
|---|---|---|---|---|---|---|---|---|
| -89.7, 129.0 | 2026-07-04 06:00 | Sol | 177.680664 | -1.508670 | 177.680665 | -1.508662 | +0.00 | +0.03 |
| -89.7, 129.0 | 2026-07-04 06:00 | Tierra | 225.005037 | -0.658148 | 225.005038 | -0.658141 | +0.00 | +0.03 |
| -89.7, 129.0 | 2026-11-14 00:00 | Sol | 357.617097 | 1.856346 | 357.617094 | 1.856337 | -0.01 | -0.03 |
| -89.7, 129.0 | 2026-11-14 00:00 | Tierra | 229.790676 | -4.841909 | 229.790672 | -4.841902 | -0.02 | +0.02 |
| -89.7, 129.0 | 2027-03-20 12:00 | Sol | 258.842542 | -1.073778 | 258.842538 | -1.073772 | -0.01 | +0.02 |
| -89.7, 129.0 | 2027-03-20 12:00 | Tierra | 233.058557 | -2.102498 | 233.058553 | -2.102488 | -0.02 | +0.04 |
| -89.7, 129.0 | 2027-09-01 18:30 | Sol | 40.698680 | 0.973152 | 40.698672 | 0.973141 | -0.03 | -0.04 |
| -89.7, 129.0 | 2027-09-01 18:30 | Tierra | 235.071998 | -5.020675 | 235.071988 | -5.020666 | -0.04 | +0.03 |
| -86.0, 0.0 | 2026-07-04 06:00 | Sol | 306.681692 | 1.181163 | 306.681693 | 1.181172 | +0.00 | +0.03 |
| -86.0, 0.0 | 2026-07-04 06:00 | Tierra | 353.990812 | 3.532516 | 353.990812 | 3.532523 | -0.00 | +0.03 |
| -86.0, 0.0 | 2026-11-14 00:00 | Sol | 126.637856 | -0.830469 | 126.637853 | -0.830478 | -0.01 | -0.03 |
| -86.0, 0.0 | 2026-11-14 00:00 | Tierra | 358.776239 | -0.649972 | 358.776235 | -0.649966 | -0.02 | +0.02 |
| -86.0, 0.0 | 2027-03-20 12:00 | Sol | 27.861762 | 2.521314 | 27.861759 | 2.521319 | -0.01 | +0.02 |
| -86.0, 0.0 | 2027-03-20 12:00 | Tierra | 2.052136 | 2.075250 | 2.052131 | 2.075260 | -0.02 | +0.04 |
| -86.0, 0.0 | 2027-09-01 18:30 | Sol | 169.680472 | -3.189740 | 169.680463 | -3.189751 | -0.03 | -0.04 |
| -86.0, 0.0 | 2027-09-01 18:30 | Tierra | 4.039219 | -0.859847 | 4.039209 | -0.859839 | -0.03 | +0.03 |
| 0.0, 0.0 | 2026-07-04 06:00 | Sol | 271.506487 | 36.670940 | 271.506476 | 36.670941 | -0.04 | +0.00 |
| 0.0, 0.0 | 2026-07-04 06:00 | Tierra | 271.856209 | 83.974341 | 271.856133 | 83.974342 | -0.27 | +0.00 |
| 0.0, 0.0 | 2026-11-14 00:00 | Sol | 91.939942 | -36.602284 | 91.939931 | -36.602281 | -0.04 | +0.01 |
| 0.0, 0.0 | 2026-11-14 00:00 | Tierra | 344.456450 | 85.409203 | 344.456376 | 85.409208 | -0.27 | +0.02 |
| 0.0, 0.0 | 2027-03-20 12:00 | Sol | 87.827087 | 62.145489 | 87.827098 | 62.145493 | +0.04 | +0.01 |
| 0.0, 0.0 | 2027-03-20 12:00 | Tierra | 51.149671 | 87.354295 | 51.149779 | 87.354305 | +0.39 | +0.04 |
| 0.0, 0.0 | 2027-09-01 18:30 | Sol | 94.165411 | -79.669157 | 94.165350 | -79.669150 | -0.22 | +0.02 |
| 0.0, 0.0 | 2027-09-01 18:30 | Tierra | 41.441047 | 83.861561 | 41.441033 | 83.861574 | -0.05 | +0.05 |

También se comparó -89.9, -45.0 (mismos instantes) con diferencias ≤0,04″; no se tabula.

## 3. Física del polo sur (SPICE, 2026-01-01 a 2027-12-31, paso 10 min, esfera lisa)

| Lat | Sol: elevación del centro (mín…máx) | Sol sobre el horizonte (centro / limbo sup.) | Tierra: elevación (mín…máx) | Tierra sobre el horizonte |
|---|---|---|---|---|
| -89.9° | -1,625° … +1,627° | 51,6 % / 57,3 % | -7,002° … +6,672° | 47,0 % |
| -89.7° | -1,858° … +1,857° | 53,3 % / 56,0 % | -7,285° … +6,355° | 45,6 % |
| -86° (Malapert aprox) | -5,524° … +5,522° | 50,2 % / 52,4 % | -3,132° … +10,541° | 67,0 % |

(Longitud 0°, salvo -89.7 con 129°.) Son porcentajes de **esfera lisa**, no de iluminación real: una cresta ve mucho más Sol, el fondo de un cráter menos.

- **Tamaños angulares** (en -89.9°): Sol 0,5228°–0,5434° (146,7–152,5 millones de km); Tierra 1,797°–2,050° (diámetro ecuatorial; 356 510–406 745 km).
- **Libración** (sub-Tierra en MOON_ME, 2026-2030): latitud ±6,8° (entre -6,86° y +6,86°, cerca del máximo del ciclo nodal de 18,6 años); longitud entre -8,05° y +7,86°. Periodo en latitud **27,22 d** (media de 66 ciclos, rango 27,04–27,46); en longitud 27,54 d (cruces por la media; mes anomalístico estándar 27,55 d).
- **Ciclo solar:** rotación sinódica (longitud subsolar) **29,5305 d** (calculada). Latitud subsolar entre -1,59° y +1,59°, periodo **347,2 d** (media de 5 ciclos 2026-2031, rango 344,5–348,6); el año de eclipses estándar es 346,62 d (valor de referencia, no recalculado). Define las "estaciones" polares: ~173 d con el Sol al norte o al sur del plano ecuatorial.
- **Eclipses de Sol por la Tierra** (desde el centro lunar, disco terrestre sin atmósfera; solape si separación < r_Sol + r_Tierra):

| Inicio → fin (UTC) | Sep. mínima | r_Tierra / r_Sol | Observación |
|---|---|---|---|
| 2026-03-03 09:20 → 13:50 | 0,359° | 0,955° / 0,268° | Sol totalmente tapado; coincide con el eclipse lunar total (a contrastar con EclipseWise) |
| 2026-08-28 02:00 → 06:25 | 0,464° | 0,936° / 0,263° | Centro lunar dentro del disco terrestre; eclipse lunar parcial visto desde la Tierra (limbo fuera) |
| 2027-02-20 22:00 → 00:25 | 1,052° | 1,006° / 0,269° | Parcial |
| 2027-08-17 06:55 → 07:35 | 1,151° | 0,902° / 0,262° | Parcial leve |

2027-07-18: sin solape (separación mínima 1,415° a las 16:05 UTC frente al umbral 1,162°). EclipseWise lo da como penumbral de magnitud 0,0032 con máximo ~16:03, coherente en instante (búsqueda web). Para un observador concreto manda el paralaje (hasta ~0,26°) y que la Tierra esté sobre su horizonte: el motor debe calcularlo por observador. La atmósfera terrestre no se modela.

**Fracción de iluminación publicada.** Verificado (resumen NTRS 20120010094): Mazarico et al. 2011, Icarus 211, 1066-1081 (LOLA 240 m/px, ciclo de nutación de 18,6 años, paso 1 h): un punto cercano al borde de Shackleton está iluminado de forma continua ~240 días al año, con la oscuridad continua más larga ~1,5 días. Wikipedia atribuye a Spudis et al. (1995, Clementine) 80–90 % para picos del borde de Shackleton (secundaria). Porcentajes por sitio (Site04/11/23) de Mazarico 2011 y Barker 2021: **a verificar**.

## 4. Catálogo

`config/sites.json` (32 entradas). Coordenadas de misiones: lista de Wikipedia de objetos artificiales en la Luna (derivadas de LROC), solo estas más IM-1. IM-1 corregido a 80.13°S 1.44°E (búsqueda web; la lista da 84.9°S 12.9°E, que es el cráter Malapert). Site04/11/23: centro del cráter/macizo (USGS Gazetteer: Shackleton 89.67°S 129.78°E; de Gerlache 88.5°S 87.1°W; Mons Malapert 85.98°S 1.67°W, ID 16338) como `aprox`, para que el código los sustituya leyendo el GeoTIFF. Las 13 regiones Artemis III (nombres de la lista de NASA, ago-2022) llevan lat/lon null y `a verificar`; Wikipedia indica además que Artemis III se reorientó en feb-2026 (a verificar). La lista vigente de NASA (oct-2024) tiene nueve regiones y no incluye Faustini Rim A ni Peak Near Shackleton (upi.com, 28/10/2024); no se encontró ninguna coordenada en fuente oficial, así que siguen null. Las fechas exactas de aterrizaje son de conocimiento general: solo el año se contrastó. `dem_dir` y `dem_prefix` son marcadores que debe fijar quien descargue los GeoTIFF.

## 5. Casos de validación que el motor debe reproducir

| Condición | Valor esperado | Tolerancia | Fuente |
|---|---|---|---|
| Az/El de Sol y Tierra, los 24 casos de la sección 2 | Columnas Horizons | El 0,001° (3,6″); Az 0,002°, salvo el>80°: 0,02° | JPL Horizons (verificado) |
| Sol en -89.9°, 2026-27: elevación del centro | -1,625° … +1,627° | ±0,01° | SPICE (calculado); coherente con la oblicuidad lunar ~1,54° |
| Tierra en -89.9°, 2026-27 | -7,002° … +6,672° | ±0,05° | SPICE (calculado) |
| Tierra sobre el horizonte, -89.9°, 2026-27 | 47,0 % del tiempo | ±1 punto | SPICE (calculado) |
| Periodo de libración en latitud | 27,22 d (27,04–27,46) | ±0,3 d | SPICE; mes dracónico estándar 27,212 d |
| Rotación sinódica | 29,5305 d | ±0,01 d | SPICE; estándar 29,5306 d |
| Periodo de latitud subsolar | 347,2 d (344,5–348,6) | ±3 d | SPICE; año de eclipses estándar 346,62 d |
| Diámetro angular del Sol | 0,5228°–0,5434° | ±0,0005° | SPICE |
| Diámetro angular de la Tierra | 1,797°–2,050° | ±0,005° | SPICE |
| Sol tapado por la Tierra | 2026-03-03 09:20–13:50 UTC | ±10 min | SPICE; contrastar con EclipseWise |
| 2027-07-18 sin solape | separación 1,415° > umbral 1,162° | ±0,01° | SPICE; EclipseWise |
| Fecha fuera de 1900-2050 | Excepción `SpiceFRAMEDATANOTFOUND` | n/a | SPICE (probado) |
| MOON_ME vs MOON_PA | 103,85″ | ±0,5″ | SPICE (calculado) |
| NONE vs LT+S, Sol en el polo | ~20,3″ en azimut | ±1″ | SPICE (calculado) |

## 6. Riesgos de marcos

1. MOON_PA o IAU_MOON en vez de MOON_ME: ~0,87 km / 35-85 m de desplazamiento.
2. Longitud oeste-positiva en fuentes (Apolo 12/14, Chang'e 3/5/6): convertir al leer.
3. Fecha fuera de 1900-2050: validar antes; el fallo es de marco, no de efemérides.
4. La elevación SPICE es sobre el plano tangente a la esfera: no restar la curvatura otra vez al combinar con el DEM.
5. Horizons usa DE441, el motor DE421: esperar ≲0,05″; no exigir menos.
6. Porcentajes de esfera lisa no son iluminación real.
7. La entrada de IM-1 en la lista de Wikipedia es el cráter, no el módulo.

## 7. Estaciones terrestres y enlace DTE

**Qué es «enlace posible».** `earth_fraction` (geometría: Tierra sobre el horizonte local) NO es capacidad de comunicar. El enlace
exige: (1) Tierra visible desde el lander con un margen mínimo de elevación sobre su horizonte (`min_earth_elevation_deg`, por perfil;
0° por defecto, sensibilidad 3° y 5°; el margen sube el horizonte `H(A)+m`, exacto en `link_fraction`) Y (2) alguna estación de la red
viendo la Luna por encima de su elevación mínima de recepción. Sigue siendo geometría: sin link budget, ocupación de red ni máscara de
terreno de la antena terrestre. `network=None` (`AnalysisRequest.link_network=None`) recupera el comportamiento geométrico anterior.

**Geometría de la estación** (`astronomy/ground_stations.py`). Posición aparente de la Luna (LT+S) respecto al centro de la Tierra en
`IAU_EARTH` (`spkpos` vectorizado) menos la posición de la estación (punto geodésico WGS 84), proyectada sobre la vertical geodésica;
sin refracción. La cobertura se calcula UNA vez por rejilla temporal (común a todos los sitios lunares).

**Precisión de `IAU_EARTH` frente a ITRF93 (medida).** 30 instantes de 2026-12 por complejo contra JPL Horizons
(`ssd.jpl.nasa.gov/api/horizons.api`, `CENTER=coord@399`, `QUANTITIES=4`, AIRLESS; ITRF93, EOP al 13/11/2026):

| Marco de la Tierra | DSS-14 máx (rms) | DSS-43 máx (rms) | DSS-63 máx (rms) |
|---|---|---|---|
| `IAU_EARTH` (pck00011.tpc, el que ya cargamos) | 0,0716° (0,055°) | 0,0720° (0,056°) | 0,0670° (0,052°) |
| `ITRF93` con `earth_latest_high_prec.bpc` + `earth_2026_260806_2126_predict.bpc` (5 + 19 MB) | 0,0005° | 0,0005° | 0,0005° |

(Con la corrección ingenua ΔT = ET−UTC en `IAU_EARTH` el error SUBE a 0,30°: el modelo IAU ya está referido a un UT1 de la época J2000;
no se aplica.) 0,07° mueve una salida/puesta de la Luna ~20 s, 30 veces menos que la rejilla de 600 s, y el efecto en horas de contacto
por día es ≲ 2 min: **no compensa descargar el kernel binario** (19 MB, solo 2026-2126, predicciones peores fuera de las EOP). El test
`tests/test_ground_stations.py` guarda los valores de Horizons (12 instantes + un día a 10 min por complejo, `scripts/fetch_horizons_stations.py`)
con tolerancia 0,10° (el margen sobre lo medido no oculta un error de signo o longitud, que daría grados).

**Misma máscara de red para todos los sitios lunares (medido).** La cobertura usa el centro de la Luna. Un punto de la superficie cambia la
elevación vista desde la estación como mucho ≈ el radio angular lunar (0,28° en el perigeo; el «paralaje ≲ 0,5°» del plan era una
cota holgada): Shackleton, Malapert y un punto del limbo dan 0,283° / 0,281° / 0,271° de diferencia máxima en 14 d, y la cobertura por
estación cambia ≤ 0,07 puntos porcentuales (red: 99,93 % → 99,91 %).

**Fuentes de las estaciones** (`config/ground_stations.json`; solo números verificados):

- DSN (Goldstone DSS-14, Madrid DSS-63, Canberra DSS-43, antenas de 70 m): coordenadas WGS 84 de DSN 810-005, módulo 301, Rev. P
  (22/05/2026), Tabla 5 (<https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf>); contrastadas con las ITRF93 cartesianas de NAIF
  `earth_topo_260814.tf` (Tabla 2, mismo documento): coinciden < 1 m. Elevación mínima de recepción 6,0° [pub] (301 Rev. P §2.2.2 y §2.2.4:
  límite mecánico ≈ 6° en antenas az-el); límites mecánicos medidos 5,923° (34 m) y 5,962° (70 m) en NTRS 20120004035. La máscara de terreno
  real de cada antena (figuras 10-25 de 301) puede ser mayor en algunos azimuts y NO se modela. Transmisión (enlace de subida): ≥ 10,1° [pub].
- ESTRACK (New Norcia, Cebreros, Malargüe): coordenadas planetodéticas WGS 84 del kernel NAIF `ndosl_190716_v02.tf` (NDOSL NN1D, CB1D, MG1D).
  Elevación mínima **a verificar** (no se encontró fuente oficial de ESA): la red ESTRACK usa 6° SUPUESTO [sup] y avisa; no es red por defecto.
- NASA Near Space Network (LEGS-1 en White Sands, etc.): anunciado por NASA pero sin ubicación exacta, elevación ni fecha verificadas
  en fuente oficial: **no se incluye ninguna estación**.
- Zonas horarias IANA: Goldstone `America/Los_Angeles`, Madrid/Robledo `Europe/Madrid`, Canberra/Tidbinbilla `Australia/Canberra`
  (ACT = Sydney), New Norcia `Australia/Perth`, Cebreros `Europe/Madrid`, Malargüe `America/Argentina/Mendoza`. `tzdata` está en `requirements.txt`.

**Umbrales por perfil (todos [sup], editables en `simulation.json: score.profiles.<id>.link`).** `min_earth_elevation_deg` 0° (panels.json:
dte_comms 0°, «estimado»; margen de 3° «suposición»). G6 (ventana de enlace continua mínima útil) conserva los valores de panels.json (2 h; 8 h
base). G7 (hueco máximo sin enlace, blanda): lander sin RHU y con baterías 48 h (un lander opera ≤ 14 d y 2 días sin contacto impiden comandar o
recuperar un fallo), lander con RHU 96 h (sobrevive sin contactar), rover 24 h (ciclos de operación diarios), base 12 h (contacto casi continuo; en
la práctica vía relé), DTE puro 24 h. Ninguno está publicado.

**Score.** `s_earth = min(1, f_enlace / max(f_ref, suelo))` con `f_ref` = Tierra sobre esfera lisa con el mismo margen SIN red: la red es un
factor externo común que penaliza (una estación sola, 45 % de cobertura, baja `s_earth` ~45 %); el DSN (99,9 %) apenas se nota.
