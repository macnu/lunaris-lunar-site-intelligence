# Puerta de realidad final 2: el núcleo «conectividad y solar por ubicación»

Fecha: 2026-11-14. Todo lo de abajo lo ejecuté o leí yo en esta sesión. Scripts de comprobación fuera del repo (scratchpad). No se ha editado código, config ni tests; solo este informe y dos correcciones factuales en `docs/guion-demo.md`.

## Veredicto: CON RESERVAS (el núcleo funciona y sus cifras son reproducibles; no hay defecto bloqueante)

- El núcleo pedido (qué energía solar y qué conectividad da cada ubicación, a qué bases de la NASA y a qué horas locales) existe, calcula bien y lo dice con honestidad.
- No certifico más que eso: «APTO» no certifica nada; el enlace es geometría más cobertura de estación, no un presupuesto de radio; la potencia es de celda y sin empaquetado.
- Lo que el usuario llamó «datos estimados» está **resuelto en lo que importa** (η, γ_T y α de los paneles respaldados leídos en datasheet, con página) y **lo que sigue siendo suposición está listado abajo y la UI lo declara**.

## Ejecuciones propias

| Qué | Resultado exacto |
|---|---|
| `python -m pytest -q` completo (incluye `test_independent_visibility` y `test_independent_link`) | **811 passed, 38 skipped, 0 failed** en 300 s, código de salida 0. Los 38 skips son «falta el DEM Site01» (`test_luna_cases.py`, comprobado con `-rs`: 7 reportes que agrupan los casos, todos por ese motivo) |
| `pytest --collect-only` / ficheros / `def test_` | 849 casos / 46 ficheros / 590 funciones (coincide con el README) |
| `run_analysis` con ventana de 14 d, panel `tj-gaas-lander-body` + seguimiento, DSN/recepción/0° | Reproduce **todas** las cifras del guion de los puntos Shackleton TOP-2, TOP-1 (12-dic y 6-dic), de Gerlache, Malapert (14 y 30 d), sensibilidad 0/3/5° de los cuatro casos, sentido de transmisión, vertical fijo/horizontal de los tres sitios, 4J frente a 3J, cuenta atrás de Malapert, distancias y rangos del snap, confianza y horizonte máximo |
| Streamlit `--server.port 8771` | `/_stcore/health` = `ok` HTTP 200 y `/` 200. PID 8732, línea de comandos `python -m streamlit run app.py ... --server.port 8771`; `Stop-Process`; después `Get-NetTCPConnection -LocalPort 8771 -State Listen` no devuelve nada |

## Tabla de criterios

