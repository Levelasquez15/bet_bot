import logging
import os
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.analyzer.logic_tree import LogicTreeAnalyzer
from src.bot.subscribers import get_subscribers

logger = logging.getLogger(__name__)

# Evita enviar la misma señal dos veces en el mismo ciclo
_sent_picks: set = set()


def format_live_pick(pick: dict) -> str:
    """Formato estilo Robot Millonario para partidos EN VIVO."""
    stake = 4 if pick["confidence"] >= 80 else 3 if pick["confidence"] >= 73 else 2
    return (
        f"🤖⚽🤖 <b>ROBOT APUESTA</b> ⚽🤖⚽\n\n"
        f"<b>{pick['match']}</b>\n\n"
        f"{pick['market']}\n\n"
        f"🏦 <b>CONFIANZA</b> 🏦 👉 {pick['confidence']}%\n\n"
        f"⏱️ Minuto: {pick['minute']}'\n"
        f"💡 {pick['reason']}\n\n"
        f"STAKE {stake}"
    )


def format_upcoming_pick(pick: dict) -> str:
    """Formato para partidos PRÓXIMOS."""
    stake = 3 if pick["confidence"] >= 78 else 2
    return (
        f"📅⚽ <b>ANÁLISIS PRE-PARTIDO</b> ⚽📅\n\n"
        f"<b>{pick['match']}</b>\n"
        f"🕐 Inicio: {pick['minute']}\n\n"
        f"{pick['market']}\n\n"
        f"📊 <b>PROBABILIDAD</b> 📊 👉 {pick['confidence']}%\n"
        f"💡 {pick['reason']}\n\n"
        f"STAKE {stake}"
    )


async def _broadcast(context, picks: list, formatter) -> None:
    """Envía picks a todos los suscriptores evitando duplicados."""
    global _sent_picks
    subscribers = get_subscribers()

    if not subscribers:
        logger.warning(f"{len(picks)} señal(es) detectada(s) pero sin suscriptores.")
        return

    for pick in picks:
        pick_key = f"{pick['match']}|{pick['market']}"
        if pick_key in _sent_picks:
            logger.info(f"Señal duplicada ignorada: {pick_key}")
            continue

        msg = formatter(pick)
        sent_to = 0
        for chat_id in subscribers:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="HTML"
                )
                sent_to += 1
            except Exception as e:
                logger.error(f"Error enviando a {chat_id}: {e}")

        if sent_to > 0:
            _sent_picks.add(pick_key)
            logger.info(f"✅ Señal enviada a {sent_to} usuario(s): {pick['match']} → {pick['market']}")

    # Limpiar el historial cada 500 picks para no crecer indefinidamente
    if len(_sent_picks) > 500:
        _sent_picks.clear()


async def scraping_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea de fondo principal. Corre cada 2 minutos.
    1. Analiza partidos EN VIVO con árboles de decisión
    2. Analiza PRÓXIMOS partidos con modelo Poisson
    3. Envía notificaciones a todos los suscriptores
    """
    logger.info("━━━ Ciclo de escaneo iniciado ━━━")
    scraper = Scraper365()
    analyzer = LogicTreeAnalyzer()

    try:
        # ── En Vivo ────────────────────────────────────────────────────────
        live_games = await scraper.fetch_live_matches()
        if live_games:
            live_picks = analyzer.analyze_live(live_games)
            if live_picks:
                await _broadcast(context, live_picks, format_live_pick)
        else:
            logger.info("Sin partidos en vivo en este ciclo.")

        # ── Próximos (siguientes 3 horas) ──────────────────────────────────
        upcoming_games = await scraper.fetch_upcoming_matches(hours_ahead=3)
        if upcoming_games:
            upcoming_picks = analyzer.analyze_upcoming(upcoming_games)
            if upcoming_picks:
                await _broadcast(context, upcoming_picks, format_upcoming_pick)
        else:
            logger.info("Sin partidos próximos en las siguientes 3h.")

    except Exception as e:
        logger.error(f"Error crítico en scraping_job: {e}", exc_info=True)
    finally:
        await scraper.close()
        logger.info("━━━ Ciclo de escaneo completado ━━━")


def setup_worker(app) -> None:
    """Registra el job recurrente en el scheduler de PTB."""
    job_queue = app.job_queue
    job_queue.run_repeating(scraping_job, interval=120, first=15)
    logger.info("⚙️  Worker registrado: ciclo de 2 min (Live + Próximos).")
