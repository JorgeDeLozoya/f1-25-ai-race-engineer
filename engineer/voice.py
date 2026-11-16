"""Escucha continua por voz (Wake Word + STT manual ES/EN con Vosk) + tecla PTT opcional."""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import EngineerConfig
from .radio_fx import play_ack_beep

log = logging.getLogger("voice")
SetLogLevel(-1)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
VOSK_MODELS = {
    "es": (
        "vosk-model-small-es-0.42",
        "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
    ),
    "en": (
        "vosk-model-small-en-us-0.15",
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    ),
}


def ensure_vosk_model(lang: str) -> Path:
    """Descarga el modelo ligero de voz de Vosk (~40 MB) si aun no esta en disco."""
    folder_name, url = VOSK_MODELS["en" if lang == "en" else "es"]
    target = MODELS_DIR / folder_name
    if target.exists():
        return target
    shared_cache = Path(__file__).resolve().parent.parent / "models" / folder_name
    if shared_cache.exists():
        return shared_cache
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = MODELS_DIR / f"{folder_name}.zip"
    log.info("Descargando modelo de voz offline (%s) desde %s ...", lang.upper(), url)
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(MODELS_DIR)
    try:
        zip_path.unlink()
    except OSError:
        pass
    log.info("Modelo de voz %s listo en %s", lang.upper(), target)
    return target


def clean_f1_stt_text(text: str, lang: str = "es") -> str:
    """Corrige errores foneticos tipicos de Vosk en radio de F1 (Plan A/B/C, neumaticos, pilotos, paradas)."""
    if not text:
        return ""
    import re
    s = text.strip()
    if lang == "en":
        s = re.sub(r"\bplan\s+(be|bee|v|vee|me|d|dee)\b", "plan b", s, flags=re.IGNORECASE)
        s = re.sub(r"\bplan\s+(see|sea|si|she|z|zee)\b", "plan c", s, flags=re.IGNORECASE)
        s = re.sub(r"\bplan\s+(hey|eh|ay)\b", "plan a", s, flags=re.IGNORECASE)
        return s

    # Español: normalizar "plan al plan veía el planche" -> "plan a plan b y el plan c"
    s = re.sub(r"\bplan\s+al\s+plan\b", "plan a, plan", s, flags=re.IGNORECASE)
    # Plan C: "plan fe", "planche", "plan che", "plan ce", "plan se", "plan ze", "plan te", "plan si", "plance"
    s = re.sub(
        r"\b(plan\s+(fe|ce|se|ze|che|te|si|pe|hace|sed|ces|c)|planche|plance)\b",
        "plan c",
        s,
        flags=re.IGNORECASE,
    )
    # Plan B: "plan vez", "plan de", "plan ve", "plan be", "plan ver", "plan v", "plan me", "plan bien", "plan veía", "plambe"
    s = re.sub(
        r"\b(plan\s+(vez|ve|be|de|ver|v|me|bien|veía|veia|vi|va|ven|ves|b)|plambe|planbe)\b",
        "plan b",
        s,
        flags=re.IGNORECASE,
    )
    # Plan A: "plan ha", "plan ah", "plan la", "plana"
    s = re.sub(
        r"\b(plan\s+(ha|ah|la|al|a)|plana)\b",
        "plan a",
        s,
        flags=re.IGNORECASE,
    )
    # Limpiar duplicado accidental "plan pasar al plan" -> "pasar al plan"
    s = re.sub(r"\bplan\s+(pasar|pasamos|cambiar|cambiamos|ir|vamos)\s+al\s+plan\b", r"\1 al plan", s, flags=re.IGNORECASE)
    # "lo más rico" -> "neumático"
    s = re.sub(r"\blo\s+m[aá]s\s+rico\b", "neumático", s, flags=re.IGNORECASE)
    # "para de" -> "parada de", "sáenz" -> "sainz"
    s = re.sub(r"\ba\s+para\s+de\b", "la parada de", s, flags=re.IGNORECASE)
    s = re.sub(r"\bpara\s+de\b", "parada de", s, flags=re.IGNORECASE)
    s = re.sub(r"\bs[aá]enz\b", "sainz", s, flags=re.IGNORECASE)
    return s


def extract_after_wake_word(text: str, wake_words: list[str]) -> tuple[bool, str]:
    """Busca si el texto contiene alguna palabra clave y devuelve (encontrado, resto_de_la_frase)."""
    low = text.lower().strip()
    if not low:
        return False, ""
    words = low.split()
    for i, w in enumerate(words):
        clean_w = w.strip(".,;:¡!¿?")
        if clean_w in wake_words:
            rest = " ".join(words[i + 1:]).strip()
            return True, rest
    return False, ""


