"""Centro de Mando de Muro de Boxes, HUD F1 TV y Ajustes (Overtake.gg Edition)."""
from __future__ import annotations

import math
import random
import threading
import time
import tkinter as tk
from tkinter import ttk

from .app import RaceEngineerApp
from .config import EngineerConfig
from .overlay import RadioHudOverlay
from .strategy import analyze_strategy
from .telemetry import lookups as L
from .telemetry.context import build_standings
from .voice import list_input_devices

SPANISH_VOICES = [
    ("es-ES-AlvaroNeural", "Álvaro (España · Marc / Ingeniero F1)"),
    ("es-ES-ElviraNeural", "Elvira (España · Ingeniera de Estrategia)"),
    ("es-ES-XimenaNeural", "Ximena (España / Colombia · Muro)"),
    ("es-MX-JorgeNeural", "Jorge (México · Enérgico / Dinámico)"),
    ("es-MX-DaliaNeural", "Dalia (México · Muro de Boxes)"),
    ("es-AR-TomasNeural", "Tomás (Argentina · Directo / Radio)"),
    ("es-AR-ElenaNeural", "Elena (Argentina · Ingeniera)"),
    ("es-CO-GonzaloNeural", "Gonzalo (Colombia · Pit Wall)"),
    ("es-CO-SalomeNeural", "Salomé (Colombia · Estrategia)"),
    ("es-US-AlonsoNeural", "Alonso (EE.UU. / Español · Muro)"),
    ("es-CL-LorenzoNeural", "Lorenzo (Chile · Ingeniero)"),
]

ENGLISH_VOICES = [
    ("en-GB-RyanNeural", "Ryan (UK British · GP Lambiase / Bono Style)"),
    ("en-GB-ThomasNeural", "Thomas (UK British · Technical Director)"),
    ("en-GB-SoniaNeural", "Sonia (UK British · Senior Strategy Engineer)"),
    ("en-US-GuyNeural", "Guy (US American · American Pit Wall)"),
    ("en-US-ChristopherNeural", "Christopher (US American · Radio Engineer)"),
    ("en-US-EricNeural", "Eric (US American · Deep Voice)"),
    ("en-US-JennyNeural", "Jenny (US American · Race Engineer)"),
    ("en-AU-WilliamMultilingualNeural", "William (Australia · Aussie Race Engineer)"),
    ("en-CA-LiamNeural", "Liam (Canada · Pit Wall)"),
    ("en-IE-ConnorNeural", "Connor (Ireland · High Energy)"),
]

TEAM_OPTIONS = list(L.TEAM_STYLES.keys())


