"""Terreno de contexto y parche fino del visor 3D (src/lsi/data/viewer_context.py): alturas finitas, solape sin hueco,
sombra determinista y payload acotado. Valores esperados independientes (planos y rampas conocidos)."""
import json
from pathlib import Path

import numpy as np
import pytest

from lsi.data import viewer_context as VC

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
needs_far = pytest.mark.skipif(not list(RAW.glob("*/LDEM_80S_80MPP_ADJ.TIF")), reason="falta el DEM polar de 80 m")


def _crop(z=-500.0, n=100, px=12.0, x0=5000.0, y0=122000.0):
    return dict(heights=np.full((n, n), z), x0_m=x0, y0_m=y0, px_m=px)


def _ctx(crop=None, el=1.0):
    crop = crop or _crop()
    c = (crop["x0_m"] + 49.5 * crop["px_m"], crop["y0_m"] - 49.5 * crop["px_m"])
    return VC.context_terrain(RAW, c, 20000.0, crop, dict(az_deg=95.0, el_deg=el, lat=-85.98, lon_deg_e=2.6)), crop


@needs_far
def test_contexto_finito_acotado_y_determinista():
    a, _ = _ctx()
    b, _ = _ctx()
    assert a["heights"].shape == (VC.CTX_N, VC.CTX_N) and VC.CTX_N <= 448
    assert np.isfinite(a["heights"]).all() and np.isfinite(a["lit"]).all()
    assert 0.0 <= a["lit"].min() and a["lit"].max() <= 1.0
    assert np.array_equal(a["lit"], b["lit"]) and np.array_equal(a["heights"], b["heights"])       # sombra determinista
    n = len(json.dumps(VC.context_payload(a)))
    assert n < VC.MAX_EXTRA_BYTES * 0.6                                                              # contexto < 1,5 MB


@needs_far
def test_contexto_sin_hueco_con_el_recorte():
    a, crop = _ctx()
    n, st = a["n"], a["step_m"]
    xs = a["x0_m"] + st * np.arange(n)
    ys = a["y0_m"] - st * np.arange(n)
    gx, gy = np.meshgrid(xs, ys)
    inside = (gx >= crop["x0_m"]) & (gx <= crop["x0_m"] + 99 * 12.0) & (gy <= crop["y0_m"]) & (gy >= crop["y0_m"] - 99 * 12.0)
    assert inside.sum() > 4
    assert np.allclose(a["heights"][inside], -500.0, atol=1e-3)            # dentro: las alturas del recorte (plano de -500 m)
    ring = (np.hypot(gx - np.clip(gx, crop["x0_m"], crop["x0_m"] + 1188), gy - np.clip(gy, crop["y0_m"] - 1188, crop["y0_m"])) > VC.FEATHER_M)
    assert not np.allclose(a["heights"][ring], -500.0)                      # lejos del recorte vuelve el DEM de 80 m
    d = np.abs(np.diff(a["heights"], axis=1))
    assert np.nanmax(d[~inside[:, 1:]]) < 2500.0                            # sin escalón brusco en la mezcla (≤ pendiente del DEM)


@needs_far
def test_sol_bajo_el_horizonte_todo_a_oscuras():
    a, _ = _ctx(el=-5.0)
    assert a["lit"].max() == pytest.approx(0.0, abs=1e-6)


def test_parche_fino_bicubico_conserva_rampa_y_rango():
    z = 100.0 + 0.2 * np.arange(200)[None, :] * 5.0 + 0.1 * np.arange(200)[:, None] * 5.0      # rampa plana: la bicúbica la reproduce exacta
    p = VC.fine_patch(z, 0.0, 995.0, 5.0, (500.0, 500.0))
    assert p["n"] % 2 == 1 and p["step_m"] == 2.5 and abs(p["n"] * 2.5 - 700.0) < 6
    h = p["heights"]
    assert np.isfinite(h).all()
    c = p["n"] // 2
    assert h[c, c] == pytest.approx(100.0 + 0.2 * 500.0 + 0.1 * (995.0 - 500.0), abs=1e-3)
    assert h[c, c + 2] - h[c, c] == pytest.approx(0.2 * 5.0, abs=1e-3)                          # pendiente esperada en x (0,2 m/m · 5 m)
    assert h.min() >= z.min() and h.max() <= z.max()
    n = len(json.dumps(VC.patch_payload(p)))
    assert n < 400_000


def test_parche_sin_datos_devuelve_none():
    z = np.full((200, 200), np.nan)
    assert VC.fine_patch(z, 0.0, 995.0, 5.0, (500.0, 500.0)) is None
    assert VC.fine_patch(np.ones((10, 10)), 0.0, 45.0, 5.0, (500.0, 500.0)) is None            # ventana que no cubre el parche


def test_contexto_half_acotado():
    assert VC.context_half_m(3000.0) == 20000.0 and VC.context_half_m(10500.0) == pytest.approx(23100.0)
    assert VC.context_half_m(50000.0) == 25000.0


def test_psr_pct_sin_celdas_sin_foto_es_none():
    assert VC.psr_nophoto_pct(0.0, 0.0, 10.0, (4, 4), np.zeros((4, 4), bool)) is None
