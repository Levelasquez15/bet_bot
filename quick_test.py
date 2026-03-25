#!/usr/bin/env python3
"""
Quick test for current football scraper
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from football_scraper import api_scraper

print("🔍 Probando The Sports DB API scraper...")

try:
    # Test upcoming matches
    df_upcoming = api_scraper.get_upcoming_matches('English Premier League', 7)
    print(f"✅ Partidos próximos: {len(df_upcoming)} encontrados")

    # Test historical matches
    df_history = api_scraper.get_historical_matches('English Premier League', '2022-2023', 5)
    print(f"✅ Partidos históricos: {len(df_history)} encontrados")

    print("🎉 ¡The Sports DB API funciona perfectamente!")

except Exception as e:
    print(f"❌ Error: {e}")