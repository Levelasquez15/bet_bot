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

    lines = [
        "🎯 <b>AYUDANTE DE JUGADORES (TIROS & FALTAS)</b> 🎯",
        f"⚽ <b>{data['match']}</b>",
        f"📋 Estado de Alineación: <b>{status_badge}</b>",
        f"📐 Formaciones: {form_h} vs {form_a}\n",
    ]

    # 1. Tiros a Puerta
    lines.append("🎯 <b>TOP DISPAROS A PUERTA (REMATES AL ARCO):</b>")
    if data["top_shots_on_target"]:
        for p in data["top_shots_on_target"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} al arco | Conf: {p['confidence']}%"
            )
    else:
        lines.append("  <i>Sin datos suficientes de disparos a puerta.</i>")
    lines.append("")

    # 2. Total de Disparos
    lines.append("🚀 <b>TOP DISPAROS TOTALES (TIROS DENTRO/FUERA):</b>")
    if data["top_total_shots"]:
        for p in data["top_total_shots"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} tiros | Conf: {p['confidence']}%"
            )
    else:
        lines.append("  <i>Sin datos suficientes de disparos totales.</i>")
    lines.append("")

    # 3. Faltas Cometidas
    lines.append("🟨 <b>TOP FALTAS COMETIDAS:</b>")
    if data["top_fouls_committed"]:
        for p in data["top_fouls_committed"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']}) [{p['position']}]\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} faltas"
            )
    else:
        lines.append("  <i>Sin datos suficientes de faltas.</i>")
    lines.append("")

    # 4. Faltas Recibidas
    lines.append("⚡ <b>TOP FALTAS RECIBIDAS (JUGADORES PELIGROSOS):</b>")
    if data["top_fouls_received"]:
        for p in data["top_fouls_received"]:
            lines.append(
                f"  • <b>{p['player']}</b> ({p['team']})\n"
                f"    👉 <b>{p['line']}</b> [@ {p['odd']}] | Prom: {p['avg']} faltas recibidas"
            )
    lines.append("")

    lines.append(data["player_parlay"])
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
        "🎯 <b>MERCADO DE JUGADORES CLAVE:</b>"
    ]

    if players["top_shots_on_target"]:
        top_sot = players["top_shots_on_target"][0]
        lines.append(f"  • 🎯 Tiros al arco: <b>{top_sot['player']}</b> ({top_sot['team']}) → <b>{top_sot['line']}</b>")

    if players["top_total_shots"]:
        top_ts = players["top_total_shots"][0]
        lines.append(f"  • 🚀 Tiros totales: <b>{top_ts['player']}</b> ({top_ts['team']}) → <b>{top_ts['line']}</b>")

    if players["top_fouls_committed"]:
        top_fc = players["top_fouls_committed"][0]
        lines.append(f"  • 🟨 Faltas cometidas: <b>{top_fc['player']}</b> ({top_fc['team']}) → <b>{top_fc['line']}</b>")

    lines.append("\n" + corners["parlay_suggestion"])
    return "\n".join(lines)


def format_lineup_alert(match_name: str, comp_name: str, start_time: str, players_data: dict, corners_data: dict) -> str:
    """Mensaje para notificación automática cuando se confirma la alineación oficial."""
    lines = [
        "🚨 <b>¡ALINEACIÓN OFICIAL CONFIRMADA!</b> 🚨",
        f"⚽ <b>{match_name}</b>",
        f"🏆 <i>{comp_name}</i> | 🕐 Inicio: <b>{start_time}</b>\n",
        f"📐 Formaciones: {players_data.get('formation_home','N/D')} vs {players_data.get('formation_away','N/D')}\n",
        "🎯 <b>PICKS DESTACADOS DE JUGADORES:</b>"
    ]
    if players_data.get("top_shots_on_target"):
        top_sot = players_data["top_shots_on_target"][0]
        lines.append(f"  • 🎯 <b>{top_sot['player']}</b>: {top_sot['line']} [@ {top_sot['odd']}]")

    if players_data.get("top_total_shots"):
        top_ts = players_data["top_total_shots"][0]
        lines.append(f"  • 🚀 <b>{top_ts['player']}</b>: {top_ts['line']} [@ {top_ts['odd']}]")

    if players_data.get("top_fouls_committed"):
        top_fc = players_data["top_fouls_committed"][0]
        lines.append(f"  • 🟨 <b>{top_fc['player']}</b>: {top_fc['line']} [@ {top_fc['odd']}]")

    lines.append("\n🚩 <b>TENDENCIA DE CÓRNERS (10 partidos):</b>")
    lines.append(f"  👉 <b>{corners_data['recommended_line']}</b> (Cuota: {corners_data['recommended_odd']})")
    lines.append(f"  • Proyección: {corners_data['projected_total']} córners totales")

    lines.append("\n💡 <i>Verifica estas líneas en tu casa de apuestas antes de que comience el partido.</i>")
    return "\n".join(lines)
