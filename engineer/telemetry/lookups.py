"""Tablas de traduccion de IDs del juego a texto (Ingles y Espanol)."""

TRACKS = {
    0: "Melbourne", 2: "Shanghai", 3: "Sakhir", 4: "Catalunya", 5: "Mónaco",
    6: "Montreal", 7: "Silverstone", 9: "Hungaroring", 10: "Spa-Francorchamps", 11: "Monza",
    12: "Singapur", 13: "Suzuka", 14: "Abu Dhabi", 15: "Austin", 16: "Interlagos",
    17: "Red Bull Ring", 19: "México", 20: "Bakú", 26: "Zandvoort", 27: "Imola",
    29: "Jeddah", 30: "Miami", 31: "Las Vegas", 32: "Qatar",
    39: "Silverstone Inverso", 40: "Red Bull Ring Inverso", 41: "Zandvoort Inverso",
}

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
}

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
