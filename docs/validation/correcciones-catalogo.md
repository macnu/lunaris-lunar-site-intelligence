# Registro de correcciones del catálogo (paneles, misiones, sitios)

Fecha: 14/11/2026. Base: `revision-espacial.md` §5 y verificación web hecha ahora. Confianza: **alta** = varias fuentes concordantes; **media** = prensa; **sin cambio de valor** = solo etiqueta.

| # | Fichero / campo | Anterior | Nuevo | Fuente | Confianza |
|---|---|---|---|---|---|
| 1 | `panels.json` `lander_solar_no_rhu.max_landing_slope_deg.failure_observed` | 12 | `null` (a verificar) | El ~12° local (atribuido a LRO, «sporty») solo aparece en prensa de búsqueda; no se leyó fuente primaria ni NASA | media |
| 2 | mismo, nueva clave `final_tilt_deg_observed` | (no existía) | 30 | https://www.flyingmag.com/odysseus-lunar-lander-alive-well-but-likely-not-upright ; inverse.com (prensa) | media |
| 3 | mismo, `confidence` | publicado | a_verificar | 10°/5° son declaración del CTO de IM en prensa, no especificación | alta |
| 4 | `panels.json` `design_life_surface_days` | publicado | a_verificar (valor 14 igual); nota con IM-2 ~10 d y Blue Ghost ~14 d | Wikipedia/Skyrocket (secundaria); https://spacepolicyonline.com/news/im-2-mission-ends-one-day-after-lunar-landing/ | alta |
| 5 | `panels.json` misión IM-2 | «~24 h por orientación» | planificada ~10 d; terminada en <1 día; «~24 h» a verificar | spacepolicyonline.com (URL arriba); https://www.astronomy.com/space-exploration/intuitive-machines-im-2-moon-lander-is-lying-dead-in-a-crater/ | alta |
| 6 | `panels.json` misión Blue Ghost M1 | sin fechas | aterrizó 02/03/2025, apagada al ocaso 16/03/2025 (~14 d); horas exactas a verificar | https://www.nasa.gov/news-release/nasa-science-continues-after-fireflys-first-moon-mission-concludes/ ; https://www.space.com/the-universe/moon/farewell-blue-ghost-private-moon-lander-goes-dark-to-end-record-breaking-commercial-lunar-mission | alta |
| 7 | `panels.json` misión Chandrayaan-3 | sin estado | sin calentadores, no despertó el 22/09/2023, sin señal | https://theprint.in/science/chandrayaan-3-lander-rover-put-on-sleep-mode-for-lunar-night-isro-hopes-they-wake-up-on-22-sept/1745709 ; https://www.universetoday.com/163394/day-has-returned-but-indias-lander-and-rover-have-failed-to-wake-up | alta |
| 8 | `paneles-y-misiones.md` §2 pendiente | «Odysseus tocó a ~12°» | ~30° final; 12° a verificar | ver 1-2 | media |
| 9 | `paneles-y-misiones.md` §5 filas Chandrayaan-3, IM-1, IM-2, Blue Ghost, VIPER | estados antiguos | como 5-7; VIPER «condicionada a Blue Moon MK1, finales de 2027» | https://www.space.com/astronomy/moon/viper-lives-jeff-bezos-blue-origin-will-land-ice-hunting-nasa-rover-on-the-moon-in-2027 | media |
| 10 | `paneles-y-misiones.md` fila Artemis III | «Amundsen, Nobile, Leibnitz β, Faustini, Shackleton–Slater, Malapert» (erróneo) | las nueve de oct-2024: Peak near Cabeus B, Haworth, Malapert Massif, Mons Mouton Plateau, Mons Mouton, Nobile Rim 1, Nobile Rim 2, de Gerlache Rim 2, Slater Plain | https://www.upi.com/Science_News/2024/10/28/nasa-artemis-moon-landing-regions/5971730152372/ | media |
| 11 | `paneles-y-misiones.md` fila Rover (12 h) | sin referencia | anotado que VIPER publica ~50 h (propuesta, valor NO cambiado) | NTRS 20220008301 vía revision-espacial.md | alta (dato) |
| 12 | `sites.json` 13 regiones `artemis3_*` (nota) | «No usar hasta tener lat/lon» | añade si siguen o no en la lista de nueve (Faustini Rim A, Peak Near Shackleton, Connecting Ridge(+Ext), de Gerlache Rim 1, de Gerlache-Kocher, Leibnitz Beta, Amundsen Rim: fuera) y que no hay coordenadas oficiales | UPI (arriba) | media |
| 13 | `luna-spice-sitios.md` §sites | — | misma aclaración | UPI | media |

