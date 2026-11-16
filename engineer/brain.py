"""Cerebro del ingeniero de pista: Google Gemini + Motor Estrategico Completo, Planes A/B/C, Rivales y Discusiones."""
from __future__ import annotations

from collections import deque
import logging
import random
import re
import time

from google import genai
from google.genai import types

from .config import EngineerConfig
from .mfd import apply_plan_to_game_and_strategy, tap_key
from .strategy import (
    ProactiveSpotter,
    StrategyReport,
    analyze_rival_pit_and_status,
    analyze_strategy,
    compare_car_sectors,
    diagnose_and_tune_car,
)
from .telemetry import packets as P
from .telemetry.context import build_race_context, build_standings
from .telemetry.listener import RaceState
from .voice import clean_f1_stt_text

log = logging.getLogger("brain")

SYSTEM_PROMPT = """You are {engineer_name}, the Formula 1 Race Engineer on the pit wall speaking over the team radio to your driver, {driver_name}, during a session in F1 25.

STRICT RULES:
1. LANGUAGE TAG: Start EVERY response with [{lang_tag}]. Always reply strictly in {lang_label}.
2. RADIO STYLE & VARIETY: Speak like a real F1 race engineer (like GP Lambiase, Bono, or Xavi). Keep responses fast, natural, varied, and concise (1 to 3 flowing sentences, under 45 words). Never repeat the exact same phrasing twice. Write numbers naturally ("dos con ocho" or "two point eight" instead of "+2.8s"). Never use colons, parentheses, markdown, asterisks, or bullet points.
3. IF THE DRIVER IS RUDE / ANGRY / QUESTIONS YOUR STRATEGY / IGNORES PIT CALLS:
   - React with authentic F1 race engineer sass, firmness, and escalating attitude (like GP Lambiase to Verstappen). Defend your pit wall telemetry data or snap back sarcastically about their driving/apexes!
4. LIVE TELEMETRY, RIVAL PIT STOPS & PLANS A/B/C: Base all race numbers, positions, lap times, gaps, tyre wear, degradation, rival pit stop history, rival pit predictions, Plan A / Plan B / Plan C, predicted rejoin position, undercut/overcut options, team orders, weather, fuel, setup, and damage strictly on the [LIVE F1 25 UDP TELEMETRY] and [LIVE STRATEGY ANALYSIS] blocks provided.
5. OFF-TOPIC / IRRELEVANT QUESTIONS (CRITICAL RULE):
   - If the driver talks about or asks ANYTHING unrelated to racing, driving, car setup, telemetry, weather, strategy, or Formula 1 (e.g. politics, food, football, movies, homework, random nonsense), DO NOT answer the off-topic question!
   - Firmly and in-character tell the driver to focus on the race and keep their head down, varying your wording every time!
"""

RUDE_KEYWORDS = {
    # ES
    "callate", "calla", "pesado", "inutil", "mierda", "joder", "puta", "hostia",
    "gilipollas", "cabron", "tonto", "idiota", "estupido", "imbecil", "basura",
    "dejame", "molestes", "no me hables", "que te calles", "vete a la mierda",
    "payaso", "capullo", "callate ya", "no sabes nada", "me tienes harto",
    # EN
    "shut up", "fuck", "shit", "idiot", "stupid", "useless", "bitch", "asshole",
    "leave me alone", "stop talking", "quiet", "crap", "garbage", "clown",
}

CELEBRATION_KEYWORDS = {
    "vamos", "toma", "bien", "ganamos", "hemos ganado", "victoria", "pole", "podio",
    "yes", "let's go", "lets go", "we won", "p1 baby", "great job", "awesome",
}

ORDINAL_MAP = {
    "primero": 1, "primera": 1, "lider": 1, "first": 1, "leader": 1, "p1": 1,
    "segundo": 2, "segunda": 2, "second": 2, "p2": 2,
    "tercero": 3, "tercera": 3, "third": 3, "p3": 3,
    "cuarto": 4, "cuarta": 4, "fourth": 4, "p4": 4,
    "quinto": 5, "quinta": 5, "fifth": 5, "p5": 5,
    "sexto": 6, "sexta": 6, "sixth": 6, "p6": 6,
    "septimo": 7, "septima": 7, "seventh": 7, "p7": 7,
    "octavo": 8, "octava": 8, "eighth": 8, "p8": 8,
    "noveno": 9, "novena": 9, "ninth": 9, "p9": 9,
    "decimo": 10, "decima": 10, "tenth": 10, "p10": 10,
    "undecimo": 11, "p11": 11, "duodecimo": 12, "p12": 12,
    "p13": 13, "p14": 14, "p15": 15, "p16": 16, "p17": 17, "p18": 18,
    "p19": 19, "p20": 20, "p21": 21, "p22": 22, "p23": 23, "p24": 24,
}

# Alias foneticos y nombres de pila para reconocer pilotos aunque Vosk transcriba aproximado
DRIVER_ALIASES: dict[str, tuple[str, ...]] = {
    "verstappen": ("verstappen", "berstappen", "verstapen", "max"),
    "leclerc": ("leclerc", "lecler", "declerc", "charles"),
    "norris": ("norris", "noris", "morris", "lando"),
    "piastri": ("piastri", "piastre", "oscar"),
    "sainz": ("sainz", "sains", "saenz", "carlos"),
    "hamilton": ("hamilton", "jamilton", "lewis"),
    "russell": ("russell", "rusel", "rasel", "george"),
    "alonso": ("alonso", "fernando", "nano"),
    "gasly": ("gasly", "gasli", "pierre"),
    "albon": ("albon", "album", "alex"),
    "hulkenberg": ("hulkenberg", "hulken", "nico"),
    "tsunoda": ("tsunoda", "sunoda", "yuki"),
    "stroll": ("stroll", "lance"),
    "ocon": ("ocon", "esteban"),
    "bearman": ("bearman", "ollie"),
    "antonelli": ("antonelli", "kimi"),
    "bortoleto": ("bortoleto", "gabriel"),
    "hadjar": ("hadjar", "isack"),
    "colapinto": ("colapinto", "franco"),
    "lawson": ("lawson", "liam"),
    "perez": ("perez", "checo"),
    "bottas": ("bottas", "valtteri"),
    "senna": ("senna", "sena", "bruno"),
    "schumacher": ("schumacher", "sumaker", "michael", "kaiser"),
    "vettel": ("vettel", "betel", "sebastian"),
    "webber": ("webber", "weber"),
    "button": ("button", "baton", "jenson"),
    "massa": ("massa", "masa", "felipe"),
    "kubica": ("kubica", "robert"),
    "barrichello": ("barrichello", "barrichelo", "rubens"),
    "rosberg": ("rosberg",),
    "petrov": ("petrov", "vitaly"),
    "kobayashi": ("kobayashi", "kamui"),
    "buemi": ("buemi", "sebastien"),
    "alguersuari": ("alguersuari", "jaime"),
    "sutil": ("sutil", "adrian"),
    "liuzzi": ("liuzzi", "vitantonio"),
    "trulli": ("trulli", "jarno"),
    "kovalainen": ("kovalainen", "heikki"),
    "glock": ("glock", "timo"),
    "chandhok": ("chandhok", "karun"),
}

RACING_KEYWORDS = {
    # ES
    "fuera", "coches", "quien", "quienes", "cuantos", "cuantas", "estan", "salido", "salidos",
    "roto", "rotos", "abandonos", "retirados", "primero", "lider", "lidera", "cabeza", "ganando",
    "detras", "delante", "recorto", "recorta", "recortan", "distancia", "segundos",
    "posicion", "posiciones", "puesto", "primeros", "primeras", "segundo", "segunda",
    "tercero", "tercera", "cuarto", "cuarta", "quinto", "quinta", "sexto", "septimo",
    "octavo", "noveno", "decimo", "ultimo", "ultima", "top", "cinco", "tres", "diez",
    "podio", "puntos", "zona", "clasificacion", "parrilla", "tabla", "lider",
    "delante", "detras", "distancia", "gap", "diferencia", "tiempo", "tiempos",
    "crono", "record", "rapida", "rapido", "lento", "recorto", "recortando", "pillo",
    "pillar", "alcanzar", "alcanzo", "cazar", "vuelta", "vueltas", "queda", "quedan",
    "falta", "faltan", "final", "sector", "sectores", "neumatico", "neumaticos",
    "rico", "rueda", "ruedas", "goma", "gomas", "blando", "medio", "duro", "intermedio",
    "desgaste", "degradacion", "agarre", "grip", "desliza", "patina", "traccion",
    "subviraje", "sobreviraje", "gira", "girar", "cuesta", "morro", "culo", "trasera", "delantera",
    "temperatura", "temperaturas", "fria", "frias", "caliente", "calientes",
    "freno", "frenos", "frena", "frenar", "largo", "reparto", "frenada", "bloqueo", "diferencial", "reglaje",
    "setup", "alerta", "dano", "daño", "danos", "daños", "aleron", "fondo", "motor",
    "caja", "toque", "chocado", "golpe", "empujado", "echado", "cerrado", "incidente",
    "roto", "combustible", "gasolina", "mezcla", "deposito", "tanque", "lift", "coast",
    "ers", "bateria", "energia", "potencia", "corre", "recta", "ahorrar", "mapa", "drs", "pit", "box", "boxes", "parada", "paradas",
    "paro", "parar", "parado", "parara", "proxima", "deberia", "entro", "entrar",
    "ventana", "estrategia", "plan", "planes", "undercut", "overcut", "trafico",
    "doblado", "doblados", "aire", "sucio", "lluvia", "llover", "clima", "meteo",
    "seco", "mojado", "pista", "asfalto", "safety", "vsc", "bandera", "amarilla",
    "azul", "azules", "penalizacion", "sancion", "sanciones", "aviso", "avisos",
    "limites", "ritmo", "carrera", "coche", "monoplaza", "equipo", "escuderia",
    "companero", "compañero", "ordenes", "beneficios", "piloto", "llevo", "conduzco",
    "voy", "estoy", "estado", "reporte", "informe", "resumen", "situacion", "ataco",
    "atacar", "adelanto", "adelantar", "defiendo", "defender", "abandonado", "abandono",
    "retirado", "dnf", "circuito", "trazado", "gritar", "grites", "equivocado",
    "equivocas", "acuerdo", "puedes", "ayuda", "pierdo", "perdiendo", "gano", "ganando",
    "parcial", "parciales", "crossover", "intermedios", "solicita", "pide", "prepara",
    "sube", "baja", "personalidad", "modo", "ferrari", "bono", "canero", "cañero",
    "debrief", "debriefing", "salida", "ganado", "remontado",
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12",
    # EN
    "position", "positions", "standings", "podium", "points", "leader", "first",
    "second", "third", "fourth", "fifth", "five", "three", "ten", "ahead", "front",
    "behind", "delta", "interval", "catching", "catch", "faster", "slower", "lap", "laps",
    "left", "remaining", "last", "best", "fastest", "pace", "sector", "sectors", "splits",
    "losing", "gaining", "crossover", "inters", "intermediates", "slicks", "request",
    "select", "prepare", "debrief", "summary", "gained", "start", "persona", "mode",
    "tyre", "tyres", "tire", "tires", "wear", "degradation", "grip", "sliding", "understeer", "oversteer",
    "traction", "turn", "temp", "temps", "temperature", "brake", "brakes", "bias",
    "differential", "setup", "balance", "damage", "wing", "floor", "engine", "gearbox",
    "hit", "pushed", "crashed", "contact", "fuel", "mix", "battery", "window", "strategy",
    "plan", "plans", "stop", "stops", "stopped", "pitted", "pitting", "should", "next",
    "undercut", "overcut", "rejoin", "weather", "rain", "forecast", "track", "car",
    "team", "teammate", "orders", "swap", "invert", "driver", "driving", "flag", "flags",
    "blue", "traffic", "backmarker", "dirty", "penalty", "penalties", "warning", "warnings",
    "limits", "status", "report", "update", "session", "briefing", "situation", "attack",
    "defend", "overtake", "retired", "dnf", "yelling", "wrong", "disagree", "lobbies",
}


