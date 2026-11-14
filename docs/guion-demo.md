# Guion de demostración (3 minutos)

Adaptado a lo que LSI hace de verdad. **Todas las cifras se recalcularon el 14/11/2026 ejecutando el pipeline real** (`lsi.pipeline`, SPICE, DEM, red DSN y estaciones reales) y cada una indica su origen. **Reconfirmar antes de grabar:** cualquier cambio del motor, de `config/` o del precálculo las mueve. Ya se movieron una vez: al pasar el score al enlace con continuidad, el punto de de Gerlache cambió de mejor fecha (de 2026-12-16 a 2027-06-21), su score del 16-dic pasó de 98,2 a 95,0 y el *Earthset* de Malapert del 29-dic pasó de 17,4 h a 16,3 h (ver «Coordenadas exactas»).

**Historia:** no basta con ver una montaña lunar; hay que entender si desde un punto concreto se ve el Sol, se ve la Tierra, **si alguna antena terrestre podría hablar con el lander** y durante cuánto tiempo, qué panel y qué montaje lo aprovechan, y qué confianza merece cada resultado.

## Antes de grabar (5 minutos, una vez)

1. `python -m streamlit run app.py`. Modo **Planificador** en la barra lateral.
2. Barra lateral → **Conectividad**: red **DSN**, sentido **recepción**, margen de antena **0°** (los valores por defecto; todas las cifras de enlace de abajo son con ellos).
3. Comprueba que «Mejores puntos y fechas» tiene datos (si no: `python scripts/precompute_suitability.py --profile lander_solar_no_rhu --profile rover --duration 7 --duration 14 --duration 30`; el mapa usa el enlace DSN en recepción).
4. **Reconfirma las cifras** de las tablas de abajo en la propia app. Si difieren, usa las de la app.
5. Deja el panel por defecto **Array vertical en mástil** (`tj-gaas-vertical-mast`, GaAs 3J de la misma celda de referencia): su montaje por defecto en el polo es **vertical con seguimiento azimutal** y reproduce las cifras de abajo (405 W/m², 9717 Wh/m² por día en Shackleton). **No elijas «GaAs triple unión (lander)» (`tj-gaas-lander-body`) en la app:** no admite el seguimiento y la pantalla pasa a *Vertical fijo* (Malapert: 272 W/m² de media en vez de 397; Shackleton: 1,4 % de la nominal). Las tablas de abajo con `tj-gaas-lander-body` + seguimiento son del motor (`run_analysis`), no de ese camino de la UI. Deja activado «Mostrar rangos de incertidumbre» en «Capacidad del sitio» (el primer cálculo es lento).
6. Precalienta la caché abriendo una vez cada punto y pulsando «Calcular la sensibilidad».

## Puntos y fechas que se usan

Perfil **lander solar sin RHU**, misión de **14 d**, altura del observador 2 m. **Teclea las coordenadas exactas** de la sección «Coordenadas exactas», no las redondeadas: con 4 decimales (≈ 11 m) la cuenta atrás de Malapert cambia ~1 h.

| Zona | Punto (lat, lon E) | Inicio (UTC) | Cómo se obtiene en la app |
|---|---|---|---|
| Shackleton (Site04) | −89,9353°, 217,6443° | **2026-12-12** | Buscador → «Shackleton» → «Evaluar este lugar» (elige el mejor punto del entorno del rasgo). Es el **TOP-2** del mapa; el TOP-1 queda a 16 km del centro, fuera del borde, y se descarta |
| Shackleton, TOP-1 del mapa (solo para el contraste 12-dic / 6-dic) | −89,5626°, 215,4724° | 2026-12-12 y **2026-12-06** | «Coordenadas propias» en la barra lateral (es el punto de `docs/validation/revision-enlace.md`) |
| de Gerlache (Site11) | −88,4530°, 292,1626° | 2026-12-16 | Buscador → «de Gerlache» → «Evaluar este lugar» (TOP-4 del mapa). **El mapa propone ahora 2027-06-21**; el 16-dic se elige a mano porque ilustra un hueco de comunicaciones |
| Mons Malapert (Site23) | −85,9841°, 2,6123° | **2026-12-16** | Buscador → «Malapert» con filtro de tipo *Mons* → «Evaluar este lugar» (TOP-1) |