## No cambiado (y por qué)

- Coordenadas Artemis III: la búsqueda no devolvió lat/lon en fuente NASA; siguen `null`.
- `max_dark_h_no_nuclear` del rover (12 h hard): el cambio a 50 h soft es de semántica del score (otro agente, `simulation.json`/código); solo se anota.
- `sites.json`: las misiones con `confianza: publicado` tienen como fuente la lista de Wikipedia (secundaria) y fechas de conocimiento general (la nota ya lo dice). No se degradó la etiqueta porque `contracts.py` solo admite `publicado | aprox | a verificar`; queda como deuda: considerar `aprox`.
- Odysseus: coordenadas del sitio ya son `aprox` (80.13°S 1.44°E).

Tests: `tests/test_catalog.py`, `tests/test_panels.py`, `tests/test_pipeline.py` en verde (49 passed); ninguna asserción codificaba un dato corregido.

## Cierre del defecto D1 de `puerta-final.md`: paneles `null` pasan a estimados (14/11/2026)

Los cuatro paneles no calculables pasan a **calculables con etiqueta «estimación sin datasheet»**, con valor central, rango y fuente por parámetro (detalle y tabla en `docs/science/paneles-y-misiones.md` §8). Confianza: `estimado` (hay ancla en fuente) o `suposicion` (sin ancla); ninguno `publicado`. Las fuentes se leyeron como resumen de búsqueda, no como PDF.

| # | Campo | Anterior | Nuevo | Fuente | Confianza |
|---|---|---|---|---|---|
| 14 | `rosa-flexible-rollout` η, γ_T, α, ε | null / a_verificar | η 29,5 % (27–33,3); γ_T −0,23 (−0,26…−0,20); α 0,91; ε 0,85 / 0,80 (0,5–0,85) | Azur 3G30-Advanced; NASA NTRS 20230002489; Rockwell SPS 1976 | estimado |
| 15 | `si-legacy` α, ε; η 17→16 % (14–18); γ_T −0,45 (−0,60…−0,30) | α/ε null | α 0,80, ε 0,85 / 0,80 | PVSC 2020 (resumen); NREL 9061 (snippet) | estimado / suposición (α, ε trasera) |
| 16 | `cigs-thin-film-flex` α, ε; η 12 % (10–15,7); γ_T −0,35 (−0,45…−0,30) | α/ε null; a_verificar | α 0,88, ε 0,80 / 0,80 | Ascent Solar 15,7 % AM0; MiaSolé FLEX-03 −0,38 %/°C (terrestre) | estimado / suposición (α, ε) |
| 17 | `perovskite-si-tandem-demo` η 25→21,1 % (18–25); γ_T null→−0,26 (−0,30…−0,20); α, ε | null / suposición | α 0,85, ε 0,85 / 0,80 | IEEE PVSC 2020 21,1 % AM0; KAUST −0,26 %/K (AM1.5) | estimado / suposición (α, ε trasera) |
| 18 | `panels.py` | `PanelSpec` | `PanelSpecEx(PanelSpec)` + `panel_status()` + `power_band()`; API anterior intacta | — | — |
| 19 | `tests/test_pipeline.py` (2 aserciones) | esperaban ROSA con `error` «α/ε» | ROSA ahora calculable | — | — |

**Siguen sin poder calcularse:** ninguno del catálogo. Perovskita-Si queda con la advertencia de que la degradación por radiación (Joule 2020: ~1 % de eficiencia residual en tándem perovskita/Si-SHJ) no está modelada.

## Sustitución de «estimado» por fuente primaria en los paneles (14/11/2026)

Registro completo con páginas: `docs/validation/datos-paneles.md`. Documentos en `data/raw/datasheets/` (fuera de git). Resumen de cambios en `config/panels.json` (schema 1.1.0):

