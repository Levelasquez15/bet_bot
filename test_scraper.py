#!/usr/bin/env python3
"""
Test script for The Sports DB API football scraper
"""

import asyncio
import logging
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from football_scraper import api_scraper

logging.basicConfig(level=logging.INFO)

async def test_upcoming_matches():
    """Test getting upcoming matches"""
    print("Testing upcoming matches...")

    # Test different leagues
    leagues = [
        "English Premier League",
        "La Liga",
        "Serie A",
        "Bundesliga",
        "Ligue 1"
    ]

    for league in leagues:
        print(f"\n--- Testing {league} ---")
        df = api_scraper.get_upcoming_matches(league_name=league, days_ahead=14)

        if df.empty:
            print(f"No upcoming matches found for {league}")
        else:
            print(f"Found {len(df)} upcoming matches:")
            print(df.head(5).to_string(index=False))
            print("...")

async def test_historical_matches():
    """Test getting historical matches"""
    print("\n\nTesting historical matches...")

    # Test Premier League 2022-2023 season
    df = api_scraper.get_historical_matches(
        league_name="English Premier League",
        season="2022-2023",
        limit=10
    )

    if df.empty:
        print("No historical matches found")
    else:
        print(f"Found {len(df)} historical matches:")
        print(df.to_string(index=False))

async def main():
    """Run all tests"""
    print("Starting football scraper tests with The Sports DB API...")
    print("=" * 60)

    await test_upcoming_matches()
    await test_historical_matches()

    print("\n" + "=" * 60)
    print("Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())