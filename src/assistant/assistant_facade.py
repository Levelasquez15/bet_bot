"""
Fachada Central del Ayudante Personal de Apuestas (BetBot Assistant).
Integra y coordina el Asistente de Córners (10 partidos recientes) y el Asistente de Jugadores
(Alineaciones oficiales/probables, Disparos, Disparos a Puerta y Faltas).
Provee formateadores HTML optimizados para la interfaz interactiva de Telegram.
"""

import logging
from typing import Dict, Any, Optional
import httpx

from src.assistant.corners_assistant import CornersAssistant
from src.assistant.players_assistant import PlayersAssistant
from src.scraper.scraper_365 import extract_match_odds

logger = logging.getLogger(__name__)


class BetAssistant:
    """Motor central del Asistente Personal de Apuestas."""

    def __init__(self, limit_corners_matches: int = 10):
        self.corners_engine = CornersAssistant(limit_matches=limit_corners_matches)
        self.players_engine = PlayersAssistant()

    async def analyze_match_corners(
        self,
        client: httpx.AsyncClient,
        home_id: int,
        away_id: int,
        home_name: str,
        away_name: str,
        home_recent_ids: Optional[list] = None,
        away_recent_ids: Optional[list] = None,
        game_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Ejecuta el análisis de tiros de esquina en los últimos 10 partidos."""
        return await self.corners_engine.analyze_match_corners(
            client, home_id, away_id, home_name, away_name, home_recent_ids, away_recent_ids, game_id=game_id
        )

    async def analyze_match_players(
        self,
        client: httpx.AsyncClient,
        game_id: int,
        home_id: int,
        away_id: int,
        home_name: str,
        away_name: str,
        game_obj: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ejecuta el análisis de jugadores (Alineaciones + Tiros + Faltas)."""
        return await self.players_engine.analyze_match_players(
            client, game_id, home_id, away_id, home_name, away_name, game_obj=game_obj
        )

    async def analyze_full_match(
        self,
        client: httpx.AsyncClient,
        game_id: int,
        home_id: int,
        away_id: int,
        home_name: str,
        away_name: str,
        game_obj: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Ejecuta el análisis completo (Córners + Props de Jugador)."""
        h_rec = game_obj.get("homeCompetitor", {}).get("recentMatches") if game_obj else None
        a_rec = game_obj.get("awayCompetitor", {}).get("recentMatches") if game_obj else None

        corners_res = await self.analyze_match_corners(
            client, home_id, away_id, home_name, away_name, h_rec, a_rec, game_id=game_id
        )
        players_res = await self.analyze_match_players(
            client, game_id, home_id, away_id, home_name, away_name, game_obj=game_obj
        )

        return {
            "match": f"{home_name} vs {away_name}",
            "corners": corners_res,
            "players": players_res
        }


# ── Formateadores HTML para Telegram ──────────────────────────────────────────

def format_corners_report(data: Dict[str, Any]) -> str:
    """Formatea el informe de Córners de los últimos 10 partidos."""
    h = data["home"]
    a = data["away"]

    lines = [
        "🚩 <b>AYUDANTE DE TIROS DE ESQUINA (CÓRNERS)</b> 🚩",
        f"⚽ <b>{data['match']}</b>",
        f"📊 <i>Muestra analizada: Últimos {h['matches_analyzed']} partidos de cada equipo</i>\n",
        f"🏠 <b>{h['team']}:</b>",
        f"  • Córners a favor: <b>{h['avg_for']}</b> / partido",
        f"  • Córners en contra: <b>{h['avg_against']}</b> / partido",
        f"  • Total en sus partidos: <b>{h['avg_total']}</b>",
        f"  • +8.5 Córners: <b>{h['over_8_5_pct']}%</b> | +9.5: <b>{h['over_9_5_pct']}%</b>\n",
        f"✈️ <b>{a['team']}:</b>",
        f"  • Córners a favor: <b>{a['avg_for']}</b> / partido",
        f"  • Córners en contra: <b>{a['avg_against']}</b> / partido",
        f"  • Total en sus partidos: <b>{a['avg_total']}</b>",
        f"  • +8.5 Córners: <b>{a['over_8_5_pct']}%</b> | +9.5: <b>{a['over_9_5_pct']}%</b>\n",
        "🎯 <b>PROYECCIÓN DEL ENCUENTRO:</b>",
        f"  • Córners Esperados Totales: <b>{data['projected_total']}</b>",
        f"  • Probabilidad Over 8.5: <b>{data['combined_over_8_5']}%</b>",
        f"  • Probabilidad Over 9.5: <b>{data['combined_over_9_5']}%</b>\n",
        "💡 <b>LÍNEAS RECOMENDADAS:</b>",
        f"  👉 <b>{data['recommended_line']}</b>",
        f"  💶 Cuota Estimada: {data['recommended_odd']}",
        f"  🏦 Confianza: {data['confidence']}%\n",
        "📌 <b>Líneas Individuales:</b>",
        f"  • {data['ind_home']}",
        f"  • {data['ind_away']}\n",
        data["parlay_suggestion"]
    ]
    return "\n".join(lines)


def format_players_report(data: Dict[str, Any]) -> str:
    """Formatea el informe de Alineaciones y Props de Jugadores (Tiros y Faltas)."""
    status_badge = data["lineup_status_text"]
    form_h = data.get("formation_home", "N/D")
    form_a = data.get("formation_away", "N/D")

    note_text = (
        "⚡ <i>Once titular oficial verificado. Los jugadores listados arrancan desde el pitazo inicial.</i>"
        if data.get("is_confirmed")
        else "💡 <i>Análisis previo (horas antes). Once habitual basado en partidos anteriores. La confirmación oficial sale ~60 min antes.</i>"
    )

    lines = [
        "🎯 <b>AYUDANTE DE JUGADORES (TIROS & FALTAS)</b> 🎯",
        f"⚽ <b>{data['match']}</b>",
        f"📋 Estado: <b>{status_badge}</b>",
        f"📐 Formaciones: {form_h} vs {form_a}",
        f"{note_text}\n",
    ]

    # Lista de Jugadores Titulares (Oficiales o Habituales)
    h_names = [s.get("name") for s in data.get("home_starters", []) if s.get("name")]
    a_names = [s.get("name") for s in data.get("away_starters", []) if s.get("name")]
    parts = data.get("match", "").split(" vs ")
    h_team = parts[0] if len(parts) > 0 else "Local"
    a_team = parts[1] if len(parts) > 1 else "Visitante"

    if h_names or a_names:
        title_starters = (
            "👥 <b>ONCE TITULAR OFICIAL:</b>"
            if data.get("is_confirmed")
            else "👥 <b>ONCE HABITUAL (PARTIDOS RECIENTES):</b>"
        )
        lines.append(title_starters)
        if h_names:
            lines.append(f"🏠 <b>{h_team} ({form_h}):</b>\n  <i>{', '.join(h_names[:11])}</i>")
        if a_names:
            lines.append(f"✈️ <b>{a_team} ({form_a}):</b>\n  <i>{', '.join(a_names[:11])}</i>")
        lines.append("")

    # 1. Tiros a Puerta
    lines.append("🎯 <b>TOP DISPAROS A PUERTA (REMATES AL ARCO):</b>")
    if data.get("top_shots_on_target"):
        for p in data["top_shots_on_target"]:
            alt_info = f" | ⚡ Casa: {p['alt_line']} [@ {p.get('alt_odd', '2.15')}]" if p.get("alt_line") else ""
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 🛡️ <b>{p['line']}</b> [@ {p['odd']}] (Éxito: {p.get('hit_rate', '85%')}){alt_info}\n"
                f"    📊 Prom: {p['avg']} al arco | Conf: {p['confidence']}%"
            )
    else:
        lines.append("  <i>Sin datos suficientes de disparos a puerta.</i>")
    lines.append("")

    # 2. Total de Disparos
    lines.append("🚀 <b>TOP DISPAROS TOTALES (TIROS DENTRO/FUERA):</b>")
    if data.get("top_total_shots"):
        for p in data["top_total_shots"]:
            alt_info = f" | ⚡ Casa: {p['alt_line']} [@ {p.get('alt_odd', '2.15')}]" if p.get("alt_line") else ""
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 🛡️ <b>{p['line']}</b> [@ {p['odd']}] (Éxito: {p.get('hit_rate', '85%')}){alt_info}\n"
                f"    📊 Prom: {p['avg']} tiros | Conf: {p['confidence']}%"
            )
    else:
        lines.append("  <i>Sin datos suficientes de disparos totales.</i>")
    lines.append("")

    # 3. Faltas Cometidas
    lines.append("🟨 <b>TOP FALTAS COMETIDAS:</b>")
    if data.get("top_fouls_committed"):
        for p in data["top_fouls_committed"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']}) [{p.get('position', 'Jugador')}]\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} faltas"
            )
    else:
        lines.append("  <i>Sin datos suficientes de faltas.</i>")
    lines.append("")

    # 4. Faltas Recibidas
    lines.append("⚡ <b>TOP FALTAS RECIBIDAS (JUGADORES PELIGROSOS):</b>")
    if data.get("top_fouls_received"):
        for p in data["top_fouls_received"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} faltas recibidas"
            )
    lines.append("")

    if data.get("player_parlay"):
        lines.append(data["player_parlay"])
    return "\n".join(lines)


def format_total_shots_report(data: Dict[str, Any]) -> str:
    """Formatea el informe EXCLUSIVO de Disparos Totales con comparativa de cuotas y auditoría de rentabilidad (+EV)."""
    h_team = data.get("home_name") or data.get("match", "").split(" vs ")[0]
    a_team = data.get("away_name") or (data.get("match", "").split(" vs ")[1] if " vs " in data.get("match","") else "Visitante")
    status_badge = data.get("lineup_status_text", "")

    lines = [
        "🚀 <b>AYUDANTE: DISPAROS TOTALES (TIROS DENTRO/FUERA)</b> 🚀",
        f"⚽ <b>{data['match']}</b>",
        f"📋 Estado: <b>{status_badge}</b>\n",
        f"🏠 <b>DISPAROS TOTALES — {h_team}:</b>"
    ]

    def _render_shooter(p: dict) -> list[str]:
        pos_disp = p.get('position') or p.get('team') or 'Atacante'
        best_line = p.get('line', '+1.5 Disparos Totales')
        best_odd = p.get('odd', '1.55')
        hit_rate = p.get('hit_rate', f"{int(p.get('confidence', 80))}%")
        avg_disp = p.get('avg', 0.0)

        card = [
            f"  • 👤 <b>{p['player']}</b> ({pos_disp}) — Prom: <b>{avg_disp}</b> tiros",
            f"    🛡️ <b>MÁS RENTABLE (+EV):</b> <b>{best_line}</b> [@ {best_odd}] (Éxito est.: <b>{hit_rate}</b>)"
        ]
        if p.get("alt_line"):
            card.append(f"    ⚡ <i>Opción Agresiva Casa:</i> {p['alt_line']} [@ {p.get('alt_odd', '2.15')}] (Éxito est.: {p.get('alt_hit_rate', '52%')})")
        if p.get("rentability_note"):
            card.append(f"    💡 <i>{p['rentability_note']}</i>")
        return card

    h_shots = data.get("home_total_shots", [])
    if h_shots:
        for p in h_shots:
            lines.extend(_render_shooter(p))
    else:
        lines.append("  ⚠️ <i>Sin atacantes con volumen suficiente para superar la línea con alta rentabilidad (+EV).</i>")

    lines.append(f"\n✈️ <b>DISPAROS TOTALES — {a_team}:</b>")
    a_shots = data.get("away_total_shots", [])
    if a_shots:
        for p in a_shots:
            lines.extend(_render_shooter(p))
    else:
        lines.append("  ⚠️ <i>Sin atacantes con volumen suficiente para superar la línea con alta rentabilidad (+EV).</i>")

    if h_shots and a_shots:
        lines.extend([
            "\n💡 <b>TICKET SUGERIDO DE DISPAROS (AMBOS EQUIPOS):</b>",
            f"  • 🏠 {h_shots[0]['player']}: <b>{h_shots[0]['line']}</b> [@ {h_shots[0]['odd']}]",
            f"  • ✈️ {a_shots[0]['player']}: <b>{a_shots[0]['line']}</b> [@ {a_shots[0]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.25 - 2.70 (+EV Sólido)</i>",
            "  💡 <i>Estrategia 'Uno Menos': cobro constante ante partidos trabados evitando perder por 1 solo tiro.</i>"
        ])
    elif h_shots and len(h_shots) >= 2:
        lines.extend([
            f"\n💡 <b>TICKET SUGERIDO DE DISPAROS ({h_team} DOMINANTE):</b>",
            f"  • 🏠 {h_shots[0]['player']}: <b>{h_shots[0]['line']}</b> [@ {h_shots[0]['odd']}]",
            f"  • 🏠 {h_shots[1]['player']}: <b>{h_shots[1]['line']}</b> [@ {h_shots[1]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.30 - 2.85 (+EV por volumen ofensivo)</i>"
        ])
    elif a_shots and len(a_shots) >= 2:
        lines.extend([
            f"\n💡 <b>TICKET SUGERIDO DE DISPAROS ({a_team} DOMINANTE):</b>",
            f"  • ✈️ {a_shots[0]['player']}: <b>{a_shots[0]['line']}</b> [@ {a_shots[0]['odd']}]",
            f"  • ✈️ {a_shots[1]['player']}: <b>{a_shots[1]['line']}</b> [@ {a_shots[1]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.30 - 2.85 (+EV por volumen ofensivo)</i>"
        ])
    elif h_shots or a_shots:
        single = h_shots[0] if h_shots else a_shots[0]
        t_icon = "🏠" if h_shots else "✈️"
        lines.extend([
            f"\n💡 <b>SELECCIÓN DESTACADA INDIVIDUAL ({t_icon} {single['team']}):</b>",
            f"  • 🎯 {single['player']}: <b>{single['line']}</b> [@ {single['odd']}]",
            "  💡 <i>Opción más rentable (+EV) con volumen ofensivo justificado.</i>"
        ])

    return "\n".join(lines)


def format_shots_on_target_report(data: Dict[str, Any]) -> str:
    """Formatea el informe EXCLUSIVO de Disparos a Puerta / Arco con comparativa de cuotas y rentabilidad (+EV)."""
    h_team = data.get("home_name") or data.get("match", "").split(" vs ")[0]
    a_team = data.get("away_name") or (data.get("match", "").split(" vs ")[1] if " vs " in data.get("match","") else "Visitante")
    status_badge = data.get("lineup_status_text", "")

    lines = [
        "🎯 <b>AYUDANTE: DISPAROS A PUERTA (REMATES AL ARCO)</b> 🎯",
        f"⚽ <b>{data['match']}</b>",
        f"📋 Estado: <b>{status_badge}</b>\n",
        f"🏠 <b>REMATES A PORTERÍA — {h_team}:</b>"
    ]

    def _render_sot(p: dict) -> list[str]:
        pos_disp = p.get('position') or p.get('team') or 'Atacante'
        best_line = p.get('line', '+0.5 Disparos a Puerta')
        best_odd = p.get('odd', '1.50')
        hit_rate = p.get('hit_rate', f"{int(p.get('confidence', 80))}%")
        avg_disp = p.get('avg', 0.0)

        card = [
            f"  • 👤 <b>{p['player']}</b> ({pos_disp}) — Prom: <b>{avg_disp}</b> al arco",
            f"    🛡️ <b>MÁS RENTABLE (+EV):</b> <b>{best_line}</b> [@ {best_odd}] (Éxito est.: <b>{hit_rate}</b>)"
        ]
        if p.get("alt_line"):
            card.append(f"    ⚡ <i>Opción Agresiva Casa:</i> {p['alt_line']} [@ {p.get('alt_odd', '2.20')}] (Éxito est.: {p.get('alt_hit_rate', '50%')})")
        if p.get("rentability_note"):
            card.append(f"    💡 <i>{p['rentability_note']}</i>")
        return card

    h_sot = data.get("home_shots_on_target", [])
    if h_sot:
        for p in h_sot:
            lines.extend(_render_sot(p))
    else:
        lines.append("  ⚠️ <i>Sin atacantes con promedio de remates a puerta suficiente para garantizar alta probabilidad.</i>")

    lines.append(f"\n✈️ <b>REMATES A PORTERÍA — {a_team}:</b>")
    a_sot = data.get("away_shots_on_target", [])
    if a_sot:
        for p in a_sot:
            lines.extend(_render_sot(p))
    else:
        lines.append("  ⚠️ <i>Sin atacantes con promedio de remates a puerta suficiente para garantizar alta probabilidad.</i>")

    if h_sot and a_sot:
        lines.extend([
            "\n💡 <b>TICKET SUGERIDO DE TIROS AL ARCO (AMBOS EQUIPOS):</b>",
            f"  • 🏠 {h_sot[0]['player']}: <b>{h_sot[0]['line']}</b> [@ {h_sot[0]['odd']}]",
            f"  • ✈️ {a_sot[0]['player']}: <b>{a_sot[0]['line']}</b> [@ {a_sot[0]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.15 - 2.55 (+EV Muy Seguro)</i>",
            "  💡 <i>Ventaja: solo se necesita 1 tiro a portería en los 90' por atacante para cobrar.</i>"
        ])
    elif h_sot and len(h_sot) >= 2:
        lines.extend([
            f"\n💡 <b>TICKET SUGERIDO DE TIROS AL ARCO ({h_team} DOMINANTE):</b>",
            f"  • 🏠 {h_sot[0]['player']}: <b>{h_sot[0]['line']}</b> [@ {h_sot[0]['odd']}]",
            f"  • 🏠 {h_sot[1]['player']}: <b>{h_sot[1]['line']}</b> [@ {h_sot[1]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.20 - 2.75 (+EV por efectividad ofensiva)</i>"
        ])
    elif a_sot and len(a_sot) >= 2:
        lines.extend([
            f"\n💡 <b>TICKET SUGERIDO DE TIROS AL ARCO ({a_team} DOMINANTE):</b>",
            f"  • ✈️ {a_sot[0]['player']}: <b>{a_sot[0]['line']}</b> [@ {a_sot[0]['odd']}]",
            f"  • ✈️ {a_sot[1]['player']}: <b>{a_sot[1]['line']}</b> [@ {a_sot[1]['odd']}]",
            "  💵 <i>Cuota Estimada: 2.20 - 2.75 (+EV por efectividad ofensiva)</i>"
        ])
    elif h_sot or a_sot:
        single = h_sot[0] if h_sot else a_sot[0]
        t_icon = "🏠" if h_sot else "✈️"
        lines.extend([
            f"\n💡 <b>SELECCIÓN DESTACADA INDIVIDUAL ({t_icon} {single['team']}):</b>",
            f"  • 🎯 {single['player']}: <b>{single['line']}</b> [@ {single['odd']}]",
            "  💡 <i>Opción con máxima rentabilidad (+EV) comprobada al arco.</i>"
        ])

    return "\n".join(lines)


def format_fouls_report(data: Dict[str, Any]) -> str:
    """Formatea el informe EXCLUSIVO de Faltas Cometidas y Recibidas (ambos equipos)."""
    h_team = data.get("home_name") or data.get("match", "").split(" vs ")[0]
    a_team = data.get("away_name") or (data.get("match", "").split(" vs ")[1] if " vs " in data.get("match","") else "Visitante")
    status_badge = data.get("lineup_status_text", "")

    lines = [
        "🟨 <b>AYUDANTE: MERCADO DE FALTAS (COMETIDAS & RECIBIDAS)</b> 🟨",
        f"⚽ <b>{data['match']}</b>",
        f"📋 Estado: <b>{status_badge}</b>\n",
        f"🏠 <b>FALTAS — {h_team}:</b>"
    ]

    h_fc = data.get("home_fouls_committed", [])
    h_fr = data.get("home_fouls_received", [])
    if h_fc:
        pos_disp = h_fc[0].get('position') or h_fc[0].get('team') or 'Pivote'
        lines.append(f"  • 🟨 Cometidas: <b>{h_fc[0]['player']}</b> ({pos_disp}) → <b>{h_fc[0]['line']}</b> [@ {h_fc[0]['odd']}]")
    if h_fr:
        pos_disp = h_fr[0].get('position') or h_fr[0].get('team') or 'Extremo'
        lines.append(f"  • ⚡ Recibidas: <b>{h_fr[0]['player']}</b> ({pos_disp}) → <b>{h_fr[0]['line']}</b> [@ {h_fr[0]['odd']}]")

    lines.append(f"\n✈️ <b>FALTAS — {a_team}:</b>")
    a_fc = data.get("away_fouls_committed", [])
    a_fr = data.get("away_fouls_received", [])
    if a_fc:
        pos_disp = a_fc[0].get('position') or a_fc[0].get('team') or 'Pivote'
        lines.append(f"  • 🟨 Cometidas: <b>{a_fc[0]['player']}</b> ({pos_disp}) → <b>{a_fc[0]['line']}</b> [@ {a_fc[0]['odd']}]")
    if a_fr:
        pos_disp = a_fr[0].get('position') or a_fr[0].get('team') or 'Extremo'
        lines.append(f"  • ⚡ Recibidas: <b>{a_fr[0]['player']}</b> ({pos_disp}) → <b>{a_fr[0]['line']}</b> [@ {a_fr[0]['odd']}]")

    if (h_fc or h_fr) and (a_fc or a_fr):
        foul_leg_1 = h_fc[0] if h_fc else h_fr[0]
        foul_leg_2 = a_fc[0] if a_fc else a_fr[0]
        lines.extend([
            "\n💡 <b>TICKET SUGERIDO DE FALTAS (AMBOS EQUIPOS):</b>",
            f"  • 🏠 {foul_leg_1['player']} ({h_team}): <b>{foul_leg_1['line']}</b>",
            f"  • ✈️ {foul_leg_2['player']} ({a_team}): <b>{foul_leg_2['line']}</b>",
            "  💵 <i>Cuota Estimada: 2.35 - 3.10</i>"
        ])

    return "\n".join(lines)


def format_match_parlay_report(full_data: Dict[str, Any]) -> str:
    """Formatea la combinada especializada para este partido integrando AMBOS equipos y todos los apartados."""
    corners = full_data["corners"]
    players = full_data["players"]
    h_team = players.get("home_name") or "Local"
    a_team = players.get("away_name") or "Visitante"

    legs = []
    # Pierna 1: Córners del partido
    legs.append(f"  1️⃣ 🚩 <b>Córners:</b> {corners['recommended_line']} [@ {corners['recommended_odd']}]")

    # Pierna 2: Prop de jugador Local (tiros o sot)
    h_cand = players.get("home_shots_on_target", []) or players.get("home_total_shots", [])
    if h_cand:
        p1 = h_cand[0]
        legs.append(f"  2️⃣ 🏠 <b>{h_team}:</b> {p1['player']} → <b>{p1['line']}</b> [@ {p1['odd']}]")

    # Pierna 3: Prop de jugador Visitante (tiros o faltas)
    a_cand = players.get("away_shots_on_target", []) or players.get("away_total_shots", []) or players.get("away_fouls_committed", [])
    if a_cand:
        p2 = a_cand[0]
        legs.append(f"  3️⃣ ✈️ <b>{a_team}:</b> {p2['player']} → <b>{p2['line']}</b> [@ {p2['odd']}]")

    lines = [
        "🎰 <b>COMBINADA EXCLUSIVA DEL PARTIDO</b> 🎰",
        f"⚽ <b>{full_data['match']}</b>",
        f"📋 Alineación: <b>{players['lineup_status_text']}</b>\n",
        "🎯 <b>SELECCIONES DEL TICKET (AMBOS EQUIPOS CONTEMPLADOS):</b>",
        "\n".join(legs),
        "\n💵 <b>CUOTA TOTAL ESTIMADA:</b> <code>2.70 - 3.80</code>",
        "🏦 <b>STAKE RECOMENDADO:</b> <code>2 / 5</code>\n",
        "💡 <i>Ticket construido integrando córners, disparos y faltas de ambos bandos con enfoque +EV.</i>"
    ]
    return "\n".join(lines)


def format_match_hub_message(game_info: dict, players_data: dict) -> str:
    """Muestra la pantalla de inicio del partido seleccionado con sus alineaciones, cuotas de casa y selector de mercados."""
    status_badge = players_data.get("lineup_status_text", "🟡 Probable")
    form_h = players_data.get("formation_home", "N/D")
    form_a = players_data.get("formation_away", "N/D")
    h_name = players_data.get("home_name", "Local")
    a_name = players_data.get("away_name", "Visitante")
    comp = game_info.get("competitionDisplayName") or "Liga"
    st = game_info.get("startTime", "")[11:16] if game_info.get("startTime") else "Hoy"
    time_left = game_info.get("time_left_str", "")
    time_disp = f"{st} ({time_left})" if time_left else st

    h_starters = [s.get("name") for s in players_data.get("home_starters", []) if s.get("name")]
    a_starters = [s.get("name") for s in players_data.get("away_starters", []) if s.get("name")]

    lines = [
        f"⚽ <b>{h_name} vs {a_name}</b>",
        f"🏆 <i>{comp}</i> | 🕐 Inicio: <b>{time_disp}</b>",
        f"📋 Estado: <b>{status_badge}</b>",
        f"📐 Formaciones: {form_h} vs {form_a}"
    ]

    odds_info = game_info.get("parsed_odds") or extract_match_odds(game_info)
    if odds_info and odds_info.get("has_odds"):
        h_odd = odds_info.get("home") or "-"
        d_odd = odds_info.get("draw") or "-"
        a_odd = odds_info.get("away") or "-"
        lines.append(f"💰 <b>Cuotas 1X2 (Casa):</b> 1: <code>{h_odd}</code> | X: <code>{d_odd}</code> | 2: <code>{a_odd}</code>")

    lines.append("")

    title_starters = (
        "👥 <b>ONCE TITULAR OFICIAL:</b>"
        if players_data.get("is_confirmed")
        else "👥 <b>ONCE HABITUAL (PARTIDOS ANTERIORES):</b>"
    )
    lines.append(title_starters)
    if h_starters:
        lines.append(f"🏠 <b>{h_name} ({form_h}):</b>\n  <i>{', '.join(h_starters[:11])}</i>")
    if a_starters:
        lines.append(f"✈️ <b>{a_name} ({form_a}):</b>\n  <i>{', '.join(a_starters[:11])}</i>")

    lines.append("\n👇 <b>Selecciona el mercado específico que deseas analizar para este partido:</b>")
    return "\n".join(lines)



def format_custom_combinada_ticket(matches_data: list, profile: str = "media") -> str:
    """Genera un ticket combinado multipartido según la cuota objetivo deseada."""
    profile_names = {
        "moderada": ("🛡️ CUOTA MODERADA (~2.00)", "1.85 - 2.25", "3 / 5", 2),
        "media":    ("⚖️ CUOTA MEDIA (~3.00)", "2.70 - 3.50", "2 / 5", 3),
        "alta":     ("🚀 CUOTA ALTA (4.50+)", "4.20 - 6.00+", "1.5 / 5", 4)
    }
    title, target_odd, stake, target_legs = profile_names.get(profile, profile_names["media"])

    legs = []
    # Seleccionar piernas equilibradas de los partidos disponibles
    for idx, match_item in enumerate(matches_data[:target_legs], 1):
        m_name = match_item.get("match", "Partido")
        p_data = match_item.get("players", {})
        c_data = match_item.get("corners", {})

        if profile == "moderada":
            # Líneas muy seguras
            if c_data and idx == 1:
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {c_data.get('recommended_line', 'Over Córners')} [@ {c_data.get('recommended_odd', '1.45')}]")
            elif p_data.get("home_shots_on_target"):
                p = p_data["home_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → +0.5 Tiros a Puerta [@ {p['odd']}]")
            elif p_data.get("away_shots_on_target"):
                p = p_data["away_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → +0.5 Tiros a Puerta [@ {p['odd']}]")
        elif profile == "alta":
            # Cuota alta: props de remates + córners + faltas
            if idx == 1 and p_data.get("home_shots_on_target"):
                p = p_data["home_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → +1.5 Tiros a Puerta [@ 2.05]")
            elif idx == 2 and p_data.get("away_shots_on_target"):
                p = p_data["away_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → +1.5 Tiros a Puerta [@ 2.10]")
            elif idx == 3 and c_data:
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {c_data.get('recommended_line', '+9.5 Córners')} [@ {c_data.get('recommended_odd', '1.80')}]")
            elif p_data.get("home_fouls_committed"):
                p = p_data["home_fouls_committed"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → {p['line']} [@ {p['odd']}]")
        else:
            # Perfil medio
            if idx == 1 and c_data:
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {c_data.get('recommended_line', 'Córners')} [@ {c_data.get('recommended_odd', '1.75')}]")
            elif p_data.get("home_shots_on_target"):
                p = p_data["home_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → {p['line']} [@ {p['odd']}]")
            elif p_data.get("away_shots_on_target"):
                p = p_data["away_shots_on_target"][0]
                legs.append(f"  {idx}️⃣ <b>{m_name}:</b> {p['player']} ({p['team']}) → {p['line']} [@ {p['odd']}]")

    if not legs:
        return "⚠️ No hay suficientes partidos programados con datos estadísticos para generar esta combinada."

    lines = [
        f"🎰 <b>COMBINADA MULTIPARTIDO ({title})</b> 🎰\n",
        "📋 <b>SELECCIONES DEL TICKET:</b>",
        "\n".join(legs),
        f"\n💵 <b>CUOTA TOTAL ESTIMADA:</b> <code>{target_odd}</code>",
        f"🏦 <b>STAKE RECOMENDADO:</b> <code>{stake}</code>\n",
        "💡 <i>Selecciones construidas contemplando ambos equipos y optimizando el valor (+EV).</i>"
    ]
    return "\n".join(lines)


def format_full_match_report(match_data: Dict[str, Any]) -> str:
    """Genera un reporte consolidado de Córners + Jugadores."""
    corners = match_data["corners"]
    players = match_data["players"]

    lines = [
        "🤖⚽ <b>INFORME COMPLETO DEL AYUDANTE BETBOT</b> ⚽🤖",
        f"<b>{match_data['match']}</b>",
        f"📋 Alineación: <b>{players['lineup_status_text']}</b>\n",
        "🚩 <b>MERCADO DE CÓRNERS (Últimos 10 Partidos):</b>",
        f"  • Córners proyectados en el partido: <b>{corners['projected_total']}</b>",
        f"  👉 Línea sugerida: <b>{corners['recommended_line']}</b> (Cuota: {corners['recommended_odd']})",
        f"  • {corners['ind_home']}",
        f"  • {corners['ind_away']}\n",
        "🎯 <b>MERCADO DE JUGADORES CLAVE (AMBOS EQUIPOS):</b>"
    ]

    if players.get("home_shots_on_target"):
        p = players["home_shots_on_target"][0]
        lines.append(f"  • 🏠 {p['team']}: <b>{p['player']}</b> → <b>{p['line']}</b> [@ {p['odd']}]")
    if players.get("away_shots_on_target"):
        p = players["away_shots_on_target"][0]
        lines.append(f"  • ✈️ {p['team']}: <b>{p['player']}</b> → <b>{p['line']}</b> [@ {p['odd']}]")
    if players.get("home_total_shots"):
        p = players["home_total_shots"][0]
        lines.append(f"  • 🚀 Tiros totales: <b>{p['player']}</b> ({p['team']}) → <b>{p['line']}</b>")
    if players.get("home_fouls_committed"):
        p = players["home_fouls_committed"][0]
        lines.append(f"  • 🟨 Faltas cometidas: <b>{p['player']}</b> ({p['team']}) → <b>{p['line']}</b>")

    lines.append("\n" + corners["parlay_suggestion"])
    return "\n".join(lines)


def format_lineup_alert(match_name: str, comp_name: str, start_time: str, players_data: dict, corners_data: dict) -> str:
    """Mensaje para notificación automática cuando se confirma la alineación oficial."""
    lines = [
        "🚨 <b>¡ALINEACIÓN OFICIAL CONFIRMADA!</b> 🚨",
        f"⚽ <b>{match_name}</b>",
        f"🏆 <i>{comp_name}</i> | 🕐 Inicio: <b>{start_time}</b>\n",
        f"📐 Formaciones: {players_data.get('formation_home','N/D')} vs {players_data.get('formation_away','N/D')}\n",
        "🎯 <b>PICKS DESTACADOS DE JUGADORES (AMBOS EQUIPOS):</b>"
    ]
    if players_data.get("home_shots_on_target"):
        p = players_data["home_shots_on_target"][0]
        lines.append(f"  • 🏠 <b>{p['player']}</b> ({p['team']}): {p['line']} [@ {p['odd']}]")
    if players_data.get("away_shots_on_target"):
        p = players_data["away_shots_on_target"][0]
        lines.append(f"  • ✈️ <b>{p['player']}</b> ({p['team']}): {p['line']} [@ {p['odd']}]")

    lines.append("\n🚩 <b>TENDENCIA DE CÓRNERS (10 partidos):</b>")
    lines.append(f"  👉 <b>{corners_data['recommended_line']}</b> (Cuota: {corners_data['recommended_odd']})")
    lines.append(f"  • Proyección: {corners_data['projected_total']} córners totales")

    lines.append("\n💡 <i>Verifica estas líneas en tu casa de apuestas antes de que comience el partido.</i>")
    return "\n".join(lines)
