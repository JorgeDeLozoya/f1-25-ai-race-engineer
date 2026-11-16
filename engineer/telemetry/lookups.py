"""Tablas de traduccion de IDs del juego a texto (Ingles y Espanol)."""
from __future__ import annotations

TRACKS = {
    0: "Melbourne",
    1: "Paul Ricard",
    2: "Shanghai",
    3: "Sakhir (Bahréin)",
    4: "Catalunya",
    5: "Mónaco",
    6: "Montreal",
    7: "Silverstone",
    8: "Hockenheim",
    9: "Hungaroring",
    10: "Spa-Francorchamps",
    11: "Monza",
    12: "Singapur",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Austin",
    16: "Interlagos",
    17: "Red Bull Ring",
    18: "Sochi",
    19: "México",
    20: "Bakú",
    21: "Sakhir Corto",
    22: "Silverstone Corto",
    23: "Austin Corto",
    24: "Suzuka Corto",
    25: "Hanoi",
    26: "Zandvoort",
    27: "Imola",
    28: "Portimão",
    29: "Jeddah",
    30: "Miami",
    31: "Las Vegas",
    32: "Qatar (Losail)",
    39: "Silverstone Inverso",
    40: "Red Bull Ring Inverso",
    41: "Zandvoort Inverso",
}

# Longitudes aproximadas en metros para identificar circuitos (incluidos mods clasicos en Swofty
# cuando track_id == -1 y el paquete 200 aun no ha llegado)
TRACK_LENGTH_MAP = [
    (3337, "Mónaco"),
    (4259, "Zandvoort"),
    (4309, "Interlagos"),
    (4318, "Red Bull Ring"),
    (4361, "Montreal"),
    (4381, "Hungaroring"),
    (4411, "Magny-Cours"),
    (4574, "Hockenheim"),
    (4653, "Portimão"),
    (4657, "Catalunya"),
    (4909, "Imola"),
    (4940, "Singapur"),
    (5063, "Singapur"),
    (5148, "Nürburgring"),
    (5278, "Melbourne"),
    (5281, "Abu Dhabi"),
    (5303, "Melbourne"),
    (5338, "Estambul"),
    (5412, "Sakhir (Bahréin)"),
    (5419, "Valencia"),
    (5451, "Shanghai"),
    (5513, "Austin"),
    (5543, "Sepang (Malasia)"),
    (5554, "Abu Dhabi"),
    (5615, "Yeongam (Corea)"),
    (5793, "Monza"),
    (5807, "Suzuka"),
    (5842, "Paul Ricard"),
    (5848, "Sochi"),
    (5891, "Silverstone"),
    (6003, "Bakú"),
    (6174, "Jeddah"),
    (6201, "Las Vegas"),
    (7004, "Spa-Francorchamps"),
]


