# Paneles solares, perfiles de misión y umbrales (LSI)

Autor del rol: ingeniero de sistemas de misiones lunares. Fecha de verificación de fuentes: 14/11/2026.
Datos en `config/panels.json` (esquema en la sección 1). Etiquetas de confianza:
**publicado** (leído en datasheet/paper/nota oficial), **estimado** (derivado; se indica el cálculo),
**suposición** (parámetro de diseño de LSI, sin fuente, configurable) y **a verificar** (recuerdo o fuente secundaria).

> Regla de lectura: ningún número de este documento debe aparecer en la UI sin su etiqueta de confianza.

## 1. Catálogo de paneles

### 1.1 Esquema de `config/panels.json`

| Clave | Contenido |
|---|---|
| `reference` | Constante solar 1361 W/m², T de referencia de célula 28 °C, albedo (opcional), diámetro angular del Sol |
| `mounting_modes` | Las cuatro geometrías (`horizontal`, `tilted`, `vertical_fixed`, `vertical_az_tracking`) con su fórmula de cos θ |
| `model_defaults` | Fórmula de `P_rel`, tope de ganancia en frío, factores por defecto de radiación y polvo, modelo térmico |
| `panels[]` | `id`, `name`, `cell_technology`, `mounting_default`, `mounting_allowed`, `efficiency_bol_pct{min,max,default,basis,confidence}`, `temp_coeff_pmax_pct_per_K{value,valid_range_C,derivation,confidence}`, `ref_temperature_C`, `thermal{absorptivity_front, emissivity_front, emissivity_back}`, `mass_and_specific_power`, `degradation_defaults`, `iam`, `missions[{name,role,confidence,note}]`, `sources[{id,ref,url}]` |
| `mission_profiles` | Umbrales por perfil (sección 2). Cada umbral: `value`, `type` (`hard`/`soft`), `confidence`, `note`. La clave `_note` no es un perfil: el código debe ignorar claves que empiezan por `_` |
| `sources_global` | Fuentes de iluminación, DSN y polvo |

Los campos desconocidos son `null` con `confidence: "a_verificar"`; el código debe tratarlos como "no calculable" (p. ej. no estimar temperatura si falta α/ε), no como cero.

**Evidencia de fuente primaria (14/11/2026).** Cada panel lleva `evidence_group` (`respaldado` | `experimental_sin_datasheet`), `evidence_level` (`datasheet` | `paper` | `derivado` | `investigacion`; el del eslabón más débil entre η y γ_T), `evidence_summary` y `areal_power_w_m2_am0` (= η·1361 W/m², solo celda/CIC). Cada parámetro lleva además `evidence` (`datasheet`, `paper`, `derivado`, `investigacion` o `no_disponible`) y `source` (ids `D1…D19` del bloque `datasheet_sources`: URL, fichero en `data/raw/datasheets/`, fecha de lectura). El campo `confidence` conserva los cuatro niveles antiguos que usa la UI (`datasheet`/`paper` → `publicado`; `derivado` → `estimado`; aproximación propuesta → `suposicion`; sin fuente primaria → `a_verificar`). El registro completo, parámetro a parámetro con página, está en `docs/validation/datos-paneles.md`. Los tres paneles del grupo **experimental_sin_datasheet** (`si-legacy`, `cigs-thin-film-flex`, `perovskite-si-tandem-demo`) siguen llevando `estimate_without_datasheet` y rangos, se muestran etiquetados «estimación sin datasheet» y **no deben mezclarse con los respaldados en rankings por defecto** (`panels.split_by_evidence_group()`). `panels.panel_status()` distingue `no_calculable`, `estimado` (experimental) y `calculable`; `panels.power_band()` devuelve la banda [P_min, P_max] recalculando solo η_rel en las 4 esquinas {T caliente, T fría}×{γ_T mín, γ_T máx}. La banda mide la incertidumbre de los parámetros, no un error estadístico, y no cubre la degradación por radiación ni el polvo.

### 1.2 Entradas

