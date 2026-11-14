import os
from dataclasses import replace

import numpy as np
import pytest

from lsi.contracts import HorizonMode, HorizonParams
from lsi.data import cache

P = HorizonParams()


def test_digest_canonical():
    assert cache.digest({"b": 1, "a": 2.0000000000001}) == cache.digest({"a": 2.0, "b": 1})
    assert cache.digest(1) != cache.digest(2)
    assert len(cache.digest("x")) == 64


def test_horizon_key_sensitivity():
    k = cache.horizon_key("sha", HorizonMode.DEM, 100.0, 200.0, P)
    assert k == cache.horizon_key("sha", HorizonMode.DEM, 100.0004, 200.0, P)  # < 1 cm: misma celda
    assert k != cache.horizon_key("sha", HorizonMode.DEM, 100.02, 200.0, P)
    assert k != cache.horizon_key("sha2", HorizonMode.DEM, 100.0, 200.0, P)
    assert k != cache.horizon_key("sha", HorizonMode.SMOOTH_SPHERE, 100.0, 200.0, P)
    assert k != cache.horizon_key("sha", HorizonMode.DEM, 100.0, 200.0, replace(P, observer_height_m=3.0))
    assert k != cache.horizon_key("sha", HorizonMode.DEM, 100.0, 200.0, replace(P, z_up_m=500.0))


def test_roundtrip_and_miss(tmp_path):
    key = cache.digest("a")
    assert cache.load_npz(tmp_path, "horizons", key) is None
    a = {"h_lb": np.linspace(0, 1, 5), "limited": np.array([True, False])}
    p = cache.save_npz(tmp_path, "horizons", key, a)
    assert p == tmp_path / "horizons" / f"{key}.npz"
    out = cache.load_npz(tmp_path, "horizons", key)
    np.testing.assert_array_equal(out["h_lb"], a["h_lb"])
    assert out["limited"].dtype == bool
    assert list((tmp_path / "horizons").glob("*.tmp")) == []


def test_corrupt_is_discarded(tmp_path):
    key = cache.digest("c")
    p = cache.save_npz(tmp_path, "k", key, {"a": np.zeros(3)})
    p.write_bytes(b"basura")
    assert cache.load_npz(tmp_path, "k", key) is None
    assert not p.exists()


def test_atomic_failure_leaves_nothing(tmp_path):
    with pytest.raises(ValueError):
        cache.save_npz(tmp_path, "k", cache.digest("z"), {"a": object()})  # sin pickle
    assert not list(tmp_path.rglob("*.npz")) and not list(tmp_path.rglob("*.tmp"))


def test_invalid_kind_key(tmp_path):
    with pytest.raises(ValueError):
        cache.load_npz(tmp_path, "../x", "abc")


def test_purge_lru(tmp_path):
    keys = [cache.digest(i) for i in range(3)]
    for i, k in enumerate(keys):
        p = cache.save_npz(tmp_path, "h", k, {"a": np.zeros(1000)})
        os.utime(p, ns=(10**18 + i, 10**18 + i))
    size = (tmp_path / "h" / f"{keys[0]}.npz").stat().st_size
    cache.load_npz(tmp_path, "h", keys[0])  # keys[0] pasa a ser el más reciente
    freed = cache.purge(tmp_path, int(size * 1.5), kinds=("h",))   # «h» no es regenerable por defecto: se pide
    assert freed == 2 * size
    assert (tmp_path / "h" / f"{keys[0]}.npz").exists()
    assert not (tmp_path / "h" / f"{keys[1]}.npz").exists()
    assert cache.purge(tmp_path, 10**9, kinds=("h",)) == 0
    assert cache.purge(tmp_path / "no_existe", 0) == 0


def test_purge_never_touches_suitability_gazetteer_or_dem_hash(tmp_path):
    """A1 (revision-codigo): la purga LRU solo toca horizons/. Los mapas de idoneidad (suitability/, los MÁS antiguos y fuera
    de tope), gazetteer.* y dem_hash.json sobreviven aunque ``cache_dir`` sea la raíz data/processed y el tope sea 0."""
    old = 10**18
    for i in range(3):
        p = cache.save_npz(tmp_path, "suitability", cache.digest("su", i), {"a": np.zeros(1000)})
        os.utime(p, ns=(old + i, old + i))
    hz = [cache.save_npz(tmp_path, "horizons", cache.digest("hz", i), {"a": np.zeros(1000)}) for i in range(3)]
    for i, p in enumerate(hz):
        os.utime(p, ns=(old + 10 + i, old + 10 + i))
    keep = [tmp_path / "gazetteer.parquet", tmp_path / "gazetteer.csv", tmp_path / "dem_hash.json",
            tmp_path / "suitability" / "windows_Site04_rover_abc.json"]
    for k in keep:
        k.write_text("x", encoding="utf-8")
    su = sorted((tmp_path / "suitability").glob("*.npz"))
    assert len(su) == 3
    freed = cache.purge(tmp_path, 0)                      # tope 0: la purga más agresiva posible
    assert freed > 0 and not any(p.exists() for p in hz)  # horizons sí se purga
    assert all(p.exists() for p in su) and all(k.exists() for k in keep)
    # ni pidiéndolo explícitamente: «suitability» está protegido
    assert cache.purge(tmp_path, 0, kinds=("suitability", "horizons")) == 0 and all(p.exists() for p in su)