Distancias de Shackleton (`pipeline.snap_candidate`, `prefer="best"`): el punto cae a **10,13 km del centro** del rasgo (−89,67°, 129,78°E) y a **0,34 km dentro de su borde** (radio 10,46 km). De Gerlache: 16,55 km del centro, **0,20 km fuera del borde** (radio 16,35 km, dentro del margen). Malapert: 9,10 km del centro, 24,4 km dentro del borde.

## Guion

| Tiempo | Acción en pantalla | Mensaje (lo que dices) |
|---|---|---|
| **0:00–0:20** | **Buscador**. Escribe «Shackleton»; menciona que hay 9106 lugares (9087 rasgos de la IAU/USGS y 19 sitios de misión). Pulsa «Evaluar este lugar». | «Buscamos por nombre entre 9106 lugares. Pero el nombre es el centro de un rasgo, no un sitio de aterrizaje: LSI elige el mejor punto dentro del rasgo. En Shackleton cae a unos 10 km del centro y a 0,34 km dentro del borde.» |
| **0:20–0:40** | **Mejores puntos y fechas** → Shackleton, lander sin RHU, 14 d. Señala el punto y su mejor fecha. | «El mapa ordena puntos y fechas. Mejor fecha de inicio para este punto: el 12 de diciembre de 2026. La elección ya tiene en cuenta los huecos de comunicaciones, no solo la luz.» |
| **0:40–1:20** | **Capacidad del sitio** (la pantalla que sigue al buscador). Recorre **Solar**, **Conectividad**, la sensibilidad al margen y la tabla de bases terrestres con la hora local. | «Con el panel de GaAs, vertical con seguimiento: Sol el 100 % de la ventana, noche máxima 0 h, unos 405 W y 9,7 kWh por metro cuadrado de panel y día. Conectividad: la Tierra visible y el enlace posible son el 100 %; contacto 24 h al día, sin hueco. Si la antena del lander necesitara ver la Tierra 3° o 5° sobre el horizonte, el enlace bajaría al 84 % y al 74 %, con huecos de más de 53 y de más de 88 horas. Las estaciones, con su hora local: Madrid, Goldstone y Canberra se turnan.» |
| **1:20–1:50** | «Capacidad del sitio» con las **coordenadas del TOP-1** (−89,5626°, 215,4724°E). Compara inicio **2026-12-12** con inicio **2026-12-06**. | «Mismo punto, otra fecha. El 12 de diciembre: enlace 100 %, APTO, score 97,4. El 6 de diciembre el Sol es igual de bueno, el 100 %, pero el enlace baja al 62 % y hay un hueco de 127 horas sin comunicaciones, hasta el 11 de diciembre. La puerta G7 falla y el veredicto es CONDICIONAL, score 73,9. Es la diferencia entre ver la Tierra y poder hablar con ella.» |
| **1:50–2:10** | **Score del sitio** (Shackleton, 12-dic): cambia el montaje a **Horizontal**. Después, **Potencia y paneles** en Malapert: GaAs 3J y 4J. | «El score depende del panel: con el montaje horizontal baja a 15 y el veredicto pasa a CONDICIONAL, porque la puerta G5 falla. En Malapert el montaje pesa más que la tecnología: el vertical con seguimiento da unas 35 veces la energía del horizontal (98,8 % frente a 2,8 % del máximo teórico), y cambiar de GaAs 3J a 4J apenas lo mueve. Tres de los ocho paneles son experimentales sin datasheet y salen etiquetados.» |
| **2:10–2:30** | **Horizonte y visibilidad** en **Mons Malapert**. Cursor en **2026-12-29 12:00 UTC** (periodo 2026-12-16 + 20 d). Enseña las tarjetas de cuenta atrás. | «El horizonte incluye terreno y curvatura. A mediodía del 29 de diciembre, la Tierra se pone en 16,3 horas y el Sol en 20,9: el *Earthset* llega unas 4,6 horas antes que el *sunset*.» |
| **2:30–2:45** | **Línea temporal**, 30 d desde 2026-12-16 en Malapert. | «Si la misión durara 30 días, el Sol aparece solo el 48 % del tiempo: 14,4 días de Sol y después una noche de al menos 375 horas (la ventana la corta, por eso "al menos"). Veredicto CONDICIONAL: solo 1 de 17 fechas de inicio probadas pasa.» |
| **2:45–3:00** | **Comparación de sitios** (Shackleton, de Gerlache, Malapert) y **Acerca de y límites**. Si hay tiempo, de Gerlache en «Capacidad del sitio». | «Los tres salen APTO en la fecha elegida, pero no hay ganador: de Gerlache, por ejemplo, pierde el enlace 16 horas antes de acabar la ventana. Enlace posible es geometría y cobertura de estación, no un presupuesto de radio; el DEM de 5 m tiene resolución efectiva de unos 30 m; no modelamos rocas, polvo ni eclipses.» + frase de cierre |

