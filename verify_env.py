from dotenv import load_dotenv
import os

load_dotenv()
key = os.getenv("API_FOOTBALL_KEY", "")
if key:
    print(f"✓ API key cargada (length={len(key)}, suffix={key[-4:]})")
else:
    print("✗ API key NO está configurada")
