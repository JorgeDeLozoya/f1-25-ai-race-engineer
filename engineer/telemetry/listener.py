"""Escucha el puerto UDP del juego y mantiene el estado de la carrera."""
from __future__ import annotations

import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from . import packets as P

log = logging.getLogger("telemetry")


@dataclass
class RaceState:
    session_uid: int = 0
    player_idx: int = 0
    session: P.Session | None = None
    laps: list[P.LapData] = field(default_factory=list)
    participants: list[P.Participant] = field(default_factory=list)
    num_active: int = 0
    status: list[P.CarStatus] = field(default_factory=list)
    damage: list[P.CarDamage] = field(default_factory=list)
    telemetry: list[P.CarTelemetry] = field(default_factory=list)
    best_laps: dict[int, int] = field(default_factory=dict)       # idx -> ms
    fastest_lap: tuple[int, float] | None = None                    # (idx, seconds)
    last_packet_time: float = 0.0
    packet_count: int = 0
    packet_format: int = 2025

    @property
    def connected(self) -> bool:
        return time.time() - self.last_packet_time < 3.0


class TelemetryListener(threading.Thread):
    """Hilo que recibe los paquetes, actualiza RaceState y emite eventos."""

    def __init__(self, host: str = "0.0.0.0", port: int = 20777,
                 forward_to: list[str] | None = None,
                 on_event: Callable[[P.Event, RaceState], None] | None = None):
        super().__init__(daemon=True, name="udp-listener")
        self.host, self.port = host, port
        self.on_event = on_event
        self.state = RaceState()
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._fwd = []
        for target in forward_to or []:
            h, _, p = target.rpartition(":")
            self._fwd.append((h or "127.0.0.1", int(p)))
        self._fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if self._fwd else None

    def stop(self):
        self._stop.set()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.settimeout(0.5)
        log.info("Escuchando telemetria UDP en %s:%d", self.host, self.port)
        warned_format = False
        while not self._stop.is_set():
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as e:          # p.ej. WSAECONNRESET en Windows
                log.debug("socket: %s", e)
                continue
            for target in self._fwd:
                try:
                    self._fwd_sock.sendto(data, target)
                except OSError:
                    pass
            hdr = P.parse_header(data)
            if hdr is None:
                continue
            if hdr.packet_format != 2025 and not warned_format:
                log.warning("Formato UDP %s detectado. Pon 'UDP Format' = 2025 en el juego.",
                            hdr.packet_format)
                warned_format = True
            parser = P.PARSERS.get(hdr.packet_id)
            if parser is None:
                continue
            try:
                parsed = parser(data)
            except Exception as e:  # noqa: BLE001 - nunca tumbar el hilo
                log.debug("Error parseando paquete %d: %s", hdr.packet_id, e)
                continue
            self._apply(hdr, parsed)
        sock.close()

    def _apply(self, hdr: P.Header, parsed):
        event = None
        with self.lock:
            st = self.state
            if hdr.session_uid != st.session_uid and hdr.session_uid != 0:
                log.info("Nueva sesion detectada (%x)", hdr.session_uid)
                self.state = st = RaceState(session_uid=hdr.session_uid)
            st.player_idx = hdr.player_car_index
            st.last_packet_time = time.time()
            st.packet_count += 1
            st.packet_format = hdr.packet_format
            pid = hdr.packet_id
            if pid == 1 and parsed:
                st.session = parsed
            elif pid == 2 and parsed:
                prev = st.laps
                st.laps = parsed
                # registrar mejores vueltas a partir de last_lap al cambiar de vuelta
                for i, ld in enumerate(parsed):
                    if prev and i < len(prev) and ld.lap != prev[i].lap and ld.last_lap_ms > 0:
                        best = st.best_laps.get(i)
                        if best is None or ld.last_lap_ms < best:
                            st.best_laps[i] = ld.last_lap_ms
            elif pid == 3 and parsed:
                event = parsed
                if parsed.code == "FTLP":
                    st.fastest_lap = (parsed.vehicle, parsed.value)
            elif pid == 4:
                st.num_active, st.participants = parsed
            elif pid == 6 and parsed:
                st.telemetry = parsed
            elif pid == 7 and parsed:
                st.status = parsed
            elif pid == 10 and parsed:
                st.damage = parsed
        if event and self.on_event:
            try:
                self.on_event(event, self.state)
            except Exception:  # noqa: BLE001
                log.exception("Error en on_event")
