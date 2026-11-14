"""Tests de astronomy.spice_engine: contraste con Horizons (24 casos de luna-spice-sitios.md §2)."""
import re
import threading
from pathlib import Path

import numpy as np
import pytest

from lsi.contracts import Body, DateOutOfRangeError, KernelsMissingError, MOON_RADIUS_KM

pytestmark = pytest.mark.needs_spice

DOC = Path(__file__).resolve().parents[1] / "docs" / "science" / "luna-spice-sitios.md"


@pytest.fixture(scope="module")
def eng():
    from lsi.astronomy import spice_engine
    spice_engine.load_kernels()
    return spice_engine


def _horizons_cases():
    row = re.compile(r"^\| (-?[\d.]+), (-?[\d.]+) \| (\d{4}-\d\d-\d\d) (\d\d:\d\d) \| (Sol|Tierra) \| "
                     r"([\d.]+) \| (-?[\d.]+) \|")
    out = []
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = row.match(line)
        if m:
            la, lo, d, t, b, az, el = m.groups()
            out.append((float(la), float(lo), f"{d} {t}:00", Body.SUN if b == "Sol" else Body.EARTH,
                        float(az), float(el)))
    return out


CASES = _horizons_cases()


def test_hay_24_casos():
    assert len(CASES) == 24


@pytest.mark.parametrize("la,lo,utc,body,az_h,el_h", CASES)
def test_horizons(eng, la, lo, utc, body, az_h, el_h):
    t = eng.body_track(eng.utc_to_et(utc), la, lo, body)
    assert abs(t.el_deg[0] - el_h) < 0.001
    daz = (t.az_deg[0] - az_h + 180) % 360 - 180
    assert abs(daz) < (0.02 if el_h > 80 else 0.002)


def test_spkcpo_independiente(eng):
    """Snippet verificado (spkcpo + ENU local) como referencia independiente del camino vectorizado."""
    import spiceypy as sp
    lat, lon = -89.7, 129.0
    et = eng.utc_to_et("2026-11-14 00:00:00")
    obs = sp.georec(np.radians(lon), np.radians(lat), 0.0, MOON_RADIUS_KM, 0.0)
    with eng.SPICE_LOCK:
        st, _ = sp.spkcpo("SUN", et, "MOON_ME", "OBSERVER", "LT+S", obs, "MOON", "MOON_ME")
    v = np.array(st[:3])
    la, lo = np.radians(lat), np.radians(lon)
    E = np.array([-np.sin(lo), np.cos(lo), 0])
    N = np.array([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo), np.cos(la)])
    U = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    t = eng.body_track(et, lat, lon, Body.SUN)
    assert abs(t.az_deg[0] - np.degrees(np.arctan2(v @ E, v @ N)) % 360) < 1e-6
    assert abs(t.el_deg[0] - np.degrees(np.arcsin(v @ U / np.linalg.norm(v)))) < 1e-6
    assert abs(t.dist_km[0] - np.linalg.norm(v)) < 1e-3


def test_vectorizado_igual_escalar(eng):
    et = eng.et_grid(eng.utc_to_et("2026-11-14 00:00:00"), eng.utc_to_et("2026-11-15 00:00:00"), 3600.0)
    assert len(et) == 25
    for b in (Body.SUN, Body.EARTH):
        v = eng.body_track(et, -86.0, 0.0, b)
        for i in (0, 7, 24):
            s = eng.body_track(float(et[i]), -86.0, 0.0, b)
            assert (v.az_deg[i], v.el_deg[i], v.dist_km[i], v.radius_deg[i]) == (
                s.az_deg[0], s.el_deg[0], s.dist_km[0], s.radius_deg[0])


def test_determinista(eng):
    et = np.linspace(eng.utc_to_et("2027-01-01 00:00:00"), eng.utc_to_et("2027-01-02 00:00:00"), 50)
    a, b = eng.sky_series(et, -89.9, 10.0), eng.sky_series(et, -89.9, 10.0)
    assert np.array_equal(a.sun.el_deg, b.sun.el_deg) and a.kernel_hash == b.kernel_hash != ""


def test_continuidad_temporal(eng):
    et = eng.et_grid(eng.utc_to_et("2026-11-14 00:00:00"), eng.utc_to_et("2026-11-16 00:00:00"), 600.0)
    for b in (Body.SUN, Body.EARTH):
        t = eng.body_track(et, -89.7, 129.0, b)
        assert np.abs(np.diff(t.el_deg)).max() < 0.1   # <0.1 deg en 10 min en el polo
        assert np.abs(np.diff(t.dist_km)).max() < 2000
        assert np.all((t.az_deg >= 0) & (t.az_deg < 360))


def test_radio_angular(eng):
    t = eng.body_track(eng.utc_to_et("2026-11-14 00:00:00"), -89.9, 0.0, Body.SUN)
    assert 0.5228 / 2 - 0.0005 < t.radius_deg[0] < 0.5434 / 2 + 0.0005
    e = eng.body_track(eng.utc_to_et("2026-11-14 00:00:00"), -89.9, 0.0, Body.EARTH)
    assert 1.797 / 2 - 0.005 < e.radius_deg[0] < 2.050 / 2 + 0.005


def test_elevacion_sol_polo_un_anio(eng):
    et = eng.et_grid(eng.utc_to_et("2026-01-01 00:00:00"), eng.utc_to_et("2027-12-31 00:00:00"), 3600.0)
    el = eng.body_track(et, -89.9, 0.0, Body.SUN).el_deg
    assert abs(el.min() + 1.625) < 0.01 and abs(el.max() - 1.627) < 0.01


@pytest.mark.parametrize("utc", ["1899-12-31 00:00:00", "2050-12-31 23:59:00", "2051-06-01 00:00:00"])
def test_fuera_de_rango_utc(eng, utc):
    with pytest.raises(DateOutOfRangeError):
        eng.utc_to_et(utc)


def test_fuera_de_rango_et(eng):
    for et in (-3.2e9, 1.62e9, float("nan")):
        with pytest.raises(DateOutOfRangeError):
            eng.body_track(et, -89.9, 0.0, Body.SUN)


def test_limites_validos(eng):
    for utc in ("1900-01-02 00:00:00", "2050-12-30 00:00:00"):
        assert np.isfinite(eng.body_track(eng.utc_to_et(utc), -89.9, 0.0, Body.SUN).el_deg[0])


def test_kernels_faltantes(eng, tmp_path):
    with pytest.raises(KernelsMissingError):
        eng.load_kernels(tmp_path)


def test_et_utc_roundtrip(eng):
    assert eng.et_to_utc(eng.utc_to_et("2026-11-14T00:00:00")) == "2026-11-14T00:00:00"


def test_threads(eng):
    et = eng.utc_to_et("2026-11-14 00:00:00")
    ref = eng.body_track(et, -89.7, 129.0, Body.EARTH).el_deg[0]
    res, errs = [], []

    def work():
        try:
            for _ in range(20):
                res.append(eng.body_track(et, -89.7, 129.0, Body.EARTH).el_deg[0])
        except Exception as e:  # pragma: no cover
            errs.append(e)

    ths = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert not errs and len(res) == 160 and set(res) == {ref}
    assert not eng.SPICE_LOCK.locked()
