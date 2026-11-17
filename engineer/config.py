"""Configuracion del AI Race Engineer."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def get_default_config_path() -> Path:
    env_cfg = os.environ.get("ENGINEER_CONFIG", "").strip()
    if env_cfg:
        return Path(env_cfg)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        p_exe = exe_dir / "config.json"
        if p_exe.exists():
            return p_exe
        p_parent = exe_dir.parent / "config.json"
        if p_parent.exists():
            return p_parent
        return p_exe
    pkg_parent = Path(__file__).resolve().parent.parent
    local_cfg = pkg_parent / "config.json"
    if local_cfg.exists():
        return local_cfg
    if pkg_parent.name == "app":
        root_cfg = pkg_parent.parent / "config.json"
        if root_cfg.exists():
            return root_cfg
    return local_cfg


DEFAULT_CONFIG_PATH = get_default_config_path()


@dataclass
class EngineerConfig:
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    language: str = "en"                  # "en" (English) or "es" (Espanol)
    engineer_name: str = "Marc"           # Race engineer name
    driver_name: str = "Driver"           # Fallback name if custom driver
    engineer_persona: str = "balanced"    # "balanced" (Marc), "gp" (Red Bull), "bono" (Mercedes), "ferrari" (Maranello), "canero" (Sargento)
    voice_mode: str = "wake_word"         # "wake_word" (Wake word + F9), "always_on", "ptt_only"
    wake_words: str = "engineer, marc, bono, box, radio"
    ptt_key: str = "f9"                   # Tecla Push-To-Talk opcional (ademas de palabra clave)
    udp_host: str = "0.0.0.0"
    udp_port: int = 20777
    udp_forward: list[str] = field(default_factory=list)   # p.ej. ["127.0.0.1:20778"] para SimHub
    voice_es: str = "es-ES-AlvaroNeural"
    voice_en: str = "en-GB-RyanNeural"
    voice_rate: str = "+25%"              # Ritmo agil y natural de ingeniero de muro de boxes
    radio_effect: float = 0.85            # 0.0 (limpio) a 1.0 (efecto radio F1 completo)
    radio_beep_enabled: bool = True       # Activar o desactivar el pitido de apertura/cierre de radio F1 TV
    radio_beep_style: str = "f1_tv_real"  # "f1_tv_real" (Oficial F1 TV Real), "f1_tv_synth" (Sintético Anterior), "fia_pitwall" (Chirp FIA), "classic_v10" (Walkie Clásico), "off"
    radio_bg_enabled: bool = True         # Activar o desactivar sonido de fondo en la radio del ingeniero
    radio_bg_style: str = "pitwall_f1_flyby"  # "pitwall_f1_flyby" (F1 pasando por recta + muro), "pit_garage_guns" (Garaje + pistolas box), "pitwall_telemetry" (Solo muro sutil), "off"
    radio_bg_level: float = 0.65          # Nivel del sonido de fondo (0.0 a 1.0)
    volume: float = 1.0                   # Volumen de salida (0.1 a 1.5)
    proactive_callouts: bool = True       # Avisar automaticamente de Safety Car, penalizaciones, etc.
    mic_device: int | None = None         # None = microfono por defecto del sistema
    hud_mode: str = "auto"                # "auto" (Sale al hablar/recibir radio), "always" (Siempre fijo en el HUD), "off" (Oculto)
    hud_x: int = -1                       # Coordenada X en pantalla (-1 = automatico a la derecha del HUD de F1 25)
    hud_y: int = -1                       # Coordenada Y en pantalla (-1 = automatico debajo del crono de F1 25)
    hud_hold_seconds: float = 6.5         # Segundos que permanece visible tras terminar de hablar el ingeniero
    hud_opacity: float = 0.94             # Opacidad del HUD en el juego (0.50 a 1.00)
    hud_identity_mode: str = "auto"       # "auto" (Segun el coche que lleves en telemetria) o "custom" (Siempre tu nombre/equipo elegido)
    hud_custom_team: str = "Ferrari"      # Escuderia para el estilo visual cuando hud_identity_mode == "custom" o sin telemetria
    hud_custom_number: int = 16           # Dorsal personalizado (1-99)
    mfd_enabled: bool = False             # Permitir que el ingeniero pulse teclas MFD en el juego por voz (desactivado por defecto)
    auto_mfd_ai: bool = False             # La IA te aconseja por radio en vez de modificar teclas automaticamente
    mfd_box_key: str = "b"                # Tecla en F1 25 para Solicitar Parada en Boxes (Box This Lap)
    mfd_tyre_key: str = "t"               # Tecla en F1 25 para Cambiar Compuesto Siguiente en el MFD
    mfd_brake_up_key: str = "page_up"     # Tecla para subir reparto de frenada (+ delante)
    mfd_brake_down_key: str = "page_down" # Tecla para bajar reparto de frenada (- atras)
    mfd_diff_up_key: str = "home"         # Tecla para subir diferencial en aceleracion
    mfd_diff_down_key: str = "end"        # Tecla para bajar diferencial (mas traccion)
    mfd_ers_key: str = "e"                # Tecla para cambiar modo de despliegue ERS / Overtake
    mfd_wing_up_key: str = "insert"       # Tecla para subir angulo de aleron delantero en parada
    mfd_wing_down_key: str = "delete"     # Tecla para bajar angulo de aleron delantero en parada

    controller_ptt_enabled: bool = True   # Activar Push-To-Talk desde cualquier volante o mando USB
    controller_ptt_button: int = -1       # -1 = Cualquier boton del volante/mando, o 0-31 para boton especifico
    obs_overlay_port: int = 8088          # Puerto local para OBS Browser Source (http://localhost:8088/overlay)
    streamer_mode: bool = False           # Modo streamer (filtro limpio familiar sin tacos)

    @property
    def wake_word_list(self) -> list[str]:
        words = [w.strip().lower() for w in self.wake_words.split(",") if w.strip()]
        if self.engineer_name:
            eng_norm = self.engineer_name.strip().lower()
            if eng_norm and eng_norm not in words:
                words.insert(0, eng_norm)
        for kw in ("engineer", "ingeniero", "ingenieur", "ingénieur", "ingegnere", "engenheiro", "box", "bono", "radio"):
            if kw not in words:
                words.append(kw)
        return words

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
