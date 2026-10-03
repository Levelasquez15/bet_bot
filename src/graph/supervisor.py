"""
Agente Supervisor / Director Técnico IA (LLM Supervisor).
Módulo 7: Motor de Decisión con Grafo de Agentes y LLM Supervisor.

Integra Google Gemini Flash mediante inferencia REST asíncrona (httpx).
Resuelve contradicciones tácticas entre Nodos Especialistas y emite un veredicto estructurado.
Incluye un Supervisor Determinista de Respaldo que garantiza operatividad 24/7 sin API Key.
"""

import os
import json
import logging
import httpx
from typing import Optional, List
from src.graph.state import MatchState, SupervisorVerdict

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_FALLBACK_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


class LLMSupervisor:
    """Supervisor de decisiones que combina IA generativa (Gemini Flash) con reglas de consenso táctico."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if self.api_key:
            logger.info("LLMSupervisor: API Key de Google Gemini detectada. Modo IA Activo.")
        else:
            logger.info("LLMSupervisor: Sin GEMINI_API_KEY. Operando en modo Supervisor Determinista de alto rendimiento.")

    async def supervise(self, state: MatchState, force_llm: bool = False) -> SupervisorVerdict:
        """
        Emite el veredicto definitivo sobre el partido evaluando los nodos especialistas.
        Prioriza Gemini Flash si la clave está disponible y la llamada es aprobada.
        """
        # Si no hay evaluaciones de especialistas, rechazar de inmediato
        if not state.evaluations:
            return SupervisorVerdict(
                decision="REJECT",
                selected_market="Sin Selección de Valor",
                confidence=0.0,
                recommended_stake=0,
                tactical_report="Ningún especialista detectó anomalías estadísticas o valor matemático suficiente.",
                risk_factors=["Sin disparadores en los modelos"],
                source="DETERMINISTIC"
            )

        # Si tenemos API Key y se aprueba invocación
        if self.api_key:
            try:
                verdict = await self._call_gemini_flash(state)
                if verdict:
                    return verdict
            except Exception as e:
                logger.warning(f"LLMSupervisor: Falló llamada a Gemini ({e}). Aplicando Supervisor Determinista de respaldo.")

        # Supervisor Determinista como motor primario o respaldo
        return self._deterministic_consensus(state)

    async def _call_gemini_flash(self, state: MatchState) -> Optional[SupervisorVerdict]:
        """Realiza llamada asíncrona a la API de Google Gemini Flash."""
        prompt = self._build_tactical_prompt(state)

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topK": 20,
                "topP": 0.8,
                "maxOutputTokens": 450,
                "responseMimeType": "application/json"
            }
        }

        async with httpx.AsyncClient(timeout=9.0) as client:
            url = f"{GEMINI_API_URL}?key={self.api_key}"
            response = await client.post(url, json=payload)

            if response.status_code == 404:
                # Probar URL de fallback 1.5 flash
                url = f"{GEMINI_FALLBACK_URL}?key={self.api_key}"
                response = await client.post(url, json=payload)

            if response.status_code != 200:
                logger.error(f"Error HTTP {response.status_code} desde Gemini: {response.text[:200]}")
                return None

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return self._parse_llm_json(text, state)

    def _build_tactical_prompt(self, state: MatchState) -> str:
        """Construye el prompt estructurado para el Director Técnico IA."""
        specs_summary = []
        for name, ev in state.evaluations.items():
            specs_summary.append(
                f"- [{name}] Recomienda: '{ev.recommended_market}' (Confianza: {ev.confidence}%, Cuota est.: {ev.estimated_odd}). Motivo: {ev.rationale}"
            )
        specs_text = "\n".join(specs_summary)

        conflicts_text = "\n".join([f"⚠️ {c}" for c in state.conflicts]) if state.conflicts else "Ninguno detectado."

        stats = state.live_stats
        return f"""
Actúa como un Director Técnico de Élite y Analista Cuantitativo de Apuestas Deportivas.
Analiza la siguiente situación táctica y matemática:

PARTIDO: {state.match_name} ({state.competition})
ESTADO: {'EN VIVO - Minuto ' + str(state.minute) if state.is_live else 'PRÓXIMO PRE-PARTIDO'}
MARCADOR: {state.score_home} - {state.score_away}
ESTADÍSTICAS EN VIVO:
- Posesión: Local {stats.get('possession', {}).get('home', 50)}% vs Visitante {stats.get('possession', {}).get('away', 50)}%
- Tiros al Arco: Local {stats.get('shots_on_target', {}).get('home', 0)} vs Visitante {stats.get('shots_on_target', {}).get('away', 0)}
- xG Generado: Local {stats.get('xg', {}).get('home', 0.0)} vs Visitante {stats.get('xg', {}).get('away', 0.0)}
- Córners: Local {stats.get('corners', {}).get('home', 0)} vs Visitante {stats.get('corners', {}).get('away', 0)}
- Tarjetas Rojas: Local {stats.get('red_cards', {}).get('home', 0)} vs Visitante {stats.get('red_cards', {}).get('away', 0)}

EVALUACIONES DE NODOS ESPECIALISTAS:
{specs_text}

CONFLICTOS ENTRE NODOS:
{conflicts_text}

