"""Motor de estrategia de carrera en tiempo real y avisos proactivos (Spotter + Estratega)."""
from __future__ import annotations

from dataclasses import dataclass
import random
import time

from .telemetry import lookups as L
from .telemetry.context import build_standings, fmt_ms
from .telemetry.listener import RaceState


@dataclass
class StrategyReport:
    connected: bool
    track_name: str
    session_name: str
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
    full_briefing_es: str
    full_briefing_en: str


def analyze_strategy(state: RaceState, driver_label: str = "Jorge") -> StrategyReport:
    """Calcula toda la situacion tactica y posibles estrategias de la carrera."""
    if not state.connected or not state.laps:
        return StrategyReport(
            connected=False,
            track_name="Spa-Francorchamps (Demo)",
            session_name="Race",
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
            full_briefing_es=(
                f"Vas cuarto en la vuelta 14 de 18, quedan 4 vueltas. Delante Norris a 1 con 4, "
                "detrás Sainz a 2 con 1. Neumático medio al 33 por ciento, aguanta perfecto hasta el final."
            ),
            full_briefing_en=(
                "You are P4 on lap 14 of 18, 4 laps remaining. Norris is 1 point 4 ahead, "
                "Sainz 2 point 1 behind. Mediums at 33 percent wear will easily make the finish."
            ),
        )

    pidx = state.player_idx
    s = state.session
    track_name = L.TRACKS.get(s.track_id, f"Circuito #{s.track_id}") if s else "Circuito"
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

    standings = build_standings(state, limit=22)
    me_row = next((r for r in standings if r["is_player"]), None)
    pos = me_row["pos"] if me_row else 1
    cur_lap = me_row["lap"] if me_row else 1
    player_team = me_row["team"] if me_row else "Tu Equipo"
    last_lap_str = me_row["last_lap"] if me_row else "--"
    best_lap_str = me_row["best_lap"] if me_row else "--"

    raw_total_laps = (s.total_laps if s and s.total_laps > 0 else cur_lap)
    total_laps = max(cur_lap, raw_total_laps)
    laps_rem = max(0, total_laps - cur_lap)

    ahead_row = next((r for r in standings if r["pos"] == pos - 1), None)
    behind_row = next((r for r in standings if r["pos"] == pos + 1), None)
    pl_lap = state.laps[pidx] if 0 <= pidx < len(state.laps) else None
    ahead_gap_s = (pl_lap.delta_front_ms / 1000.0) if pl_lap and pl_lap.delta_front_ms > 0 else 0.0
    behind_lap = state.laps[behind_row["idx"]] if behind_row and 0 <= behind_row["idx"] < len(state.laps) else None
    behind_gap_s = (behind_lap.delta_front_ms / 1000.0) if behind_lap and behind_lap.delta_front_ms > 0 else 0.0

    penalties_s = pl_lap.penalties_s if pl_lap else 0
    warnings_count = pl_lap.corner_cut_warnings if pl_lap else 0

    comp_name = "Medium"
    tyre_age = 1
    fuel_kg = 20.0
    fuel_laps = 1.0
    ers_pct = 70
    ers_mode = "medium"
    brake_bias = 56
    if 0 <= pidx < len(state.status):
        cs = state.status[pidx]
        comp_name = L.COMPOUNDS.get(cs.visual_compound) or L.COMPOUNDS.get(cs.actual_compound, "Medium")
        tyre_age = max(1, cs.tyre_age)
        fuel_kg = cs.fuel_kg
        fuel_laps = cs.fuel_laps
        ers_pct = min(100, int(round((cs.ers_store_j / 4_000_000.0) * 100)))
        ers_mode = L.ERS_MODE.get(cs.ers_mode, "medium")
        brake_bias = cs.brake_bias

    comp_es = L.COMPOUNDS_ES.get(comp_name, comp_name.lower())
    ers_mode_es = L.ERS_MODE_ES.get(ers_mode, ers_mode)

    max_tyre_temp = 92
    max_brake_temp = 550
    if 0 <= pidx < len(state.telemetry):
        tm = state.telemetry[pidx]
        max_tyre_temp = max(tm.tyre_inner_temps) if tm.tyre_inner_temps else 92
        max_brake_temp = max(tm.brake_temps) if tm.brake_temps else 550

    max_wear = 0.0
    worst_wheel = "FL"
    wing_fl = wing_fr = rear_w = floor_d = 0
    if 0 <= pidx < len(state.damage):
        dm = state.damage[pidx]
        for i, w in enumerate(L.WHEELS):
            if dm.tyre_wear[i] >= max_wear:
                max_wear = float(dm.tyre_wear[i])
                worst_wheel = w
        wing_fl, wing_fr, rear_w, floor_d = dm.front_left_wing, dm.front_right_wing, dm.rear_wing, dm.floor

    worst_wheel_es = L.WHEELS_ES.get(worst_wheel, worst_wheel)
    worst_wheel_en = L.WHEELS_EN.get(worst_wheel, worst_wheel)
    wear_per_lap = max(1.8, max_wear / max(1, tyre_age)) if max_wear > 2.0 else 3.2
    est_tyre_laps_left = max(0, int((68.0 - max_wear) / wear_per_lap))

    ideal_lap = s.pit_window_ideal if s and s.pit_window_ideal > 0 else max(1, total_laps // 2 - 1)
    latest_lap = s.pit_window_latest if s and s.pit_window_latest > 0 else max(2, total_laps // 2 + 2)
    pit_loss_ms = 13000 if sc_status in (1, 2) else 21500
    my_delta_leader = pl_lap.delta_leader_ms if pl_lap else 0
    after_pit_delta = my_delta_leader + pit_loss_ms

    rejoin_pos = pos
    car_ahead_on_rejoin = None
    for r in standings:
        if r["is_player"]:
            continue
        r_lap = state.laps[r["idx"]]
        if r_lap.delta_leader_ms < after_pit_delta and r["pos"] > pos:
            rejoin_pos = r["pos"]
            car_ahead_on_rejoin = r["name"]
    if s and s.pit_rejoin_position > 0:
        rejoin_pos = s.pit_rejoin_position

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
    if max_wing >= 25:
        box_rec = "BOX THIS LAP (WING DAMAGE)"
    elif max_wear >= 65.0 and laps_rem > 1:
        box_rec = "BOX THIS LAP (TYRE WEAR CRITICAL)"
    elif sc_status in (1, 2) and max_wear >= 35.0 and laps_rem >= 5:
        box_rec = "BOX UNDER SAFETY CAR (FREE STOP)"
    elif rain_pct >= 55 and 0 < rain_mins <= 10 and comp_name not in ("Intermediate", "Wet"):
        box_rec = "HOLD OUT FOR RAIN"
    elif total_laps >= 8 and ideal_lap <= cur_lap <= latest_lap and (pl_lap and pl_lap.num_pit_stops == 0):
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
            "Estás en rango de undercut si paramos antes o de presionarle para buscar el DRS."
        )
        undercut_en = (
            f"{ahead_row['name']} is {ahead_gap_s:.1f} seconds ahead. "
            "You are in undercut range if we box early, or push hard to get DRS."
        )
    elif ahead_row:
        undercut_es = f"Delante tienes a {ahead_row['name']} a {ahead_gap_s:.1f} segundos."
        undercut_en = f"Car ahead is {ahead_row['name']} at {ahead_gap_s:.1f} seconds."
    else:
        undercut_es = "Lideras la carrera con aire limpio delante."
        undercut_en = "You are leading the race with clean air ahead."

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
        f"Ruedas en posición {pos} en la vuelta {cur_lap} de {total_laps}, quedan {laps_rem} vueltas. "
        f"{undercut_es} Llevas goma {comp_es} al {max_wear:.0f} por ciento y batería al {ers_pct} por ciento."
    )
    brief_en = (
        f"You are P{pos} on lap {cur_lap} of {total_laps}, {laps_rem} laps remaining. "
        f"{undercut_en} {comp_name} tyres at {max_wear:.0f} percent wear and battery at {ers_pct} percent."
    )

    return StrategyReport(
        connected=True,
        track_name=track_name,
        session_name=session_name,
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
        self.last_drs_ahead_ts = 0.0
        self.last_drs_behind_ts = 0.0
        self.warned_track_limits = 0

    def check(self, state: RaceState, lang: str = "es") -> str | None:
        """Devuelve un mensaje proactivo variado si ha ocurrido algo relevante en pista."""
        if not state.connected or not state.laps:
            return None
        now = time.time()
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
                    f"Radio check {self.driver_name}, live telemetry locked in from {rep.track_name}. You are P{rep.position} on {rep.current_tyre}s. Let's have a clean race.",
                    f"Loud and clear from the pit wall at {rep.track_name}. Starting P{rep.position} on the {rep.current_tyre} compound. Head down!",
                ])
            return random.choice([
                f"Radio conectada {self.driver_name}, telemetría en vivo desde {rep.track_name}. Sales en posición {rep.position} con goma {rep.current_tyre_es}. Vamos a por todas.",
                f"Te copio alto y claro en el muro de {rep.track_name}, {self.driver_name}. Posición {rep.position} con neumático {rep.current_tyre_es}, buena salida.",
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
                        f"Great move {self.driver_name}! Up into P{rep.position}, next target ahead is {rep.ahead_name}.",
                        f"Nice overtake! That puts us P{rep.position}. Keep your head down and build the gap.",
                    ])
                return random.choice([
                    f"¡Buena maniobra {self.driver_name}! Subes a la posición {rep.position}, tu siguiente objetivo es {rep.ahead_name}.",
                    f"¡Gran adelantamiento! Ya estás en posición {rep.position}, ahora abre hueco.",
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
                    ])
                return random.choice([
                    f"¡Última vuelta {self.driver_name}, entramos en la última vuelta! Vas posición {rep.position}, delante {rep.ahead_name} a {rep.ahead_gap_s:.1f}, detrás {rep.behind_name} a {rep.behind_gap_s:.1f}. ¡Vacía la batería!",
                    f"¡Bandera blanca {self.driver_name}, queda una sola vuelta! Estás en posición {rep.position}, gasta todo el ERS que te queda hasta la meta.",
                ])

            if rep.laps_remaining == 3 and rep.total_laps >= 5:
                self.last_callout_time = now
                if lang == "en":
                    return f"Three laps remaining, P{rep.position}. Tyres at {rep.max_wear_pct:.0f} percent, battery at {rep.ers_pct} percent. Push now."
                return f"Tres vueltas para el final, ruedas en posición {rep.position}. Gomas al {rep.max_wear_pct:.0f} por ciento y batería al {rep.ers_pct}. Tira fuerte."

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
                    else f"Vemos un toque en el alerón del {wing} por ciento en telemetría. Vigila el subviraje en curva rápida."
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
            return "Ojo con los límites de pista, llevas dos avisos, al siguiente nos sancionan con tres segundos."

        # 6. Entrada en zona de DRS delante o amenaza de DRS detras (con cooldown de 45s para no repetir cada vuelta)
        if 0.15 < rep.ahead_gap_s <= 0.95 and (now - self.last_drs_ahead_ts > 45.0) and rep.current_lap >= 2:
            self.last_drs_ahead_ts = now
            self.last_callout_time = now
            if lang == "en":
                return random.choice([
                    f"You are inside DRS range of {rep.ahead_name}, {rep.ahead_gap_s:.1f} seconds. Use Overtake on the straight!",
                    f"DRS available on {rep.ahead_name} ahead, gap is {rep.ahead_gap_s:.1f}. Attack when ready!",
                ])
            return random.choice([
                f"Tienes DRS con {rep.ahead_name} delante, a {rep.ahead_gap_s:.1f} segundos. ¡Atácale en la recta!",
                f"Ya estás a menos de un segundo de {rep.ahead_name}, DRS disponible, usa el botón de adelantamiento.",
            ])

        if 0.15 < rep.behind_gap_s <= 0.90 and (now - self.last_drs_behind_ts > 45.0) and rep.current_lap >= 2:
            self.last_drs_behind_ts = now
            self.last_callout_time = now
            if lang == "en":
                return random.choice([
                    f"Watch your mirrors, {rep.behind_name} has DRS behind you at {rep.behind_gap_s:.1f} seconds.",
                    f"Pressure from {rep.behind_name} behind at {rep.behind_gap_s:.1f} with DRS, defend the inside line.",
                ])
            return random.choice([
                f"Vigila los retrovisores, {rep.behind_name} tiene DRS detrás a {rep.behind_gap_s:.1f} segundos.",
                f"Tienes a {rep.behind_name} pegado a {rep.behind_gap_s:.1f} con DRS, cierra bien el interior en la frenada.",
            ])

        # 7. Lluvia inminente
        if not self.warned_rain and rep.rain_forecast_pct >= 60 and 0 < rep.rain_in_mins <= 10:
            self.warned_rain = True
            self.last_callout_time = now
            if lang == "en":
                return f"Weather radar shows {rep.rain_forecast_pct} percent chance of rain in {rep.rain_in_mins} minutes."
            return f"Atención al radar, sube al {rep.rain_forecast_pct} por ciento la probabilidad de lluvia en {rep.rain_in_mins} minutos."

        return None
