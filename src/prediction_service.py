from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import pandas as pd
import soccerdata as sd

from .api_client import get_odds_for_fixture
from .config import MESSAGES
from .models.poisson import poisson_1x2_over25


def get_team_stats_soccerdata(team_name: str, league: str, seasons: str = "2324") -> Optional[Dict]:
    """
    Get team statistics from soccerdata for enhanced predictions.
    Returns recent form, xG, etc.
    """
    try:
        # Try to match team name with soccerdata format
        fbref = sd.FBref(leagues=[league], seasons=seasons)

        # Get team match logs
        team_match_logs = fbref.read_team_match_stats(team_name, force_cache=True)

        if team_match_logs.empty:
            return None

        # Get last 5 matches
        recent_matches = team_match_logs.tail(5)

        # Calculate recent form metrics
        goals_scored = recent_matches['GF'].sum() if 'GF' in recent_matches.columns else 0
        goals_conceded = recent_matches['GA'].sum() if 'GA' in recent_matches.columns else 0
        xg_for = recent_matches['xG'].sum() if 'xG' in recent_matches.columns else 0
        xg_against = recent_matches['xGA'].sum() if 'xGA' in recent_matches.columns else 0

        wins = len(recent_matches[recent_matches['Result'] == 'W']) if 'Result' in recent_matches.columns else 0
        draws = len(recent_matches[recent_matches['Result'] == 'D']) if 'Result' in recent_matches.columns else 0
        losses = len(recent_matches[recent_matches['Result'] == 'L']) if 'Result' in recent_matches.columns else 0

        return {
            'recent_goals_scored': goals_scored,
            'recent_goals_conceded': goals_conceded,
            'recent_xg_for': xg_for,
            'recent_xg_against': xg_against,
            'recent_wins': wins,
            'recent_draws': draws,
            'recent_losses': losses,
            'form_score': (wins * 3 + draws) / 5.0 if recent_matches.shape[0] > 0 else 0
        }

    except Exception as e:
        print(f"Error getting stats for {team_name}: {e}")
        return None


def enhance_prediction_with_soccerdata(
    home_team: str,
    away_team: str,
    league: str,
    base_probs: Dict,
    seasons: str = "2324"
) -> Dict:
    """
    Enhance basic Poisson prediction with soccerdata stats.
    """
    home_stats = get_team_stats_soccerdata(home_team, league, seasons)
    away_stats = get_team_stats_soccerdata(away_team, league, seasons)

    enhanced_probs = base_probs.copy()

    if home_stats and away_stats:
        # Adjust probabilities based on recent form
        home_form = home_stats.get('form_score', 0)
        away_form = away_stats.get('form_score', 0)

        form_diff = home_form - away_form

        # Adjust win probabilities based on form (small adjustment)
        form_adjustment = form_diff * 0.05  # Max 5% adjustment

        enhanced_probs['home_win'] = max(0.01, min(0.99, base_probs['home_win'] + form_adjustment))
        enhanced_probs['away_win'] = max(0.01, min(0.99, base_probs['away_win'] - form_adjustment))

        # Recalculate draw probability to maintain sum = 1
        total_win_probs = enhanced_probs['home_win'] + enhanced_probs['away_win']
        enhanced_probs['draw'] = 1.0 - total_win_probs

        # Add metadata
        enhanced_probs['home_form'] = home_form
        enhanced_probs['away_form'] = away_form
        enhanced_probs['enhanced'] = True

    return enhanced_probs