| id | Tecnología | η BOL (defecto) | Coef. T (%/K) | Montajes | Estado de verificación |
|---|---|---|---|---|---|
| `tj-gaas-lander-body` | InGaP/GaAs/Ge 3J | 29,5 % (29,1–30,7) · 401 W/m² | −0,23 (derivado) | horizontal, inclinado, vertical fijo | **Respaldado · datasheet** (Azur p.2, Spectrolab p.1-2). Uso en CLPS: Blue Ghost 400 W leído en Firefly/Rocket Lab; celda no declarada |
| `tj-gaas-vertical-mast` | 3J en mástil (VSAT/LSITP) | 29,5 % · 401 W/m² | −0,23 (heredado) | vertical fijo / con seguimiento | **Respaldado · derivado** (celda 3J de referencia); la celda de VSAT y sus cifras no están publicadas ni releídas |
| `mj-4j-high-eff` | Z4J+ / Z4J / IMM-α (Rocket Lab) | 31,3 % (30,0–32,0) · 426 W/m² | −0,264 (Z4J+ medido 28–80 °C); −0,25 (Z4J); −0,195 (IMM-α proyectado) | todos | **Respaldado · datasheet**; uso lunar a verificar |
| `rosa-flexible-rollout` | Manta enrollable ROSA | 29,5 % (celda 3J; manta no publicada) · 401 W/m² cota | −0,23 (heredado) | inclinado, vertical | **Respaldado · derivado**: arquitectura agnóstica a la celda; 71–124 W/kg de array derivados del flysheet Redwire; solo ISS/Gateway |
| `si-legacy` | Silicio (Sharp, Azur) | 17,4 % (16,9–17,4) · 237 W/m² | −0,45 (**no disponible**; rango −0,60…−0,30) | horizontal, inclinado | **Experimental**: η y radiación de datasheet Sharp; γ_T, α, ε sin fuente |
| `cigs-thin-film-flex` | CIGS flexible | 15,7 % (8,84–15,7) · 214 W/m² | −0,38 (módulo **terrestre** AM1.5) | horizontal, inclinado, vertical fijo | **Experimental · investigación**: AM0 solo de nota de prensa y paper de laboratorio 2002 |
| `perovskite-si-tandem-demo` | Perovskita/Si-SHJ | 19,2 % AM0 (19,2–27,49) · 261 W/m² | −0,26 (**no disponible** en fuente leída) | horizontal | **Experimental · investigación**: Joule 2020 (paper leído); cae a ~1 % con protones |
| `tj-gaas-rover-body` | 3J en rover | 29,5 % · 401 W/m² | −0,23 (heredado) | horizontal, inclinado | **Respaldado · derivado** (celda de referencia); Pragyan/Yutu-2 degradados a «a verificar» |

Derivaciones de los coeficientes de temperatura (**derivados** de datasheets leídos; páginas en `datos-paneles.md`):

- `dP/dT = Vmp′·Jmp + Jmp′·Vmp`. XTJ Prime (15–125 °C): (−6,3 mV/K · 17,5 mA/cm² + 5,0 µA/cm²/K · 2,406 V) / 42,1 mW/cm² = **−0,233 %/K**. La unidad de Jmp′ sale corrupta en el PDF; por magnitud es µA/cm²/K. NASA/JPL D-101316 (PDF p.30) lista −0,22 %/°C para XTJ Prime y −0,23 % para 3G30C.
- Azur 3G30C 6x12 (28–140 °C): (−6,7 mV/K · 1185 mA + 0,57 mA/K · 2,4 V) / 2844 mW = **−0,231 %/K**. Coincide con el anterior: buena señal.
- Rocket Lab Z4J+ (28–80 °C, medido): Pmp′ = −0,1117 mW/cm²/K sobre 42,37 mW/cm² (3,31 V · 12,8 mA/cm²) = **−0,264 %/K**. Z4J: −103 µW/cm²/K sobre 40,7 mW/cm² = **−0,253 %/K**.
- IMM-α: coeficientes **proyectados** por el fabricante (no medidos; nota al pie p.2): −0,195 %/K.
- Rango de validez: se miden entre 15 y 140 °C. A bajas temperaturas lunares (≈ 120–150 K en paneles horizontales, ver 3.4) la extrapolación lineal sobrestima la ganancia: `cold_gain_cap = 1,15` (**suposición**). Azur cita 33,5 % BOL a −150 °C, pero en condiciones de baja intensidad (LILT, ~3,7 % AM0) y para otra célula: no es un dato extrapolable.
- Específicos de célula/CIC (solo celda, no panel): XTJ Prime 495–831 W/kg; Azur CIC 320 W/kg; IMM-α 884 W/kg; Si Azur 715 W/kg. Array completo (NASA/JPL D-101316 PDF p.33-34): ~80 W/kg y ~330 W/m² rígido; 100–175 W/kg y ~338 W/m² flexible. ROSA (flysheet Redwire): 71–124 W/kg según configuración.