**Frase de cierre:**

> «Lunar Site Intelligence transforma topografía y efemérides lunares en una decisión visual y trazable. No entrega una puntuación mágica: permite entender cuándo un lugar ve el Sol, cuándo ve la Tierra, cuándo una antena terrestre podría hablar con él y cuánta confianza merece cada resultado.»

Añade, si hay tiempo: «Visibilidad geométrica no es potencia ni enlace garantizados.»

## De dónde sale cada cifra (reconfirmar antes de grabar)

Origen común: script de Python con `from lsi import pipeline as P`; `ctx = P.build_context(raíz)`; `P.run_analysis(ctx, AnalysisRequest(lat, lon, inicio, inicio + 14 d, panel_id="tj-gaas-lander-body", mounting=MountingSpec(MountingType.VERTICAL_AZ_TRACKING), with_uncertainty=True, snap_to_dem=False, mission_days=14))`, con los valores por defecto `link_network="DSN"`, `link_direction="receive"` y `min_earth_elevation_deg=None` (0° del perfil). El snap sale de `P.snap_candidate(ctx, lat, lon, prefer="best", profile_id="lander_solar_no_rhu", mission_days=14, feature_radius_km=P.feature_radius_km(ctx, gazetteer_id=...))` con los ids del gazetteer 5450 (Shackleton), 1439 (de Gerlache) y 16338 (Mons Malapert). Los scripts de comprobación no se guardan en el repositorio.

**Coordenadas exactas** (`snap_candidate` y el JSON del mapa las dan con todos los decimales):

| Punto | lat, lon E |
|---|---|
| Shackleton TOP-2 | −89,93534095487371; 217,6443152415009 |
| Shackleton TOP-1 | −89,56256875269997; 215,47240065149862 |
| de Gerlache | −88,45298231373764; 292,1625756877026 |
| Malapert | −85,98414346633864; 2,612332541796465 |

Con las coordenadas redondeadas a 4 decimales, la cuenta atrás de Malapert da 76 257 s y 62 757 s (21,2 h y 17,4 h, las cifras de la versión anterior de este guion); con las exactas, 75 328 s y 58 843 s. La diferencia es el horizonte a ~11 m, no un error del motor.

**Modelo fino, 14 d, panel con vertical con seguimiento (montaje por defecto en el polo)**

