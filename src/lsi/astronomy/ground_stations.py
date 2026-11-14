"""Estaciones terrestres y cobertura de red: ¿ve alguna estación la Luna por encima de su elevación mínima?

La «conectividad» de un sitio lunar no es solo «la Tierra está sobre el horizonte local»: hace falta además que una antena
terrestre vea la Luna. Esa cobertura es casi independiente del sitio lunar (paralaje de la Luna vista desde dos puntos
de ella ≲ 0,5°; medido en ``tests/test_ground_stations.py``), así que se calcula UNA vez por rejilla temporal.

Geometría (arquitectura §5.8, luna-spice-sitios.md §Estaciones): posición aparente de la Luna (LT+S) respecto al centro de
la Tierra en ``IAU_EARTH`` (``spkpos`` vectorizado), menos la posición de la estación (punto geodésico sobre el elipsoide
WGS 84), proyectada sobre la vertical geodésica. Sin refracción (el límite de la antena, no de la atmósfera, manda).

Precisión de ``IAU_EARTH`` (pck00011.tpc): ignora nutación, movimiento polar y UT1-UTC. Medido contra JPL Horizons
(ITRF93) en 2026-12: ≤ 0,072° (rms 0,055°); con el PCK binario de ITRF93, 0,0005°. 0,07° mueve una salida/puesta ~20 s,
despreciable frente a la rejilla de 600 s; por eso no se descarga el kernel binario (ver ``config/ground_stations.json``).

**Sentido del enlace** (``link_direction``): ``receive`` (defecto) usa la elevación mínima de RECEPCIÓN de cada estación (6,0° en el
DSN, 810-005/301 Rev. P §2.2.2/§2.2.4 [pub]); ``transmit`` la de TRANSMISIÓN (10,1°: «no hay transmisión por debajo de 10,1° en
ninguna antena y a ninguna potencia», §2.2.1 [pub]; las reservas de alta potencia, 13,6° y DSS-43 17,6°, NO se modelan); ``both`` =
intersección de ambas = la mayor de las dos por estación. Comandar al lander exige transmitir: la cobertura de red baja de ~99,9 % a ~98,0 %.

**Huecos de traspaso** (``handoff_merge_tol_s``): los cruces por elevación mínima se interpolan linealmente sobre la rejilla (600 s); en un
traspaso entre dos estaciones a ~6° eso deja huecos espurios de unos segundos que no existen. Al unir las ventanas de red se fusionan los
huecos ≤ ``handoff_merge_tol_s``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import spiceypy as sp

from lsi.analysis import metrics as mt
from lsi.astronomy import spice_engine
from lsi.contracts import LINK_DIRECTIONS, ContactWindow, FloatArray, et_to_utc_datetime

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "ground_stations.json"
WGS84_A_KM = 6378.137
WGS84_INV_F = 298.257223563
_EMPTY = np.empty((0, 2), dtype=np.float64)


# ----------------------------------------------------------------------------------------------- configuración
@lru_cache(maxsize=1)
def load_config(path: str = str(CONFIG_PATH)) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Station:
    """Estación terrestre: punto geodésico (lat, lon E+, altura sobre el elipsoide) y elevación mínima de recepción."""
    id: str
    name: str
    lat_deg: float
    lon_deg_e: float
    alt_m: float
    min_elevation_deg: float
    tz: str = "UTC"
    complex: str = ""
    confidence: str = ""             # etiqueta de la elevación mínima: publicado | a verificar [sup] | personalizada
    verified: bool = True
    rx_min_elevation_deg: Optional[float] = None   # elevación mínima de recepción (None = ``min_elevation_deg``)
    tx_min_elevation_deg: Optional[float] = None   # elevación mínima de transmisión (None = sin límite propio: se usa la de recepción [sup])


@dataclass(frozen=True)
class Network:
    id: str
    label: str
    stations: tuple
    notes: tuple = ()
    direction: str = "receive"       # sentido con el que se fijó ``Station.min_elevation_deg``


def handoff_merge_tol_s(cfg: Optional[Mapping] = None) -> float:
    """Hueco máximo (s) que se considera ruido de interpolación al unir las ventanas de las estaciones (``ground_stations.json``)."""
    return float((cfg or load_config()).get("handoff_merge_tol_s", 0.0))


def _direction_el(rx: float, tx: Optional[float], direction: str) -> float:
    """Elevación mínima efectiva según el sentido; sin límite de transmisión propio se usa el de recepción."""
    t = rx if tx is None else tx
    return {"receive": rx, "transmit": t, "both": max(rx, t)}[direction]


def _direction_note(direction: str) -> tuple:
    if direction == "receive":
        return ()
    txt = {"transmit": "TRANSMISIÓN (comandar al lander)", "both": "RECEPCIÓN y TRANSMISIÓN a la vez (intersección)"}[direction]
    return (f"Sentido del enlace: {txt}: elevación mínima de transmisión 10,1° [pub, 810-005/301 Rev. P §2.2.1]; las reservas de alta "
            f"potencia (13,6°, DSS-43 17,6°), la máscara de terreno de cada antena y la ocupación de la red NO se modelan.",)


def get_network(network_id: str, *, custom: Optional[Sequence] = None, min_elevation_deg: Optional[float] = None,
                cfg: Optional[Mapping] = None, link_direction: str = "receive") -> Network:
    """Red por id ('DSN', 'ESTRACK', 'DSN+ESTRACK') o 'custom' con ``custom`` = [(lat, lon_E, min_el[, tz]), ...].

    ``min_elevation_deg`` fuerza la misma elevación mínima en todas las estaciones (sensibilidad) y manda sobre el sentido. Las
    estaciones con la elevación 'a verificar' usan el valor supuesto [sup] y la red lo declara en ``notes``.
    ``link_direction``: 'receive' (defecto) | 'transmit' | 'both' (ver el docstring del módulo).
    """
    if link_direction not in LINK_DIRECTIONS:
        raise ValueError(f"link_direction debe ser uno de {LINK_DIRECTIONS}, recibido {link_direction!r}")
    cfg = cfg or load_config()
    if network_id == "custom":
        if not custom:
            raise ValueError("red 'custom' sin estaciones: pasa [(lat, lon_E, min_el[, tz]), ...]")
        st = []
        for i, c in enumerate(custom, 1):
            lat, lon, el = (float(x) for x in c[:3])
            el = el if min_elevation_deg is None else float(min_elevation_deg)
            st.append(Station(f"custom-{i}", f"Personalizada {i}", lat, lon, 0.0, el, c[3] if len(c) > 3 else "UTC",
                              confidence="personalizada [sup]", verified=False, rx_min_elevation_deg=el, tx_min_elevation_deg=el))
        return Network("custom", "Red personalizada", tuple(st),
                       ("Red personalizada: coordenadas y elevación del usuario (la misma en recepción y transmisión).",), link_direction)
    if network_id not in cfg["networks"]:
        raise ValueError(f"red desconocida '{network_id}'; válidas: {sorted(cfg['networks'])} o 'custom'")
    n = cfg["networks"][network_id]
    st, notes = [], []
    for sid in n["stations"]:
        s = cfg["stations"][sid]
        el, conf = s.get("min_elevation_deg"), s.get("min_elevation_confidence", "")
        if el is None:
            el = n.get("min_elevation_override_deg", s.get("min_elevation_assumed_deg"))
            notes.append(f"{sid}: elevación mínima {el:g}° SUPUESTA [sup] (a verificar con fuente oficial)")
        rx, tx = float(el), s.get("tx_min_elevation_deg")
        tx = None if tx is None else float(tx)
        if min_elevation_deg is not None:
            rx, tx, conf = float(min_elevation_deg), float(min_elevation_deg), "forzada por el usuario"
        elif link_direction != "receive" and tx is None:
            notes.append(f"{sid}: sin elevación mínima de transmisión publicada; en el sentido {link_direction} se usa la de recepción {rx:g}° [sup]")
        st.append(Station(sid, s["name"], s["lat_deg"], s["lon_deg_e"], s["alt_m"], _direction_el(rx, tx, link_direction), s.get("tz", "UTC"),
                          s.get("complex", ""), conf, bool(s.get("verified", True)), rx, tx))
    return Network(network_id, n["label"], tuple(st), (*notes, *_direction_note(link_direction)), link_direction)


# ----------------------------------------------------------------------------------------------- geometría
def station_position_km(st: Station) -> FloatArray:
    """Posición de la estación en el marco fijo a la Tierra (km): punto geodésico sobre el elipsoide WGS 84."""
    f = 1.0 / WGS84_INV_F
    e2 = f * (2.0 - f)
    la, lo = np.radians(st.lat_deg), np.radians(st.lon_deg_e)
    n = WGS84_A_KM / np.sqrt(1.0 - e2 * np.sin(la) ** 2)
    h = st.alt_m / 1000.0
    return np.array([(n + h) * np.cos(la) * np.cos(lo), (n + h) * np.cos(la) * np.sin(lo),
                     (n * (1.0 - e2) + h) * np.sin(la)])


def station_up(st: Station) -> FloatArray:
    """Vertical geodésica local (no la geocéntrica: el elipsoide aplana 0,19° a 45° de latitud)."""
    la, lo = np.radians(st.lat_deg), np.radians(st.lon_deg_e)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


_MOON_CACHE: dict = {}


def moon_position_earth_fixed(et) -> FloatArray:
    """Posición aparente de la Luna (LT+S) respecto al centro de la Tierra en IAU_EARTH, (N,3) km."""
    info = spice_engine.load_kernels()
    et = np.atleast_1d(np.asarray(et, dtype=np.float64))
    key = (float(et[0]), float(et[-1]), len(et), info.kernel_hash)
    hit = _MOON_CACHE.get(key)
    if hit is not None:
        return hit
    with spice_engine.SPICE_LOCK:
        pos, _ = sp.spkpos("MOON", et, "IAU_EARTH", "LT+S", "EARTH")
    pos = np.atleast_2d(np.asarray(pos, dtype=np.float64))
    if len(_MOON_CACHE) > 8:
        _MOON_CACHE.clear()
    _MOON_CACHE[key] = pos
    return pos


def moon_elevation_deg(et, st: Station) -> FloatArray:
    """Elevación de la Luna (centro, aparente, sin refracción) sobre el horizonte geométrico de la estación."""
    v = moon_position_earth_fixed(et) - station_position_km(st)
    return np.degrees(np.arcsin(np.clip((v @ station_up(st)) / np.linalg.norm(v, axis=1), -1.0, 1.0)))


# ----------------------------------------------------------------------------------------------- cobertura de red
def cross_intervals(t: FloatArray, g: FloatArray) -> FloatArray:
    """Intervalos [a, b) de ``g >= 0`` sobre la rejilla ``t`` con los cruces interpolados linealmente (los extremos de la
    rejilla truncan). Con paso de 600 s y una elevación suave el error del cruce es de segundos."""
    t, g = np.asarray(t, dtype=np.float64), np.asarray(g, dtype=np.float64)
    m = g >= 0.0
    idx = np.flatnonzero(m[:-1] != m[1:])
    tc = t[idx] + (0.0 - g[idx]) / (g[idx + 1] - g[idx]) * (t[idx + 1] - t[idx])
    rise = ~m[idx]
    starts = np.concatenate(([t[0]] if m[0] else [], tc[rise]))
    ends = np.concatenate((tc[~rise], [t[-1]] if m[-1] else []))
    return mt.merge(np.column_stack((starts, ends)))


@dataclass(eq=False)
class NetworkCoverage:
    """Elevación de la Luna desde cada estación sobre una rejilla ET (independiente del sitio lunar)."""
    et: FloatArray
    network: Network
    el_deg: FloatArray              # (S, N)

    @property
    def min_el(self) -> FloatArray:
        return np.array([s.min_elevation_deg for s in self.network.stations])

    @property
    def visible(self) -> np.ndarray:        # (S, N) bool
        return self.el_deg >= self.min_el[:, None]

    @property
    def any_grid(self) -> np.ndarray:       # (N,) bool: alguna estación ve la Luna
        return self.visible.any(axis=0)

    def station_intervals(self) -> list:
        return [cross_intervals(self.et, self.el_deg[i] - m) for i, m in enumerate(self.min_el)]

    def any_intervals(self, tol_s: Optional[float] = None) -> FloatArray:
        """Unión de las ventanas de las estaciones fusionando huecos ≤ ``tol_s`` (defecto ``handoff_merge_tol_s``): en un traspaso
        los cruces lineales de la rejilla dejan huecos espurios de segundos que no existen (B2 de revision-enlace)."""
        tol = handoff_merge_tol_s() if tol_s is None else tol_s
        out = _EMPTY
        for iv in self.station_intervals():
            out = mt.union(out, iv, tol)
        return out

    def fraction_by_direction(self) -> dict:
        """Fracción del periodo con ≥ 1 estación viendo la Luna, por sentido del enlace (recepción / transmisión / ambos). Usa la
        misma elevación de la Luna ya calculada: solo cambia el umbral por estación (``Station.rx/tx_min_elevation_deg``)."""
        T = float(self.et[-1] - self.et[0])
        out = {}
        for d in LINK_DIRECTIONS:
            mins = [_direction_el(s.rx_min_elevation_deg if s.rx_min_elevation_deg is not None else s.min_elevation_deg,
                                  s.tx_min_elevation_deg, d) for s in self.network.stations]
            iv = _EMPTY
            for m, el in zip(mins, self.el_deg):
                iv = mt.union(iv, cross_intervals(self.et, el - m), handoff_merge_tol_s())
            out[d] = mt.total_duration(iv, float(self.et[0]), float(self.et[-1])) / T
        return out

    def sliced(self, a: int, b: int) -> "NetworkCoverage":
        return NetworkCoverage(self.et[a:b], self.network, self.el_deg[:, a:b])


def network_coverage(et, network: Network) -> NetworkCoverage:
    """UNA vez por rejilla: elevación de la Luna desde cada estación de la red."""
    et = np.atleast_1d(np.asarray(et, dtype=np.float64))
    spice_engine._check_range(et)
    return NetworkCoverage(et, network, np.vstack([moon_elevation_deg(et, s) for s in network.stations]))


@dataclass(frozen=True)
class LinkContext:
    """Red + elevación mínima de la Tierra en la antena del lander (margen sobre el horizonte local) + cobertura."""
    network: Network
    coverage: NetworkCoverage
    min_earth_elevation_deg: float = 0.0

    def sliced(self, a: int, b: int) -> "LinkContext":
        return LinkContext(self.network, self.coverage.sliced(a, b), self.min_earth_elevation_deg)


def make_link_context(et, network_id: Optional[str], min_earth_elevation_deg: float = 0.0, *,
                      custom: Optional[Sequence] = None, station_min_elevation_deg: Optional[float] = None,
                      link_direction: str = "receive") -> Optional[LinkContext]:
    """``network_id=None`` → ``None`` (conectividad solo geométrica, comportamiento anterior)."""
    if network_id is None:
        return None
    net = get_network(network_id, custom=custom, min_elevation_deg=station_min_elevation_deg, link_direction=link_direction)
    return LinkContext(net, network_coverage(et, net), float(min_earth_elevation_deg))


# ----------------------------------------------------------------------------------------------- hora local
def et_to_local(et: float, tz: str) -> datetime:
    """ET → hora civil local con zona (horario de verano de la base IANA/``tzdata``)."""
    return et_to_utc_datetime(et).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))


def local_mean_solar_hours(et: float, lon_deg_e: float) -> float:
    """Hora solar media local (h, 0-24) = UTC + lon/15 (sin ecuación del tiempo)."""
    d = et_to_utc_datetime(et)
    return float((d.hour + d.minute / 60.0 + (d.second + d.microsecond / 1e6) / 3600.0 + lon_deg_e / 15.0) % 24.0)


def _hhmm(h: float) -> str:
    m = int(round(h * 60.0)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# ----------------------------------------------------------------------------------------------- ventanas de contacto
def _max_on(t: FloatArray, y: FloatArray, a: float, b: float) -> float:
    """Máximo de la serie ``y(t)`` en [a, b]: nodos dentro y valores interpolados en los extremos."""
    m = (t >= a) & (t <= b)
    return float(max(np.max(y[m]) if m.any() else -np.inf, np.interp(a, t, y), np.interp(b, t, y)))


def contact_windows(cov: NetworkCoverage, geo_iv=None, earth_el_deg: Optional[FloatArray] = None, *,
                    t0: Optional[float] = None, t1: Optional[float] = None) -> list[ContactWindow]:
    """Ventanas de contacto por estación = (Tierra visible desde el lander con margen) ∧ (estación ve la Luna ≥ mínimo).

    ``geo_iv`` (n,2) ET: intervalos con la Tierra visible desde el lander (None = no se restringe: solo la visibilidad de
    la Luna desde la estación). ``earth_el_deg``: elevación de la Tierra en el lander sobre la rejilla (para el máximo de
    cada ventana). Orden: inicio, luego estación. ``left/right_truncated``: la ventana toca el borde del periodo.
    """
    t0 = float(cov.et[0]) if t0 is None else t0
    t1 = float(cov.et[-1]) if t1 is None else t1
    out = []
    for s, iv, el in zip(cov.network.stations, cov.station_intervals(), cov.el_deg):
        if geo_iv is not None:
            iv = mt.intersection(iv, geo_iv)
        for a, b in iv:
            lo, hi = et_to_local(a, s.tz), et_to_local(b, s.tz)
            out.append(ContactWindow(
                station_id=s.id, station_name=s.name, complex=s.complex, tz=s.tz,
                start_et=float(a), end_et=float(b),
                start_utc=et_to_utc_datetime(a).strftime("%Y-%m-%dT%H:%M:%S"),
                end_utc=et_to_utc_datetime(b).strftime("%Y-%m-%dT%H:%M:%S"),
                start_local=lo.strftime("%Y-%m-%d %H:%M:%S ") + (lo.tzname() or ""),
                end_local=hi.strftime("%Y-%m-%d %H:%M:%S ") + (hi.tzname() or ""),
                start_solar_h=local_mean_solar_hours(a, s.lon_deg_e), end_solar_h=local_mean_solar_hours(b, s.lon_deg_e),
                duration_s=float(b - a), max_moon_el_deg=_max_on(cov.et, el, a, b),
                max_earth_el_deg=None if earth_el_deg is None else _max_on(cov.et, np.asarray(earth_el_deg), a, b),
                left_truncated=bool(a <= t0), right_truncated=bool(b >= t1)))
    out.sort(key=lambda w: (w.start_et, w.station_id))
    return out


def _utc_days(t0: float, t1: float) -> list[tuple[float, float]]:
    """[(inicio, fin)] de cada día UTC que toca [t0, t1] (el primero y el último pueden ser parciales). Tolerancia de 50 ms:
    la conversión ET↔UTC pura ignora TDB−TT (< 2 ms) y no debe crear días de milisegundos."""
    from datetime import timedelta
    from lsi.contracts import utc_datetime_to_et
    tol = 0.05
    d = et_to_utc_datetime(t0 + tol).replace(hour=0, minute=0, second=0, microsecond=0)
    edges = [t0]
    while True:
        d += timedelta(days=1)
        e = utc_datetime_to_et(d)
        if e >= t1 - tol:
            break
        edges.append(e)
    edges.append(t1)
    return list(zip(edges[:-1], edges[1:]))


def _local_hhmm(et: float, tz: str):
    """Hora local redondeada al minuto (no truncada: 18:12:50 → 18:13) y su fecha local."""
    d = et_to_local(et + 30.0, tz)
    return f"{d:%H:%M}", d.date(), d.tzname()


def window_text(c: ContactWindow, day_utc: Optional[str] = None, *, continues_prev: bool = False, continues_next: bool = False) -> str:
    """Texto de UNA ventana de contacto REAL en hora local («08:37-22:11 AEDT»), entera y no recortada al día UTC. Si la hora local de
    inicio cae en otra fecha que ``day_utc`` se antepone «dd/mm»; si acaba otro día local, «(+1 d)»; y se etiqueta si continúa del día
    UTC anterior o al siguiente."""
    h0, d0, tz0 = _local_hhmm(c.start_et, c.tz)
    h1, d1, tz1 = _local_hhmm(c.end_et, c.tz)
    pre = "" if day_utc is None or d0.isoformat() == day_utc else f"{d0:%d/%m} "
    nxt = f" (+{(d1 - d0).days} d)" if d1 > d0 else ""
    tag = (" (continúa del día anterior)" if continues_prev else "") + (" (continúa al día siguiente)" if continues_next else "")
    return f"{pre}{h0}-{h1}{nxt} {tz1 or tz0}{tag}"


def daily_contact_table(contacts: Sequence[ContactWindow], t0: float, t1: float) -> list[dict]:
    """Por día UTC: las ventanas de contacto REALES de cada estación que tocan el día (sin partirlas ni unirlas), las horas de
    enlace de cada estación DENTRO del día (número aparte), solape entre estaciones (traspaso: ≥ 2 a la vez) y huecos sin ninguna.

    Una ventana que cruza la medianoche UTC aparece en los dos días con su hora local COMPLETA y la etiqueta «continúa del día
    anterior» / «continúa al día siguiente»; ya no se parte por día UTC (eso fabricaba ventanas inexistentes como «Canberra 09:34-22:11
    AEDT» uniendo el final de una ventana con el inicio de la siguiente). ``stations[sid]``: ``hours`` (horas dentro del día),
    ``windows`` (lista de ``{start_utc, end_utc, start_local, end_local, text, continues_prev, continues_next, hours_in_day}``) y
    ``local`` (los textos). Horas de enlace de red = unión de los trozos DENTRO del día (no suma de estaciones). A diferencia de
    ``contact_windows`` (ventanas enteras del periodo), esta tabla es por día: ambas coinciden en las ventanas, no en las horas."""
    by = {}
    for c in contacts:
        by.setdefault(c.station_id, []).append(c)
    rows = []
    for a, b in _utc_days(t0, t1):
        day = et_to_utc_datetime(a + 0.05).strftime("%Y-%m-%d")
        row = {"day_utc": day, "start_et": a, "end_et": b, "stations": {}}
        ivs = {}
        for sid, cs in by.items():
            seg = [(max(c.start_et, a), min(c.end_et, b), c) for c in cs if c.end_et > a and c.start_et < b]
            if not seg:
                continue
            ivs[sid] = np.array([(s, e) for s, e, _ in seg])
            wins = []
            for s, e, c in seg:
                prev, nxt = c.start_et < a - 0.05, c.end_et > b + 0.05
                wins.append({"start_utc": c.start_utc, "end_utc": c.end_utc, "start_local": c.start_local, "end_local": c.end_local,
                             "text": window_text(c, day, continues_prev=prev, continues_next=nxt),
                             "continues_prev": prev, "continues_next": nxt, "hours_in_day": float((e - s) / 3600.0)})
            row["stations"][sid] = {"hours": float((ivs[sid][:, 1] - ivs[sid][:, 0]).sum() / 3600.0), "windows": wins,
                                    "local": [w["text"] for w in wins]}
        union = _EMPTY
        for iv in ivs.values():
            union = mt.union(union, iv)
        pts = np.concatenate([iv.ravel() for iv in ivs.values()]) if ivs else np.empty(0)
        delta = np.concatenate([np.tile([1, -1], len(iv)) for iv in ivs.values()]) if ivs else np.empty(0)
        o = np.argsort(pts, kind="stable")
        cover = np.cumsum(delta[o])
        overlap = float(np.sum(np.diff(pts[o])[cover[:-1] >= 2])) / 3600.0 if len(pts) > 1 else 0.0
        link_h = float(mt.total_duration(union)) / 3600.0
        row.update(link_hours=link_h, overlap_hours=overlap, gap_hours=(b - a) / 3600.0 - link_h)
        row["text"] = "; ".join(f"{sid} {', '.join(v['local'])}" for sid, v in row["stations"].items()) or "sin enlace"
        rows.append(row)
    return rows
