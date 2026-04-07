import logging
import httpx
from datetime import datetime, timezone, timedelta
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

# statusGroup codes de 365scores
STATUS_UPCOMING  = 1
STATUS_LIVE      = 2
STATUS_HALF_TIME = 3
STATUS_FINISHED  = 4

BOGOTA_TZ = timezone(timedelta(hours=-5))


class Scraper365:
    """Motor de recolección de datos de 365scores. Usa el endpoint /web/games/ (verificado)."""

    BASE_URL = "https://webws.365scores.com/web/games/"

    def __init__(self):
        self.session = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=20.0,
            follow_redirects=True
        )

    def _today_str(self) -> str:
        today = datetime.now(tz=BOGOTA_TZ)
        return today.strftime("%d/%m/%Y")

    def _base_params(self) -> dict:
        return {
            "appTypeId": "5",
            "langId": "29",
            "timezoneName": "America/Bogota",
            "userCountryId": "170",
            "sports": "1",
            "showOdds": "true",
            "startDate": self._today_str(),
            "endDate": self._today_str(),
        }

    async def _fetch_games(self) -> List[Dict[str, Any]]:
        """Fetches all games for today from the working 365scores endpoint."""
        try:
            params = self._base_params()
            logger.info(f"Consultando 365scores para {params['startDate']}...")
            response = await self.session.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            games = data.get("games", [])
            logger.info(f"Total partidos del día: {len(games)}")
            return games
        except httpx.TimeoutException:
            logger.error("Timeout conectando a 365scores.")
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code} en 365scores.")
            return []
        except Exception as e:
            logger.error(f"Error inesperado en fetch_games: {e}")
            return []

    async def fetch_live_matches(self) -> List[Dict[str, Any]]:
        """Partidos EN VIVO ahora mismo (en juego + medio tiempo)."""
        games = await self._fetch_games()
        live = [g for g in games if g.get("statusGroup") in (STATUS_LIVE, STATUS_HALF_TIME)]
        logger.info(f"Partidos en vivo: {len(live)}")
        return live

    async def fetch_upcoming_matches(self, hours_ahead: int = 3) -> List[Dict[str, Any]]:
        """Próximos partidos que empiezan en las siguientes N horas."""
        games = await self._fetch_games()
        now = datetime.now(tz=BOGOTA_TZ)
        limit = now + timedelta(hours=hours_ahead)
        upcoming = []
        for g in games:
            if g.get("statusGroup") != STATUS_UPCOMING:
                continue
            start_str = g.get("startTime", "")
            try:
                # 365scores devuelve formato ISO: "2026-04-07T18:00:00-05:00"
                start_dt = datetime.fromisoformat(start_str)
                if now <= start_dt <= limit:
                    upcoming.append(g)
            except Exception:
                continue
        logger.info(f"Próximos partidos (en {hours_ahead}h): {len(upcoming)}")
        return upcoming

    async def fetch_all_for_debug(self) -> dict:
        """Para el comando /debug: estadísticas del scraper."""
        games = await self._fetch_games()
        groups = {1: 0, 2: 0, 3: 0, 4: 0}
        for g in games:
            sg = g.get("statusGroup", 0)
            if sg in groups:
                groups[sg] += 1

        live_games = [g for g in games if g.get("statusGroup") in (STATUS_LIVE, STATUS_HALF_TIME)]
        upcoming = await self.fetch_upcoming_matches(hours_ahead=3)

        return {
            "total": len(games),
            "upcoming": groups[1],
            "live": groups[2] + groups[3],
            "finished": groups[4],
            "upcoming_3h": len(upcoming),
            "live_sample": [
                f"{g.get('homeCompetitor',{}).get('name','?')} {g.get('homeCompetitor',{}).get('score','?')}-{g.get('awayCompetitor',{}).get('score','?')} {g.get('awayCompetitor',{}).get('name','?')} (min {g.get('gameTime','?')})"
                for g in live_games[:5]
            ],
            "upcoming_sample": [
                f"{g.get('homeCompetitor',{}).get('name','?')} vs {g.get('awayCompetitor',{}).get('name','?')} ({g.get('startTime','?')[:16]})"
                for g in upcoming[:5]
            ]
        }

    async def close(self):
        await self.session.aclose()
