"""
Módulo Especialista en Análisis de Jugadores (Player Props).
Evalúa la alineación (🟢 Oficial Confirmada vs 🟡 Probable/Proyectada),
formación táctica de ambos equipos, y calcula las mejores selecciones en:
1. Disparos Totales de Jugador (+1.5, +2.5)
2. Disparos a Puerta / Remates al Arco (+0.5, +1.5)
3. Faltas Cometidas y Faltas Recibidas (+1.5)
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)


class PlayersAssistant:
    """Calculador y extractor de métricas de rendimiento individual de jugadores."""

    async def fetch_game_lineup_data(self, client: httpx.AsyncClient, game_id: int) -> Dict[str, Any]:
        """Consulta los detalles completos del partido incluyendo alineaciones y miembros."""
        try:
            url = f"https://webws.365scores.com/web/game/?gameId={game_id}&langId=29&appTypeId=5"
            resp = await client.get(url, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("game", {})
        except Exception as e:
            logger.error(f"Error consultando alineaciones para game {game_id}: {e}")
        return {}

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
        """
        Analiza las alineaciones y estadísticas de jugadores para el partido especificado.
        """
        if not game_obj:
            game_obj = await self.fetch_game_lineup_data(client, game_id)

        home_comp = game_obj.get("homeCompetitor", {})
        away_comp = game_obj.get("awayCompetitor", {})
        all_members = game_obj.get("members", [])
        members_map = {m.get("id"): m.get("name", "Jugador") for m in all_members if m.get("id")}

        h_lineup = home_comp.get("lineups") or {}
        a_lineup = away_comp.get("lineups") or {}

        # Determinar estado de alineación
        h_status = str(h_lineup.get("status", "")).strip().capitalize()
        a_status = str(a_lineup.get("status", "")).strip().capitalize()

        is_confirmed = (h_status == "Confirmado" or a_status == "Confirmado")
        has_any_lineup = bool(h_lineup.get("members") or a_lineup.get("members"))

        lineup_status_text = "🟢 Confirmada (Oficial)" if is_confirmed else ("🟡 Probable / Proyectada" if has_any_lineup else "⚪ No Disponible Aún")

        formation_home = h_lineup.get("formation", "N/D")
        formation_away = a_lineup.get("formation", "N/D")

        # Extraer jugadores titulares
        h_starters = self._extract_starters(h_lineup, members_map)
        a_starters = self._extract_starters(a_lineup, members_map)

        # Si aún no hay alineación cargada, extraer jugadores clave de la plantilla
        if not h_starters:
            h_starters = self._fallback_key_players(all_members, home_id)
        if not a_starters:
            a_starters = self._fallback_key_players(all_members, away_id)

        # Consultar estadísticas de los últimos partidos para enriquecer a los jugadores
        h_recent_ids = home_comp.get("recentMatches", [])[:5]
        a_recent_ids = away_comp.get("recentMatches", [])[:5]

        # Enriquecer métricas de jugadores con datos históricos recientes
        enriched_home = await self._enrich_players_stats(client, h_starters, h_recent_ids, home_id)
        enriched_away = await self._enrich_players_stats(client, a_starters, a_recent_ids, away_id)

        # Seleccionar las mejores apuestas de jugador
        top_shots_on_target = self._select_top_shots_on_target(enriched_home, enriched_away, home_name, away_name)
        top_total_shots = self._select_top_total_shots(enriched_home, enriched_away, home_name, away_name)
        top_fouls_committed = self._select_top_fouls_committed(enriched_home, enriched_away, home_name, away_name)
        top_fouls_received = self._select_top_fouls_received(enriched_home, enriched_away, home_name, away_name)

        # Combinada de props de jugador
        player_parlay = self._build_player_parlay(top_shots_on_target, top_total_shots, top_fouls_committed)

        return {
            "match": f"{home_name} vs {away_name}",
            "is_confirmed": is_confirmed,
            "lineup_status_text": lineup_status_text,
            "formation_home": formation_home,
            "formation_away": formation_away,
            "home_starters_count": len(h_starters),
            "away_starters_count": len(a_starters),
            "home_starters": enriched_home,
            "away_starters": enriched_away,
            "top_shots_on_target": top_shots_on_target,
            "top_total_shots": top_total_shots,
            "top_fouls_committed": top_fouls_committed,
            "top_fouls_received": top_fouls_received,
            "player_parlay": player_parlay
        }

    def _extract_starters(self, lineup_dict: dict, members_map: dict) -> List[Dict[str, Any]]:
        """Filtra los 11 titulares del objeto de alineación."""
        starters = []
        members = lineup_dict.get("members", [])
        for m in members:
            status_text = str(m.get("statusText", "")).strip().lower()
            if status_text in ("starting", "titular") or m.get("status") == 1:
                mid = m.get("id")
                name = members_map.get(mid, m.get("name", "Titular"))
                pos = m.get("position", {}).get("name", "Jugador")
                # Extraer stats directas del partido si están disponibles
                stats = {s.get("name"): s.get("value") for s in m.get("stats", [])}
                starters.append({
                    "id": mid,
                    "name": name,
                    "position": pos,
                    "stats": stats
                })
        return starters

    def _fallback_key_players(self, all_members: list, competitor_id: int) -> List[Dict[str, Any]]:
        """Si la alineación no ha salido, extrae jugadores de la plantilla general."""
        players = []
        for m in all_members:
            if m.get("competitorId") == competitor_id:
                name = m.get("name", "Jugador")
                mid = m.get("id")
                players.append({
                    "id": mid,
                    "name": name,
                    "position": "Plantilla",
                    "stats": {}
                })
        return players[:11]

    async def _enrich_players_stats(
        self,
        client: httpx.AsyncClient,
        players: List[Dict[str, Any]],
        recent_ids: List[int],
        team_id: int
    ) -> List[Dict[str, Any]]:
        """
        Calcula el promedio de disparos, disparos a puerta y faltas
        de los jugadores a través de los partidos recientes del equipo.
        """
        if not recent_ids or not players:
            # Asignar promedios estimados según posición
            for p in players:
                pos = p.get("position", "").lower()
                if "delantero" in pos or "atacante" in pos:
                    p["avg_shots"] = 2.4
                    p["avg_sot"] = 1.2
                    p["avg_fouls_comm"] = 1.1
                    p["avg_fouls_rec"] = 1.4
                elif "mediocampista" in pos or "volante" in pos:
                    p["avg_shots"] = 1.5
                    p["avg_sot"] = 0.6
                    p["avg_fouls_comm"] = 1.5
                    p["avg_fouls_rec"] = 1.2
                elif "defensor" in pos or "central" in pos or "lateral" in pos:
                    p["avg_shots"] = 0.6
                    p["avg_sot"] = 0.2
                    p["avg_fouls_comm"] = 1.6
                    p["avg_fouls_rec"] = 0.8
                else:
                    p["avg_shots"] = 0.0
                    p["avg_sot"] = 0.0
                    p["avg_fouls_comm"] = 0.1
                    p["avg_fouls_rec"] = 0.2
            return players

        # Consultar hasta 4 partidos recientes para medir rendimiento individual real
        tasks = [
            client.get(
                f"https://webws.365scores.com/web/game/?gameId={gid}&langId=29&appTypeId=5",
                timeout=10.0
            )
            for gid in recent_ids[:4]
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        player_history = {p["name"].lower(): {"shots": [], "sot": [], "fouls_c": [], "fouls_r": []} for p in players}

        for r in responses:
            if isinstance(r, Exception) or not hasattr(r, "status_code") or r.status_code != 200:
                continue
            try:
                g_data = r.json().get("game", {})
                h_c = g_data.get("homeCompetitor", {})
                a_c = g_data.get("awayCompetitor", {})
                target_comp = h_c if h_c.get("id") == team_id else a_c
                lineup = target_comp.get("lineups", {})
                members_map = {m["id"]: m["name"] for m in g_data.get("members", [])}

                for m in lineup.get("members", []):
                    mid = m.get("id")
                    m_name = members_map.get(mid, m.get("name", "")).lower()
                    if m_name in player_history:
                        s_map = {s.get("name"): s.get("value") for s in m.get("stats", [])}
                        try:
                            shots = int(float(s_map.get("Total Remates", 0)))
                        except (ValueError, TypeError):
                            shots = 0
                        try:
                            sot = int(float(s_map.get("Remates al arco", 0)))
                        except (ValueError, TypeError):
                            sot = 0
                        try:
                            fc = int(float(s_map.get("Faltas cometidas", 0)))
                        except (ValueError, TypeError):
                            fc = 0
                        try:
                            fr = int(float(s_map.get("Faltas recibidas", 0)))
                        except (ValueError, TypeError):
                            fr = 0

                        player_history[m_name]["shots"].append(shots)
                        player_history[m_name]["sot"].append(sot)
                        player_history[m_name]["fouls_c"].append(fc)
                        player_history[m_name]["fouls_r"].append(fr)
            except Exception as e:
                logger.debug(f"Error procesando historial de jugador: {e}")

        # Integrar datos históricos reales calculados
        for p in players:
            name_key = p["name"].lower()
            hist = player_history.get(name_key, {})
            pos = p.get("position", "").lower()

            if hist.get("shots"):
                p["avg_shots"] = round(sum(hist["shots"]) / len(hist["shots"]), 1)
                p["avg_sot"] = round(sum(hist["sot"]) / len(hist["sot"]), 1)
                p["avg_fouls_comm"] = round(sum(hist["fouls_c"]) / len(hist["fouls_c"]), 1)
                p["avg_fouls_rec"] = round(sum(hist["fouls_r"]) / len(hist["fouls_r"]), 1)
                p["sample_games"] = len(hist["shots"])
            else:
                # Proyección de base por rol
                if "delantero" in pos or "atacante" in pos:
                    p["avg_shots"], p["avg_sot"], p["avg_fouls_comm"], p["avg_fouls_rec"] = 2.5, 1.3, 1.1, 1.5
                elif "mediocampista" in pos or "volante" in pos:
                    p["avg_shots"], p["avg_sot"], p["avg_fouls_comm"], p["avg_fouls_rec"] = 1.6, 0.7, 1.6, 1.2
                elif "defensor" in pos or "central" in pos or "lateral" in pos:
                    p["avg_shots"], p["avg_sot"], p["avg_fouls_comm"], p["avg_fouls_rec"] = 0.6, 0.2, 1.7, 0.9
                else:
                    p["avg_shots"], p["avg_sot"], p["avg_fouls_comm"], p["avg_fouls_rec"] = 0.0, 0.0, 0.1, 0.1
                p["sample_games"] = 0

        return players

    def _select_top_shots_on_target(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        """Selecciona las mejores 3 opciones de tiros a puerta / remates al arco."""
        all_p = [dict(p, team=home_name) for p in h_players] + [dict(p, team=away_name) for p in a_players]
        # Filtrar porteros
        candidates = [p for p in all_p if "portero" not in p.get("position", "").lower()]
        candidates.sort(key=lambda x: x.get("avg_sot", 0), reverse=True)

        picks = []
        for p in candidates[:3]:
            avg = p.get("avg_sot", 0)
            line = "+0.5 Disparos a Puerta" if avg < 1.8 else "+1.5 Disparos a Puerta"
            odd = "1.50 - 1.70" if line == "+0.5 Disparos a Puerta" else "1.85 - 2.15"
            picks.append({
                "player": p["name"],
                "team": p["team"],
                "position": p.get("position", "Atacante"),
                "line": line,
                "avg": avg,
                "odd": odd,
                "confidence": min(88.0, round(60.0 + avg * 18.0, 1))
            })
        return picks

    def _select_top_total_shots(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        """Selecciona las mejores 3 opciones de tiros totales."""
        all_p = [dict(p, team=home_name) for p in h_players] + [dict(p, team=away_name) for p in a_players]
        candidates = [p for p in all_p if "portero" not in p.get("position", "").lower()]
        candidates.sort(key=lambda x: x.get("avg_shots", 0), reverse=True)

        picks = []
        for p in candidates[:3]:
            avg = p.get("avg_shots", 0)
            line = "+1.5 Disparos Totales" if avg < 2.8 else "+2.5 Disparos Totales"
            odd = "1.55 - 1.75" if line == "+1.5 Disparos Totales" else "1.85 - 2.20"
            picks.append({
                "player": p["name"],
                "team": p["team"],
                "position": p.get("position", "Atacante"),
                "line": line,
                "avg": avg,
                "odd": odd,
                "confidence": min(89.0, round(58.0 + avg * 12.0, 1))
            })
        return picks

    def _select_top_fouls_committed(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        """Selecciona las mejores opciones de faltas cometidas por jugadores."""
        all_p = [dict(p, team=home_name) for p in h_players] + [dict(p, team=away_name) for p in a_players]
        candidates = [p for p in all_p if "portero" not in p.get("position", "").lower()]
        candidates.sort(key=lambda x: x.get("avg_fouls_comm", 0), reverse=True)

        picks = []
        for p in candidates[:2]:
            avg = p.get("avg_fouls_comm", 0)
            picks.append({
                "player": p["name"],
                "team": p["team"],
                "position": p.get("position", "Pivote / Defensor"),
                "line": "+1.5 Faltas Cometidas",
                "avg": avg,
                "odd": "1.60 - 1.85",
                "confidence": min(86.0, round(60.0 + avg * 14.0, 1))
            })
        return picks

    def _select_top_fouls_received(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        """Selecciona las mejores opciones de faltas recibidas por jugadores."""
        all_p = [dict(p, team=home_name) for p in h_players] + [dict(p, team=away_name) for p in a_players]
        candidates = [p for p in all_p if "portero" not in p.get("position", "").lower()]
        candidates.sort(key=lambda x: x.get("avg_fouls_rec", 0), reverse=True)

        picks = []
        for p in candidates[:2]:
            avg = p.get("avg_fouls_rec", 0)
            picks.append({
                "player": p["name"],
                "team": p["team"],
                "position": p.get("position", "Atacante / Extremo"),
                "line": "+1.5 Faltas Recibidas",
                "avg": avg,
                "odd": "1.65 - 1.90",
                "confidence": min(85.0, round(58.0 + avg * 14.0, 1))
            })
        return picks

    def _build_player_parlay(self, sot_picks: list, shot_picks: list, foul_picks: list) -> str:
        """Arma una combinada de props de jugador optimizada."""
        legs = []
        if sot_picks:
            top_sot = sot_picks[0]
            legs.append(f"  1️⃣ <b>{top_sot['player']}</b> ({top_sot['team']}): {top_sot['line']} (Prom: {top_sot['avg']})")
        if shot_picks and len(shot_picks) > 1:
            top_shot = shot_picks[1]
            legs.append(f"  2️⃣ <b>{top_shot['player']}</b> ({top_shot['team']}): {top_shot['line']} (Prom: {top_shot['avg']})")
        if foul_picks:
            top_foul = foul_picks[0]
            legs.append(f"  3️⃣ <b>{top_foul['player']}</b> ({top_foul['team']}): {top_foul['line']} (Prom: {top_foul['avg']})")

        if not legs:
            return "No se encontraron suficientes selecciones de jugador para armar una combinada."

        legs_text = "\n".join(legs)
        return (
            f"🎰 <b>Combinada de Props de Jugador Sugerida:</b>\n"
            f"{legs_text}\n"
            f"💵 <i>Cuota Estimada Combinada: 2.20 - 2.80</i>"
        )
