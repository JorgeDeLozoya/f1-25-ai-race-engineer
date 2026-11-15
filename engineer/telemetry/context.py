"""Convierte el RaceState en clasificacion en vivo (20/22/24 coches) y contexto para la IA."""
from __future__ import annotations

from . import lookups as L
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


def is_classic_2010_grid(state: RaceState) -> bool:
    """Detecta si la parrilla corresponde al mod de la temporada 2010 (Swofty)."""
    markers = {"SCHUMACHER", "BARRICHELLO", "LIUZZI", "TRULLI", "PETROV", "BUEMI", "SUTIL", "KOVALAINEN", "GLOCK", "CHANDHOK", "WEBBER", "MASSA", "BUTTON", "ROSBERG"}
    hits = 0
    for p in state.participants:
        if p.name.upper().strip() in markers:
            hits += 1
    return hits >= 3


def driver_name(state: RaceState, idx: int) -> str:
    if 0 <= idx < len(state.participants):
        name = state.participants[idx].name
        if name:
            return name
    return f"Car #{idx}"


def team_name(state: RaceState, idx: int, drv_name: str = "") -> str:
    name_up = (drv_name or driver_name(state, idx)).upper().strip()
    if is_classic_2010_grid(state) and name_up in L.CLASSIC_DRIVER_TEAMS:
        return L.CLASSIC_DRIVER_TEAMS[name_up]
    if 0 <= idx < len(state.participants):
        return L.TEAMS.get(state.participants[idx].team_id, "Unknown Team")
    return "Unknown Team"


def compound_str(state: RaceState, idx: int) -> str:
    if 0 <= idx < len(state.status):
        st = state.status[idx]
        comp = L.COMPOUNDS.get(st.visual_compound) or L.COMPOUNDS.get(st.actual_compound, "?")
        return f"{comp} ({st.tyre_age}L)"
    if idx in state.fitted_tyres:
        ft = state.fitted_tyres[idx]
        comp = L.COMPOUNDS.get(ft.visual_compound) or L.COMPOUNDS.get(ft.actual_compound, "Soft")
        age = state.session_history[idx].tyre_age if idx in state.session_history else 1
        return f"{comp} ({age}L)"
    if idx in state.session_history:
        sh = state.session_history[idx]
        comp = L.COMPOUNDS.get(sh.visual_compound) or L.COMPOUNDS.get(sh.actual_compound, "Soft")
        return f"{comp} ({sh.tyre_age}L)"
    return "Soft (1L)"


def _infer_missing_2010_drivers(state: RaceState) -> list[tuple[str, str]]:
    """Si faltan 1 o 2 coches (slots 22 y 23 en UDP 2025), deduce sus nombres y equipos."""
    present_names = {p.name.upper().strip() for p in state.participants if p.name}
    if not is_classic_2010_grid(state):
        return [("SENNA", "Tu Monoplaza"), ("KUBICA", "Renault")]
    # Pares de companeros de 2010 cuyos slots suelen ir al final (HRT, Renault, Toro Rosso, Virgin)
    pairs = [
        ("CHANDHOK", "SENNA", "HRT (Hispania)"),
        ("SENNA", "CHANDHOK", "HRT (Hispania)"),
        ("PETROV", "KUBICA", "Renault"),
        ("KUBICA", "PETROV", "Renault"),
        ("BUEMI", "ALGUERSUARI", "Toro Rosso"),
        ("GLOCK", "DI GRASSI", "Virgin Racing"),
    ]
    missing: list[tuple[str, str]] = []
    for teammate_present, missing_drv, team in pairs:
        if teammate_present in present_names and missing_drv not in present_names:
            if (missing_drv, team) not in missing:
                missing.append((missing_drv, team))
    if not missing:
        missing = [("SENNA", "HRT (Hispania)"), ("KUBICA", "Renault")]
    return missing


