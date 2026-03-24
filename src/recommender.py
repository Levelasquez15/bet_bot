from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class Pick:
    fixture_id: int
    match: str
    market: str
    selection: str
    probability: float
    odds: float
    expected_value: float
    bookmaker: str


class BettingRecommender:
    """Compares model probabilities against bookmaker lines and ranks picks."""

    def compare_lines(
        self,
        fixture_id: int,
        home_team: str,
        away_team: str,
        model_probs: Dict[str, float],
        odds_df: pd.DataFrame,
    ) -> pd.DataFrame:
        if odds_df.empty:
            return pd.DataFrame()

        rows: List[Dict] = []
        match_name = f"{home_team} vs {away_team}"

        for _, odd_row in odds_df.iterrows():
            bookmaker = str(odd_row.get("bookmaker", "unknown"))

            rows.extend(
                self._market_rows(
                    fixture_id=fixture_id,
                    match_name=match_name,
                    bookmaker=bookmaker,
                    market="1X2",
                    options=[
                        ("1", model_probs.get("home_win", 0.0), odd_row.get("home_odds")),
                        ("X", model_probs.get("draw", 0.0), odd_row.get("draw_odds")),
                        ("2", model_probs.get("away_win", 0.0), odd_row.get("away_odds")),
                    ],
                )
            )

            rows.extend(
                self._market_rows(
                    fixture_id=fixture_id,
                    match_name=match_name,
                    bookmaker=bookmaker,
                    market="OU2.5",
                    options=[
                        ("Over 2.5", model_probs.get("over_2_5", 0.0), odd_row.get("over_2_5_odds")),
                        ("Under 2.5", model_probs.get("under_2_5", 0.0), odd_row.get("under_2_5_odds")),
                    ],
                )
            )

        out = pd.DataFrame(rows)
        if out.empty:
            return out
        return out.sort_values(["expected_value", "probability"], ascending=False).reset_index(drop=True)

    def best_pick_per_fixture(
        self,
        compared_df: pd.DataFrame,
        min_probability: float = 0.55,
        min_expected_value: float = 0.03,
    ) -> pd.DataFrame:
        if compared_df.empty:
            return pd.DataFrame()

        candidates = compared_df[
            (compared_df["probability"] >= min_probability)
            & (compared_df["expected_value"] >= min_expected_value)
        ].copy()

        if candidates.empty:
            return pd.DataFrame()

        best = candidates.sort_values(["fixture_id", "expected_value"], ascending=[True, False]).drop_duplicates(
            subset=["fixture_id"], keep="first"
        )
        return best.reset_index(drop=True)

    def build_accumulator(
        self,
        picks_df: pd.DataFrame,
        max_legs: int = 3,
    ) -> Optional[Dict[str, float]]:
        if picks_df.empty:
            return None

        top = picks_df.sort_values(["expected_value", "probability"], ascending=False).head(max_legs)
        if top.empty:
            return None

        combined_probability = float(top["probability"].prod())
        combined_odds = float(top["odds"].prod())
        combined_ev = combined_probability * combined_odds - 1.0

        return {
            "legs": float(len(top)),
            "combined_probability": combined_probability,
            "combined_odds": combined_odds,
            "combined_expected_value": combined_ev,
        }

    def _market_rows(
        self,
        fixture_id: int,
        match_name: str,
        bookmaker: str,
        market: str,
        options: List[tuple],
    ) -> List[Dict]:
        out: List[Dict] = []
        for selection, prob, odd in options:
            odd_value = _to_float(odd)
            if odd_value is None or odd_value <= 1.01:
                continue

            prob_f = float(max(0.0, min(1.0, prob)))
            fair_odd = 1.0 / max(prob_f, 1e-9)
            expected_value = prob_f * odd_value - 1.0
            edge = odd_value - fair_odd

            out.append(
                {
                    "fixture_id": fixture_id,
                    "match": match_name,
                    "market": market,
                    "selection": selection,
                    "probability": prob_f,
                    "odds": odd_value,
                    "fair_odds": fair_odd,
                    "edge": edge,
                    "expected_value": expected_value,
                    "bookmaker": bookmaker,
                }
            )
        return out


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
