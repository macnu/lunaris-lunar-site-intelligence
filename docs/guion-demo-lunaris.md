# Guion de demostración corto (3 minutos) · rama `feat/lunaris-ui`

Este es el guion para grabar el vídeo con la rama **`feat/lunaris-ui`** (marca LUNARIS, navegación superior y visor 3D con foto, Sol y Tierra reales). Tiene **tres escenas y cuatro cifras**. El guion largo, [`guion-demo.md`](guion-demo.md), sigue siendo la referencia de datos, plan B y qué no decir; las cifras de aquí salen de él (reproducidas con `lsi.pipeline` el 14/11/2026).

**Reconfirma las cuatro cifras en la app antes de grabar.** Si difieren, usa las de la app. El vídeo sigue **pendiente**: grabarlo y publicarlo es decisión del dueño.

**Ajustes previos:** `python -m streamlit run app.py`, modo **Planificador**, red **DSN**, sentido **recepción**, margen **0°**, perfil lander solar sin RHU, misión de 14 d, panel por defecto «Array vertical en mástil». Teclea las coordenadas exactas de `guion-demo.md` («Coordenadas exactas»).

## Las cuatro cifras

| Cifra | Valor | Dónde se ve |
|---|---|---|
| Malapert, inicio 2026-12-16 | APTO, nota 98,4 | «Capacidad del sitio» |
| Fechas de inicio que sirven en Malapert | 5 de 366 | tarjeta principal («Fechas de inicio que sirven»). **Solo sale con un periodo mayor que la misión**: pon inicio 2026-12-01 y 379 días (con periodo = misión hay una sola fecha y la fila no aparece) |
| Shackleton TOP-1, inicio 2026-12-12 | enlace 100 %, nota 97,4, APTO | «Capacidad del sitio» |
| Shackleton TOP-1, inicio 2026-12-06 | enlace 62 %, hueco de 127 h, CONDICIONAL (73,9) | «Capacidad del sitio» |

## Guion

| Tiempo | Pantalla | Qué dices |
|---|---|---|
| **0:00–0:50** | **Buscador** → «Malapert» → «Evaluar este lugar». Llegas a **Capacidad del sitio** con la tarjeta principal. | «Buscamos entre más de 9 000 lugares de la Luna. LSI responde a una pregunta: ¿este punto ve el Sol, ve la Tierra y podría hablar con ella? Malapert, 16 de diciembre: APTO, 98,4. Pero fíjate en la línea de al lado: solo 5 de 366 fechas de inicio sirven. La nota es la de la mejor fecha, y un candidato no es una certificación.» |
| **0:50–1:50** | **Visor 3D** de la misma página. Vista oblicua con foto y sombras; luego vista del observador con el Sol y la Tierra. | «Esto es relieve real de la NASA con foto de la cámara LROC. Las sombras y el Sol son los de este instante; la foto es una mezcla de pasadas, así que no es la luz de la fecha. Aquí el Sol está tapado por el horizonte *en este instante*: la ventana de 14 días lo tiene visible otras horas.» |
| **1:50–2:40** | **Capacidad del sitio** con las coordenadas del TOP-1 de Shackleton. Inicio **12-dic**, luego **6-dic**. | «Mismo punto, otra fecha. El 12 de diciembre el enlace con las antenas de la NASA es del 100 %: APTO, 97,4. El 6 de diciembre el Sol es igual de bueno, pero el enlace cae al 62 % y hay 127 horas sin comunicaciones: CONDICIONAL. Ver la Tierra no es poder hablar con ella.» |
| **2:40–3:00** | **Acerca de y límites** | «Esto es geometría y cobertura de estación, no un presupuesto de radio. Nuestros mejores candidatos no coinciden con el mapa de iluminación publicado (±0,2–0,3) y el relieve de 5 m tiene resolución efectiva de unos 30 m. Por eso decimos candidato, no recomendado.» + frase de cierre de `guion-demo.md`. |

## Reglas

- **Una sola cifra por frase.** Las demás (paneles, estaciones, pendiente a 50 y 100 m) están en pantalla: no las leas.
- No mezcles el 97,4 del TOP-1 con el 94,7 del TOP-2 de Shackleton: son puntos distintos.
- No digas «seguro», «aterrizable» ni «recomendado»; di «candidato».
- Plan B y lo que no se dice: `guion-demo.md`, secciones «Plan B» y «Qué NO decir en la demo».
