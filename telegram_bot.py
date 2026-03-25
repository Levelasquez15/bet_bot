from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, date, timedelta, timezone
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
DEFAULT_SEASON = 2023  # Usar temporada con datos disponibles
MAX_FIXTURES_ANALYSIS = 12

# Mensajes completamente ASCII para evitar errores de parsing Markdown
MESSAGES = {
    'start': """*BetBot - Pronosticos Deportivos*

Hola! Soy tu asistente de pronosticos deportivos con IA.

*Comandos disponibles:*
/jornada - Analisis de partidos proximos (hoy y proximos dias)
/jornada_manana - Analisis especifico de manana
/jornada_pasado - Analisis especifico en 2 dias
/proximos - Ver lista completa de proximos partidos
/partido `Local` vs `Visitante` - Analisis especifico
/combinada - Generar combinada automatica
/comparar_lineas `Local` vs `Visitante` - Comparar cuotas
/notificaciones - Activar/desactivar alertas de oportunidades
/status - Estado del bot y configuracion
/setleague `id` `temporada` - Cambiar liga y temporada

*Para activar notificaciones de oportunidades:* Usa /notificaciones
*Configuracion actual:* Liga={league}, Temporada={season}
*Notificaciones:* {notifications}""",

    'status': """*Estado del Bot*

Configuracion:
- Liga: {league_id}
- Temporada: {season}
- API Football: {api_status}
- Token Telegram: {token_status}
- Notificaciones: {notifications}

Modelo listo para analisis""",

    'jornada_header': """*ANALISIS DE JORNADA - {date}*

*{count} partidos programados*
*Liga:* {league_name}
*Actualizado:* {time}

---------------""",

    'match_analysis': """*{home} vs {away}*
{time}

*Probabilidades del Modelo:*
- Local: {home_win:.1%}
- Empate: {draw:.1%}
- Visitante: {away_win:.1%}
- +2.5 Goles: {over:.1%}

*Fuerza de Ataque:*
- {home}: {lambda_home:.2f}
- {away}: {lambda_away:.2f}

*Recomendacion:* {recommendation}
---------------""",

    'top_picks': """*TOP PICKS RECOMENDADOS*

{matches_text}

*Recomendaciones basadas en modelo Poisson+Elo*
*Valor esperado minimo:* 3%""",

    'accumulator': """*COMBINADA SUGERIDA*

{legs} partidos combinados
Probabilidad total: {prob:.1%}
Cuota total: {odds:.2f}
Valor esperado: {ev:.1%}

*Recuerda:* Juego responsable""",

    'notification_alert': """*ALERTA DE OPORTUNIDAD!*

*{home} vs {away}*
{date}

*Pick recomendado:* {selection} ({market})
Probabilidad: {prob:.1%}
Cuota: {odds:.2f}
EV: {ev:.1%}

*Confianza:* {confidence}

*Actua rapido - las cuotas cambian*""",

    'no_matches': "No hay partidos programados para {date} en la liga configurada.",

    'analyzing': "Analizando {count} partidos de {date}...",

    'error_data': "Error obteniendo datos. Verifica la configuracion.",
    'error_analysis': "Error en el analisis. Intentelo de nuevo.",
    'processing': "Procesando...",

    'notifications_enabled': "*Notificaciones activadas*\n\nRecibiras alertas automaticas cuando el bot encuentre oportunidades de valor (EV >3% y prob >50%) durante los analisis de jornada.",
    'notifications_disabled': "*Notificaciones desactivadas*",

    'upcoming_matches_notification': """*PARTIDOS PROXIMOS - {date}*

*{count} partidos programados*

{matches_list}

*Usa /jornada para analisis completo*
*Usa /notificaciones para activar alertas de oportunidades*""",

    'invalid_format': "Formato invalido. Usa: {usage}",
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


def _get_notifications_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if notifications are enabled for this user."""
    return context.bot_data.get("notifications_enabled", False)


def _set_notifications_enabled(context: ContextTypes.DEFAULT_TYPE, enabled: bool):
    """Enable or disable notifications for this user."""
    context.bot_data["notifications_enabled"] = enabled


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
    try:
        logger.info("cmd_start called")
        league_id, season = _current_config(context)
        notifications_status = "✅ ACTIVADAS" if _get_notifications_enabled(context) else "❌ DESACTIVADAS"
        message = MESSAGES['start'].format(
            league=league_id,
            season=season,
            notifications=notifications_status
        )
        logger.info(f"Sending start message: {message[:100]}...")
        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info("Start message sent successfully")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = _current_config(context)
    has_api = bool(os.getenv("API_FOOTBALL_KEY", ""))
    has_token = bool(os.getenv("TELEGRAM_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", ""))
    notifications_status = "✅ ACTIVADAS" if _get_notifications_enabled(context) else "❌ DESACTIVADAS"

    message = MESSAGES['status'].format(
        league_id=league_id,
        season=season,
        api_status="✅ OK" if has_api else "❌ FALTA",
        token_status="✅ OK" if has_token else "❌ FALTA",
        notifications=notifications_status
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


async def _analyze_jornada_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE, days_ahead: int = 0):
    """Analyze matches for a specific date (today + days_ahead)."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Calculate target date
        target_date = date.today() + timedelta(days=days_ahead)
        date_str = target_date.strftime("%d/%m/%Y")

        # Get fixtures for target date
        source = ApiFootballDataSource(api_key=_get_api_key())
        all_fixtures = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 50)

        if all_fixtures.empty:
            await update.message.reply_text(MESSAGES['no_matches'].format(date=date_str))
            return

        # Filter for target date
        target_fixtures = all_fixtures[
            (all_fixtures['date'].dt.date == target_date)
        ]

        if target_fixtures.empty:
            await update.message.reply_text(MESSAGES['no_matches'].format(date=date_str))
            return

        count = len(target_fixtures)
        await update.message.reply_text(MESSAGES['analyzing'].format(count=count, date=date_str))

        # Analyze matches
        result = await asyncio.to_thread(_analyze_jornada_inline, matches, target_fixtures)

        # Send jornada header
        header = MESSAGES['jornada_header'].format(
            date=date_str,
            count=count,
            league_name=f"Liga {league_id}",
            time=datetime.now().strftime("%H:%M")
        )
        await update.message.reply_text(header, parse_mode='Markdown')

        # Send individual match analyses
        for _, fx in target_fixtures.iterrows():
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])

            try:
                probs = await asyncio.to_thread(_predict_match_inline, home, away, matches)
                recommendation = _get_recommendation(probs)

                match_msg = MESSAGES['match_analysis'].format(
                    home=home,
                    away=away,
                    time=target_date.strftime("%H:%M") if fx.get("time") else "TBD",
                    venue="Estadio",
                    home_win=probs['home_win'],
                    draw=probs['draw'],
                    away_win=probs['away_win'],
                    over=probs['over_2_5'],
                    lambda_home=probs['lambda_home'],
                    lambda_away=probs['lambda_away'],
                    recommendation=recommendation
                )
                await update.message.reply_text(match_msg, parse_mode='Markdown')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

        # Send top picks if available
        if result['picks'] and not result['picks'].empty:
            picks_text = []
            for _, row in result['picks'].head(6).iterrows():
                picks_text.append(
                    f"• {row['match']} | {row['selection']} ({row['market']}) | "
                    f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
                )

            message = MESSAGES['top_picks'].format(matches_text="\n".join(picks_text))
            await update.message.reply_text(message, parse_mode='Markdown')

            # Send accumulator if available
            if result['acc']:
                acc_msg = MESSAGES['accumulator'].format(
                    legs=int(result['acc']['legs']),
                    prob=result['acc']['combined_probability'],
                    odds=result['acc']['combined_odds'],
                    ev=result['acc']['combined_expected_value']
                )
                await update.message.reply_text(acc_msg, parse_mode='Markdown')

            # Check for notification-worthy picks
            await _check_and_send_notifications(update, context, result['picks'])

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada: {str(exc)}")


