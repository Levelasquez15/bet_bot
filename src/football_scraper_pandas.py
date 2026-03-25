"""
Football scraper using pandas for multiple sources as alternative to LanusStats
"""
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging
import time

logger = logging.getLogger(__name__)

class FootballDataScraper:
    """
    Alternative scraper using pandas.read_html() for multiple football data sources
    Similar functionality to LanusStats but using direct web scraping
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        # Disable SSL verification to avoid connection issues
        self.session.verify = False
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # League mappings for different sources
        self.league_mappings = {
            'Premier League': {
                'fbref': '9',
                'sofascore': '17',
                'name': 'Premier League'
            },
            'La Liga': {
                'fbref': '12',
                'sofascore': '8',
                'name': 'La Liga'
            },
            'Serie A': {
                'fbref': '11',
                'sofascore': '23',
                'name': 'Serie A'
            },
            'Bundesliga': {
                'fbref': '20',
                'sofascore': '35',
                'name': 'Bundesliga'
            },
            'Ligue 1': {
                'fbref': '13',
                'sofascore': '34',
                'name': 'Ligue 1'
            }
        }

    def get_upcoming_matches(self, league_name: str = "Premier League", days_ahead: int = 7) -> pd.DataFrame:
        """
        Get upcoming matches - using mock data for now until FBref scraping is fixed
        """
        try:
            logger.info(f"🔍 Getting upcoming matches for {league_name} (using mock data)")

            # Mock data for testing - replace with real scraping later
            mock_matches = {
                'Premier League': [
                    {'date': '2024-12-15 15:00', 'home_team': 'Arsenal', 'away_team': 'Chelsea'},
                    {'date': '2024-12-16 17:30', 'home_team': 'Manchester City', 'away_team': 'Liverpool'},
                    {'date': '2024-12-17 20:00', 'home_team': 'Manchester United', 'away_team': 'Tottenham'},
                ],
                'La Liga': [
                    {'date': '2024-12-15 16:15', 'home_team': 'Real Madrid', 'away_team': 'Barcelona'},
                    {'date': '2024-12-16 18:30', 'home_team': 'Atletico Madrid', 'away_team': 'Sevilla'},
                ],
                'Serie A': [
                    {'date': '2024-12-15 20:45', 'home_team': 'Juventus', 'away_team': 'Inter Milan'},
                    {'date': '2024-12-16 15:00', 'home_team': 'AC Milan', 'away_team': 'Napoli'},
                ],
                'Bundesliga': [
                    {'date': '2024-12-14 15:30', 'home_team': 'Bayern Munich', 'away_team': 'Borussia Dortmund'},
                ],
                'Ligue 1': [
                    {'date': '2024-12-15 21:00', 'home_team': 'PSG', 'away_team': 'Marseille'},
                ]
            }

            league_matches = mock_matches.get(league_name, [])
            if not league_matches:
                logger.warning(f"No mock data for {league_name}")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(league_matches)

            # Convert date strings to datetime
            df['date'] = pd.to_datetime(df['date'])

            # Filter by date range
            now = pd.Timestamp.now()
            cutoff_date = now + pd.Timedelta(days=days_ahead)

            upcoming = df[
                (df['date'] >= now) &
                (df['date'] <= cutoff_date)
            ]

            # Add required columns
            result_df = pd.DataFrame({
                'fixture_id': range(len(upcoming)),
                'date': upcoming['date'],
                'home_team': upcoming['home_team'],
                'away_team': upcoming['away_team'],
                'league': league_name,
                'source': 'MockData'
            })

            logger.info(f"✅ Found {len(result_df)} upcoming matches (mock data)")
            return result_df

        except Exception as e:
            logger.error(f"❌ Error getting upcoming matches: {e}")
            return pd.DataFrame()

    def get_historical_matches(self, league_name: str = "Premier League", season: str = "2023-2024", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches - using mock data for now
        """
        try:
            logger.info(f"🔍 Getting historical matches for {league_name} {season} (mock data)")

            # Mock historical data
            mock_historical = {
                'Premier League': [
                    {'date': '2024-12-01', 'home_team': 'Arsenal', 'away_team': 'Chelsea', 'home_score': 2, 'away_score': 1},
                    {'date': '2024-11-30', 'home_team': 'Manchester City', 'away_team': 'Liverpool', 'home_score': 3, 'away_score': 0},
                    {'date': '2024-11-29', 'home_team': 'Manchester United', 'away_team': 'Tottenham', 'home_score': 1, 'away_score': 1},
                    {'date': '2024-11-28', 'home_team': 'Newcastle', 'away_team': 'Aston Villa', 'home_score': 2, 'away_score': 2},
                    {'date': '2024-11-27', 'home_team': 'Brighton', 'away_team': 'Crystal Palace', 'home_score': 1, 'away_score': 0},
                ],
                'La Liga': [
                    {'date': '2024-12-01', 'home_team': 'Real Madrid', 'away_team': 'Barcelona', 'home_score': 3, 'away_score': 2},
                    {'date': '2024-11-30', 'home_team': 'Atletico Madrid', 'away_team': 'Sevilla', 'home_score': 1, 'away_score': 1},
                ],
                'Serie A': [
                    {'date': '2024-12-01', 'home_team': 'Juventus', 'away_team': 'Inter Milan', 'home_score': 2, 'away_score': 0},
                    {'date': '2024-11-30', 'home_team': 'AC Milan', 'away_team': 'Napoli', 'home_score': 1, 'away_score': 3},
                ]
            }

            league_matches = mock_historical.get(league_name, [])
            if not league_matches:
                logger.warning(f"No mock historical data for {league_name}")
                return pd.DataFrame()

            # Convert to DataFrame and limit results
            df = pd.DataFrame(league_matches[:limit])

            # Convert date strings to datetime
            df['date'] = pd.to_datetime(df['date'])

            # Add required columns
            result_df = pd.DataFrame({
                'fixture_id': range(len(df)),
                'date': df['date'],
                'home_team': df['home_team'],
                'away_team': df['away_team'],
                'home_score': df['home_score'],
                'away_score': df['away_score'],
                'league': league_name,
                'season': season,
                'source': 'MockData'
            })

            logger.info(f"✅ Found {len(result_df)} historical matches (mock data)")
            return result_df

        except Exception as e:
            logger.error(f"❌ Error getting historical matches: {e}")
            return pd.DataFrame()

    def get_team_stats(self, league_name: str = "Premier League", season: str = "2023-2024") -> pd.DataFrame:
        """
        Get team statistics from FBref
        """
        try:
            logger.info(f"🔍 Getting team stats for {league_name} {season} from FBref")

            league_info = self.league_mappings.get(league_name)
            if not league_info:
                logger.error(f"League {league_name} not supported")
                return pd.DataFrame()

            fbref_id = league_info['fbref']
            url = f"https://fbref.com/en/comps/{fbref_id}/{season}/stats/"

            response = self.session.get(url)
            response.raise_for_status()

            tables = pd.read_html(response.text)

            # Find the team stats table
            stats_table = None
            for table in tables:
                if 'Squad' in table.columns and 'MP' in table.columns:
                    stats_table = table
                    break

            if stats_table is None:
                logger.error("Could not find team stats table")
                return pd.DataFrame()

            # Clean the table
            df = stats_table.copy()

            # Remove multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(0)

            # Add league and season info
            df['league'] = league_name
            df['season'] = season
            df['source'] = 'FBref'

            logger.info(f"✅ Found team stats for {len(df)} teams from FBref")
            return df

        except Exception as e:
            logger.error(f"❌ Error getting team stats from FBref: {e}")
            return pd.DataFrame()