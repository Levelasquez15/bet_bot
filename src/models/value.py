"""
Módulo de Value Betting y Gestión Matemática de Stake (Kelly Criterion).
Calcula si una apuesta tiene Valor Esperado Positivo (EV > 0).
"""

from typing import Dict, Any, Optional


def calculate_value(
    model_prob: float,
    bookmaker_odd: Optional[float],
    min_edge: float = 0.04
) -> Dict[str, Any]:
    """
    Evalúa si una apuesta tiene valor matemático frente a la casa de apuestas.

    model_prob: Probabilidad estimada por nuestro modelo (ej: 0.65 para 65%)
    bookmaker_odd: Cuota decimal ofrecida por la casa (ej: 1.85)
    min_edge: Margen de ventaja mínimo requerido sobre la casa (defecto: 4%)
    """
    if not bookmaker_odd or bookmaker_odd <= 1.0 or model_prob <= 0.0 or model_prob >= 1.0:
        return {
            "has_value": False,
            "ev": 0.0,
            "ev_pct": 0.0,
            "edge": 0.0,
            "fair_odd": round(1.0 / max(model_prob, 0.01), 2),
            "bookmaker_odd": bookmaker_odd,
            "recommended_stake": 1
        }

    fair_odd = round(1.0 / model_prob, 2)
    implied_prob = 1.0 / bookmaker_odd

    # Fórmula de Valor Esperado: EV = (Prob * (Cuota - 1)) - (1 - Prob)
    ev = (model_prob * (bookmaker_odd - 1.0)) - (1.0 - model_prob)
    edge = model_prob - implied_prob
    ev_pct = round(ev * 100.0, 1)

    has_value = (ev > 0.0) and (edge >= min_edge)

    # Cálculo de Stake proporcional (Criterio Kelly Fraccional 1/4)
    # b = odd - 1, f* = (bp - q) / b
    b = bookmaker_odd - 1.0
    q = 1.0 - model_prob
    full_kelly = (b * model_prob - q) / b if b > 0 else 0.0
    fractional_kelly = max(0.0, full_kelly * 0.25)

    # Mapear a stake entre 1 y 5 unidades
    if fractional_kelly >= 0.08 or ev_pct >= 15.0:
        stake = 4
    elif fractional_kelly >= 0.05 or ev_pct >= 10.0:
        stake = 3
    elif has_value or model_prob >= 0.70:
        stake = 2
    else:
        stake = 1

    # Stake 5 solo para oportunidades extraordinarias (EV > 20% y Prob > 75%)
    if ev_pct >= 20.0 and model_prob >= 0.75:
        stake = 5

    return {
        "has_value": has_value,
        "ev": round(ev, 4),
        "ev_pct": ev_pct,
        "edge": round(edge, 4),
        "fair_odd": fair_odd,
        "bookmaker_odd": round(bookmaker_odd, 2),
        "recommended_stake": stake
    }
