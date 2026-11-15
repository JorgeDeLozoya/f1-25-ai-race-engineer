"""Motor de estrategia de carrera en tiempo real y avisos proactivos (Spotter + Estratega)."""
from __future__ import annotations

from dataclasses import dataclass, field
import random
import re
import time

from .config import EngineerConfig
from .mfd import LIVE_OVERRIDES, auto_adjust_car_mfd
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
    plan_a_es: str = ""
    plan_a_en: str = ""
    plan_b_es: str = ""
    plan_b_en: str = ""
    plan_c_es: str = ""
    plan_c_en: str = ""
    s1_str: str = "29.410s"
    s2_str: str = "47.820s"
    s3_str: str = "29.590s"
    sector_comparison_es: str = (
        "En el Sector 1 le recortas una décima y media a Norris y en el Sector 3 le ganas dos décimas, pero estás perdiendo casi dos décimas en las curvas rápidas del Sector 2."
    )
    sector_comparison_en: str = (
        "You are gaining a tenth and a half on Norris in Sector 1 and two tenths in Sector 3, but losing nearly two tenths through the fast corners of Sector 2."
    )
    crossover_ready: bool = False
    crossover_summary_es: str = (
        "La pista sigue para neumático de seco; toda la parrilla rueda con slicks y aún no hemos llegado al punto de crossover para intermedios, aunque tenemos un 45% de probabilidad de lluvia en 15 minutos."
    )
    crossover_summary_en: str = (
        "Track is still fastest on dry slicks; the whole grid is on slicks and we haven't hit the Intermediate crossover point yet, though rain chance is 45% in 15 minutes."
    )
    grid_position: int = 6
    positions_gained: int = 2
    debrief_es: str = (
        "¡Bandera a cuadros, carrera terminada! Has cruzado meta en posición 4 tras salir P6 en parrilla, ganando 2 posiciones con una vuelta rápida personal de 1:46.210. ¡Carrerón impecable desde el muro!"
    )
    debrief_en: str = (
        "Chequered flag, race over! You brought it home P4 after starting P6 on the grid, gaining 2 positions with a personal best of 1:46.210. Mega job from the pit wall!"
    )
    diff_pct: int = 60
    front_wing_delta: int = 0
    ai_auto_action_es: str = "Muro IA en modo automático activo."
    ai_auto_action_en: str = "Pit wall AI auto-tuning active."
    full_briefing_es: str = ""
    full_briefing_en: str = ""


CIRCUIT_PROFILES: dict[str, dict[str, str]] = {
    "spa": {
        "fast_es": "Pouhon, Raidillon y Blanchimont",
        "fast_en": "Pouhon, Raidillon and Blanchimont",
        "brake_es": "la chicane Bus Stop y la horquilla de La Source",
        "brake_en": "the Bus Stop chicane and La Source hairpin",
        "harvest_es": "la frenada de Les Combes y Bruxelles",
        "harvest_en": "braking into Les Combes and Bruxelles",
        "straight_es": "la recta de Kemmel",
        "straight_en": "the Kemmel straight",
    },
    "silverstone": {
        "fast_es": "Maggotts, Becketts y Copse",
        "fast_en": "Maggotts, Becketts and Copse",
        "brake_es": "Vale, Club y Brooklands",
        "brake_en": "Vale, Club and Brooklands",
        "harvest_es": "Stowe y Village",
        "harvest_en": "Stowe and Village",
        "straight_es": "la recta de Hangar",
        "straight_en": "the Hangar straight",
    },
    "catalunya": {
        "fast_es": "la Curva 3 y la Curva 9 Campsa",
        "fast_en": "Turn 3 and Turn 9 Campsa",
        "brake_es": "la Curva 1 Elf y la Curva 10 La Caixa",
        "brake_en": "Turn 1 and Turn 10",
        "harvest_es": "la Curva 5 y la Curva 10",
        "harvest_en": "Turn 5 and Turn 10",
        "straight_es": "la recta principal de meta",
        "straight_en": "the main pit straight",
    },
    "monza": {
        "fast_es": "la Curva Grande, Ascari y la Parabólica",
        "fast_en": "Curva Grande, Ascari and Parabolica",
        "brake_es": "la Prima Variante y la Variante della Roggia",
        "brake_en": "Prima Variante and Variante della Roggia",
        "harvest_es": "las dos curvas de Lesmo y la primera chicane",
        "harvest_en": "both Lesmos and the first chicane",
        "straight_es": "la recta principal de Monza",
        "straight_en": "the Monza main straight",
    },
    "monaco": {
        "fast_es": "Massenet, Casino y la zona de la Piscina",
        "fast_en": "Massenet, Casino and the Swimming Pool section",
        "brake_es": "Sainte Dévote y la Nouvelle Chicane",
        "brake_en": "Sainte Devote and the Nouvelle Chicane",
        "harvest_es": "Mirabeau, Loews y Rascasse",
        "harvest_en": "Mirabeau, Loews and Rascasse",
        "straight_es": "la salida del túnel",
        "straight_en": "the tunnel exit",
    },
    "sakhir": {
        "fast_es": "las enlazadas de las curvas 5, 6 y 7",
        "fast_en": "the Turn 5-6-7 sweepers",
        "brake_es": "la Curva 1 y la delicada frenada en apoyo de la Curva 10",
        "brake_en": "Turn 1 and the tricky trail-braking zone at Turn 10",
        "harvest_es": "la horquilla de la Curva 8 y la Curva 14",
        "harvest_en": "Turn 8 hairpin and Turn 14",
        "straight_es": "la recta principal y la recta trasera hacia la curva 4",
        "straight_en": "the main straight and the run to Turn 4",
    },
    "suzuka": {
        "fast_es": "las Eses del primer sector, Degner y la 130R",
        "fast_en": "the Sector 1 Esses, Degner and 130R",
        "brake_es": "la Horquilla y la última Chicane del Triángulo",
        "brake_en": "the Hairpin and the Casio Triangle chicane",
        "harvest_es": "la curva Spoon y la Horquilla",
        "harvest_en": "Spoon Curve and the Hairpin",
        "straight_es": "la recta trasera antes de la 130R",
        "straight_en": "the back straight into 130R",
    },
    "interlagos": {
        "fast_es": "Curva do Sol y Ferradura",
        "fast_en": "Curva do Sol and Ferradura",
        "brake_es": "las Eses de Senna y Descida do Lago",
        "brake_en": "the Senna S and Descida do Lago",
        "harvest_es": "Junção y Bico de Pato",
        "harvest_en": "Juncao and Bico de Pato",
        "straight_es": "la subida de Reta Oposta",
        "straight_en": "the Reta Oposta climb",
    },
}