| # | Criterio | Estado | Evidencia propia |
|---|---|---|---|
| 1 | Las cifras de «Capacidad del sitio» = `run_analysis` | **Cumple** | AppTest en Shackleton mejor punto (−89,9353; 217,6443; 12-dic), de Gerlache (16-dic) y Malapert (16-dic), 14 d: Sol 100 %, noche 0 h, elevación solar máx. 1,4 / 2,6 / 5,2°, enlace 100 / 95,4 / 100 %, hueco 0 min / ≥ 15 h 35 min / 0 min, 405 W/m² y 9717 Wh/m² (Shackleton), horas de contacto por día 24,0 / 22,9 / 24,0. Idénticas al motor |
| 2 | Rotula periodo, ventana y perfil | **Cumple** | «Periodo analizado», «Ventana de misión», «perfil: Lander solar (sin RHU)», «Cifras sobre: periodo completo» |
| 3 | Distingue Tierra visible y enlace posible | **Cumple** | Tarjetas «Tierra visible (geometría)» y «ENLACE POSIBLE» separadas (de Gerlache: ambas 95,4 % porque con margen 0° y red DSN coinciden); textos de Earthset aclaran que el enlace puede acabar antes |
| 4 | Tabla de bases con hora local correcta | **Cumple** | diciembre: PST, CET, AEDT; 14-jul-2027: PDT, CEST, AEST; zonas del 27-mar, 2-abr, 5-abr, 30-oct y 1-nov de 2027 con `et_to_local`: cambios de horario en las fechas esperadas. La tabla del día muestra ventanas **enteras** con «continúa…»; coinciden con `contact_windows` y con el UTC+huso a mano (Madrid 13-dic 11:27:11-20:10:57 UTC = 12:27-21:11 CET; Canberra 12-dic 22:34:50 → 13-dic 11:45:31 = 09:35-22:46 AEDT). Las ventanas inexistentes «Canberra 09:34-22:11» y «Goldstone 10:21-18:12» no aparecen |
| 5 | Avisos honestos | **Cumple** | Visibles en pantalla: «NO es un presupuesto de enlace RF», «Sol visible no es potencia garantizada», «Elevación mínima de ESTRACK supuesta (6°)», «La red NSN no está incluida», paneles experimentales con etiqueta y aviso rojo, «Visibilidad geométrica ≠ potencia ni enlace garantizados». Sin afirmaciones de «seguro/aterrizable/garantizado»: las únicas apariciones de «recomendado» están acotadas («no es aprobado») |
| 6 | Paneles: nada datasheet/paper/derivado sin fuente | **Cumple** | Recorrí `config/panels.json` (8 paneles, todos los campos con `evidence`): ninguno con evidencia datasheet/paper/derivado queda sin `source`, `note`, `basis` o `derivation`. Los α/ε sin fuente están marcados `a_verificar` o `suposicion`. Grupos: 5 respaldados, 3 experimentales (`si-legacy`, `cigs-thin-film-flex`, `perovskite-si-tandem-demo`) |
| 7 | Tres datasheets contrastados con `pdftotext` | **Cumple** | Azur 3G30 p.2: η 29,5 % (CIC 29,1 %), α ≤ 0,91, ΔVmp −6,7 mV/°C, Imp 1185 mA. Rocket Lab Z4J+ p.2: η 31,3 %, coeficientes «28 °C a 80 °C», Pmp′ −0,1117 mW/cm²/°C (el orden en bruto confirma que −0,1117 es la fila BOL). Sharp Si p.1: 17,4 % a AM0 136,7 mW/cm² y 25 °C. Spectrolab XTJ Prime p.1: 30,7 %, retención 0,94 a 1E14 |
| 8 | Experimentales separados y etiquetados en la UI | **Cumple** | Selector con «· EXPERIMENTAL», columna «Evidencia», `st.error` con `EXPERIMENTAL_TEXT`, y en «Acerca de» la división 5/3 |
| 9 | Coherencia entre pantallas, NaN, negativos, >100 % | **Cumple con reservas** | Score del sitio Malapert: 98 (98,4), confianza media 0,75, APTO, hueco 0 h: igual que Capacidad y motor. 8 paneles calculables, sin no finitos en potencia/score. Un valor sobre 100 % (100,85 % Shackleton, vertical con seguimiento) está explicado (perihelio, frío) y no se recorta. Ver D2 |
| 10 | Cifras del guion de demo | **Cumplía salvo 2 puntos, corregidos** | Ver «Cambios en el guion» |
| 11 | README | **Sin falsedades encontradas** | 46 ficheros, 590 funciones, 849 casos, 811 passed / 38 skipped, 31 JPG, 9106 lugares, 8 paneles calculables, 5/3: todo verificado. No tiene cifras por sitio |

## Defectos (ninguno bloquea)

- **D1 (medio). Texto de «hueco máximo» inventa un hueco cuando es 0.** Con enlace continuo la pantalla escribe «Hueco máximo sin enlace: del 11/12/2026 23:59 al 11/12/2026 23:59 UTC, 0 min. El enlace vuelve el 11/12/2026 23:59 UTC y lo recupera primero Goldstone» (Shackleton; Malapert igual con el 15/12). Es una fecha anterior al periodo y un «regreso» que no existe. La métrica «HUECO MÁXIMO sin enlace: 0 min» sí está bien. `test_station_table_has_utc_and_local_columns_and_gap_recovery_text` solo exige que el texto exista.
- **D2 (medio). Trampa de panel/montaje.** En la UI, `tj-gaas-lander-body` (el panel que el guion mandaba elegir) no admite seguimiento y la pantalla cae a *Vertical fijo*: Malapert 272 W/m² de media (no 397), Shackleton 1,4 % de la nominal. El panel por defecto `tj-gaas-vertical-mast` da las cifras del guion. Corregido en el guion; la app no avisa de que ese panel en el polo cae a vertical fijo (sí muestra «montaje Vertical fijo»).
- **D3 (bajo). «Mejor fecha… Sirven el 100% de las fechas probadas»** cuando el periodo es igual a la misión (una sola fecha de inicio, 1 de 1). El mapa dice 5 de 365 fechas aptas para el mismo punto de Malapert (no re-verificado por mí el 5/365; el 39/365 y 143/365 del guion tampoco). Dos pantallas, dos «porcentajes de fechas» sin rotular el denominador.
- **D4 (bajo). Errata «parcialmente ocultoo»** en «Horizonte y visibilidad» (`_STATE_WORD` añade «{g}» a «oculto»).
- **D5 (bajo). «Contactos del 2026-12-14»** encabeza viñetas cuyo «contacto más largo» es del 22-dic, con hora local sin fecha cuando cruza la medianoche.

## Qué sigue siendo estimado o suposición en el núcleo, y si la UI lo dice

