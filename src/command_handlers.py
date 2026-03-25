from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Dict

import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes

from .api_client import load_history, get_upcoming_fixtures, get_odds_for_fixture, get_betting_recommendations
from .config import MESSAGES, current_config, get_notifications_enabled, set_notifications_enabled, get_api_key, get_telegram_token
from .prediction_service import predict_match_inline, get_recommendation, analyze_jornada_inline, build_accumulator_inline, backtest_inline

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        logger.info("cmd_start called")
        league_id, season = current_config(context)
        notifications_status = "✅ ACTIVADAS" if get_notifications_enabled(context) else "❌ DESACTIVADAS"
        message = MESSAGES['start'].format(
            league=league_id,
            season=season,
            notifications=notifications_status
        )
        logger.info(f"Sending start message: {message[:100]}...")
        await update.message.reply_text(message, parse_mode='HTML')
        logger.info("Start message sent successfully")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    league_id, season = current_config(context)
    has_api = bool(get_api_key())
    has_token = bool(get_telegram_token())
    notifications_status = "✅ ACTIVADAS" if get_notifications_enabled(context) else "❌ DESACTIVADAS"

    message = MESSAGES['status'].format(
        league_id=league_id,
        season=season,
        api_status="✅ OK" if has_api else "❌ FALTA",
        token_status="✅ OK" if has_token else "❌ FALTA",
        notifications=notifications_status
    )
    await update.message.reply_text(message, parse_mode='HTML')


async def cmd_setleague(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /setleague <league_id> <season>", parse_mode='HTML')
        return

    try:
        league_id = int(context.args[0])
        season = int(context.args[1])
    except ValueError:
        await update.message.reply_text("league_id y season deben ser números", parse_mode='HTML')
        return

    context.bot_data["league_id"] = league_id
    context.bot_data["season"] = season
    await update.message.reply_text(f"✅ Configurado: Liga={league_id}, Temporada={season}", parse_mode='HTML')


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = " ".join(context.args).strip()
    if "|" not in raw and "vs" not in raw.lower():
        await update.message.reply_text("Uso: /partido `<Local>` vs `<Visitante>`\nEjemplo: /partido Real Madrid vs Barcelona", parse_mode='HTML')
        return

    # Parse different formats: "Local | Visitante" or "Local vs Visitante"
    if "|" in raw:
        home_team, away_team = [p.strip() for p in raw.split("|", maxsplit=1)]
    else:
        parts = raw.lower().split("vs")
        if len(parts) != 2:
            await update.message.reply_text("Formato inválido. Usa: /partido Real Madrid vs Barcelona", parse_mode='HTML')
            return
        home_team, away_team = [p.strip() for p in parts]

    if not home_team or not away_team:
        await update.message.reply_text("Equipos inválidos. Ejemplo: /partido Real Madrid vs Barcelona", parse_mode='HTML')
        return

    await update.message.reply_text(MESSAGES['processing'])

    try:
        matches = await load_history(context)
        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        probs = await asyncio.to_thread(predict_match_inline, home_team, away_team, matches)
        recommendation = get_recommendation(probs)

        # Get league info
        league_id, season = current_config(context)
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

        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {str(exc)}")


async def _analyze_jornada_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE, days_ahead: int = 0):
    """Analyze matches for a specific date (today + days_ahead)."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Calculate target date
        target_date = date.today() + timedelta(days=days_ahead)
        date_str = target_date.strftime("%d/%m/%Y")

        # Get fixtures for target date
        all_fixtures = await get_upcoming_fixtures(league_id, season, 50)

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
        result = await asyncio.to_thread(analyze_jornada_inline, matches, target_fixtures)

        # Send jornada header
        header = MESSAGES['jornada_header'].format(
            date=date_str,
            count=count,
            league_name=f"Liga {league_id}",
            time=datetime.now().strftime("%H:%M")
        )
        await update.message.reply_text(header, parse_mode='HTML')

        # Send individual match analyses
        for _, fx in target_fixtures.iterrows():
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])

            try:
                probs = await asyncio.to_thread(predict_match_inline, home, away, matches)
                recommendation = get_recommendation(probs)

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
                await update.message.reply_text(match_msg, parse_mode='HTML')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

        # Send top picks if available
        if result['picks'] and not result['picks'].empty:
            picks_text = []
            for _, row in result['picks'].head(6).iterrows():
                picks_text.append(
                    f"• {row['match']} | {row['selection']} \\({row['market']}\\) | "
                    f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
                )

            message = MESSAGES['top_picks'].format(matches_text="\n".join(picks_text))
            await update.message.reply_text(message, parse_mode='HTML')

            # Send accumulator if available
            if result['acc']:
                acc_msg = MESSAGES['accumulator'].format(
                    legs=int(result['acc']['legs']),
                    prob=result['acc']['combined_probability'],
                    odds=result['acc']['combined_odds'],
                    ev=result['acc']['combined_expected_value']
                )
                await update.message.reply_text(acc_msg, parse_mode='HTML')

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
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get tomorrow's fixtures
        tomorrow = date.today() + timedelta(days=1)
        fixtures_df = await get_upcoming_fixtures(league_id, season, 50)

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
        result = await asyncio.to_thread(analyze_jornada_inline, matches, tomorrow_fixtures)

        # Send jornada header
        header = f"""🏆 <b>ANÁLISIS DE MAÑANA - {tomorrow.strftime('%d/%m/%Y')}</b>