| Punto, inicio | Sol / Tierra (ventana) | Enlace · hueco máx. | Noche máx. | Score [rango] | Veredicto, confianza | Horizonte máx.\* | Potencia (% del máx. teórico) |
|---|---|---|---|---|---|---|---|
| Shackleton TOP-2, 2026-12-12 | 100 % / 100 % | 100 % · 0 h | 0 h | 94,7 [94,7–94,7] | APTO, alta (0,87) | 6,31° | 100,85 % |
| Shackleton TOP-1, 2026-12-12 | 100 % / 100 % | 100 % · 0 h | 0 h | 97,4 [97,4–97,4] | APTO, alta | — | 100,86 % |
| **Shackleton TOP-1, 2026-12-06** | 100 % / 62,1 % | **62,1 % · 127,5 h** (truncado) | 0 h | **73,9 [73,7–73,9]** | **CONDICIONAL** (G7: hueco de 127,5 h > 48 h; los 3 escenarios de incertidumbre también fallan G7), alta | — | 101,08 % |
| de Gerlache, 2026-12-16 | 100 % / 95,4 % | 95,4 % · 15,6 h (truncado) | 0 h | 95,0 [94,6–95,0] | APTO, alta (0,96) | 2,58° | 100,75 % |
| Malapert, 2026-12-16 | 100 % / 100 % | 100 % · 0 h | 0 h | 98,4 [98,4–98,4] | APTO, **media** (0,75) | 2,25° | 98,78 % |

\* Máximo de `horizon.h_lb_deg`.

- El **rango de ancho cero** (94,7–94,7) es real: en puntos saturados los escenarios de incertidumbre no mueven el score. No lo presentes como «certeza».
- La confianza mide la calidad del dato (huecos, error vertical, estabilidad del horizonte), no el riesgo de haber elegido el punto por optimización.
- Con el mismo TOP-1 **solo cambia la fecha** (6-dic frente a 12-dic): Sol 100 % en ambas. Con el punto TOP-2 el 6-dic es otra historia (Sol 61,9 %, noche 128 h, enlace 57,7 %, hueco 142 h, NO APTO por G0, G4 y G7): no mezcles las dos.
- El hueco de de Gerlache (15,6 h) está **al final** de la ventana: el enlace se pierde el 29-dic 08:24 UTC y no vuelve dentro del periodo. El del TOP-1 el 6-dic está **al principio**: del 5-dic 23:59 UTC al 11-dic 07:29 UTC, y lo recupera primero Canberra (11-dic 18:29 AEDT).

**«Capacidad del sitio», Shackleton TOP-2, 2026-12-12 + 14 d** (periodo = ventana; `result.metrics`, `result.power_summary`, `result.link`)

| Bloque | Cifra |
|---|---|
| Solar | Sol visible 100 %; noche máxima 0 h; ventana solar más larga 336 h (truncada: es toda la ventana); elevación solar máxima 1,4°. Potencia media 404,9 W/m² (100,85 % de la nominal de 401,5 W/m²), pico 406 W/m²; energía por día 9717 Wh/m² (media) y 9696 Wh/m² (mínima) |
| Conectividad | Tierra visible 100 %; **enlace posible 100 %**; horas de contacto por día 24,0 (media y mínima); ventana de enlace más larga 336 h (truncada); hueco máximo 0 h; G7 superada |
| Sensibilidad al margen de antena (periodo completo) | 0°: 100 %, 24,0 h/d, hueco 0 h · 3°: **84,1 %**, 20,2 h/d, hueco ≥ 53,5 h · 5°: **73,6 %**, 17,7 h/d, hueco ≥ 88,6 h |
| Estaciones (% del tiempo con enlace, h/día, ventanas) | Goldstone DSS-14 47,3 %, 11,3 h, 14 · Madrid DSS-63 47,7 %, 11,4 h, 14 · Canberra DSS-43 42,6 %, 10,2 h, 14 |
| Sentido de transmisión (10,1°) | enlace 99,0 %, hueco 0,66 h, score 94,6, APTO (cambia el sentido en la barra lateral) |

Sensibilidad del TOP-1 el 6-dic: 0°: 62,1 %, hueco ≥ 127,5 h · 3°: 43,8 %, ≥ 188,9 h · 5°: 31,8 %, ≥ 229,2 h. Malapert 16-dic: 100 % · 86,5 % · 78,1 %, huecos 0 / ≥ 45,2 / ≥ 73,6 h. De Gerlache 16-dic: 95,4 % · 81,8 % · 71,8 %.

