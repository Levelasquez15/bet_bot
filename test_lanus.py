#!/usr/bin/env python3
import LanusStats as ls

def test_lanus_stats():
    print("🔍 Probando LanusStats...")

    # Ver páginas disponibles
    print("\n📄 Páginas disponibles:")
    pages = ls.get_available_pages()
    for page in pages:
        print(f"  - {page}")

    # Ver ligas disponibles para FBRef (la más completa según la doc)
    print("\n⚽ Ligas disponibles en FBRef:")
    try:
        leagues = ls.get_available_leagues("FBRef")
        for league in leagues[:10]:  # Mostrar solo las primeras 10
            print(f"  - {league}")
        if len(leagues) > 10:
            print(f"  ... y {len(leagues) - 10} más")
    except Exception as e:
        print(f"  Error: {e}")

    # Ver temporadas disponibles para una liga específica
    print("\n📅 Temporadas disponibles para Premier League:")
    try:
        seasons = ls.get_available_season_for_leagues("FBRef", "Premier League")
        for season in seasons[:5]:  # Mostrar solo las primeras 5
            print(f"  - {season}")
    except Exception as e:
        print(f"  Error: {e}")

    # Probar obtener datos de equipos
    print("\n📊 Probando obtener estadísticas de equipos...")
    try:
        fbref = ls.Fbref()
        # Obtener GCA (Goal Creating Actions) para Premier League 2023
        df = fbref.get_teams_season_stats('gca', 'Premier League', season='2023', save_csv=False)
        print(f"✅ Datos obtenidos: {len(df)} equipos")
        print("Columnas:", list(df.columns[:5]), "...")
        print("Primeros equipos:")
        for idx, row in df.head(3).iterrows():
            print(f"  - {row['Squad']}: GCA {row.get('GCA', 'N/A')}")
    except Exception as e:
        print(f"❌ Error obteniendo datos: {e}")

if __name__ == "__main__":
    test_lanus_stats()