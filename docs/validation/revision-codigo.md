# Revisión de código de LSI (solo lectura)

Fecha: 2026-11-14. Alcance: `src/lsi/**`, `ui/**`, `app.py`, `scripts/**`, contrastado con `CLAUDE.md` y `docs/plan/arquitectura.md` (§3, §4, §9).
Método: lectura completa más ejecución de scripts de prueba contra los datos reales (DEM Site04/11/23, LOLA 80 m, kernels). Línea base: `pytest` → **536 passed, 38 skipped** (172 s). No se ha editado ningún otro fichero del proyecto; los scripts de prueba viven fuera del repo.

Leyenda: **confirmado** = reproducido con un script; **por lectura** = deducido del código, sin ejecutar; **sospecha** = no comprobado.

## Resumen

- **Críticos: ninguno.** No he encontrado un error de signo, unidad o marco de coordenadas en el núcleo (ver «Comprobado y correcto»).
- **Alto (1, latente):** la purga LRU de la caché comparte cuota con los mapas de idoneidad precalculados y los borra (A1).
- **Medios (6):** paso de serie de la UI que siempre falla, puerta G0 ausente en el mapa de ventanas, aviso de frío incoherente con el rango de validez del panel, `precompute_horizons.py` inservible, violaciones de §3, config muerta mostrada como verdad en «Acerca de».
- **Bajos:** constante TDB−UTC triplicada, redondeo de `et2utc`, validación del núcleo, código muerto, hardcodes, ficheros sueltos (82 MB), scripts de descarga sin hash.

---

## Hallazgos

### A1. ALTO (latente) — La purga LRU de `data/processed` borra los mapas de idoneidad precalculados
- **Dónde:** `src/lsi/data/cache.py:87-105` (`purge`, `rglob("*.npz")`), `src/lsi/pipeline.py:76-79` (se llama con `cfg["cache"]["dir"]` = `data/processed`, tope `max_bytes` = 524 288 000), `src/lsi/analysis/suitability_map.py:~736-760` (`_save` escribe en `data/processed/suitability/`).
- **Qué falla:** el tope de 500 MB y la purga por antigüedad abarcan TODO `data/processed`, no solo `horizons/`. Los `.npz` de `suitability/` (28 ficheros, 241 MB, minutos de cómputo cada uno) compiten con los horizontes baratos (187 ficheros, 6 MB). Hoy suman ~247 MB, así que no salta. Cada cambio de parámetro genera una clave nueva y deja los mapas viejos (51 ficheros en `suitability/`: 28 npz + 23 json), de modo que el tope se alcanza solo. Al pasarlo, `build_context` (cada arranque de la app) borra primero los mapas más antiguos, que son justo los precalculados. La página «Mejores puntos» los trata como «el `.npz` ya no está» (`best_spots._load` devuelve `None`) sin avisar de la causa.
- **Escenario (confirmado):** directorio temporal con 3 `.npz` de `suitability/` antiguos y 3 de `horizons/` recientes (1 MB cada uno), `purge(td, 4 MB)`:
  ```
  antes: horizons/kho0..2, suitability/ksu0..2
  purge a 4 MB, liberado 3000768 -> solo quedan horizons/kho0..2   # los 3 de suitability, borrados
  ```
- **Arreglo mínimo:** purgar solo `cache_dir / "horizons"` en `build_context` (`cache_mod.purge(cdir / cfg["cache"]["horizons_subdir"], ...)`; la clave `horizons_subdir` ya está en la config y no se usa). Opcional: purgar `suitability/` con otro tope y borrar JSON/NPZ huérfanos.

### M1. MEDIO — El selector «Paso de la serie» ofrece 15, 30 y 60 min y las tres opciones siempre fallan
- **Dónde:** `ui/state.py:35` (`STEP_CHOICES_MIN = (5, 10, 15, 30, 60)`), `ui/sidebar.py:204`, contra `src/lsi/data/catalog.py:131-133` (`step_s > max_step_s=840` → `InvalidParameterError`).
- **Escenario (confirmado):** modo Experto → Avanzado → paso 15 min:
  ```
  5 min OK / 10 min OK
  15 min -> InvalidParameterError timeline.step_s=900.0 supera max_step_s=840.0
  30 min -> ... 1800.0 supera max_step_s=840.0 ;  60 min -> ... 3600.0 supera ...
  ```
  La UI lo muestra como error (no hay traceback), pero 3 de las 5 opciones son inalcanzables.
- **Arreglo mínimo:** `STEP_CHOICES_MIN = (5, 10, 14)` o derivarlo de `cfg["timeline"]["max_step_s"]`. Si 15/30/60 se quieren de verdad, hay que subir `max_step_s` asumiendo la pérdida de eventos cortos que documenta `timeline.py`.

