from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, date
from typing import Dict, Tuple, List

from dotenv import load_dotenv
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lazy imports to avoid scipy issues at startup
Backtester = None
ApiFootballDataSource = None
PredictionEngine = None
BettingRecommender = None

def _import_modules():
    """Lazy import of modules that depend on scipy."""
    global Backtester, ApiFootballDataSource, PredictionEngine, BettingRecommender
    if Backtester is None:
        try:
            from src.backtesting import Backtester
            from src.data_sources import ApiFootballDataSource
            from src.engine import PredictionEngine
            from src.recommender import BettingRecommender
            logger.info("Modules imported successfully")
        except Exception as e:
            logger.error(f"Failed to import modules: {e}")
            raise

load_dotenv()

DEFAULT_LEAGUE_ID = 39  # Premier League
DEFAULT_SEASON = datetime.utcnow().year
MAX_FIXTURES_ANALYSIS = 12

# Mensajes en español
MESSAGES = {
    'start': """🤖 *BetBot - Pronósticos Deportivos*

¡Hola! Soy tu asistente de pronósticos deportivos.

📊 *Comandos disponibles:*
/jornada - Análisis completo de la jornada actual
/partido `<Local>` vs `<Visitante>` - Análisis de un partido específico
/combinada `<n>` - Generar combinada (3, 5 o 10 cuotas)
/comparar_lineas - Comparar diferentes líneas del mismo partido
/backtest - Validar rendimiento del modelo
/status - Estado del bot y configuración
/setleague `<id>` `<temporada>` - Cambiar liga y temporada

⚙️ *Configuración actual:* Liga={league}, Temporada={season}""",

    'status': """📊 *Estado del Bot*

🔧 Configuración:
• Liga: {league_id}
• Temporada: {season}
• API Football: {api_status}
• Token Telegram: {token_status}

📈 Modelo listo para análisis""",

    'no_matches_today': "📅 No hay partidos programados para hoy en la liga configurada.",

    'analyzing_matches': "🔍 Analizando {count} partidos de la jornada...",

    'top_picks': """🎯 *Mejores Picks de la Jornada*

{matches_text}

💡 *Recomendaciones basadas en modelo Poisson+Elo*""",

    'accumulator': """🎰 *Combinada Sugerida*

🔗 {legs} partidos combinados
📊 Probabilidad total: {prob:.1%}
💰 Cuota total: {odds:.2f}
🎯 Valor esperado: {ev:.1%}

⚠️ *Recuerda:* El juego responsable es fundamental""",

    'single_match': """⚽ *Análisis: {home} vs {away}*

📅 Fecha: {date}
🏆 Liga: {league}

🎲 *Probabilidades del modelo:*
• 1 (Local): {home_win:.1%}
• X (Empate): {draw:.1%}
• 2 (Visitante): {away_win:.1%}
• +2.5 Goles: {over:.1%}

⚡ *Fuerza de ataque:*
• {home}: {lambda_home:.2f}
• {away}: {lambda_away:.2f}

💡 *Recomendación:* {recommendation}""",

    'accumulator_options': """🎰 *Opciones de Combinada*

Elige el número de cuotas para tu combinada:

• `/combinada 3` - Combinada de 3 cuotas (recomendado)
• `/combinada 5` - Combinada de 5 cuotas
• `/combinada 10` - Combinada de 10 cuotas

💡 *Consejo:* Las combinadas de 3-5 cuotas ofrecen mejor balance riesgo/recompensa.""",

    'line_comparison': """📊 *Comparación de Líneas*

Envía las líneas en este formato:
/comparar_lineas
Local: Real Madrid
Visitante: Barcelona
Línea 1: 1.85, 3.40, 4.20
Línea 2: 1.90, 3.30, 4.10

Te diré cuál es la más favorable según el modelo.""",

    'error_data': "❌ Error obteniendo datos. Verifica la configuración de liga/temporada.",
    'error_analysis': "❌ Error en el análisis. Inténtalo de nuevo.",
    'error_backtest': "❌ Error en validación del modelo.",
    'invalid_format': "❌ Formato inválido. Usa: {usage}",
    'processing': "⏳ Procesando...",
}


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