📊 <b>{count} partidos programados</b>
⚽ <b>Liga:</b> {league_id}
⏰ <b>Actualizado:</b> {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='HTML')

        # Send individual match analyses
        for i, (_, fx) in enumerate(tomorrow_fixtures.iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_time = fx['date'].strftime("%H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(predict_match_inline, home, away, matches)
                recommendation = get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_time}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='HTML')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada de mañana: {str(exc)}")


async def cmd_jornada_pasado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Analyze matches in 2 days."""
    await update.message.reply_text("🔍 Buscando partidos en 2 días...")

    try:
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get fixtures in 2 days
        target_date = date.today() + timedelta(days=2)
        fixtures_df = await get_upcoming_fixtures(league_id, season, 50)

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
        result = await asyncio.to_thread(analyze_jornada_inline, matches, target_fixtures)

        # Send jornada header
        header = f"""🏆 <b>ANÁLISIS EN 2 DÍAS - {target_date.strftime('%d/%m/%Y')}</b>

📊 <b>{count} partidos programados</b>
⚽ <b>Liga:</b> {league_id}
⏰ <b>Actualizado:</b> {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='HTML')

        # Send individual match analyses
        for i, (_, fx) in enumerate(target_fixtures.iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_time = fx['date'].strftime("%H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(predict_match_inline, home, away, matches)
                recommendation = get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_time}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='HTML')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando jornada en 2 días: {str(exc)}")


async def cmd_proximos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of upcoming matches."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = current_config(context)

        # Get upcoming fixtures
        fixtures_df = await get_upcoming_fixtures(league_id, season, 20)

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
        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error obteniendo próximos partidos: {str(exc)}")


