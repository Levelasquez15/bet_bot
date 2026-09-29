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
    from src.bot.health_server import start_health_server

    logger = logging.getLogger(__name__)
    logger.info("Inicializando BetBot Motor Central...")

    # 1. Iniciar servidor HTTP en segundo plano para Koyeb/Cloud health check
    start_health_server()

    # 2. Instanciar aplicación de Telegram
    app = create_application()

    # 3. Configurar motor de background (worker scheduler)
    setup_worker(app)

    # 4. Arrancar polling
    logger.info("🤖 BetBot iniciado. Escuchando telegram y escaneando 365scores (Modo Polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()