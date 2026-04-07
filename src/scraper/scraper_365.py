import logging
import httpx
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://www.365scores.com",
    "Referer": "https://www.365scores.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# Deportes a monitorear (1=Fútbol)
SPORT_IDS = "1"

class Scraper365:
    """Motor de recolección de datos de 365scores."""

    def __init__(self):
        self.base_url = "https://webws.365scores.com/web/games/current/"
        self.session = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=20.0,
            follow_redirects=True
        )

    async def fetch_live_matches(self) -> List[Dict[str, Any]]:
        """Obtiene partidos EN VIVO en curso en este momento."""
        try:
            params = {
                "appTypeId": "5",
                "langId": "29",
                "timezoneName": "America/Bogota",
                "userCountryId": "170",
                "sports": SPORT_IDS,
                "showOdds": "true",
            }

            logger.info("Consultando partidos en vivo a 365scores...")
            response = await self.session.get(self.base_url, params=params)
            response.raise_for_status()

            data = response.json()
            all_games = data.get("games", [])
            logger.info(f"Total partidos recibidos: {len(all_games)}")

            # Filtrar solo los que están EN VIVO (statusGroup 2 = en curso)
            # statusGroup: 1=programado, 2=en juego, 3=finalizado, 4=cancelado
            live_games = [
                g for g in all_games
                if g.get("statusGroup") == 2
            ]

            logger.info(f"Partidos en vivo (en juego): {len(live_games)}")

            # Log de partidos para debugging
            for g in live_games[:5]:
                home = g.get("homeCompetitor", {}).get("name", "?")
                away = g.get("awayCompetitor", {}).get("name", "?")
                minute = g.get("gameTime", "?")
                sh = g.get("homeCompetitor", {}).get("score", "?")
                sa = g.get("awayCompetitor", {}).get("score", "?")
                logger.info(f"  ⚽ {home} {sh} - {sa} {away} | min {minute}")

            return live_games

        except httpx.HTTPStatusError as e:
            logger.error(f"Error HTTP {e.response.status_code} al consultar 365scores: {e}")
            return []
        except httpx.TimeoutException:
            logger.error("Timeout al conectar con 365scores.")
            return []
        except Exception as e:
            logger.error(f"Error inesperado en scraper_365: {e}")
            return []

    async def close(self):
        await self.session.aclose()
