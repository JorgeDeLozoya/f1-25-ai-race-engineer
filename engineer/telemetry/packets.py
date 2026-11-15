"""Decodificador de los paquetes UDP de F1 25 / F1 26 (formatos 2024, 2025 y 2026 + Swofty).

Se decodifican todos los paquetes utiles para el ingeniero y para parrillas de 22 y 24 coches:
  1  Session
  2  Lap Data (22 o 24 coches, formato 50B o 57B)
  3  Event
  4  Participants (22 o 24 coches, formato 2024/2025/2026)
  6  Car Telemetry (22 o 24 coches)
  7  Car Status (22 o 24 coches)
  10 Car Damage (22 o 24 coches)
  11 Session History (por coche 0..23: tiempos de vuelta, sectores y stints de neumaticos)
  12 Tyre Sets (por coche 0..23: desgaste exacto y vida restante del juego montado)
  15 Lap Positions (posiciones por vuelta hasta 24 coches)
  200 Swofty Track (nombre del circuito en mods de Swofty cuando trackId == -1)
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct

NUM_CARS = 22
MAX_CARS = 24

HEADER = struct.Struct("<HBBBBBQfIIBB")  # 29 bytes


@dataclass
class Header:
    packet_format: int
    game_year: int
    packet_id: int
    session_uid: int
    session_time: float
    frame: int
    player_car_index: int


def parse_header(data: bytes) -> Header | None:
    if len(data) < HEADER.size:
        return None
    (fmt, year, _maj, _min, _pver, pid, uid, stime, frame, _oframe,
     player, _second) = HEADER.unpack_from(data, 0)
    return Header(fmt, year, pid, uid, stime, frame, player)


def _detect_cars_and_stride(body: int, preferred_strides: tuple[int, ...]) -> tuple[int, int]:
    """Detecta dinamicamente (num_cars, stride) para 22 o 24 coches."""
    for n_cars in (24, 22):
        for s in preferred_strides:
            if body == n_cars * s:
                return n_cars, s
    for n_cars in (22, 24):
        if body > 0 and body % n_cars == 0:
            return n_cars, body // n_cars
    return NUM_CARS, body // NUM_CARS if body > 0 else 0


# ---------------------------------------------------------------- Lap Data (2)
LAP = struct.Struct("<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB")  # 57 bytes (2025/2026)
LAP_2024 = struct.Struct("<IIHBHBHHfffBBBBBBBBBBBBBBBHHBfB")  # 50 bytes (2024)


@dataclass
class LapData:
    last_lap_ms: int
    current_lap_ms: int
    s1_ms: int
    s2_ms: int
    delta_front_ms: int
    delta_leader_ms: int
    lap_distance: float
    total_distance: float
    position: int
    lap: int
    pit_status: int          # 0 none, 1 pitting, 2 in pit area
    num_pit_stops: int
    sector: int              # 0,1,2
    lap_invalid: bool
    penalties_s: int
    warnings: int
    corner_cut_warnings: int
    unserved_dt: int
    unserved_sg: int
    grid_position: int
    driver_status: int       # 0 garage, 1 flying, 2 in lap, 3 out lap, 4 on track
    result_status: int       # 2 active, 3 finished, 4 dnf, 5 dsq, 6 not classified, 7 retired


def parse_lap_data(data: bytes) -> list[LapData]:
    body = len(data) - HEADER.size - 2
    n_cars, stride = _detect_cars_and_stride(body, (57, 50))
    out: list[LapData] = []
    if stride >= 57:
        for i in range(n_cars):
            v = LAP.unpack_from(data, HEADER.size + i * stride)
            out.append(LapData(
                last_lap_ms=v[0], current_lap_ms=v[1],
                s1_ms=v[3] * 60000 + v[2], s2_ms=v[5] * 60000 + v[4],
                delta_front_ms=v[7] * 60000 + v[6], delta_leader_ms=v[9] * 60000 + v[8],
                lap_distance=v[10], total_distance=v[11],
                position=v[13], lap=v[14], pit_status=v[15], num_pit_stops=v[16],
                sector=v[17], lap_invalid=bool(v[18]), penalties_s=v[19], warnings=v[20],
                corner_cut_warnings=v[21], unserved_dt=v[22], unserved_sg=v[23],
                grid_position=v[24], driver_status=v[25], result_status=v[26],
            ))
    elif stride >= 50:
        for i in range(n_cars):
            v = LAP_2024.unpack_from(data, HEADER.size + i * stride)
            out.append(LapData(
                last_lap_ms=v[0], current_lap_ms=v[1],
                s1_ms=v[3] * 60000 + v[2], s2_ms=v[5] * 60000 + v[4],
                delta_front_ms=v[6], delta_leader_ms=v[7],
                lap_distance=v[8], total_distance=v[9],
                position=v[11], lap=v[12], pit_status=v[13], num_pit_stops=v[14],
                sector=v[15], lap_invalid=bool(v[16]), penalties_s=v[17], warnings=v[18],
                corner_cut_warnings=v[19], unserved_dt=v[20], unserved_sg=v[21],
                grid_position=v[22], driver_status=v[23], result_status=v[24],
            ))
    return out


# ------------------------------------------------------------ Participants (4)
PART_HEAD = struct.Struct("<BBBBBBB32sBBHBB")  # 45 bytes (en stride 57 o 60)


@dataclass
class Participant:
    ai: bool
    driver_id: int
    team_id: int
    race_number: int
    nationality: int
    name: str


def parse_participants(data: bytes) -> tuple[int, list[Participant]]:
    off = HEADER.size
    if len(data) <= off:
        return 0, []
    fmt = data[0] | (data[1] << 8)
    num_active = data[off]
    off += 1
    body = len(data) - off
    n_cars, stride = _detect_cars_and_stride(body, (57, 60))
    if stride < 45:
        return num_active, []
    out: list[Participant] = []
    for i in range(n_cars):
        base = off + i * stride
        e = data[base:base + stride]
        if fmt == 2026 and stride == 60:
            ai = bool(e[0])
            driver_id = e[1] | (e[2] << 8)
            team_id = e[5] | (e[6] << 8)
            race_num = e[7]
            nat = e[8]
            raw_name = e[9:41].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
            out.append(Participant(ai=ai, driver_id=driver_id, team_id=team_id,
                                   race_number=race_num, nationality=nat, name=raw_name))
        else:
            v = PART_HEAD.unpack_from(data, base)
            name_len = 48 if (fmt == 2024 and stride >= 60) else 32
            raw_name = e[7:7 + name_len].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
            out.append(Participant(ai=bool(v[0]), driver_id=v[1], team_id=v[3],
                                   race_number=v[5], nationality=v[6], name=raw_name))
    return num_active, out


# ----------------------------------------------------------------- Session (1)
SESSION_HEAD = struct.Struct("<BbbBHBbBHHBBBBBB")  # 19 bytes
MARSHAL_ZONE = 5
FORECAST = struct.Struct("<BBBbbbbB")  # 8 bytes


@dataclass
class ForecastSample:
    session_type: int
    minutes_ahead: int
    weather: int
    track_temp: int
    air_temp: int
    rain_pct: int


@dataclass
class Session:
    weather: int
    track_temp: int
    air_temp: int
    total_laps: int
    track_length: int
    session_type: int
    track_id: int
    time_left_s: int
    duration_s: int
    pit_speed_limit: int
    paused: bool
    safety_car: int          # 0 none, 1 SC, 2 VSC, 3 formation lap
    forecast: list[ForecastSample] = field(default_factory=list)
    pit_window_ideal: int = 0
    pit_window_latest: int = 0
    pit_rejoin_position: int = 0


def parse_session(data: bytes) -> Session | None:
    off = HEADER.size
    if len(data) < off + 160:
        return None
    v = SESSION_HEAD.unpack_from(data, off)
    off += SESSION_HEAD.size + 21 * MARSHAL_ZONE
    sc_status = data[off]
    num_fc = data[off + 2]
    off += 3
    forecast = []
    for i in range(min(num_fc, 64)):
        f = FORECAST.unpack_from(data, off + i * FORECAST.size)
        forecast.append(ForecastSample(f[0], f[1], f[2], f[3], f[5], f[7]))
    off += 64 * FORECAST.size
    off += 2 + 12
    ideal = latest = rejoin = 0
    if len(data) >= off + 3:
        ideal, latest, rejoin = data[off], data[off + 1], data[off + 2]
    return Session(
        weather=v[0], track_temp=v[1], air_temp=v[2], total_laps=v[3],
        track_length=v[4], session_type=v[5], track_id=v[6],
        time_left_s=v[8], duration_s=v[9], pit_speed_limit=v[10], paused=bool(v[11]),
        safety_car=sc_status, forecast=forecast,
        pit_window_ideal=ideal, pit_window_latest=latest, pit_rejoin_position=rejoin,
    )


# ------------------------------------------------------------ Car Status (7)
STATUS = struct.Struct("<BBBBBfffHHBBHBBBbfffBfffB")  # 55 bytes


@dataclass
class CarStatus:
    traction_control: int
    abs: int
    fuel_mix: int
    brake_bias: int
    pit_limiter: bool
    fuel_kg: float
    fuel_capacity: float
    fuel_laps: float
    drs_allowed: bool
    drs_distance: int
    actual_compound: int
    visual_compound: int
    tyre_age: int
    fia_flag: int            # -1 invalid, 0 none, 1 green, 2 blue, 3 yellow
    ers_store_j: float
    ers_mode: int
    ers_deployed_lap_j: float


def parse_car_status(data: bytes) -> list[CarStatus]:
    body = len(data) - HEADER.size
    n_cars, stride = _detect_cars_and_stride(body, (55, 59))
    if stride < STATUS.size:
        return []
    out = []
    for i in range(n_cars):
        v = STATUS.unpack_from(data, HEADER.size + i * stride)
        out.append(CarStatus(
            traction_control=v[0], abs=v[1], fuel_mix=v[2], brake_bias=v[3],
            pit_limiter=bool(v[4]), fuel_kg=v[5], fuel_capacity=v[6], fuel_laps=v[7],
            drs_allowed=bool(v[11]), drs_distance=v[12], actual_compound=v[13],
            visual_compound=v[14], tyre_age=v[15], fia_flag=v[16],
            ers_store_j=v[19], ers_mode=v[20], ers_deployed_lap_j=v[23],
        ))
    return out


# ------------------------------------------------------------ Car Damage (10)
DAMAGE = struct.Struct("<4f4B4B4B18B")  # 46 bytes. Ruedas: RL, RR, FL, FR


@dataclass
class CarDamage:
    tyre_wear: list[float]
    tyre_damage: list[int]
    brake_damage: list[int]
    front_left_wing: int
    front_right_wing: int
    rear_wing: int
    floor: int
    diffuser: int
    sidepod: int
    drs_fault: bool
    ers_fault: bool
    gearbox: int
    engine: int
    engine_blown: bool


def parse_car_damage(data: bytes) -> list[CarDamage]:
    body = len(data) - HEADER.size
    n_cars, stride = _detect_cars_and_stride(body, (46,))
    if stride < DAMAGE.size:
        return []
    out = []
    for i in range(n_cars):
        v = DAMAGE.unpack_from(data, HEADER.size + i * stride)
        r = v[16:]
        out.append(CarDamage(
            tyre_wear=list(v[0:4]), tyre_damage=list(v[4:8]), brake_damage=list(v[8:12]),
            front_left_wing=r[0], front_right_wing=r[1], rear_wing=r[2], floor=r[3],
            diffuser=r[4], sidepod=r[5], drs_fault=bool(r[6]), ers_fault=bool(r[7]),
            gearbox=r[8], engine=r[9], engine_blown=bool(r[16]),
        ))
    return out


# --------------------------------------------------------- Car Telemetry (6)
TELEMETRY = struct.Struct("<HfffBbHBBH4H4B4BH4f4B")  # 60 bytes
TELEMETRY_59 = struct.Struct("<HfffBbHBBH4H4B4BH4f")  # 56 bytes iniciales (compatible con 59B en 2026)


@dataclass
class CarTelemetry:
    speed_kmh: int
    gear: int
    rpm: int
    drs: bool
    brake_temps: list[int]
    tyre_surface_temps: list[int]
    tyre_inner_temps: list[int]
    engine_temp: int
    tyre_pressures: list[float]


def parse_car_telemetry(data: bytes) -> list[CarTelemetry]:
    body = len(data) - HEADER.size - 3
    n_cars, stride = _detect_cars_and_stride(body, (60, 59))
    if stride < 56:
        return []
    out = []
    for i in range(n_cars):
        v = TELEMETRY_59.unpack_from(data, HEADER.size + i * stride)
        out.append(CarTelemetry(
            speed_kmh=v[0], gear=v[5], rpm=v[6], drs=bool(v[7]),
            brake_temps=list(v[10:14]), tyre_surface_temps=list(v[14:18]),
            tyre_inner_temps=list(v[18:22]), engine_temp=v[22],
            tyre_pressures=list(v[23:27]),
        ))
    return out


# ------------------------------------------------------- Session History (11)
LAP_HIST_ENTRY = struct.Struct("<IHBHBHBB")  # 14 bytes


@dataclass
class CarSessionHistory:
    car_idx: int
    num_laps: int
    num_stints: int
    best_lap_num: int
    last_lap_ms: int
    best_lap_ms: int
    current_s1_ms: int
    current_s2_ms: int
    cumulative_ms: int
    actual_compound: int
    visual_compound: int
    tyre_age: int


def parse_session_history(data: bytes) -> CarSessionHistory | None:
    off = HEADER.size
    if len(data) < off + 7 + 100 * 14 + 8 * 3:
        return None
    car_idx, num_laps, num_stints, best_lap_num = data[off], data[off + 1], data[off + 2], data[off + 3]
    hist_off = off + 7
    last_lap_ms = 0
    best_lap_ms = 0
    cur_s1_ms = 0
    cur_s2_ms = 0
    cum_ms = 0
    valid_laps = min(num_laps, 100)
    for lap_i in range(valid_laps):
        lv = LAP_HIST_ENTRY.unpack_from(data, hist_off + lap_i * 14)
        lap_ms = lv[0]
        s1_ms = lv[2] * 60000 + lv[1]
        s2_ms = lv[4] * 60000 + lv[3]
        if lap_ms > 0:
            last_lap_ms = lap_ms
            cum_ms += lap_ms
            if best_lap_ms == 0 or lap_ms < best_lap_ms:
                best_lap_ms = lap_ms
        if lap_i == valid_laps - 1:
            cur_s1_ms = s1_ms
            cur_s2_ms = s2_ms

    stint_off = hist_off + 100 * 14
    act_comp = 0
    vis_comp = 0
    tyre_age = max(1, num_laps)
    if 0 < num_stints <= 8:
        prev_end = 0
        if num_stints >= 2:
            prev_end = data[stint_off + (num_stints - 2) * 3]
        last_stint = stint_off + (num_stints - 1) * 3
        act_comp = data[last_stint + 1]
        vis_comp = data[last_stint + 2]
        if num_laps > prev_end and prev_end < 250:
            tyre_age = max(1, num_laps - prev_end)

    return CarSessionHistory(
        car_idx=car_idx,
        num_laps=num_laps,
        num_stints=num_stints,
        best_lap_num=best_lap_num,
        last_lap_ms=last_lap_ms,
        best_lap_ms=best_lap_ms,
        current_s1_ms=cur_s1_ms,
        current_s2_ms=cur_s2_ms,
        cumulative_ms=cum_ms,
        actual_compound=act_comp,
        visual_compound=vis_comp,
        tyre_age=tyre_age,
    )


# ------------------------------------------------------------- Tyre Sets (12)
TYRE_SET_ENTRY = struct.Struct("<BBBBBBBhB")  # 10 bytes


@dataclass
class CarFittedTyre:
    car_idx: int
    actual_compound: int
    visual_compound: int
    wear_pct: float
    life_span_laps: int
    usable_life_laps: int


def parse_tyre_sets(data: bytes) -> CarFittedTyre | None:
    off = HEADER.size
    if len(data) < off + 1 + 20 * 10:
        return None
    car_idx = data[off]
    sets_off = off + 1
    fitted_idx = data[sets_off + 200] if len(data) > sets_off + 200 else 255
    chosen = None
    for i in range(20):
        tv = TYRE_SET_ENTRY.unpack_from(data, sets_off + i * 10)
        if tv[8] == 1 or i == fitted_idx:
            chosen = tv
            break
    if chosen is None:
        return None
    return CarFittedTyre(
        car_idx=car_idx,
        actual_compound=chosen[0],
        visual_compound=chosen[1],
        wear_pct=float(chosen[2]),
        life_span_laps=int(chosen[5]),
        usable_life_laps=int(chosen[6]),
    )


# --------------------------------------------------------- Lap Positions (15)
@dataclass
class LapPositions:
    num_laps: int
    latest_positions: dict[int, int]  # car_idx -> pos


def parse_lap_positions(data: bytes) -> LapPositions | None:
    off = HEADER.size
    if len(data) < off + 2 + 50 * 22:
        return None
    num_laps = data[off]
    body = len(data) - (off + 2)
    n_cars = 24 if body >= 50 * 24 else 22
    if num_laps <= 0:
        return None
    lap_row = min(num_laps - 1, 49)
    row_off = off + 2 + lap_row * n_cars
    latest: dict[int, int] = {}
    for c in range(n_cars):
        pos = data[row_off + c]
        if 0 < pos <= 24:
            latest[c] = pos
    return LapPositions(num_laps=num_laps, latest_positions=latest)


# -------------------------------------------------------- Swofty Track (200)
@dataclass
class SwoftyTrack:
    swofty_track_id: int
    stat_id: int
    track_key: str


def parse_swofty_track(data: bytes) -> SwoftyTrack | None:
    off = HEADER.size
    if len(data) < off + 5:
        return None
    track_id = struct.unpack_from("<I", data, off)[0]
    stat_id = data[off + 4]
    raw_key = data[off + 5:off + 5 + 64].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
    return SwoftyTrack(swofty_track_id=track_id, stat_id=stat_id, track_key=raw_key)


# ------------------------------------------------------------------ Event (3)
@dataclass
class Event:
    code: str
    vehicle: int = 255
    other_vehicle: int = 255
    value: float = 0.0
    extra: int = 0


def parse_event(data: bytes) -> Event | None:
    off = HEADER.size
    if len(data) < off + 4:
        return None
    code = data[off:off + 4].decode("ascii", "replace")
    d = data[off + 4:]
    try:
        if code == "FTLP":                       # fastest lap
            idx, t = struct.unpack_from("<Bf", d)
            return Event(code, vehicle=idx, value=t)
        if code in ("RTMT", "TMPT", "RCWN", "DTSV", "SGSV"):
            return Event(code, vehicle=d[0], extra=d[1] if code == "RTMT" else 0)
        if code == "PENA":                       # penalty
            ptype, inf, veh, other, t, lap, places = struct.unpack_from("<BBBBBBB", d)
            return Event(code, vehicle=veh, other_vehicle=other, value=t, extra=ptype * 1000 + inf)
        if code == "OVTK":                       # overtake
            return Event(code, vehicle=d[0], other_vehicle=d[1])
        if code == "SCAR":                       # safety car
            return Event(code, extra=d[0] * 10 + d[1])   # type*10 + eventType
        if code == "COLL":                       # collision
            return Event(code, vehicle=d[0], other_vehicle=d[1])
        if code == "STLG":                       # start lights
            return Event(code, extra=d[0])
    except (struct.error, IndexError):
        return Event(code)
    return Event(code)


PARSERS = {
    1: parse_session,
    2: parse_lap_data,
    3: parse_event,
    4: parse_participants,
    6: parse_car_telemetry,
    7: parse_car_status,
    10: parse_car_damage,
    11: parse_session_history,
    12: parse_tyre_sets,
    15: parse_lap_positions,
    200: parse_swofty_track,
}