async def _load_history(context: ContextTypes.DEFAULT_TYPE) -> pd.DataFrame:
    """Load historical matches with better error handling."""
    try:
        _import_modules()
        league_id, season = _current_config(context)
        source = ApiFootballDataSource(api_key=_get_api_key())
        matches = await asyncio.to_thread(source.get_historical_matches, league_id, season)

        # If no data for current season, try previous season
        if matches.empty and season > 2020:
            matches = await asyncio.to_thread(source.get_historical_matches, league_id, season - 1)

        return matches
    except Exception as e:
        print(f"Error loading history: {e}")
        return pd.DataFrame()


def _predict_match_inline(home_team: str, away_team: str, matches: pd.DataFrame) -> Dict:
    """Predict match with better error handling."""
    if matches.empty:
        raise ValueError("No historical data available for predictions")

    _import_modules()
    engine = PredictionEngine()
    played = matches.dropna(subset=["home_goals", "away_goals"]).copy()

    if played.empty:
        raise ValueError("No completed matches found for training")

    strengths = engine.build_team_strengths(played)
    elo_model = engine.fit_elo(played)
    return engine.predict_match(home_team, away_team, strengths, elo_model)


def _get_recommendation(probs: Dict) -> str:
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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = _current_config(context)
    message = MESSAGES['start'].format(league=league_id, season=season)
    await update.message.reply_text(message, parse_mode='Markdown')


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = _current_config(context)
    has_api = bool(os.getenv("API_FOOTBALL_KEY", ""))
    has_token = bool(os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", ""))

    message = MESSAGES['status'].format(
        league_id=league_id,
        season=season,
        api_status="✅ OK" if has_api else "❌ FALTA",
        token_status="✅ OK" if has_token else "❌ FALTA"
    )
    await update.message.reply_text(message, parse_mode='Markdown')


async def cmd_setleague(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /setleague <league_id> <season>", parse_mode='Markdown')
        return

    try:
        league_id = int(context.args[0])
        season = int(context.args[1])
    except ValueError:
        await update.message.reply_text("league_id y season deben ser números", parse_mode='Markdown')
        return

    context.bot_data["league_id"] = league_id
    context.bot_data["season"] = season
    await update.message.reply_text(f"✅ Configurado: Liga={league_id}, Temporada={season}", parse_mode='Markdown')


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = " ".join(context.args).strip()
    if "|" not in raw and "vs" not in raw.lower():
        await update.message.reply_text("Uso: /partido `<Local>` vs `<Visitante>`\nEjemplo: /partido Real Madrid vs Barcelona", parse_mode='Markdown')
        return

    # Parse different formats: "Local | Visitante" or "Local vs Visitante"
    if "|" in raw:
        home_team, away_team = [p.strip() for p in raw.split("|", maxsplit=1)]
    else:
        parts = raw.lower().split("vs")
        if len(parts) != 2:
            await update.message.reply_text("Formato inválido. Usa: /partido Real Madrid vs Barcelona", parse_mode='Markdown')
            return
        home_team, away_team = [p.strip() for p in parts]

    if not home_team or not away_team:
        await update.message.reply_text("Equipos inválidos. Ejemplo: /partido Real Madrid vs Barcelona", parse_mode='Markdown')
        return

    await update.message.reply_text(MESSAGES['processing'])

    try:
        matches = await _load_history(context)
        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        probs = await asyncio.to_thread(_predict_match_inline, home_team, away_team, matches)
        recommendation = _get_recommendation(probs)

        # Get league info
        league_id, season = _current_config(context)
        league_name = f"Liga {league_id}"  # Could be enhanced to get actual name

        message = MESSAGES['single_match'].format(
            home=home_team,
            away=away_team,
            date=date.today().strftime("%d/%m/%Y"),
            league=league_name,
            home_win=probs['home_win'],
            draw=probs['draw'],
            away_win=probs['away_win'],
            over=probs['over_2_5'],
            lambda_home=probs['lambda_home'],
            lambda_away=probs['lambda_away'],
            recommendation=recommendation
        )

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {str(exc)}")


async def cmd_jornada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze today's matches (jornada)."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get today's fixtures
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 20)

        if fixtures_df.empty:
            await update.message.reply_text(MESSAGES['no_matches_today'])
            return

        # Filter for today
        today = date.today()
        today_fixtures = fixtures_df[
            (fixtures_df['date'].dt.date == today) |
            (fixtures_df['date'].dt.date == today)  # Could add next day if no matches today
        ]

        if today_fixtures.empty:
            # If no matches today, show next available matches
            next_matches = fixtures_df.head(6)
            await update.message.reply_text(f"📅 No hay partidos hoy. Mostrando próximos partidos:")
            today_fixtures = next_matches

        count = len(today_fixtures)
        await update.message.reply_text(MESSAGES['analyzing_matches'].format(count=count))

        # Analyze matches
        result = await asyncio.to_thread(_analyze_jornada_inline, matches, today_fixtures)

        if not result['picks'] or result['picks'].empty:
            await update.message.reply_text("No encontré picks que cumplan los criterios mínimos (prob ≥55%, EV ≥3%).")
            return

        # Format picks
        picks_text = []
        for _, row in result['picks'].head(8).iterrows():
            picks_text.append(
                f"• {row['match']} | {row['selection']} ({row['market']}) | "
                f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
            )

        message = MESSAGES['top_picks'].format(matches_text="\n".join(picks_text))
        await update.message.reply_text(message, parse_mode='Markdown')

        # Show accumulator if available
        if result['acc']:
            acc_msg = MESSAGES['accumulator'].format(
                legs=int(result['acc']['legs']),
                prob=result['acc']['combined_probability'],
                odds=result['acc']['combined_odds'],
                ev=result['acc']['combined_expected_value']
            )
            await update.message.reply_text(acc_msg, parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada: {str(exc)}")


async def cmd_combinada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate accumulator with specified number of legs."""
    if not context.args:
        await update.message.reply_text(MESSAGES['accumulator_options'], parse_mode='Markdown')
        return

    try:
        legs = int(context.args[0])
        if legs not in [3, 5, 10]:
            await update.message.reply_text("Número de cuotas debe ser 3, 5 o 10", parse_mode='Markdown')
            return
    except ValueError:
        await update.message.reply_text("Uso: /combinada <número>\nEjemplo: /combinada 3", parse_mode='Markdown')
        return

    await update.message.reply_text(f"🎰 Generando combinada de {legs} cuotas...")

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get upcoming fixtures
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 20)

        if fixtures_df.empty:
            await update.message.reply_text("No hay partidos próximos para generar combinada")
            return

        # Analyze and build accumulator
        result = await asyncio.to_thread(_build_accumulator_inline, matches, fixtures_df, legs)

        if not result['acc']:
            await update.message.reply_text(f"No pude generar una combinada de {legs} cuotas con los criterios mínimos.")
            return

        acc = result['acc']
        picks = result['picks']

        # Format accumulator details
        details = [f"🎰 *Combinada de {legs} cuotas:*"]
        for _, pick in picks.iterrows():
            details.append(
                f"• {pick['match']} | {pick['selection']} ({pick['market']}) | "
                f"Cuota: {pick['odds']:.2f}"
            )

        details.append("")
        details.append("📊 *Estadísticas:*")
        details.append(f"• Probabilidad total: {acc['combined_probability']:.1%}")
        details.append(f"• Cuota total: {acc['combined_odds']:.2f}")
        details.append(f"• Valor esperado: {acc['combined_expected_value']:.1%}")

        await update.message.reply_text("\n".join(details), parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error generando combinada: {str(exc)}")


async def cmd_comparar_lineas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compare different betting lines for the same match."""
    await update.message.reply_text(MESSAGES['line_comparison'], parse_mode='Markdown')


def _analyze_jornada_inline(matches: pd.DataFrame, fixtures_df: pd.DataFrame) -> Dict:
    """Analyze today's jornada matches."""
    _import_modules()
    engine = PredictionEngine()
    recommender = BettingRecommender()
    source = ApiFootballDataSource(api_key=_get_api_key())

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


def _build_accumulator_inline(matches: pd.DataFrame, fixtures_df: pd.DataFrame, legs: int) -> Dict:
    """Build accumulator with specified number of legs."""
    _import_modules()
    engine = PredictionEngine()
    recommender = BettingRecommender()
    source = ApiFootballDataSource(api_key=_get_api_key())

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
        odds = source.get_odds_for_fixture(fixture_id)
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


async def cmd_analyze_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        n = int(context.args[0]) if context.args else 6
    except ValueError:
        await update.message.reply_text("Uso: /analyze_next [n]", parse_mode='Markdown')
        return

    n = max(2, min(n, MAX_FIXTURES_ANALYSIS))

    await update.message.reply_text(f"🔍 Analizando próximos {n} partidos...")

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        result = await asyncio.to_thread(_analyze_next_inline, matches, league_id, season, n)

        picks_df = result.get("picks")
        acc = result.get("acc")

        if picks_df is None or picks_df.empty:
            await update.message.reply_text("No encontré picks que cumplan los filtros (prob≥55% y EV≥3%).")
            return

        lines = ["🎯 *Top picks por partido:*"]
        for _, row in picks_df.head(8).iterrows():
            lines.append(
                f"• {row['match']} | {row['selection']} ({row['market']}) | "
                f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
            )

        if acc:
            lines.append("")
            lines.append("🎰 *Combinada sugerida:*")
            lines.append(f"• Piernas: {int(acc['legs'])}")
            lines.append(f"• Probabilidad: {acc['combined_probability']:.2%}")
            lines.append(f"• Cuota: {acc['combined_odds']:.2f}")
            lines.append(f"• EV: {acc['combined_expected_value']:.2%}")

        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando próximos partidos: {str(exc)}")


async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        min_history = int(context.args[0]) if context.args else 120
    except ValueError:
        await update.message.reply_text("Uso: /backtest [min_history]", parse_mode='Markdown')
        return

    min_history = max(20, min_history)

    await update.message.reply_text("📊 Validando rendimiento del modelo...")

    try:
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        metrics = await asyncio.to_thread(_backtest_inline, matches, min_history)

        text = (
            "📊 *Validación del Modelo*\n"
            f"• Muestras analizadas: {int(metrics['samples'])}\n"
            f"• Precisión 1X2: {metrics['accuracy_1x2']:.1%}\n"
            f"• Pérdida Logarítmica 1X2: {metrics['logloss_1x2']:.4f}\n"
            f"• Error Brier +2.5: {metrics['brier_over25']:.4f}\n"
            "\n💡 *Interpretación:*\n"
            "• Precisión >50% indica valor predictivo\n"
            "• LogLoss <1.0 es bueno, <0.8 es excelente\n"
            "• Brier <0.25 es aceptable"
        )
        await update.message.reply_text(text, parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error en validación: {str(exc)}")


def _analyze_next_inline(matches: pd.DataFrame, league_id: int, season: int, n: int) -> Dict:
    """Analyze next n fixtures (legacy function, kept for compatibility)."""
    _import_modules()
    source = ApiFootballDataSource(api_key=_get_api_key())
    fixtures_df = source.get_upcoming_fixtures(league_id=league_id, season=season, next_n=n)
    return _analyze_jornada_inline(matches, fixtures_df)


def _backtest_inline(matches: pd.DataFrame, min_history: int) -> Dict[str, float]:
    _import_modules()
    engine = PredictionEngine()
    bt = Backtester(engine)
    result = bt.run_rolling(matches, min_history=min_history)
    return result.metrics


def main() -> None:
    try:
        logger.info("Starting BetBot...")
        token = _get_telegram_token()
        logger.info("Telegram token loaded successfully")

        app = Application.builder().token(token).build()

        # Register commands
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("setleague", cmd_setleague))
        app.add_handler(CommandHandler("partido", cmd_predict))  # Changed from predict
        app.add_handler(CommandHandler("jornada", cmd_jornada))  # New command
        app.add_handler(CommandHandler("combinada", cmd_combinada))  # New command
        app.add_handler(CommandHandler("comparar_lineas", cmd_comparar_lineas))  # New command
        app.add_handler(CommandHandler("analyze_next", cmd_analyze_next))
        app.add_handler(CommandHandler("backtest", cmd_backtest))

        logger.info("🤖 BetBot iniciado. Esperando mensajes...")
        print("🤖 BetBot iniciado. Esperando mensajes...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error al iniciar el bot: {e}")
        raise


if __name__ == "__main__":
    main()
