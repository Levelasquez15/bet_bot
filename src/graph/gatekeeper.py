"""
Gatekeeper de Costo $0 y Anti-Saturación de LLM.
Módulo 7: Motor de Decisión con Grafo de Agentes y LLM Supervisor.

Filtra el tráfico hacia el LLM asegurando:
1. Ejecución matemática local a costo $0 y milisegundos.
2. Invocación de Gemini únicamente cuando exista una oportunidad de valor real (+EV confirmado o alta confianza).
3. Límite de tasa para segundo plano (máximo 5-8 llamadas/hora) para evitar saturación y costos.
4. Caché temporal por partido para evitar análisis redundantes.
"""

import time
import logging
from typing import Dict, Any, Optional
from src.graph.state import MatchState

logger = logging.getLogger(__name__)


class Gatekeeper:
    """Controlador de acceso y anti-saturación para el LLM Supervisor."""

    MAX_HOURLY_LLM_CALLS = 8  # Máximo de llamadas automáticas por hora
    COOLDOWN_PER_MATCH_SECONDS = 600  # 10 minutos de gracia por partido

    def __init__(self):
        self._llm_call_timestamps: list[float] = []
        self._match_cache: Dict[str, float] = {}

    def should_invoke_llm(self, state: MatchState, force: bool = False) -> tuple[bool, str]:
        """
        Determina si un partido califica para invocar al LLM Supervisor.
        Retorna (autorizado: bool, motivo: str).
        """
        # Si el usuario lo pide explícitamente vía /analizar
        if force:
            return True, "Solicitud manual de usuario (/analizar)"

        # 1. Filtro de Oportunidad de Valor: ¿Algún especialista encontró algo contundente?
        has_high_confidence = any(
            ev.confidence >= 70.0 for ev in state.evaluations.values()
        )
        has_positive_ev = state.has_value

        if not (has_high_confidence or has_positive_ev):
            return False, "Filtro local $0: No hay ventaja estadística suficiente (+EV o confianza >= 70%)"

        now = time.time()

        # 2. Caché por partido: evitar re-consultar el mismo partido en pocos minutos
        last_eval = self._match_cache.get(state.game_id, 0.0)
        if (now - last_eval) < self.COOLDOWN_PER_MATCH_SECONDS:
            return False, f"Anti-saturación: Partido analizado recientemente (hace {int(now - last_eval)}s)"

        # 3. Límite de tasa por hora para segundo plano
        # Limpiar llamadas viejas (> 1 hora)
        self._llm_call_timestamps = [t for t in self._llm_call_timestamps if (now - t) < 3600]

        if len(self._llm_call_timestamps) >= self.MAX_HOURLY_LLM_CALLS:
            return False, f"Límite de tasa: Se alcanzó el máximo de {self.MAX_HOURLY_LLM_CALLS} llamadas automáticas por hora"

        return True, "Oportunidad de alto valor detectada; invoca al Supervisor IA"

    def record_llm_invocation(self, game_id: str) -> None:
        """Registra una llamada exitosa al LLM para control de cuota."""
        now = time.time()
        self._llm_call_timestamps.append(now)
        self._match_cache[game_id] = now
        logger.info(f"Gatekeeper: Invocación de LLM registrada para {game_id}. Total en última hora: {len(self._llm_call_timestamps)}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna telemetría del Gatekeeper para comandos de monitoreo."""
        now = time.time()
        self._llm_call_timestamps = [t for t in self._llm_call_timestamps if (now - t) < 3600]
        return {
            "calls_last_hour": len(self._llm_call_timestamps),
            "max_hourly": self.MAX_HOURLY_LLM_CALLS,
            "cached_matches": len(self._match_cache)
        }
