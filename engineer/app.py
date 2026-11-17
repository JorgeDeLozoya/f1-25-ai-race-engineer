"""Aplicacion principal que coordina UDP Telemetry, Voz (Wake Word), Gemini y Radio TTS."""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from .brain import EngineerBrain
from .config import DEFAULT_CONFIG_PATH, EngineerConfig
from .telemetry import packets as P
from .telemetry.context import build_standings
from .telemetry.listener import RaceState, TelemetryListener
from .tts import RadioSpeaker
from .voice import VoiceListener
from .web_overlay import OverlayServer

log = logging.getLogger("engineer")
PID_FILE = DEFAULT_CONFIG_PATH.parent / "engineer.pid"
CTRL_FILE = DEFAULT_CONFIG_PATH.parent / "engineer.ctrl"
_CTRL_QUIT_CB: Callable[[], None] | None = None
_CTRL_SOCK: socket.socket | None = None


def register_shutdown_callback(cb: Callable[[], None]) -> None:
    """Registra el callback de cierre limpio ante una nueva instancia o comando stop."""
    global _CTRL_QUIT_CB
    _CTRL_QUIT_CB = cb


def request_running_instance_stop(timeout: float = 0.4) -> bool:
    """Solicita por loopback local que cualquier instancia previa se cierre limpiamente."""
    if not CTRL_FILE.exists():
        return False
    try:
        port = int(CTRL_FILE.read_text(encoding="utf-8").strip())
        if port <= 0:
            return False
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as conn:
            conn.sendall(b"QUIT\n")
        return True
    except Exception:
        return False


def ensure_single_instance() -> None:
    """Cierra cualquier instancia previa de AI Race Engineer por canal local para evitar audio duplicado."""
    global _CTRL_SOCK
    if request_running_instance_stop():
        time.sleep(0.35)

    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    if _CTRL_SOCK is not None:
        return

    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(2)
        _CTRL_SOCK = srv
        port = srv.getsockname()[1]
        CTRL_FILE.parent.mkdir(parents=True, exist_ok=True)
        CTRL_FILE.write_text(str(port), encoding="utf-8")

        def _serve_ctrl() -> None:
            while True:
                try:
                    conn, _ = srv.accept()
                    with conn:
                        data = conn.recv(64)
                    if b"QUIT" in data:
                        if _CTRL_QUIT_CB is not None:
                            try:
                                _CTRL_QUIT_CB()
                            except Exception:
                                pass
                        time.sleep(0.15)
                        os._exit(0)
                except OSError:
                    break
                except Exception:
                    continue

        threading.Thread(target=_serve_ctrl, daemon=True, name="instance-ctrl").start()
    except Exception:
        pass