def list_input_devices() -> list[tuple[int | None, str]]:
    """Devuelve la lista de microfonos disponibles en el sistema para el selector de Ajustes."""
    out: list[tuple[int | None, str]] = [(None, "Sistema por defecto / System Default")]
    try:
        devs = sd.query_devices()
        seen_names: set[str] = set()
        for idx, d in enumerate(devs):
            if int(d.get("max_input_channels", 0)) > 0:
                name = str(d.get("name", f"Mic #{idx}")).strip()
                if name and name not in seen_names:
                    seen_names.add(name)
                    out.append((idx, f"[{idx}] {name[:48]}"))
    except Exception:
        pass
    return out


class VoiceListener(threading.Thread):
    """Hilo de escucha continua con idioma dedicado ('es' o 'en') y palabra clave ('Ingeniero')."""

    def __init__(self, cfg: EngineerConfig, on_query: Callable[[str], None],
                 is_speaking_fn: Callable[[], bool] | None = None):
        super().__init__(daemon=True, name="voice-listener")
        self.cfg = cfg
        self.on_query = on_query
        self.is_speaking_fn = is_speaking_fn or (lambda: False)
        self._stop = threading.Event()
        self._audio_q: queue.Queue[bytes] = queue.Queue(maxsize=80)
        self.armed_until: float = 0.0
        self.ready: bool = False
        self.last_error: str = ""
        self.mic_level: float = 0.0
        self.last_partial: str = ""
        self.last_heard: str = ""

    @property
    def is_armed(self) -> bool:
        return time.time() < self.armed_until

    def stop(self) -> None:
        self._stop.set()

    def _beep_now(self) -> None:
        if self.cfg.radio_beep_enabled and self.cfg.radio_beep_style != "off":
            play_ack_beep(self.cfg.radio_effect, self.cfg.volume, style=self.cfg.radio_beep_style)

    def arm_now(self, seconds: float = 8.0) -> None:
        """Activa la escucha directa sin palabra clave durante unos segundos (ej. tecla PTT)."""
        self.armed_until = time.time() + seconds
        self._beep_now()
        log.info("[RADIO ABIERTA] Escuchando mensaje del piloto durante %.0fs...", seconds)

    def _start_ptt_listener(self) -> None:
        try:
            from pynput import keyboard

            def on_press(key):
                key_name = (self.cfg.ptt_key or "").strip().lower()
                if not key_name:
                    return
                try:
                    k = key.char.lower() if hasattr(key, "char") and key.char else key.name.lower()
                except Exception:
                    return
                if k == key_name and time.time() > self.armed_until:
                    self.arm_now(8.0)

            listener = keyboard.Listener(on_press=on_press, daemon=True)
            listener.start()
            log.info("Tecla Push-To-Talk opcional activa: [%s]", (self.cfg.ptt_key or "F9").upper())
        except Exception as e:
            log.debug("No se pudo iniciar PTT opcional: %s", e)

    def _start_controller_ptt_listener(self) -> None:
        """Escucha eventos de pulsacion de botones en volantes (Logitech, Fanatec, Thrustmaster, Moza) o mandos USB."""
        if not getattr(self.cfg, "controller_ptt_enabled", True):
            return

        def _poller():
            try:
                import ctypes
                from ctypes import wintypes

                class JOYINFOEX(ctypes.Structure):
                    _fields_ = [
                        ("dwSize", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD),
                        ("dwXpos", wintypes.DWORD),
                        ("dwYpos", wintypes.DWORD),
                        ("dwZpos", wintypes.DWORD),
                        ("dwRpos", wintypes.DWORD),
                        ("dwUpos", wintypes.DWORD),
                        ("dwVpos", wintypes.DWORD),
                        ("dwButtons", wintypes.DWORD),
                        ("dwButtonNumber", wintypes.DWORD),
                        ("dwPOV", wintypes.DWORD),
                        ("dwReserved1", wintypes.DWORD),
                        ("dwReserved2", wintypes.DWORD),
                    ]

                winmm = getattr(ctypes.windll, "winmm", None)
                if not winmm:
                    return

                info = JOYINFOEX()
                info.dwSize = ctypes.sizeof(JOYINFOEX)
                info.dwFlags = 0x80  # JOY_RETURNBUTTONS

                last_mask_by_dev: dict[int, int] = {}
                target_btn = int(getattr(self.cfg, "controller_ptt_button", -1))

                while not self._stop.is_set():
                    time.sleep(0.02)  # 50 Hz
                    pressed = False
                    for dev_id in range(4):
                        if winmm.joyGetPosEx(dev_id, ctypes.byref(info)) == 0:
                            mask = info.dwButtons
                            last = last_mask_by_dev.get(dev_id, 0)
                            new_press = mask & (~last)
                            last_mask_by_dev[dev_id] = mask
                            if new_press:
                                if target_btn < 0 or (new_press & (1 << target_btn)):
                                    pressed = True
                                    break
                    if pressed and time.time() > self.armed_until:
                        log.info("[RADIO PTT VOLANTE] Boton pulsado en volante/mando -> Radio abierta")
                        self.arm_now(8.0)
            except Exception as e:
                log.debug("Error en controller PTT listener: %s", e)

        threading.Thread(target=_poller, daemon=True, name="controller-ptt-listener").start()
        log.info("Push-To-Talk para Volante y Mando USB activo")

    def run(self) -> None:
        try:
            recognizers: dict[str, KaldiRecognizer] = {}
            for lg in ("es", "en"):
                mpath = ensure_vosk_model(lg)
                recognizers[lg] = KaldiRecognizer(Model(str(mpath)), 16000)
        except Exception as e:
            self.last_error = f"Error cargando modelo de voz: {e}"
            log.error(self.last_error)
            return

        self._start_ptt_listener()
        self._start_controller_ptt_listener()

        def audio_callback(indata, frames, time_info, status):
            raw = bytes(indata)
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr * arr))) if len(arr) else 0.0
            self.mic_level = min(1.0, rms * 8.5)
            if self.is_speaking_fn():
                return
            try:
                self._audio_q.put_nowait(raw)
            except queue.Full:
                pass

        try:
            with sd.RawInputStream(
                samplerate=16000,
                blocksize=4000,
                device=self.cfg.mic_device,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            ):
                self.ready = True
                log.info(
                    "Microfono activo [%s]. Di (%s) + tu pregunta, o pulsa [%s].",
                    self.cfg.language.upper(),
                    ", ".join(self.cfg.wake_word_list[:4]),
                    self.cfg.ptt_key.upper(),
                )
                while not self._stop.is_set():
                    try:
                        chunk = self._audio_q.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    if self.is_speaking_fn():
                        continue
                    self._process_chunk(chunk, recognizers)
        except Exception as e:
            self.last_error = f"Error de microfono: {e}"
            log.error(self.last_error)

    def _process_chunk(self, chunk: bytes, recognizers: dict[str, KaldiRecognizer]) -> None:
        wake_words = self.cfg.wake_word_list
        now = time.time()
        active_lang = "en" if self.cfg.language == "en" else "es"
        rec = recognizers[active_lang]

        if not rec.AcceptWaveform(chunk):
            pres = json.loads(rec.PartialResult())
            raw_part = (pres.get("partial") or "").strip()
            self.last_partial = clean_f1_stt_text(raw_part, active_lang)
            return

        res = json.loads(rec.Result())
        raw_chosen = (res.get("text") or "").strip()
        chosen = clean_f1_stt_text(raw_chosen, active_lang)
        self.last_partial = ""
        if not chosen:
            return

        self.last_heard = chosen
        mode = (self.cfg.voice_mode or "wake_word").lower()

        # 1. Si ya estaba armado (dijo "Ingeniero" hace un momento o pulso PTT F9)
        if now < self.armed_until:
            _, after = extract_after_wake_word(chosen, wake_words)
            query = after if after else chosen
            if query and query.lower() not in wake_words:
                self.armed_until = 0.0
                rec.Reset()
                self._dispatch(query)
            return

        # 2. Modo solo Push-To-Talk: ignorar si no se ha pulsado F9 / boton PTT
        if mode == "ptt_only":
            return

        # 3. Modo manos libres directo (always_on): cualquier frase de >= 2 palabras entra directo
        if mode == "always_on":
            _, after = extract_after_wake_word(chosen, wake_words)
            query = after if after else chosen
            if len(query.split()) >= 2:
                rec.Reset()
                self._beep_now()
                self._dispatch(query)
            return

        # 4. Modo Wake Word (por defecto): buscar palabra clave ("ingeniero", "marc", etc.)
        found, rest = extract_after_wake_word(chosen, wake_words)
        if found:
            rec.Reset()
            if len(rest.split()) >= 2:
                self._beep_now()
                self._dispatch(rest)
            else:
                self.arm_now(8.0)

    def _dispatch(self, query: str) -> None:
        log.info("[PILOTO]: %s", query)
        threading.Thread(target=self.on_query, args=(query,), daemon=True).start()
