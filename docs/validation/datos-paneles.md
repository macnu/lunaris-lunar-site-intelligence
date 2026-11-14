# Registro de datos de paneles: fuente primaria, parámetro a parámetro

Fecha de lectura de todas las fuentes: **14/11/2026**. Los documentos están en `data/raw/datasheets/` (carpeta de datos, fuera de git; junto a cada PDF hay un `.txt` de `pdftotext -layout` para verificar la cifra). La página es la del PDF (orden de hoja), salvo que se diga otra cosa. Sin citas textuales: valores numéricos con su página.

**Niveles de evidencia:** `datasheet` (leído en el documento del fabricante) · `paper` (revisado por pares o informe de agencia, leído) · `derivado` (calculado a partir de lo anterior, con fórmula) · `investigación` (sin datasheet ni medida espacial) · `no disponible` (no existe en fuente primaria localizada: se propone aproximación con rango y etiqueta).

**Grupos:** `respaldado` (η y γ_T de datasheet/paper o derivados) y `experimental_sin_datasheet` (falta η o γ_T primarios; siempre visible y etiquetado, no se mezcla con los respaldados en rankings por defecto).

## 0. Resultado

| Panel | Antes | Grupo | Nivel | η BOL AM0 (%) | γ_T (%/K) | W/m² AM0 (η·1361) | W/kg |
|---|---|---|---|---|---|---|---|
| `tj-gaas-lander-body` | publicado | respaldado | datasheet | 29,5 (Azur) / 30,7 (Spectrolab) | −0,23 derivado | 401,5 | celda 320–831; array típico rígido ~80 |
| `tj-gaas-vertical-mast` | a verificar | respaldado | derivado | 29,5 (celda de referencia) | −0,23 heredado | 401,5 | no disponible |
| `mj-4j-high-eff` | publicado/estimado | respaldado | datasheet | 31,3 (Z4J+); 30,0 (Z4J); 32,0 (IMM-α) | −0,264 medido (Z4J+) | 426,0 | celda IMM-α 884 |
| `rosa-flexible-rollout` | **estimado** | respaldado | derivado | 29,5 (celda; manta no publicada) | −0,23 heredado | 401,5 (cota) | **array 71–124** (flysheet) |
| `si-legacy` | **estimado** | experimental | investigación (γ_T) | **17,4** datasheet Sharp | **no disponible** (−0,45 ±) | 236,8 | celda 715 (Azur) |
| `cigs-thin-film-flex` | **estimado** | experimental | investigación | 15,7 (nota de prensa) / 8,84 (paper 2002) | −0,38 módulo terrestre | 213,7 | 1960 sin encapsular (nota de prensa) |
| `perovskite-si-tandem-demo` | **estimado** | experimental | investigación | **19,2** AM0 (Joule 2020) | **no disponible** (−0,26 ±) | 261,3 | 420 sin encapsular (paper) |
| `tj-gaas-rover-body` | a verificar | respaldado | derivado | 29,5 (celda de referencia) | −0,23 heredado | 401,5 | no disponible |

W/m² = η_default × 1361 W/m² (constante solar del proyecto). Es potencia **de celda/CIC**, sin empaquetado, cableado ni estructura; los datasheets miden a 1353 W/m² (Spectrolab, Rocket Lab, Azur), 1367 (Azur) o 1367 W/m² a 25 °C (Sharp), diferencia <0,6 %.

**Aviso de alcance.** `respaldado` en `tj-gaas-vertical-mast`, `rosa-flexible-rollout` y `tj-gaas-rover-body` significa que los parámetros de la **celda de referencia** modelada están leídos; ni VSAT ni los rovers ni la manta ROSA publican su celda ni su eficiencia de conjunto.

## 1. Spectrolab XTJ Prime (D1) · `spectrolab_xtj_prime.pdf`

URL https://www.spectrolab.com/photovoltaics/XTJ-Prime_Data_Sheet.pdf · datasheet fechado 7/16/18 · tipo: datasheet.

