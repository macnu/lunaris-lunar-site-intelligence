# Revisión independiente del enlace DTE y de las bases terrestres (T62)

Fecha: 14/11/2026. Roles: matemático + selenógrafo. Fichero de pruebas: `tests/test_independent_link.py` (37 pruebas: 33 pasan, 4 `xfail(strict=True)` que
documentan defectos). No se ha tocado `src/` ni `config/`. El motor y el pipeline se usan solo para COMPARAR.

## Método (camino distinto al del motor)

| Pieza | Motor | Revisión independiente |
|---|---|---|
| Orientación de la Tierra | `IAU_EARTH` (`pck00011.tpc`): sin nutación, movimiento polar ni UT1-UTC | `ITRF93` de los PCK binarios de NAIF (`earth_latest_high_prec.bpc`, 5,2 MB, cubre hasta 2027-02-09, + `earth_2026_260806_2126_predict.bpc`, 19,2 MB), descargados a `data/raw/earth/` (no versionados; las pruebas se omiten si faltan). Cadena: `spkpos(MOON, J2000, LT+S, EARTH)` + `pxform(J2000→ITRF93)` a mano, y control topocéntrico con `spkcpo` |
| Estación | `station_position_km` desde el JSON | DMS escritos a mano de DSN 810-005/301 Rev. P Tabla 5 (PDF descargado el 14/11/2026, accesible) y geodésicas→cartesianas propias; Tabla 6 (geocéntricas) como 2.ª fuente |
| Enlace lander→Tierra | `disc_fraction` ≥ 0,5 sobre H(A) del DEM, rejilla 600 s | Rayo 3D `spkpos(EARTH, MOON_ME, LT+S)` contra el DEM con rasterio (misma técnica que `test_independent_visibility.py`), centro de la Tierra, paso 120 s; el margen m baja la elevación del rayo m° a azimut constante |
| Hora local | `zoneinfo` (`tzdata`) | Reglas de verano de 2027 escritas a mano (último domingo, etc.) |
| Contraste externo | — | JPL Horizons API (301, `CENTER=coord@399`, `SITE_COORD`, `QUANTITIES=4`, AIRLESS): 144 instantes embebidos en el test + 1 en vivo (se omite sin red) |

**Por qué ITRF93 binario y no una rotación a mano con GMST.** GMST sin precesión-nutación yerra ~0,36° en 2026 (50″/año × 26 años), peor que
el 0,07° que se quiere medir; incluirlas a mano sería reescribir IAU-2006 y sin EOP. El BPC de NAIF lleva todo (EOP medidas hasta ago-2026,
predichas después) y cuesta 24 MB de datos no versionados. Resultado: 0,0002° con Horizons.

## 1. Elevación de la Luna desde DSS-14 / DSS-63 / DSS-43

| Comparación (72 instantes por mes: 24 × 3 estaciones) | dic-2026 máx / rms | mar-2027 máx / rms |
|---|---|---|
| **Propia (ITRF93) − Horizons** | **0,00016° / 0,00007°** | **0,00070° / 0,00045°** |
| Motor (IAU_EARTH) − Horizons | 0,0720° / 0,0556° | 0,0711° / 0,0533° |
| Motor − propia, 31 d a 600 s | 0,0725° / 0,056° | — |
| `spkpos` ITRF93 vs `pxform` a mano | 1e-9° | — |
| `spkpos` geocéntrico vs `spkcpo` topocéntrico | ≤ 1,2e-4° (aberración diurna, 0,46 km/s) | — |

- El 0,07° que `config/ground_stations.json` declara para `IAU_EARTH` es real (medido 0,072°) y no oculta nada: mi cadena no ve el sesgo.
  El motor no se equivoca de signo ni de longitud (eso daría grados). El efecto en tiempo es ~20 s por cruce; en la cobertura de red,
  invisible a 5 cifras (§2).
