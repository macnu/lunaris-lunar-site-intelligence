"""Sombras del relieve (``terrain.shadows``): valores esperados por geometría, independientes del código."""
import numpy as np
import pytest

from lsi.astronomy.coordinates import stereo_forward
from lsi.terrain import shadows as SH

PX = 10.0


def ridge(h=100.0, ncol=200, nrow=5, at=100):
    """Acantilado: meseta de altura h desde la columna ``at`` hacia el este (un muro, no una cresta de 1 píxel: el paso radial
    del barrido es el 3 % de la distancia y una cresta más fina que eso puede pasar entre dos muestras)."""
    z = np.zeros((nrow, ncol))
    z[:, at:] = h
    return z


def test_terreno_plano_sin_sombra_con_el_sol_sobre_el_horizonte():
    z = np.full((30, 40), 1234.0)
    for el in (0.5, 5.0, 45.0):
        assert not SH.shadow_mask(z, PX, 90.0, el).any()
    assert SH.illumination(z, PX, 90.0, 5.0).min() == 1.0


def test_cresta_proyecta_sombra_de_longitud_h_sobre_tan_el():
    h, el = 100.0, 10.0
    z = ridge(h)                                    # cresta en la columna 100; Sol al este (az de rejilla 90°) ⇒ sombra al oeste
    m = SH.shadow_mask(z, PX, 90.0, el)
    n_shadow = int(m[2, :100].sum())                # celdas al pie del muro (oeste); la meseta queda iluminada
    esperada = h / np.tan(np.radians(el))           # 567,1 m = 56,7 celdas
    assert abs(n_shadow * PX - esperada) <= 2 * PX
    assert not m[2, 100:].any()
    assert m[2, 100 - 5:100].all() and not m[2, :100 - 60].any()
    # con el Sol al oeste el muro (a su este) queda de cara al Sol: sin sombra; el muro espejado proyecta hacia el este
    assert not SH.shadow_mask(z, PX, 270.0, el).any()
    m2 = SH.shadow_mask(z[:, ::-1], PX, 270.0, el)
    assert abs(int(m2[2, 100:].sum()) * PX - esperada) <= 2 * PX


def test_sol_bajo_el_horizonte_todo_en_sombra_y_nan_tolerado():
    z = np.full((10, 10), 50.0)
    assert SH.shadow_mask(z, PX, 0.0, -3.0).all()
    assert SH.illumination(z, PX, 0.0, -3.0).max() == 0.0
    z[3, 3] = np.nan
    m = SH.shadow_mask(z, PX, 45.0, 2.0)
    assert not m.any()                                # el hueco no tapa ni se marca
    assert np.isnan(SH.illumination(z, PX, 45.0, 2.0)[3, 3])
    assert not SH.shadow_mask(np.full((4, 4), np.nan), PX, 0.0, 5.0).any()


def test_determinista():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 30, (40, 40))
    assert np.array_equal(SH.shadow_mask(z, PX, 33.0, 3.0), SH.shadow_mask(z.copy(), PX, 33.0, 3.0))


def test_la_curvatura_lunar_esconde_una_cresta_lejana():
    # Meseta de 40 m con el Sol a 0,1° (al este). Celda a 10 km: la meseta sube 40 − s²/2R = 40 − 28,8 = 11 m sobre su horizonte
    # (0,063° < 0,1°) y no sombrea; sobre una esfera de radio enorme (sin curvatura) 40 m / 10 km = 0,23° sí. A 20 km, igual.
    z = np.zeros((3, 400))
    z[:, 200:] = 40.0
    luna = SH.shadow_mask(z, 100.0, 90.0, 0.1)
    plana = SH.shadow_mask(z, 100.0, 90.0, 0.1, sphere_radius_m=1e12)
    for col in (100, 0):
        assert not luna[1, col] and plana[1, col]


def test_con_origen_la_direccion_sigue_la_longitud_local_cerca_del_polo():
    # Polo sur, recorte de 2 km centrado en (x, y) = (0, 5 km): el norte local es «hacia fuera del polo» (+y). Con el Sol
    # al NORTE (az 0°) el rayo en el centro apunta a +y (fila decreciente). Cresta E-O de 60 m en la fila 30.
    n, px = 60, 40.0
    x0, y0 = -n / 2 * px, 5000.0 + n / 2 * px
    z = np.zeros((n, n))
    z[30, :] = 60.0
    m = SH.shadow_mask(z, px, 0.0, 3.0, origin_xy_m=(x0, y0))
    esperada = 60.0 / np.tan(np.radians(3.0)) / px          # ≈ 28,6 celdas hacia el sur (filas mayores) del lado opuesto al Sol
    assert 24 <= int(m[31:, 30].sum()) <= 33 and abs(int(m[31:, 30].sum()) - esperada) <= 4
    assert not m[:30, 30].any()


def test_azimut_de_rejilla_casi_constante_en_el_recorte_junto_al_polo():
    # Un Sol lejano tiene el MISMO azimut de rejilla (λ+A) en todo el recorte aunque el norte local gire con la longitud:
    # a ≈ 10 km del polo el azimut LOCAL cambia ≈ 30° entre bordes del recorte de 6 km, el de rejilla < 1°.
    from lsi.astronomy.coordinates import stereo_inverse
    from lsi.terrain.shadows import _sun_field
    x, y = (float(v) for v in stereo_forward(-89.67, 129.78))
    n, px = 150, 40.0
    x0, y0 = x - n / 2 * px, y + n / 2 * px
    d_col, d_row, el = _sun_field((n, n), px, 120.0, 1.5, (x0, y0))
    grid = np.degrees(np.arctan2(d_col, -d_row))
    spread = float(np.ptp(((grid - grid[n // 2, n // 2] + 180) % 360) - 180))
    assert spread < 1.0
    assert abs(np.degrees(el) - 1.5).max() < 0.4 and np.isfinite(el).all()          # la elevación cambia ≤ 0,3° por la curvatura
    xs = x0 + px * np.arange(n)
    lon = stereo_inverse(xs, np.full(n, y0))[1]
    assert np.ptp(((lon - lon[n // 2] + 180) % 360) - 180) > 15          # ≈ 18°: la longitud (norte local) sí gira mucho


def test_sun_seen_from_identidad_y_cambio_de_longitud_en_el_polo():
    assert SH.sun_seen_from(123.0, 2.5, -86.0, 10.0, -86.0, 10.0) == pytest.approx((123.0, 2.5), abs=1e-9)
    # junto al polo, 30° de longitud más al este giran el azimut local ≈ −30° (el azimut de rejilla λ+A se conserva) y apenas la elevación
    az, el = SH.sun_seen_from(100.0, 2.0, -89.9, 0.0, -89.9, 30.0)
    assert az == pytest.approx(70.0, abs=0.5) and el == pytest.approx(2.0, abs=0.1)
