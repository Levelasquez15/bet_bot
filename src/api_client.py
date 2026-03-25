from __future__ import annotations

import asyncio
import logging
from typing import Dict

import pandas as pd

from .config import get_api_key
from .data_sources import ApiFootballDataSource

logger = logging.getLogger(__name__)

# Lazy imports to avoid scipy issues at startup
Backtester = None
ApiFootballDataSourceImported = None
PredictionEngine = None
BettingRecommender = None

def _import_modules():
    """Lazy import of modules that depend on scipy."""
    global Backtester, ApiFootballDataSourceImported, PredictionEngine, BettingRecommender
    if Backtester is None:
        try:
            from .backtesting import Backtester
            from .data_sources import ApiFootballDataSource as ApiFootballDataSourceImported
            from .engine import PredictionEngine
            from .recommender import BettingRecommender
            logger.info("Modules imported successfully")
        except Exception as e:
            logger.error(f"Failed to import modules: {e}")
            raise


async def load_history(context) -> pd.DataFrame:
    """Load historical matches with better error handling."""
    try:
        _import_modules()
        from .config import current_config
        league_id, season = current_config(context)
        source = ApiFootballDataSource(api_key=get_api_key())
        matches = await asyncio.to_thread(source.get_historical_matches, league_id, season)

        # If no data for current season, try previous season
        if matches.empty and season > 2020:
            matches = await asyncio.to_thread(source.get_historical_matches, league_id, season - 1)

        return matches
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return pd.DataFrame()


async def get_upcoming_fixtures(league_id: int, season: int, next_n: int = 10) -> pd.DataFrame:
    """Get upcoming fixtures for a league and season."""
    try:
        source = ApiFootballDataSource(api_key=get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, next_n)
        return fixtures_df
    except Exception as e:
        logger.error(f"Error getting upcoming fixtures: {e}")
        return pd.DataFrame()


def get_odds_for_fixture(fixture_id: int) -> pd.DataFrame:
    """Get odds for a specific fixture."""
    try:
        source = ApiFootballDataSource(api_key=get_api_key())
        return source.get_odds_for_fixture(fixture_id)
    except Exception as e:
        logger.error(f"Error getting odds for fixture {fixture_id}: {e}")
        return pd.DataFrame()