| Parámetro | Valor | Unidad | Condición | Pág. | Nivel |
|---|---|---|---|---|---|
| η BOL | 30,7 | % | AM0 135,3 mW/cm², 28 °C, promedio >100 000 células | 1 | datasheet |
| Voc / Jsc / Vmp / Jmp | 2,720 / 18,0 / 2,406 / 17,5 | V, mA/cm², V, mA/cm² | ídem | 1 | datasheet |
| Retención Pmp 1 MeV e⁻ (AIAA S-111) | 0,94 (1E14), 0,88 (5E14), 0,85 (1E15), 0,65 (1E16) | factor | ídem | 1 | datasheet |
| Retención Pmp (ECSS, con recocido) | 0,94 / 0,90 / 0,87 / 0,70 | factor | ídem | 1 | datasheet |
| Masa de celda | 50–84 | mg/cm² | espesor 80–225 µm | 1 | datasheet |
| ΔVmp/ΔT, ΔJmp/ΔT (BOL) | −6,3 mV/°C ; 5,0 (µA/cm²/°C) | | rango 15–125 °C | 2 | datasheet |
| γ_T | −0,233 | %/K | (−6,3 mV/K·17,5 mA/cm² + 5,0 µA/cm²/K·2,406 V)/42,1 mW/cm² | 2 | derivado |

Absortividad 0,88 y γ_T −0,22 %/°C: NASA/JPL D-101316 (sección 8 de este registro), no este PDF. La unidad de Jmp′ sale corrupta en el PDF; se toma µA/cm²/K por magnitud (un término en mA daría una pendiente física imposible).

## 2. Azur Space 3G30-Advanced 6x12 (D2) · `azur_3g30_advanced.pdf`

URL https://www.azurspace.com/media/uploads/file_links/file/bdb_00010893-02-00_3g30-advanced_6x12.pdf · DB 00010893-02, 24/03/2026 · datasheet.

| Parámetro | Valor | Condición | Pág. | Nivel |
|---|---|---|---|---|
| η BOL celda / CIC | 29,5 / 29,1 % (1353 W/m²); 29,2 / 28,8 % (1367 W/m²) | AM0 WRC, 28 °C | 2 | datasheet |
| Voc, Isc, Vmp, Imp (celda BOL) | 2700 mV, 1215 mA, 2400 mV, 1185 mA | 71,25 cm² | 2 | datasheet |
| Degradación 1E15 e⁻ 1 MeV | η 26,2 % (celda, 1353): retención 26,2/29,5 = 0,888 | | 2 | derivado |
| Masa | ≤86 mg/cm² (celda, 6,1 g) · ≤123 mg/cm² (CIC, 8,8 g) | | 2 | datasheet |
| Coeficientes BOL | ΔVoc −6,2 mV/°C; ΔIsc 0,85 mA/°C; ΔVmp −6,7 mV/°C; ΔImp 0,57 mA/°C | 28–140 °C | 2 | datasheet |
| γ_T | −0,231 %/K = (−6,7 mV/K·1185 mA + 0,57 mA/K·2,4 V)/2844 mW | | 2 | derivado |
| Absortividad (CIC, coverglass AR 100 µm) | ≤0,91 | | 2 | datasheet |

Emisividad: no aparece.

## 3. Rocket Lab SolAero Z4J+, Z4J, IMM-α (D3, D4, D5)

URLs: `RL-SolAero-Data-Sheet-Z4J+-v8.pdf`, `…-Z4J.pdf`, `…-IMM-Alpha.pdf` en https://www.rocketlabusa.com/assets/Uploads/ · datasheets.