def resolve_track_name(track_id: int, track_length: int = 0, swofty_track_key: str = "") -> str:
    """Resuelve el nombre legible del circuito a partir de Swofty Track Key, Track ID o longitud."""
    if swofty_track_key:
        slug = swofty_track_key.rpartition("/")[2] or swofty_track_key
        slug_clean = slug.replace("_", " ").replace("-", " ").strip()
        low = slug_clean.lower()
        for key, friendly in {
            "hockenheim": "Hockenheim",
            "nurburgring": "Nürburgring",
            "istanbul": "Estambul",
            "sepang": "Sepang (Malasia)",
            "malaysia": "Sepang (Malasia)",
            "valencia": "Valencia",
            "yeongam": "Yeongam (Corea)",
            "korea": "Yeongam (Corea)",
            "magny": "Magny-Cours",
            "imola": "Imola",
            "portimao": "Portimão",
            "mugello": "Mugello",
            "jerez": "Jerez",
            "indianapolis": "Indianápolis",
            "fuji": "Fuji",
            "kyalami": "Kyalami",
            "adelaide": "Adelaida",
            "estoril": "Estoril",
            "brands": "Brands Hatch",
            "bahrain": "Sakhir",
            "catalunya": "Catalunya",
            "barcelona": "Catalunya",
            "monaco": "Mónaco",
            "montreal": "Montreal",
            "canada": "Montreal",
            "silverstone": "Silverstone",
            "hungaroring": "Hungaroring",
            "spa": "Spa-Francorchamps",
            "monza": "Monza",
            "singapore": "Singapur",
            "suzuka": "Suzuka",
            "yas": "Abu Dhabi",
            "abu dhabi": "Abu Dhabi",
            "interlagos": "Interlagos",
            "brazil": "Interlagos",
            "melbourne": "Melbourne",
            "australia": "Melbourne",
            "shanghai": "Shanghai",
            "china": "Shanghai",
        }.items():
            if key in low:
                return friendly
        if slug_clean:
            return slug_clean.title()

    if track_id in TRACKS:
        return TRACKS[track_id]

    if track_length > 1000:
        best_name = None
        best_diff = 999999
        for length_m, name in TRACK_LENGTH_MAP:
            diff = abs(track_length - length_m)
            if diff < best_diff:
                best_diff = diff
                best_name = name
        if best_name and best_diff <= 95:
            return best_name

    return "el circuito"


SESSION_TYPES = {
    0: "Unknown", 1: "Practice 1", 2: "Practice 2", 3: "Practice 3", 4: "Short Practice",
    5: "Qualifying 1", 6: "Qualifying 2", 7: "Qualifying 3", 8: "Short Qualifying",
    9: "One-Shot Qualifying", 10: "Sprint Shootout 1", 11: "Sprint Shootout 2",
    12: "Sprint Shootout 3", 13: "Short Sprint Shootout", 14: "One-Shot Sprint Shootout",
    15: "Race", 16: "Race 2", 17: "Race 3", 18: "Time Trial",
}
RACE_SESSIONS = {15, 16, 17}

WEATHER = {0: "clear", 1: "light cloud", 2: "overcast", 3: "light rain",
           4: "heavy rain", 5: "storm"}

WEATHER_ES = {
    "clear": "cielo despejado y pista seca",
    "light cloud": "ligeramente nublado y pista seca",
    "overcast": "cielo muy cubierto",
    "light rain": "lluvia ligera en pista",
    "heavy rain": "lluvia intensa",
    "storm": "tormenta fuerte",
}

SAFETY_CAR = {0: "none", 1: "SAFETY CAR deployed", 2: "VIRTUAL SAFETY CAR", 3: "formation lap"}

TEAMS = {
    0: "Mercedes", 1: "Ferrari", 2: "Red Bull", 3: "Williams", 4: "Aston Martin",
    5: "Alpine", 6: "Racing Bulls", 7: "Haas", 8: "McLaren", 9: "Sauber",
    41: "F1 Generic", 104: "Custom Team", 129: "Konnersport", 142: "APXGP",
    154: "APXGP", 155: "Konnersport",
    # IDs de formato 2026 / Swofty (476..486)
    476: "Mercedes", 477: "Ferrari", 478: "Red Bull", 479: "Williams", 480: "Aston Martin",
    481: "Alpine", 482: "Racing Bulls", 483: "Haas", 484: "McLaren", 485: "Audi / Sauber",
    486: "Cadillac",
}

