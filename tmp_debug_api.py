"""
Script extendido de diagnóstico para entender la estructura completa de datos.
"""
import asyncio
import httpx
import json
from datetime import datetime, timezone, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://www.365scores.com",
    "Referer": "https://www.365scores.com/",
}

async def test_api():
    async with httpx.AsyncClient(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
        today = datetime.now(tz=timezone(timedelta(hours=-5)))
        date_str = today.strftime("%d/%m/%Y")

        print(f"=== DIAGNÓSTICO 365SCORES - {date_str} ===\n")

        params = {
            "appTypeId": "5",
            "langId": "29",
            "timezoneName": "America/Bogota",
            "userCountryId": "170",
            "sports": "1",
            "startDate": date_str,
            "endDate": date_str,
        }
        r = await client.get("https://webws.365scores.com/web/games/", params=params)
        data = r.json()
        games = data.get("games", [])

        # Contar por statusGroup
        groups = {}
        for g in games:
            sg = g.get("statusGroup", "?")
            groups[sg] = groups.get(sg, 0) + 1
        print(f"Total partidos: {len(games)}")
        print(f"Por statusGroup (1=Próximo, 2=En Vivo, 3=Medio Tiempo, 4=Finalizado): {groups}\n")

        # Mostrar estructura de UN partido completo
        print("=== ESTRUCTURA COMPLETA DE UN PARTIDO ===")
        if games:
            print(json.dumps(games[0], indent=2, ensure_ascii=False)[:3000])

asyncio.run(test_api())