| Parámetro | Valor | Condición | Pág. | Nivel |
|---|---|---|---|---|
| Z4J+ η BOL (CIC, coverglass 100 µm) | 31,3 % ("mínimo promedio" en p.1); Voc 3,72 V, Jsc 13,4, Vmp 3,31 V, Jmp 12,8 mA/cm² | AM0 135,3 mW/cm², 28 °C | 2 | datasheet |
| Z4J+ retención Pmp (ECSS recocido) | 0,988 (3E13), 0,966 (1E14), 0,927 (5E14), 0,894 (1E15), 0,848 (5E15), 0,715 (1E16) | 1 MeV e⁻ | 2 | datasheet |
| Z4J+ Pmp′ BOL | −0,1117 mW/cm²/°C (Voc −9,3 mV/°C, Vmp −9,8 mV/°C, Jmp 4,7 µA/cm²/°C) | **28–80 °C**, medido, "aproximaciones simplificadas" | 2 | datasheet |
| Z4J+ γ_T | −0,264 %/K = −0,1117/42,37 | | 2 | derivado |
| Z4J η BOL (celda desnuda) | 30,0 % (Voc 3,95, Jsc 12,0, Vmp 3,54, Jmp 11,5) | AM0 135,3, 28 °C | 2 | datasheet |
| Z4J Pmp′ BOL / retención 1E15 | −103 µW/cm²/°C / 0,90 | | 2 | datasheet |
| Z4J γ_T | −0,253 %/K = −0,103/40,7 | | 2 | derivado |
| IMM-α η BOL | 32,0 % mínimo promedio (Voc 4,78, Jsc 10,66, Vmp 4,28, Jmp 10,12) | AM0 135,3, 28 °C | 1-2 | datasheet |
| IMM-α masa | 49 mg/cm² (−42 % vs ZTJ); CIC 70,6 / 76,9 / 83,3 / 96,0 mg/cm² con coverglass 2/3/4/6 mil (orden de la tabla) | | 1-2 | datasheet |
| IMM-α retención | Pmp 0,91 (5E14), 0,87 (1E15), 0,71 (5E15) | recocido ECSS | 2 | datasheet |
| IMM-α coef. BOL | Voc −10,5, Vmp −11,2 mV/°C; Jmp 6,7 µA/cm²/°C | **PROYECTADOS** por el fabricante | 2 | datasheet (proyectado) |
| IMM-α γ_T | −0,195 %/K = (−11,2 mV/K·10,12 mA/cm² + 6,7 µA/cm²/K·4,28 V)/43,3 mW/cm² | | 2 | derivado |
| IMM-α W/kg (celda) | 884 = 0,32·135,3/49 | | 1-2 | derivado |

Tabla de coeficientes de Z4J+: pdftotext desordena las filas; BOL = fila con Pmp′ −0,1117 (valores por fluencia en el mismo orden 1E14/1E15/1E16: −0,1123, −0,1095, −0,1021). Ningún datasheet de Rocket Lab da α ni ε. IMM-β 33,3 % (nota de prensa) no se usa.

## 4. Sharp, silicio espacial (D6) · `sharp_si_cic.pdf`

URL https://global.sharp/solar/en/space-qualified/pdf/datasheet_Si-CIC.pdf · 22/03/2024 · datasheet (Si tipo p, PERC, CIC).

| Parámetro | Valor | Condición | Pág. | Nivel |
|---|---|---|---|---|
| η BOL | 17,4 % | AM0 136,7 mW/cm², **25 °C** | 1 | datasheet |
| Voc, Jsc, Vmp, Jmp, FF, Pmax | 0,665 V; 46,8; 0,543 V; 43,8 mA/cm²; 0,763; 23,8 mW/cm² | ídem | 1-2 | datasheet |
| η EOL | 13,1 % (1E14), 10,8 % (1E15) | 1 MeV e⁻ | 1 | datasheet |
| Retención Pmax | 0,75 (1E14), 0,62 (1E15) | 1 MeV e⁻, 1E12 e/cm²/s | 2 | datasheet |
| Espesor de coverglass | 0,1 / 0,21 / 0,3 mm | | 1 | datasheet |
| γ_T, masa, α, ε | **no disponible** | | — | no disponible |

Aproximación propuesta (investigación): γ_T −0,45 %/K (rango −0,60…−0,30), α 0,80, ε 0,85/0,80; ninguna leída en fuente.

**Azur silicio** (NASA/JPL D-101316, PDF p.30, que cita azurspace.com a 07/09/2016): η 16,9 % AM0 28 °C, masa 32 mg/cm² de celda desnuda, diodo Zener integrado. El datasheet propio de Azur no se leyó. Nivel: paper (agencia citando al fabricante). W/kg celda = 0,169·135,3/32 = 715 (derivado).

## 5. ROSA (Redwire) y ELSA (D8, D9, D10)