async def cmd_jornada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze upcoming matches (next 12 matches)."""
    await _analyze_upcoming_matches(update, context, max_matches=12)


async def cmd_jornada_manana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze tomorrow's matches."""
    await update.message.reply_text("🔍 Buscando partidos de mañana...")

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get tomorrow's fixtures
        tomorrow = date.today() + timedelta(days=1)
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 50)

        if fixtures_df.empty:
            await update.message.reply_text(f"📅 No hay partidos programados para mañana ({tomorrow.strftime('%d/%m/%Y')}).")
            return

        # Filter for tomorrow
        fixtures_df['date_only'] = fixtures_df['date'].dt.date
        tomorrow_fixtures = fixtures_df[fixtures_df['date_only'] == tomorrow]

        if tomorrow_fixtures.empty:
            await update.message.reply_text(f"📅 No hay partidos programados para mañana ({tomorrow.strftime('%d/%m/%Y')}).")
            return

        count = len(tomorrow_fixtures)
        await update.message.reply_text(f"🔍 Analizando {count} partidos de mañana...")

        # Analyze matches
        result = await asyncio.to_thread(_analyze_jornada_inline, matches, tomorrow_fixtures)

        # Send jornada header
        header = f"""🏆 *ANÁLISIS DE MAÑANA - {tomorrow.strftime('%d/%m/%Y')}*

📊 *{count} partidos programados*
⚽ *Liga:* {league_id}
⏰ *Actualizado:* {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='Markdown')

        # Send individual match analyses
        for i, (_, fx) in enumerate(tomorrow_fixtures.iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_time = fx['date'].strftime("%H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(_predict_match_inline, home, away, matches)
                recommendation = _get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_time}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='Markdown')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada de mañana: {str(exc)}")


async def cmd_jornada_pasado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze matches in 2 days."""
    await update.message.reply_text("🔍 Buscando partidos en 2 días...")

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get fixtures in 2 days
        target_date = date.today() + timedelta(days=2)
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 50)

        if fixtures_df.empty:
            await update.message.reply_text(f"📅 No hay partidos programados para {target_date.strftime('%d/%m/%Y')}.")
            return

        # Filter for target date
        fixtures_df['date_only'] = fixtures_df['date'].dt.date
        target_fixtures = fixtures_df[fixtures_df['date_only'] == target_date]

        if target_fixtures.empty:
            await update.message.reply_text(f"📅 No hay partidos programados para {target_date.strftime('%d/%m/%Y')}.")
            return

        count = len(target_fixtures)
        await update.message.reply_text(f"🔍 Analizando {count} partidos en 2 días...")

        # Analyze matches
        result = await asyncio.to_thread(_analyze_jornada_inline, matches, target_fixtures)

        # Send jornada header
        header = f"""🏆 *ANÁLISIS EN 2 DÍAS - {target_date.strftime('%d/%m/%Y')}*

📊 *{count} partidos programados*
⚽ *Liga:* {league_id}
⏰ *Actualizado:* {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='Markdown')

        # Send individual match analyses
        for i, (_, fx) in enumerate(target_fixtures.iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_time = fx['date'].strftime("%H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(_predict_match_inline, home, away, matches)
                recommendation = _get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_time}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='Markdown')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada en 2 días: {str(exc)}")


async def cmd_proximos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of upcoming matches."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = _current_config(context)

        # Get upcoming fixtures
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 20)

        if fixtures_df.empty:
            await update.message.reply_text("📅 No hay partidos próximos programados.")
            return

        # Group by date
        fixtures_df['date_only'] = fixtures_df['date'].dt.date
        grouped = fixtures_df.groupby('date_only')

        lines = [f"📅 *Próximos partidos - Liga {league_id}*\n"]

        for date_key, group in grouped:
            date_str = date_key.strftime("%d/%m/%Y")
            day_name = date_key.strftime("%A")

            lines.append(f"🗓️ *{day_name} {date_str}*")
            for _, match in group.iterrows():
                home = str(match['home_team'])
                away = str(match['away_team'])
                time_str = match['date'].strftime("%H:%M") if pd.notna(match['date']) else "TBD"
                lines.append(f"  ⚽ {time_str} - {home} vs {away}")
            lines.append("")

        message = "\n".join(lines)
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error obteniendo próximos partidos: {str(exc)}")


async def _analyze_upcoming_matches(update: Update, context: ContextTypes.DEFAULT_TYPE, max_matches: int = 12):
    """Analyze upcoming matches."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = _current_config(context)
        matches = await _load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get upcoming fixtures
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, max_matches)

        if fixtures_df.empty:
            await update.message.reply_text("📅 No hay partidos próximos programados.")
            return

        count = len(fixtures_df)
        await update.message.reply_text(f"🔍 Analizando {count} próximos partidos...")

        # Analyze matches
        result = await asyncio.to_thread(_analyze_jornada_inline, matches, fixtures_df)

        # Send jornada header
        header = f"""🏆 *ANÁLISIS DE PRÓXIMOS PARTIDOS*

📊 *{count} partidos programados*
⚽ *Liga:* {league_id}
⏰ *Actualizado:* {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='Markdown')

        # Send individual match analyses (limit to first 8 for readability)
        for i, (_, fx) in enumerate(fixtures_df.head(8).iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_date = fx['date'].strftime("%d/%m %H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(_predict_match_inline, home, away, matches)
                recommendation = _get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_date}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='Markdown')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

        # Send top picks if available
        if result['picks'] and not result['picks'].empty:
            picks_text = []
            for _, row in result['picks'].head(6).iterrows():
                picks_text.append(
                    f"• {row['match']} | {row['selection']} ({row['market']}) | "
                    f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
                )

            message = MESSAGES['top_picks'].format(matches_text="\n".join(picks_text))
            await update.message.reply_text(message, parse_mode='Markdown')

            # Send accumulator if available
            if result['acc']:
                acc_msg = MESSAGES['accumulator'].format(
                    legs=int(result['acc']['legs']),
                    prob=result['acc']['combined_probability'],
                    odds=result['acc']['combined_odds'],
                    ev=result['acc']['combined_expected_value']
                )
                await update.message.reply_text(acc_msg, parse_mode='Markdown')

            # Check for notification-worthy picks
            await _check_and_send_notifications(update, context, result['picks'])

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando próximos partidos: {str(exc)}")


async def _check_and_send_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE, picks_df):
    """Check for high-value picks and send notifications if enabled."""
    if not _get_notifications_enabled(context):
        return

    # Look for picks with EV > 3% and probability > 50% (less restrictive)
    notification_picks = picks_df[
        (picks_df['expected_value'] > 0.03) &
        (picks_df['probability'] > 0.50)
    ]

    if notification_picks.empty:
        return

    # Send notification for the best pick
    best_pick = notification_picks.loc[notification_picks['expected_value'].idxmax()]

    confidence = "Alta" if best_pick['probability'] > 0.65 else "Media"

    alert_msg = MESSAGES['notification_alert'].format(
        home=best_pick['match'].split(' vs ')[0],
        away=best_pick['match'].split(' vs ')[1],
        date=datetime.now().strftime("%d/%m/%Y"),
        selection=best_pick['selection'],
        market=best_pick['market'],
        prob=best_pick['probability'],
        odds=best_pick['odds'],
        ev=best_pick['expected_value'],
        confidence=confidence
    )

    try:
        await update.message.reply_text(alert_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending notification: {e}")


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


async def cmd_notificaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notifications on/off."""
    currently_enabled = _get_notifications_enabled(context)
    new_state = not currently_enabled
    _set_notifications_enabled(context, new_state)

    if new_state:
        message = MESSAGES['notifications_enabled']
        # Send upcoming matches notification immediately when enabled
        try:
            await _send_upcoming_matches_notification(update, context)
        except Exception as e:
            logger.error(f"Error sending initial notification: {e}")
    else:
        message = MESSAGES['notifications_disabled']

    await update.message.reply_text(message, parse_mode='Markdown')


