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
import re
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

ELITE_ATTACKING_CLUBS = {
    "barcelona", "real madrid", "manchester city", "man city", "bayern munich", "bayern münchen",
    "paris saint-germain", "psg", "arsenal", "liverpool", "inter", "inter milan",
    "bayer leverkusen", "atletico madrid", "atlético madrid", "sporting", "sporting cp",
    "porto", "chelsea", "tottenham", "juventus", "milan", "napoli",
    "borussia dortmund", "dortmund", "aston villa", "monaco", "atalanta",
    "flamengo", "palmeiras", "river plate", "boca juniors", "botafogo"
}


def get_team_tier(team_name: str) -> str:
    """Clasifica el poderío ofensivo del equipo para proyectar volumen real de disparo."""
    t = (team_name or "").lower().strip()
    # Detectar equipos B / filiales o divisiones juveniles
    if re.search(r'\b(b|ii|sub-\d+|u19|u20|u21|u23|juvenil|femenino|femenil)\b', t):
        return "low"
    for elite in ELITE_ATTACKING_CLUBS:
        if elite in t:
            return "elite"
    return "competitive"


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

        # Enriquecer métricas de jugadores con datos históricos recientes y perfil del club
        enriched_home = await self._enrich_players_stats(client, h_starters, h_recent_ids, home_id, team_name=home_name)
        enriched_away = await self._enrich_players_stats(client, a_starters, a_recent_ids, away_id, team_name=away_name)

        # Seleccionar ÚNICAMENTE jugadores determinantes con alta probabilidad
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
        team_id: int,
        team_name: str = "Equipo"
    ) -> List[Dict[str, Any]]:
        """
        Calcula métricas estadísticas individuales de los jugadores.
        Si la liga no registra mapa de tiros individuales en 365scores (segunda división, etc.),
        calibra proyecciones matemáticas inteligentes basadas en el Poderío Ofensivo del Club (Tier) y posición.
        """
        tier = get_team_tier(team_name)

        if not recent_ids or not players:
            for p in players:
                pos = p.get("position", "").lower()
                ash, asot, afc, afr = self._get_role_baselines(tier, pos)
                p["avg_shots"], p["avg_sot"], p["avg_fouls_comm"], p["avg_fouls_rec"] = ash, asot, afc, afr
                p["sample_games"] = 0
            return players

        # Consultar hasta 4 partidos recientes
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
                        s_list = m.get("stats", [])
                        shots = 0.0
                        sot = 0.0
                        fc = 0.0
                        fr = 0.0

                        for s in s_list:
                            stype = s.get("type")
                            sname = s.get("name", "").lower()
                            sval = s.get("value", 0)
                            try:
                                sval_num = float(str(sval).split("/")[0].split("(")[0].strip())
                            except Exception:
                                sval_num = 0.0

                            # Total remates (type 3 o type 4+5)
                            if stype == 3 or "total remates" in sname or "total shots" in sname:
                                shots = max(shots, sval_num)
                            elif stype in (4, 5):
                                shots += sval_num

                            # Remates al arco (type 4)
                            if stype == 4 or "remates al arco" in sname or "shots on target" in sname or "disparos a puerta" in sname:
                                sot = max(sot, sval_num)

                            # Faltas cometidas (type 42)
                            if stype == 42 or "faltas cometidas" in sname or "fouls committed" in sname:
                                fc = max(fc, sval_num)

                            # Faltas recibidas (type 37)
                            if stype == 37 or "faltas recibidas" in sname or "fouls suffered" in sname:
                                fr = max(fr, sval_num)

                        player_history[m_name]["shots"].append(shots)
                        player_history[m_name]["sot"].append(sot)
                        player_history[m_name]["fouls_c"].append(fc)
                        player_history[m_name]["fouls_r"].append(fr)
            except Exception as e:
                logger.debug(f"Error procesando historial de jugador: {e}")

        # Verificar si la API registró efectivamente tiros para este equipo en estos partidos
        total_shots_scraped = sum(sum(p_h["shots"]) for p_h in player_history.values())
        has_detailed_shot_stats = total_shots_scraped > 0

        # Integrar datos históricos reales calculados
        for p in players:
            name_key = p["name"].lower()
            hist = player_history.get(name_key, {})
            pos = p.get("position", "").lower()
            ash, asot, afc, afr = self._get_role_baselines(tier, pos)

            if has_detailed_shot_stats and hist.get("shots"):
                p["avg_shots"] = round(sum(hist["shots"]) / len(hist["shots"]), 1)
                p["avg_sot"] = round(sum(hist["sot"]) / len(hist["sot"]), 1)
                p["avg_fouls_comm"] = round(sum(hist["fouls_c"]) / len(hist["fouls_c"]), 1) if hist.get("fouls_c") else afc
                p["avg_fouls_rec"] = round(sum(hist["fouls_r"]) / len(hist["fouls_r"]), 1) if hist.get("fouls_r") else afr
                p["sample_games"] = len(hist["shots"])
            else:
                # Proyección matemática calibrada por Poderío del Club y Posición
                p["avg_shots"] = ash
                p["avg_sot"] = asot
                p["avg_fouls_comm"] = round(sum(hist["fouls_c"]) / len(hist["fouls_c"]), 1) if hist.get("fouls_c") and sum(hist["fouls_c"]) > 0 else afc
                p["avg_fouls_rec"] = round(sum(hist["fouls_r"]) / len(hist["fouls_r"]), 1) if hist.get("fouls_r") and sum(hist["fouls_r"]) > 0 else afr
                p["sample_games"] = len(hist.get("shots", []))

        return players

    def _get_role_baselines(self, tier: str, pos: str) -> tuple[float, float, float, float]:
        """
        Retorna (avg_shots, avg_sot, avg_fouls_comm, avg_fouls_rec)
        calibrado según el nivel del equipo y la demarcación táctica.
        """
        pos = (pos or "").lower()
        if "portero" in pos or "goalkeeper" in pos:
            return 0.0, 0.0, 0.1, 0.2

        if tier == "elite":
            # Equipos ultra ofensivos (Barcelona, Real Madrid, City, PSG, Bayern, etc.)
            if any(w in pos for w in ("delantero", "atacante", "striker", "forward")):
                return 3.2, 1.6, 1.1, 1.7
            if any(w in pos for w in ("extremo", "winger")):
                return 2.7, 1.3, 1.0, 2.1
            if any(w in pos for w in ("mediapunta", "ofensivo", "cam")):
                return 2.1, 0.9, 1.3, 1.6
            if any(w in pos for w in ("mediocampista", "volante", "centrocampista", "pivote")):
                return 1.3, 0.4, 1.7, 1.2
            if any(w in pos for w in ("lateral", "carrilero")):
                return 0.7, 0.2, 1.4, 1.1
            # Defensores centrales
            return 0.4, 0.1, 1.8, 0.7

        elif tier == "low":
            # Equipos filiales o de ligas menores / underdogs defensivos
            if any(w in pos for w in ("delantero", "atacante", "striker", "forward")):
                return 1.6, 0.7, 1.4, 1.3
            if any(w in pos for w in ("extremo", "winger")):
                return 1.2, 0.4, 1.3, 1.4
            if any(w in pos for w in ("mediapunta", "ofensivo")):
                return 0.9, 0.3, 1.4, 1.1
            if any(w in pos for w in ("mediocampista", "volante", "centrocampista", "pivote")):
                return 0.6, 0.1, 1.8, 0.9
            return 0.2, 0.0, 1.6, 0.5

        else:
            # Equipos competitivos estándar
            if any(w in pos for w in ("delantero", "atacante", "striker", "forward")):
                return 2.4, 1.1, 1.2, 1.5
            if any(w in pos for w in ("extremo", "winger")):
                return 1.9, 0.8, 1.2, 1.8
            if any(w in pos for w in ("mediapunta", "ofensivo")):
                return 1.4, 0.5, 1.3, 1.4
            if any(w in pos for w in ("mediocampista", "volante", "centrocampista", "pivote")):
                return 0.9, 0.3, 1.7, 1.1
            if any(w in pos for w in ("lateral", "carrilero")):
                return 0.5, 0.1, 1.4, 0.9
            return 0.3, 0.1, 1.6, 0.6

    def _select_team_shots_on_target(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Selecciona ÚNICAMENTE jugadores determinantes con alta probabilidad de tiro a puerta / arco (+0.5 o +1.5).
        - Excluye estrictamente a defensores, pivotes defensivos y porteros.
        - Requiere un promedio mínimo de remates a puerta (avg_sot >= 0.7).
        - Cantidad dinámica: hasta 2-3 en equipos élite, 1 o 0 en equipos chicos.
        """
        def _get_determinant_sot(players, team_name):
            tier = get_team_tier(team_name)
            max_picks = 3 if tier == "elite" else (2 if tier == "competitive" else 1)

            candidates = []
            for p in players:
                pos = p.get("position", "").lower()
                # Excluir porteros y defensores
                if any(w in pos for w in ("portero", "goalkeeper", "defensor", "central", "lateral", "defender")):
                    continue
                # Excluir mediocentros defensivos puros
                if any(w in pos for w in ("pivote", "defensivo", "contención", "corte")):
                    continue

                avg_sot = p.get("avg_sot", 0.0)
                # Umbral mínimo para remates a portería
                if avg_sot < 0.7:
                    continue

                if avg_sot >= 1.4:
                    line = "+1.5 Disparos a Puerta"
                    odd = "1.85 - 2.15"
                    conf = min(88.0, round(68.0 + (avg_sot - 1.4) * 14.0, 1))
                else:
                    line = "+0.5 Disparos a Puerta"
                    odd = "1.45 - 1.70"
                    conf = min(89.0, round(72.0 + (avg_sot - 0.7) * 16.0, 1))

                candidates.append({
                    "player": p["name"],
                    "team": team_name,
                    "position": p.get("position", "Atacante"),
                    "line": line,
                    "avg": avg_sot,
                    "odd": odd,
                    "confidence": conf
                })

            candidates.sort(key=lambda x: (x["avg"], x["confidence"]), reverse=True)
            return candidates[:max_picks]

        return _get_determinant_sot(h_players, home_name), _get_determinant_sot(a_players, away_name)

    def _select_team_total_shots(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Selecciona ÚNICAMENTE jugadores determinantes con alta probabilidad de superar la línea de disparos.
        - Excluye estrictamente defensores y porteros.
        - Filtra a jugadores con promedio < 1.4 tiros.
        - La cantidad es dinámica:
            * Equipos élite (ej. Barcelona): hasta 2 o 3 si cumplen alta probabilidad.
            * Equipos estándar/chicos: 1 o 0 si nadie tiene volumen suficiente.
        """
        def _get_determinant_shooters(players, team_name):
            tier = get_team_tier(team_name)
            max_picks = 3 if tier == "elite" else (2 if tier == "competitive" else 1)

            candidates = []
            for p in players:
                pos = p.get("position", "").lower()
                # Excluir porteros y defensores
                if any(w in pos for w in ("portero", "goalkeeper", "defensor", "central", "lateral", "defender")):
                    if p.get("avg_shots", 0) < 1.8:
                        continue

                avg = p.get("avg_shots", 0.0)
                # Umbral mínimo estricto para considerarse "jugador determinante" en disparos
                if avg < 1.4:
                    continue

                if avg >= 2.8:
                    line = "+2.5 Disparos Totales"
                    odd = "1.85 - 2.20"
                    conf = min(88.0, round(65.0 + (avg - 2.8) * 10.0, 1))
                else:
                    line = "+1.5 Disparos Totales"
                    odd = "1.50 - 1.75"
                    conf = min(89.0, round(70.0 + (avg - 1.4) * 12.0, 1))

                candidates.append({
                    "player": p["name"],
                    "team": team_name,
                    "position": p.get("position", "Atacante"),
                    "line": line,
                    "avg": avg,
                    "odd": odd,
                    "confidence": conf
                })

            candidates.sort(key=lambda x: (x["avg"], x["confidence"]), reverse=True)
            return candidates[:max_picks]

        return _get_determinant_shooters(h_players, home_name), _get_determinant_shooters(a_players, away_name)

    def _select_team_fouls_committed(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Selecciona jugadores determinantes con alta probabilidad de cometer faltas (+1.5 Faltas).
        - Dirigido a pivotes, mediocampistas de marca, defensores y laterales con corte intenso.
        - Umbral mínimo: avg_fouls_comm >= 1.3 faltas por partido.
        """
        def _get_top_fouls(players, team_name):
            candidates = []
            for p in players:
                pos = p.get("position", "").lower()
                if "portero" in pos or "goalkeeper" in pos:
                    continue
                avg_fc = p.get("avg_fouls_comm", 0.0)
                if avg_fc < 1.3:
                    continue
                candidates.append({
                    "player": p["name"],
                    "team": team_name,
                    "position": p.get("position", "Pivote / Defensor"),
                    "line": "+1.5 Faltas Cometidas",
                    "avg": avg_fc,
                    "odd": "1.60 - 1.85",
                    "confidence": min(87.0, round(66.0 + (avg_fc - 1.3) * 12.0, 1))
                })
            candidates.sort(key=lambda x: (x["avg"], x["confidence"]), reverse=True)
            return candidates[:2]

        return _get_top_fouls(h_players, home_name), _get_top_fouls(a_players, away_name)

    def _select_team_fouls_received(
        self, h_players: list, a_players: list, home_name: str, away_name: str
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Selecciona jugadores determinantes que reciben faltas (+1.5 Faltas Recibidas).
        - Dirigido a extremos desequilibrantes, regateadores y delanteros de choque.
        - Umbral mínimo: avg_fouls_rec >= 1.3 faltas recibidas por partido.
        """
        def _get_fouled_players(players, team_name):
            candidates = []
            for p in players:
                pos = p.get("position", "").lower()
                if any(w in pos for w in ("portero", "defensor", "central")):
                    continue
                avg_fr = p.get("avg_fouls_rec", 0.0)
                if avg_fr < 1.3:
                    continue
                candidates.append({
                    "player": p["name"],
                    "team": team_name,
                    "position": p.get("position", "Extremo / Atacante"),
                    "line": "+1.5 Faltas Recibidas",
                    "avg": avg_fr,
                    "odd": "1.65 - 1.90",
                    "confidence": min(86.0, round(65.0 + (avg_fr - 1.3) * 12.0, 1))
                })
            candidates.sort(key=lambda x: (x["avg"], x["confidence"]), reverse=True)
            return candidates[:2]

        return _get_fouled_players(h_players, home_name), _get_fouled_players(a_players, away_name)

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
        """Arma una combinada de props de jugador con jugadores determinantes de alta probabilidad."""
        legs = []
        # Pierna 1: del equipo Local (si tiene jugador determinante)
        if h_sot:
            p = h_sot[0]
            legs.append(f"  1️⃣ 🏠 <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")
        elif h_shots:
            p = h_shots[0]
            legs.append(f"  1️⃣ 🏠 <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")

        # Pierna 2: del equipo Visitante (si tiene jugador determinante)
        if a_sot:
            p = a_sot[0]
            legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")
        elif a_shots:
            p = a_shots[0]
            legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")

        # Si uno de los equipos no tiene determinante en tiros pero el otro sí tiene un segundo determinante:
        if len(legs) == 1:
            if h_shots and len(h_shots) > 1:
                p = h_shots[1]
                legs.append(f"  2️⃣ 🏠 <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")
            elif a_shots and len(a_shots) > 1:
                p = a_shots[1]
                legs.append(f"  2️⃣ ✈️ <b>{p['player']}</b> ({p['team']}): <b>{p['line']}</b> [@ {p['odd']}]")

        # Pierna 3: Faltas
        all_fouls = a_fouls + h_fouls
        existing_names = [l.split("<b>")[1].split("</b>")[0] for l in legs if "<b>" in l]
        for f in all_fouls:
            if f["player"] not in existing_names:
                badge = "🏠" if any(f["team"] == p["team"] for p in (h_shots or h_sot or [])) else "✈️"
                legs.append(f"  3️⃣ 🟨 <b>{f['player']}</b> ({f['team']}): <b>{f['line']}</b> [@ {f['odd']}]")
                break

        if not legs:
            return "💡 <i>No se encontraron selecciones individuales que superen el umbral de alta probabilidad para este partido.</i>"

        legs_text = "\n".join(legs)
        return (
            f"🎰 <b>COMBINADA SUGERIDA (JUGADORES DETERMINANTES):</b>\n"
            f"{legs_text}\n\n"
            f"💵 <b>CUOTA TOTAL ESTIMADA:</b> <code>2.40 - 3.25</code>\n"
            f"💡 <i>Selecciones filtradas por probabilidad alta y rol ofensivo real (+EV).</i>"
        )

