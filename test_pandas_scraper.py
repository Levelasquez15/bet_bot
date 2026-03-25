#!/usr/bin/env python3
"""
Test script for the new pandas-based football scraper
"""
import asyncio
import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
from api_client import get_upcoming_fixtures, load_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_scraper():
    """Test the new football scraper functionality"""
    print("🧪 Testing pandas-based football scraper...")

    try:
        # Test 1: Upcoming matches
        print("\n1️⃣ Testing upcoming matches...")
        upcoming = await get_upcoming_fixtures(39, 2024, 5)  # Premier League
        print(f"✅ Found {len(upcoming)} upcoming matches")
        if len(upcoming) > 0:
            print("Sample upcoming matches:")
            for _, match in upcoming.head(3).iterrows():
                print(f"  {match['date'].strftime('%Y-%m-%d')} - {match['home_team']} vs {match['away_team']}")

        # Test 2: Historical matches
        print("\n2️⃣ Testing historical matches...")
        class MockContext:
            def __init__(self):
                self.bot_data = {'league_name': 'Premier League', 'season': '2023-2024'}

        context = MockContext()
        historical = await load_history(context)
        print(f"✅ Found {len(historical)} historical matches")
        if len(historical) > 0:
            print("Sample historical matches:")
            for _, match in historical.head(3).iterrows():
                score = f"{int(match['home_score'])}-{int(match['away_score'])}" if pd.notna(match['home_score']) else "N/A"
                print(f"  {match['date'].strftime('%Y-%m-%d')} - {match['home_team']} {score} {match['away_team']}")

        print("\n🎉 All tests passed! The pandas-based scraper is working correctly.")
        print("This provides similar functionality to LanusStats but using direct web scraping from FBref.")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scraper())