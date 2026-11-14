"""Idoneidad del emplazamiento (RF-27…RF-32): nota 0–100 explicable con rango, estado, puertas y sensibilidad.

La página NO calcula física: pide el análisis (con incertidumbre) a ``ui.cache`` y re-puntúa al instante con las
funciones puras de ``lsi.analysis.site_score`` al mover pesos o umbrales (sin recomputar la simulación).
Claves de widgets propias ``_sc_*``; ninguna escritura de estado fuera de callbacks.
"""
from __future__ import annotations

import dataclasses
import math

import streamlit as st

from lsi.analysis.site_score import normalize_weights, params_from_config, profiles_from_config, score_with_range
from lsi.contracts import (
    STANDARD_WARNINGS_ES, GateStatus, HorizonMode, MissionProfile, ScoreInputs, StateKey as K, Threshold, WarningCode,
)
from lsi.visualization import score_plot
from ui import cache, components as C, state as S

KEYS = ("sun", "night", "earth", "terrain")
NAMES = {"sun": "Energía solar", "night": "Noche continua máxima", "earth": "Tierra / enlace con la red", "terrain": "Terreno (pendiente)"}
WEAK_PLAIN = {"sun": "la poca luz solar", "night": "las noches demasiado largas", "earth": "el poco enlace posible con la Tierra",
              "terrain": "la pendiente del terreno"}
# El estado (APTO/CONDICIONAL/NO APTO/SIN DATOS) lo decide ``res.score.verdict`` por puertas y escenarios: no hay umbral de nota.
_WINDOW_FIELDS = ("mission_days", "window_start_utc", "window_end_utc", "best_start_utc", "best_window_end_utc",
                  "feasible_start_fraction", "n_starts", "top_windows", "max_sustainable_days",
                  "energy_panel_id", "energy_mounting", "energy_note")


# ------------------------------------------------------------------------------------------------ re-score puro
def edit_mission(mission, slope):
    """Copia del perfil de misión con la pendiente elegida (dura); el resto de umbrales intacto."""
    th = dict(mission.thresholds) if mission else {}
    if slope is not None:
        th["max_landing_slope_deg"] = Threshold(float(slope), "hard", "suposicion", "valor de la página")
    return MissionProfile(mission.id if mission else "custom", mission.label if mission else "Personalizado", th)


def run(res, c):
    """Re-puntúa con la configuración ``c`` (perfil, parámetros, misión, pesos, pendiente, noche). Instantáneo.

    Usa las entradas y escenarios de la VENTANA que midió el pipeline (``res.score_inputs``/``score_scenarios``), así que sin
    cambios reproduce ``res.score`` (nota, rango y veredicto). La ventana elegida no se recalcula: eso es del pipeline.
    """
    sc, profile = res.score, c["profile"]
    g4 = next((g for g in sc.gates if g.id == "G4" and g.limit is not None), None)
    if c["dark"] is not None and g4 is not None and abs(c["dark"] - g4.limit) > 1e-9:
        profile = dataclasses.replace(profile, g4_limit_h=float(c["dark"]), g4_type="hard" if g4.hard else "soft", g4_na=False)
    r = score_with_range(res.score_inputs, res.score_scenarios, profile, c["params"], edit_mission(c["mission"], c["slope"]),
                         c["weights"], c_sup=sc.confidence.c_sup, dem=res.dem_confidence, short_period=C.short_period(sc),
                         feasible_fraction=sc.feasible_start_fraction)
    for f in _WINDOW_FIELDS:
        setattr(r, f, getattr(sc, f))
    if res.observer.mode is HorizonMode.FAR_FIELD:      # el re-puntuado vuelve a decir «esfera lisa»: mismos textos que el pipeline
        from lsi import pipeline
        pipeline._far_field_score_texts(r)              # ponytail: helper privado del pipeline, igual que ui.cache._countdowns
    return r


def stars(score: float) -> str:
    n = max(0, min(5, round(score / 20.0)))
    return "★" * n + "☆" * (5 - n) + f" ({n} de 5)"