| Parámetro | Valor | Fuente / pág. | Nivel |
|---|---|---|---|
| Celdas admitidas | "todos los tipos y tamaños de celda" (agnóstico) | flysheet ROSA v1_10-2-2025, p.1 | datasheet |
| Configuraciones (longitud m, masa kg, potencia BOL kW, ancho estibado m) | Diamond 8,6 / 36 / 3,3 / 2,32 · Opal 12,6 / 42,7 / 5,3 / 2,67 · Sapphire 21,2 / 160 / 12,9 / 3,35 · Tanzanite 24,8 / 180 / 17,6 / 4,15 · SunStone 19,4 / 331 / 28 / 3,1 · Phenacite 18,5 / 521 / 37 / 4,94 | `redwire_rosa_flysheet.pdf` p.1 (misma tabla en `redwire_rosa_page.html`) | datasheet ("aproximación basada en planes de diseño") |
| W/kg de array | 91,7 · 124,1 · 80,6 · 97,8 · 84,6 · 71,0 (= potencia/masa) | cálculo | derivado |
| Densidad de potencia estibada | ~40 kW/m³ | flysheet p.1 | datasheet |
| Voló en ISS 2017 | lanzamiento 03/06/2017 (CRS-11); ala "parcialmente poblada con tres tipos de celda" | NTRS 20190000446, p.1-2 | paper |
| η de manta, γ_T, α, ε, W/m² de array | **no disponible** (se hereda la celda 3J de referencia, cota superior) | — | no disponible |
| ELSA (hermano de ROSA) | Si o III-V, >100 W/kg, 500 W–5 kW, −125…125 °C operativo | `redwire_elsa_flysheet.pdf` p.1 | datasheet |

No se confirma por lectura que ROSA de ISS (iROSA) use XTJ Prime: solo aparece en resultados de búsqueda; no se usa.

## 6. CIGS (D11, D12, D13)

| Parámetro | Valor | Fuente / pág. | Nivel |
|---|---|---|---|
| η AM0 | 15,7 % "a escala de producción" (módulo Titan, 15,7 W, ~8 g, 0,03 mm) | Ascent Solar, nota de prensa 09/06/2025 (`ascent_pr_157.html`) | investigación (nota del fabricante, sin certificado; la nota mezcla "STC y AM0") |
| W/kg | 1960 "antes de encapsulación" | misma nota | investigación |
| η AM0 de laboratorio | 8,84 % (Voc 802,9 mV, Jsc 25,07 mA/cm², FF 60,06 %), CIGS2 sobre acero 127 µm, medido en NASA GRC; AM1.5 en NREL 9,26 % | NTRS 20030000597, resumen p.1 (NASA/CP-2002-211831) | paper (2002, laboratorio) |
| γ_T Pmpp | −0,38 %/°C | MiaSolé FLEX-03N, p.2; **STC AM1.5, 25 °C, módulo terrestre** | datasheet terrestre → investigación en AM0 |
| Masa areal | 1,8 kg/m² sin adhesivo (2,2 con adhesivo) | MiaSolé p.2 | datasheet terrestre |
| η de módulo terrestre | 14,4–17,0 % a STC | MiaSolé p.2 | datasheet terrestre |
| Rango de T medido, degradación por radiación, α, ε | **no disponible** | — | no disponible |

El estudio NASA Marshall (NTRS 20180006427, TFAWS 2018) se descargó y revisó: diapositivas sin η ni α/ε utilizables para CIGS.

## 7. Perovskita/silicio (D14, D15, D19)

| Parámetro | Valor | Fuente / pág. | Nivel |
|---|---|---|---|
| η AM0 | 19,2 % con ~257 W/m² estabilizados, AM0 1350 W/m² (η AM1.5G 21,3 %); tándem monolítico perovskita/SHJ encapsulado en cuarzo; AM0 "mimetizado" con LED y EQE | Lang et al., Joule 2020, doi:10.1016/j.joule.2020.03.006 (texto completo en `joule2020_lang_europepmc.txt`; sin paginación en el XML: secciones Summary/Results) | paper (laboratorio) |
| Masa y W/kg | 61 mg/cm² (capa activa 261,5 µm) → 0,42 W/g **sin** encapsulado | ídem | paper |
| Degradación | η a ~1 % de la inicial tras ~1E11 p⁺/cm² de 68 MeV (Jsc 21,5 → 0,3 mA/cm²; 257 → 4 W/m²); perovskita/CIGS retiene ~85 % | ídem | paper (protones, no e⁻) |
| 27,49 % AM0 certificado (12,56 cm²; Voc 2,003 V, Jsc 22,44 mA/cm², FF 82,74 %) | tándem de Tianjin Univ. et al.; vuelo en globo a 29,7 km | **solo noticia** (`perovskite_info_2749.html`); paper no localizado | investigación (secundaria; no se usa como default) |
| γ_T | **no disponible**: ACS Energy Lett. 2023 (Babics et al., solo resumen) indica que el coeficiente de Isc depende del espectro y del rango de T; sin Pmax | `kaust_tempcoef.html` | no disponible |
| Medida en el espacio | **no existe** en lo leído: solo laboratorio. SSTEF-1 (IM-3) pendiente | — | investigación |

