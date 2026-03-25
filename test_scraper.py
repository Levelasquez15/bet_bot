#!/usr/bin/env python3
"""
Test script for LanusStats football scraper
"""

import asyncio
import logging
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from football_scraper import api_scraper
    LANUS_AVAILABLE = api_scraper is not None
except ImportError:
    LANUS_AVAILABLE = False
    print("LanusStats not available, tests will be limited")

logging.basicConfig(level=logging.INFO)

async def test_upcoming_matches():
    """Test getting upcoming matches"""
    print("Testing upcoming matches...")

    if not LANUS_AVAILABLE:
        print("❌ LanusStats not available, skipping upcoming matches test")
        return

    # Test different leagues
    leagues = [
        "Premier League",
        "La Liga",
        "Serie A",
        "Bundesliga",
        "Ligue 1"
    ]

    for league in leagues:
        print(f"\n--- Testing {league} ---")
        try:
            df = api_scraper.get_upcoming_matches(league_name=league, days_ahead=14)

            if df.empty:
                print(f"No upcoming matches found for {league}")
            else:
                print(f"Found {len(df)} upcoming matches:")
                print(df.head(3).to_string(index=False))
                print("...")
        except Exception as e:
            print(f"Error testing {league}: {e}")

async def test_historical_matches():
    """Test getting historical matches"""
    print("\n\nTesting historical matches...")

    if not LANUS_AVAILABLE:
        print("❌ LanusStats not available, skipping historical matches test")
        return

    # Test Premier League recent season
    try:
        df = api_scraper.get_historical_matches(
            league_name="Premier League",
            season="2023/2024",
            limit=10
        )

        if df.empty:
            print("No historical matches found")
        else:
            print(f"Found {len(df)} historical matches:")
            print(df.to_string(index=False))
    except Exception as e:
        print(f"Error testing historical matches: {e}")

async def test_lanus_direct():
    """Test LanusStats directly"""
    print("\n\nTesting LanusStats direct functionality...")

    if not LANUS_AVAILABLE:
        print("❌ LanusStats not available")
        return

    try:
        import LanusStats as ls

        # Test available pages
        print("Available pages in LanusStats:")
        pages = ls.get_available_pages()
        print(pages)

        # Test available leagues for FotMob
        if 'FotMob' in pages:
            print("\nAvailable leagues in FotMob:")
            leagues = ls.get_available_leagues('FotMob')
            print(leagues[:5])  # Show first 5

        # Test available seasons for Premier League
        if 'FBRef' in pages:
            print("\nAvailable seasons for Premier League in FBRef:")
            try:
                seasons = ls.get_available_season_for_leagues('FBRef', 'Premier League')
                print(seasons[:3])  # Show first 3
            except Exception as e:
                print(f"Error getting seasons: {e}")

    except Exception as e:
        print(f"Error testing LanusStats directly: {e}")

async def main():
    """Run all tests"""
    print("Starting LanusStats football scraper tests...")
    print("=" * 60)

    if LANUS_AVAILABLE:
        print("✅ LanusStats is available")
    else:
        print("❌ LanusStats is NOT available - limited functionality")

    await test_lanus_direct()
    await test_upcoming_matches()
    await test_historical_matches()

    print("\n" + "=" * 60)
    print("Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())