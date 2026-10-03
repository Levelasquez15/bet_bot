"""
Nodos Especialistas para el Grafo de Decisión de BetBot.
Encapsulan las 8 heurísticas y modelos matemáticos en agentes especialistas modulares:
1. MomentumSpecialistNode (Ritmo, timing crítico, empate tardío, medio tiempo)
2. SiegeXGSpecialistNode (Asedio territorial, xG, tiros a puerta, córners y cerrojos)
3. PoissonEloValueSpecialistNode (Elo, Poisson bivariado, cuotas reales y Value Betting EV > 0)
4. DisciplinarySpecialistNode (Tarjetas rojas, superioridad numérica, tensión disciplinaria)
"""

import logging
from typing import Optional
from src.graph.state import MatchState, NodeEvaluation
from src.models.elo import EloModel
from src.models.poisson import calculate_poisson_matrix
from src.models.value import calculate_value

logger = logging.getLogger(__name__)


def _safe_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class MomentumSpecialistNode:
    """
    Especialista en Timing, Ritmo de Juego y Presión de Gol Inminente.
    Evalúa la aceleración del marcador y ventanas críticas de tiempo.
    """

    def evaluate(self, state: MatchState) -> Optional[NodeEvaluation]:
        if not state.is_live:
            return None

        minute = self._safe_int(state.minute)
        # Modo Sniper: ventana de apuestas cerrada en minutos finales o relojes anómalos
        if minute <= 0 or minute > 80:
            return None

        sh = state.score_home
        sa = state.score_away
        total_goles = state.total_goals

        stats = state.live_stats
        shots_target_h = stats.get("shots_on_target", {}).get("home", 0)
        shots_target_a = stats.get("shots_on_target", {}).get("away", 0)
        total_shots_target = shots_target_h + shots_target_a

        xg_h = stats.get("xg", {}).get("home", 0.0)
        xg_a = stats.get("xg", {}).get("away", 0.0)
        total_xg = round(xg_h + xg_a, 2)

        # Heurística 1: Empate tardío con llegada constante (Min 62-78) - MODO SNIPER
        if 62 <= minute <= 78 and sh == sa:
            if total_shots_target >= 6 or total_xg >= 1.4:
                return NodeEvaluation(
                    node_name="MomentumSpecialist",
                    recommended_market="Próximo Gol: Habrá al menos 1 gol más",
                    confidence=82.0,
                    estimated_odd=1.75,
                    rationale=f"Empate {sh}-{sa} al min {minute} con asedio ofensivo brutal ({total_shots_target} tiros a puerta, xG {total_xg}).",
                    sentiment="BULLISH_OVER",
                    signals={"minute": minute, "shots_on_target": total_shots_target, "total_xg": total_xg}
                )

        # Heurística 3: Ritmo frenético de goles tempraneros (Min <= 58, 2+ goles) - MODO SNIPER
        if 15 <= minute <= 58 and total_goles >= 2:
            if total_shots_target >= 5 or total_xg >= 1.4:
                return NodeEvaluation(
                    node_name="MomentumSpecialist",
                    recommended_market="Más de 2.5 Goles en el partido",
                    confidence=85.0,
                    estimated_odd=1.60,
                    rationale=f"Ritmo vertiginoso confirmado: {total_goles} goles en min {minute}, {total_shots_target} tiros al arco y xG acumulado de {total_xg}.",
                    sentiment="BULLISH_OVER",
                    signals={"minute": minute, "total_goals": total_goles, "total_xg": total_xg}
                )

        # Heurística 6: Medio Tiempo con 2+ goles anotados
        # Solo válido si es entretiempo explícito y el minuto corresponde al descanso (<= 52)
        if state.is_half_time and (minute <= 52 or minute == 0) and total_goles >= 2:
            return NodeEvaluation(
                node_name="MomentumSpecialist",
                recommended_market="Más de 2.5 Goles en el partido",
                confidence=84.0,
                estimated_odd=1.52,
                rationale=f"Descanso explosivo con {total_goles} goles ({sh}-{sa}). Muy alta correlación de Over 2.5 final.",
                sentiment="BULLISH_OVER",
                signals={"is_half_time": True, "total_goals": total_goles}
            )

        return None

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


