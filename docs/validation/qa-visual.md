# QA visual y de accesibilidad de LSI

Fecha: 14/11/2026. Método: app lanzada con `python -m streamlit run app.py --server.headless true --server.port 8765` y recorrida en Chrome (extensión Claude in Chrome), viewport 1727×1304. Capturas en `docs/capturas/` (JPG; la herramienta no permite elegir nombre ni formato PNG, se copiaron con el nombre `NN-pagina-modo`). Texto de página leído con `get_page_text`.

Alcance real: no se pudo cubrir todo (ver "Limitaciones de la prueba"). Lo no probado está marcado como NO PROBADO, no como OK.

## Resultado por página

| Página | Estado | Evidencia |
|---|---|---|
| Buscador (search) | OK con defectos menores | 01, 02, 11. Shackleton y Malapert encuentran resultados; el aviso de "ajuste al DEM (Site04, 0,80 km)" y el de "esfera lisa: sin datos de terreno" aparecen antes de evaluar. Defecto P2-1 (métricas truncadas). |
| Explorador 3D (explorer) | DEFECTO P1 | 18-21. Mapa global sin DEM correcto (aviso presente). Con DEM, la superficie 3D queda colapsada a un canvas de ~64×420 px en todas las capas (JS: `canvas {w:64,h:420}`, plot de 620 px). Las 4 capas se alternan, pero solo el mapa polar 2D es legible. |
| Mejores puntos y fechas (best_spots) | OK | 22. Site23, 14 d, perfil "Lander solar sin RHU": mapa, tabla top 3 y calendario con datos (mejor punto -85.984°, 2.612°E, score 98, inicio 2026-12-16). Sin NaN. |
| Horizonte y visibilidad (horizon_visibility) | OK con defectos menores | 03-06, 12. Deslizador funciona (100 pasos de teclado = +16 h 40 min). Perfil azimut-elevación y vista polar se dibujan. En Malapert: avisos de esfera lisa visibles. P2-2, P2-3. |
| Línea temporal (timeline) | DEFECTO P1 | 07-10. Las cuatro vistas (Periodo actual, Comparar fechas, Año y estaciones, Animación) cargan sin traza. Con Shackleton (0 % de Sol) las bandas y "Resumen por mes" salen vacías con ejes numéricos sin sentido (-1…6). P1-2. |
| Comparación de sitios (comparison) | OK con defectos | 23. Los 3 sitios DEM se comparan; hay veredicto por puertas, avisos de ajuste por sitio y gráficas con valores. P1-3, P2-6. |
| Potencia y paneles (power_panels) | OK con defectos | 13-17. Comparar 3 tecnologías, vertical con seguimiento (media 61 %, pico 101 %) y batería (alertas rojas + gráfica) funcionan. P2-4, P2-5, P2-7. |
| Score del sitio (site_score) | OK con defectos | 24-26. Perfil y pesos (Planificador): al subir Energía solar, la nota pasa de 58 a 70 y los pesos se renormalizan. Avisos y puertas visibles. P1-3, P2-8. |
| Acerca de (about) | OK | 27. Texto completo, fuentes, limitaciones y estado de validación. |

## Defectos priorizados

### P0 (bloquean la demo)
Ninguno confirmado. El servidor dejó de responder una vez durante la prueba (ver P1-4); si se reproduce en la demo sería P0.

### P1 (graves)

**P1-1. Explorador 3D: la superficie 3D no es utilizable.**
Pasos: abrir `/explorer` (Site23 por defecto) -> pestaña de capas "Elevación/Pendiente/Incertidumbre/Calidad".
Observado: el canvas WebGL mide ~64×420 px dentro de un plot de 620 px; solo se ve una tira del terreno. La fila de botones de capa del plot aparece cortada por la izquierda ("diente | Incertidumbre vertical | Confianza de muestreo"). La barra de color "Elevación (m)" se solapa con la leyenda en ambos plots (mapa 3D y polar). Reproducible tras recargar y en las capas Elevación y Pendiente. Evidencia: 19, 20, 21.
Salvedad: probado solo en este Chrome; no se descarta un problema de tamaño del contenedor Plotly dependiente del navegador, pero el 2D polar sí se ve bien.