- Posiciones: **acuerdo exacto**. Latitud, longitud (E+) y altura de las tres estaciones = Tabla 5 (< 1e-8°; altura idéntica); las alturas son
  elipsoidales WGS 84 (nota 1 del PDF: restar la separación geoidal para MSL), que es lo que el motor usa. Tabla 6: radio geocéntrico
  y latitud geocéntrica de DSS-14/-43 coinciden (0,05 m / 2e-6°). Posición del motor = la mía a 0,3 mm (redondeo del JSON).
- Elevación 6,0° (recepción) confirmada en 301 Rev. P §2.2.2/§2.2.4 («≈ 6°», genérico 6,0°). **Reservas de la fuente**: transmisión 10,0° + 0,1°
  = 10,1° (baja potencia), 13,5/13,6° (alta potencia) y **DSS-43 17,6°** en alta potencia; máscaras de terreno por antena (figuras 10-25) no modeladas.

## 2. Cobertura de red, 1-31 dic 2026 (≥ 1 DSN ve la Luna ≥ 6°)

| Magnitud | Propia (30 s) | Motor (600 s) |
|---|---|---|
| Fracción de red | 99,929 % | 99,929 % (dif. < 2e-4) |
| DSS-14 / DSS-63 / DSS-43 por separado | 44,06 / 43,55 / 45,51 % | idénticas a < 3e-4 |
| Huecos reales | 3: 8-dic 15:17-15:25, 9-dic 16:04:30-16:20, 10-dic 17:00-17:07:30 UTC (8,5 / 15,5 / 7,8 min; 0,53 h en total) | 3, inicio a 10-50 s, duración a < 1 min |

- **Sí hay huecos reales**, pero diminutos: traspaso Madrid→Goldstone (Madrid baja de 6° y Goldstone no sube de 6° hasta 8-16 min después; Canberra a −23°). Se repiten cada
  mes en dos tandas (dic 8-10, ene 4-6, feb 1-3 y 28, mar 1-2 y 27-29): 15 huecos en dic-mar, de 0,8 a 16,8 min. El motor los encuentra
  los 15 con cualquier desfase de la rejilla (el hueco es la diferencia de dos cruces, no un valle de una sola estación).
- Para los polos sur la red **no restringe** en las ventanas de enlace de 14 d (los huecos caen en horas sin Tierra): el enlace es la geometría.
  Donde la red SÍ restringe (sitio cercano a la Tierra, lat −70°, lon 0°, 3-7 ene 2027) el motor reproduce los 3 huecos
  (4,18 / 15,52 / 11,93 min vs 4,25 / 15,5 / 11,75 propios; `link_fraction` a 3e-4).
- **Reserva de alcance (sensibilidad TX)**: el motor solo modela RECEPCIÓN. Comandar al lander exige transmitir: con 10,1° la red cubre
  **97,99 %** (37 huecos, el mayor 1,30 h, 14,9 h en total) y con 13,6° 94,23 % (39 huecos, máx. 2,29 h). El motor lo admite con
  `link_station_min_elevation_deg` y coincide con mi cálculo (a 1e-3), pero `tx_min_elevation_deg` del JSON no se usa ni se avisa.
  Tampoco se modela ocupación de la red DSN (las tres de 70 m las comparten todas las misiones).

## 3. Enlace posible por fuerza bruta 3D (14 d desde la mejor fecha del motor, mejor punto de la rejilla de idoneidad)

Puntos: top-1 de `data/processed/suitability` (Shackleton −89,5626°, 215,4724°E; de Gerlache −88,4530°, 292,1626°E; Malapert −85,9685°, 357,6815°E).
Inicio (barrido 1-dic..1-ene del motor): 6, 16 y 13 de diciembre de 2026. `lf` = link_fraction; `h/d` = horas de enlace por día; hueco = máximo.

