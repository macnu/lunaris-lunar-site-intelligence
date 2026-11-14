# Estaciones terrestres adicionales: búsqueda y verificación (14/11/2026)

Objetivo: completar la red de estaciones con NASA NSN/LEGS, la elevación mínima real de ESTRACK y otras redes con soporte lunar. Regla: solo entra en una red lo que tiene posición **y** elevación mínima verificadas en documento. Los documentos descargados están en `data/raw/stations_docs/` (no va a git).

Niveles: **verificado** (documento + página), **derivado** (leído de una figura), **a verificar**.

## Resultado

| Estación / red | Posición | Elevación mínima | DTE lunar | Estado |
|---|---|---|---|---|
| DSN (DSS-14/-43/-63) | verificado (810-005/301 P) | 6° rx / 10,1° tx, verificado | sí | red por defecto, sin cambios |
| ESTRACK CEB-1 | verificado (EFM Tabla 2, p. 21 = NAIF, < 1 m) | máscara por acimut, máx. ≈ 5,5° (**derivado**, fig. 7) | sí (35 m, X/Ka) | red ESTRACK con 6° [sup] |
| ESTRACK NNO-1 | verificado (EFM Tabla 8, p. 77 = NAIF, < 1 m) | máscara por acimut, máx. ≈ 8,5° (**derivado**, fig. 35) | sí | red ESTRACK con 6° [sup] |
| ESTRACK MLG-1 | verificado (NAIF NDOSL) | no localizada (no está en el EFM de 2008) | sí | red ESTRACK con 6° [sup] |
| NASA WS1 (White Sands, 18,3 m) | verificado (NAIF NDOSL `WS1S`; NEN UG §9.2 a 1″) | **a verificar** | sí, histórico (LRO, NEN UG §9.2) | fuera de redes |
| NASA LEGS-1 (White Sands, 20 m) | lat/lon en folleto (sin altura) | **a verificar** (solo rango mecánico 0-90°) | es su misión; "capacidad futura" en NSN UG §3.4.1 | fuera de redes |
| NASA LEGS-2 (Matjiesfontein) | folleto, marcada "TBD" | **a verificar** | ídem | fuera de redes |
| JAXA Usuda 64 m | página JAXA/ISAS (segundo de arco) | **a verificar** | a verificar | fuera de redes |
| IDSN Byalalu, KSAT Lunar, CNSA | sin fuente oficial hallada | a verificar | n/c | no incluidas |

No se crea la red `NSN` ni `DSN+NSN`: no existe ninguna elevación mínima de NSN/LEGS en fuente oficial. No se inventa.

## Fuentes y páginas

