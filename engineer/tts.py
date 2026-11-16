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

# Pronunciaciones fonéticas naturales para el motor de voz neural en español (Álvaro / Elvira)
_DRIVER_PHONETICS_ES = [
    (r"\bRussell\b", "Rásel"),
    (r"\bRUSSELL\b", "Rásel"),
    (r"\bLeclerc\b", "Leclér"),
    (r"\bLECLERC\b", "Leclér"),
    (r"\bVerstappen\b", "Verstápen"),
    (r"\bVERSTAPPEN\b", "Verstápen"),
    (r"\bHamilton\b", "Jámilton"),
    (r"\bHAMILTON\b", "Jámilton"),
    (r"\bHulkenberg\b", "Júlkenberg"),
    (r"\bHülkenberg\b", "Júlkenberg"),
    (r"\bHULKENBERG\b", "Júlkenberg"),
    (r"\bRicciardo\b", "Rikiardo"),
    (r"\bRICCIARDO\b", "Rikiardo"),
    (r"\bDoohan\b", "Dújan"),
    (r"\bDOOHAN\b", "Dújan"),
    (r"\bLawson\b", "Lóson"),
    (r"\bLAWSON\b", "Lóson"),
    (r"\bAntonelli\b", "Antoneli"),
    (r"\bANTONELLI\b", "Antoneli"),
    (r"\bHadjar\b", "Jádjar"),
    (r"\bHADJAR\b", "Jádjar"),
    (r"\bBearman\b", "Béarman"),
    (r"\bBEARMAN\b", "Béarman"),
    (r"\bTsunoda\b", "Zunoda"),
    (r"\bTSUNODA\b", "Zunoda"),
    (r"\bOcon\b", "Ocón"),
    (r"\bOCON\b", "Ocón"),
    (r"\bGasly\b", "Gaslí"),
    (r"\bGASLY\b", "Gaslí"),
    (r"\bPiastri\b", "Piástri"),
    (r"\bPIASTRI\b", "Piástri"),
    (r"\bBottas\b", "Bótas"),
    (r"\bBOTTAS\b", "Bótas"),
    (r"\bStroll\b", "Strol"),
    (r"\bSTROLL\b", "Strol"),
    (r"\bAlbon\b", "Albón"),
    (r"\bALBON\b", "Albón"),
    (r"\bMagnussen\b", "Mágnusen"),
    (r"\bMAGNUSSEN\b", "Mágnusen"),
    (r"\bBortoleto\b", "Bortoléto"),
    (r"\bBORTOLETO\b", "Bortoléto"),
    (r"\bSauber\b", "Sáuber"),
    (r"\bSAUBER\b", "Sáuber"),
    (r"\bAlpine\b", "Alpín"),
    (r"\bALPINE\b", "Alpín"),
    (r"\bMcLaren\b", "Maclaren"),
    (r"\bMCLAREN\b", "Maclaren"),
    (r"\bHaas\b", "Jas"),
    (r"\bHAAS\b", "Jas"),
    (r"\bRed Bull\b", "Red Bul"),
    (r"\bWilliams\b", "Uíliams"),
]


def naturalize_for_speech(text: str, lang: str) -> str:
    """Adapta abreviaturas y numeros de telemetria para que el TTS hable fluido como en F1."""
    s = text.strip()
    # Quitar parentesis y dos puntos que provocan pausas largas en el TTS
    s = s.replace("(", ", ").replace(")", "").replace(":", ",")
    if lang.lower().startswith("en"):
        # English F1 telemetry
        s = re.sub(r"\bS1\b", "Sector 1", s)
        s = re.sub(r"\bS2\b", "Sector 2", s)
        s = re.sub(r"\bS3\b", "Sector 3", s)
        s = re.sub(r"[+-]?\b0\.(\d{1,3})\s*(?:seconds?|s\b)", r"0 point \1 seconds", s)
        s = re.sub(r"\+(\d+)\.(\d+)s\b", r"\1 point \2 seconds", s)
        s = re.sub(r"\b(\d+)\.(\d+)s\b", r"\1 point \2 seconds", s)
        s = re.sub(r"\b(\d{1,2})\.(\d{3})s\b", r"\1 point \2", s)
        s = re.sub(r"\bL(\d{1,2})\b", r"lap \1", s)
    else:
        # Español F1 telemetría
        # 1. Nombres de sectores para evitar que diga "ese uno"
        s = re.sub(r"\bS1\b", "Sector uno", s)
        s = re.sub(r"\bS2\b", "Sector dos", s)
        s = re.sub(r"\bS3\b", "Sector tres", s)

        # 2. Decimales de segundo: 0.22 segundos, 0.14s, 0.20s, 0.05 segundos -> décimas / centésimas
        def _sub_zero_sec(m: re.Match) -> str:
            dec = m.group(1)
            val = int(dec)
            if len(dec) == 1:
                return "una décima de segundo" if val == 1 else f"{val} décimas de segundo"
            elif len(dec) == 2:
                d1, d2 = int(dec[0]), int(dec[1])
                if d1 == 0:
                    return f"{val} centésimas de segundo"
                elif d2 == 0:
                    return "una décima de segundo" if d1 == 1 else f"{d1} décimas de segundo"
                else:
                    return f"{val} centésimas de segundo"
            elif len(dec) == 3:
                return f"{int(dec[:2])} centésimas de segundo"
            return f"cero con {dec} segundos"

        s = re.sub(r"[+-]?\b0\.(\d{1,3})\s*(?:segundos?|s\b)", _sub_zero_sec, s)

        # 3. Parciales con milésimas: 29.410s -> 29 con 410
        s = re.sub(r"\b(\d{1,2})\.(\d{3})s\b", r"\1 con \2", s)

        # 4. Gaps normales: +1.4s -> 1 con 4 segundos
        s = re.sub(r"\+0\.0s\b", "", s)
        s = re.sub(r"\+(\d+)\.(\d+)s\b", r"\1 con \2 segundos", s)
        s = re.sub(r"\b(\d+)\.(\d+)s\b", r"\1 con \2 segundos", s)

        s = re.sub(r"\bP(\d{1,2})\b", lambda m: _POS_ES.get(m.group(1), f"posición {m.group(1)}"), s)
        s = re.sub(r"\bV(\d{1,2})\b", r"vuelta \1", s)
        s = re.sub(r"\b(\d+)%\b", r"\1 por ciento", s)

        # 5. Correcciones fonéticas de nombres propios para que Álvaro suene natural
        for pattern, replacement in _DRIVER_PHONETICS_ES:
            s = re.sub(pattern, replacement, s)

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


VOICE_MAP: dict[str, str] = {
    "en": "en-GB-RyanNeural",
    "es": "es-ES-AlvaroNeural",
    "de": "de-DE-KillianNeural",
    "fr": "fr-FR-HenriNeural",
    "it": "it-IT-DiegoNeural",
    "pt": "pt-BR-AntonioNeural",
}


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
        code = lang.lower()[:2]
        if code == "en":
            voice = self.cfg.voice_en
        elif code == "es":
            voice = self.cfg.voice_es
        else:
            voice = VOICE_MAP.get(code, self.cfg.voice_en)
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
