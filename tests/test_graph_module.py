"""
Pruebas unitarias para el Módulo 7: DecisionGraph, Nodos Especialistas, Gatekeeper y Supervisor.
"""

import sys
import os
import asyncio

# Asegurar path raíz del proyecto y UTF-8
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from src.graph.state import MatchState, NodeEvaluation, SupervisorVerdict
from src.graph.specialists import (
    MomentumSpecialistNode,
    SiegeXGSpecialistNode,
    PoissonEloValueSpecialistNode,
    DisciplinarySpecialistNode
)
from src.graph.gatekeeper import Gatekeeper
from src.graph.supervisor import LLMSupervisor
from src.graph.decision_graph import DecisionGraph


def test_specialists_and_conflict():
    print("Testing specialist nodes...")
    # 1. Test Momentum Specialist (Late draw pressure)
    state_momentum = MatchState(
        game_id="101",
        match_name="Arsenal - Chelsea",
        home_team="Arsenal",
        away_team="Chelsea",
        competition="Premier League",
        minute=72,
        score_home=1,
        score_away=1,
        is_live=True,
        is_half_time=False,
        live_stats={
            "shots_on_target": {"home": 4, "away": 3},
            "xg": {"home": 0.8, "away": 0.7},
            "possession": {"home": 52.0, "away": 48.0}
        }
    )
    node_mom = MomentumSpecialistNode()
    ev_mom = node_mom.evaluate(state_momentum)
    assert ev_mom is not None
    assert "Próximo Gol" in ev_mom.recommended_market
    assert ev_mom.confidence >= 75.0
    print("✅ MomentumSpecialistNode validado.")

    # 2. Test SiegeXG Specialist (Siege when trailing by 1)
    state_siege = MatchState(
        game_id="102",
        match_name="Real Madrid - Sevilla",
        home_team="Real Madrid",
        away_team="Sevilla",
        competition="La Liga",
        minute=65,
        score_home=0,
        score_away=1,
        is_live=True,
        is_half_time=False,
        live_stats={
            "shots_on_target": {"home": 5, "away": 1},
            "corners": {"home": 7, "away": 1},
            "possession": {"home": 62.0, "away": 38.0}
        }
    )
    node_siege = SiegeXGSpecialistNode()
    ev_siege = node_siege.evaluate(state_siege)
    assert ev_siege is not None
    assert "Córners" in ev_siege.recommended_market
    print("✅ SiegeXGSpecialistNode validado.")

    # 3. Test Disciplinary Specialist (Red Card advantage)
    state_disc = MatchState(
        game_id="103",
        match_name="Liverpool - Everton",
        home_team="Liverpool",
        away_team="Everton",
        competition="Premier League",
        minute=55,
        score_home=0,
        score_away=0,
        is_live=True,
        is_half_time=False,
        live_stats={
            "red_cards": {"home": 0, "away": 1},
            "possession": {"home": 68.0, "away": 32.0}
        }
    )
    node_disc = DisciplinarySpecialistNode()
    ev_disc = node_disc.evaluate(state_disc)
    assert ev_disc is not None
    assert "Liverpool" in ev_disc.recommended_market
    print("✅ DisciplinarySpecialistNode validado.")


def test_gatekeeper():
    print("Testing Gatekeeper...")
    gk = Gatekeeper()
    state = MatchState(
        game_id="201",
        match_name="Bayern - Dortmund",
        home_team="Bayern",
        away_team="Dortmund",
        competition="Bundesliga",
        minute=70,
        score_home=1,
        score_away=1,
        is_live=True,
        is_half_time=False,
        evaluations={
            "Momentum": NodeEvaluation(
                node_name="MomentumSpecialist",
                recommended_market="Más de 2.5",
                confidence=78.0,
                estimated_odd=1.70,
                rationale="Alta presión"
            )
        }
    )
    allowed, reason = gk.should_invoke_llm(state)
    assert allowed is True

    # After recording invocation, cooling down prevents immediate duplicate
    gk.record_llm_invocation("201")
    allowed2, reason2 = gk.should_invoke_llm(state)
    assert allowed2 is False
    assert "Anti-saturación" in reason2

    # Force bypass works
    allowed_force, _ = gk.should_invoke_llm(state, force=True)
    assert allowed_force is True
    print("✅ Gatekeeper de costo $0 validado.")


def test_decision_graph_pipeline():
    print("Testing DecisionGraph full pipeline...")
    graph = DecisionGraph()

    dummy_game = {
        "id": 99999,
        "homeCompetitor": {"name": "Barcelona", "score": 1},
        "awayCompetitor": {"name": "Atletico Madrid", "score": 1},
        "competitionDisplayName": "La Liga",
        "gameTime": 75,
        "statusGroup": 2,
        "live_stats": {
            "shots_on_target": {"home": 5, "away": 3},
            "xg": {"home": 1.2, "away": 0.6},
            "possession": {"home": 60.0, "away": 40.0},
            "corners": {"home": 6, "away": 2},
            "red_cards": {"home": 0, "away": 0}
        },
        "odds": {
            "options": [
                {"name": "1", "rate": {"decimal": 2.10}},
                {"name": "X", "rate": {"decimal": 3.20}},
                {"name": "2", "rate": {"decimal": 3.40}}
            ]
        }
    }

    state = asyncio.run(graph.evaluate_match(dummy_game, is_live=True, force_llm=False))
    assert state.verdict is not None
    assert state.final_pick is not None
    assert state.final_pick["match"] == "Barcelona - Atletico Madrid"
    assert state.final_pick["confidence"] >= 65.0
    print(f"✅ Pick generado por el Grafo: {state.final_pick['market']} (Confianza: {state.final_pick['confidence']}%)")
    print(f"   Veredicto Supervisor: {state.final_pick['reason']}")


if __name__ == "__main__":
    test_specialists_and_conflict()
    test_gatekeeper()
    test_decision_graph_pipeline()
    print("🎉 ¡TODOS LOS TESTS DEL MÓDULO 7 PASARON EXITOSAMENTE!")
