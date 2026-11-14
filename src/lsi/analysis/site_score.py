"""Score de idoneidad de un emplazamiento (arquitectura §5.14, matematica.md §7).

Funciones puras y deterministas, sin I/O. Cada subindicador se normaliza a [0,1], se agregan con media
geométrica ponderada (no compensatoria) y se acompañan de puertas, rango por escenarios, desglose y
supuestos. Sin datos de terreno el resultado es PARCIAL (§5.9), nunca una cifra completa.
Todas las constantes salen de ``ScoreParams``/``ScoreProfile`` (``config/simulation.json: score``).

Ronda de correcciones (revision-espacial §2-§4, revision-matematica):

- **El estado lo deciden las puertas y los escenarios, no la nota** (``decide_verdict``): APTO = todas las puertas en el
  nominal y en todos los escenarios; CONDICIONAL = nominal sin fallo duro pero con puerta blanda fallida, escenario que
  falla o ventana de inicio frágil; NO APTO = falla una puerta DURA en el nominal (sobre esfera lisa: provisional,
  «cota optimista»); SIN DATOS = nada falla pero falta un dato (terreno, periodo < misión). No existe ningún umbral de
  nota: el score solo ordena. El pipeline evalúa todo sobre la VENTANA de misión; aquí solo están las piezas puras.
- **s_earth con mínimo útil**: ``min(1, f_E / max(f_E,ref, earth_floor))``. Antes ``f_E/f_E,ref`` daba 1 con
  f_E = f_E,ref = 0,08 (una Tierra visible el 8 % del tiempo puntuaba «perfecta» porque la esfera lisa tampoco la ve).
  ``earth_floor`` es la fracción de ventana con Tierra que se considera comunicación plena [sup: 0,25 por defecto, 0,5 en
  DTE]. Con la referencia ≥ floor (lo habitual: ~0,5 en el polo) nada cambia.
- **Resolución arriba**: ``S = 100·A^(1−λ)·Q^λ`` con A = media geométrica de los s_i (que saturan en su umbral) y Q =
  media geométrica de indicadores SIN saturar (f_sol bruta, s_noche, s_Tierra, 1 − pendiente/σ1). Con λ =
  ``resolution_weight`` (0,25 en config; 0 = comportamiento antiguo) superar el umbral sigue sumando, y solo 100 % de
  Sol, 0 h de noche y 0° de pendiente dan 100: ya no se amontonan sitios distintos en 100 en ventanas cortas.

- **Continuidad del enlace en s_earth** (revision-enlace B1): con enlace DTE y ventana de misión, ``s_earth = s_rel · c_hueco · c_día``
  (``subscores``/``continuity_factor``). ``s_rel = min(1, f_E / max(f_E,ref, earth_floor))`` es RELATIVO a la esfera lisa y satura:
  un enlace del 62 % con un hueco de 127 h puntuaba igual (97,41) que uno del 100 % sin huecos, porque la esfera lisa de ESA ventana también
  ve la Tierra solo el 36 %. Los dos factores son ABSOLUTOS: ``c_hueco = 2^(−hueco / (k·hueco tolerado por el perfil))`` (la misma familia
  que ``s_night = 2^(−D/d_half)``: ambos miden una interrupción continua; vale 1 sin hueco, 1/2 con un hueco igual a ``k`` veces lo tolerado
  (k = ``link_gap_half_factor``, [sup]), estrictamente decreciente y continuo) y ``c_día = min(1, h_contacto_por_día / mínimo útil del
  perfil)`` (lineal hasta el mínimo; el mínimo es la ventana útil G6 de panels.json, [sup]). Producto = no compensatorio: ni muchas horas
  compensan un apagón largo ni un enlace continuo compensa tener casi ninguna hora. Sin enlace/ventana (geometría, periodo entero) o con
  ``link_gap_half_factor = 0`` el factor es 1 y nada cambia.

Cierre del objetivo (T39 / RF-33, puerta final R2/R4):

- **Energía ligada al panel elegido**: con ``ScoreInputs.f_power_eff`` (``effective_energy``: (1-w)·P_rel medio + w·duty útil
  sobre la ventana de misión) la subpuntuación de Sol usa la potencia efectiva del panel y montaje elegidos en vez de la
  fracción de Sol geométrica (que sigue gobernando G0/G1). Sin panel (``None``) se usa el Sol geométrico y el resultado lo
  dice (``energy_basis``). **G5** (duty útil ≥ mínimo del perfil) se evalúa solo con panel.
- **Rango**: ``range_computed``/``range_note`` dicen si el rango sale de escenarios de incertidumbre; sin ellos NO es un rango.
"""
from __future__ import annotations

import math
from typing import Mapping, Optional, Sequence

import numpy as np

from lsi.analysis.confidence import data_confidence
from lsi.contracts import (
    STANDARD_WARNINGS_ES, DemConfidence, GateResult, GateStatus, MissionProfile,
    ScoreInputs, ScoreParams, ScoreProfile, SiteScoreResult, SubScore, WarningCode,
)

APTO, CONDICIONAL, NO_APTO, SIN_DATOS = "APTO", "CONDICIONAL", "NO APTO", "SIN DATOS"
KEYS = ("sun", "night", "earth", "terrain")
_LABELS = {"sun": "Energía solar", "night": "Noche continua máxima", "earth": "Visibilidad de la Tierra",
           "terrain": "Pendiente del terreno"}