def get_circuit_profile(track_name: str) -> dict[str, str]:
    low = (track_name or "").lower()
    for key, prof in CIRCUIT_PROFILES.items():
        if key in low:
            return prof
    return {
        "fast_es": "las curvas rápidas del segundo sector",
        "fast_en": "the high-speed corners in Sector 2",
        "brake_es": "las frenadas fuertes de final de recta",
        "brake_en": "the heavy braking zones at the end of the straights",
        "harvest_es": "las horquillas lentas del circuito",
        "harvest_en": "the slow hairpins on the circuit",
        "straight_es": "la recta principal de DRS",
        "straight_en": "the main DRS straight",
    }


def diagnose_and_tune_car(
    issue: str, rep: StrategyReport, cfg: EngineerConfig, lang: str = "es"
) -> str:
    """Analiza circuito + neumatico + clima + temperaturas, aplica el cambio automatico en el MFD y responde."""
    prof = get_circuit_profile(rep.track_name)
    tuned = auto_adjust_car_mfd(issue, cfg, base_brake_bias=rep.brake_bias)
    new_bb = tuned.get("brake_bias", rep.brake_bias)
    new_diff = tuned.get("diff", LIVE_OVERRIDES.diff_pct)
    new_wing = tuned.get("wing", LIVE_OVERRIDES.front_wing_delta)
    wet_note_es = " con la pista delicada por la humedad" if "rain" in rep.weather_now or rep.rain_forecast_pct >= 50 else f" con el asfalto a {rep.track_temp} grados"
    wet_note_en = " on this damp surface" if "rain" in rep.weather_now or rep.rain_forecast_pct >= 50 else f" with track temp at {rep.track_temp} degrees"

    if issue == "understeer":
        if lang == "en":
            return (
                f"Copy on the understeer in {rep.track_name}. With your {rep.current_tyre}s at {rep.max_tyre_temp} degrees and {rep.max_wear_pct:.0f}% wear{wet_note_en}, "
                f"the front axle is washing out through {prof['fast_en']}. "
                f"I have automatically shifted your MFD brake bias rearward to {new_bb}%, opened the differential to {new_diff}% to help the car rotate, "
                f"and pre-set +{new_wing} click of front wing for our lap {rep.pit_window_ideal} pit stop."
            )
        return (
            f"Te copio con la falta de giro aquí en {rep.track_name}. Con el neumático {rep.current_tyre_es} a {rep.max_tyre_temp} grados y al {rep.max_wear_pct:.0f}% de desgaste{wet_note_es}, "
            f"te cuesta meter el morro en {prof['fast_es']}. "
            f"Ya te he bajado automáticamente desde el muro el reparto de frenada al {new_bb}% en el MFD, he abierto el diferencial al {new_diff}% para que rote mejor en el vértice, "
            f"y he dejado preparado +{new_wing} punto de alerón delantero para la parada de la vuelta {rep.pit_window_ideal}."
        )

    if issue == "oversteer":
        if lang == "en":
            return (
                f"Understood on the rear instability at {rep.track_name}. Your {rep.current_tyre} tyres are at {rep.max_tyre_temp} degrees{wet_note_en}. "
                f"I just moved your MFD brake bias forward to {new_bb}% and opened the on-throttle differential to {new_diff}% to calm the rear down exiting {prof['harvest_en']}. "
                f"Short-shift from 2nd to 3rd gear on exit!"
            )
        return (
            f"Recibido con el sobreviraje en {rep.track_name}. Tus gomas {rep.current_tyre_es}s van a {rep.max_tyre_temp} grados{wet_note_es}. "
            f"Te acabo de subir automáticamente el reparto de frenada al {new_bb}% delante y he bajado el diferencial en aceleración al {new_diff}% en el MFD para sujetar la trasera al salir de {prof['harvest_es']}. "
            f"Mete tercera un poco antes al traccionar."
        )

    if issue == "poor_braking":
        if lang == "en":
            return (
                f"Copy on the braking feel at {rep.track_name}. Brake discs are at {rep.max_brake_temp} degrees on {rep.tyre_age}-lap old {rep.current_tyre}s. "
                f"I have automatically adjusted your MFD brake bias to {new_bb}% and increased engine braking differential to {new_diff}% so the car stops much shorter into {prof['brake_en']}. "
                f"Brake five metres earlier in straight-line threshold before turning in."
            )
        return (
            f"Te copio con los frenos aquí en {rep.track_name}. Llevas los discos a {rep.max_brake_temp} grados con goma {rep.current_tyre_es} de {rep.tyre_age} vueltas. "
            f"Te he reajustado automáticamente el reparto de frenada al {new_bb}% y la retención del diferencial al {new_diff}% en el MFD para darte más mordiente en {prof['brake_es']}. "
            f"Frena fuerte en línea recta y suelta pedal progresivo al girar."
        )

    if issue == "more_power":
        if lang == "en":
            return (
                f"Copy, giving you full power now! I have switched your MFD ERS deployment to Overtake mode with {rep.ers_pct}% battery left. "
                f"Use it all down {prof['straight_en']} to attack {rep.ahead_name}, and harvest on braking into {prof['harvest_en']}."
            )
        return (
            f"¡Recibido, te doy toda la potencia ahora mismo! Ya te he activado automáticamente el mapa de Adelantamiento en el MFD con tu {rep.ers_pct}% de batería. "
            f"Despliégalo a fondo en {prof['straight_es']} para tirarle el coche a {rep.ahead_name}, y recarga luego frenando en {prof['harvest_es']}."
        )

    if issue == "save_battery":
        if lang == "en":
            return (
                f"Copy, switching your MFD ERS mode to Harvest now. Do 20 metres of lift and coast before braking into {prof['brake_en']} and {prof['harvest_en']} and we will recover 15% battery per lap."
            )
        return (
            f"Copiado, te acabo de bajar automáticamente el mapa de ERS a modo Recarga en el MFD. Levanta el pie veinte metros antes de frenar en {prof['brake_es']} y {prof['harvest_es']} y recuperaremos un 15% de batería por vuelta."
        )

    return rep.setup_advice_en if lang == "en" else rep.setup_advice_es


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


