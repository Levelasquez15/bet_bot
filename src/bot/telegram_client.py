import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from src.bot.subscribers import add_subscriber, get_subscribers
from src.scraper.scraper_365 import Scraper365

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra al usuario como suscriptor y le da la bienvenida."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    is_new = add_subscriber(chat_id)

    if is_new:
        logger.info(f"Nuevo suscriptor: {chat_id} ({user.full_name})")
        await update.message.reply_html(
            rf"¡Hola {user.mention_html()}! Soy 365BetBot. 🤖"
            "\n\n✅ <b>¡Registrado con éxito!</b>"
            "\nA partir de ahora recibirás alertas cuando detecte señales de valor."
            "\n\n📊 Analizo partidos <b>en vivo</b> y <b>próximos</b> usando:"
            "\n  • Árboles de decisión (live)"
            "\n  • Modelo Poisson (pre-partido)"
            "\n\nUsa /status para ver el motor | /debug para ver datos en vivo."
        )
    else:
        await update.message.reply_html(
            rf"¡Hola de nuevo {user.mention_html()}! 👋"
            "\n\nYa estás registrado. Sigo analizando partidos cada 2 minutos. 🔄"
            "\nTe avisaré aquí cuando detecte una buena señal. 🎯"
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado del bot."""
    subs = get_subscribers()
    await update.message.reply_text(
        "📊 <b>Estado del Motor BetBot</b>\n\n"
        "✅ Scraping 365scores: ACTIVO\n"
        "✅ Análisis en Vivo (8 árboles): ACTIVO\n"
        "✅ Análisis Próximos (Poisson): ACTIVO\n"
        "✅ Notificaciones: ACTIVO\n"
        f"👥 Suscriptores: {len(subs)}\n"
        "⏱️ Ciclo de escaneo: cada 2 minutos",
        parse_mode="HTML"
    )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra datos en tiempo real del scraper para diagnóstico."""
    await update.message.reply_text("🔍 Consultando 365scores... espera un momento.")
    scraper = Scraper365()
    try:
        info = await scraper.fetch_all_for_debug()
        lines = [
            "🛠️ <b>DEBUG — Estado del Scraper</b>\n",
            f"📅 Partidos hoy: <b>{info['total']}</b>",
            f"🟡 Próximos: {info['upcoming']}",
            f"🟢 En vivo: {info['live']}",
            f"⚫ Finalizados: {info['finished']}",
            f"⏰ Próximos (3h): {info['upcoming_3h']}\n",
        ]
        if info["live_sample"]:
            lines.append("⚽ <b>En vivo ahora:</b>")
            lines += [f"  • {m}" for m in info["live_sample"]]
        else:
            lines.append("⚽ Sin partidos en vivo ahora mismo.")

        if info["upcoming_sample"]:
            lines.append("\n📅 <b>Próximos partidos:</b>")
            lines += [f"  • {m}" for m in info["upcoming_sample"]]
        else:
            lines.append("\n📅 Sin partidos próximos en 3h.")

        await update.message.reply_html("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ Error en debug: {e}")
    finally:
        await scraper.close()


def create_application() -> Application:
    """Inicializa la aplicación y registra todos los comandos."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("No se encontró TELEGRAM_TOKEN en el entorno.")
        raise ValueError("No se encontró TELEGRAM_TOKEN en el entorno.")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start",  start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("debug",  debug_command))

    return app
