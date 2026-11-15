"""Convierte el RaceState en un resumen compacto para el prompt de la IA."""
from __future__ import annotations

from . import lookups as L
from . import packets as P
from .listener import RaceState


def fmt_ms(ms: int) -> str:
    if ms <= 0:
        return "--"
    m, rem = divmod(ms, 60000)
    s, millis = divmod(rem, 1000)
    return f"{m}:{s:02d}.{millis:03d}" if m else f"{s}.{millis:03d}s"


def fmt_delta(ms: int) -> str:
    if ms <= 0:
        return "+0.0s"
    return f"+{ms / 1000.0:.1f}s"


def driver_name(state: RaceState, idx: int) -> str:
    if 0 <= idx < len(state.participants):
        name = state.participants[idx].name
        if name:
            return name
    return f"Car #{idx}"


def team_name(state: RaceState, idx: int) -> str:
    if 0 <= idx < len(state.participants):
        return L.TEAMS.get(state.participants[idx].team_id, "Unknown Team")
    return "Unknown Team"


def compound_str(state: RaceState, idx: int) -> str:
    if 0 <= idx < len(state.status):
        st = state.status[idx]
        comp = L.COMPOUNDS.get(st.visual_compound) or L.COMPOUNDS.get(st.actual_compound, "?")
        return f"{comp} ({st.tyre_age}L)"
    return "?"


def build_standings(state: RaceState, limit: int = 22) -> list[dict]:
    """Devuelve la clasificacion ordenada por posicion."""
    rows = []
    for idx, ld in enumerate(state.laps):
        if ld.position <= 0:
            continue
        if ld.result_status in (0, 1):
            continue
        rows.append({
            "idx": idx,
            "pos": ld.position,
            "name": driver_name(state, idx),
            "team": team_name(state, idx),
            "lap": ld.lap,
            "last_lap": fmt_ms(ld.last_lap_ms),
            "best_lap": fmt_ms(state.best_laps.get(idx, 0)),
            "gap_front": fmt_delta(ld.delta_front_ms),
            "gap_leader": fmt_delta(ld.delta_leader_ms),
            "tyre": compound_str(state, idx),
            "pits": ld.num_pit_stops,
            "pit_status": L.PIT_STATUS.get(ld.pit_status, ""),
            "penalties_s": ld.penalties_s,
            "status": L.RESULT_STATUS.get(ld.result_status, "active"),
            "is_player": idx == state.player_idx,
        })
    rows.sort(key=lambda r: r["pos"])
    return rows[:limit]