def analyze_rival_pit_and_status(row: dict, rep: StrategyReport, lang: str = "es") -> dict[str, str]:
    """Calcula cuando ha parado un piloto rival, cuando creemos que parara y su estado completo."""
    rname = row.get("name", "Rival")
    rteam = row.get("team", "su escudería")
    rpos = int(row.get("pos", 1))
    rgap_ldr = row.get("gap_leader", "+0.0s")
    rlast = row.get("last_lap", "--")
    rtyre_lbl = row.get("tyre", "Medium (5L)")
    comp, age = _parse_tyre_label(rtyre_lbl)
    comp_es = L.COMPOUNDS_ES.get(comp, comp.lower())
    pits = int(row.get("pits", 0))

    # Si en modo demo no viene 'pits', deducirlo por la edad de la goma frente a la vuelta actual
    if pits == 0 and rep.current_lap > age + 1:
        pits = 1

    pit_lap = max(1, rep.current_lap - age)
    stint_max_map = {
        "Super Soft": 12,
        "Soft": 15,
        "Medium": 23,
        "Hard": 33,
        "Intermediate": 24,
        "Wet": 28,
    }
    typical_life = stint_max_map.get(comp, 20)
    laps_left_on_rival_tyre = max(1, typical_life - age)
    pred_stop_start = max(rep.current_lap + 1, rep.current_lap + laps_left_on_rival_tyre - 1)
    pred_stop_end = pred_stop_start + 2

    if lang == "en":
        if pits > 0:
            pit_hist = (
                f"{rname} has made {pits} pit stop{'s' if pits > 1 else ''} so far. "
                f"He boxed on lap {pit_lap} to fit the {comp} tyre, which now has {age} laps on it."
            )
        else:
            pit_hist = (
                f"{rname} has not pitted yet, zero stops. He is still on his starting {comp} set with {age} laps of wear."
            )

        if rep.laps_remaining <= 3 or pred_stop_start >= rep.total_laps:
            pit_pred = (
                f"We don't expect {rname} to box again; with {rep.laps_remaining} laps remaining, his {age}-lap old {comp}s will make it to the chequered flag."
            )
        else:
            pit_pred = (
                f"Based on tyre degradation, we estimate {rname} will pit between lap {pred_stop_start} and {min(rep.total_laps - 1, pred_stop_end)}, "
                f"in about {laps_left_on_rival_tyre} laps, since his {comp}s are already {age} laps old."
            )

        full = f"{rname} in the {rteam} is P{rpos} at {rgap_ldr} from the leader, last lap {rlast}. {pit_hist} {pit_pred}"
        return {"history": pit_hist, "prediction": pit_pred, "full": full}

    if pits > 0:
        pit_hist = (
            f"{rname} lleva {pits} {'parada' if pits == 1 else 'paradas'} en boxes. "
            f"Hizo su parada en la vuelta {pit_lap} para montar el neumático {comp_es}, con el que ya lleva {age} vueltas."
        )
    else:
        pit_hist = (
            f"{rname} todavía no ha parado en boxes, lleva cero paradas y sigue con el juego de goma {comp_es} de salida de {age} vueltas."
        )

    if rep.laps_remaining <= 3 or pred_stop_start >= rep.total_laps:
        pit_pred = (
            f"En el muro no creemos que {rname} vuelva a parar; quedan {rep.laps_remaining} vueltas y su goma {comp_es} de {age} giros llega hasta la bandera a cuadros."
        )
    else:
        pit_pred = (
            f"Calculamos que {rname} parará en boxes entre la vuelta {pred_stop_start} y la {min(rep.total_laps - 1, pred_stop_end)}, "
            f"dentro de unas {laps_left_on_rival_tyre} vueltas, porque su neumático {comp_es} ya acumula {age} giros."
        )

    full = f"{rname} va en la posición {rpos} con el {rteam} a {rgap_ldr} de cabeza, última vuelta {rlast}. {pit_hist} {pit_pred}"
    return {"history": pit_hist, "prediction": pit_pred, "full": full}


