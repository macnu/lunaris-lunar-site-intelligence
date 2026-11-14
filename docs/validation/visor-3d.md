# Visor 3D (three.js) del Explorador

Verificado el 14/11/2026 en Chrome real (`streamlit run app.py`, puerto 8781). Código: `ui/terrain_viewer.py`, `ui/static/terrain_viewer.{js,css}`, integración en `ui/pages/explorer.py`; pruebas: `tests/test_terrain_viewer.py`. Capturas: `docs/capturas/visor/`.

## Qué es
Vista 3D principal del Explorador (el 3D de Plotly queda en el expander «Vista alternativa»). three.js **r147 vendorizado** en `ui/static/vendor/` (MIT, SHA-256 en `MANIFEST.json`): el HTML es autocontenido, sin peticiones de red (comprobado con `read_network_requests`: solo `data:` y ficheros propios de Streamlit; una prueba lo vigila).

## Datos y límites honestos
- Malla ≤ 512 × 512 vértices. Malapert/de Gerlache: SDEM de 5 m remuestreado a ≈ 12 m/celda (recorte de 6 km); Site04: relieve LOLA a 15 m. Si hay más de 512 por lado se promedia por bloques.
- **Foto**: Site23/Site11 = ortomosaico SDEM (5 m/px de origen; desplazado ≈ 2,5 m del relieve) y, donde falta, mosaico NAC de 1 m/px (hasta ≈ 15 m de desfase); Site04 = solo mosaico NAC. Es un promedio de pasadas: **no es la luz de la fecha**. El aviso con fuente y resolución real está siempre visible. Donde no hay foto (máscara 0): gris con granulosidad muy sutil y rótulo «sin foto en esta zona»; no se inventa textura.
- **Luz**: dirección real del Sol (`AnalysisResult.sky`, instante del selector). Las sombras son las de `shadows.illumination` sobre la MISMA malla que se dibuja (canal B de la textura, sin shadow maps de three). Ambiente casi nulo. El sombreado por pendiente usa una exposición automática (con el Sol a 1° una superficie plana si no quedaría casi negra); es un recurso visual, no radiometría.
- **Cielo**: Sol (0,267° de radio real) y Tierra (radio angular real, ≈ 1,9° de diámetro; interruptor «Agrandar»; textura procedural, fase según el ángulo Sol-Tierra real). Estrellas aleatorias sin significado astronómico.
- **Vista del observador**: cámara a la altura del observador, exageración 1. Fuera del recorte se dibuja la silueta del **horizonte calculado** (`h_lb_deg`, cota inferior si el rayo salió del DEM): el Sol/Tierra bajo esa cota quedan tapados.
- La curvatura lunar se resta en la malla respecto al observador; el recorte es un plano estereográfico (simplificación declarada).
- Rendimiento: si una imagen tarda > 70 ms se reconstruye con la mitad de vértices. Sin WebGL: mensaje y remisión a la vista alternativa.

## Verificación visual (resumen honesto)
Convence: el relieve se lee como 3D con foto y sombras; el Sol y la Tierra coinciden con la tarjeta (Sol az 44° el 4,2° visible sobre el horizonte; Tierra az 350° el 5,7° visible; con el Sol a 1,0° y horizonte a 1,1° queda tapado). No convence del todo: el recorte se ve como una losa flotante sobre cielo negro en vistas orbitales; a 2 m de altura el terreno cercano es casi liso (12 m/celda); de Gerlache y Site04 tienen poca foto útil (Site04: 91 % sin foto en este instante; la foto NAC de sombra permanente es negra o inexistente). Las sombras cambian entre instantes (`malapert-cenital-16dic.jpg` frente a `malapert-cenital-20dic.jpg`).

Payload típico: 1,0 MB (cota dura 4 MB), más ≈ 0,6 MB de three.js en línea.