| Parámetro | Valor | ¿Lo dice la UI? |
|---|---|---|
| Margen de antena del lander | 0° por defecto (suposición) | Sí (sidebar, «Acerca de», «El margen de antena del lander es una suposición») |
| Umbral G7, hueco máximo | 12 / 24 / 48 / 96 h por perfil, blandas, `suposicion` | Sí («Acerca de» los lista y dice que no son datos publicados) |
| Contacto mínimo útil / G6 | 2 h por día (8 en base ISRU), `suposicion` | Sí |
| ESTRACK | 6° supuesta; posiciones NAIF | Sí, «SUPUESTA» en la tabla y aviso |
| NSN | no incluida | Sí |
| Transmisión | 10,1° publicada (baja potencia); 13,6° alta potencia no modelada; `tx_min_elevation_deg` del JSON sin uso | Parcial: el selector existe; la alta potencia solo en README |
| Criterio de borde de la Tierra | ≥ 50 % del disco, «a calibrar» | Sí en «Acerca de» (umbral 0,50 «a calibrar»); la cifra de 17 min de error de borde solo en `limitaciones.md` |
| Tolerancia de traspaso | 20 s `[cal]` | **No en la UI** (sí en `metodologia.md` y `ground_stations.json`) |
| Orientación terrestre `IAU_EARTH` | 0,072° (≈ 20 s por cruce), medido | Documentación; no en pantalla |
| Máscara de terreno y ocupación de las antenas DSN | no modelados | Sí |
| Emisividades y α de casi todos los paneles | `a_verificar` o `suposicion` | Sí (aviso naranja por panel) |
| γ_T de silicio y perovskita-Si; η de manta de ROSA/VSAT/rover | no disponible, hereda la celda 3J | Sí (grupo experimental y «respaldado = celda de referencia») |
| Polvo, albedo, sombra propia, eclipses | no modelados | Sí |
| Pesos y umbrales del score | convenciones sin calibrar | Sí |
| Resolución efectiva del DEM | ~30 m, heurística `a verificar` | Sí |

## Cambios en `docs/guion-demo.md` (verificados con `run_analysis` y AppTest)

1. **Paso 5 de «Antes de grabar».** Antes: «Panel GaAs triple unión (lander) (`tj-gaas-lander-body`); el montaje por defecto en el polo es vertical con seguimiento azimutal». Ahora: dejar el panel por defecto `tj-gaas-vertical-mast` y no elegir `tj-gaas-lander-body` en la app. Verificación: AppTest en Malapert con `tj-gaas-lander-body` muestra «montaje Vertical fijo» y 272 W/m²; con el panel por defecto 397 W/m² y 98,8 %; en Shackleton el panel por defecto da 405 W/m² y 9717 Wh/m² (las cifras del guion). Vertical fijo a azimut 0° da 1,40 % en el motor para Shackleton.
2. **Nota del TOP-2 el 6-dic.** Antes: «NO APTO por G0 y G4». Ahora: «G0, G4 y G7». Verificación: `run_analysis` Shackleton −89,9353 / 217,6443, inicio 2026-12-06: puertas que fallan G0, G4 y G7 (Sol 61,9 %, noche 128,1 h, enlace 57,7 %, hueco 142,0 h; score 35,0).

El resto de cifras del guion coincide con el motor (ver ejecuciones). El guion distingue bien el punto (TOP-2 = mejor punto del buscador, TOP-1 = mapa) y la ventana de cada cifra.

## Reservas honestas

- **R1.** El 39/365, 143/365 y 5/365 («inicios aptos») y el caso límite de de Gerlache (SIN DATOS con periodo igual a la misión; 98,0 con 15 d) **no los reproduje**. Rangos, fechas, puntos y puntuaciones del mapa sí (`best_points` y `snap_candidate`).
- **R2.** Contrastes con Horizons y las 38 pruebas contra literatura (DEM Site01) no los ejecuté; confío en los tests que pasan y en `revision-enlace.md`.
- **R3.** Solo reproduje la UI con AppTest, no en navegador. La captura visual de «Capacidad del sitio» sigue sin existir en `docs/capturas/`.
- **R4.** Rangos de incertidumbre de ancho cero en puntos saturados (0,0 h – 0,0 h): correcto pero poco informativo.
- **R5.** Selección: el «mejor punto» sale de optimización sobre malla de 250 m; la confianza «alta» mide calidad de dato, no riesgo de selección.
- **R6.** Hallazgo previo D1 de la primera puerta (4 de 8 paneles no calculables) **ya no se da**: los 8 se calculan; el README se corrigió en consecuencia.

## Lo que decide el usuario

1. Si D1 y D2 se corrigen en `ui/` antes de la entrega (hoy el texto del hueco 0 min confunde y el panel `tj-gaas-lander-body` cae a vertical fijo sin aviso en el polo).
2. Si se acepta que las cifras de potencia son de celda y sin empaquetado (W/m²), y que «APTO» sigue sin ser certificación.
3. Si se graba el vídeo con el panel por defecto y las cifras del guion corregido, y si se añade una captura de «Capacidad del sitio».
4. Licencias de datos y de código, y repositorio remoto (como en la primera puerta; no han cambiado).
