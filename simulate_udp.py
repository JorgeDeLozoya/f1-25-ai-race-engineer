"""Simulador de paquetes UDP binarios de F1 25 (formato 2025) para pruebas."""
from __future__ import annotations

import socket
import struct

from engineer.telemetry import packets as P


def make_header(packet_id: int, player_idx: int = 3, session_uid: int = 0xCAFE2025) -> bytes:
    return P.HEADER.pack(
        2025, 25, 1, 0, 1, packet_id, session_uid, 320.5, 1200, 1200, player_idx, 255
    )


def send_test_telemetry(host: str = "127.0.0.1", port: int = 20777, final_lap: bool = False) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    total_laps = 24
    cur_lap = 24 if final_lap else 14

    # 0. Session packet (ID 1) - Silverstone (7), Race (15), 24 laps, pit window 11..15, rejoin P7
    sess_head = P.SESSION_HEAD.pack(
        1, 29, 21, total_laps, 5891, 15, 7, 0, 1800, 3600, 80, 0, 0, 0, 0, 0
    )
    marshal = b"\x00" * (21 * P.MARSHAL_ZONE)
    sc_and_fc_hdr = bytes([0, 0, 2])
    fc1 = P.FORECAST.pack(15, 5, 1, 28, 0, 21, 0, 25)
    fc2 = P.FORECAST.pack(15, 15, 3, 25, 0, 19, 0, 65)
    fc_pad = b"\x00" * ((64 - 2) * P.FORECAST.size)
    links = b"\x00" * 14
    pit_win = bytes([11, 15, 7])
    pkt_session = make_header(1) + sess_head + marshal + sc_and_fc_hdr + fc1 + fc2 + fc_pad + links + pit_win + (b"\x00" * 64)
    sock.sendto(pkt_session, (host, port))

    # 1. Participants packet (ID 4)
    drivers = [
        ("VERSTAPPEN", 2), ("NORRIS", 8), ("LECLERC", 1), ("HAMILTON", 0),
        ("SAINZ", 3), ("HAMILTON", 1), ("RUSSELL", 0), ("ALONSO", 4),
        ("PIASTRI", 8), ("GASLY", 5),
    ]
    part_entries = bytearray()
    for i in range(P.NUM_CARS):
        name, team = drivers[i] if i < len(drivers) else (f"DRIVER_{i+1}", i % 10)
        entry = P.PART_HEAD.pack(
            0 if i == 3 else 1, i, 0, team, 0, i + 1, 1,
            name.encode("utf-8").ljust(32, b"\x00"),
            1, 1, 0, 1, 4
        ) + (b"\x00" * 12)
        part_entries.extend(entry)
    pkt_participants = make_header(4) + bytes([len(drivers)]) + bytes(part_entries)
    sock.sendto(pkt_participants, (host, port))

    # 2. Lap Data packet (ID 2)
    lap_entries = bytearray()
    for i in range(P.NUM_CARS):
        pos = i + 1
        delta_front = 1400 if i > 0 else 0
        delta_lead = i * 1900
        entry = P.LAP.pack(
            89450 + i * 210, 42100,
            28100, 0, 31200, 0,
            delta_front, 0, delta_lead, 0,
            2150.0, 45000.0, 0.0,
            pos, cur_lap, 0, 0, 1, 0, 0, 0, 0, 0, 0, pos, 4, 2,
            0, 1200, 100, 0, 0.0, 0
        )
        lap_entries.extend(entry)
    pkt_laps = make_header(2) + bytes(lap_entries) + b"\x00\x00"
    sock.sendto(pkt_laps, (host, port))

    # 3. Car Status packet (ID 7)
    status_entries = bytearray()
    for i in range(P.NUM_CARS):
        entry = P.STATUS.pack(
            0, 0, 1, 56, 0, 18.5, 110.0, 1.35,
            13000, 3800, 15, 1, 0, 17, 17, 11, 0,
            300, 750, 2900000.0, 1, 400000.0, 350000.0, 1200000.0, 0
        )
        status_entries.extend(entry)
    sock.sendto(make_header(7) + bytes(status_entries), (host, port))

    # 4. Car Damage packet (ID 10)
    dmg_entries = bytearray()
    for i in range(P.NUM_CARS):
        wear = (46.0, 48.0, 54.0, 51.0) if final_lap else (32.0, 34.0, 39.0, 36.0)
        entry = P.DAMAGE.pack(
            *wear,
            0, 0, 0, 0,
            0, 0, 0, 0,
            0, 0, 0, 0,
            *(0 for _ in range(18))
        )
        dmg_entries.extend(entry)
    sock.sendto(make_header(10) + bytes(dmg_entries), (host, port))
    sock.close()


if __name__ == "__main__":
    print("Enviando telemetria UDP simulada de F1 25 a 127.0.0.1:20777...")
    send_test_telemetry()
    print("Paquetes enviados correctamente.")