| # | Panel / campo | Anterior | Nuevo | Fuente (leída) | Nivel |
|---|---|---|---|---|---|
| 20 | todos: `evidence_group`, `evidence_level`, `evidence_summary`, `areal_power_w_m2_am0`, `datasheet_sources` | (no existían) | nuevos; W/m² = η·1361 | ver datos-paneles.md | derivado |
| 21 | `rosa-flexible-rollout` | estimado (27–33,3 %; sin W/kg) | respaldado/derivado: η 29,5 % (celda 3J), 71–124 W/kg derivados del flysheet; se retira el 27 % y el 33,3 % | Redwire ROSA flysheet p.1; NTRS 20190000446 | derivado |
| 22 | `si-legacy` η | 16 % (14–18) por resumen PVSC | 17,4 % AM0 136,7 mW/cm² 25 °C; retención 0,75/0,62 (1E14/1E15); Azur 16,9 % y 32 mg/cm² vía JPL | Sharp datasheet p.1-2; NASA/JPL D-101316 p.30 | datasheet |
| 23 | `si-legacy` γ_T, α, ε | −0,45; 0,80; 0,85/0,80 | iguales, relabeladas `no_disponible`/suposición; grupo experimental | ninguna lo da | no disponible |
| 24 | `cigs-thin-film-flex` η | 12 % (juicio LSI) | 15,7 % (mejor caso declarado, nota de prensa) / 8,84 % (NASA GRC 2002); experimental | Ascent PR 09/06/2025; NTRS 20030000597 | investigación |
| 25 | `cigs-thin-film-flex` γ_T | −0,35 | −0,38 %/°C de módulo terrestre AM1.5 | MiaSolé FLEX-03N p.2 | investigación |
| 26 | `perovskite-si-tandem-demo` η | 21,1 % (resumen PVSC) | 19,2 % AM0 (1350 W/m²); 61 mg/cm²; ~1 % de η con protones | Lang et al., Joule 2020 (leído) | paper |
| 27 | `perovskite-si-tandem-demo` γ_T | −0,26 (KAUST vía comentario) | −0,26 relabelada `a_verificar`/`no_disponible` | Babics 2023 solo resumen | no disponible |
| 28 | `mj-4j-high-eff` | η 32,0 % (IMM-α), γ_T −0,20 proyectado; IMM-β 33,3 % | default Z4J+ 31,3 % y −0,264 %/K medido (28–80 °C); IMM-α 32,0 % y Z4J 30,0 % como extremos; IMM-β retirado | Rocket Lab Z4J+, Z4J, IMM-α datasheets p.1-2 | datasheet |
| 29 | `tj-gaas-lander-body` | γ_T «estimado», α «publicado» sin leer | γ_T derivado con páginas; α 0,91 leído (Azur p.2); XTJ Prime α 0,88 (JPL) | Azur p.2; Spectrolab p.1-2 | datasheet |
| 30 | Misión IM-1 (Nova-C 200 W) | publicado | a_verificar | solo Wikipedia; press kit NASA IM-1 leído sin la cifra | — |
| 31 | Misión Blue Ghost M1 (400 W, 3 paneles) | publicado (S5 sin leer) | publicado, con fuente leída; celda no declarada | Firefly + Rocket Lab 23/01/2025 | fabricante |
| 32 | Gateway PPE, VSAT/VSAT-XL, mástil 32 ft, Pragyan 50 W, Yutu-2, Lunojod 2 | publicado | a_verificar (fuente no releída) | — | — |
| 33 | `panels.py` | `PanelSpecEx` con estimación | + `evidence_group`, `evidence_level`, `evidence_summary`, `areal_power_w_m2_am0`, `split_by_evidence_group()`; fórmulas físicas intactas | — | — |
| 34 | `tests/test_panels.py` | ROSA entre los «estimados»; asertaba confianza ∈ {estimado, suposicion} | ROSA es «calculable» sin banda (ya no es estimación); los tres experimentales se asertan por grupo/nivel (η de Si y perovskita sí es `publicado`); 2 tests nuevos | justificación: el valor estimado de ROSA se sustituyó por uno derivado de datasheets | — |

**Para otros agentes (no tocado):** (1) `ui/pages/power_panels.py`: mostrar `evidence_group` y no mezclar el grupo experimental en rankings por defecto; usar `panels.split_by_evidence_group()` y `areal_power_w_m2_am0`; (2) `confidence` mantiene los 4 niveles antiguos, así que la UI actual sigue funcionando; (3) `tests/test_determinism.py::dem_site23` falla por un `KeyError: 'h'` en `export._METRIC_DECIMALS` ajeno a los paneles.
