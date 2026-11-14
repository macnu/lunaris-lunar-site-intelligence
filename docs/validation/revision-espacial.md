# Revisión de ingeniería de misión del score y de sus puertas (T71)

Rol: ingeniero de sistemas de misiones lunares. Fecha de verificación de fuentes: 14/11/2026.
Etiquetas: **publicado** (leído en fuente ahora), **secundaria** (prensa/wiki, leído ahora), **convención**, **suposición**, **a verificar**.
Alcance: propuesta. No se ha tocado `src/` ni `config/`.

## 0. Diagnóstico

El hallazgo es correcto y es un error de **semántica**, no de umbral. La puerta G4 (`D_max ≤ 12 h`) responde a «¿sobrevive la batería a la noche más larga que la misión va a atravesar?». Hoy se evalúa sobre 365 d, así que pregunta «¿sobrevive a la peor noche del año?». Ninguna misión solar real está sometida a eso:

- IM-1 se diseñó para ~14 d (panels.json, secundaria) e IM-2 para ~10 d (secundaria: spacepolicyonline, astronomy.com).
- Blue Ghost M1 aterrizó el 02/03/2025 y se apagó el 16/03/2025 al ponerse el Sol, tras ~2 semanas (secundaria: spaceflightnow, space.com). Una fuente de segunda mano cita 346 h con Sol y ~5 h tras el ocaso: **a verificar** contra Firefly.
- Chandrayaan-3 se diseñó para ~1 día lunar, sin calentadores; no despertó el 22/09/2023, sin señal (secundaria: theprint, space.com, Universe Today).
- Chang'e-4 sobrevive las noches con RHU y registró ~−190 °C en la primera (secundaria: space.com). Yutu-2: vida de diseño de 3 meses (secundaria).
- VIPER: misión de 100 d, 3 ciclos día/noche, autonomía en modo mínimo ~50 h, ~9,5 h trabajando en sombra con taladro (publicado: NASA, NTRS 20220008301 y overview de planificación; PDF NASA).

Conclusión: la unidad de decisión no es «sitio», es **(sitio, fecha de inicio, duración de misión, perfil)**. Eso es lo que pide el reto («fechas de aterrizaje»). El sitio sin ventana solo es correcto para el perfil base/ISRU (vida de años).

## 1. Duración de misión por perfil

| Perfil | `mission_days` | Etiqueta | Razonamiento y fuente |
|---|---|---|---|
| `lander_solar_no_rhu` (clase CLPS) | **14** (alternativa corta 10) | publicado en lo básico (IM-1 14 d; IM-2 ~10 d; Blue Ghost ~14 d; Chandrayaan-3 ~1 día lunar), valor elegido = convención | Todos los landers solares sin RHU de los últimos años se diseñan para un día lunar o menos. 14 d ≈ medio mes sinódico (29,53 d, constante conocida) |
| `lander_with_batteries` | **30** | suposición | ~1 mes sinódico. Con batería para ≤36 h (suposición ya existente) solo cabe en sitios de noche corta; en polo la ventana de 30 d es la que discrimina |
| `lander_rhu` (propuesto, nuevo) | **90** | suposición | Chang'e-4: RHU, sobrevive noches. Yutu-2 diseñado a 3 meses (secundaria). G4 no aplica; sí pendiente, Tierra y Sol de llegada. Si no se quiere perfil nuevo, omitir |
| `rover` | **100** | publicado (VIPER-class) | VIPER, 100 d. Un rover pequeño tipo Pragyan sería ≈ perfil lander (no sobrevivió la noche) |
| `base_isru` | **365** | suposición | Operación continua. Es el único perfil donde evaluar el año entero es correcto. El requisito de 10 años de NASA FSP es de fisión, no de solar |
| `dte_comms` | **365** (o la del perfil anfitrión) | suposición | Un nodo de comunicaciones es infraestructura; sin puerta solar |

Importante: la duración **no es un deseo, es lo que la noche permite**. Para un lander sin RHU, `mission_days` es el horizonte de planificación; la salida útil es además `max_sustainable_days` (sección 2.4): cuántos días opera desde cada fecha hasta la primera noche que viola G4.