def sensitivity(res, c, base_score: float, base_verdict: str, partial: bool) -> list[dict]:
    """Variaciones de un parámetro cada vez: peso ±10 puntos, umbrales; devuelve filas con el cambio de nota/estado."""
    out = []

    def add(label, **chg):
        try:
            r = run(res, {**c, **chg})
        except ValueError:
            return
        v = r.verdict
        out.append({"Qué cambia": label, "Nota": round(r.score, 1), "Cambio": round(r.score - base_score, 1),
                    "Estado": v + (" (cambia)" if v != base_verdict else "")})

    w = normalize_weights(c["weights"] or c["profile"].weights)
    for k in KEYS:
        if k == "terrain" and partial:
            continue
        for d in (+0.10, -0.10):
            if w[k] + d >= 0:
                add(f"Peso de «{NAMES[k]}» {100 * d:+.0f} puntos", weights={**w, k: w[k] + d})
    p, prof = c["params"], c["profile"]
    dh = prof.d_half_h or p.d_half_h
    add(f"Umbral solar f₀ = {C.fmt_num(min(p.f0 + 0.1, p.f1 - 0.05), 2)}", params=dataclasses.replace(p, f0=min(p.f0 + 0.1, p.f1 - 0.05)))
    add(f"Mitad de noche D½ ×2 ({2 * dh:g} h)", profile=dataclasses.replace(prof, d_half_h=2 * dh))
    add(f"Mitad de noche D½ ÷2 ({dh / 2:g} h)", profile=dataclasses.replace(prof, d_half_h=dh / 2))
    if not partial:
        for d in (+5.0, -5.0):
            add(f"Pendiente máxima de aterrizaje {max(c['slope'] + d, 0.0):g}°", slope=max(c["slope"] + d, 0.0))
        add(f"Pendiente de nota cero σ₁ = {p.sigma1_deg + 5:g}°", params=dataclasses.replace(p, sigma1_deg=p.sigma1_deg + 5))
    if c["dark"] is not None:
        for d in (+12.0, -6.0):
            add(f"Noche máxima sin RHU {max(c['dark'] + d, 1.0):g} h", dark=max(c["dark"] + d, 1.0))
    return out


# ------------------------------------------------------------------------------------------------ texto llano
def gate_plain(g, i: ScoreInputs) -> str:
    """Frase llana de una puerta, con el valor/límite que midió el motor (``g.value``/``g.limit``)."""
    n = lambda x, d=1: C.fmt_num(x, d)    # noqa: E731
    soft = "" if g.hard else " Es una puerta blanda: no rechaza el sitio, solo pone reservas."
    if g.status is GateStatus.NOT_APPLICABLE:
        return {"G0": "Este perfil no exige Sol en la llegada: la puerta no se aplica.",
                "G1": "Esta misión no depende de paneles solares: la puerta no se aplica."}.get(
                    g.id, "Este perfil no fija una noche máxima: la puerta no se aplica.")
    if g.id == "G0":
        return ("El Sol se ve en la fecha de inicio: se puede llegar con luz." if g.status is GateStatus.PASS else
                "Se llegaría de noche: el Sol no se ve en la fecha de inicio. Otra fecha de inicio puede resolverlo.")
    if g.id == "G1":
        if g.status is GateStatus.FAIL:
            return (f"El Sol casi no ilumina este punto ({n(100 * i.f_sun)} % del tiempo de la ventana de misión con alguna parte del Sol visible, mínimo "
                    f"{C.fmt_num(100 * g.limit, 0)} %): una misión solar no tendría energía.")
        return f"Hay luz solar suficiente ({i.f_sun:.0%} del tiempo; mínimo {C.fmt_num(100 * g.limit, 0)} %)."
    if g.id == "G2":
        if g.status is GateStatus.NO_DATA:
            return "No se puede comprobar la pendiente: no hay mapa de terreno en este punto."
        if g.status is GateStatus.FAIL:
            return (f"El suelo es demasiado inclinado para posarse: pendiente típica alta {n(i.slope_p90_deg)}° "
                    f"frente a un máximo de {g.limit:g}°.")
        return f"La pendiente ({n(i.slope_p90_deg)}°) no supera el máximo de {g.limit:g}°."
    if g.id == "G3":
        if g.status is GateStatus.NO_DATA:
            return ("Faltan datos fiables del terreno (sin mapa del lugar, fuera de él, o con demasiado horizonte "
                    "desconocido): el resultado es orientativo.")
        return "Hay datos de terreno suficientes alrededor del punto."
    if g.id == "G4":
        lb = " (como mínimo: la noche toca el borde de la ventana)" if i.d_max_truncated else ""
        if g.status is GateStatus.FAIL:
            return (f"La noche más larga dura {n(i.d_max_h)} h{lb}, más de las {g.limit:g} h que aguanta la misión "
                    f"sin calentador nuclear (RHU).{soft}")
        return f"La noche más larga ({n(i.d_max_h)} h) cabe en las {g.limit:g} h que aguanta la misión."
    if g.id == "G5":
        if g.status is GateStatus.FAIL:
            return (f"El panel y el montaje elegidos dan potencia útil solo el {n(100 * g.value, 0)} % de la ventana, menos del "
                    f"{n(100 * g.limit, 0)} % exigido (puerta de potencia útil{'' if C.state.is_public() else ', G5'}).{soft}")
        return f"El panel da potencia útil el {n(100 * g.value, 0)} % de la ventana (mínimo {n(100 * g.limit, 0)} %)."
    if g.id == "G7":
        if g.status is GateStatus.NO_DATA:
            return "No se puede comprobar el hueco sin enlace: no hay red de estaciones elegida o no hay ventana de misión."
        if g.status is GateStatus.FAIL:
            return (f"Hay un hueco de {n(g.value)} h seguidas sin enlace posible, más de las {g.limit:g} h que tolera este perfil "
                    f"(sin contacto no se puede comandar ni recuperar un fallo).{soft}")
        return f"El mayor hueco sin enlace posible ({n(g.value)} h) cabe en las {g.limit:g} h que tolera este perfil."
    # G6
    what = "enlace posible (Tierra con margen de elevación y alguna estación de la red viendo la Luna)" if i.link_mode else "Tierra visible (geometría)"
    if g.status is GateStatus.FAIL:
        return (f"La ventana continua de {what} dura como mucho {n(g.value)} h, menos de las {g.limit:g} h necesarias para comunicar "
                f"(sigue siendo geometría, sin presupuesto de enlace).{soft}")
    return f"Hay una ventana continua de {what} de {n(g.value)} h (mínimo {g.limit:g} h)."


