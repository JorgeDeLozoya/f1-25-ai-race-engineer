"""Overlay HUD de Radio estilo Retransmision F1 TV (integrado sobre el HUD del juego)."""
from __future__ import annotations

import ctypes
import math
import os
import random
import threading
import time
import tkinter as tk

from .app import RaceEngineerApp
from .radio_fx import play_ack_beep, play_close_beep
from .strategy import analyze_strategy
from .telemetry import lookups as L


def _blend_hex(bg_hex: str, fg_hex: str, alpha: float) -> str:
    """Mezcla dos colores hexadecimales (#RRGGBB) con factor alpha (0.0 a 1.0)."""
    try:
        bg = bg_hex.lstrip("#")
        fg = fg_hex.lstrip("#")
        br, bg_g, bb = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
        fr, fg_g, fb = int(fg[0:2], 16), int(fg[2:4], 16), int(fg[4:6], 16)
        r = int(br + (fr - br) * alpha)
        g = int(bg_g + (fg_g - bg_g) * alpha)
        b = int(bb + (fb - bb) * alpha)
        return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"
    except Exception:
        return fg_hex


class RadioHudOverlay:
    """Caja de Team Radio identica a la retransmision oficial de F1 TV para el HUD del juego."""

    WIDTH = 360
    HEADER_H = 118
    BG_HEADER = "#0D0F14"
    BG_BODY = "#151821"
    BORDER_COLOR = "#252A38"

    def __init__(self, master: tk.Misc, app: RaceEngineerApp):
        self.master = master
        self.app = app
        self.cfg = app.cfg

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=self.BORDER_COLOR)
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-alpha", 0.94)
        except Exception:
            pass

        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._anim_phase = 0.0
        self._visible = False
        self._current_alpha = 0.0
        self._show_until = time.time() + 7.5  # Mostrar al arrancar para confirmar posicion en el HUD
        self._last_seen_dialogue_len = -1
        self._last_partial_text = ""
        self._was_speaking = False
        self._last_hud_beep_ts = 0.0

        # Identidad visual activa (se actualiza sola con la telemetria del coche que conduzcas)
        self._drv_name = self.cfg.driver_name.upper()
        self._team_color = "#FF1E27"
        self._badge_code = "FER"
        self._race_num = 16

        self._build_widgets()
        self._position_initial()
        self.win.after(120, self._apply_win32_noactivate)
        self.win.after(60, self._tick)

    def _build_widgets(self) -> None:
        self.outer = tk.Frame(
            self.win,
            bg=self.BG_BODY,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR,
        )
        self.outer.pack(fill=tk.BOTH, expand=True)

        # 1. Cabecera F1 TV (Nombre Piloto + Logo Escuderia + "RADIO" + Dorsal + Ecualizador)
        self.header_canvas = tk.Canvas(
            self.outer,
            width=self.WIDTH,
            height=self.HEADER_H,
            bg=self.BG_HEADER,
            highlightthickness=0,
            bd=0,
            cursor="fleur",
        )
        self.header_canvas.pack(fill=tk.X)

        # 2. Cuerpo de transcripcion (Piloto alineado a la derecha en color de equipo, Ingeniero a la izquierda en blanco)
        self.body_frame = tk.Frame(self.outer, bg=self.BG_BODY, padx=16, pady=12)
        self.body_frame.pack(fill=tk.BOTH, expand=True)

        self.driver_msg_lbl = tk.Label(
            self.body_frame,
            text="",
            bg=self.BG_BODY,
            fg=self._team_color,
            font=("Segoe UI", 11, "bold italic"),
            justify=tk.RIGHT,
            anchor="e",
            wraplength=self.WIDTH - 36,
            cursor="fleur",
        )
        self.driver_msg_lbl.pack(fill=tk.X, pady=(0, 8))

        self.eng_msg_lbl = tk.Label(
            self.body_frame,
            text=f'"RADIO CONECTADA {self.cfg.driver_name.upper()}, TELEMETRÍA EN VIVO LISTA EN EL MURO."',
            bg=self.BG_BODY,
            fg="#FFFFFF",
            font=("Segoe UI", 11, "bold italic"),
            justify=tk.LEFT,
            anchor="w",
            wraplength=self.WIDTH - 36,
            cursor="fleur",
        )
        self.eng_msg_lbl.pack(fill=tk.X, pady=(0, 2))

        # Permitir arrastrar la caja de radio a cualquier punto del HUD con el raton
        for w in (self.header_canvas, self.body_frame, self.driver_msg_lbl, self.eng_msg_lbl):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_drag_end)

    def _position_initial(self) -> None:
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        # Por defecto: borde derecho, justo debajo del cronometro superior derecho de F1 25
        x = self.cfg.hud_x if self.cfg.hud_x >= 0 else max(20, sw - self.WIDTH - 28)
        y = self.cfg.hud_y if self.cfg.hud_y >= 0 else max(40, int(sh * 0.23))
        x = max(0, min(sw - self.WIDTH, x))
        y = max(0, min(sh - 180, y))
        self.win.geometry(f"{self.WIDTH}x240+{x}+{y}")

    def _apply_win32_noactivate(self) -> None:
        """Evita que el overlay robe el foco del volante/mando/teclado y lo vincula con la ventana de F1 25."""
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            )

            # Buscar la ventana del juego F1 para declararnos como propiedad de su ventana
            found_game_hwnd = None

            def enum_cb(h, _):
                nonlocal found_game_hwnd
                if user32.IsWindowVisible(h):
                    length = user32.GetWindowTextLengthW(h)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buff, length + 1)
                        title = buff.value
                        if any(k in title for k in ("F1 25", "F1® 25", "F1 24", "F1® 24", "F1 26", "F1® 26")):
                            found_game_hwnd = h
                            return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if found_game_hwnd and found_game_hwnd != hwnd:
                # GWLP_HWNDPARENT = -8: vincula la ventana al Z-order del juego
                if hasattr(user32, "SetWindowLongPtrW"):
                    user32.SetWindowLongPtrW(hwnd, -8, found_game_hwnd)
                else:
                    user32.SetWindowLongW(hwnd, -8, found_game_hwnd)
        except Exception:
            pass

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_offset_x = event.x_root - self.win.winfo_x()
        self._drag_offset_y = event.y_root - self.win.winfo_y()

    def _on_drag_motion(self, event: tk.Event) -> None:
        nx = event.x_root - self._drag_offset_x
        ny = event.y_root - self._drag_offset_y
        self.win.geometry(f"+{nx}+{ny}")

    def _on_drag_end(self, _event: tk.Event) -> None:
        self.cfg.hud_x = self.win.winfo_x()
        self.cfg.hud_y = self.win.winfo_y()
        self.cfg.save()

    def trigger_preview(self, duration: float = 7.0) -> None:
        """Fuerza la aparicion inmediata del HUD de Radio en pantalla para previsualizarlo o moverlo."""
        self._show_until = max(self._show_until, time.time() + duration)
        if not self._visible and (self.cfg.hud_mode or "auto").lower() != "off":
            self._show_window()

    def show_driver_transmitting(self, text: str) -> None:
        """Muestra de inmediato el mensaje del piloto en el HUD de F1 TV mientras el ingeniero responde."""
        if (self.cfg.hud_mode or "auto").lower() == "off":
            return
        self._update_identity_from_telemetry()
        if not self.driver_msg_lbl.winfo_ismapped():
            self.driver_msg_lbl.pack(fill=tk.X, pady=(0, 8), before=self.eng_msg_lbl)
        self.driver_msg_lbl.configure(text=f'"{text.strip().upper()}"')
        self.eng_msg_lbl.configure(text='"..."')
        self._show_until = max(self._show_until, time.time() + self.cfg.hud_hold_seconds + 2.0)
        self._sync_geometry_height()
        self._show_window()

    def reset_position(self) -> None:
        """Restaura la posicion del HUD al lateral derecho por defecto."""
        self.cfg.hud_x = -1
        self.cfg.hud_y = -1
        self.cfg.save()
        self._position_initial()
        self.trigger_preview(8.0)

    def _show_window(self) -> None:
        if not self._visible:
            self._visible = True
            self.win.deiconify()
            try:
                self.win.lift()
                self.win.attributes("-topmost", True)
            except Exception:
                pass
            now = time.time()
            if (
                getattr(self.cfg, "radio_beep_enabled", True)
                and getattr(self.cfg, "radio_beep_style", "f1_tv") != "off"
                and not self.app.speaker.is_speaking
                and (now - self._last_hud_beep_ts > 1.8)
            ):
                self._last_hud_beep_ts = now
                play_ack_beep(
                    self.cfg.radio_effect,
                    self.cfg.volume,
                    style=getattr(self.cfg, "radio_beep_style", "f1_tv"),
                )
        self._current_alpha = max(0.45, min(1.0, float(getattr(self.cfg, "hud_opacity", 0.94))))
        try:
            self.win.attributes("-alpha", self._current_alpha)
        except Exception:
            pass

    def _hide_window(self) -> None:
        if self._visible:
            self._visible = False
            self.win.withdraw()
            now = time.time()
            if (
                getattr(self.cfg, "radio_beep_enabled", True)
                and getattr(self.cfg, "radio_beep_style", "f1_tv") != "off"
                and not self.app.speaker.is_speaking
                and (now - self._last_hud_beep_ts > 1.2)
            ):
                self._last_hud_beep_ts = now
                play_close_beep(
                    self.cfg.radio_effect,
                    self.cfg.volume,
                    style=getattr(self.cfg, "radio_beep_style", "f1_tv"),
                )

    def _sync_geometry_height(self) -> None:
        """Ajusta dinamicamente la altura de la tarjeta F1 TV al texto actual sin cortar frases."""
        self.outer.update_idletasks()
        req_h = max(195, min(420, self.HEADER_H + self.body_frame.winfo_reqheight() + 4))
        cur_x = self.win.winfo_x()
        cur_y = self.win.winfo_y()
        self.win.geometry(f"{self.WIDTH}x{req_h}+{cur_x}+{cur_y}")

    def _update_identity_from_telemetry(self) -> None:
        id_mode = (getattr(self.cfg, "hud_identity_mode", "auto") or "auto").lower()
        custom_team = getattr(self.cfg, "hud_custom_team", "Aston Martin") or "Aston Martin"
        custom_num = int(getattr(self.cfg, "hud_custom_number", 14) or 14)

        with self.app.telemetry.lock:
            st = self.app.telemetry.state
            if id_mode == "custom":
                # MODO MANUAL: Fijado expresamente por el usuario en los ajustes
                drv, color, badge, num = L.resolve_radio_identity(
                    self.cfg.driver_name,
                    custom_team,
                    fallback_driver=self.cfg.driver_name,
                    race_number=custom_num,
                )
            else:
                # MODO AUTOMÁTICO: Detecta escudería, color y dorsal del coche en carrera
                rep = analyze_strategy(st, self.cfg.driver_name)
                r_num = getattr(rep, "player_race_number", 0)
                if r_num <= 0 and 0 <= st.player_idx < len(st.participants):
                    r_num = st.participants[st.player_idx].race_number
                if r_num <= 0:
                    r_num = L.DRIVER_NUMBERS.get((rep.player_driver or "").upper(), 0)
                if r_num <= 0:
                    r_num = 14

                drv, color, badge, num = L.resolve_radio_identity(
                    rep.player_driver,
                    rep.player_team,
                    fallback_driver=self.cfg.driver_name,
                    race_number=r_num,
                )
        self._drv_name = drv
        self._team_color = color
        self._badge_code = badge
        self._race_num = num
        self.driver_msg_lbl.configure(fg=self._team_color)

    def _draw_team_badge(self, c: tk.Canvas, cx: float, cy: float, badge: str, color: str) -> None:
        """Dibuja el escudo de la escuderia al estilo F1 TV junto a la palabra RADIO."""
        if badge == "FER":
            # Escudo amarillo Scuderia Ferrari con franja tricolor italiana superior
            pts = [cx - 12, cy - 14, cx + 12, cy - 14, cx + 11, cy + 3, cx, cy + 15, cx - 11, cy + 3]
            c.create_polygon(pts, fill="#FFF200", outline="#1A1A1A", width=1.5)
            c.create_rectangle(cx - 11, cy - 14, cx - 4, cy - 10, fill="#009246", outline="")
            c.create_rectangle(cx - 4, cy - 14, cx + 4, cy - 10, fill="#FFFFFF", outline="")
            c.create_rectangle(cx + 4, cy - 14, cx + 11, cy - 10, fill="#CE2B37", outline="")
            c.create_text(cx, cy + 1, text="SF", fill="#000000", font=("Segoe UI Black", 8, "bold"))
        elif badge == "MER":
            # Estrella de 3 puntas Mercedes-AMG
            c.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill="#0E1117", outline="#E2E8F0", width=2)
            c.create_line(cx, cy, cx, cy - 11, fill="#E2E8F0", width=2)
            c.create_line(cx, cy, cx - 9, cy + 8, fill="#E2E8F0", width=2)
            c.create_line(cx, cy, cx + 9, cy + 8, fill="#E2E8F0", width=2)
        elif badge == "KICK":
            # Circulo verde neon Kick Sauber con K
            c.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill="#0B0E12", outline="#52E252", width=2)
            c.create_text(cx, cy, text="K", fill="#52E252", font=("Segoe UI Black", 11, "bold"))
        elif badge == "MCL":
            # Swoosh Papaya McLaren
            pts = [cx - 14, cy + 4, cx + 12, cy - 10, cx + 6, cy + 6, cx - 4, cy + 2]
            c.create_polygon(pts, fill="#FF8000", outline="")
        elif badge == "RBR":
            # Emblema Red Bull Racing
            c.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill="#FFD700", outline="")
            c.create_polygon([cx - 14, cy + 2, cx - 2, cy - 3, cx - 4, cy + 5], fill="#E10600", outline="")
            c.create_polygon([cx + 14, cy + 2, cx + 2, cy - 3, cx + 4, cy + 5], fill="#E10600", outline="")
        else:
            # Escudo moderno con las siglas de la escuderia (WIL, AMR, ALP, HRT, REN...)
            c.create_oval(cx - 13, cy - 13, cx + 13, cy + 13, fill="#11151E", outline=color, width=2)
            c.create_text(cx, cy, text=badge[:3], fill=color, font=("Segoe UI Black", 7, "bold"))

    def _draw_header(self, speaking: bool, armed: bool, mic_lvl: float) -> None:
        c = self.header_canvas
        c.delete("all")
        w = self.WIDTH
        h = self.HEADER_H
        color = self._team_color
        dark_band = _blend_hex(self.BG_HEADER, color, 0.24)
        mid_band = _blend_hex(self.BG_HEADER, color, 0.14)

        # Franjas escalonadas del color del equipo detras del dorsal (identico al grafico de F1 TV)
        c.create_rectangle(0, 48, 155, 76, fill=dark_band, outline="")
        c.create_rectangle(0, 58, 225, 76, fill=mid_band, outline="")
        c.create_rectangle(0, 66, w, 76, fill=_blend_hex(self.BG_HEADER, color, 0.08), outline="")

        # Marca superior izquierda estilo F1 TV
        c.create_text(
            16, 13, text="F1", fill="#B0B7C3", font=("Segoe UI Black", 13, "bold italic"), anchor="nw"
        )
        c.create_text(
            42, 16, text="TEAM RADIO", fill="#6C7586", font=("Segoe UI", 7, "bold"), anchor="nw"
        )

        # Dorsal del piloto en grande a la izquierda
        c.create_text(
            16, 34, text=str(self._race_num), fill=color, font=("Segoe UI Black", 28, "bold"), anchor="nw"
        )

        # Apellido del piloto arriba a la derecha en color de escuderia
        drv_font_size = 20 if len(self._drv_name) <= 10 else 16
        c.create_text(
            w - 14,
            8,
            text=self._drv_name,
            fill=color,
            font=("Segoe UI Black", drv_font_size, "bold italic"),
            anchor="ne",
        )

        # Palabra "RADIO" en blanco debajo del apellido + escudo de la escuderia a su izquierda
        radio_id = c.create_text(
            w - 14,
            38,
            text="RADIO",
            fill="#FFFFFF",
            font=("Segoe UI Black", 21, "bold italic"),
            anchor="ne",
        )
        bbox = c.bbox(radio_id)
        badge_cx = (bbox[0] - 20) if bbox else (w - 135)
        self._draw_team_badge(c, badge_cx, 54, self._badge_code, color)

        # Ecualizador de barras verticales F1 TV (36 barras sobre linea base del color del equipo)
        n_bars = 36
        pad_x = 12
        usable_w = w - 2 * pad_x
        step = usable_w / n_bars
        bar_w = max(4.0, step - 3.0)
        base_y = h - 5

        for i in range(n_bars):
            bx = pad_x + i * step
            # Envolvente de campana como en el espectrograma real de F1 TV
            center_weight = 0.45 + 0.55 * math.sin(math.pi * (i + 0.5) / n_bars)
            if speaking:
                wave = 0.30 + 0.70 * abs(math.sin(self._anim_phase + i * 0.45)) * random.uniform(0.65, 1.0)
                bh = max(4.0, wave * center_weight * 28.0)
            elif armed or mic_lvl > 0.04:
                energy = max(0.22, min(1.0, mic_lvl * 2.1))
                wave = energy * (0.4 + 0.6 * abs(math.cos(self._anim_phase + i * 0.38)))
                bh = max(4.0, wave * center_weight * 26.0)
            else:
                wave = 0.14 + 0.10 * abs(math.sin(self._anim_phase * 0.4 + i * 0.35))
                bh = max(3.0, wave * center_weight * 16.0)

            c.create_rectangle(bx, base_y - bh, bx + bar_w, base_y - 2, fill=color, outline="")

        # Linea horizontal solida inferior del ecualizador (firma visual de F1 TV)
        c.create_rectangle(0, base_y - 1, w, base_y + 2, fill=color, outline="")

    def _tick(self) -> None:
        self._anim_phase += 0.42
        mode = (self.cfg.hud_mode or "auto").lower()
        if mode == "off":
            self._hide_window()
            self.win.after(200, self._tick)
            return

        self._update_identity_from_telemetry()

        v = self.app.voice
        speaking = bool(self.app.speaker.is_speaking)
        armed = bool(v and v.is_armed)
        mic_lvl = float(v.mic_level) if v else 0.0
        partial = (v.last_partial or "").strip() if v else ""

        now = time.time()
        dialogue = list(self.app.brain.dialogue_log)

        # 1. ¿Esta hablando el piloto ahora mismo por el microfono o procesando su frase?
        active_q = getattr(self.app, "active_driver_query", "").strip()
        driver_talking_now = False
        if active_q:
            driver_talking_now = True
            partial = active_q
        elif not speaking and (armed or (self.cfg.voice_mode == "always_on" and partial)):
            if partial and partial != self._last_partial_text:
                self._last_partial_text = partial
                driver_talking_now = True
            elif armed:
                driver_talking_now = True

        if driver_talking_now:
            self._show_until = max(self._show_until, now + self.cfg.hud_hold_seconds)
            live_txt = partial.upper() if partial else "ESCUCHANDO TRANSMISIÓN..."
            if not self.driver_msg_lbl.winfo_ismapped():
                self.driver_msg_lbl.pack(fill=tk.X, pady=(0, 8), before=self.eng_msg_lbl)
            self.driver_msg_lbl.configure(text=f'"{live_txt}"')
            if not dialogue:
                self.eng_msg_lbl.configure(text='"..."')
            self._sync_geometry_height()

        # 2. ¿Hay un nuevo mensaje en el historial de radio (respuesta del ingeniero o aviso proactivo)?
        if len(dialogue) != self._last_seen_dialogue_len and dialogue:
            self._last_seen_dialogue_len = len(dialogue)
            latest = dialogue[0]
            drv_raw = (latest.get("driver") or "").strip()
            eng_raw = (latest.get("engineer") or "").strip()

            # Si es un aviso proactivo del ingeniero o control de carrera, mostrar solo el texto blanco del ingeniero
            if drv_raw.startswith("[") and drv_raw.endswith("]"):
                if self.driver_msg_lbl.winfo_ismapped():
                    self.driver_msg_lbl.pack_forget()
            else:
                if not self.driver_msg_lbl.winfo_ismapped():
                    self.driver_msg_lbl.pack(fill=tk.X, pady=(0, 8), before=self.eng_msg_lbl)
                self.driver_msg_lbl.configure(text=f'"{drv_raw.upper()}"')

            self.eng_msg_lbl.configure(text=f'"{eng_raw.upper()}"')
            self._show_until = max(self._show_until, now + self.cfg.hud_hold_seconds)
            self._sync_geometry_height()

        # 3. Mantener visible mientras el ingeniero este hablando + hud_hold_seconds despues de terminar
        preview_until = float(getattr(self.app, "hud_preview_until", 0.0))
        if preview_until > self._show_until:
            self._show_until = preview_until

        if speaking:
            self._was_speaking = True
            self._show_until = max(self._show_until, now + self.cfg.hud_hold_seconds)
        elif self._was_speaking:
            self._was_speaking = False
            self._show_until = max(self._show_until, now + self.cfg.hud_hold_seconds)

        if getattr(self.app, "_stop", None) and self.app._stop.is_set():
            try:
                self.win.destroy()
                self.master.quit()
            except Exception:
                pass
            return

        should_show = (mode == "always") or speaking or armed or (now < self._show_until)

        if should_show:
            self._show_window()
            self._draw_header(speaking=speaking, armed=armed, mic_lvl=mic_lvl)
        else:
            # Fundido suave al terminar la transmision de radio
            if self._visible:
                self._current_alpha = max(0.0, self._current_alpha - 0.12)
                if self._current_alpha <= 0.05:
                    self._hide_window()
                else:
                    try:
                        self.win.attributes("-alpha", self._current_alpha)
                    except Exception:
                        self._hide_window()

        self.win.after(55, self._tick)


def start_overlay_thread(app: RaceEngineerApp) -> threading.Thread:
    """Inicia el HUD de Radio F1 TV en un hilo Tk dedicado (para Swofty Launcher / modo daemon)."""
    def _runner() -> None:
        try:
            root = tk.Tk()
            root.withdraw()
            _overlay = RadioHudOverlay(root, app)
            root.mainloop()
        except Exception:
            pass

    t = threading.Thread(target=_runner, daemon=True, name="f1-tv-radio-hud")
    t.start()
    return t


def run_daemon_with_overlay(app: RaceEngineerApp) -> None:
    """Ejecuta el ingeniero en segundo plano (Swofty Launcher) mostrando el HUD de Radio F1 TV en el juego."""
    root = tk.Tk()
    root.withdraw()
    _overlay = RadioHudOverlay(root, app)
    app.start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