**P1-2. Línea temporal: gráficas vacías sin explicación en puntos sin Sol.**
Pasos: buscar Shackleton -> "Evaluar con ajuste al DEM" -> Línea temporal (cualquier vista).
Observado: "Bandas temporales de visibilidad" y "Resumen por mes" son rectángulos vacíos con ejes -1…6 y "Instante" suelto; en "Año y estaciones" las barras mensuales no se ven y las muestras de la leyenda de Tierra y de "Sol y Tierra" son casi invisibles. Los KPIs sí dicen "0,0 % / ≥ 365,0 d". Falta un texto del tipo "no hay Sol ni Tierra visibles en este periodo". Evidencia: 08, 09.

**P1-3. Cifras de Sol y noche distintas entre pantallas para el mismo sitio, sin indicar la ventana.**
Pasos: Site23, 2026-12-01, 30 d, perfil Lander sin RHU. Comparación: Sol 42,7 %, noche más larga ≥ 304,7 h. Score del sitio: "89 % del tiempo de Sol" y "noche más larga 30,8 h". Puede deberse a ventana de misión de 14 d con la mejor fecha frente al periodo de 30 d, pero ninguna pantalla lo rotula, y en la de score "89 %" coincide con el 89,5 % de Tierra de Comparación. Verificar que no se confunda Sol con Tierra. Evidencia: 23, 24.

**P1-4. El servidor Streamlit dejó de responder una vez.**
Tras recorrer las páginas y lanzar una carga rápida de 9 páginas en iframes desde JavaScript, `/_stcore/health` dejó de responder (curl rc=7) y no hay traza en el log. No se aisló la causa (puede ser mi carga o el cierre del proceso de fondo). Hay que repetirlo con carga concurrente real antes de la demo.

### P2 (menores)

1. **Texto cortado en las métricas del Buscador** (modo Público): "Crater (crá…" y "-89.670°, 1…" en las tarjetas Tipo y Coordenadas. Evidencia: 02, 11.
2. **Avisos de potencia en páginas sin potencia** (Horizonte, Línea temporal, Score en modo Público): se muestran 3-4 avisos de panel ("tj-gaas-lander-body", "Temperatura de panel fuera del rango…") que empujan el contenido útil bajo el pliegue. Evidencia: 03, 07.
3. **Concordancia de género y estados**: "la Tierra sigue oculto", "la Tierra está oculto bajo el horizonte". En Animación, la insignia "↑ ○ oculto" sale en verde, mientras en el resto "oculto" es rojo; el instante inicial es "2026 11 30 23:59:59", anterior al inicio del periodo y con otro formato de fecha. Evidencia: 04, 10.
4. **Formato numérico mixto**: "0.80 km" y "0,80 km" en la misma pantalla; "Rango 57.9 – 58.3", "Confianza 0.00" frente a "58,0". Evidencia: 03, 24.
5. **Gráfica de potencia**: las series horizontales (GaAs y 4J) se superponen y quedan tapadas por los marcadores naranjas de "Extrapolación en frío"; el texto al pie solapa la etiqueta "Dec 6 / 2026" del eje X. El texto de ayuda dice "100 % sería su potencia máxima" y la gráfica llega al 101 %. Nombres de panel truncados con "…" en el selector y en el resumen. Evidencia: 14.
6. **Mensajes de desarrollador al usuario público**: Comparación muestra "Captura PNG: instala kaleido (pip install kaleido)". También el párrafo de "Mejores puntos" cita `python scripts/precompute_suitability.py --validate`. Evidencia: 22, 23.
7. **Ortografía sin acentos** en datos del catálogo de paneles: "mastil", "union", "baterias", "maximo", "segun". Incumple la regla de acentos del proyecto. Evidencia: 13, 15.
8. **Confianza 0,00 con "Estrechez 0,98"**: la tarjeta del score muestra Confianza global 0.00 y Soporte del DEM 0.00 mientras el texto dice "ya no sale baja por sistema". Mostrarlo de forma coherente (puede ser correcto: mínimo de factores, pero el valor "0.00" parece un fallo). Evidencia: 24.
9. **Etiquetas del mapa global del Explorador** recortadas o solapadas: "15 (Falcon)", "ldysseus", "Site23 Malap…", "Apolo 12/14" superpuestos. Evidencia: 18.
10. **Accesibilidad**: `<html lang="en">` con contenido en español; tooltips con `aria-label` en inglés ("Help for Sitio"). Evidencia: 30.
11. **Mensaje "Recomendaría" frente a "no hay ganador"** en Comparación: el aviso azul dice que no hay ganador automático y el bloque siguiente titula "Cuál recomendaría y por qué". Evidencia: 23.
12. **Estado entre sitios**: al cambiar de Shackleton a Malapert, el deslizador de Horizonte conserva el instante anterior (16:40) sin avisar.

