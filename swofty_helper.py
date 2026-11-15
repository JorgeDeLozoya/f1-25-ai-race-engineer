"""Plugin de Swofty Launcher (JSON-RPC sobre stdin/stdout) para AI Race Engineer."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
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

from engineer.app import RaceEngineerApp  # noqa: E402
from engineer.config import EngineerConfig  # noqa: E402

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
        self.tab = "settings"
        self.cfg = EngineerConfig.load(self.config_path)
        self.app: RaceEngineerApp | None = None
        self._last_log_len = 0
        self._last_game_running = False

    @property
    def config_path(self) -> Path:
        local_cfg = Path(__file__).resolve().parent / "config.json"
        if local_cfg.exists():
            return local_cfg
        return self.data_dir / "config.json"

    def start_engineer(self) -> None:
        if self.app is not None:
            return
        self.cfg = EngineerConfig.load(self.config_path)
        self.app = RaceEngineerApp(
            self.cfg,
            status_file=self.cache_dir / "runtime_status.json",
            enable_voice=True,
        )
        self.app.start()
        log.info("AI Race Engineer iniciado dentro de Swofty Launcher.")

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

    def build_view(self) -> dict:
        self.cfg = EngineerConfig.load(self.config_path)
        try:
            gstatus = self.host.call("game_status", None) or {}
        except Exception:
            gstatus = {}
        game_running = bool(gstatus.get("running"))
        self._last_game_running = game_running

        eng_running = self.app is not None
        udp_ok = bool(self.app and self.app.telemetry.state.connected)
        has_key = bool(self.cfg.resolved_api_key())
        dialogue = list(self.app.brain.dialogue_log) if self.app else []
        self._last_log_len = len(dialogue)

        pills = [
            {
                "text": "ENGINEER LIVE (Voice Active)" if eng_running else "Engineer Stopped",
                "tone": "good" if eng_running else "muted",
                "dot": True,
            },
            {
                "text": "UDP 20777 Connected" if udp_ok else f"Waiting UDP :{self.cfg.udp_port}",
                "tone": "good" if udp_ok else "warn",
                "dot": True,
            },
            {
                "text": "Gemini AI Active" if has_key else "Local Tactical Brain (No API Key)",
                "tone": "accent" if has_key else "warn",
            },
        ]

        hero = {
            "hero": {
                "title": f"AI Race Engineer · {self.cfg.engineer_name}",
                "subtitle": (
                    f"Driver: {self.cfg.driver_name} · Lang: {self.cfg.language.upper()} · "
                    f"Wake words: {self.cfg.wake_words}"
                ),
                "art": {"monogram": "RE"},
                "pills": pills,
                "facts": [
                    {"label": "UDP Port", "value": str(self.cfg.udp_port)},
                    {"label": "PTT Key", "value": self.cfg.ptt_key.upper()},
                    {"label": "Voices", "value": f"{self.cfg.voice_es} / {self.cfg.voice_en}"},
                ],
                "buttons": [
                    {
                        "id": "toggle_engineer",
                        "label": "Stop Engineer" if eng_running else "Start Engineer",
                        "icon": "trash" if eng_running else "play",
                        "style": "danger" if eng_running else "primary",
                    },
                    {
                        "id": "test_es",
                        "label": "Test Radio (ES Top 5)",
                        "icon": "zap",
                        "style": "outline",
                    },
                    {
                        "id": "test_en",
                        "label": "Test Radio (EN Top 5)",
                        "icon": "zap",
                        "style": "outline",
                    },
                    {
                        "id": "test_offtopic",
                        "label": "Test Off-Topic",
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
                    {"id": "settings", "label": "Engineer Settings", "icon": "settings"},
                    {
                        "id": "radio_log",
                        "label": "Live Team Radio Log",
                        "icon": "activity",
                        "badge": str(len(dialogue)),
                    },
                ],
            }
        }

        blocks = [hero, tabs]

        if self.tab == "radio_log":
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
                    "title": "Team Radio Transcript",
                    "subtitle": "Say 'Radio, ¿cuáles son las 5 primeras posiciones?' or 'Engineer, what are the top 5?'",
                    "blocks": [
                        {
                            "table": {
                                "id": "transcript",
                                "columns": [
                                    {"key": "time", "title": "Time", "width": 85},
                                    {"key": "lang", "title": "Lang", "width": 65},
                                    {"key": "driver", "title": "Driver (You)"},
                                    {"key": "engineer", "title": f"Engineer ({self.cfg.engineer_name})"},
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
                    "text": {
                        "id": "gemini_api_key",
                        "label": "Google Gemini API Key",
                        "value": self.cfg.gemini_api_key,
                        "placeholder": "AIzaSy... (leave empty for local tactical brain)",
                        "max_len": 120,
                        "help": "Get a free key at aistudio.google.com",
                    }
                },
                {
                    "select": {
                        "id": "language",
                        "label": "Radio Language",
                        "value": self.cfg.language,
                        "options": [
                            {"value": "auto", "label": "Bilingual Auto (Spanish & English)"},
                            {"value": "es", "label": "Español (es-ES-AlvaroNeural)"},
                            {"value": "en", "label": "English (en-GB-RyanNeural)"},
                        ],
                    }
                },
                {
                    "text": {
                        "id": "driver_name",
                        "label": "Your Driver Name",
                        "value": self.cfg.driver_name,
                        "max_len": 32,
                    }
                },
                {
                    "text": {
                        "id": "engineer_name",
                        "label": "Engineer Name",
                        "value": self.cfg.engineer_name,
                        "max_len": 32,
                    }
                },
                {
                    "text": {
                        "id": "wake_words",
                        "label": "Voice Wake Words (comma-separated)",
                        "value": self.cfg.wake_words,
                        "max_len": 120,
                        "help": "Say one of these words followed by your question.",
                    }
                },
                {
                    "text": {
                        "id": "ptt_key",
                        "label": "Optional Push-To-Talk Key",
                        "value": self.cfg.ptt_key,
                        "max_len": 16,
                    }
                },
                {
                    "number": {
                        "id": "udp_port",
                        "label": "F1 25 UDP Telemetry Port",
                        "value": self.cfg.udp_port,
                        "min": 1024,
                        "max": 65535,
                        "step": 1,
                    }
                },
                {
                    "slider": {
                        "id": "radio_effect_pct",
                        "label": "F1 Radio DSP Effect Intensity",
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
                        "label": "Proactive Race Control Callouts (Safety Car, Penalties, Fastest Lap)",
                        "value": self.cfg.proactive_callouts,
                    }
                },
            ]
            blocks.append({
                "card": {
                    "title": "Configuration",
                    "subtitle": "Changes apply immediately to your Race Engineer",
                    "blocks": [
                        {"form": {"id": "engineer_settings", "columns": 2, "fields": fields}}
                    ],
                }
            })

        return {
            "subtitle": "Voice-activated F1 25/26 Race Engineer (UDP + Gemini + Edge TTS Radio)",
            "tick": True,
            "actions": [
                {"id": "open_folder", "label": "Open Config Folder", "icon": "folder-open"}
            ],
            "body": {"blocks": blocks},
            "footer": "Enable UDP Telemetry on port 20777 (Format 2025) in F1 25 Settings -> Telemetry Settings.",
        }

    def handle_event(self, event: dict) -> dict | str:
        if "startup" in event:
            self.start_engineer()
            return "none"

        if "tab" in event:
            self.tab = event["tab"].get("tab", "settings")
            return "reload"

        if "submit" in event and event["submit"].get("form") == "engineer_settings":
            vals = event["submit"].get("values", {})
            for k in ("gemini_api_key", "language", "driver_name", "engineer_name", "wake_words", "ptt_key"):
                if k in vals and isinstance(vals[k], str):
                    setattr(self.cfg, k, vals[k].strip())
            if "udp_port" in vals:
                self.cfg.udp_port = int(vals["udp_port"])
            if "radio_effect_pct" in vals:
                self.cfg.radio_effect = float(vals["radio_effect_pct"]) / 100.0
            if "proactive_callouts" in vals:
                self.cfg.proactive_callouts = bool(vals["proactive_callouts"])
            self.cfg.save(self.config_path)
            self.restart_engineer()
            return {"notice": "Race Engineer settings saved"}

        click_id = event.get("click", {}).get("id")
        if click_id == "toggle_engineer":
            if self.app is not None:
                self.stop_engineer()
                return {"notice": "AI Race Engineer stopped"}
            self.start_engineer()
            return {"notice": "AI Race Engineer started (listening for wake word)"}

        if click_id in ("test_es", "test_en", "test_offtopic"):
            if self.app is None:
                self.start_engineer()
            q_map = {
                "test_es": "¿Cuáles son las cinco primeras posiciones ahora mismo?",
                "test_en": "What are the top five positions right now?",
                "test_offtopic": "Oye, ¿qué película me recomiendas ver esta noche?",
            }
            q = q_map[click_id]
            threading.Thread(target=self.app.handle_driver_message, args=(q,), daemon=True).start()
            return {"notice": f"Driver radio sent: '{q}'"}

        if click_id == "open_folder":
            return {"open": str(self.config_path.parent)}

        return "none"

    def handle_tick(self, section: str) -> None:
        try:
            gstatus = self.host.call("game_status", None) or {}
            running = bool(gstatus.get("running"))
        except Exception:
            running = False
        cur_len = len(self.app.brain.dialogue_log) if self.app else 0
        if running != self._last_game_running or cur_len != self._last_log_len:
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