def sentence(r) -> str:
    """Frase del veredicto; en APTO/CONDICIONAL añade qué resta más a la nota."""
    t = C.verdict_sentence(r)
    return t + (f" Lo que más resta a la nota es {WEAK_PLAIN[r.weakest_key]}." if r.verdict in ("APTO", "CONDICIONAL") else "")


def window_section(res, req, edited: bool, public: bool) -> None:
    """Ventana de misión: duración, tramo evaluado, mejor fecha, fechas factibles, ventanas alternativas y días sostenibles."""
    sc = res.score
    if sc.mission_days is None:
        st.info("Este perfil no tiene ventana de misión: la nota y las puertas se evalúan sobre todo el periodo elegido.", icon=":material/event:")
        return
    period_d = res.metrics.period_s / 86400.0
    if C.short_period(sc):
        st.warning(f"El periodo ({period_d:g} d) es menor que la misión ({sc.mission_days:g} d): no cabe una ventana completa, así que el "
                   f"veredicto es SIN DATOS (o NO APTO si ya falla una puerta dura). Alarga el periodo a {sc.mission_days:g} d o más en la barra lateral.",
                   icon=":material/event_busy:")
    elif sc.best_start_utc is None:
        st.warning("Ninguna fecha de inicio del periodo supera las puertas duras: la ventana mostrada es la de menor violación y no es apta.",
                   icon=":material/event_busy:")
    if public:
        return
    a, b, c3, d = st.columns(4)
    a.metric("Duración de la misión", f"{sc.mission_days:g} d", border=False,
             help="Personalizada en la barra lateral." if req.mission_days is not None else "La del perfil de misión (cámbiala en la barra lateral).")
    b.metric("Mejor fecha de inicio", C.fmt_utc_short(sc.best_start_utc) if sc.best_start_utc else "ninguna", border=False,
             help="La de mayor nota entre las fechas que superan todas las puertas duras.")
    c3.metric("Fechas de inicio factibles", "—" if sc.feasible_start_fraction is None else f"{sc.feasible_start_fraction:.0%}", border=False,
              help=f"Sobre {sc.n_starts} fechas probadas; si es menos del 10 % la ventana es frágil." if sc.n_starts else None)
    d.metric("Periodo analizado", f"{period_d:g} d", border=False)
    st.caption(f"Ventana evaluada: {C.fmt_utc_short(sc.window_start_utc)} → {C.fmt_utc_short(sc.window_end_utc)}"
               + (" (menor violación, no apta)" if sc.best_start_utc is None and not C.short_period(sc) else "")
               + (" · la ventana y los porcentajes salen con los umbrales del perfil; los umbrales editados solo re-puntúan esta ventana" if edited else ""))
    sd = sc.max_sustainable_days
    if sd is not None:
        cens = (f" Con el {sd.censored_fraction:.0%} de los inicios no hay noche letal en el periodo: ahí el valor es una cota inferior (≥)."
                if sd.censored_fraction > 0 else "")
        st.markdown(f"**Días sostenibles:** hasta la primera noche de más de {sd.limit_h:g} h, un lander aguanta una mediana de "
                    f"**{C.fmt_num(sd.median_days, 1)} d** (máximo {C.fmt_num(sd.best_days, 1)} d si empieza el {C.fmt_utc_short(sd.best_start_utc)}).{cens}")
    if sc.top_windows:
        st.markdown("**Mejores ventanas (no solapadas):**")
        st.dataframe([{"Inicio": C.fmt_utc_short(w.start_utc), "Fin": C.fmt_utc_short(w.end_utc), "Nota": round(w.score, 1),
                       "Rango": "—" if w.score_min is None else f"{C.fmt_num(w.score_min, 0)} – {C.fmt_num(w.score_max, 0)}",
                       "Noche máx. (h)": round(w.d_max_h, 1), "Sol (%)": round(100 * w.f_sun, 1)} for w in sc.top_windows],
                     hide_index=True, width="stretch")