# Mapeo de todos los pilotos oficiales (modernos y clásicos) a su escudería
OFFICIAL_DRIVER_TEAMS: dict[str, str] = {
    # Red Bull Racing
    "VERSTAPPEN": "Red Bull",
    "PEREZ": "Red Bull",
    "VETTEL": "Red Bull",
    "WEBBER": "Red Bull",
    "RICCIARDO": "Red Bull",
    # Scuderia Ferrari
    "LECLERC": "Ferrari",
    "HAMILTON": "Ferrari",
    "SAINZ": "Ferrari",
    "ALONSO": "Ferrari",
    "MASSA": "Ferrari",
    "RAIKKONEN": "Ferrari",
    "RÄIKKÖNEN": "Ferrari",
    # McLaren
    "NORRIS": "McLaren",
    "PIASTRI": "McLaren",
    "BUTTON": "McLaren",
    # Mercedes-AMG
    "RUSSELL": "Mercedes",
    "ANTONELLI": "Mercedes",
    "SCHUMACHER": "Mercedes",
    "ROSBERG": "Mercedes",
    # Aston Martin
    "STROLL": "Aston Martin",
    # Williams Racing
    "ALBON": "Williams",
    "COLAPINTO": "Williams",
    "BARRICHELLO": "Williams",
    # Alpine / Renault
    "GASLY": "Alpine",
    "DOOHAN": "Alpine",
    "OCON": "Alpine",
    "KUBICA": "Renault",
    "PETROV": "Renault",
    # Racing Bulls / Toro Rosso
    "TSUNODA": "Racing Bulls",
    "LAWSON": "Racing Bulls",
    "HADJAR": "Racing Bulls",
    "BUEMI": "Toro Rosso",
    "ALGUERSUARI": "Toro Rosso",
    # Haas F1 Team
    "BEARMAN": "Haas",
    "MAGNUSSEN": "Haas",
    "HULKENBERG": "Haas",
    "HÜLKENBERG": "Haas",
    # Sauber / Kick / Audi
    "BORTOLETO": "Sauber",
    "BOTTAS": "Sauber",
    "ZHOU": "Sauber",
    "DE LA ROSA": "Sauber",
    "KOBAYASHI": "Sauber",
    # Equipos históricos
    "SENNA": "HRT (Hispania)",
    "CHANDHOK": "HRT (Hispania)",
    "SUTIL": "Force India",
    "LIUZZI": "Force India",
    "TRULLI": "Lotus Racing",
    "KOVALAINEN": "Lotus Racing",
    "GLOCK": "Virgin Racing",
    "DI GRASSI": "Virgin Racing",
}

CLASSIC_DRIVER_TEAMS = OFFICIAL_DRIVER_TEAMS

# Colores oficiales de retransmision F1 TV (color principal brillante sobre fondo oscuro + codigo de emblema)
TEAM_STYLES: dict[str, tuple[str, str]] = {
    "Ferrari": ("#FF1E27", "FER"),
    "McLaren": ("#FF8000", "MCL"),
    "Mercedes": ("#27F4D2", "MER"),
    "Red Bull": ("#4781D7", "RBR"),
    "Aston Martin": ("#00E7A7", "AMR"),
    "Williams": ("#64C4FF", "WIL"),
    "Alpine": ("#00A8FF", "ALP"),
    "Racing Bulls": ("#6692FF", "RB"),
    "Toro Rosso": ("#5B8CFF", "STR"),
    "Haas": ("#F03A47", "HAAS"),
    "Sauber": ("#52E252", "KICK"),
    "Audi / Sauber": ("#52E252", "KICK"),
    "HRT (Hispania)": ("#E5B842", "HRT"),
    "Renault": ("#FFD800", "REN"),
    "Force India": ("#FF851B", "FI"),
    "Lotus Racing": ("#19C37D", "LOT"),
    "Virgin Racing": ("#FF3333", "VRG"),
    "Cadillac": ("#E5B842", "CAD"),
    "APXGP": ("#D4AF37", "APX"),
    "Konnersport": ("#A3E635", "KON"),
}

