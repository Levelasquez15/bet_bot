from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class EloModel:
    """Simple Elo implementation with configurable home advantage."""

    k_factor: float = 20.0
    base_rating: float = 1500.0
    home_advantage: float = 75.0
    ratings: Dict[str, float] = field(default_factory=dict)

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.base_rating)

    def expected_home_score(self, home_team: str, away_team: str) -> float:
        home_rating = self.get_rating(home_team) + self.home_advantage
        away_rating = self.get_rating(away_team)
        return 1.0 / (1.0 + 10.0 ** ((away_rating - home_rating) / 400.0))

    def update(self, home_team: str, away_team: str, home_goals: int, away_goals: int) -> None:
        expected_home = self.expected_home_score(home_team, away_team)
        expected_away = 1.0 - expected_home

        if home_goals > away_goals:
            actual_home, actual_away = 1.0, 0.0
        elif home_goals < away_goals:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        home_new = self.get_rating(home_team) + self.k_factor * (actual_home - expected_home)
        away_new = self.get_rating(away_team) + self.k_factor * (actual_away - expected_away)

        self.ratings[home_team] = home_new
        self.ratings[away_team] = away_new
