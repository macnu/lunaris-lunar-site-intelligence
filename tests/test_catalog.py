import json
from pathlib import Path

import pytest

from lsi.contracts import ErrorCode, LSIError
from lsi.data import catalog

CFG_DIR = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="module")
def cfg():
    return catalog.load_simulation_config(CFG_DIR / "simulation.json")


def test_real_sites():
    sites = catalog.load_sites(CFG_DIR / "sites.json")
    by = {s.id: s for s in sites}
    assert len(sites) == len(by) == 36   # 32 + 4 regiones Artemis III solo de la lista de 2024 (sin coordenadas)
    assert by["site04"].dem_prefix == "Site04" and by["site04"].has_dem
    assert by["apollo11"].lat_deg == pytest.approx(0.6741)
    assert any(s.lat_deg is None for s in sites)  # null conservado


def test_params_from_real_config(cfg):
    h = catalog.horizon_params(cfg)
    assert (h.observer_height_m, h.az_step_deg, h.r_max_m, h.z_up_m) == (2.0, 0.25, 30000.0, None)
    assert catalog.horizon_params(cfg, 10.0).observer_height_m == 10.0
    assert catalog.visibility_params(cfg).n_slices == 64
    assert catalog.timeline_params(cfg).step_s == 600.0
    assert catalog.timeline_params(cfg, 300).step_s == 300.0
    assert catalog.uncertainty_params(cfg).k_sigma == 1.0
    s = catalog.score_params(cfg)
    assert (s.f0, s.f1, s.g2_max_slope_deg, s.conf_high) == (0.20, 0.90, 20.0, 0.75)
    pr = catalog.score_profiles(cfg)
    assert set(pr) == {"lander_solar_no_rhu", "lander_with_batteries", "lander_rhu", "rover", "base_isru",
                       "dte_comms", "custom"}
    assert pr["rover"].weights["terrain"] == 0.40 and pr["custom"].mission_profile_id is None
    assert pr["dte_comms"].uses_solar_gate is False
    assert (s.earth_floor, s.resolution_weight) == (0.25, 0.25) and pr["dte_comms"].earth_floor == 0.5
    assert pr["lander_rhu"].g4_na and pr["lander_rhu"].mission_profile_id == "lander_solar_no_rhu"
    with pytest.raises(Exception):
        h.r_max_m = 1  # frozen


def test_default_observer(cfg):
    assert catalog.default_observer(cfg, "Site11") == pytest.approx((-88.683418, 292.0679))
    assert catalog.default_observer(cfg, "SiteXX") is None


def _mut(cfg, tmp_path, fn):
    c = json.loads(json.dumps(cfg))
    fn(c)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(c))
    return p


@pytest.mark.parametrize("fn,frag", [
    (lambda c: c.pop("horizon"), "horizon"),
    (lambda c: c["horizon"].update(az_step_deg=0), "az_step_deg"),
    (lambda c: c["horizon"].update(r_max_m=1.0), "r_max_m"),
    (lambda c: c["visibility"].update(eps="x"), "eps"),
    (lambda c: c["timeline"].update(step_s=9999), "max_step_s"),
    (lambda c: c["score"].update(f0=0.95), "f0"),
    (lambda c: c["score"]["profiles"]["rover"]["weights"].pop("sun"), "rover"),
    (lambda c: c["observer"].update(height_m=500), "height_m"),
])
def test_invalid_config(cfg, tmp_path, fn, frag):
    with pytest.raises(LSIError, match=frag) as e:
        catalog.load_simulation_config(_mut(cfg, tmp_path, fn))
    assert e.value.code == ErrorCode.INVALID_PARAMETER


def test_missing_and_bad_json(tmp_path):
    with pytest.raises(LSIError):
        catalog.load_simulation_config(tmp_path / "no.json")
    (tmp_path / "b.json").write_text("{")
    with pytest.raises(LSIError):
        catalog.load_sites(tmp_path / "b.json")


def test_sites_validation(tmp_path):
    ok = {"id": "a", "nombre": "A", "lat": -91, "lon": 0, "confianza": "aprox", "has_dem": False}
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"sites": [ok]}))
    with pytest.raises(LSIError, match="lat"):
        catalog.load_sites(p)
    ok.update(lat=-80, _x=1)
    p.write_text(json.dumps({"sites": [ok, ok]}))
    with pytest.raises(LSIError, match="duplicado"):
        catalog.load_sites(p)
    p.write_text(json.dumps({"sites": [ok]}))
    assert catalog.load_sites(p)[0].lat_deg == -80.0