- **LEGS Brochure r20** (https://essp.larc.nasa.gov/EVI-6/pdf_files/LEGS%20Brochure%20r20.pdf): "White Sands, USA: 32.544863, -106.612504"; "Matjiesfontein, South Africa: -33.231224, 20.58163 (TBD)"; "Pacific Region TBD". Misión: comunicaciones directas a Tierra y navegación de GEO a cislunar y hasta 2 millones de km, tres sitios equiespaciados. Sin altura ni máscara.
- **LEGS Brochure r25** (https://explorers.larc.nasa.gov/APSMEX25/SMEX/pdf_files/Prog05d_LEGS_Brochure_r25-1.pdf): sitios White Sands, Matjiesfontein y Geraldton (TBC), sin coordenadas; antena de 20 m; "Antenna Travel Range: ±300° azimut, 0 a 90° elevación" (rango mecánico, no máscara); G/T mínima 39 dB/K (X) y 47,5 dB/K (Ka), "preliminary pending finalization of system requirements". La r20 tenía a Alice Springs/Pacífico sin decidir: la ubicación del tercer sitio no está cerrada.
- **NSN User's Guide 457-GUIDE-0001** (21/02/2023, https://soma.larc.nasa.gov/STP/DYNAMIC/pdf_files/NSN%20UsersGuide%20457-GUIDE-0001_Baseline.pdf) §3.4.1, p. 13: LEGS = subred "futura" de antenas de clase 18 m para usuarios cislunares, L1 y L2, X y Ka; "capacidad comprometida", no operativa. No contiene latitudes ni longitudes, y no da elevación mínima de ninguna estación.
- **NEN User's Guide 453-UG-002905 Rev. 4** (19/03/2019, https://explorers.larc.nasa.gov/2021APMIDEX/pdf_files/453-UG-002905.pdf) §9.2: WS1 en 32°32′27″ N, 106°36′44″ W ("see NDOSL WS1S"), antena de 18,3 m, apoya a LRO. Las G/T se dan a 5° y 10° (referencias de rendimiento, no límites).
- **NAIF NDOSL** `ndosl_190716_v02.tf` (https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/stations/ndosl_190716_v02.tf), fila `WS1S`: 32°32′26.7178″ N, 253°23′16.4417″ E, h 1456.545 m (WGS 84). La posición de LEGS-1 del folleto queda ~450 m al norte de WS1: son emplazamientos distintos.
- **ESA ESTRACK Facilities Manual (EFM)** DOPS-ESTR-OPS-MAN-1001-OPS-ONN, issue 1 rev. 1, 19/09/2008 (copia en https://qsl.net/kj6dzb/images/GEO/DOPS-ESTR-OPS-MAN-1001-OPS-ONN_ESTRACK_Facilities_Manual_issue1.1.pdf; la copia es de terceros, el documento es de ESA):
  - CEB-1, Tabla 2 (p. 21): 40°27′09.68″ N, 4°22′03.18″ W, h 794.095 m; rango de elevación 0-90°. Figura 7 (p. 21): **máscara de horizonte por acimut** de 0,5° a 5,5° (pico ≈ 5,5° hacia 260°).
  - NNO-1, Tabla 8 (p. 77): 31°02′53.61″ S, 116°11′29.40″ E, h 252.2558 m; rango 0-90°. Figura 35 (p. 78): máscara de 0° a ≈ 8,4° (pico hacia 205°); supera 6° aproximadamente entre 175° y 235° de acimut (y roza 6,1° hacia 264°).
  - §5.5: las terminales "respetan el requisito de elevación mínima" de la UIT y de los acuerdos con el país anfitrión, sin dar cifra.
  - Las coordenadas del EFM (GRS80) coinciden con NAIF NDOSL a menos de 1 m. MLG-1 (2012) no está en el EFM.
- **ESA-DOPS-MGT-TN-0014 Issue 1.2** (16/03/2026, https://commercialisation.esa.int/wp-content/uploads/2025/09/ESA-DOPS-MGT-TN-0014_Antenna-Performance-Requirements_Issue1.2-20260316.pdf): requisitos de diseño para estaciones de "Near Space" (cislunar y SEL1/2): "Minimum TX elevation angle: 5 deg". Es un requisito para operadores que desarrollen capacidad, no la máscara de las antenas ESTRACK existentes.
- **JAXA/ISAS Usuda** (https://www.isas.jaxa.jp/en/about/facilities/usuda.html): 36°07′54″ N, 138°21′54″ E, 1456 m; no da elevaciones.

## ESTRACK: ¿elevación verificada?

**No como escalar.** Lo que ESA publica es una máscara por acimut, no una elevación única, y solo para CEB-1 y NNO-1 (2008). Por eso el valor de 6° sigue siendo suposición y los resultados de ESTRACK **no cambian**. Pero ahora se sabe que la suposición es optimista para NNO-1 en un sector de unos 60° de acimut (máscara hasta ≈ 8,5°) y ligeramente pesimista para CEB-1 (≤ 5,5°). Los máximos se leyeron a ojo de la figura (±0,3°): son "derivados". Modelar la máscara por acimut exigiría digitizar la figura y calcular el acimut de la Luna; no se hizo.

## Qué falta

- Elevación mínima (o máscara) de WS1, LEGS-1/-2/-3, Usuda, IDSN, KSAT Lunar, CNSA y de la transmisión de ESTRACK.
- Altura de LEGS-1 y fecha de operación de cualquier LEGS.
- Máscara de MLG-1 y NNO-3 (35 m, inaugurada el 04/10/2025).
- Máscara numérica de CEB-1/NNO-1 (solo hay figura).

## Cambios de código y datos

`config/ground_stations.json`: campos `horizon_mask_max_deg_read`, `position_crosscheck` y fuente de elevación en CEB-1, NNO-1 y MLG-1; sección nueva `stations_unverified` (WS1, LEGS-1, LEGS-2, UDSC-64), fuera de toda red y sin que ninguna función la cargue; `networks_not_available` actualizado. No se tocó `ground_stations.py`: la API no cambia. Tests: `tests/test_ground_stations.py` (final del fichero).
