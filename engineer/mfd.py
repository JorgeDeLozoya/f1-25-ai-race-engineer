"""Controlador de MFD (Panel Multifuncion) por voz para F1 25 / F1 26 sin soltar el volante."""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time

log = logging.getLogger("mfd")

# Mapa de nombres de teclas a Virtual-Key Codes (VK) de Windows
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


def tap_key(key_name: str, hold_s: float = 0.055, repeat: int = 1, gap_s: float = 0.08) -> bool:
    """Envía una pulsacion de teclado con ScanCode real para que F1 25 (DirectInput) la detecte."""
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
