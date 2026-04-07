import logging
import os
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.analyzer.logic_tree import LogicTreeAnalyzer
from src.bot.subscribers import get_subscribers

logger = logging.getLogger(__name__)

def format_pick_message(pick: dict) -> str:
    """Formatea una señal al estilo Robot Millonario."""
    stake = 4 if pick["confidence"] >= 80 else 3 if pick["confidence"] >= 70 else 2

    msg = (
        f"🤖⚽🤖 <b>ROBOT APUESTA</b> ⚽🤖⚽\n\n"
        f"<b>{pick['match']}</b>\n\n"
        f"{pick['market']}\n\n"
        f"🏦 <b>CONFIANZA</b> 🏦 👉 {pick['confidence']}%\n\n"
        f"⏱️ Minuto: {pick['minute']}'\n"
        f"💡 {pick['reason']}\n\n"
        f"STAKE {stake}"
    )
    return msg

async def scraping_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea de fondo: raspa 365scores, analiza con árbol de decisiones
    y manda notificación a todos los suscriptores si hay valor.
    """
    logger.info("Iniciando ciclo de escaneo de 365scores...")
    scraper = Scraper365()
    analyzer = LogicTreeAnalyzer()

    try:
        # 1. Extraer partidos en vivo
        live_games = await scraper.fetch_live_matches()
        if not live_games:
            logger.info("No hay partidos en curso o no se pudo extraer datos.")
            return

        # 2. Analizar con Árbol de Decisiones
        picks = analyzer.analyze_games(live_games)

        if not picks:
            logger.info("Escaneo terminado. No se detectaron apuestas de valor.")
            return

        # 3. Notificar a todos los suscriptores
        subscribers = get_subscribers()
        if not subscribers:
            logger.warning("Hay señales pero no hay suscriptores registrados. Nadie recibirá notificaciones.")
            logger.info(f"Señales detectadas: {[p['market'] for p in picks]}")
            return

        logger.info(f"Se detectaron {len(picks)} señal(es). Enviando a {len(subscribers)} suscriptor(es)...")

        for pick in picks:
            msg = format_pick_message(pick)
            logger.info(f"Señal: {pick['match']} → {pick['market']}")

            for chat_id in subscribers:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error enviando a chat_id {chat_id}: {e}")

    except Exception as e:
        logger.error(f"Error en el ciclo de escaneo: {e}")
    finally:
        await scraper.close()

def setup_worker(app) -> None:
    """Configura el loop asíncrono que corre de fondo."""
    job_queue = app.job_queue
    # Intervalo de 2 minutos (120 seg) - evita límites de API
    job_queue.run_repeating(scraping_job, interval=120, first=10)
    logger.info("Worker configurado: Scraping → Analyzer → Telegram (todos los suscriptores).")
