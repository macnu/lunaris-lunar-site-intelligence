"""Descargas honestas: ``fetch_validation_data`` (Site01) y manifiesto de SHA-256 (``data_manifest``). Sin red."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import data_manifest as dm  # noqa: E402
import fetch_validation_data as fv  # noqa: E402


def test_help_does_not_touch_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("--help no puede usar la red")
    monkeypatch.setattr(fv.requests, "head", boom)
    monkeypatch.setattr(fv.requests, "get", boom)
    with pytest.raises(SystemExit) as e:
        fv.main(["--help"])
    assert e.value.code == 0


def test_without_yes_only_heads(monkeypatch, tmp_path):
    class R:
        headers = {"content-type": "image/tiff", "Content-Length": "10"}
        def raise_for_status(self): pass
    monkeypatch.setattr(fv.requests, "head", lambda *a, **k: R())
    monkeypatch.setattr(fv.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("descargó sin --yes")))
    monkeypatch.setattr(fv, "OUT", tmp_path)
    assert fv.main([]) == 0 and not list(tmp_path.iterdir())


def test_html_and_wrong_size_rejected(tmp_path):
    p = tmp_path / "x.tif"
    p.write_bytes(b"<html>404</html>")
    with pytest.raises(RuntimeError, match="no es un TIFF"):
        fv.check_tiff(p, p.stat().st_size)
    p.write_bytes(b"II*\x00" + b"0" * 6)
    fv.check_tiff(p, 10)
    with pytest.raises(RuntimeError, match="esperados 11"):
        fv.check_tiff(p, 11)


def test_manifest_mismatch_message_and_match(tmp_path, monkeypatch):
    f = tmp_path / "d.bin"
    f.write_bytes(b"abc")
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"files": {"k": {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}}}))
    monkeypatch.setattr(dm, "MANIFEST", man)
    assert dm.check(f, "k") is True and dm.check(f, "desconocido") is False
    f.write_bytes(b"abd")
    with pytest.raises(dm.DataMismatchError, match="--regenerate"):
        dm.check(f, "k")


def test_repo_manifest_covers_what_is_downloaded():
    files = dm.load().get("files", {})
    assert files, "falta config/data_manifest.json"
    for k, p in dm.tracked().items():
        assert k in files, f"{k} descargado sin hash en el manifiesto"
