#!/usr/bin/env python3
"""
Test script for soccerdata fixtures
"""

import soccerdata as sd
import pandas as pd
from datetime import datetime

def test_soccerdata():
    print("Testing soccerdata initialization...")

    # Test leagues - use combined for efficiency
    leagues = "Big 5 European Leagues Combined"
    print(f"Using leagues: {leagues}")

    # Test seasons - use past season that should have data
    seasons_options = ["2324", ["2023-2024"], "2223"]

    for seasons in seasons_options:
        try:
            print(f"\nTrying seasons={seasons}")
            fbref = sd.FBref(leagues=leagues, seasons=seasons)
            schedule = fbref.read_schedule(force_cache=True)  # Use cache first
            print(f"✅ Success! Schedule shape: {schedule.shape}")
            print(f"Columns: {list(schedule.columns)[:15]}...")

            # Test filtering for a date in the season
            test_date = "2024-03-26"  # Use a date that should have matches
            print(f"\nFiltering for date: {test_date}")

            # Convert date column to datetime if needed
            if 'date' in schedule.columns:
                schedule['date'] = pd.to_datetime(schedule['date'])
                filtered = schedule[schedule['date'].dt.date == pd.to_datetime(test_date).date()]
                print(f"Matches on {test_date}: {len(filtered)}")
                if len(filtered) > 0:
                    print(filtered[['date', 'home_team', 'away_team']].head(3))
                    break
                else:
                    print("No matches on that date, trying another...")
                    # Try another date
                    test_date = "2024-04-01"
                    filtered = schedule[schedule['date'].dt.date == pd.to_datetime(test_date).date()]
                    print(f"Matches on {test_date}: {len(filtered)}")
                    if len(filtered) > 0:
                        print(filtered[['date', 'home_team', 'away_team']].head(3))
                        break
            else:
                print("❌ No 'date' column found")
                break

        except Exception as e:
            print(f"❌ Failed with seasons={seasons}: {e}")
            continue

    print("\nTest completed.")

if __name__ == "__main__":
    test_soccerdata()