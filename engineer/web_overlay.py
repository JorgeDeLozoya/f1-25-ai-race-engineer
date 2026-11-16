"""Servidor Web local para OBS Studio / Streamlabs Browser Source (Overlay F1 TV para Streamers)."""
from __future__ import annotations

import http.server
import json
import logging
import socketserver
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import RaceEngineerApp

log = logging.getLogger("web-overlay")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>F1 TV Radio HUD - OBS Browser Source</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: transparent;
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    font-family: "Arial Black", "Arial", sans-serif;
    user-select: none;
  }
  #radio-hud {
    position: absolute;
    top: 48px;
    right: 56px;
    width: 440px;
    background: linear-gradient(135deg, rgba(16, 20, 28, 0.96) 0%, rgba(22, 27, 38, 0.94) 100%);
    border-radius: 10px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.65), 0 0 1px rgba(255, 255, 255, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.12);
    transform: translateX(520px);
    opacity: 0;
    transition: transform 0.42s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease;
    overflow: hidden;
  }
  #radio-hud.visible {
    transform: translateX(0);
    opacity: 1;
  }
  .accent-bar {
    height: 4px;
    width: 100%;
    background: #e10600;
    transition: background 0.3s;
  }
  .hud-header {
    display: flex;
    align-items: center;
    padding: 10px 16px 8px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .team-color-box {
    width: 4px;
    height: 24px;
    border-radius: 2px;
    background: #e10600;
    margin-right: 12px;
  }
  .car-number {
    font-size: 22px;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: -0.5px;
    margin-right: 12px;
  }
  .driver-info {
    flex: 1;
  }
  .driver-name {
    font-size: 15px;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: 1.2px;
    text-transform: uppercase;
  }
  .team-name {
    font-size: 11px;
    color: #9aa2b1;
    font-family: Arial, sans-serif;
    font-weight: 600;
    letter-spacing: 0.5px;
  }
  .radio-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(225, 6, 0, 0.18);
    border: 1px solid rgba(225, 6, 0, 0.4);
    padding: 4px 10px;
    border-radius: 12px;
  }
  .radio-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #e10600;
    animation: blink 1s infinite alternate;
  }
  @keyframes blink {
    from { opacity: 0.3; transform: scale(0.85); }
    to { opacity: 1; transform: scale(1.15); }
  }
  .radio-text {
    font-size: 10px;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: 0.8px;
  }
  .hud-body {
    padding: 14px 18px 16px 18px;
  }
  .speaker-tag {
    font-size: 11px;
    font-weight: 800;
    color: #38bdf8;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .message-text {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.45;
    color: #f1f5f9;
    font-weight: 600;
  }
</style>
</head>
<body>

<div id="radio-hud">
  <div class="accent-bar" id="accent-bar"></div>
  <div class="hud-header">
    <div class="team-color-box" id="team-color-box"></div>
    <div class="car-number" id="car-number">1</div>
    <div class="driver-info">
      <div class="driver-name" id="driver-name">VERSTAPPEN</div>
      <div class="team-name" id="team-name">Red Bull Racing</div>
    </div>
    <div class="radio-pill">
      <div class="radio-dot"></div>
      <div class="radio-text">RADIO</div>
    </div>
  </div>
  <div class="hud-body">
    <div class="speaker-tag" id="speaker-tag">TEAM RADIO</div>
    <div class="message-text" id="message-text">Radio check, five by five.</div>
  </div>
</div>

<script>
  const hud = document.getElementById("radio-hud");
  const accentBar = document.getElementById("accent-bar");
  const teamColorBox = document.getElementById("team-color-box");
  const carNumber = document.getElementById("car-number");
  const driverName = document.getElementById("driver-name");
  const teamName = document.getElementById("team-name");
  const speakerTag = document.getElementById("speaker-tag");
  const messageText = document.getElementById("message-text");

  let lastTs = 0;

  async function pollStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) return;
      const data = await res.json();
      if (data.visible) {
        carNumber.textContent = data.car_number || "1";
        driverName.textContent = data.driver_name || "DRIVER";
        teamName.textContent = data.team_name || "Formula 1";
        speakerTag.textContent = data.speaker || "TEAM RADIO";
        messageText.textContent = data.message || "...";
        const col = data.color || "#e10600";
        accentBar.style.background = col;
        teamColorBox.style.background = col;
        hud.classList.add("visible");
      } else {
        hud.classList.remove("visible");
      }
    } catch (e) {}
  }

  setInterval(pollStatus, 250);
</script>

</body>
</html>
"""

class OverlayServer:
    def __init__(self, app: RaceEngineerApp, port: int = 8088):
        self.app = app
        self.port = port
        self.httpd = None
        self._thread = None
        self.current_state = {
            "visible": False,
            "driver_name": "DRIVER",
            "car_number": "1",
            "team_name": "Formula 1",
            "speaker": "TEAM RADIO",
            "message": "Radio check five by five.",
            "color": "#e10600",
            "until": 0.0,
        }

    def trigger(self, driver: str, number: str, team: str, speaker: str, msg: str, color: str, duration: float = 6.5) -> None:
        self.current_state = {
            "visible": True,
            "driver_name": driver.upper(),
            "car_number": number,
            "team_name": team,
            "speaker": speaker.upper(),
            "message": msg,
            "color": color,
            "until": time.time() + duration,
        }

    def start(self) -> None:
        server_instance = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silenciar logs para no ensuciar la consola

            def do_GET(self):
                if self.path in ("/", "/overlay", "/obs"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
                elif self.path == "/api/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    st = dict(server_instance.current_state)
                    if time.time() > st["until"]:
                        st["visible"] = False
                    self.wfile.write(json.dumps(st).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        def _runner():
            for p in (self.port, 8089, 8090, 8099):
                try:
                    self.httpd = socketserver.TCPServer(("0.0.0.0", p), Handler)
                    self.port = p
                    log.info("OBS Streamer Web Overlay Server iniciado en http://localhost:%d/overlay", p)
                    self.httpd.serve_forever()
                    break
                except OSError:
                    continue

        self._thread = threading.Thread(target=_runner, daemon=True, name="obs-overlay-server")
        self._thread.start()

    def stop(self) -> None:
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
