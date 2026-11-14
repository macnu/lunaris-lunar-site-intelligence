"""Tests de DemConfidence y DataConfidence con mallas sintéticas (valores esperados calculados a mano)."""
from types import SimpleNamespace

import numpy as np
import pytest

from lsi.analysis.confidence import data_confidence, dem_confidence, horizon_sigma_p90, support_confidence
from lsi.contracts import ConfidenceLevel as L, DemWindow, ScoreParams

PS = 5.0
N = 81                                   # 405 m de lado, centro en el píxel (40, 40)
HOR = lambda frac=0.0: SimpleNamespace(limited=np.arange(100) < frac * 100)  # noqa: E731
CFG = {"terrain": {"effective_resolution_m": 30.0, "dem_confidence": {"radius_m": 100.0}}}


def win(data):
    # centro del píxel [0,0] en (x0,y0); el punto (0,0) m cae en el píxel (40,40)
    return DemWindow(data=data.astype(float), x0_m=-40 * PS, y0_m=40 * PS, pixel_size_m=PS)


def ldec_every(step):
    """Un retorno cada ``step`` píxeles en ambas direcciones."""
    a = np.zeros((N, N))
    a[::step, ::step] = 1
    return a


def test_rejilla_densa_y_error_bajo_es_alta():
    # retornos cada 2 px (10 m): distancia máx. al retorno ~7,1 m -> g90 <= 10 m
    r = dem_confidence(win(ldec_every(2)), win(np.full((N, N), 0.3)), 0.0, 0.0, HOR(), CFG)
    assert r.level == L.HIGH and r.g90_m <= 10.0 + 1e-9 and r.e90_m == pytest.approx(0.3)
    assert r.dc == pytest.approx(1.0)                   # g90<=10 y e90<=0,4
    assert r.f_obs == pytest.approx(0.25, abs=0.06)
    assert r.radius_m == 100.0 and r.effective_resolution_m == 30.0 and r.open_azimuth_fraction == 0.0


def test_dc_continuo_valor_a_mano():
    # un solo retorno en el centro: g90 = p90 de la distancia al centro dentro del disco R=100 m
    a = np.zeros((N, N)); a[40, 40] = 1
    r = dem_confidence(win(a), win(np.full((N, N), 0.95)), 0.0, 0.0, HOR(), CFG)
    assert 60 < r.g90_m <= 100                           # disco de radio 100: p90 ≈ 95 m
    assert r.level == L.LOW
    # e90 = 0,95 -> (1,5-0,95)/1,1 = 0,5; g90 muy alto -> clip a 0 -> DC = 0
    assert r.dc == 0.0
    r2 = dem_confidence(win(ldec_every(2)), win(np.full((N, N), 0.95)), 0.0, 0.0, HOR(), CFG)
    assert r2.dc == pytest.approx(0.5)                  # g90<=10 -> 1; e90 0,95 -> 0,5
    assert r2.level == L.MEDIUM                          # e90 > 0,6 pero <= 1,0


def test_nunca_alta_con_g90_o_e90_malos():
    assert dem_confidence(win(ldec_every(2)), win(np.full((N, N), 1.2)), 0, 0, HOR(), CFG).level == L.LOW
    assert dem_confidence(win(ldec_every(8)), win(np.full((N, N), 0.2)), 0, 0, HOR(), CFG).level != L.HIGH


def test_azimutes_abiertos_bajan_un_nivel():
    args = (win(ldec_every(2)), win(np.full((N, N), 0.3)), 0.0, 0.0)
    assert dem_confidence(*args, HOR(0.10), CFG).level == L.HIGH       # 10 % no supera el umbral
    r = dem_confidence(*args, HOR(0.2), CFG)
    assert r.level == L.MEDIUM and r.open_azimuth_fraction == pytest.approx(0.2)
    low = dem_confidence(win(ldec_every(2)), win(np.full((N, N), 1.2)), 0, 0, HOR(0.5), CFG)
    assert low.level == L.LOW                                            # no baja de BAJA


def test_sin_retornos_ni_error_es_baja_sin_inventar():
    r = dem_confidence(win(np.zeros((N, N))), win(np.full((N, N), np.nan)), 0, 0, HOR(), CFG)
    assert r.level == L.LOW and r.dc == 0.0 and np.isnan(r.e90_m) and np.isinf(r.g90_m)


def test_cfg_acepta_solo_el_bloque_y_umbrales_editables():
    args = (win(ldec_every(2)), win(np.full((N, N), 0.3)), 0.0, 0.0, HOR())
    assert dem_confidence(*args, {"e90_high_m": 0.2}).level == L.MEDIUM   # umbral venido de config
    assert dem_confidence(*args, {"radius_m": 50.0}).radius_m == 50.0