## 2. Puertas sobre la ventana de misión

### 2.1 Definiciones

Sea `W(t0) = [t0, t0 + mission_days]` y `t0` en una rejilla de fechas de inicio candidatas (paso `start_step_h`, convención 24 h; ya existe línea de tiempo a 600 s, por lo que el coste marginal es barrido de ventanas, no re-simulación).

Todas las métricas se recalculan **recortadas a `W`**:

- `f_sun_W`, `f_earth_W`: fracción de tiempo en `W`.
- `D_max_W`: noche continua más larga con cada intervalo de oscuridad **recortado a `W`**. La bandera `truncated` solo se activa si el recorte ocurre en el borde **final** y la noche no ha terminado (cota inferior inútil: la misión ha acabado ahí, no hay nada que acotar). Una noche que se corta en `t0` implica llegar de noche: se trata por la puerta G0.
- `window_earth_max_h`: ventana de Tierra continua más larga en `W`.

| Id | Puerta | Regla sobre `W(t0)` | Tipo |
|---|---|---|---|
| G0 | Llegada | Sol visible en `t0` (y, si el perfil tiene `needs_earth_at_landing`, Tierra visible en `t0`) | hard, convención |
| G1 | Energía | `f_sun_W ≥ g1_min_sun_fraction` | hard (solo perfiles solares) |
| G2 | Pendiente | `slope_p90 ≤ max_landing_slope_deg` (no depende de la fecha) | hard |
| G3 | Datos | igual que hoy (terreno/DEM/observador) | estado, no rechazo |
| G4 | Noche | `D_max_W ≤ max_dark_h_no_nuclear` | hard en lander/base; **soft en rover** (el rover se desplaza hacia la luz, VIPER planificaba «safe havens» de <50 h de sombra; un sitio estático lo penaliza demasiado) |
| G5 | Potencia útil | `duty_useful_W ≥ min_duty_useful` donde `duty_useful_W` = fracción de `W` con `P_rel ≥ min_useful_power_fraction` | soft (hard en base) |
| G6 | Tierra | `window_earth_max_h ≥ min_contiguous_earth_window_h` | soft; **hard en `dte_comms`** |

Nota sobre G0 y Apolo: los alunizajes tripulados fueron con luz; que el Sol sea visible en `t0` es convención operativa. No se cita aquí ningún ángulo solar de aterrizaje: **a verificar** antes de usarlo como umbral.

### 2.2 «Mejor fecha de inicio»

Para cada `t0` válido se calcula un resultado completo (puertas + score con los mismos `s_i`, ahora sobre `W`). Se reporta:

1. `best_start_utc` = `t0` de mayor score entre las que superan **todas las puertas hard**. Empate: la más temprana (la de mayor margen en G4 si aún empata).
2. `best_window` = `[t0, t0+mission_days]`, `score`, `score_min`, `score_max` (rango por escenarios de incertidumbre ya existentes).
3. `feasible_start_fraction` = fracción de `t0` que pasan las puertas hard (**robustez**: una ventana única y estrecha es frágil frente a un retraso del lanzamiento).
4. `top_windows`: hasta 3 ventanas no solapadas (separadas ≥ `mission_days`), para presentar alternativas.
5. Si ninguna `t0` pasa: `best_start_utc = null`, se muestra la `t0` de menor violación (marcada «no apta») y `max_sustainable_days`.

Sin ventana completa en el periodo (periodo < `mission_days`): estado **SIN DATOS**, motivo «periodo más corto que la misión».

### 2.3 Lo que cambia con la ventana de 14 d

En un sitio con iluminación casi continua (Mazarico et al. describen ubicaciones del polo con iluminación casi continua; las cifras concretas de oscuridad máxima **no se han podido re-verificar en esta pasada**, ver sección 5) las 15 mejores celdas pasarán a evaluarse en ventanas de 14 d. Las noches de 96–400 h dejan de descartar el sitio **si caen fuera de la ventana**. Pierden las `t0` cuya ventana contiene el inicio de una noche >12 h, lo cual es exactamente la información operativa que se quiere («aterrizar en esta fecha, no en esa»).

