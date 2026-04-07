import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.bot.subscribers import add_subscriber, get_subscribers

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra al usuario y le da la bienvenida."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    is_new = add_subscriber(chat_id)

    if is_new:
        logger.info(f"Nuevo suscriptor registrado: {chat_id} ({user.full_name})")
        await update.message.reply_html(
            rf"¡Hola {user.mention_html()}! Soy 365BetBot. 🤖"
            "\n\n✅ <b>Te has registrado con éxito.</b>"
            "\nA partir de ahora recibirás alertas de apuestas de valor directamente aquí cuando detecte una señal en vivo."
            "\n\nUsa /status para ver el estado del motor de recolección."
        )
    else:
        await update.message.reply_html(
            rf"¡Hola de nuevo {user.mention_html()}! 👋"
            "\n\nYa estás registrado. Sigo analizando partidos en segundo plano."
            "\nTe avisaré aquí cuando detecte una buena señal. 🎯"
        )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado del bot y número de suscriptores."""
    subs = get_subscribers()
    await update.message.reply_text(
        f"✅ Motor de Scraping: ACTIVO\n"
        f"✅ Motor de Análisis: ACTIVO\n"
        f"✅ Motor de Notificaciones: ACTIVO\n"
        f"👥 Suscriptores activos: {len(subs)}"
    )

def create_application() -> Application:
    """Inicializa la aplicación y registra los comandos."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No se encontró TELEGRAM_TOKEN en el entorno.")
        raise ValueError("No se encontró TELEGRAM_TOKEN en el entorno.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))

    return app