class PitWallWindow:
    BG = "#0B0D13"
    CARD = "#131722"
    CARD_ALT = "#191F2E"
    INPUT_BG = "#0E121B"
    RED = "#E10600"
    CYAN = "#00E5C3"
    GREEN = "#00E58B"
    AMBER = "#FFB800"
    TEXT = "#F4F6FB"
    MUTED = "#8A94A6"

    def __init__(self, app: RaceEngineerApp):
        self.app = app
        self.cfg = app.cfg
        self.root = tk.Tk()
        self.root.title(
            f"F1 25/26 AI Race Engineer · {self.cfg.engineer_name} (Pit Wall, F1 TV HUD & Settings)"
        )
        self.root.geometry("1220x790")
        self.root.minsize(1060, 700)
        self.root.configure(bg=self.BG)

        self._active_tab = "pitwall"
        self._anim_phase = 0.0
        self._last_dialogue_count = -1
        self._capturing_key = False
        self._show_api_key = False
        self._mic_devices: list[tuple[int | None, str]] = list_input_devices()

        self._configure_ttk_styles()
        self._build_ui()
        self.hud_overlay = RadioHudOverlay(self.root, self.app)
        self._apply_ui_language()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _is_en(self) -> bool:
        return (self.cfg.language or "es").lower() == "en"

    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "F1.TCombobox",
            fieldbackground=self.INPUT_BG,
            background="#222B3D",
            foreground=self.TEXT,
            arrowcolor=self.CYAN,
            bordercolor="#263044",
            lightcolor=self.INPUT_BG,
            darkcolor=self.INPUT_BG,
            selectbackground="#26334D",
            selectforeground="#FFFFFF",
            padding=4,
        )
        style.map(
            "F1.TCombobox",
            fieldbackground=[("readonly", self.INPUT_BG)],
            foreground=[("readonly", self.TEXT)],
            selectbackground=[("readonly", "#26334D")],
            selectforeground=[("readonly", "#FFFFFF")],
        )

    def _build_ui(self) -> None:
        # ==================== 1. BARRA SUPERIOR + PESTAÑAS DE NAVEGACIÓN ====================
        top = tk.Frame(
            self.root, bg=self.CARD, height=58, highlightthickness=1, highlightbackground="#252C3F"
        )
        top.pack(fill=tk.X, padx=12, pady=(10, 4))

        tk.Frame(top, bg=self.RED, width=8).pack(side=tk.LEFT, fill=tk.Y)

        self.title_lbl = tk.Label(
            top,
            text=f"  F1 25/26 PIT WALL  ·  {self.cfg.engineer_name.upper()}",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 11, "bold"),
        )
        self.title_lbl.pack(side=tk.LEFT, padx=(6, 12), pady=10)

        # Botones de Pestañas (Pit Wall vs Ajustes)
        self.tab_pitwall_btn = tk.Button(
            top,
            text="🏁 MURO DE BOXES Y RADIO",
            bg=self.RED,
            fg="#FFFFFF",
            activebackground="#B80500",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
            cursor="hand2",
            command=lambda: self._switch_tab("pitwall"),
        )
        self.tab_pitwall_btn.pack(side=tk.LEFT, padx=3, pady=8)

        self.tab_settings_btn = tk.Button(
            top,
            text="⚙️ AJUSTES Y PERSONALIZACIÓN",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            activebackground="#2B354D",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
            cursor="hand2",
            command=lambda: self._switch_tab("settings"),
        )
        self.tab_settings_btn.pack(side=tk.LEFT, padx=3, pady=8)

        # Controles rapidos a la derecha
        self.udp_badge = tk.Label(
            top,
            text=f"📡 UDP :{self.cfg.udp_port}",
            bg="#232A3B",
            fg=self.AMBER,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        )
        self.udp_badge.pack(side=tk.RIGHT, padx=8)

        self.hud_btn = tk.Button(
            top,
            text="",
            bg="#361922",
            fg="#FF4D58",
            activebackground="#4C2230",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=4,
            cursor="hand2",
            command=self._cycle_hud_mode,
        )
        self.hud_btn.pack(side=tk.RIGHT, padx=3)

        self.mode_btn = tk.Button(
            top,
            text="",
            bg="#1E293B",
            fg=self.CYAN,
            activebackground="#2B3B54",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=4,
            cursor="hand2",
            command=self._cycle_voice_mode,
        )
        self.mode_btn.pack(side=tk.RIGHT, padx=3)

        self.lang_btn = tk.Button(
            top,
            text="",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=4,
            cursor="hand2",
            command=self._toggle_language,
        )
        self.lang_btn.pack(side=tk.RIGHT, padx=3)

        # Contenedor principal de vistas
        self.body_container = tk.Frame(self.root, bg=self.BG)
        self.body_container.pack(fill=tk.BOTH, expand=True)

        self.pitwall_frame = tk.Frame(self.body_container, bg=self.BG)
        self.settings_frame = tk.Frame(self.body_container, bg=self.BG)

        self._build_pitwall_tab(self.pitwall_frame)
        self._build_settings_tab(self.settings_frame)

        self.pitwall_frame.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # PESTAÑA 1: MURO DE BOXES Y TELEMETRÍA EN VIVO
    # =========================================================================
    def _build_pitwall_tab(self, parent: tk.Frame) -> None:
        radio_card = tk.Frame(
            parent, bg=self.CARD, highlightthickness=2, highlightbackground="#263044"
        )
        radio_card.pack(fill=tk.X, padx=12, pady=4)
        self.radio_card = radio_card

        header_row = tk.Frame(radio_card, bg=self.CARD)
        header_row.pack(fill=tk.X, padx=14, pady=(8, 2))

        self.driver_tag = tk.Label(
            header_row,
            text=f" {self.cfg.driver_name.upper()}  ⇄  {self.cfg.engineer_name.upper()} (RACE ENGINEER) ",
            bg=self.RED,
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=2,
        )
        self.driver_tag.pack(side=tk.LEFT)

        self.mic_state_lbl = tk.Label(
            header_row,
            text="MIC ACTIVO",
            bg=self.CARD,
            fg=self.GREEN,
            font=("Segoe UI", 9, "bold"),
            padx=10,
        )
        self.mic_state_lbl.pack(side=tk.LEFT)

        self.live_hint = tk.Label(
            header_row,
            text='F1 25: Settings -> Telemetry Settings -> UDP Telemetry ON (Port 20777)',
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.live_hint.pack(side=tk.RIGHT)

        self.wave_canvas = tk.Canvas(
            radio_card, bg="#0E121B", height=50, highlightthickness=0
        )
        self.wave_canvas.pack(fill=tk.X, padx=14, pady=4)

        self.driver_line = tk.Label(
            radio_card,
            text="",
            bg=self.CARD,
            fg="#FFD166",
            font=("Segoe UI", 10, "italic"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=1150,
        )
        self.driver_line.pack(fill=tk.X, padx=16, pady=(2, 2))

        self.engineer_line = tk.Label(
            radio_card,
            text="",
            bg=self.CARD,
            fg=self.CYAN,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=1150,
        )
        self.engineer_line.pack(fill=tk.X, padx=16, pady=(2, 8))

        # Panel de 3 columnas
        mid = tk.Frame(parent, bg=self.BG)
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        # Columna 1: Clasificacion
        col1 = tk.Frame(
            mid, bg=self.CARD, width=325, highlightthickness=1, highlightbackground="#252C3F"
        )
        col1.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        col1.pack_propagate(False)

        self.col1_title = tk.Label(
            col1,
            text="🏁 CLASIFICACIÓN EN TIEMPO REAL",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.col1_title.pack(fill=tk.X, padx=12, pady=(8, 4))

        self.standings_box = tk.Label(
            col1,
            text="",
            bg=self.INPUT_BG,
            fg=self.TEXT,
            font=("Consolas", 8),
            justify=tk.LEFT,
            anchor="nw",
            padx=8,
            pady=6,
        )
        self.standings_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        sim_frame = tk.Frame(col1, bg=self.CARD)
        sim_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        self.sim_race_btn = tk.Button(
            sim_frame,
            text="📡 Simular Carrera UDP",
            bg="#222B3D",
            fg=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self._inject_udp(final_lap=False),
            cursor="hand2",
            pady=5,
        )
        self.sim_race_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.sim_final_btn = tk.Button(
            sim_frame,
            text="🏳️ Simular Última Vuelta",
            bg="#3A241B",
            fg=self.AMBER,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self._inject_udp(final_lap=True),
            cursor="hand2",
            pady=5,
        )
        self.sim_final_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # Columna 2: Estrategia
        col2 = tk.Frame(
            mid, bg=self.CARD, width=415, highlightthickness=1, highlightbackground="#252C3F"
        )
        col2.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        col2.pack_propagate(False)

        self.col2_title = tk.Label(
            col2,
            text="📊 ESTRATEGIA, BOXES Y ESTADO DEL MONOPLAZA",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.col2_title.pack(fill=tk.X, padx=12, pady=(8, 4))

        self.strategy_banner = tk.Label(
            col2,
            text="RECOMENDACIÓN: STAY OUT",
            bg="#16322B",
            fg=self.GREEN,
            font=("Segoe UI", 11, "bold"),
            pady=6,
        )
        self.strategy_banner.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.strategy_box = tk.Label(
            col2,
            text="",
            bg=self.INPUT_BG,
            fg=self.TEXT,
            font=("Consolas", 9),
            justify=tk.LEFT,
            anchor="nw",
            wraplength=380,
            padx=10,
            pady=8,
        )
        self.strategy_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        # Columna 3: Historial de Radio
        col3 = tk.Frame(
            mid, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        col3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.col3_title = tk.Label(
            col3,
            text="📻 HISTORIAL DE RADIO (PILOTO ⇄ INGENIERO)",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.col3_title.pack(fill=tk.X, padx=12, pady=(8, 4))

        self.log_text = tk.Text(
            col3,
            bg=self.INPUT_BG,
            fg=self.TEXT,
            font=("Consolas", 9),
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            padx=8,
            pady=6,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        self.log_text.tag_configure("time", foreground=self.MUTED)
        self.log_text.tag_configure("driver", foreground="#FFD166", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("eng", foreground=self.CYAN, font=("Consolas", 9, "bold"))

        # Barra Inferior: Botones rapidos + Entrada de texto
        bot = tk.Frame(
            parent, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        bot.pack(fill=tk.X, padx=12, pady=(4, 10))

        self.quick_btn_row = tk.Frame(bot, bg=self.CARD)
        self.quick_btn_row.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.ptt_action_btn = tk.Button(
            self.quick_btn_row,
            text="",
            bg=self.RED,
            fg="#FFFFFF",
            activebackground="#B80500",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._trigger_ptt,
        )
        self.ptt_action_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._quick_buttons: list[tk.Button] = []
        for i in range(7):
            b = tk.Button(
                self.quick_btn_row,
                text="",
                bg=self.CARD_ALT,
                fg=self.TEXT,
                activebackground="#2B354D",
                activeforeground="#FFFFFF",
                relief=tk.FLAT,
                font=("Segoe UI", 8),
                padx=8,
                pady=5,
                cursor="hand2",
            )
            b.pack(side=tk.LEFT, padx=2)
            self._quick_buttons.append(b)

        input_row = tk.Frame(bot, bg=self.CARD)
        input_row.pack(fill=tk.X, padx=10, pady=(4, 8))

        self.entry = tk.Entry(
            input_row,
            bg=self.INPUT_BG,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._on_enter())

        self.send_btn = tk.Button(
            input_row,
            text="TRANSMITIR POR RADIO ⏎",
            bg="#00A88F",
            fg="#FFFFFF",
            activebackground="#008C77",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_enter,
        )
        self.send_btn.pack(side=tk.RIGHT)

    # =========================================================================
    # PESTAÑA 2: CENTRO DE AJUSTES Y PERSONALIZACIÓN (OVERTAKE.GG EDITION)
    # =========================================================================
    def _build_settings_tab(self, parent: tk.Frame) -> None:
        grid_wrap = tk.Frame(parent, bg=self.BG)
        grid_wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 6))
        grid_wrap.columnconfigure(0, weight=1, uniform="setcol")
        grid_wrap.columnconfigure(1, weight=1, uniform="setcol")
        grid_wrap.rowconfigure(0, weight=1)
        grid_wrap.rowconfigure(1, weight=1)

        # ---- CARD 1: IDIOMA, PILOTO, INGENIERO Y VOCES NEURALES ----
        c1 = self._make_settings_card(grid_wrap, 0, 0)
        self.c1_header = self._make_card_header(c1, "🌍 IDIOMA, PILOTO, INGENIERO Y VOCES")

        self.lbl_lang, self.cmb_lang = self._add_combo_row(
            c1,
            "Idioma del Ingeniero y la Interfaz:",
            [
                "🇬🇧 English (EN)",
                "🇪🇸 Español (ES)",
                "🇩🇪 Deutsch (DE)",
                "🇫🇷 Français (FR)",
                "🇮🇹 Italiano (IT)",
                "🇧🇷 Português (PT)",
            ],
        )
        self.cmb_lang.bind("<<ComboboxSelected>>", lambda _e: self._on_lang_combo_change())

        self.lbl_drv_name, self.ent_drv_name = self._add_entry_row(
            c1, "Tu Nombre de Piloto (Cómo te llama):", self.cfg.driver_name
        )
        self.lbl_eng_name, self.ent_eng_name = self._add_entry_row(
            c1, "Nombre del Ingeniero (Palabra Clave de Voz):", self.cfg.engineer_name
        )

        self.lbl_eng_hint = tk.Label(
            c1,
            text="💡 Decir este nombre por voz activa la radio automáticamente.",
            bg=self.CARD,
            fg=self.CYAN,
            font=("Segoe UI", 8, "italic"),
            anchor="w",
            padx=14,
        )
        self.lbl_eng_hint.pack(fill=tk.X, pady=(0, 4))

        self.lbl_persona, self.cmb_persona = self._add_combo_row(
            c1,
            "Personalidad del Ingeniero (Estilo):",
            [
                "⚖️ Marc · Estándar F1 (Equilibrado)",
                "🐂 GP Lambiase · Red Bull (Directo / Sarcástico)",
                "⭐ Bono · Mercedes (Motivador / Hammer Time)",
                "🐎 Maranello · Ferrari (We are checking / Plan E)",
                "🔥 Sargento de Pista (Cañero Sin Filtro)",
            ],
        )

        self.lbl_voice_es, self.cmb_voice_es = self._add_combo_row(
            c1, "Voz Neural en Español (Edge TTS):", [lbl for _, lbl in SPANISH_VOICES]
        )
        self.lbl_voice_en, self.cmb_voice_en = self._add_combo_row(
            c1, "Voz Neural en Inglés (Edge TTS):", [lbl for _, lbl in ENGLISH_VOICES]
        )

        rate_row = tk.Frame(c1, bg=self.CARD)
        rate_row.pack(fill=tk.X, padx=14, pady=4)
        self.lbl_rate = tk.Label(
            rate_row,
            text="Velocidad de Habla (%):",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=30,
            anchor="w",
        )
        self.lbl_rate.pack(side=tk.LEFT)

        self.scale_rate = tk.Scale(
            rate_row,
            from_=-10,
            to=50,
            orient=tk.HORIZONTAL,
            bg=self.CARD,
            fg=self.CYAN,
            troughcolor=self.INPUT_BG,
            highlightthickness=0,
            bd=0,
            font=("Segoe UI", 8),
        )
        self.scale_rate.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.btn_test_voice = tk.Button(
            rate_row,
            text="🔊 Probar Voz",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._test_voice_sample,
        )
        self.btn_test_voice.pack(side=tk.RIGHT)

        # ---- CARD 2: MICRÓFONO, PUSH-TO-TALK Y EFECTO DSP DE RADIO ----
        c2 = self._make_settings_card(grid_wrap, 0, 1)
        self.c2_header = self._make_card_header(c2, "🎙️ MICRÓFONO, PUSH-TO-TALK Y RADIO DSP")

        mic_row = tk.Frame(c2, bg=self.CARD)
        mic_row.pack(fill=tk.X, padx=14, pady=4)
        self.lbl_mic_dev = tk.Label(
            mic_row,
            text="Dispositivo de Micrófono:",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=26,
            anchor="w",
        )
        self.lbl_mic_dev.pack(side=tk.LEFT)

        self.cmb_mic_dev = ttk.Combobox(
            mic_row,
            values=[lbl for _, lbl in self._mic_devices],
            state="readonly",
            style="F1.TCombobox",
            font=("Segoe UI", 9),
        )
        self.cmb_mic_dev.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        tk.Button(
            mic_row,
            text="🔄",
            bg=self.CARD_ALT,
            fg=self.CYAN,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=6,
            cursor="hand2",
            command=self._refresh_mic_list,
        ).pack(side=tk.RIGHT)

        self.lbl_vmode, self.cmb_vmode = self._add_combo_row(
            c2,
            "Modo de Activación por Voz:",
            [
                'Palabra Clave ("Ingeniero" + Tecla PTT)',
                "Siempre Escuchando Directo (Manos Libres)",
                "Solo Push-To-Talk (Pulsar Tecla PTT)",
            ],
        )

        self.lbl_wake, self.ent_wake = self._add_entry_row(
            c2, "Palabras Clave (separadas por coma):", self.cfg.wake_words
        )

        ptt_row = tk.Frame(c2, bg=self.CARD)
        ptt_row.pack(fill=tk.X, padx=14, pady=4)
        self.lbl_ptt = tk.Label(
            ptt_row,
            text="Tecla Push-To-Talk (PTT):",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=26,
            anchor="w",
        )
        self.lbl_ptt.pack(side=tk.LEFT)

        self.ent_ptt = tk.Entry(
            ptt_row,
            bg=self.INPUT_BG,
            fg=self.CYAN,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Consolas", 10, "bold"),
            width=12,
        )
        self.ent_ptt.pack(side=tk.LEFT, ipady=4, padx=(0, 6))

        self.btn_bind_key = tk.Button(
            ptt_row,
            text="🎹 Detectar Tecla...",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._start_key_capture,
        )
        self.btn_bind_key.pack(side=tk.LEFT)

        ctrl_row = tk.Frame(c2, bg=self.CARD)
        ctrl_row.pack(fill=tk.X, padx=14, pady=4)
        self.lbl_controller_ptt = tk.Label(
            ctrl_row,
            text="Botón Volante/Mando (PTT):",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=26,
            anchor="w",
        )
        self.lbl_controller_ptt.pack(side=tk.LEFT)

        self.lbl_controller_status = tk.Label(
            ctrl_row,
            text="Cualquier Botón",
            bg=self.CARD,
            fg=self.CYAN,
            font=("Consolas", 10, "bold"),
            width=14,
            anchor="w",
        )
        self.lbl_controller_status.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_bind_controller = tk.Button(
            ctrl_row,
            text="🎮 Detectar Botón Volante / Mando...",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._start_controller_capture,
        )
        self.btn_bind_controller.pack(side=tk.LEFT)

        self.lbl_fx, self.scale_fx = self._add_slider_row(
            c2, "Efecto DSP de Radio FIA (%):", 0, 100
        )
        self.lbl_vol, self.scale_vol = self._add_slider_row(
            c2, "Volumen General de Radio (%):", 10, 150
        )

        # ---- CONTROLES DE PITIDO "BEEP" F1 TV Y AMBIENTE DE FONDO (F1 PASANDO / GARAJE) ----
        self.var_radio_beep = tk.BooleanVar(value=self.cfg.radio_beep_enabled)
        self.var_radio_bg = tk.BooleanVar(value=self.cfg.radio_bg_enabled)
        toggles_row = tk.Frame(c2, bg=self.CARD)
        toggles_row.pack(fill=tk.X, padx=14, pady=(4, 2))

        self.chk_radio_beep = tk.Checkbutton(
            toggles_row,
            text="🔊 Activar Pitido 'Beep' F1 TV",
            variable=self.var_radio_beep,
            bg=self.CARD,
            fg=self.CYAN,
            selectcolor=self.INPUT_BG,
            activebackground=self.CARD,
            activeforeground=self.CYAN,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.chk_radio_beep.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.chk_radio_bg = tk.Checkbutton(
            toggles_row,
            text="🏎️ Activar Sonido de Fondo (F1 / Muro)",
            variable=self.var_radio_bg,
            bg=self.CARD,
            fg=self.GREEN,
            selectcolor=self.INPUT_BG,
            activebackground=self.CARD,
            activeforeground=self.GREEN,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.chk_radio_bg.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_beep_style, self.cmb_beep_style = self._add_combo_row(
            c2,
            "Sonido del Pitido de Radio:",
            [
                "📻 Oficial F1 TV (Audio Real F1)",
                "🔊 F1 TV (Sintético Anterior)",
                "📡 Chirp Digital FIA Muro de Boxes",
                "📻 Walkie Clásico F1 (Años 2000)",
                "🔇 Sin Pitido (Solo Voz)",
            ],
        )

        self.lbl_bg_style, self.cmb_bg_style = self._add_combo_row(
            c2,
            "Ambiente de Fondo en la Radio:",
            [
                "🏎️ Muro de Boxes + F1 Pasando a Fondo (Doppler V6)",
                "🔧 Garaje / Pit Lane + Pistolas Neumáticas",
                "💻 Muro de Boxes Sutil (Servidores y Telemetría)",
                "🔇 Sin Ambiente de Fondo (Radio Limpia)",
            ],
        )

        self.lbl_bg_lvl, self.scale_bg_lvl = self._add_slider_row(
            c2, "Volumen de F1s / Ambiente Fondo (%):", 0, 100
        )

        # ---- CARD 3: HUD DE RADIO F1 TV EN EL JUEGO ----
        c3 = self._make_settings_card(grid_wrap, 1, 0)
        self.c3_header = self._make_card_header(c3, "📺 HUD DE RADIO F1 TV DENTRO DEL JUEGO")

        self.lbl_hud_mode, self.cmb_hud_mode = self._add_combo_row(
            c3,
            "Visibilidad del HUD en el Juego:",
            [
                "Auto-Popup al Hablar o Recibir Radio (F1 TV)",
                "Siempre Fijo en el HUD del Juego",
                "Oculto (Solo Audio)",
            ],
        )

        self.lbl_hud_id, self.cmb_hud_id = self._add_combo_row(
            c3,
            "Modo de Identidad del HUD:",
            [
                "🏎️ Automático (Detecta Equipo, Color y Dorsal del Juego)",
                "✏️ Modo Manual (Personalizado por Mí en Ajustes)",
            ],
        )

        self.lbl_hud_auto_hint = tk.Label(
            c3,
            text="",
            bg=self.CARD,
            fg=self.GREEN,
            font=("Segoe UI", 8, "italic"),
            wraplength=480,
            justify=tk.LEFT,
        )
        self.lbl_hud_auto_hint.pack(fill=tk.X, padx=14, pady=(2, 4))

        self.lbl_hud_team, self.cmb_hud_team = self._add_combo_row(
            c3, "Escudería Manual (Color HUD):", TEAM_OPTIONS
        )

        self.lbl_hud_num, self.ent_hud_num = self._add_entry_row(
            c3, "Dorsal Manual (1 - 99):", str(self.cfg.hud_custom_number)
        )
        self.cmb_hud_id.bind("<<ComboboxSelected>>", self._on_hud_id_mode_change)

        self.lbl_hud_hold, self.scale_hud_hold = self._add_slider_row(
            c3, "Segundos Visible tras Hablar:", 2, 15
        )
        self.lbl_hud_alpha, self.scale_hud_alpha = self._add_slider_row(
            c3, "Opacidad del HUD en Pantalla (%):", 50, 100
        )

        hud_btn_row = tk.Frame(c3, bg=self.CARD)
        hud_btn_row.pack(fill=tk.X, padx=14, pady=(6, 4))

        self.btn_preview_hud = tk.Button(
            hud_btn_row,
            text="👁️ Previsualizar HUD Ahora (8s)",
            bg="#361922",
            fg="#FF6B6B",
            activebackground="#4C2230",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.hud_overlay.trigger_preview(8.0),
        )
        self.btn_preview_hud.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_reset_hud = tk.Button(
            hud_btn_row,
            text="🎯 Resetear Posición del HUD",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            activebackground="#2B354D",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self.hud_overlay.reset_position(),
        )
        self.btn_reset_hud.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        obs_row = tk.Frame(c3, bg=self.CARD)
        obs_row.pack(fill=tk.X, padx=14, pady=(8, 4))
        self.lbl_obs_streamer = tk.Label(
            obs_row,
            text="OBS / Streamlabs Browser Source:",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9, "bold"),
            width=28,
            anchor="w",
        )
        self.lbl_obs_streamer.pack(side=tk.LEFT)

        self.btn_copy_obs = tk.Button(
            obs_row,
            text="📋 Copiar URL para OBS",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._copy_obs_url,
        )
        self.btn_copy_obs.pack(side=tk.LEFT)

        # ---- CARD 4: TELEMETRÍA UDP, SIMHUB FORWARDING E IA GENERATIVA ----
        c4 = self._make_settings_card(grid_wrap, 1, 1)
        self.c4_header = self._make_card_header(c4, "📡 TELEMETRÍA UDP, REENVÍO SIMHUB E IA")

        self.lbl_udp_port, self.ent_udp_port = self._add_entry_row(
            c4, "Puerto UDP de F1 25 / F1 26:", str(self.cfg.udp_port)
        )
        self.lbl_udp_fwd, self.ent_udp_fwd = self._add_entry_row(
            c4,
            "Reenvío UDP (SimHub / MoTeC ip:port):",
            ", ".join(self.cfg.udp_forward),
        )

        self.var_proactive = tk.BooleanVar(value=self.cfg.proactive_callouts)
        chk_row = tk.Frame(c4, bg=self.CARD)
        chk_row.pack(fill=tk.X, padx=14, pady=6)
        self.chk_proactive = tk.Checkbutton(
            chk_row,
            text="Activar Avisos Proactivos (DRS, Desgaste, Última Vuelta, Safety Car, Sanciones)",
            variable=self.var_proactive,
            bg=self.CARD,
            fg=self.GREEN,
            selectcolor=self.INPUT_BG,
            activebackground=self.CARD,
            activeforeground=self.GREEN,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.chk_proactive.pack(fill=tk.X)

        api_row = tk.Frame(c4, bg=self.CARD)
        api_row.pack(fill=tk.X, padx=14, pady=4)
        self.lbl_api_key = tk.Label(
            api_row,
            text="Google Gemini API Key (Opcional):",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=26,
            anchor="w",
        )
        self.lbl_api_key.pack(side=tk.LEFT)

        self.ent_api_key = tk.Entry(
            api_row,
            bg=self.INPUT_BG,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Consolas", 9),
            show="*",
        )
        self.ent_api_key.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 4))

        tk.Button(
            api_row,
            text="👁️",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 8),
            padx=6,
            cursor="hand2",
            command=self._toggle_api_visibility,
        ).pack(side=tk.RIGHT)

        self.lbl_gemini_mdl, self.cmb_gemini_mdl = self._add_combo_row(
            c4,
            "Modelo de IA Generativa (Gemini):",
            ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
        )

        self.lbl_overtake_note = tk.Label(
            c4,
            text="💡 Sin API Key, el mod funciona 100% offline con su Motor Táctico de Muro de Boxes.",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8, "italic"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=520,
        )
        self.lbl_overtake_note.pack(fill=tk.X, padx=14, pady=(8, 4))

        # ---- BARRA INFERIOR DE GUARDADO EN AJUSTES ----
        save_bar = tk.Frame(
            parent, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        save_bar.pack(fill=tk.X, padx=12, pady=(2, 10))

        self.settings_status_lbl = tk.Label(
            save_bar,
            text="Configura tu ingeniero, idioma, micrófono y HUD para F1 25/26.",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=10,
        )
        self.settings_status_lbl.pack(side=tk.LEFT)

        self.btn_save_settings = tk.Button(
            save_bar,
            text="💾 GUARDAR Y APLICAR AJUSTES",
            bg="#00A88F",
            fg="#FFFFFF",
            activebackground="#008C77",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=6,
            cursor="hand2",
            command=self._save_all_settings,
        )
        self.btn_save_settings.pack(side=tk.RIGHT, padx=10, pady=6)

        self.btn_reset_defaults = tk.Button(
            save_bar,
            text="🔄 Restaurar por Defecto",
            bg=self.CARD_ALT,
            fg=self.TEXT,
            activebackground="#2B354D",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._reset_default_settings,
        )
        self.btn_reset_defaults.pack(side=tk.RIGHT, padx=4, pady=6)

        self._load_values_into_settings_form()

    def _make_settings_card(self, parent: tk.Frame, row: int, col: int) -> tk.Frame:
        f = tk.Frame(
            parent, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        f.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
        return f

    def _make_card_header(self, card: tk.Frame, title: str) -> tk.Label:
        hdr = tk.Frame(card, bg="#181E2C")
        hdr.pack(fill=tk.X, pady=(0, 6))
        tk.Frame(hdr, bg=self.RED, width=5).pack(side=tk.LEFT, fill=tk.Y)
        lbl = tk.Label(
            hdr,
            text=title,
            bg="#181E2C",
            fg=self.CYAN,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
            anchor="w",
        )
        lbl.pack(side=tk.LEFT, fill=tk.X)
        return lbl

    def _add_entry_row(self, card: tk.Frame, label_txt: str, initial: str) -> tuple[tk.Label, tk.Entry]:
        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill=tk.X, padx=14, pady=4)
        lbl = tk.Label(
            row,
            text=label_txt,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=28,
            anchor="w",
        )
        lbl.pack(side=tk.LEFT)
        ent = tk.Entry(
            row,
            bg=self.INPUT_BG,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 9),
        )
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        ent.insert(0, initial)
        return lbl, ent

    def _add_combo_row(
        self, card: tk.Frame, label_txt: str, options: list[str]
    ) -> tuple[tk.Label, ttk.Combobox]:
        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill=tk.X, padx=14, pady=4)
        lbl = tk.Label(
            row,
            text=label_txt,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=28,
            anchor="w",
        )
        lbl.pack(side=tk.LEFT)
        cmb = ttk.Combobox(
            row, values=options, state="readonly", style="F1.TCombobox", font=("Segoe UI", 9)
        )
        cmb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if options:
            cmb.current(0)
        return lbl, cmb

    def _add_slider_row(
        self, card: tk.Frame, label_txt: str, min_v: int, max_v: int
    ) -> tuple[tk.Label, tk.Scale]:
        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill=tk.X, padx=14, pady=2)
        lbl = tk.Label(
            row,
            text=label_txt,
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 9),
            width=28,
            anchor="w",
        )
        lbl.pack(side=tk.LEFT)
        sc = tk.Scale(
            row,
            from_=min_v,
            to=max_v,
            orient=tk.HORIZONTAL,
            bg=self.CARD,
            fg=self.CYAN,
            troughcolor=self.INPUT_BG,
            highlightthickness=0,
            bd=0,
            font=("Segoe UI", 8),
        )
        sc.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return lbl, sc

    # =========================================================================
    # LOGICA DE PESTAÑAS, IDIOMA BILINGÜE Y GUARDADO DE AJUSTES
    # =========================================================================
    def _switch_tab(self, tab: str) -> None:
        self._active_tab = tab
        if tab == "pitwall":
            self.settings_frame.pack_forget()
            self.pitwall_frame.pack(fill=tk.BOTH, expand=True)
            self.tab_pitwall_btn.configure(bg=self.RED, fg="#FFFFFF")
            self.tab_settings_btn.configure(bg=self.CARD_ALT, fg=self.TEXT)
        else:
            self._load_values_into_settings_form()
            self.pitwall_frame.pack_forget()
            self.settings_frame.pack(fill=tk.BOTH, expand=True)
            self.tab_settings_btn.configure(bg=self.RED, fg="#FFFFFF")
            self.tab_pitwall_btn.configure(bg=self.CARD_ALT, fg=self.TEXT)

    def _load_values_into_settings_form(self) -> None:
        # 1. Idioma
        lang_codes = ["en", "es", "de", "fr", "it", "pt"]
        l_code = self.cfg.language.lower()[:2]
        self.cmb_lang.current(lang_codes.index(l_code) if l_code in lang_codes else (1 if self._is_en() else 0))
        # 2. Nombres
        self.ent_drv_name.delete(0, tk.END)
        self.ent_drv_name.insert(0, self.cfg.driver_name)
        self.ent_eng_name.delete(0, tk.END)
        self.ent_eng_name.insert(0, self.cfg.engineer_name)
        personas = ["balanced", "gp", "bono", "ferrari", "canero"]
        self.cmb_persona.current(personas.index(self.cfg.engineer_persona) if self.cfg.engineer_persona in personas else 0)
        # 3. Voces
        es_keys = [k for k, _ in SPANISH_VOICES]
        self.cmb_voice_es.current(es_keys.index(self.cfg.voice_es) if self.cfg.voice_es in es_keys else 0)
        en_keys = [k for k, _ in ENGLISH_VOICES]
        self.cmb_voice_en.current(en_keys.index(self.cfg.voice_en) if self.cfg.voice_en in en_keys else 0)
        # 4. Rate
        try:
            r_num = int(str(self.cfg.voice_rate).replace("%", "").replace("+", "").strip())
        except Exception:
            r_num = 25
        self.scale_rate.set(r_num)
        # 5. Microfono
        dev_ids = [d_id for d_id, _ in self._mic_devices]
        self.cmb_mic_dev.current(dev_ids.index(self.cfg.mic_device) if self.cfg.mic_device in dev_ids else 0)
        # 6. Modo de voz
        vmodes = ["wake_word", "always_on", "ptt_only"]
        self.cmb_vmode.current(vmodes.index(self.cfg.voice_mode) if self.cfg.voice_mode in vmodes else 0)
        self.ent_wake.delete(0, tk.END)
        self.ent_wake.insert(0, self.cfg.wake_words)
        self.ent_ptt.delete(0, tk.END)
        self.ent_ptt.insert(0, self.cfg.ptt_key.upper())
        btn = getattr(self.cfg, "controller_ptt_button", -1)
        if btn < 0:
            c_text = "Any Button" if self._is_en() else "Cualquier Botón"
        else:
            c_text = f"Button {btn + 1}" if self._is_en() else f"Botón {btn + 1}"
        self.lbl_controller_status.configure(text=c_text, fg=self.CYAN)
        self.scale_fx.set(int(round(self.cfg.radio_effect * 100)))
        self.scale_vol.set(int(round(self.cfg.volume * 100)))
        self.var_radio_beep.set(bool(self.cfg.radio_beep_enabled))
        self.var_radio_bg.set(bool(self.cfg.radio_bg_enabled))
        beep_styles = ["f1_tv_real", "f1_tv_synth", "fia_pitwall", "classic_v10", "off"]
        cur_style = self.cfg.radio_beep_style
        if cur_style == "f1_tv":
            cur_style = "f1_tv_real"
        self.cmb_beep_style.current(
            beep_styles.index(cur_style) if cur_style in beep_styles else 0
        )
        bg_styles = ["pitwall_f1_flyby", "pit_garage_guns", "pitwall_telemetry", "off"]
        self.cmb_bg_style.current(
            bg_styles.index(self.cfg.radio_bg_style) if self.cfg.radio_bg_style in bg_styles else 0
        )
        self.scale_bg_lvl.set(int(round(self.cfg.radio_bg_level * 100)))
        # 7. HUD
        hmodes = ["auto", "always", "off"]
        self.cmb_hud_mode.current(hmodes.index(self.cfg.hud_mode) if self.cfg.hud_mode in hmodes else 0)
        self.cmb_hud_id.current(1 if self.cfg.hud_identity_mode == "custom" else 0)
        if self.cfg.hud_custom_team in TEAM_OPTIONS:
            self.cmb_hud_team.current(TEAM_OPTIONS.index(self.cfg.hud_custom_team))
        self.ent_hud_num.delete(0, tk.END)
        self.ent_hud_num.insert(0, str(self.cfg.hud_custom_number))
        self.scale_hud_hold.set(int(round(self.cfg.hud_hold_seconds)))
        self.scale_hud_alpha.set(int(round(self.cfg.hud_opacity * 100)))
        self._on_hud_id_mode_change()
        # 8. UDP & Gemini
        self.ent_udp_port.delete(0, tk.END)
        self.ent_udp_port.insert(0, str(self.cfg.udp_port))
        self.ent_udp_fwd.delete(0, tk.END)
        self.ent_udp_fwd.insert(0, ", ".join(self.cfg.udp_forward))
        self.var_proactive.set(bool(self.cfg.proactive_callouts))
        self.ent_api_key.delete(0, tk.END)
        if self.cfg.gemini_api_key:
            self.ent_api_key.insert(0, self.cfg.gemini_api_key)
        mdls = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        self.cmb_gemini_mdl.current(mdls.index(self.cfg.gemini_model) if self.cfg.gemini_model in mdls else 0)

    def _save_all_settings(self) -> None:
        old_mic = self.cfg.mic_device
        lang_codes = ["en", "es", "de", "fr", "it", "pt"]
        l_idx = max(0, self.cmb_lang.current())
        self.cfg.language = lang_codes[l_idx] if l_idx < len(lang_codes) else "en"
        self.cfg.driver_name = self.ent_drv_name.get().strip() or "Driver"
        def_eng = "Ingeniero" if self.cfg.language == "es" else "Engineer"
        self.cfg.engineer_name = self.ent_eng_name.get().strip() or def_eng
        personas = ["balanced", "gp", "bono", "ferrari", "canero"]
        self.cfg.engineer_persona = personas[max(0, self.cmb_persona.current())]
        self.cfg.voice_es = SPANISH_VOICES[max(0, self.cmb_voice_es.current())][0]
        self.cfg.voice_en = ENGLISH_VOICES[max(0, self.cmb_voice_en.current())][0]
        r_val = int(self.scale_rate.get())
        self.cfg.voice_rate = f"{r_val:+d}%"

        mic_idx = max(0, self.cmb_mic_dev.current())
        if mic_idx < len(self._mic_devices):
            self.cfg.mic_device = self._mic_devices[mic_idx][0]

        vmodes = ["wake_word", "always_on", "ptt_only"]
        self.cfg.voice_mode = vmodes[max(0, self.cmb_vmode.current())]
        self.cfg.wake_words = self.ent_wake.get().strip() or "ingeniero, marc, engineer, bono, box"
        self.cfg.ptt_key = (self.ent_ptt.get().strip() or "f9").lower()
        self.cfg.radio_effect = float(self.scale_fx.get()) / 100.0
        self.cfg.volume = float(self.scale_vol.get()) / 100.0
        self.cfg.radio_beep_enabled = bool(self.var_radio_beep.get())
        self.cfg.radio_bg_enabled = bool(self.var_radio_bg.get())
        beep_styles = ["f1_tv_real", "f1_tv_synth", "fia_pitwall", "classic_v10", "off"]
        self.cfg.radio_beep_style = beep_styles[max(0, self.cmb_beep_style.current())]
        bg_styles = ["pitwall_f1_flyby", "pit_garage_guns", "pitwall_telemetry", "off"]
        self.cfg.radio_bg_style = bg_styles[max(0, self.cmb_bg_style.current())]
        self.cfg.radio_bg_level = float(self.scale_bg_lvl.get()) / 100.0

        hmodes = ["auto", "always", "off"]
        self.cfg.hud_mode = hmodes[max(0, self.cmb_hud_mode.current())]
        self.cfg.hud_identity_mode = "custom" if self.cmb_hud_id.current() == 1 else "auto"
        self.cfg.hud_custom_team = TEAM_OPTIONS[max(0, self.cmb_hud_team.current())]
        try:
            self.cfg.hud_custom_number = max(1, min(99, int(self.ent_hud_num.get().strip())))
        except Exception:
            self.cfg.hud_custom_number = 16
        self.cfg.hud_hold_seconds = float(self.scale_hud_hold.get())
        self.cfg.hud_opacity = float(self.scale_hud_alpha.get()) / 100.0

        try:
            self.cfg.udp_port = max(1024, min(65535, int(self.ent_udp_port.get().strip())))
        except Exception:
            self.cfg.udp_port = 20777
        fwd_raw = self.ent_udp_fwd.get().strip()
        self.cfg.udp_forward = [x.strip() for x in fwd_raw.split(",") if ":" in x]
        self.cfg.proactive_callouts = bool(self.var_proactive.get())
        self.cfg.gemini_api_key = self.ent_api_key.get().strip()
        mdls = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        self.cfg.gemini_model = mdls[max(0, self.cmb_gemini_mdl.current())]

        self.cfg.save()
        if self.cfg.mic_device != old_mic:
            threading.Thread(target=self.app.restart_voice, daemon=True).start()

        self._apply_ui_language()
        if self.cfg.hud_mode != "off":
            self.hud_overlay.trigger_preview(7.0)

        msg_ok = (
            "✅ Settings saved & applied in real time!"
            if self._is_en()
            else "✅ ¡Ajustes guardados y aplicados en tiempo real!"
        )
        self.settings_status_lbl.configure(text=msg_ok, fg=self.GREEN)

    def _reset_default_settings(self) -> None:
        defaults = EngineerConfig()
        defaults.save()
        for k in defaults.__dataclass_fields__:
            setattr(self.cfg, k, getattr(defaults, k))
        self._load_values_into_settings_form()
        self._apply_ui_language()
        self.hud_overlay.reset_position()
        self.settings_status_lbl.configure(
            text="🔄 Default settings restored." if self._is_en() else "🔄 Valores por defecto restaurados.",
            fg=self.AMBER,
        )

    def _on_lang_combo_change(self) -> None:
        lang_codes = ["en", "es", "de", "fr", "it", "pt"]
        idx = max(0, self.cmb_lang.current())
        self.cfg.language = lang_codes[idx] if idx < len(lang_codes) else "en"
        curr_eng = self.ent_eng_name.get().strip()
        if self.cfg.language == "es" and curr_eng in ("Engineer", "Marc", ""):
            self.ent_eng_name.delete(0, tk.END)
            self.ent_eng_name.insert(0, "Ingeniero")
            self.cfg.engineer_name = "Ingeniero"
        elif self.cfg.language == "en" and curr_eng in ("Ingeniero", "Marc", ""):
            self.ent_eng_name.delete(0, tk.END)
            self.ent_eng_name.insert(0, "Engineer")
            self.cfg.engineer_name = "Engineer"
        self.cfg.save()
        self._apply_ui_language()

    def _on_hud_id_mode_change(self, event=None) -> None:
        is_manual = (self.cmb_hud_id.current() == 1)
        if is_manual:
            self.cmb_hud_team.configure(state="readonly")
            self.ent_hud_num.configure(state="normal")
            self.lbl_hud_team.configure(fg=self.TEXT)
            self.lbl_hud_num.configure(fg=self.TEXT)
            hint = (
                "✏️ Manual Mode active: Selected team color theme & dorsal number will always be used."
                if self._is_en()
                else "✏️ Modo Manual activo: Se usará siempre la escudería, color y dorsal que elijas aquí debajo."
            )
            self.lbl_hud_auto_hint.configure(text=hint, fg=self.CYAN)
        else:
            self.cmb_hud_team.configure(state="disabled")
            self.ent_hud_num.configure(state="disabled")
            self.lbl_hud_team.configure(fg=self.MUTED)
            self.lbl_hud_num.configure(fg=self.MUTED)
            hint = (
                "🏎️ Auto Mode active: Team colors, badge and car number are detected live from your car in F1 25 / F1 26."
                if self._is_en()
                else "🏎️ Modo Automático activo: El color, escudo y dorsal se leen automáticamente del monoplaza que conduzcas en el juego."
            )
            self.lbl_hud_auto_hint.configure(text=hint, fg=self.GREEN)

    def _refresh_mic_list(self) -> None:
        self._mic_devices = list_input_devices()
        self.cmb_mic_dev.configure(values=[lbl for _, lbl in self._mic_devices])
        self.cmb_mic_dev.current(0)

    def _start_key_capture(self) -> None:
        self._capturing_key = True
        self.btn_bind_key.configure(
            text="⌨️ Press any key..." if self._is_en() else "⌨️ Pulsa una tecla...",
            bg=self.AMBER,
            fg="#000000",
        )
        self.root.bind("<KeyPress>", self._on_key_captured)

    def _on_key_captured(self, event: tk.Event) -> None:
        if not self._capturing_key:
            return
        self._capturing_key = False
        self.root.unbind("<KeyPress>")
        key_sym = (event.keysym or "F9").lower()
        self.ent_ptt.delete(0, tk.END)
        self.ent_ptt.insert(0, key_sym.upper())
        self.btn_bind_key.configure(
            text="🎹 Bind Key..." if self._is_en() else "🎹 Detectar Tecla...",
            bg="#26334D",
            fg="#FFFFFF",
        )

    def _start_controller_capture(self) -> None:
        self.btn_bind_controller.configure(
            text="🎮 Press Wheel Button..." if self._is_en() else "🎮 Pulsa el botón en tu volante/mando...",
            bg=self.AMBER,
            fg="#000000",
        )

        def _poll():
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
            info.dwFlags = 0x80
            last_mask = 0
            t_end = time.time() + 8.0
            found_btn = None

            while time.time() < t_end:
                time.sleep(0.02)
                for dev in range(4):
                    if winmm.joyGetPosEx(dev, ctypes.byref(info)) == 0:
                        m = info.dwButtons
                        new_p = m & (~last_mask)
                        last_mask = m
                        if new_p:
                            for b in range(32):
                                if new_p & (1 << b):
                                    found_btn = b
                                    break
                    if found_btn is not None:
                        break
                if found_btn is not None:
                    break

            def _update():
                if found_btn is not None:
                    self.cfg.controller_ptt_enabled = True
                    self.cfg.controller_ptt_button = found_btn
                    self.cfg.save()
                    msg = f"✅ Wheel Button {found_btn + 1}" if self._is_en() else f"✅ Botón {found_btn + 1} de Volante"
                    self.lbl_controller_status.configure(text=msg, fg=self.GREEN)
                else:
                    self.lbl_controller_status.configure(text="❌ No button detected" if self._is_en() else "❌ No se detectó botón", fg=self.AMBER)
                self.btn_bind_controller.configure(
                    text="🎮 Detect Wheel Button" if self._is_en() else "🎮 Detectar Botón Volante / Mando",
                    bg="#26334D",
                    fg="#FFFFFF",
                )

            self.root.after(0, _update)

        threading.Thread(target=_poll, daemon=True).start()

    def _copy_obs_url(self) -> None:
        url = f"http://localhost:{getattr(self.cfg, 'obs_overlay_port', 8088)}/overlay"
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.btn_copy_obs.configure(text="✅ Copied to Clipboard!" if self._is_en() else "✅ ¡Copiado al Portapapeles!", bg=self.GREEN, fg="#000000")
        self.root.after(2500, lambda: self.btn_copy_obs.configure(
            text="📋 Copy URL for OBS" if self._is_en() else "📋 Copiar URL para OBS",
            bg="#26334D", fg="#FFFFFF"
        ))

    def _toggle_api_visibility(self) -> None:
        self._show_api_key = not self._show_api_key
        self.ent_api_key.configure(show="" if self._show_api_key else "*")

    def _test_voice_sample(self) -> None:
        self._save_all_settings()
        sample = (
            f"Radio check {self.cfg.driver_name}, loud and clear from the pit wall. Telemetry and strategy online, copy."
            if self._is_en()
            else f"Prueba de radio {self.cfg.driver_name}, te escucho alto y claro desde el muro de boxes. Telemetría lista, copy."
        )
        self.hud_overlay.show_driver_transmitting("Radio check" if self._is_en() else "Prueba de radio")
        self.app.brain._log("Radio check" if self._is_en() else "Prueba de radio", sample, self.cfg.language)
        threading.Thread(
            target=self.app.speaker.speak, args=(sample, self.cfg.language), daemon=True
        ).start()

    def _apply_ui_language(self) -> None:
        """Actualiza todos los textos de la interfaz (Pit Wall y Ajustes) entre Español e Inglés."""
        en = self._is_en()
        self.title_lbl.configure(
            text=f"  F1 25/26 PIT WALL  ·  {self.cfg.engineer_name.upper()}"
        )
        self.tab_pitwall_btn.configure(
            text="🏁 PIT WALL & LIVE RADIO" if en else "🏁 MURO DE BOXES Y RADIO"
        )
        self.tab_settings_btn.configure(
            text="⚙️ SETTINGS & CUSTOMIZATION" if en else "⚙️ AJUSTES Y PERSONALIZACIÓN"
        )
        self.lang_btn.configure(
            text="🇬🇧 LANG: ENGLISH" if en else "🇪🇸 IDIOMA: ESPAÑOL"
        )
        self.mode_btn.configure(text=self._mode_label(self.cfg.voice_mode))
        active_hud = self.cfg.hud_mode != "off"
        self.hud_btn.configure(
            text=self._hud_label(self.cfg.hud_mode),
            bg="#361922" if active_hud else "#2B2D38",
            fg="#FF4D58" if active_hud else self.MUTED,
        )

        self.driver_tag.configure(
            text=f" {self.cfg.driver_name.upper()}  ⇄  {self.cfg.engineer_name.upper()} (RACE ENGINEER) "
        )
        if self._last_dialogue_count <= 0:
            self.driver_line.configure(
                text=(
                    f'DRIVER: (Say "Engineer, should I box now?" or press [{self.cfg.ptt_key.upper()}])'
                    if en
                    else f'PILOTO: (Di "Ingeniero, ¿debería parar en boxes?" o pulsa [{self.cfg.ptt_key.upper()}])'
                )
            )
            self.engineer_line.configure(
                text=(
                    f'{self.cfg.engineer_name.upper()}: "Radio check {self.cfg.driver_name}. Telemetry and strategy online on the pit wall. Copy."'
                    if en
                    else f'{self.cfg.engineer_name.upper()}: "Radio conectada, {self.cfg.driver_name}. Telemetría y estrategia listas en el muro. Copy."'
                )
            )

        self.col1_title.configure(
            text="🏁 LIVE STANDINGS (20/22/24 CARS)" if en else "🏁 CLASIFICACIÓN EN TIEMPO REAL"
        )
        self.col2_title.configure(
            text="📊 STRATEGY, PIT WINDOW & CAR STATUS" if en else "📊 ESTRATEGIA, BOXES Y ESTADO DEL MONOPLAZA"
        )
        self.col3_title.configure(
            text="📻 TEAM RADIO TRANSCRIPT LOG" if en else "📻 HISTORIAL DE RADIO (PILOTO ⇄ INGENIERO)"
        )
        self.sim_race_btn.configure(text="📡 Simulate Race UDP" if en else "📡 Simular Carrera UDP")
        self.sim_final_btn.configure(text="🏳️ Simulate Final Lap" if en else "🏳️ Simular Última Vuelta")
        self.ptt_action_btn.configure(
            text=f"🎙️ PUSH TO TALK ({self.cfg.ptt_key.upper()})"
            if en
            else f"🎙️ PULSAR PARA HABLAR ({self.cfg.ptt_key.upper()})"
        )
        self.send_btn.configure(text="SEND OVER RADIO ⏎" if en else "TRANSMITIR POR RADIO ⏎")

        quick_queries = (
            [
                ("📋 Switch to Plan B", "Can we switch to Plan B?"),
                ("🔄 Car Won't Turn", "The car won't turn, I have understeer"),
                ("⚡ Need More Energy", "I need more energy and power on the straight"),
                ("🛑 Brakes Are Weak", "The car has poor braking and I'm locking up"),
                ("⏱️ Rival Pit Stop?", "When did Norris pit and when do you think he will pit?"),
                ("📊 Sectors S1/S2/S3", "Where am I losing time in the sectors?"),
                ("💢 Argue Strategy", "I don't want to box, your strategy call is wrong"),
            ]
            if en
            else [
                ("📋 Pasar a Plan B", "Podemos pasar al Plan B"),
                ("🔄 Me Cuesta Girar", "Me cuesta girar el coche en las curvas"),
                ("⚡ Necesito Energía", "Necesito más energía y potencia en recta"),
                ("🛑 Frena Poco", "El coche frena poco y me voy largo en la frenada"),
                ("⏱️ ¿Parada Rival?", "¿Cuándo ha hecho la parada Norris y cuándo crees que parará?"),
                ("📊 Sectores S1/S2/S3", "¿Dónde estoy perdiendo tiempo en los sectores?"),
                ("💢 Discutir / No Paro", "No quiero parar en boxes, estás equivocado con la estrategia"),
            ]
        )
        for btn, (lbl, q) in zip(self._quick_buttons, quick_queries):
            btn.configure(text=lbl, command=lambda query=q: self._send_query(query))

        # Etiquetas de la Pestaña de Ajustes
        self.c1_header.configure(
            text="🌍 LANGUAGE, DRIVER, ENGINEER & NEURAL VOICES"
            if en
            else "🌍 IDIOMA, PILOTO, INGENIERO Y VOCES"
        )
        self.lbl_lang.configure(text="Language (Voice & UI):" if en else "Idioma del Ingeniero y la Interfaz:")
        self.lbl_drv_name.configure(text="Your Driver Name:" if en else "Tu Nombre de Piloto (Cómo te llama):")
        self.lbl_eng_name.configure(text="Race Engineer Name (Voice Wake Word):" if en else "Nombre del Ingeniero (Palabra Clave de Voz):")
        self.lbl_eng_hint.configure(
            text="💡 Saying this name activates the radio callout automatically."
            if en
            else "💡 Decir este nombre por voz activa la radio automáticamente."
        )
        self.lbl_persona.configure(text="Engineer Personality Style:" if en else "Personalidad del Ingeniero (Estilo):")
        personas = ["balanced", "gp", "bono", "ferrari", "canero"]
        self.cmb_persona.configure(
            values=(
                [
                    "⚖️ Marc · Standard F1 (Balanced)",
                    "🐂 GP Lambiase · Red Bull (Direct / Sarcastic)",
                    "⭐ Bono · Mercedes (Supportive / Hammer Time)",
                    "🐎 Maranello · Ferrari (We are checking / Plan E)",
                    "🔥 Track Sergeant (Hardcore No-Filter)",
                ]
                if en
                else [
                    "⚖️ Marc · Estándar F1 (Equilibrado)",
                    "🐂 GP Lambiase · Red Bull (Directo / Sarcástico)",
                    "⭐ Bono · Mercedes (Motivador / Hammer Time)",
                    "🐎 Maranello · Ferrari (We are checking / Plan E)",
                    "🔥 Sargento de Pista (Cañero Sin Filtro)",
                ]
            )
        )
        self.cmb_persona.current(personas.index(self.cfg.engineer_persona) if self.cfg.engineer_persona in personas else 0)
        self.lbl_voice_es.configure(text="Spanish Neural Voice:" if en else "Voz Neural en Español (Edge TTS):")
        self.lbl_voice_en.configure(text="English Neural Voice:" if en else "Voz Neural en Inglés (Edge TTS):")
        self.lbl_rate.configure(text="Speech Speed Rate (%):" if en else "Velocidad de Habla (%):")
        self.btn_test_voice.configure(text="🔊 Test Voice" if en else "🔊 Probar Voz")

        self.c2_header.configure(
            text="🎙️ MICROPHONE, PUSH-TO-TALK & F1 RADIO DSP"
            if en
            else "🎙️ MICRÓFONO, PUSH-TO-TALK Y RADIO DSP"
        )
        self.lbl_mic_dev.configure(text="Microphone Input Device:" if en else "Dispositivo de Micrófono:")
        self.lbl_vmode.configure(text="Voice Activation Mode:" if en else "Modo de Activación por Voz:")
        self.cmb_vmode.configure(
            values=(
                [
                    'Wake Word ("Engineer" + PTT Key)',
                    "Always Listening (Hands-Free Direct)",
                    "Push-To-Talk Only (PTT Key)",
                ]
                if en
                else [
                    'Palabra Clave ("Ingeniero" + Tecla PTT)',
                    "Siempre Escuchando Directo (Manos Libres)",
                    "Solo Push-To-Talk (Pulsar Tecla PTT)",
                ]
            )
        )
        vmodes = ["wake_word", "always_on", "ptt_only"]
        self.cmb_vmode.current(vmodes.index(self.cfg.voice_mode) if self.cfg.voice_mode in vmodes else 0)
        self.lbl_wake.configure(text="Wake Words (comma-separated):" if en else "Palabras Clave (separadas por coma):")
        self.lbl_ptt.configure(text="Push-To-Talk (PTT) Key:" if en else "Tecla Push-To-Talk (PTT):")
        self.btn_bind_key.configure(text="🎹 Bind Key..." if en else "🎹 Detectar Tecla...")
        self.lbl_controller_ptt.configure(text="Wheel/Gamepad PTT Button:" if en else "Botón Volante/Mando (PTT):")
        self.btn_bind_controller.configure(text="🎮 Detect Wheel Button..." if en else "🎮 Detectar Botón Volante / Mando...")
        self.lbl_fx.configure(text="FIA Radio DSP Effect (%):" if en else "Efecto DSP de Radio FIA (%):")
        self.lbl_vol.configure(text="Master Radio Volume (%):" if en else "Volumen General de Radio (%):")
        self.chk_radio_beep.configure(
            text="🔊 Enable F1 TV 'Beep' Sound" if en else "🔊 Activar Pitido 'Beep' F1 TV"
        )
        self.chk_radio_bg.configure(
            text="🏎️ Enable Background Ambience (F1 Flybys)" if en else "🏎️ Activar Sonido de Fondo (F1 / Muro)"
        )
        self.lbl_beep_style.configure(text="Radio Beep Sound Style:" if en else "Sonido del Pitido de Radio:")
        beep_styles = ["f1_tv_real", "f1_tv_synth", "fia_pitwall", "classic_v10", "off"]
        self.cmb_beep_style.configure(
            values=(
                [
                    "📻 Official F1 TV (Real Broadcast Audio)",
                    "🔊 F1 TV (Previous Synthetic Beep)",
                    "📡 FIA Pit Wall Digital Chirp",
                    "📻 Classic F1 Analog Walkie (2000s)",
                    "🔇 No Beep (Voice Only)",
                ]
                if en
                else [
                    "📻 Oficial F1 TV (Audio Real F1)",
                    "🔊 F1 TV (Sintético Anterior)",
                    "📡 Chirp Digital FIA Muro de Boxes",
                    "📻 Walkie Clásico F1 (Años 2000)",
                    "🔇 Sin Pitido (Solo Voz)",
                ]
            )
        )
        cur_style = self.cfg.radio_beep_style
        if cur_style == "f1_tv":
            cur_style = "f1_tv_real"
        self.cmb_beep_style.current(
            beep_styles.index(cur_style) if cur_style in beep_styles else 0
        )

        self.lbl_bg_style.configure(text="Radio Background Ambience:" if en else "Ambiente de Fondo en la Radio:")
        bg_styles = ["pitwall_f1_flyby", "pit_garage_guns", "pitwall_telemetry", "off"]
        self.cmb_bg_style.configure(
            values=(
                [
                    "🏎️ Pit Wall + F1 Cars Passing at 320 km/h (Doppler V6)",
                    "🔧 Pit Garage + Pneumatic Wheel Guns",
                    "💻 Subtle Pit Wall (Telemetry Servers Only)",
                    "🔇 No Background Ambience (Clean Radio)",
                ]
                if en
                else [
                    "🏎️ Muro de Boxes + F1 Pasando a Fondo (Doppler V6)",
                    "🔧 Garaje / Pit Lane + Pistolas Neumáticas",
                    "💻 Muro de Boxes Sutil (Servidores y Telemetría)",
                    "🔇 Sin Ambiente de Fondo (Radio Limpia)",
                ]
            )
        )
        self.cmb_bg_style.current(
            bg_styles.index(self.cfg.radio_bg_style) if self.cfg.radio_bg_style in bg_styles else 0
        )
        self.lbl_bg_lvl.configure(
            text="F1 Flyby / Ambience Volume (%):" if en else "Volumen de F1s / Ambiente Fondo (%):"
        )

        self.c3_header.configure(
            text="📺 IN-GAME F1 TV BROADCAST RADIO HUD"
            if en
            else "📺 HUD DE RADIO F1 TV DENTRO DEL JUEGO"
        )
        self.lbl_hud_mode.configure(text="In-Game HUD Visibility:" if en else "Visibilidad del HUD en el Juego:")
        self.cmb_hud_mode.configure(
            values=(
                [
                    "Auto-Popup on Radio Transmission (F1 TV)",
                    "Always Pinned on Game HUD",
                    "Hidden (Audio Only)",
                ]
                if en
                else [
                    "Auto-Popup al Hablar o Recibir Radio (F1 TV)",
                    "Siempre Fijo en el HUD del Juego",
                    "Oculto (Solo Audio)",
                ]
            )
        )
        hmodes = ["auto", "always", "off"]
        self.cmb_hud_mode.current(hmodes.index(self.cfg.hud_mode) if self.cfg.hud_mode in hmodes else 0)
        self.lbl_hud_id.configure(text="HUD Identity Mode:" if en else "Modo de Identidad del HUD:")
        self.cmb_hud_id.configure(
            values=(
                [
                    "🏎️ Automatic (Detects Team, Color & Dorsal from Game)",
                    "✏️ Manual Mode (Customized by Me in Settings)",
                ]
                if en
                else [
                    "🏎️ Automático (Detecta Equipo, Color y Dorsal del Juego)",
                    "✏️ Modo Manual (Personalizado por Mí en Ajustes)",
                ]
            )
        )
        self.cmb_hud_id.current(1 if self.cfg.hud_identity_mode == "custom" else 0)
        self.lbl_hud_team.configure(text="Manual Team Color Theme:" if en else "Escudería Manual (Color HUD):")
        self.lbl_hud_num.configure(text="Manual Car Number (1-99):" if en else "Dorsal Manual (1 - 99):")
        self._on_hud_id_mode_change()
        self.lbl_hud_hold.configure(text="Hold Duration on Screen (s):" if en else "Segundos Visible tras Hablar:")
        self.lbl_hud_alpha.configure(text="HUD Opacity (%):" if en else "Opacidad del HUD en Pantalla (%):")
        self.btn_preview_hud.configure(
            text="👁️ Preview HUD Now (8s)" if en else "👁️ Previsualizar HUD Ahora (8s)"
        )
        self.btn_reset_hud.configure(
            text="🎯 Reset HUD Position" if en else "🎯 Resetear Posición del HUD"
        )
        self.lbl_obs_streamer.configure(text="OBS Studio / Streamlabs Browser Source:" if en else "OBS / Streamlabs Browser Source:")
        self.btn_copy_obs.configure(text="📋 Copy URL for OBS" if en else "📋 Copiar URL para OBS")

        self.c4_header.configure(
            text="📡 UDP TELEMETRY, SIMHUB FORWARDING & AI"
            if en
            else "📡 TELEMETRÍA UDP, REENVÍO SIMHUB E IA"
        )
        self.lbl_udp_port.configure(text="F1 25 / F1 26 UDP Port:" if en else "Puerto UDP de F1 25 / F1 26:")
        self.lbl_udp_fwd.configure(
            text="UDP Forward (SimHub ip:port):" if en else "Reenvío UDP (SimHub / MoTeC ip:port):"
        )
        self.chk_proactive.configure(
            text=(
                "Enable Proactive Spotter & Strategy Callouts (DRS, Wear, Final Lap, SC)"
                if en
                else "Activar Avisos Proactivos (DRS, Desgaste, Última Vuelta, Safety Car, Sanciones)"
            )
        )
        self.lbl_api_key.configure(text="Google Gemini API Key (Optional):" if en else "Google Gemini API Key (Opcional):")
        self.lbl_gemini_mdl.configure(text="Generative AI Model:" if en else "Modelo de IA Generativa (Gemini):")
        self.lbl_overtake_note.configure(
            text=(
                "💡 Without an API Key, the mod works 100% offline using its built-in Tactical Race Engineer Engine."
                if en
                else "💡 Sin API Key, el mod funciona 100% offline con su Motor Táctico de Muro de Boxes."
            )
        )
        self.btn_save_settings.configure(
            text="💾 SAVE & APPLY SETTINGS" if en else "💾 GUARDAR Y APLICAR AJUSTES"
        )
        self.btn_reset_defaults.configure(
            text="🔄 Reset to Defaults" if en else "🔄 Restaurar por Defecto"
        )

    def _mode_label(self, mode: str) -> str:
        en = self._is_en()
        if mode == "always_on":
            return "🎙️ MODE: ALWAYS LISTENING" if en else "🎙️ MODO: SIEMPRE ESCUCHANDO"
        if mode == "ptt_only":
            return f"🎙️ MODE: PTT ONLY ({self.cfg.ptt_key.upper()})" if en else f"🎙️ MODO: SOLO PTT ({self.cfg.ptt_key.upper()})"
        return (
            f'🎙️ MODE: WAKE WORD + {self.cfg.ptt_key.upper()}'
            if en
            else f'🎙️ MODO: PALABRA CLAVE + {self.cfg.ptt_key.upper()}'
        )

    def _hud_label(self, mode: str) -> str:
        en = self._is_en()
        if mode == "always":
            return "📺 IN-GAME HUD: PINNED" if en else "📺 HUD JUEGO: SIEMPRE FIJO"
        if mode == "off":
            return "📺 IN-GAME HUD: OFF" if en else "📺 HUD JUEGO: OCULTO"
        return "📺 IN-GAME HUD: AUTO (F1 TV)" if en else "📺 HUD JUEGO: AUTO (F1 TV)"

    def _cycle_voice_mode(self) -> None:
        keys = ["wake_word", "always_on", "ptt_only"]
        idx = keys.index(self.cfg.voice_mode) if self.cfg.voice_mode in keys else 0
        self.cfg.voice_mode = keys[(idx + 1) % len(keys)]
        self.cfg.save()
        self._apply_ui_language()

    def _cycle_hud_mode(self) -> None:
        keys = ["auto", "always", "off"]
        idx = keys.index(self.cfg.hud_mode) if self.cfg.hud_mode in keys else 0
        self.cfg.hud_mode = keys[(idx + 1) % len(keys)]
        self.cfg.save()
        self._apply_ui_language()
        if self.cfg.hud_mode != "off" and hasattr(self, "hud_overlay"):
            self.hud_overlay.trigger_preview(7.0)

    def _toggle_language(self) -> None:
        self.cfg.language = "en" if not self._is_en() else "es"
        self.cfg.save()
        self._load_values_into_settings_form()
        self._apply_ui_language()

    def _trigger_ptt(self) -> None:
        if self.app.voice:
            self.app.voice.arm_now(8.0)
        if hasattr(self, "hud_overlay"):
            self.hud_overlay.trigger_preview(8.0)

    def _inject_udp(self, final_lap: bool = False) -> None:
        def _run():
            import simulate_udp
            simulate_udp.send_test_telemetry("127.0.0.1", self.cfg.udp_port, final_lap=final_lap)
        threading.Thread(target=_run, daemon=True).start()

    def _on_enter(self) -> None:
        q = self.entry.get().strip()
        if not q:
            return
        self.entry.delete(0, tk.END)
        self._send_query(q)

    def _send_query(self, query: str) -> None:
        prefix = "DRIVER" if self._is_en() else "PILOTO"
        wait_txt = "Copying transmission..." if self._is_en() else "Copiando transmisión..."
        self.driver_line.configure(text=f'{prefix}: "{query}"')
        self.engineer_line.configure(text=f"{self.cfg.engineer_name.upper()}: {wait_txt}")
        if hasattr(self, "hud_overlay"):
            self.hud_overlay.show_driver_transmitting(query)
        threading.Thread(target=self.app.handle_driver_message, args=(query,), daemon=True).start()

    def _update_ui(self) -> None:
        self._anim_phase += 0.35
        en = self._is_en()
        v = self.app.voice
        speaking = self.app.speaker.is_speaking
        armed = bool(v and v.is_armed)
        mic_lvl = float(v.mic_level) if v else 0.0

        # 1. Estado del microfono
        if speaking:
            self.mic_state_lbl.configure(
                text="● ENGINEER ON RADIO" if en else "● INGENIERO EN RADIO", fg=self.RED
            )
            self.radio_card.configure(highlightbackground=self.CYAN)
        elif armed:
            rem = max(0.0, v.armed_until - time.time()) if v else 0.0
            self.mic_state_lbl.configure(
                text=f"● RADIO OPEN ({rem:.0f}s) - SPEAK NOW" if en else f"● RADIO ABIERTA ({rem:.0f}s) - HABLA AHORA",
                fg=self.GREEN,
            )
            self.radio_card.configure(highlightbackground=self.GREEN)
        elif v and v.ready:
            if self.cfg.voice_mode == "always_on":
                self.mic_state_lbl.configure(
                    text="● LISTENING DIRECT" if en else "● ESCUCHANDO DIRECTO", fg=self.GREEN
                )
            elif self.cfg.voice_mode == "ptt_only":
                self.mic_state_lbl.configure(
                    text=f"● WAITING [{self.cfg.ptt_key.upper()}]" if en else f"● ESPERANDO [{self.cfg.ptt_key.upper()}]",
                    fg=self.AMBER,
                )
            else:
                ww = (self.cfg.wake_word_list[0] if self.cfg.wake_word_list else "ingeniero").capitalize()
                self.mic_state_lbl.configure(
                    text=f'● LISTENING ("{ww}" / [{self.cfg.ptt_key.upper()}])'
                    if en
                    else f'● ESCUCHANDO ("{ww}" / [{self.cfg.ptt_key.upper()}])',
                    fg=self.CYAN,
                )
            self.radio_card.configure(highlightbackground="#263044")
        else:
            self.mic_state_lbl.configure(
                text="● LOADING VOICE..." if en else "● CARGANDO VOZ...", fg=self.AMBER
            )

        # 2. Telemetria y Estrategia en vivo
        with self.app.telemetry.lock:
            st = self.app.telemetry.state
            connected = st.connected
            pkt_count = st.packet_count
            standings = build_standings(st, limit=24) if connected else []
            rep = analyze_strategy(st, self.cfg.driver_name)
            if connected and 0 <= st.player_idx < len(st.damage):
                wear_wheels = list(st.damage[st.player_idx].tyre_wear)
            else:
                w_est = rep.max_wear_pct
                wear_wheels = [max(0.0, w_est - 3.0), max(0.0, w_est - 2.0), w_est, max(0.0, w_est - 1.0)]

        if connected:
            self.udp_badge.configure(
                text=f"📡 F1 25 LIVE · {rep.track_name.upper()} ({pkt_count:,} pkts)",
                bg="#14332C",
                fg=self.GREEN,
            )
            lines = []
            you_tag = " ◄ YOU" if en else " ◄ TÚ"
            for r in standings:
                you = you_tag if r["is_player"] else ""
                lines.append(
                    f"P{r['pos']:<2} {r['name'][:11]:<11} {r['gap_leader']:>6}  {r['tyre']:<10}{you}"
                )
            self.standings_box.configure(text="\n".join(lines) if lines else "Receiving grid...")
        else:
            self.udp_badge.configure(
                text=f"📡 WAITING F1 25 UDP :{self.cfg.udp_port}" if en else f"📡 ESPERANDO F1 25 UDP :{self.cfg.udp_port}",
                bg="#232A3B",
                fg=self.AMBER,
            )
            demo_lines = [
                "P1  Verstappen    +0.0s  Medium (9L)",
                "P2  Leclerc       +2.8s  Medium (9L)",
                "P3  Norris        +5.1s  Medium (9L)",
                f"P4  {self.cfg.driver_name[:11]:<11}   +6.5s  Medium (9L) ◄",
                "P5  Sainz         +8.6s  Hard (14L)",
                "P6  Hamilton     +11.2s  Hard (14L)",
                "P7  Russell      +13.0s  Medium (9L)",
                "P8  Alonso       +16.4s  Hard (14L)",
                "P9  Piastri      +18.1s  Medium (9L)",
                "P10 Gasly        +22.0s  Hard (14L)",
                "",
                "─" * 34,
                "HOW TO CONNECT TO F1 25:" if en else "PARA CONECTAR AL F1 25 REAL:",
                "1. Open F1 25 -> Settings" if en else "1. Abre F1 25 -> Settings",
                "2. Telemetry Settings",
                "3. UDP Telemetry: ON",
                f"4. UDP Port: {self.cfg.udp_port} | Format: 2025",
            ]
            self.standings_box.configure(text="\n".join(demo_lines))

        # 3. Actualizar panel de Estrategia y Coche
        active_plan = getattr(self.app.brain, "active_plan", "A")
        if "BOX" in rep.box_recommendation:
            self.strategy_banner.configure(
                text=f"🚨 PLAN {active_plan}: {rep.box_recommendation}",
                bg="#4A151B",
                fg="#FF6B6B",
            )
        elif "OPEN" in rep.box_recommendation or "RAIN" in rep.box_recommendation:
            self.strategy_banner.configure(
                text=f"⚠️ PLAN {active_plan}: {rep.box_recommendation}",
                bg="#3D2E14",
                fg=self.AMBER,
            )
        else:
            self.strategy_banner.configure(
                text=f"✅ PLAN {active_plan}: {rep.box_recommendation}" if en else f"✅ PLAN {active_plan}: {rep.box_recommendation} (Seguir en pista)",
                bg="#16322B",
                fg=self.GREEN,
            )

        if en:
            strat_lines = [
                f"CAR / TEAM : {rep.player_driver} · {rep.player_team}",
                f"CIRCUIT    : {rep.track_name} ({rep.session_name})",
                f"LAP        : {rep.current_lap} / {rep.total_laps}  ({rep.laps_remaining} laps left)",
                f"POSITION   : P{rep.position} / {rep.total_cars}  (Last: {rep.last_lap_str})",
                f"SPLITS     : S1 {rep.s1_str} | S2 {rep.s2_str} | S3 {rep.s3_str}",
                f"CAR AHEAD  : {rep.ahead_name} (+{rep.ahead_gap_s:.1f}s) [{rep.ahead_tyre}]",
                f"CAR BEHIND : {rep.behind_name} (-{rep.behind_gap_s:.1f}s) [{rep.behind_tyre}]",
                "─" * 42,
                f"PIT WALL PLAN  : PLAN {active_plan} · Style: {self.cfg.engineer_persona.upper()}",
                f"PIT WINDOW     : Lap {rep.pit_window_ideal} to {rep.pit_window_latest} -> P{rep.predicted_rejoin_pos} ({rep.recommended_compound})",
                "─" * 42,
                f"TYRE COMPOUND  : {rep.current_tyre} ({rep.tyre_age} laps)",
                f"TYRE WEAR      : FL {wear_wheels[2]:.0f}% | FR {wear_wheels[3]:.0f}% | RL {wear_wheels[0]:.0f}% | RR {wear_wheels[1]:.0f}%",
                f"DEGRADATION    : {rep.wear_per_lap:.1f}%/lap (~{rep.est_tyre_laps_left} good laps)",
                "─" * 42,
                f"FUEL REMAINING : {rep.fuel_kg:.1f} kg ({rep.fuel_laps_margin:+.2f} laps)",
                f"ERS BATTERY    : {rep.ers_pct}% (Mode: {rep.ers_mode.upper()})",
                f"MFD CAR SETUP  : Brake Bias {rep.brake_bias}% | Diff {rep.diff_pct}% | Wing {rep.front_wing_delta:+d}",
                f"AI AUTO-ACTION : {rep.ai_auto_action_en[:46] if rep.ai_auto_action_en else 'Active (Say Plan B, cant turn, need energy...)'}",
                f"WEATHER        : {rep.weather_now.upper()} (Rain: {rep.rain_forecast_pct}%)",
                f"CAR DAMAGE     : {rep.damage_summary_en}",
            ]
        else:
            strat_lines = [
                f"MONOPLAZA: {rep.player_driver} · {rep.player_team}",
                f"CIRCUITO : {rep.track_name} ({rep.session_name})",
                f"VUELTA   : {rep.current_lap} / {rep.total_laps}  (Quedan {rep.laps_remaining} vueltas)",
                f"POSICIÓN : P{rep.position} / {rep.total_cars}  (Última: {rep.last_lap_str})",
                f"PARCIALES: S1 {rep.s1_str} | S2 {rep.s2_str} | S3 {rep.s3_str}",
                f"DELANTE  : {rep.ahead_name} (+{rep.ahead_gap_s:.1f}s) [{rep.ahead_tyre}]",
                f"DETRÁS   : {rep.behind_name} (-{rep.behind_gap_s:.1f}s) [{rep.behind_tyre}]",
                "─" * 42,
                f"PLAN EN MURO   : PLAN {active_plan} · Estilo: {self.cfg.engineer_persona.upper()}",
                f"VENTANA BOXES  : V{rep.pit_window_ideal}-V{rep.pit_window_latest} -> Salida P{rep.predicted_rejoin_pos} ({rep.recommended_compound})",
                "─" * 42,
                f"NEUMÁTICO      : {rep.current_tyre} ({rep.tyre_age} vueltas)",
                f"DESGASTE RUEDAS: FL {wear_wheels[2]:.0f}% | FR {wear_wheels[3]:.0f}% | RL {wear_wheels[0]:.0f}% | RR {wear_wheels[1]:.0f}%",
                f"DEGRADACIÓN    : {rep.wear_per_lap:.1f}%/vuelta (~{rep.est_tyre_laps_left} vueltas buenas)",
                "─" * 42,
                f"COMBUSTIBLE    : {rep.fuel_kg:.1f} kg ({rep.fuel_laps_margin:+.2f} vueltas)",
                f"BATERÍA ERS    : {rep.ers_pct}% (Modo: {rep.ers_mode.upper()})",
                f"REGLAJES MFD   : Frenada {rep.brake_bias}% | Diferencial {rep.diff_pct}% | Ala {rep.front_wing_delta:+d}",
                f"IA AUTO-SETUP  : {rep.ai_auto_action_es[:46] if rep.ai_auto_action_es else 'Activo (Di Plan B, cuesta girar, más energía...)'}",
                f"METEOROLOGÍA   : {rep.weather_now.upper()} (Lluvia: {rep.rain_forecast_pct}%)",
                f"ESTADO COCHE   : {rep.damage_summary_es}",
            ]
        self.strategy_box.configure(text="\n".join(strat_lines))

        # 4. Transcripcion parcial mientras hablas
        if v and v.last_partial and not speaking:
            lbl_rec = "Recognizing speech" if en else "Reconociendo tu voz"
            self.live_hint.configure(text=f'{lbl_rec}: "{v.last_partial}"', fg="#FFD166")

        # 5. Historial de radio
        dialogue = list(self.app.brain.dialogue_log)
        if len(dialogue) != self._last_dialogue_count and dialogue:
            self._last_dialogue_count = len(dialogue)
            latest = dialogue[0]
            drv_prefix = "DRIVER" if en else "PILOTO"
            self.driver_line.configure(text=f'{drv_prefix}: "{latest["driver"]}"')
            self.engineer_line.configure(
                text=f'{self.cfg.engineer_name.upper()} [{latest["lang"]}]: "{latest["engineer"]}"'
            )
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            for item in dialogue:
                self.log_text.insert(tk.END, f"[{item['time']}] ", "time")
                self.log_text.insert(tk.END, f"{item['driver']}\n", "driver")
                self.log_text.insert(
                    tk.END,
                    f"  ↳ {self.cfg.engineer_name.upper()} ({item['lang']}): {item['engineer']}\n\n",
                    "eng",
                )
            self.log_text.configure(state=tk.DISABLED)

        if self._active_tab == "pitwall":
            self._draw_equalizer(speaking=speaking, armed=armed, mic_lvl=mic_lvl)
        self.root.after(55, self._update_ui)

    def _draw_equalizer(self, speaking: bool, armed: bool, mic_lvl: float) -> None:
        c = self.wave_canvas
        c.delete("all")
        w = max(300, c.winfo_width())
        h = max(44, c.winfo_height())
        mid_y = h / 2.0
        n_bars = 42
        bar_w = max(5, (w - 36) / n_bars - 4)

        for i in range(n_bars):
            x = 18 + i * ((w - 36) / n_bars)
            if speaking:
                amp = 0.25 + 0.72 * abs(math.sin(self._anim_phase + i * 0.42)) * random.uniform(0.65, 1.0)
                color = self.CYAN if i % 3 else "#00B4D8"
            elif armed:
                amp = max(0.12, min(0.95, mic_lvl * 1.8 * (0.5 + 0.5 * abs(math.cos(self._anim_phase + i * 0.3)))))
                color = self.GREEN
            else:
                amp = max(0.05, min(0.60, mic_lvl * 1.2 * (0.4 + 0.6 * abs(math.sin(i * 0.4)))))
                color = "#283347" if mic_lvl < 0.05 else "#FFD166"

            bh = max(4.0, amp * (h - 8))
            c.create_rectangle(
                x, mid_y - bh / 2, x + bar_w, mid_y + bh / 2, fill=color, outline=""
            )

    def _on_close(self) -> None:
        self.app.stop()
        self.root.destroy()

    def run(self) -> None:
        self.app.start()
        self.root.after(100, self._update_ui)
        self.root.mainloop()
