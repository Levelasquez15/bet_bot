import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from src.scraper.leagues import classify_competition, is_valid_match

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


def extract_match_odds(game: dict) -> Dict[str, Any]:
    """
    Extrae y normaliza las cuotas decimales del nodo de 365scores.
    Retorna cuotas 1X2 (Home, Draw, Away) y disponibilidad.
    """
    odds_node = game.get("odds")
    result = {
        "has_odds": False,
        "home": None,
        "draw": None,
        "away": None,
        "bookmaker": "365Scores"
    }

    if not isinstance(odds_node, dict):
        return result

    options = odds_node.get("options", [])
    if not options or not isinstance(options, list):
        return result

    for opt in options:
        name = str(opt.get("name", "")).strip().upper()
        rate_dict = opt.get("rate", {})
        try:
            decimal_rate = float(rate_dict.get("decimal", 0))
        except (TypeError, ValueError):
            decimal_rate = 0.0

        if decimal_rate > 1.0:
            if name == "1":
                result["home"] = decimal_rate
            elif name in ("X", "EMPATE", "DRAW"):
                result["draw"] = decimal_rate
            elif name == "2":
                result["away"] = decimal_rate

    if result["home"] or result["draw"] or result["away"]:
        result["has_odds"] = True

    return result


class Scraper365:
    """Motor robusto de recolección de datos en tiempo real de 365scores."""

    BASE_URL = "https://webws.365scores.com/web/games/"

    def __init__(self, timeout: float = 30.0):
        # Transport con reintentos automáticos para evitar microcortes de red
        transport = httpx.AsyncHTTPTransport(retries=3)
        self.session = httpx.AsyncClient(
            transport=transport,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True
        )

    def _today_str(self) -> str:
        today = datetime.now(tz=BOGOTA_TZ)
        return today.strftime("%d/%m/%Y")

    def _tomorrow_str(self) -> str:
        tomorrow = datetime.now(tz=BOGOTA_TZ) + timedelta(days=1)
        return tomorrow.strftime("%d/%m/%Y")

    def _base_params(self, include_tomorrow: bool = False) -> dict:
        return {
            "appTypeId": "5",
            "langId": "29",
            "timezoneName": "America/Bogota",
            "userCountryId": "170",
            "sports": "1",
            "showOdds": "true",
            "startDate": self._today_str(),
            "endDate": self._tomorrow_str() if include_tomorrow else self._today_str(),
        }

    async def _fetch_games(self, include_tomorrow: bool = False) -> List[Dict[str, Any]]:
        """Consulta los partidos crudos desde la API web de 365scores."""
        try:
            params = self._base_params(include_tomorrow=include_tomorrow)
            response = await self.session.get(self.BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            games = data.get("games", [])
            return games
        except httpx.TimeoutException:
            logger.error("Timeout conectando a 365scores (se agotó el tiempo de espera).")
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP {e.response.status_code} en 365scores.")
            return []
        except Exception as e:
            logger.error(f"Error inesperado en fetch_games: {e}")
            return []

    async def fetch_live_matches(self, filter_leagues: bool = True, min_tier: int = 3) -> List[Dict[str, Any]]:
        """
        Devuelve partidos EN VIVO (en juego + medio tiempo),
        enriquecidos con cuotas y filtrados por relevancia de liga.
        """
        games = await self._fetch_games(include_tomorrow=False)
        live = []

        for g in games:
            # Solo partidos en juego o medio tiempo
            if g.get("statusGroup") not in (STATUS_LIVE, STATUS_HALF_TIME):
                continue

            # Filtro inteligente de ligas (ignorar juveniles, 7ª división, amateurs)
            if filter_leagues and not is_valid_match(g, min_tier=min_tier):
                continue

            # Enriquecer con cuotas normalizadas
            g["parsed_odds"] = extract_match_odds(g)
            live.append(g)

        logger.info(f"Partidos en vivo detectados (filtrados): {len(live)}")
        return live

    async def fetch_upcoming_matches(self, hours_ahead: int = 4, filter_leagues: bool = True, min_tier: int = 3) -> List[Dict[str, Any]]:
        """
        Próximos partidos programados para las siguientes N horas,
        filtrados por calidad de liga y con cuotas extraídas.
        """
        games = await self._fetch_games(include_tomorrow=True)
        now = datetime.now(tz=BOGOTA_TZ)
        limit = now + timedelta(hours=hours_ahead)
        upcoming = []

        for g in games:
            if g.get("statusGroup") != STATUS_UPCOMING:
                continue

            # Filtro inteligente de ligas
            if filter_leagues and not is_valid_match(g, min_tier=min_tier):
                continue

            start_str = g.get("startTime", "")
            try:
                start_dt = datetime.fromisoformat(start_str)
                if now <= start_dt <= limit:
                    g["parsed_odds"] = extract_match_odds(g)
                    upcoming.append(g)
            except Exception:
                continue

        logger.info(f"Próximos partidos en las próximas {hours_ahead}h: {len(upcoming)}")
        return upcoming

    async def fetch_all_for_debug(self) -> dict:
        """Devuelve diagnóstico completo del estado del scraper y datos en tiempo real."""
        games = await self._fetch_games(include_tomorrow=True)
        live_games = await self.fetch_live_matches(filter_leagues=True)
        upcoming = await self.fetch_upcoming_matches(hours_ahead=4, filter_leagues=True)

        return {
            "total_raw": len(games),
            "live_filtered": len(live_games),
            "upcoming_filtered": len(upcoming),
            "live_sample": [
                f"{g.get('homeCompetitor',{}).get('name','?')} {g.get('homeCompetitor',{}).get('score',0)}-{g.get('awayCompetitor',{}).get('score',0)} {g.get('awayCompetitor',{}).get('name','?')} (min {int(float(g.get('gameTime',0)))}) [{g.get('competitionDisplayName')}]"
                for g in live_games[:5]
            ],
            "upcoming_sample": [
                f"{g.get('homeCompetitor',{}).get('name','?')} vs {g.get('awayCompetitor',{}).get('name','?')} ({g.get('startTime','')[:16]}) [{g.get('competitionDisplayName')}]"
                for g in upcoming[:5]
            ]
        }

    async def close(self):
        """Cierra la sesión HTTP."""
        await self.session.aclose()
