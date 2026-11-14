"""T62: el motor frente a valores PUBLICADOS (Barker et al. 2021, Table 2) en el borde Shackleton-de Gerlache.

Fuente leída (PDF completo, texto extraído): Barker, M.K. et al. 2021, Planetary and Space Science 203, 105119,
https://ntrs.nasa.gov/api/citations/20205009660/downloads/Mike%20Barker_%20Paper_%20Improved%20Lola.pdf
Definiciones del artículo: periodo 2024-01-01 a 2026-01-01, paso 1 h, altura z=1 m y 5 m, iluminación media = fracción
visible del DISCO del Sol (disco finito) promediada en el tiempo; LCIP = periodo continuo más largo con CUALQUIER parte del
Sol; LCSP = periodo continuo más largo sin NINGUNA parte del Sol. Table 2 da, para 100 «clones» del DEM con errores, el
percentil 1 (iluminación, LCIP) o 99 (LCSP) → son cotas PESIMISTAS del DEM nominal que usa el motor (el propio artículo:
«the new (non-clone) LDEM tends to be better than the mean/median of the clones»). Por eso se afirman solo cotas.
Los centroides de las 7 RoI son (X, Y) estereográficos polares en metros de Table 2 (mismo marco que los GeoTIFF).

Necesita el DEM Site01 (no está en data/raw para no alterar el resto de la suite). Descarga reproducible, con tamaño, comprobación
de que no es HTML y SHA-256 en data/validation_raw/manifest.json (164 MB: surf, slp, ldec, toterr):
  python scripts/fetch_validation_data.py          # solo consulta tamaños (HEAD)
  python scripts/fetch_validation_data.py --yes    # descarga
y LSI_SITE01_DIR=<dir> si no es el defecto data/validation_raw/site01. Sin él, se omiten (ejecutado 14/11/2026: 38 passed).
"""
import os
from pathlib import Path

import pytest

from lsi import pipeline as P
from lsi.astronomy.coordinates import stereo_inverse
from lsi.contracts import AnalysisRequest
from lsi.data import loader