| Sitio | Margen | lf propia / motor | h/d propia / motor | Hueco máx. (h) propia / motor | Ventana más larga (h) | Error máx. de borde |
|---|---|---|---|---|---|---|
| Shackleton | 0° | 0,6207 / 0,6206 | 14,90 / 14,89 | 127,42 / 127,49 | 208,6 / 208,5 | 266 s |
| Shackleton | 3° | 0,4385 / 0,4377 | 10,52 / 10,50 | 188,65 / 188,94 | 147,3 / 147,1 | 1049 s |
| Shackleton | 5° | 0,3180 / 0,3178 | 7,63 / 7,63 | 229,15 / 229,21 | 106,8 / 106,8 | 211 s |
| de Gerlache | 0° | 0,9542 / 0,9536 | 22,90 / 22,89 | 15,42 / 15,59 | 320,6 / 320,4 | 618 s |
| de Gerlache | 3° | 0,8185 / 0,8183 | 19,64 / 19,64 | 61,02 / 61,05 | 275,0 / 275,0 | 104 s |
| de Gerlache | 5° | 0,7182 / 0,7185 | 17,24 / 17,24 | 91,02 / 90,85 | 241,3 / 241,4 | 599 s |
| Malapert | 0° | 1,0000 / 1,0000 | 24,00 / 24,00 | 0 / 0 | 336,0 / 336,0 | 0 s |
| Malapert | 3° | 0,8488 / 0,8487 | 20,37 / 20,37 | 47,12 / 47,18 | 285,2 / 285,2 | 214 s |
| Malapert | 5° | 0,6652 / 0,6650 | 15,96 / 15,96 | 81,08 / 81,11 | 223,5 / 223,4 | 97 s |

**Acuerdo**: |Δlf| ≤ 8e-4 (0,3 h en 14 d), |Δhueco| ≤ 0,29 h, mismo número de ventanas (1) en los nueve casos. **Diferencias explicadas**: el motor
cierra la ventana con «fracción de disco ≥ 0,5» sobre H(A) y rejilla de 600 s; yo con el centro del disco y 120 s. Cerca del horizonte polar la Tierra
sube ~0,1°/h, así que 0,03° de diferencia entre «centro» y «mitad del área con terreno irregular» son ~17 min (máx. observado 1049 s, Shackleton 3°);
el signo no es sistemático. Ninguna diferencia es de signo, marco ni margen.

**Cifras de Shackleton**, confirmadas: Tierra/enlace **62,1 %** (propio 62,07 %, motor 62,06 %), hueco máximo **127,5 h** (propio 127,4 h),
**sin enlace del 6 de dic 00:00 al 11 de dic ~07:25-07:29 UTC** (5 d 7,4 h; los días 6-10 completos sin una hora de enlace). El enlace dura entonces
hasta el final de la ventana (208,5 h = 8,7 d, truncada por el borde: el hueco inicial también toca el borde y es cota inferior; el motor lo marca).

**El enlace no cae cuando la máscara de red no restringe**: en los 9 casos mi enlace = Tierra geométrica a 1e-9 (la red cubre ≥ 99,85 % y los
3 huecos reales del 8-10 dic caen en horas sin Tierra), y con margen 0° el motor da `link_fraction == earth_fraction` a 1e-6.

## 4. Hora local

- Dic: PST = UTC−8, CET = UTC+1, AEDT = UTC+11. **Todos** los inicios y finales de las ventanas de contacto de Shackleton (6-20 dic, ≥ 10 ventanas) = UTC + desfase
  manual, con abreviatura correcta; hora solar media local = UTC + lon/15 a 1e-3 h.
- DST 2027 con reglas a mano, contra `et_to_local` (7 008 instantes de 2027 + los 6 cambios al segundo): Madrid 28-mar 01:00 UTC y 31-oct 01:00 UTC;
  Canberra 3-abr 16:00 UTC (domingo 4-abr 03:00 AEDT→AEST) y 2-oct 16:00 UTC (domingo 3-oct 02:00 AEST→AEDT); Goldstone 14-mar 10:00 UTC y 7-nov 09:00 UTC
  (EE. UU.: 2.º domingo de marzo, 1.º de noviembre; no era parte del enunciado, se comprueba porque Goldstone sí entra en las ventanas). **Acuerdo total.**
  (El ET→UTC del motor ignora TDB−TT, ±1,7 ms: irrelevante salvo exactamente en el borde.)
