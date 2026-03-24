from __future__ import annotations

from typing import Dict

import numpy as np
from scipy.stats import poisson


def poisson_1x2_over25(lambda_home: float, lambda_away: float, max_goals: int = 7) -> Dict[str, float]:
    """Return probabilities for 1X2 and over 2.5 goals with a Poisson score matrix."""
    goals = np.arange(max_goals + 1)

    home_pmf = poisson.pmf(goals, mu=max(lambda_home, 0.05))
    away_pmf = poisson.pmf(goals, mu=max(lambda_away, 0.05))

    matrix = np.outer(home_pmf, away_pmf)

    p_home = float(np.tril(matrix, k=-1).sum())
    p_draw = float(np.trace(matrix))
    p_away = float(np.triu(matrix, k=1).sum())

    over_mask = np.add.outer(goals, goals) >= 3
    p_over_25 = float(matrix[over_mask].sum())
    p_under_25 = 1.0 - p_over_25

    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    return {
        "home_win": p_home,
        "draw": p_draw,
        "away_win": p_away,
        "over_2_5": p_over_25,
        "under_2_5": p_under_25,
        "lambda_home": float(lambda_home),
        "lambda_away": float(lambda_away),
    }