class RaceEngineerApp:
    def __init__(self, cfg: EngineerConfig, status_file: Path | None = None,
                 enable_voice: bool = True):
        self.cfg = cfg
        self.status_file = status_file or (DEFAULT_CONFIG_PATH.parent / "runtime_status.json")
        self.speaker = RadioSpeaker(cfg)
        self.brain = EngineerBrain(cfg)
        self.telemetry = TelemetryListener(
            host=cfg.udp_host,
            port=cfg.udp_port,
            forward_to=cfg.udp_forward,
            on_event=self._on_race_event,
        )
        self.voice = (
            VoiceListener(
                cfg=cfg,
                on_query=self.handle_driver_message,
                is_speaking_fn=lambda: self.speaker.is_speaking,
            )
            if enable_voice
            else None
        )
        self._stop = threading.Event()
        self._msg_lock = threading.Lock()
        self.active_driver_query: str = ""
        self.hud_preview_until: float = 0.0
        self.web_overlay = OverlayServer(self, port=getattr(self.cfg, "obs_overlay_port", 8088))

    def start(self) -> None:
        self.telemetry.start()
        if self.voice:
            self.voice.start()
        self.web_overlay.start()
        threading.Thread(target=self._status_Loop, daemon=True, name="status-writer").start()

    def stop(self) -> None:
        self._stop.set()
        self.telemetry.stop()
        if self.voice:
            self.voice.stop()
        self.web_overlay.stop()
        self._write_status(running=False)

    def restart_voice(self) -> None:
        """Reinicia la captura de microfono en caliente cuando se cambia de dispositivo de entrada en Ajustes."""
        if self.voice:
            self.voice.stop()
        self.voice = VoiceListener(
            cfg=self.cfg,
            on_query=self.handle_driver_message,
            is_speaking_fn=lambda: self.speaker.is_speaking,
        )
        self.voice.start()

    def handle_driver_message(self, text: str, save_wav: Path | str | None = None) -> tuple[str, str]:
        if not self._msg_lock.acquire(blocking=False):
            return "", "es"
        try:
            self.active_driver_query = text
            with self.telemetry.lock:
                state = self.telemetry.state
            reply, lang = self.brain.ask(text, state)
            self.active_driver_query = ""
            log.info("[%s - %s]: %s", self.cfg.engineer_name.upper(), lang.upper(), reply)
            self._write_status(running=True)

            try:
                from .strategy import analyze_strategy
                from .telemetry import lookups as L
                rep = analyze_strategy(state, self.cfg.driver_name)
                drv, color, badge, num = L.resolve_radio_identity(
                    rep.player_driver,
                    rep.player_team,
                    fallback_driver=self.cfg.driver_name,
                    race_number=rep.player_race_number,
                )
                self.web_overlay.trigger(
                    driver=drv,
                    number=str(num),
                    team=rep.player_team or "Formula 1",
                    speaker=self.cfg.engineer_name or "Engineer",
                    msg=reply,
                    color=color,
                    badge=badge,
                    duration=getattr(self.cfg, "hud_hold_seconds", 6.5),
                )
            except Exception:
                pass

            self.speaker.speak(reply, lang=lang, save_wav=save_wav, blocking=True)
            return reply, lang
        finally:
            self.active_driver_query = ""
            self._msg_lock.release()

    def _on_race_event(self, ev: P.Event, state: RaceState) -> None:
        callout = self.brain.format_proactive_event(ev, state)
        if callout:
            msg, lang = callout
            log.info("[RADIO PROACTIVA - %s]: %s", lang.upper(), msg)
            self._write_status(running=True)
            threading.Thread(
                target=self.speaker.speak, args=(msg, lang), daemon=True
            ).start()

    def _status_Loop(self) -> None:
        while not self._stop.is_set():
            self._write_status(running=True)
            if not self.speaker.is_speaking:
                with self.telemetry.lock:
                    st = self.telemetry.state
                spotter_callout = self.brain.check_proactive_spotter(st)
                if spotter_callout:
                    msg, lang = spotter_callout
                    log.info("[SPOTTER PROACTIVO - %s]: %s", lang.upper(), msg)
                    self._write_status(running=True)
                    threading.Thread(
                        target=self.speaker.speak, args=(msg, lang), daemon=True
                    ).start()
            time.sleep(1.0)

    def _write_status(self, running: bool) -> None:
        try:
            with self.telemetry.lock:
                st = self.telemetry.state
                standings = build_standings(st, limit=10) if st.connected else []
                payload = {
                    "running": running,
                    "pid": os.getpid(),
                    "updated_at": time.time(),
                    "udp_connected": st.connected,
                    "udp_port": self.cfg.udp_port,
                    "voice_ready": bool(self.voice and self.voice.ready),
                    "voice_error": self.voice.last_error if self.voice else "",
                    "has_api_key": bool(self.cfg.resolved_api_key()),
                    "standings": standings,
                    "dialogue": list(self.brain.dialogue_log),
                }
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            self.status_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Race Engineer para F1 25 (Swofty Addon & Standalone)")
    parser.add_argument("--config", type=str, default=None, help="Ruta a config.json")
    parser.add_argument("--status-file", type=str, default=None, help="Ruta a runtime_status.json")
    parser.add_argument("--daemon", action="store_true", help="Ejecutar en segundo plano sin prompt interactivo")
    parser.add_argument("--gui", action="store_true", help="Abrir ventana grafica F1 Team Radio (ideal para compartir pantalla)")
    parser.add_argument("--no-voice", action="store_true", help="Desactivar captura de microfono")
    parser.add_argument("--demo", action="store_true", help="Ejecutar demostracion de voz y radio (ES + EN)")
    parser.add_argument("--stop", action="store_true", help="Detener limpiamente cualquier instancia activa")
    args = parser.parse_args()

    if args.stop:
        request_running_instance_stop()
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = EngineerConfig.load(args.config)
    status_path = Path(args.status_file) if args.status_file else None

    if args.demo:
        app = RaceEngineerApp(cfg, status_file=status_path, enable_voice=False)
        samples_dir = DEFAULT_CONFIG_PATH.parent / "demo_audio"
        samples_dir.mkdir(exist_ok=True)
        print("\n=== DEMO 1 (ESPANOL - Top 5 posiciones) ===")
        q1 = "¿Cuáles son las cinco primeras posiciones ahora mismo?"
        print(f"Piloto: {q1}")
        r1, _ = app.handle_driver_message(q1, save_wav=samples_dir / "demo_es_top5.wav")
        print(f"Ingeniero: {r1}\n")

        print("=== DEMO 2 (ESPANOL - Pregunta fuera de lugar) ===")
        q2 = "Oye, ¿cómo se hace una tortilla de patatas?"
        print(f"Piloto: {q2}")
        r2, _ = app.handle_driver_message(q2, save_wav=samples_dir / "demo_es_offtopic.wav")
        print(f"Ingeniero: {r2}\n")

        print("=== DEMO 3 (ENGLISH - Top 5 & Strategy) ===")
        q3 = "What are the top five positions and how are my tyres?"
        print(f"Driver: {q3}")
        r3, _ = app.handle_driver_message(q3, save_wav=samples_dir / "demo_en_top5.wav")
        print(f"Engineer: {r3}\n")

        print("=== DEMO 4 (ENGLISH - Off-topic) ===")
        q4 = "Who won the Champions League last night?"
        print(f"Driver: {q4}")
        r4, _ = app.handle_driver_message(q4, save_wav=samples_dir / "demo_en_offtopic.wav")
        print(f"Engineer: {r4}\n")
        return

    if not args.demo:
        ensure_single_instance()

    app = RaceEngineerApp(cfg, status_file=status_path, enable_voice=not args.no_voice)
    register_shutdown_callback(app.stop)

    if args.gui:
        from .gui import PitWallWindow
        win = PitWallWindow(app)
        win.run()
        return

    if args.daemon:
        try:
            from .overlay import run_daemon_with_overlay
            run_daemon_with_overlay(app)
            return
        except Exception:
            pass

    app.start()

    print("=" * 68)
    print(f"  F1 25/26 AI RACE ENGINEER ({cfg.engineer_name}) - LISTO EN MURO DE BOXES")
    print("=" * 68)
    print(f"  * Puerto UDP F1 25 : {cfg.udp_host}:{cfg.udp_port}")
    print(f"  * Idioma           : {cfg.language.upper()} (ES voz: {cfg.voice_es} | EN voz: {cfg.voice_en})")
    print(f"  * Palabras clave   : {cfg.wake_words}")
    print(f"  * Tecla PTT        : [{cfg.ptt_key.upper()}]")
    print(f"  * Gemini API Key   : {'Configurada (IA activa)' if cfg.resolved_api_key() else 'No configurada (Usando motor tactico local)'}")
    print("-" * 68)
    print("  Habla por el microfono diciendo 'Radio, ¿cuales son las 5 primeras posiciones?'")
    print("  o escribe cualquier pregunta aqui abajo y pulsa ENTER (escribe 'salir' para cerrar).")
    print("=" * 68)

    try:
        if args.daemon:
            while True:
                time.sleep(1.0)
        else:
            for line in sys.stdin:
                q = line.strip()
                if not q:
                    continue
                if q.lower() in ("salir", "exit", "quit"):
                    break
                app.handle_driver_message(q)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
