# Workflow para grabar el vídeo de demo

Resultado: `demo_out/lsi-demo.mp4` (≈ 2 min, 1600×900, voz Helena en español) y `demo_out/narracion.srt`. Todo es reproducible con un solo comando; no hay edición manual.

## Herramientas (ya instaladas en esta máquina)

| Qué | Para qué | Cómo se instala |
|---|---|---|
| Playwright (Python) + Google Chrome | Maneja la app como un usuario y graba la pantalla | `python -m pip install playwright` (Chrome ya instalado) |
| `imageio-ffmpeg` | ffmpeg incluido (sin permisos de administrador) para montar vídeo y audio | `python -m pip install imageio-ffmpeg` |
| Voz «Microsoft Helena Desktop» (es-ES) | Narración, vía `System.Speech` de Windows | Viene con Windows 11 |

## Pasos

1. **Arranca la app** en un puerto libre, desde la rama `feat/lunaris-ui`:
   `python -m streamlit run app.py --server.port 8598 --server.headless true`
2. **Comprueba antes de grabar** (sin grabar): `python scripts/record_demo.py --out demo_out --no-record`.
   Hace la pasada de calentamiento (llena la caché de Streamlit: el primer cálculo con rangos es lento) y **lee de la pantalla** las cifras que se van a narrar. Si algo no se ve, el script se niega a grabar (`ERROR: no se pudo leer…`).
3. **Graba**: `python scripts/record_demo.py --out demo_out`.
   - Repite el calentamiento, genera las narraciones con Helena, graba el recorrido y lo monta.
   - Cada narración empieza cuando ya se ve lo que cuenta; el tramo de carga entre escenas se acelera hasta 2,5 s.
   - Se recorta la carga inicial (Streamlit muestra «Page not found» al abrir una URL interna en frío).
4. **Revisa el resultado**: abre `demo_out/lsi-demo.mp4` y `narracion.srt`. Una hoja de contacto rápida:
   `ffmpeg -i demo_out/lsi-demo.mp4 -vf "fps=1/6,scale=640:-1,tile=4x5" -frames:v 1 demo_out/sheet.jpg`
5. **Para.** el servidor de Streamlit (mira el PID del puerto con `Get-NetTCPConnection -LocalPort 8598`).

## Versión en inglés de 30 s (entrega a NASA Space Apps)

El portal pide inglés y una demo de vídeo ≤ 30 s o ≤ 7 diapositivas (límite de la guía anterior: confirmarlo en la guía 2026).
`python scripts/record_demo.py --url http://localhost:8598 --out demo_out --en-short` → `demo_out/lsi-demo-en-30s.mp4` (28,6 s, voz «Microsoft David» en-US) y `narration-en.srt`. Usa 3 escenas (Malapert «5 of 353», visor 3D, Shackleton 12-dic frente a 6-dic). La interfaz que se ve sigue en español.

## Escenas (lo que hace y lo que se narra)

| Escena | Pantalla | Se comprueba en pantalla |
|---|---|---|
| s1 | Buscador: escribe «Malapert», elige «Mons Malapert», «Evaluar este lugar» | La app llega a «Horizonte y visibilidad» |
| s2 | «Capacidad del sitio», Planificador, coordenadas −85,9841 / 2,6123, inicio 2026-12-01, 366 días | Nota 98, CONDICIONAL, **«5 de 353»** fechas de inicio que sirven |
| s3 | Explorador 3D: vista oblicua → observador → orbital amplia | El Sol «tapado… en este instante» |
| s4 | Shackleton TOP-1 (−89,5626 / 215,4724): inicio 2026-12-12 y luego 2026-12-06 | 12-dic APTO con enlace 100 %; 06-dic CONDICIONAL con 62 % y 127 h |
| s5 | «Mapa del polo sur»: zoom con la barra del mapa, del polo entero a Shackleton (cierre) | La app muestra el mapa; se narran los límites declarados |

## Reglas

- **No se narra ninguna cifra que no se vea.** Las del texto de cada escena están en `SCENES` de `scripts/record_demo.py`; la de la escena 2 se lee de la pantalla durante el calentamiento.
- Los puntos se teclean con 4 decimales (lo que admite el campo). La app propone las fechas; el vídeo no las inventa.
- El buscador evalúa el **centro** del rasgo (Mons Malapert: −85,98°, 358,33°E, NO APTO por pendiente). Por eso la escena 2 teclea el mejor punto candidato, y la narración lo dice.
- Si cambias el motor, `config/` o los datos: repite el paso 2 y mira si las comprobaciones siguen en verde antes de grabar.
- Subirlo a YouTube/Vimeo, firmarlo con tu cuenta y la licencia del vídeo son decisiones tuyas.
