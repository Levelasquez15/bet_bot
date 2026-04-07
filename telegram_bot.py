#!/usr/bin/env python3
import logging
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    # Cargar variables de entorno predeterminadas de .env
    load_dotenv()

    # Retrasar importaciones para evitar que telegram interfiera con el loop si es cargado antes
    from src.bot.telegram_client import create_application
    from src.worker.main_worker import setup_worker

    logger = logging.getLogger(__name__)
    logger.info("Inicializando BetBot Motor Central...")

    # 1. Instanciar aplicación de Telegram
    app = create_application()

    # 2. Configurar motor de background (worker scheduler)
    setup_worker(app)

    # 3. Arrancar polling
    logger.info("🤖 BetBot iniciado. Escuchando telegram y escaneando 365scores (Modo Polling)...")
    logger.info("En Azure (Container Instances) este bot quedará ejecutándose continuamente.")
    app.run_polling()

if __name__ == "__main__":
    main()