- **Textos del informe del día 12 de dic** (UTC), a partir de las ventanas UTC del motor:

| Estación | Ventana(s) reales (UTC → local) | Texto del informe | Veredicto |
|---|---|---|---|
| Madrid DSS-63 | 12-dic 11:00:20-19:06:06 → 12:00-20:06 CET | 12:00-20:06 CET | **Correcto** |
| Canberra DSS-43 | 11-dic 21:37:09 → 12-dic 11:11:57 = 12-dic 08:37-22:11 AEDT; 12-dic 22:34:50 → 13-dic 11:45:31 = 13-dic 09:34-22:45 AEDT | 09:34-22:11 AEDT | **Incorrecto**: une el final de la ventana del 12 con el inicio de la del 13 |
| Goldstone DSS-14 | 11-dic 17:48:05 → 12-dic 02:12:50 = 11-dic 09:48-18:12 PST; 12-dic 18:21:59 → 13-dic 03:13:58 = 12-dic 10:21-19:13 PST | 10:21-18:12 PST | **Incorrecto**: une el inicio de la del 12 con el final de la del 11 |

  Causa: `daily_contact_table` parte las ventanas por día UTC (00:00 UTC = 11:00 AEDT = 16:00 PST), así que el día 12 contiene trozos «11:00-22:11 AEDT» y «09:34-11:00 AEDT»
  (cada trozo está bien convertido, comprobado), y el resumen toma min(inicio)-max(fin) de los trozos. Para el día 12 correcto: Canberra 08:37-22:11 AEDT, Madrid 12:00-20:06 CET,
  Goldstone 10:21-19:13 PST (más la continuación de la siguiente ventana, etiquetada). Además los minutos se truncan (18:12:50 → 18:12), no se redondean.

## 5. `s_earth` y G7

`s_earth = min(1, f_enlace / max(f_ref, suelo))`, `f_ref` = Tierra sobre esfera lisa, mismo margen, sin red; suelo 0,25 (0,5 en `dte_comms`).

- **Valores a mano** (0,30/0,50 → 0,60; 0,10/0,05 → 0,40 por el suelo; 0,45/0,20 con suelo 0,5 → 0,90): pasan.
- **Monótona** no decreciente en `f_enlace`, acotada en [0, 1], continua (Lipschitz 1/max(f_ref, suelo), sin saltos), no creciente en `f_ref`; **satura** exactamente en
  `f_enlace ≥ max(f_ref, suelo)`. Verificado en rejilla de 401 × 6 referencias.
- **Saturación que oculta el hueco (reserva real)**: en Shackleton la ventana elegida (6-dic) tiene `f_ref` = 0,361 y enlace 0,6206 con 127,5 h sin enlace; la ventana
  del 11-dic 08:00 tiene `f_ref` = 0,742 y enlace 1,000 sin huecos. Ambas dan `s_earth` = 1 y **el mismo score, 97,41**. Solo G7 las distingue (FAIL vs PASS), y G7 es blanda.
  Por eso `s_earth` no mide «cuánto» ni «con qué huecos» comunica: mide si se alcanza la esfera lisa.
- **Defecto de selección de fecha (B1)**: el barrido de fechas puntúa sin `max_link_gap_h`/`longest_earth_h` y `choose_start` desempata por la fecha más temprana; la mejor
  fecha entregada falla G7 aunque otra con el mismo score lo cumpla. Test `xfail`.
