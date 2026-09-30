"""
Pick Tracker — Gestiona y rastrea el rendimiento de las señales enviadas.
Respaldado por la base de datos relacional SQLite/PostgreSQL (src.db.repositories).
"""

import logging
from typing import List, Dict, Any, Optional
from src.db.repositories import PickRepository

logger = logging.getLogger(__name__)


def record_pick(pick: dict, game_id: Any, score_at_pick: str, pick_type: str = "live") -> str:
    """Registra un pick en la base de datos y retorna su ID."""
    return PickRepository.record_pick(pick, game_id, score_at_pick, pick_type)


def update_pick_result(pick_id: str, status: str, final_score: str) -> None:
    """Actualiza el resultado y calcula el beneficio neto."""
    PickRepository.update_pick_result(pick_id, status, final_score)


def get_pending_picks() -> List[dict]:
    """Devuelve los pronósticos pendientes de verificar."""
    raw_picks = PickRepository.get_pending_picks()
    # Mapear nombres de columnas a la interfaz esperada por el worker
    result = []
    for r in raw_picks:
        p = dict(r)
        p["match"] = p.get("match_name", "")
        p["timestamp"] = p.get("created_at", "")
        p["type"] = p.get("pick_type", "live")
        result.append(p)
    return result


def get_stats() -> dict:
    """Calcula métricas globales de acierto y rentabilidad."""
    return PickRepository.get_stats()


def get_recent_picks(limit: int = 10) -> List[dict]:
    """Devuelve los últimos N picks ordenados por fecha."""
    raw = PickRepository.get_recent_picks(limit=limit)
    result = []
    for r in raw:
        p = dict(r)
        p["match"] = p.get("match_name", "")
        p["timestamp"] = p.get("created_at", "")
        p["type"] = p.get("pick_type", "live")
        result.append(p)
    return result


def verify_pick(pick: dict, final_home: int, final_away: int, stats: Optional[dict] = None) -> str:
    """
    Determina si un pick fue GANADO, PERDIDO o NO_VERIFICABLE
    basándose en el marcador final y estadísticas avanzadas del partido.
    Cubre: Córners, Tarjetas, 1X2, Doble Oportunidad, Over/Under, BTTS y Próximo Gol.
    """
    import re
    market = pick.get("market", "").lower().strip()
    total  = final_home + final_away

    # ── 1. Córners (Estadísticas Avanzadas) ────────────────────────────────────
    if "córner" in market or "corner" in market:
        if stats and stats.get("has_stats"):
            c_home = int(stats.get("corners", {}).get("home", 0))
            c_away = int(stats.get("corners", {}).get("away", 0))
            total_corners = c_home + c_away

            m_over = re.search(r"(?:más de|over)\s+(\d+(?:\.\d+)?)", market)
            m_under = re.search(r"(?:menos de|under)\s+(\d+(?:\.\d+)?)", market)

            if m_over:
                line = float(m_over.group(1))
                return "GANADO" if total_corners > line else "PERDIDO"
            elif m_under:
                line = float(m_under.group(1))
                return "GANADO" if total_corners < line else "PERDIDO"
            else:
                return "GANADO" if total_corners >= 9 else "PERDIDO"
        return "NO_VERIFICABLE"

    # ── 2. Tarjetas (Estadísticas Avanzadas) ───────────────────────────────────
    if "tarjeta" in market or "card" in market:
        if stats and stats.get("has_stats"):
            y_home = int(stats.get("yellow_cards", {}).get("home", 0))
            y_away = int(stats.get("yellow_cards", {}).get("away", 0))
            r_home = int(stats.get("red_cards", {}).get("home", 0))
            r_away = int(stats.get("red_cards", {}).get("away", 0))
            total_cards = y_home + y_away + (r_home + r_away)

            m_over = re.search(r"(?:más de|over)\s+(\d+(?:\.\d+)?)", market)
            m_under = re.search(r"(?:menos de|under)\s+(\d+(?:\.\d+)?)", market)

            if m_over:
                line = float(m_over.group(1))
                return "GANADO" if total_cards > line else "PERDIDO"
            elif m_under:
                line = float(m_under.group(1))
                return "GANADO" if total_cards < line else "PERDIDO"
            else:
                return "GANADO" if total_cards >= 4 else "PERDIDO"
        return "NO_VERIFICABLE"

    # ── 3. Mercados de Línea de Goles (Over / Under) ───────────────────────────
    if "más de 0.5" in market or "over 0.5" in market:
        return "GANADO" if total > 0 else "PERDIDO"

    if "más de 1.5" in market or "over 1.5" in market:
        return "GANADO" if total > 1 else "PERDIDO"

    if "más de 2.5" in market or "over 2.5" in market:
        return "GANADO" if total > 2 else "PERDIDO"

    if "más de 3.5" in market or "over 3.5" in market:
        return "GANADO" if total > 3 else "PERDIDO"

    if "menos de 1.5" in market or "under 1.5" in market:
        return "GANADO" if total < 2 else "PERDIDO"

    if "menos de 2.5" in market or "under 2.5" in market:
        return "GANADO" if total < 3 else "PERDIDO"

    if "menos de 3.5" in market or "under 3.5" in market:
        return "GANADO" if total < 4 else "PERDIDO"

    # ── 4. Mercados 1X2 (Ganador del Partido) ───────────────────────────────────
    if "gana local" in market:
        return "GANADO" if final_home > final_away else "PERDIDO"

    if "gana visitante" in market:
        return "GANADO" if final_away > final_home else "PERDIDO"

    if "empate" in market:
        return "GANADO" if final_home == final_away else "PERDIDO"

    # ── 5. Doble Oportunidad ──────────────────────────────────────────────────
    if "doble oportunidad: 1x" in market or "1x" in market:
        return "GANADO" if final_home >= final_away else "PERDIDO"

    if "doble oportunidad: x2" in market or "x2" in market:
        return "GANADO" if final_away >= final_home else "PERDIDO"

    if "doble oportunidad: 12" in market or "12" in market:
        return "GANADO" if final_home != final_away else "PERDIDO"

    # ── 6. Ambos Marcan (BTTS) ────────────────────────────────────────────────
    if ("ambos equipos marcarán: sí" in market) or ("btts" in market and "sí" in market):
        return "GANADO" if final_home > 0 and final_away > 0 else "PERDIDO"

    if "ambos equipos marcarán: no" in market or ("btts" in market and "no" in market):
        return "GANADO" if (final_home == 0 or final_away == 0) else "PERDIDO"

    # ── 7. Próximo Gol (Live) ─────────────────────────────────────────────────
    if "próximo gol" in market:
        try:
            score_parts = str(pick.get("score_at_pick", "0-0")).split("-")
            sh_at = int(score_parts[0].strip())
            sa_at = int(score_parts[1].strip())
            total_at = sh_at + sa_at
            return "GANADO" if total > total_at else "PERDIDO"
        except Exception:
            return "NO_VERIFICABLE"

    return "NO_VERIFICABLE"