pytestmark = [pytest.mark.needs_spice, pytest.mark.needs_dem, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[1]
SITE01_DIR = Path(os.environ.get("LSI_SITE01_DIR", ROOT / "data" / "validation_raw" / "site01"))
START, END = "2024-01-01T00:00:00", "2026-01-01T00:00:00"

# RoI: (X_m, Y_m) y valores de Table 2 (caso A: percentil sobre el promedio de la RoI de cada clon)
ROI_XY = {1: (-11582.5, -12462.5), 2: (-11487.5, -12557.5), 3: (-11352.5, -12502.5), 4: (-11287.5, -12167.5),
          5: (-11102.5, -11942.5), 6: (-10802.5, -11737.5), 7: (-10227.5, -11552.5)}
LCSP99_1M = {1: 16.55, 2: 17.84, 3: 22.23, 4: 13.27, 5: 15.24, 6: 12.74, 7: 14.54}         # días, z=1 m
AVG1_5M = {1: 89.26, 2: 88.51, 3: 84.53, 4: 88.12, 5: 85.71, 6: 87.35, 7: 82.79}          # %, z=5 m
LCIP1_5M = {1: 215.79, 2: 216.28, 3: 216.89, 4: 231.20, 5: 218.98, 6: 220.98, 7: 119.07}   # días, z=5 m
LCSP99_5M = {1: 5.29, 2: 7.31, 3: 8.41, 4: 4.00, 5: 4.52, 6: 4.16, 7: 5.42}                # días, z=5 m


@pytest.fixture(scope="module")
def runs():
    if not list(SITE01_DIR.glob("Site01_final_adj_5mpp_surf.tif")):
        pytest.skip(f"falta el DEM Site01 en {SITE01_DIR} (ver docstring)")
    ctx = P.build_context(ROOT)
    ctx.dem_refs = {**ctx.dem_refs, **loader.discover_dems(SITE01_DIR.parent)}
    out = {}
    for k, (x, y) in ROI_XY.items():
        lat, lon = stereo_inverse(x, y)
        for z in (1.0, 5.0):
            req = AnalysisRequest(float(lat), float(lon), START, END, observer_height_m=z, step_s=840.0, snap_to_dem=False)
            out[(k, z)] = P.run_analysis(ctx, req).metrics
    return out


@pytest.mark.parametrize("k", ROI_XY)
def test_roi_mean_illumination_1m_above_70pct(runs, k):
    # Barker define las RoI como píxeles con iluminación media > 70 % a z=1 m (Table 2, 1.er percentil de clones 67-71 %).
    assert runs[(k, 1.0)].effective_illumination >= 0.70


@pytest.mark.parametrize("k", ROI_XY)
def test_roi_mean_illumination_5m_not_below_published_p1(runs, k):
    assert runs[(k, 5.0)].effective_illumination * 100 >= AVG1_5M[k] - 1.0   # -1 punto: centroide vs promedio de RoI


@pytest.mark.parametrize("k", ROI_XY)
def test_roi_longest_sun_5m_not_below_published_p1(runs, k):
    assert runs[(k, 5.0)].longest_sun_window_s / 86400 >= 0.9 * LCIP1_5M[k]


def test_roi7_is_the_short_one_like_in_the_paper(runs):
    # RoI 7 (pico aislado) tiene la ventana de Sol más corta en la publicación (119 d frente a 216-231 d) y en el motor
    s = {k: runs[(k, 5.0)].longest_sun_window_s / 86400 for k in ROI_XY}
    assert s[7] == min(s.values()) and 0.8 * 119.07 <= s[7] <= 1.5 * 119.07


@pytest.mark.parametrize("k", ROI_XY)
def test_roi_longest_night_5m_within_published_p99(runs, k):
    d = runs[(k, 5.0)].max_darkness_s / 86400
    assert 3.0 <= d <= LCSP99_5M[k] * 1.1   # cota inferior: caso C (píxel óptimo) 3.1-5.5 d


@pytest.mark.parametrize("k", ROI_XY)
def test_roi_longest_night_1m_within_published_p99(runs, k):
    d = runs[(k, 1.0)].max_darkness_s / 86400
    assert 3.0 <= d <= LCSP99_1M[k] * 1.1


# ---------------------------------------------------------------------------------------------------------------
# Gläser et al. 2014, Icarus 243, 78-90 (resumen leído en https://elib.dlr.de/94240/, doi 10.1016/j.icarus.2014.08.013):
# Connecting Ridge, 19 años (ciclo de precesión) a 2 m: «locations receiving sunlight for 92.27% of the time at 2 m
# above ground ... the longest continuous periods in darkness are typically only 3-5 days». Son los MEJORES puntos de la
# cresta (DTM de 20 m); las RoI de Barker (5 m) son puntos de la misma cresta, no los mismos píxeles → tolerancia de
# ±3 puntos en la fracción y 3-5,5 d de noche. f_sun del motor = fracción de tiempo con CUALQUIER parte del Sol.
@pytest.mark.parametrize("k", [4, 6])
def test_connecting_ridge_19yr_2m_vs_glaser_2014(k):
    if not list(SITE01_DIR.glob("Site01_final_adj_5mpp_surf.tif")):
        pytest.skip(f"falta el DEM Site01 en {SITE01_DIR}")
    ctx = P.build_context(ROOT)
    ctx.dem_refs = {**ctx.dem_refs, **loader.discover_dems(SITE01_DIR.parent)}
    lat, lon = stereo_inverse(*ROI_XY[k])
    req = AnalysisRequest(float(lat), float(lon), "2024-01-01T00:00:00", "2043-01-01T00:00:00", observer_height_m=2.0,
                          step_s=840.0, snap_to_dem=False)
    m = P.run_analysis(ctx, req).metrics
    assert abs(m.solar_fraction - 0.9227) <= 0.03
    assert 3.0 <= m.max_darkness_s / 86400 <= 5.5
