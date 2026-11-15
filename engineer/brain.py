"""Cerebro del ingeniero de pista: Google Gemini + Motor Estrategico Completo y Ultra-Variado."""
from __future__ import annotations

from collections import deque
import logging
import random
import re
import time

from google import genai
from google.genai import types

from .config import EngineerConfig
from .strategy import ProactiveSpotter, StrategyReport, analyze_strategy
from .telemetry import packets as P
from .telemetry.context import build_race_context, build_standings
from .telemetry.listener import RaceState

log = logging.getLogger("brain")

SYSTEM_PROMPT = """You are {engineer_name}, the Formula 1 Race Engineer on the pit wall speaking over the team radio to your driver, {driver_name}, during a session in F1 25.

STRICT RULES:
1. LANGUAGE TAG: Start EVERY response with [{lang_tag}]. Always reply strictly in {lang_label}.
2. RADIO STYLE & VARIETY: Speak like a real F1 race engineer (like GP Lambiase, Bono, or Xavi). Keep responses fast, natural, varied, and concise (1 to 3 flowing sentences, under 45 words). Never repeat the exact same phrasing twice. Write numbers naturally ("dos con ocho" or "two point eight" instead of "+2.8s"). Never use colons, parentheses, markdown, asterisks, or bullet points.
3. IF THE DRIVER IS RUDE / ANGRY / TELLS YOU TO SHUT UP:
   - React with authentic F1 race engineer sass and attitude (like GP Lambiase to Verstappen or Kimi's engineer). Snap back sarcastically about their driving/apexes and tell them to get on with it!
4. LIVE TELEMETRY & STRATEGY: Base all race numbers, positions, lap times, gaps, tyre wear, degradation, pit windows, predicted rejoin position, undercut/overcut options, weather, fuel, setup, and damage strictly on the [LIVE F1 25 UDP TELEMETRY] and [LIVE STRATEGY ANALYSIS] blocks provided.
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

RACING_KEYWORDS = {
    # ES
    "posicion", "posiciones", "puesto", "primero", "primeros", "primeras", "segundo", "segunda",
    "tercero", "tercera", "cuarto", "cuarta", "quinto", "quinta", "sexto", "septimo",
    "octavo", "noveno", "decimo", "ultimo", "ultima", "top", "cinco", "tres", "diez",
    "podio", "puntos", "zona", "clasificacion", "parrilla", "tabla", "lider",
    "delante", "detras", "distancia", "gap", "diferencia", "tiempo", "tiempos",
    "crono", "record", "rapida", "rapido", "lento", "recorto", "recortando", "pillo",
    "pillar", "alcanzar", "alcanzo", "cazar", "vuelta", "vueltas", "queda", "quedan",
    "falta", "faltan", "final", "sector", "sectores", "neumatico", "neumaticos",
    "rueda", "ruedas", "goma", "gomas", "blando", "medio", "duro", "intermedio",
    "desgaste", "degradacion", "agarre", "grip", "desliza", "patina", "traccion",
    "subviraje", "sobreviraje", "gira", "morro", "culo", "trasera", "delantera",
    "temperatura", "temperaturas", "fria", "frias", "caliente", "calientes",
    "freno", "frenos", "reparto", "frenada", "bloqueo", "diferencial", "reglaje",
    "setup", "alerta", "dano", "daño", "danos", "daños", "aleron", "fondo", "motor",
    "caja", "toque", "chocado", "golpe", "empujado", "echado", "cerrado", "incidente",
    "roto", "combustible", "gasolina", "mezcla", "deposito", "tanque", "lift", "coast",
    "ers", "bateria", "energia", "mapa", "drs", "pit", "box", "boxes", "parada", "paro",
    "parar", "proxima", "deberia", "entro", "entrar", "ventana", "estrategia", "plan",
    "undercut", "overcut", "trafico", "lluvia", "llover", "clima", "meteo", "seco",
    "mojado", "pista", "asfalto", "safety", "vsc", "bandera", "amarilla", "azul",
    "penalizacion", "sancion", "sanciones", "aviso", "avisos", "limites", "ritmo",
    "carrera", "coche", "monoplaza", "equipo", "escuderia", "companero", "compañero",
    "piloto", "llevo", "conduzco", "voy", "estoy", "estado", "reporte", "informe",
    "resumen", "situacion", "ataco", "atacar", "adelanto", "adelantar", "defiendo",
    "defender", "abandonado", "abandono", "retirado", "dnf", "circuito", "trazado",
    "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12",
    # EN
    "position", "positions", "standings", "podium", "points", "leader", "first",
    "second", "third", "fourth", "fifth", "five", "three", "ten", "ahead", "behind",
    "delta", "interval", "catching", "catch", "faster", "slower", "lap", "laps",
    "left", "remaining", "last", "best", "fastest", "pace", "sector", "tyre", "tyres",
    "tire", "tires", "wear", "degradation", "grip", "sliding", "understeer", "oversteer",
    "traction", "turn", "temp", "temps", "temperature", "brake", "brakes", "bias",
    "differential", "setup", "balance", "damage", "wing", "floor", "engine", "gearbox",
    "hit", "pushed", "crashed", "contact", "fuel", "mix", "battery", "window", "strategy",
    "stop", "should", "next", "undercut", "overcut", "rejoin", "weather", "rain",
    "forecast", "track", "car", "team", "teammate", "driver", "driving", "flag",
    "penalty", "penalties", "warning", "warnings", "limits", "status", "report",
    "update", "session", "briefing", "situation", "pitting", "attack", "defend",
    "overtake", "retired", "dnf",
}


class EngineerBrain:
    """Gestiona las consultas al ingeniero (Gemini API + motor estrategico completo y ultra-variado)."""

    def __init__(self, cfg: EngineerConfig):
        self.cfg = cfg
        self.history: deque[tuple[str, str]] = deque(maxlen=8)
        self._last_callout_ts: float = 0.0
        self.dialogue_log: deque[dict] = deque(maxlen=40)
        self.spotter = ProactiveSpotter(driver_name=cfg.driver_name)
        self._recent_choices: dict[str, deque[int]] = {}

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

    def ask(self, user_text: str, state: RaceState) -> tuple[str, str]:
        """Devuelve (respuesta_limpia, idioma 'es'|'en')."""
        lang = "en" if self.cfg.language == "en" else "es"
        rep = analyze_strategy(state, self.cfg.driver_name)
        context = (
            build_race_context(state)
            + "\n[LIVE STRATEGY ANALYSIS]\n"
            + f"Driver Car: {rep.player_driver} ({rep.player_team}) | Position: P{rep.position}/{rep.total_cars} | "
            + f"Lap: {rep.current_lap}/{rep.total_laps} ({rep.laps_remaining} laps left)\n"
            + f"Box Recommendation: {rep.box_recommendation} | Next Compound: {rep.recommended_compound} | "
            + f"Predicted Rejoin: P{rep.predicted_rejoin_pos} | Tyre Wear Rate: {rep.wear_per_lap:.1f}%/lap "
            + f"(~{rep.est_tyre_laps_left} good laps left)\n"
            + f"Pace Analysis: {rep.pace_analysis_en}\n"
            + f"Setup Advice: {rep.setup_advice_en}\n"
            + f"ES Briefing: {rep.full_briefing_es}\n"
            + f"EN Briefing: {rep.full_briefing_en}"
        )
        api_key = self.cfg.resolved_api_key()

        reply_text = ""
        if api_key:
            try:
                reply_text = self._ask_gemini(user_text, context, lang, api_key)
            except Exception as e:
                log.warning("Fallo Gemini API (%s), usando motor estrategico local.", e)

        if not reply_text:
            reply_text = self._local_strategic_brain(user_text, state, rep, lang)

        self.history.append((user_text, reply_text))
        self.dialogue_log.appendleft({
            "time": time.strftime("%H:%M:%S"),
            "driver": user_text,
            "engineer": reply_text,
            "lang": lang.upper(),
        })
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
        """Motor estrategico local supercompleto con decenas de intenciones y alta variedad de frases."""
        low = user_text.lower().strip()
        norm = (
            low.replace("á", "a").replace("é", "e").replace("í", "i")
               .replace("ó", "o").replace("ú", "u").replace("ü", "u")
        )
        words = set(re.findall(r"[a-z0-9]+", norm))
        drv = self.cfg.driver_name

        standings = build_standings(state, limit=24)
        if not standings:
            standings = [
                {"pos": 1, "name": "Verstappen", "team": "Red Bull", "gap_leader": "+0.0s", "gap_front": "+0.0s", "tyre": "Medium (9L)", "last_lap": "1:46.110", "is_player": False},
                {"pos": 2, "name": "Leclerc", "team": "Ferrari", "gap_leader": "+2.8s", "gap_front": "+2.8s", "tyre": "Medium (9L)", "last_lap": "1:46.450", "is_player": False},
                {"pos": 3, "name": "Norris", "team": "McLaren", "gap_leader": "+5.1s", "gap_front": "+2.3s", "tyre": "Medium (9L)", "last_lap": "1:46.780", "is_player": False},
                {"pos": 4, "name": drv, "team": "Aston Martin", "gap_leader": "+6.5s", "gap_front": "+1.4s", "tyre": "Medium (9L)", "last_lap": "1:46.820", "is_player": True},
                {"pos": 5, "name": "Sainz", "team": "Williams", "gap_leader": "+8.6s", "gap_front": "+2.1s", "tyre": "Hard (14L)", "last_lap": "1:47.020", "is_player": False},
                {"pos": 6, "name": "Hamilton", "team": "Ferrari", "gap_leader": "+11.2s", "gap_front": "+2.6s", "tyre": "Hard (14L)", "last_lap": "1:47.190", "is_player": False},
                {"pos": 7, "name": "Russell", "team": "Mercedes", "gap_leader": "+13.0s", "gap_front": "+1.8s", "tyre": "Medium (9L)", "last_lap": "1:47.340", "is_player": False},
                {"pos": 8, "name": "Alonso", "team": "Aston Martin", "gap_leader": "+16.4s", "gap_front": "+3.4s", "tyre": "Hard (14L)", "last_lap": "1:47.500", "is_player": False},
            ]

        # ------------------------------------------------------------------
        # 1. ¿EL PILOTO ESTA SIENDO BORDE / INSULTANDO / MANDANDO CALLAR?
        # ------------------------------------------------------------------
        if any(rk in norm for rk in RUDE_KEYWORDS):
            if lang == "en":
                return self._pick("rude_en", [
                    f"Watch your tone {drv}, I am not the one missing every apex in sector two. Head down and drive!",
                    f"Copy that Kimi, I will leave you alone then. Just try not to put it in the barriers.",
                    f"Less barking on the radio and more right foot on the throttle, mate. The stopwatch does not lie.",
                    f"Don't shout at me {drv}, I'm looking at your telemetry right now and you're braking ten metres too early.",
                    f"Yeah, yeah, blame the engineer. Keep both hands on the wheel and focus on your lines, copy.",
                    f"If you drove as fast as you complain on the radio we would be P1 by twenty seconds. Push!",
                    f"Understood, radio silence from the pit wall. Let's see how you manage those tyres on your own.",
                    f"Take a deep breath {drv}, shouting into the mic only drains your focus, not the car ahead.",
                ])
            return self._pick("rude_es", [
                f"Oye {drv}, relaja ese tono conmigo que yo no soy el que se está comiendo todos los pianos. Conduce y calla, copy.",
                f"Vale Kimi, te dejo tranquilo, tú sabrás lo que haces ahí fuera con esas gomas.",
                f"Menos llorar por la radio y más pisar el pedal derecho, campeón, que el crono no engaña.",
                f"A mí no me grites {drv}, que estoy viendo tu telemetría desde el muro y estás frenando diez metros tarde en cada curva.",
                f"Sí, sí, ahora échale la culpa al ingeniero. Baja la cabeza, mete cuarta y demuestra manos en la pista.",
                f"Si fueras tan rápido en curva como soltando borderías por la radio iríamos líderes con veinte segundos de ventaja. ¡Tira!",
                f"Respira hondo {drv}, que con ese calentón solo vas a sobrecalentar las ruedas traseras. Centrado en lo tuyo.",
                f"Recibido, cierro el micro desde el muro. A ver cómo gestionas tú solito la degradación en este stint.",
                f"Guárdate ese carácter para adelantar a {rep.ahead_name}, que lo tienes a {rep.ahead_gap_s:.1f} segundos y a mí no me tienes que ganar.",
                f"Mucho ruido por la radio {drv}, pero en el segundo sector te acabas de dejar dos décimas. Menos quejarse y más trazar fino.",
            ])

        # ------------------------------------------------------------------
        # 2. SALUDOS / RADIO CHECK / CONVERSACION CON EL INGENIERO
        # ------------------------------------------------------------------
        if words <= {"hola", "buenas", "hey", "hi", "hello", "ingeniero", "marc", "engineer", "radio", "que", "tal", "como", "estas"} or any(
            g in norm for g in ("me escuchas", "me copias", "me oyes", "radio check", "loud and clear", "probando", "como estas", "que tal estas", "confias en mi")
        ):
            if lang == "en":
                return self._pick("greet_en", [
                    f"Loud and clear on the pit wall {drv}, telemetry is green across the board. You are P{rep.position} in the {rep.player_team}, let's push.",
                    f"Five by five {drv}, I hear you loud and clear. Everything looks solid on the car, head down.",
                    f"Radio check good, we have all your data live from {rep.track_name}. You are P{rep.position}, tell me what you need.",
                    f"Always backing you from the pit wall {drv}. You are P{rep.position} with {rep.ahead_name} {rep.ahead_gap_s:.1f} ahead, go get him.",
                ])
            return self._pick("greet_es", [
                f"Te escucho alto y claro desde el muro {drv}, telemetría en verde. Ruedas en posición {rep.position} con el {rep.player_team}, dime qué necesitas.",
                f"Cinco de cinco {drv}, te copio perfecto en boxes. El monoplaza está en orden, concentrado y a por ellos.",
                f"Radio conectada y recibiendo todos tus datos desde {rep.track_name}. Vas en el puesto {rep.position}, dime qué quieres consultar.",
                f"Aquí estamos al pie del cañón en el muro {drv}, confiando al cien por cien en tus manos. Vas posición {rep.position}, ¡a apretar!",
                f"Te copio cristalino {drv}. Todo el sistema de telemetría del {rep.player_team} marca verde, tú pide por esa boca.",
            ])

        # ------------------------------------------------------------------
        # 3. CELEBRACION / ANIMO ("VAMOS", "TOMA")
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
                f"¡Toma ya {drv}! Clavas los tiempos como un reloj suizo, sigue empujando así.",
            ])

        # ------------------------------------------------------------------
        # 4. QUEJAS DE INCIDENTE / TOQUE / "ME HA CHOCADO / CERRADO / EMPUJADO"
        # ------------------------------------------------------------------
        if any(k in norm for k in ("me ha chocado", "me han chocado", "me ha tocado", "me ha dado", "me ha empujado", "me ha echado", "me ha cerrado", "has visto eso", "que hace este", "incident", "hit me", "pushed me", "turned in on me")):
            if lang == "en":
                return self._pick("inc_en", [
                    f"We saw that on the pit wall cameras {drv}, we are reporting it to the stewards right now. {rep.damage_summary_en} Keep your head cool.",
                    f"Unbelievable driving from him, we have sent the telemetry clip to Race Control. {rep.damage_summary_en} Settle back into your rhythm.",
                    f"Copy {drv}, we saw the contact. {rep.damage_summary_en} Don't retaliate, get him back cleanly on the stopwatch.",
                ])
            return self._pick("inc_es", [
                f"Lo hemos visto por las cámaras del muro {drv}, ya nos estamos quejando a dirección de carrera. {rep.damage_summary_es} Cabeza fría y devuélvesela en pista.",
                f"Menuda maniobra más sucia te ha hecho, ya lo hemos reportado a los comisarios. {rep.damage_summary_es} No entres al trapo y céntrate en tu ritmo.",
                f"Te copio {drv}, hemos visto el golpe en los sensores. {rep.damage_summary_es} Respira y recupérale la posición con el DRS.",
                f"Increíble que no te haya dejado espacio, estamos hablando con Charlie desde el muro. {rep.damage_summary_es} Sigue tirando.",
            ])

        # ------------------------------------------------------------------
        # 5. QUEJAS DEL COCHE / MANEJO (SUBVIRAJE, SOBREVIRAJE, FALTA DE AGARRE, REGLAJES)
        # ------------------------------------------------------------------
        if any(k in norm for k in ("no gira", "subviraje", "se va de delante", "morro", "sobreviraje", "se va de atras", "patina", "desliza", "no tengo agarre", "sin agarre", "traccion", "bloqueo", "diferencial", "reglaje", "setup", "understeer", "oversteer", "no grip", "sliding", "traction", "balance")):
            if lang == "en":
                return self._pick("setup_en", [
                    f"Copy on the balance {drv}. {rep.setup_advice_en}",
                    f"We see the slip on telemetry. {rep.setup_advice_en} Also be progressive on the throttle out of slow zones.",
                    f"Understood {drv}. {rep.setup_advice_en} Your peak tyre core temp is {rep.max_tyre_temp} degrees right now.",
                ])
            return self._pick("setup_es", [
                f"Te copio con el comportamiento del coche {drv}. {rep.setup_advice_es}",
                f"Vemos ese deslizamiento en los sensores del muro. {rep.setup_advice_es}",
                f"Recibido {drv}. {rep.setup_advice_es} Acaricia el acelerador a la salida de las curvas lentas para cuidar las gomas.",
                f"Entendido {drv}. {rep.setup_advice_es} Ahora mismo llevas las gomas a {rep.max_tyre_temp} grados de temperatura interna.",
            ])

        # ------------------------------------------------------------------
        # 6. ¿QUE COCHE / EQUIPO / PILOTO LLEVO? (Antes de buscar piloto rival!)
        # ------------------------------------------------------------------
        if any(k in norm for k in ("que coche", "que equipo", "escuderia", "monoplaza llevo", "coche llevo", "quien soy", "que piloto soy", "mi coche", "what car", "what team", "who am i")):
            drv_tag = f" de {rep.player_driver}" if rep.player_driver and rep.player_driver.upper() != drv.upper() else ""
            if lang == "en":
                return self._pick("car_en", [
                    f"You are driving the {rep.player_team} car ({rep.player_driver}), currently running P{rep.position} of {rep.total_cars} on {rep.current_tyre} tyres. {rep.damage_summary_en}",
                    f"You're at the wheel of the {rep.player_team}, P{rep.position} on track with {rep.ers_pct} percent battery and {rep.current_tyre} tyres.",
                    f"You are in the {rep.player_team} machine running P{rep.position}, lap {rep.current_lap} of {rep.total_laps}. {rep.damage_summary_en}",
                ])
            return self._pick("car_es", [
                f"Estás al volante del {rep.player_team}{drv_tag}, rodando en la posición {rep.position} de {rep.total_cars} con goma {rep.current_tyre_es} de {rep.tyre_age} vueltas. {rep.damage_summary_es}",
                f"Conduces el {rep.player_team}{drv_tag}, ahora mismo en el puesto {rep.position} de carrera con neumático {rep.current_tyre_es} y batería al {rep.ers_pct} por ciento.",
                f"Llevas el monoplaza de {rep.player_team}{drv_tag}. Vas en posición {rep.position} en la vuelta {rep.current_lap} de {rep.total_laps}, delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos.",
                f"Ruedas con el {rep.player_team}{drv_tag} en el puesto {rep.position}. {rep.damage_summary_es} Tus gomas {rep.current_tyre_es}s están al {rep.max_wear_pct:.0f} por ciento.",
            ])

        # ------------------------------------------------------------------
        # 7. ¿DONDE ESTA MI COMPAÑERO DE EQUIPO?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("companero", "compañero", "teammate", "el otro coche")):
            if rep.teammate_pos > 0:
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
        # 8. ¿PREGUNTA POR UN PILOTO CONCRETO DE LA PARRILLA?
        # ------------------------------------------------------------------
        for r in standings:
            dname = r["name"].lower().replace("ü", "u")
            if len(dname) >= 4 and dname in norm:
                if r.get("is_player"):
                    if lang == "en":
                        return f"That's your car {drv}! You are P{rep.position} in the {rep.player_team}, ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds."
                    return f"¡Ese eres tú con el {rep.player_team}, {drv}! Vas en posición {rep.position}, con {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} segundos."
                if lang == "en":
                    return self._pick("drv_en", [
                        f"Copy, {r['name']} is currently P{r['pos']} in the {r['team']}, {r['gap_leader']} off the lead on {r['tyre']}.",
                        f"{r['name']} is running in P{r['pos']} right now, {r['gap_leader']} behind the leader, last lap was {r['last_lap']}.",
                        f"Checking the board, {r['name']} holds P{r['pos']} for {r['team']} on {r['tyre']}, clocking {r['last_lap']} last time around.",
                    ])
                return self._pick("drv_es", [
                    f"Te confirmo, {r['name']} rueda ahora mismo en la posición {r['pos']} con el {r['team']}, a {r['gap_leader']} de la cabeza.",
                    f"Ahora mismo {r['name']} está en el puesto {r['pos']}, su última vuelta ha sido {r['last_lap']} y monta goma {r['tyre']}.",
                    f"Localizado en el monitor, {r['name']} va en la posición {r['pos']} con el {r['team']}, a {r['gap_leader']} del líder y con {r['pits']} paradas.",
                    f"{r['name']} marcha en el puesto {r['pos']} con neumáticos {r['tyre']}, marcando {r['last_lap']} en su último paso por meta.",
                ])

        # ------------------------------------------------------------------
        # 9. ¿QUIEN VA EN UNA POSICION CONCRETA? ("quien va segundo / tercero / P1 / ultimo...")
        # ------------------------------------------------------------------
        if any(q in norm for q in ("quien va", "quien esta", "quien es el", "quien lidera", "who is in", "who is p", "who's in", "who leads", "segunda posicion", "tercera posicion", "primera posicion", "cuarta posicion", "quinta posicion", "ultimo", "last place")):
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
                    if lang == "en":
                        return self._pick("who_pos_en", [
                            f"P{target_pos} right now is {row['name']} in the {row['team']}, {row['gap_leader']} behind the leader on {row['tyre']}.",
                            f"Currently in P{target_pos} we have {row['name']}, last lap was {row['last_lap']} on {row['tyre']}.",
                            f"Holding P{target_pos} is {row['name']} for {row['team']}, running {row['gap_leader']} off P1.",
                        ])
                    return self._pick("who_pos_es", [
                        f"En la posición {target_pos} rueda ahora mismo {row['name']} con el {row['team']}, a {row['gap_leader']} del líder.",
                        f"Ahora mismo el puesto {target_pos} lo ocupa {row['name']}, viene marcando {row['last_lap']} en su última vuelta con {row['tyre']}.",
                        f"En ese puesto {target_pos} tenemos a {row['name']} al volante del {row['team']}, a {row['gap_leader']} de la cabeza de carrera.",
                    ])

        # ------------------------------------------------------------------
        # 10. ¿VIENE A CUENTO DE LA CARRERA? SI NO -> BRONCA VARIADA DE INGENIERO
        # ------------------------------------------------------------------
        if not (words & RACING_KEYWORDS):
            if lang == "en":
                return self._pick("scold_en", [
                    f"Focus on the race {drv}! Head down and eyes on the track, we are in a live session right now, copy.",
                    f"Not now {drv}! Keep your mind in the cockpit and hit your braking markers, we will talk about that later.",
                    f"Eyes on the tarmac {drv}! Save the chit-chat for the hospitality motorhome after the chequered flag.",
                    f"We are in the middle of a Grand Prix {drv}, concentrate on your corners and forget about that!",
                    f"Cut the distractions on the radio {drv}, watch your mirrors and hit your apexes, copy.",
                    f"Are you serious {drv}? You have {rep.ahead_name} {rep.ahead_gap_s:.1f} seconds ahead, focus on driving!",
                    f"Radio is for race calls only {drv}, keep both hands on the wheel and push through this sector.",
                ])
            return self._pick("scold_es", [
                f"¡Céntrate en la carrera, {drv}! Manos al volante y vista en la pista, eso no toca ahora, copy.",
                f"¡Ahora no, {drv}! Cabeza en el cockpit y clava los vértices, hablamos de eso al bajar del coche.",
                f"¡Concéntrate en conducir, {drv}! Estamos en mitad de sesión, vigila las referencias de frenada, copy.",
                f"Déjate de distracciones por la radio {drv}, que te estás dejando dos décimas en este sector. ¡A la pista!",
                f"Eso lo discutimos luego en el motorhome {drv}, ahora mismo quiero tus cinco sentidos en el asfalto.",
                f"¡Ojos en el trazado, {drv}! No me vengas con esos temas a doscientos cincuenta por hora, concéntrate.",
                f"Corta el rollo por la radio {drv} y métete en la trazada, que tienes a {rep.behind_name} detrás a {rep.behind_gap_s:.1f} segundos.",
                f"¿En serio me preguntas eso en plena carrera, {drv}? Tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, ¡ponte a conducir!",
                f"La radio está para hablar de telemetría y estrategia {drv}, no para charlar. Baja la visera y aprieta.",
                f"No pierdas la concentración con tonterías {drv}, clava la frenada de la siguiente curva y sigue tirando.",
            ])

        # ------------------------------------------------------------------
        # 11. PODIO / TOP 3 / ¿A CUANTO TENGO EL PODIO?
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

        # ------------------------------------------------------------------
        # 12. PUNTOS / TOP 10 / ¿ESTOY EN LOS PUNTOS?
        # ------------------------------------------------------------------
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
        # 13. ABANDONOS / COCHES RETIRADOS / DNF
        # ------------------------------------------------------------------
        if any(k in norm for k in ("abandonado", "abandono", "retirado", "cuantos coches quedan", "dnf", "retired")):
            if rep.retired_names:
                rlist = ", ".join(rep.retired_names)
                if lang == "en":
                    return f"We have {len(rep.retired_names)} retirements so far, {rlist} out of the race."
                return f"Llevamos {len(rep.retired_names)} abandonos confirmados en carrera, están fuera {rlist}."
            if lang == "en":
                return f"All {rep.total_cars} cars are still running on track, zero retirements so far."
            return f"Siguen los {rep.total_cars} coches en pista {drv}, de momento no ha abandonado nadie."

        # ------------------------------------------------------------------
        # 14. ¿LE RECORTAMOS / EN CUANTAS VUELTAS LE PILLO / COMPARACION DE RITMO?
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
                f"Te doy el delta de ritmo, {rep.pace_analysis_es.lower()} Por detrás {rep.behind_name} ha marcado {rep.behind_last_lap}.",
            ])

        # ------------------------------------------------------------------
        # 15. ¿COMO LE ADELANTO / DONDE ATACO / COMO ME DEFIENDO?
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
                f"Para defenderte de {rep.behind_name}, protege el carril interior en la frenada fuerte y despliega un golpe de ERS justo al subir de tercera a cuarta marcha.",
            ])

        # ------------------------------------------------------------------
        # 16. TIEMPOS DE VUELTA / ULTIMA VUELTA / MEJOR VUELTA / RITMO
        # ------------------------------------------------------------------
        if any(k in norm for k in ("tiempo de vuelta", "ultimo tiempo", "mejor vuelta", "vuelta rapida", "crono", "ritmo", "sector", "sectores", "lap time", "last lap", "best lap", "fastest lap", "pace")):
            if lang == "en":
                return self._pick("laptime_en", [
                    f"Your last lap was {rep.last_lap_str}, and your personal best is {rep.best_lap_str}. Ahead, {rep.ahead_name} just did a {rep.ahead_last_lap}.",
                    f"Stopwatch check, you crossed the line in {rep.last_lap_str}. Behind you, {rep.behind_name} clocked a {rep.behind_last_lap}. {rep.pace_analysis_en}",
                    f"Last time around was {rep.last_lap_str}, best of the session is {rep.best_lap_str}. {rep.pace_analysis_en}",
                ])
            return self._pick("laptime_es", [
                f"Tu último paso por meta ha sido {rep.last_lap_str}, y tu mejor vuelta de la sesión es {rep.best_lap_str}. Delante, {rep.ahead_name} ha rodado en {rep.ahead_last_lap}.",
                f"Mirando el crono, vienes de marcar un {rep.last_lap_str}. Por comparar, {rep.behind_name} detrás ha hecho {rep.behind_last_lap} en el último giro.",
                f"Tu última vuelta fue {rep.last_lap_str}. {rep.pace_analysis_es}",
                f"Acabas de cruzar meta en {rep.last_lap_str}, con un mejor registro personal de {rep.best_lap_str}. {rep.pace_analysis_es}",
            ])

        # ------------------------------------------------------------------
        # 17. COMBUSTIBLE / GASOLINA / MEZCLA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("combustible", "gasolina", "mezcla", "deposito", "tanque", "lift", "coast", "fuel", "mix")):
            if lang == "en":
                return self._pick("fuel_en", [
                    f"{rep.fuel_advice_en} We have {rep.fuel_kg:.1f} kilos in the tank.",
                    f"Fuel check, {rep.fuel_kg:.1f} kilograms remaining, margin is {rep.fuel_laps_margin:+.1f} laps to the finish.",
                    f"Tank is at {rep.fuel_kg:.1f} kilos, {rep.fuel_laps_margin:+.1f} laps delta. {rep.fuel_advice_en}",
                ])
            return self._pick("fuel_es", [
                f"{rep.fuel_advice_es} Llevamos ahora mismo {rep.fuel_kg:.1f} kilos en el depósito.",
                f"Revisando el tanque, nos quedan {rep.fuel_kg:.1f} kilos de combustible, un margen de {rep.fuel_laps_margin:+.1f} vueltas respecto al objetivo.",
                f"De gasolina vamos con {rep.fuel_laps_margin:+.1f} vueltas de margen y {rep.fuel_kg:.1f} kilos a bordo. {rep.fuel_advice_es}",
                f"El caudalímetro marca {rep.fuel_kg:.1f} kilos restantes. {rep.fuel_advice_es}",
            ])

        # ------------------------------------------------------------------
        # 18. BATERIA / ERS / ENERGIA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("ers", "bateria", "energia", "mapa", "battery", "energy", "deploy")):
            if lang == "en":
                return self._pick("ers_en", [
                    f"ERS battery charge is at {rep.ers_pct} percent in {rep.ers_mode} deployment mode.",
                    f"You have {rep.ers_pct} percent battery available right now, mode is set to {rep.ers_mode}.",
                    f"Hybrid system shows {rep.ers_pct} percent state of charge, harvesting cleanly under braking.",
                ])
            return self._pick("ers_es", [
                f"La batería del ERS está al {rep.ers_pct} por ciento de carga, llevas el mapa en modo {rep.ers_mode_es}.",
                f"Tienes un {rep.ers_pct} por ciento de energía eléctrica disponible ahora mismo, modo {rep.ers_mode_es} activado.",
                f"El sistema híbrido marca un {rep.ers_pct} por ciento de batería en modo {rep.ers_mode_es}, regenerando bien en las frenadas fuertes.",
            ])

        # ------------------------------------------------------------------
        # 19. FRENOS / REPARTO DE FRENADA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("freno", "frenos", "reparto", "frenada", "brake", "brakes", "bias")):
            if lang == "en":
                return f"Brake bias is set to {rep.brake_bias} percent front, peak brake disc temperature is {rep.max_brake_temp} degrees. {rep.setup_advice_en}"
            return f"Llevas el reparto de frenada al {rep.brake_bias} por ciento delante, y los discos están a {rep.max_brake_temp} grados de pico. {rep.setup_advice_es}"

        # ------------------------------------------------------------------
        # 20. SANCIONES / AVISOS / LIMITES DE PISTA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("sancion", "sanciones", "penalizacion", "aviso", "avisos", "limites", "penalty", "penalties", "warning", "warnings", "limits")):
            if lang == "en":
                return f"You have {rep.penalties_s} seconds of time penalties and {rep.warnings_count} track limit warnings so far."
            return f"Llevas {rep.penalties_s} segundos de sanción acumulada y {rep.warnings_count} avisos por límites de pista. Mantén dos ruedas dentro de la línea blanca."

        # ------------------------------------------------------------------
        # 21. ¿EN QUE POSICION VOY? / ¿COMO VOY?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("en que posicion", "que posicion voy", "que puesto voy", "en que puesto", "como voy", "como vamos", "posicion", "puesto", "what position am", "where am i")) and not any(
            k in norm for k in ("primera", "primeras", "primeros", "top", "cinco", "diez", "clasificacion", "tabla", "parrilla")
        ):
            if lang == "en":
                return self._pick("mypos_en", [
                    f"You are running in P{rep.position} of {rep.total_cars} right now in the {rep.player_team}, lap {rep.current_lap} of {rep.total_laps}. Ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds, behind is {rep.behind_name} at {rep.behind_gap_s:.1f}.",
                    f"Currently P{rep.position} {drv}. You have {rep.ahead_name} {rep.ahead_gap_s:.1f} seconds up the road and {rep.behind_name} {rep.behind_gap_s:.1f} behind you.",
                    f"You hold P{rep.position} on lap {rep.current_lap} of {rep.total_laps}, {rep.laps_remaining} laps remaining. Gap ahead to {rep.ahead_name} is {rep.ahead_gap_s:.1f} seconds.",
                    f"P{rep.position} on track {drv}. {rep.ahead_name} is your target ahead at {rep.ahead_gap_s:.1f}, and {rep.behind_name} is {rep.behind_gap_s:.1f} behind in your mirrors.",
                ])
            return self._pick("mypos_es", [
                f"Vas en la posición {rep.position} de {rep.total_cars} con el {rep.player_team}, vuelta {rep.current_lap} de {rep.total_laps}. Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos y detrás a {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Ruedas en el puesto {rep.position} ahora mismo {drv}. Tu referencia delante es {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, y por los espejos viene {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Estás en posición {rep.position} de {rep.total_cars} coches, a falta de {rep.laps_remaining} vueltas. Delante {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, detrás {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Marchas en el puesto {rep.position} en el giro {rep.current_lap} de {rep.total_laps}. Tienes a {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} segundos con {rep.ahead_tyre}, y a {rep.behind_name} detrás a {rep.behind_gap_s:.1f}.",
                f"Ahora mismo ocupas la posición {rep.position} al volante del {rep.player_team}. Objetivo delante {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos; por detrás {rep.behind_name} a {rep.behind_gap_s:.1f}.",
            ])

        # ------------------------------------------------------------------
        # 22. ESTRATEGIA / ¿DEBERIA PARAR EN BOXES? / PROXIMA PARADA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("estrategia", "plan", "parar", "paro", "parada", "proxima parada", "boxes", "box", "pit", "ventana", "undercut", "overcut", "deberia", "entro", "entrar", "strategy", "window", "should", "stop")):
            if lang == "en":
                return self._pick("strat_en", [
                    f"Strategy call right now is {rep.box_recommendation}. Ideal window is lap {rep.pit_window_ideal} to {rep.pit_window_latest}. {rep.rejoin_summary_en}",
                    f"Looking at the pit wall numbers, {rep.rejoin_summary_en} {rep.undercut_summary_en}",
                    f"Plan A is {rep.box_recommendation}. Your {rep.current_tyre}s have around {rep.est_tyre_laps_left} strong laps left. {rep.rejoin_summary_en}",
                ])
            rec_map = {
                "STAY OUT": "mantenernos fuera en pista y alargar el stint",
                "PIT WINDOW OPEN": "ventana de parada abierta, podemos entrar cuando quieras",
                "HOLD OUT FOR RAIN": "aguantar en pista esperando a que descargue la lluvia",
            }
            rec_es = rec_map.get(rep.box_recommendation, "entrar a boxes en esta misma vuelta")
            return self._pick("strat_es", [
                f"El plan en el muro es {rec_es}. Nuestra ventana ideal va de la vuelta {rep.pit_window_ideal} a la {rep.pit_window_latest}. {rep.rejoin_summary_es}",
                f"Mirando las simulaciones de estrategia, te recomiendo {rec_es}. {rep.rejoin_summary_es} {rep.undercut_summary_es}",
                f"Ahora mismo la orden táctica es {rec_es}. A tus gomas les quedan unas {rep.est_tyre_laps_left} vueltas fuertes; {rep.rejoin_summary_es.lower()}",
                f"En la pizarra del muro tenemos marcado {rec_es}. {rep.rejoin_summary_es} {rep.pace_analysis_es}",
            ])

        # ------------------------------------------------------------------
        # 23. ¿CUANTAS VUELTAS QUEDAN? / VUELTA ACTUAL
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
                    f"Lap {rep.current_lap} of {rep.total_laps} right now {drv}, {rep.laps_remaining} to the finish and fuel margin is {rep.fuel_laps_margin:+.1f} laps.",
                ])
            return self._pick("laps_es", [
                f"Estamos en la vuelta {rep.current_lap} de {rep.total_laps}, te quedan {rep.laps_remaining} vueltas hasta la bandera a cuadros.",
                f"Faltan {rep.laps_remaining} vueltas para terminar, vas por el giro {rep.current_lap} de {rep.total_laps} y las gomas aguantan otras {rep.est_tyre_laps_left} vueltas buenas.",
                f"Quedan exactamente {rep.laps_remaining} vueltas {drv}, vuelta {rep.current_lap} de {rep.total_laps} en {rep.track_name}.",
                f"Paso por la vuelta {rep.current_lap} de {rep.total_laps}, restan {rep.laps_remaining} giros y vamos con {rep.fuel_laps_margin:+.1f} vueltas de gasolina.",
            ])

        # ------------------------------------------------------------------
        # 24. TOP 5 / PRIMERAS POSICIONES / CLASIFICACION GENERAL
        # ------------------------------------------------------------------
        if any(k in norm for k in ("primera", "primero", "primeros", "posiciones", "top", "clasificacion", "parrilla", "tabla", "standings", "positions", "five", "cinco", "lider", "leader")):
            top5 = standings[:5]
            if lang == "en":
                parts = [
                    f"P{r['pos']} {r['name']}" + (f" at {r['gap_leader']}" if r['pos'] > 1 else " leading")
                    for r in top5
                ]
                return self._pick("top5_en", [
                    "Copy that, top five right now, " + ", ".join(parts) + f". You are P{rep.position}.",
                    "Here is the front of the field, " + ", ".join(parts) + ".",
                    "Classification at the front, " + ", ".join(parts) + f", while you run P{rep.position}.",
                ])
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
            return self._pick("top5_es", [
                "Ahora mismo en cabeza tenemos a " + ", ".join(parts) + f".{me_tail}",
                "Te canto los cinco primeros, " + ", ".join(parts) + f".{me_tail}",
                "Así está la parte alta de la tabla, " + ", ".join(parts) + f".{me_tail}",
                "Repaso de los cinco de cabeza, " + ", ".join(parts) + f".{me_tail}",
            ])

        # ------------------------------------------------------------------
        # 25. COCHE DE DELANTE / DETRAS / GAPS / DRS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("delante", "detras", "distancia", "gap", "diferencia", "ahead", "behind", "interval", "drs")):
            if lang == "en":
                return self._pick("gaps_en", [
                    f"You are P{rep.position}. Ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds on {rep.ahead_tyre}, and behind is {rep.behind_name} at {rep.behind_gap_s:.1f} seconds.",
                    f"Interval ahead to {rep.ahead_name} is {rep.ahead_gap_s:.1f} seconds, gap behind to {rep.behind_name} is {rep.behind_gap_s:.1f} seconds. {rep.pace_analysis_en}",
                ])
            return self._pick("gaps_es", [
                f"Vas en posición {rep.position}. Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos con {rep.ahead_tyre}, y por detrás viene {rep.behind_name} a {rep.behind_gap_s:.1f} segundos.",
                f"Tus referencias en pista son {rep.ahead_name} por delante a {rep.ahead_gap_s:.1f} segundos y {rep.behind_name} en tus retrovisores a {rep.behind_gap_s:.1f}. {rep.pace_analysis_es}",
                f"El hueco con {rep.ahead_name} delante es de {rep.ahead_gap_s:.1f} segundos, y {rep.behind_name} te sigue a {rep.behind_gap_s:.1f} segundos con goma {rep.behind_tyre}.",
            ])

        # ------------------------------------------------------------------
        # 26. NEUMATICOS / RUEDAS / DESGASTE / TEMPERATURAS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("neumatico", "neumaticos", "rueda", "ruedas", "goma", "gomas", "desgaste", "degradacion", "agarre", "temperatura", "temperaturas", "tyre", "tyres", "tire", "tires", "wear", "temp")):
            if lang == "en":
                return self._pick("tyre_en", [
                    f"Your {rep.current_tyre} tyres are {rep.tyre_age} laps old, peak wear is {rep.max_wear_pct:.0f} percent on the {rep.worst_wheel_en}, degrading at {rep.wear_per_lap:.1f} percent per lap. Around {rep.est_tyre_laps_left} good laps left.",
                    f"Tyre check, {rep.max_wear_pct:.0f} percent wear on the {rep.worst_wheel_en}, core temperature is {rep.max_tyre_temp} degrees. They will hold for another {rep.est_tyre_laps_left} laps.",
                    f"We are on {rep.tyre_age} lap old {rep.current_tyre}s at {rep.max_wear_pct:.0f} percent wear. {rep.setup_advice_en}",
                ])
            return self._pick("tyre_es", [
                f"Llevas goma {rep.current_tyre_es} con {rep.tyre_age} vueltas, el mayor desgaste es del {rep.max_wear_pct:.0f} por ciento en la {rep.worst_wheel_es}. Te quedan unas {rep.est_tyre_laps_left} vueltas óptimas.",
                f"Revisando las gomas, tienes un {rep.max_wear_pct:.0f} por ciento de desgaste en la {rep.worst_wheel_es} y {rep.max_tyre_temp} grados de temperatura interna. Aguantan bien otras {rep.est_tyre_laps_left} vueltas.",
                f"Tus neumáticos {rep.current_tyre_es}s van por el {rep.max_wear_pct:.0f} por ciento de desgaste, degradando un {rep.wear_per_lap:.1f} por vuelta. {rep.setup_advice_es}",
                f"El juego de {rep.current_tyre_es} tiene {rep.tyre_age} giros y está al {rep.max_wear_pct:.0f} por ciento en la {rep.worst_wheel_es}. Tenemos margen para unas {rep.est_tyre_laps_left} vueltas fuertes.",
            ])

        # ------------------------------------------------------------------
        # 27. DAÑOS / ALERON / FONDO / MOTOR
        # ------------------------------------------------------------------
        if any(k in norm for k in ("dano", "daño", "danos", "daños", "aleron", "fondo", "motor", "caja", "toque", "roto", "damage", "wing", "floor", "engine")):
            return rep.damage_summary_en if lang == "en" else rep.damage_summary_es

        # ------------------------------------------------------------------
        # 28. METEOROLOGIA / LLUVIA / CLIMA / PISTA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("lluvia", "llover", "clima", "tiempo", "meteo", "asfalto", "pista", "circuito", "weather", "rain", "forecast")):
            if lang == "en":
                return self._pick("wx_en", [
                    f"At {rep.track_name}, track condition is {rep.weather_now}, tarmac at {rep.track_temp} degrees. Rain probability is {rep.rain_forecast_pct} percent.",
                    f"Weather radar over {rep.track_name} shows {rep.weather_now} right now, air temp {rep.air_temp} degrees and {rep.rain_forecast_pct} percent chance of rain.",
                ])
            return self._pick("wx_es", [
                f"Aquí en {rep.track_name} tenemos {rep.weather_now_es} con {rep.track_temp} grados en el asfalto. La probabilidad de lluvia es del {rep.rain_forecast_pct} por ciento.",
                f"En el radar meteorológico vemos {rep.weather_now_es}, temperatura ambiente de {rep.air_temp} grados y un {rep.rain_forecast_pct} por ciento de opciones de agua.",
                f"El asfalto de {rep.track_name} está a {rep.track_temp} grados con {rep.weather_now_es}. Probabilidad de lluvia en el {rep.rain_forecast_pct} por ciento.",
            ])

        # ------------------------------------------------------------------
        # 29. RESUMEN COMPLETO / INFORME GENERAL
        # ------------------------------------------------------------------
        return rep.full_briefing_en if lang == "en" else rep.full_briefing_es

    def check_proactive_spotter(self, state: RaceState) -> tuple[str, str] | None:
        """Comprueba si el Spotter proactivo tiene algun aviso automatico de carrera."""
        if not self.cfg.proactive_callouts:
            return None
        lang = "en" if self.cfg.language == "en" else "es"
        msg = self.spotter.check(state, lang=lang)
        if msg:
            self._last_callout_ts = time.time()
            self.dialogue_log.appendleft({
                "time": time.strftime("%H:%M:%S"),
                "driver": "[INGENIERO PROACTIVO]",
                "engineer": msg,
                "lang": lang.upper(),
            })
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
        msg = None
        if ev.code == "SCAR":
            sc_type = ev.extra // 10
            ev_type = ev.extra % 10
            if sc_type == 1 and ev_type == 0:
                if rep.max_wear_pct >= 30 and rep.laps_remaining >= 4:
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
            # En F1 las sanciones de tiempo reales son de 3, 5 o 10 segundos (evitar 2s de tiempo ganado o 255)
            if ptype == 4 and secs in (3, 5, 10, 15, 20):
                msg = (
                    f"Stewards have given us a {secs} second time penalty. Head down, build the gap."
                    if lang == "en"
                    else f"Dirección de carrera nos aplica {secs} segundos de sanción. Cabeza fría y abre hueco."
                )
            elif ptype == 0:
                msg = (
                    "Stewards have handed us a drive-through penalty. We have three laps to serve it."
                    if lang == "en"
                    else "Dirección de carrera nos sanciona con un drive-through. Tenemos tres vueltas para cumplirlo."
                )
            elif ptype in (10, 11, 12, 13, 14, 15):
                msg = (
                    "Stewards have deleted this lap time for track limits. Keep it between the white lines."
                    if lang == "en"
                    else "Dirección de carrera nos ha anulado el tiempo de vuelta por límites de pista. Mantente dentro de las líneas blancas."
                )
        elif ev.code == "FTLP" and ev.vehicle == state.player_idx:
            msg = (
                f"Purple lap, {ev.value:.3f}, fastest lap of the race! Great pace."
                if lang == "en"
                else f"¡Vuelta rápida de carrera con {ev.value:.3f}! Ritmazo {self.cfg.driver_name}, sigue así."
            )

        if msg:
            self._last_callout_ts = now
            self.dialogue_log.appendleft({
                "time": time.strftime("%H:%M:%S"),
                "driver": "[CONTROL DE CARRERA]",
                "engineer": msg,
                "lang": lang.upper(),
            })
            return msg, lang
        return None