**Estaciones con hora local de un día real** (copiadas de `ground_stations.daily_contact_table(result.link.contacts, t0, t1)`, Shackleton TOP-2, ventana 2026-12-12 + 14 d; **no las reconstruyas a mano**). Ventanas reales de cada estación que tocan el día UTC **2026-12-13** (una ventana que cruza la medianoche UTC aparece completa y marcada):

| Estación | UTC | Hora local civil (texto de la app) |
|---|---|---|
| Madrid DSS-63 | 13-dic 11:27:11 → 20:10:57 | 12:27–21:11 CET |
| Goldstone DSS-14 | 12-dic 18:21:59 → 13-dic 03:13:58 | 12/12 10:22–19:14 PST (continúa del día anterior) |
| Goldstone DSS-14 | 13-dic 18:51:05 → 14-dic 04:14:48 | 10:51–20:15 PST (continúa al día siguiente) |
| Canberra DSS-43 | 12-dic 22:34:50 → 13-dic 11:45:31 | 09:35–22:46 AEDT (continúa del día anterior) |
| Canberra DSS-43 | 13-dic 23:32:35 → 14-dic 12:15:01 | 14/12 10:33–23:15 AEDT (continúa al día siguiente) |

El día 2026-12-12 la app da Madrid 12:00–20:06 CET y Goldstone 10:22–19:14 PST (continúa al día siguiente). Las primeras ventanas de Goldstone y Canberra de ese día arrancan en el inicio del periodo (11/12 16:00–18:13 PST y 11:00–22:12 AEDT) y quedan cortadas por él: usa el 13-dic para la demo. **No cites** «Canberra 09:34–22:11 AEDT» ni «Goldstone 10:21–18:12 PST»: son ventanas inexistentes de un informe previo (partido por día UTC; `docs/validation/revision-enlace.md` §4).

**El score depende del panel y del montaje** (mismo punto y fecha; vertical fijo con la normal a azimut 0°)

| Punto | Vertical con seguimiento | Vertical fijo (az 0°) | Horizontal |
|---|---|---|---|
| Shackleton TOP-2, 12-dic | 100,85 % · score 94,7 · APTO | 1,40 % · 15,7 · CONDICIONAL (G5 falla: 1,8 % de la ventana con potencia útil) | 0,32 % · 15,0 · CONDICIONAL (G5: 0 %) |
| de Gerlache, 16-dic | 100,75 % · 95,0 · APTO | 37,27 % · 61,5 · CONDICIONAL (G5: 46,6 % < 50 %) | 0,55 % · 15,1 · CONDICIONAL (G5: 0 %) |
| Malapert, 16-dic | 98,78 % · 98,4 · APTO | 67,79 % · 90,4 · APTO | 2,82 % · 16,1 · CONDICIONAL (G5: 0 %) |

**Mapa precalculado** (`data/processed/suitability/windows_*.json`, el más reciente por sitio con el `MODULE_VERSION` actual; clave `<Site>|lander_solar_no_rhu|14d`; malla de 250 m, serie de 30 min, enlace DSN en recepción). Se lee con `lsi.analysis.suitability_map.best_points(Path("data/processed"), dem_key, "lander_solar_no_rhu", 14)`.

| Punto | Rango en el mapa | Mejor inicio del mapa | Score del mapa | Inicios aptos | Fichero |
|---|---|---|---|---|---|
| Shackleton TOP-2 | TOP-2 (el TOP-1, −89,5626°, 215,4724°E, queda a 16 km del centro, fuera del borde) | 2026-12-12 | 94,7 | 39 de 365 en el mapa; 37 de 366 en el modelo fino | `windows_Site04_lander_solar_no_rhu_92646b3309.json` |
| de Gerlache | TOP-4 | **2027-06-21** | 98,2 | 143 de 365 en el mapa; 143 de 366 en el modelo fino | `windows_Site11_lander_solar_no_rhu_29d7e51a35.json` |
| Malapert | TOP-1 | 2026-12-16 | 98,4 | 5 de 365 en el mapa; 5 de 366 en el modelo fino | `windows_Site23_lander_solar_no_rhu_ff01bc0bf3.json` |

