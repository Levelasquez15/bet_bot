import logging
import httpx
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Headers básicos para simular comportamiento humano (Web scraping ético)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://www.365scores.com",
    "Referer": "https://www.365scores.com/",
}

class Scraper365:
    """Motor de recolección de datos de 365scores."""
    
    def __init__(self):
        # Endpoints comunes de 365scores (webws proxy interno usualmente)
        # Nota: La estructura exacta puede variar y podría requerir ingenieria inversa en vivo si cambia
        self.base_url = "https://webws.365scores.com/web/games/current"
        self.session = httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=15.0)

    async def fetch_live_matches(self) -> List[Dict[str, Any]]:
        """Consigue los partidos que se están jugando actualmente o los del día."""
        try:
            # appTypeId=5 y langId=29 para español, timezoneName ajustado
            params = {
                "appTypeId": "5",
                "langId": "29", 
                "timezoneName": "America/Bogota",
                "userCountryId": "1" # Varia
            }
            
            logger.info("Solicitando datos en vivo a 365scores...")
            response = await self.session.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            games = data.get("games", [])
            logger.info(f"Se encontraron {len(games)} partidos en total.")
            
            return games

        except httpx.HTTPError as e:
            logger.error(f"Error HTTP al conectar con 365scores: {e}")
            return []
        except Exception as e:
            logger.error(f"Error inesperado en scraper_365: {e}")
            return []

    async def close(self):
        await self.session.aclose()
