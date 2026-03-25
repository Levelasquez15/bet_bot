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
        Get upcoming matches from FBref
        """
        try:
            logger.info(f"🔍 Getting upcoming matches for {league_name} from FBref")

            league_info = self.league_mappings.get(league_name)
            if not league_info:
                logger.error(f"League {league_name} not supported")
                return pd.DataFrame()

            fbref_id = league_info['fbref']
            url = f"https://fbref.com/en/comps/{fbref_id}/schedule/{league_name.replace(' ', '-')}-Scores-and-Fixtures"

            response = self.session.get(url)
            response.raise_for_status()

            # Read all tables from the page
            tables = pd.read_html(response.text)

            # Find the schedule table (usually the first or second table)
            schedule_table = None
            for table in tables:
                if 'Date' in table.columns and 'Home' in table.columns:
                    schedule_table = table
                    break

            if schedule_table is None:
                logger.error("Could not find schedule table")
                return pd.DataFrame()

            # Clean and filter upcoming matches
            df = schedule_table.copy()

            # Convert date column
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

            # Filter out past matches and matches too far in the future
            now = datetime.now()
            cutoff_date = now + timedelta(days=days_ahead)

            upcoming = df[
                (df['Date'] >= now) &
                (df['Date'] <= cutoff_date) &
                (df['Home'].notna()) &
                (df['Away'].notna())
            ]

            # Standardize column names
            result_df = pd.DataFrame({
                'fixture_id': range(len(upcoming)),
                'date': upcoming['Date'],
                'home_team': upcoming['Home'],
                'away_team': upcoming['Away'],
                'league': league_name,
                'source': 'FBref'
            })

            logger.info(f"✅ Found {len(result_df)} upcoming matches from FBref")
            return result_df

        except Exception as e:
            logger.error(f"❌ Error getting upcoming matches from FBref: {e}")
            return pd.DataFrame()

    def get_historical_matches(self, league_name: str = "Premier League", season: str = "2023-2024", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches from FBref
        """
        try:
            logger.info(f"🔍 Getting historical matches for {league_name} {season} from FBref")

            league_info = self.league_mappings.get(league_name)
            if not league_info:
                logger.error(f"League {league_name} not supported")
                return pd.DataFrame()

            fbref_id = league_info['fbref']
            url = f"https://fbref.com/en/comps/{fbref_id}/{season}/schedule/{league_name.replace(' ', '-')}-Scores-and-Fixtures"

            response = self.session.get(url)
            response.raise_for_status()

            tables = pd.read_html(response.text)

            # Find the results table
            results_table = None
            for table in tables:
                if 'Date' in table.columns and 'Home' in table.columns and 'Score' in table.columns:
                    results_table = table
                    break

            if results_table is None:
                logger.error("Could not find results table")
                return pd.DataFrame()

            # Clean the data
            df = results_table.copy()

            # Convert date column
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

            # Filter out rows without scores (future matches)
            historical = df[
                (df['Score'].notna()) &
                (df['Score'] != '') &
                (df['Home'].notna()) &
                (df['Away'].notna())
            ].head(limit)

            # Parse scores
            def parse_score(score_str):
                if pd.isna(score_str) or score_str == '':
                    return None, None
                try:
                    home_score, away_score = str(score_str).split('–')
                    return int(home_score), int(away_score)
                except:
                    return None, None

            historical['home_score'], historical['away_score'] = zip(*historical['Score'].apply(parse_score))

            # Standardize column names
            result_df = pd.DataFrame({
                'fixture_id': range(len(historical)),
                'date': historical['Date'],
                'home_team': historical['Home'],
                'away_team': historical['Away'],
                'home_score': historical['home_score'],
                'away_score': historical['away_score'],
                'league': league_name,
                'season': season,
                'source': 'FBref'
            })

            # Remove rows with invalid scores
            result_df = result_df.dropna(subset=['home_score', 'away_score'])

            logger.info(f"✅ Found {len(result_df)} historical matches from FBref")
            return result_df

        except Exception as e:
            logger.error(f"❌ Error getting historical matches from FBref: {e}")
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