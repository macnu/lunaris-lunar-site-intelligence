# Horizonte desde el campo lejano (DEM polar de 80 m): exactitud medida

## Qué es el modo FAR_FIELD

Fuera de los tres recortes de 5 m (Site04, Site11, Site23) LSI caía a «esfera lisa». Desde ahora, para cualquier punto del
dominio del DEM polar LOLA de 80 m (de 80°S al polo, ±304 km) el horizonte se calcula con ese DEM como **única** fuente
(`HorizonMode.FAR_FIELD`, `terrain.horizon.compute_horizon_far_field`):

- el suelo del observador sale del propio DEM de 80 m (interpolación bilineal);
- paso radial de 40 m (½ píxel; un paso de 5 m no añade información y cuesta 8 veces más);
- Sol, Tierra, enlace y ventanas se calculan igual que en modo DEM con ese horizonte;
- el **score es parcial** («terreno fino sin datos», `terrain_data = False`): la pendiente a 80 m no se usa como pendiente de
  aterrizaje; la confianza sale **baja** (c_sup = 0); el veredicto es SIN DATOS o NO APTO provisional, nunca APTO;
- no se calcula el rango de incertidumbre (no hay σz/TOTERR a 80 m);
- más al norte de 80°S sigue la esfera lisa; dentro de un recorte de 5 m manda el DEM de 5 m.

Aviso científico (con las cifras de esta validación, nunca genérico): «Resolución 80 m: horizonte aproximado; no sirve para
decidir un aterrizaje fino. Medido frente al DEM de 5 m en 120 puntos: …».

## Método

`scripts/validate_far_field.py` (semilla 20260814; reproducible): 40 puntos aleatorios en cada recorte (Site23, Site11, Site04),
a ≥ 3 km del borde y con ≥ 95 % de píxeles válidos en ±500 m. Para cada punto dos análisis completos de 30 días
(2027-03-01 → 2027-03-31, paso 600 s, observador a 2 m, perfil `lander_solar_no_rhu`): modo DEM (5 m, con el 80 m como campo
lejano más allá del recorte, como en la app) y modo FAR_FIELD (solo 80 m, `AnalysisRequest.force_far_field=True`).
Horizonte: 1440 azimuts por punto (0,25°). «Veredicto»: estado (apto / no apto / sin datos) de las puertas no terrenales
del score (G0, G1, G4, G6, G7; G2 y G3 dependen del terreno fino y no existen en 80 m).

## Resultados (120 puntos)

| Magnitud (80 m − 5 m) | Valor |
|---|---|
| Horizonte, RMS global | **0,68°** (mediana por punto 0,24°; p95 por punto 1,76°) |
| Horizonte, máximo absoluto | **5,8°** (p95 de los máximos por punto: 4,5°) |
| Horizonte, sesgo medio | **−0,25°** (80 m más bajo en el 87 % de los puntos: optimista) |
| Fracción de Sol (30 d) | media +0,008; \|error\| medio 0,009; **p95 0,040**; máx. 0,126 |
| Fracción de Tierra (30 d) | media +0,008; \|error\| medio 0,009; **p95 0,038**; máx. 0,246 |
| Fracción de enlace DSN (30 d) | p95 0,038; máx. 0,246 |
| Puntos que cambian el veredicto por puertas no terrenales | **10 %** (12 de 120) |
| Puntos que pasan de NO APTO a SIN DATOS | 5 % (6 de 120) |
| Suelo del observador (80 m − 5 m) | \|Δz\| medio 1,0 m, máx. 3,6 m |

Por recorte (RMS del horizonte / p95 de \|ΔSol\| / % que cambia de veredicto): Site23 0,78° / 0,027 / 10 %; Site11 0,70° / 0,062 / 12,5 %;
Site04 0,52° / 0,009 / 7,5 %.

## Cuándo es fiable y cuándo no (honesto)

**Fiable** para estimar el orden de magnitud de la luz y de la Tierra visible en terreno abierto y para comparar zonas del polo
entre sí: en la mitad de los puntos el horizonte difiere menos de 0,24° (el disco solar mide 0,53°) y la fracción de Sol cambia
menos de 0,001 en la mediana (el 50 % de los puntos tiene \|ΔSol\| < 0,001).

**No fiable** para:

1. **Decidir un aterrizaje.** Un punto de cada diez cambia de veredicto por puertas no terrenales, y no hay pendiente ni
   rocas: por eso el score es parcial y nunca APTO.
2. **Cerca de paredes y bordes de cráter, crestas y cimas.** El 80 m suaviza los obstáculos próximos: el error máximo del
   horizonte llega a 5,8° en una dirección (≈ un resalto de 8-10 m a 100 m), y el 80 m **subestima** el horizonte (sesgo −0,25°,
   87 % de los puntos), es decir, **sobreestima la luz**. El punto curado por defecto de Malapert (una cresta) da 0,69 de
   Sol con 80 m frente a 0,50 con 5 m (+0,19), peor que cualquier punto del muestreo aleatorio: en cimas, tomar el
   resultado como cota optimista.
3. **Puntos con Sol o Tierra parciales.** Un 4 % de los puntos tiene \|ΔSol\| > 0,05 (hasta 0,13) y un 5 % \|ΔTierra\| > 0,05
   (hasta 0,25). No se midió por separado el rango de fracción de Sol donde el error es mayor.
4. **Suelos de cráter en sombra permanente**: ambos modos dan ≈ 0 de Sol y el acuerdo es trivial; no valida nada.

Limitaciones de la validación: los puntos caen en tres recortes (Malapert, de Gerlache, Shackleton), que no representan todo
el polo (llanuras altas, cráteres grandes); 30 días de una sola lunación; la atribución del error máximo a las paredes
próximas es una interpretación física (Δz del suelo ≤ 3,6 m no la explica), no se midió por distancia.

Los tres números principales entran en `lsi.pipeline.FAR_FIELD_VALIDATION` y en el aviso de la interfaz; si se repite la
validación hay que actualizarlos allí.