def test_errores_de_geometria():
    with pytest.raises(ValueError):
        dem_confidence(win(np.zeros((N, N))), win(np.zeros((N - 1, N - 1))), 0, 0, HOR(), CFG)
    with pytest.raises(ValueError):
        dem_confidence(win(np.zeros((N, N))), win(np.zeros((N, N))), 1e6, 1e6, HOR(), CFG)


# ---- DataConfidence (§7.5) ------------------------------------------------------------
P = ScoreParams()


@pytest.mark.parametrize("c,nivel", [(0.75, L.HIGH), (0.7499, L.MEDIUM), (0.5, L.MEDIUM), (0.4999, L.LOW)])
def test_data_confidence_umbrales(c, nivel):
    r = data_confidence(1.0, 1.0, c, None, P)
    assert r.level == nivel and r.c == pytest.approx(c)


def test_data_confidence_es_el_minimo():
    r = data_confidence(0.9, 0.35, 0.8, None, P)         # c_sup calibrado (min de gap/err/hz) manda aquí
    assert (r.c, r.c_cov, r.c_sup, r.c_range, r.level) == (0.35, 0.9, 0.35, 0.8, L.LOW)


def test_data_confidence_recorta_y_rechaza_nan():
    assert data_confidence(1.5, 2.0, 1.0, None, P).c == 1.0
    with pytest.raises(ValueError):
        data_confidence(float("nan"), 1.0, 1.0, None, P)


def test_data_confidence_umbrales_de_params():
    assert data_confidence(0.6, 1, 1, None, ScoreParams(conf_high=0.6)).level == L.HIGH


# ---- c_sup calibrada (revision-geologica §2): c_sup = min(c_gap, c_err, c_hz) ------------------
def _dem(g90, e90):
    """Stand-in de DemConfidence con g90/e90 medidos: ``dc`` = min(c_gap, c_err), anclajes 10-40 m y 0,4-1,5 m (a mano)."""
    clip = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    return SimpleNamespace(dc=min(clip((40.0 - g90) / 30.0), clip((1.5 - e90) / 1.1)))


def test_horizon_sigma_p90_valor_a_mano():
    # |H+ - H-|/2 = 0,01·k para k = 0..99 (°): p90 de 0..0,99 con interpolación lineal = 0,891
    k = np.arange(100)
    assert horizon_sigma_p90(0.02 * k, 0.0 * k) == pytest.approx(0.891, abs=1e-9)
    assert horizon_sigma_p90(np.full(10, 1.0), np.full(10, 1.0)) == 0.0
    assert np.isnan(horizon_sigma_p90(np.array([0.0, np.nan]), np.array([0.0, 0.0])))
    with pytest.raises(ValueError):
        horizon_sigma_p90(np.zeros(3), np.zeros(4))


@pytest.mark.parametrize("g90,e90,sh,c,c_hz,nivel", [
    (11.2, 0.353, 0.074, 0.96, 1.0, L.HIGH),            # Site04 TOP-1 medido (revision-geologica §2): alta
    (15.8, 0.59, 0.243, 0.6425, 0.6425, L.MEDIUM),      # Site11 R2: limita el horizonte: (0,5-0,243)/0,4
    (18.0, 0.78, 0.476, 0.06, 0.06, L.LOW),             # Malapert 2: horizonte inestable pese a buena cobertura
    (25.0, 1.0, 0.712, 0.0, 0.0, L.LOW),                # σh90 > 0,5° → c_hz = 0
])
def test_support_confidence_valores_a_mano(g90, e90, sh, c, c_hz, nivel):
    c_sup, hz = support_confidence(_dem(g90, e90), sh)
    assert hz == pytest.approx(c_hz, abs=1e-9)
    assert c_sup == pytest.approx(c, abs=2e-3)
    assert data_confidence(1.0, c_sup, 1.0, None, P).level == nivel   # umbrales 0,75/0,5 de siempre


def test_support_confidence_sin_dato_es_cero_nunca_plausible():
    assert support_confidence(None, 0.05) == (0.0, 0.0)                    # sin DEM / sin toterr
    assert support_confidence(_dem(11.2, 0.35), float("nan")) == (0.0, 0.0)   # horizonte no medible


def test_support_confidence_discrimina_a_diferencia_de_la_fraccion_observada():
    # la fracción de píxeles observados es ~constante (≈ 9 %): con ella C ≤ 0,17 siempre → siempre «baja».
    # El nuevo c_sup recorre las tres etiquetas con entradas físicas razonables.
    niveles = {data_confidence(1.0, support_confidence(_dem(g, e), sh)[0], 1.0, None, P).level
               for g, e, sh in [(11.2, 0.35, 0.05), (15.8, 0.8, 0.25), (30.0, 1.4, 0.45)]}
    assert niveles == {L.HIGH, L.MEDIUM, L.LOW}
