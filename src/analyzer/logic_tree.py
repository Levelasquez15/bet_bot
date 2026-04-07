import logging
import math
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class LogicTreeAnalyzer:
    """
    Motor de análisis multi-mercado para apuestas de fútbol.
    Cubre partidos EN VIVO y PRÓXIMOS con diferentes estrategias.
    """

    CONFIANZA_MINIMA = 68

    # ── Parámetros de Liga (promedio goles/partido por categoría) ────────────
    # Usado en modelo Poisson para pre-partido
    GOLES_LIGA_ALTA = 2.7   # Premier, La Liga, Bundesliga, Serie A, etc.
    GOLES_LIGA_MEDIA = 2.4  # Segunda división, ligas medianas
    GOLES_LIGA_BAJA  = 2.1  # Ligas menores

    def analyze_live(self, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analiza partidos EN VIVO con árboles de decisión."""
        picks = []
        seen = set()

        for game in games:
            gid = game.get("id", "")
            if gid in seen:
                continue

            # Filtro estricto: descartar si no tiene información de apuestas (no está en casas de apuestas)
            has_odds = bool(game.get("odds")) or bool(game.get("bookmakers"))
            if not has_odds:
                continue

            home = game.get("homeCompetitor", {}).get("name", "Local")
            away = game.get("awayCompetitor", {}).get("name", "Visitante")
            match_name = f"{home} - {away}"
            sh = self._safe_int(game.get("homeCompetitor", {}).get("score", 0))
            sa = self._safe_int(game.get("awayCompetitor", {}).get("score", 0))
            minute = self._safe_int(game.get("gameTime", 0))

            if minute < 0:
                continue

            total_goles = sh + sa
            diff = abs(sh - sa)
            is_half_time = game.get("statusGroup") == 3

            pick = None

            # ── ÁRBOL 1: Empate tardío → Próximo Gol ──────────────────────
            if minute >= 65 and sh == sa:
                pick = self._make_pick(
                    match_name, minute,
                    "Próximo Gol (Cualquiera)",
                    f"Empate {sh}-{sa} en min {minute}. Ambos equipos presionan para desempatar.",
                    76.0
                )

            # ── ÁRBOL 2: Perdiendo por 1 en 2T → Más Corners ─────────────
            elif minute >= 60 and diff == 1:
                perdedor = home if sh < sa else away
                pick = self._make_pick(
                    match_name, minute,
                    f"Más de 2 Córners ({perdedor})",
                    f"{perdedor} pierde {sh}-{sa} y atacará desesperadamente.",
                    82.0
                )

            # ── ÁRBOL 3: Partido vivo sin goles antes del 60 → Under 1.5 ─
            elif 40 <= minute <= 60 and total_goles == 0:
                pick = self._make_pick(
                    match_name, minute,
                    "Menos de 1.5 Goles (Under 1.5)",
                    f"Sin goles hasta min {minute}. Partido muy cerrado.",
                    72.0
                )

            # ── ÁRBOL 4: 2+ goles antes del 55 → Over 2.5 se cumplirá ──
            elif minute <= 55 and total_goles >= 2:
                pick = self._make_pick(
                    match_name, minute,
                    "Más de 2.5 Goles en el partido",
                    f"Ya van {total_goles} goles en min {minute}. Partido muy abierto.",
                    79.0
                )

            # ── ÁRBOL 5: Ambos marcaron en 2T → BTTS Sí confirmado ───────
            elif minute >= 60 and sh > 0 and sa > 0 and total_goles >= 2:
                pick = self._make_pick(
                    match_name, minute,
                    "Ambos Equipos Marcarán: Sí ✅",
                    f"Ambos ya marcaron. Resultado {sh}-{sa} en min {minute}.",
                    74.5
                )

            # ── ÁRBOL 6: Goleada temprana → Over 3.5 ─────────────────────
            elif minute <= 70 and diff >= 2 and total_goles >= 3:
                pick = self._make_pick(
                    match_name, minute,
                    "Más de 3.5 Goles en el partido",
                    f"Marcador {sh}-{sa} en min {minute}. Partido completamente abierto.",
                    80.0
                )

            # ── ÁRBOL 7: Primer tiempo activo (1+ gol antes 35) → Over 1.5 2T
            elif minute <= 35 and total_goles >= 1:
                pick = self._make_pick(
                    match_name, minute,
                    "Más de 1.5 Goles en el Segundo Tiempo",
                    f"Ya hay {total_goles} gol(es) en min {minute}. Partido con ritmo.",
                    71.0
                )

            # ── ÁRBOL 8: MEDIO TIEMPO, la cabeza tiene 2+ goles → Over 2.5
            elif is_half_time and total_goles >= 2:
                pick = self._make_pick(
                    match_name, "MT",
                    "Más de 2.5 Goles en el partido",
                    f"Ya van {total_goles} goles al medio tiempo. Muy probable superar 2.5.",
                    83.0
                )

            if pick and pick["confidence"] >= self.CONFIANZA_MINIMA:
                picks.append(pick)
                seen.add(gid)

        logger.info(f"Live: {len(picks)} picks de valor en {len(games)} partidos.")
        return picks

    def analyze_upcoming(self, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analiza partidos PRÓXIMOS usando modelo Poisson y factores de riesgo."""
        picks = []
        seen = set()

        for game in games:
            gid = game.get("id", "")
            if gid in seen:
                continue

            # Filtro estricto: descartar si no tiene información de apuestas
            has_odds = bool(game.get("odds")) or bool(game.get("bookmakers"))
            if not has_odds:
                continue

            home = game.get("homeCompetitor", {}).get("name", "Local")
            away = game.get("awayCompetitor", {}).get("name", "Visitante")
            match_name = f"{home} - {away}"
            start_time = game.get("startTime", "")[:16].replace("T", " ")

            # Obtener cuotas si están disponibles
            odds_data = game.get("odds", {})
            odds_over25 = self._extract_odd(odds_data, "over_2.5")
            odds_btts   = self._extract_odd(odds_data, "btts_yes")

            # Análisis Poisson basado en liga
            competition = game.get("competition", {}).get("name", "")
            lambda_goles = self._lambda_por_liga(competition)
            prob_over25 = self._poisson_over(lambda_goles, 2.5)
            prob_over15 = self._poisson_over(lambda_goles, 1.5)

            pick = None

            # ── PRE-PARTIDO 1: Alta probabilidad Over 2.5 por Poisson ─────
            if prob_over25 >= 0.55:
                confianza = round(min(prob_over25 * 100, 85), 1)
                pick = self._make_pick(
                    match_name, start_time,
                    "Más de 2.5 Goles (Pre-partido)",
                    f"Modelo Poisson: {confianza}% prob. de Over 2.5 | Liga: {competition}",
                    confianza
                )

            # ── PRE-PARTIDO 2: Liga muy goleadora + prob alta Over 1.5 ───
            elif prob_over15 >= 0.75 and prob_over25 < 0.55:
                confianza = round(min(prob_over15 * 100 * 0.9, 82), 1)
                pick = self._make_pick(
                    match_name, start_time,
                    "Más de 1.5 Goles (Pre-partido)",
                    f"Modelo Poisson: {round(prob_over15*100,1)}% prob. de Over 1.5 | Liga: {competition}",
                    confianza
                )

            if pick and pick["confidence"] >= self.CONFIANZA_MINIMA:
                picks.append(pick)
                seen.add(gid)

        logger.info(f"Upcoming: {len(picks)} picks de valor en {len(games)} próximos partidos.")
        return picks

    def analyze_games(self, games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Wrapper para compatibilidad (solo live)."""
        return self.analyze_live(games)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_pick(match, minute, market, reason, confidence, odd="Validada ✅") -> dict:
        return {
            "match": match,
            "minute": minute,
            "market": market,
            "reason": reason,
            "confidence": float(confidence),
            "odd": odd
        }

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _extract_odd(odds_data: dict, key: str) -> float:
        """Extrae cuota de apuesta si está disponible."""
        try:
            return float(odds_data.get(key, 0))
        except (TypeError, ValueError):
            return 0.0

    def _lambda_por_liga(self, competition_name: str) -> float:
        """Estima lambda (goles esperados) según prestigio de la liga."""
        name_lower = competition_name.lower()
        ligas_altas = ["premier", "bundesliga", "serie a", "la liga", "ligue 1",
                       "eredivisie", "champions", "europa"]
        ligas_medias = ["segunda", "championship", "serie b", "2. bundesliga",
                        "brasileirao", "primera", "mls"]
        for l in ligas_altas:
            if l in name_lower:
                return self.GOLES_LIGA_ALTA
        for l in ligas_medias:
            if l in name_lower:
                return self.GOLES_LIGA_MEDIA
        return self.GOLES_LIGA_BAJA

    @staticmethod
    def _poisson_prob(lam: float, k: int) -> float:
        """P(X = k) con distribución Poisson."""
        return (math.exp(-lam) * (lam ** k)) / math.factorial(k)

    def _poisson_over(self, lam: float, threshold: float) -> float:
        """Probabilidad de que los goles totales superen el umbral (threshold)."""
        k_max = int(threshold)
        prob_under_or_equal = sum(self._poisson_prob(lam, k) for k in range(k_max + 1))
        return round(1 - prob_under_or_equal, 4)