### M2. MEDIO — `window_scores` no evalúa la puerta G0 (Sol visible a la llegada); el mapa y el pipeline discrepan
- **Dónde:** `src/lsi/analysis/suitability_map.py:442-480` (`window_scores` se presenta como réplica de `compute_score` + `evaluate_gates`, pero solo implementa G1, G2, G3, G4), frente a `site_score.py:203-209` y `pipeline.py:596-599` (G0, dura para perfiles solares, vía `sun_at_start`).
- **Qué falla:** una fecha de inicio en plena noche cuenta como «apta» en el mapa precalculado (`apt_days`, ranking, `best_start`) aunque el pipeline la declare NO APTA («llegada de noche»).
- **Evidencia (por lectura + medición coherente, no prueba concluyente):** `run_analysis` sobre los 3 mejores candidatos de `windows_Site04_lander_solar_no_rhu_856ccdc8b5.json` (14 d, 366 inicios) da menos fechas factibles que el mapa en los tres:
  ```
  rank1: mapa apt_days=69/365 | pipeline 65/366      rank2: 30 vs 27      rank3: 40 vs 38
  ```
  La mejor fecha coincide en los tres (2026-12-06, 2027-11-29, 2026-12-12). La diferencia (3–4 días de 365) cuadra con G0, pero el mapa usa horizonte grueso (1°, 80 m), así que no la atribuyo del todo a G0.
- **Arreglo mínimo:** pasar `sun_at_start = sun_m[i0]` por inicio a `window_scores` y añadir `rank = max(rank, 2)` donde falle G0 (si `profile.uses_solar_gate and sp_.g0_needs_sun`). Añadir un test que compare `apt_days` con `run_analysis` en un punto.

### M3. MEDIO — Aviso `COLD_EXTRAPOLATION` incoherente con el rango de validez real del coeficiente térmico
- **Dónde:** `src/lsi/energy/panels.py:147-156` (`clamped = t < params.t_min_valid_k`, 173,15 K global), `panels.py:57` (`temp_valid_range_c` se parsea y NO se usa en ningún sitio), `pipeline.py:354` (`series.t_clamped.any()`), texto en `contracts.py` (`COLD_EXTRAPOLATION`: «fuera del rango de validez del coeficiente térmico… resultado optimista»).
- **Qué falla (por lectura + datos de `config/panels.json`):**
  1. Los coeficientes de GaAs valen en 15–125 °C (`tj-gaas-*`, `rosa-flexible-rollout`), 28–80 °C (`mj-4j`), −50–80 °C (CIGS). El aviso solo salta por debajo de −100 °C. Entre 15 °C y −100 °C el coeficiente está extrapolado sin aviso. Por ejemplo, con G ≈ 300 W/m² el balance da T ≈ 209 K (−64 °C), η queda limitado solo por `cold_gain_cap` (1,15) y no hay aviso. La propia nota de `panels.json` dice que por debajo de ~−50 °C el lineal sobreestima.
  2. El texto dice «optimista», pero el código sube T hasta 173 K y aplica el tope, así que el resultado es menor que la extrapolación lineal. Si es optimista o conservador respecto a la célula real es una incógnita, no un hecho.
  3. (confirmado) Se emite aunque no haya potencia: Site04, 2026-12-01 → 31, `t_clamped` = 4322/4322 y `p_rel.max() = 0.0`, aviso presente.
- **Arreglo mínimo:** usar `panel.temp_valid_range_c` (lo parseado) para el aviso, restringirlo a instantes con `p_rel > 0` y reescribir el texto («extrapolado fuera de [15, 125] °C; eficiencia acotada al tope +15 %; sin datos de validación»).

### M4. MEDIO — `scripts/precompute_horizons.py` genera entradas de caché que el pipeline nunca reutiliza (y semánticamente peores)
- **Dónde:** `scripts/precompute_horizons.py:44` (`compute_horizon(windows[site], o, p, cache_dir=cache_dir)` sin `far`) frente a `pipeline.py:482-483` (siempre con `far` si existe `LDEM_80S_80MPP_ADJ.TIF`).
- **Qué falla:** la clave incluye el campo lejano (`horizon.py`, `cache.digest(key, ext, sig, ("far", ...))`), así que las claves difieren. Además, sin `far` el resultado es otro: con el DEM de 5 m solo, todos los azimutes quedan limitados.
- **Escenario (confirmado):** Site23, observador por defecto, h = 2 m:
  ```
  clave sin far : a5462dc4f4ca7055      clave con far : 11f0a92eef7509b0      iguales: False
  limited sin far: 1440      con far: 0
  ```
