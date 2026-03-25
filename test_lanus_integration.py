#!/usr/bin/env python3
"""
Test script for LanusStats integration with fallback
Shows which data source is being used
"""

import sys
import os

# Add src directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

print("🔍 Probando integración de LanusStats con fallback...")
print("=" * 60)

# Test import
try:
    from football_scraper import api_scraper, LANUS_AVAILABLE
    print("✅ Módulo football_scraper importado correctamente")
    print(f"📊 LanusStats disponible: {LANUS_AVAILABLE}")
    print(f"🎯 Fuente primaria: {api_scraper.primary_source}")
except Exception as e:
    print(f"❌ Error importando football_scraper: {e}")
    sys.exit(1)

print("\n" + "=" * 60)

# Test upcoming matches
print("📅 Probando partidos próximos...")
try:
    df_upcoming = api_scraper.get_upcoming_matches('English Premier League', 7)
    print(f"✅ Encontrados {len(df_upcoming)} partidos próximos")
    if not df_upcoming.empty:
        print("Muestra de datos:")
        for idx, row in df_upcoming.head(2).iterrows():
            print(f"  - {row['home_team']} vs {row['away_team']} ({row['date']}) - Fuente: {row.get('source', 'Unknown')}")
    else:
        print("⚠️ No se encontraron partidos próximos")
except Exception as e:
    print(f"❌ Error obteniendo partidos próximos: {e}")

print("\n" + "=" * 60)

# Test historical matches
print("📊 Probando partidos históricos...")
try:
    df_history = api_scraper.get_historical_matches('English Premier League', '2022-2023', 5)
    print(f"✅ Encontrados {len(df_history)} partidos históricos")
    if not df_history.empty:
        print("Muestra de datos:")
        for idx, row in df_history.head(2).iterrows():
            score = f"{row['home_goals']}-{row['away_goals']}"
            print(f"  - {row['home_team']} {score} {row['away_team']} ({row['date']}) - Fuente: {row.get('source', 'Unknown')}")
    else:
        print("⚠️ No se encontraron partidos históricos")
except Exception as e:
    print(f"❌ Error obteniendo partidos históricos: {e}")

print("\n" + "=" * 60)
print("🎉 ¡Pruebas completadas!")
print(f"🔄 Sistema funcionando con fuente: {api_scraper.primary_source}")

if not LANUS_AVAILABLE:
    print("\n💡 Para activar LanusStats:")
    print("   1. Resolver problemas de instalación de pydoll y dependencias")
    print("   2. pip install LanusStats")
    print("   3. Reiniciar el scraper")
    print("   4. El sistema automáticamente usará LanusStats como fuente primaria")