# Convenciones físicas de LSI (fijas para todo el equipo)

Fuente de verdad. Cambiar una fila exige actualizar también `CLAUDE.md` y los tests de `tests/`. Verificado con spiceypy 8.4 (CSPICE N0067) y contra JPL Horizons; detalle en `luna-spice-sitios.md`.

| Convención | Valor fijo | Justificación |
|---|---|---|
| Azimut | Desde el Norte local hacia el Este, sentido horario visto desde arriba, 0°–360° (`atan2(E, N) mod 360`) | Criterio de Horizons ("Azi") y de la brújula; verificado: diferencia <0,0001° con Horizons. |
| Elevación | 0° = horizonte local plano de la esfera, +90° = cenit; `asin(U/|v|)` | Sin atmósfera no hay refracción (Horizons con `APPARENT=AIRLESS`). El horizonte real = terreno + curvatura lo añade el DEM; la elevación SPICE es sobre el plano tangente a la esfera. |
| Ejes ENU | E=(−sin λ, cos λ, 0); N=(−sin φ cos λ, −sin φ sin λ, cos φ); U=(cos φ cos λ, cos φ sin λ, sin φ), expresados en MOON_ME | Base ortonormal derecha. Sobre esfera, U coincide con la vertical geodésica. |
| Longitud | Este-positiva, −180…180 (o 0…360 al guardar), grados | Convención IAU/NAIF para la Luna, de MOON_ME y de Horizons (`{East-longitude positive}`). Fuentes con oeste-positivo se convierten al leer. |
| Latitud | Planetocéntrica = geodésica (esfera, f=0), grados, sur negativo | Sobre esfera no hay distinción. Horizons usa radios 1737.4 km en los tres ejes, por lo que coincide. |
| Marco de referencia | **MOON_ME** (media Tierra/eje polar, DE421), ID 31001, alias de MOON_ME_DE421 | Marco de los DEM LOLA de PGDA (polar estereográfico sur, DE421). No usar MOON_PA ni IAU_MOON (ver abajo). |
| Aberración | `LT+S` (tiempo luz + estelar), observador fijo en la superficie (`spkcpo`) | Coincide con la posición "aparente" de Horizons (<0,05″). Sin `S` el Sol se desplaza ~20,3″ (0,0056°): despreciable frente al disco de 0,53°, pero se pierde la coincidencia con Horizons. |
| Tiempo (interfaz) | UTC, cadena ISO; `str2et` interpreta UTC por defecto | Lo que ve el usuario y lo que acepta Horizons. |
| Tiempo (interno) | ET = TDB, segundos desde J2000 (`str2et`), requiere LSK `naif0012.tls` | Escala de SPICE. Todo cálculo sobre `et`; nunca sumar segundos a UTC. |
| Rango temporal | 1900-01-01 a 2050-12-31 23:58:51 (cobertura del BPC `moon_pa_de421_1900-2050.bpc`) | Fuera falla `SPICE(FRAMEDATANOTFOUND)`; el motor valida y rechaza con mensaje claro. El SPK DE421 llega a 2053-10-08, el límite real es el BPC. |
| Radio de referencia | 1737.4 km (esfera) | Radio de referencia del DEM LOLA (alturas sobre esa esfera) y el que usa Horizons. |
| Observador | `georec(lon, lat, 0, 1737.4, 0)`; el relieve se añade como altura aparte | Evita doble conteo del relieve: el DEM ya es altura sobre la esfera. |
| Distancias y tamaño angular | km (SPICE). Sol `2·asin(695700/d)`, Tierra `2·asin(6378.137/d)` (ecuatorial, sin atmósfera) | Radio solar IAU 2015 (el de Horizons); radio ecuatorial terrestre. |
| Ángulos | Grados en API y UI; radianes solo dentro de numpy/SPICE; sufijos `_deg`/`_rad` | Evita mezclas. |
| Longitudes | km en SPICE; metros en DEM; convertir en la frontera | Evita errores de factor 1000. |

## Marcos: cuál y por qué

| Marco | Qué es | Diferencia medida con MOON_ME (2026) |
|---|---|---|
| MOON_ME | Ejes media Tierra/eje polar. Rotación fija 67.92″, 78.56″, 0.30″ (ejes 3-2-1) desde MOON_PA_DE421. Definido en `moon_080317.tf` | 0 |
| MOON_PA | Ejes principales de inercia = MOON_PA_DE421 (del BPC) | 103,85″ de rotación (~0,87 km en superficie); latitud/longitud sub-Tierra difieren 0,022° / 0,019° |
| IAU_MOON | Fórmulas IAU aproximadas (`pck00011.tpc`) | 4″–10″ en 2026-2045 (~35-85 m). Único que funciona fuera de 1900-2050 |

Usar MOON_PA en lugar de MOON_ME desplaza todo ~0,87 km: peor que la resolución del DEM (5 m/px) y sin error visible; es el riesgo nº 1.
