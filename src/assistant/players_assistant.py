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

        # Extraer jugadores titulares si ya están definidos en el partido
        h_starters = self._extract_starters(h_lineup, members_map)
        a_starters = self._extract_starters(a_lineup, members_map)

        # Consultar IDs de los últimos partidos jugados por ambos equipos
        h_recent_ids = home_comp.get("recentMatches", [])[:5]
        a_recent_ids = away_comp.get("recentMatches", [])[:5]

        # Si aún no hay alineación confirmada (análisis horas antes), extraer el Once Habitual de partidos previos
        if not h_starters:
            h_starters, form_h_recent = await self._fetch_habitual_starting_11(
                client, h_recent_ids, home_id, all_members
            )
            if formation_home == "N/D" and form_h_recent:
                formation_home = form_h_recent

        if not a_starters:
            a_starters, form_a_recent = await self._fetch_habitual_starting_11(
                client, a_recent_ids, away_id, all_members
            )
            if formation_away == "N/D" and form_a_recent:
                formation_away = form_a_recent

        if is_confirmed:
            lineup_status_text = "🟢 Confirmada Oficial (Once titular ~1h antes)"
        else:
            lineup_status_text = "🟡 Probable (Once habitual según partidos anteriores)"

        # Enriquecer métricas de jugadores con datos históricos recientes
        enriched_home = await self._enrich_players_stats(client, h_starters, h_recent_ids, home_id)
        enriched_away = await self._enrich_players_stats(client, a_starters, a_recent_ids, away_id)

        # Seleccionar las mejores apuestas contemplando AMBOS equipos
        home_sot, away_sot = self._select_team_shots_on_target(enriched_home, enriched_away, home_name, away_name)
        home_shots, away_shots = self._select_team_total_shots(enriched_home, enriched_away, home_name, away_name)
        home_fc, away_fc = self._select_team_fouls_committed(enriched_home, enriched_away, home_name, away_name)
        home_fr, away_fr = self._select_team_fouls_received(enriched_home, enriched_away, home_name, away_name)

        # Listas combinadas para compatibilidad
        top_shots_on_target = home_sot + away_sot
        top_total_shots = home_shots + away_shots
        top_fouls_committed = home_fc + away_fc
        top_fouls_received = home_fr + away_fr

        # Combinada de props de jugador contemplando AMBOS equipos
        player_parlay = self._build_balanced_player_parlay(home_sot, away_sot, home_shots, away_shots, home_fc, away_fc)

        return {
            "match": f"{home_name} vs {away_name}",
            "home_name": home_name,
            "away_name": away_name,
            "is_confirmed": is_confirmed,
            "lineup_status_text": lineup_status_text,
            "formation_home": formation_home,
            "formation_away": formation_away,
            "home_starters_count": len(h_starters),
            "away_starters_count": len(a_starters),
            "home_starters": enriched_home,
            "away_starters": enriched_away,
            "home_shots_on_target": home_sot,
            "away_shots_on_target": away_sot,
            "home_total_shots": home_shots,
            "away_total_shots": away_shots,
            "home_fouls_committed": home_fc,
            "away_fouls_committed": away_fc,
            "home_fouls_received": home_fr,
            "away_fouls_received": away_fr,
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
                stats = {s.get("name"): s.get("value") for s in m.get("stats", [])}
                starters.append({
                    "id": mid,
                    "name": name,
                    "position": pos,
                    "stats": stats
                })
        return starters

    async def _fetch_habitual_starting_11(
        self,
        client: httpx.AsyncClient,
        recent_ids: List[int],
        team_id: int,
        all_members: list
    ) -> tuple[List[Dict[str, Any]], str]:
        """
        Para análisis horas antes del partido (sin alineación confirmada):
        Examina las alineaciones titulares que el equipo utilizó en sus últimos 2-3 partidos
        y construye el Once Habitual basándose en el historial reciente.
        """
        starters_dict: Dict[str, Dict[str, Any]] = {}
        last_formation = ""

        if recent_ids:
            tasks = [
                client.get(
                    f"https://webws.365scores.com/web/game/?gameId={gid}&langId=29&appTypeId=5",
                    timeout=10.0
                )
                for gid in recent_ids[:3]
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for r in responses:
                if isinstance(r, Exception) or not hasattr(r, "status_code") or r.status_code != 200:
                    continue
                try:
                    g_data = r.json().get("game", {})
                    h_c = g_data.get("homeCompetitor", {})
                    a_c = g_data.get("awayCompetitor", {})
                    target_comp = h_c if h_c.get("id") == team_id else a_c
                    lineup = target_comp.get("lineups", {})
                    members_map = {m["id"]: m for m in g_data.get("members", [])}

                    if not last_formation and lineup.get("formation"):
                        last_formation = str(lineup.get("formation"))

                    for m in lineup.get("members", []):
                        if m.get("statusText") == "Starting" or m.get("status") == 1:
                            mid = m.get("id")
                            m_obj = members_map.get(mid, m)
                            name = m_obj.get("name", f"Jugador_{mid}")
                            pos = m.get("position", {}).get("name", "Jugador")
                            stats = {s.get("name"): s.get("value") for s in m.get("stats", [])}

                            if name not in starters_dict:
                                starters_dict[name] = {
                                    "id": mid,
                                    "name": name,
                                    "position": pos,
                                    "starts_count": 0,
                                    "stats": stats
                                }
                            starters_dict[name]["starts_count"] += 1
                except Exception as e:
                    logger.debug(f"Error extrayendo titulares habituales: {e}")

        sorted_starters = sorted(starters_dict.values(), key=lambda x: x["starts_count"], reverse=True)
        final_starters = sorted_starters[:11]

        # Si faltan cupos para 11, rellenar con plantilla general
        if len(final_starters) < 11:
            existing_names = {s["name"].lower() for s in final_starters}
            for m in all_members:
                if m.get("competitorId") == team_id and m.get("name", "").lower() not in existing_names:
                    final_starters.append({
                        "id": m.get("id"),
                        "name": m.get("name", "Jugador"),
                        "position": "Plantilla",
                        "starts_count": 1,
                        "stats": {}
                    })
                    if len(final_starters) >= 11:
                        break

        return final_starters, last_formation

    def _fallback_key_players(self, all_members: list, competitor_id: int) -> List[Dict[str, Any]]:
        """Si la plantilla no tiene historial, extrae jugadores de la plantilla general."""
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

    def _select_team_shots_on_target(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Selecciona las mejores opciones de tiros al arco para CADA equipo."""
        def _get_top(players, team):
            out = []
            cand = [p for p in players if "portero" not in p.get("position", "").lower()]
            cand.sort(key=lambda x: x.get("avg_sot", 0), reverse=True)
            for p in cand[:2]:
                avg = p.get("avg_sot", 0)
                line = "+0.5 Disparos a Puerta" if avg < 1.8 else "+1.5 Disparos a Puerta"
                odd = "1.50 - 1.70" if line == "+0.5 Disparos a Puerta" else "1.85 - 2.15"
                out.append({
                    "player": p["name"],
                    "team": team,
                    "position": p.get("position", "Atacante"),
                    "line": line,
                    "avg": avg,
                    "odd": odd,
                    "confidence": min(88.0, round(60.0 + avg * 18.0, 1))
                })
            return out

        return _get_top(h_players, home_name), _get_top(a_players, away_name)

    def _select_team_total_shots(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Selecciona las mejores opciones de disparos totales para CADA equipo."""
        def _get_top(players, team):
            out = []
            cand = [p for p in players if "portero" not in p.get("position", "").lower()]
            cand.sort(key=lambda x: x.get("avg_shots", 0), reverse=True)
            for p in cand[:2]:
                avg = p.get("avg_shots", 0)
                line = "+1.5 Disparos Totales" if avg < 2.8 else "+2.5 Disparos Totales"
                odd = "1.55 - 1.75" if line == "+1.5 Disparos Totales" else "1.85 - 2.20"
                out.append({
                    "player": p["name"],
                    "team": team,
                    "position": p.get("position", "Atacante"),
                    "line": line,
                    "avg": avg,
                    "odd": odd,
                    "confidence": min(89.0, round(58.0 + avg * 12.0, 1))
                })
            return out

        return _get_top(h_players, home_name), _get_top(a_players, away_name)

    def _select_team_fouls_committed(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Selecciona las mejores opciones de faltas cometidas para CADA equipo."""
        def _get_top(players, team):
            out = []
            cand = [p for p in players if "portero" not in p.get("position", "").lower()]
            cand.sort(key=lambda x: x.get("avg_fouls_comm", 0), reverse=True)
            for p in cand[:2]:
                avg = p.get("avg_fouls_comm", 0)
                out.append({
                    "player": p["name"],
                    "team": team,
                    "position": p.get("position", "Pivote / Defensor"),
                    "line": "+1.5 Faltas Cometidas",
                    "avg": avg,
                    "odd": "1.60 - 1.85",
                    "confidence": min(86.0, round(60.0 + avg * 14.0, 1))
                })
            return out

        return _get_top(h_players, home_name), _get_top(a_players, away_name)

    def _select_team_fouls_received(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Selecciona las mejores opciones de faltas recibidas para CADA equipo."""
        def _get_top(players, team):
            out = []
            cand = [p for p in players if "portero" not in p.get("position", "").lower()]
            cand.sort(key=lambda x: x.get("avg_fouls_rec", 0), reverse=True)
            for p in cand[:2]:
                avg = p.get("avg_fouls_rec", 0)
                out.append({
                    "player": p["name"],
                    "team": team,
                    "position": p.get("position", "Atacante / Extremo"),
                    "line": "+1.5 Faltas Recibidas",
                    "avg": avg,
                    "odd": "1.65 - 1.90",
                    "confidence": min(85.0, round(58.0 + avg * 14.0, 1))
                })
            return out

        return _get_top(h_players, home_name), _get_top(a_players, away_name)

    def _select_top_shots_on_target(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        h, a = self._select_team_shots_on_target(h_players, a_players, home_name, away_name)
        combined = h + a
        combined.sort(key=lambda x: x.get("avg", 0), reverse=True)
        return combined[:3]

    def _select_top_total_shots(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        h, a = self._select_team_total_shots(h_players, a_players, home_name, away_name)
        combined = h + a
        combined.sort(key=lambda x: x.get("avg", 0), reverse=True)
        return combined[:3]

    def _select_top_fouls_committed(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        h, a = self._select_team_fouls_committed(h_players, a_players, home_name, away_name)
        combined = h + a
        combined.sort(key=lambda x: x.get("avg", 0), reverse=True)
        return combined[:2]

    def _select_top_fouls_received(self, h_players: list, a_players: list, home_name: str, away_name: str) -> List[Dict[str, Any]]:
        h, a = self._select_team_fouls_received(h_players, a_players, home_name, away_name)
        combined = h + a
        combined.sort(key=lambda x: x.get("avg", 0), reverse=True)
        return combined[:2]

    def _build_balanced_player_parlay(
        self,
        h_sot: list, a_sot: list,
        h_shots: list, a_shots: list,
        h_fouls: list, a_fouls: list
    ) -> str:
        """Arma una combinada de props de jugador contemplando rigurosamente AMBOS equipos."""
        legs = []
        # Pierna 1: del equipo Local
        if h_sot:
            p = h_sot[0]
            legs.append(f"  1️⃣ 🏠 <b>{p['player']}</b> ({p['team']}): {p['line']} (Prom: {p['avg']})")
        elif h_shots:
            p = h_shots[0]
            legs.append(f"  1️⃣ 🏠 <b>{p['player']}</b> ({p['team']}): {p['line']} (Prom: {p['avg']})")

        # Pierna 2: del equipo Visitante
        if a_sot:
            p = a_sot[0]
            legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): {p['line']} (Prom: {p['avg']})")
        elif a_shots:
            p = a_shots[0]
            legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): {p['line']} (Prom: {p['avg']})")
        elif a_fouls:
            p = a_fouls[0]
            legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): {p['line']} (Prom: {p['avg']})")

        # Pierna 3: faltas (cometidas o recibidas del equipo que corresponda)
        if len(legs) < 3:
            foul_cand = a_fouls[0] if (a_fouls and not any(p['team'] == a_fouls[0]['team'] for p in [h_sot[0]] if h_sot)) else (h_fouls[0] if h_fouls else None)
            if foul_cand and foul_cand['player'] not in [x.split('<b>')[1].split('</b>')[0] for x in legs]:
                legs.append(f"  3️⃣ 🟨 <b>{foul_cand['player']}</b> ({foul_cand['team']}): {foul_cand['line']} (Prom: {foul_cand['avg']})")

        if not legs:
            return "No se encontraron suficientes selecciones de jugador para armar una combinada."

        legs_text = "\n".join(legs)
        return (
            f"🎰 <b>Combinada de Props (Ambos Equipos Contemplados):</b>\n"
            f"{legs_text}\n"
            f"💵 <i>Cuota Estimada Combinada: 2.45 - 3.20</i>"
        )