El 21,1 % AM0 (IEEE PVSC 2020) y el −0,26 %/K de KAUST solo aparecieron en resúmenes o comentarios; se retiran como valores de partida (−0,26 queda como aproximación `a_verificar` con rango).

## 8. Informe NASA/JPL D-101316 (D7) · `nasa_planetary_2017.pdf`

URL https://solarsystem.nasa.gov/system/downloadable_items/715_Solar_Power_Tech_Report_FINAL.PDF · dic 2017 · informe de agencia que recopila datos de fabricantes a 07/09/2016.

| Parámetro | Valor | Pág. PDF | Nivel |
|---|---|---|---|
| Tabla 3-2: η, masa, γ_T, absortividad | 3G30C 29,8 %, 86 mg/cm², −0,23 %, α 0,91; ZTJ 29,5 %, 84, −0,22 %, 0,92; XTJ Prime 30,7 %, 84, −0,22 %, 0,88 | 30 | paper (agencia) |
| Azur Si | 16,9 % AM0 28 °C, 32 mg/cm² | 30 | paper (agencia) |
| Array rígido típico | ~80 W/kg, ~330 W/m² | 33 | paper |
| Array flexible típico | 100–175 W/kg, ~338 W/m² | 34 | paper |

## 9. Misiones: fuente primaria o degradación

| Misión | Antes | Ahora | Fuente leída |
|---|---|---|---|
| Blue Ghost M1: 400 W, 3 paneles (2 laterales + 1 cubierta), 1470 h, SolAero | publicado | **publicado** (celda no declarada) | Firefly (`firefly_bg1.html`) y Rocket Lab 23/01/2025 (`rl_blueghost_pr.html`) |
| IM-1/Nova-C: 200 W, 3 paneles | publicado | **a verificar** | solo Wikipedia; press kit NASA IM-1 (`nasa_im1_presskit.pdf`) leído: sin potencia ni celda (solo cita un panel en cubierta, p.12); el press kit IM-2 tampoco |
| ISS ROSA 2017 | publicado | publicado | NTRS 20190000446 |
| Gateway PPE 60–65 kW | publicado | a verificar | nota Redwire solo vista en búsqueda |
| VSAT/VSAT-XL, mástil 32 ft, LunaGrid | publicado | a verificar | NASA/Astrobotic no releídas |
| Pragyan 50 W, Yutu-2 | publicado | a verificar | Wikipedia / Space.com |
| Lunojod 2, Surveyor | publicado/a verificar | a verificar | presentación JHUAPL no releída |
| Chandrayaan-3 738 W | a verificar | a verificar | prensa |

No se tocaron `mission_profiles` (umbrales de misión, fuera de este encargo): varios siguen etiquetados `publicado` sin releer (p. ej. FSP 10–40 kWe, límites DSN); conviene una pasada análoga.

## 10. Lo que sigue sin fuente primaria

- Emisividades ε de todos los paneles y α de todos salvo 3G30A (Azur) y XTJ Prime/ZTJ (JPL).
- γ_T: silicio y perovskita-Si (ninguno en fuente leída); CIGS solo de un módulo terrestre.
- Eficiencia de conjunto y W/m² de array de ROSA, VSAT y rovers.
- Cualquier medida en superficie lunar de células Si, CIGS o perovskita-Si.
- Degradación por polvo (ya declarada sin cifra en `model_defaults.f_dust_default`).