- **Arreglo mínimo:** cargar `far` en el script con `loader.load_far_field(raw, x, y, r_max)` y pasarlo (como hace `pipeline._far`), o retirar el script. Mientras exista, esas entradas ocupan cuota de la purga (A1).

### M5. MEDIO — Violaciones de las reglas de dependencia de §3
Comprobadas con un AST de imports (resultado completo abajo) más lectura.

| # | Violación | Riesgo real |
|---|---|---|
| a | `simulation/timeline.py:13` y `simulation/uncertainty.py:21` importan `lsi.analysis.metrics` (§3: «`simulation` no importa `energy`/`analysis`»). La propia tabla de §3 dice que `analysis.metrics` depende de `timeline`, lo contrario de lo que hace el código | Bajo ahora (`metrics` solo usa `contracts`), pero el grafo real es `simulation → analysis` y el documento y el test de imports no lo reflejan. Lo sano: mover el álgebra de intervalos a un módulo neutro (`simulation/intervals.py`) o corregir §3 |
| b | `data/catalog.py:12` importa `analysis.site_score` (§3: `data.catalog` depende de `contracts`) | Inversión de capas: `data` depende de `analysis`, y `analysis.suitability_map` importa `catalog`. Hoy no hay ciclo de import, pero cualquier import de `catalog` desde `site_score` lo crearía |
| c | `ui/cache.py:121` llama a `pipeline._countdowns` (privada) | Cambiar su firma rompe la UI sin que lo detecte ningún test (0 tests referencian `_countdowns`) |
| d | `ui/pages/site_score.py:231` llama a `pipeline._mission` (privada) | Ídem; además esa página recalcula el score en la UI (`score_with_range`, `params_from_config`, `normalize_weights`), contra «UI sin cálculo» |
| e | `ui/pages/best_spots.py:71` llama a `suitability_map._load` (privada) y `:23` importa `analysis.suitability_map` | La UI conoce el formato de caché en disco; ligado a A1 |
| f | `ui/pages/explorer.py:22,45` importa `data.loader` y lee el DEM con `loader.read_window` (hasta 3 capas completas de ≤ 4200² por interacción nueva), saltándose `pipeline._layer` | Duplicación de lecturas pesadas. Mitigado por `st.cache_data(max_entries=12)`; no comparte caché con el pipeline |
| g | `ui/*` importa `analysis.export`, `analysis.metrics`, `energy.panels`, `astronomy.coordinates` (comparison, timeline, power_panels, explorer, components) | Lista completa en el anexo. Hay que decidir si `pipeline` reexporta estas funciones o si §3 las permite |

**Arreglo mínimo:** exponer en `pipeline` versiones públicas (`countdowns_at`, `mission_for`) y una función `load_suitability`; ampliar §3 con lo que se acepta (`analysis.export`, `analysis.metrics`) y añadir el test de imports que §3 anuncia («comprobables con un test de imports»; hoy solo existe el de `visualization`, en `tests/test_visualization.py:113`; no hay uno para `simulation`, `data`, `terrain` ni `ui`).

### M6. MEDIO — La página «Acerca de» muestra valores de `config/` que el código no usa
- **Dónde:** `ui/pages/about.py:63,93,109` lee `cfg["frames"]`, `cfg["power"]["solar_constant_w_m2"]`, `cfg["time"]["utc_min/max"]`. El código físico usa otras fuentes: `contracts.py:35-51` (`MOON_RADIUS_M`, `AU_KM`, `UTC_MIN`…) y `panels.json: reference.solar_constant_W_m2` (`panels.py:74`).
- **Config muerta (comprobado con grep):** `frames.*`, `time.utc_min/max`, `power.solar_constant_w_m2`, `power.iam.n_coverglass_default`, `power.eta_rel.eta_max_fallback`, `gazetteer.fuzzy_cutoff`, `horizon.near_field_conservative_r_min_m`, `horizon.curvature`, `cache.horizons_subdir`.
- **Qué falla:** hoy los valores coinciden (1361 en ambos), pero si alguien edita el de `simulation.json` la página dice una cosa y los cálculos hacen otra. Es la «constante duplicada» que `CLAUDE.md` pide evitar.
- **Arreglo mínimo:** que «Acerca de» lea de `contracts`/`ctx.panels.solar_constant_w_m2`, o que el núcleo consuma esas claves; borrar las que no se vayan a usar.

