"""
Generador inteligente de Apuestas Combinadas (Parlays de 2-3 selecciones).
Combina pronósticos con alto valor matemático y probabilidad contrastada.
"""

from typing import List, Dict, Any, Optional
import itertools


def generate_best_parlay(picks: List[Dict[str, Any]], legs: int = 3, min_combined_odd: float = 2.0, max_combined_odd: float = 6.0) -> Optional[Dict[str, Any]]:
    """
    Selecciona la mejor combinación de N selecciones independientes (diferentes partidos)
    con mayor probabilidad acumulada y cuota atractiva.
    """
    if len(picks) < legs:
        return None

    # Filtrar picks elegibles con probabilidad de éxito alta
    eligible_picks = [p for p in picks if p.get("confidence", 0) >= 64.0]
    if len(eligible_picks) < legs:
        eligible_picks = picks[:legs]

    best_parlay = None
    best_score = -1.0

    # Evaluar combinaciones posibles sin repetir partido
    for combo in itertools.combinations(eligible_picks, legs):
        # Asegurar partidos únicos
        matches = set(p["match"] for p in combo)
        if len(matches) < legs:
            continue

        # Calcular cuota combinada y probabilidad acumulada
        combined_prob = 1.0
        combined_odd = 1.0

        for p in combo:
            prob = p.get("confidence", 65.0) / 100.0
            odd = p.get("odd_num", 1.55)
            combined_prob *= prob
            combined_odd *= odd

        combined_odd = round(combined_odd, 2)
        combined_prob_pct = round(combined_prob * 100.0, 1)

        # Filtrar rango de cuota deseado (entre 2.0 y 6.0)
        if min_combined_odd <= combined_odd <= max_combined_odd:
            # Score de selección = probabilidad combinada * cuota (valor global)
            score = combined_prob * combined_odd
            if score > best_score:
                best_score = score
                best_parlay = {
                    "legs": list(combo),
                    "legs_count": legs,
                    "combined_odd": combined_odd,
                    "combined_prob": combined_prob_pct,
                    "recommended_stake": 2 if combined_prob_pct >= 28.0 else 1
                }

    # Si ninguna combinación cayó en el rango estricto, tomar los N picks más seguros
    if not best_parlay and len(eligible_picks) >= legs:
        sorted_picks = sorted(eligible_picks, key=lambda x: x.get("confidence", 0), reverse=True)[:legs]
        comb_odd = 1.0
        comb_prob = 1.0
        for p in sorted_picks:
            comb_odd *= p.get("odd_num", 1.55)
            comb_prob *= (p.get("confidence", 65.0) / 100.0)

        best_parlay = {
            "legs": sorted_picks,
            "legs_count": legs,
            "combined_odd": round(comb_odd, 2),
            "combined_prob": round(comb_prob * 100.0, 1),
            "recommended_stake": 2
        }

    return best_parlay


def format_parlay_message(parlay: Dict[str, Any]) -> str:
    """Formatea la combinada en un mensaje elegante con HTML para Telegram."""
    lines = [
        f"🎰 <b>COMBINADA INTELIGENTE ({parlay['legs_count']} Selecciones)</b> 🎰\n",
        f"💶 <b>Cuota Total:</b> 👉 <b>{parlay['combined_odd']}</b>",
        f"📊 <b>Probabilidad Acumulada:</b> 👉 <b>{parlay['combined_prob']}%</b>\n",
        "📋 <b>Selecciones del Ticket:</b>"
    ]

    for i, leg in enumerate(parlay["legs"], 1):
        odd_str = f" [@ {leg.get('odd_num', '1.55')}]" if leg.get('odd_num') else ""
        lines.append(
            f"{i}. ⚽ <b>{leg['match']}</b>\n"
            f"   🎯 <i>{leg['market']}</i>{odd_str}\n"
            f"   💡 Confianza: {leg['confidence']}%\n"
        )

    lines.append(f"🏦 <b>STAKE RECOMENDADO:</b> {parlay['recommended_stake']}")
    return "\n".join(lines)
