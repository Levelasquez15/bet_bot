import logging
import math
from typing import Dict, Any, List, Optional
from src.models.elo import EloModel
from src.models.poisson import calculate_poisson_matrix
from src.models.value import calculate_value

logger = logging.getLogger(__name__)


class LogicTreeAnalyzer:
    """
    Motor de análisis multi-mercado para fútbol.
    Combina estadísticas reales en vivo (tiros, xG, córners),
    Ratings Elo y Distribución Poisson con detección de Value Bets (EV > 0).
    """

    CONFIANZA_MINIMA = 75.0

    # Promedio de goles base por categoría de liga
    GOLES_LIGA_ALTA = 2.75   # Premier, Bundesliga, La Liga, Serie A, Champions
    GOLES_LIGA_MEDIA = 2.45  # BetPlay, Brasileirao, Segunda división, MLS
    GOLES_LIGA_BAJA = 2.15   # Ligas muy tácticas o defensivas

    def __init__(self):
        self.elo = EloModel()

    def analyze_live(self, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analiza partidos EN VIVO utilizando árboles de decisión contrastados
        con estadísticas reales (tiros a puerta, xG, córners, posesión y rojas).
        """
        picks = []
        seen = set()

        for game in games:
            gid = game.get("id", "")
            if gid in seen:
                continue

            home = game.get("homeCompetitor", {}).get("name", "Local")
            away = game.get("awayCompetitor", {}).get("name", "Visitante")
            match_name = f"{home} - {away}"

            sh = self._safe_int(game.get("homeCompetitor", {}).get("score", 0))
            sa = self._safe_int(game.get("awayCompetitor", {}).get("score", 0))
            minute = self._safe_int(game.get("gameTime", 0))

            if minute <= 0:
                continue

            total_goles = sh + sa
            diff = abs(sh - sa)
            is_half_time = game.get("statusGroup") == 3

            # Estadísticas en vivo reales
            stats = game.get("live_stats", {})
            shots_target_h = stats.get("shots_on_target", {}).get("home", 0)
            shots_target_a = stats.get("shots_on_target", {}).get("away", 0)
            total_shots_target = shots_target_h + shots_target_a

            corners_h = stats.get("corners", {}).get("home", 0)
            corners_a = stats.get("corners", {}).get("away", 0)
            total_corners = corners_h + corners_a

            xg_h = stats.get("xg", {}).get("home", 0.0)
            xg_a = stats.get("xg", {}).get("away", 0.0)
            total_xg = round(xg_h + xg_a, 2)

            poss_h = stats.get("possession", {}).get("home", 50.0)
            poss_a = stats.get("possession", {}).get("away", 50.0)

            red_h = stats.get("red_cards", {}).get("home", 0)
            red_a = stats.get("red_cards", {}).get("away", 0)

            pick = None

            # ── ÁRBOL 1: Presión de Gol Inminente (Empate tardío con llegada constante) ──
            if 62 <= minute <= 82 and sh == sa:
                if total_shots_target >= 5 or total_xg >= 1.2:
                    pick = self._make_pick(
                        match_name, minute,
                        "Próximo Gol: Habrá al menos 1 gol más",
                        f"Empate {sh}-{sa} con alta generación ({total_shots_target} tiros a puerta, xG {total_xg}).",
                        78.0,
                        odd="1.65 - 1.85",
                        odd_num=1.75
                    )

            # ── ÁRBOL 2: Córners en Vivo (Asedio del equipo que pierde) ──
            elif minute >= 58 and diff == 1:
                trailing_home = sh < sa
                perdedor = home if trailing_home else away
                poss_perdedor = poss_h if trailing_home else poss_a
                tiros_perdedor = shots_target_h if trailing_home else shots_target_a

                if poss_perdedor >= 54.0 or tiros_perdedor >= 3:
                    target_corners = total_corners + 2
                    pick = self._make_pick(
                        match_name, minute,
                        f"Más de {target_corners}.5 Córners Totales",
                        f"{perdedor} pierde por 1 e intensifica el ataque (Posesión {poss_perdedor}%, {total_corners} córners ya).",
                        76.5,
                        odd="1.70 - 1.90",
                        odd_num=1.80
                    )

            # ── ÁRBOL 3: Ritmo Fuerte → Over 2.5 confirmado ──
            elif minute <= 58 and total_goles >= 2:
                if total_shots_target >= 4 or total_xg >= 1.3:
                    pick = self._make_pick(
                        match_name, minute,
                        "Más de 2.5 Goles en el partido",
                        f"Ritmo frenético: {total_goles} goles en min {minute}, {total_shots_target} tiros a puerta y xG {total_xg}.",
                        82.0,
                        odd="1.50 - 1.70",
                        odd_num=1.60
                    )

            # ── ÁRBOL 4: Partido de Bloqueo → Menos de 1.5 / 2.5 Goles ──
            elif 42 <= minute <= 65 and total_goles == 0:
                if total_shots_target <= 2 and total_xg <= 0.55:
                    pick = self._make_pick(
                        match_name, minute,
                        "Menos de 1.5 Goles (Under 1.5)",
                        f"Partido muy trabado: 0-0 en min {minute} con apenas {total_shots_target} remates y xG {total_xg}.",
                        74.0,
                        odd="1.65 - 1.80",
                        odd_num=1.70
                    )

            # ── ÁRBOL 5: Ventaja Numérica por Tarjeta Roja ──
            elif minute >= 30 and (red_h > 0 or red_a > 0):
                equipo_superior = home if red_a > 0 else away
                equipo_inferior = away if red_a > 0 else home
                poss_superior = poss_h if red_a > 0 else poss_a

                if poss_superior >= 58.0:
                    pick = self._make_pick(
                        match_name, minute,
                        f"Gana o Próximo Gol: {equipo_superior}",
                        f"{equipo_inferior} con tarjeta roja. {equipo_superior} domina posesión ({poss_superior}%).",
                        79.5,
                        odd="1.55 - 1.75",
                        odd_num=1.65
                    )

            # ── ÁRBOL 6: Medio Tiempo con Goles → Over 2.5 ──
            elif is_half_time and total_goles >= 2:
                pick = self._make_pick(
                    match_name, "MT",
                    "Más de 2.5 Goles en el partido",
                    f"2+ goles ya anotados al descanso ({sh}-{sa}). Altísima probabilidad de superar 2.5.",
                    84.0,
                    odd="1.45 - 1.60",
                    odd_num=1.52
                )

            if pick and pick["confidence"] >= self.CONFIANZA_MINIMA:
                pick["score_home"] = sh
                pick["score_away"] = sa
                picks.append(pick)
                seen.add(gid)

        logger.info(f"Live Analyzer: {len(picks)} señales generadas con estadísticas reales.")
        return picks

    def analyze_upcoming(self, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analiza partidos PRÓXIMOS utilizando modelo de Poisson alimentado por ratings Elo,
        contrastado contra las cuotas reales de 365scores para detectar VALUE BETS (EV > 0).
        """
        picks = []
        seen = set()

        for game in games:
            gid = game.get("id", "")
            if gid in seen:
                continue

            home = game.get("homeCompetitor", {}).get("name", "Local")
            away = game.get("awayCompetitor", {}).get("name", "Visitante")
            match_name = f"{home} - {away}"
            start_time = game.get("startTime", "")[:16].replace("T", " ")

            comp_name = game.get("competitionDisplayName") or game.get("competition", {}).get("name", "")
            base_goals = self._lambda_por_liga(comp_name)

            # 1. Estimar lambdas con Elo
            lambda_h, lambda_a = self.elo.estimate_lambdas(home, away, base_league_goals=base_goals)

            # 2. Calcular probabilidades Poisson
            probs = calculate_poisson_matrix(lambda_h, lambda_a)

            # 3. Leer cuotas reales
            parsed_odds = game.get("parsed_odds", {})
            odd_home = parsed_odds.get("home")
            odd_draw = parsed_odds.get("draw")
            odd_away = parsed_odds.get("away")

            pick = None

            # ── EVALUAR 1X2 CON VALUE BETTING ──
            if odd_home and probs["home_win"] >= 0.52:
                val = calculate_value(probs["home_win"], odd_home)
                if val["has_value"] or probs["home_win"] >= 0.65:
                    conf = round(probs["home_win"] * 100.0, 1)
                    pick = self._make_pick(
                        match_name, start_time,
                        f"Gana Local: {home}",
                        f"Modelo Poisson + Elo: {conf}% prob. (Cuota justa: {val['fair_odd']} | Cuota casa: {odd_home}). EV: +{val['ev_pct']}%",
                        conf,
                        odd=str(odd_home),
                        odd_num=odd_home,
                        value_info=val
                    )

            elif odd_away and probs["away_win"] >= 0.48:
                val = calculate_value(probs["away_win"], odd_away)
                if val["has_value"] or probs["away_win"] >= 0.60:
                    conf = round(probs["away_win"] * 100.0, 1)
                    pick = self._make_pick(
                        match_name, start_time,
                        f"Gana Visitante: {away}",
                        f"Modelo Poisson + Elo: {conf}% prob. (Cuota justa: {val['fair_odd']} | Cuota casa: {odd_away}). EV: +{val['ev_pct']}%",
                        conf,
                        odd=str(odd_away),
                        odd_num=odd_away,
                        value_info=val
                    )

            # ── EVALUAR OVER 2.5 ──
            if not pick and probs["over_2_5"] >= 0.62:
                conf = round(probs["over_2_5"] * 100.0, 1)
                est_odd = round(1.0 / probs["over_2_5"] * 1.08, 2)  # Cuota aproximada de mercado
                pick = self._make_pick(
                    match_name, start_time,
                    "Más de 2.5 Goles (Pre-partido)",
                    f"Poisson: {conf}% prob. de Over 2.5 (Goles esperados: {probs['expected_total_goals']}).",
                    conf,
                    odd=f"~{est_odd}",
                    odd_num=est_odd
                )

            # ── EVALUAR AMBOS MARCAN (BTTS) ──
            elif not pick and probs["btts_yes"] >= 0.60:
                conf = round(probs["btts_yes"] * 100.0, 1)
                est_odd = round(1.0 / probs["btts_yes"] * 1.08, 2)
                pick = self._make_pick(
                    match_name, start_time,
                    "Ambos Equipos Marcarán: Sí",
                    f"Poisson: {conf}% prob. de que ambos marquen (λH={probs['lambda_home']}, λA={probs['lambda_away']}).",
                    conf,
                    odd=f"~{est_odd}",
                    odd_num=est_odd
                )

            # ── EVALUAR DOBLE OPORTUNIDAD 1X ──
            elif not pick and probs["double_chance_1x"] >= 0.78:
                conf = round(probs["double_chance_1x"] * 100.0, 1)
                est_odd = round(1.0 / probs["double_chance_1x"] * 1.05, 2)
                pick = self._make_pick(
                    match_name, start_time,
                    f"Doble Oportunidad: {home} o Empate (1X)",
                    f"Alta solvencia de local: {conf}% de probabilidad combinada.",
                    conf,
                    odd=f"~{est_odd}",
                    odd_num=est_odd
                )

            if pick and pick["confidence"] >= self.CONFIANZA_MINIMA:
                picks.append(pick)
                seen.add(gid)

        logger.info(f"Upcoming Analyzer: {len(picks)} pronósticos pre-partido generados.")
        return picks

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_pick(
        match: str, minute: Any, market: str, reason: str, confidence: float,
        odd: str = "Validada ✅", odd_num: float = 1.65, value_info: Optional[dict] = None
    ) -> dict:
        p = {
            "match": match,
            "minute": minute,
            "market": market,
            "reason": reason,
            "confidence": float(confidence),
            "odd": odd,
            "odd_num": float(odd_num)
        }
        if value_info:
            p["value_info"] = value_info
        return p

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _lambda_por_liga(self, competition_name: str) -> float:
        """Estima el promedio de goles por partido según la liga."""
        name_lower = competition_name.lower()
        ligas_altas = ["premier", "bundesliga", "serie a", "la liga", "ligue 1",
                       "eredivisie", "champions", "europa"]
        ligas_medias = ["segunda", "championship", "serie b", "2. bundesliga",
                        "brasileirao", "betplay", "liga profesional", "primera", "mls"]
        for l in ligas_altas:
            if l in name_lower:
                return self.GOLES_LIGA_ALTA
        for l in ligas_medias:
            if l in name_lower:
                return self.GOLES_LIGA_MEDIA
        return self.GOLES_LIGA_BAJA