Absortividad 0,91 (Azur 3G30A, p.2; JPL: XTJ Prime 0,88, ZTJ 0,92) es el único α **publicado**; **ningún** datasheet leído da emisividad: las ε (0,85/0,80) son suposiciones o a verificar en todos los paneles.

### 1.3 Qué se verificó de las misiones

- **Nova-C (IM-1 Odysseus, IM-2 Athena):** 3 paneles (cubierta + 2 laterales), máximo 200 W, batería 25 Ah / bus 28 VDC (Wikipedia, fuente secundaria: **a verificar**; el press kit NASA IM-1 se leyó el 14/11/2026 y no da ni la potencia ni la celda); el filing de la FCC cita células Spectrolab (sin releer). Química y eficiencia no confirmadas.
- **Blue Ghost M1 (Firefly):** paneles SolAero by Rocket Lab, 2 laterales + 1 de cubierta, 400 W y 1470 h de generación (página de Firefly y nota de Rocket Lab, leídas el 14/11/2026: **publicado**). Ninguna nombra la celda: familia a verificar.
- **VSAT/LSITP:** NASA adjudica 19,4 M USD a Astrobotic, Honeybee Robotics y Lockheed Martin; mástiles de hasta 32 ft; objetivo de desplegar uno cerca del polo sur a finales de década. VSAT-XL de Astrobotic: 50 kW sobre Griffin (SBIR Phase II, jul 2024). El 10 kW de 2021 es del concepto "Relocatable Solar Array": **no** confirmado para los prototipos.
- **ROSA:** demostración en ISS (jun 2017); PPE de Gateway 60–65 kW (las fuentes discrepan); es de órbita lunar, no de superficie. Sin W/kg publicado en lo consultado.
- **Perovskita-Si:** Hanwha Qcells suministra celdas tandem para SSTEF-1 (Aegis Aerospace, NASA, GTRI), previsto en IM-3. 28,6 % certificado es de celda terrestre M10 (AM1.5): no usar como AM0. El "44 %" de la prensa es un límite teórico.
- **CIGS:** sin misión lunar confirmada; Ascent Solar en ISS; NASA Marshall estudió película delgada para el Lunar Pallet Lander polar.
- **No encontrado:** cualquier misión lunar publicada que use IMM o Z4J. Tampoco se encontró MiaSolé en contexto lunar.

## 2. Perfiles de misión y umbrales de decisión

Alimentan el score del emplazamiento. **Hard** = incumplirlo hace el sitio inviable para ese perfil; **soft** = penaliza. Todos viven en `mission_profiles` y son configurables.

| Perfil | Potencia mínima útil (fracción de nominal on-sun) | Noche máx. sin nuclear | Ventana Tierra mín. continua | Pendiente máx. de aterrizaje |
|---|---|---|---|---|
| Lander solar sin RHU | 0,25 (suposición) | **12 h** hard (estimado) | 2 h (suposición) | 10° diseño / 5° objetivo de navegación (publicado) |
| Lander con baterías | 0,25 (suposición) | **36 h** hard (suposición) | 2 h (suposición) | 10° / 5° (publicado) |
| Rover | 0,30 (suposición) | 12 h hard (suposición; VIPER publica ~50 h de autonomía en modo mínimo, NTRS 20220008301, propuesta en revisión-espacial §3) | 2 h (suposición) | aplica el lander; pendiente de traverso 15° (a verificar) |
| Base / ISRU | 0,75 hard (suposición); 10–40 kWe (publicado, NASA FSP) | 24 h hard (suposición) | 8 h (suposición) | 5° (suposición) |
| DTE | — | — | 2 h (suposición) | — |

Justificación de lo único no arbitrario:

