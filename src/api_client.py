from __future__ import annotations

import asyncio
import logging
from typing import Dict

import pandas as pd

# Try to import the pandas-based scraper first (alternative to LanusStats)
try:
    from .football_scraper_pandas import FootballDataScraper
    api_scraper = FootballDataScraper()
    print("✅ Using pandas-based football scraper (FBref alternative)")
except ImportError:
    try:
        # Try absolute import for direct execution
        from football_scraper_pandas import FootballDataScraper
        api_scraper = FootballDataScraper()
        print("✅ Using pandas-based football scraper (FBref alternative)")
    except ImportError:
        # Fallback to original scraper
        try:
            from .football_scraper import api_scraper
            print("✅ Using original football scraper")
        except ImportError:
            try:
                from football_scraper import api_scraper
                print("✅ Using original football scraper")
            except ImportError:
                print("❌ No football scraper available")
                api_scraper = None

logger = logging.getLogger(__name__)


async def load_history(context) -> pd.DataFrame:
    """Load historical matches using pandas-based scraper or fallback."""
    try:
        # Get league name from context or use default
        league_name_raw = getattr(context, 'bot_data', {}).get('league_name', 'English Premier League')
        season = getattr(context, 'bot_data', {}).get('season', '2022-2023')

        # Map league names to scraper format
        league_mapping = {
            'English Premier League': 'Premier League',
            'Premier League': 'Premier League',
            'La Liga': 'La Liga',
            'Spanish La Liga': 'La Liga',
            'Serie A': 'Serie A',
            'Italian Serie A': 'Serie A',
            'Bundesliga': 'Bundesliga',
            'German Bundesliga': 'Bundesliga',
            'Ligue 1': 'Ligue 1',
            'French Ligue 1': 'Ligue 1'
        }

        league_name = league_mapping.get(league_name_raw, 'Premier League')

        if api_scraper is None:
            logger.error("No scraper available")
            return pd.DataFrame()

        # Use the API scraper
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
    """Get upcoming fixtures using pandas-based scraper."""
    try:
        # Map league_id to league name
        league_mapping = {
            39: 'Premier League',  # English Premier League
            140: 'La Liga',        # Spanish La Liga
            135: 'Serie A',        # Italian Serie A
            78: 'Bundesliga',      # German Bundesliga
            61: 'Ligue 1'          # French Ligue 1
        }

        league_name = league_mapping.get(league_id, 'Premier League')

        if api_scraper is None:
            logger.error("No scraper available")
            return pd.DataFrame()

        # Use the API scraper
        matches = await asyncio.to_thread(
            api_scraper.get_upcoming_matches,
            league_name=league_name,
            days_ahead=14  # Get matches for next 2 weeks
        )

        # Limit to next_n matches
        matches = matches.head(next_n)

        logger.info(f"Loaded {len(matches)} upcoming fixtures for {league_name}")
        return matches
    except Exception as e:
        logger.error(f"Error getting upcoming fixtures: {e}")
        return pd.DataFrame()
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