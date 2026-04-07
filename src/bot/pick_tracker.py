"""
Pick Tracker — guarda cada señal enviada y rastrea su resultado.
Almacena en picks_history.json para persistencia.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

PICKS_FILE = "picks_history.json"
BOGOTA_TZ  = timezone(timedelta(hours=-5))


def _now_str() -> str:
    return datetime.now(tz=BOGOTA_TZ).strftime("%Y-%m-%d %H:%M")


def load_picks() -> List[dict]:
    if not os.path.exists(PICKS_FILE):
        return []
    try:
        with open(PICKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error leyendo picks_history.json: {e}")
        return []


def save_picks(picks: List[dict]) -> None:
    try:
        with open(PICKS_FILE, "w", encoding="utf-8") as f:
            json.dump(picks, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando picks_history.json: {e}")


def record_pick(pick: dict, game_id: Any, score_at_pick: str, pick_type: str = "live") -> str:
    """
    Registra un pick enviado. Devuelve el pick_id generado.
    pick_type: 'live' o 'upcoming'
    """
    picks = load_picks()
    pick_id = str(uuid.uuid4())[:8]

    entry = {
        "id":             pick_id,
        "game_id":        str(game_id),
        "match":          pick["match"],
        "market":         pick["market"],
        "minute":         str(pick.get("minute", "?")),
        "score_at_pick":  score_at_pick,
        "confidence":     pick["confidence"],
        "reason":         pick.get("reason", ""),
        "type":           pick_type,
        "timestamp":      _now_str(),
        "status":         "PENDIENTE",   # PENDIENTE | GANADO | PERDIDO | NO_VERIFICABLE
        "final_score":    None,
        "verified_at":    None,
    }
    picks.append(entry)
    save_picks(picks)
    logger.info(f"Pick registrado [{pick_id}]: {pick['match']} → {pick['market']}")
    return pick_id


def update_pick_result(pick_id: str, status: str, final_score: str) -> None:
    """Actualiza el resultado de un pick (GANADO/PERDIDO/NO_VERIFICABLE)."""
    picks = load_picks()
    for p in picks:
        if p["id"] == pick_id:
            p["status"]      = status
            p["final_score"] = final_score
            p["verified_at"] = _now_str()
            break
    save_picks(picks)
    logger.info(f"Pick [{pick_id}] actualizado → {status} ({final_score})")


def get_pending_picks() -> List[dict]:
    """Devuelve todos los picks con status PENDIENTE."""
    return [p for p in load_picks() if p["status"] == "PENDIENTE"]


def get_stats() -> dict:
    """Calcula estadísticas globales."""
    picks = load_picks()
    total     = len(picks)
    ganados   = sum(1 for p in picks if p["status"] == "GANADO")
    perdidos  = sum(1 for p in picks if p["status"] == "PERDIDO")
    pendientes= sum(1 for p in picks if p["status"] == "PENDIENTE")
    no_verif  = sum(1 for p in picks if p["status"] == "NO_VERIFICABLE")
    verificados = ganados + perdidos
    efectividad = round((ganados / verificados * 100), 1) if verificados > 0 else 0.0

    return {
        "total":        total,
        "ganados":      ganados,
        "perdidos":     perdidos,
        "pendientes":   pendientes,
        "no_verif":     no_verif,
        "efectividad":  efectividad,
    }


def get_recent_picks(limit: int = 10) -> List[dict]:
    """Devuelve los últimos N picks ordenados por más recientes."""
    picks = load_picks()
    return picks[-limit:][::-1]  # Más recientes primero


def verify_pick(pick: dict, final_home: int, final_away: int) -> str:
    """
    Determina si un pick fue GANADO, PERDIDO o NO_VERIFICABLE
    basándose en el marcador final.
    """
    market = pick["market"].lower()
    total  = final_home + final_away

    if "más de 2.5" in market or "over 2.5" in market:
        return "GANADO" if total > 2 else "PERDIDO"

    if "más de 1.5" in market or "over 1.5" in market:
        return "GANADO" if total > 1 else "PERDIDO"

    if "más de 3.5" in market or "over 3.5" in market:
        return "GANADO" if total > 3 else "PERDIDO"

    if "menos de 1.5" in market or "under 1.5" in market:
        return "GANADO" if total < 2 else "PERDIDO"

    if "ambos equipos marcarán: sí" in market or "btts" in market and "sí" in market:
        return "GANADO" if final_home > 0 and final_away > 0 else "PERDIDO"

    if "ambos equipos marcarán: no" in market:
        return "GANADO" if final_home == 0 or final_away == 0 else "PERDIDO"

    if "próximo gol" in market:
        # Si el marcador cambió desde que se enviaron el pick → GANADO
        try:
            score_parts = pick["score_at_pick"].split("-")
            sh_at = int(score_parts[0].strip())
            sa_at = int(score_parts[1].strip())
            total_at  = sh_at + sa_at
            return "GANADO" if total > total_at else "PERDIDO"
        except Exception:
            return "NO_VERIFICABLE"

    if "córner" in market or "corner" in market:
        return "NO_VERIFICABLE"

    return "NO_VERIFICABLE"
