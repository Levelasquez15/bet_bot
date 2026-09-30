from __future__ import annotations
import math
from typing import Dict
import numpy as np


def _poisson_pmf(k: int, mu: float) -> float:
    """Calcula P(X = k) con distribución Poisson sin requerir scipy."""
    mu = max(float(mu), 0.05)
    return (math.exp(-mu) * (mu ** k)) / math.factorial(k)


def calculate_poisson_matrix(lambda_home: float, lambda_away: float, max_goals: int = 7) -> Dict[str, float]:
    """
    Calcula la matriz de probabilidad bivariada de Poisson para los principales
    mercados de apuestas: 1X2, Doble Oportunidad, Over/Under (1.5, 2.5, 3.5) y BTTS.
    Implementación pura de alta velocidad sin dependencias pesadas de scipy.
    """
    goals = np.arange(max_goals + 1)
    lh = max(float(lambda_home), 0.05)
    la = max(float(lambda_away), 0.05)

    home_pmf = np.array([_poisson_pmf(k, lh) for k in goals])
    away_pmf = np.array([_poisson_pmf(k, la) for k in goals])

    # Matriz [goles_local, goles_visitante]
    matrix = np.outer(home_pmf, away_pmf)

    # 1X2
    p_home = float(np.tril(matrix, k=-1).sum())
    p_draw = float(np.trace(matrix))
    p_away = float(np.triu(matrix, k=1).sum())

    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    # Doble oportunidad
    p_1x = min(1.0, p_home + p_draw)
    p_x2 = min(1.0, p_away + p_draw)
    p_12 = min(1.0, p_home + p_away)

    # Over / Under
    goals_sum = np.add.outer(goals, goals)

    p_over_15 = float(matrix[goals_sum >= 2].sum())
    p_under_15 = max(0.0, 1.0 - p_over_15)

    p_over_25 = float(matrix[goals_sum >= 3].sum())
    p_under_25 = max(0.0, 1.0 - p_over_25)

    p_over_35 = float(matrix[goals_sum >= 4].sum())
    p_under_35 = max(0.0, 1.0 - p_over_35)

    # Ambos Equipos Marcarán (BTTS)
    p_btts_yes = float((1.0 - home_pmf[0]) * (1.0 - away_pmf[0]))
    p_btts_no = max(0.0, 1.0 - p_btts_yes)

    return {
        "home_win": round(p_home, 4),
        "draw": round(p_draw, 4),
        "away_win": round(p_away, 4),
        "double_chance_1x": round(p_1x, 4),
        "double_chance_x2": round(p_x2, 4),
        "double_chance_12": round(p_12, 4),
        "over_1_5": round(p_over_15, 4),
        "under_1_5": round(p_under_15, 4),
        "over_2_5": round(p_over_25, 4),
        "under_2_5": round(p_under_25, 4),
        "over_3_5": round(p_over_35, 4),
        "under_3_5": round(p_under_35, 4),
        "btts_yes": round(p_btts_yes, 4),
        "btts_no": round(p_btts_no, 4),
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
        "expected_total_goals": round(lh + la, 2)
    }


def poisson_1x2_over25(lambda_home: float, lambda_away: float, max_goals: int = 7) -> Dict[str, float]:
    """Wrapper para mantener compatibilidad con código existente."""
    return calculate_poisson_matrix(lambda_home, lambda_away, max_goals=max_goals)
