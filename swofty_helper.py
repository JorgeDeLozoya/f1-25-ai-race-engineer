"""Plugin oficial de Swofty Launcher (JSON-RPC sobre stdin/stdout) para AI Race Engineer."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

# Preservar el descriptor real de stdout solo para JSON-RPC y desviar cualquier otro print a stderr
_rpc_fd = os.dup(1)
os.dup2(2, 1)
_rpc_out = os.fdopen(_rpc_fd, "w", encoding="utf-8", buffering=1)

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("swofty-helper")

from engineer.app import RaceEngineerApp, ensure_single_instance  # noqa: E402
from engineer.config import EngineerConfig  # noqa: E402
from engineer.overlay import start_overlay_thread  # noqa: E402
from engineer.strategy import analyze_strategy  # noqa: E402
from engineer.telemetry.context import build_standings  # noqa: E402

API_VERSION = 1


class Host:
    def __init__(self):
        self.next_id = 0
        self._write_lock = threading.Lock()

    def send(self, msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False)
        with self._write_lock:
            _rpc_out.write(line + "\n")
            _rpc_out.flush()

    def call(self, method: str, params=None):
        req_id = self.next_id
        self.next_id += 1
        self.send({"id": req_id, "method": method, "params": params})
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        reply = json.loads(line)
        if "error" in reply and reply["error"] is not None:
            raise RuntimeError(str(reply["error"]))
        return reply.get("result")

    def invalidate(self, section: str = "dashboard") -> None:
        self.send({"method": "invalidate", "params": {"section": section}})


class SwoftyEngineerPlugin:
    def __init__(self, host: Host):
        self.host = host
        self.data_dir = Path(__file__).resolve().parent
        self.cache_dir = Path(__file__).resolve().parent / "cache"
        self.vanilla = False
        self.tab = "pitwall"
        self.cfg = EngineerConfig.load(self.config_path)
        self.app: RaceEngineerApp | None = None
        self._hud_proc: subprocess.Popen | None = None
        self._last_log_len = 0
        self._last_pkt_bucket = -1
        self._last_game_running = False
        self._manual_start = False

    def _is_game_process_running(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            found = False

            def enum_cb(h, _):
                nonlocal found
                if user32.IsWindowVisible(h):
                    length = user32.GetWindowTextLengthW(h)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(h, buff, length + 1)
                        if any(k in buff.value for k in ("F1 25", "F1® 25", "F1 24", "F1® 24", "F1 26", "F1® 26")):
                            found = True
                            return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            return found
        except Exception:
            return False

    @property
    def config_path(self) -> Path:
        local_cfg = Path(__file__).resolve().parent / "config.json"
        if local_cfg.exists():
            return local_cfg
        return self.data_dir / "config.json"

    def start_engineer(self) -> None:
        if self.app is not None:
            return
        ensure_single_instance()
        self.cfg = EngineerConfig.load(self.config_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.app = RaceEngineerApp(
            self.cfg,
            status_file=self.cache_dir / "runtime_status.json",
            enable_voice=True,
        )
        self.app.start()
        start_overlay_thread(self.app)
        log.info("AI Race Engineer + F1 TV Radio HUD iniciado dentro de Swofty Launcher.")

    def stop_engineer(self) -> None:
        if self.app is None:
            return
        self.app.stop()
        self.app = None
        log.info("AI Race Engineer detenido.")

    def restart_engineer(self) -> None:
        was_running = self.app is not None
        self.stop_engineer()
        if was_running:
            self.start_engineer()

    def open_hud_window(self) -> None:
        """Cierra el motor en segundo plano del helper y abre la ventana HUD completa."""
        self.stop_engineer()
        root_dir = Path(__file__).resolve().parent
        pyw = root_dir / ".venv" / "Scripts" / "pythonw.exe"
        if not pyw.exists():
            pyw = Path(r"c:\Users\Jorge\.gemini\antigravity\scratch\f1_mods\ai_race_engineer\.venv\Scripts\pythonw.exe")
        exe = str(pyw) if pyw.exists() else sys.executable
        self._hud_proc = subprocess.Popen([exe, "-m", "engineer", "--gui"], cwd=str(root_dir))

    def build_view(self) -> dict:
        self.cfg = EngineerConfig.load(self.config_path)
        try:
            gstatus = self.host.call("game_status", None) or {}
        except Exception:
            gstatus = {}
        game_running = bool(gstatus.get("running"))
        self._last_game_running = game_running

        hud_alive = bool(self._hud_proc and self._hud_proc.poll() is None)
        eng_running = (self.app is not None) or hud_alive
        st = self.app.telemetry.state if self.app else None
        udp_ok = bool(st and st.connected)
        rep = analyze_strategy(st, self.cfg.driver_name) if st else None
        has_key = bool(self.cfg.resolved_api_key())
        dialogue = list(self.app.brain.dialogue_log) if self.app else []
        self._last_log_len = len(dialogue)

        mode_names = {
            "wake_word": 'Palabra Clave ("Ingeniero" + F9)',
            "always_on": "Siempre Escuchando (Directo)",
            "ptt_only": f"Solo Push-To-Talk ({self.cfg.ptt_key.upper()})",
        }

        pills = [
            {
                "text": (
                    "HUD WINDOW ACTIVE"
                    if hud_alive
                    else ("ENGINEER LIVE (Voice Active)" if eng_running else "Engineer Stopped")
                ),
                "tone": "good" if eng_running else "muted",
                "dot": True,
            },
            {
                "text": (
                    f"F1 25 Connected · {rep.track_name}"
                    if (udp_ok and rep)
                    else f"Waiting UDP :{self.cfg.udp_port}"
                ),
                "tone": "good" if udp_ok else "warn",
                "dot": True,
            },
            {
                "text": "Idioma: ESPAÑOL" if self.cfg.language != "en" else "Language: ENGLISH",
                "tone": "accent",
            },
            {
                "text": "Gemini AI Active" if has_key else "Motor Estratégico Local",
                "tone": "good" if has_key else "accent",
            },
        ]

        hero = {
            "hero": {
                "title": f"F1 25/26 AI Race Engineer · {self.cfg.engineer_name}",
                "subtitle": (
                    f"Piloto: {self.cfg.driver_name} · Modo de voz: {mode_names.get(self.cfg.voice_mode, self.cfg.voice_mode)}"
                ),
                "art": {"monogram": "RE"},
                "pills": pills,
                "facts": [
                    {"label": "Puerto UDP", "value": str(self.cfg.udp_port)},
                    {"label": "Tecla PTT", "value": self.cfg.ptt_key.upper()},
                    {"label": "Palabra Clave", "value": '"Ingeniero" / "Marc"'},
                ],
                "buttons": [
                    {
                        "id": "toggle_engineer",
                        "label": "Detener Ingeniero" if eng_running else "Activar Ingeniero",
                        "icon": "trash" if eng_running else "play",
                        "style": "danger" if eng_running else "primary",
                    },
                    {
                        "id": "open_hud",
                        "label": "Abrir Ventana Pit Wall HUD",
                        "icon": "activity",
                        "style": "primary" if not hud_alive else "outline",
                    },
                    {
                        "id": "test_pos",
                        "label": "Probar: ¿Posición y Coche?",
                        "icon": "zap",
                        "style": "outline",
                    },
                    {
                        "id": "test_strat",
                        "label": "Probar: ¿Estrategia Boxes?",
                        "icon": "zap",
                        "style": "outline",
                    },
                    {
                        "id": "test_rude",
                        "label": "Probar: Ser Borde",
                        "icon": "circle-alert",
                        "style": "ghost",
                    },
                ],
            }
        }

        tabs = {
            "tabs": {
                "id": "main_tabs",
                "active": self.tab,
                "items": [
                    {"id": "pitwall", "label": "Muro de Boxes y Clasificación", "icon": "activity"},
                    {
                        "id": "radio_log",
                        "label": "Historial de Radio",
                        "icon": "activity",
                        "badge": str(len(dialogue)),
                    },
                    {"id": "settings", "label": "Ajustes del Ingeniero", "icon": "settings"},
                ],
            }
        }

        blocks = [hero, tabs]

        if self.tab == "pitwall":
            standings = build_standings(st, limit=24) if (st and st.connected) else []
            if rep:
                blocks.append({
                    "card": {
                        "title": f"Estrategia en Vivo · {rep.player_driver} ({rep.player_team})",
                        "subtitle": f"Circuito: {rep.track_name} · Vuelta {rep.current_lap}/{rep.total_laps} · Posición P{rep.position}/{rep.total_cars}",
                        "blocks": [
                            {
                                "table": {
                                    "id": "strat_summary",
                                    "columns": [
                                        {"key": "metric", "title": "Parámetro", "width": 190},
                                        {"key": "val", "title": "Estado en Telemetría"},
                                    ],
                                    "rows": [
                                        {"id": "s1", "cells": [{"text": "Recomendación Muro", "tone": "muted"}, {"text": rep.box_recommendation, "pill": True, "tone": "good" if rep.box_recommendation == "STAY OUT" else "warn"}]},
                                        {"id": "s2", "cells": [{"text": "Referencias en Pista", "tone": "muted"}, {"text": f"Delante: {rep.ahead_name} (+{rep.ahead_gap_s:.1f}s) | Detrás: {rep.behind_name} (-{rep.behind_gap_s:.1f}s)"}]},
                                        {"id": "s3", "cells": [{"text": "Neumáticos y Desgaste", "tone": "muted"}, {"text": f"{rep.current_tyre} ({rep.tyre_age} vueltas) · Máx {rep.max_wear_pct:.0f}% ({rep.worst_wheel}) · ~{rep.est_tyre_laps_left} vueltas buenas"}]},
                                        {"id": "s4", "cells": [{"text": "Ventana de Parada", "tone": "muted"}, {"text": f"Vuelta {rep.pit_window_ideal}-{rep.pit_window_latest} -> Salida prevista P{rep.predicted_rejoin_pos} ({rep.recommended_compound})"}]},
                                        {"id": "s5", "cells": [{"text": "Ritmo Comparativo", "tone": "muted"}, {"text": rep.pace_analysis_es}]},
                                        {"id": "s6", "cells": [{"text": "Consejo de Reglajes", "tone": "muted"}, {"text": rep.setup_advice_es}]},
                                    ],
                                    "compact": True,
                                }
                            }
                        ],
                    }
                })
            if standings:
                s_rows = []
                for r in standings:
                    s_rows.append({
                        "id": f"car_{r['pos']}",
                        "cells": [
                            {"text": f"P{r['pos']}", "pill": True, "tone": "accent" if r["is_player"] else "muted"},
                            {"text": f"{r['name']} {'(TÚ)' if r['is_player'] else ''}", "tone": "good" if r["is_player"] else "default"},
                            {"text": r["team"], "tone": "muted"},
                            {"text": r["gap_leader"]},
                            {"text": r["tyre"]},
                            {"text": r["last_lap"], "tone": "muted"},
                        ],
                    })
                blocks.append({
                    "card": {
                        "title": f"Clasificación en Tiempo Real ({len(standings)} coches)",
                        "subtitle": "Parrilla completa decodificada por UDP (20/22/24 coches)",
                        "blocks": [
                            {
                                "table": {
                                    "id": "live_standings",
                                    "columns": [
                                        {"key": "pos", "title": "Pos", "width": 65},
                                        {"key": "drv", "title": "Piloto"},
                                        {"key": "team", "title": "Escudería"},
                                        {"key": "gap", "title": "Gap Líder", "width": 95},
                                        {"key": "tyre", "title": "Goma", "width": 115},
                                        {"key": "lap", "title": "Última Vuelta", "width": 110},
                                    ],
                                    "rows": s_rows,
                                    "compact": True,
                                }
                            }
                        ],
                    }
                })
        elif self.tab == "radio_log":
            rows = []
            for i, entry in enumerate(dialogue):
                rows.append({
                    "id": f"msg_{i}",
                    "cells": [
                        {"text": entry.get("time", ""), "tone": "muted"},
                        {"text": entry.get("lang", "ES"), "pill": True, "tone": "accent"},
                        {"text": entry.get("driver", "")},
                        {"text": entry.get("engineer", ""), "tone": "good"},
                    ],
                })
            blocks.append({
                "card": {
                    "title": "Historial de Radio en Vivo (Piloto ⇄ Ingeniero)",
                    "subtitle": 'Di "Ingeniero, ¿en qué posición voy?" o "¿En cuántas vueltas pillo al de delante?"',
                    "blocks": [
                        {
                            "table": {
                                "id": "transcript",
                                "columns": [
                                    {"key": "time", "title": "Hora", "width": 85},
                                    {"key": "lang", "title": "Idioma", "width": 65},
                                    {"key": "driver", "title": "Piloto"},
                                    {"key": "engineer", "title": f"Ingeniero ({self.cfg.engineer_name})"},
                                ],
                                "rows": rows,
                                "compact": True,
                            }
                        }
                    ],
                }
            })
        else:
            fields = [
                {
                    "select": {
                        "id": "language",
                        "label": "Idioma del Ingeniero (Selección Manual)",
                        "value": "en" if self.cfg.language == "en" else "es",
                        "options": [
                            {"value": "es", "label": "🇪🇸 Español (Voz Álvaro Neural)"},
                            {"value": "en", "label": "🇬🇧 English (Voice Ryan Neural)"},
                        ],
                    }
                },
                {
                    "select": {
                        "id": "voice_mode",
                        "label": "Modo de Activación por Voz",
                        "value": self.cfg.voice_mode,
                        "options": [
                            {"value": "wake_word", "label": 'Palabra Clave ("Ingeniero" / "Marc" + F9)'},
                            {"value": "always_on", "label": "Siempre Escuchando (Directo sin palabra clave)"},
                            {"value": "ptt_only", "label": "Solo Push-To-Talk (Tecla F9)"},
                        ],
                    }
                },
                {
                    "select": {
                        "id": "hud_mode",
                        "label": "HUD de Radio F1 TV dentro del Juego",
                        "value": self.cfg.hud_mode,
                        "options": [
                            {"value": "auto", "label": "📺 Auto-Popup al Hablar o Recibir Radio (Estilo F1 TV)"},
                            {"value": "always", "label": "📌 Siempre Fijo en el HUD del Juego"},
                            {"value": "off", "label": "🚫 Oculto (Solo Audio)"},
                        ],
                    }
                },
                {
                    "select": {
                        "id": "hud_identity_mode",
                        "label": "Identidad y Escudería en el HUD F1 TV",
                        "value": self.cfg.hud_identity_mode,
                        "options": [
                            {"value": "auto", "label": "🏎️ Automático por Telemetría del Coche (LECLERC, SENNA...)"},
                            {"value": "custom", "label": "👤 Usar Siempre Mi Nombre, Escudería y Dorsal"},
                        ],
                    }
                },
                {
                    "select": {
                        "id": "hud_custom_team",
                        "label": "Escudería / Tema de Color F1 TV",
                        "value": self.cfg.hud_custom_team,
                        "options": [
                            {"value": "Ferrari", "label": "Ferrari (Rojo #FF1E27)"},
                            {"value": "McLaren", "label": "McLaren (Papaya #FF8000)"},
                            {"value": "Mercedes", "label": "Mercedes (Petronas #27F4D2)"},
                            {"value": "Red Bull", "label": "Red Bull Racing (#4781D7)"},
                            {"value": "Aston Martin", "label": "Aston Martin (#00E7A7)"},
                            {"value": "Williams", "label": "Williams (#64C4FF)"},
                            {"value": "Alpine", "label": "Alpine (#00A8FF)"},
                            {"value": "Racing Bulls", "label": "Racing Bulls (#6692FF)"},
                            {"value": "Haas", "label": "Haas F1 (#F03A47)"},
                            {"value": "Sauber", "label": "Kick Sauber / Audi (#52E252)"},
                            {"value": "HRT (Hispania)", "label": "HRT Hispania 2010 (#E5B842)"},
                            {"value": "Renault", "label": "Renault F1 2010 (#FFD800)"},
                        ],
                    }
                },
                {
                    "number": {
                        "id": "hud_custom_number",
                        "label": "Dorsal Personalizado (1 - 99)",
                        "value": self.cfg.hud_custom_number,
                        "min": 1,
                        "max": 99,
                        "step": 1,
                    }
                },
                {
                    "select": {
                        "id": "voice_es",
                        "label": "Voz Neural en Español (Edge TTS)",
                        "value": self.cfg.voice_es,
                        "options": [
                            {"value": "es-ES-AlvaroNeural", "label": "Álvaro (España · Ingeniero F1)"},
                            {"value": "es-ES-ElviraNeural", "label": "Elvira (España · Ingeniera F1)"},
                            {"value": "es-MX-JorgeNeural", "label": "Jorge (Latinoamérica · Muro)"},
                            {"value": "es-AR-TomasNeural", "label": "Tomás (Argentina · Muro)"},
                        ],
                    }
                },
                {
                    "select": {
                        "id": "voice_en",
                        "label": "Voz Neural en Inglés (Edge TTS)",
                        "value": self.cfg.voice_en,
                        "options": [
                            {"value": "en-GB-RyanNeural", "label": "Ryan (UK British · GP / Bono Style)"},
                            {"value": "en-GB-ThomasNeural", "label": "Thomas (UK British · Pit Wall)"},
                            {"value": "en-GB-SoniaNeural", "label": "Sonia (UK British · Strategy Engineer)"},
                            {"value": "en-US-GuyNeural", "label": "Guy (US · Race Engineer)"},
                            {"value": "en-AU-WilliamNeural", "label": "William (Australia · Race Engineer)"},
                        ],
                    }
                },
                {
                    "text": {
                        "id": "driver_name",
                        "label": "Tu Nombre de Piloto",
                        "value": self.cfg.driver_name,
                        "max_len": 32,
                    }
                },
                {
                    "text": {
                        "id": "engineer_name",
                        "label": "Nombre del Ingeniero",
                        "value": self.cfg.engineer_name,
                        "max_len": 32,
                    }
                },
                {
                    "text": {
                        "id": "wake_words",
                        "label": "Palabras Clave de Activación (separadas por comas)",
                        "value": self.cfg.wake_words,
                        "max_len": 120,
                    }
                },
                {
                    "text": {
                        "id": "ptt_key",
                        "label": "Tecla Push-To-Talk",
                        "value": self.cfg.ptt_key,
                        "max_len": 16,
                    }
                },
                {
                    "number": {
                        "id": "udp_port",
                        "label": "Puerto UDP de F1 25",
                        "value": self.cfg.udp_port,
                        "min": 1024,
                        "max": 65535,
                        "step": 1,
                    }
                },
                {
                    "slider": {
                        "id": "radio_effect_pct",
                        "label": "Intensidad del Efecto DSP de Radio F1",
                        "value": int(round(self.cfg.radio_effect * 100)),
                        "min": 0,
                        "max": 100,
                        "step": 5,
                        "unit": "%",
                    }
                },
                {
                    "toggle": {
                        "id": "proactive_callouts",
                        "label": "Avisos Proactivos del Ingeniero (DRS, Desgaste, Última Vuelta, Safety Car)",
                        "value": self.cfg.proactive_callouts,
                    }
                },
                {
                    "text": {
                        "id": "gemini_api_key",
                        "label": "Google Gemini API Key (Opcional)",
                        "value": self.cfg.gemini_api_key,
                        "placeholder": "AIzaSy... (déjalo vacío para usar el Motor Estratégico Local)",
                        "max_len": 120,
                    }
                },
            ]
            blocks.append({
                "card": {
                    "title": "Configuración del Ingeniero de Pista",
                    "subtitle": "Los cambios se aplican en tiempo real al guardar",
                    "blocks": [
                        {"form": {"id": "engineer_settings", "columns": 2, "fields": fields}}
                    ],
                }
            })

        return {
            "subtitle": "Ingeniero de Pista por Voz e IA para F1 25/26 (22/24 coches, Estrategia y Radio F1)",
            "tick": True,
            "actions": [
                {"id": "open_hud", "label": "Abrir Ventana Pit Wall HUD", "icon": "activity"},
                {"id": "open_folder", "label": "Abrir Carpeta del Addon", "icon": "folder-open"},
            ],
            "body": {"blocks": blocks},
            "footer": "Activa UDP Telemetry en el puerto 20777 en F1 25 (Settings -> Telemetry Settings).",
        }

    def handle_event(self, event: dict) -> dict | str:
        if "startup" in event:
            self.start_engineer()
            return "none"

        if "tab" in event:
            self.tab = event["tab"].get("tab", "pitwall")
            return "reload"

        if "submit" in event and event["submit"].get("form") == "engineer_settings":
            vals = event["submit"].get("values", {})
            for k in (
                "gemini_api_key",
                "language",
                "voice_mode",
                "hud_mode",
                "hud_identity_mode",
                "hud_custom_team",
                "voice_es",
                "voice_en",
                "driver_name",
                "engineer_name",
                "wake_words",
                "ptt_key",
            ):
                if k in vals and isinstance(vals[k], str):
                    setattr(self.cfg, k, vals[k].strip())
            if "hud_custom_number" in vals:
                self.cfg.hud_custom_number = max(1, min(99, int(vals["hud_custom_number"])))
            if "udp_port" in vals:
                self.cfg.udp_port = int(vals["udp_port"])
            if "radio_effect_pct" in vals:
                self.cfg.radio_effect = float(vals["radio_effect_pct"]) / 100.0
            if "proactive_callouts" in vals:
                self.cfg.proactive_callouts = bool(vals["proactive_callouts"])
            self.cfg.save(self.config_path)
            self.restart_engineer()
            return {"notice": "Ajustes del ingeniero guardados y aplicados"}

        click_id = event.get("click", {}).get("id")
        if click_id == "toggle_engineer":
            if self.app is not None:
                self._manual_start = False
                self.stop_engineer()
                return {"notice": "AI Race Engineer detenido"}
            self._manual_start = True
            self.start_engineer()
            return {"notice": "AI Race Engineer activo y escuchando por radio"}

        if click_id == "open_hud":
            self.open_hud_window()
            return {"notice": "Ventana Pit Wall HUD abierta"}

        if click_id in ("test_pos", "test_strat", "test_rude"):
            if self.app is None:
                self.start_engineer()
            q_map = {
                "test_pos": "¿En qué posición voy y qué coche llevo?",
                "test_strat": "¿Debería parar en boxes ahora? ¿Cuál es la estrategia?",
                "test_rude": "Cállate ya pesado, déjame conducir en paz",
            }
            q = q_map[click_id]
            threading.Thread(target=self.app.handle_driver_message, args=(q,), daemon=True).start()
            return {"notice": f"Radio enviada: '{q}'"}

        if click_id == "open_folder":
            return {"open": str(self.config_path.parent)}

        return "none"

    def handle_tick(self, section: str) -> None:
        try:
            gstatus = self.host.call("game_status", None) or {}
            running = bool(gstatus.get("running"))
        except Exception:
            running = False

        game_active = running or self._is_game_process_running()
        if game_active and self.app is None and (self._hud_proc is None or self._hud_proc.poll() is not None):
            log.info("F1 25 detectado en ejecucion: arrancando AI Race Engineer automaticamente.")
            self.start_engineer()
        elif not game_active and self.app is not None and not self._manual_start:
            log.info("F1 25 cerrado: deteniendo AI Race Engineer.")
            self.stop_engineer()

        cur_len = len(self.app.brain.dialogue_log) if self.app else 0
        pkt_bucket = (self.app.telemetry.state.packet_count // 30) if self.app else -1
        if running != self._last_game_running or cur_len != self._last_log_len or pkt_bucket != self._last_pkt_bucket:
            self._last_pkt_bucket = pkt_bucket
            self.host.invalidate(section)
        return None


def main() -> None:
    host = Host()
    plugin = SwoftyEngineerPlugin(host)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except Exception:
            continue

        method = message.get("method", "")
        params = message.get("params") or {}
        req_id = message.get("id")

        if req_id is None:
            if method == "profile":
                plugin.vanilla = bool(params.get("vanilla", False))
            continue

        try:
            if method == "hello":
                if params.get("data_dir"):
                    plugin.data_dir = Path(params["data_dir"])
                if params.get("cache_dir"):
                    plugin.cache_dir = Path(params["cache_dir"])
                plugin.vanilla = bool(params.get("profile", {}).get("vanilla", False))
                result = {"api": API_VERSION}
            elif method == "view":
                result = plugin.build_view()
            elif method == "event":
                result = plugin.handle_event(params.get("event") or {})
            elif method == "tick":
                result = plugin.handle_tick(params.get("section", "dashboard"))
            elif method == "command":
                args = params.get("args") or []
                if args:
                    if plugin.app is None:
                        plugin.start_engineer()
                    reply, lang = plugin.app.handle_driver_message(" ".join(args))
                    result = f"[{lang.upper()}] {reply}"
                else:
                    st = "LIVE" if plugin.app else "STOPPED"
                    result = f"AI Race Engineer ({plugin.cfg.engineer_name}): {st} on UDP :{plugin.cfg.udp_port}"
            elif method == "summary":
                result = {
                    "label": "ENGINEER",
                    "items": [f"{plugin.cfg.engineer_name} ({plugin.cfg.language.upper()})"],
                }
            else:
                raise RuntimeError(f"Unknown method: {method}")

            host.send({"id": req_id, "result": result})
        except Exception as e:
            log.exception("Error handling %s", method)
            host.send({"id": req_id, "error": str(e)})


if __name__ == "__main__":
    main()