_LABEL_LINK = "Enlace con la Tierra (red terrestre)"   # s_earth en modo enlace (``ScoreInputs.link_mode``)
_UNITS = {"sun": "fracción", "night": "h", "earth": "fracción", "terrain": "°"}
_VALUE_ATTR = {"sun": "f_sun", "night": "d_max_h", "earth": "f_earth", "terrain": "slope_p90_deg"}

# Pesos por defecto (matematica.md §7.4). Reflejan config/simulation.json; un test comprueba que coinciden.
_W_LANDER = {"sun": 0.40, "night": 0.25, "earth": 0.15, "terrain": 0.20}
DEFAULT_PROFILES: Mapping[str, ScoreProfile] = {
    "lander_solar_no_rhu": ScoreProfile("lander_solar_no_rhu", "Lander solar (sin RHU)", _W_LANDER,
                                        mission_profile_id="lander_solar_no_rhu", mission_days=14.0, max_link_gap_h=48.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=2.0),
    "lander_with_batteries": ScoreProfile("lander_with_batteries", "Lander con baterías", _W_LANDER,
                                          mission_profile_id="lander_with_batteries", mission_days=30.0, max_link_gap_h=48.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=2.0),
    "lander_rhu": ScoreProfile("lander_rhu", "Lander con RHU (clase Chang'e-4)",
                               {"sun": 0.40, "night": 0.10, "earth": 0.25, "terrain": 0.25},
                               mission_profile_id="lander_solar_no_rhu", mission_days=90.0, g4_na=True, max_link_gap_h=96.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=2.0),
    "rover": ScoreProfile("rover", "Rover", {"sun": 0.30, "night": 0.15, "earth": 0.15, "terrain": 0.40},
                          mission_profile_id="rover", mission_days=100.0, g4_limit_h=50.0, g4_type="soft", max_link_gap_h=24.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=2.0),
    "base_isru": ScoreProfile("base_isru", "Base / ISRU", _W_LANDER, mission_profile_id="base_isru",
                              mission_days=365.0, g5_min_duty=0.75, g5_type="hard", max_link_gap_h=12.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=8.0),
    "dte_comms": ScoreProfile("dte_comms", "Comunicaciones (DTE)",
                              {"sun": 0.15, "night": 0.10, "earth": 0.60, "terrain": 0.15},
                              mission_profile_id="dte_comms", uses_solar_gate=False, mission_days=365.0,
                              earth_floor=0.5, max_link_gap_h=24.0, max_link_gap_type="soft", min_earth_elevation_deg=0.0, min_link_hours_per_day=2.0),
    "custom": ScoreProfile("custom", "Personalizado", {k: 0.25 for k in KEYS}),
}


# --------------------------------------------------------------------------------------
# Configuración -> tipos
# --------------------------------------------------------------------------------------
def params_from_config(score_cfg: Mapping) -> ScoreParams:
    """``simulation.json['score']`` -> ``ScoreParams`` (lo no presente conserva el defecto)."""
    g, c = score_cfg.get("gates", {}), score_cfg.get("confidence", {})
    w, st = score_cfg.get("window", {}), score_cfg.get("status_rules", {})
    sat = score_cfg.get("saturation", {})
    kw = {k: score_cfg[k] for k in ("f0", "f1", "d_half_h", "sigma0_deg", "sigma1_deg", "eps_s", "earth_floor",
                                    "resolution_weight") if k in score_cfg}
    kw.update({k: sat[k] for k in ("earth_floor", "resolution_weight") if k in sat})
    kw.update({dst: w[src] for src, dst in (("start_step_h", "window_step_h"), ("top_n_windows", "top_n_windows"))
               if src in w})
    if "needs_sun" in w.get("arrival_gate", {}):
        kw["g0_needs_sun"] = bool(w["arrival_gate"]["needs_sun"])
    if "min_feasible_start_fraction" in st:
        kw["min_feasible_start_fraction"] = st["min_feasible_start_fraction"]
    kw.update({k: g[k] for k in ("g1_min_sun_fraction", "g2_max_slope_deg", "g3_max_unknown_fraction", "g5_min_duty", "g5_type")
               if k in g})
    if "power_duty_weight" in score_cfg.get("energy", {}):
        kw["power_duty_weight"] = score_cfg["energy"]["power_duty_weight"]
    cont = score_cfg.get("link", {}).get("continuity", {})
    if "gap_half_factor" in cont:
        kw["link_gap_half_factor"] = float(cont["gap_half_factor"])
    for src, dst in (("conf_range_scale", "conf_range_scale"), ("high", "conf_high"), ("medium", "conf_medium")):
        if src in c:
            kw[dst] = c[src]
    return ScoreParams(**kw)


