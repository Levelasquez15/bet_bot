#!/usr/bin/env python3
"""
Test script for API client with The Sports DB
"""

import asyncio
import sys
import os

# Add src directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from api_client import load_history, get_upcoming_fixtures

class MockContext:
    def __init__(self):
        self.bot_data = {
            'league_name': 'English Premier League',
            'season': '2022-2023'
        }

async def test_api_client():
    print("Testing API client with The Sports DB...")

    # Test historical data
    print("\n📊 Testing historical matches...")
    ctx = MockContext()
    history = await load_history(ctx)
    print(f"✅ Found {len(history)} historical matches")

    if not history.empty:
        print("Sample historical matches:")
        for idx, row in history.head(3).iterrows():
            score = f"{row['home_goals']}-{row['away_goals']}"
            print(f"  - {row['home_team']} {score} {row['away_team']} - {row['date']}")

    # Test upcoming fixtures
    print("\n📅 Testing upcoming fixtures...")
    fixtures = await get_upcoming_fixtures(39, 2023, 5)
    print(f"✅ Found {len(fixtures)} upcoming fixtures")

    if not fixtures.empty:
        print("Sample upcoming fixtures:")
        for idx, row in fixtures.head(3).iterrows():
            print(f"  - {row['home_team']} vs {row['away_team']} - {row['date']}")

if __name__ == "__main__":
    asyncio.run(test_api_client())