def compare_car_sectors(me_row: dict | None, rival_row: dict | None, rep: StrategyReport, lang: str = "es") -> str:
    """Compara los parciales S1, S2 y S3 del jugador contra un rival concreto."""
    if not me_row or not rival_row:
        return rep.sector_comparison_en if lang == "en" else rep.sector_comparison_es

    rname = rival_row.get("name", rep.ahead_name)
    ms1, ms2, ms3 = int(me_row.get("s1_ms", 0)), int(me_row.get("s2_ms", 0)), int(me_row.get("s3_ms", 0))
    rs1, rs2, rs3 = int(rival_row.get("s1_ms", 0)), int(rival_row.get("s2_ms", 0)), int(rival_row.get("s3_ms", 0))

    # Si no hay desglose S1/S2/S3 pero si last_lap_ms, repartir proporcionalmente (28%, 44%, 28%)
    mlap = int(me_row.get("last_lap_ms", 0))
    rlap = int(rival_row.get("last_lap_ms", 0))
    if (ms1 <= 0 or ms2 <= 0) and mlap > 0:
        ms1, ms2, ms3 = int(mlap * 0.28), int(mlap * 0.44), int(mlap * 0.28)
    if (rs1 <= 0 or rs2 <= 0) and rlap > 0:
        rs1, rs2, rs3 = int(rlap * 0.28), int(rlap * 0.44), int(rlap * 0.28)

    if ms1 <= 0 or rs1 <= 0:
        return rep.sector_comparison_en if lang == "en" else rep.sector_comparison_es

    d1 = (ms1 - rs1) / 1000.0  # positivo = pierdes tiempo frente al rival
    d2 = (ms2 - rs2) / 1000.0
    d3 = (ms3 - rs3) / 1000.0 if (ms3 > 0 and rs3 > 0) else 0.0
    deltas = [(1, d1), (2, d2), (3, d3)]
    worst_sec, worst_val = max(deltas, key=lambda x: x[1])
    best_sec, best_val = min(deltas, key=lambda x: x[1])

    if lang == "en":
        if worst_val > 0.05 and best_val < -0.05:
            return (
                f"Against {rname}, you are losing {worst_val:.2f} seconds in Sector {worst_sec}, "
                f"but gaining {abs(best_val):.2f} seconds in Sector {best_sec}. "
                f"Your splits were S1 {fmt_ms(ms1)}, S2 {fmt_ms(ms2)}, S3 {fmt_ms(ms3)}."
            )
        if worst_val > 0.05:
            return (
                f"You are losing the most time to {rname} in Sector {worst_sec}, dropping {worst_val:.2f} seconds there. "
                f"Focus on your exits in Sector {worst_sec}."
            )
        return (
            f"You are faster than {rname} across the lap, especially in Sector {best_sec} where you gain {abs(best_val):.2f} seconds."
        )

    if worst_val > 0.05 and best_val < -0.05:
        return (
            f"Comparando telemetría con {rname}, pierdes {worst_val:.2f} segundos en el Sector {worst_sec}, "
            f"pero le recortas {abs(best_val):.2f} segundos en el Sector {best_sec}. "
            f"Tus parciales: S1 {fmt_ms(ms1)}, S2 {fmt_ms(ms2)} y S3 {fmt_ms(ms3)}."
        )
    if worst_val > 0.05:
        return (
            f"Donde más tiempo nos dejamos frente a {rname} es en el Sector {worst_sec}, perdiendo {worst_val:.2f} segundos. "
            f"Afina la tracción en las curvas del Sector {worst_sec}."
        )
    return (
        f"Estás rodando más rápido que {rname} en todos los parciales, sobre todo en el Sector {best_sec} donde le metes {abs(best_val):.2f} segundos."
    )


