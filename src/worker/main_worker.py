import logging
import os
from telegram.ext import ContextTypes
from src.scraper.scraper_365 import Scraper365
from src.analyzer.logic_tree import LogicTreeAnalyzer

logger = logging.getLogger(__name__)

async def scraping_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea de fondo que raspará 365scores, procesará con el 
    árbol de decisiones, y mandará notificación si hay valor.
    """
    logger.info("Iniciando ciclo de escaneo de 365scores...")
    scraper = Scraper365()
    analyzer = LogicTreeAnalyzer()
    
    try:
        # Extraer partidos en vivo
        live_games = await scraper.fetch_live_matches()
        if not live_games:
            logger.info("No hay partidos en curso o no se pudo extraer datos.")
            return

        # Analizar con Diagrama de Árbol (Reglas Condicionales)
        picks = analyzer.analyze_games(live_games)
        
        if not picks:
            logger.info("Escaneo terminado. No se detectaron apuestas de valor en este momento.")
            return

        # Hay picks ganadores. Notificamos a un chat ID configurado.
        # Por ahora enviamos a todos los posibles admin o logs
        # Se requiere configurar CHANNEL_ID en .env o notificar global
        dest_chat = os.getenv("TELEGRAM_CHANNEL_ID")
        
        for pick in picks:
            msg = (
                f"🚨 <b>¡NUEVA SEÑAL DETECTADA!</b> 🚨\n\n"
                f"⚽ <b>Partido:</b> {pick['match']}\n"
                f"⏱️ <b>Minuto:</b> {pick['minute']}'\n"
                f"🎯 <b>Mercado Recomendado:</b> {pick['market']}\n"
                f"💡 <b>Lógica:</b> {pick['reason']}\n"
                f"📊 <b>Confianza:</b> {pick['confidence']}%\n"
            )
            logger.info(f"Señal generada: {pick['market']}")
            
            if dest_chat:
                await context.bot.send_message(
                    chat_id=dest_chat, 
                    text=msg, 
                    parse_mode='HTML'
                )
    except Exception as e:
        logger.error(f"Error en el ciclo de escaneo: {e}")
    finally:
        await scraper.close()

def setup_worker(app) -> None:
    """Configura el loop asíncrono que corre de fondo."""
    job_queue = app.job_queue
    # Intervalo de 2 minutos (120 seg) - evita banneos rápidos de IP
    job_queue.run_repeating(scraping_job, interval=120, first=10)
    logger.info("Worker integrado: Scraping -> Analyzer -> Telegram configurado.")