### B1. BAJO — Constante TDB−UTC = 69,184 s: correcta en 2026, pero hay 3 fuentes y ninguna es SPICE
Respuesta a la pregunta: **sí es correcta en 2026** (TAI−UTC = 37 s desde 2017-01-01; SPICE da ET−UTC = 69,183–69,184 s; la diferencia de 1 ms es TDB−TT). Mientras no se anuncie otro segundo intercalar, vale hasta 2050. No hay una única fuente de verdad: tres implementaciones distintas.

| Sitio | Qué hace | Error medido frente a SPICE |
|---|---|---|
| `analysis/export.py:79-96` | Tabla de segundos intercalares + 32,184 | Exacto desde 1972. **Antes de 1972 usa 10 s y el LSK usa 9 s: 1 s de error** (el comentario «se extrapola 10 s, como el LSK» es falso) |
| `visualization/theme.py:45` | Constante 69,184 | **−28 s en 1900, −27 s en 1972, −18 s en 1980, −5 s en 2000, −1 s en 2016**; exacto desde 2017 |
| `energy/panels.py:25` | `DAY_ORIGIN_ET` con 69,184 | +3 s en 2010, +5 s en 2000. Solo es el valor por defecto: el pipeline pasa `day_origin_et` correcto (`_day0`) |

- **Escenario (confirmado):**
  ```
  1900-01-02T00:00:00 export=1900-01-01T23:59:59Z spice=1900-01-02T00:00:00 theme-err=-28.0s
  2000-01-01T12:00:00 export=2000-01-01T12:00:00Z spice=2000-01-01T12:00:00 theme-err=-5.0s
  2026-11-14T12:00:00 export=OK spice=OK theme-err=-0.0s
  ```
  Efecto práctico: los ejes de las gráficas y el cursor de `timeline.py:337` (ET→UTC aproximado→ET) se desplazan hasta 28 s en fechas anteriores a 2017.
- **Arreglo mínimo:** una sola función `et_minus_utc_s(et)` en `spice_engine`, alimentada por `sp.gdpool("DELTET/DELTA_AT", ...)` del LSK ya cargado (así sigue al kernel), usada por export, theme y panels. Corregir la rama pre-1972 (9 s) o el comentario.

### B2. BAJO — `et_to_utc(...)[:10]` redondea al segundo: cerca de medianoche da el día siguiente
- **Dónde:** `pipeline.py:254` (`_midnights`), `pipeline.py:318` (`_day0`), `pipeline.py:285`.
- **Escenario (confirmado):** ET de `2026-11-14T23:59:59.700` → `et_to_utc` devuelve `2026-11-15T00:00:00`. Con un inicio con fracción ≥ 0,5 s en el último segundo del día, `_midnights` se salta la primera medianoche y la primera fila diaria sale con la etiqueta de día equivocada.
- **Impacto:** nulo desde la UI (siempre segundos enteros). **Arreglo:** `prec=3` y truncar, o usar `fmt="ISOC"` sobre `et - 0.5`.

### B3. BAJO — El núcleo valida poco; la UI lo tapa
Probado con `run_analysis` (confirmado):
- `lat=NaN` / `lon=NaN` → `ValueError: cannot convert float NaN to integer` (críptico; la UI lo captura por ser `ValueError`).
- `lat=+95` con `site_id` → se evalúa con DEM: `snap_candidate` con sitio curado emparejado no tiene límite de distancia (`pipeline.py:150-151`). Sin `site_id`, `lat=-90` exacto y `lon=-30` se normalizan bien.
- `BatteryParams(capacity_wh=None)` o `p_nominal_w=None` → `TypeError`; `capacity_wh=0` → `ZeroDivisionError` (`panels.py:244`). `run_power` solo captura `PanelNotCalculableError`/`LSIError` (`pipeline.py:376`), y la UI solo `(LSIError, ValueError)`. Los widgets de la UI acotan estos valores (mín. 1 Wh), así que hoy no se dispara.
- `degradation=1.5` da `p_rel = -0.0` sin error.
- `start_utc="JD 2461000"` se acepta (formatos laxos de `str2et`). `"… TDB"` falla con `DateOutOfRangeError`, mensaje engañoso («no interpretable», no «fuera de rango»).
- **Arreglo mínimo:** `__post_init__` en `AnalysisRequest`/`BatteryParams` que lance `InvalidParameterError` con finitud y rangos (`-90 ≤ lat ≤ 90`, `capacity_wh > 0`, `0 ≤ degradation < 1`).

### B4. BAJO — `ui/cache.get_observer` ignora `snap_to_dem`
`ui/cache.py:109-112` no pasa `req.snap_to_dem`, que `run_analysis` sí usa (`pipeline.py:474`). Si algún día la UI fija `snap_to_dem=False`, la cabecera mostraría un snap que el análisis no hace. Hoy la UI no lo establece nunca (grep), así que es latente.

