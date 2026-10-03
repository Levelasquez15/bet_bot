"""
Scraper de Respaldo para Flashscore (MisMarcadores).
Módulo de contingencia para enriquecer estadísticas en vivo cuando 365scores no cuenta con telemetría.
Consulta los feeds directos de Flashscore Ninja con xG, posesión, tiros a puerta y córners.
"""

import logging
import asyncio
import httpx
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

FLASHSCORE_FEED_URL = "https://global.flashscore.ninja/2/x/feed/f_1_1_3_es_1"
FLASHSCORE_STATS_URL = "https://global.flashscore.ninja/2/x/feed/df_st_1_{match_id}"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://www.flashscore.com",
    "Referer": "https://www.flashscore.com/",
    "x-fsign": "SW9D1eZo",
}


class FlashscoreFallbackScraper:
    """
    Scraper de respaldo secundario para Flashscore.
    Se activa únicamente si 365scores no posee estadísticas detalladas en vivo de un partido.
    """

    def __init__(self, timeout: float = 6.0):
        self.timeout = timeout

    async def find_stats_for_teams(self, home_team: str, away_team: str) -> Optional[Dict[str, Any]]:
        """
        Busca un partido en vivo en Flashscore por nombres de equipo y extrae sus estadísticas.
        """
        try:
            async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout) as client:
                # 1. Obtener listado de partidos en vivo de Flashscore
                resp = await client.get(FLASHSCORE_FEED_URL)
                if resp.status_code != 200 or not resp.text:
                    return None

                match_id = self._match_teams_in_feed(resp.text, home_team, away_team)
                if not match_id:
                    return None

                # 2. Consultar feed de estadísticas del partido
                stats_url = FLASHSCORE_STATS_URL.format(match_id=match_id)
                stats_resp = await client.get(stats_url)
                if stats_resp.status_code != 200 or not stats_resp.text:
                    return None

                parsed = self._parse_flashscore_stats(stats_resp.text)
                if parsed and parsed.get("has_stats"):
                    logger.info(f"Flashscore Scraper: Estadísticas de respaldo recuperadas para {home_team} vs {away_team}")
                    return parsed

        except Exception as e:
            logger.debug(f"FlashscoreFallbackScraper: No se pudieron obtener estadísticas ({e})")

        return None

    def _match_teams_in_feed(self, feed_text: str, home_team: str, away_team: str) -> Optional[str]:
        """Localiza el ID del partido en el feed de Flashscore comparando nombres de equipos."""
        h_clean = self._clean_team_name(home_team)
        a_clean = self._clean_team_name(away_team)

        parts = feed_text.split("~AA÷")
        for chunk in parts[1:]:
            fields = {}
            for item in chunk.split("¬"):
                if "÷" in item:
                    k, v = item.split("÷", 1)
                    fields[k] = v

            mid = chunk.split("¬")[0]
            cx_home = self._clean_team_name(fields.get("CX", ""))
            af_away = self._clean_team_name(fields.get("AF", ""))

            # Coincidencia directa o parcial
            if (h_clean in cx_home or cx_home in h_clean) and (a_clean in af_away or af_away in a_clean):
                return mid

        return None

    def _parse_flashscore_stats(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """Parsea el payload estructurado con delimitadores de Flashscore."""
        stats = {
            "has_stats": False,
            "source": "Flashscore",
            "possession": {"home": 50.0, "away": 50.0},
            "xg": {"home": 0.0, "away": 0.0},
            "shots_total": {"home": 0, "away": 0},
            "shots_on_target": {"home": 0, "away": 0},
            "corners": {"home": 0, "away": 0},
            "yellow_cards": {"home": 0, "away": 0},
            "red_cards": {"home": 0, "away": 0},
        }

        found_any = False
        chunks = raw_text.split("~SD÷")
        for chunk in chunks:
            fields = {}
            for item in chunk.split("¬"):
                if "÷" in item:
                    k, v = item.split("÷", 1)
                    fields[k] = v

            name = fields.get("SG", "").lower()
            val_h = fields.get("SH", "").replace("%", "").strip()
            val_a = fields.get("SI", "").replace("%", "").strip()

            if not name or not val_h:
                continue

            try:
                if "expected goals" in name or "xg" in name:
                    stats["xg"]["home"] = float(val_h)
                    stats["xg"]["away"] = float(val_a)
                    found_any = True
                elif "possession" in name or "posesi" in name:
                    stats["possession"]["home"] = float(val_h)
                    stats["possession"]["away"] = float(val_a)
                    found_any = True
                elif "shots on target" in name or "remates a puerta" in name:
                    stats["shots_on_target"]["home"] = int(float(val_h))
                    stats["shots_on_target"]["away"] = int(float(val_a))
                    found_any = True
                elif "total shots" in name or "total remates" in name:
                    stats["shots_total"]["home"] = int(float(val_h))
                    stats["shots_total"]["away"] = int(float(val_a))
                    found_any = True
                elif "corner" in name or "esquina" in name:
                    stats["corners"]["home"] = int(float(val_h))
                    stats["corners"]["away"] = int(float(val_a))
                    found_any = True
                elif "yellow" in name or "amarilla" in name:
                    stats["yellow_cards"]["home"] = int(float(val_h))
                    stats["yellow_cards"]["away"] = int(float(val_a))
                elif "red" in name or "roja" in name:
                    stats["red_cards"]["home"] = int(float(val_h))
                    stats["red_cards"]["away"] = int(float(val_a))
            except (ValueError, TypeError):
                continue

        stats["has_stats"] = found_any
        return stats if found_any else None

    @staticmethod
    def _clean_team_name(name: str) -> str:
        """Normaliza nombres de equipos removiendo caracteres especiales y mayúsculas."""
        cleaned = name.lower()
        for prefix in ["fc ", "cf ", "cd ", "deportivo ", "atletico ", "atl. "]:
            cleaned = cleaned.replace(prefix, "")
        return cleaned.strip()
