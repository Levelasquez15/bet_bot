from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd
import numpy as np

from .engine import PredictionEngine


@dataclass
class BacktestResult:
    metrics: Dict[str, float]
    predictions: pd.DataFrame


class Backtester:
    def __init__(self, engine: PredictionEngine) -> None:
        self.engine = engine

    def run_rolling(self, matches: pd.DataFrame, min_history: int = 120) -> BacktestResult:
        played = matches.dropna(subset=["home_goals", "away_goals"]).sort_values("date").reset_index(drop=True)
        rows: List[Dict] = []

        for idx in range(min_history, len(played)):
            history = played.iloc[:idx]
            target = played.iloc[idx]

            strengths = self.engine.build_team_strengths(history)
            elo = self.engine.fit_elo(history)

            probs = self.engine.predict_match(
                home_team=str(target["home_team"]),
                away_team=str(target["away_team"]),
                strengths=strengths,
                elo_model=elo,
            )

            outcome_1x2 = _actual_1x2(int(target["home_goals"]), int(target["away_goals"]))
            outcome_over = 1 if int(target["home_goals"]) + int(target["away_goals"]) >= 3 else 0

            rows.append(
                {
                    "date": target["date"],
                    "home_team": target["home_team"],
                    "away_team": target["away_team"],
                    "actual_1x2": outcome_1x2,
                    "actual_over25": outcome_over,
                    **probs,
                }
            )

        pred_df = pd.DataFrame(rows)
        metrics = _compute_metrics(pred_df)
        return BacktestResult(metrics=metrics, predictions=pred_df)


def _actual_1x2(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "H"
    if home_goals < away_goals:
        return "A"
    return "D"


def _compute_metrics(pred_df: pd.DataFrame) -> Dict[str, float]:
    if pred_df.empty:
        return {
            "samples": 0.0,
            "accuracy_1x2": 0.0,
            "logloss_1x2": 0.0,
            "brier_over25": 0.0,
        }

    pred_labels = pred_df[["home_win", "draw", "away_win"]].idxmax(axis=1)
    map_label = {"home_win": "H", "draw": "D", "away_win": "A"}
    pred_1x2 = pred_labels.map(map_label)

    acc_1x2 = (pred_1x2 == pred_df["actual_1x2"]).mean()

    eps = 1e-12
    probs_actual = []
    for _, row in pred_df.iterrows():
        if row["actual_1x2"] == "H":
            probs_actual.append(row["home_win"])
        elif row["actual_1x2"] == "D":
            probs_actual.append(row["draw"])
        else:
            probs_actual.append(row["away_win"])

    logloss = -pd.Series(probs_actual).clip(eps, 1.0 - eps).apply(lambda p: np.log(p)).mean()

    brier_over = ((pred_df["over_2_5"] - pred_df["actual_over25"]) ** 2).mean()

    return {
        "samples": float(len(pred_df)),
        "accuracy_1x2": float(acc_1x2),
        "logloss_1x2": float(logloss),
        "brier_over25": float(brier_over),
    }
