"""Controlador autonomo del MFD y Telemetria Activa en el juego (F1 25 / F1 26)."""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import logging
import os
import threading
import time

from .config import EngineerConfig

log = logging.getLogger("mfd")

VK_MAP: dict[str, int] = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46,
    "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52,
    "s": 0x53, "t": 0x54, "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "page_up": 0x21, "prior": 0x21, "pgup": 0x21,
    "page_down": 0x22, "next": 0x22, "pgdn": 0x22,
    "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "space": 0x20, "return": 0x0D, "enter": 0x0D, "tab": 0x09,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62, "numpad3": 0x63,
    "numpad4": 0x64, "numpad5": 0x65, "numpad6": 0x66, "numpad7": 0x67,
    "numpad8": 0x68, "numpad9": 0x69,
}

KEYEVENTF_KEYUP = 0x0002

COMPOUND_CYCLE_ORDER = ["Soft", "Medium", "Hard", "Intermediate", "Wet"]


def tap_key(key_name: str, hold_s: float = 0.055, repeat: int = 1, gap_s: float = 0.085) -> bool:
    """Envia pulsaciones reales con ScanCode DirectInput a F1 25."""
    if os.name != "nt":
        return False
    clean = (key_name or "").strip().lower()
    vk = VK_MAP.get(clean)
    if not vk and len(clean) == 1:
        vk = ord(clean.upper())
    if not vk:
        return False

    def _worker() -> None:
        try:
            user32 = ctypes.windll.user32
            scan = user32.MapVirtualKeyW(vk, 0)
            for i in range(max(1, repeat)):
                user32.keybd_event(vk, scan, 0, 0)
                time.sleep(hold_s)
                user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
                if i + 1 < repeat:
                    time.sleep(gap_s)
        except Exception as e:
            log.debug("MFD key tap error: %s", e)

    threading.Thread(target=_worker, daemon=True, name="mfd-key").start()
    return True


@dataclass
class PitWallOverrides:
    """Estado activo de ajustes aplicados por la IA del ingeniero sobre el coche y la parada."""
    active_plan: str = "A"                      # "A", "B", "C"
    pit_lap_override: int = 0                   # Vuelta de parada fijada por el Plan activo o el piloto (0 = auto)
    compound_override: str | None = None        # "Soft", "Medium", "Hard", "Intermediate", "Wet"
    compound_override_es: str | None = None     # "blando", "medio", "duro", "intermedio", "lluvia"
    brake_bias_delta: int = 0                   # Ajuste aplicado por la IA (ej. -2% o +2%)
    diff_pct: int = 60                          # Diferencial en aceleracion (50% - 100%)
    ers_mode_override: str | None = None        # "overtake", "high", "medium", "harvest"
    ers_mode_override_es: str | None = None     # "adelantamiento", "alto", "medio", "recarga"
    front_wing_delta: int = 0                   # Clics de aleron delantero programados para el pit stop
    box_requested_in_game: bool = False         # Si se ha enviado la orden de Box al MFD del juego
    last_ai_action_es: str = "Muro en modo automático monitorizando telemetría."
    last_ai_action_en: str = "Pit wall AI actively monitoring telemetry."

    def reset(self) -> None:
        self.active_plan = "A"
        self.pit_lap_override = 0
        self.compound_override = None
        self.compound_override_es = None
        self.brake_bias_delta = 0
        self.diff_pct = 60
        self.ers_mode_override = None
        self.ers_mode_override_es = None
        self.front_wing_delta = 0
        self.box_requested_in_game = False
        self.last_ai_action_es = "Muro en modo automático monitorizando telemetría."
        self.last_ai_action_en = "Pit wall AI actively monitoring telemetry."


# Instancia compartida para que tanto strategy.py como brain.py y gui.py lean los cambios en vivo
LIVE_OVERRIDES = PitWallOverrides()