def generate_betting_recommendations(probs: Dict, min_prob: float = 0.55) -> List[Dict]:
    """
    Generate betting recommendations based on probabilities.
    """
    recommendations = []

    # 1X2 recommendations
    if probs['home_win'] >= min_prob:
        recommendations.append({
            'type': '1X2',
            'pick': '1',
            'description': f'Local gana ({probs["home_win"]:.1%})',
            'probability': probs['home_win']
        })

    if probs['draw'] >= min_prob:
        recommendations.append({
            'type': '1X2',
            'pick': 'X',
            'description': f'Empate ({probs["draw"]:.1%})',
            'probability': probs['draw']
        })

    if probs['away_win'] >= min_prob:
        recommendations.append({
            'type': '1X2',
            'pick': '2',
            'description': f'Visitante gana ({probs["away_win"]:.1%})',
            'probability': probs['away_win']
        })

    # Over/Under recommendations
    if probs['over_2_5'] >= min_prob:
        recommendations.append({
            'type': 'Over/Under',
            'pick': 'Over 2.5',
            'description': f'Más de 2.5 goles ({probs["over_2_5"]:.1%})',
            'probability': probs['over_2_5']
        })

    if probs['under_2_5'] >= min_prob:
        recommendations.append({
            'type': 'Over/Under',
            'pick': 'Under 2.5',
            'description': f'Menos de 2.5 goles ({probs["under_2_5"]:.1%})',
            'probability': probs['under_2_5']
        })

    # Sort by probability descending
    recommendations.sort(key=lambda x: x['probability'], reverse=True)

    return recommendations


def predict_match_inline(home_team: str, away_team: str, matches: pd.DataFrame, league: str = "ENG-Premier League") -> Dict:
    """Predict match with better error handling and soccerdata enhancement."""
    if matches.empty:
        raise ValueError("No historical data available for predictions")

    from .engine import PredictionEngine
    engine = PredictionEngine()
    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()

    if played.empty:
        raise ValueError("No completed matches found for training")

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)

    # Get base probabilities
    base_probs = engine.predict_match(home_team, away_team, strengths, elo_model)

    # Enhance with soccerdata if available
    try:
        enhanced_probs = enhance_prediction_with_soccerdata(home_team, away_team, league, base_probs)
    except Exception as e:
        print(f"Could not enhance prediction with soccerdata: {e}")
        enhanced_probs = base_probs

    # Generate recommendations
    recommendations = generate_betting_recommendations(enhanced_probs)

    return {
        'probabilities': enhanced_probs,
        'recommendations': recommendations,
        'base_lambda_home': base_probs.get('lambda_home', 0),
        'base_lambda_away': base_probs.get('lambda_away', 0)
    }


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


async def analyze_jornada_inline(matches: pd.DataFrame, fixtures_df: pd.DataFrame, league: str = "ENG-Premier League") -> Dict:
    """Analyze today's jornada matches with enhanced predictions."""
    from .engine import PredictionEngine
    from .recommender import BettingRecommender

    engine = PredictionEngine()
    recommender = BettingRecommender()

    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    if played.empty:
        return {"picks": None, "acc": None, "error": "No historical data available"}

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)

    analyzed_matches = []

    for _, fx in fixtures_df.iterrows():
        fixture_id = int(fx["fixture_id"])
        home = str(fx["home_team"])
        away = str(fx["away_team"])

        try:
            # Get base probabilities
            base_probs = engine.predict_match(home, away, strengths, elo_model)

            # Enhance with soccerdata
            enhanced_probs = enhance_prediction_with_soccerdata(home, away, league, base_probs)

            # Generate recommendations
            recommendations = generate_betting_recommendations(enhanced_probs, min_prob=0.52)  # Slightly lower threshold

            analyzed_matches.append({
                'fixture_id': fixture_id,
                'home_team': home,
                'away_team': away,
                'probabilities': enhanced_probs,
                'recommendations': recommendations,
                'best_pick': recommendations[0] if recommendations else None
            })

        except Exception as e:
            print(f"Error analyzing {home} vs {away}: {e}")
            continue

    if not analyzed_matches:
        return {"picks": None, "acc": None, "error": "No matches could be analyzed"}

    # Create picks DataFrame for compatibility with existing recommender
    picks_data = []
    for match in analyzed_matches:
        if match['best_pick']:
            picks_data.append({
                'fixture_id': match['fixture_id'],
                'home_team': match['home_team'],
                'away_team': match['away_team'],
                'pick': match['best_pick']['pick'],
                'type': match['best_pick']['type'],
                'probability': match['best_pick']['probability'],
                'description': match['best_pick']['description']
            })

    if picks_data:
        picks_df = pd.DataFrame(picks_data)
        acc = recommender.build_accumulator(picks_df, max_legs=3)
    else:
        picks_df = None
        acc = None

    return {
        "picks": picks_df,
        "acc": acc,
        "analyzed_matches": analyzed_matches
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