from __future__ import annotations

import logging

from .command_handlers import (
    cmd_start, cmd_status, cmd_setleague, cmd_predict, cmd_jornada,
    cmd_jornada_manana, cmd_jornada_pasado, cmd_proximos, cmd_combinada,
    cmd_notificaciones, cmd_comparar_lineas, cmd_analyze_next, cmd_backtest,
    cmd_apuestas
)
from .config import get_telegram_token
from .soccerdata_calendar_handlers import build_calendario_conversation

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    # Import telegram components only when needed to avoid tornado issues
    from telegram.ext import Application, CommandHandler

    try:
        logger.info("Starting BetBot...")
        token = get_telegram_token()
        logger.info("Telegram token loaded successfully")

        app = Application.builder().token(token).build()
        logger.info("Application created successfully")

        # Register commands
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_start))
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("setleague", cmd_setleague))
        app.add_handler(CommandHandler("partido", cmd_predict))
        app.add_handler(CommandHandler("jornada", cmd_jornada))
        app.add_handler(CommandHandler("jornada_manana", cmd_jornada_manana))
        app.add_handler(CommandHandler("jornada_pasado", cmd_jornada_pasado))
        app.add_handler(CommandHandler("proximos", cmd_proximos))
        app.add_handler(CommandHandler("combinada", cmd_combinada))
        app.add_handler(CommandHandler("notificaciones", cmd_notificaciones))
        app.add_handler(CommandHandler("comparar_lineas", cmd_comparar_lineas))
        app.add_handler(CommandHandler("analyze_next", cmd_analyze_next))
        app.add_handler(CommandHandler("backtest", cmd_backtest))
        app.add_handler(CommandHandler("apuestas", cmd_apuestas))
        # Calendario/fixtures basado en soccerdata (hoy/mañana + selector de mes/día)
        app.add_handler(build_calendario_conversation())
        logger.info("All commands registered successfully")

        logger.info("🤖 BetBot iniciado. Esperando mensajes...")
        print("🤖 BetBot iniciado. Esperando mensajes...")
        app.run_polling(allowed_updates=["message", "edited_message", "callback_query"])

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error al iniciar el bot: {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error al iniciar el bot: {e}")
        raise


if __name__ == "__main__":
    main()