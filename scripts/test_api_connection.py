from __future__ import annotations

import os

from dotenv import load_dotenv
import requests

load_dotenv()


def main() -> None:
    api_key = os.getenv("API_FOOTBALL_KEY", "")
    if not api_key:
        raise SystemExit("Set API_FOOTBALL_KEY before running this script.")

    url = "https://v3.football.api-sports.io/leagues"
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key": api_key,
        "x-apisports-key": api_key,
    }

    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code != 200:
        raise SystemExit(f"Connection failed: {response.status_code} - {response.text[:200]}")

    data = response.json()
    leagues = data.get("response", [])
    print(f"Connection OK. Leagues found: {len(leagues)}")
    if leagues:
        print(f"Example league: {leagues[0].get('league', {}).get('name', 'N/A')}")


if __name__ == "__main__":
    main()