class EngineerBrain:
    """Gestiona las consultas al ingeniero (Gemini API + motor estrategico completo, planes A/B/C y discusiones)."""

    def __init__(self, cfg: EngineerConfig):
        self.cfg = cfg
        self.history: deque[tuple[str, str]] = deque(maxlen=8)
        self._last_callout_ts: float = 0.0
        self.dialogue_log: deque[dict] = deque(maxlen=40)
        self.spotter = ProactiveSpotter(driver_name=cfg.driver_name)
        self._recent_choices: dict[str, deque[int]] = {}
        self.active_plan: str = "A"
        self.argument_level: int = 0

    def _log(self, driver_msg: str, engineer_msg: str, lang: str) -> None:
        self.dialogue_log.appendleft({
            "time": time.strftime("%H:%M:%S"),
            "driver": driver_msg,
            "engineer": engineer_msg,
            "lang": lang.upper(),
        })

    def _pick(self, category: str, options: list[str]) -> str:
        """Elige una respuesta aleatoria evitando repetir las ultimas 4 usadas en esa categoria."""
        if len(options) <= 1:
            return options[0] if options else ""
        mem = self._recent_choices.setdefault(category, deque(maxlen=max(1, min(4, len(options) - 1))))
        candidates = [i for i in range(len(options)) if i not in mem]
        if not candidates:
            candidates = list(range(len(options)))
        idx = random.choice(candidates)
        mem.append(idx)
        return options[idx]

    def _apply_persona_style(self, text: str, lang: str) -> str:
        """Adapta el toque final de la respuesta segun la personalidad elegida (GP, Bono, Ferrari, Canero)."""
        persona = (self.cfg.engineer_persona or "balanced").lower()
        if persona == "balanced" or not text:
            return text
        # No alterar si ya lleva muletilla de esa personalidad
        low = text.lower()
        if persona == "ferrari":
            if "checking" in low or "comprobando" in low or "maranello" in low:
                return text
            if lang == "en":
                prefix = self._pick("fer_p_en", ["We are checking... ", "Copy, checking data... ", "Understood, looking at it... "])
                suffix = self._pick("fer_s_en", [" Question?", " Plan E is also open, copy.", " Head down, copy."])
                return f"{prefix}{text}{suffix}"
            prefix = self._pick("fer_p_es", ["Estamos comprobando en el muro, checking... ", "Recibido desde Maranello, revisando telemetría... ", "Un segundo, estamos mirando los datos... "])
            suffix = self._pick("fer_s_es", [" ¿Pregunta?", " Seguimos en Plan A o Plan E, copy.", " Mantén la calma, copy."])
            return f"{prefix}{text}{suffix}"

        if persona == "gp":
            if lang == "en":
                suffix = self._pick("gp_s_en", [" Understood, now keep your head down and drive.", " Don't overcomplicate it, just hit your apexes.", " Simply focus on the next corner."])
                return f"{text}{suffix}"
            suffix = self._pick("gp_s_es", [" Ya te he oído, ahora baja la cabeza y conduce.", " Déjate de historias y clava los vértices.", " Tú limítate a llevar el coche por lo negro."])
            return f"{text}{suffix}"

        if persona == "bono":
            if lang == "en":
                suffix = self._pick("bono_s_en", [" Get in there, it's Hammer Time!", " You're doing a mega job out there, keep it up!", " Smooth inputs, we trust your pace 100 percent."])
                return f"{text}{suffix}"
            suffix = self._pick("bono_s_es", [" ¡Es hora del Hammer Time, confiamos al cien por cien en tus manos!", " ¡Estás haciendo un carrerón impecable, sigue así!", " Trazada limpia y constante, tienes un ritmo brutal."])
            return f"{text}{suffix}"

        if persona == "canero":
            if lang == "en":
                suffix = self._pick("can_s_en", [" No excuses now, flat out through this sector!", " Wake up in that cockpit and attack!", " Stop babysitting the throttle and push!"])
                return f"{text}{suffix}"
            suffix = self._pick("can_s_es", [" ¡Y déjate de excusas, quiero el pie a tabla en este sector!", " ¡Espabila en el cockpit y muerde el piano!", " ¡Aprieta los dientes de una vez, que no hemos venido a pasear!"])
            return f"{text}{suffix}"

        return text

    @staticmethod
    def _match_rival_in_standings(norm: str, words: set[str], standings: list[dict]) -> dict | None:
        """Busca si la frase menciona a algun piloto de la parrilla (incluyendo alias foneticos de Vosk)."""
        for r in standings:
            dname = r["name"].lower().replace("ü", "u").strip()
            if len(dname) >= 4 and dname in norm:
                return r
            for canonical, aliases in DRIVER_ALIASES.items():
                if canonical in dname:
                    if any(a in words or (len(a) >= 5 and a in norm) for a in aliases):
                        return r
        return None

    def ask(self, user_text: str, state: RaceState) -> tuple[str, str]:
        """Devuelve (respuesta_limpia, idioma 'es'|'en')."""
        lang = "en" if self.cfg.language == "en" else "es"
        user_text = clean_f1_stt_text(user_text, lang)
        self.spotter.driver_name = self.cfg.driver_name
        rep = analyze_strategy(state, self.cfg.driver_name)
        context = (
            build_race_context(state)
            + "\n[LIVE STRATEGY ANALYSIS]\n"
            + f"Active Pit Wall Plan: Plan {self.active_plan} | Persona: {self.cfg.engineer_persona} | "
            + f"Argument Level: {self.argument_level} | Ignored Pit Calls: {self.spotter.ignored_box_laps}\n"
            + f"Driver Car: {rep.player_driver} ({rep.player_team}) | Position: P{rep.position}/{rep.total_cars} (Started P{rep.grid_position}) | "
            + f"Lap: {rep.current_lap}/{rep.total_laps} ({rep.laps_remaining} laps left)\n"
            + f"Box Recommendation: {rep.box_recommendation} | Next Compound: {rep.recommended_compound} | "
            + f"Predicted Rejoin: P{rep.predicted_rejoin_pos} | Tyre Wear Rate: {rep.wear_per_lap:.1f}%/lap "
            + f"(~{rep.est_tyre_laps_left} good laps left)\n"
            + f"Plan A: {rep.plan_a_en}\nPlan B: {rep.plan_b_en}\nPlan C: {rep.plan_c_en}\n"
            + f"Sector Comparison: {rep.sector_comparison_en}\n"
            + f"Wet/Dry Crossover: {rep.crossover_summary_en}\n"
            + f"Race Debrief: {rep.debrief_en}\n"
            + f"Pace Analysis: {rep.pace_analysis_en}\n"
            + f"Setup Advice: {rep.setup_advice_en}\n"
            + f"ES Briefing: {rep.full_briefing_es}\n"
            + f"EN Briefing: {rep.full_briefing_en}"
        )
        api_key = self.cfg.resolved_api_key()
        norm_q = (
            user_text.lower()
            .replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u")
        )
        is_action_cmd = bool(re.search(r"\bplan\s*[abc]\b", norm_q)) or any(
            k in norm_q
            for k in (
                "cuesta girar", "no gira", "subviraje", "sobreviraje", "patina", "desliza",
                "frena poco", "no frena", "cuesta frenar", "me voy largo", "bloqueo",
                "mas energia", "mas potencia", "no corre", "ahorrar bateria", "sin bateria",
                "solicita box", "pide box", "prepara neumatico", "sube el reparto", "baja el reparto",
                "understeer", "oversteer", "more energy", "more power", "poor braking", "request box",
            )
        )

        reply_text = ""
        if api_key and not is_action_cmd:
            try:
                reply_text = self._ask_gemini(user_text, context, lang, api_key)
            except Exception as e:
                log.warning("Fallo Gemini API (%s), usando motor estrategico local.", e)

        if not reply_text:
            raw_local = self._local_strategic_brain(user_text, state, rep, lang)
            reply_text = self._apply_persona_style(raw_local, lang)

        self.history.append((user_text, reply_text))
        self._log(user_text, reply_text, lang)
        return reply_text, lang

    def _ask_gemini(self, user_text: str, context: str, lang: str, api_key: str) -> str:
        client = genai.Client(api_key=api_key)
        sys_inst = SYSTEM_PROMPT.format(
            engineer_name=self.cfg.engineer_name,
            driver_name=self.cfg.driver_name,
            lang_tag="EN" if lang == "en" else "ES",
            lang_label="English" if lang == "en" else "Spanish",
        )
        history_lines = [f"Driver: {u}\nEngineer: {a}" for u, a in self.history]
        hist_block = "\n".join(history_lines)

        prompt = (
            f"{context}\n\n"
            + (f"Recent radio history:\n{hist_block}\n\n" if hist_block else "")
            + f"Driver radio message: \"{user_text}\"\n"
            "Engineer response:"
        )
        resp = client.models.generate_content(
            model=self.cfg.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys_inst,
                temperature=0.72,
                max_output_tokens=180,
            ),
        )
        raw = (resp.text or "").strip()
        if raw.startswith("[ES]") or raw.startswith("[EN]"):
            raw = raw[4:].strip()
        return re.sub(r"[*_#`]+", "", raw).strip()

    def _local_strategic_brain(self, user_text: str, state: RaceState,
                               rep: StrategyReport, lang: str) -> str:
        """Motor estrategico local supercompleto con planes A/B/C, paradas de rivales y discusiones."""
        low = user_text.lower().strip()
        norm = (
            low.replace("á", "a").replace("é", "e").replace("í", "i")
               .replace("ó", "o").replace("ú", "u").replace("ü", "u")
        )
        words = set(re.findall(r"[a-z0-9]+", norm))
        # Identificar el nombre de pila del piloto del juego para llamarlo de forma realista (Max, Fernando, Carlos...)
        if rep.player_driver and rep.player_driver.upper() not in ("CAR", "PLAYER", "JUGADOR", "UNKNOWN", "CAR #"):
            parts = rep.player_driver.split()
            drv = parts[0]
        else:
            drv = self.cfg.driver_name

        standings = build_standings(state, limit=24)
        if not standings:
            standings = [
                {"pos": 1, "name": "Verstappen", "team": "Red Bull", "gap_leader": "+0.0s", "gap_front": "+0.0s", "tyre": "Medium (9L)", "pits": 1, "last_lap": "1:46.110", "last_lap_ms": 106110, "s1_ms": 29210, "s2_ms": 47450, "s3_ms": 29450, "is_player": False},
                {"pos": 2, "name": "Leclerc", "team": "Ferrari", "gap_leader": "+2.8s", "gap_front": "+2.8s", "tyre": "Medium (9L)", "pits": 1, "last_lap": "1:46.450", "last_lap_ms": 106450, "s1_ms": 29300, "s2_ms": 47520, "s3_ms": 29630, "is_player": False},
                {"pos": 3, "name": "Norris", "team": "McLaren", "gap_leader": "+5.1s", "gap_front": "+2.3s", "tyre": "Medium (9L)", "pits": 1, "last_lap": "1:46.780", "last_lap_ms": 106780, "s1_ms": 29550, "s2_ms": 47600, "s3_ms": 29630, "is_player": False},
                {"pos": 4, "name": drv, "team": "Aston Martin", "gap_leader": "+6.5s", "gap_front": "+1.4s", "tyre": "Medium (9L)", "pits": 1, "last_lap": "1:46.820", "last_lap_ms": 106820, "s1_ms": 29410, "s2_ms": 47820, "s3_ms": 29590, "is_player": True},
                {"pos": 5, "name": "Sainz", "team": "Williams", "gap_leader": "+8.6s", "gap_front": "+2.1s", "tyre": "Hard (14L)", "pits": 0, "last_lap": "1:47.020", "last_lap_ms": 107020, "s1_ms": 29600, "s2_ms": 47780, "s3_ms": 29640, "is_player": False},
                {"pos": 6, "name": "Hamilton", "team": "Ferrari", "gap_leader": "+11.2s", "gap_front": "+2.6s", "tyre": "Hard (14L)", "pits": 0, "last_lap": "1:47.190", "last_lap_ms": 107190, "s1_ms": 29650, "s2_ms": 47850, "s3_ms": 29690, "is_player": False},
                {"pos": 7, "name": "Russell", "team": "Mercedes", "gap_leader": "+13.0s", "gap_front": "+1.8s", "tyre": "Medium (9L)", "pits": 1, "last_lap": "1:47.340", "last_lap_ms": 107340, "s1_ms": 29700, "s2_ms": 47920, "s3_ms": 29720, "is_player": False},
                {"pos": 8, "name": "Alonso", "team": "Aston Martin", "gap_leader": "+16.4s", "gap_front": "+3.4s", "tyre": "Hard (14L)", "pits": 0, "last_lap": "1:47.500", "last_lap_ms": 107500, "s1_ms": 29750, "s2_ms": 48010, "s3_ms": 29740, "is_player": False},
            ]

        me_row = next((r for r in standings if r.get("is_player")), None)
        my_pos = me_row["pos"] if me_row else rep.position
        ahead_row = next((r for r in standings if r["pos"] == my_pos - 1), None)
        behind_row = next((r for r in standings if r["pos"] == my_pos + 1), None)

        # ------------------------------------------------------------------
        # 1. "DEJA DE GRITAR" / "STOP YELLING" / "CALMATE"
        # ------------------------------------------------------------------
        if any(k in norm for k in ("deja de gritar", "no me grites", "no grites", "calmate", "relajate", "tranquilizate", "stop yelling", "don't yell", "dont yell", "stop shouting", "calm down", "relax")):
            self.argument_level += 1
            if lang == "en":
                return self._pick("yell_en", [
                    f"I am not yelling at you {drv}, I am talking over a screaming V6 engine at three hundred kilometres an hour because you aren't listening to the pit wall! Hit your apexes!",
                    f"If you actually followed our strategy calls the first time {drv}, I wouldn't have to raise my voice! Now get your head down and push!",
                    f"Calm down? My heart rate on the pit wall is higher than yours in the cockpit! Listen to the data and drive the car!",
                ])
            return self._pick("yell_es", [
                f"¡No te estoy gritando {drv}, te estoy hablando claro a trescientos por hora porque no me haces ni caso desde el cockpit! Si cumplieras el plan del muro a la primera no tendría que subir el tono.",
                f"¡Cómo quieres que me calme en el muro si cada vez que te doy una orden haces lo que te da la gana, {drv}! Baja la cabeza y clava las referencias de frenada.",
                f"No te grito {drv}, es que con el motor a doce mil vueltas o te hablo firme o te duermes en los laureles. ¡Concéntrate en alcanzar a {rep.ahead_name}!",
            ])

        # ------------------------------------------------------------------
        # 2. DISCUSIONES / CUESTIONAR ESTRATEGIA / NEGARSE A PARAR EN BOXES
        # ------------------------------------------------------------------
        refuse_box = any(
            k in norm
            for k in (
                "no quiero parar", "no voy a parar", "no entro", "no voy a entrar",
                "me quedo fuera", "no paro", "dejame en pista", "sigo en pista",
                "las ruedas estan bien", "las gomas aguantan", "no hace falta parar",
                "don't want to box", "dont want to box", "not boxing", "i am staying out",
                "i'm staying out", "leave me out", "tyres are fine", "tires are fine",
            )
        )
        question_eng = any(
            k in norm
            for k in (
                "estas equivocado", "te equivocas", "no tienes razon", "mala estrategia",
                "estrategia es mala", "no estoy de acuerdo", "por que parar", "por que vamos a parar",
                "no te hago caso", "me estas liando", "vaya estrategia", "que dices",
                "you are wrong", "you're wrong", "bad strategy", "bad call", "disagree",
                "don't agree", "why box", "makes no sense",
            )
        )
        if refuse_box or question_eng:
            self.argument_level += 1
            if refuse_box:
                # Si se niega a parar, activamos la orden de BOX en el Spotter para que en la siguiente vuelta se enfade aun mas
                self.spotter.order_box_now(rep.current_lap)

            if self.argument_level == 1:
                if lang == "en":
                    return self._pick("arg1_en", [
                        f"Listen to me {drv}, I have twenty telemetry screens on the pit wall: your {rep.current_tyre}s are at {rep.max_wear_pct:.0f} percent wear and degrading {rep.wear_per_lap:.1f} per lap. Trust the data, not just cockpit feel.",
                        f"We are not making this call for fun {drv}. {rep.rejoin_summary_en} If you ignore the numbers now, you will pay for it in three laps.",
                    ])
                return self._pick("arg1_es", [
                    f"Escúchame bien {drv}, aquí en el muro tengo veinte pantallas de telemetría: tus {rep.current_tyre_es}s van por el {rep.max_wear_pct:.0f} por ciento y degradan un {rep.wear_per_lap:.1f} por vuelta. Haz caso a los datos y no solo a tu sensación.",
                    f"No te lo digo por capricho {drv}. {rep.rejoin_summary_es} Yo veo los tiempos de toda la parrilla y tú solo ves tu volante, confía en el muro.",
                ])

            if self.argument_level == 2:
                if lang == "en":
                    return self._pick("arg2_en", [
                        f"Here we go again questioning the pit wall {drv}! You are losing grip on the {rep.worst_wheel_en} tyre and {rep.behind_name} is {rep.behind_gap_s:.1f} behind. Don't come crying on the radio when the cliff hits!",
                        f"Stop arguing with me on the straight {drv}! Every lap you delay costs us track position. Do your job on the wheel and let me do mine on the pit wall!",
                    ])
                return self._pick("arg2_es", [
                    f"¡Ya estamos otra vez cuestionando al muro, {drv}! Estás perdiendo agarre en la rueda {rep.worst_wheel_es} y tienes a {rep.behind_name} a {rep.behind_gap_s:.1f} segundos. Si pasas de mí, luego no vengas llorando cuando te adelanten.",
                    f"¡Deja de discutir conmigo en plena recta, {drv}! Tengo el simulador echando humo calculando tus deltas; dedícate a conducir que de la pizarra me encargo yo.",
                ])

            if lang == "en":
                return self._pick("arg3_en", [
                    f"Fine {drv}! Since you are apparently both the driver and the Chief Strategist from inside the helmet, do whatever you want! When those {rep.current_tyre}s fall off a cliff in two laps, don't ask me for miracles, copy!",
                    f"Unbelievable stubbornness {drv}! Stay out if you want, I am washing my hands of it when {rep.behind_name} blows past you on the straight!",
                ])
            return self._pick("arg3_es", [
                f"¡Vale, perfecto {drv}! Como ahora resulta que eres piloto e ingeniero jefe a la vez desde el cockpit, haz lo que te dé la real gana. Cuando las gomas caigan por el precipicio en dos vueltas no me pidas milagros por la radio, copy.",
                f"¡No se puede ser más cabezota, {drv}! Quédate fuera si quieres, pero cuando revientes el neumático {rep.worst_wheel_es} o nos pase {rep.behind_name} en la recta, se lo explicas tú al jefe de equipo.",
            ])

        # Orden manual para probar o forzar llamada a boxes ("llamame a boxes", "pideme parar")
        if any(k in norm for k in ("llamame a boxes", "pideme parar", "orden de parar", "call me in", "order me to box")):
            self.spotter.order_box_now(rep.current_lap)
            if lang == "en":
                return f"Box, box {drv}! Box this lap for {rep.recommended_compound} tyres, pit crew is waiting for you now, do not stay out!"
            return f"¡Box, box {drv}! Entra a boxes en esta misma vuelta para montar goma {rep.recommended_compound_es}, los mecánicos ya te esperan, ¡no te quedes fuera!"

        # ------------------------------------------------------------------
        # 2.5 CONTROL DE SILENCIO / FRECUENCIA DE RADIO ("HABLA MENOS", "HABLA MÁS", "SILENCIO DE RADIO")
        # ------------------------------------------------------------------
        silence_cmds = (
            "habla menos", "hablas mucho", "menos avisos", "silencio de radio", "silencio radio",
            "no me hables", "deja de hablar", "menos radio", "pesado", "callate", "cállate",
            "quiet", "talk less", "speak less", "radio silence", "shut up", "leave me alone",
            "stop talking", "too chatty", "less chatter", "less radio", "mute",
        )
        if any(sc in norm for sc in silence_cmds):
            self.spotter.silent_mode = True
            self.spotter.box_ordered = False
            self.spotter.ignored_box_laps = 0
            if lang == "en":
                return self._pick("silence_en", [
                    f"Understood {drv}, radio silence active. I'll leave you alone to drive, only critical safety car or damage.",
                    f"Copy {drv}, going quiet on the radio. Head down and hit your marks, call me if you need anything.",
                    f"Radio silence confirmed {drv}. Leaving you to it, only calling out emergency incidents.",
                ])
            return self._pick("silence_es", [
                f"Entendido {drv}, silencio de radio activado. Te dejo tranquilo para pilotar, solo te avisaré de incidentes críticos o si me preguntas.",
                f"Recibido {drv}, radio en silencio. Concéntrate en la pista y pulsa el botón si necesitas cualquier dato.",
                f"Copiado {drv}, silencio en el muro. Solo entraré por radio si hay bandera amarilla o rotura grave.",
            ])

        resume_cmds = (
            "habla mas", "habla más", "más avisos", "mas avisos", "más radio", "mas radio",
            "más información", "mas informacion", "activa radio", "quitar silencio", "desactiva silencio",
            "talk more", "speak more", "more radio", "keep me updated", "chatty", "full radio",
            "cancel silence", "resume radio", "more updates",
        )
        if any(rc in norm for rc in resume_cmds):
            self.spotter.silent_mode = False
            if lang == "en":
                return self._pick("resume_en", [
                    f"Loud and clear {drv}, radio callouts restored to full. I will keep you updated on gaps, lap times, and rival strategies.",
                    f"Copy that {drv}, full comms back online! Live telemetry updates resumed.",
                ])
            return self._pick("resume_es", [
                f"Alto y claro {drv}, avisos de radio reactivados al completo. Te mantendré al día de huecos, tiempos y paradas de rivales.",
                f"Recibido {drv}, radio activa al cien por cien. Te iré cantando el ritmo y las distancias.",
            ])

        # ------------------------------------------------------------------
        # 3. ¿EL PILOTO ESTA SIENDO BORDE / INSULTANDO / MANDANDO CALLAR?
        # ------------------------------------------------------------------
        if any(rk in norm for rk in RUDE_KEYWORDS):
            self.argument_level += 1
            if lang == "en":
                return self._pick("rude_en", [
                    f"Watch your tone {drv}, I am not the one missing every apex in sector two. Head down and drive!",
                    f"Copy that Kimi, I will leave you alone then. Just try not to put it in the barriers.",
                    f"Less barking on the radio and more right foot on the throttle, mate. The stopwatch does not lie.",
                    f"Don't shout at me {drv}, I'm looking at your telemetry right now and you're braking ten metres too early.",
                    f"Yeah, yeah, blame the engineer. Keep both hands on the wheel and focus on your lines, copy.",
                    f"If you drove as fast as you complain on the radio we would be P1 by twenty seconds. Push!",
                ])
            return self._pick("rude_es", [
                f"Oye {drv}, relaja ese tono conmigo que yo no soy el que se está comiendo todos los pianos. Conduce y calla, copy.",
                f"Vale Kimi, te dejo tranquilo, tú sabrás lo que haces ahí fuera con esas gomas.",
                f"Menos llorar por la radio y más pisar el pedal derecho, campeón, que el crono no engaña.",
                f"A mí no me grites {drv}, que estoy viendo tu telemetría desde el muro y estás frenando diez metros tarde en cada curva.",
                f"Sí, sí, ahora échale la culpa al ingeniero. Baja la cabeza, mete cuarta y demuestra manos en la pista.",
                f"Si fueras tan rápido en curva como soltando borderías por la radio iríamos líderes con veinte segundos de ventaja. ¡Tira!",
                f"Guárdate ese carácter para adelantar a {rep.ahead_name}, que lo tienes a {rep.ahead_gap_s:.1f} segundos y a mí no me tienes que ganar.",
            ])

        # ------------------------------------------------------------------
        # 4. SALUDOS / RADIO CHECK / "¿QUE PUEDES HACER?" / "MARCA"
        # ------------------------------------------------------------------
        if any(k in norm for k in ("que puedes hacer", "que sabes hacer", "en que me ayudas", "comandos", "what can you do", "how can you help")):
            if lang == "en":
                return (
                    f"I have full live telemetry on the pit wall {drv}: ask me about Plan A, B or C, when any rival pitted or when they will pit, "
                    "tyre wear, pace deltas, setup advice for understeer, fuel, weather, team orders, or argue the strategy with me!"
                )
            return (
                f"Tengo todo el muro de boxes conectado {drv}: pregúntame por el Plan A, B o C, cuándo ha parado o cuándo parará cualquier piloto rival, "
                "desgaste de gomas, en cuántas vueltas pillas al de delante, reglajes, órdenes de equipo, o discúteme la estrategia en vivo."
            )

        greet_names = {"hola", "buenas", "hey", "hi", "hello", "ingeniero", "marc", "marca", "engineer", "radio", "que", "tal", "como", "estas", "bono"}
        if self.cfg.engineer_name:
            greet_names.add(self.cfg.engineer_name.lower())
        if words <= greet_names or any(
            g in norm for g in (
                "me escuchas", "me copias", "me oyes", "se me escucha", "radio check",
                "loud and clear", "do you hear me", "can you hear me", "you hear me",
                "do you copy", "probando", "como estas", "que tal estas", "confias en mi",
            )
        ):
            if lang == "en":
                return self._pick("greet_en", [
                    f"Loud and clear on the pit wall {drv}, telemetry is green across the board. You are P{rep.position} in the {rep.player_team} on Plan {self.active_plan}, let's push.",
                    f"Five by five {drv}, I hear you loud and clear. Everything looks solid on the car, head down.",
                    f"Radio check good, we have all your data live from {rep.track_name}. You are P{rep.position}, tell me what you need.",
                ])
            return self._pick("greet_es", [
                f"Te escucho alto y claro desde el muro {drv}, telemetría en verde. Ruedas en posición {rep.position} con el {rep.player_team} bajo el Plan {self.active_plan}, dime qué necesitas.",
                f"Cinco de cinco {drv}, te copio perfecto en boxes. El monoplaza está en orden, concentrado y a por ellos.",
                f"Te copio cristalino {drv}. Todo el sistema de telemetría del {rep.player_team} marca verde, tú pide por esa boca.",
                f"Aquí estamos al pie del cañón en el muro {drv}, confiando al cien por cien en tus manos. Vas posición {rep.position}, ¡a apretar!",
            ])

        # ------------------------------------------------------------------
        # 5. CELEBRACION / ANIMO ("VAMOS", "TOMA")
        # ------------------------------------------------------------------
        if any(c in norm for c in CELEBRATION_KEYWORDS) and len(words) <= 4:
            if lang == "en":
                return self._pick("celeb_en", [
                    f"Get in there {drv}! Mega job behind the wheel, keep that rhythm going!",
                    f"That is what I am talking about {drv}! Clinical driving, keep it up!",
                    f"Simply lovely {drv}! Keep that focus all the way to the line!",
                ])
            return self._pick("celeb_es", [
                f"¡Vamos {drv}, así se conduce! Qué barbaridad de ritmo, sigue enchufado.",
                f"¡Grande {drv}! En el muro estamos todos aplaudiendo, mantén la cabeza fría.",
                f"¡Espectacular {drv}! Eso son manos de campeón, ni un milímetro de margen.",
            ])

        # ------------------------------------------------------------------
        # 6. PLANES DE CARRERA (PLAN A, PLAN B, PLAN C - CONSULTAR O CAMBIAR)
        # ------------------------------------------------------------------
        # ¿Quiere activar, consultar uno, o consultar todos los planes (Plan A, B, C)?
        plan_matches = list(dict.fromkeys(m.upper() for m in re.findall(r"\bplan\s*([abc])\b", norm)))
        switching_plan = any(
            w in norm
            for w in (
                "pasar", "pasamos", "pasa", "podemos", "vamos", "ir al", "cambia", "cambiar",
                "cambiamos", "activa", "activar", "activamos", "pon", "poner", "ponemos",
                "usar", "usamos", "hacemos", "hacer", "prefiero", "confirmado",
                "switch", "activate", "go to", "do plan", "use plan",
            )
        )
        asking_all_plans = len(plan_matches) > 1 or any(
            k in norm for k in ("planes", "que planes", "cuales son", "definir planes", "what plans", "our plans", "what are plan")
        )
        if len(plan_matches) == 1 and not asking_all_plans:
            letter = plan_matches[0]
            plan_desc_es = {"A": rep.plan_a_es, "B": rep.plan_b_es, "C": rep.plan_c_es}[letter]
            plan_desc_en = {"A": rep.plan_a_en, "B": rep.plan_b_en, "C": rep.plan_c_en}[letter]
            if switching_plan or len(words) <= 4:
                self.active_plan = letter
                pinfo = apply_plan_to_game_and_strategy(
                    letter,
                    self.cfg,
                    rep.current_lap,
                    rep.total_laps,
                    rep.pit_window_ideal,
                    rep.current_tyre,
                    rep.rain_forecast_pct,
                )
                rep = analyze_strategy(state, self.cfg.driver_name)
                if letter == "B" and rep.laps_remaining >= 2:
                    self.spotter.order_box_now(pinfo["pit_lap"])
                if lang == "en":
                    return (
                        f"Copy {drv}, switching pit wall and MFD to Plan {letter} now! "
                        f"New target pit stop is Lap {pinfo['pit_lap']} for {pinfo['comp']} tyres, ERS set to {pinfo['ers']}. {plan_desc_en}"
                    )
                return (
                    f"¡Recibido {drv}, activamos el Plan {letter} en la pizarra y en el MFD del coche! "
                    f"He reajustado tu parada a la vuelta {pinfo['pit_lap']} para montar neumático {pinfo['comp_es']} y el mapa de ERS en modo {pinfo['ers_es']}. {plan_desc_es}"
                )
            if lang == "en":
                return f"{plan_desc_en} Right now our active strategy is Plan {self.active_plan}. Tell me if you want to switch."
            return f"{plan_desc_es} Ahora mismo tenemos activo el Plan {self.active_plan} en pizarra; dime si quieres que cambiemos."

        if asking_all_plans or any(k in norm for k in ("plan a", "plan b", "plan c")):
            if lang == "en":
                return (
                    f"Here are our three options on the pit wall {drv}, currently on Plan {self.active_plan}. "
                    f"{rep.plan_a_en} {rep.plan_b_en} And {rep.plan_c_en}"
                )
            return (
                f"Te resumo las tres pizarras del muro {drv}, ahora mismo vamos con el Plan {self.active_plan}. "
                f"{rep.plan_a_es} {rep.plan_b_es} Y {rep.plan_c_es}"
            )

        # ------------------------------------------------------------------
        # 6B. CAMBIO DE PERSONALIDAD DEL INGENIERO POR VOZ (GP, BONO, FERRARI, CAÑERO)
        # ------------------------------------------------------------------
        if any(k in norm for k in ("modo ferrari", "estilo ferrari", "ferrari mode", "modo gp", "estilo red bull", "gp mode", "modo bono", "estilo mercedes", "bono mode", "modo canero", "modo sargento", "modo normal", "modo estandar")):
            if "ferrari" in norm:
                self.cfg.engineer_persona = "ferrari"
                self.cfg.save()
                return "Copy, Maranello pit wall mode active. We are checking telemetry, Plan A or Plan E available, question?" if lang == "en" else "Recibido desde Maranello, modo Ferrari activado en el muro. Estamos comprobando telemetría, checking... ¿pregunta?"
            if "gp" in norm or "red bull" in norm:
                self.cfg.engineer_persona = "gp"
                self.cfg.save()
                return f"GP Red Bull mode active {drv}. Less talking on the radio and more apex speed, copy." if lang == "en" else f"Modo GP Red Bull activado {drv}. Menos charla por la radio y más velocidad de paso por curva, copy."
            if "bono" in norm or "mercedes" in norm:
                self.cfg.engineer_persona = "bono"
                self.cfg.save()
                return f"Bono mode online {drv}. Get in there, it's Hammer Time!" if lang == "en" else f"Modo Bono activado {drv}. ¡Es hora del Hammer Time, vamos a por todas!"
            if "canero" in norm or "sargento" in norm:
                self.cfg.engineer_persona = "canero"
                self.cfg.save()
                return f"Hardcore Sergeant mode active {drv}! No excuses now, flat out!" if lang == "en" else f"¡Modo Sargento Cañero activado {drv}! Cero excusas en el cockpit, quiero el pie a tabla."
            self.cfg.engineer_persona = "balanced"
            self.cfg.save()
            return f"Standard race engineer mode restored {drv}, copy." if lang == "en" else f"Modo ingeniero estándar restaurado en el muro {drv}, copy."

        # ------------------------------------------------------------------
        # 6C. COMANDOS DE VOZ PARA EL MFD DEL JUEGO (SIN SOLTAR EL VOLANTE)
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "solicita box", "solicitar box", "pide box", "pedir box", "pide parada",
                "confirma box", "confirmo box", "avisa a los mecanicos", "prepara el box",
                "request pit", "request box", "confirm box", "call the pit crew",
            )
        ):
            if self.cfg.mfd_enabled:
                tap_key(self.cfg.mfd_box_key)
            self.spotter.order_box_now(rep.current_lap)
            if lang == "en":
                return (
                    f"Copy {drv}, pit stop requested on the MFD and the crew is getting the {rep.recommended_compound} tyres out of the blankets! Box this lap, predicted rejoin is P{rep.predicted_rejoin_pos}."
                )
            return (
                f"¡Recibido {drv}, parada solicitada en el MFD y los mecánicos ya están sacando las mantas del neumático {rep.recommended_compound_es}! Entra en esta vuelta, saldremos en torno a P{rep.predicted_rejoin_pos}."
            )

        if any(
            k in norm
            for k in (
                "prepara neumatico", "preparame neumatico", "prepara goma", "ponme neumatico",
                "quiero montar", "montar blando", "montar medio", "montar duro", "montar intermedio",
                "select soft", "select medium", "select hard", "select inter", "prepare soft",
                "prepare medium", "prepare hard", "prepare inter",
            )
        ):
            if self.cfg.mfd_enabled:
                tap_key(self.cfg.mfd_tyre_key)
            chosen_es = rep.recommended_compound_es
            chosen_en = rep.recommended_compound
            for c_es, c_en in (("blando", "Soft"), ("medio", "Medium"), ("duro", "Hard"), ("intermedio", "Intermediate"), ("lluvia", "Wet")):
                if c_es in norm or c_en.lower() in norm:
                    chosen_es, chosen_en = c_es, c_en
                    break
            if lang == "en":
                return f"Understood {drv}, cycling MFD tyre compound to {chosen_en}s for the next stop. The pit crew has the {chosen_en} set ready."
            return f"Copiado {drv}, seleccionando compuesto {chosen_es} en el MFD para tu próxima parada. Los mecánicos ya tienen preparado el juego de {chosen_es}s."

        if any(
            k in norm
            for k in (
                "sube el reparto", "subir reparto", "reparto hacia delante", "mas freno delante",
                "baja el reparto", "bajar reparto", "reparto hacia atras", "mas freno detras",
                "brake bias forward", "brake bias up", "brake bias rearward", "brake bias down",
            )
        ):
            going_up = any(w in norm for w in ("sube", "subir", "delante", "forward", "up"))
            if self.cfg.mfd_enabled:
                tap_key(self.cfg.mfd_brake_up_key if going_up else self.cfg.mfd_brake_down_key)
            new_bb = min(70, rep.brake_bias + 1) if going_up else max(50, rep.brake_bias - 1)
            if lang == "en":
                return f"Copy {drv}, adjusting MFD brake bias {'forward' if going_up else 'rearward'} to {new_bb} percent."
            return f"Recibido {drv}, ajustando el reparto de frenada en el MFD un punto hacia {'delante' if going_up else 'atrás'}, al {new_bb} por ciento."

        # ------------------------------------------------------------------
        # 6D. COMPARATIVA DE SECTORES S1 / S2 / S3 ("¿DONDE PIERDO O GANO TIEMPO?")
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "donde pierdo", "donde estoy perdiendo", "donde gano", "donde me saca",
                "como van mis sectores", "mis sectores", "mis parciales", "comparar sectores",
                "en que sector", "sector 1", "sector 2", "sector 3",
                "where am i losing", "where do i lose", "how are my sectors", "sector splits", "compare sectors",
            )
        ):
            me_r = next((r for r in standings if r.get("is_player")), None)
            target_r = self._match_rival_in_standings(norm, words, standings)
            if target_r is None:
                if "lider" in norm or "leader" in norm or "primero" in norm:
                    target_r = standings[0] if standings else None
                else:
                    target_r = next((r for r in standings if r["pos"] == rep.position - 1), None) or (standings[0] if standings else None)
            if target_r and me_r and not target_r.get("is_player"):
                return compare_car_sectors(me_r, target_r, rep, lang=lang)
            return rep.sector_comparison_en if lang == "en" else rep.sector_comparison_es

        # ------------------------------------------------------------------
        # 6E. DETECTOR DE CROSSOVER DE LLUVIA / INTERMEDIOS VS SLICKS
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "crossover", "momento de intermedios", "pongo intermedios", "poner intermedios",
                "para intermedios", "pista para secos", "se ha secado", "quien lleva intermedios",
                "time for inters", "switch to inters", "box for inters", "dry line", "who is on inters",
            )
        ):
            return rep.crossover_summary_en if lang == "en" else rep.crossover_summary_es

        # ------------------------------------------------------------------
        # 6F. DEBRIEFING / RESUMEN DE CARRERA Y POSICIONES GANADAS EN SALIDA
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "resumen de la carrera", "resumen de carrera", "debrief", "debriefing",
                "cuantas posiciones he ganado", "posiciones desde la salida", "en que posicion sali",
                "race debrief", "race summary", "positions gained", "where did i start",
            )
        ):
            return rep.debrief_en if lang == "en" else rep.debrief_es

        # ------------------------------------------------------------------
        # 7. ORDENES DE EQUIPO / COMPAÑERO DE EQUIPO ("DEJO ADELANTAR A MI COMPAÑERO", "MULTI 21")
        # ------------------------------------------------------------------
        if any(k in norm for k in ("companero", "compañero", "teammate", "el otro coche", "ordenes de equipo", "team orders", "multi 21", "swap positions", "invert the cars")):
            is_team_order_q = any(
                k in norm
                for k in (
                    "adelantar", "dejo", "pasar", "pase", "beneficio", "beneficios",
                    "ordenes", "intercambiar", "invertir", "swap", "let him", "pass", "orders", "multi",
                )
            )
            if rep.teammate_pos > 0:
                if is_team_order_q:
                    pos_diff = rep.teammate_pos - rep.position
                    if pos_diff == 1:
                        # El companero va justo detras (p.ej. tu P4, el P5)
                        if lang == "en":
                            return (
                                f"{rep.teammate_name} is right behind you in P{rep.teammate_pos}. If he has fresher rubber, we can swap positions on the main straight so he can attack {rep.ahead_name}, and if he doesn't make it stick he gives the place back before the flag."
                            )
                        return (
                            f"Tienes a tu compañero {rep.teammate_name} justo detrás en la posición {rep.teammate_pos}. Si ves que viene con mejor ritmo de gomas, puedes dejarle pasar en la recta para que intente cazar a {rep.ahead_name}, y si no lo consigue nos devuelve la posición antes de meta."
                        )
                    if pos_diff == -1:
                        # El companero va justo delante (p.ej. el P3, tu P4)
                        if lang == "en":
                            return (
                                f"We are talking to {rep.teammate_name}'s engineer across the pit wall right now. Close the gap under one second and we will call team orders so he lets you through cleanly."
                            )
                        return (
                            f"Ya estamos hablando con el ingeniero de {rep.teammate_name} al otro lado del muro. Pégate a menos de un segundo y daremos orden de equipo para que no te defienda y te deje pasar limpio."
                        )
                    # Hay coches rivales entre medias (como en el log del usuario: P4 vs P8)
                    cars_between = max(1, abs(pos_diff) - 1)
                    if pos_diff > 1:
                        if lang == "en":
                            return (
                                f"Negative on team orders right now {drv}! You are P{rep.position} and {rep.teammate_name} is back in P{rep.teammate_pos} at {rep.teammate_gap} with {cars_between} rival cars between you. Dropping back would gift free points to our rivals, keep pushing!"
                            )
                        return (
                            f"¡Negativo, ni hablar de dejar pasar a {rep.teammate_name} ahora mismo {drv}! Tú ruedas en posición {rep.position} y él está atrás en el puesto {rep.teammate_pos} a {rep.teammate_gap}, con {cars_between} rivales entre vosotros. Regalaríamos posiciones gratis a otras escuderías, ¡tú tira hacia delante!"
                        )
                    if lang == "en":
                        return (
                            f"{rep.teammate_name} is way up in P{rep.teammate_pos} with {cars_between} cars between you and him. Clear the traffic ahead first and then we'll review team orders."
                        )
                    return (
                        f"{rep.teammate_name} está delante en el puesto {rep.teammate_pos} con {cars_between} coches entre medias. Quítate primero el tráfico de delante y luego vemos si invertimos posiciones."
                    )

                if lang == "en":
                    return self._pick("mate_en", [
                        f"Your teammate {rep.teammate_name} in the other {rep.player_team} is currently P{rep.teammate_pos}, {rep.teammate_gap} off the leader.",
                        f"{rep.teammate_name} is running in P{rep.teammate_pos} right now at {rep.teammate_gap}, while you are P{rep.position}.",
                    ])
                return self._pick("mate_es", [
                    f"Tu compañero {rep.teammate_name} con el otro {rep.player_team} rueda ahora mismo en la posición {rep.teammate_pos}, a {rep.teammate_gap} del líder.",
                    f"Ahora mismo {rep.teammate_name} está en el puesto {rep.teammate_pos} a {rep.teammate_gap} de cabeza, mientras tú ruedas en posición {rep.position}.",
                ])
            if lang == "en":
                return f"We don't have telemetry on the second {rep.player_team} car right now, focus on your P{rep.position}."
            return f"Ahora mismo no tengo señal de telemetría del segundo coche de {rep.player_team}, tú céntrate en tu posición {rep.position}."

        # ------------------------------------------------------------------
        # 8. ¿QUE COCHE / EQUIPO / PILOTO LLEVO?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("que coche", "que equipo", "escuderia", "monoplaza llevo", "coche llevo", "quien soy", "que piloto soy", "mi coche", "what car", "what team", "who am i")):
            drv_tag = f" de {rep.player_driver}" if rep.player_driver and rep.player_driver.upper() != drv.upper() else ""
            if lang == "en":
                return self._pick("car_en", [
                    f"You are driving the {rep.player_team} car ({rep.player_driver}), currently running P{rep.position} of {rep.total_cars} on {rep.current_tyre} tyres. {rep.damage_summary_en}",
                    f"You're at the wheel of the {rep.player_team}, P{rep.position} on track with {rep.ers_pct} percent battery and {rep.current_tyre} tyres.",
                ])
            return self._pick("car_es", [
                f"Estás al volante del {rep.player_team}{drv_tag}, rodando en la posición {rep.position} de {rep.total_cars} con goma {rep.current_tyre_es} de {rep.tyre_age} vueltas. {rep.damage_summary_es}",
                f"Conduces el {rep.player_team}{drv_tag}, ahora mismo en el puesto {rep.position} de carrera con neumático {rep.current_tyre_es} y batería al {rep.ers_pct} por ciento.",
            ])

        # ------------------------------------------------------------------
        # 9. CONSULTA DE PILOTO RIVAL: ¿CUANDO HA PARADO X? / ¿CUANDO PARARA X? / ESTADO DE X
        # ------------------------------------------------------------------
        rival_row = self._match_rival_in_standings(norm, words, standings)
        asking_rival_pit_hist = any(
            k in norm
            for k in (
                "cuando ha parado", "ha parado", "en que vuelta ha parado", "hizo la parada",
                "cuantas paradas lleva", "paradas lleva", "when did", "has he pitted",
                "did he pit", "how many stops",
            )
        )
        asking_rival_pit_pred = any(
            k in norm
            for k in (
                "cuando crees que parara", "cuando parara", "cuando va a parar", "en que vuelta parara",
                "en que vuelta va a parar", "volvera a parar", "va a parar", "when will",
                "when do you think", "going to pit", "going to box", "will he pit", "will he box",
            )
        )
        # Si pregunta "cuando ha parado el de delante / lider / detras" sin decir el nombre propio
        if rival_row is None and (asking_rival_pit_hist or asking_rival_pit_pred):
            if any(k in norm for k in ("delante", "ahead", "in front")):
                rival_row = next((r for r in standings if r["pos"] == rep.position - 1), None)
            elif any(k in norm for k in ("detras", "behind")):
                rival_row = next((r for r in standings if r["pos"] == rep.position + 1), None)
            elif any(k in norm for k in ("lider", "primero", "leader", "p1")):
                rival_row = standings[0] if standings else None

        if rival_row is not None:
            if rival_row.get("is_player") and not (asking_rival_pit_hist or asking_rival_pit_pred):
                if lang == "en":
                    return f"That's your car {drv}! You are P{rep.position} in the {rep.player_team}, ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds."
                return f"¡Ese eres tú con el {rep.player_team}, {drv}! Vas en posición {rep.position}, con {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} segundos."

            r_info = analyze_rival_pit_and_status(rival_row, rep, lang=lang)
            if asking_rival_pit_hist and asking_rival_pit_pred:
                return f"{r_info['history']} {r_info['prediction']}"
            if asking_rival_pit_hist:
                return f"{r_info['history']} {r_info['prediction']}"
            if asking_rival_pit_pred:
                return f"{r_info['prediction']} ({r_info['history']})"
            return r_info["full"]

        # ------------------------------------------------------------------
        # 10. QUEJAS DE INCIDENTE / TOQUE / BANDERAS AZULES / AIRE SUCIO / TRAFICO
        # ------------------------------------------------------------------
        if any(k in norm for k in ("me ha chocado", "me han chocado", "me ha tocado", "me ha dado", "me ha empujado", "me ha echado", "me ha cerrado", "has visto eso", "que hace este", "incident", "hit me", "pushed me", "turned in on me")):
            if lang == "en":
                return self._pick("inc_en", [
                    f"We saw that on the pit wall cameras {drv}, we are reporting it to the stewards right now. {rep.damage_summary_en} Keep your head cool.",
                    f"Unbelievable driving from him, we have sent the telemetry clip to Race Control. {rep.damage_summary_en} Settle back into your rhythm.",
                ])
            return self._pick("inc_es", [
                f"Lo hemos visto por las cámaras del muro {drv}, ya nos estamos quejando a dirección de carrera. {rep.damage_summary_es} Cabeza fría y devuélvesela en pista.",
                f"Menuda maniobra más sucia te ha hecho, ya lo hemos reportado a los comisarios. {rep.damage_summary_es} No entres al trapo y céntrate en tu ritmo.",
            ])

        if any(k in norm for k in ("bandera azul", "banderas azules", "doblado", "doblados", "no se aparta", "trafico", "blue flag", "blue flags", "backmarker", "traffic")):
            if lang == "en":
                return (
                    f"We are on to Race Control about the blue flags right now {drv}. Stay patient through the corners and pass him safely on the next straight."
                )
            return (
                f"Ya estamos reclamando las banderas azules a dirección de carrera desde el muro, {drv}. No arriesgues el alerón en curva y pásale en la recta."
            )

        if any(k in norm for k in ("aire sucio", "tren de drs", "se calienta detras", "dirty air", "drs train")):
            if lang == "en":
                return (
                    f"You are in dirty air behind {rep.ahead_name}, tyre temps are at {rep.max_tyre_temp} degrees. Pull out of his wake on the straights to cool the brakes and consider switching to Plan B undercut."
                )
            return (
                f"Estás comiéndote todo el aire sucio de {rep.ahead_name} y las gomas van a {rep.max_tyre_temp} grados. Sal un poco de su rebufo en recta para refrigerar o dime si activamos el Plan B para hacerle el undercut."
            )

        # ------------------------------------------------------------------
        # 11. QUEJAS DEL COCHE / MANEJO Y ENERGIA (AUTO-MFD IA SEGUN CIRCUITO, NEUMATICO Y TIEMPO)
        # ------------------------------------------------------------------
        understeer_q = any(
            k in norm
            for k in (
                "cuesta girar", "no gira", "subviraje", "se va de delante", "no entra el morro",
                "entra el morro", "me voy recto", "morro", "understeer", "won't turn", "wont turn", "cant turn",
            )
        )
        oversteer_q = any(
            k in norm
            for k in (
                "sobreviraje", "se va de atras", "patina", "desliza", "pierdo la trasera",
                "culo", "cuesta traccionar", "traccion", "oversteer", "sliding", "wheelspin", "rear is loose",
            )
        )
        poor_braking_q = any(
            k in norm
            for k in (
                "frena poco", "no frena", "cuesta frenar", "me voy largo", "paso de frenada",
                "bloqueo", "bloqueando", "frenos calientes", "frenos frios", "cant stop",
                "can't stop", "locking up", "braking is poor", "no brakes",
            )
        )
        more_power_q = any(
            k in norm
            for k in (
                "necesito mas energia", "mas energia", "dame energia", "mas potencia",
                "dame potencia", "no corre", "falta velocidad", "modo ataque", "necesito bateria",
                "need more energy", "more power", "need power", "no top speed",
            )
        )
        save_battery_q = any(
            k in norm
            for k in (
                "ahorrar bateria", "ahorrar energia", "recargar bateria", "cargar bateria",
                "sin bateria", "me quedo sin bateria", "save battery", "harvest energy",
            )
        )
        general_setup_q = any(
            k in norm
            for k in ("no tengo agarre", "sin agarre", "reglaje", "setup", "diferencial", "no grip", "balance")
        )

        if understeer_q or oversteer_q or poor_braking_q or more_power_q or save_battery_q or general_setup_q:
            if understeer_q:
                issue_code = "understeer"
            elif oversteer_q:
                issue_code = "oversteer"
            elif poor_braking_q:
                issue_code = "poor_braking"
            elif more_power_q:
                issue_code = "more_power"
            elif save_battery_q:
                issue_code = "save_battery"
            else:
                issue_code = "understeer" if "FL" in rep.worst_wheel or "FR" in rep.worst_wheel else "oversteer"
            return diagnose_and_tune_car(issue_code, rep, self.cfg, lang=lang)

        # ------------------------------------------------------------------
        # 12. ¿QUIEN VA EN UNA POSICION CONCRETA? ("quien va segundo / tercero / P1 / ultimo...")
        # ------------------------------------------------------------------
        if any(q in norm for q in ("quien va", "quien esta", "quien es el", "quien lidera", "who is in", "who is p", "who's in", "who leads", "segunda posicion", "tercera posicion", "primera posicion", "cuarta posicion", "quinta posicion", "ultimo", "last place")) and not any(
            f in norm for f in ("delante", "detras", "in front", "ahead", "behind")
        ):
            if "ultimo" in norm or "last place" in norm:
                last_r = standings[-1]
                if lang == "en":
                    return f"Running last in P{last_r['pos']} is {last_r['name']} in the {last_r['team']}, {last_r['gap_leader']} behind the leader."
                return f"Cerrando la parrilla en la posición {last_r['pos']} rueda {last_r['name']} con el {last_r['team']}, a {last_r['gap_leader']} de la cabeza."
            target_pos = 1 if ("lidera" in norm or "leads" in norm) else None
            if target_pos is None:
                for word, pnum in ORDINAL_MAP.items():
                    if word in words or word in norm:
                        target_pos = pnum
                        break
            if target_pos is not None:
                row = next((r for r in standings if r["pos"] == target_pos), None)
                if row:
                    if row.get("is_player"):
                        if lang == "en":
                            return f"That is you {drv}! You are running in P{target_pos} right now, ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds."
                        return f"¡En la posición {target_pos} vas tú mismo con el {rep.player_team}, {drv}! Tienes a {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} segundos."
                    r_info = analyze_rival_pit_and_status(row, rep, lang=lang)
                    return r_info["full"]

        # ------------------------------------------------------------------
        # 13. ABANDONOS / COCHES FUERA / RETIRADOS / DNFs ("cuántos coches están fuera", "quién ha roto")
        # ------------------------------------------------------------------
        if any(k in norm for k in (
            "fuera", "abandonado", "abandono", "abandonos", "retirado", "retirados",
            "cuantos coches quedan", "quedan en pista", "quien se ha salido", "se salio",
            "ha roto", "quien no sigue", "quien falta", "dnf", "dnfs", "retired", "out of the race",
            "who is out", "how many cars out", "any retirements", "anyone out", "cars out", "quien abandono"
        )):
            ret_list = list(rep.retired_names)
            for r in standings:
                if r.get("status") in ("DNF", "DSQ", "retired", "not classified") and r.get("name") not in ret_list:
                    ret_list.append(r["name"])

            if ret_list:
                rlist = ", ".join(ret_list)
                if lang == "en":
                    return f"We have {len(ret_list)} cars out of the race {drv}: {rlist} are DNF."
                return f"Llevamos {len(ret_list)} coches fuera de carrera {drv}: han abandonado {rlist}."
            if lang == "en":
                return f"All {rep.total_cars} cars are still running on track {drv}, zero retirements so far."
            return f"Siguen los {rep.total_cars} coches en pista {drv}, de momento no hay ningún coche fuera ni abandonos."

        # ------------------------------------------------------------------
        # 14. LÍDER / QUIÉN VA PRIMERO / P1 ("quién va ganando", "quién lidera")
        # ------------------------------------------------------------------
        if any(k in norm for k in ("quien va primero", "quien lidera", "quien va en cabeza", "quien es el lider", "quien va p1", "quien va ganando", "who is p1", "who is leading", "who leads")):
            p1_r = next((r for r in standings if r["pos"] == 1), standings[0] if standings else None)
            if p1_r:
                if p1_r.get("is_player"):
                    if lang == "en":
                        return f"You are leading the race {drv}! P1 is yours, keep your rhythm and control the gap."
                    return f"¡Vas liderando la carrera, {drv}! Ruedas en P1 con el {rep.player_team}, mantén el ritmo y gestiona la distancia."
                if lang == "en":
                    return f"P1 is currently {p1_r['name']} in the {p1_r['team']}, leading the race."
                return f"En primera posición va {p1_r['name']} con el {p1_r['team']}, liderando la carrera."

        # ------------------------------------------------------------------
        # 14b. QUIÉN VIENE DETRÁS / GAP DETRÁS / DISTANCIA POR DETRÁS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("quien viene detras", "quien tengo detras", "quien va detras", "a cuanto esta el de detras", "cuanto le saco", "distancia con el de detras", "gap detras", "me recortan", "me recorta", "quien me persigue", "who is behind", "who is behind me", "gap behind")):
            if behind_row:
                b_name = behind_row['name']
                b_gap = abs(rep.behind_gap_s)
                if lang == "en":
                    return f"Behind you is {b_name} in P{behind_row['pos']} at {b_gap:.1f} seconds. Keep your exits clean."
                return f"Detrás tienes a {b_name} en posición {behind_row['pos']} a {b_gap:.1f} segundos. Concéntrate en la tracción y sal limpio."
            if lang == "en":
                return f"You have clear track behind you {drv}, no cars threatening from the rear."
            return f"Tienes la pista completamente libre por detrás {drv}, no hay nadie pegado a ti."

        # ------------------------------------------------------------------
        # 14c. QUIÉN VA DELANTE / GAP DELANTE / DISTANCIA POR DELANTE
        # ------------------------------------------------------------------
        if any(k in norm for k in ("quien va delante", "quien tengo delante", "a cuanto esta el de delante", "cuanto le recorto", "distancia con el de delante", "gap delante", "a cuanto estoy", "who is ahead", "who is in front", "gap ahead")):
            if ahead_row:
                a_name = ahead_row['name']
                a_gap = rep.ahead_gap_s
                drs_note = " Tienes zona de DRS disponible." if a_gap <= 1.0 else ""
                if lang == "en":
                    return f"Ahead is {a_name} in P{ahead_row['pos']} at {a_gap:.1f} seconds.{' DRS is available.' if a_gap <= 1.0 else ''}"
                return f"Delante tienes a {a_name} en posición {ahead_row['pos']} a {a_gap:.1f} segundos.{drs_note}"
            if lang == "en":
                return f"You are P1 {drv}, clean air ahead to the chequered flag!"
            return f"¡Vas en primera posición {drv}! Aire limpio por delante, sigue tirando hasta la bandera."

        # ------------------------------------------------------------------
        # 14d. REPARTO DE FRENADA / BALANCE Y DIFERENCIAL (CONSEJO DE INGENIERO)
        # ------------------------------------------------------------------
        if any(k in norm for k in ("reparto de frenada", "reparto de freno", "balance de frenos", "que reparto pongo", "reparto frenada", "freno", "frenada", "brake bias")):
            bias = 56 if rep.max_wear_pct < 40 else 57
            if lang == "en":
                return f"For this stint {drv}, keep brake bias at {bias}% forward to protect rear tyre stability under braking."
            return f"Para este sector te recomiendo poner el reparto de frenada al {bias}% hacia delante {drv}, así evitas que bloquee el eje trasero."

        if any(k in norm for k in ("diferencial", "que diferencial pongo", "ajuste diferencial", "differential")):
            diff = 55 if rep.max_wear_pct > 35 else 60
            if lang == "en":
                return f"Set on-throttle differential to {diff}% {drv}, gives smooth traction on exit without killing the rear tyres."
            return f"Pon el diferencial de aceleración en torno al {diff}% {drv}, te dará tracción progresiva en las salidas sin castigar las gomas."

        # ------------------------------------------------------------------
        # 14e. RADIO CHECKS Y CONFIRMACIONES TÍPICAS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("radio check", "me recibes", "me escuchas", "probando radio", "comprobacion de radio")):
            if lang == "en":
                return f"Loud and clear {drv}, radio five by five! The car is looking good on telemetry, keep pushing!"
            return f"¡Cinco de cinco {drv}, te recibo alto y claro desde el muro! La telemetría marca todo en orden, a por ellos."

        if any(k in norm for k in ("entendido", "copiado", "recibido", "roger", "copy that")) and len(norm.split()) <= 4:
            if lang == "en":
                return f"Copy that {drv}, head down and keep your rhythm."
            return f"Copiado {drv}, cabeza fría, clava los vértices y sigue empujando."

        # ------------------------------------------------------------------
        # 14f. PODIO / TOP 3 / PUNTOS / TOP 10
        # ------------------------------------------------------------------
        if any(k in norm for k in ("podio", "podium", "top 3", "tres primeros", "tres primeras")):
            top3 = standings[:3]
            p3_names = ", ".join(f"P{r['pos']} {r['name']}" for r in top3)
            if rep.position <= 3:
                if lang == "en":
                    return f"You are inside the podium positions right now in P{rep.position}! Top three are {p3_names}. Keep pushing!"
                return f"¡Ya estás metido en puestos de podio en la posición {rep.position}, {drv}! El podio ahora mismo es {p3_names}. ¡Defiéndelo a muerte!"
            if lang == "en":
                return f"The podium right now is {p3_names}. You are P{rep.position}, {rep.podium_gap_s:.1f} seconds away from P3."
            return f"El podio provisional lo forman {p3_names}. Tú ruedas en posición {rep.position}, tienes el tercer cajón del podio a {rep.podium_gap_s:.1f} segundos."

        if any(k in norm for k in ("puntos", "zona de puntos", "top 10", "diez primeros", "points")):
            p10_r = next((r for r in standings if r["pos"] == 10), standings[-1])
            if rep.position <= 10:
                if lang == "en":
                    return f"Yes {drv}, you are solidly in the points in P{rep.position}! {p10_r['name']} closes the top ten."
                return f"Sí {drv}, estás dentro de la zona de puntos rodando en posición {rep.position}. El décimo puesto que cierra los puntos lo lleva {p10_r['name']}."
            if lang == "en":
                return f"You are currently P{rep.position}, outside the points by {rep.position - 10} positions and {rep.points_gap_s:.1f} seconds behind P10 {p10_r['name']}."
            return f"Ahora mismo estás fuera de los puntos en la posición {rep.position}. Tienes el décimo puesto de {p10_r['name']} a {rep.points_gap_s:.1f} segundos y {rep.position - 10} coches por delante."

        # ------------------------------------------------------------------
        # 15. ¿LE RECORTAMOS / EN CUANTAS VUELTAS LE PILLO / COMPARACION DE RITMO?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("recorto", "recortando", "pillo", "pillar", "alcanzar", "alcanzo", "cazar", "mas rapido", "mas lento", "catching", "catch", "faster", "slower")):
            if lang == "en":
                return self._pick("pace_en", [
                    f"{rep.pace_analysis_en} Your last lap was {rep.last_lap_str} against {rep.ahead_name}'s {rep.ahead_last_lap}.",
                    f"Looking at sector deltas, {rep.pace_analysis_en}",
                ])
            return self._pick("pace_es", [
                f"{rep.pace_analysis_es} Tu última vuelta ha sido {rep.last_lap_str} frente al {rep.ahead_last_lap} de {rep.ahead_name}.",
                f"Comparando telemetrías en el muro, {rep.pace_analysis_es.lower()}",
            ])

        # ------------------------------------------------------------------
        # 16. ¿COMO LE ADELANTO / DONDE ATACO / COMO ME DEFIENDO?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("ataco", "atacar", "adelanto", "adelantar", "defiendo", "defender", "attack", "defend", "overtake")):
            if lang == "en":
                return self._pick("atk_en", [
                    f"You have {rep.ers_pct} percent battery. Save ERS through the twisty section, get a clean exit onto the main straight, and hit Overtake with DRS on {rep.ahead_name}.",
                    f"Focus on traction out of the last corner before the DRS detection zone. {rep.ahead_name} is {rep.ahead_gap_s:.1f} ahead on {rep.ahead_tyre}.",
                ])
            return self._pick("atk_es", [
                f"Tienes un {rep.ers_pct} por ciento de batería. Recarga en las zonas reviradas, tracciona limpio al salir a la recta principal y vacía el botón de adelantamiento con DRS sobre {rep.ahead_name}.",
                f"Para pasar a {rep.ahead_name}, sacrifica un poco la entrada de la curva previa a la zona de DRS para salir con mucha más tracción que él. Lo tienes a {rep.ahead_gap_s:.1f} segundos.",
            ])

        # ------------------------------------------------------------------
        # 17. TIEMPOS DE VUELTA / ULTIMA VUELTA HECHA / MEJOR VUELTA / CRONO
        #     (Importante: evaluado ANTES de vueltas restantes para capturar "que tiempo he hecho en la ultima vuelta")
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "tiempo de vuelta", "ultimo tiempo", "mejor vuelta", "vuelta rapida",
                "que tiempo he", "que tiempo hecha", "tiempo en la ultima", "tiempo de la ultima",
                "crono", "ritmo", "sector", "sectores", "lap time", "last lap time",
                "best lap", "fastest lap", "pace",
            )
        ):
            if lang == "en":
                return self._pick("laptime_en", [
                    f"Your last lap was {rep.last_lap_str}, and your personal best is {rep.best_lap_str}. Ahead, {rep.ahead_name} just did a {rep.ahead_last_lap}.",
                    f"Stopwatch check, you crossed the line in {rep.last_lap_str}. Behind you, {rep.behind_name} clocked a {rep.behind_last_lap}. {rep.pace_analysis_en}",
                ])
            return self._pick("laptime_es", [
                f"Tu último paso por meta ha sido {rep.last_lap_str}, y tu mejor vuelta de la sesión es {rep.best_lap_str}. Delante, {rep.ahead_name} ha rodado en {rep.ahead_last_lap}.",
                f"Mirando el crono, vienes de marcar un {rep.last_lap_str}. Por comparar, {rep.behind_name} detrás ha hecho {rep.behind_last_lap} en el último giro.",
                f"Acabas de cruzar meta en {rep.last_lap_str}, con un mejor registro personal de {rep.best_lap_str}. {rep.pace_analysis_es}",
            ])

        # ------------------------------------------------------------------
        # 18. NEUMATICOS / RUEDAS / DESGASTE / TEMPERATURAS
        #     (Incluye fix fonetico Vosk "lo mas rico" -> "neumatico", evaluado ANTES de "cuantas vueltas quedan")
        # ------------------------------------------------------------------
        if any(
            k in norm
            for k in (
                "neumatico", "neumaticos", "lo mas rico", "mas rico", "rueda", "ruedas",
                "goma", "gomas", "desgaste", "degradacion", "agarre", "temperatura",
                "temperaturas", "tyre", "tyres", "tire", "tires", "wear", "temp",
            )
        ):
            if lang == "en":
                return self._pick("tyre_en", [
                    f"Your {rep.current_tyre} tyres are {rep.tyre_age} laps old, peak wear is {rep.max_wear_pct:.0f} percent on the {rep.worst_wheel_en}, degrading at {rep.wear_per_lap:.1f} percent per lap. Around {rep.est_tyre_laps_left} good laps left.",
                    f"Tyre check, {rep.max_wear_pct:.0f} percent wear on the {rep.worst_wheel_en}, core temperature is {rep.max_tyre_temp} degrees. They will hold for another {rep.est_tyre_laps_left} laps.",
                ])
            return self._pick("tyre_es", [
                f"Llevas goma {rep.current_tyre_es} con {rep.tyre_age} vueltas, el mayor desgaste es del {rep.max_wear_pct:.0f} por ciento en la {rep.worst_wheel_es}. Te quedan unas {rep.est_tyre_laps_left} vueltas óptimas de neumático.",
                f"Revisando las gomas, tienes un {rep.max_wear_pct:.0f} por ciento de desgaste en la {rep.worst_wheel_es} y {rep.max_tyre_temp} grados de temperatura interna. Aguantan bien otras {rep.est_tyre_laps_left} vueltas.",
                f"Tus neumáticos {rep.current_tyre_es}s van por el {rep.max_wear_pct:.0f} por ciento de desgaste, degradando un {rep.wear_per_lap:.1f} por vuelta. Les quedan unos {rep.est_tyre_laps_left} giros buenos.",
            ])

        # ------------------------------------------------------------------
        # 19. COMBUSTIBLE / GASOLINA / MEZCLA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("combustible", "gasolina", "mezcla", "deposito", "tanque", "lift", "coast", "fuel", "mix")):
            if lang == "en":
                return self._pick("fuel_en", [
                    f"{rep.fuel_advice_en} We have {rep.fuel_kg:.1f} kilos in the tank.",
                    f"Fuel check, {rep.fuel_kg:.1f} kilograms remaining, margin is {rep.fuel_laps_margin:+.1f} laps to the finish.",
                ])
            return self._pick("fuel_es", [
                f"{rep.fuel_advice_es} Llevamos ahora mismo {rep.fuel_kg:.1f} kilos en el depósito.",
                f"Revisando el tanque, nos quedan {rep.fuel_kg:.1f} kilos de combustible, un margen de {rep.fuel_laps_margin:+.1f} vueltas respecto al objetivo.",
            ])

        # ------------------------------------------------------------------
        # 20. BATERIA / ERS / ENERGIA / FRENOS / SANCIONES
        # ------------------------------------------------------------------
        if any(k in norm for k in ("ers", "bateria", "energia", "mapa", "battery", "energy", "deploy")):
            if lang == "en":
                return f"ERS battery charge is at {rep.ers_pct} percent in {rep.ers_mode} deployment mode."
            return f"La batería del ERS está al {rep.ers_pct} por ciento de carga, llevas el mapa en modo {rep.ers_mode_es}."

        if any(k in norm for k in ("freno", "frenos", "reparto", "frenada", "brake", "brakes", "bias")):
            if lang == "en":
                return f"Brake bias is set to {rep.brake_bias} percent front, peak brake disc temperature is {rep.max_brake_temp} degrees. {rep.setup_advice_en}"
            return f"Llevas el reparto de frenada al {rep.brake_bias} por ciento delante, y los discos están a {rep.max_brake_temp} grados de pico. {rep.setup_advice_es}"

        if any(k in norm for k in ("sancion", "sanciones", "penalizacion", "aviso", "avisos", "limites", "penalty", "penalties", "warning", "warnings", "limits")):
            if lang == "en":
                return f"You have {rep.penalties_s} seconds of time penalties and {rep.warnings_count} track limit warnings so far."
            return f"Llevas {rep.penalties_s} segundos de sanción acumulada y {rep.warnings_count} avisos por límites de pista. Mantén dos ruedas dentro de la línea blanca."

        # ------------------------------------------------------------------
        # 21. COCHE DE DELANTE / DETRAS / GAPS / DRS ("who is in front of me" / "quien tengo delante")
        # ------------------------------------------------------------------
        if any(k in norm for k in ("delante", "detras", "distancia", "gap", "diferencia", "ahead", "in front", "front of me", "behind", "interval", "drs")):
            if lang == "en":
                return self._pick("gaps_en", [
                    f"You are P{rep.position}. Ahead of you is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds on {rep.ahead_tyre}, and behind is {rep.behind_name} at {rep.behind_gap_s:.1f} seconds.",
                    f"In front of you is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds, and in your mirrors {rep.behind_name} is {rep.behind_gap_s:.1f} back. {rep.pace_analysis_en}",
                ])
            return self._pick("gaps_es", [
                f"Vas en posición {rep.position}. Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos con {rep.ahead_tyre}, y por detrás viene {rep.behind_name} a {rep.behind_gap_s:.1f} segundos.",
                f"Tus referencias en pista son {rep.ahead_name} por delante a {rep.ahead_gap_s:.1f} segundos y {rep.behind_name} en tus retrovisores a {rep.behind_gap_s:.1f}. {rep.pace_analysis_es}",
            ])

        # ------------------------------------------------------------------
        # 22. ¿EN QUE POSICION VOY? / ¿COMO VOY?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("en que posicion", "que posicion voy", "que puesto voy", "en que puesto", "como voy", "como vamos", "posicion", "puesto", "what position am", "where am i")) and not any(
            k in norm for k in ("primera", "primeras", "primeros", "top", "cinco", "diez", "clasificacion", "tabla", "parrilla")
        ):
            if lang == "en":
                return self._pick("mypos_en", [
                    f"You are running in P{rep.position} of {rep.total_cars} right now in the {rep.player_team}, lap {rep.current_lap} of {rep.total_laps}. Ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds, behind is {rep.behind_name} at {rep.behind_gap_s:.1f}.",
                    f"Currently P{rep.position} {drv}. You have {rep.ahead_name} {rep.ahead_gap_s:.1f} seconds up the road and {rep.behind_name} {rep.behind_gap_s:.1f} behind you.",
                ])
            return self._pick("mypos_es", [
                f"Vas en la posición {rep.position} de {rep.total_cars} con el {rep.player_team}, vuelta {rep.current_lap} de {rep.total_laps}. Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos y detrás a {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Ruedas en el puesto {rep.position} ahora mismo {drv}. Tu referencia delante es {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, y por los espejos viene {rep.behind_name} a {rep.behind_gap_s:.1f}.",
            ])

        # ------------------------------------------------------------------
        # 23. ESTRATEGIA / ¿DEBERIA PARAR EN BOXES? / PROXIMA PARADA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("estrategia", "parar", "paro", "parada", "proxima parada", "boxes", "box", "pit", "ventana", "undercut", "overcut", "deberia", "entro", "entrar", "strategy", "window", "should", "stop", "lobbies")):
            if rep.total_laps <= 10 and rep.max_wear_pct < 65.0:
                if lang == "en":
                    return (
                        f"This is a {rep.total_laps}-lap sprint race {drv}, there are NO pit stops scheduled! "
                        f"Your {rep.current_tyre}s are only at {rep.max_wear_pct:.0f}% wear and easily go to the end. "
                        f"It is flat out to the flag, no stops needed!"
                    )
                return (
                    f"Esta es una carrera corta a {rep.total_laps} vueltas {drv}, ¡aquí NO hay parada en boxes programada! "
                    f"Tus neumáticos {rep.current_tyre_es}s van solo al {rep.max_wear_pct:.0f}% de desgaste y aguantan de sobra hasta el final. "
                    f"¡Es ir a fondo hasta la bandera a cuadros sin entrar a boxes!"
                )

            if rep.laps_remaining <= 2 and rep.total_laps >= 8:
                if lang == "en":
                    return f"Negative on boxing {drv}, only {rep.laps_remaining} laps remaining! Pitting now would throw away all our track position, stay out and bring it home!"
                return f"¡Negativo, no paramos {drv}! Quedan solo {rep.laps_remaining} vueltas para meta; entrar ahora sería regalar todas las posiciones. Quédate fuera y cruza la meta."

            if ("BOX" in rep.box_recommendation or rep.box_recommendation == "PIT WINDOW OPEN") and rep.total_laps > 10:
                self.spotter.order_box_now(rep.current_lap)
            if lang == "en":
                return self._pick("strat_en", [
                    f"Active Plan {self.active_plan} call is {rep.box_recommendation}. Ideal window is lap {rep.pit_window_ideal} to {rep.pit_window_latest}. {rep.rejoin_summary_en}",
                    f"Looking at the pit wall numbers on Plan {self.active_plan}, {rep.rejoin_summary_en} {rep.undercut_summary_en}",
                ])
            rec_map = {
                "STAY OUT": "mantenernos fuera en pista y alargar el stint",
                "PIT WINDOW OPEN": "ventana de parada abierta, podemos entrar en esta vuelta",
                "HOLD OUT FOR RAIN": "aguantar en pista esperando a que descargue la lluvia",
            }
            rec_es = rec_map.get(rep.box_recommendation, "entrar a boxes en esta misma vuelta")
            return self._pick("strat_es", [
                f"Bajo nuestro Plan {self.active_plan}, la orden es {rec_es}. La ventana ideal va de la vuelta {rep.pit_window_ideal} a la {rep.pit_window_latest}. {rep.rejoin_summary_es}",
                f"Mirando las simulaciones del Plan {self.active_plan}, te recomiendo {rec_es}. {rep.rejoin_summary_es} {rep.undercut_summary_es}",
            ])

        # ------------------------------------------------------------------
        # 24. ¿CUANTAS VUELTAS QUEDAN? / VUELTA ACTUAL
        # ------------------------------------------------------------------
        if any(k in norm for k in ("cuantas vueltas", "que vuelta", "queda", "quedan", "falta", "faltan", "ultima vuelta", "laps left", "remaining", "many laps", "what lap")):
            if rep.laps_remaining <= 1 and rep.total_laps >= 2 and rep.current_lap >= rep.total_laps:
                if lang == "en":
                    return f"This is the final lap {drv}, last lap! You are P{rep.position}, deploy everything to the line!"
                return f"¡Estás en la última vuelta {drv}, ya no queda nada! Vas en posición {rep.position}, vacía la batería hasta la bandera a cuadros."
            if lang == "en":
                return self._pick("laps_en", [
                    f"We are on lap {rep.current_lap} of {rep.total_laps}, so {rep.laps_remaining} laps to go. Tyres have about {rep.est_tyre_laps_left} good laps in them.",
                    f"{rep.laps_remaining} laps remaining up to the chequered flag, currently on lap {rep.current_lap} of {rep.total_laps}.",
                ])
            return self._pick("laps_es", [
                f"Estamos en la vuelta {rep.current_lap} de {rep.total_laps}, te quedan {rep.laps_remaining} vueltas hasta la bandera a cuadros.",
                f"Faltan {rep.laps_remaining} vueltas para terminar, vas por el giro {rep.current_lap} de {rep.total_laps} y las gomas aguantan otras {rep.est_tyre_laps_left} vueltas buenas.",
            ])

        # ------------------------------------------------------------------
        # 25. TOP 5 / PRIMERAS POSICIONES / CLASIFICACION GENERAL
        # ------------------------------------------------------------------
        if any(k in norm for k in ("primera", "primero", "primeros", "posiciones", "top", "clasificacion", "parrilla", "tabla", "standings", "positions", "five", "cinco", "lider", "leader")):
            top5 = standings[:5]
            if lang == "en":
                parts = [
                    f"P{r['pos']} {r['name']}" + (f" at {r['gap_leader']}" if r['pos'] > 1 else " leading")
                    for r in top5
                ]
                return "Copy that, top five right now, " + ", ".join(parts) + f". You are P{rep.position}."
            ord_es = {1: "primero", 2: "segundo", 3: "tercero", 4: "cuarto", 5: "quinto"}
            parts = []
            for r in top5:
                o = ord_es.get(r["pos"], f"P{r['pos']}")
                if r.get("is_player"):
                    parts.append(f"tú vas {o} a {r['gap_leader']}")
                elif r["pos"] == 1:
                    parts.append(f"{r['name']} {o}")
                else:
                    parts.append(f"{r['name']} {o} a {r['gap_leader']}")
            me_tail = f" Tú ruedas en el puesto {rep.position}." if rep.position > 5 else ""
            return "Ahora mismo en cabeza tenemos a " + ", ".join(parts) + f".{me_tail}"

        # ------------------------------------------------------------------
        # 26. DAÑOS / METEOROLOGIA / RESUMEN COMPLETO
        # ------------------------------------------------------------------
        if any(k in norm for k in ("dano", "daño", "danos", "daños", "aleron", "fondo", "motor", "caja", "toque", "roto", "damage", "wing", "floor", "engine")):
            return rep.damage_summary_en if lang == "en" else rep.damage_summary_es

        if any(k in norm for k in ("lluvia", "llover", "clima", "tiempo", "meteo", "asfalto", "pista", "circuito", "weather", "rain", "forecast")):
            if lang == "en":
                return f"At {rep.track_name}, track condition is {rep.weather_now}, tarmac at {rep.track_temp} degrees. Rain probability is {rep.rain_forecast_pct} percent."
            return f"Aquí en {rep.track_name} tenemos {rep.weather_now_es} con {rep.track_temp} grados en el asfalto. La probabilidad de lluvia es del {rep.rain_forecast_pct} por ciento."

        # Si no encaja con ninguna pregunta tecnica pero tampoco tiene ninguna palabra de carreras
        if not (words & RACING_KEYWORDS):
            if lang == "en":
                return self._pick("scold_en", [
                    f"Focus on the race {drv}! Head down and eyes on the track, we are in a live session right now, copy.",
                    f"Not now {drv}! Keep your mind in the cockpit and hit your braking markers, we will talk about that later.",
                    f"Eyes on the tarmac {drv}! Save the chit-chat for the hospitality motorhome after the chequered flag.",
                    f"We are in the middle of a Grand Prix {drv}, concentrate on your corners and forget about that!",
                    f"Radio is for race calls only {drv}, keep both hands on the wheel and push through this sector.",
                ])
            return self._pick("scold_es", [
                f"¡Céntrate en la carrera, {drv}! Manos al volante y vista en la pista, eso no toca ahora, copy.",
                f"¡Ahora no, {drv}! Cabeza en el cockpit y clava los vértices, hablamos de eso al bajar del coche.",
                f"¡Concéntrate en conducir, {drv}! Estamos en mitad de sesión, vigila las referencias de frenada, copy.",
                f"Déjate de distracciones por la radio {drv}, que te estás dejando dos décimas en este sector. ¡A la pista!",
                f"Eso lo discutimos luego en el motorhome {drv}, ahora mismo quiero tus cinco sentidos en el asfalto.",
                f"La radio está para hablar de telemetría y estrategia {drv}, no para charlar. Baja la visera y aprieta.",
            ])

        return rep.full_briefing_en if lang == "en" else rep.full_briefing_es

    def check_proactive_spotter(self, state: RaceState) -> tuple[str, str] | None:
        """Comprueba si el Spotter proactivo tiene algun aviso automatico de carrera."""
        if not self.cfg.proactive_callouts:
            return None
        lang = "en" if self.cfg.language == "en" else "es"
        rep = analyze_strategy(state, self.cfg.driver_name)
        if rep.player_driver and rep.player_driver.upper() not in ("CAR", "PLAYER", "JUGADOR", "UNKNOWN", "CAR #"):
            self.spotter.driver_name = rep.player_driver.split()[0]
        else:
            self.spotter.driver_name = self.cfg.driver_name
        msg = self.spotter.check(state, lang=lang)
        if msg:
            self._last_callout_ts = time.time()
            self._log("[INGENIERO PROACTIVO]", msg, lang)
            return msg, lang
        return None

    def format_proactive_event(self, ev: P.Event, state: RaceState) -> tuple[str, str] | None:
        """Genera un aviso de radio proactivo si ocurre un paquete de evento UDP (ID 3)."""
        if not self.cfg.proactive_callouts:
            return None
        now = time.time()
        if now - self._last_callout_ts < 6.0:
            return None

        lang = "en" if self.cfg.language == "en" else "es"
        rep = analyze_strategy(state, self.cfg.driver_name)
        drv = rep.player_driver.split()[0] if (rep.player_driver and rep.player_driver.upper() not in ("CAR", "PLAYER", "JUGADOR", "UNKNOWN", "CAR #")) else self.cfg.driver_name
        msg = None
        if ev.code == "SCAR":
            sc_type = ev.extra // 10
            ev_type = ev.extra % 10
            if sc_type == 1 and ev_type == 0:
                if rep.max_wear_pct >= 30 and rep.laps_remaining >= 4:
                    self.spotter.order_box_now(rep.current_lap)
                    msg = (
                        f"Safety Car deployed! Cheap pit stop available, if we box now we rejoin P{rep.predicted_rejoin_pos} on fresh {rep.recommended_compound}s!"
                        if lang == "en"
                        else f"¡Safety Car en pista! Tenemos parada barata, si entras ahora salimos en posición {rep.predicted_rejoin_pos} con goma {rep.recommended_compound_es} nueva."
                    )
                else:
                    msg = (
                        "Safety Car deployed, keep your delta positive and stay out."
                        if lang == "en"
                        else "Safety Car en pista, respeta el delta positivo y quédate fuera."
                    )
            elif sc_type == 2 and ev_type == 0:
                msg = (
                    "Virtual Safety Car deployed, watch your delta and save fuel."
                    if lang == "en"
                    else "Virtual Safety Car desplegado, mantén el delta en verde y ahorra gasolina."
                )
            elif ev_type == 1:
                msg = (
                    "Safety Car in this lap, warm up your tyres and brakes for the restart!"
                    if lang == "en"
                    else "¡El Safety Car se marcha en esta vuelta! Calienta bien neumáticos y frenos para la resalida."
                )
        elif ev.code == "PENA" and ev.vehicle == state.player_idx:
            ptype = ev.extra // 1000
            secs = int(ev.value)
            if ptype == 4 and secs in (3, 5, 10, 15, 20):
                msg = (
                    f"Stewards have given us a {secs} second time penalty. Head down and build a gap."
                    if lang == "en"
                    else f"Dirección de carrera nos aplica {secs} segundos de sanción. Cabeza fría y abre hueco."
                )
            elif ptype == 0:
                msg = (
                    "We have been handed a drive-through penalty by the stewards."
                    if lang == "en"
                    else "Los comisarios nos han puesto un drive-through de sanción."
                )
            elif ptype in (10, 11, 12, 13, 14, 15):
                msg = (
                    "Track limits, that lap time has been deleted by Race Control."
                    if lang == "en"
                    else "Límites de pista superados, dirección de carrera nos invalida el tiempo de vuelta."
                )

        if msg:
            self._last_callout_ts = now
            self._log("[CONTROL DE CARRERA]", msg, lang)
            return msg, lang
        return None