DRIVER_NUMBERS: dict[str, int] = {
    "VERSTAPPEN": 1,
    "LECLERC": 16,
    "NORRIS": 4,
    "PIASTRI": 81,
    "HAMILTON": 44,
    "RUSSELL": 63,
    "SAINZ": 55,
    "ALONSO": 14,
    "STROLL": 18,
    "ALBON": 23,
    "GASLY": 10,
    "OCON": 31,
    "HÜLKENBERG": 27,
    "HULKENBERG": 27,
    "TSUNODA": 22,
    "LAWSON": 30,
    "BEARMAN": 87,
    "ANTONELLI": 12,
    "BORTOLETO": 5,
    "HADJAR": 6,
    "DOOHAN": 7,
    "COLAPINTO": 43,
    "PEREZ": 11,
    "BOTTAS": 77,
    "MAGNUSSEN": 20,
    # Temporada 2010 / Swofty
    "SENNA": 7,
    "CHANDHOK": 20,
    "VETTEL": 5,
    "WEBBER": 6,
    "MASSA": 7,
    "BUTTON": 1,
    "SCHUMACHER": 3,
    "ROSBERG": 4,
    "KUBICA": 11,
    "PETROV": 12,
    "BARRICHELLO": 9,
    "SUTIL": 14,
    "LIUZZI": 15,
    "BUEMI": 16,
    "ALGUERSUARI": 17,
    "TRULLI": 18,
    "KOVALAINEN": 19,
    "DE LA ROSA": 22,
    "KOBAYASHI": 23,
    "GLOCK": 24,
    "DI GRASSI": 25,
}


def resolve_radio_identity(
    player_driver: str,
    player_team: str,
    fallback_driver: str = "DRIVER",
    race_number: int = 0,
) -> tuple[str, str, str, int]:
    """Devuelve (display_driver_name, team_color_hex, badge_code, race_number) para el HUD F1 TV."""
    drv_clean = (player_driver or "").strip().upper()
    if not drv_clean or drv_clean.startswith("CAR #") or drv_clean in ("PLAYER", "JUGADOR", "UNKNOWN"):
        drv_display = (fallback_driver or "DRIVER").strip().upper()
    else:
        # Quitar prefijos y quedarse con el apellido como en F1 TV ("LECLERC", "SENNA", "ALONSO")
        parts = drv_clean.split()
        drv_display = parts[-1] if len(parts) == 1 or parts[0] not in ("DE",) else drv_clean

    team_clean = (player_team or "").strip()
    # Si la escudería no viene especificada o es genérica, deducirla del nombre del piloto oficial
    if not team_clean or team_clean in ("Unknown Team", "Tu Monoplaza", "Tu Escudería", "Custom Team", "F1 Generic"):
        if drv_display in OFFICIAL_DRIVER_TEAMS:
            team_clean = OFFICIAL_DRIVER_TEAMS[drv_display]

    if team_clean in TEAM_STYLES:
        color_hex, badge_code = TEAM_STYLES[team_clean]
    else:
        # Búsqueda parcial e insensible a mayúsculas/minúsculas para nombres largos de escudería
        matched = False
        t_low = team_clean.lower()
        for k, v in TEAM_STYLES.items():
            k_low = k.lower()
            if k_low in t_low or t_low in k_low:
                color_hex, badge_code = v
                matched = True
                break
        if not matched:
            if "red bull" in t_low or "redbull" in t_low or "rbr" in t_low or drv_display in ("VERSTAPPEN", "PEREZ"):
                color_hex, badge_code = ("#3671C6", "RBR")
            elif "aston" in t_low or drv_display in ("ALONSO", "STROLL"):
                color_hex, badge_code = ("#00E7A7", "AMR")
            elif "ferrari" in t_low or drv_display in ("LECLERC", "HAMILTON", "SAINZ"):
                color_hex, badge_code = ("#FF1E27", "FER")
            elif "mclaren" in t_low or drv_display in ("NORRIS", "PIASTRI"):
                color_hex, badge_code = ("#FF8000", "MCL")
            elif "mercedes" in t_low or drv_display in ("RUSSELL", "ANTONELLI"):
                color_hex, badge_code = ("#00D2BE", "MER")
            elif "williams" in t_low or drv_display in ("ALBON", "COLAPINTO"):
                color_hex, badge_code = ("#00A0DE", "WIL")
            elif "alpine" in t_low or drv_display in ("GASLY", "DOOHAN"):
                color_hex, badge_code = ("#0090FF", "ALP")
            elif "sauber" in t_low or "kick" in t_low or drv_display in ("HULKENBERG", "HÜLKENBERG", "BORTOLETO"):
                color_hex, badge_code = ("#52E252", "KICK")
            elif "haas" in t_low or drv_display in ("BEARMAN", "OCON", "MAGNUSSEN"):
                color_hex, badge_code = ("#F03A47", "HAAS")
            elif "bulls" in t_low or "rb" in t_low or drv_display in ("TSUNODA", "LAWSON", "HADJAR"):
                color_hex, badge_code = ("#6692FF", "RB")
            else:
                color_hex, badge_code = ("#3671C6", "RBR") if drv_display in OFFICIAL_DRIVER_TEAMS else ("#FF1E27", "F1")

    # Si es un piloto oficial reconocido, su dorsal es el oficial (ej: Verstappen siempre 1)
    if drv_display in DRIVER_NUMBERS:
        num = DRIVER_NUMBERS[drv_display]
    elif race_number and 0 < race_number < 100:
        num = race_number
    elif (fallback_driver or "").strip().upper() in DRIVER_NUMBERS:
        num = DRIVER_NUMBERS[(fallback_driver or "").strip().upper()]
    elif badge_code == "AMR":
        num = 14
    elif badge_code == "RBR":
        num = 1
    else:
        num = 14
    return drv_display, color_hex, badge_code, num