CUOTAS DISPONIBLES:
Local: {state.odds.get('home')}, Empate: {state.odds.get('draw')}, Visitante: {state.odds.get('away')}

CRITERIO DE CALIDAD EXTREMA (MODO FRANCOTIRADOR / SNIPER):
- Tu meta primordial es CERO fallos y máxima efectividad (Efectividad proyectada > 80%).
- Preferimos CALIDAD antes que cantidad.
- Si existe contradicción entre nodos, volatilidad excesiva o falta de datos contundentes, DEBES responder con decision: "REJECT".
- Solo responde "APPROVE" si la probabilidad y la ventaja táctica son indiscutibles.

INSTRUCCIONES DE SALIDA:
Responde EXCLUSIVAMENTE en formato JSON con la siguiente estructura:
{{
  "decision": "APPROVE" | "REJECT",
  "selected_market": "Mercado exacto elegido",
  "confidence": número flotante 0-100,
  "recommended_stake": número entero 1 al 5,
  "tactical_report": "Explicación concisa y convincente del Director Técnico (máximo 3 líneas) explicando el motivo táctico",
  "risk_factors": ["factor 1", "factor 2"]
}}
"""

    def _parse_llm_json(self, raw_json: str, state: MatchState) -> Optional[SupervisorVerdict]:
        """Parsea la respuesta JSON emitida por Gemini."""
        try:
            cleaned = raw_json.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            data = json.loads(cleaned.strip())

            decision = data.get("decision", "APPROVE").upper()
            selected_market = data.get("selected_market")
            confidence = float(data.get("confidence", 75.0))
            stake = int(data.get("recommended_stake", 2))
            report = data.get("tactical_report", "Análisis táctico sintetizado por IA.")
            risks = data.get("risk_factors", [])

            # Encontrar cuota estimada
            odd_num = 1.65
            for ev in state.evaluations.values():
                if ev.recommended_market == selected_market:
                    odd_num = ev.estimated_odd
                    break

            return SupervisorVerdict(
                decision=decision,
                selected_market=selected_market or "Mercado Validado",
                confidence=min(max(confidence, 50.0), 95.0),
                recommended_stake=min(max(stake, 1), 5),
                tactical_report=report,
                risk_factors=risks,
                source="GEMINI_FLASH",
                odd_num=odd_num,
                odd_str=str(odd_num)
            )
        except Exception as e:
            logger.error(f"Error parseando JSON de Gemini: {e}")
            return None

    def _deterministic_consensus(self, state: MatchState) -> SupervisorVerdict:
        """
        Supervisor de Consenso Determinista (Modo Francotirador / Sniper).
        Prioriza CALIDAD extrema antes que cantidad.
        """
        # Ordenar evaluaciones por nivel de confianza
        sorted_evals = sorted(state.evaluations.values(), key=lambda e: e.confidence, reverse=True)
        top_eval = sorted_evals[0]

        # 1. Tolerancia cero a conflictos tácticos: si hay contradicciones, RECHAZAR pick
        if state.conflicts:
            return SupervisorVerdict(
                decision="REJECT",
                selected_market=top_eval.recommended_market,
                confidence=round(top_eval.confidence, 1),
                recommended_stake=0,
                tactical_report=f"Descartado por filtro de calidad Sniper: contradicción táctica ({state.conflicts[0]}).",
                risk_factors=state.conflicts.copy(),
                source="DETERMINISTIC",
                odd_num=top_eval.estimated_odd,
                odd_str=str(top_eval.estimated_odd)
            )

        final_confidence = top_eval.confidence

        # 2. Filtro estricto de efectividad mínima: solo se aprueba si confianza >= 78%
        if final_confidence < 78.0:
            return SupervisorVerdict(
                decision="REJECT",
                selected_market=top_eval.recommended_market,
                confidence=round(final_confidence, 1),
                recommended_stake=0,
                tactical_report=f"Descartado por umbral Sniper: confianza del {final_confidence}% insuficiente para alta efectividad (mínimo 78%).",
                risk_factors=["Confianza por debajo del umbral de alta efectividad"],
                source="DETERMINISTIC",
                odd_num=top_eval.estimated_odd,
                odd_str=str(top_eval.estimated_odd)
            )

        # Cálculo de Stake
        if final_confidence >= 82.0:
            stake = 4
        elif final_confidence >= 78.0:
            stake = 3
        else:
            stake = 2

        # Síntesis táctica natural
        if state.is_live:
            report = (
                f"Sinergia táctica en Min {state.minute}': {top_eval.rationale} "
                f"Confirmado por {top_eval.node_name} (Modo Sniper)."
            )
        else:
            report = (
                f"Validación estadística pre-partido: {top_eval.rationale} "
                f"Algoritmo cuantitativo con alta probabilidad."
            )

        risks = ["Volatilidad estándar del fútbol"]

        return SupervisorVerdict(
            decision="APPROVE",
            selected_market=top_eval.recommended_market,
            confidence=round(final_confidence, 1),
            recommended_stake=stake,
            tactical_report=report,
            risk_factors=risks,
            source="DETERMINISTIC",
            odd_num=top_eval.estimated_odd,
            odd_str=str(top_eval.estimated_odd)
        )