def build_standings(state: RaceState, limit: int = 24) -> list[dict]:
    """Devuelve la clasificacion completa ordenada por posicion (incluyendo reconstruccion de 24 coches)."""
    if not state.laps:
        return []

    pidx = state.player_idx
    # Si player_idx no apunta a un coche con posicion > 0, buscar participante humano (ai == False)
    resolved_pidx = pidx
    if not (0 <= pidx < len(state.laps) and state.laps[pidx].position > 0):
        for idx, part in enumerate(state.participants):
            if not part.ai and idx < len(state.laps) and state.laps[idx].position > 0:
                resolved_pidx = idx
                break

    rows: list[dict] = []
    by_pos: dict[int, dict] = {}

    for idx, ld in enumerate(state.laps):
        if ld.position <= 0:
            continue
        # Solo ignorar result_status 0/1 si realmente es un slot vacio sin vuelta ni distancia
        if ld.result_status in (0, 1) and ld.lap <= 0 and ld.total_distance <= 0.0 and idx != resolved_pidx:
            continue
        dname = driver_name(state, idx)
        tname = team_name(state, idx, dname)
        sh = state.session_history.get(idx)
        s1 = (sh.last_s1_ms if (sh and sh.last_s1_ms > 0) else ld.s1_ms)
        s2 = (sh.last_s2_ms if (sh and sh.last_s2_ms > 0) else ld.s2_ms)
        s3 = (sh.last_s3_ms if (sh and sh.last_s3_ms > 0) else max(0, ld.last_lap_ms - s1 - s2) if (ld.last_lap_ms > 0 and s1 > 0 and s2 > 0) else 0)
        rnum = 0
        if 0 <= idx < len(state.participants):
            rnum = state.participants[idx].race_number
        if rnum <= 0:
            rnum = L.DRIVER_NUMBERS.get(dname.upper(), 0)
        row = {
            "idx": idx,
            "pos": ld.position,
            "grid_pos": max(1, ld.grid_position) if ld.grid_position > 0 else ld.position,
            "name": dname,
            "team": tname,
            "race_number": rnum,
            "lap": max(1, ld.lap),
            "last_lap_ms": ld.last_lap_ms,
            "last_lap": fmt_ms(ld.last_lap_ms),
            "best_lap": fmt_ms(state.best_laps.get(idx, 0)),
            "s1_ms": s1,
            "s2_ms": s2,
            "s3_ms": s3,
            "delta_front_ms": ld.delta_front_ms,
            "delta_leader_ms": ld.delta_leader_ms,
            "gap_front": fmt_delta(ld.delta_front_ms),
            "gap_leader": fmt_delta(ld.delta_leader_ms),
            "tyre": compound_str(state, idx),
            "pits": ld.num_pit_stops,
            "pit_status": L.PIT_STATUS.get(ld.pit_status, ""),
            "penalties_s": ld.penalties_s,
            "warnings": ld.corner_cut_warnings,
            "status": L.RESULT_STATUS.get(ld.result_status, "active"),
            "is_player": idx == resolved_pidx,
        }
        rows.append(row)
        by_pos[ld.position] = row

    # ¿El jugador esta en los slots 22 o 23 de una parrilla de 24 coches (Swofty) con UDP 2025 (22 slots)?
    has_player_row = any(r["is_player"] for r in rows)
    if not has_player_row and rows:
        max_seen_pos = max(r["pos"] for r in rows)
        total_expected = max(max_seen_pos, len(rows) + 1, state.num_active if state.num_active <= 24 else 22)
        missing_positions = [p for p in range(1, total_expected + 1) if p not in by_pos]

        if missing_positions:
            # Determinar cual de las posiciones ausentes en 1..N corresponde al jugador (slot 22/23)
            player_missing_pos = missing_positions[0]
            if pidx in state.lap_positions and state.lap_positions[pidx] in missing_positions:
                player_missing_pos = state.lap_positions[pidx]
            elif state.player_pos_hint in missing_positions:
                player_missing_pos = state.player_pos_hint
            elif 0 <= state.last_opponent_idx < len(state.laps):
                op_pos = state.laps[state.last_opponent_idx].position
                if op_pos > 0:
                    player_missing_pos = min(missing_positions, key=lambda mp: abs(mp - op_pos))
            elif len(missing_positions) >= 2 and pidx in state.session_history:
                other_slot = 23 if pidx == 22 else 22
                if other_slot in state.session_history:
                    my_h = state.session_history[pidx]
                    ot_h = state.session_history[other_slot]
                    if my_h.cumulative_ms > 0 and ot_h.cumulative_ms > 0 and my_h.num_laps == ot_h.num_laps:
                        player_missing_pos = (
                            min(missing_positions) if my_h.cumulative_ms <= ot_h.cumulative_ms else max(missing_positions)
                        )

            missing_identities = _infer_missing_2010_drivers(state)
            # Reconstruir cada coche ausente usando el delta_front_ms exacto del coche inmediatamente detras
            for i_miss, m_pos in enumerate(missing_positions):
                is_me = (m_pos == player_missing_pos)
                slot_idx = pidx if is_me else (23 if pidx == 22 else 22)

                car_ahead = by_pos.get(m_pos - 1)
                car_behind = by_pos.get(m_pos + 1)

                # Calcular delta_leader_ms y delta_front_ms exactos a partir del coche de detras y delante
                if car_behind and car_behind["delta_leader_ms"] > 0:
                    my_delta_leader_ms = max(0, car_behind["delta_leader_ms"] - car_behind["delta_front_ms"])
                elif car_ahead:
                    my_delta_leader_ms = car_ahead["delta_leader_ms"] + 700
                else:
                    my_delta_leader_ms = 0

                if m_pos == 1:
                    my_delta_front_ms = 0
                elif car_ahead:
                    my_delta_front_ms = max(100, my_delta_leader_ms - car_ahead["delta_leader_ms"])
                else:
                    my_delta_front_ms = 700

                # Vuelta actual, tiempos y neumatico desde SessionHistory (11) / TyreSets (12) o coches adyacentes
                sh = state.session_history.get(slot_idx)
                ref_car = car_ahead or car_behind or rows[0]
                lap_num = sh.num_laps if (sh and sh.num_laps > 0) else ref_car["lap"]
                last_ms = sh.last_lap_ms if (sh and sh.last_lap_ms > 0) else ref_car["last_lap_ms"]
                best_ms = sh.best_lap_ms if (sh and sh.best_lap_ms > 0) else state.best_laps.get(slot_idx, last_ms)
                pits_cnt = max(0, sh.num_stints - 1) if (sh and sh.num_stints > 0) else ref_car["pits"]

                if slot_idx in state.fitted_tyres or slot_idx in state.session_history:
                    tyre_label = compound_str(state, slot_idx)
                else:
                    tyre_label = ref_car["tyre"]

                if 0 <= slot_idx < len(state.participants) and state.participants[slot_idx].name:
                    dname = state.participants[slot_idx].name
                    tname = team_name(state, slot_idx, dname)
                else:
                    ident_idx = 0 if is_me else min(1, len(missing_identities) - 1)
                    dname, tname = missing_identities[ident_idx]

                synth_s1 = sh.last_s1_ms if (sh and sh.last_s1_ms > 0) else ref_car.get("s1_ms", 0)
                synth_s2 = sh.last_s2_ms if (sh and sh.last_s2_ms > 0) else ref_car.get("s2_ms", 0)
                synth_s3 = sh.last_s3_ms if (sh and sh.last_s3_ms > 0) else ref_car.get("s3_ms", 0)
                synth_rnum = 0
                if 0 <= slot_idx < len(state.participants):
                    synth_rnum = state.participants[slot_idx].race_number
                if synth_rnum <= 0:
                    synth_rnum = L.DRIVER_NUMBERS.get(dname.upper(), 0)
                synth_row = {
                    "idx": slot_idx,
                    "pos": m_pos,
                    "grid_pos": m_pos,
                    "name": dname,
                    "team": tname,
                    "race_number": synth_rnum,
                    "lap": lap_num,
                    "last_lap_ms": last_ms,
                    "last_lap": fmt_ms(last_ms),
                    "best_lap": fmt_ms(best_ms),
                    "s1_ms": synth_s1,
                    "s2_ms": synth_s2,
                    "s3_ms": synth_s3,
                    "delta_front_ms": my_delta_front_ms,
                    "delta_leader_ms": my_delta_leader_ms,
                    "gap_front": fmt_delta(my_delta_front_ms),
                    "gap_leader": fmt_delta(my_delta_leader_ms),
                    "tyre": tyre_label,
                    "pits": pits_cnt,
                    "pit_status": "",
                    "penalties_s": 0,
                    "warnings": 0,
                    "status": "active",
                    "is_player": is_me,
                }
                rows.append(synth_row)
                by_pos[m_pos] = synth_row

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
        track = L.resolve_track_name(s.track_id, s.track_length, state.swofty_track_key)
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

    standings = build_standings(state, limit=24)
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
                f"at {player_row['gap_front']} on {ahead['tyre']} (last lap {ahead['last_lap']})"
            )
        if behind:
            lines.append(
                f"Car Behind (P{behind['pos']}): {behind['name']} ({behind['team']}) "
                f"at {behind['gap_front']} behind on {behind['tyre']} (last lap {behind['last_lap']})"
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
        for r in standings[:24]:
            me = " [YOU]" if r["is_player"] else ""
            pit = f" [{r['pit_status']}]" if r["pit_status"] else ""
            st_tag = f" ({r['status']})" if r["status"] != "active" else ""
            top_str.append(
                f"P{r['pos']} {r['name']}{me} ({r['team']}, {r['gap_leader']}, {r['tyre']}, {r['pits']}stop){pit}{st_tag}"
            )
        lines.append("Classification: " + " | ".join(top_str))

    return "\n".join(lines)
