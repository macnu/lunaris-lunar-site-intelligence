"""Graba el vídeo de demo (guion `docs/guion-demo-lunaris.md`) con Playwright + voz Helena (SAPI) + ffmpeg.

Uso (con la app ya arrancada: `python -m streamlit run app.py --server.port 8598 --server.headless true`):
    python scripts/record_demo.py --url http://localhost:8598 --out demo_out

Hace dos pasadas: una de calentamiento SIN grabar (llena la caché de Streamlit; el primer cálculo con rangos es lento) y otra grabada.
Cada escena dura lo que dura su narración. Solo se narra lo que se ve en pantalla; antes de grabar comprueba las cifras (README del guion).
Salida: demo_out/lsi-demo.mp4 (+ narracion.srt). Necesita: playwright, Chrome, imageio-ffmpeg, Windows (voz «Microsoft Helena» es-ES).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

W, H = 1600, 900
LAT_MALAPERT, LON_MALAPERT = "-85.9841", "2.6123"   # mejor punto candidato de Malapert (guion largo, «Coordenadas exactas»)
LAT_TOP1, LON_TOP1 = "-89.5626", "215.4724"      # TOP-1 de Shackleton (4 decimales: lo que admite el campo)

# (id, narración). Solo cifras que se ven en pantalla y que figuran en docs/guion-demo-lunaris.md.
SCENES = [
    ("s1", "Lunar Site Intelligence responde a una pregunta: ¿este punto de la Luna ve el Sol, ve la Tierra, y podría hablar con ella? "
           "Buscamos entre más de nueve mil lugares. Escribimos Malapert. Un nombre es el centro de un rasgo, no un sitio de aterrizaje: "
           "hay que evaluar un punto concreto."),
    ("s2", "Probamos el mejor punto candidato de Malapert, buscando la mejor fecha en el año siguiente: nota noventa y ocho. "
           "Pero mira el recuadro: solo {fechas} fechas de inicio probadas sirven, y por eso el veredicto es condicional, "
           "un candidato con reservas. La nota es la de la mejor fecha, y un candidato no es una certificación."),
    ("s3", "Esto es relieve real de la NASA con foto de la cámara LROC. Las sombras y la posición del Sol y de la Tierra son las de este instante; "
           "la foto es una mezcla de pasadas, no la luz de la fecha. Desde el observador, el Sol está tapado por el horizonte en este instante; "
           "la ventana de catorce días lo tiene visible otras horas."),
    ("s4", "Ahora Shackleton, mismo punto, otra fecha. El doce de diciembre el enlace con las antenas de la NASA es del cien por cien. "
           "El seis de diciembre el Sol es igual de bueno, pero el enlace cae al sesenta y dos por ciento, con un hueco de ciento veintisiete horas "
           "sin comunicaciones. Ver la Tierra no es poder hablar con ella."),
    ("s5", "Esto es geometría y cobertura de estación, no un presupuesto de radio. Nuestros mejores candidatos no coinciden con el mapa de iluminación "
           "publicado, y el relieve de cinco metros tiene resolución efectiva de unos treinta. Por eso decimos candidato, no recomendado. "
           "Lunar Site Intelligence: entender cuándo un lugar ve el Sol, cuándo ve la Tierra y cuánta confianza merece cada resultado."),
]
TAIL_S = 0.8
MAX_GAP_S = 2.5          # tope de las pausas de carga entre escenas en el vídeo final
MEASURED: dict = {}      # cifras leídas de la pantalla durante el calentamiento


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def tts(text: str, wav: Path) -> float:
    """Narración con la voz Helena (es-ES) de Windows; devuelve la duración en s."""
    txt = wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.SelectVoice('Microsoft Helena Desktop'); $s.Rate = 0; "
          f"$s.SetOutputToWaveFile('{wav}'); $s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8)); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


# ---------------------------------------------------------------- acciones de pantalla
def side_input(pg: Page, label_start: str):
    return pg.locator(f'[data-testid="stSidebar"] input[aria-label^="{label_start}"]').first


def set_side(pg: Page, label_start: str, value: str) -> None:
    box = side_input(pg, label_start)
    box.click(force=True)
    box.press("Control+A")
    box.type(value, delay=45)
    box.press("Enter")
    pg.wait_for_timeout(1500)


def goto(pg: Page, base: str, path: str, ready: str) -> None:
    pg.goto(f"{base}/{path}", timeout=60000)
    pg.wait_for_selector(ready, timeout=120000)
    pg.wait_for_timeout(2500)


def wait_calc(pg: Page, timeout_ms: int = 240000) -> None:
    """Espera a que Streamlit termine de calcular (sin el indicador «Running»)."""
    pg.wait_for_timeout(1200)
    pg.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=timeout_ms)
    pg.wait_for_timeout(800)


def use_custom_point(pg: Page, lat: str, lon: str) -> None:
    """Modo Planificador + «Coordenadas personalizadas» con el punto dado (4 decimales)."""
    sel = pg.locator('[data-testid="stSidebar"] [data-baseweb="select"]')
    sel.first.click()
    pg.get_by_role("option", name="Planificador").click()
    pg.wait_for_timeout(2500)
    sel = pg.locator('[data-testid="stSidebar"] [data-baseweb="select"]')
    sel.nth(1).click()
    pg.keyboard.type("Coordenadas")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2500)
    set_side(pg, "Latitud", lat)
    set_side(pg, "Longitud", lon)


def scene_search(pg: Page, base: str, log, start) -> None:
    goto(pg, base, "search", 'input[placeholder*="Shackleton"]')
    start()
    box = pg.locator('input[placeholder*="Shackleton"]').first
    box.click(force=True)
    box.type("Malapert", delay=110)
    box.press("Enter")
    pg.wait_for_timeout(2500)
    pg.mouse.wheel(0, 500)
    pg.wait_for_timeout(1200)
    sel = pg.locator('input[aria-label^="Selected"][aria-label*="Rasgo para ver en detalle"], [data-baseweb="select"]:has(input[aria-label*="Rasgo para ver en detalle"])').first
    sel.click(force=True)
    pg.keyboard.type("Site23 Malapert")
    pg.wait_for_timeout(700)
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(2500)
    btn = pg.get_by_role("button", name=re.compile(r"Evaluar este lugar(?! en esfera)"))
    if btn.count():
        btn.first.scroll_into_view_if_needed()
        pg.wait_for_timeout(900)
        btn.first.click()
        log("  · «Evaluar este lugar» pulsado")
        pg.wait_for_selector('h1:has-text("Horizonte")', timeout=120000)
        pg.wait_for_timeout(2500)
    else:
        log("  · AVISO: no apareció «Evaluar este lugar»; se continúa con el sitio por defecto (Malapert)")


def scene_capacity(pg: Page, base: str, log, start) -> None:
    goto(pg, base, "site_capacity", 'h1:has-text("Capacidad del sitio")')
    use_custom_point(pg, LAT_MALAPERT, LON_MALAPERT)
    set_side(pg, "Inicio", "2026-12-01 00:00")
    set_side(pg, "Días", "366")
    wait_calc(pg)
    pg.mouse.wheel(0, 520)
    pg.wait_for_timeout(1500)
    txt = pg.locator("main, [data-testid='stMain']").first.inner_text()
    m = re.search(r"Fechas de inicio que sirven\s*(\d+) de (\d+)", txt, re.I)
    MEASURED["fechas"] = f"{m.group(1)} de {m.group(2)}" if m else None
    start()
    log(f"  · «Fechas de inicio que sirven»: {MEASURED['fechas']} · CONDICIONAL en pantalla: {'CONDICIONAL' in txt} · nota 98: {'98 / 100' in txt}")


def scene_viewer(pg: Page, base: str, log, start) -> None:
    goto(pg, base, "explorer", 'iframe')
    pg.mouse.wheel(0, 700)
    pg.wait_for_timeout(3500)
    start()
    fr = None
    for f in pg.frames:
        if f.locator("#m-oblique").count():
            fr = f
            break
    if fr is None:
        log("  · AVISO: no se encontró el marco del visor 3D")
        return
    for mode, secs in (("oblique", 3.5), ("observer", 5.5), ("wide", 4.0)):
        try:
            fr.locator(f"#m-{mode}").click(timeout=8000)
        except Exception as e:
            log(f"  · AVISO: no se pudo pulsar #m-{mode}: {type(e).__name__}")
        pg.wait_for_timeout(int(secs * 1000))
    try:
        fr.locator("#m-oblique").click(timeout=5000)
    except Exception:
        pass


def scene_contrast(pg: Page, base: str, log, scene_s: float, start) -> None:
    goto(pg, base, "site_capacity", 'h1:has-text("Capacidad del sitio")')
    use_custom_point(pg, LAT_TOP1, LON_TOP1)
    set_side(pg, "Días", "14")
    set_side(pg, "Inicio", "2026-12-12 00:00")
    wait_calc(pg)
    pg.mouse.wheel(0, 520)
    t12 = pg.locator("main, [data-testid='stMain']").first.inner_text()
    log(f"  · 12-dic: 'APTO' {('APTO' in t12)}; '100' enlace {('100,0 %' in t12)}")
    start()
    pg.wait_for_timeout(int(scene_s * 0.30 * 1000))
    set_side(pg, "Inicio", "2026-12-06 00:00")
    wait_calc(pg)
    t06 = pg.locator("main, [data-testid='stMain']").first.inner_text()
    log(f"  · 06-dic: 'CONDICIONAL' {('CONDICIONAL' in t06)}; '62' {('62,' in t06)}; '127' {('127' in t06)}")


def scene_limits(pg: Page, base: str, log, start) -> None:
    goto(pg, base, "about", "h1")
    start()
    pg.mouse.wheel(0, 380)


def run_flow(pg: Page, base: str, durations: dict, log, t_marks: dict | None) -> None:
    """Cada escena llama a start() cuando ya se ve lo que cuenta su narración; la escena dura hasta el final de su audio."""
    fns = {
        "s1": lambda st: scene_search(pg, base, log, st),
        "s2": lambda st: scene_capacity(pg, base, log, st),
        "s3": lambda st: scene_viewer(pg, base, log, st),
        "s4": lambda st: scene_contrast(pg, base, log, durations["s4"], st),
        "s5": lambda st: scene_limits(pg, base, log, st),
    }
    for k, _ in SCENES:
        log(f"[{k}]")
        t_audio = {}

        def start(k=k, t_audio=t_audio):
            t_audio["t"] = time.monotonic()
            if t_marks is not None:
                t_marks[k] = t_audio["t"]

        fns[k](start)
        t0 = t_audio.get("t", time.monotonic())
        left = durations[k] + TAIL_S - (time.monotonic() - t0)
        if left > 0:
            pg.wait_for_timeout(int(left * 1000))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8598")
    ap.add_argument("--out", default="demo_out")
    ap.add_argument("--no-record", action="store_true", help="solo calienta y comprueba (no graba)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log = lambda m: print(m, flush=True)

    durations, wavs = {}, {}
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        log("== Calentamiento (sin grabar) ==")
        ctx0 = br.new_context(viewport={"width": W, "height": H})
        pg0 = ctx0.new_page()
        run_flow(pg0, a.url, {k: 0.5 for k, _ in SCENES}, log, None)
        ctx0.close()
        if not MEASURED.get("fechas"):
            log("ERROR: no se pudo leer «Fechas de inicio que sirven» de la pantalla; no se graba una narración con cifras sin ver.")
            br.close()
            return 2
        texts = {k: tx.replace("{fechas}", MEASURED["fechas"].replace(" de ", " de ")) for k, tx in SCENES}
        for k, _ in SCENES:
            wavs[k] = out / f"{k}.wav"
            durations[k] = tts(texts[k], wavs[k])
            log(f"{k}: narración {durations[k]:.1f} s")
        if a.no_record:
            br.close()
            return 0
        log("== Grabación ==")
        ctx = br.new_context(viewport={"width": W, "height": H}, record_video_dir=str(out / "raw"), record_video_size={"width": W, "height": H})
        t_ctx = time.monotonic()
        pg = ctx.new_page()
        marks: dict = {}
        run_flow(pg, a.url, durations, log, marks)
        pg.wait_for_timeout(1200)
        vid = pg.video.path()
        ctx.close()
        br.close()

    ff = ffmpeg_exe()
    trim = max(marks["s1"] - t_ctx - 0.4, 0.0)       # quita la carga inicial (aviso de página no encontrada de Streamlit)
    # Línea de tiempo del vídeo bruto (s): cada narración [ini, fin]; los tramos sin narración se aceleran (carga de Streamlit) hasta MAX_GAP_S.
    starts = {k: marks[k] - t_ctx + 0.1 for k, _ in SCENES}
    ends = {k: starts[k] + durations[k] + TAIL_S for k, _ in SCENES}
    raw_end = trim + 1e6
    pieces = []                                       # (ini, fin, factor)
    cur = trim
    for i, (k, _) in enumerate(SCENES):
        gap = starts[k] - cur
        if gap > 0.05:
            pieces.append((cur, starts[k], max(1.0, gap / MAX_GAP_S) if i else 1.0))
        pieces.append((starts[k], ends[k], 1.0))
        cur = ends[k]
    new_start, tnew = {}, 0.0
    vf, vl = [], []
    for i, (a0, a1, f) in enumerate(pieces):
        for k, _ in SCENES:
            if abs(a0 - starts[k]) < 1e-6:
                new_start[k] = tnew
        vf.append(f"[0:v]trim=start={a0:.3f}:end={a1:.3f},setpts=(PTS-STARTPTS)/{f:.4f}[v{i}]")
        vl.append(f"[v{i}]")
        tnew += (a1 - a0) / f
    vf.append("".join(vl) + f"concat=n={len(pieces)}:v=1:a=0[vout]")
    inputs, af, labels = [], [], []
    for i, (k, _) in enumerate(SCENES):
        off_ms = int(new_start[k] * 1000)
        inputs += ["-i", str(wavs[k])]
        af.append(f"[{i + 1}:a]adelay={off_ms}|{off_ms}[a{i}]")
        labels.append(f"[a{i}]")
    af.append("".join(labels) + f"amix=inputs={len(SCENES)}:normalize=0[aout]")
    mp4 = out / "lsi-demo.mp4"
    subprocess.run([ff, "-y", "-i", str(vid), *inputs, "-filter_complex", ";".join(vf + af), "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", str(mp4)],
                   check=True, capture_output=True)
    starts = new_start                                # subtítulos en la línea de tiempo final
    # subtítulos
    def ts(s):
        return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(s % 1 * 1000):03d}"
    srt = []
    for i, (k, _t) in enumerate(SCENES, 1):
        text = texts[k]
        s0 = starts[k]
        srt.append(f"{i}\n{ts(s0)} --> {ts(s0 + durations[k])}\n{text}\n")
    (out / "narracion.srt").write_text("\n".join(srt), encoding="utf-8")
    log(f"LISTO: {mp4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
