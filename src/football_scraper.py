#!/usr/bin/env python3
"""
Football Data Scraper - Using The Sports DB API (free, no API key required)
Reliable football data from TheSportsDB.com
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

class FootballAPIScraper:
    """Scraper using The Sports DB API (completely free, no API key required)"""

    def __init__(self):
        self.base_url = "https://www.thesportsdb.com/api/v1/json/3"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BetBot/1.0'
        })

    def get_upcoming_matches(self, league_name: str = "English Premier League", days_ahead: int = 7) -> pd.DataFrame:
        """
        Get upcoming matches from The Sports DB
        """
        try:
            # First get league ID
            league_id = self._get_league_id(league_name)
            if not league_id:
                logger.error(f"Could not find league: {league_name}")
                return pd.DataFrame()

            # Get next 15 events (matches) for the league
            url = f"{self.base_url}/eventsnext.php"
            params = {'id': league_id}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            events = data.get('events', [])

            fixtures = []
            for event in events[:15]:  # Limit to 15 matches
                try:
                    # Parse date and time
                    date_str = event.get('dateEvent')
                    time_str = event.get('strTime', '00:00:00')

                    if date_str:
                        # Combine date and time
                        datetime_str = f"{date_str} {time_str}"
                        match_datetime = pd.to_datetime(datetime_str, errors='coerce')

                        if pd.isna(match_datetime):
                            continue

                        # Only include matches within the next N days
                        if match_datetime.date() > (datetime.now().date() + timedelta(days=days_ahead)):
                            continue

                        fixtures.append({
                            'fixture_id': event.get('idEvent'),
                            'date': match_datetime,
                            'home_team': event.get('strHomeTeam', ''),
                            'away_team': event.get('strAwayTeam', ''),
                            'league': league_name
                        })
                except Exception as e:
                    logger.warning(f"Error parsing event {event.get('idEvent')}: {e}")
                    continue

            df = pd.DataFrame(fixtures)
            if not df.empty:
                df = df.sort_values('date').reset_index(drop=True)

            logger.info(f"Found {len(df)} upcoming matches for {league_name}")
            return df

        except Exception as e:
            logger.error(f"Error getting upcoming matches: {e}")
            return pd.DataFrame()

    def get_historical_matches(self, league_name: str = "English Premier League", season: str = "2022-2023", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches from The Sports DB
        """
        try:
            # Get league ID
            league_id = self._get_league_id(league_name)
            if not league_id:
                logger.error(f"Could not find league: {league_name}")
                return pd.DataFrame()

            # Get events for the season
            url = f"{self.base_url}/eventsseason.php"
            params = {'id': league_id, 's': season}

            response = self.session.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            events = data.get('events', [])

            historical = []
            for event in events[:limit]:
                try:
                    # Only process finished matches
                    if event.get('strStatus') != 'Match Finished':
                        continue

                    date_str = event.get('dateEvent')
                    time_str = event.get('strTime', '00:00:00')

                    if date_str:
                        datetime_str = f"{date_str} {time_str}"
                        match_datetime = pd.to_datetime(datetime_str, errors='coerce')

                        if pd.isna(match_datetime):
                            continue

                        # Parse score
                        home_score = event.get('intHomeScore')
                        away_score = event.get('intAwayScore')

                        if home_score is not None and away_score is not None:
                            historical.append({
                                'date': match_datetime,
                                'home_team': event.get('strHomeTeam', ''),
                                'away_team': event.get('strAwayTeam', ''),
                                'home_goals': int(home_score),
                                'away_goals': int(away_score),
                                'season': season,
                                'league': league_name
                            })
                except Exception as e:
                    logger.warning(f"Error parsing historical event {event.get('idEvent')}: {e}")
                    continue

            df = pd.DataFrame(historical)
            if not df.empty:
                df = df.sort_values('date', ascending=False).reset_index(drop=True)

            logger.info(f"Found {len(df)} historical matches for {league_name} {season}")
            return df

        except Exception as e:
            logger.error(f"Error getting historical matches: {e}")
            return pd.DataFrame()

    def _get_league_id(self, league_name: str) -> Optional[str]:
        """
        Get league ID from league name
        """
        try:
            # Map common league names to TheSportsDB league IDs
            league_mapping = {
                "English Premier League": "4328",
                "Premier League": "4328",
                "La Liga": "4335",
                "Spanish La Liga": "4335",
                "Serie A": "4332",
                "Italian Serie A": "4332",
                "Bundesliga": "4331",
                "German Bundesliga": "4331",
                "Ligue 1": "4334",
                "French Ligue 1": "4334"
            }

            return league_mapping.get(league_name)
        except Exception as e:
            logger.error(f"Error getting league ID: {e}")
            return None

# Global API scraper instance
api_scraper = FootballAPIScraper()

async def get_upcoming_fixtures(league_id: int, season: int, next_n: int = 10) -> pd.DataFrame:
    """
    Get upcoming fixtures - replacement for API-based function
    Maps league_id to league code
    """
    league_mapping = {
        39: "PL",      # Premier League
        140: "PD",     # La Liga
        135: "SA",     # Serie A
        78: "BL1",     # Bundesliga
        61: "FL1"      # Ligue 1
    }

    league_code = league_mapping.get(league_id, "PL")

    # Run API call in thread pool to avoid blocking
    df = await asyncio.to_thread(api_scraper.get_upcoming_matches, league_code, 14)  # 2 weeks ahead

    return df

async def load_history(context) -> pd.DataFrame:
    """
    Load historical matches - replacement for API-based function
    """
    try:
        from .config import current_config
        league_id, season = current_config(context)

        league_mapping = {
            39: "PL",      # Premier League
            140: "PD",     # La Liga
            135: "SA",     # Serie A
            78: "BL1",     # Bundesliga
            61: "FL1"      # Ligue 1
        }

        league_code = league_mapping.get(league_id, "PL")

        # Run API call in thread pool
        df = await asyncio.to_thread(api_scraper.get_historical_matches, league_code, str(season), 200)

        return df

    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return pd.DataFrame()

def get_odds_for_fixture(fixture_id: int) -> pd.DataFrame:
    """
    Get odds for a fixture - placeholder for now
    """
    # Football Data API doesn't provide odds in free tier
    # This would require a different API or scraping betting sites
    return pd.DataFrame()