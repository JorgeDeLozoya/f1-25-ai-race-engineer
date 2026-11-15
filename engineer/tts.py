"""Sintesis de voz neuronal (Edge TTS) + reproduccion con efecto de radio F1."""
from __future__ import annotations

import asyncio
import io
import logging
import re
import threading
from pathlib import Path

import edge_tts
import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import EngineerConfig
from .radio_fx import apply_f1_radio_effect

log = logging.getLogger("tts")

_POS_ES = {
    "1": "primero", "2": "segundo", "3": "tercero", "4": "cuarto", "5": "quinto",
    "6": "sexto", "7": "séptimo", "8": "octavo", "9": "noveno", "10": "décimo",
}


def naturalize_for_speech(text: str, lang: str) -> str:
    """Adapta abreviaturas y numeros de telemetria para que el TTS hable fluido como en F1."""
    s = text.strip()
    # Quitar parentesis y dos puntos que provocan pausas largas en el TTS
    s = s.replace("(", ", ").replace(")", "").replace(":", ",")
    if lang.lower().startswith("en"):
        # "+2.8s" -> "2.8"
        s = re.sub(r"\+(\d+)\.(\d+)s\b", r"\1 point \2", s)
        s = re.sub(r"\b(\d+)\.(\d+)s\b", r"\1 point \2 seconds", s)
    else:
        # En espanol, "+2.8s" -> "2 con 8", "P1" -> "primero"
        s = re.sub(r"\+0\.0s\b", "", s)
        s = re.sub(r"\+(\d+)\.(\d+)s\b", r"\1 con \2", s)
        s = re.sub(r"\b(\d+)\.(\d+)s\b", r"\1 con \2 segundos", s)
        s = re.sub(
            r"\bP(\d{1,2})\b",
            lambda m: _POS_ES.get(m.group(1), f"posición {m.group(1)}"),
            s,
        )
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


def tighten_pauses(samples: np.ndarray, sr: int, max_pause_ms: int = 75) -> np.ndarray:
    """Recorta silencios largos generados por el TTS para dar urgencia de radio de carrera."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    win = max(1, int(sr * 0.015))  # bloques de 15 ms
    max_silent_blocks = max(2, int((max_pause_ms / 1000.0) / 0.015))
    n_blocks = len(samples) // win
    if n_blocks < 4:
        return samples

    kept = []
    silent_run = 0
    for i in range(n_blocks):
        chunk = samples[i * win:(i + 1) * win]
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        if rms < 0.008:
            silent_run += 1
            if silent_run <= max_silent_blocks:
                kept.append(chunk)
        else:
            silent_run = 0
            kept.append(chunk)
    rem = samples[n_blocks * win:]
    if len(rem):
        kept.append(rem)
    return np.concatenate(kept).astype(np.float32) if kept else samples


class RadioSpeaker:
    """Convierte texto a voz en espanol o ingles y lo reproduce como radio F1."""

    def __init__(self, cfg: EngineerConfig):
        self.cfg = cfg
        self._lock = threading.Lock()
        self.is_speaking = False

    def speak(self, text: str, lang: str = "es", save_wav: Path | str | None = None,
              blocking: bool = True) -> None:
        clean = naturalize_for_speech(text, lang)
        if not clean:
            return
        voice = self.cfg.voice_en if lang.lower().startswith("en") else self.cfg.voice_es
        try:
            mp3_bytes = asyncio.run(self._synthesize(clean, voice, self.cfg.voice_rate))
            samples, sr = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
            samples = tighten_pauses(samples, sr, max_pause_ms=70)
            radio_audio = apply_f1_radio_effect(
                samples,
                sr,
                intensity=self.cfg.radio_effect,
                volume=self.cfg.volume,
                beep_enabled=self.cfg.radio_beep_enabled,
                beep_style=self.cfg.radio_beep_style,
                bg_enabled=self.cfg.radio_bg_enabled,
                bg_style=self.cfg.radio_bg_style,
                bg_level=self.cfg.radio_bg_level,
            )
            if save_wav:
                sf.write(str(save_wav), radio_audio, sr)
            with self._lock:
                self.is_speaking = True
                try:
                    sd.play(radio_audio, samplerate=sr, blocking=blocking)
                finally:
                    self.is_speaking = False
        except Exception as e:
            log.error("Error en TTS / reproduccion de radio: %s", e)

    @staticmethod
    async def _synthesize(text: str, voice: str, rate: str) -> bytes:
        comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="-2Hz")
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)
