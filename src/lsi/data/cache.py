"""Caché por contenido en disco: npz + JSON, sin pickle (arquitectura.md §5.3 y §6)."""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping, Optional

import numpy as np

from lsi.contracts import CACHE_ALGORITHM_VERSION, HorizonMode, HorizonParams

_FLOAT_DECIMALS = 9


def _canon(o):
    if isinstance(o, enum.Enum):
        return _canon(o.value)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: _canon(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, np.generic):
        return _canon(o.item())
    if isinstance(o, float):
        return round(o, _FLOAT_DECIMALS)
    if isinstance(o, Mapping):
        return {str(k): _canon(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_canon(v) for v in o]
    return o


def digest(*parts: object) -> str:
    s = json.dumps(_canon(list(parts)), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def horizon_key(dem_sha256: Optional[str], mode: HorizonMode, x_m: float, y_m: float,
                params: HorizonParams, coord_round_m: float = 0.01) -> str:
    q = lambda v: round(round(v / coord_round_m) * coord_round_m, 6)
    return digest(CACHE_ALGORITHM_VERSION, dem_sha256, mode, q(x_m), q(y_m), params)


def _path(cache_dir: Path, kind: str, key: str) -> Path:
    if not (kind.isidentifier() and key.isalnum()):  # evita escapar de cache_dir
        raise ValueError(f"kind/key inválidos: {kind!r}, {key!r}")
    return Path(cache_dir) / kind / f"{key}.npz"


def load_npz(cache_dir: Path, kind: str, key: str) -> dict[str, np.ndarray] | None:
    p = _path(cache_dir, kind, key)
    if not p.exists():
        return None
    try:
        with np.load(p, allow_pickle=False) as z:
            out = {k: z[k] for k in z.files}
    except Exception:  # corrupto: se descarta
        p.unlink(missing_ok=True)
        return None
    try:
        os.utime(p)  # marca de uso para la purga LRU
    except OSError:
        pass
    return out


def save_npz(cache_dir: Path, kind: str, key: str, arrays: Mapping[str, np.ndarray]) -> Path:
    p = _path(cache_dir, kind, key)
    arrays = {k: np.asarray(v) for k, v in arrays.items()}
    if any(a.dtype.hasobject for a in arrays.values()):
        raise ValueError("arrays con dtype object no se cachean (sin pickle)")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez(f, **arrays)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return p


REGENERABLE_KINDS = ("horizons",)   # cachés baratas de regenerar: las únicas que la purga LRU puede tocar
PROTECTED_KINDS = ("suitability",)  # mapas de idoneidad precalculados (minutos de cómputo cada uno): la purga NUNCA los borra


def purge(cache_dir: Path, max_bytes: int, kinds=REGENERABLE_KINDS) -> int:
    """Purga LRU (por mtime) de ``cache_dir/<kind>/**.npz`` solo para ``kinds`` (por defecto ``horizons``); devuelve bytes liberados.

    Nunca recorre otra cosa: ``suitability/`` (``PROTECTED_KINDS``), ``gazetteer.*``, ``dem_hash.json``... quedan fuera aunque
    ``cache_dir`` sea ``data/processed``. El tope ``max_bytes`` cuenta solo los ficheros de ``kinds``.
    """
    files = []
    for kind in kinds:
        if kind in PROTECTED_KINDS or not kind.isidentifier():
            continue
        for p in (Path(cache_dir) / kind).rglob("*.npz"):
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((st.st_mtime_ns, st.st_size, p))
    total, freed = sum(f[1] for f in files), 0
    for _, size, p in sorted(files, key=lambda f: f[0]):  # menos recientes primero
        if total <= max_bytes:
            break
        try:
            p.unlink()
        except OSError:
            continue
        total -= size
        freed += size
    return freed