COMPOUNDS = {16: "Soft", 17: "Medium", 18: "Hard", 7: "Intermediate", 8: "Wet",
             15: "Wet", 19: "Super Soft", 20: "Soft", 21: "Hard", 22: "Wet"}

COMPOUNDS_ES = {
    "Soft": "blando",
    "Super Soft": "superblando",
    "Medium": "medio",
    "Hard": "duro",
    "Intermediate": "intermedio",
    "Wet": "de lluvia extrema",
}

WHEELS = ("RL", "RR", "FL", "FR")
WHEELS_ES = {
    "FL": "delantera izquierda",
    "FR": "delantera derecha",
    "RL": "trasera izquierda",
    "RR": "trasera derecha",
}
WHEELS_EN = {
    "FL": "front left",
    "FR": "front right",
    "RL": "rear left",
    "RR": "rear right",
}

FUEL_MIX = {0: "lean", 1: "standard", 2: "rich", 3: "max"}
ERS_MODE = {0: "none", 1: "medium", 2: "hotlap", 3: "overtake"}
ERS_MODE_ES = {"none": "apagado", "medium": "medio", "hotlap": "vuelta rápida", "overtake": "adelantamiento"}
PIT_STATUS = {0: "", 1: "PITTING", 2: "IN PIT LANE"}
RESULT_STATUS = {0: "invalid", 1: "inactive", 2: "active", 3: "finished",
                 4: "DNF", 5: "DSQ", 6: "not classified", 7: "retired"}
DRIVER_STATUS = {0: "in garage", 1: "flying lap", 2: "in lap", 3: "out lap", 4: "on track"}
FIA_FLAG = {-1: "unknown", 0: "none", 1: "green", 2: "blue", 3: "yellow"}

PENALTY_TYPES = {
    0: "drive-through", 1: "stop-go", 2: "grid penalty", 3: "penalty reminder",
    4: "time penalty", 5: "warning", 6: "disqualified", 7: "removed from formation lap",
    8: "parked too long timer", 9: "tyre regulations", 10: "this lap invalidated",
    11: "this and next lap invalidated", 12: "this lap invalidated without reason",
    13: "this and next lap invalidated without reason", 14: "this and previous lap invalidated",
    15: "this and previous lap invalidated without reason", 16: "retired", 17: "black flag timer",
}