def profiles_from_config(score_cfg: Mapping) -> dict[str, ScoreProfile]:
    """``simulation.json['score']['profiles']`` -> ``{id: ScoreProfile}`` (``mission_profile_id`` = id salvo custom o
    ``mission_profile_id`` explícito). Claves de ventana/puertas: ``mission_days``, ``earth_floor``,
    ``g4: {max_dark_h, type}`` (anula el límite de panels.json) o ``g4: {na: true}``."""
    out = {}
    for pid, p in score_cfg["profiles"].items():
        g4, g5 = p.get("g4", {}), p.get("g5", {})
        out[pid] = ScoreProfile(
            pid, p["label"], dict(p["weights"]),
            mission_profile_id=p.get("mission_profile_id", None if pid == "custom" else pid),
            uses_solar_gate=p.get("uses_solar_gate", True), d_half_h=p.get("d_half_h"),
            mission_days=None if p.get("mission_days") is None else float(p["mission_days"]),
            earth_floor=p.get("earth_floor"), g4_limit_h=g4.get("max_dark_h"), g4_type=g4.get("type"),
            g4_na=bool(g4.get("na", False)), g5_min_duty=g5.get("min_duty"), g5_type=g5.get("type"),
            min_earth_elevation_deg=p.get("link", {}).get("min_earth_elevation_deg"),
            max_link_gap_h=p.get("link", {}).get("max_gap_h"), max_link_gap_type=p.get("link", {}).get("max_gap_type"),
            min_link_hours_per_day=p.get("link", {}).get("min_hours_per_day"))
    return out


# --------------------------------------------------------------------------------------
# Núcleo matemático
# --------------------------------------------------------------------------------------
def _check_inputs(i: ScoreInputs) -> None:
    if i.f_power_eff is not None and not (0.0 <= i.f_power_eff <= 1.0):
        raise ValueError(f"ScoreInputs.f_power_eff={i.f_power_eff!r} fuera de [0, 1]")
    for name, v, hi in (("f_sun", i.f_sun, 1.0), ("f_earth", i.f_earth, 1.0),
                        ("unknown_fraction", i.unknown_fraction, 1.0), ("d_max_h", i.d_max_h, math.inf)):
        if not (0.0 <= v <= hi):  # NaN falla la comparación
            raise ValueError(f"ScoreInputs.{name}={v!r} fuera de [0, {hi}]")
    if i.slope_p90_deg is not None and not (i.slope_p90_deg >= 0):
        raise ValueError(f"ScoreInputs.slope_p90_deg={i.slope_p90_deg!r} inválido")
    if not i.f_earth_ref > 0:
        raise ValueError("f_earth_ref debe ser > 0")
    if i.max_link_gap_h is not None and not (i.max_link_gap_h >= 0):
        raise ValueError(f"ScoreInputs.max_link_gap_h={i.max_link_gap_h!r} inválido")
    if i.slope_p90_deg is not None and not i.has_dem:
        raise ValueError("slope_p90_deg con has_dem=False es incoherente")


def effective_energy(p_rel_mean: float, duty_useful: float, duty_weight: float) -> float:
    """Energía efectiva en [0,1] de un panel+montaje en la ventana: ``(1-w)·P_rel medio + w·duty útil`` (w = ``power_duty_weight``,
    [sup]). Monótona en ambos; 0 si el panel no rinde nada y 1 solo con potencia máxima todo el tiempo."""
    return min(1.0, max(0.0, (1.0 - duty_weight) * p_rel_mean + duty_weight * duty_useful))


def _f_energy(i: ScoreInputs) -> float:
    """Fracción que alimenta s_sun: la efectiva del panel si la hay, si no la geométrica."""
    return i.f_sun if i.f_power_eff is None else i.f_power_eff


def earth_reference_fraction(f_earth_on_smooth_sphere: float) -> float:
    """Valida y devuelve f_E,ref (lo mide el pipeline con H≡H_esfera); debe ser > 0."""
    if not f_earth_on_smooth_sphere > 0:
        raise ValueError("f_E,ref debe ser > 0")
    return float(f_earth_on_smooth_sphere)


def normalize_weights(weights: Mapping[str, float], drop: Sequence[str] = ()) -> dict[str, float]:
    """Pesos de ``KEYS`` renormalizados a Σ=1, excluyendo ``drop``. Claves ausentes = 0."""
    extra = set(weights) - set(KEYS)
    if extra:
        raise ValueError(f"claves de peso desconocidas: {sorted(extra)}")
    w = {k: float(weights.get(k, 0.0)) for k in KEYS if k not in drop}
    if any(not (v >= 0) for v in w.values()) or sum(w.values()) <= 0:
        raise ValueError("los pesos deben ser >= 0 con suma > 0")
    t = sum(w.values())
    return {k: v / t for k, v in w.items()}


def aggregate(s: Mapping[str, float], weights: Mapping[str, float], eps_s: float) -> float:
    """Media geométrica ponderada ×100: ``100·Π max(s_i, ε)^{w_i}`` (pesos ya con Σ=1)."""
    return 100.0 * math.exp(sum(w * math.log(max(s[k], eps_s)) for k, w in weights.items() if w > 0))


def blend(s: Mapping[str, float], q: Mapping[str, float], weights: Mapping[str, float], eps_s: float,
          lam: float) -> float:
    """``100·A^(1−λ)·Q^λ`` (A sobre ``s`` saturados, Q sobre ``q`` sin saturar). Con λ=0 es ``aggregate``."""
    return 100.0 * math.exp(sum(w * ((1.0 - lam) * math.log(max(s[k], eps_s)) + lam * math.log(max(q[k], eps_s)))
                                for k, w in weights.items() if w > 0))


def _earth_floor(profile: ScoreProfile, params: ScoreParams) -> float:
    return params.earth_floor if profile.earth_floor is None else profile.earth_floor


