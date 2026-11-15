"""Motor de estrategia de carrera en tiempo real y avisos proactivos (Spotter + Estratega)."""
from __future__ import annotations

from dataclasses import dataclass, field
import random
import re
import time

from .telemetry import lookups as L
from .telemetry.context import build_standings, fmt_ms
from .telemetry.listener import RaceState


@dataclass
class StrategyReport:
    connected: bool
    track_name: str
    session_name: str
    player_driver: str
    player_team: str
    current_lap: int
    total_laps: int
    laps_remaining: int
    position: int
    total_cars: int
    last_lap_str: str
    best_lap_str: str
    current_tyre: str
    current_tyre_es: str
    tyre_age: int
    max_wear_pct: float
    worst_wheel: str
    worst_wheel_es: str
    worst_wheel_en: str
    wear_per_lap: float
    est_tyre_laps_left: int
    max_tyre_temp: int
    max_brake_temp: int
    brake_bias: int
    penalties_s: int
    warnings_count: int
    box_recommendation: str          # "STAY OUT", "PIT WINDOW OPEN", "BOX THIS LAP", "HOLD FOR RAIN"
    recommended_compound: str
    recommended_compound_es: str
    pit_window_ideal: int
    pit_window_latest: int
    predicted_rejoin_pos: int
    rejoin_summary_es: str
    rejoin_summary_en: str
    undercut_summary_es: str
    undercut_summary_en: str
    fuel_kg: float
    fuel_laps_margin: float
    fuel_advice_es: str
    fuel_advice_en: str
    ers_pct: int
    ers_mode: str
    ers_mode_es: str
    damage_summary_es: str
    damage_summary_en: str
    weather_now: str
    weather_now_es: str
    track_temp: int
    air_temp: int
    rain_forecast_pct: int
    rain_in_mins: int
    ahead_name: str
    ahead_gap_s: float
    ahead_tyre: str
    ahead_last_lap: str
    behind_name: str
    behind_gap_s: float
    behind_tyre: str
    behind_last_lap: str
    pace_delta_ahead_s: float
    laps_to_catch_ahead: int
    pace_delta_behind_s: float
    laps_until_caught_behind: int
    pace_analysis_es: str
    pace_analysis_en: str
    setup_advice_es: str
    setup_advice_en: str
    teammate_name: str
    teammate_pos: int
    teammate_gap: str
    podium_gap_s: float
    points_gap_s: float
    retired_names: list[str] = field(default_factory=list)
    full_briefing_es: str = ""
    full_briefing_en: str = ""


def _parse_tyre_label(label: str) -> tuple[str, int]:
    """Extrae ('Soft', 3) de una etiqueta como 'Soft (3L)'."""
    comp = "Soft"
    for c in ("Super Soft", "Soft", "Medium", "Hard", "Intermediate", "Wet"):
        if c.lower() in label.lower():
            comp = c
            break
    m = re.search(r"\((\d+)L\)", label)
    age = int(m.group(1)) if m else 1
    return comp, max(1, age)


