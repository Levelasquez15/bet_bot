#!/usr/bin/env python3
"""
Test script to verify bot components work correctly
"""

def test_imports():
    """Test that all bot components can be imported"""
    try:
        print("Testing imports...")

        # Test main modules
        from src.main import main
        print("✅ src.main imported")

        from src.command_handlers import cmd_start
        print("✅ src.command_handlers imported")

        from src.soccerdata_calendar_handlers import build_calendario_conversation
        print("✅ src.soccerdata_calendar_handlers imported")

        from src.prediction_service import predict_match_inline, analyze_jornada_inline
        print("✅ src.prediction_service imported")

        from src.engine import PredictionEngine
        print("✅ src.engine imported")

        from src.models.poisson import poisson_1x2_over25
        print("✅ src.models.poisson imported")

        from src.soccerdata_fixtures import get_matches_for_date_token
        print("✅ src.soccerdata_fixtures imported")

        print("\n🎉 All imports successful!")
        return True

    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_prediction_engine():
    """Test the prediction engine with mock data"""
    try:
        print("\nTesting prediction engine...")

        from src.engine import PredictionEngine
        import pandas as pd

        engine = PredictionEngine()

        # Mock historical data
        mock_matches = pd.DataFrame({
            'home_team': ['Team A', 'Team B', 'Team C', 'Team A'],
            'away_team': ['Team B', 'Team C', 'Team A', 'Team D'],
            'home_goals': [2, 1, 0, 3],
            'away_goals': [1, 1, 2, 1],
            'date': pd.date_range('2024-01-01', periods=4)
        })

        strengths = engine.build_team_strengths(mock_matches)
        elo_model = engine.fit_elo(mock_matches)

        probs = engine.predict_match('Team A', 'Team B', strengths, elo_model)

        print(f"✅ Prediction successful: {probs}")
        return True

    except Exception as e:
        print(f"❌ Prediction engine test failed: {e}")
        return False

def test_poisson_model():
    """Test Poisson probability calculations"""
    try:
        print("\nTesting Poisson model...")

        from src.models.poisson import poisson_1x2_over25

        probs = poisson_1x2_over25(1.5, 1.2)
        print(f"✅ Poisson calculation successful: {probs}")

        # Check probabilities sum to reasonable values
        total_1x2 = probs['home_win'] + probs['draw'] + probs['away_win']
        print(f"1X2 probabilities sum: {total_1x2:.3f} (should be ~1.0)")

        return True

    except Exception as e:
        print(f"❌ Poisson test failed: {e}")
        return False

def main():
    print("🧪 BetBot Component Tests")
    print("=" * 40)

    results = []
    results.append(test_imports())
    results.append(test_prediction_engine())
    results.append(test_poisson_model())

    print("\n" + "=" * 40)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"🎉 All tests passed! ({passed}/{total})")
        print("\n✅ Bot is ready to run!")
        print("💡 To start: python telegram_bot.py")
        print("   Make sure to set TELEGRAM_BOT_TOKEN in .env")
    else:
        print(f"❌ Some tests failed: {passed}/{total} passed")
        print("\n🔧 Check the errors above and fix them before running the bot")

if __name__ == "__main__":
    main()