def continuity_factor(max_gap_h, f_link, gap_tol_h: Optional[float], half_factor: float, min_h_day: Optional[float]):
    """Factor ABSOLUTO de continuidad del enlace en (0, 1]: ``2^(−hueco/(k·tol)) · min(1, 24·f_enlace/mín_h_día)``.

    Admite escalares o arrays (el mapa de idoneidad lo vectoriza con la MISMA función). ``gap_tol_h`` = hueco tolerado por el perfil
    (G7); ``half_factor`` = k (``ScoreParams.link_gap_half_factor``; 0 desactiva todo); ``min_h_day`` = contacto mínimo útil por día
    (``ScoreProfile.min_link_hours_per_day``; ``None`` sin ese componente). Monótono: nunca sube con más hueco ni baja con más fracción.
    """
    c = 1.0
    if not half_factor > 0:
        return c
    if gap_tol_h:
        c = c * np.exp2(-np.asarray(max_gap_h, dtype=float) / (half_factor * float(gap_tol_h)))
    if min_h_day:
        c = c * np.minimum(1.0, 24.0 * np.asarray(f_link, dtype=float) / float(min_h_day))
    return c


def _continuity(i: ScoreInputs, profile: ScoreProfile, params: ScoreParams) -> float:
    """``continuity_factor`` de unas entradas: solo con hueco medido (enlace DTE + ventana de misión); si no, 1."""
    if i.max_link_gap_h is None:
        return 1.0
    return float(continuity_factor(i.max_link_gap_h, i.f_earth, profile.max_link_gap_h, params.link_gap_half_factor,
                                   profile.min_link_hours_per_day))


def subscores(inputs: ScoreInputs, profile: ScoreProfile, params: ScoreParams) -> dict[str, Optional[float]]:
    """s_sun, s_night, s_earth, s_terrain en [0,1]; s_terrain=None si no hay pendiente (sin DEM)."""
    _check_inputs(inputs)
    d_half = profile.d_half_h if profile.d_half_h is not None else params.d_half_h
    clip01 = lambda x: min(1.0, max(0.0, x))  # noqa: E731
    s_terrain = None if inputs.slope_p90_deg is None else \
        1.0 - clip01((inputs.slope_p90_deg - params.sigma0_deg) / (params.sigma1_deg - params.sigma0_deg))
    return {
        "sun": clip01((_f_energy(inputs) - params.f0) / (params.f1 - params.f0)),
        "night": 2.0 ** (-inputs.d_max_h / d_half),
        "earth": min(1.0, inputs.f_earth / max(inputs.f_earth_ref, _earth_floor(profile, params))) * _continuity(inputs, profile, params),
        "terrain": s_terrain,
    }


def _quality(inputs: ScoreInputs, s: Mapping[str, Optional[float]], params: ScoreParams) -> dict[str, Optional[float]]:
    """Indicadores SIN saturar (la parte alta del score): f_sol bruta, noche, Tierra y 1 − pendiente/σ1."""
    return {"sun": min(1.0, max(0.0, _f_energy(inputs))), "night": s["night"], "earth": s["earth"],
            "terrain": None if inputs.slope_p90_deg is None else
            1.0 - min(1.0, max(0.0, inputs.slope_p90_deg / params.sigma1_deg))}


def _g(gid, ok, reason, *, hard=True, value=None, limit=None, margin=None, window=None) -> GateResult:
    return GateResult(gid, GateStatus.PASS if ok else GateStatus.FAIL, reason, hard, value, limit, margin, window)


def _margin(value: float, limit: float, upper: bool) -> Optional[float]:
    """(límite − valor)/límite en puertas «≤» y (valor − límite)/límite en «≥»; None con límite 0."""
    return None if not limit else ((limit - value) if upper else (value - limit)) / limit