### B5. BAJO — Ficheros sueltos en la raíz sin ignorar
`S_horn.npy` (82 MB, 14/11 12:30), `fine_Site04.json`, `.coverage` están sin seguimiento y `.gitignore` no los cubre; un `git add .` (prohibido por `CLAUDE.md`, pero posible) subiría 82 MB. Nada del código los lee. **Arreglo:** moverlos fuera o añadir `*.npy`, `.coverage`, `fine_*.json` a `.gitignore`.

### B6. BAJO — Scripts de descarga: sin verificación de integridad
- `scripts/fetch_data.py:20-30`: omite lo ya descargado si `size > 4096` y no verifica hash ni tamaño esperado; los kernels y los DEM (~600 MB) se aceptan tal cual. HTTPS con verificación TLS por defecto.
- `scripts/fetch_gazetteer.py:51-61`: cada ejecución crea un `dl_*` nuevo en `data/raw/gazetteer/` y nunca lo limpia (ya hay uno); sin tope de tamaño de descarga ni de descompresión (`extractall`). La defensa contra zip-slip es correcta (ver «Comprobado»).
- **Arreglo mínimo:** tabla de `sha256` esperados (los kernels de NAIF publican checksums) y tope de bytes; borrar el `dl_*` tras convertir.

### B7. BAJO — Código muerto y duplicado
- Sin uso en `src/ui/scripts` (solo tests): todo `terrain/roughness.py`, `slope.footprint_area_below_pct`, `timeline.union_windows`, `metrics.windows_from_mask`, `metrics.daily_table` (sustituida por `pipeline.daily_table_utc`), `site_score.earth_reference_fraction`, `coordinates.stereo_scale`, `gazetteer.get_entry`.
- Avisos declarados y nunca emitidos: `NEAR_FIELD_UNRELIABLE`, `DATE_TRUNCATED` (las fechas fuera de rango lanzan error, no se truncan).
- Duplicación: la base ENU se reescribe a mano en `spice_engine.body_track:100-106` en vez de usar `coordinates.enu_basis`; `SPICE_FRAME`/`ABCORR` están también en la config.
- Resultados JSON/NPZ de `suitability/` de claves antiguas (ver A1).

### B8. BAJO — Umbrales y constantes que deberían venir de la config
`pipeline.py:57-59` (`SNAP_MAX_KM`, `SNAP_INSET_M`, `SHORT_PERIOD_D=29.53`), `pipeline.py:156,215` (`* 5.0`: supone píxel de 5 m, la capa lo conoce), `pipeline.py:356` (80° del aviso IAM), `gazetteer.py:24` (`FUZZY_CUTOFF`, el comentario admite que duplica la config), `panels.py:22-23,38` (`N_COVERGLASS_DEFAULT`, `ETA_MAX_FALLBACK`, `or 1.15`, `or 1.0`), `visibility.py:23` (`_COS_E_MIN`), `export.py:DECIMALS`.

### B9. BAJO — Texto de `POWER_IS_ESTIMATE` y parámetro `dust_loss`
El aviso dice «sin polvo, sombra propia ni albedo», pero existe `dust_loss` (sensibilidad). Con `dust_loss > 0` el texto contradice lo que se calcula.

### B10. BAJO — Rendimiento de metadatos
`loader.read_window` llama a `read_metadata` en cada lectura (abre el GeoTIFF otra vez, lee el JSON del sidecar de hashes). `snap_candidate` puede hacer ~41 llamadas a `_ground` → `_small` → `read_window` (`pipeline.py:172-175`). Cacheable por `(ruta, mtime)`.

---

## Sospechas (no comprobadas)

- **S1.** `CACHE_ALGORITHM_VERSION = 1` (`contracts.py:47`) no se ha subido pese a que la lógica del horizonte ha cambiado (campo lejano, `limited` por azimut). Una caché `horizons/` creada con una versión anterior del algoritmo se serviría sin avisar. No he podido comprobar qué había en los 187 ficheros actuales. Conviene subir la versión y limpiar `horizons/`.
- **S2.** `cache.load_npz` (`cache.py:57-62`): ante un `.npz` corrupto hace `p.unlink()` dentro del `except`. En Windows, si otro hilo de Streamlit lo tiene abierto, `unlink` lanza `PermissionError` sin capturar. No reproducido.
- **S3.** `loader.dem_sha256` escribe el sidecar con `tmp = sidecar.with_suffix(f".{os.getpid()}.tmp")`: dos hilos del mismo proceso comparten nombre temporal. Los `OSError` se capturan, así que no hay corrupción; se pierde la optimización. No reproducido.
- **S4.** `LSI_PAGES_DIR` (`app.py:49`) hace que Streamlit ejecute los `.py` de esa carpeta. Es entrada del operador, no del usuario de la UI; riesgo solo si el entorno no es de confianza. `LSI_SUITABILITY_DIR` solo lee JSON/NPZ (con `allow_pickle=False`).
- **S5.** `horizon_at` interpola linealmente en la rejilla de 0,25°. A 30 km son ~131 m: una cresta más estrecha se subestima. No lo he medido; el disco solar (0,53°) lo amortigua. Merece una línea en las limitaciones.