def apply_plan_to_game_and_strategy(
    plan: str,
    cfg: EngineerConfig,
    cur_lap: int,
    total_laps: int,
    base_ideal_lap: int,
    current_tyre: str,
    rain_pct: int,
) -> dict[str, int | str]:
    """Ajusta automaticamente la vuelta de parada, el neumatico en el MFD del juego y el mapa ERS segun el Plan A/B/C."""
    p = plan.upper().strip()
    LIVE_OVERRIDES.active_plan = p
    laps_rem = max(0, total_laps - cur_lap)

    if p == "B":
        # Plan B: Undercut agresivo / Ataque -> adelantamos la parada 2 vueltas (o proxima vuelta si ya paso la ventana) y montamos goma blanda/media agresiva
        if base_ideal_lap > cur_lap:
            target_lap = max(cur_lap + 1, base_ideal_lap - 2)
        else:
            target_lap = min(total_laps, cur_lap + 1)
        if current_tyre == "Soft" and laps_rem > 10:
            comp, comp_es = "Medium", "medio"
        else:
            comp, comp_es = "Soft", "blando"
        LIVE_OVERRIDES.pit_lap_override = target_lap
        LIVE_OVERRIDES.compound_override = comp
        LIVE_OVERRIDES.compound_override_es = comp_es
        LIVE_OVERRIDES.ers_mode_override = "overtake"
        LIVE_OVERRIDES.ers_mode_override_es = "adelantamiento"
        LIVE_OVERRIDES.last_ai_action_es = f"IA aplicó Plan B: Parada ajustada a V{target_lap}, goma {comp_es} en MFD y ERS en Adelantamiento."
        LIVE_OVERRIDES.last_ai_action_en = f"AI applied Plan B: Pit stop set to L{target_lap}, {comp} selected on MFD & Overtake ERS."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_tyre_key, repeat=1)
            tap_key(cfg.mfd_ers_key, repeat=1)
            if target_lap <= cur_lap + 1 and not LIVE_OVERRIDES.box_requested_in_game:
                tap_key(cfg.mfd_box_key, repeat=1)
                LIVE_OVERRIDES.box_requested_in_game = True
        return {"pit_lap": target_lap, "comp": comp, "comp_es": comp_es, "ers": "overtake", "ers_es": "adelantamiento"}

    if p == "C":
        # Plan C: Overcut / Alargar stint / Esperar lluvia -> retrasamos la parada 3 vueltas y preparamos Duro o Intermedio
        if base_ideal_lap >= cur_lap:
            target_lap = min(total_laps - 1, base_ideal_lap + 3)
        else:
            target_lap = min(total_laps - 1, cur_lap + 3)
        if rain_pct >= 30:
            comp, comp_es = "Intermediate", "intermedio"
        elif current_tyre == "Hard":
            comp, comp_es = "Medium", "medio"
        else:
            comp, comp_es = "Hard", "duro"
        LIVE_OVERRIDES.pit_lap_override = target_lap
        LIVE_OVERRIDES.compound_override = comp
        LIVE_OVERRIDES.compound_override_es = comp_es
        LIVE_OVERRIDES.ers_mode_override = "medium"
        LIVE_OVERRIDES.ers_mode_override_es = "medio (ahorro)"
        LIVE_OVERRIDES.last_ai_action_es = f"IA aplicó Plan C: Stint alargado hasta V{target_lap}, goma {comp_es} preparada en MFD."
        LIVE_OVERRIDES.last_ai_action_en = f"AI applied Plan C: Stint extended to L{target_lap}, {comp} pre-selected on MFD."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_tyre_key, repeat=2)
        return {"pit_lap": target_lap, "comp": comp, "comp_es": comp_es, "ers": "medium", "ers_es": "medio (ahorro)"}

    # Plan A: Estrategia equilibrada optima calculada por telemetria
    target_lap = base_ideal_lap if base_ideal_lap >= cur_lap else min(total_laps, cur_lap + 2)
    comp, comp_es = ("Medium", "medio") if current_tyre != "Medium" else ("Hard", "duro")
    LIVE_OVERRIDES.active_plan = "A"
    LIVE_OVERRIDES.pit_lap_override = target_lap
    LIVE_OVERRIDES.compound_override = comp
    LIVE_OVERRIDES.compound_override_es = comp_es
    LIVE_OVERRIDES.ers_mode_override = "medium"
    LIVE_OVERRIDES.ers_mode_override_es = "medio"
    LIVE_OVERRIDES.last_ai_action_es = f"IA aplicó Plan A: Ventana óptima V{target_lap}, goma {comp_es} y mapa equilibrado."
    LIVE_OVERRIDES.last_ai_action_en = f"AI applied Plan A: Optimal window L{target_lap}, {comp} tyre & balanced map."
    if cfg.mfd_enabled and cfg.auto_mfd_ai:
        tap_key(cfg.mfd_tyre_key, repeat=1)
    return {"pit_lap": target_lap, "comp": comp, "comp_es": comp_es, "ers": "medium", "ers_es": "medio"}


