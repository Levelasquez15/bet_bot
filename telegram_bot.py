from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Dict, Tuple

from dotenv import load_dotenv
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.backtesting import Backtester
from src.data_sources import ApiFootballDataSource
from src.engine import PredictionEngine
from src.recommender import BettingRecommender

load_dotenv()

DEFAULT_LEAGUE_ID = 39
DEFAULT_SEASON = datetime.utcnow().year
MAX_FIXTURES_ANALYSIS = 12


def _get_api_key() -> str:
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing API_FOOTBALL_KEY in .env or environment")
    return api_key


def _get_telegram_token() -> str:
    token = os.getenv("TELEGRAM_TOKEN", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TELEGRAM_TOKEN/TELEGRAM_BOT_TOKEN in .env or environment")
    return token


def _current_config(context: ContextTypes.DEFAULT_TYPE) -> Tuple[int, int]:
    league_id = int(context.bot_data.get("league_id", DEFAULT_LEAGUE_ID))
    season = int(context.bot_data.get("season", DEFAULT_SEASON))
    return league_id, season


async def _load_history(context: ContextTypes.DEFAULT_TYPE):
    league_id, season = _current_config(context)
    source = ApiFootballDataSource(api_key=_get_api_key())
    matches = await asyncio.to_thread(source.get_historical_matches, league_id, season)
    return matches


def _predict_match_inline(home_team: str, away_team: str, matches):
    engine = PredictionEngine()
    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)
    return engine.predict_match(home_team, away_team, strengths, elo_model)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = _current_config(context)
    message = (
        "Bot listo.\n"
        "Comandos:\n"
        "/status - estado actual\n"
        "/setleague <league_id> <season> - configurar liga\n"
        "/predict <Local> | <Visitante> - prediccion de un partido\n"
        "/analyze_next [n] - picks de proximos partidos y combinada\n"
        "/backtest [min_history] - validar modelo\n"
        f"\nConfiguracion actual: league={league_id}, season={season}"
    )
    await update.message.reply_text(message)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = _current_config(context)
    has_api = bool(os.getenv("API_FOOTBALL_KEY", ""))
    has_token = bool(os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", ""))
    await update.message.reply_text(
        f"Estado:\n"
        f"league_id={league_id}\n"
        f"season={season}\n"
        f"API_FOOTBALL_KEY={'OK' if has_api else 'MISSING'}\n"
        f"TELEGRAM_TOKEN={'OK' if has_token else 'MISSING'}"
    )


async def cmd_setleague(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /setleague <league_id> <season>")
        return

    try:
        league_id = int(context.args[0])
        season = int(context.args[1])
    except ValueError:
        await update.message.reply_text("league_id y season deben ser numericos")
        return

    context.bot_data["league_id"] = league_id
    context.bot_data["season"] = season
    await update.message.reply_text(f"Configurado: league_id={league_id}, season={season}")


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text("Uso: /predict <Local> | <Visitante>")
        return

    home_team, away_team = [p.strip() for p in raw.split("|", maxsplit=1)]
    if not home_team or not away_team:
        await update.message.reply_text("Equipos invalidos. Uso: /predict <Local> | <Visitante>")
        return

    try:
        matches = await _load_history(context)
        probs = await asyncio.to_thread(_predict_match_inline, home_team, away_team, matches)
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Error calculando prediccion: {exc}")
        return

    text = (
        f"Prediccion {home_team} vs {away_team}\n"
        f"P(1): {probs['home_win']:.2%}\n"
        f"P(X): {probs['draw']:.2%}\n"
        f"P(2): {probs['away_win']:.2%}\n"
        f"P(+2.5): {probs['over_2_5']:.2%}\n"
        f"Lambda local: {probs['lambda_home']:.3f}\n"
        f"Lambda visita: {probs['lambda_away']:.3f}"
    )
    await update.message.reply_text(text)


def _analyze_next_inline(matches, league_id: int, season: int, n: int) -> Dict:
    engine = PredictionEngine()
    recommender = BettingRecommender()
    source = ApiFootballDataSource(api_key=_get_api_key())

    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)

    fixtures_df = source.get_upcoming_fixtures(league_id=league_id, season=season, next_n=n)

    compared_rows = []
    for _, fx in fixtures_df.iterrows():
        fixture_id = int(fx["fixture_id"])
        home = str(fx["home_team"])
        away = str(fx["away_team"])

        probs = engine.predict_match(home, away, strengths, elo_model)
        odds = source.get_odds_for_fixture(fixture_id)
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


async def cmd_analyze_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        n = int(context.args[0]) if context.args else 6
    except ValueError:
        await update.message.reply_text("Uso: /analyze_next [n]")
        return

    n = max(2, min(n, MAX_FIXTURES_ANALYSIS))

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)
        result = await asyncio.to_thread(_analyze_next_inline, matches, league_id, season, n)
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Error analizando proximos partidos: {exc}")
        return

    picks_df = result.get("picks")
    acc = result.get("acc")

    if picks_df is None or picks_df.empty:
        await update.message.reply_text("No encontre picks que cumplan los filtros (prob>=55% y EV>=3%).")
        return

    lines = ["Top picks por partido:"]
    for _, row in picks_df.head(8).iterrows():
        lines.append(
            f"- {row['match']} | {row['selection']} ({row['market']}) | "
            f"P={row['probability']:.1%} | Odd={row['odds']:.2f} | EV={row['expected_value']:.1%}"
        )

    if acc:
        lines.append("")
        lines.append("Combinada sugerida:")
        lines.append(f"- Piernas: {int(acc['legs'])}")
        lines.append(f"- Probabilidad: {acc['combined_probability']:.2%}")
        lines.append(f"- Cuota: {acc['combined_odds']:.2f}")
        lines.append(f"- EV: {acc['combined_expected_value']:.2%}")

    await update.message.reply_text("\n".join(lines))


def _backtest_inline(matches, min_history: int) -> Dict[str, float]:
    engine = PredictionEngine()
    bt = Backtester(engine)
    result = bt.run_rolling(matches, min_history=min_history)
    return result.metrics


async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        min_history = int(context.args[0]) if context.args else 120
    except ValueError:
        await update.message.reply_text("Uso: /backtest [min_history]")
        return

    min_history = max(20, min_history)

    try:
        matches = await _load_history(context)
        metrics = await asyncio.to_thread(_backtest_inline, matches, min_history)
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Error en backtesting: {exc}")
        return

    text = (
        "Backtesting:\n"
        f"- Muestras: {int(metrics['samples'])}\n"
        f"- Accuracy 1X2: {metrics['accuracy_1x2']:.2%}\n"
        f"- LogLoss 1X2: {metrics['logloss_1x2']:.4f}\n"
        f"- Brier +2.5: {metrics['brier_over25']:.4f}"
    )
    await update.message.reply_text(text)


def main() -> None:
    token = _get_telegram_token()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("setleague", cmd_setleague))
    app.add_handler(CommandHandler("predict", cmd_predict))
    app.add_handler(CommandHandler("analyze_next", cmd_analyze_next))
    app.add_handler(CommandHandler("backtest", cmd_backtest))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