### 2.4 `max_sustainable_days`

Para cada `t0` con G0 superada: tiempo hasta el primer instante en que una noche en curso supera `max_dark_h_no_nuclear` **o** el sitio deja de cumplir G1 acumulada. Reportar mediana, mejor valor y su fecha. Es la respuesta a «¿cuántos días puede operar un lander solar aquí?» y es comparable entre sitios sin fijar `mission_days`.

## 3. Umbrales por perfil, revisados

| Perfil | Potencia mín. útil | Noche máx. (G4) | Ventana Tierra mín. | Pendiente de diseño | Duty mín. (G5) |
|---|---|---|---|---|---|
| lander_solar_no_rhu | 0,25 (suposición) | 12 h hard (estimado: 25 Ah·28 V·0,8/50 W; Wikipedia, secundaria; carga de 50 W suposición) | 2 h soft (suposición) | 10° diseño / 5° navegación (declaración del CTO de IM, secundaria) | 0,5 soft (suposición) |
| lander_with_batteries | 0,25 (suposición) | 36 h hard (suposición) | 2 h soft (suposición) | 10° / 5° | 0,5 soft |
| lander_rhu | 0,25 (suposición) | no aplica | 2 h soft | 10° / 5° | 0,5 soft |
| rover | 0,30 (suposición) | **50 h soft** (publicado VIPER: autonomía en modo mínimo ~50 h, NASA); 12 h solo si es rover pequeño sin batería de hibernación (suposición) | 2 h soft | hereda lander; traverso 15° **a verificar** | 0,5 soft |
| base_isru | 0,75 hard (suposición) | 24 h hard (suposición) | 8 h soft (suposición) | 5° (suposición) | 0,75 hard (suposición) |
| dte_comms | no aplica | no aplica | 2 h **hard** (suposición) | no aplica | no aplica |

Cambios respecto al catálogo actual: (a) rover pasa de 12 h hard (suposición) a 50 h soft (publicado para VIPER-class) porque tiene movilidad; (b) se añade `duty_useful` porque `min_useful_power_fraction` hoy no se usa en ninguna puerta; (c) todo lo demás se conserva y sigue como suposición.

**Pendiente:** el valor de 10° es declaración de prensa, no especificación. Las búsquedas actuales confirman la inclinación final de Odysseus en ~30° y la declaración «diseñado para quedar en pie con pendientes de 10° o más» del CTO (secundaria); **no confirman los ~12° de pendiente local** citados en `panels.json`.

## 4. Estados APTO / CONDICIONAL / NO APTO / SIN DATOS

El `APTO_MIN = 60` es una suposición sin base física: la nota agregada es media geométrica de rampas normalizadas arbitrarias (`f0`, `f1`, `d_half`, `sigma`); no hay razón para que 60 separe «apto» de «no apto». **Propuesta: el estado lo deciden las puertas y los escenarios, no el score.** El score solo ordena.

Se evalúan las puertas hard sobre el **mejor `t0`** en el escenario nominal y en todos los escenarios de incertidumbre ya calculados:

| Estado | Definición |
|---|---|
| **SIN DATOS** | Falta un dato imprescindible: (i) periodo < `mission_days`; (ii) G3 = sin datos (sin DEM, observador fuera, horizonte desconocido > 50 %) y las puertas con datos no deciden el rechazo; (iii) el perfil necesita una magnitud que no se calculó |
| **NO APTO** | No existe ninguna `t0` que supere todas las puertas hard con los datos disponibles (con DEM: definitivo; sin DEM: «NO APTO (provisional)», ver abajo) |
| **CONDICIONAL** | Existe al menos una `t0` válida pero: pasa solo en el nominal y falla en algún escenario; o `feasible_start_fraction < 0,10` (ventana muy frágil; convención ajustable); o falla alguna puerta soft; o algún margen hard < 10 % del umbral (convención) |
| **APTO** | Mejor `t0` supera todas las hard en nominal y en todos los escenarios, sin soft fallida y con margen ≥ 10 % |

