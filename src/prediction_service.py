from __future__ import annotations

import asyncio
from typing import Dict

import pandas as pd

from .api_client import get_odds_for_fixture
from .config import MESSAGES


def predict_match_inline(home_team: str, away_team: str, matches: pd.DataFrame) -> Dict:
    """Predict match with better error handling."""
    if matches.empty:
        raise ValueError("No historical data available for predictions")

    from .engine import PredictionEngine
    engine = PredictionEngine()
    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()

    if played.empty:
        raise ValueError("No completed matches found for training")

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)
    return engine.predict_match(home_team, away_team, strengths, elo_model)


def get_recommendation(probs: Dict) -> str:
    """Get recommendation based on probabilities."""
    home_win = probs['home_win']
    draw = probs['draw']
    away_win = probs['away_win']

    max_prob = max(home_win, draw, away_win)

    if max_prob >= 0.6:
        confidence = "Muy alta"
    elif max_prob >= 0.55:
        confidence = "Alta"
    elif max_prob >= 0.5:
        confidence = "Media"
    else:
        confidence = "Baja"

    if home_win == max_prob:
        return f"1 (Local gana) - Confianza: {confidence}"
    elif draw == max_prob:
        return f"X (Empate) - Confianza: {confidence}"
    else:
        return f"2 (Visitante gana) - Confianza: {confidence}"


async def analyze_jornada_inline(matches: pd.DataFrame, fixtures_df: pd.DataFrame) -> Dict:
    """Analyze today's jornada matches."""
    from .engine import PredictionEngine
    from .recommender import BettingRecommender

    engine = PredictionEngine()
    recommender = BettingRecommender()

    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    if played.empty:
        return {"picks": None, "acc": None}

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)

    compared_rows = []
    for _, fx in fixtures_df.iterrows():
        fixture_id = int(fx["fixture_id"])
        home = str(fx["home_team"])
        away = str(fx["away_team"])

        probs = engine.predict_match(home, away, strengths, elo_model)
        odds = get_odds_for_fixture(fixture_id)
        compared = recommender.compare_lines(fixture_id, home, away, probs, odds)
        if not compared.empty:
            compared_rows.append(compared)

    if not compared_rows:
        return {"picks": None, "acc": None}

    compared_df = pd.concat(compared_rows, ignore_index=True)
    picks_df = recommender.best_pick_per_fixture(compared_df, min_probability=0.55, min_expected_value=0.03)
    acc = recommender.build_accumulator(picks_df, max_legs=3)

    return {
        "picks": picks_df,
        "acc": acc,
    }


async def build_accumulator_inline(matches: pd.DataFrame, fixtures_df: pd.DataFrame, legs: int) -> Dict:
    """Build accumulator with specified number of legs."""
    from .engine import PredictionEngine
    from .recommender import BettingRecommender

    engine = PredictionEngine()
    recommender = BettingRecommender()

    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    if played.empty:
        return {"picks": None, "acc": None}

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)

    compared_rows = []
    for _, fx in fixtures_df.iterrows():
        fixture_id = int(fx["fixture_id"])
        home = str(fx["home_team"])
        away = str(fx["away_team"])

        probs = engine.predict_match(home, away, strengths, elo_model)
        odds = get_odds_for_fixture(fixture_id)
        compared = recommender.compare_lines(fixture_id, home, away, probs, odds)
        if not compared.empty:
            compared_rows.append(compared)

    if not compared_rows:
        return {"picks": None, "acc": None}

    compared_df = pd.concat(compared_rows, ignore_index=True)
    picks_df = recommender.best_pick_per_fixture(compared_df, min_probability=0.5, min_expected_value=0.02)

    if picks_df.empty or len(picks_df) < legs:
        return {"picks": None, "acc": None}

    # Select top picks for accumulator
    top_picks = picks_df.head(legs)
    acc = recommender.build_accumulator(top_picks, max_legs=legs)

    return {
        "picks": top_picks,
        "acc": acc,
    }


def backtest_inline(matches: pd.DataFrame, min_history: int) -> Dict[str, float]:
    from .engine import PredictionEngine
    from .backtesting import Backtester

    engine = PredictionEngine()
    bt = Backtester(engine)
    result = bt.run_rolling(matches, min_history=min_history)
    return result.metrics