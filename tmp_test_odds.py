import asyncio
import httpx
import json

async def test_odds():
    try:
        url = "https://webws.365scores.com/web/games/"
        params = {
            "appTypeId": "5",
            "langId": "29",
            "timezoneName": "America/Bogota",
            "userCountryId": "170",
            "sports": "1",
            "showOdds": "true",
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Origin": "https://www.365scores.com",
            "Referer": "https://www.365scores.com/",
        }
        
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            
            games_with_odds = [g for g in data.get('games', []) if 'odds' in g or g.get('bookmakers')]
            print(f"Total games: {len(data.get('games', []))}")
            print(f"Games with 'odds' or 'bookmakers' key: {len(games_with_odds)}")
            
            if games_with_odds:
                # Dump the first game's odds structure
                print(json.dumps(games_with_odds[0].get('odds', {}), indent=2))
                print(json.dumps(games_with_odds[0].get('bookmakers', []), indent=2))
                
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_odds())
