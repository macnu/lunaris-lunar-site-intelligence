"""TDB-UTC: UNA fuente de verdad pura (``contracts.et_minus_utc_s``), reutilizada por export, theme y panels, y exacta al
segundo frente al LSK de SPICE (2010, 2017, 2026 y los cambios de segundo intercalar)."""
from datetime import datetime

import numpy as np
import pytest

from lsi import contracts as C
from lsi.analysis import export as ex
from lsi.energy import panels
from lsi.visualization import theme


@pytest.mark.parametrize("utc,expected", [
    (datetime(1900, 1, 2), 41.184), (datetime(1971, 12, 31), 41.184), (datetime(1972, 1, 2), 42.184),
    (datetime(2000, 1, 1, 12), 64.184), (datetime(2010, 6, 1), 66.184), (datetime(2016, 12, 31, 12), 68.184),
    (datetime(2017, 1, 2), 69.184), (datetime(2026, 11, 14, 12), 69.184), (datetime(2050, 12, 1), 69.184)])
def test_et_minus_utc_values(utc, expected):
    et = C.utc_datetime_to_et(utc)
    assert C.et_minus_utc_s(et) == pytest.approx(expected, abs=1e-9)
    assert C.et_to_utc_datetime(et) == utc                        # ida y vuelta exacta
    assert C.et_minus_utc_s(np.array([et, et]))[1] == pytest.approx(expected)


def test_leap_second_boundary_2016_12_31():
    """El salto de 2017-01-01: ET-UTC pasa de 68,184 a 69,184 justo en el segundo intercalar (23:59:60 no se representa)."""
    et = C.utc_datetime_to_et(datetime(2017, 1, 1))
    assert C.et_minus_utc_s(et - 2.0) == pytest.approx(68.184) and C.et_minus_utc_s(et + 2.0) == pytest.approx(69.184)


@pytest.mark.parametrize("utc", ["2010-06-01T00:00:00", "2016-12-31T23:30:00", "2017-01-01T00:30:00", "2026-11-14T12:00:00",
                                 "1990-03-04T05:06:07", "1960-01-01T00:00:00"])
@pytest.mark.needs_spice
def test_exact_against_spice_lsk(utc):
    from lsi.astronomy import spice_engine
    et = spice_engine.utc_to_et(utc)
    mine = C.utc_datetime_to_et(datetime.fromisoformat(utc))
    assert mine == pytest.approx(et, abs=0.01)                    # TDB-TT < 2 ms
    assert ex.et_to_utc_str(et) == utc + "Z"                      # export al segundo
    assert abs((theme.et_to_datetimes([et])[0] - datetime.fromisoformat(utc)).total_seconds()) < 0.01


@pytest.mark.parametrize("year", [2010, 2017, 2026])
def test_export_theme_and_panels_share_the_single_source(year):
    """Las tres consumidoras dan la misma respuesta (la de contracts) en 2010, 2017 y 2026."""
    utc = datetime(year, 5, 5, 6, 7, 8)
    et = C.utc_datetime_to_et(utc)
    assert theme.et_to_datetimes([et])[0] == utc
    assert ex.et_to_utc_str(et) == utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    day0 = C.utc_midnight_et(et)
    assert day0 == pytest.approx(C.utc_datetime_to_et(datetime(year, 5, 5)))
    assert et - day0 == pytest.approx(6 * 3600 + 7 * 60 + 8)
    # panels.summarize_power: origen de día por defecto = medianoche UTC real del primer instante (no 69,184 fijo)
    s = _series(np.array([et, et + 3600.0]))
    d = panels.summarize_power(s, _PANEL, 0.5, _CAT).daily
    assert d[0].day_start_et == pytest.approx(day0)


def _series(t):
    from lsi.contracts import MountingSpec, MountingType, PowerSeries
    z = np.ones(len(t))
    return PowerSeries(et=t, p_rel=z, f_sun=z, cos_inc=z, theta_deg=0 * z, iam=z, t_panel_k=300 * z, eta_rel=z, dist_factor=z,
                       t_clamped=np.zeros(len(t), bool), panel_id="x", mounting=MountingSpec(MountingType.TWO_AXIS))


_PANEL = C.PanelSpec(id="x", name="x", cell_technology="", mounting_default=C.MountingType.TWO_AXIS,
                     mounting_allowed=(C.MountingType.TWO_AXIS,), eta_bol=0.3, temp_coeff_per_k=-0.0025,
                     temp_valid_range_c=None, ref_temperature_c=25.0, alpha_front=0.9, emissivity_front=0.8,
                     emissivity_back=0.8, iam=C.IamSpec("cosine_only", None), cold_gain_cap=None, confidence={}, description="")
_CAT = C.PanelCatalog(panels=(_PANEL,), profiles={}, solar_constant_w_m2=1361.0, cold_gain_cap_default=1.15,
                      f_rad_default=1.0, f_dust_default=1.0, schema_version="t")