def evaluate_gates(inputs: ScoreInputs, profile: ScoreProfile, params: ScoreParams,
                   mission: Optional[MissionProfile]) -> tuple[GateResult, ...]:
    """G0 llegada con Sol (si ``sun_at_start``), G1 energía, G2 pendiente (diseño del perfil), G3 datos/sin terreno,
    G4 noche del perfil (dura o blanda; el perfil puede anularla) y G6 ventana de Tierra o de enlace (si ``longest_earth_h``) y G7 hueco máximo sin enlace (si ``max_link_gap_h``).

    Una puerta blanda (``hard=False``) que falla no rechaza el sitio: lo vuelve CONDICIONAL (``decide_verdict``).
    G5 (potencia útil: ``duty_useful`` ≥ mínimo del perfil) se evalúa solo si hay panel elegido (``inputs.duty_useful``); sin
    él no aparece (no se inventa). G1 sigue siendo sobre el Sol geométrico.
    """
    _check_inputs(inputs)
    P, F, N, D = GateStatus.PASS, GateStatus.FAIL, GateStatus.NO_DATA, GateStatus.NOT_APPLICABLE
    thr = (lambda key: mission.thresholds.get(key)) if mission is not None else (lambda key: None)
    win = "ventana" if inputs.sun_at_start is not None else "periodo"
    out = []
    # G0
    if inputs.sun_at_start is not None:
        if not (profile.uses_solar_gate and params.g0_needs_sun):
            out.append(GateResult("G0", D, "el perfil no exige Sol en la llegada", True, window="inicio"))
        else:
            out.append(_g("G0", inputs.sun_at_start,
                          "Sol visible en la fecha de inicio" if inputs.sun_at_start else
                          "no apto (llegada de noche): el Sol no es visible en la fecha de inicio", window="inicio"))
    # G1
    if not profile.uses_solar_gate:
        g1 = GateResult("G1", D, "el perfil no depende de energía solar")
    else:
        ok = inputs.f_sun >= params.g1_min_sun_fraction
        g1 = _g("G1", ok, (f"f_sol {inputs.f_sun:.3f} ≥ {params.g1_min_sun_fraction}" if ok else
                           f"no apto (sin energía solar): f_sol {inputs.f_sun:.3f} < {params.g1_min_sun_fraction}"),
                value=inputs.f_sun, limit=params.g1_min_sun_fraction,
                margin=_margin(inputs.f_sun, params.g1_min_sun_fraction, False), window=win)
    out.append(g1)
    # G2
    t2 = thr("max_landing_slope_deg")
    max_slope = params.g2_max_slope_deg if t2 is None or t2.value is None else float(t2.value)
    if inputs.slope_p90_deg is None:
        out.append(GateResult("G2", N, "pendiente no evaluable: sin datos de terreno", limit=max_slope, window="punto"))
    else:
        ok = inputs.slope_p90_deg <= max_slope
        out.append(_g("G2", ok, (f"pendiente p90 {inputs.slope_p90_deg:.1f}° ≤ {max_slope:g}°" if ok else
                                 f"no apto (pendiente): p90 {inputs.slope_p90_deg:.1f}° > {max_slope:g}°"),
                      value=inputs.slope_p90_deg, limit=max_slope,
                      margin=_margin(inputs.slope_p90_deg, max_slope, True), window="punto"))
    # G3
    if inputs.slope_p90_deg is None or not inputs.has_dem:
        g3 = GateResult("G3", N, "sin datos de terreno (esfera lisa)", window="punto")
    elif not inputs.observer_in_dem:
        g3 = GateResult("G3", N, "sin datos suficientes: observador fuera del DEM", window="punto")
    elif inputs.unknown_fraction > params.g3_max_unknown_fraction:
        g3 = GateResult("G3", N, f"sin datos suficientes: {inputs.unknown_fraction:.0%} de azimutes con horizonte "
                                 f"desconocido relevante > {params.g3_max_unknown_fraction:.0%}", window="punto")
    else:
        g3 = GateResult("G3", P, f"datos suficientes ({inputs.unknown_fraction:.0%} de azimutes desconocidos)",
                        window="punto")
    out.append(g3)
    # G4: el perfil puede fijar su propio límite (rover: 50 h blanda) o anularlo (RHU); si no, el del perfil de misión
    t4 = thr("max_dark_h_no_nuclear")
    if profile.g4_na:
        lim, typ = None, None
    elif profile.g4_limit_h is not None:
        lim, typ = float(profile.g4_limit_h), profile.g4_type or "hard"
    elif t4 is not None and t4.value is not None:
        lim, typ = float(t4.value), t4.type
    else:
        lim, typ = None, None
    if lim is None or typ not in ("hard", "soft"):
        g4 = GateResult("G4", D, "el perfil no fija noche máxima")
    else:
        ok = inputs.d_max_h <= lim
        lb = " (cota inferior: ventana truncada)" if inputs.d_max_truncated and not ok else ""
        g4 = _g("G4", ok, (f"D_max {inputs.d_max_h:.1f} h ≤ {lim:g} h" if ok else
                           f"{'no apto' if typ == 'hard' else 'puerta blanda'} (noche): D_max {inputs.d_max_h:.1f} h > "
                           f"{lim:g} h{lb}"),
                hard=typ == "hard", value=inputs.d_max_h, limit=lim, margin=_margin(inputs.d_max_h, lim, True),
                window=win)
    out.append(g4)
    # G5 (solo con panel elegido y perfil solar)
    if inputs.duty_useful is not None and profile.uses_solar_gate:
        lim5 = params.g5_min_duty if profile.g5_min_duty is None else float(profile.g5_min_duty)
        typ5 = (profile.g5_type or params.g5_type)
        ok = inputs.duty_useful >= lim5
        thr_txt = "" if inputs.useful_power_fraction is None else f" (P_rel ≥ {inputs.useful_power_fraction:g})"
        out.append(_g("G5", ok, (f"potencia útil {inputs.duty_useful:.0%} de la ventana{thr_txt} ≥ {lim5:.0%}" if ok else
                                 f"{'no apto' if typ5 == 'hard' else 'puerta blanda'} (potencia útil): solo {inputs.duty_useful:.0%} de "
                                 f"la ventana{thr_txt} < {lim5:.0%}"),
                      hard=typ5 == "hard", value=inputs.duty_useful, limit=lim5,
                      margin=_margin(inputs.duty_useful, lim5, False), window=win))
    # G6
    t6 = thr("min_contiguous_earth_window_h")
    if inputs.longest_earth_h is not None and t6 is not None and t6.value is not None and t6.type in ("hard", "soft"):
        lim6 = float(t6.value)
        ok = inputs.longest_earth_h >= lim6
        what = "enlace continuo" if inputs.link_mode else "Tierra continua"
        out.append(_g("G6", ok, (f"ventana de {what} {inputs.longest_earth_h:.1f} h ≥ {lim6:g} h" if ok else
                                 f"{'no apto' if t6.type == 'hard' else 'puerta blanda'} (comunicación): ventana de "
                                 f"{what} {inputs.longest_earth_h:.1f} h < {lim6:g} h"),
                      hard=t6.type == "hard", value=inputs.longest_earth_h, limit=lim6,
                      margin=_margin(inputs.longest_earth_h, lim6, False), window=win))
    # G7: hueco máximo sin enlace (solo con enlace DTE y límite del perfil) [sup]
    if inputs.max_link_gap_h is not None and profile.max_link_gap_h is not None and profile.max_link_gap_type in ("hard", "soft"):
        lim7, typ7 = float(profile.max_link_gap_h), profile.max_link_gap_type
        ok = inputs.max_link_gap_h <= lim7
        out.append(_g("G7", ok, (f"hueco sin comunicaciones de {inputs.max_link_gap_h:.1f} h dentro de lo tolerado por el perfil ({lim7:g} h)" if ok else
                                 f"{'no apto' if typ7 == 'hard' else 'puerta blanda'} (comunicación): hueco sin comunicaciones de "
                                 f"{inputs.max_link_gap_h:.1f} h supera lo tolerado por el perfil ({lim7:g} h)"),
                      hard=typ7 == "hard", value=inputs.max_link_gap_h, limit=lim7,
                      margin=_margin(inputs.max_link_gap_h, lim7, True), window=win))
    return tuple(out)