Todos los porcentajes anteriores son **convención/suposición**, expuestos en `config` y marcados en la UI. La estrella/nota 0–100 se mantiene como ordenación y como «cuánto margen hay», nunca como veredicto. Opcional y más defendible que el 60: mostrar el score del sitio junto al de **un sitio de referencia** (p. ej. el mejor punto del DEM del mismo perfil) en lugar de un umbral absoluto.

### Modo parcial (sin terreno)

El modelo de esfera lisa **no es una cota estricta**: normalmente el relieve reduce el Sol y alarga las noches, pero un observador en cresta puede ver más que sobre la esfera. Regla propuesta:

- Puerta hard que **falla ya con esfera lisa** (p. ej. noche de ventana > límite): «NO APTO (provisional)», porque el relieve rara vez lo arregla. Se etiqueta «cota optimista».
- Todas las hard pasan con esfera lisa: **SIN DATOS**, nunca APTO ni CONDICIONAL, y se muestra el score con su rango parcial.
- G2 sin DEM: no evaluable, nunca «pasa».

### ¿Es correcto que Apolo 11 salga NO APTO?

**No tal como sale hoy, y el motivo es la ventana, no el resultado final.** Hoy: 327 h > 12 h sobre el periodo analizado, lo que mezcla dos cosas (la noche existe, pero la misión no la atraviesa). Con ventana de 14 d iniciada al amanecer local la noche no cae en `W`, G4 pasa, y en un sitio ecuatorial sin DEM el estado correcto es **SIN DATOS** (G2 y G3 no evaluables). Hecho no controvertido: el LM operó en superficie ~21,5 h tras alunizar el 20/07/1969 (hecho histórico; coordenadas y cifras de EASEP **no verificadas aquí**). Para un perfil sin RHU de 100 d, sí saldría NO APTO, y con razón. El resultado es sensible al perfil elegido, lo cual debe mostrarse.

## 5. Revisión del catálogo frente a fuentes verificables ahora

| Elemento | Hallazgo | Acción |
|---|---|---|
| Chandrayaan-3 (doc §5, panels.json) | «Reactivación no confirmada»: **confirmado más fuerte**: sin calentadores, programado para despertar el 22/09/2023, sin señal (secundaria) | Actualizar estado a «no se reactivó (sin señal de ISRO)»; sigue sin RHU: ejemplo de misión de un día lunar |
| IM-2 Athena (§5) | Planificada ~10 d; aterrizó de costado y terminó en <1 día (secundaria). Una wiki espejo da «8 d 5 h»: contradice, descartar | Añadir `planned_days: 10`; mantener «~24 h» como a verificar |
| Blue Ghost M1 (§5, panels.json) | Misión completada y apagada al ocaso el 16/03/2025 tras ~14 d; «346 h de Sol + ~5 h» es de segunda mano | Añadir fecha de fin y duración; la cifra horaria queda a verificar |
| VIPER (§5) | Fila «2027, fuente secundaria»: **cierto con matices**: tarea con Blue Origin en Blue Moon MK1, entrega «a finales de 2027», sin compromiso firme hasta opción posterior (secundaria; la fecha del anuncio, sept. 2025, la dan varias fuentes) | Mantener 2027 con etiqueta «condicionada a Blue Moon MK1» |
| Rover, `max_dark_h_no_nuclear` = 12 h | 12 h es suposición; VIPER publica 50 h en modo mínimo | Cambiar según §3 |
| Odysseus ~12° | No confirmado en esta pasada (sí ~30° final y «≥10°» de diseño) | Marcar 12° como a verificar |
| Chang'e-4 (§1.3, §5) | −190 °C en la 1.ª noche, RHU: confirmado (secundaria) | Ninguna |
| Mazarico: oscuridad máx. ~1,5 d, ~240 d de Sol | La búsqueda confirma el artículo y su método (Icarus 211, 1066-1081, 240 m/px, paso de 1 h) pero **no se leyeron esas cifras** | Mantener «a verificar» hasta leer el paper/PDS |
| Wikipedia como fuente de potencia (200 W, 25 Ah) | Seguían siendo secundaria; el cálculo de 12 h depende de ella | Mantener etiqueta «estimado» |
| `dust_loss`, IAM, coeficientes de temperatura de los paneles | No revisados en esta pasada (sin fuente nueva leída) | Sin cambios |