def build_race_context(state: RaceState) -> str:
    """Genera el bloque de telemetria en tiempo real que lee Gemini."""
    if not state.connected or not state.laps:
        return (
            "[TELEMETRY STATUS: DEMO / NOT CONNECTED TO LIVE UDP YET]\n"
            "Simulated Demo Data (use if driver asks for race data while testing outside the game):\n"
            "Session: Race at Spa (Lap 14/44), Weather: Light cloud (Track 29C, Air 21C), Rain forecast in 15m: 45%.\n"
            "Player: P4, Medium tyres (9 laps old, max wear 31% FL), Fuel: +1.2 laps, ERS: 68%.\n"
            "Gap ahead: P3 Norris +1.4s (Medium 9L) | Gap behind: P5 Sainz -2.1s (Hard 14L).\n"
            "Standings Top 10: P1 Verstappen (Red Bull, Medium), P2 Leclerc (Ferrari, +2.8s, Medium), "
            "P3 Norris (McLaren, +5.1s, Medium), P4 Player (+6.5s, Medium), P5 Sainz (Williams, +8.6s, Hard), "
            "P6 Hamilton (Ferrari, +11.2s, Hard), P7 Russell (Mercedes, +13.0s, Medium), "
            "P8 Alonso (Aston Martin, +16.4s, Hard), P9 Piastri (McLaren, +18.1s, Medium), P10 Gasly (Alpine, +22.0s, Hard)."
        )

    lines: list[str] = ["[LIVE F1 25 UDP TELEMETRY]"]
    pidx = state.player_idx
    s = state.session
    if s:
        track = L.TRACKS.get(s.track_id, f"Track #{s.track_id}")
        stype = L.SESSION_TYPES.get(s.session_type, "Session")
        weather = L.WEATHER.get(s.weather, "unknown")
        sc = L.SAFETY_CAR.get(s.safety_car, "none")
        lines.append(
            f"Session: {stype} at {track} | Weather: {weather} "
            f"(Track {s.track_temp}C, Air {s.air_temp}C) | Safety Car: {sc}"
        )
        if s.pit_window_ideal > 0:
            lines.append(
                f"Pit Strategy: Ideal lap {s.pit_window_ideal}-{s.pit_window_latest}, "
                f"predicted rejoin P{s.pit_rejoin_position}"
            )
        if s.forecast:
            fc_parts = []
            for f in s.forecast[:5]:
                if f.session_type == s.session_type:
                    w = L.WEATHER.get(f.weather, "?")
                    fc_parts.append(f"+{f.minutes_ahead}m: {w} ({f.rain_pct}% rain)")
            if fc_parts:
                lines.append("Weather Forecast: " + ", ".join(fc_parts))

    standings = build_standings(state, limit=22)
    player_row = next((r for r in standings if r["is_player"]), None)
    if player_row:
        pos = player_row["pos"]
        total_laps = s.total_laps if s else "?"
        ahead = next((r for r in standings if r["pos"] == pos - 1), None)
        behind = next((r for r in standings if r["pos"] == pos + 1), None)
        lines.append(
            f"Player ({player_row['name']}, {player_row['team']}): "
            f"P{pos}/{len(standings)}, Lap {player_row['lap']}/{total_laps}, "
            f"Last lap {player_row['last_lap']}, Best {player_row['best_lap']}, "
            f"Gap to leader {player_row['gap_leader']}, Penalties {player_row['penalties_s']}s"
        )
        if ahead:
            lines.append(
                f"Car Ahead (P{ahead['pos']}): {ahead['name']} ({ahead['team']}) "
                f"at {player_row['gap_front']} on {ahead['tyre']}"
            )
        if behind:
            lines.append(
                f"Car Behind (P{behind['pos']}): {behind['name']} ({behind['team']}) "
                f"at {behind['gap_front']} behind on {behind['tyre']}"
            )

    if 0 <= pidx < len(state.status):
        cs = state.status[pidx]
        comp = L.COMPOUNDS.get(cs.visual_compound) or L.COMPOUNDS.get(cs.actual_compound, "?")
        ers_pct = min(100, int(round((cs.ers_store_j / 4_000_000.0) * 100)))
        flag = L.FIA_FLAG.get(cs.fia_flag, "none")
        lines.append(
            f"Player Car Status: Tyres={comp} ({cs.tyre_age} laps old), "
            f"Fuel={cs.fuel_kg:.1f}kg ({cs.fuel_laps:+.2f} laps margin, mix={L.FUEL_MIX.get(cs.fuel_mix, '?')}), "
            f"ERS={ers_pct}% (mode={L.ERS_MODE.get(cs.ers_mode, '?')}), "
            f"BrakeBias={cs.brake_bias}%, DRS={'allowed' if cs.drs_allowed else 'off'}, Flag={flag}"
        )

    if 0 <= pidx < len(state.damage):
        dm = state.damage[pidx]
        wear = ", ".join(f"{w}:{dm.tyre_wear[i]:.0f}%" for i, w in enumerate(L.WHEELS))
        lines.append(
            f"Player Tyre Wear & Damage: Wear=[{wear}], "
            f"WingFL={dm.front_left_wing}%, WingFR={dm.front_right_wing}%, RearWing={dm.rear_wing}%, "
            f"Floor={dm.floor}%, Diffuser={dm.diffuser}%, Sidepod={dm.sidepod}%, "
            f"Engine={dm.engine}%, Gearbox={dm.gearbox}%, "
            f"Faults={'DRS ' if dm.drs_fault else ''}{'ERS ' if dm.ers_fault else '' or 'none'}"
        )

    if 0 <= pidx < len(state.telemetry):
        tm = state.telemetry[pidx]
        stemp = "/".join(f"{t}C" for t in tm.tyre_surface_temps)
        itemp = "/".join(f"{t}C" for t in tm.tyre_inner_temps)
        lines.append(
            f"Player Telemetry: Speed={tm.speed_kmh}km/h, Gear={tm.gear}, "
            f"TyreSurfTemp(RL/RR/FL/FR)={stemp}, TyreCoreTemp={itemp}, EngineTemp={tm.engine_temp}C"
        )

    if standings:
        top_str = []
        for r in standings[:15]:
            me = " [YOU]" if r["is_player"] else ""
            pit = f" [{r['pit_status']}]" if r["pit_status"] else ""
            st_tag = f" ({r['status']})" if r["status"] != "active" else ""
            top_str.append(
                f"P{r['pos']} {r['name']}{me} ({r['team']}, {r['gap_leader']}, {r['tyre']}, {r['pits']}stop){pit}{st_tag}"
            )
        lines.append("Classification: " + " | ".join(top_str))

    return "\n".join(lines)