async def _analyze_upcoming_matches(update: Update, context: ContextTypes.DEFAULT_TYPE, max_matches: int = 12):
    """Analyze upcoming matches."""
    await update.message.reply_text(MESSAGES['processing'])

    try:
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get upcoming fixtures
        fixtures_df = await get_upcoming_fixtures(league_id, season, max_matches)

        if fixtures_df.empty:
            await update.message.reply_text("📅 No hay partidos próximos programados.")
            return

        count = len(fixtures_df)
        await update.message.reply_text(f"🔍 Analizando {count} próximos partidos...")

        # Analyze matches
        result = await asyncio.to_thread(analyze_jornada_inline, matches, fixtures_df)

        # Send jornada header
        header = f"""🏆 <b>ANÁLISIS DE PRÓXIMOS PARTIDOS</b>

📊 <b>{count} partidos programados</b>
⚽ <b>Liga:</b> {league_id}
⏰ <b>Actualizado:</b> {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='HTML')

        # Send individual match analyses (limit to first 8 for readability)
        for i, (_, fx) in enumerate(fixtures_df.head(8).iterrows()):
            fixture_id = int(fx["fixture_id"])
            home = str(fx["home_team"])
            away = str(fx["away_team"])
            match_date = fx['date'].strftime("%d/%m %H:%M") if pd.notna(fx['date']) else "TBD"

            try:
                probs = await asyncio.to_thread(predict_match_inline, home, away, matches)
                recommendation = get_recommendation(probs)

                match_msg = f"""⚽ *{home} vs {away}*
🕐 {match_date}

🎲 *Probabilidades del Modelo:*
• 1️⃣ Local: {probs['home_win']:.1%}
• ❌ Empate: {probs['draw']:.1%}
• 2️⃣ Visitante: {probs['away_win']:.1%}
• ➕ +2.5 Goles: {probs['over_2_5']:.1%}