_RANK = {GateStatus.PASS: 0, GateStatus.NOT_APPLICABLE: 0, GateStatus.NO_DATA: 1, GateStatus.FAIL: 2}


def hard_fails(gates: Sequence[GateResult]) -> list[GateResult]:
    return [g for g in gates if g.hard and g.status is GateStatus.FAIL]


def _gate_status(gates: Sequence[GateResult]) -> GateStatus:
    """Peor estado entre las puertas que rechazan (FAIL duras) o faltan (NO_DATA); las blandas no cuentan."""
    r = max((_RANK[g.status] for g in gates if g.hard or g.status is not GateStatus.FAIL), default=0)
    return {0: GateStatus.PASS, 1: GateStatus.NO_DATA, 2: GateStatus.FAIL}[r]


def _assumptions(partial: bool, inputs: ScoreInputs, profile: ScoreProfile, gap_on: bool = False) -> tuple[str, ...]:
    W = STANDARD_WARNINGS_ES
    out = [W[WarningCode.GEOMETRIC_ONLY], W[WarningCode.SCORE_UNCALIBRATED], W[WarningCode.ROCKS_NOT_MODELED]]
    if inputs.f_power_eff is None:
        out.append("Energía evaluada con el Sol geométrico (fracción de tiempo con Sol): no hay panel elegido; G5 (potencia útil) "
                   "no se evalúa. Elige un panel y montaje para ligar la energía a su potencia efectiva.")
    if partial:
        out += [W[WarningCode.NO_TERRAIN_DATA_SCORE], W[WarningCode.NO_DEM_SMOOTH_SPHERE]]
    if inputs.link_mode:
        out.append("Comunicaciones = ENLACE posible: Tierra sobre el horizonte del lander con el margen de elevación del perfil Y una "
                   "estación de la red viendo la Luna sobre su elevación mínima. Sigue siendo geometría: sin link budget, "
                   "ocupación de red ni máscara de terreno de la antena terrestre.")
    if inputs.max_link_gap_h is not None and gap_on:
        out.append("s_earth = fracción relativa a la esfera lisa × continuidad ABSOLUTA del enlace (hueco máximo frente al tolerado por el "
                   "perfil y horas de contacto por día frente al mínimo útil): un enlace con huecos largos ya no puntúa como uno continuo.")
    if inputs.d_max_truncated:
        out.append("D_max toca el borde del periodo: es una cota inferior (la noche real puede ser más larga).")
    if profile.id in ("lander_with_batteries", "base_isru", "lander_rhu"):
        out.append(f"Pesos del perfil «{profile.id}» son una suposición (reutilizan o derivan de los del lander solar).")
    return tuple(out)


def decide_verdict(res: SiteScoreResult, runs: Sequence[SiteScoreResult], params: ScoreParams, *,
                   short_period: bool = False, feasible_fraction: Optional[float] = None) -> tuple[str, str, bool]:
    """(veredicto, motivo, provisional). Lo deciden las puertas del nominal y los escenarios, NUNCA la nota.

    1. Falla una puerta dura en el nominal → NO APTO (sin terreno: provisional, «cota optimista»: el relieve rara vez
       arregla lo que ya falla sobre esfera lisa).
    2. ``short_period`` (periodo < duración de misión) o alguna puerta NO_DATA (terreno, observador, horizonte) →
       SIN DATOS: nunca APTO ni CONDICIONAL con datos incompletos.
    3. Puerta blanda fallida en el nominal, escenario de incertidumbre que falla alguna puerta, o fracción de fechas de
       inicio factibles < ``min_feasible_start_fraction`` → CONDICIONAL.
    4. Resto → APTO.
    """
    hf = hard_fails(res.gates)
    if hf:
        why = "; ".join(f"{g.id}: {g.reason}" for g in hf)
        if res.partial:
            return NO_APTO, f"NO APTO (provisional, cota optimista sobre esfera lisa): {why}", True
        return NO_APTO, why, False
    if short_period:
        return SIN_DATOS, "periodo más corto que la misión: no hay una ventana completa que evaluar", False
    nod = [g for g in res.gates if g.status is GateStatus.NO_DATA]
    if nod:
        return SIN_DATOS, "; ".join(f"{g.id}: {g.reason}" for g in nod), False
    why = []
    sf = [g for g in res.gates if not g.hard and g.status is GateStatus.FAIL]
    why += [f"{g.id}: {g.reason}" for g in sf]
    bad = [r for r in runs if any(g.status is GateStatus.FAIL for g in r.gates)]
    if bad:
        ids = sorted({g.id for r in bad for g in r.gates if g.status is GateStatus.FAIL})
        why.append(f"{len(bad)} de {len(runs)} escenarios de incertidumbre fallan {'/'.join(ids)}")
    if feasible_fraction is not None and feasible_fraction < params.min_feasible_start_fraction:
        why.append(f"solo {feasible_fraction:.0%} de las fechas de inicio superan las puertas duras "
                   f"(< {params.min_feasible_start_fraction:.0%}): ventana frágil")
    if why:
        return CONDICIONAL, "; ".join(why), False
    return APTO, ("supera todas las puertas en el nominal y en los escenarios de incertidumbre" if runs else
                  "supera todas las puertas en el nominal (escenarios de incertidumbre no calculados)"), False


