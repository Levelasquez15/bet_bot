import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class LogicTreeAnalyzer:
    """
    Evalúa cada juego en vivo con múltiples árboles de decisión.
    Genera señales de apuestas de valor (Value Bets) en varios mercados.
    """

    # Umbrales de tiempo
    MIN_PRIMER_TIEMPO = 35   # Señales de primer tiempo
    MIN_SEGUNDO_TIEMPO = 65  # Señales de segundo tiempo
    MIN_FINAL = 75           # Señales de final del partido

    # Confianzas mínimas para generar pick
    CONFIANZA_MINIMA = 68

    def analyze_games(self, games_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recibe lista de juegos del scraper y devuelve picks de valor."""
        valuables = []
        already_alerted = set()  # Evita duplicados por partido

        for game in games_data:
            game_id = game.get("id", "")
            if game_id in already_alerted:
                continue

            home = game.get("homeCompetitor", {}).get("name", "Local")
            away = game.get("awayCompetitor", {}).get("name", "Visitante")
            match_name = f"{home} - {away}"

            score_home = self._safe_int(game.get("homeCompetitor", {}).get("score", 0))
            score_away = self._safe_int(game.get("awayCompetitor", {}).get("score", 0))
            minute = self._safe_int(game.get("gameTime", 0))
            total_goles = score_home + score_away

            # ── ÁRBOL 1: Empate tardío → Siguiente gol ─────────────────────
            if minute >= self.MIN_SEGUNDO_TIEMPO:
                if score_home == score_away:
                    pick = {
                        "match": match_name,
                        "minute": minute,
                        "market": "Próximo Gol (Cualquiera)",
                        "reason": f"Empate {score_home}-{score_away} en min {minute}. Ambos equipos buscan desempatar.",
                        "confidence": 76.0
                    }
                    valuables.append(pick)
                    already_alerted.add(game_id)
                    continue

            # ── ÁRBOL 2: Diferencia de 1 gol tard. → Corners del perdedor ──
            if minute >= self.MIN_SEGUNDO_TIEMPO:
                diff = abs(score_home - score_away)
                if diff == 1:
                    perdedor = home if score_home < score_away else away
                    pick = {
                        "match": match_name,
                        "minute": minute,
                        "market": f"Más de 1.5 Córners adicionales ({perdedor})",
                        "reason": f"{perdedor} va perdiendo {score_home}-{score_away} en min {minute} y buscará el empate.",
                        "confidence": 82.0
                    }
                    valuables.append(pick)
                    already_alerted.add(game_id)
                    continue

            # ── ÁRBOL 3: Primer tiempo sin goles → Ambos Marcan (BTTS NO) ──
            if self.MIN_PRIMER_TIEMPO <= minute <= 44:
                if total_goles == 0:
                    pick = {
                        "match": match_name,
                        "minute": minute,
                        "market": "Ambos Equipos Marcarán: No",
                        "reason": f"Sin goles hasta el min {minute}. Alta probabilidad de que acabe 0-0 el primer tiempo.",
                        "confidence": 70.0
                    }
                    valuables.append(pick)
                    already_alerted.add(game_id)
                    continue

            # ── ÁRBOL 4: 2+ goles en primera hora → Más de 2.5 goles ──────
            if minute <= 60 and total_goles >= 2:
                pick = {
                    "match": match_name,
                    "minute": minute,
                    "market": "Más de 2.5 Goles en el partido",
                    "reason": f"Ya van {total_goles} goles en el min {minute}. Partido muy activo.",
                    "confidence": 79.0
                }
                valuables.append(pick)
                already_alerted.add(game_id)
                continue

            # ── ÁRBOL 5: Segundo tiempo, empate con 2+ goles → BTTS Sí ─────
            if minute >= self.MIN_SEGUNDO_TIEMPO:
                if total_goles >= 2 and score_home > 0 and score_away > 0:
                    pick = {
                        "match": match_name,
                        "minute": minute,
                        "market": "Ambos Equipos Marcarán: Sí",
                        "reason": f"Ambos ya marcaron ({score_home}-{score_away}) y el partido sigue activo en min {minute}.",
                        "confidence": 74.5
                    }
                    valuables.append(pick)
                    already_alerted.add(game_id)
                    continue

            # ── ÁRBOL 6: Paliza (ventaja de 2+) → Más de 3.5 goles ─────────
            if minute <= 70 and abs(score_home - score_away) >= 2 and total_goles >= 3:
                pick = {
                    "match": match_name,
                    "minute": minute,
                    "market": "Más de 3.5 Goles en el partido",
                    "reason": f"Marcador {score_home}-{score_away} en min {minute}. Partido muy abierto.",
                    "confidence": 80.0
                }
                valuables.append(pick)
                already_alerted.add(game_id)
                continue

        # Filtrar por confianza mínima
        result = [p for p in valuables if p["confidence"] >= self.CONFIANZA_MINIMA]
        logger.info(f"Análisis completo: {len(result)} picks de valor encontrados.")
        return result

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
