#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '')

print(f"Token configurado: {'SI' if token else 'NO'}")
print(f"Longitud del token: {len(token)} caracteres")

if token:
    print(f"Token comienza con: {token[:10]}...")
    print("✅ El bot debería funcionar")
else:
    print("❌ Token vacío - necesitas configurarlo")
    print("\nPara configurar:")
    print("1. Ve a @BotFather en Telegram")
    print("2. Crea un nuevo bot con /newbot")
    print("3. Copia el token que te da")
    print("4. Pégalo en .env como: TELEGRAM_BOT_TOKEN=tu_token_aqui")