- **12 h (lander sin RHU):** 25 Ah × 28 V = 700 Wh × 0,8 utilizable / 50 W de carga de supervivencia ≈ 11 h. La carga de 50 W es una suposición; el orden de magnitud coincide con las "10–20 h de batería" que quedaban a Odysseus tras aterrizar (Reuters).
- **36 h (lander con baterías):** la mejor ubicación de la cresta de Shackleton tiene oscuridad continua máxima de ~1,5 días (Mazarico et al.). A 50 W exige ≈ 1,8 kWh útiles. Es un diseño hipotético; un sitio con oscuridad mayor es inviable sin RHU.
- **Pendiente:** el CTO de Intuitive Machines declaró diseño ≥ 10° y búsqueda de sitio ≤ 5°; Odysseus terminó a ~30° de la horizontal (flyingmag.com; prensa). La pendiente local de ~12° (atribuida a LRO) **no está confirmada en fuente primaria: a verificar**. Es prensa/declaración, no una especificación; no hay requisito CLPS general publicado en lo consultado. No se encontró límite del LM de Apolo.
- **Noche:** Chang'e-4 midió ~−190 °C en su primera noche y la sobrevivió con RHU. Sin RHU, ningún lander solar de los consultados superó la noche con certeza (Chandrayaan-3: sin calentadores, programado para despertar el 22/09/2023 y sin señal de ISRO; theprint.in, space.com, universetoday.com).
- **ISRU:** los 10–40 kWe son los niveles de usuario de NASA Fission Surface Power; no son un requisito para solar y sirven solo de orden de magnitud.
- **Quedan como suposición** todos los umbrales de potencia mínima y de ventana de comunicación: no existe fuente genérica. La UI debe permitir editarlos y mostrar la etiqueta.

## 3. Física operativa del polo sur que afecta a la potencia

### 3.1 La orientación pesa más que la célula

La potencia por m² sobre un panel es `S · cos θ`, con θ el ángulo entre la normal y el Sol. En el polo sur la elevación del Sol sobre el horizonte local es pequeña todo el año: el eje de la Luna está inclinado solo **1,54°** respecto a la eclíptica, de modo que en el polo exacto la elevación solar oscila entre ≈ −1,5° y +1,5° (fuente secundaria, ScienceTrends; coherente con la oblicuidad; el relieve puede elevar el Sol aparente en crestas). Estos son valores de la geometría; LSI los calculará con SPICE y DEM, no con esta aproximación.

Para elevación solar `h` y panel con el Sol en su azimut:

- horizontal: `cos θ = sin h`
- vertical orientado al Sol: `cos θ = cos h`
- inclinado β: `sin h cos β + cos h sin β cos(Δaz)`

Potencia relativa a incidencia normal (ley del coseno pura, sin IAM, sin temperatura):

| h | Horizontal (sin h) | Vertical al Sol (cos h) | Cociente V/H |
|---|---|---|---|
| 1° | 0,0175 (1,7 %) | 0,9998 | 57× |
| 1,5° | 0,0262 (2,6 %) | 0,9997 | 38× |
| 3° | 0,0523 (5,2 %) | 0,9986 | 19× |

Comparación decisiva: pasar de una célula 3J (30,7 %) a IMM-β (33,3 %) multiplica la potencia por 1,085. Pasar de horizontal a vertical orientado multiplica por 19–57. El catálogo de células cambia un 8 %; la orientación cambia un orden de magnitud o más.

Matices obligatorios:

- **Vertical fijo (sin seguimiento):** el azimut solar da una vuelta en un día sinódico (29,5 d). Un panel vertical de una cara recibe, en promedio, `1/π ≈ 0,32` de la potencia pico durante un día lunar; dos caras opuestas, `2/π ≈ 0,64`. Con seguimiento azimutal perfecto: 1,0 (cota ideal; seguimiento real a verificar).
- **IAM:** en horizontal θ > 87°; la ley del coseno es una cota **superior**. Las pérdidas de Fresnel y de AR a incidencia rasante reducen más la potencia (el parámetro está en `iam`; valor a verificar).
- **Disco solar:** diámetro ≈ 0,53°. Con el centro a menos de 0,27° del horizonte solo se ve parte del disco; la potencia se escala por la fracción visible.
- **Horizonte topográfico:** la fracción de sombra (`f_shadow`) de un DEM domina cualquier diferencia de célula. Un mástil sube el panel por encima del relieve cercano (concepto VSAT).
- **Luz reflejada del regolito** (albedo Bond ~0,11, a verificar): aporta algo a un panel vertical; no se modela por defecto.

### 3.2 Eclipses de Tierra

Cuando la Tierra pasa delante del Sol visto desde la Luna ("Earth blocks Sun"), la potencia cae a cero o parcial. Ocurre en los eclipses lunares (Luna llena, en nodos): pocos al año. Duración total entre primer y último contacto: del orden de 3,5–4 h (**estimado**, por analogía con la duración de eclipses lunares vistos desde la Tierra; a verificar). Blue Ghost M1 observó uno con sus baterías, según Firefly. Para LSI: aplicar `f_earth_occ = 1 − área_solapada/área_disco_solar` con discos angulares de SPICE (stretch). Un sitio con noche corta pero con eclipse que cae en esa noche puede violar el umbral de 12 h.

