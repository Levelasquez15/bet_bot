#!/usr/bin/env python3
"""
Test script to verify bot initialization
"""

def test_bot_init():
    """Test that the bot can initialize correctly"""
    try:
        print("🔄 Probando inicialización del bot...")

        # Test token loading
        from src.config import get_telegram_token
        token = get_telegram_token()
        if not token:
            print("❌ Token no encontrado")
            return False
        print(f"✅ Token cargado: {len(token)} caracteres")

        # Test telegram imports
        from telegram.ext import Application
        print("✅ Librerías de Telegram importadas")

        # Test application creation (without starting)
        app = Application.builder().token(token).build()
        print("✅ Aplicación de Telegram creada")

        # Test command imports
        from src.command_handlers import cmd_start
        from src.soccerdata_calendar_handlers import build_calendario_conversation
        print("✅ Handlers importados correctamente")

        print("\n🎉 ¡Bot listo para funcionar!")
        print("💡 Ejecuta: python telegram_bot.py")
        print("🤖 Tu bot: @Lewis_bet_15_bot")

        return True

    except Exception as e:
        print(f"❌ Error en inicialización: {e}")
        return False

if __name__ == "__main__":
    test_bot_init()