def analyze_strategy(state: RaceState, driver_label: str = "Jorge") -> StrategyReport:
    """Calcula toda la situacion tactica, ritmo relativo, reglajes y posibles estrategias."""
    if not state.connected or not state.laps:
        return StrategyReport(
            connected=False,
            track_name="Spa-Francorchamps (Demo)",
            session_name="Race",
            player_driver=driver_label,
            player_team="Aston Martin",
            current_lap=14,
            total_laps=18,
            laps_remaining=4,
            position=4,
            total_cars=20,
            last_lap_str="1:46.820",
            best_lap_str="1:46.210",
            current_tyre="Medium",
            current_tyre_es="medio",
            tyre_age=9,
            max_wear_pct=33.0,
            worst_wheel="FL",
            worst_wheel_es="delantera izquierda",
            worst_wheel_en="front left",
            wear_per_lap=3.5,
            est_tyre_laps_left=9,
            max_tyre_temp=96,
            max_brake_temp=610,
            brake_bias=56,
            penalties_s=0,
            warnings_count=1,
            box_recommendation="STAY OUT",
            recommended_compound="Soft",
            recommended_compound_es="blando",
            pit_window_ideal=10,
            pit_window_latest=13,
            predicted_rejoin_pos=8,
            rejoin_summary_es="Si paras ahora caerías a octava posición detrás de Alonso, quedando 4 vueltas es mejor seguir en pista.",
            rejoin_summary_en="If we box now we drop to P8 behind Alonso, with 4 laps remaining it is better to stay out.",
            undercut_summary_es="Tienes a Norris delante a 1 con 4 segundos con medios de 9 vueltas, empujando con ERS entras en su DRS en la próxima vuelta.",
            undercut_summary_en="Norris is 1 point 4 ahead on 9 lap old mediums, push with ERS to get into his DRS next lap.",
            fuel_kg=9.2,
            fuel_laps_margin=1.25,
            fuel_advice_es="Combustible en positivo, más 1 con 2 vueltas de margen.",
            fuel_advice_en="Fuel is comfortable, plus 1 point 2 laps margin.",
            ers_pct=70,
            ers_mode="medium",
            ers_mode_es="medio",
            damage_summary_es="Monoplaza limpio, sin daños en alerones ni fondo plano.",
            damage_summary_en="Car is clean, no aero damage on wings or floor.",
            weather_now="light cloud",
            weather_now_es="ligeramente nublado y pista seca",
            track_temp=29,
            air_temp=21,
            rain_forecast_pct=45,
            rain_in_mins=15,
            ahead_name="Norris",
            ahead_gap_s=1.4,
            ahead_tyre="Medium (9L)",
            ahead_last_lap="1:46.990",
            behind_name="Sainz",
            behind_gap_s=2.1,
            behind_tyre="Hard (14L)",
            behind_last_lap="1:47.120",
            pace_delta_ahead_s=0.17,
            laps_to_catch_ahead=3,
            pace_delta_behind_s=-0.30,
            laps_until_caught_behind=99,
            pace_analysis_es="Vienes rodando dos décimas por vuelta más rápido que Norris delante y tres décimas más rápido que Sainz detrás. En dos o tres giros tendrás DRS con Norris.",
            pace_analysis_en="You are lapping two tenths faster than Norris ahead and pulling away from Sainz behind by three tenths per lap. You will have DRS on Norris in two or three laps.",
            setup_advice_es="El tren delantero sufre algo más que el trasero. Pasa el reparto de frenada al 54 por ciento hacia atrás para ayudar a rotar el morro en el vértice.",
            setup_advice_en="Front axle is working harder than the rear. Move brake bias rearward to 54 percent to help rotate the nose at the apex.",
            teammate_name="Alonso",
            teammate_pos=8,
            teammate_gap="+16.4s",
            podium_gap_s=1.4,
            points_gap_s=0.0,
            retired_names=[],
            full_briefing_es=(
                "Vas cuarto en la vuelta 14 de 18, quedan 4 vueltas. Delante Norris a 1 con 4, "
                "detrás Sainz a 2 con 1. Neumático medio al 33 por ciento, aguanta perfecto hasta el final."
            ),
            full_briefing_en=(
                "You are P4 on lap 14 of 18, 4 laps remaining. Norris is 1 point 4 ahead, "
                "Sainz 2 point 1 behind. Mediums at 33 percent wear will easily make the finish."
            ),
        )

    pidx = state.player_idx
    s = state.session
    track_name = (
        L.resolve_track_name(s.track_id, s.track_length, state.swofty_track_key)
        if s
        else L.resolve_track_name(-1, 0, state.swofty_track_key)
    )
    session_name = L.SESSION_TYPES.get(s.session_type, "Session") if s else "Race"
    weather_now = L.WEATHER.get(s.weather, "clear") if s else "clear"
    weather_now_es = L.WEATHER_ES.get(weather_now, "pista seca")
    track_temp = s.track_temp if s else 28
    air_temp = s.air_temp if s else 21
    sc_status = s.safety_car if s else 0

    rain_pct = 0
    rain_mins = 0
    if s and s.forecast:
        for fc in s.forecast:
            if fc.session_type == s.session_type and fc.rain_pct > rain_pct:
                rain_pct = fc.rain_pct
                rain_mins = fc.minutes_ahead

    standings = build_standings(state, limit=24)
    me_row = next((r for r in standings if r["is_player"]), None)
    pos = me_row["pos"] if me_row else 1
    cur_lap = me_row["lap"] if me_row else 1
    player_driver = me_row["name"] if me_row else driver_label
    player_team = me_row["team"] if me_row else "Tu Escudería"
    last_lap_str = me_row["last_lap"] if me_row else "--"
    best_lap_str = me_row["best_lap"] if me_row else "--"
    my_last_ms = me_row.get("last_lap_ms", 0) if me_row else 0
    my_delta_leader_ms = me_row.get("delta_leader_ms", 0) if me_row else 0

    raw_total_laps = (s.total_laps if s and s.total_laps > 0 else cur_lap)
    total_laps = max(cur_lap, raw_total_laps)
    laps_rem = max(0, total_laps - cur_lap)

    ahead_row = next((r for r in standings if r["pos"] == pos - 1), None)
    behind_row = next((r for r in standings if r["pos"] == pos + 1), None)
    pl_lap = state.laps[pidx] if 0 <= pidx < len(state.laps) else None

    if me_row and me_row.get("delta_front_ms", 0) > 0:
        ahead_gap_s = me_row["delta_front_ms"] / 1000.0
    elif pl_lap and pl_lap.delta_front_ms > 0:
        ahead_gap_s = pl_lap.delta_front_ms / 1000.0
    else:
        ahead_gap_s = 0.0

    if behind_row and behind_row.get("delta_front_ms", 0) > 0:
        behind_gap_s = behind_row["delta_front_ms"] / 1000.0
    else:
        behind_gap_s = 0.0

    penalties_s = pl_lap.penalties_s if pl_lap else (me_row.get("penalties_s", 0) if me_row else 0)
    warnings_count = pl_lap.corner_cut_warnings if pl_lap else (me_row.get("warnings", 0) if me_row else 0)

    # Compuesto y edad de neumatico (con fallback inteligente para slots 22/23)
    inferred_comp, inferred_age = _parse_tyre_label(me_row["tyre"]) if me_row else ("Soft", max(1, cur_lap - 1))
    comp_name = inferred_comp
    tyre_age = inferred_age
    fuel_kg = max(3.5, (laps_rem + 1.4) * 1.65)
    fuel_laps = 1.40
    ers_pct = 78
    ers_mode = "medium"
    brake_bias = 56
    if 0 <= pidx < len(state.status):
        cs = state.status[pidx]
        comp_name = L.COMPOUNDS.get(cs.visual_compound) or L.COMPOUNDS.get(cs.actual_compound, inferred_comp)
        tyre_age = max(1, cs.tyre_age)
        fuel_kg = cs.fuel_kg
        fuel_laps = cs.fuel_laps
        ers_pct = min(100, int(round((cs.ers_store_j / 4_000_000.0) * 100)))
        ers_mode = L.ERS_MODE.get(cs.ers_mode, "medium")
        brake_bias = cs.brake_bias

    comp_es = L.COMPOUNDS_ES.get(comp_name, comp_name.lower())
    ers_mode_es = L.ERS_MODE_ES.get(ers_mode, ers_mode)

    max_tyre_temp = 94
    max_brake_temp = 560
    if 0 <= pidx < len(state.telemetry):
        tm = state.telemetry[pidx]
        max_tyre_temp = max(tm.tyre_inner_temps) if tm.tyre_inner_temps else 94
        max_brake_temp = max(tm.brake_temps) if tm.brake_temps else 560

    max_wear = 0.0
    worst_wheel = "FL"
    wing_fl = wing_fr = rear_w = floor_d = 0
    front_wear_avg = 0.0
    rear_wear_avg = 0.0
    if 0 <= pidx < len(state.damage):
        dm = state.damage[pidx]
        for i, w in enumerate(L.WHEELS):
            if dm.tyre_wear[i] >= max_wear:
                max_wear = float(dm.tyre_wear[i])
                worst_wheel = w
        rear_wear_avg = (dm.tyre_wear[0] + dm.tyre_wear[1]) / 2.0
        front_wear_avg = (dm.tyre_wear[2] + dm.tyre_wear[3]) / 2.0
        wing_fl, wing_fr, rear_w, floor_d = dm.front_left_wing, dm.front_right_wing, dm.rear_wing, dm.floor
    elif pidx in state.fitted_tyres:
        ft = state.fitted_tyres[pidx]
        max_wear = float(ft.wear_pct)
        front_wear_avg = max_wear
        rear_wear_avg = max(0.0, max_wear - 3.0)
    else:
        rate_est = 4.2 if "Soft" in comp_name else (3.0 if "Medium" in comp_name else 2.2)
        max_wear = min(75.0, round(tyre_age * rate_est, 1))
        front_wear_avg = max_wear
        rear_wear_avg = max(0.0, max_wear - 2.5)

    worst_wheel_es = L.WHEELS_ES.get(worst_wheel, worst_wheel)
    worst_wheel_en = L.WHEELS_EN.get(worst_wheel, worst_wheel)
    wear_per_lap = max(1.8, max_wear / max(1, tyre_age)) if max_wear > 2.0 else 3.2
    if pidx in state.fitted_tyres and state.fitted_tyres[pidx].life_span_laps > 0:
        est_tyre_laps_left = state.fitted_tyres[pidx].life_span_laps
    else:
        est_tyre_laps_left = max(0, int((68.0 - max_wear) / wear_per_lap))

    ideal_lap = s.pit_window_ideal if s and s.pit_window_ideal > 0 else max(1, total_laps // 2 - 1)
    latest_lap = s.pit_window_latest if s and s.pit_window_latest > 0 else max(2, total_laps // 2 + 1)
    pit_loss_ms = 13000 if sc_status in (1, 2) else 21500
    after_pit_delta = my_delta_leader_ms + pit_loss_ms

    rejoin_pos = pos
    car_ahead_on_rejoin = None
    for r in standings:
        if r["is_player"]:
            continue
        if r.get("delta_leader_ms", 0) < after_pit_delta and r["pos"] > pos:
            rejoin_pos = r["pos"]
            car_ahead_on_rejoin = r["name"]
    if s and 0 < s.pit_rejoin_position <= len(standings):
        rejoin_pos = s.pit_rejoin_position
    rejoin_pos = min(rejoin_pos, len(standings))

    if s and s.weather in (3, 4, 5) or (rain_pct >= 65 and rain_mins <= 5):
        rec_comp = "Intermediate"
    elif laps_rem <= 11:
        rec_comp = "Soft"
    elif laps_rem <= 23:
        rec_comp = "Medium"
    else:
        rec_comp = "Hard"
    rec_comp_es = L.COMPOUNDS_ES.get(rec_comp, rec_comp.lower())

    max_wing = max(wing_fl, wing_fr, rear_w)
    my_pits = me_row["pits"] if me_row else 0
    if max_wing >= 25:
        box_rec = "BOX THIS LAP (WING DAMAGE)"
    elif max_wear >= 65.0 and laps_rem > 1:
        box_rec = "BOX THIS LAP (TYRE WEAR CRITICAL)"
    elif sc_status in (1, 2) and max_wear >= 35.0 and laps_rem >= 5:
        box_rec = "BOX UNDER SAFETY CAR (FREE STOP)"
    elif rain_pct >= 55 and 0 < rain_mins <= 10 and comp_name not in ("Intermediate", "Wet"):
        box_rec = "HOLD OUT FOR RAIN"
    elif total_laps >= 8 and ideal_lap <= cur_lap <= latest_lap and my_pits == 0:
        box_rec = "PIT WINDOW OPEN"
    else:
        box_rec = "STAY OUT"

    rejoin_es = (
        f"Si entras a boxes en esta vuelta saldrías en la posición {rejoin_pos}"
        + (f" detrás de {car_ahead_on_rejoin}" if car_ahead_on_rejoin else " con aire limpio")
        + f", montando goma {rec_comp_es}."
    )
    rejoin_en = (
        f"If we box this lap we rejoin in P{rejoin_pos}"
        + (f" behind {car_ahead_on_rejoin}" if car_ahead_on_rejoin else " in clean air")
        + f", fitting the {rec_comp} tyre."
    )

    if ahead_row and 0.8 <= ahead_gap_s <= 3.2:
        undercut_es = (
            f"Tienes a {ahead_row['name']} delante a {ahead_gap_s:.1f} segundos. "
            "Estás en rango de undercut si paramos antes o de presionarle para buscar su DRS."
        )
        undercut_en = (
            f"{ahead_row['name']} is {ahead_gap_s:.1f} seconds ahead. "
            "You are in undercut range if we box early, or push hard to get into his DRS."
        )
    elif ahead_row:
        undercut_es = f"Delante tienes a {ahead_row['name']} a {ahead_gap_s:.1f} segundos."
        undercut_en = f"Car ahead is {ahead_row['name']} at {ahead_gap_s:.1f} seconds."
    else:
        undercut_es = "Lideras la carrera con aire limpio por delante."
        undercut_en = "You are leading the race with clean air ahead."

    # Analisis de ritmo comparativo (cuanto recortas o pierdes por vuelta y en cuantas vueltas le pillas)
    ahead_ms = ahead_row.get("last_lap_ms", 0) if ahead_row else 0
    behind_ms = behind_row.get("last_lap_ms", 0) if behind_row else 0
    pace_delta_ahead_s = (ahead_ms - my_last_ms) / 1000.0 if (ahead_ms > 0 and my_last_ms > 0) else 0.0
    pace_delta_behind_s = (my_last_ms - behind_ms) / 1000.0 if (behind_ms > 0 and my_last_ms > 0) else 0.0

    if ahead_row and pace_delta_ahead_s > 0.08:
        gap_to_drs = max(0.1, ahead_gap_s - 0.9)
        laps_to_catch_ahead = max(1, int(round(gap_to_drs / pace_delta_ahead_s)))
    else:
        laps_to_catch_ahead = 99

    if behind_row and pace_delta_behind_s > 0.08:
        gap_from_behind = max(0.1, behind_gap_s - 0.8)
        laps_until_caught_behind = max(1, int(round(gap_from_behind / pace_delta_behind_s)))
    else:
        laps_until_caught_behind = 99

    if ahead_row and pace_delta_ahead_s >= 0.12:
        pace_es = (
            f"Vienes rodando {pace_delta_ahead_s:.1f} segundos por vuelta más rápido que {ahead_row['name']}. "
            + (
                f"A este ritmo te metes en su DRS en unas {laps_to_catch_ahead} vueltas."
                if ahead_gap_s > 1.0 and laps_to_catch_ahead <= max(1, laps_rem)
                else "Ya lo tienes a tiro de ataque."
            )
        )
        pace_en = (
            f"You are lapping {pace_delta_ahead_s:.1f} seconds faster than {ahead_row['name']} ahead. "
            + (
                f"At this pace you will catch his DRS in about {laps_to_catch_ahead} laps."
                if ahead_gap_s > 1.0 and laps_to_catch_ahead <= max(1, laps_rem)
                else "You are right on his gearbox."
            )
        )
    elif ahead_row and pace_delta_ahead_s <= -0.12:
        pace_es = (
            f"{ahead_row['name']} delante ha rodado {abs(pace_delta_ahead_s):.1f} segundos más rápido en el último giro"
            + (
                f", y ojo detrás que {behind_row['name']} nos recorta {pace_delta_behind_s:.1f} por vuelta."
                if behind_row and pace_delta_behind_s > 0.12
                else f", pero mantienes a {behind_row['name']} detrás controlado a {behind_gap_s:.1f} segundos."
                if behind_row
                else "."
            )
        )
        pace_en = (
            f"{ahead_row['name']} ahead was {abs(pace_delta_ahead_s):.1f} seconds quicker last lap"
            + (
                f", and watch out behind as {behind_row['name']} is closing by {pace_delta_behind_s:.1f} per lap."
                if behind_row and pace_delta_behind_s > 0.12
                else "."
            )
        )
    else:
        pace_es = (
            f"Estás calcando los tiempos con {ahead_row['name'] if ahead_row else 'la cabeza'}. "
            f"Tu última vuelta fue {last_lap_str} y tu mejor registro es {best_lap_str}."
        )
        pace_en = (
            f"Your pace is matching {ahead_row['name'] if ahead_row else 'the leader'} within a tenth. "
            f"Last lap {last_lap_str}, personal best {best_lap_str}."
        )

    # Consejo de reglajes (Frenada / Diferencial / Temperaturas)
    if max_tyre_temp >= 104:
        setup_es = (
            f"Tienes las gomas a {max_tyre_temp} grados, rozando el sobrecalentamiento. "
            "Suaviza el giro de volante en curva rápida y abre un punto el diferencial en aceleración."
        )
        setup_en = (
            f"Tyre core temps are high at {max_tyre_temp} degrees. "
            "Be smoother on steering input through fast corners and open the on-throttle differential."
        )
    elif front_wear_avg > rear_wear_avg + 3.5:
        rec_bb = max(50, brake_bias - 2)
        setup_es = (
            f"Estás castigando más el tren delantero que el trasero. "
            f"Baja el reparto de frenada un par de puntos al {rec_bb} por ciento para ayudar a meter el morro sin bloquear."
        )
        setup_en = (
            f"Front tyres are wearing faster than the rears. "
            f"Move brake bias two clicks rearward to {rec_bb} percent to help rotate the car without locking up."
        )
    elif rear_wear_avg > front_wear_avg + 3.5:
        rec_bb = min(62, brake_bias + 2)
        setup_es = (
            f"Las ruedas traseras están sufriendo en tracción. "
            f"Sube el reparto de frenada al {rec_bb} por ciento delante y mete una marcha más larga al salir de curva lenta."
        )
        setup_en = (
            f"Rear tyres are taking a beating on traction. "
            f"Shift brake bias forward to {rec_bb} percent and short-shift out of slow corners."
        )
    else:
        setup_es = (
            f"El equilibrio entre ejes es muy bueno con el reparto de frenada al {brake_bias} por ciento y gomas a {max_tyre_temp} grados. "
            "Si notas subviraje en entrada de curva, atrasa un clic la frenada."
        )
        setup_en = (
            f"Aero and mechanical balance look solid with brake bias at {brake_bias} percent and tyres at {max_tyre_temp} degrees. "
            "Move bias one click rearward if you feel entry understeer."
        )

    # Companero de equipo, distancia a podio (P3) y puntos (P10), y abandonos
    teammate_row = next(
        (r for r in standings if r["team"] == player_team and not r["is_player"] and player_team not in ("Unknown Team", "Tu Monoplaza")),
        None,
    )
    teammate_name = teammate_row["name"] if teammate_row else "tu compañero"
    teammate_pos = teammate_row["pos"] if teammate_row else 0
    teammate_gap = teammate_row["gap_leader"] if teammate_row else "--"

    p3_row = next((r for r in standings if r["pos"] == 3), None)
    if pos <= 3:
        podium_gap_s = 0.0
    elif p3_row:
        podium_gap_s = max(0.1, (my_delta_leader_ms - p3_row.get("delta_leader_ms", 0)) / 1000.0)
    else:
        podium_gap_s = 0.0

    p10_row = next((r for r in standings if r["pos"] == 10), None)
    if pos <= 10:
        points_gap_s = 0.0
    elif p10_row:
        points_gap_s = max(0.1, (my_delta_leader_ms - p10_row.get("delta_leader_ms", 0)) / 1000.0)
    else:
        points_gap_s = 0.0

    retired_names = [r["name"] for r in standings if r["status"] in ("DNF", "DSQ", "retired")]

    if fuel_laps < 0.15:
        fuel_es = f"Ojo al combustible, estamos en {fuel_laps:+.1f} vueltas, haz lift and coast al final de las rectas."
        fuel_en = f"Fuel is tight at {fuel_laps:+.1f} laps, we need lift and coast into heavy braking zones."
    elif fuel_laps > 1.2:
        fuel_es = f"Vamos sobrados de gasolina, tienes más {fuel_laps:.1f} vueltas de margen."
        fuel_en = f"Plenty of fuel on board, plus {fuel_laps:.1f} laps margin."
    else:
        fuel_es = f"Combustible en objetivo, más {fuel_laps:.1f} vueltas de margen."
        fuel_en = f"Fuel is on target, plus {fuel_laps:.1f} laps margin."

    if max_wing > 5 or floor_d > 5:
        dmg_es = f"Tenemos daños aerodinámicos: alerón al {max(wing_fl, wing_fr)} por ciento y fondo plano al {floor_d} por ciento."
        dmg_en = f"Aero damage detected: front wing {max(wing_fl, wing_fr)} percent, floor {floor_d} percent."
    else:
        dmg_es = "El monoplaza está intacto, cero daños en alerones ni fondo plano."
        dmg_en = "Car is clean, zero damage on wings or floor."

    brief_es = (
        f"Ruedas en posición {pos} de {len(standings)} con el {player_team}, vuelta {cur_lap} de {total_laps}, quedan {laps_rem} vueltas. "
        f"{undercut_es} Llevas goma {comp_es} al {max_wear:.0f} por ciento y batería al {ers_pct} por ciento."
    )
    brief_en = (
        f"You are P{pos} of {len(standings)} in the {player_team}, lap {cur_lap} of {total_laps}, {laps_rem} laps remaining. "
        f"{undercut_en} {comp_name} tyres at {max_wear:.0f} percent wear and battery at {ers_pct} percent."
    )

    return StrategyReport(
        connected=True,
        track_name=track_name,
        session_name=session_name,
        player_driver=player_driver,
        player_team=player_team,
        current_lap=cur_lap,
        total_laps=total_laps,
        laps_remaining=laps_rem,
        position=pos,
        total_cars=len(standings),
        last_lap_str=last_lap_str,
        best_lap_str=best_lap_str,
        current_tyre=comp_name,
        current_tyre_es=comp_es,
        tyre_age=tyre_age,
        max_wear_pct=max_wear,
        worst_wheel=worst_wheel,
        worst_wheel_es=worst_wheel_es,
        worst_wheel_en=worst_wheel_en,
        wear_per_lap=wear_per_lap,
        est_tyre_laps_left=est_tyre_laps_left,
        max_tyre_temp=max_tyre_temp,
        max_brake_temp=max_brake_temp,
        brake_bias=brake_bias,
        penalties_s=penalties_s,
        warnings_count=warnings_count,
        box_recommendation=box_rec,
        recommended_compound=rec_comp,
        recommended_compound_es=rec_comp_es,
        pit_window_ideal=ideal_lap,
        pit_window_latest=latest_lap,
        predicted_rejoin_pos=rejoin_pos,
        rejoin_summary_es=rejoin_es,
        rejoin_summary_en=rejoin_en,
        undercut_summary_es=undercut_es,
        undercut_summary_en=undercut_en,
        fuel_kg=fuel_kg,
        fuel_laps_margin=fuel_laps,
        fuel_advice_es=fuel_es,
        fuel_advice_en=fuel_en,
        ers_pct=ers_pct,
        ers_mode=ers_mode,
        ers_mode_es=ers_mode_es,
        damage_summary_es=dmg_es,
        damage_summary_en=dmg_en,
        weather_now=weather_now,
        weather_now_es=weather_now_es,
        track_temp=track_temp,
        air_temp=air_temp,
        rain_forecast_pct=rain_pct,
        rain_in_mins=rain_mins,
        ahead_name=ahead_row["name"] if ahead_row else "Nadie",
        ahead_gap_s=ahead_gap_s,
        ahead_tyre=ahead_row["tyre"] if ahead_row else "-",
        ahead_last_lap=ahead_row["last_lap"] if ahead_row else "--",
        behind_name=behind_row["name"] if behind_row else "Nadie",
        behind_gap_s=behind_gap_s,
        behind_tyre=behind_row["tyre"] if behind_row else "-",
        behind_last_lap=behind_row["last_lap"] if behind_row else "--",
        pace_delta_ahead_s=pace_delta_ahead_s,
        laps_to_catch_ahead=laps_to_catch_ahead,
        pace_delta_behind_s=pace_delta_behind_s,
        laps_until_caught_behind=laps_until_caught_behind,
        pace_analysis_es=pace_es,
        pace_analysis_en=pace_en,
        setup_advice_es=setup_es,
        setup_advice_en=setup_en,
        teammate_name=teammate_name,
        teammate_pos=teammate_pos,
        teammate_gap=teammate_gap,
        podium_gap_s=podium_gap_s,
        points_gap_s=points_gap_s,
        retired_names=retired_names,
        full_briefing_es=brief_es,
        full_briefing_en=brief_en,
    )


class ProactiveSpotter:
    """Supervisa cambios en el estado de carrera y lanza avisos automaticos variados."""

    def __init__(self, driver_name: str = "Jorge"):
        self.driver_name = driver_name
        self.last_session_uid: int = 0
        self.last_lap: int = 0
        self.last_pos: int = 0
        self.warned_pit_open: bool = False
        self.warned_wear_50: bool = False
        self.warned_wear_70: bool = False
        self.warned_fuel_low: bool = False
        self.warned_wing_dmg: int = 0
        self.warned_rain: bool = False
        self.warned_ers_full: bool = False
        self.warned_ers_low: bool = False
        self.last_drs_ahead_ts: float = 0.0
        self.last_drs_behind_ts: float = 0.0
        self.warned_track_limits: int = 0
        self.last_callout_time: float = 0.0

    def reset(self, session_uid: int) -> None:
        self.last_session_uid = session_uid
        self.last_lap = 0
        self.last_pos = 0
        self.warned_pit_open = False
        self.warned_wear_50 = False
        self.warned_wear_70 = False
        self.warned_fuel_low = False
        self.warned_wing_dmg = 0
        self.warned_rain = False
        self.warned_ers_full = False
        self.warned_ers_low = False
        self.last_drs_ahead_ts = 0.0
        self.last_drs_behind_ts = 0.0
        self.warned_track_limits = 0

    def check(self, state: RaceState, lang: str = "es") -> str | None:
        """Devuelve un mensaje proactivo variado si ha ocurrido algo relevante en pista."""
        if not state.connected or not state.laps:
            return None
        now = time.time()
        # Esperar 1.2s al inicio de sesion para que lleguen Participants (4), Status (7) y Swofty Track (200)
        if state.first_packet_time > 0 and (now - state.first_packet_time < 1.2) and not state.participants:
            return None
        if now - self.last_callout_time < 8.5:
            return None

        rep = analyze_strategy(state, self.driver_name)

        if state.session_uid != self.last_session_uid and state.session_uid != 0:
            self.reset(state.session_uid)
            self.last_lap = rep.current_lap
            self.last_pos = rep.position
            self.last_callout_time = now
            if lang == "en":
                return random.choice([
                    f"Radio check {self.driver_name}, live telemetry locked in from {rep.track_name}. You are P{rep.position} in the {rep.player_team} on {rep.current_tyre}s. Let's have a strong race.",
                    f"Loud and clear from the pit wall at {rep.track_name}. Running P{rep.position} on the {rep.current_tyre} compound. Head down!",
                    f"Pit wall online at {rep.track_name}, {self.driver_name}. You are P{rep.position}, temperatures look good. Let's push!",
                ])
            return random.choice([
                f"Radio conectada {self.driver_name}, telemetría en vivo desde {rep.track_name}. Ruedas en posición {rep.position} con el {rep.player_team} y goma {rep.current_tyre_es}. Vamos a por todas.",
                f"Te copio alto y claro en el muro de {rep.track_name}, {self.driver_name}. Posición {rep.position} con neumático {rep.current_tyre_es}, buena carrera.",
                f"Telemetría enganchada en {rep.track_name}. Estás en el puesto {rep.position} al volante del {rep.player_team}, todo en verde.",
            ])

        pidx = state.player_idx
        pl_lap = state.laps[pidx] if 0 <= pidx < len(state.laps) else None

        # 0. Adelantamiento ganado o posicion perdida en pista (a partir de vuelta 2)
        if self.last_pos > 0 and rep.position != self.last_pos and rep.current_lap >= 2:
            old_pos = self.last_pos
            self.last_pos = rep.position
            if rep.position < old_pos:
                self.last_callout_time = now
                if lang == "en":
                    return random.choice([
                        f"Great move {self.driver_name}! Up into P{rep.position}, next target ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds.",
                        f"Nice overtake! That puts us P{rep.position}. Keep your head down and hunt down {rep.ahead_name}.",
                        f"Clinical pass {self.driver_name}, P{rep.position} is ours! Build the gap now.",
                    ])
                return random.choice([
                    f"¡Buena maniobra {self.driver_name}! Subes a la posición {rep.position}, tu siguiente objetivo es {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos.",
                    f"¡Gran adelantamiento! Ya estás en el puesto {rep.position}, ahora abre hueco con {rep.behind_name}.",
                    f"¡Así se mete el coche {self.driver_name}! Posición {rep.position} consolidada, vamos a por {rep.ahead_name}.",
                ])
            if rep.position > old_pos and (rep.position - old_pos) <= 2:
                self.last_callout_time = now
                if lang == "en":
                    return random.choice([
                        f"We lost a spot to {rep.ahead_name}, now P{rep.position}. Stay calm and tuck into his slipstream.",
                        f"Down to P{rep.position}, don't overcook the tyres trying to get it back in one corner, use DRS on the straight.",
                    ])
                return random.choice([
                    f"Hemos perdido posición con {rep.ahead_name}, ahora vas puesto {rep.position}. Pégate a su alerón y devuélvesela con DRS.",
                    f"Caemos al puesto {rep.position} {self.driver_name}, cabeza fría, no sobrecalientes las gomas y prepárate la recta.",
                ])
        else:
            self.last_pos = rep.position

        # 1. Cambio de vuelta: Ultima vuelta, Quedan 3 vueltas, Ventana de boxes abierta
        if rep.current_lap != self.last_lap and rep.current_lap > 1:
            self.last_lap = rep.current_lap

            if rep.total_laps >= 2 and rep.current_lap == rep.total_laps:
                self.last_callout_time = now
                if lang == "en":
                    return random.choice([
                        f"Final lap {self.driver_name}, last lap! You are P{rep.position}, {rep.ahead_name} is {rep.ahead_gap_s:.1f} ahead, {rep.behind_name} {rep.behind_gap_s:.1f} behind. Empty the battery!",
                        f"White flag, one lap to go! P{rep.position} right now, deploy all remaining ERS to the line!",
                        f"Last lap of the race {self.driver_name}! Everything you have got left, P{rep.position}, push to the chequered flag!",
                    ])
                return random.choice([
                    f"¡Última vuelta {self.driver_name}, entramos en la última vuelta! Vas posición {rep.position}, delante {rep.ahead_name} a {rep.ahead_gap_s:.1f}, detrás {rep.behind_name} a {rep.behind_gap_s:.1f}. ¡Vacía la batería!",
                    f"¡Bandera blanca {self.driver_name}, queda una sola vuelta! Estás en posición {rep.position}, gasta todo el ERS que te queda hasta la meta.",
                    f"¡Último giro {self.driver_name}! Posición {rep.position}, dalo absolutamente todo de aquí a la bandera a cuadros.",
                ])

            if rep.laps_remaining == 3 and rep.total_laps >= 5:
                self.last_callout_time = now
                if lang == "en":
                    return f"Three laps remaining, P{rep.position}. Tyres at {rep.max_wear_pct:.0f} percent, battery at {rep.ers_pct} percent. {rep.pace_analysis_en}"
                return f"Tres vueltas para el final, ruedas en posición {rep.position}. Gomas al {rep.max_wear_pct:.0f} por ciento y batería al {rep.ers_pct}. {rep.pace_analysis_es}"

            if not self.warned_pit_open and rep.total_laps >= 8 and rep.pit_window_ideal > 0 and rep.current_lap == rep.pit_window_ideal:
                self.warned_pit_open = True
                self.last_callout_time = now
                if lang == "en":
                    return f"Pit window is now open, ideal stop between lap {rep.pit_window_ideal} and {rep.pit_window_latest}. {rep.rejoin_summary_en}"
                return f"Se abre nuestra ventana de parada en boxes en esta vuelta. {rep.rejoin_summary_es}"

        # 2. Daño nuevo en el aleron tras toque
        if 0 <= pidx < len(state.damage):
            dm = state.damage[pidx]
            wing = max(dm.front_left_wing, dm.front_right_wing, dm.rear_wing)
            if wing >= self.warned_wing_dmg + 12:
                self.warned_wing_dmg = wing
                self.last_callout_time = now
                if wing >= 30:
                    return (
                        f"Heavy front wing damage at {wing} percent! Box this lap for a new nose, copy."
                        if lang == "en"
                        else f"¡Daño grave en el alerón del {wing} por ciento! Entra a boxes en esta vuelta para cambiar el morro."
                    )
                return (
                    f"We see minor wing damage on the data, {wing} percent. Watch your front grip."
                    if lang == "en"
                    else f"Vemos pérdida de carga en el alerón del {wing} por ciento en telemetría. Vigila el subviraje en curva rápida."
                )

        # 3. Desgaste de neumaticos al 50% y al 70%
        if not self.warned_wear_70 and rep.max_wear_pct >= 70.0:
            self.warned_wear_70 = True
            self.last_callout_time = now
            if lang == "en":
                return f"Careful {self.driver_name}, tyre wear is critical at {rep.max_wear_pct:.0f} percent on the {rep.worst_wheel_en}, puncture risk! Box this lap!"
            return f"¡Mucho cuidado {self.driver_name}, desgaste crítico del {rep.max_wear_pct:.0f} por ciento en la {rep.worst_wheel_es}, riesgo de pinchazo! ¡Box en esta vuelta!"

        if not self.warned_wear_50 and rep.max_wear_pct >= 50.0:
            self.warned_wear_50 = True
            self.last_callout_time = now
            if lang == "en":
                return f"Tyres have crossed {rep.max_wear_pct:.0f} percent wear on the {rep.worst_wheel_en}, about {rep.est_tyre_laps_left} good laps left."
            return f"Superamos el {rep.max_wear_pct:.0f} por ciento de desgaste en la {rep.worst_wheel_es}, te quedan unas {rep.est_tyre_laps_left} vueltas con agarre."

        # 4. Combustible bajo
        if not self.warned_fuel_low and rep.fuel_laps_margin < 0.12 and rep.current_lap > 1:
            self.warned_fuel_low = True
            self.last_callout_time = now
            return rep.fuel_advice_en if lang == "en" else rep.fuel_advice_es

        # 5. Avisos de limites de pista (2 avisos = al borde de sancion)
        if pl_lap and pl_lap.corner_cut_warnings >= 2 and pl_lap.corner_cut_warnings > self.warned_track_limits:
            self.warned_track_limits = pl_lap.corner_cut_warnings
            self.last_callout_time = now
            if lang == "en":
                return "Careful with track limits, you are on two warnings, one more is a three second penalty."
            return "Ojo con los límites de pista, llevas dos avisos, al siguiente nos caen tres segundos de sanción."

        # 6. Entrada en zona de DRS delante o amenaza de DRS detras (con cooldown de 45s)
        if 0.15 < rep.ahead_gap_s <= 0.95 and (now - self.last_drs_ahead_ts > 45.0) and rep.current_lap >= 2:
            self.last_drs_ahead_ts = now
            self.last_callout_time = now
            if lang == "en":
                return random.choice([
                    f"You are inside DRS range of {rep.ahead_name}, {rep.ahead_gap_s:.1f} seconds. Use Overtake on the straight!",
                    f"DRS available on {rep.ahead_name} ahead, gap is {rep.ahead_gap_s:.1f}. Attack when ready!",
                    f"Right under one second to {rep.ahead_name}, open the rear wing in the DRS zone and send it!",
                ])
            return random.choice([
                f"Tienes DRS con {rep.ahead_name} delante, a {rep.ahead_gap_s:.1f} segundos. ¡Atácale en la recta!",
                f"Ya estás a menos de un segundo de {rep.ahead_name}, DRS disponible, usa el botón de adelantamiento.",
                f"Entras en ventana de DRS con {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos. Prepara bien la salida a recta.",
            ])

        if 0.15 < rep.behind_gap_s <= 0.90 and (now - self.last_drs_behind_ts > 45.0) and rep.current_lap >= 2:
            self.last_drs_behind_ts = now
            self.last_callout_time = now
            if lang == "en":
                return random.choice([
                    f"Watch your mirrors, {rep.behind_name} has DRS behind you at {rep.behind_gap_s:.1f} seconds.",
                    f"Pressure from {rep.behind_name} behind at {rep.behind_gap_s:.1f} with DRS, defend the inside line.",
                    f"{rep.behind_name} is right on your tail at {rep.behind_gap_s:.1f} with DRS, save some ERS for the straight.",
                ])
            return random.choice([
                f"Vigila los retrovisores, {rep.behind_name} tiene DRS detrás a {rep.behind_gap_s:.1f} segundos.",
                f"Tienes a {rep.behind_name} pegado a {rep.behind_gap_s:.1f} con DRS, cierra bien el interior en la frenada.",
                f"Atento por detrás, {rep.behind_name} viene a {rep.behind_gap_s:.1f} segundos con el alerón abierto, guárdate batería para defender.",
            ])

        # 7. Gestion de bateria (casi llena 98% o agotada <12%)
        if not self.warned_ers_full and rep.ers_pct >= 98 and rep.current_lap >= 2:
            self.warned_ers_full = True
            self.last_callout_time = now
            if lang == "en":
                return f"Battery is topped up at {rep.ers_pct} percent {self.driver_name}, deploy Overtake on the straights so we don't clip energy."
            return f"Tienes la batería al {rep.ers_pct} por ciento {self.driver_name}, despliega adelantamiento en las rectas para no desperdiciar regeneración."

        if not self.warned_ers_low and rep.ers_pct <= 12 and rep.current_lap >= 2 and rep.laps_remaining > 1:
            self.warned_ers_low = True
            self.last_callout_time = now
            if lang == "en":
                return f"ERS battery is down to {rep.ers_pct} percent, switch to Medium deployment to harvest for a lap."
            return f"Cuidado con la batería, te queda solo un {rep.ers_pct} por ciento, baja el mapa para recargar en las frenadas."

        # 8. Lluvia inminente
        if not self.warned_rain and rep.rain_forecast_pct >= 60 and 0 < rep.rain_in_mins <= 10:
            self.warned_rain = True
            self.last_callout_time = now
            if lang == "en":
                return f"Weather radar shows {rep.rain_forecast_pct} percent chance of rain in {rep.rain_in_mins} minutes."
            return f"Atención al radar, sube al {rep.rain_forecast_pct} por ciento la probabilidad de lluvia en {rep.rain_in_mins} minutos."

        return None