## Comprobaciones transversales

- **Excepciones/trazas en pantalla**: ninguna en las 9 páginas recorridas.
- **Consola**: solo un aviso de librería (`preventOverflow modifier is required by hide modifier`, de Streamlit/Popper). La consola se empezó a leer a mitad del recorrido (la herramienta solo registra desde la primera lectura); Buscador y primera carga de Horizonte no están cubiertos.
- **Avisos científicos siempre visibles**: SÍ. El cuadro "Alcance y límites" aparece en las 9 páginas y en los 3 modos (visto en capturas y en el texto de página). Los avisos de "esfera lisa/sin datos de terreno" aparecen en Buscador, Horizonte, Potencia, Explorador y en la barra lateral (11, 12, 18).
- **Tiempos de carga**: percibidos < 5 s en navegación entre páginas (esperas de 3-8 s usadas por prudencia). Explorador 3D, Comparación y Año y estaciones fueron las más lentas, no cronometradas. Sin medición objetiva.
- **Contraste**: texto de avisos amarillos, rojos y verdes legible sobre fondo oscuro. Texto secundario muy pequeño (leyendas y pies de gráfica, ~9-10 px) y de bajo contraste. Leyendas de Tierra en Resumen por mes casi invisibles (P1-2). No se midió con herramienta.
- **No depende solo del color**: bien resuelto. Estados con icono y texto ("○ oculto", "● visible", "NO APTO", "✖ NO superada"), series con trama distinta (dashed/dotted) y puertas con texto.
- **Teclado**: foco visible (contorno ámbar de 3 px) tras 12 pulsaciones de Tab; el deslizador de tiempo responde a flechas. Orden de foco no recorrido completo.
- **Responsive**: no se pudo redimensionar la ventana (la herramienta informó éxito pero `innerWidth` siguió en 1727). Alternativa: iframe de 390 px de ancho con `/power_panels`. Con la barra lateral expandida (estado inicial) esta cubre casi todo el contenido y hay que cerrarla (28); cerrada, el contenido se apila bien y los avisos siguen visibles (29). No se comprobó tablet ni el resto de páginas en móvil (la verificación automática por iframe falló).
- **Enlaces rotos**: no se comprobaron los enlaces externos (ficha USGS/IAU) por la regla de navegar solo a localhost.
- **Modos Público/Planificador/Experto**: probados Público (todas las páginas), Experto (Potencia, Explorador) y Planificador (Score, Acerca de). Experto muestra Panel/Montaje/Perfil duplicados entre barra lateral y cuerpo de Potencia (riesgo de desincronización, no verificado).

## Limitaciones de la prueba

- Redimensionado real de ventana no disponible; el responsive se evaluó con un iframe de 390 px solo en una página.
- Shackleton se evaluó con ajuste al DEM (Site04, 0,80 km); sin Sol durante todo el periodo, así que las gráficas de visibilidad con datos se vieron con Malapert/Site23.
- Horizonte con Malapert en esfera lisa: se vio la parte superior; no se comparó la forma del horizonte contra otro sitio.
- Un incidente de servidor caído obligó a relanzarlo (misma configuración); no se retocó código ni tests.
- Ningún dialogo del navegador (alert/confirm) se disparó.

## Veredicto

**NEEDS WORK** para demo pública. El flujo principal (buscar, evaluar, horizonte, comparación, score, paneles, batería, mejores puntos) funciona sin trazas y los avisos científicos son visibles de forma consistente, que era el requisito más importante. Pero el Explorador 3D, que es una de las pantallas más vistosas, no muestra la superficie 3D en este navegador (P1-1); la Línea temporal muestra gráficas vacías sin explicación para el sitio estrella del reto, Shackleton (P1-2); y hay cifras no conciliadas entre Comparación y Score (P1-3). Conviene arreglar P1-1 a P1-3, repetir la prueba de estabilidad del servidor (P1-4) y revisar los P2 de formato y ortografía antes de presentar.
