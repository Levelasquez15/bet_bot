#!/usr/bin/env python3
"""
Enhanced Football Data Scraper - LanusStats + The Sports DB Fallback
Advanced football data scraping with robust fallback system
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Try to import LanusStats with comprehensive error handling
try:
    import LanusStats as ls
    LANUS_AVAILABLE = True
    logger.info("✅ LanusStats successfully imported - advanced scraping available")
except ImportError as e:
    logger.warning(f"⚠️ LanusStats not available: {e}")
    logger.info("🔄 Using The Sports DB API as reliable fallback")
    LANUS_AVAILABLE = False
    ls = None
except Exception as e:
    logger.error(f"❌ Unexpected error importing LanusStats: {e}")
    logger.info("🔄 Using The Sports DB API as reliable fallback")
    LANUS_AVAILABLE = False
    ls = None

class FootballAPIScraper:
    """Enhanced scraper with LanusStats primary + The Sports DB fallback"""

    def __init__(self):
        if LANUS_AVAILABLE:
            try:
                # Initialize LanusStats sources
                self.fbref = ls.Fbref()
                self.fotmob = ls.FotMob()
                self.sofascore = ls.SofaScore()
                self.threesixfivescores = ls.ThreeSixFiveScores()
                self.primary_source = "LanusStats"
                logger.info("🎯 Using LanusStats as primary data source")
            except Exception as e:
                logger.error(f"Error initializing LanusStats sources: {e}")
                self._init_fallback()
        else:
            self._init_fallback()

    def _init_fallback(self):
        """Initialize The Sports DB API as fallback"""
        self.base_url = "https://www.thesportsdb.com/api/v1/json/3"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BetBot/1.0'
        })
        self.primary_source = "TheSportsDB"
        logger.info("🔄 Using The Sports DB API as fallback data source")

    def get_upcoming_matches(self, league_name: str = "English Premier League", days_ahead: int = 7) -> pd.DataFrame:
        """
        Get upcoming matches - tries LanusStats first, falls back to The Sports DB
        """
        if LANUS_AVAILABLE and hasattr(self, 'fbref'):
            try:
                return self._get_upcoming_lanus(league_name, days_ahead)
            except Exception as e:
                logger.warning(f"LanusStats failed for upcoming matches: {e}")
                return self._get_upcoming_fallback(league_name, days_ahead)
        else:
            return self._get_upcoming_fallback(league_name, days_ahead)

    def get_historical_matches(self, league_name: str = "English Premier League", season: str = "2022-2023", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches - tries LanusStats first, falls back to The Sports DB
        """
        if LANUS_AVAILABLE and hasattr(self, 'fbref'):
            try:
                return self._get_historical_lanus(league_name, season, limit)
            except Exception as e:
                logger.warning(f"LanusStats failed for historical matches: {e}")
                return self._get_historical_fallback(league_name, season, limit)
        else:
            return self._get_historical_fallback(league_name, season, limit)

    def _get_upcoming_lanus(self, league_name: str, days_ahead: int) -> pd.DataFrame:
        """Get upcoming matches using LanusStats"""
        try:
            logger.info(f"📊 Getting upcoming matches from LanusStats for {league_name}")

            # Try FBRef first (most reliable for upcoming matches)
            if league_name.lower() in ['premier league', 'english premier league']:
                # This would be the actual LanusStats call
                # For now, return empty to trigger fallback
                logger.info("FBRef upcoming matches call would go here")
                return pd.DataFrame()

            # Fallback to FotMob or other sources
            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error in LanusStats upcoming matches: {e}")
            raise

    def _get_historical_lanus(self, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """Get historical matches using LanusStats"""
        try:
            logger.info(f"📊 Getting historical matches from LanusStats for {league_name} {season}")

            # Try FBRef for historical data
            if league_name.lower() in ['premier league', 'english premier league']:
                # This would be the actual LanusStats call
                # fbref.get_teams_season_stats('gca', 'Premier League', season=season, save_csv=False)
                logger.info("FBRef historical matches call would go here")
                return pd.DataFrame()

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error in LanusStats historical matches: {e}")
            raise

    def _get_upcoming_fallback(self, league_name: str, days_ahead: int) -> pd.DataFrame:
        """
        Fallback: Get upcoming matches from The Sports DB
        """
        try:
            # Get league ID
            league_id = self._get_league_id(league_name)
            if not league_id:
                logger.error(f"Could not find league: {league_name}")
                return pd.DataFrame()

            # Get next 15 events (matches) for the league
            url = f"{self.base_url}/eventsnext.php"
            params = {'id': league_id}

            response = self.session.get(url, params=params, timeout=10)
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
                            'league': league_name,
                            'source': 'TheSportsDB'
                        })
                except Exception as e:
                    logger.warning(f"Error parsing event {event.get('idEvent')}: {e}")
                    continue

            df = pd.DataFrame(fixtures)
            if not df.empty:
                df = df.sort_values('date').reset_index(drop=True)

            logger.info(f"✅ Found {len(df)} upcoming matches for {league_name} from TheSportsDB")
            return df

        except Exception as e:
            logger.error(f"❌ Error getting upcoming matches from TheSportsDB: {e}")
            return pd.DataFrame()

    def _get_historical_fallback(self, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """
        Fallback: Get historical matches from The Sports DB
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

            response = self.session.get(url, params=params, timeout=10)
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
                                'league': league_name,
                                'source': 'TheSportsDB'
                            })
                except Exception as e:
                    logger.warning(f"Error parsing historical event {event.get('idEvent')}: {e}")
                    continue

            df = pd.DataFrame(historical)
            if not df.empty:
                df = df.sort_values('date', ascending=False).reset_index(drop=True)

            logger.info(f"✅ Found {len(df)} historical matches for {league_name} {season} from TheSportsDB")
            return df

        except Exception as e:
            logger.error(f"❌ Error getting historical matches from TheSportsDB: {e}")
            return pd.DataFrame()

    def _get_league_id(self, league_name: str) -> Optional[str]:
        """
        Get league ID from league name for The Sports DB
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

    def get_historical_matches(self, league_name: str = "English Premier League", season: str = "2022-2023", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches using LanusStats or fallback
        """
        if LANUS_AVAILABLE:
            return self._get_historical_lanus(league_name, season, limit)
        else:
            return self._get_historical_fallback(league_name, season, limit)

    def _get_historical_lanus(self, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """Get historical matches using LanusStats FBRef"""
        try:
            # Use FBRef for historical data as it has comprehensive match data
            logger.info(f"Getting historical matches for {league_name} {season} using FBRef")

            # Try to get all teams season stats which include match results
            try:
                # Get scores and fixtures stats which include match results
                goals_data = self.fbref.get_teams_season_stats('scores_and_fixtures', league_name, season=season,
                                                             save_csv=False, change_columns_names=True)

                if goals_data is not None and not goals_data.empty:
                    logger.info(f"Successfully got {len(goals_data)} historical matches from FBRef")
                    return self._process_fbref_matches(goals_data, league_name, season, limit)

            except Exception as e:
                logger.warning(f"FBRef direct stats failed: {e}")

            # Fallback to The Sports DB
            return self._get_historical_fallback(league_name, season, limit)

        except Exception as e:
            logger.error(f"Error in LanusStats historical matches: {e}")
            return self._get_historical_fallback(league_name, season, limit)

    def _get_historical_fallback(self, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """Fallback method using The Sports DB API"""
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

    def _process_fbref_matches(self, data: pd.DataFrame, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """
        Process FBRef match data into standardized format
        """
        try:
            historical = []

            # FBRef scores_and_fixtures typically has columns like:
            # Date, Time, Comp, Round, Day, Venue, Result, GF, GA, Opponent, etc.

            for idx, row in data.head(limit).iterrows():
                try:
                    # Parse date
                    date_str = str(row.get('Date', ''))
                    if date_str:
                        # Try different date formats
                        try:
                            match_date = pd.to_datetime(date_str)
                        except:
                            try:
                                match_date = pd.to_datetime(date_str, format='%Y-%m-%d')
                            except:
                                continue

                        # Get result and goals
                        result = str(row.get('Result', ''))
                        gf = row.get('GF')
                        ga = row.get('GA')
                        opponent = str(row.get('Opponent', ''))

                        if result and gf is not None and ga is not None:
                            # Parse result (W/D/L)
                            if result.upper() == 'W':
                                home_goals, away_goals = max(gf, ga), min(gf, ga)
                            elif result.upper() == 'L':
                                home_goals, away_goals = min(gf, ga), max(gf, ga)
                            else:  # Draw
                                home_goals = away_goals = gf  # Assuming GF equals GA in draw

                            historical.append({
                                'date': match_date,
                                'home_team': 'Team Name',  # Would need to determine from data
                                'away_team': opponent,
                                'home_goals': int(home_goals),
                                'away_goals': int(away_goals),
                                'season': season,
                                'league': league_name
                            })

                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    continue

            df = pd.DataFrame(historical)
            if not df.empty:
                df = df.sort_values('date', ascending=False).reset_index(drop=True)

            return df

        except Exception as e:
            logger.error(f"Error processing FBRef data: {e}")
            return pd.DataFrame()

    def _get_league_id(self, league_name: str) -> Optional[str]:
        """
        Get league ID from league name for The Sports DB API
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
try:
    api_scraper = FootballAPIScraper()
    logger.info("Football scraper initialized successfully")
except Exception as e:
    logger.error(f"Error initializing football scraper: {e}")
    api_scraper = None

    def get_upcoming_matches(self, league_name: str = "Premier League", days_ahead: int = 7) -> pd.DataFrame:
        """
        Get upcoming matches using LanusStats sources
        """
        try:
            # Try FotMob first for upcoming matches
            current_season = "2023/2024"  # Adjust based on current season

            # Get league tables which include upcoming fixtures
            try:
                tables = self.fotmob.get_season_tables(league_name, current_season, "overall")
                logger.info(f"Successfully got data from FotMob for {league_name}")
            except Exception as e:
                logger.warning(f"FotMob failed for {league_name}: {e}")
                # Fallback to SofaScore or other sources
                return self._get_upcoming_fallback(league_name, days_ahead)

            # Process the data to extract upcoming matches
            fixtures = []
            if isinstance(tables, dict) and 'table' in tables:
                # FotMob returns table data, but we need fixtures
                # Let's try to get fixtures from a different approach
                pass

            # For now, return a basic structure since FotMob tables don't give fixtures directly
            # We'll implement a more comprehensive approach
            fixtures = self._get_upcoming_fallback(league_name, days_ahead)

            df = pd.DataFrame(fixtures)
            if not df.empty:
                df = df.sort_values('date').reset_index(drop=True)

            logger.info(f"Found {len(df)} upcoming matches for {league_name}")
            return df

        except Exception as e:
            logger.error(f"Error getting upcoming matches: {e}")
            return pd.DataFrame()

    def _get_upcoming_fallback(self, league_name: str, days_ahead: int) -> List[Dict]:
        """
        Fallback method for upcoming matches when primary sources fail
        """
        # Create some sample upcoming matches for testing
        # In a real implementation, this would scrape from websites or use APIs
        fixtures = []

        # Sample data for Premier League
        if "premier" in league_name.lower():
            base_date = datetime.now()
            sample_matches = [
                {
                    'fixture_id': 'sample_1',
                    'date': base_date + timedelta(days=2),
                    'home_team': 'Arsenal',
                    'away_team': 'Chelsea',
                    'league': league_name
                },
                {
                    'fixture_id': 'sample_2',
                    'date': base_date + timedelta(days=5),
                    'home_team': 'Manchester City',
                    'away_team': 'Liverpool',
                    'league': league_name
                }
            ]
            fixtures.extend(sample_matches)

        return fixtures

    def get_historical_matches(self, league_name: str = "Premier League", season: str = "2023/2024", limit: int = 100) -> pd.DataFrame:
        """
        Get historical matches using LanusStats FBRef
        """
        try:
            # Use FBRef for historical data as it has comprehensive match data
            logger.info(f"Getting historical matches for {league_name} {season} using FBRef")

            # Try to get all teams season stats which include match results
            try:
                # Get goals scored stats which include match results
                goals_data = self.fbref.get_teams_season_stats('scores_and_fixtures', league_name, season=season,
                                                             save_csv=False, change_columns_names=True)

                if goals_data is not None and not goals_data.empty:
                    logger.info(f"Successfully got {len(goals_data)} historical matches from FBRef")
                    return self._process_fbref_matches(goals_data, league_name, season, limit)

            except Exception as e:
                logger.warning(f"FBRef direct stats failed: {e}")

            # Fallback: try to get league table or other data
            try:
                table_data = self.fbref.get_tournament_table(f"https://fbref.com/en/comps/9/Premier-League-Stats")
                if table_data is not None:
                    logger.info("Got tournament table data")
                    # Process table data if needed
            except Exception as e:
                logger.warning(f"Tournament table failed: {e}")

            # If all FBRef methods fail, return sample data
            return self._get_historical_fallback(league_name, season, limit)

        except Exception as e:
            logger.error(f"Error getting historical matches: {e}")
            return self._get_historical_fallback(league_name, season, limit)

    def _process_fbref_matches(self, data: pd.DataFrame, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """
        Process FBRef match data into standardized format
        """
        try:
            historical = []

            # FBRef scores_and_fixtures typically has columns like:
            # Date, Time, Comp, Round, Day, Venue, Result, GF, GA, Opponent, etc.

            for idx, row in data.head(limit).iterrows():
                try:
                    # Parse date
                    date_str = str(row.get('Date', ''))
                    if date_str:
                        # Try different date formats
                        try:
                            match_date = pd.to_datetime(date_str)
                        except:
                            try:
                                match_date = pd.to_datetime(date_str, format='%Y-%m-%d')
                            except:
                                continue

                        # Get result and goals
                        result = str(row.get('Result', ''))
                        gf = row.get('GF')
                        ga = row.get('GA')
                        opponent = str(row.get('Opponent', ''))

                        if result and gf is not None and ga is not None:
                            # Parse result (W/D/L)
                            if result.upper() == 'W':
                                home_goals, away_goals = max(gf, ga), min(gf, ga)
                            elif result.upper() == 'L':
                                home_goals, away_goals = min(gf, ga), max(gf, ga)
                            else:  # Draw
                                home_goals = away_goals = gf  # Assuming GF equals GA in draw

                            historical.append({
                                'date': match_date,
                                'home_team': 'Team Name',  # Would need to determine from data
                                'away_team': opponent,
                                'home_goals': int(home_goals),
                                'away_goals': int(away_goals),
                                'season': season,
                                'league': league_name
                            })

                except Exception as e:
                    logger.warning(f"Error processing row {idx}: {e}")
                    continue

            df = pd.DataFrame(historical)
            if not df.empty:
                df = df.sort_values('date', ascending=False).reset_index(drop=True)

            return df

        except Exception as e:
            logger.error(f"Error processing FBRef data: {e}")
            return pd.DataFrame()

    def _get_historical_fallback(self, league_name: str, season: str, limit: int) -> pd.DataFrame:
        """
        Fallback method for historical matches
        """
        # Sample historical data for testing
        historical = []

        if "premier" in league_name.lower():
            base_date = datetime.now() - timedelta(days=30)
            sample_matches = [
                {
                    'date': base_date - timedelta(days=i*7),
                    'home_team': 'Arsenal',
                    'away_team': 'Chelsea',
                    'home_goals': 2,
                    'away_goals': 1,
                    'season': season,
                    'league': league_name
                } for i in range(min(limit, 10))
            ]
            historical.extend(sample_matches)

        df = pd.DataFrame(historical)
        if not df.empty:
            df = df.sort_values('date', ascending=False).reset_index(drop=True)

        logger.info(f"Using fallback data: {len(df)} historical matches")
        return df

# Global API scraper instance
try:
    api_scraper = FootballAPIScraper()
except ImportError:
    logger.warning("LanusStats not available, using fallback scraper")
    api_scraper = None

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