# ------------------------------------------------------------------------------------------------ callbacks
def _reset() -> None:
    for k in [k for k in st.session_state if str(k).startswith(("_sc_w_", "_sc_p_"))]:
        del st.session_state[k]


# ------------------------------------------------------------------------------------------------ página
def main() -> None:
    ctx = cache.get_context()
    st.title("Idoneidad del emplazamiento")
    base = S.request_or_stop()
    public, expert = S.is_public(), S.is_expert()
    canon = S.get_str(K.SCORE_PROFILE, "lander_solar_no_rhu")
    profiles = profiles_from_config(ctx.cfg["score"])
    if canon not in profiles:
        canon = "lander_solar_no_rhu"
    params0 = params_from_config(ctx.cfg["score"])
    valid = {f.name for f in dataclasses.fields(params0)}
    params0 = dataclasses.replace(params0, **{k: v for k, v in (S.get_state(K.SCORE_PARAMS) or {}).items() if k in valid})

    pid = canon
    if not public:
        pid = st.selectbox("Perfil de misión", list(profiles), index=list(profiles).index(canon), key=f"_sc_profile_{canon}",
                           format_func=lambda k: profiles[k].label,
                           help="Cambia los pesos, los umbrales y la duración de la misión (si no la fijas en la barra lateral). "
                                "Cambiar de perfil recalcula la ventana; mover pesos y umbrales re-puntúa al instante.")
    # activa el rango; los pesos se aplican aquí. El perfil entra en la petición porque la ventana de misión depende de él.
    req = dataclasses.replace(base, score_profile_id=pid, with_uncertainty=True, score_weights=None)
    res, err = cache.try_analysis(req)
    if err:
        C.warnings_band()
        C.show_error(err)
        st.stop()
        return
    C.warnings_band(res)
    C.result_header(res)

    profile0 = profile = profiles[pid]
    from lsi import pipeline      # herencia de pendiente del rover: API pública si existe; si no, la privada (M5: pedido al núcleo)
    mission = getattr(pipeline, "mission_profile", None) or pipeline._mission
    mission = mission(ctx, profile.mission_profile_id)
    gates0 = {g.id: g for g in res.score.gates}
    t2 = mission.thresholds.get("max_landing_slope_deg") if mission else None
    t4 = mission.thresholds.get("max_dark_h_no_nuclear") if mission else None
    g2, g4 = gates0.get("G2"), gates0.get("G4")
    slope_def = float(g2.limit) if g2 is not None and g2.limit is not None else params0.g2_max_slope_deg
    dark_def = float(g4.limit) if g4 is not None and g4.limit is not None and g4.status is not GateStatus.NOT_APPLICABLE else None

    # --- pesos y umbrales editables
    params, slope, dark = params0, slope_def, dark_def
    w_def = normalize_weights(profile.weights)
    w_edit = None
    if not public:
        with st.expander("Pesos del perfil (editables)", expanded=True):
            st.caption("Los pesos se normalizan solos para sumar 100 %. El score se recalcula al instante.")
            cols = st.columns(4)
            raw = {k: cols[i].slider(NAMES[k], 0, 100, int(round(100 * w_def[k])), 5, key=f"_sc_w_{canon}_{pid}_{k}")
                   for i, k in enumerate(KEYS)}
            if sum(raw.values()) <= 0:
                st.error("Al menos un peso debe ser mayor que 0.")
                st.stop()
                return
            w_edit = {k: v / 100.0 for k, v in raw.items()}
            eff = normalize_weights(w_edit)
            st.caption("Pesos efectivos: " + " · ".join(f"{NAMES[k]} {eff[k]:.0%}" for k in KEYS))
            st.button("Restablecer pesos y umbrales", on_click=_reset, icon=":material/restart_alt:")
        with st.expander("Umbrales y supuestos (a calibrar con un experto de misión)"):
            st.caption("Todos los umbrales están **a calibrar**; «Confianza» es la etiqueta del catálogo de misiones.")
            rows = [{"Umbral": "Pendiente máxima de aterrizaje (°)", "Valor": f"{slope_def:g}",
                     "Confianza": t2.confidence if t2 is not None else "a calibrar"},
                    {"Umbral": "Rampa solar f₀ → f₁", "Valor": f"{params0.f0:g} → {params0.f1:g}", "Confianza": "a calibrar"},
                    {"Umbral": "Pendiente σ₀ → σ₁ (nota 1 → 0, °)", "Valor": f"{params0.sigma0_deg:g} → {params0.sigma1_deg:g}", "Confianza": "a calibrar"},
                    {"Umbral": "Mitad de noche D½ (h)", "Valor": f"{profile.d_half_h or params0.d_half_h:g}", "Confianza": "a calibrar"},
                    {"Umbral": C.plain_gate_name("Sol mínimo (puerta G1)"), "Valor": f"{params0.g1_min_sun_fraction:g}", "Confianza": "a calibrar"}]
            if dark_def is not None:
                rows.append({"Umbral": "Noche máxima sin RHU (h)", "Valor": f"{dark_def:g}" + ("" if g4.hard else " (blanda)"), "Confianza": t4.confidence if t4 is not None else "a calibrar (perfil)"})
            st.dataframe(rows, hide_index=True, width="stretch")
            if expert:
                a, b, c3 = st.columns(3)
                slope = a.number_input("Pendiente máxima de aterrizaje (°) · a calibrar", 0.0, 60.0, slope_def, 0.5, key=f"_sc_p_slope_{pid}")
                if dark_def is not None:
                    dark = b.number_input("Noche máxima sin RHU (h) · a calibrar", 1.0, 400.0, dark_def, 1.0, key=f"_sc_p_dark_{pid}")
                d_half = c3.number_input("Mitad de noche D½ (h) · a calibrar", 1.0, 400.0, float(profile.d_half_h or params0.d_half_h), 1.0,
                                         key=f"_sc_p_dhalf_{pid}")
                a, b, c3 = st.columns(3)
                f0 = a.number_input("f₀ rampa solar · a calibrar", 0.0, 0.95, params0.f0, 0.05, key="_sc_p_f0")
                f1 = b.number_input("f₁ rampa solar · a calibrar", 0.05, 1.0, params0.f1, 0.05, key="_sc_p_f1")
                g1 = c3.number_input("Sol mínimo G1 · a calibrar", 0.0, 0.5, params0.g1_min_sun_fraction, 0.01, key="_sc_p_g1")
                a, b, _ = st.columns(3)
                s0 = a.number_input("σ₀ (°) · a calibrar", 0.0, 40.0, params0.sigma0_deg, 1.0, key="_sc_p_s0")
                s1 = b.number_input("σ₁ (°) · a calibrar", 1.0, 60.0, params0.sigma1_deg, 1.0, key="_sc_p_s1")
                if f0 >= f1 or s0 >= s1:
                    st.error("Se necesita f₀ < f₁ y σ₀ < σ₁: se usan los valores por defecto.")
                else:
                    params = dataclasses.replace(params0, f0=f0, f1=f1, sigma0_deg=s0, sigma1_deg=s1, g1_min_sun_fraction=g1)
                    profile = dataclasses.replace(profile, d_half_h=d_half)

    cfg = {"profile": profile, "params": params, "mission": mission, "weights": w_edit, "slope": slope, "dark": dark}
    r = run(res, cfg)
    v = r.verdict
    nominal = res.score_inputs
    edited = (w_edit is not None and any(abs(normalize_weights(w_edit)[k] - w_def[k]) > 1e-9 for k in KEYS)) or         slope != slope_def or dark != dark_def or params != params0 or         (profile.d_half_h or params.d_half_h) != (profile0.d_half_h or params0.d_half_h)
    plain = {g.id: gate_plain(g, nominal) for g in r.gates}

    # --- titular
    color, icon, tl = C.VERDICT[v]
    with st.container(border=True):
        a, b = st.columns([1, 2])
        a.metric("Nota de 0 a 100" if public else "Idoneidad (0–100)", f"{C.fmt_num(r.score, 0)}" + (" (parcial)" if r.partial else ""),
                 help=C.term_help("Score"), border=False)
        a.caption(C.range_text(r) + (" · con pesos o umbrales editados" if edited else ""))
        with b:
            C.verdict_badge(r)
            if r.partial:
                st.badge("Sin datos de terreno", icon=":material/terrain:", color="orange",
                         help=C.partial_score_help(res.observer.mode))
            if public:
                st.markdown(f"**Semáforo: {tl}**" + (f" · {stars(r.score)}" if v in ("APTO", "CONDICIONAL")
                                                      else " · sin estrellas (nota no concluyente)"))
            st.markdown(sentence(r))
            gap_line = C.link_gap_line(res)
            if gap_line:
                st.markdown(":material/signal_disconnected: " + gap_line)
            if not public:
                st.caption(f"Motivo (por puertas y escenarios, no por la nota): {C.plain_reason(r.verdict_reason)}")
            C.uncertainty_note(res, key="_sc_unc_btn")
            C.range_prompt([res], key="_sc_rng_btn", can_activate=not req.with_uncertainty)
            if r.confidence:
                C.confidence_badge(r.confidence.level)
    C.energy_summary(r, ctx, req.lat_deg, req)
    if v == "APTO":
        st.info(C.CERTIFY_NOTE, icon=":material/gavel:")
    st.info("**Una ayuda a la decisión, no una certificación de sitio de aterrizaje.** " + STANDARD_WARNINGS_ES[WarningCode.SCORE_UNCALIBRATED]
            + " " + STANDARD_WARNINGS_ES[WarningCode.ROCKS_NOT_MODELED], icon=":material/balance:")
    C.public_note("La nota resume en un número lo buena que es esta zona: mucha luz del Sol, noches cortas, enlace posible con la Tierra y suelo llano. "
                  "El veredicto (apto, con reservas, no apto o sin datos) sale de unas comprobaciones mínimas, no de la nota. "
                  "Fíjate también en el rango: si es ancho, la nota es poco segura.")

    # --- ventana de misión y mejor fecha
    st.subheader("Ventana de misión" if not public else "Cuándo mejor aterrizar")
    if public:
        st.markdown(C.best_date_sentence(res.score))
    window_section(res, req, edited, public)
    C.scope_table(res, profile0.label)

    # --- modo parcial
    if r.partial:
        with st.container(border=True):
            st.markdown("**:material/terrain: Modo parcial: sin datos de terreno**")
            far = res.observer.mode is HorizonMode.FAR_FIELD
            st.markdown(("Aquí solo hay el DEM polar de 80 m (relieve aproximado), no el de 5 m. **Falta:** la **pendiente** de aterrizaje y el relieve fino "
                         "(la nota de terreno no se evalúa); el Sol y la Tierra sí usan el horizonte de 80 m, optimista cerca de crestas. "
                         "La nota es optimista: el rango" if far else
                         "Aquí no hay mapa de alturas (DEM), así que el lugar se trata como una esfera lisa. **Falta:** el relieve que tapa el Sol "
                         "y la Tierra, y la **pendiente** del suelo (la nota de terreno no se evalúa). La luz y la noche están calculadas sin montañas, "
                         "por eso la nota es optimista: el rango") + f" {C.fmt_num(r.score_min, 0)}–{C.fmt_num(r.score_max, 0)} va de «terreno pésimo» a «terreno perfecto». "
                        "No es comparable con sitios que sí tienen DEM.")

    # --- desglose
    st.subheader("Desglose")
    subs = [{"Subindicador": s.label, "Valor medido": "—" if s.value is None else f"{C.fmt_num(s.value, 2)} {s.unit}",
             "Nota (0–1)": C.fmt_num(s.s, 2), "Peso": f"{s.weight:.0%}", "Penalización": C.fmt_num(max(0.0, s.penalty_pct), 0, "%"),
             "Nota si fuera 1": C.fmt_num(s.score_if_one, 0)} for s in r.subscores]
    pw = res.power_summary
    panel = next((p for p in ctx.panels.panels if p.id == req.panel_id), None)
    if panel is not None and r.energy_basis != "panel":
        subs.append({"Subindicador": f"Energía con «{panel.name}» (informativo)",
                     "Valor medido": f"{C.fmt_num(pw.pct_of_max, 0)} % del máximo" if pw is not None else "panel no calculable",
                     "Nota (0–1)": "—", "Peso": "no puntúa", "Penalización": "—", "Nota si fuera 1": "—"})
    if r.confidence:
        subs.append({"Subindicador": "Confianza de los datos (informativo)", "Valor medido": f"{r.confidence.level.value} (C = {C.fmt_num(r.confidence.c, 2)})",
                     "Nota (0–1)": "—", "Peso": "no puntúa", "Penalización": "—", "Nota si fuera 1": "—"})
    st.dataframe(subs, hide_index=True, width="stretch")
    st.caption(("El subindicador solar usa la energía efectiva del panel y montaje elegidos (potencia media y fracción de la ventana con potencia útil), "
                "no solo la fracción de Sol visible. " if r.energy_basis == "panel" else
                "No hay panel elegido: el subindicador solar usa la fracción de tiempo con Sol visible. ")
               + f"Eslabón más débil: **{NAMES[r.weakest_key]}**. " + C.SUN_FRACTION_NOTE)
    lw = res.link_window or res.link
    if nominal.link_mode:
        st.info(f"**La nota de «Tierra / enlace» usa el ENLACE posible, no la Tierra visible.** s_Tierra = mín(1, f_enlace / f_ref) × continuidad (el factor de continuidad baja la nota cuando hay huecos largos sin enlace): "
                f"f_enlace = {C.fmt_pct(nominal.f_earth, 1)} del tiempo de la ventana, con Tierra a más de "
                f"{C.fmt_num(lw.min_earth_elevation_deg, 0, '°') if lw else 'el margen del perfil'} sobre el horizonte del lander Y alguna estación "
                f"de la red {lw.network_label if lw else ''} viendo la Luna; f_ref = {C.fmt_pct(nominal.f_earth_ref, 1)} (Tierra sobre un horizonte sin relieve, solo curvatura, con el "
                "mismo margen y SIN red). La red es un factor externo que penaliza igual a todos los sitios: una sola estación baja la nota, el DSN casi no.",
                icon=":material/satellite_alt:")
    else:
        st.caption("Sin red de estaciones elegida: la nota de Tierra usa solo la visibilidad geométrica (la Tierra sobre el horizonte).")
    alt = (f"Desglose del score {C.fmt_num(r.score, 0)} ({C.range_text(r).lower()}): " +
           "; ".join(f"{s.label} sin datos (no evaluado)" if not math.isfinite(s.s) else
                     f"{s.label} {C.fmt_num(100 * s.s, 0)} sobre 100 con peso {s.weight:.0%}" for s in r.subscores) + ".")
    det = [f"{s.label}: valor {C.fmt_num(s.value, 2)} {s.unit}, nota {C.fmt_num(s.s, 2)}, peso {s.weight:.0%}, "
           f"penalización {C.fmt_num(max(0.0, s.penalty_pct), 0)} %, nota si fuera 1: {C.fmt_num(s.score_if_one, 0)}" for s in r.subscores]
    if public:
        with st.expander("Ver el desglose en un gráfico"):
            C.accessible_chart(score_plot.score_bars(r), alt, key="_sc_bars_p", details=det)
    else:
        t1, t2_ = st.tabs(["Barras", "Radar"])
        with t1:
            C.accessible_chart(score_plot.score_bars(r), alt, key="_sc_bars", details=det)
        with t2_:
            C.accessible_chart(score_plot.score_radar(r), alt, key="_sc_radar", details=det)

    # --- puertas
    st.subheader("Puertas")
    st.caption("Una puerta no pone la nota a cero: cambia el estado y se explica el motivo. Una puerta **dura** que falla rechaza el sitio; una "
               "**blanda** solo lo deja con reservas. Se miden sobre la ventana de misión (el Sol al inicio, sobre la fecha de inicio). "
               "Las puertas están **a calibrar**.")
    if any(g.id == "G5" for g in r.gates) and not S.is_public():
        st.caption(C.G5_NOTE)
    if any(g.id == "G7" for g in r.gates) and not S.is_public():
        st.caption("**G7, hueco máximo sin enlace:** el tramo más largo de la ventana de misión sin enlace posible no debe superar el límite del perfil "
                   "(supuesto, no publicado). G6 mide la ventana de enlace continua mínima; G7 el peor hueco.")
    for g, row in zip(r.gates, C.gate_rows(r.gates)):
        if g.id == "G7":
            row["Puerta"] = C.plain_gate_name("Hueco máximo sin enlace (G7)")
        with st.container(border=True):
            st.markdown(f"**{row['Puerta']}** · {row['Estado']} · {'dura' if g.hard else 'blanda'}")
            st.write(plain[g.id])
            if g.value is not None or g.limit is not None:
                st.caption(f"Valor {row['Valor']} · límite {row['Límite']} · margen {row['Margen']} (negativo = incumple)")
            if not public:
                st.caption(f"Detalle técnico ({g.id}): {g.reason}")
    if nominal.f_earth <= 1e-9:
        st.warning("Sin enlace posible: " + ("con la red y el margen elegidos nunca hay enlace" if nominal.link_mode else "la Tierra nunca se ve")
                   + " desde este punto en la ventana analizada (geometría, no un presupuesto de enlace).",
                   icon=":material/signal_disconnected:")

    # --- confianza
    st.subheader("Confianza de los datos")
    conf = r.confidence
    if conf:
        a, b, c3, d = st.columns(4)
        a.metric("Confianza global C", f"{C.fmt_num(conf.c, 2)}", help="C = mínimo de las tres siguientes; solo etiqueta, no entra en la nota.")
        b.metric("Cobertura del horizonte", f"{C.fmt_num(conf.c_cov, 2)}")
        c3.metric("Soporte del DEM", f"{C.fmt_num(conf.c_sup, 2)}", help="Mínimo de huecos sin medida (c_gap), error vertical (c_err) y estabilidad del horizonte (c_hz).")
        d.metric("Estrechez del rango", f"{C.fmt_num(conf.c_range, 2)}")
        C.confidence_badge(conf.level)
        if min(conf.c, conf.c_cov, conf.c_sup, conf.c_range) < 0.005:
            st.caption("Un 0,00 no es un fallo de cálculo: la confianza global es el mínimo de los factores y al menos uno está en su suelo.")
        low = min(("cobertura", conf.c_cov), ("soporte", conf.c_sup), ("rango", conf.c_range), key=lambda t: t[1])[0]
        if res.observer.mode is HorizonMode.DEM:
            eff = res.dem_confidence.effective_resolution_m if res.dem_confidence else 30.0
            st.markdown(f"Sale **{conf.level.value}** porque el factor limitante es el **{low}**. El mapa de terreno (DEM) tiene píxeles de 5 m, "
                        f"pero **alrededor del 90 % son interpolados** (sin medida láser propia); la resolución efectiva es de unos {C.fmt_num(eff, 0, 'm')}. "
                        "Eso no invalida la nota, pero los detalles finos (rocas, cráteres pequeños, pendiente local) no están medidos y la nota puede "
                        "tener errores que el rango no recoge. La etiqueta usa la escala calibrada (soporte = el peor entre huecos sin medida, error "
                        "vertical y estabilidad del horizonte): ya distingue unos puntos de otros, no sale «baja» por sistema.")
        elif res.observer.mode is HorizonMode.FAR_FIELD:
            st.markdown("Con el relieve aproximado de 80 m no hay datos de terreno fino (ni pendiente de aterrizaje): la confianza es baja por construcción.")
        else:
            st.markdown("Sin DEM no hay datos de terreno: la confianza es baja por construcción.")
        if not public and res.dem_confidence:
            dc = res.dem_confidence
            st.caption(f"DEM en {dc.radius_m:g} m: píxeles con medida {dc.f_obs:.0%} · g90 {C.fmt_num(dc.g90_m, 1, 'm')} · e90 {C.fmt_num(dc.e90_m, 2, 'm')} · "
                       f"horizonte abierto {dc.open_azimuth_fraction:.0%}" + (f" · estabilidad del horizonte c_hz {C.fmt_num(dc.c_hz, 2)}" if dc.c_hz is not None else "") + f". Umbrales de la etiqueta (alta ≥ {params.conf_high}, media ≥ {params.conf_medium}): a calibrar.")

    # --- sensibilidad
    if not public:
        st.subheader("¿Qué cambiaría el resultado?")
        st.caption("Se varía un solo parámetro cada vez (pesos ±10 puntos, umbrales) y se vuelve a puntuar. Todo está a calibrar: sirve para ver "
                   "cuánto depende la nota de decisiones aún no fijadas.")
        rows = sensitivity(res, cfg, r.score, v, r.partial)
        if rows:
            st.dataframe(rows, hide_index=True, width="stretch")
            top = max(rows, key=lambda x: abs(x["Cambio"]))
            flips = [x["Qué cambia"] for x in rows if "(cambia)" in x["Estado"]]
            st.markdown(f"Lo que más mueve la nota: **{top['Qué cambia']}** ({top['Cambio']:+.1f} puntos). " +
                        (f"Cambia el estado: {'; '.join(flips)}." if flips else "Ninguna de estas variaciones cambia el estado."))
    if expert:
        with st.expander("Supuestos y fórmula"):
            st.markdown("S = 100 · A^(1−λ) · Q^λ, con A = Π max(sᵢ, ε)^wᵢ (media geométrica ponderada, no compensatoria, sᵢ saturados en su umbral) y "
                        "Q la misma media con indicadores sin saturar (λ = resolution_weight); ε = 0,01. El estado no sale de S: lo deciden las puertas "
                        "y los escenarios. Rango = extremos de los escenarios de "
                        "incertidumbre (cobertura, σz, discretización); en modo parcial, terreno entre ε y 1.")
            for a in r.assumptions:
                st.markdown(f"- {a}")


main()
