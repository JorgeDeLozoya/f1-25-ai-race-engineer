"""Configuracion del AI Race Engineer."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class EngineerConfig:
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    language: str = "es"                  # "es" (Espanol) o "en" (English) seleccionable manualmente
    engineer_name: str = "Marc"           # Nombre del ingeniero
    driver_name: str = "Jorge"            # Como te llama el ingeniero
    voice_mode: str = "wake_word"         # "wake_word" (Palabra clave + F9), "always_on" (Directo sin palabra clave), "ptt_only" (Solo F9)
    wake_words: str = "ingeniero, marc, engineer, bono, box"
    ptt_key: str = "f9"                   # Tecla Push-To-Talk opcional (ademas de palabra clave)
    udp_host: str = "0.0.0.0"
    udp_port: int = 20777
    udp_forward: list[str] = field(default_factory=list)   # p.ej. ["127.0.0.1:20778"] para SimHub
    voice_es: str = "es-ES-AlvaroNeural"
    voice_en: str = "en-GB-RyanNeural"
    voice_rate: str = "+25%"              # Ritmo agil y natural de ingeniero de muro de boxes
    radio_effect: float = 0.85            # 0.0 (limpio) a 1.0 (efecto radio F1 completo)
    volume: float = 1.0                   # Volumen de salida (0.1 a 1.5)
    proactive_callouts: bool = True       # Avisar automaticamente de Safety Car, penalizaciones, etc.
    mic_device: int | None = None         # None = microfono por defecto del sistema
    hud_mode: str = "auto"                # "auto" (Sale al hablar/recibir radio), "always" (Siempre fijo en el HUD), "off" (Oculto)
    hud_x: int = -1                       # Coordenada X en pantalla (-1 = automatico a la derecha del HUD de F1 25)
    hud_y: int = -1                       # Coordenada Y en pantalla (-1 = automatico debajo del crono de F1 25)
    hud_hold_seconds: float = 6.5         # Segundos que permanece visible tras terminar de hablar el ingeniero

    @property
    def wake_word_list(self) -> list[str]:
        return [w.strip().lower() for w in self.wake_words.split(",") if w.strip()]

    def resolved_api_key(self) -> str:
        return (self.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")).strip()

    @classmethod
    def load(cls, path: Path | str | None = None) -> "EngineerConfig":
        p = Path(path) if path else Path(os.environ.get("ENGINEER_CONFIG", DEFAULT_CONFIG_PATH))
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**valid)
            except Exception:
                pass
        cfg = cls()
        cfg.save(p)
        return cfg

    def save(self, path: Path | str | None = None) -> None:
        p = Path(path) if path else Path(os.environ.get("ENGINEER_CONFIG", DEFAULT_CONFIG_PATH))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