- **G7 (12-96 h, supuestos)**: valores del JSON verificados (48/48/96/24/12/24 h, todas blandas; límite inclusivo: 48,0 pasa, 48,1 falla). Con mi enlace, fechas de inicio
  cada 6 h del 1-dic al 28-mar en el mejor punto de Shackleton: hueco ≤ 12 h en **23,5 %**, ≤ 24 h 27,3 %, ≤ 48 h **34,8 %**, ≤ 96 h 49,9 % (y existen ventanas de 14 d sin
  ningún hueco). Es decir, los umbrales **sí discriminan** (no pasan ni fallan todo), pero un lander sin RHU (48 h) solo cumple en 1 de cada 3 fechas en Shackleton; Malapert a 3°
  queda en 47,1 h, a 0,9 h de fallar: con umbrales sin fuente conviene mostrar el hueco, no solo PASS/FAIL. G7 cuenta el hueco truncado en el borde inicial (llegada sin enlace):
  coherente para un lander que aterriza al inicio, pero debe leerse como «hueco inicial».

## Bugs (4 `xfail(strict=True)` en el test; al corregirlos fallarán «inesperadamente» y hay que quitar la marca)

| Id | Gravedad | Dónde | Qué | Prueba |
|---|---|---|---|---|
| B1 | media | `pipeline._score_window` + `site_score.choose_start` | La mejor fecha ignora G7/G6 y desempata por la más temprana: con `s_earth` saturado elige 6-dic (hueco 127,5 h, G7 FAIL) pudiendo elegir 11-dic 08:00 (mismo score, enlace 100 %, G7 PASS) | `test_best_start_does_not_fail_soft_g7_when_a_tied_start_passes` |
| B2 | baja | `ground_stations.cross_intervals` / `NetworkCoverage.any_intervals` | En traspasos con dos estaciones a ≈6° los cruces lineales de la rejilla de 600 s dejan huecos espurios de ~3 s (2-feb-2027 05:41:28 UTC; 1-2 en dic-mar) que parten una ventana de enlace en dos y acortan `longest_link_window` | `test_no_spurious_handoff_gap_in_link_windows` |
| B3 | baja (texto) | `daily_contact_table` y su resumen | Trozos por día UTC unidos por min-max: ventanas inexistentes («Canberra 09:34-22:11 AEDT», «Goldstone 10:21-18:12 PST»); minutos truncados | `test_report_text_day12_is_a_real_window[...]` ×2 |

## Reservas (no son bugs del motor)

1. Solo recepción 6°; comandar (10,1° / 13,6° / DSS-43 17,6°) baja la red a 98,0 / 94,2 %; `tx_min_elevation_deg` sin uso ni aviso.
2. Sin máscara de terreno de las antenas ni ocupación DSN; sin link budget (ya declarado: `NOT_RF_LINK`).
3. Centro vs disco: el motor define «enlace» con ≥ 50 % del disco terrestre sobre H(A)+m; con el centro los bordes cambian hasta 17,5 min (|Δlf| ≤ 8e-4). Un lander con antena de haz estrecho
   apuntada al centro verá ventanas algo distintas.
4. `IAU_EARTH` (0,07°) frente a ITRF93 (0,0002°): sin efecto en la red a 5 cifras; no compensa cargar 24 MB. Fuera de EOP medidas (más allá de ago-2026) mi propio contraste degrada a 0,0007°.
5. Los puntos y fechas de este informe son los del motor a 14/11/2026 (rejilla de idoneidad y barrido dic-2026); si cambia la rejilla, cambian los casos.

## Reproducir

```
python scripts/fetch_data.py            # kernels y DEM
# PCK de ITRF93 (no versionados):
curl -o data/raw/earth/earth_latest_high_prec.bpc https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_latest_high_prec.bpc
curl -o data/raw/earth/earth_2026_260806_2126_predict.bpc https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/earth_2026_260806_2126_predict.bpc
python -m pytest tests/test_independent_link.py -q -rxX     # 33 pasan + 4 xfail, ~40 s
```