def auto_adjust_car_mfd(
    issue: str,
    cfg: EngineerConfig,
    base_brake_bias: int = 56,
) -> dict[str, int | str]:
    """Ejecuta automaticamente los cambios en el MFD del coche cuando el piloto reporta un problema de conduccion."""
    if issue == "understeer":
        # Cuesta girar / subviraje -> retrasar reparto de frenada (-2%), bajar diferencial (-5%), +1 clic aleron en box
        LIVE_OVERRIDES.brake_bias_delta = max(-6, LIVE_OVERRIDES.brake_bias_delta - 2)
        LIVE_OVERRIDES.diff_pct = max(50, LIVE_OVERRIDES.diff_pct - 5)
        LIVE_OVERRIDES.front_wing_delta = min(4, LIVE_OVERRIDES.front_wing_delta + 1)
        new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
        LIVE_OVERRIDES.last_ai_action_es = f"IA Auto-Setup (Subviraje): Frenada al {new_bb}%, Diferencial al {LIVE_OVERRIDES.diff_pct}% y +{LIVE_OVERRIDES.front_wing_delta} alerón."
        LIVE_OVERRIDES.last_ai_action_en = f"AI Auto-Setup (Understeer): Brake bias {new_bb}%, Diff {LIVE_OVERRIDES.diff_pct}% & +{LIVE_OVERRIDES.front_wing_delta} front wing."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_brake_down_key, repeat=2)
            tap_key(cfg.mfd_diff_down_key, repeat=1)
            tap_key(cfg.mfd_wing_up_key, repeat=1)
        return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "wing": LIVE_OVERRIDES.front_wing_delta}

    if issue == "oversteer":
        # Sobreviraje / patina de atras -> adelantar frenada (+2%), abrir diferencial (-5%)
        LIVE_OVERRIDES.brake_bias_delta = min(6, LIVE_OVERRIDES.brake_bias_delta + 2)
        LIVE_OVERRIDES.diff_pct = max(50, LIVE_OVERRIDES.diff_pct - 5)
        new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
        LIVE_OVERRIDES.last_ai_action_es = f"IA Auto-Setup (Tracción/Sobreviraje): Frenada subida al {new_bb}% y Diferencial abierto al {LIVE_OVERRIDES.diff_pct}%."
        LIVE_OVERRIDES.last_ai_action_en = f"AI Auto-Setup (Oversteer): Brake bias forward to {new_bb}% & Diff opened to {LIVE_OVERRIDES.diff_pct}%."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_brake_up_key, repeat=2)
            tap_key(cfg.mfd_diff_down_key, repeat=1)
        return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "wing": LIVE_OVERRIDES.front_wing_delta}

    if issue == "poor_braking":
        # Frena poco / cuesta parar el coche -> adelantar reparto (+1%) si iba muy atras o retrasar (-1%) si bloquea delante, y subir freno motor/diferencial
        delta_step = -1 if (base_brake_bias + LIVE_OVERRIDES.brake_bias_delta) >= 57 else 1
        LIVE_OVERRIDES.brake_bias_delta = max(-6, min(6, LIVE_OVERRIDES.brake_bias_delta + delta_step))
        LIVE_OVERRIDES.diff_pct = min(85, LIVE_OVERRIDES.diff_pct + 5)
        new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
        LIVE_OVERRIDES.last_ai_action_es = f"IA Auto-Setup (Frenada): Reparto ajustado al {new_bb}% y retención de diferencial al {LIVE_OVERRIDES.diff_pct}%."
        LIVE_OVERRIDES.last_ai_action_en = f"AI Auto-Setup (Braking): Brake bias set to {new_bb}% & diff locking to {LIVE_OVERRIDES.diff_pct}%."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_brake_up_key if delta_step > 0 else cfg.mfd_brake_down_key, repeat=1)
            tap_key(cfg.mfd_diff_up_key, repeat=1)
        return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "wing": LIVE_OVERRIDES.front_wing_delta}

    if issue == "more_power":
        # Necesito mas energia / potencia / velocidad punta -> activar modo Overtake / Alto en ERS
        LIVE_OVERRIDES.ers_mode_override = "overtake"
        LIVE_OVERRIDES.ers_mode_override_es = "adelantamiento (máxima potencia)"
        LIVE_OVERRIDES.last_ai_action_es = "IA Auto-ERS: Mapa de Adelantamiento (Máxima Potencia) activado en el MFD."
        LIVE_OVERRIDES.last_ai_action_en = "AI Auto-ERS: Overtake (Max Power) deployment activated on MFD."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_ers_key, repeat=1)
        new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
        return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "ers": "overtake"}

    if issue == "save_battery":
        # Me quedo sin bateria / ahorrar energia -> modo Harvest / Recarga
        LIVE_OVERRIDES.ers_mode_override = "harvest"
        LIVE_OVERRIDES.ers_mode_override_es = "recarga (ahorro de batería)"
        LIVE_OVERRIDES.last_ai_action_es = "IA Auto-ERS: Modo Recarga activado en el MFD (+15% batería/vuelta)."
        LIVE_OVERRIDES.last_ai_action_en = "AI Auto-ERS: Harvest mode activated on MFD (+15% battery/lap)."
        if cfg.mfd_enabled and cfg.auto_mfd_ai:
            tap_key(cfg.mfd_ers_key, repeat=2)
        new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
        return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "ers": "harvest"}

    new_bb = max(50, min(70, base_brake_bias + LIVE_OVERRIDES.brake_bias_delta))
    return {"brake_bias": new_bb, "diff": LIVE_OVERRIDES.diff_pct, "wing": LIVE_OVERRIDES.front_wing_delta}
