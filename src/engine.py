from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

from .models import EloModel, poisson_1x2_over25


@dataclass
class PredictionEngine:
    max_goals: int = 7
    elo_k_factor: float = 20.0
    elo_home_adv: float = 75.0
    min_lambda: float = 0.15
    max_lambda: float = 3.5

    def build_team_strengths(self, matches: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
        if played.empty:
            return {}

        home_avg = float(played["home_goals"].mean())
        away_avg = float(played["away_goals"].mean())

        teams: Iterable[str] = sorted(set(played["home_team"]).union(set(played["away_team"])))
        strengths: Dict[str, Dict[str, float]] = {}

        for team in teams:
            home_matches = played[played["home_team"] == team]
            away_matches = played[played["away_team"] == team]

            scored_home = home_matches["home_goals"].mean()
            conceded_home = home_matches["away_goals"].mean()
            scored_away = away_matches["away_goals"].mean()
            conceded_away = away_matches["home_goals"].mean()

            strengths[team] = {
                "attack_home": _ratio(scored_home, home_avg),
                "defense_home": _ratio(conceded_home, away_avg),
                "attack_away": _ratio(scored_away, away_avg),
                "defense_away": _ratio(conceded_away, home_avg),
            }

        strengths["_league"] = {
            "home_avg": home_avg,
            "away_avg": away_avg,
        }
        return strengths

    def fit_elo(self, matches: pd.DataFrame) -> EloModel:
        model = EloModel(k_factor=self.elo_k_factor, home_advantage=self.elo_home_adv)
        played = matches.dropna(subset=["home_goals", "away_goals"]).sort_values("date")

        for _, row in played.iterrows():
            model.update(
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                home_goals=int(row["home_goals"]),
                away_goals=int(row["away_goals"]),
            )

        return model

    def expected_goals(
        self,
        home_team: str,
        away_team: str,
        strengths: Dict[str, Dict[str, float]],
        elo_model: EloModel,
    ) -> Tuple[float, float]:
        league = strengths.get("_league", {})
        home_avg = league.get("home_avg", 1.35)
        away_avg = league.get("away_avg", 1.10)

        home_strength = strengths.get(home_team, _default_strengths())
        away_strength = strengths.get(away_team, _default_strengths())

        base_home = home_avg * home_strength["attack_home"] * away_strength["defense_away"]
        base_away = away_avg * away_strength["attack_away"] * home_strength["defense_home"]

        elo_home = elo_model.get_rating(home_team) + self.elo_home_adv
        elo_away = elo_model.get_rating(away_team)
        elo_diff = elo_home - elo_away

        # Moderate Elo impact to avoid unstable lambdas.
        home_factor = np.exp(elo_diff / 1200.0)
        away_factor = np.exp(-elo_diff / 1200.0)

        lambda_home = _clip(base_home * home_factor, self.min_lambda, self.max_lambda)
        lambda_away = _clip(base_away * away_factor, self.min_lambda, self.max_lambda)

        return lambda_home, lambda_away

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        strengths: Dict[str, Dict[str, float]],
        elo_model: EloModel,
    ) -> Dict[str, float]:
        lambda_home, lambda_away = self.expected_goals(home_team, away_team, strengths, elo_model)
        probs = poisson_1x2_over25(lambda_home, lambda_away, max_goals=self.max_goals)
        return probs


def _clip(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def _ratio(value: float, baseline: float) -> float:
    if pd.isna(value) or baseline <= 0:
        return 1.0
    return float(value / baseline)


def _default_strengths() -> Dict[str, float]:
    return {
        "attack_home": 1.0,
        "defense_home": 1.0,
        "attack_away": 1.0,
        "defense_away": 1.0,
    }