### 3.3 Iluminación del polo (orden de magnitud)

- Cresta cerca del borde de Shackleton: sol ≈ 240 días/año, oscuridad continua máxima ≈ 1,5 d (Mazarico et al.).
- Borde de Shackleton: ≈ 85,5 % de iluminación; cresta Shackleton–de Gerlache ≈ 88–92 % según el autor (Gläser et al. 2018; resumen NASA).
- Estas cifras son para sitios óptimos en DEM de 20–240 m; el sitio medio es mucho peor.

### 3.4 Temperatura del panel

Modelo de equilibrio con α = 0,91, η eléctrica ≈ 0,29, ε frontal 0,85, ε trasera 0,80 (las dos últimas a verificar), sumideros a 3 K y sin intercambio IR con regolito:

- vertical al Sol en pleno flujo: ≈ **308 K (≈ 35 °C)** (estimado); la pérdida frente a 28 °C es ≈ −1,6 %.
- horizontal con h = 1,5°: ≈ **124 K (≈ −150 °C)** como cota inferior (estimado); con IR del regolito será mayor. Fuera del rango de coeficientes (15–140 °C): usar el tope de ganancia.

La temperatura superficial del regolito en sombras permanentes polares es del orden de decenas de K (Paige et al., Diviner; **a verificar**): relevante para la noche del panel, no para su rendimiento diurno.

### 3.5 Polvo lunar

No hay cifra publicada fiable y verificada de pérdida de potencia de paneles por polvo en la Luna en lo consultado. Referencias cuantitativas leídas:

- Surveyor III: tras 945 días, polvo cubría ≈ 25 % del vidrio de la cámara; gran parte se sospecha causado por el aterrizaje del Apolo 12 y su actividad. Un modelo indica acumulación apreciable hasta ~2 km del aterrizaje.
- Reflectores láser: Lunojod 2 hoy rinde ≈ 10 % del de Apolo 15 (polvo, probable); la eficiencia de los reflectores de Apolo cae ×10 en Luna llena (calentamiento por polvo).
- Lunojod 2: panel en tapa abatible; polvo depositado tras un incidente en cráter; sin porcentaje.
- Levitación: Apolo 17 LEAM sugiere levitación y transporte electrostático, pero la levitación "no está confirmada" en la literatura consultada y las alturas serían de pocos metros; partículas de ~5–6 µm de radio se citan para el horizon glow (hipótesis).
- Estimaciones de penalización de potencia en NASA NTRS 19920002733: **leer antes de usar cifras**.

Decisión: `dust_factor` es un parámetro (por defecto 1,0, **suposición**), con deslizador de sensibilidad; no se predice polvo. El polvo de plumas del propio aterrizaje es un riesgo de la misión, no del sitio.

## 4. Comunicaciones DTE

**Lo que LSI modela:** visibilidad geométrica de la Tierra sobre el horizonte local (terreno + curvatura), elevación y ventanas continuas de Tierra, y comparación con el umbral `min_earth_elevation_deg` (0° geométrico; sensibilidad 3–5°, **suposición**).

Datos de contexto:

- Desde el polo sur, la elevación de la Tierra oscila con la libración latitudinal: ≈ ±6,7° (1,54° + 5,15° de inclinación orbital, **estimado**). La Tierra es visible en torno a la mitad del tiempo y baja sobre el horizonte; el relieve cercano decide.
- Estaciones: las antenas DSN tienen un límite mecánico de elevación de 5,923° (34 m) y 5,962° (70 m) (NTRS 20120004035); la máscara de terreno de cada sitio es otro dato. ESTRACK: **a verificar**. No se modela por defecto que la Luna esté sobre el horizonte de la estación.

**Lo que NO se modela:** link budget, frecuencia, ganancia/pointing de antena, ruido, interferencias, margen, ni ocupación de red (DSN/ESTRACK). Visibilidad geométrica ≠ enlace garantizado.

## 5. Misiones de referencia para validar y poblar el selector

Solo se dan coordenadas verificadas en fuente consultada. El resto: leer de NASA/LROC antes de poblar.