No se ha encontrado en esta revisión ningún error numérico claro en el catálogo de paneles; las discrepancias son de **estado de misión y de etiquetas**.

## 6. Especificación para el código (propuesta, copiable a `config/simulation.json`)

```jsonc
"score": {
  // ...f0, f1, d_half_h, sigma0_deg, sigma1_deg, eps_s, confidence: sin cambios...
  "window": {
    "start_step_h": 24,                // convención: rejilla de fechas de inicio
    "min_separation_days_top": "mission_days",
    "top_n_windows": 3,
    "arrival_gate": {"needs_sun": true, "needs_earth": false}   // G0, convención
  },
  "status_rules": {
    "decide_by": "gates_and_scenarios",  // el score deja de decidir el estado
    "hard_margin_fraction": 0.10,        // convención: margen mínimo en puertas hard
    "min_feasible_start_fraction": 0.10, // convención: robustez de la ventana
    "partial_mode": {"hard_fail_on_sphere": "NO_APTO_PROVISIONAL", "all_pass_on_sphere": "SIN_DATOS"}
  },
  "profiles": {
    "lander_solar_no_rhu":   {"mission_days": 14,  "uses_solar_gate": true,  "gates_scope": "window"},
    "lander_with_batteries": {"mission_days": 30,  "uses_solar_gate": true,  "gates_scope": "window"},
    "lander_rhu":            {"label": "Lander con RHU", "mission_days": 90, "uses_solar_gate": true, "gates_scope": "window",
                              "weights": {"sun": 0.40, "night": 0.10, "earth": 0.25, "terrain": 0.25}},
    "rover":                 {"mission_days": 100, "uses_solar_gate": true,  "gates_scope": "window"},
    "base_isru":             {"mission_days": 365, "uses_solar_gate": true,  "gates_scope": "window"},
    "dte_comms":             {"mission_days": 365, "uses_solar_gate": false, "gates_scope": "window"}
  }
}
```

Y en `config/panels.json` → `mission_profiles` (claves nuevas o cambiadas; el resto igual):

```jsonc
"lander_solar_no_rhu": {
  "mission_days": {"value": 14, "confidence": "publicado", "note": "IM-1 ~14 d, IM-2 ~10 d, Blue Ghost ~14 d, Chandrayaan-3 ~1 día lunar; valor elegido = convención"},
  "min_duty_useful": {"value": 0.5, "type": "soft", "confidence": "suposicion"}
},
"lander_with_batteries": {
  "mission_days": {"value": 30, "confidence": "suposicion", "note": "~1 mes sinódico"},
  "min_duty_useful": {"value": 0.5, "type": "soft", "confidence": "suposicion"}
},
"lander_rhu": {
  "label": "Lander con RHU (clase Chang'e-4)",
  "mission_days": {"value": 90, "confidence": "suposicion", "note": "Chang'e-4 sobrevive noches con RHU; Yutu-2 diseñado a 3 meses"},
  "max_dark_h_no_nuclear": {"value": null, "type": "n/a", "confidence": "publicado", "note": "RHU: sin límite de batería"},
  "min_useful_power_fraction": {"value": 0.25, "type": "soft", "confidence": "suposicion"},
  "min_contiguous_earth_window_h": {"value": 2, "type": "soft", "confidence": "suposicion"},
  "max_landing_slope_deg": {"design": 10, "navigation_target": 5, "type": "hard", "confidence": "publicado"}
},
"rover": {
  "mission_days": {"value": 100, "confidence": "publicado", "note": "VIPER, 100 d, 3 ciclos día/noche (NASA)"},
  "max_dark_h_no_nuclear": {"value": 50, "type": "soft", "confidence": "publicado", "note": "VIPER: autonomía en modo mínimo ~50 h (NASA, NTRS 20220008301); rover pequeño sin batería de hibernación: 12 h (suposición)"},
  "min_duty_useful": {"value": 0.5, "type": "soft", "confidence": "suposicion"}
},
"base_isru": {
  "mission_days": {"value": 365, "confidence": "suposicion", "note": "operación continua; 10 años de NASA FSP son de fisión"},
  "min_duty_useful": {"value": 0.75, "type": "hard", "confidence": "suposicion"}
},
"dte_comms": {
  "mission_days": {"value": 365, "confidence": "suposicion"},
  "min_contiguous_earth_window_h": {"value": 2, "type": "hard", "confidence": "suposicion"}
}
```

