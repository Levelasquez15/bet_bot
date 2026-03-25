from __future__ import annotations

import asyncio
import logging
from typing import Dict

import pandas as pd

try:
    from .football_scraper import api_scraper
except ImportError:
    # For direct execution
    from football_scraper import api_scraper

logger = logging.getLogger(__name__)


async def load_history(context) -> pd.DataFrame:
    """Load historical matches using The Sports DB API."""
    try:
        # Get league name from context or use default
        league_name = getattr(context, 'bot_data', {}).get('league_name', 'English Premier League')
        season = getattr(context, 'bot_data', {}).get('season', '2022-2023')

        # Use the new API scraper
        matches = await asyncio.to_thread(
            api_scraper.get_historical_matches,
            league_name=league_name,
            season=season,
            limit=200
        )

        # If no data for current season, try previous season
        if matches.empty and season > 2020:
            prev_season = f"{int(season.split('-')[0])-1}-{int(season.split('-')[1])-1}"
            matches = await asyncio.to_thread(
                api_scraper.get_historical_matches,
                league_name=league_name,
                season=prev_season,
                limit=200
            )

        logger.info(f"Loaded {len(matches)} historical matches for {league_name} {season}")
        return matches
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return pd.DataFrame()


async def get_upcoming_fixtures(league_id: int, season: int, next_n: int = 10) -> pd.DataFrame:
    """Get upcoming fixtures using The Sports DB API."""
    try:
        # Map league_id to league name (simplified mapping)
        league_mapping = {
            39: "English Premier League",
            140: "La Liga",
            135: "Serie A",
            78: "Bundesliga",
            61: "Ligue 1"
        }

        league_name = league_mapping.get(league_id, "English Premier League")

        # Use the new API scraper
        fixtures_df = await asyncio.to_thread(
            api_scraper.get_upcoming_matches,
            league_name=league_name,
            days_ahead=14  # Get matches for next 2 weeks
        )

        # Limit to next_n fixtures
        if not fixtures_df.empty:
            fixtures_df = fixtures_df.head(next_n)

        logger.info(f"Loaded {len(fixtures_df)} upcoming fixtures for {league_name}")
        return fixtures_df
    except Exception as e:
        logger.error(f"Error getting upcoming fixtures: {e}")
        return pd.DataFrame()


def get_odds_for_fixture(fixture_id: int) -> pd.DataFrame:
    """Get odds for a specific fixture (placeholder - The Sports DB doesn't provide odds)."""
    logger.warning("Odds data not available from The Sports DB API")
    return pd.DataFrame()