class SiegeXGSpecialistNode:
    """
    Especialista en Asedio Territorial, Córners y Generación xG vs Bloqueos Defensivos.
    """

    def evaluate(self, state: MatchState) -> Optional[NodeEvaluation]:
        if not state.is_live:
            return None

        minute = self._safe_int(state.minute)
        # Modo Sniper: ventana de apuestas cerrada en minutos finales o relojes anómalos
        if minute <= 0 or minute > 80:
            return None

        sh = state.score_home
        sa = state.score_away
        diff = state.score_diff
        total_goles = state.total_goals

        stats = state.live_stats
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

        # Heurística 2: Asedio del equipo que pierde por 1 gol -> Córners (Modo Sniper: min 55 a 78)
        if 55 <= minute <= 78 and diff == 1:
            trailing_home = sh < sa
            perdedor = state.home_team if trailing_home else state.away_team
            poss_perdedor = poss_h if trailing_home else poss_a
            tiros_perdedor = shots_target_h if trailing_home else shots_target_a

            if (poss_perdedor >= 56.0 and tiros_perdedor >= 3) or (poss_perdedor >= 62.0 and total_corners >= 5):
                target_corners = total_corners + 2
                return NodeEvaluation(
                    node_name="SiegeXGSpecialist",
                    recommended_market=f"Más de {target_corners}.5 Córners Totales",
                    confidence=81.0,
                    estimated_odd=1.80,
                    rationale=f"{perdedor} pierde por 1 e intensifica el asedio ({poss_perdedor}% posesión, {total_corners} córners actuales).",
                    sentiment="CORNERS_HIGH",
                    signals={"target_corners": target_corners, "corners_now": total_corners, "possession": poss_perdedor}
                )

        # Heurística 4: Partido de Bloqueo / Cerrojo -> Under 1.5 (Modo Sniper: min 48 a 65)
        if 48 <= minute <= 65 and total_goles == 0:
            if total_shots_target <= 2 and total_xg <= 0.45:
                return NodeEvaluation(
                    node_name="SiegeXGSpecialist",
                    recommended_market="Menos de 1.5 Goles (Under 1.5)",
                    confidence=78.5,
                    estimated_odd=1.70,
                    rationale=f"Bloqueo táctico y cerrojo mutuo: 0-0 en min {minute}, solo {total_shots_target} tiros a puerta y xG {total_xg}.",
                    sentiment="BEARISH_UNDER",
                    signals={"minute": minute, "shots_on_target": total_shots_target, "total_xg": total_xg}
                )

        return None

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0


