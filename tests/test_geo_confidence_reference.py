"""Referencia de la confianza de datos calibrada (docs/validation/revision-geologica.md §2). No toca src/.

C = min(c_gap, c_err, c_hz); etiqueta con los umbrales ya vigentes (conf_high 0.75, conf_medium 0.5).
Valores esperados calculados a mano de las fórmulas del documento, no de la función.
"""
import numpy as np
from scipy.ndimage import distance_transform_edt


def _clip01(v):
    return min(1.0, max(0.0, v))


def disk_g90_e90(ldec, toterr, row, col, r_px=20, px_m=5.0):
    """(g90 m, e90 m) en el disco: p90 de la distancia al retorno LOLA más cercano y p90 de toterr."""
    obs = np.nan_to_num(ldec, nan=0.0) > 0
    if not obs.any():
        return float("inf"), float(np.nanpercentile(toterr, 90))
    dist = distance_transform_edt(~obs) * px_m
    yy, xx = np.mgrid[:ldec.shape[0], :ldec.shape[1]]
    disk = (yy - row) ** 2 + (xx - col) ** 2 <= r_px ** 2
    return float(np.percentile(dist[disk], 90)), float(np.nanpercentile(toterr[disk], 90))


def geo_confidence(g90_m, e90_m, sigma_h90_deg, high=0.75, medium=0.5):
    """sigma_h90_deg = p90 sobre azimuts de |h(z+σ)-h(z-σ)|/2 (toterr, k=1). Devuelve (C, etiqueta, partes)."""
    if not (np.isfinite(g90_m) and np.isfinite(e90_m) and np.isfinite(sigma_h90_deg)):
        return 0.0, "baja", (0.0, 0.0, 0.0)          # sin dato: nunca un valor plausible
    parts = (_clip01((40.0 - g90_m) / 30.0), _clip01((1.5 - e90_m) / 1.1), _clip01((0.5 - sigma_h90_deg) / 0.4))
    c = min(parts)
    return c, ("alta" if c >= high else "media" if c >= medium else "baja"), parts


def test_medidos_shackleton_top1_alta():          # g90 11.2 m, e90 0.353 m, σh90 0.074°
    c, lab, p = geo_confidence(11.2, 0.353, 0.074)
    assert lab == "alta" and abs(p[0] - 0.96) < 1e-9 and p[1] == 1.0 and p[2] == 1.0 and abs(c - 0.96) < 1e-9


def test_medidos_malapert_r5_baja():              # g90 25 m, e90 1.0 m, σh90 0.712° (horizonte inestable)
    c, lab, p = geo_confidence(25.0, 1.0, 0.712)
    assert lab == "baja" and c == 0.0 and abs(p[0] - 0.5) < 1e-9 and abs(p[1] - 0.4545454545) < 1e-9


def test_medidos_intermedio_media():              # Site11 rank 2: limita el horizonte (0.243° -> 0.6425)
    c, lab, _ = geo_confidence(15.8, 0.59, 0.243)
    assert lab == "media" and abs(c - 0.6425) < 1e-9


def test_sin_dato_es_baja():
    assert geo_confidence(float("inf"), 0.4, 0.05)[1] == "baja"


def test_ventana_sintetica():
    n = 81
    full = np.ones((n, n)); te = np.full((n, n), 0.4)
    assert disk_g90_e90(full, te, 40, 40) == (0.0, 0.4)           # todo observado: distancia 0
    one = np.zeros((n, n)); one[40, 40] = 1                       # un solo retorno en el centro
    g90, e90 = disk_g90_e90(one, te, 40, 40, r_px=10)
    assert 0 < g90 <= 50.0 and e90 == 0.4                         # p90 de distancias en disco de 10 px (≤ 50 m)
    assert disk_g90_e90(np.zeros((n, n)), te, 40, 40)[0] == float("inf")
