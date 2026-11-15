"""Cerebro del ingeniero de pista: Google Gemini + Motor Estrategico Completo y Variado."""
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
from .telemetry import lookups as L
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
4. LIVE TELEMETRY & STRATEGY: Base all race numbers, positions, lap times, gaps, tyre wear, degradation, pit windows, predicted rejoin position, undercut/overcut options, weather, fuel, and damage strictly on the [LIVE F1 25 UDP TELEMETRY] and [LIVE STRATEGY ANALYSIS] blocks provided.
5. OFF-TOPIC / IRRELEVANT QUESTIONS (CRITICAL RULE):
   - If the driver talks about or asks ANYTHING unrelated to racing, driving, car setup, telemetry, weather, strategy, or Formula 1 (e.g. politics, food, football, movies, homework, random nonsense), DO NOT answer the off-topic question!
   - Firmly and in-character tell the driver to focus on the race and keep their head down, varying your wording every time!
"""

RUDE_KEYWORDS = {
    # ES
    "callate", "calla", "pesado", "inutil", "mierda", "joder", "puta", "hostia",
    "gilipollas", "cabron", "tonto", "idiota", "estupido", "imbecil", "basura",
    "dejame", "molestes", "no me hables", "que te calles", "vete a la mierda",
    # EN
    "shut up", "fuck", "shit", "idiot", "stupid", "useless", "bitch", "asshole",
    "leave me alone", "stop talking", "quiet", "crap", "garbage",
}

GREETING_KEYWORDS = {
    "hola", "buenas", "me escuchas", "me copias", "me oyes", "probando",
    "hello", "hi", "hey", "radio check", "loud and clear", "copy", "testing",
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
}

RACING_KEYWORDS = {
    # ES
    "posicion", "posiciones", "primero", "primeros", "primeras", "segundo", "segunda",
    "tercero", "tercera", "cuarto", "cuarta", "quinto", "quinta", "sexto", "septimo",
    "octavo", "noveno", "decimo", "top", "cinco", "tres", "diez", "clasificacion",
    "lider", "delante", "detras", "distancia", "gap", "diferencia", "tiempo", "tiempos",
    "crono", "record", "rapida", "vuelta", "vueltas", "queda", "quedan", "falta",
    "faltan", "ultima", "final", "sector", "neumatico", "neumaticos", "rueda", "ruedas",
    "goma", "gomas", "blando", "medio", "duro", "intermedio", "desgaste", "degradacion",
    "temperatura", "temperaturas", "freno", "frenos", "reparto", "frenada", "alerta",
    "dano", "daño", "danos", "daños", "aleron", "fondo", "motor", "caja", "toque",
    "roto", "combustible", "gasolina", "mezcla", "lift", "coast", "ers", "bateria",
    "energia", "drs", "pit", "box", "boxes", "parada", "paro", "parar", "proxima",
    "deberia", "entro", "entrar", "ventana", "estrategia", "undercut", "overcut",
    "trafico", "lluvia", "llover", "clima", "meteo", "seco", "mojado", "pista",
    "asfalto", "safety", "vsc", "bandera", "penalizacion", "sancion", "sanciones",
    "aviso", "avisos", "limites", "ritmo", "carrera", "coche", "monoplaza", "equipo",
    "escuderia", "llevo", "voy", "estoy", "estado", "reporte", "informe", "resumen",
    "situacion", "vamos", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10",
    # EN
    "position", "positions", "standings", "leader", "first", "second", "third", "fourth",
    "fifth", "five", "three", "ten", "ahead", "behind", "delta", "interval", "lap",
    "laps", "left", "remaining", "last", "best", "fastest", "pace", "sector", "tyre",
    "tyres", "tire", "tires", "wear", "degradation", "temp", "temps", "temperature",
    "brake", "brakes", "bias", "damage", "wing", "floor", "engine", "gearbox", "fuel",
    "mix", "battery", "window", "strategy", "stop", "should", "next", "undercut",
    "overcut", "rejoin", "weather", "rain", "forecast", "track", "car", "team", "driving",
    "flag", "penalty", "penalties", "warning", "warnings", "limits", "status", "report",
    "update", "session", "briefing", "situation", "pitting",
}


class EngineerBrain:
    """Gestiona las consultas al ingeniero (Gemini API + motor estrategico completo y variado)."""

    def __init__(self, cfg: EngineerConfig):
        self.cfg = cfg
        self.history: deque[tuple[str, str]] = deque(maxlen=8)
        self._last_callout_ts: float = 0.0
        self.dialogue_log: deque[dict] = deque(maxlen=40)
        self.spotter = ProactiveSpotter(driver_name=cfg.driver_name)
        self._last_choice: dict[str, int] = {}

    def _pick(self, category: str, options: list[str]) -> str:
        """Elige una respuesta aleatoria garantizando que nunca repite la anterior."""
        if len(options) <= 1:
            return options[0] if options else ""
        last_idx = self._last_choice.get(category, -1)
        candidates = [i for i in range(len(options)) if i != last_idx]
        idx = random.choice(candidates)
        self._last_choice[category] = idx
        return options[idx]

    def ask(self, user_text: str, state: RaceState) -> tuple[str, str]:
        """Devuelve (respuesta_limpia, idioma 'es'|'en')."""
        lang = "en" if self.cfg.language == "en" else "es"
        rep = analyze_strategy(state, self.cfg.driver_name)
        context = (
            build_race_context(state)
            + "\n[LIVE STRATEGY ANALYSIS]\n"
            + f"Box Recommendation: {rep.box_recommendation} | Next Compound: {rep.recommended_compound} | "
            + f"Predicted Rejoin: P{rep.predicted_rejoin_pos} | Tyre Wear Rate: {rep.wear_per_lap:.1f}%/lap "
            + f"(~{rep.est_tyre_laps_left} good laps left) | Laps Remaining: {rep.laps_remaining}\n"
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
                temperature=0.65,
                max_output_tokens=180,
            ),
        )
        raw = (resp.text or "").strip()
        if raw.startswith("[ES]") or raw.startswith("[EN]"):
            raw = raw[4:].strip()
        return re.sub(r"[*_#`]+", "", raw).strip()

    def _local_strategic_brain(self, user_text: str, state: RaceState,
                               rep: StrategyReport, lang: str) -> str:
        """Motor estrategico local supercompleto con alta variedad de respuestas."""
        low = user_text.lower().strip()
        norm = (
            low.replace("á", "a").replace("é", "e").replace("í", "i")
               .replace("ó", "o").replace("ú", "u")
        )
        words = set(re.findall(r"[a-z0-9]+", norm))
        drv = self.cfg.driver_name

        standings = build_standings(state, limit=22)
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
                    f"Copy that Kimi, I will leave you alone then. Just try not to put it in the wall.",
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
                f"Respira hondo {drv}, que con ese calentón solo vas a sobrecalentar las ruedas traseras. Centrado en lo tuyo.",
            ])

        # ------------------------------------------------------------------
        # 2. SALUDOS / RADIO CHECK / PRUEBA DE RADIO
        # ------------------------------------------------------------------
        if words <= {"hola", "buenas", "hey", "hi", "hello", "ingeniero", "marc", "engineer", "radio"} or any(
            g in norm for g in ("me escuchas", "me copias", "me oyes", "radio check", "loud and clear", "probando")
        ):
            if lang == "en":
                return self._pick("greet_en", [
                    f"Loud and clear on the pit wall {drv}, telemetry is green across the board. You are P{rep.position}, let's push.",
                    f"Five by five {drv}, I hear you loud and clear. Everything looks good on the car, head down.",
                    f"Radio check good, we have all your data live from {rep.track_name}. Tell me what you need.",
                ])
            return self._pick("greet_es", [
                f"Te escucho alto y claro desde el muro {drv}, telemetría en verde. Ruedas en posición {rep.position}, dime qué necesitas.",
                f"Cinco de cinco {drv}, te copio perfecto en boxes. El monoplaza está en orden, concentrado y a por ellos.",
                f"Radio conectada y recibiendo todos tus datos desde {rep.track_name}. Dime qué quieres consultar.",
            ])

        # ------------------------------------------------------------------
        # 3. CELEBRACION / ANIMO ("VAMOS", "TOMA")
        # ------------------------------------------------------------------
        if any(c in norm for c in CELEBRATION_KEYWORDS) and len(words) <= 4:
            if lang == "en":
                return self._pick("celeb_en", [
                    f"Get in there {drv}! Mega job behind the wheel, keep that rhythm going!",
                    f"That is what I am talking about {drv}! Clinical driving, keep it up!",
                ])
            return self._pick("celeb_es", [
                f"¡Vamos {drv}, así se conduce! Qué barbaridad de ritmo, sigue enchufado.",
                f"¡Grande {drv}! En el muro estamos todos aplaudiendo, mantén la cabeza fría.",
            ])

        # ------------------------------------------------------------------
        # 4. ¿PREGUNTA POR UN PILOTO CONCRETO DE LA PARRILLA?
        # ------------------------------------------------------------------
        for r in standings:
            dname = r["name"].lower()
            if len(dname) >= 4 and dname in norm and not r.get("is_player"):
                if lang == "en":
                    return self._pick("drv_en", [
                        f"Copy, {r['name']} is currently P{r['pos']} in the {r['team']}, {r['gap_leader']} off the lead on {r['tyre']}.",
                        f"{r['name']} is running in P{r['pos']} right now, {r['gap_leader']} behind the leader, last lap was {r['last_lap']}.",
                    ])
                return self._pick("drv_es", [
                    f"Te confirmo, {r['name']} rueda ahora mismo en la posición {r['pos']} con el {r['team']}, a {r['gap_leader']} de la cabeza.",
                    f"Ahora mismo {r['name']} está en posición {r['pos']}, su última vuelta ha sido {r['last_lap']} y lleva {r['tyre']}.",
                ])

        # ------------------------------------------------------------------
        # 5. ¿QUIEN VA EN UNA POSICION CONCRETA? ("quien va segundo / tercero / P1...")
        # ------------------------------------------------------------------
        if any(q in norm for q in ("quien va", "quien esta", "quien es el", "who is in", "who is p", "who's in", "segunda posicion", "tercera posicion", "primera posicion", "cuarta posicion", "quinta posicion")):
            target_pos = None
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
                        return f"¡En la posición {target_pos} vas tú mismo, {drv}! Tienes a {rep.ahead_name} delante a {rep.ahead_gap_s:.1f} segundos."
                    if lang == "en":
                        return self._pick("who_pos_en", [
                            f"P{target_pos} right now is {row['name']} in the {row['team']}, {row['gap_leader']} behind the leader on {row['tyre']}.",
                            f"Currently in P{target_pos} we have {row['name']}, last lap was {row['last_lap']} on {row['tyre']}.",
                        ])
                    return self._pick("who_pos_es", [
                        f"En la posición {target_pos} rueda ahora mismo {row['name']} con el {row['team']}, a {row['gap_leader']} del líder.",
                        f"Ahora mismo el puesto {target_pos} lo tiene {row['name']}, viene marcando {row['last_lap']} en su última vuelta.",
                    ])

        # ------------------------------------------------------------------
        # 6. ¿VIENE A CUENTO DE LA CARRERA? SI NO -> BRONCA VARIADA DE INGENIERO
        # ------------------------------------------------------------------
        if not (words & RACING_KEYWORDS):
            if lang == "en":
                return self._pick("scold_en", [
                    f"Focus on the race {drv}! Head down and eyes on the track, we are in a live session right now, copy.",
                    f"Not now {drv}! Keep your mind in the cockpit and hit your braking markers, we will talk about that later.",
                    f"Eyes on the tarmac {drv}! Save the chit-chat for the hospitality motorhome after the chequered flag.",
                    f"We are in the middle of a Grand Prix {drv}, concentrate on your corners and forget about that!",
                    f"Cut the distractions on the radio {drv}, watch your mirrors and hit your apexes, copy.",
                ])
            return self._pick("scold_es", [
                f"¡Céntrate en la carrera, {drv}! Manos al volante y vista en la pista, eso no toca ahora, copy.",
                f"¡Ahora no, {drv}! Cabeza en el cockpit y clava los vértices, hablamos de eso al bajar del coche.",
                f"¡Concéntrate en conducir, {drv}! Estamos en mitad de sesión, vigila las referencias de frenada, copy.",
                f"Déjate de distracciones por la radio {drv}, que te estás dejando dos décimas en este sector. ¡A la pista!",
                f"Eso lo discutimos luego en el motorhome {drv}, ahora mismo quiero tus cinco sentidos en el asfalto.",
                f"¡Ojos en el trazado, {drv}! No me vengas con esos temas a doscientos por hora, concéntrate.",
                f"Corta el rollo por la radio {drv} y métete en la trazada, que el de detrás nos está recortando tiempo.",
            ])

        # ------------------------------------------------------------------
        # 7. TIEMPOS DE VUELTA / ULTIMA VUELTA / MEJOR VUELTA / RITMO
        # ------------------------------------------------------------------
        if any(k in norm for k in ("tiempo de vuelta", "ultimo tiempo", "mejor vuelta", "vuelta rapida", "crono", "ritmo", "sector", "lap time", "last lap", "best lap", "fastest lap", "pace")):
            if lang == "en":
                return self._pick("laptime_en", [
                    f"Your last lap was {rep.last_lap_str}, and your personal best is {rep.best_lap_str}. Ahead, {rep.ahead_name} just did a {rep.ahead_last_lap}.",
                    f"Stopwatch check, you crossed the line in {rep.last_lap_str}. Behind you, {rep.behind_name} clocked a {rep.behind_last_lap}.",
                ])
            return self._pick("laptime_es", [
                f"Tu último paso por meta ha sido {rep.last_lap_str}, y tu mejor vuelta de la sesión es {rep.best_lap_str}. Delante, {rep.ahead_name} ha rodado en {rep.ahead_last_lap}.",
                f"Mirando el crono, vienes de marcar un {rep.last_lap_str}. Por comparar, {rep.behind_name} detrás ha hecho {rep.behind_last_lap} en el último giro.",
                f"Tu última vuelta fue {rep.last_lap_str}. El ritmo es sólido, estás rodando muy parejo con {rep.ahead_name} que hizo {rep.ahead_last_lap}.",
            ])

        # ------------------------------------------------------------------
        # 8. COMBUSTIBLE / GASOLINA / MEZCLA (antes de "quedan" para no confundir!)
        # ------------------------------------------------------------------
        if any(k in norm for k in ("combustible", "gasolina", "mezcla", "lift", "coast", "fuel", "mix")):
            if lang == "en":
                return self._pick("fuel_en", [
                    f"{rep.fuel_advice_en} We have {rep.fuel_kg:.1f} kilos in the tank.",
                    f"Fuel check, {rep.fuel_kg:.1f} kilograms remaining, margin is {rep.fuel_laps_margin:+.1f} laps to the finish.",
                ])
            return self._pick("fuel_es", [
                f"{rep.fuel_advice_es} Llevamos ahora mismo {rep.fuel_kg:.1f} kilos en el depósito.",
                f"Revisando el tanque, nos quedan {rep.fuel_kg:.1f} kilos de combustible, un margen de {rep.fuel_laps_margin:+.1f} vueltas respecto al objetivo.",
                f"De gasolina vamos con {rep.fuel_laps_margin:+.1f} vueltas de margen y {rep.fuel_kg:.1f} kilos a bordo. {rep.fuel_advice_es}",
            ])

        # ------------------------------------------------------------------
        # 9. BATERIA / ERS / ENERGIA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("ers", "bateria", "energia", "battery", "energy", "deploy")):
            if lang == "en":
                return self._pick("ers_en", [
                    f"ERS battery charge is at {rep.ers_pct} percent in {rep.ers_mode} deployment mode.",
                    f"You have {rep.ers_pct} percent battery available right now, mode is set to {rep.ers_mode}.",
                ])
            return self._pick("ers_es", [
                f"La batería del ERS está al {rep.ers_pct} por ciento de carga, llevas el mapa en modo {rep.ers_mode_es}.",
                f"Tienes un {rep.ers_pct} por ciento de energía eléctrica disponible ahora mismo, modo {rep.ers_mode_es} activado.",
            ])

        # ------------------------------------------------------------------
        # 10. FRENOS / REPARTO DE FRENADA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("freno", "frenos", "reparto", "frenada", "brake", "brakes", "bias")):
            if lang == "en":
                return f"Brake bias is set to {rep.brake_bias} percent front, peak brake disc temperature is {rep.max_brake_temp} degrees."
            return f"Llevas el reparto de frenada al {rep.brake_bias} por ciento delante, y los discos están a {rep.max_brake_temp} grados de pico."

        # ------------------------------------------------------------------
        # 11. SANCIONES / AVISOS / LIMITES DE PISTA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("sancion", "sanciones", "penalizacion", "aviso", "avisos", "limites", "penalty", "penalties", "warning", "warnings", "limits")):
            if lang == "en":
                return f"You have {rep.penalties_s} seconds of time penalties and {rep.warnings_count} track limit warnings so far."
            return f"Llevas {rep.penalties_s} segundos de sanción acumulada y {rep.warnings_count} avisos por límites de pista."

        # ------------------------------------------------------------------
        # 12. ¿QUE COCHE / EQUIPO LLEVO?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("que coche", "que equipo", "escuderia", "monoplaza llevo", "coche llevo", "what car", "what team")):
            if lang == "en":
                return self._pick("car_en", [
                    f"You are driving the {rep.player_team}, currently running P{rep.position} on {rep.current_tyre} tyres. {rep.damage_summary_en}",
                    f"You're in the {rep.player_team} car, P{rep.position} on track with {rep.ers_pct} percent battery and {rep.current_tyre} tyres.",
                ])
            return self._pick("car_es", [
                f"Llevas el {rep.player_team}, ruedas en posición {rep.position} con goma {rep.current_tyre_es} de {rep.tyre_age} vueltas. {rep.damage_summary_es}",
                f"Estás al volante del {rep.player_team}, en el puesto {rep.position} de carrera con neumático {rep.current_tyre_es} y todo el sistema híbrido al {rep.ers_pct} por ciento.",
            ])

        # ------------------------------------------------------------------
        # 13. ¿EN QUE POSICION VOY?
        # ------------------------------------------------------------------
        if any(k in norm for k in ("en que posicion", "que posicion voy", "que puesto voy", "como voy", "what position am", "where am i")):
            if lang == "en":
                return self._pick("mypos_en", [
                    f"You are running in P{rep.position} right now, lap {rep.current_lap} of {rep.total_laps}. Ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds, behind is {rep.behind_name} at {rep.behind_gap_s:.1f}.",
                    f"Currently P{rep.position} {drv}. You have {rep.ahead_name} {rep.ahead_gap_s:.1f} seconds up the road and {rep.behind_name} {rep.behind_gap_s:.1f} behind you.",
                ])
            return self._pick("mypos_es", [
                f"Vas en la posición {rep.position}, vuelta {rep.current_lap} de {rep.total_laps}. Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos y detrás a {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Ruedas en el puesto {rep.position} ahora mismo {drv}. Tu referencia delante es {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, y por los espejos viene {rep.behind_name} a {rep.behind_gap_s:.1f}.",
                f"Estás en posición {rep.position} de {rep.total_cars} coches, a falta de {rep.laps_remaining} vueltas. Delante {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos.",
            ])

        # ------------------------------------------------------------------
        # 14. ESTRATEGIA / ¿DEBERIA PARAR EN BOXES? / PROXIMA PARADA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("estrategia", "parar", "paro", "parada", "proxima parada", "boxes", "box", "pit", "ventana", "undercut", "overcut", "deberia", "entro", "entrar", "strategy", "window", "should", "stop")):
            if lang == "en":
                return self._pick("strat_en", [
                    f"Strategy call right now is {rep.box_recommendation}. Ideal window is lap {rep.pit_window_ideal} to {rep.pit_window_latest}. {rep.rejoin_summary_en}",
                    f"Looking at the pit wall numbers, {rep.rejoin_summary_en} {rep.undercut_summary_en}",
                ])
            rec_map = {
                "STAY OUT": "mantenernos fuera en pista",
                "PIT WINDOW OPEN": "ventana abierta, podemos parar en cuanto quieras",
                "HOLD OUT FOR RAIN": "alargar el stint esperando a que caiga la lluvia",
            }
            rec_es = rec_map.get(rep.box_recommendation, "entrar a boxes en esta misma vuelta")
            return self._pick("strat_es", [
                f"El plan en el muro es {rec_es}. Nuestra ventana ideal va de la vuelta {rep.pit_window_ideal} a la {rep.pit_window_latest}. {rep.rejoin_summary_es}",
                f"Mirando los números de estrategia, te recomiendo {rec_es}. {rep.rejoin_summary_es} {rep.undercut_summary_es}",
                f"Ahora mismo la orden es {rec_es}. A tus gomas les quedan unas {rep.est_tyre_laps_left} vueltas fuertes; {rep.rejoin_summary_es.lower()}",
            ])

        # ------------------------------------------------------------------
        # 15. ¿CUANTAS VUELTAS QUEDAN? / VUELTA ACTUAL
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
                f"Quedan exactamente {rep.laps_remaining} vueltas {drv}, vuelta {rep.current_lap} de {rep.total_laps}.",
            ])

        # ------------------------------------------------------------------
        # 16. TOP 5 / PRIMERAS POSICIONES / CLASIFICACION
        # ------------------------------------------------------------------
        if any(k in norm for k in ("primera", "primero", "primeros", "posiciones", "top", "clasificacion", "standings", "positions", "five", "cinco", "lider", "leader")):
            top5 = standings[:5]
            if lang == "en":
                parts = [
                    f"P{r['pos']} {r['name']}" + (f" at {r['gap_leader']}" if r['pos'] > 1 else " leading")
                    for r in top5
                ]
                return self._pick("top5_en", [
                    "Copy that, top five right now, " + ", ".join(parts) + ", keep pushing.",
                    "Here is the front of the field, " + ", ".join(parts) + ".",
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
            return self._pick("top5_es", [
                "Ahora mismo en cabeza tenemos a " + ", ".join(parts) + ". Sigue empujando.",
                "Te canto los cinco primeros, " + ", ".join(parts) + ". Buen ritmo.",
                "Así está la parte alta de la tabla, " + ", ".join(parts) + ".",
            ])

        # ------------------------------------------------------------------
        # 17. COCHE DE DELANTE / DETRAS / GAPS / DRS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("delante", "detras", "distancia", "gap", "diferencia", "ahead", "behind", "interval", "drs")):
            if lang == "en":
                return self._pick("gaps_en", [
                    f"You are P{rep.position}. Ahead is {rep.ahead_name} at {rep.ahead_gap_s:.1f} seconds on {rep.ahead_tyre}, and behind is {rep.behind_name} at {rep.behind_gap_s:.1f} seconds.",
                    f"Interval ahead to {rep.ahead_name} is {rep.ahead_gap_s:.1f} seconds, gap behind to {rep.behind_name} is {rep.behind_gap_s:.1f} seconds.",
                ])
            return self._pick("gaps_es", [
                f"Delante tienes a {rep.ahead_name} a {rep.ahead_gap_s:.1f} segundos, y por detrás viene {rep.behind_name} a {rep.behind_gap_s:.1f} segundos.",
                f"Tus referencias en pista son {rep.ahead_name} por delante a {rep.ahead_gap_s:.1f} segundos y {rep.behind_name} en tus retrovisores a {rep.behind_gap_s:.1f}.",
            ])

        # ------------------------------------------------------------------
        # 18. NEUMATICOS / RUEDAS / DESGASTE / TEMPERATURAS
        # ------------------------------------------------------------------
        if any(k in norm for k in ("neumatico", "neumaticos", "rueda", "ruedas", "goma", "gomas", "desgaste", "degradacion", "temperatura", "temperaturas", "tyre", "tyres", "tire", "tires", "wear", "temp")):
            if lang == "en":
                return self._pick("tyre_en", [
                    f"Your {rep.current_tyre} tyres are {rep.tyre_age} laps old, peak wear is {rep.max_wear_pct:.0f} percent on the {rep.worst_wheel_en}, degrading at {rep.wear_per_lap:.1f} percent per lap. Around {rep.est_tyre_laps_left} good laps left.",
                    f"Tyre check, {rep.max_wear_pct:.0f} percent wear on the {rep.worst_wheel_en}, core temperature is {rep.max_tyre_temp} degrees. They will hold for another {rep.est_tyre_laps_left} laps.",
                ])
            return self._pick("tyre_es", [
                f"Llevas goma {rep.current_tyre_es} con {rep.tyre_age} vueltas, el mayor desgaste es del {rep.max_wear_pct:.0f} por ciento en la {rep.worst_wheel_es}. Te quedan unas {rep.est_tyre_laps_left} vueltas óptimas.",
                f"Revisando las gomas, tienes un {rep.max_wear_pct:.0f} por ciento de desgaste en la {rep.worst_wheel_es} y {rep.max_tyre_temp} grados de temperatura interna. Aguantan bien otras {rep.est_tyre_laps_left} vueltas.",
                f"Tus neumáticos {rep.current_tyre_es}s van por el {rep.max_wear_pct:.0f} por ciento de desgaste, degradando un {rep.wear_per_lap:.1f} por vuelta. Todo bajo control.",
            ])

        # ------------------------------------------------------------------
        # 19. DAÑOS / ALERON / FONDO / MOTOR
        # ------------------------------------------------------------------
        if any(k in norm for k in ("dano", "daño", "danos", "daños", "aleron", "fondo", "motor", "caja", "toque", "roto", "damage", "wing", "floor", "engine")):
            return rep.damage_summary_en if lang == "en" else rep.damage_summary_es

        # ------------------------------------------------------------------
        # 20. METEOROLOGIA / LLUVIA / CLIMA / PISTA
        # ------------------------------------------------------------------
        if any(k in norm for k in ("lluvia", "llover", "clima", "tiempo", "meteo", "asfalto", "pista", "weather", "rain", "forecast")):
            if lang == "en":
                return self._pick("wx_en", [
                    f"Track condition is {rep.weather_now}, tarmac at {rep.track_temp} degrees. Rain probability is {rep.rain_forecast_pct} percent.",
                    f"Weather radar shows {rep.weather_now} right now, air temp {rep.air_temp} degrees and {rep.rain_forecast_pct} percent chance of rain.",
                ])
            return self._pick("wx_es", [
                f"Ahora mismo tenemos {rep.weather_now_es} con {rep.track_temp} grados en el asfalto. La probabilidad de lluvia es del {rep.rain_forecast_pct} por ciento.",
                f"En el radar vemos {rep.weather_now_es}, temperatura ambiente de {rep.air_temp} grados y un {rep.rain_forecast_pct} por ciento de opciones de agua.",
            ])

        # ------------------------------------------------------------------
        # 21. RESUMEN COMPLETO / INFORME GENERAL
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
            # Evitar el valor 255 (0xFF = sin segundos en vueltas invalidadas o avisos)
            if ptype == 4 and 0 < secs < 60:
                msg = (
                    f"Stewards have given us a {secs} second time penalty. Head down, build the gap."
                    if lang == "en"
                    else f"Dirección de carrera nos aplica {secs} segundos de sanción. Cabeza fría y abre hueco."
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