| Misión | Agencia/empresa | Fecha | Estado | Coordenadas |
|---|---|---|---|---|
| Chandrayaan-3 (Shiv Shakti) | ISRO | 23/08/2023 (fecha a verificar en el brochure de ISRO) | Aterrizó; lander y rover hibernaron; no se reactivaron (sin señal tras el 22/09/2023; prensa) | 69,373° S, 32,319° E (Wikipedia; ISRO) |
| IM-1 Odysseus | Intuitive Machines (NASA CLPS) | 22/02/2024 | Aterrizó en Malapert A; volcó (inclinación final ~30°; pendiente local ~12° **a verificar**); misión corta | ≈ 80° S; longitud a verificar |
| IM-2 Athena | Intuitive Machines (CLPS) | 06/03/2025 | Aterrizó de costado en Mons Mouton; planificada ~10 d, terminó en <1 día (spacepolicyonline.com); «~24 h de energía» a verificar | objetivo 84,78° S, 29,13° E (LROC); tocó a ~250 m |
| Blue Ghost M1 | Firefly (CLPS) | 02/03/2025 | Misión completada; apagada al ocaso el 16/03/2025 tras ~14 d (NASA, space.com) | Mare Crisium; coordenadas a verificar |
| Chang'e-4 | CNSA | enero 2019 | Sobrevivió noches con RHU | cara oculta (Von Kármán); coordenadas a verificar |
| Chang'e-7 | CNSA | 2026 → 2027 (un único medio: Scientific American, 24/08/2026) | Planificada; polo sur, zona de Shackleton | a verificar |
| Griffin-1 (con FLIP, Astrolab) | Astrobotic (CLPS) | NET dic 2026–ene 2027 | Planificada; región de Nobile | a verificar |
| Blue Moon MK1 Pathfinder | Blue Origin | NET inicios 2027 | Planificada; polo sur no confirmado; ligada a New Glenn | a verificar |
| VIPER | NASA | 2027 (fuente secundaria) | Planificada; condicionada a la entrega con Blue Origin Blue Moon MK1 (a finales de 2027 según space.com, sin compromiso firme) | a verificar |
| SSTEF-1 en IM-3 | Aegis Aerospace/NASA/GTRI; Intuitive Machines | fin 2026 (fuente secundaria) | Planificada | a verificar |
| Artemis III | NASA | probable 2028 | Nueve regiones candidatas (oct-2024, sin orden): Peak near Cabeus B, Haworth, Malapert Massif, Mons Mouton Plateau, Mons Mouton, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2, Slater Plain (upi.com/Science_News/2024/10/28/nasa-artemis-moon-landing-regions/5971730152372/); sitio final no fijado | regiones, no puntos |

Pendientes de verificar y no incluidos por falta de fuente leída: Apolo 11–17 (usar coordenadas oficiales NASA/LROC), SLIM, Hakuto-R M1/M2, Peregrine, Luna-25, Chandrayaan-2.

## 6. Qué decir y qué NO decir en la demo

Decir:

- "Estimación relativa de potencia bajo supuestos declarados: geometría Sol–panel de SPICE y DEM, ley del coseno, temperatura simple, y factores por defecto."
- "La orientación del panel cambia la potencia entre 19× y 57×; la tecnología de célula cambia ~8 %."
- "El score es una herramienta de comparación y de priorización; los umbrales son editables y llevan etiqueta de confianza."
- "La visibilidad de la Tierra es geométrica; el enlace real exige un link budget que no hacemos."

No decir:

- No dar vatios absolutos sin área y sin declarar que son estimaciones; la salida por defecto es **% de la potencia nominal** del propio panel.
- No afirmar que un sitio "es seguro" o "aterrizable": no se modelan plumas, rocas, ni la incertidumbre de navegación; solo pendiente del DEM.
- No presentar ROSA, VSAT, 4J, CIGS o perovskita como "usados en la Luna" salvo donde la columna de misiones lo diga con "publicado". ROSA solo vuela en ISS y órbita lunar; perovskita es una demostración sin resultados.
- No decir que el polvo está modelado: es un parámetro con rango ilustrativo.
- No prometer supervivencia nocturna; el umbral de 12 h es una estimación con una carga de supervivencia supuesta y los 36 h son un diseño hipotético.
- No usar la elevación solar de ±1,5° como cifra de un sitio: depende del DEM y de la fecha.
- No mezclar fechas de misiones planificadas como firmes: Griffin-1, Chang'e-7, Blue Moon MK1, VIPER e IM-3 han cambiado varias veces; hay una fuente secundaria para cada una.