async def _send_upcoming_matches_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a professional notification about upcoming matches."""
    try:
        league_id, season = _current_config(context)

        # Get upcoming fixtures (next 7 days)
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = await asyncio.to_thread(source.get_upcoming_fixtures, league_id, season, 30)

        if fixtures_df.empty:
            return

        # Group by date and get next 3 days
        fixtures_df['date_only'] = fixtures_df['date'].dt.date
        today = date.today()

        upcoming_dates = []
        for i in range(7):  # Next 7 days
            check_date = today + timedelta(days=i)
            day_fixtures = fixtures_df[fixtures_df['date_only'] == check_date]
            if not day_fixtures.empty:
                upcoming_dates.append((check_date, day_fixtures))
                if len(upcoming_dates) >= 3:  # Limit to 3 days
                    break

        if not upcoming_dates:
            return

        # Build notification message
        lines = []
        total_matches = 0

        for check_date, day_fixtures in upcoming_dates:
            date_str = check_date.strftime("%d/%m")
            day_name = check_date.strftime("%A")

            # Translate day names to Spanish
            day_translations = {
                "Monday": "Lunes",
                "Tuesday": "Martes",
                "Wednesday": "Miércoles",
                "Thursday": "Jueves",
                "Friday": "Viernes",
                "Saturday": "Sábado",
                "Sunday": "Domingo"
            }
            day_name_es = day_translations.get(day_name, day_name)

            lines.append(f"📅 *{day_name_es} {date_str}*")

            for _, match in day_fixtures.iterrows():
                home = str(match['home_team'])
                away = str(match['away_team'])
                time_str = match['date'].strftime("%H:%M") if pd.notna(match['date']) else "TBD"
                lines.append(f"  ⚽ {time_str} - {home} vs {away}")
                total_matches += 1

            lines.append("")

        if total_matches > 0:
            notification_msg = MESSAGES['upcoming_matches_notification'].format(
                date=today.strftime("%d/%m/%Y"),
                count=total_matches,
                matches_list="\n".join(lines)
            )
            await update.message.reply_text(notification_msg, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error sending upcoming matches notification: {e}")


async def cmd_comparar_lineas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compare betting lines for a specific match."""
    raw = " ".join(context.args).strip()
    if not raw or ("|" not in raw and "vs" not in raw.lower()):
        await update.message.reply_text("Uso: /comparar_lineas `<Local>` vs `<Visitante>`\nEjemplo: /comparar_lineas Real Madrid vs Barcelona", parse_mode='Markdown')
        return

    # Parse different formats: "Local | Visitante" or "Local vs Visitante"
    if "|" in raw:
        home_team, away_team = [p.strip() for p in raw.split("|", maxsplit=1)]
    else:
        parts = raw.lower().split("vs")
        if len(parts) != 2:
            await update.message.reply_text("Formato inválido. Usa: /comparar_lineas Real Madrid vs Barcelona", parse_mode='Markdown')
            return
        home_team, away_team = [p.strip() for p in parts]

    if not home_team or not away_team:
        await update.message.reply_text("Equipos inválidos. Ejemplo: /comparar_lineas Real Madrid vs Barcelona", parse_mode='Markdown')
        return

    await update.message.reply_text("🔍 Comparando líneas de apuestas...")

    try:
        matches = await _load_history(context)
        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get league config
        league_id, season = _current_config(context)

        # Find fixture
        _import_modules()
        source = ApiFootballDataSource(api_key=_get_api_key())
        fixtures_df = source.get_upcoming_fixtures(league_id=league_id, season=season, next_n=20)

        # Find matching fixture
        fixture_row = None
        for _, fx in fixtures_df.iterrows():
            if (str(fx['home_team']).lower().strip() == home_team.lower().strip() and
                str(fx['away_team']).lower().strip() == away_team.lower().strip()):
                fixture_row = fx
                break

        if fixture_row is None:
            await update.message.reply_text(f"❌ No se encontró el partido: {home_team} vs {away_team}")
            return

        fixture_id = int(fixture_row['fixture_id'])
        fixture_date = pd.to_datetime(fixture_row['fixture_date']).strftime("%d/%m/%Y %H:%M")

        # Get odds and compare lines
        odds_df = source.get_odds_for_fixture(fixture_id)
        if odds_df.empty:
            await update.message.reply_text("❌ No hay cuotas disponibles para este partido")
            return

        # Get model prediction
        probs = await asyncio.to_thread(_predict_match_inline, home_team, away_team, matches)

        # Compare lines
        recommender = BettingRecommender()
        compared_df = recommender.compare_lines(fixture_id, home_team, away_team, probs, odds_df)

        if compared_df.empty:
            await update.message.reply_text("❌ No se pudieron comparar las líneas")
            return

        # Format results
        lines = [f"🏆 *Comparación de líneas: {home_team} vs {away_team}*"]
        lines.append(f"📅 Fecha: {fixture_date}")
        lines.append("")

        # Group by bet type
        for bet_type in compared_df['bet_type'].unique():
            type_df = compared_df[compared_df['bet_type'] == bet_type]
            if not type_df.empty:
                best_row = type_df.loc[type_df['expected_value'].idxmax()]
                lines.append(f"🎯 *{bet_type}*")
                lines.append(f"  📊 Prob. modelo: {best_row['model_prob']:.1%}")
                lines.append(f"  💰 Mejor cuota: {best_row['best_odds']:.2f}")
                lines.append(f"  📈 EV: {best_row['expected_value']:.1%}")
                lines.append(f"  🏦 Casa: {best_row['bookmaker']}")
                lines.append("")

        message = "\n".join(lines)
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error comparando líneas: {str(exc)}")


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
        logger.info("Application created successfully")

        # Register commands
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("setleague", cmd_setleague))
        app.add_handler(CommandHandler("partido", cmd_predict))  # Changed from predict
        app.add_handler(CommandHandler("jornada", cmd_jornada))  # Próximos partidos
        app.add_handler(CommandHandler("jornada_manana", cmd_jornada_manana))  # Tomorrow's matches
        app.add_handler(CommandHandler("jornada_pasado", cmd_jornada_pasado))  # Matches in 2 days
        app.add_handler(CommandHandler("proximos", cmd_proximos))  # Lista de próximos partidos
        app.add_handler(CommandHandler("combinada", cmd_combinada))  # Accumulator
        app.add_handler(CommandHandler("notificaciones", cmd_notificaciones))  # Notifications toggle
        app.add_handler(CommandHandler("comparar_lineas", cmd_comparar_lineas))  # Line comparison
        app.add_handler(CommandHandler("analyze_next", cmd_analyze_next))
        app.add_handler(CommandHandler("backtest", cmd_backtest))
        logger.info("All commands registered successfully")

        logger.info("🤖 BetBot iniciado. Esperando mensajes...")
        print("🤖 BetBot iniciado. Esperando mensajes...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error al iniciar el bot: {e}")
        raise


if __name__ == "__main__":
    main()
