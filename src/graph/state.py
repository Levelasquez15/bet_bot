"""
Definición de estados y estructuras de datos para el Grafo de Decisión (StateGraph).
Módulo 7: Motor de Decisión con Grafo de Agentes y LLM Supervisor.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class NodeEvaluation:
    """Evaluación emitida por un Nodo Especialista del grafo."""
    node_name: str
    recommended_market: str
    confidence: float  # 0.0 a 100.0
    estimated_odd: float
    rationale: str
    sentiment: str = "NEUTRAL"  # BULLISH_OVER, BEARISH_UNDER, FAVOR_HOME, FAVOR_AWAY, CORNERS_HIGH, DEFENSIVE, NEUTRAL
    signals: Dict[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass
class SupervisorVerdict:
    """Veredicto final emitido por el Supervisor (LLM Gemini o Supervisor Determinista)."""
    decision: str  # "APPROVE", "REJECT", "MODIFY"
    selected_market: str
    confidence: float
    recommended_stake: int  # 1 a 5
    tactical_report: str  # Explicación táctica en lenguaje natural
    risk_factors: List[str] = field(default_factory=list)
    source: str = "DETERMINISTIC"  # "GEMINI_FLASH" o "DETERMINISTIC"
    odd_num: float = 1.65
    odd_str: str = "1.65"


@dataclass
class MatchState:
    """
    Estado contextual completo de un partido en el Grafo de Decisión.
    Viaja y se muta a través de los Nodos Especialistas, Detector de Conflictos y Supervisor.
    """
    game_id: str
    match_name: str
    home_team: str
    away_team: str
    competition: str
    minute: Any
    score_home: int
    score_away: int
    is_live: bool
    is_half_time: bool

    # Estadísticas en vivo
    live_stats: Dict[str, Any] = field(default_factory=dict)

    # Cuotas de casas de apuestas
    odds: Dict[str, Any] = field(default_factory=dict)

    # Evaluaciones de los Nodos Especialistas
    evaluations: Dict[str, NodeEvaluation] = field(default_factory=dict)

    # Detección de dinámicas
    conflicts: List[str] = field(default_factory=list)
    synergies: List[str] = field(default_factory=list)
    has_value: bool = False

    # Veredicto y Pick final
    gatekeeper_passed: bool = False
    verdict: Optional[SupervisorVerdict] = None
    final_pick: Optional[Dict[str, Any]] = None

    @property
    def total_goals(self) -> int:
        return self.score_home + self.score_away

    @property
    def score_diff(self) -> int:
        return abs(self.score_home - self.score_away)