def compute_score(inputs: ScoreInputs, profile: ScoreProfile, params: ScoreParams,
                  mission: Optional[MissionProfile] = None,
                  weights_override: Optional[Mapping[str, float]] = None) -> SiteScoreResult:
    """Media geométrica ponderada con desglose, eslabón débil y puertas; parcial si falta terreno (§5.9).

    ``status`` = peor puerta que rechaza (las blandas no cuentan); ``verdict`` = estado de 4 valores por puertas
    (aquí solo con el nominal: ``score_with_range`` lo recalcula con los escenarios).
    """
    s = subscores(inputs, profile, params)
    q = _quality(inputs, s, params)
    gates = evaluate_gates(inputs, profile, params, mission)
    raw = weights_override if weights_override is not None else profile.weights
    partial = s["terrain"] is None
    eps, lam = params.eps_s, params.resolution_weight
    w_full = normalize_weights(raw)
    w = normalize_weights(raw, drop=("terrain",)) if partial else w_full
    ev, qv = {k: s[k] for k in w}, {k: q[k] for k in w}        # subindicadores evaluados
    score = blend(ev, qv, w, eps, lam)
    if partial:  # rango (§5.9.3): terreno = ε_s y terreno = 1 con los pesos SIN renormalizar
        score_min = blend({**ev, "terrain": eps}, {**qv, "terrain": eps}, w_full, eps, lam)
        score_max = blend({**ev, "terrain": 1.0}, {**qv, "terrain": 1.0}, w_full, eps, lam)
    else:
        score_min = score_max = score

    pen = {k: w[k] * -((1.0 - lam) * math.log(max(ev[k], eps)) + lam * math.log(max(qv[k], eps))) for k in w}
    pen_total = sum(pen.values())
    rows = []
    for k in KEYS:
        if k in w:
            label = _LABELS[k] + (" (potencia efectiva del panel)" if k == "sun" and inputs.f_power_eff is not None else "")
            if k == "earth" and inputs.link_mode:
                label = _LABEL_LINK
            val = _f_energy(inputs) if k == "sun" else getattr(inputs, _VALUE_ATTR[k])
            rows.append(SubScore(k, label, val, _UNITS[k], ev[k], w[k],
                                 100.0 * pen[k] / pen_total if pen_total > 0 else 0.0,
                                 blend({**ev, k: 1.0}, {**qv, k: 1.0}, w, eps, lam)))
        else:  # terreno no evaluable: ni 0 ni 1 (s=NaN), sin peso efectivo; «S si s=1» = score_max
            rows.append(SubScore(k, _LABELS[k], None, _UNITS[k], math.nan, 0.0, 0.0, score_max))
    weakest = max(w, key=lambda k: pen[k])                      # empate: primero en KEYS
    status = _gate_status(gates)
    res = SiteScoreResult(
        profile_id=profile.id, score=score, score_min=score_min, score_max=score_max, subscores=tuple(rows),
        weakest_key=weakest, gates=gates, status=status, confidence=None,
        assumptions=_assumptions(partial, inputs, profile, params.link_gap_half_factor > 0), attenuated=status != GateStatus.PASS,
        partial=partial, missing_keys=("terrain",) if partial else (), terrain_data=not partial)
    if inputs.f_power_eff is not None:
        res.energy_basis, res.energy_p_rel_mean = "panel", inputs.p_rel_mean
        res.energy_duty_useful, res.energy_useful_threshold = inputs.duty_useful, inputs.useful_power_fraction
        res.energy_note = (f"Energía = (1−{params.power_duty_weight:g})·P_rel medio ({inputs.p_rel_mean:.3f}) + {params.power_duty_weight:g}·"
                           f"fracción de la ventana con potencia útil ({inputs.duty_useful:.3f}) = {inputs.f_power_eff:.3f} (panel y montaje elegidos).")
    else:
        res.energy_note = "Energía = fracción de tiempo con Sol (geométrica): sin panel elegido."
    res.verdict, res.verdict_reason, res.verdict_provisional = decide_verdict(res, [], params)
    return res


