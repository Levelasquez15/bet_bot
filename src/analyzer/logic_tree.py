import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class LogicTreeAnalyzer:
    """
    Evalúa cada juego según reglas condicionales estáticas (Árboles de decisión simulados).
    Genera predicciones y señala apuestas de valor (Value Bets).
    """

    def __init__(self):
        # Configurar umbrales, por ejemplo:
        self.umbral_goles = 2.5
        self.umbral_corners = 9.5

    def analyze_games(self, games_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recibe una lista de juegos desde el scraper y aplica lógica de evaluación."""
        valuables = []

        for game in games_data:
            # Extraer vectores de información
            # (Dependerá de la estructura exacta de 365scores)
            home_team = game.get("homeCompetitor", {}).get("name", "Local")
            away_team = game.get("awayCompetitor", {}).get("name", "Visitante")
            
            # Simulamos leer las estadísticas (posesión, tiros, etc.)
            # Para esto necesitaríamos que el scraper extraiga gameDetails, 
            # pero por ahora parseamos la base.
            status = game.get("gameTime", 0) # Minuto de partido
            score_home = game.get("homeCompetitor", {}).get("score", 0)
            score_away = game.get("awayCompetitor", {}).get("score", 0)
            
            # -------------------------------------------------------------
            # EJEMPLO DE ÁRBOL DE DECISIÓN LÓGICO PARA MERCADOS EN VIVO
            # -------------------------------------------------------------
            if status > 70:  # Si el partido va en el minuto 70+
                if score_home == score_away:
                    # RAMA 1: Empate tardío empuja a equipos a buscar gol
                    # Valor: "Más de X goles" (Siguiente Gol)
                    valuables.append({
                        "match": f"{home_team} vs {away_team}",
                        "minute": status,
                        "market": "Próximo Gol (Cualquiera)",
                        "reason": "Empate en min >70. Equipos buscan desempatar.",
                        "confidence": 75.5
                    })
                elif abs(score_home - score_away) == 1:
                    # RAMA 2: Diferencia de 1 gol -> El perdedor ataca a muerte
                    # Valor: "Corners" (Over del equipo perdedor)
                    perdedor = home_team if score_home < score_away else away_team
                    valuables.append({
                        "match": f"{home_team} vs {away_team}",
                        "minute": status,
                        "market": f"Más de 1.5 Córners adicionales ({perdedor})",
                        "reason": "Equipo perdiendo apretará el acelerador.",
                        "confidence": 82.0
                    })
            
            # Próximamente: 
            # Agregar soporte para "Jugador marca gol", "Tarjetas amarillas", "Hándicap Asiático"
            
        return valuables
