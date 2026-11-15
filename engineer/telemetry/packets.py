"""Decodificador de los paquetes UDP de F1 25 (formato 2025).

Solo se decodifican los paquetes que el ingeniero necesita:
  1 Session, 2 Lap Data, 3 Event, 4 Participants, 6 Car Telemetry,
  7 Car Status, 10 Car Damage.

Referencia: "F1 25 UDP Specification" de EA/Codemasters. Todos los valores
son little-endian y las estructuras van empaquetadas (sin padding).
El tamano por coche se calcula a partir de la longitud del paquete para
tolerar pequenas variaciones entre parches.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

NUM_CARS = 22

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


# ---------------------------------------------------------------- Lap Data (2)
LAP = struct.Struct("<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB")  # 57 bytes


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
    stride = body // NUM_CARS if body > 0 else LAP.size
    if stride < LAP.size:
        return []
    out = []
    for i in range(NUM_CARS):
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
    return out


# ------------------------------------------------------------ Participants (4)
PART_HEAD = struct.Struct("<BBBBBBB32sBBHBB")  # + 4 liveries x 3 bytes = 57


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
    num_active = data[off]
    off += 1
    body = len(data) - off
    stride = body // NUM_CARS
    if stride < PART_HEAD.size:
        return num_active, []
    out = []
    for i in range(NUM_CARS):
        v = PART_HEAD.unpack_from(data, off + i * stride)
        name = v[7].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        out.append(Participant(ai=bool(v[0]), driver_id=v[1], team_id=v[3],
                               race_number=v[5], nationality=v[6], name=name))
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
    # forecastAccuracy, aiDifficulty, 3 x uint32 link ids
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
    stride = (len(data) - HEADER.size) // NUM_CARS
    if stride < STATUS.size:
        return []
    out = []
    for i in range(NUM_CARS):
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
    stride = (len(data) - HEADER.size) // NUM_CARS
    if stride < DAMAGE.size:
        return []
    out = []
    for i in range(NUM_CARS):
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
    stride = (len(data) - HEADER.size - 3) // NUM_CARS
    if stride < TELEMETRY.size:
        return []
    out = []
    for i in range(NUM_CARS):
        v = TELEMETRY.unpack_from(data, HEADER.size + i * stride)
        out.append(CarTelemetry(
            speed_kmh=v[0], gear=v[5], rpm=v[6], drs=bool(v[7]),
            brake_temps=list(v[10:14]), tyre_surface_temps=list(v[14:18]),
            tyre_inner_temps=list(v[18:22]), engine_temp=v[22],
            tyre_pressures=list(v[23:27]),
        ))
    return out


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
}