def score_with_range(nominal: ScoreInputs, scenarios: Sequence[ScoreInputs], profile: ScoreProfile,
                     params: ScoreParams, mission: Optional[MissionProfile] = None,
                     weights_override: Optional[Mapping[str, float]] = None,
                     c_sup: Optional[float] = None, dem: Optional[DemConfidence] = None, *,
                     short_period: bool = False, feasible_fraction: Optional[float] = None) -> SiteScoreResult:
    """``compute_score`` del nominal con score_min/max = extremos de los escenarios (y del propio nominal) y veredicto
    por puertas en nominal + escenarios (``short_period``/``feasible_fraction`` los aporta el barrido de ventanas).

    Si se pasa ``c_sup`` se calcula también la confianza: C = min(1 - unknown_fraction, c_sup, c_rango).
    """
    res = compute_score(nominal, profile, params, mission, weights_override)
    runs = [compute_score(sc, profile, params, mission, weights_override) for sc in scenarios]
    res.score_min = min([res.score_min] + [r.score_min for r in runs])
    res.score_max = max([res.score_max] + [r.score_max for r in runs])
    if c_sup is not None:
        c_range = 1.0 - min(1.0, max(0.0, (res.score_max - res.score_min) / params.conf_range_scale))
        res.confidence = data_confidence(1.0 - nominal.unknown_fraction, c_sup, c_range, dem, params)
    res.verdict, res.verdict_reason, res.verdict_provisional = decide_verdict(
        res, runs, params, short_period=short_period, feasible_fraction=feasible_fraction)
    res.range_computed = bool(scenarios)
    lo, hi = res.score_min, res.score_max
    if not scenarios:
        res.range_note = ("rango no calculado: no se ejecutó el análisis de incertidumbre"
                          + (f"; [{lo:.1f}, {hi:.1f}] solo refleja el terreno no evaluable (esfera lisa)" if res.partial else
                             f"; el score {res.score:.1f} es el nominal sin banda"))
    elif hi - lo < 0.05:
        res.range_note = (f"rango calculado y estrecho ({lo:.1f}–{hi:.1f}, {len(scenarios)} escenarios): la incertidumbre no mueve "
                          f"el score (punto saturado o dato robusto)")
    else:
        res.range_note = f"rango calculado con {len(scenarios)} escenarios de incertidumbre: {lo:.1f}–{hi:.1f}"
    return res


# --------------------------------------------------------------------------------------
# Ventanas de misión: piezas puras (el barrido lo orquesta pipeline.run_analysis)
# --------------------------------------------------------------------------------------
def choose_start(scores: Sequence[float], n_hard_fails: Sequence[int], gap_h: Optional[Sequence[float]] = None,
                 gap_limit_h: Optional[float] = None) -> tuple[int, bool]:
    """(índice de la mejor fecha de inicio, ¿supera todas las puertas duras?).

    1. Candidatas: las que superan todas las puertas duras; si ninguna, las de menos puertas duras fallidas («menor violación»,
       marcada no apta).
    2. Con ``gap_h`` y ``gap_limit_h`` (G7, blanda): entre las candidatas, las que CUMPLEN G7 (hueco ≤ límite) y, entre ellas, la de
       mayor score. Si ninguna cumple G7, la de MENOR hueco (a igual hueco, mayor score). Antes la elección ignoraba G7 y ante un empate
       de score (s_earth saturado) elegía la fecha más temprana aunque otra del mismo score tuviera enlace continuo (B1).
    3. Empate total: la más temprana (``argmax`` devuelve la primera).
    """
    sc, nf = np.asarray(scores, dtype=np.float64), np.asarray(n_hard_fails)
    ok = nf == 0
    cand = ok if ok.any() else nf == nf.min()
    if gap_h is not None and gap_limit_h is not None:
        g = np.asarray(gap_h, dtype=np.float64)
        met = cand & (g <= gap_limit_h)
        if met.any():
            cand = met
        else:
            gm = np.where(cand, g, np.inf)
            cand = cand & (gm <= gm.min() + 1e-9)
    return int(np.argmax(np.where(cand, sc, -np.inf))), bool(ok.any())


def pick_windows(start_et: Sequence[float], scores: Sequence[float], ok: Sequence[bool], min_sep_s: float,
                 n: int) -> list[int]:
    """Hasta ``n`` ventanas factibles de mayor score separadas ≥ ``min_sep_s`` entre inicios (no solapadas si
    ``min_sep_s`` = duración). Voraz; el empate favorece a la más temprana (orden estable)."""
    t, sc = np.asarray(start_et, dtype=np.float64), np.asarray(scores, dtype=np.float64)
    picked: list[int] = []
    for i in np.argsort(-sc, kind="stable"):
        if ok[i] and all(abs(t[i] - t[j]) >= min_sep_s for j in picked):
            picked.append(int(i))
            if len(picked) == n:
                break
    return picked


def max_sustainable(starts_et: Sequence[float], dark_iv: np.ndarray, limit_h: float,
                    et_end: float) -> tuple[np.ndarray, np.ndarray]:
    """Días que opera un lander desde cada inicio hasta que una noche en curso supera ``limit_h`` (instante = inicio de
    esa noche + límite). ``dark_iv`` (n,2) = intervalos de oscuridad [a, b) en ET s. Sin noche letal en el periodo el
    valor es hasta ``et_end`` y ``censored`` es True (cota inferior). G1 acumulada no se evalúa."""
    t = np.asarray(starts_et, dtype=np.float64)
    iv = np.asarray(dark_iv, dtype=np.float64).reshape(-1, 2)
    lim = limit_h * 3600.0
    viol = iv[(iv[:, 1] - iv[:, 0]) > lim]
    i = np.searchsorted(viol[:, 0], t, side="left")             # primera noche letal que empieza en/tras el inicio
    has = i < len(viol)
    kill = np.where(has, viol[np.minimum(i, max(len(viol) - 1, 0)), 0] + lim if len(viol) else et_end, et_end)
    return (kill - t) / 86400.0, ~has