**Reproducido el 14/11/2026.** Mapa: `apt_start_days` y `n_starts` leídos de cada JSON (39/365, 143/365 y 5/365). Modelo fino: `run_analysis` sin panel, periodo de 379 d desde 2026-12-01 (366 fechas de inicio con misión de 14 d), `snap_to_dem=False`, perfil `lander_solar_no_rhu`, `score.feasible_start_fraction × score.n_starts`: Shackleton TOP-2 37 de 366 (mejor inicio 2026-12-12), de Gerlache 143 de 366 (2027-06-21), Malapert 5 de 366 (2026-12-16). El mapa (malla gruesa, 365 fechas) y el modelo fino difieren en 2 fechas en Shackleton; cita siempre el denominador. Malapert 30 d: 1 de 17 (5,9 %) también reproducido.

Los tres con `g7_ok = True` y `max_link_gap_h = 0` en su mejor fecha. **Caso límite medido:** de Gerlache con inicio 2027-06-21 y periodo igual a la misión (14 d) da SIN DATOS en el modelo fino (`short_period`); con un periodo de 15 d da APTO, score 98,0. Alarga el periodo un día si quieres enseñar esa fecha.

**Cuenta atrás** (`result.countdowns`, periodo de 20 d desde 2026-12-16, `now_utc=2026-12-29T12:00:00`, Malapert, coordenadas exactas): el Sol se pone en 75 328 s (20,92 h, 2026-12-30 08:55 UTC) y la Tierra en 58 843 s (16,35 h, 2026-12-30 04:20 UTC); ambos siguen sobre el horizonte (`currently_up`), sin aproximación por cobertura. Diferencia: 4,58 h.

**Malapert, 30 d desde 2026-12-16** (`result.metrics` y `result.score`, periodo de 30 d y `mission_days=14`): f_sol 0,48; f_Tierra 0,73; enlace 72,9 %; noche máxima ≥ 375,1 h (truncada); ventana de Sol más larga 14,4 d (truncada); veredicto CONDICIONAL; 1 de 17 fechas de inicio factibles (5,9 %).

**Dos paneles, Malapert, 14 d** (`result.power_summary.pct_of_max`; incluye la pérdida por reflexión IAM de Fresnel):

| Panel | Horizontal | Vertical con seguimiento | Factor |
|---|---|---|---|
| `tj-gaas-lander-body` (respaldado) | 2,82 % | 98,78 % | 35,0× |
| `mj-4j-high-eff` (respaldado) | 2,78 % | 99,07 % | 35,6× |

Este factor es un promedio de la ventana con el Sol bajo; el de la pantalla «Potencia y paneles» (una tabla por elevación solar fija, `cos θ` con y sin IAM) y el de «Capacidad del sitio» (potencia media del periodo) son otros cálculos y no coinciden. No los mezcles.

**Validación del enlace que respalda estas cifras** (`docs/validation/revision-enlace.md`, `tests/test_independent_link.py`: 37 passed el 14/11/2026): Luna desde las estaciones frente a Horizons 0,0002–0,0007° con ITRF93 y 0,072° con la rotación simplificada del motor; cobertura DSN dic-2026 99,929 % en recepción y 97,992 % en transmisión; enlace 3D por fuerza bruta |Δ| ≤ 8e-4. En el 6-dic del TOP-1: enlace propio 62,07 % y motor 62,06 %; hueco 127,4 h y 127,5 h.

## Notas honestas para el presentador