---

## Comprobado y correcto

- **Física y marcos:** horizonte con curvatura exacta (`_tan_el`: componente vertical y horizontal correctas); dirección de rayo `(sin(λ+A), cos(λ+A))` coherente con el azimut N→E en el polo sur; `atan2(x, y)`, no `(y, x)`; cenit/nadir con `az=0` sin ruido; fracción de disco por rebanadas (área = πρ²) y analítica; `ΔA = x/cos e` acotado por `_COS_E_MIN`; nodata → `-inf`, nunca 0, en `sample_bilinear`, `compute_horizon`, `slope`, `roughness`; bordes del DEM (centros de píxel [0, W−1]) y `limited`/`r_cov` coherentes con y sin campo lejano.
- **Escala de la proyección:** el plano estereográfico trata `s` como arco; el error es k(φ) ≈ 1 + ρ²/4R² ≈ 3·10⁻⁵ a 30 km del polo, despreciable.
- **Fechas:** `et_to_utc_str` coincide con SPICE de 1972 a 2050; límites 1900-01-02 (OK) / 1899-12-31 (`DateOutOfRangeError`); 2050-12-30 (OK) / 2050-12-31 (error); `now_utc > UTC_MAX` → error; días UTC reales con segundos intercalares (`_midnights`).
- **Ventanas:** `K`, `n`, `b = a + n + 1` en `_score_window` sin off-by-one (la ventana cubre n·dt con n+1 puntos y `short` usa `1 ≤ n ≤ K−1`); `mission_window_metrics` y `_max_run` (rachas recortadas, tabla dispersa); `_time_above`; `max_sustainable`.
- **Caché:** la clave del horizonte incluye sha256 del DEM, extensión de la ventana, sha/ventana/paso del campo lejano, σ (sha, signo, k), parámetros completos (altura, pasos, `z_up`) y `CACHE_ALGORITHM_VERSION`. `_path` impide path traversal (`kind.isidentifier()`, `key.isalnum()`); escritura atómica (`mkstemp` + `os.replace`); `np.load(allow_pickle=False)`; rechazo de dtype `object`. `_earth_ref_f` incluye punto, periodo, longitud, umbrales y `kernel_hash`.
- **Estado global y multihilo:** `SPICE_LOCK` rodea `furnsh/str2et/et2utc/spkpos` (también en `suitability_map.ephemeris`); `_range_et` se asigna antes que `_info`; no hay adquisición anidada del lock; `_F_EARTH_REF` acotado (32) y bajo `_LOCK`; `lru_cache` (seguro entre hilos); los workers del `ProcessPoolExecutor` no llaman a SPICE. No he encontrado mutaciones de resultados cacheados en `ui/` (revisión por grep y lectura).
- **Seguridad:** no hay `file_uploader` ni campo de ruta en la UI; sin `unsafe_allow_html` (el único `st.html` es CSS estático); el gazetteer (9 087 rasgos) no tiene nombres que empiecen por `= + - @` ni contengan `< > [ ] ( ) & "`, y nada del gazetteer llega a ningún CSV (los CSV solo llevan números, ids curados y cabeceras de la config); sin secretos; zip-slip: `fetch_gazetteer` rechaza cualquier entrada cuyo nombre no sea su propio `basename` y `zipfile` además sanea `..`.
- **Rendimiento y memoria:** el campo lejano se lee recortado (±30 km ≈ 750² px, ~2 MB), nunca el 7600²; 366 d a 5 min con incertidumbre y panel: 6,0 s y ~19 MB de arrays por resultado (24 entradas ⇒ ≤ ~460 MB); a 10 min, 3,1 s y ~10 MB; `_layer` `lru_cache(4)` ≤ ~280 MB con capas de 70 MB; el buscador responde en < 0,05 s (9 087 nombres, difusa incluida).
- **Energía:** IAM de Fresnel normalizado y 0 para θ ≥ 90°; `incidence_cos` por montaje; integrador de batería (carga/descarga con rendimientos, energía no servida); `e_inc` en Wh/m²; días de potencia con origen UTC real.
- **Config:** `load_simulation_config` valida rangos y falla al cargar; `AnalysisRequest` con `step_s ≤ 0`, altura fuera de [0, 100] y `mission_days ≤ 0/NaN` lanzan `InvalidParameterError` claro.

