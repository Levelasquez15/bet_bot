from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup


REQUIRED_MATCH_COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
]


class DataValidationError(ValueError):
    pass


@dataclass
class ApiFootballDataSource:
    """API-Football wrapper for historical/upcoming fixtures and odds.

    Supports both direct API-Sports key auth and RapidAPI style headers.
    """

    api_key: str
    base_url: str = "https://v3.football.api-sports.io"
    rapidapi_host: str = "v3.football.api-sports.io"
    timeout_seconds: int = 20
    use_rapidapi_headers: bool = True

    @property
    def _headers(self) -> dict:
        headers = {
            "x-apisports-key": self.api_key,
        }
        if self.use_rapidapi_headers:
            headers["x-rapidapi-key"] = self.api_key
            headers["x-rapidapi-host"] = self.rapidapi_host
        return headers

    def _get(self, path: str, params: dict) -> dict:
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_historical_matches(self, league_id: int, season: int) -> pd.DataFrame:
        payload = self._get("/fixtures", {"league": league_id, "season": season, "status": "FT"})
        rows = []
        for item in payload.get("response", []):
            goals = item.get("goals") or {}
            fixture = item.get("fixture") or {}
            teams = item.get("teams") or {}
            rows.append(
                {
                    "date": fixture.get("date"),
                    "home_team": (teams.get("home") or {}).get("name"),
                    "away_team": (teams.get("away") or {}).get("name"),
                    "home_goals": goals.get("home"),
                    "away_goals": goals.get("away"),
                }
            )

        df = pd.DataFrame(rows)
        return normalize_matches(df)

    def get_upcoming_fixtures(self, league_id: int, season: int, next_n: int = 10) -> pd.DataFrame:
        payload = self._get(
            "/fixtures",
            {"league": league_id, "season": season, "next": max(1, min(next_n, 50))},
        )
        rows = []
        for item in payload.get("response", []):
            fixture = item.get("fixture") or {}
            teams = item.get("teams") or {}
            rows.append(
                {
                    "fixture_id": fixture.get("id"),
                    "date": fixture.get("date"),
                    "home_team": (teams.get("home") or {}).get("name"),
                    "away_team": (teams.get("away") or {}).get("name"),
                }
            )

        out = pd.DataFrame(rows)
        if out.empty:
            return out
        out["date"] = pd.to_datetime(out["date"], errors="coerce", utc=True)
        return out.sort_values("date").reset_index(drop=True)

    def get_odds_for_fixture(self, fixture_id: int) -> pd.DataFrame:
        payload = self._get("/odds", {"fixture": fixture_id})
        rows = []

        for item in payload.get("response", []):
            bookmakers = item.get("bookmakers") or []
            for bookmaker in bookmakers:
                bets = bookmaker.get("bets") or []
                for bet in bets:
                    bet_name = (bet.get("name") or "").strip()
                    values = bet.get("values") or []

                    row = _find_or_create_odds_row(rows, fixture_id, str(bookmaker.get("name")))

                    if bet_name == "Match Winner":
                        odds_map = {v.get("value"): v.get("odd") for v in values}
                        row["home_odds"] = _safe_float(odds_map.get("Home"))
                        row["draw_odds"] = _safe_float(odds_map.get("Draw"))
                        row["away_odds"] = _safe_float(odds_map.get("Away"))

                    if bet_name == "Goals Over/Under":
                        over_25, under_25 = _extract_over_under_25(values)
                        if over_25 is not None:
                            row["over_2_5_odds"] = over_25
                        if under_25 is not None:
                            row["under_2_5_odds"] = under_25

        return pd.DataFrame(rows)

    def get_leagues(self) -> pd.DataFrame:
        payload = self._get("/leagues", {})
        rows = []
        for item in payload.get("response", []):
            league = item.get("league") or {}
            country = item.get("country") or {}
            rows.append(
                {
                    "league_id": league.get("id"),
                    "league_name": league.get("name"),
                    "country": country.get("name"),
                    "type": league.get("type"),
                }
            )
        return pd.DataFrame(rows)


@dataclass
class ScrapingOddsDataSource:
    """Simple odds scraper for static HTML pages.

    `row_selector` should match each odds row.
    `home_selector`, `draw_selector`, `away_selector` are CSS selectors relative to row.
    """

    row_selector: str
    home_selector: str
    draw_selector: str
    away_selector: str
    timeout_seconds: int = 20

    def get_odds(self, url: str) -> pd.DataFrame:
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        rows = []

        for row in soup.select(self.row_selector):
            home_odd = _extract_selector_text(row, self.home_selector)
            draw_odd = _extract_selector_text(row, self.draw_selector)
            away_odd = _extract_selector_text(row, self.away_selector)
            rows.append(
                {
                    "home_odds": _safe_float(home_odd),
                    "draw_odds": _safe_float(draw_odd),
                    "away_odds": _safe_float(away_odd),
                }
            )

        return pd.DataFrame(rows)


def load_matches_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return normalize_matches(df)


def normalize_matches(df: pd.DataFrame) -> pd.DataFrame:
    missing = [col for col in REQUIRED_MATCH_COLUMNS if col not in df.columns]
    if missing:
        raise DataValidationError(f"Missing required columns: {missing}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce", utc=True)
    out["home_goals"] = pd.to_numeric(out["home_goals"], errors="coerce")
    out["away_goals"] = pd.to_numeric(out["away_goals"], errors="coerce")

    out = out.dropna(subset=["date", "home_team", "away_team"])

    # Keep rows even when goals are NA, so upcoming fixtures can be scored.
    out = out.sort_values("date").reset_index(drop=True)
    return out


def _extract_selector_text(node, selector: str) -> Optional[str]:
    found = node.select_one(selector)
    if not found:
        return None
    return found.get_text(strip=True)


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _find_or_create_odds_row(rows: list, fixture_id: int, bookmaker: str) -> Dict[str, Any]:
    for row in rows:
        if row.get("fixture_id") == fixture_id and row.get("bookmaker") == bookmaker:
            return row

    new_row: Dict[str, Any] = {
        "fixture_id": fixture_id,
        "bookmaker": bookmaker,
        "home_odds": None,
        "draw_odds": None,
        "away_odds": None,
        "over_2_5_odds": None,
        "under_2_5_odds": None,
    }
    rows.append(new_row)
    return new_row


def _extract_over_under_25(values: list) -> tuple[Optional[float], Optional[float]]:
    over_25 = None
    under_25 = None

    for item in values:
        label = str(item.get("value") or "")
        odd = _safe_float(item.get("odd"))
        if odd is None:
            continue

        normalized = label.lower().replace(" ", "")
        if "over2.5" in normalized or "o2.5" in normalized:
            over_25 = odd
        if "under2.5" in normalized or "u2.5" in normalized:
            under_25 = odd

    return over_25, under_25