💡 *Recomendación:* {recommendation}
───────────────"""
                await update.message.reply_text(match_msg, parse_mode='HTML')

            except Exception as e:
                logger.error(f"Error analyzing match {home} vs {away}: {e}")
                continue

        # Send top picks if available
        if result['picks'] and not result['picks'].empty:
            picks_text = []
            for _, row in result['picks'].head(6).iterrows():
                picks_text.append(
                    f"• {row['match']} | {row['selection']} \\({row['market']}\\) | "
                    f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
                )

            message = MESSAGES['top_picks'].format(matches_text="\n".join(picks_text))
            await update.message.reply_text(message, parse_mode='HTML')

            # Send accumulator if available
            if result['acc']:
                acc_msg = MESSAGES['accumulator'].format(
                    legs=int(result['acc']['legs']),
                    prob=result['acc']['combined_probability'],
                    odds=result['acc']['combined_odds'],
                    ev=result['acc']['combined_expected_value']
                )
                await update.message.reply_text(acc_msg, parse_mode='HTML')

            # Check for notification-worthy picks
            await _check_and_send_notifications(update, context, result['picks'])

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando próximos partidos: {str(exc)}")


async def _check_and_send_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE, picks_df):
    """Check for high-value picks and send notifications if enabled."""
    if not get_notifications_enabled(context):
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
        await update.message.reply_text(alert_msg, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending notification: {e}")


async def cmd_combinada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate accumulator with specified number of legs."""
    if not context.args:
        await update.message.reply_text(MESSAGES['accumulator_options'], parse_mode='HTML')
        return

    try:
        legs = int(context.args[0])
        if legs not in [3, 5, 10]:
            await update.message.reply_text("Número de cuotas debe ser 3, 5 o 10", parse_mode='HTML')
            return
    except ValueError:
        await update.message.reply_text("Uso: /combinada <número>\nEjemplo: /combinada 3", parse_mode='HTML')
        return

    await update.message.reply_text(f"🎰 Generando combinada de {legs} cuotas...")

    try:
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get upcoming fixtures
        fixtures_df = await get_upcoming_fixtures(league_id, season, 20)

        if fixtures_df.empty:
            await update.message.reply_text("No hay partidos próximos para generar combinada")
            return

        # Analyze and build accumulator
        result = await asyncio.to_thread(build_accumulator_inline, matches, fixtures_df, legs)

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

        await update.message.reply_text("\n".join(details), parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error generando combinada: {str(exc)}")


async def cmd_notificaciones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notifications on/off."""
    currently_enabled = get_notifications_enabled(context)
    new_state = not currently_enabled
    set_notifications_enabled(context, new_state)

    if new_state:
        message = MESSAGES['notifications_enabled']
        # Send upcoming matches notification immediately when enabled
        try:
            await _send_upcoming_matches_notification(update, context)
        except Exception as e:
            logger.error(f"Error sending initial notification: {e}")
    else:
        message = MESSAGES['notifications_disabled']

    await update.message.reply_text(message, parse_mode='HTML')


async def _send_upcoming_matches_notification(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a professional notification about upcoming matches."""
    try:
        league_id, season = current_config(context)

        # Get upcoming fixtures (next 7 days)
        fixtures_df = await get_upcoming_fixtures(league_id, season, 30)

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
            await update.message.reply_text(notification_msg, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error sending upcoming matches notification: {e}")


async def cmd_comparar_lineas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Compare betting lines for a specific match."""
    raw = " ".join(context.args).strip()
    if not raw or ("|" not in raw and "vs" not in raw.lower()):
        await update.message.reply_text("Uso: /comparar_lineas `<Local>` vs `<Visitante>`\nEjemplo: /comparar_lineas Real Madrid vs Barcelona", parse_mode='HTML')
        return

    # Parse different formats: "Local | Visitante" or "Local vs Visitante"
    if "|" in raw:
        home_team, away_team = [p.strip() for p in raw.split("|", maxsplit=1)]
    else:
        parts = raw.lower().split("vs")
        if len(parts) != 2:
            await update.message.reply_text("Formato inválido. Usa: /comparar_lineas Real Madrid vs Barcelona", parse_mode='HTML')
            return
        home_team, away_team = [p.strip() for p in parts]

    if not home_team or not away_team:
        await update.message.reply_text("Equipos inválidos. Ejemplo: /comparar_lineas Real Madrid vs Barcelona", parse_mode='HTML')
        return

    await update.message.reply_text("🔍 Comparando líneas de apuestas...")

    try:
        matches = await load_history(context)
        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        # Get league config
        league_id, season = current_config(context)

        # Find fixture
        from .data_sources import ApiFootballDataSource
        source = ApiFootballDataSource(api_key=get_api_key())
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
        odds_df = get_odds_for_fixture(fixture_id)
        if odds_df.empty:
            await update.message.reply_text("❌ No hay cuotas disponibles para este partido")
            return

        # Get model prediction
        probs = await asyncio.to_thread(predict_match_inline, home_team, away_team, matches)

        # Compare lines
        from .recommender import BettingRecommender
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
        await update.message.reply_text(message, parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error comparando líneas: {str(exc)}")


async def cmd_analyze_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        n = int(context.args[0]) if context.args else 6
    except ValueError:
        await update.message.reply_text("Uso: /analyze_next [n]", parse_mode='HTML')
        return

    n = max(2, min(n, 12))

    await update.message.reply_text(f"🔍 Analizando próximos {n} partidos...")

    try:
        league_id, season = current_config(context)
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        fixtures_df = await get_upcoming_fixtures(league_id, season, n)
        result = await asyncio.to_thread(analyze_jornada_inline, matches, fixtures_df)

        picks_df = result.get("picks")
        acc = result.get("acc")

        if picks_df is None or picks_df.empty:
            await update.message.reply_text("No encontré picks que cumplan los filtros (prob≥55% y EV≥3%).")
            return

        lines = ["🎯 *Top picks por partido:*"]
        for _, row in picks_df.head(8).iterrows():
            lines.append(
                f"• {row['match']} | {row['selection']} \\({row['market']}\\) | "
                f"P={row['probability']:.1%} | Cuota={row['odds']:.2f} | EV={row['expected_value']:.1%}"
            )

        if acc:
            lines.append("")
            lines.append("🎰 *Combinada sugerida:*")
            lines.append(f"• Piernas: {int(acc['legs'])}")
            lines.append(f"• Probabilidad: {acc['combined_probability']:.2%}")
            lines.append(f"• Cuota: {acc['combined_odds']:.2f}")
            lines.append(f"• EV: {acc['combined_expected_value']:.2%}")

        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error analizando próximos partidos: {str(exc)}")


async def cmd_backtest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        min_history = int(context.args[0]) if context.args else 120
    except ValueError:
        await update.message.reply_text("Uso: /backtest [min_history]", parse_mode='HTML')
        return

    min_history = max(20, min_history)

    await update.message.reply_text("📊 Validando rendimiento del modelo...")

    try:
        matches = await load_history(context)

        if matches.empty:
            await update.message.reply_text(MESSAGES['error_data'])
            return

        metrics = await asyncio.to_thread(backtest_inline, matches, min_history)

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
        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as exc:
        await update.message.reply_text(f"❌ Error en validación: {str(exc)}")


async def cmd_apuestas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get betting recommendations for upcoming matches."""
    try:
        # Get league from context or use default
        league_id, season = current_config(context)

        # Map league_id to league name for the new scraper
        league_mapping = {
            39: 'Premier League',
            140: 'La Liga',
            135: 'Serie A',
            78: 'Bundesliga',
            61: 'Ligue 1'
        }

        league_name = league_mapping.get(league_id, 'Premier League')
        num_matches = 5  # Default number of matches to analyze

        if context.args:
            try:
                num_matches = int(context.args[0])
                num_matches = max(1, min(num_matches, 10))  # Limit between 1-10
            except ValueError:
                pass

        await update.message.reply_text(f"🎯 Generando recomendaciones de apuestas para {league_name}...")

        recommendations = await get_betting_recommendations(league_name, num_matches)

        if recommendations.empty:
            await update.message.reply_text("❌ No se pudieron generar recomendaciones de apuestas.")
            return

        # Send header
        header = f"""🎯 <b>RECOMENDACIONES DE APUESTAS</b>

⚽ <b>Liga:</b> {league_name}
📊 <b>Partidos analizados:</b> {len(recommendations)}
⏰ <b>Actualizado:</b> {datetime.now().strftime("%H:%M")}

───────────────"""
        await update.message.reply_text(header, parse_mode='HTML')

        # Send individual recommendations
        for i, (_, rec) in enumerate(recommendations.iterrows()):
            match_date = rec['date'].strftime("%d/%m %H:%M") if pd.notna(rec['date']) else "TBD"

            rec_msg = f"""⚽ <b>{rec['home_team']} vs {rec['away_team']}</b>
🕐 {match_date}

💡 <b>Recomendación:</b> {rec['recommendation']}
📊 <b>Probabilidad:</b> {rec['probability']}%
🎯 <b>Confianza:</b> {rec['confidence']}%
💰 <b>Cuota sugerida:</b> {rec['suggested_odds']:.2f}

📝 <b>Análisis:</b> {rec['reasoning']}
───────────────"""

            await update.message.reply_text(rec_msg, parse_mode='HTML')

            # Limit to first 5 recommendations for readability
            if i >= 4:
                break

        # Send summary
        total_confidence = recommendations['confidence'].mean()
        best_pick = recommendations.loc[recommendations['confidence'].idxmax()]

        summary = f"""📊 <b>RESUMEN</b>

🎯 <b>Mejor apuesta:</b> {best_pick['home_team']} vs {best_pick['away_team']}
💡 <b>Recomendación:</b> {best_pick['recommendation']}
🎯 <b>Confianza:</b> {best_pick['confidence']}%

📈 <b>Confianza promedio:</b> {total_confidence:.1f}%
⚽ <b>Total partidos:</b> {len(recommendations)}"""

        await update.message.reply_text(summary, parse_mode='HTML')

    except Exception as exc:
        logger.error(f"Error in cmd_apuestas: {exc}")
        await update.message.reply_text(f"❌ Error generando recomendaciones: {str(exc)}")