---

## Anexo A: pruebas ejecutadas (scripts fuera del repo)

Scripts: `C:\Users\Arquitecto\AppData\Local\Temp\claude\06df16980bb5b783\dd9d8ef8-907d-4b50-af02-0fb5d90307fa\scratchpad\` (`probe1.py`…`probe8.py`, `imports.py`).

- `probe1`: ET−UTC por año, `et2utc` en medianoche, error de `DAY_ORIGIN_ET` (resultados en B1 y B2).
- `probe2`: entradas límite de `run_analysis` (B3). Casos «OK»: lat +95 con site_id (snap), lat −90, lon −30 (esfera lisa), 1900-01-02, 2050-12-30.
- `probe3`: aviso de frío con `p_rel = 0` (M3); batería con `None`/0 (B3).
- `probe4`: coste de 366 d (rendimiento).
- `probe5`: pasos de 5/10/15/30/60 min (M1).
- `probe6`: gazetteer, nombres con caracteres peligrosos, tiempos de búsqueda.
- `probe7`: purga con caché compartida (A1) y mapa de ventanas frente a pipeline (M2).
- `probe8`: claves de caché con y sin campo lejano (M4).

## Anexo B: grafo de imports frente a §3 (script `imports.py`, AST)

```
SRC src/lsi/simulation/timeline.py    13 lsi.analysis.metrics
SRC src/lsi/simulation/uncertainty.py 21 lsi.analysis.metrics.compute_metrics
UI  ui/components.py            20 lsi.analysis.export
UI  ui/state.py                233 lsi.analysis.site_score.profiles_from_config
UI  ui/pages/best_spots.py   23,25 lsi.analysis.suitability_map ; lsi.data.cache
UI  ui/pages/comparison.py   23,28 lsi.analysis.metrics/export ; lsi.analysis.site_score.profiles_from_config
UI  ui/pages/explorer.py     18,22 lsi.astronomy.coordinates.stereo_* ; lsi.data.loader
UI  ui/pages/horizon_visibility.py 14 lsi.analysis.export
UI  ui/pages/power_panels.py   23 lsi.energy.panels
UI  ui/pages/site_score.py     14 lsi.analysis.site_score.{params_from_config, profiles_from_config, score_with_range, normalize_weights}
UI  ui/pages/timeline.py       17 lsi.analysis.metrics
(+ privadas, por grep: ui/cache.py:121 pipeline._countdowns; ui/pages/site_score.py:231 pipeline._mission; ui/pages/best_spots.py:71 suitability_map._load)
(+ fuera del script: src/lsi/data/catalog.py:12 → lsi.analysis.site_score, regla «data.catalog solo depende de contracts»)
```
`visualization` solo importa `contracts` y `visualization.theme` (cumple §3). `terrain` no importa `simulation` ni `spice_engine` (cumple), y `astronomy.coordinates` no importa SPICE (cumple).

---

## Estado de correcciones (ronda del núcleo, 2026-11-14)

| Hallazgo | Estado | Dónde / cómo se comprueba |
|---|---|---|
| A1 purga borra `suitability/` | **Corregido** | `cache.purge(cache_dir, max_bytes, kinds=("horizons",))` solo recorre `horizons/` (`REGENERABLE_KINDS`); `suitability/` está en `PROTECTED_KINDS` y se ignora aunque se pida; `build_context` pasa `cfg.cache.horizons_subdir`. `tests/test_cache.py::test_purge_never_touches_suitability_gazetteer_or_dem_hash` (tmp con ambos, tope 0). |
| M1 pasos 15/30/60 min | **Corregido** | `pipeline.effective_step_s`: por encima de `max_step_s` el muestreo interno se divide en n partes iguales (900→450 s, 1800→600 s, 3600→720 s): la serie pedida es un submuestreo exacto y no se pierden transiciones. Se anota en `score.assumptions`. Pasos ≤ 0 siguen siendo error claro. `tests/test_pipeline.py::test_ui_steps_15_30_60_min_*`. La UI no necesita cambiar `STEP_CHOICES_MIN`. |
| M2 G0 ausente en el mapa | **Corregido** | `window_scores(..., sun_start)`, `WindowMetrics.sun_start`, `MODULE_VERSION = 3`. Mapas regenerados (7/14/30 d; lander sin RHU y rover; 3 sitios). TOP-3 por sitio: `apt_days` mapa = pipeline en 7 de 9 puntos y diferencia de 1 día en los otros 2 (resolución 30 min/horizonte grueso frente a 600 s/fino); antes 69 vs 65, 30 vs 27, 40 vs 38. `tests/test_pipeline.py::test_window_map_apt_days_equal_pipeline_at_top_points`, `tests/test_mission_windows.py::test_g0_*`. |
| M3 aviso de frío | **Corregido** | `eta_rel`/`relative_power`: `t_clamped` = T fuera de `temp_valid_range_c` del panel (sin rango: `t_min_valid_k`) y solo con potencia > 0. El aviso `COLD_EXTRAPOLATION` cita el rango y la T real; el texto ya no dice «optimista». `tests/test_panels.py::test_cold_extrapolation_*`. |
| M4 `precompute_horizons` | **Corregido** | Usa `pipeline.far_field_for` (misma clave que `run_analysis`). `tests/test_precompute_horizons.py::test_precompute_acierta_la_cache_de_run_analysis` (DEM real Site23: el horizonte nominal de `run_analysis` está ya en la caché del precompute). |
| B1 TDB−UTC triplicado | **Corregido** | Una sola fuente: `contracts.et_minus_utc_s / et_to_utc_datetime / utc_datetime_to_et / utc_midnight_et` (tabla de segundos intercalares; antes de 1972 = 9 s como el LSK). La usan `export.et_to_utc_str`, `theme.et_to_datetimes` y `panels.summarize_power` (origen de día por defecto). `tests/test_contracts_time.py` (2010, 2017, 2026, saltos y contraste con SPICE). |
| Hallazgo informe-pruebas: Shackleton sin Sol | **Corregido** | Snap al mejor punto (ver abajo). |
| M5, M6, B2–B10, S1–S5 | Sin tocar en esta ronda | — |

### Snap al mejor punto
`pipeline.snap_candidate(..., prefer="nearest"|"best", profile_id, mission_days)` y `resolve_observer(..., prefer=None, profile_id, mission_days)`.
`prefer=None` (auto) = «best» para rasgos del buscador (`gazetteer_id`) y sitios curados con DEM, «nearest» para coordenadas exactas del
usuario. «best» = TOP-1 del mapa de idoneidad precalculado (`suitability_map.best_points`, versión más reciente con el `MODULE_VERSION`
actual y la duración precalculada más cercana a la misión); sin mapa cae al más cercano y lo dice en `snap_reason`. `ObserverPoint` gana
`snap_kind`, `snap_reason`, `best_start_utc`, `snap_ranking` (`SnapRankEntry`) y `snap_alternative` (lat, lon, km del más cercano);
`AnalysisRequest.snap_prefer` permite forzar «nearest». Resultado real (lander sin RHU, 14 d, run_analysis en su mejor fecha):

| Rasgo | Punto (lat, lon E) | Mejor inicio | f_sol | D_max | Veredicto | Distancia al centro / más cercano |
|---|---|---|---|---|---|---|
| Shackleton (Site04) | −89,5626°, 215,4724° | 2026-12-06 | 1,00 | 0 h | APTO (97,4) | 16,0 km / 0,80 km |
| de Gerlache (Site11) | −88,4461°, 297,7601° | 2026-12-15 | 1,00 | 0 h | APTO (99,3) | 21,0 km / 5,87 km |
| Mons Malapert (Site23, dentro del DEM: sin snap; TOP-1 del mapa) | −85,9841°, 2,6123° | 2026-12-16 | 1,00 | 0 h | APTO (98,4) | — |

Limitación: el mapa es grueso (horizonte 1°, rejilla de 30 min) y el TOP-1 puede ser un punto a decenas de km del centro del rasgo; por eso
el punto cubierto más cercano se ofrece como alternativa y la etiqueta/aviso del snap dicen cuál se evalúa.

Pytest completo (`--ignore=tests/test_independent_visibility.py`): 576 passed, 38 skipped, 1 failed. El fallo es de UI y depende del snap:
`tests/test_page_comparison.py::test_changing_a_weight_changes_the_order` supone que Site04/Site11 (sitios curados) se evalúan en el punto
cubierto más cercano; con el snap al mejor punto Site11 (score 99,3) pasa a ganar con los pesos del perfil. Lo debe actualizar quien posea
`ui/` (o la página de comparación fijar `snap_prefer="nearest"`). Además, `AppTest.from_function` (`test_page_timeline.py::test_no_visibility…`)
deja `sys.modules["__main__"]` apuntando a un script temporal y cuelga cualquier `ProcessPoolExecutor` posterior; se aisló en
`tests/test_suitability_map.py` (fixture `_spawn_safe_main`).