class PoissonEloValueSpecialistNode:
    """
    Especialista Cuantitativo: Ratings Elo, Poisson Bivariado y Value Betting (+EV).
    Modo Francotirador (Sniper): Solo dispara con alta probabilidad y +EV real.
    """

    def __init__(self):
        self.elo = EloModel()

    def evaluate(self, state: MatchState) -> Optional[NodeEvaluation]:
        # Modo Sniper: en vivo, la ventana cuantitativa se restringe al minuto <= 75
        if state.is_live:
            minute = _safe_int(state.minute)
            if minute <= 0 or minute > 75:
                return None

        # Estimar promedio de goles de liga
        base_goals = self._lambda_por_liga(state.competition)

        # 1. Estimar lambdas con Elo
        lambda_h, lambda_a = self.elo.estimate_lambdas(state.home_team, state.away_team, base_league_goals=base_goals)

        # 2. Matriz de Poisson
        probs = calculate_poisson_matrix(lambda_h, lambda_a)

        # 3. Cuotas reales de bookmaker
        odd_home = state.odds.get("home")
        odd_draw = state.odds.get("draw")
        odd_away = state.odds.get("away")

        # Evaluar 1X2 con Value Betting - MODO SNIPER (Prob >= 65% + EV >= 5% o Prob >= 72%)
        if odd_home and probs["home_win"] >= 0.65:
            val = calculate_value(probs["home_win"], odd_home)
            if (val["has_value"] and val.get("ev_pct", 0) >= 5.0) or probs["home_win"] >= 0.72:
                conf = round(probs["home_win"] * 100.0, 1)
                return NodeEvaluation(
                    node_name="PoissonEloValueSpecialist",
                    recommended_market=f"Gana Local: {state.home_team}",
                    confidence=conf,
                    estimated_odd=odd_home,
                    rationale=f"Poisson+Elo Sniper: {conf}% prob. (Cuota justa: {val['fair_odd']} | Cuota casa: {odd_home}). EV: +{val['ev_pct']}%.",
                    sentiment="FAVOR_HOME",
                    signals={"value_info": val, "probs": probs, "type": "1X2_HOME"}
                )

        if odd_away and probs["away_win"] >= 0.60:
            val = calculate_value(probs["away_win"], odd_away)
            if (val["has_value"] and val.get("ev_pct", 0) >= 5.0) or probs["away_win"] >= 0.68:
                conf = round(probs["away_win"] * 100.0, 1)
                return NodeEvaluation(
                    node_name="PoissonEloValueSpecialist",
                    recommended_market=f"Gana Visitante: {state.away_team}",
                    confidence=conf,
                    estimated_odd=odd_away,
                    rationale=f"Poisson+Elo Sniper: {conf}% prob. (Cuota justa: {val['fair_odd']} | Cuota casa: {odd_away}). EV: +{val['ev_pct']}%.",
                    sentiment="FAVOR_AWAY",
                    signals={"value_info": val, "probs": probs, "type": "1X2_AWAY"}
                )

        # Evaluar Over 2.5 goles (estricto >= 70%)
        if probs["over_2_5"] >= 0.70:
            conf = round(probs["over_2_5"] * 100.0, 1)
            est_odd = round(1.0 / probs["over_2_5"] * 1.08, 2)
            return NodeEvaluation(
                node_name="PoissonEloValueSpecialist",
                recommended_market="Más de 2.5 Goles",
                confidence=conf,
                estimated_odd=est_odd,
                rationale=f"Poisson Sniper: {conf}% prob. de Over 2.5 (Goles esperados: {probs['expected_total_goals']}).",
                sentiment="BULLISH_OVER",
                signals={"probs": probs, "type": "OVER_25"}
            )

        # Evaluar Ambos Marcan (BTTS) (estricto >= 68%)
        if probs["btts_yes"] >= 0.68:
            conf = round(probs["btts_yes"] * 100.0, 1)
            est_odd = round(1.0 / probs["btts_yes"] * 1.08, 2)
            return NodeEvaluation(
                node_name="PoissonEloValueSpecialist",
                recommended_market="Ambos Equipos Marcarán: Sí",
                confidence=conf,
                estimated_odd=est_odd,
                rationale=f"Poisson Sniper: {conf}% prob. de BTTS (λH={probs['lambda_home']}, λA={probs['lambda_away']}).",
                sentiment="BULLISH_OVER",
                signals={"probs": probs, "type": "BTTS"}
            )

        # Evaluar Doble Oportunidad 1X (estricto >= 82%)
        if probs["double_chance_1x"] >= 0.82:
            conf = round(probs["double_chance_1x"] * 100.0, 1)
            est_odd = round(1.0 / probs["double_chance_1x"] * 1.05, 2)
            return NodeEvaluation(
                node_name="PoissonEloValueSpecialist",
                recommended_market=f"Doble Oportunidad: {state.home_team} o Empate (1X)",
                confidence=conf,
                estimated_odd=est_odd,
                rationale=f"Fortaleza extrema de local: {conf}% de probabilidad combinada 1X.",
                sentiment="FAVOR_HOME",
                signals={"probs": probs, "type": "1X"}
            )

        return None

    def _lambda_por_liga(self, competition_name: str) -> float:
        name_lower = str(competition_name).lower()
        ligas_altas = ["premier", "bundesliga", "serie a", "la liga", "ligue 1", "eredivisie", "champions", "europa"]
        ligas_medias = ["segunda", "championship", "serie b", "2. bundesliga", "brasileirao", "betplay", "liga profesional", "primera", "mls"]
        for l in ligas_altas:
            if l in name_lower:
                return 2.75
        for l in ligas_medias:
            if l in name_lower:
                return 2.45
        return 2.15


class DisciplinarySpecialistNode:
    """
    Especialista Disciplinario: Tarjetas Rojas, Superioridad Numérica y Riesgo de Descontrol.
    """

    def evaluate(self, state: MatchState) -> Optional[NodeEvaluation]:
        if not state.is_live:
            return None

        minute = self._safe_int(state.minute)
        # Modo Sniper: ventana disciplinaria efectiva entre minuto 30 y 78
        if minute < 30 or minute > 78:
            return None

        stats = state.live_stats
        red_h = stats.get("red_cards", {}).get("home", 0)
        red_a = stats.get("red_cards", {}).get("away", 0)
        poss_h = stats.get("possession", {}).get("home", 50.0)
        poss_a = stats.get("possession", {}).get("away", 50.0)

        # Heurística 5: Ventaja Numérica por Tarjeta Roja (Minuto 30-78)
        if (red_h > 0 or red_a > 0):
            equipo_superior = state.home_team if red_a > 0 else state.away_team
            equipo_inferior = state.away_team if red_a > 0 else state.home_team
            poss_superior = poss_h if red_a > 0 else poss_a
            sentiment = "FAVOR_HOME" if red_a > 0 else "FAVOR_AWAY"

            if poss_superior >= 58.0:
                return NodeEvaluation(
                    node_name="DisciplinarySpecialist",
                    recommended_market=f"Gana o Próximo Gol: {equipo_superior}",
                    confidence=79.5,
                    estimated_odd=1.65,
                    rationale=f"Superioridad numérica: {equipo_inferior} con tarjeta roja. {equipo_superior} controla el balón con {poss_superior}% posesión.",
                    sentiment=sentiment,
                    signals={"red_cards": {"home": red_h, "away": red_a}, "possession_advantage": poss_superior}
                )

        return None

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
