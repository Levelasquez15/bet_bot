"""
Suite de pruebas automatizadas para GitHub Actions y CI/CD de BetBot.
Verifica que todos los motores matemáticos, scraping, base de datos y bot funcionen 100%.
"""

import sys
import os

# Asegurar path raíz del proyecto y UTF-8
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def test_imports():
    """Verifica que todos los módulos clave se importen sin errores de sintaxis o dependencias."""
    import src.scraper.leagues
    import src.scraper.scraper_365
    import src.models.poisson
    import src.models.elo
    import src.models.value
    import src.analyzer.logic_tree
    import src.analyzer.combinadas
    import src.db.database
    import src.db.repositories
    import src.bot.subscribers
    import src.bot.pick_tracker
    import src.bot.health_server
    import src.bot.telegram_client
    import src.worker.main_worker
    import src.worker.result_checker
    import src.graph.state
    import src.graph.specialists
    import src.graph.gatekeeper
    import src.graph.supervisor
    import src.graph.decision_graph
    print("✅ Todos los módulos se importan correctamente.")


def test_models():
    """Verifica el cálculo de Poisson, Elo y Value Betting."""
    from src.models.elo import get_team_elo, estimate_lambdas
    from src.models.poisson import calculate_poisson_matrix
    from src.models.value import calculate_value

    lh, la = estimate_lambdas("Real Madrid", "Barcelona")
    assert lh > 0 and la > 0

    probs = calculate_poisson_matrix(lh, la)
    assert 0.99 <= (probs["home_win"] + probs["draw"] + probs["away_win"]) <= 1.01

    vb = calculate_value(model_prob=0.70, bookmaker_odd=1.65)
    assert vb["has_value"] is True
    assert vb["ev_pct"] > 0
    print("✅ Motores matemáticos validados correctamente.")


def test_database():
    """Verifica la base de datos relacional y repositorios."""
    from src.db.database import db
    from src.db.repositories import SubscriberRepository, PickRepository
    from src.bot.pick_tracker import verify_pick

    # Test suscriptores
    test_id = 888777666
    SubscriberRepository.add_subscriber(test_id, username="ci_tester")
    assert test_id in SubscriberRepository.get_active_subscribers()

    # Test mercados goles y 1X2
    assert verify_pick({"market": "Más de 2.5 Goles"}, 2, 1) == "GANADO"
    assert verify_pick({"market": "Gana Local"}, 2, 0) == "GANADO"
    assert verify_pick({"market": "Ambos equipos marcarán: Sí"}, 1, 1) == "GANADO"

    # Test córners y tarjetas con stats
    stats = {
        "has_stats": True,
        "corners": {"home": 5, "away": 5},
        "yellow_cards": {"home": 2, "away": 2},
        "red_cards": {"home": 0, "away": 0}
    }
    assert verify_pick({"market": "Más de 8.5 córners"}, 1, 1, stats=stats) == "GANADO"
    assert verify_pick({"market": "Más de 3.5 tarjetas"}, 1, 1, stats=stats) == "GANADO"
    print("✅ Persistencia y verificador de mercados validados.")


def test_graph_engine():
    """Verifica el DecisionGraph y Nodos Especialistas del Módulo 7."""
    from src.graph.decision_graph import DecisionGraph
    from src.graph.gatekeeper import Gatekeeper
    import asyncio

    graph = DecisionGraph()
    gk = Gatekeeper()
    stats = gk.get_stats()
    assert "calls_last_hour" in stats

    dummy_game = {
        "id": "777",
        "homeCompetitor": {"name": "Arsenal", "score": 1},
        "awayCompetitor": {"name": "Chelsea", "score": 1},
        "competitionDisplayName": "Premier League",
        "gameTime": 70,
        "statusGroup": 2,
        "live_stats": {
            "shots_on_target": {"home": 4, "away": 3},
            "xg": {"home": 0.9, "away": 0.8},
            "possession": {"home": 51.0, "away": 49.0},
            "corners": {"home": 5, "away": 4},
            "red_cards": {"home": 0, "away": 0}
        }
    }
    state = asyncio.run(graph.evaluate_match(dummy_game, is_live=True, force_llm=False))
    assert state.final_pick is not None
    assert state.verdict is not None
    print("✅ DecisionGraph y Nodos Especialistas validados.")


if __name__ == "__main__":
    print("Ejecutando suite de pruebas de BetBot...")
    test_imports()
    test_models()
    test_database()
    test_graph_engine()
    print("🎉 ¡TODOS LOS TESTS PASARON EXITOSAMENTE!")
