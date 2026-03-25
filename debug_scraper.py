#!/usr/bin/env python3
"""
Debug script for football scraper
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from football_scraper_pandas import FootballDataScraper
import logging
import pandas as pd

logging.basicConfig(level=logging.DEBUG)

def debug_scraper():
    print('🔍 Debug detallado del scraper...')

    scraper = FootballDataScraper()

    print('Testing URL generation...')
    league = 'Premier League'
    league_info = scraper.league_mappings.get(league)
    if league_info:
        fbref_id = league_info['fbref']
        url = f'https://fbref.com/en/comps/{fbref_id}/schedule/{league.replace(" ", "-")}-Scores-and-Fixtures'
        print(f'URL: {url}')

        # Test basic HTTP request
        try:
            print('Making HTTP request...')
            response = scraper.session.get(url, timeout=10)
            print(f'Status code: {response.status_code}')
            print(f'Content length: {len(response.text)}')

            if response.status_code == 200:
                print('✅ HTTP request successful')

                # Test pandas read_html
                print('Testing pandas read_html...')
                tables = pd.read_html(response.text)
                print(f'Found {len(tables)} tables')

                # Show first few tables info
                for i, table in enumerate(tables[:3]):
                    print(f'Table {i}: {table.shape} - Columns: {list(table.columns)[:5]}')

                # Try to find schedule table
                schedule_table = None
                for i, table in enumerate(tables):
                    if 'Date' in table.columns and 'Home' in table.columns:
                        schedule_table = table
                        print(f'✅ Found schedule table at index {i}')
                        break

                if schedule_table is not None:
                    print(f'Schedule table shape: {schedule_table.shape}')
                    print('First few rows:')
                    print(schedule_table.head(3))
                else:
                    print('❌ No schedule table found')

            else:
                print(f'❌ HTTP Error: {response.status_code}')
                print(f'Response: {response.text[:200]}')

        except Exception as e:
            print(f'❌ Error: {e}')
            import traceback
            traceback.print_exc()
    else:
        print('❌ League not found in mappings')

if __name__ == "__main__":
    debug_scraper()