## 7. Fuentes principales

- Spectrolab XTJ Prime datasheet: https://www.spectrolab.com/photovoltaics/XTJ-Prime_Data_Sheet.pdf
- Azur Space 3G30-Advanced 6x12 (DB 00010893-02): https://www.azurspace.com/media/uploads/file_links/file/bdb_00010893-02-00_3g30-advanced_6x12.pdf
- Rocket Lab SolAero Z4J+ e IMM-α: https://www.rocketlabusa.com/assets/Uploads/RL-SolAero-Data-Sheet-Z4J+-v8.pdf · https://www.rocketlabusa.com/assets/Uploads/RL-SolAero-Data-Sheet-IMM-Alpha.pdf
- NASA, VSAT: https://www.nasa.gov/news-release/three-companies-to-help-nasa-advance-solar-array-technology-for-moon · Astrobotic VSAT-XL: https://www.astrobotic.com/astrobotic-developing-xl-solar-array-tech-for-lunar-power-infrastructure/
- Firefly Blue Ghost M1: https://fireflyspace.com/missions/blue-ghost-mission-1/
- Nova-C (secundaria): https://en.wikipedia.org/wiki/Intuitive_Machines_Nova-C · FCC: https://apps.fcc.gov/els/GetAtt.html?id=265886
- Redwire ROSA: https://businesswire.com/news/home/20250702438974/en/Redwire-Successfully-Deploys-the-Most-Powerful-Roll-Out-Solar-Arrays-Ever-Built-Prepares-for-Major-Delivery-in-Fourth-Quarter
- Hanwha Qcells / SSTEF-1: https://www.perovskite-info.com/hanwha-qcells-supply-tandem-perovskite-solar-cells-nasa-backed-lunar-demo
- Mazarico et al. (iluminación polar): https://ntrs.nasa.gov/citations/20120010094
- DSN elevación: https://ntrs.nasa.gov/api/citations/20120004035/downloads/20120004035.pdf
- Polvo y potencia (NASA): https://ntrs.nasa.gov/citations/19920002733
- Chang'e-4 noche lunar: https://space.com/43192-china-farside-moon-mission-survives-lunar-night.html
- IM-2 (LROC): https://www.lroc.asu.edu/images/1401

## 8. Los cuatro paneles antes «estimados»: qué cambió con fuente primaria (14/11/2026)

Sustituye al cuadro anterior (que se apoyaba en resúmenes de búsqueda). Detalle y páginas en `docs/validation/datos-paneles.md`.

| Panel | Antes | Ahora | Grupo |
|---|---|---|---|
| ROSA | η 29,5 (27–33,3) estimado, sin W/kg | η 29,5 de celda 3J (datasheet), 71–124 W/kg derivados del flysheet Redwire | respaldado · derivado |
| Si heredado | η 16 (14–18) por un resumen PVSC | η 17,4 % AM0 136,7 mW/cm² 25 °C y 0,62 a 1E15 (datasheet Sharp); Azur 16,9 % y 32 mg/cm² (NASA/JPL); γ_T no disponible | experimental |
| CIGS | η 12 (juicio LSI), −0,35 | η 15,7 % AM0 (nota de prensa) / 8,84 % (NASA GRC 2002); −0,38 %/°C módulo terrestre (datasheet MiaSolé) | experimental |
| Perovskita-Si | η 21,1 % (resumen), −0,26 | η 19,2 % AM0 (Joule 2020, leído); 61 mg/cm², 420 W/kg sin encapsular; 1 % de η con protones; γ_T no disponible | experimental |

**Límites declarados.** (1) Perovskita-Si: el modelo usa `f_rad = 1` y **sobrestima** este panel (Joule 2020: ~1 % de η tras ~1E11 p⁺/cm²); sigue siendo solo demostración. (2) α/ε no tienen fuente primaria en ninguno de los cuatro: mueven la temperatura de panel y, con ella, γ_T; por eso existe la banda en los experimentales. (3) `areal_power_w_m2_am0` es de celda/CIC; el array real rinde ~330–340 W/m². (4) El 27,49 % AM0 certificado de un tándem perovskita/Si (Tianjin Univ. et al.) solo se conoce por una noticia (perovskite-info): no se usa como valor por defecto.
