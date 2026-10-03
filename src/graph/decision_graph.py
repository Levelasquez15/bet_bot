"""
Motor de Decisión con Grafo de Estados (Decision Graph / StateGraph).
Módulo 7: Motor de Decisión con Grafo de Agentes y LLM Supervisor.

Orquesta los Nodos Especialistas, el Enrutador Dinámico, el Detector de Conflictos,
el Gatekeeper de Costo $0 y el Supervisor IA (Gemini Flash / Determinista).
"""

import logging
from typing import Dict, Any, List, Optional
from src.graph.state import MatchState, NodeEvaluation, SupervisorVerdict
from src.graph.specialists import (
    MomentumSpecialistNode,
    SiegeXGSpecialistNode,
    PoissonEloValueSpecialistNode,
    DisciplinarySpecialistNode
)
from src.graph.gatekeeper import Gatekeeper
from src.graph.supervisor import LLMSupervisor
from src.scraper.scraper_365 import extract_match_odds

logger = logging.getLogger(__name__)


class DecisionGraph:
    """
    Grafo de Decisión y Orquestación Multi-Agente para Pronósticos Deportivos.
    """

    def __init__(self):
        # 1. Nodos Especialistas
        self.momentum_node = MomentumSpecialistNode()
        self.siege_node = SiegeXGSpecialistNode()
        self.poisson_elo_node = PoissonEloValueSpecialistNode()
        self.disciplinary_node = DisciplinarySpecialistNode()

        # 2. Gatekeeper de Costo $0 y Anti-Saturación
        self.gatekeeper = Gatekeeper()

        # 3. Director Técnico IA / Supervisor
        self.supervisor = LLMSupervisor()

    def build_state_from_game(self, game: Dict[str, Any], is_live: bool = True) -> MatchState:
        """Construye un MatchState estructurado a partir del diccionario crudo de 365scores."""
        gid = str(game.get("id", ""))
        home = game.get("homeCompetitor", {}).get("name", "Local")
        away = game.get("awayCompetitor", {}).get("name", "Visitante")
        comp = game.get("competitionDisplayName") or game.get("competition", {}).get("name", "Liga")

        sh = self._safe_int(game.get("homeCompetitor", {}).get("score", 0))
        sa = self._safe_int(game.get("awayCompetitor", {}).get("score", 0))
        minute = game.get("gameTime", "0") if is_live else game.get("startTime", "")[:16].replace("T", " ")
        is_half_time = game.get("statusGroup") == 3

        stats = game.get("live_stats", {})
        odds = game.get("parsed_odds") or extract_match_odds(game)

        return MatchState(
            game_id=gid,
            match_name=f"{home} - {away}",
            home_team=home,
            away_team=away,
            competition=comp,
            minute=minute,
            score_home=sh,
            score_away=sa,
            is_live=is_live,
            is_half_time=is_half_time,
            live_stats=stats,
            odds=odds
        )

    async def evaluate_match(self, game: Dict[str, Any], is_live: bool = True, force_llm: bool = False) -> MatchState:
        """
        Ejecuta el ciclo completo del Grafo de Estados sobre un partido:
        1. Inicialización de estado.
        2. Enrutamiento dinámico a Nodos Especialistas.
        3. Detección de conflictos tácticos y sinergias.
        4. Evaluación del Gatekeeper de Costo $0.
        5. Veredicto del Supervisor (Gemini Flash o Determinista).
        6. Síntesis del Pick final.
        """
        state = self.build_state_from_game(game, is_live=is_live)

        # ── 1. Enrutamiento Dinámico a Nodos Especialistas ──
        if is_live:
            # Evaluar especialistas en vivo
            ev_mom = self.momentum_node.evaluate(state)
            if ev_mom:
                state.evaluations["Momentum"] = ev_mom

            ev_siege = self.siege_node.evaluate(state)
            if ev_siege:
                state.evaluations["SiegeXG"] = ev_siege

            ev_disc = self.disciplinary_node.evaluate(state)
            if ev_disc:
                state.evaluations["Disciplinary"] = ev_disc

            # Pre-calibración Poisson también disponible en live
            ev_poi = self.poisson_elo_node.evaluate(state)
            if ev_poi and ev_poi.confidence >= 70.0:
                state.evaluations["PoissonElo"] = ev_poi
        else:
            # En pre-partido opera primordialmente el especialista cuantitativo
            ev_poi = self.poisson_elo_node.evaluate(state)
            if ev_poi:
                state.evaluations["PoissonElo"] = ev_poi
                state.has_value = "EV:" in ev_poi.rationale

        # ── 2. Detección de Conflictos y Sinergias ──
        self._detect_conflicts_and_synergies(state)

        # Si ningún especialista generó señal, finalizar sin pick
        if not state.evaluations:
            return state

        # ── 3. Gatekeeper: ¿Autoriza llamada a LLM? ──
        allowed, reason = self.gatekeeper.should_invoke_llm(state, force=force_llm)
        state.gatekeeper_passed = allowed

        # ── 4. Invocación del Supervisor ──
        verdict = await self.supervisor.supervise(state, force_llm=allowed)
        state.verdict = verdict

        if allowed and verdict.source == "GEMINI_FLASH":
            self.gatekeeper.record_llm_invocation(state.game_id)

        # ── 5. Construcción del Pick Final Estructurado ──
        if verdict.decision == "APPROVE" and verdict.confidence >= 65.0:
            state.final_pick = self._format_final_pick(state, verdict)

        return state

    async def analyze_batch(self, games: List[Dict[str, Any]], is_live: bool = True) -> List[Dict[str, Any]]:
        """Analiza un lote de partidos (usado por el worker de fondo)."""
        picks = []
        for g in games:
            try:
                state = await self.evaluate_match(g, is_live=is_live, force_llm=False)
                if state.final_pick:
                    picks.append(state.final_pick)
            except Exception as e:
                logger.error(f"DecisionGraph: Error analizando {g.get('id')}: {e}")
        return picks

    def _detect_conflicts_and_synergies(self, state: MatchState) -> None:
        """Analiza tensiones y acuerdos entre nodos especialistas."""
        evals = state.evaluations

        # Conflicto 1: Roja en contra vs Favoritismo de victoria
        if "Disciplinary" in evals and "PoissonElo" in evals:
            disc_sentiment = evals["Disciplinary"].sentiment
            poi_sentiment = evals["PoissonElo"].sentiment
            if disc_sentiment != "NEUTRAL" and poi_sentiment != "NEUTRAL" and disc_sentiment != poi_sentiment:
                state.conflicts.append(
                    f"Conflicto de Superioridad: Modelo cuantitativo favorece {poi_sentiment} pero tarjeta roja favorece {disc_sentiment}."
                )

        # Conflicto 2: Asedio Over vs Bloqueo Defensivo Under
        has_over = any("OVER" in ev.sentiment or "BULLISH" in ev.sentiment for ev in evals.values())
        has_under = any("UNDER" in ev.sentiment or "BEARISH" in ev.sentiment for ev in evals.values())
        if has_over and has_under:
            state.conflicts.append("Conflicto de Ritmo: Discrepancia entre indicador ofensivo (Over) e indicador de bloqueo (Under).")

        # Sinergia: Momentum y Asedio alineados
        if "Momentum" in evals and "SiegeXG" in evals:
            state.synergies.append("Sinergia Ofensiva: Tanto Momentum como Asedio confirman presión sostenida en ataque.")

    def _format_final_pick(self, state: MatchState, verdict: SupervisorVerdict) -> Dict[str, Any]:
        """Ensambla el diccionario del pick final listo para el worker y telegram."""
        return {
            "match": state.match_name,
            "minute": state.minute,
            "market": verdict.selected_market,
            "reason": verdict.tactical_report,
            "confidence": verdict.confidence,
            "odd": verdict.odd_str,
            "odd_num": verdict.odd_num,
            "recommended_stake": verdict.recommended_stake,
            "score_home": state.score_home,
            "score_away": state.score_away,
            "tactical_report": verdict.tactical_report,
            "risk_factors": verdict.risk_factors,
            "source": verdict.source,
            "conflicts": state.conflicts,
            "synergies": state.synergies
        }

    @staticmethod
    def _safe_int(value) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
