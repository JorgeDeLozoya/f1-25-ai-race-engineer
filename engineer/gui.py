"""Centro de Mando de Muro de Boxes y Radio F1 25/26 (Telemetria + Estrategia + Voz)."""
from __future__ import annotations

import math
import random
import threading
import time
import tkinter as tk

from .app import RaceEngineerApp
from .strategy import analyze_strategy
from .telemetry import lookups as L
from .telemetry.context import build_standings


VOICE_MODES = [
    ("wake_word", '🎙️ MODO: PALABRA CLAVE ("Ingeniero" + F9)'),
    ("always_on", "🎙️ MODO: SIEMPRE ESCUCHANDO (Directo)"),
    ("ptt_only", "🎙️ MODO: SOLO PUSH-TO-TALK (F9)"),
]


class PitWallWindow:
    BG = "#0B0D13"
    CARD = "#131722"
    CARD_ALT = "#191F2E"
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
            f"F1 25/26 AI Race Engineer · {self.cfg.engineer_name} (Pit Wall Strategy & Radio HUD)"
        )
        self.root.geometry("1180x760")
        self.root.minsize(1020, 660)
        self.root.configure(bg=self.BG)

        self._anim_phase = 0.0
        self._last_dialogue_count = -1
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        # ==================== 1. BARRA SUPERIOR F1 PIT WALL ====================
        top = tk.Frame(
            self.root, bg=self.CARD, height=58, highlightthickness=1, highlightbackground="#252C3F"
        )
        top.pack(fill=tk.X, padx=12, pady=(10, 5))

        tk.Frame(top, bg=self.RED, width=8).pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(
            top,
            text=f"  F1 25/26 PIT WALL  ·  INGENIERO: {self.cfg.engineer_name.upper()}",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.LEFT, padx=6, pady=10)

        self.udp_badge = tk.Label(
            top,
            text=f"📡 ESPERANDO F1 25 EN UDP :{self.cfg.udp_port}",
            bg="#232A3B",
            fg=self.AMBER,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
        )
        self.udp_badge.pack(side=tk.RIGHT, padx=8)

        self.spotter_btn = tk.Button(
            top,
            text="🔔 AVISOS PROACTIVOS: ON" if self.cfg.proactive_callouts else "🔕 AVISOS PROACTIVOS: OFF",
            bg="#18362F" if self.cfg.proactive_callouts else "#2B2D38",
            fg=self.GREEN if self.cfg.proactive_callouts else self.MUTED,
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._toggle_spotter,
        )
        self.spotter_btn.pack(side=tk.RIGHT, padx=4)

        self.mode_btn = tk.Button(
            top,
            text=self._mode_label(self.cfg.voice_mode),
            bg="#1E293B",
            fg=self.CYAN,
            activebackground="#2B3B54",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._cycle_voice_mode,
        )
        self.mode_btn.pack(side=tk.RIGHT, padx=4)

        self.lang_btn = tk.Button(
            top,
            text="🇪🇸 IDIOMA: ESPAÑOL" if self.cfg.language != "en" else "🇬🇧 LANGUAGE: ENGLISH",
            bg="#26334D",
            fg="#FFFFFF",
            activebackground="#344669",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._toggle_language,
        )
        self.lang_btn.pack(side=tk.RIGHT, padx=4)

        # ==================== 2. TARJETA CENTRAL: F1 TV TEAM RADIO ====================
        radio_card = tk.Frame(
            self.root, bg=self.CARD, highlightthickness=2, highlightbackground="#263044"
        )
        radio_card.pack(fill=tk.X, padx=12, pady=5)
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
            text='En F1 25: Settings -> Telemetry Settings -> UDP Telemetry ON (Puerto 20777, Formato 2025)',
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.live_hint.pack(side=tk.RIGHT)

        self.wave_canvas = tk.Canvas(
            radio_card, bg="#0E121B", height=52, highlightthickness=0
        )
        self.wave_canvas.pack(fill=tk.X, padx=14, pady=4)

        self.driver_line = tk.Label(
            radio_card,
            text='PILOTO: (Di "Radio, ¿debería parar en boxes?" o "Radio, ¿cuántas vueltas quedan?")',
            bg=self.CARD,
            fg="#FFD166",
            font=("Segoe UI", 10, "italic"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=1120,
        )
        self.driver_line.pack(fill=tk.X, padx=16, pady=(2, 2))

        self.engineer_line = tk.Label(
            radio_card,
            text=f'{self.cfg.engineer_name.upper()}: "Radio conectada, {self.cfg.driver_name}. Tengo toda la telemetría y estrategia lista en el muro. Copy."',
            bg=self.CARD,
            fg=self.CYAN,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=1120,
        )
        self.engineer_line.pack(fill=tk.X, padx=16, pady=(2, 8))

        # ==================== 3. PANEL DE 3 COLUMNAS (CLASIFICACION + ESTRATEGIA + RADIO LOG) ====================
        mid = tk.Frame(self.root, bg=self.BG)
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        # ---- COLUMNA 1: CLASIFICACION EN VIVO ----
        col1 = tk.Frame(
            mid, bg=self.CARD, width=320, highlightthickness=1, highlightbackground="#252C3F"
        )
        col1.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        col1.pack_propagate(False)

        tk.Label(
            col1,
            text="🏁 CLASIFICACIÓN EN TIEMPO REAL",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 4))

        self.standings_box = tk.Label(
            col1,
            text="",
            bg="#0E121B",
            fg=self.TEXT,
            font=("Consolas", 9),
            justify=tk.LEFT,
            anchor="nw",
            padx=8,
            pady=8,
        )
        self.standings_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        sim_frame = tk.Frame(col1, bg=self.CARD)
        sim_frame.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Button(
            sim_frame,
            text="📡 Simular Carrera UDP",
            bg="#222B3D",
            fg=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self._inject_udp(final_lap=False),
            cursor="hand2",
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        tk.Button(
            sim_frame,
            text="🏳️ Simular Última Vuelta",
            bg="#3A241B",
            fg=self.AMBER,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            command=lambda: self._inject_udp(final_lap=True),
            cursor="hand2",
            pady=5,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # ---- COLUMNA 2: ESTRATEGIA, NEUMATICOS, COMBUSTIBLE Y DANOS ----
        col2 = tk.Frame(
            mid, bg=self.CARD, width=410, highlightthickness=1, highlightbackground="#252C3F"
        )
        col2.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        col2.pack_propagate(False)

        tk.Label(
            col2,
            text="📊 ESTRATEGIA, BOXES Y ESTADO DEL MONOPLAZA",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 4))

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
            bg="#0E121B",
            fg=self.TEXT,
            font=("Consolas", 9),
            justify=tk.LEFT,
            anchor="nw",
            wraplength=375,
            padx=10,
            pady=8,
        )
        self.strategy_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        # ---- COLUMNA 3: HISTORIAL DE RADIO + GEMINI API KEY ----
        col3 = tk.Frame(
            mid, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        col3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        tk.Label(
            col3,
            text="📻 HISTORIAL DE RADIO (PILOTO ⇄ INGENIERO)",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(8, 4))

        self.log_text = tk.Text(
            col3,
            bg="#0E121B",
            fg=self.TEXT,
            font=("Consolas", 9),
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            padx=8,
            pady=6,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))
        self.log_text.tag_configure("time", foreground=self.MUTED)
        self.log_text.tag_configure("driver", foreground="#FFD166", font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("eng", foreground=self.CYAN, font=("Consolas", 9, "bold"))

        # Barra para pegar Gemini API Key opcionalmente
        api_row = tk.Frame(col3, bg=self.CARD)
        api_row.pack(fill=tk.X, padx=10, pady=(0, 8))

        tk.Label(
            api_row,
            text="Gemini Key:",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.api_entry = tk.Entry(
            api_row,
            bg="#0E121B",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Consolas", 9),
            show="*",
        )
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 4))
        if self.cfg.gemini_api_key:
            self.api_entry.insert(0, self.cfg.gemini_api_key)

        tk.Button(
            api_row,
            text="Guardar IA",
            bg="#26334D",
            fg=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._save_api_key,
        ).pack(side=tk.RIGHT)

        # ==================== 4. BARRA INFERIOR: BOTONES RAPIDOS + CHAT ====================
        bot = tk.Frame(
            self.root, bg=self.CARD, highlightthickness=1, highlightbackground="#252C3F"
        )
        bot.pack(fill=tk.X, padx=12, pady=(4, 10))

        btn_row = tk.Frame(bot, bg=self.CARD)
        btn_row.pack(fill=tk.X, padx=10, pady=(8, 4))

        tk.Button(
            btn_row,
            text=f"🎙️ PULSAR PARA HABLAR ({self.cfg.ptt_key.upper()})",
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
        ).pack(side=tk.LEFT, padx=(0, 6))

        quick_queries = [
            ("🛠️ ¿Debería parar?", "¿Debería parar en boxes ahora? ¿Cuál es la estrategia?"),
            ("⏱️ Última Vuelta / Crono", "¿Cuál es mi último tiempo de vuelta y cómo va mi ritmo?"),
            ("🇪🇸 Top 5 Posiciones", "¿Cuáles son las cinco primeras posiciones ahora mismo?"),
            ("🛞 Neumáticos", "¿Cómo tengo las ruedas y cuántas vueltas aguantan?"),
            ("⛽ Gasolina y ERS", "¿Cuánto combustible me queda y cómo tengo la batería?"),
            ("🤬 Ser Borde (Cállate)", "Cállate ya pesado, déjame conducir en paz"),
            ("🍕 Fuera de Lugar", "¿Qué opinas de Pedro Sánchez y qué cenamos hoy?"),
        ]
        for label, q in quick_queries:
            tk.Button(
                btn_row,
                text=label,
                bg=self.CARD_ALT,
                fg=self.TEXT,
                activebackground="#2B354D",
                activeforeground="#FFFFFF",
                relief=tk.FLAT,
                font=("Segoe UI", 8),
                padx=8,
                pady=5,
                cursor="hand2",
                command=lambda query=q: self._send_query(query),
            ).pack(side=tk.LEFT, padx=2)

        input_row = tk.Frame(bot, bg=self.CARD)
        input_row.pack(fill=tk.X, padx=10, pady=(4, 8))

        self.entry = tk.Entry(
            input_row,
            bg="#0E121B",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 8))
        self.entry.bind("<Return>", lambda _e: self._on_enter())

        tk.Button(
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
        ).pack(side=tk.RIGHT)

    @staticmethod
    def _mode_label(mode: str) -> str:
        for k, lbl in VOICE_MODES:
            if k == mode:
                return lbl
        return VOICE_MODES[0][1]

    def _cycle_voice_mode(self) -> None:
        keys = [k for k, _ in VOICE_MODES]
        idx = keys.index(self.cfg.voice_mode) if self.cfg.voice_mode in keys else 0
        self.cfg.voice_mode = keys[(idx + 1) % len(keys)]
        self.cfg.save()
        self.mode_btn.configure(text=self._mode_label(self.cfg.voice_mode))

    def _toggle_language(self) -> None:
        self.cfg.language = "en" if self.cfg.language != "en" else "es"
        self.cfg.save()
        self.lang_btn.configure(
            text="🇪🇸 IDIOMA: ESPAÑOL" if self.cfg.language != "en" else "🇬🇧 LANGUAGE: ENGLISH"
        )

    def _toggle_spotter(self) -> None:
        self.cfg.proactive_callouts = not self.cfg.proactive_callouts
        self.cfg.save()
        on = self.cfg.proactive_callouts
        self.spotter_btn.configure(
            text="🔔 AVISOS PROACTIVOS: ON" if on else "🔕 AVISOS PROACTIVOS: OFF",
            bg="#18362F" if on else "#2B2D38",
            fg=self.GREEN if on else self.MUTED,
        )

    def _save_api_key(self) -> None:
        self.cfg.gemini_api_key = self.api_entry.get().strip()
        self.cfg.save()
        self.live_hint.configure(
            text="✅ Gemini API Key guardada (IA generativa activa)" if self.cfg.gemini_api_key else "Usando Motor Estratégico Local",
            fg=self.GREEN,
        )

    def _trigger_ptt(self) -> None:
        if self.app.voice:
            self.app.voice.arm_now(8.0)

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
        self.driver_line.configure(text=f'PILOTO: "{query}"')
        self.engineer_line.configure(text=f"{self.cfg.engineer_name.upper()}: Copiando transmisión...")
        threading.Thread(target=self.app.handle_driver_message, args=(query,), daemon=True).start()

    def _update_ui(self) -> None:
        self._anim_phase += 0.35
        v = self.app.voice
        speaking = self.app.speaker.is_speaking
        armed = bool(v and v.is_armed)
        mic_lvl = float(v.mic_level) if v else 0.0

        # 1. Estado del microfono
        if speaking:
            self.mic_state_lbl.configure(text="● INGENIERO EN RADIO", fg=self.RED)
            self.radio_card.configure(highlightbackground=self.CYAN)
        elif armed:
            rem = max(0.0, v.armed_until - time.time()) if v else 0.0
            self.mic_state_lbl.configure(text=f"● RADIO ABIERTA ({rem:.0f}s) - HABLA AHORA", fg=self.GREEN)
            self.radio_card.configure(highlightbackground=self.GREEN)
        elif v and v.ready:
            if self.cfg.voice_mode == "always_on":
                self.mic_state_lbl.configure(text="● ESCUCHANDO DIRECTO (Sin palabra clave)", fg=self.GREEN)
            elif self.cfg.voice_mode == "ptt_only":
                self.mic_state_lbl.configure(text=f"● ESPERANDO TECLA [{self.cfg.ptt_key.upper()}]", fg=self.AMBER)
            else:
                self.mic_state_lbl.configure(text='● ESCUCHANDO ("Ingeniero" / [F9])', fg=self.CYAN)
            self.radio_card.configure(highlightbackground="#263044")
        else:
            self.mic_state_lbl.configure(text="● CARGANDO VOZ...", fg=self.AMBER)

        # 2. Telemetria y Estrategia en vivo
        with self.app.telemetry.lock:
            st = self.app.telemetry.state
            connected = st.connected
            pkt_count = st.packet_count
            standings = build_standings(st, limit=14) if connected else []
            rep = analyze_strategy(st, self.cfg.driver_name)
            wear_wheels = [0.0, 0.0, 0.0, 0.0]
            if connected and 0 <= st.player_idx < len(st.damage):
                wear_wheels = list(st.damage[st.player_idx].tyre_wear)
            else:
                wear_wheels = [26.0, 28.0, 33.0, 31.0]

        if connected:
            self.udp_badge.configure(
                text=f"📡 F1 25 CONECTADO · {rep.track_name.upper()} ({pkt_count:,} pkts)",
                bg="#14332C",
                fg=self.GREEN,
            )
            lines = []
            for r in standings:
                you = " ◄" if r["is_player"] else ""
                lines.append(
                    f"P{r['pos']:<2} {r['name'][:11]:<11} {r['gap_leader']:>6}  {r['tyre']:<11}{you}"
                )
            self.standings_box.configure(text="\n".join(lines) if lines else "Recibiendo parrilla...")
        else:
            self.udp_badge.configure(
                text=f"📡 ESPERANDO F1 25 EN UDP :{self.cfg.udp_port} (MODO DEMO)",
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
                "PARA CONECTAR AL F1 25 REAL:",
                "1. Abre F1 25 -> Settings",
                "2. Telemetry Settings",
                "3. UDP Telemetry: ON",
                f"4. UDP Port: {self.cfg.udp_port} | Format: 2025",
            ]
            self.standings_box.configure(text="\n".join(demo_lines))

        # 3. Actualizar panel de Estrategia y Coche
        if "BOX" in rep.box_recommendation:
            self.strategy_banner.configure(
                text=f"🚨 ESTRATEGIA: {rep.box_recommendation}", bg="#4A151B", fg="#FF6B6B"
            )
        elif "OPEN" in rep.box_recommendation or "RAIN" in rep.box_recommendation:
            self.strategy_banner.configure(
                text=f"⚠️ ESTRATEGIA: {rep.box_recommendation}", bg="#3D2E14", fg=self.AMBER
            )
        else:
            self.strategy_banner.configure(
                text=f"✅ ESTRATEGIA: {rep.box_recommendation} (Seguir en pista)", bg="#16322B", fg=self.GREEN
            )

        strat_lines = [
            f"CIRCUITO : {rep.track_name} ({rep.session_name})",
            f"VUELTA   : {rep.current_lap} / {rep.total_laps}  (Quedan {rep.laps_remaining} vueltas)",
            f"POSICIÓN : P{rep.position} / {rep.total_cars}",
            f"DELANTE  : {rep.ahead_name} (+{rep.ahead_gap_s:.1f}s) [{rep.ahead_tyre}]",
            f"DETRÁS   : {rep.behind_name} (-{rep.behind_gap_s:.1f}s) [{rep.behind_tyre}]",
            "─" * 42,
            f"VENTANA BOXES  : Vuelta {rep.pit_window_ideal} a {rep.pit_window_latest}",
            f"SALIDA PREVISTA: P{rep.predicted_rejoin_pos} -> Montar {rep.recommended_compound}",
            "─" * 42,
            f"NEUMÁTICO      : {rep.current_tyre} ({rep.tyre_age} vueltas)",
            f"DESGASTE RUEDAS: FL {wear_wheels[2]:.0f}% | FR {wear_wheels[3]:.0f}% | RL {wear_wheels[0]:.0f}% | RR {wear_wheels[1]:.0f}%",
            f"DEGRADACIÓN    : {rep.wear_per_lap:.1f}%/vuelta (~{rep.est_tyre_laps_left} vueltas buenas)",
            "─" * 42,
            f"COMBUSTIBLE    : {rep.fuel_kg:.1f} kg ({rep.fuel_laps_margin:+.2f} vueltas)",
            f"BATERÍA ERS    : {rep.ers_pct}% (Modo: {rep.ers_mode.upper()})",
            f"METEOROLOGÍA   : {rep.weather_now.upper()} (Lluvia: {rep.rain_forecast_pct}%)",
            f"ESTADO COCHE   : {rep.damage_summary_es}",
        ]
        self.strategy_box.configure(text="\n".join(strat_lines))

        # 4. Transcripcion parcial mientras hablas
        if v and v.last_partial and not speaking:
            self.live_hint.configure(text=f'Reconociendo tu voz: "{v.last_partial}"', fg="#FFD166")

        # 5. Historial de radio
        dialogue = list(self.app.brain.dialogue_log)
        if len(dialogue) != self._last_dialogue_count and dialogue:
            self._last_dialogue_count = len(dialogue)
            latest = dialogue[0]
            self.driver_line.configure(text=f'PILOTO: "{latest["driver"]}"')
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
