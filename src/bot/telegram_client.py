import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje cuando se emite el comando /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"¡Hola {user.mention_html()}! Soy 365BetBot. 🤖"
        "\n\nMe encuentro analizando partidos de 365scores en segundo plano."
        "\nCuando detecte una apuesta de valor mediante mis árboles de decisión, te notificaré aquí."
        "\n\nUsa /status para ver el estado del motor de recolección."
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("✅ Motor de Scraping: ACTIVO\n✅ Motor de Análisis: ACTIVO")

def create_application() -> Application:
    """Inicializa la aplicación y registra los comandos."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No se encontró TELEGRAM_TOKEN en el entorno.")
        raise ValueError("No se encontró TELEGRAM_TOKEN en el entorno.")

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))

    return app