- **Enlace posible = geometría + cobertura de estación.** No es presupuesto de enlace RF ni garantía: sin potencia, frecuencia, ganancia, ruido, ocupación del DSN ni máscara de terreno de la antena. Por defecto solo **recepción a 6°**; comandar exige 10,1° (97,99 % de cobertura DSN en dic-2026). No hay estaciones NSN (no se pudieron verificar); ESTRACK usa una elevación mínima supuesta.
- **El score cambia con el panel y el montaje** (en el mapa, sin panel, usa el Sol geométrico). Si un montaje falla G5, el veredicto baja a CONDICIONAL aunque el sitio vea el Sol el 100 % del tiempo. Si el hueco de comunicaciones falla G7 (blanda, umbrales supuestos de 12 a 96 h), también.
- **El veredicto depende del periodo.** Con 14 d (una sola fecha de inicio) Malapert sale APTO; con 30 d, CONDICIONAL.
- **El vertical fijo depende del azimut elegido** (aquí 0°); el vertical con seguimiento es una cota ideal. Valores por encima del 100 % son posibles (perihelio, frío); no se recortan.
- **Paneles:** cinco respaldados (tres GaAs 3J, 4J, ROSA; «respaldado» se refiere a la celda de referencia, no al conjunto) y tres experimentales sin datasheet (silicio, CIGS, perovskita-silicio). No presentes ROSA, 4J, CIGS ni perovskita como «usados en la Luna». W/m² y Wh/m² son de celda, sin empaquetado.
- **Tres APTO no son tres empates.** No digas que uno «gana».
- **Las fechas de diciembre de 2026** son lo que sale del precálculo, no una conclusión física explicada por LSI.
- **«Mejor punto» es un punto elegido por optimización** en una malla de 250 m con resolución efectiva de ~30 m: confírmalo siempre en el modelo fino. El TOP-1 de Shackleton está fuera del borde del cráter.
- **Horas locales:** cópialas de la tabla de la app o de `daily_contact_table`. No las derives restando husos a mano ni partiendo ventanas por día UTC.

## Plan B

| Si falla... | Haz esto |
|---|---|
| «Mejores puntos y fechas» está vacía (sin precálculo) | Elige el sitio en la barra lateral, inicio de la tabla, duración 14 días, y sigue desde **Capacidad del sitio**. Sin mapa, el buscador usa el punto cubierto más cercano y las cifras cambian. |
| «Capacidad del sitio» tarda | Desactiva «Mostrar rangos de incertidumbre» (respuesta inmediata) o habla del método (curvatura, disco finito, SPICE, cobertura DSN). Ten los puntos precalentados. |
| «Enlace posible: no calculado» | La red está en «Solo geometría»: elige DSN, recepción, margen 0°. |
| «Evaluar este punto y fecha» no cambia de página | Abre «Horizonte y visibilidad» o «Capacidad del sitio» desde el menú: el punto y la fecha ya están fijados. |
| No hay red | Los cálculos son locales. Que la interfaz funcione sin conexión **no se ha comprobado**: pruébalo antes de grabar. |
| Se rompe la app | Enseña las capturas de [`docs/capturas/`](capturas/) (31 JPG del QA visual del 14/11/2026, datos reales; **no incluyen** la pantalla «Capacidad del sitio») y, como último recurso, `python -m pytest -q tests/test_pipeline.py`. |
| Streamlit no arranca | `python -m pip install -r requirements.txt` y `python -m streamlit run app.py` desde la carpeta del proyecto. |

El vídeo grabado sigue **pendiente**.

## Qué NO decir en la demo

Fuente: `docs/science/paneles-y-misiones.md` §6.

- No digas «seguro», «aterrizable» ni «sitio recomendado»: di «zona candidata». «APTO» no certifica nada.
- No des vatios sin área: el panel se da en % de su potencia nominal o en W/m².
- No digas que el polvo está modelado ni prometas supervivencia nocturna.
- No presentes la visibilidad de la Tierra ni el «enlace posible» como un enlace de comunicaciones garantizado: visibilidad geométrica no es potencia ni enlace garantizados.
- No cites ventanas de estaciones que no salgan de la app («Canberra 09:34–22:11 AEDT» y «Goldstone 10:21–18:12 PST» no existen).
- No uses la elevación solar de ±1,5° como cifra de un sitio.
- Las figuras sintéticas (si las hubiera) deben decir que son ilustrativas; las capturas deben ser de datos reales.