### Salida esperada de `compute_score` por ventana (campos nuevos de `SiteScoreResult`)

`mission_days`, `best_start_utc | null`, `best_window_end_utc`, `feasible_start_fraction`, `top_windows[{start_utc, score, score_min, score_max}]`, `max_sustainable_days{median, best, best_start_utc}`, `status` (4 valores), `status_reason`, y por puerta: `id, status, value, limit, margin_fraction, window` (la `reason` actual se conserva).

### Pruebas mínimas sugeridas (valores independientes)

1. Sitio con noche única de 100 h en el día 200 del año: con `mission_days = 14`, fallan las `t0` cuya ventana solapa >12 h con la noche (recorte a `W`): intervalo de longitud 14 d + (100 − 24) h = 412 h sobre 351 d de inicios posibles → `feasible_start_fraction ≈ 1 − 412/8424 ≈ 0,95`, no 0 (con la regla anual actual el sitio es NO APTO).
2. Sitio con una noche de 100 h cada 30 d: lander 14 d → existe `t0` válida; base 365 d → NO APTO.
3. Periodo de 10 d y `mission_days = 14` → SIN DATOS.
4. Sin DEM con G4 que falla en esfera → «NO APTO (provisional)»; con todo pasando → SIN DATOS.
5. Estado invariante al cambiar `APTO_MIN` (ya no existe); score solo reordena.

## 7. Límites de esta revisión

Todo parámetro con etiqueta «suposición» o «convención» lo es de LSI y no de agencia. La visibilidad solar es geométrica (sin polvo, IAM ni pluma de aterrizaje). Las fuentes de misiones son prensa o wikis (secundarias); donde hay cifra de segunda mano se ha dicho. Sigue **a verificar**: ángulo solar de aterrizaje (Apolo/CLPS), requisito de pendiente de traverso de VIPER, cifras de oscuridad máxima de Mazarico, vida útil real del EASEP de Apolo 11.

### Fuentes leídas en esta revisión

- Chandrayaan-3: https://theprint.in/science/chandrayaan-3-lander-rover-put-on-sleep-mode-for-lunar-night-isro-hopes-they-wake-up-on-22-sept/1745709 · https://www.space.com/india-chandrayaan-3-no-heaters-lunar-night-survival · https://www.universetoday.com/163394/day-has-returned-but-indias-lander-and-rover-have-failed-to-wake-up
- IM-2: https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/ · https://spaceflightnow.com/2025/02/25/live-coverage-spacex-to-launch-intuitive-machines-moon-lander-on-falcon-9-rocket-from-the-kennedy-space-center/
- Blue Ghost M1: https://spaceflightnow.com/2025/03/18/firefly-aerospaces-blue-ghost-mission-1-concludes-successful-14-day-mission-on-the-moon/ · https://www.space.com/the-universe/moon/farewell-blue-ghost-private-moon-lander-goes-dark-to-end-record-breaking-commercial-lunar-mission
- Chang'e-4 / Yutu-2: https://space.com/43192-china-farside-moon-mission-survives-lunar-night.html · https://en.wikipedia.org/wiki/Yutu-2
- VIPER (NASA): https://ntrs.nasa.gov/api/citations/20220008301/downloads/2022-06-02-spaceops-viper-planning.pdf · https://www.nasa.gov/wp-content/uploads/2022/05/overview_of_mission_planning_for_the_viper_rover.pdf · Blue Origin: https://www.space.com/astronomy/moon/viper-lives-jeff-bezos-blue-origin-will-land-ice-hunting-nasa-rover-on-the-moon-in-2027
- Odysseus: https://www.flyingmag.com/odysseus-lunar-lander-alive-well-but-likely-not-upright
- Mazarico et al. 2011 (método): https://ntrs.nasa.gov/citations/20120010094
