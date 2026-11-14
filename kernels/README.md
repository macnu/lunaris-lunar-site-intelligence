# Kernels SPICE

Esta carpeta contiene los kernels de NAIF/JPL que usa LSI. **No se versionan** (`.gitignore`: `kernels/*`, salvo este README). Se descargan con:

```powershell
python scripts/fetch_data.py
```

El script baja también los DEM (≈ 0,8 GB); los kernels son ≈ 18 MB. Servidor: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/. Las rutas y el orden de carga están en `config/simulation.json` (`frames.kernels`).

## Condiciones de uso

Verificado el 14/11/2026 en https://naif.jpl.nasa.gov/naif/rules.html: los kernels de NAIF «pueden ser descargados y usados por cualquiera»; se permite redistribuirlos **solo sin modificar** (si se modifican, hay que cambiar la atribución del productor y el nombre del fichero); NAIF solicita reconocer el uso de SPICE y de los recursos NAIF/PDS. LSI no los modifica ni los redistribuye.

## Kernels

Tamaños y SHA-256 medidos sobre los ficheros descargados. Cobertura obtenida con `spkcov`/`pckcov` de spiceypy 8.4 (CSPICE N0067).

| Fichero | URL | Qué aporta | Cobertura / fecha | Bytes | SHA-256 |
|---|---|---|---|---|---|
| `naif0012.tls` | `.../lsk/naif0012.tls` | Segundos intercalares (LSK): UTC ↔ ET. Último intercalar registrado: 31/12/2016 | sin límite temporal propio | 5 257 | `678e32bd…a039b` |
| `pck00011.tpc` | `.../pck/pck00011.tpc` | Constantes de cuerpos (radios, `IAU_MOON`). Autor: N. Bachman (NAIF), 27/12/2022 | n/a | 131 226 | `3dff7b1d…bb1` |
| `moon_080317.tf` | `.../fk/satellites/moon_080317.tf` | Marcos lunares: define `MOON_ME_DE421` (31007) y el alias `MOON_ME` (31001) sobre `MOON_PA_DE421`. Creado 17/03/2008 por N. Bachman | n/a | 21 437 | `78732477…c7993` |
| `moon_assoc_me.tf` | `.../fk/satellites/moon_assoc_me.tf` | Asocia `MOON_ME` a la Luna (para `et2lst`, `lspcn`). Actualizado 18/03/2008 | n/a | 8 468 | `52c62204…a6c1c` |
| `moon_pa_de421_1900-2050.bpc` | `.../pck/moon_pa_de421_1900-2050.bpc` | Orientación lunar de alta precisión (ejes principales, DE421) respecto a ICRF. Creado 18/03/2008 por N. Bachman | 1900-01-01 a 2050-12-31 23:58:51 (cobertura leída del BPC: 1899-12-31T23:59:19 a 2050-12-31T23:58:51 UTC) | 1 770 496 | `656f9061…520cf` |
| `de421.bsp` | `.../spk/planets/a_old_versions/de421.bsp` | Efemérides planetarias JPL DE421 (Sol, Tierra, Luna). Publicado el 13/02/2008 por el grupo de Dinámica del Sistema Solar de JPL | 1899-07-28 a 2053-10-08 (leída del SPK, cuerpos 10, 301, 399) | 16 790 528 | `08b20db2…ecdb3` |

Hashes completos (la tabla abrevia el principio y el final):

```
08b20db2ae22488650641c5a9033e5bfda4b1c4b440cfeaf20f621cfa18ecdb3  de421.bsp
78732477b96f9863e7b0d65bcee3c22b8707ca5ed0db56d1173319cb2e8c7993  moon_080317.tf
52c622043ce0447d575e59ee01642f1894921e68c10f934ceff065f362da6c1c  moon_assoc_me.tf
656f90616403d75a75f0cd6c8830fc5b44f8cb4facb5ccb8915e752b397520cf  moon_pa_de421_1900-2050.bpc
678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b  naif0012.tls
3dff7b1dbeceaa01f25467767d3fa25816051c85d162d1edf04acb310ee28bb1  pck00011.tpc
```

Comprueba los tuyos con `Get-FileHash kernels\* -Algorithm SHA256`. Si NAIF publica una versión nueva de un kernel, el hash cambiará: no es necesariamente un error, pero conviene revisar `docs/science/luna-spice-sitios.md`.

## Cobertura temporal efectiva: 1900–2050

El límite lo pone el kernel de orientación lunar, no las efemérides: el SPK DE421 llega a 2053-10-08, pero el BPC termina el 2050-12-31 23:58:51. Fuera de ese rango SPICE lanza `SPICE(FRAMEDATANOTFOUND)`. LSI limita la interfaz a 1900-01-02 – 2050-12-30 (margen por tiempo luz, `config/simulation.json: time`) y traduce el fallo a un error claro. Fuera de rango existe `IAU_MOON` (con 4″–10″, ~35-85 m, de diferencia respecto a `MOON_ME` en 2026-2045), pero LSI no lo usa.

## Conjunto mínimo y marcos

Probado quitando cada kernel (`docs/science/luna-spice-sitios.md` §1): sin LSK falla `NOLEAPSECONDS`; sin FK, `UNKNOWNFRAME`; sin BPC, `FRAMEDATANOTFOUND`; sin SPK, `NOLOADEDFILES`. **No hacen falta** `pck00011.tpc` ni `moon_assoc_me.tf`; se cargan igualmente por ser inocuos.

El marco de trabajo es `MOON_ME` (media Tierra / eje polar), el de los DEM de PGDA. `MOON_PA` difiere 103,85″ (~0,87 km): no usarlo. Corrección de aberración `LT+S`.

## Reconocimiento

Se reconoce el uso de SPICE y de los recursos NAIF/PDS, como solicita NAIF. LSI no está afiliado ni respaldado por NASA, JPL ni NAIF.