def analyze_strategy(state: RaceState, driver_label: str = "Jorge") -> StrategyReport:
    """Calcula toda la situacion tactica, ritmo relativo, reglajes y posibles estrategias."""
    ov = LIVE_OVERRIDES
    if not state.connected or not state.laps:
        demo_pit_ideal = ov.pit_lap_override if ov.pit_lap_override > 0 else 10
        demo_pit_latest = ov.pit_lap_override if ov.pit_lap_override > 0 else 13
        demo_comp = ov.compound_override if ov.compound_override else "Soft"
        demo_comp_es = ov.compound_override_es if ov.compound_override_es else "blando"
        demo_bb = max(50, min(65, 56 + ov.brake_bias_delta))
        demo_ers = ov.ers_mode_override if ov.ers_mode_override else "medium"
        demo_ers_es = ov.ers_mode_override_es if ov.ers_mode_override_es else "medio"
        demo_box_rec = f"PLAN {ov.active_plan} (Vuelta {demo_pit_ideal} -> {demo_comp})" if ov.pit_lap_override > 0 else "STAY OUT"
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
            brake_bias=demo_bb,
            penalties_s=0,
            warnings_count=1,
            box_recommendation=demo_box_rec,
            recommended_compound=demo_comp,
            recommended_compound_es=demo_comp_es,
            pit_window_ideal=demo_pit_ideal,
            pit_window_latest=demo_pit_latest,
            predicted_rejoin_pos=8,
            rejoin_summary_es=f"Si paras en la vuelta {demo_pit_ideal} (Plan {ov.active_plan}) montarás neumático {demo_comp_es} y saldrás en octava posición detrás de Alonso.",
            rejoin_summary_en=f"If we box on lap {demo_pit_ideal} (Plan {ov.active_plan}) we fit {demo_comp} tyres and rejoin P8 behind Alonso.",
            undercut_summary_es="Tienes a Norris delante a 1 con 4 segundos con medios de 9 vueltas, empujando con ERS entras en su DRS en la próxima vuelta.",
            undercut_summary_en="Norris is 1 point 4 ahead on 9 lap old mediums, push with ERS to get into his DRS next lap.",
            fuel_kg=9.2,
            fuel_laps_margin=1.25,
            fuel_advice_es="Combustible en positivo, más 1 con 2 vueltas de margen.",
            fuel_advice_en="Fuel is comfortable, plus 1 point 2 laps margin.",
            ers_pct=70,
            ers_mode=demo_ers,
            ers_mode_es=demo_ers_es,
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
            setup_advice_es=f"Reparto de frenada al {demo_bb}% y diferencial al {ov.diff_pct}% en Spa. " + (ov.last_ai_action_es or "Si notas subviraje en Pouhon, atrasa un punto la frenada."),
            setup_advice_en=f"Brake bias at {demo_bb}% and differential at {ov.diff_pct}% at Spa. " + (ov.last_ai_action_en or "If you feel understeer in Pouhon, move brake bias rearward."),
            teammate_name="Alonso",
            teammate_pos=8,
            teammate_gap="+16.4s",
            podium_gap_s=1.4,
            points_gap_s=0.0,
            retired_names=[],
            plan_a_es="Plan A es quedarnos fuera hasta el final cuidando este medio al 33% y atacar a Norris con DRS en las últimas 3 vueltas.",
            plan_a_en="Plan A is staying out to the flag managing these 33% Mediums and attacking Norris with DRS in the final 3 laps.",
            plan_b_es="Plan B es ataque total y undercut en la vuelta 15: montar neumático blando y activar modo adelantamiento en ERS para pasar a Norris.",
            plan_b_en="Plan B is full attack and undercut on lap 15: fit Soft tyres and deploy Overtake ERS to jump Norris.",
            plan_c_es="Plan C es alargar el stint al máximo hasta la vuelta 17 haciendo lift and coast, esperando ese 45% de lluvia o un Safety Car para montar intermedios o duros.",
            plan_c_en="Plan C is extending the stint to lap 17 with lift and coast, waiting on that 45% rain chance or a Safety Car for Inters or Hards.",
            diff_pct=ov.diff_pct,
            front_wing_delta=ov.front_wing_delta,
            ai_auto_action_es=ov.last_ai_action_es,
            ai_auto_action_en=ov.last_ai_action_en,
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

    if ov.brake_bias_delta != 0:
        brake_bias = max(50, min(65, brake_bias + ov.brake_bias_delta))
    if ov.ers_mode_override:
        ers_mode = ov.ers_mode_override

    comp_es = L.COMPOUNDS_ES.get(comp_name, comp_name.lower())
    ers_mode_es = ov.ers_mode_override_es if ov.ers_mode_override_es else L.ERS_MODE_ES.get(ers_mode, ers_mode)

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
    if ov.pit_lap_override > 0:
        ideal_lap = ov.pit_lap_override
        latest_lap = min(total_laps, ov.pit_lap_override + 1)

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

    if ov.compound_override:
        rec_comp = ov.compound_override
    elif s and s.weather in (3, 4, 5) or (rain_pct >= 65 and rain_mins <= 5):
        rec_comp = "Intermediate"
    elif laps_rem <= 11:
        rec_comp = "Soft"
    elif laps_rem <= 23:
        rec_comp = "Medium"
    else:
        rec_comp = "Hard"
    rec_comp_es = ov.compound_override_es if ov.compound_override_es else L.COMPOUNDS_ES.get(rec_comp, rec_comp.lower())

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
    elif ov.pit_lap_override > 0:
        box_rec = f"PLAN {ov.active_plan} (Vuelta {ideal_lap} -> {rec_comp})"
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

    # Planes tacticos A, B y C dinamicos segun estado real de carrera
    if laps_rem <= 6 and max_wear < 62.0:
        plan_a_es = (
            f"Plan A es ir hasta el final sin parar con este {comp_es} al {max_wear:.0f}%, gestionando tracción para defender el P{pos}."
        )
        plan_a_en = (
            f"Plan A is going to the end without stopping on these {max_wear:.0f}% {comp_name}s, managing traction to hold P{pos}."
        )
        plan_b_es = (
            f"Plan B es ataque total al sprint: vaciar el {ers_pct}% de batería con modo Overtake para cazar a {ahead_row['name'] if ahead_row else 'la cabeza'} en las {laps_rem} vueltas que quedan."
        )
        plan_b_en = (
            f"Plan B is full sprint attack: deploy your {ers_pct}% battery in Overtake mode to hunt down {ahead_row['name'] if ahead_row else 'the leader'} over the final {laps_rem} laps."
        )
    else:
        plan_a_es = (
            f"Plan A es nuestra estrategia óptima: parar entre la vuelta {ideal_lap} y la {latest_lap} para montar {rec_comp_es} y salir en torno a P{rejoin_pos}."
        )
        plan_a_en = (
            f"Plan A is our baseline strategy: box between lap {ideal_lap} and {latest_lap} for {rec_comp} tyres, rejoining around P{rejoin_pos}."
        )
        undercut_lap = max(cur_lap, ideal_lap - 2)
        plan_b_es = (
            f"Plan B es el undercut agresivo: adelantar la parada a la vuelta {undercut_lap} para montar goma blanda o {rec_comp_es} y atacar con aire limpio a {ahead_row['name'] if ahead_row else 'los de delante'}."
        )
        plan_b_en = (
            f"Plan B is the aggressive undercut: box early on lap {undercut_lap} for fresh rubber and use clean air to jump {ahead_row['name'] if ahead_row else 'the cars ahead'}."
        )

    plan_c_es = (
        f"Plan C es alargar el stint al máximo cuidando las gomas ({est_tyre_laps_left} vueltas de vida), buscando un overcut o esperando un Safety Car"
        + (f" o ese {rain_pct}% de lluvia prevista." if rain_pct >= 20 else " para tener parada gratis.")
    )
    plan_c_en = (
        f"Plan C is extending this stint to the limit ({est_tyre_laps_left} laps of tyre life), going for an overcut or waiting on a Safety Car"
        + (f" or that {rain_pct}% rain chance." if rain_pct >= 20 else " for a cheap pit stop.")
    )

    # 1. Comparativa de parciales S1, S2 y S3 contra el coche de delante (o P2 si eres lider)
    ref_sector_row = ahead_row or behind_row
    ms1 = int(me_row.get("s1_ms", 0)) if me_row else 0
    ms2 = int(me_row.get("s2_ms", 0)) if me_row else 0
    ms3 = int(me_row.get("s3_ms", 0)) if me_row else 0
    if (ms1 <= 0 or ms2 <= 0) and my_last_ms > 0:
        ms1, ms2, ms3 = int(my_last_ms * 0.28), int(my_last_ms * 0.44), int(my_last_ms * 0.28)
    s1_str = fmt_ms(ms1) if ms1 > 0 else "--"
    s2_str = fmt_ms(ms2) if ms2 > 0 else "--"
    s3_str = fmt_ms(ms3) if ms3 > 0 else "--"

    # Construir comparativa de sectores
    if ref_sector_row and ms1 > 0:
        rs1 = int(ref_sector_row.get("s1_ms", 0))
        rs2 = int(ref_sector_row.get("s2_ms", 0))
        rs3 = int(ref_sector_row.get("s3_ms", 0))
        rlap = int(ref_sector_row.get("last_lap_ms", 0))
        if (rs1 <= 0 or rs2 <= 0) and rlap > 0:
            rs1, rs2, rs3 = int(rlap * 0.28), int(rlap * 0.44), int(rlap * 0.28)
        if rs1 > 0:
            d1, d2, d3 = (ms1 - rs1) / 1000.0, (ms2 - rs2) / 1000.0, (ms3 - rs3) / 1000.0
            worst_sec, worst_v = max([(1, d1), (2, d2), (3, d3)], key=lambda x: x[1])
            best_sec, best_v = min([(1, d1), (2, d2), (3, d3)], key=lambda x: x[1])
            rname = ref_sector_row["name"]
            if worst_v > 0.04:
                sec_comp_es = (
                    f"Frente a {rname}, donde más tiempo pierdes es en el Sector {worst_sec} ({worst_v:+.2f}s), "
                    + (f"aunque le recortas {abs(best_v):.2f}s en el Sector {best_sec}. " if best_v < -0.04 else "")
                    + f"Tus parciales: S1 {s1_str}, S2 {s2_str}, S3 {s3_str}."
                )
                sec_comp_en = (
                    f"Against {rname}, you are losing the most time in Sector {worst_sec} ({worst_v:+.2f}s), "
                    + (f"while gaining {abs(best_v):.2f}s in Sector {best_sec}. " if best_v < -0.04 else "")
                    + f"Your splits: S1 {s1_str}, S2 {s2_str}, S3 {s3_str}."
                )
            else:
                sec_comp_es = f"Eres más rápido que {rname} en todos los sectores, sobre todo en el Sector {best_sec} ({best_v:+.2f}s). Parciales: S1 {s1_str}, S2 {s2_str}, S3 {s3_str}."
                sec_comp_en = f"You are faster than {rname} in every sector, especially Sector {best_sec} ({best_v:+.2f}s). Splits: S1 {s1_str}, S2 {s2_str}, S3 {s3_str}."
        else:
            sec_comp_es = f"Tus parciales de la última vuelta: Sector 1 en {s1_str}, Sector 2 en {s2_str} y Sector 3 en {s3_str}."
            sec_comp_en = f"Your last lap sector splits: Sector 1 {s1_str}, Sector 2 {s2_str}, Sector 3 {s3_str}."
    else:
        sec_comp_es = f"Tus parciales actuales son S1 {s1_str}, S2 {s2_str} y S3 {s3_str}."
        sec_comp_en = f"Your current sector splits are S1 {s1_str}, S2 {s2_str}, S3 {s3_str}."

    # 2. Detector de Crossover de Lluvia (Slicks vs Intermedios/Lluvia en la parrilla)
    wet_cars = [r for r in standings if any(w in r["tyre"] for w in ("Inter", "Wet"))]
    dry_cars = [r for r in standings if not any(w in r["tyre"] for w in ("Inter", "Wet"))]
    is_player_wet = comp_name in ("Intermediate", "Wet")
    crossover_ready = False
    if wet_cars and dry_cars:
        wet_times = [r["last_lap_ms"] for r in wet_cars if r.get("last_lap_ms", 0) > 40000]
        dry_times = [r["last_lap_ms"] for r in dry_cars if r.get("last_lap_ms", 0) > 40000]
        avg_wet = sum(wet_times) / len(wet_times) if wet_times else 0
        avg_dry = sum(dry_times) / len(dry_times) if dry_times else 0
        fast_wet_drv = wet_cars[0]["name"]
        fast_dry_drv = dry_cars[0]["name"]
        if not is_player_wet and avg_wet > 0 and avg_dry > 0 and avg_wet < avg_dry - 600:
            crossover_ready = True
            diff_s = (avg_dry - avg_wet) / 1000.0
            cross_es = f"¡Atención al crossover de lluvia! {fast_wet_drv} ya lleva Intermedios y rueda {diff_s:.1f} segundos por vuelta más rápido que los slicks. ¡Box esta vuelta para Intermedios!"
            cross_en = f"Wet crossover alert! {fast_wet_drv} is on Intermediates and lapping {diff_s:.1f} seconds faster than the slicks. Box this lap for Inters!"
        elif is_player_wet and avg_wet > 0 and avg_dry > 0 and avg_dry < avg_wet - 600:
            crossover_ready = True
            diff_s = (avg_wet - avg_dry) / 1000.0
            cross_es = f"¡Se ha secado el carril! {fast_dry_drv} con neumático de seco viene {diff_s:.1f} segundos más rápido que los intermedios. ¡Entra a boxes para montar {rec_comp_es}!"
            cross_en = f"Dry line is ready! {fast_dry_drv} on slicks is {diff_s:.1f} seconds faster than Intermediates. Box now for {rec_comp}s!"
        else:
            cross_es = f"Hay {len(wet_cars)} coches con neumático de agua ({fast_wet_drv}) y {len(dry_cars)} con seco. Los tiempos están parejos en la transición, mantén tu compuesto una vuelta más."
            cross_en = f"There are {len(wet_cars)} cars on wets ({fast_wet_drv}) and {len(dry_cars)} on slicks. Lap times are right on the crossover cusp, hold your compound one more lap."
    elif "rain" in weather_now and not is_player_wet:
        crossover_ready = True
        cross_es = f"Está lloviendo sobre el circuito ({weather_now_es}) y sigues con goma {comp_es} de seco. Hemos cruzado el límite de adherencia, ¡entra a boxes a por Intermedios!"
        cross_en = f"It is raining on track ({weather_now}) and you are still on dry {comp_name}s. Grip is dropping fast, box for Intermediates!"
    else:
        cross_es = (
            f"La pista está para neumático de seco ({weather_now_es}, {track_temp}°C en asfalto); toda la parrilla rueda con slicks"
            + (f" y tenemos un {rain_pct}% de lluvia en {rain_mins} minutos." if rain_pct > 0 else " sin lluvia en el radar.")
        )
        cross_en = (
            f"Track is fastest on dry slicks ({weather_now}, {track_temp}°C track temp); the whole grid is on slicks"
            + (f" with a {rain_pct}% rain chance in {rain_mins} minutes." if rain_pct > 0 else " with zero rain on radar.")
        )

    # 3. Resumen / Debriefing de Carrera (Salida vs Posicion actual, mejor vuelta, paradas)
    grid_pos = int(me_row.get("grid_pos", pos)) if me_row else pos
    gained = grid_pos - pos
    pits_done = int(me_row.get("pits", 0)) if me_row else 0
    if gained > 0:
        gain_es = f"remontando {gained} {'posición' if gained == 1 else 'posiciones'} desde el P{grid_pos} de parrilla"
        gain_en = f"gaining {gained} {'place' if gained == 1 else 'places'} from P{grid_pos} on the grid"
    elif gained < 0:
        gain_es = f"cediendo {abs(gained)} {'posición' if abs(gained) == 1 else 'posiciones'} respecto al P{grid_pos} de salida"
        gain_en = f"dropping {abs(gained)} {'place' if abs(gained) == 1 else 'places'} from your P{grid_pos} start"
    else:
        gain_es = f"manteniendo el P{grid_pos} de salida"
        gain_en = f"holding your P{grid_pos} starting spot"

    debrief_es = (
        f"Resumen desde el muro en {track_name}: posición {pos} de {len(standings)} con el {player_team}, {gain_es}. "
        f"Mejor vuelta personal en {best_lap_str}, {pits_done} {'parada' if pits_done == 1 else 'paradas'} en boxes y neumáticos al {max_wear:.0f}%."
    )
    debrief_en = (
        f"Pit wall debrief at {track_name}: P{pos} of {len(standings)} in the {player_team}, {gain_en}. "
        f"Personal best lap {best_lap_str}, {pits_done} pit {'stop' if pits_done == 1 else 'stops'} and tyres at {max_wear:.0f}% wear."
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
        plan_a_es=plan_a_es,
        plan_a_en=plan_a_en,
        plan_b_es=plan_b_es,
        plan_b_en=plan_b_en,
        plan_c_es=plan_c_es,
        plan_c_en=plan_c_en,
        s1_str=s1_str,
        s2_str=s2_str,
        s3_str=s3_str,
        sector_comparison_es=sec_comp_es,
        sector_comparison_en=sec_comp_en,
        crossover_ready=crossover_ready,
        crossover_summary_es=cross_es,
        crossover_summary_en=cross_en,
        grid_position=grid_pos,
        positions_gained=gained,
        debrief_es=debrief_es,
        debrief_en=debrief_en,
        diff_pct=ov.diff_pct,
        front_wing_delta=ov.front_wing_delta,
        ai_auto_action_es=ov.last_ai_action_es,
        ai_auto_action_en=ov.last_ai_action_en,
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
        self.box_ordered: bool = False
        self.box_ordered_lap: int = 0
        self.ignored_box_laps: int = 0
        self.last_pits: int = 0
        self.last_sc_status: int = 0
        self.warned_crossover: bool = False
        self.warned_finish: bool = False

    def reset(self, session_uid: int) -> None:
        self.last_session_uid = session_uid
        LIVE_OVERRIDES.reset()
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
        self.box_ordered = False
        self.box_ordered_lap = 0
        self.ignored_box_laps = 0
        self.last_pits = 0
        self.last_sc_status = 0
        self.warned_crossover = False
        self.warned_finish = False

    def order_box_now(self, current_lap: int) -> None:
        """Registra que el muro ha ordenado parar en boxes en esta vuelta para vigilar si el piloto hace caso."""
        self.box_ordered = True
        self.box_ordered_lap = max(1, current_lap)

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
                    f"Radio check {self.driver_name}, live telemetry locked in from {rep.track_name}. You are P{rep.position} in the {rep.player_team} on {rep.current_tyre}s. Watch the cold brakes into Turn 1!",
                    f"Loud and clear from the pit wall at {rep.track_name}. Starting P{rep.position} on the {rep.current_tyre} compound. Clean launch and stay out of trouble in Turn 1!",
                    f"Pit wall online at {rep.track_name}, {self.driver_name}. You are P{rep.position}, Plan A is active. Keep the inside covered at the start!",
                ])
            return random.choice([
                f"Radio conectada {self.driver_name}, telemetría en vivo desde {rep.track_name}. Sales en posición {rep.position} con el {rep.player_team} y goma {rep.current_tyre_es}. ¡Cuidado con los frenos fríos en la curva 1!",
                f"Te copio alto y claro en el muro de {rep.track_name}, {self.driver_name}. Posición {rep.position} con neumático {rep.current_tyre_es}, Plan A activo. ¡Salida limpia!",
                f"Telemetría enganchada en {rep.track_name}. Estás en el puesto {rep.position} al volante del {rep.player_team}, vigila el embudo de la primera curva.",
            ])

        pidx = state.player_idx
        pl_lap = state.laps[pidx] if 0 <= pidx < len(state.laps) else None

        # A. Bandera a cuadros / Final de carrera -> Debriefing completo por radio
        if pl_lap and pl_lap.result_status == 3 and not self.warned_finish:
            self.warned_finish = True
            self.last_callout_time = now
            if lang == "en":
                return f"Chequered flag {self.driver_name}, that is the end of the race! {rep.debrief_en}"
            return f"¡Bandera a cuadros {self.driver_name}, final de carrera! {rep.debrief_es}"

        # B. Resalida de Safety Car / Virtual Safety Car (Bandera Verde en pista)
        cur_sc = state.session.safety_car if state.session else 0
        if self.last_sc_status in (1, 2) and cur_sc == 0:
            self.last_sc_status = 0
            self.last_callout_time = now
            if lang == "en":
                return (
                    f"Green flag, green flag {self.driver_name}! Race is live again, overtake mode ready! "
                    f"{rep.ahead_name} is {rep.ahead_gap_s:.1f} ahead on {rep.ahead_tyre}, {rep.behind_name} is {rep.behind_gap_s:.1f} behind."
                )
            return (
                f"¡Bandera verde, bandera verde {self.driver_name}! Se relanza la carrera, ¡modo adelantamiento listo! "
                f"Tienes a {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} con {rep.ahead_tyre}, y detrás viene {rep.behind_name} a {rep.behind_gap_s:.1f}."
            )
        self.last_sc_status = cur_sc

        # C. Crossover de lluvia / pista secándose detectado en tiempos de rivales
        if rep.crossover_ready and not self.warned_crossover:
            self.warned_crossover = True
            self.last_callout_time = now
            self.order_box_now(rep.current_lap)
            return rep.crossover_summary_en if lang == "en" else rep.crossover_summary_es

        # Si el piloto entra al pit lane cuando tenia orden de parar
        if pl_lap and (pl_lap.pit_status in (1, 2) or pl_lap.num_pit_stops > self.last_pits):
            was_ignored = self.ignored_box_laps
            self.last_pits = pl_lap.num_pit_stops
            if self.box_ordered:
                self.box_ordered = False
                self.ignored_box_laps = 0
                if was_ignored >= 1:
                    self.last_callout_time = now
                    if lang == "en":
                        return f"Finally in the pit lane {self.driver_name}! Pit limiter on, the crew is ready for you."
                    return f"¡Aleluya {self.driver_name}, por fin entras a boxes! Ya nos tenías cardíacos en el muro, clava las marcas de los mecánicos."

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

        # 1. Cambio de vuelta: Comprobar si ha ignorado la orden de BOX, Ultima vuelta, Quedan 3 vueltas, Ventana abierta
        if rep.current_lap != self.last_lap and rep.current_lap > 1:
            self.last_lap = rep.current_lap

            # ¿Tenia orden de entrar a boxes y se ha saltado la entrada al pit lane?
            if self.box_ordered and rep.current_lap > self.box_ordered_lap and rep.laps_remaining >= 1:
                if not pl_lap or pl_lap.pit_status == 0:
                    self.ignored_box_laps += 1
                    self.last_callout_time = now
                    if self.ignored_box_laps == 1:
                        if lang == "en":
                            return f"Hey {self.driver_name}, you just drove right past the pit entry! The crew was standing by with the tyres. You need to box THIS lap, copy!"
                        return f"¡Oye {self.driver_name}, te acabas de saltar la entrada a boxes! Teníamos a los mecánicos fuera con las pistolas listas. ¡Entra en ESTA vuelta sin excusas, box box!"
                    if self.ignored_box_laps == 2:
                        if lang == "en":
                            return f"That is TWO laps in a row you have ignored the pit call {self.driver_name}! What are you doing out there? Tyres are at {rep.max_wear_pct:.0f} percent, BOX THIS LAP!"
                        return f"¡Segunda vuelta seguida que pasas olímpicamente de mi orden de parar, {self.driver_name}! ¿Se puede saber a qué juegas? Llevas las gomas al {rep.max_wear_pct:.0f} por ciento, ¡entra a boxes YA!"
                    if lang == "en":
                        return f"Unbelievable {self.driver_name}, three laps ignoring the pit wall! If that {rep.worst_wheel_en} tyre blows up on the straight it is on you! Get in the pit lane NOW!"
                    return f"¡Increíble {self.driver_name}, tres vueltas ignorando al muro de boxes! Los mecánicos están que trinan contigo; como revientes la rueda {rep.worst_wheel_es} en la recta será responsabilidad tuya. ¡A boxes de una vez!"

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
                    self.order_box_now(rep.current_lap)
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
            self.order_box_now(rep.current_lap)
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
