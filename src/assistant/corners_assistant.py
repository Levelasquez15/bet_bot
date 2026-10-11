"""
Módulo Especialista en Análisis de Tiros de Esquina (Córners).
Analiza el historial de los últimos N partidos (por defecto 10) de ambos equipos
contra sus rivales previos (no solo H2H), calculando córners a favor, en contra,
promedios acumulados, frecuencias Over/Under y líneas recomendadas.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)


class CornersAssistant:
    """Calculador y modelador estadístico para mercados de tiros de esquina."""

    def __init__(self, limit_matches: int = 10):
        self.limit_matches = limit_matches

    async def fetch_team_recent_corner_history(
        self,
        client: httpx.AsyncClient,
        competitor_id: int,
        team_name: str,
        limit: int = 10,
        recent_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Consulta los últimos partidos jugados por un equipo y extrae sus estadísticas de córners.
        """
        match_ids = []
        if recent_ids:
            match_ids = recent_ids[:limit]
        else:
            try:
                url = f"https://webws.365scores.com/web/games/current/?competitors={competitor_id}&langId=29&appTypeId=5"
                resp = await client.get(url, timeout=12.0)
                if resp.status_code == 200:
                    games = resp.json().get("games", [])
                    finished = [g for g in games if g.get("statusGroup") == 4]
                    match_ids = [g.get("id") for g in finished if g.get("id")][:limit]
            except Exception as e:
                logger.debug(f"Error consultando partidos del equipo {team_name}: {e}")

        if not match_ids:
            return {
                "team": team_name,
                "matches_analyzed": 0,
                "avg_for": 5.0,
                "avg_against": 4.5,
                "avg_total": 9.5,
                "over_8_5_pct": 50.0,
                "over_9_5_pct": 45.0,
                "over_10_5_pct": 35.0,
                "matches": []
            }

        # Consultar estadísticas de cada partido en paralelo
        tasks = [
            client.get(
                f"https://webws.365scores.com/web/game/stats/?games={gid}&langId=29&appTypeId=5",
                timeout=10.0
            )
            for gid in match_ids
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        corners_for = []
        corners_against = []
        total_corners = []
        matches_detail = []

        for gid, r in zip(match_ids, responses):
            if isinstance(r, Exception) or not hasattr(r, "status_code") or r.status_code != 200:
                continue
            try:
                s_data = r.json()
                raw_stats = s_data.get("statistics", [])
                c_for = 0
                c_against = 0
                found = False

                for s in raw_stats:
                    name = str(s.get("name", "")).lower()
                    if "esquina" in name or "corner" in name:
                        cid = s.get("competitorId")
                        try:
                            val = int(float(s.get("value", 0)))
                        except (ValueError, TypeError):
                            val = 0
                        if cid == competitor_id:
                            c_for = val
                        else:
                            c_against = val
                        found = True

                if found:
                    tot = c_for + c_against
                    corners_for.append(c_for)
                    corners_against.append(c_against)
                    total_corners.append(tot)
                    matches_detail.append({
                        "game_id": gid,
                        "c_for": c_for,
                        "c_against": c_against,
                        "total": tot
                    })
            except Exception as e:
                logger.debug(f"Error parseando estadísticas de partido {gid}: {e}")

        count = len(matches_detail)
        if count == 0:
            return {
                "team": team_name,
                "matches_analyzed": 0,
                "avg_for": 5.0,
                "avg_against": 4.5,
                "avg_total": 9.5,
                "over_8_5_pct": 50.0,
                "over_9_5_pct": 45.0,
                "over_10_5_pct": 35.0,
                "matches": []
            }

        avg_for = round(sum(corners_for) / count, 2)
        avg_against = round(sum(corners_against) / count, 2)
        avg_total = round(sum(total_corners) / count, 2)
        over_8_5 = round(sum(1 for t in total_corners if t >= 9) / count * 100, 1)
        over_9_5 = round(sum(1 for t in total_corners if t >= 10) / count * 100, 1)
        over_10_5 = round(sum(1 for t in total_corners if t >= 11) / count * 100, 1)

        return {
            "team": team_name,
            "matches_analyzed": count,
            "avg_for": avg_for,
            "avg_against": avg_against,
            "avg_total": avg_total,
            "over_8_5_pct": over_8_5,
            "over_9_5_pct": over_9_5,
            "over_10_5_pct": over_10_5,
            "matches": matches_detail
        }

    async def analyze_match_corners(
        self,
        client: httpx.AsyncClient,
        home_id: int,
        away_id: int,
        home_name: str,
        away_name: str,
        home_recent_ids: Optional[List[int]] = None,
        away_recent_ids: Optional[List[int]] = None,
        game_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Analiza en profundidad los tiros de esquina para el enfrentamiento:
        Obtiene los últimos 10 partidos de cada equipo, calcula el balance ofensivo/defensivo
        de córners y determina las líneas de valor recomendadas y combinadas.
        """
        if (not home_recent_ids or not away_recent_ids) and game_id:
            try:
                g_url = f"https://webws.365scores.com/web/game/?gameId={game_id}&langId=29&appTypeId=5"
                g_resp = await client.get(g_url, timeout=12.0)
                if g_resp.status_code == 200:
                    g_data = g_resp.json().get("game", {})
                    if not home_recent_ids:
                        home_recent_ids = g_data.get("homeCompetitor", {}).get("recentMatches")
                    if not away_recent_ids:
                        away_recent_ids = g_data.get("awayCompetitor", {}).get("recentMatches")
            except Exception as e:
                logger.debug(f"Error extrayendo recentMatches del partido {game_id}: {e}")

        t_home = self.fetch_team_recent_corner_history(
            client, home_id, home_name, limit=self.limit_matches, recent_ids=home_recent_ids
        )
        t_away = self.fetch_team_recent_corner_history(
            client, away_id, away_name, limit=self.limit_matches, recent_ids=away_recent_ids
        )

        home_stats, away_stats = await asyncio.gather(t_home, t_away)

        # Proyección ponderada de córners esperados en este encuentro:
        # Expected Home = (Home a favor + Away en contra) / 2
        # Expected Away = (Away a favor + Home en contra) / 2
        proj_home = round((home_stats["avg_for"] + away_stats["avg_against"]) / 2, 2)
        proj_away = round((away_stats["avg_for"] + home_stats["avg_against"]) / 2, 2)
        proj_total = round(proj_home + proj_away, 2)

        # Frecuencia conjunta Over 8.5, Over 9.5, Over 10.5
        combined_over_8_5 = round((home_stats["over_8_5_pct"] + away_stats["over_8_5_pct"]) / 2, 1)
        combined_over_9_5 = round((home_stats["over_9_5_pct"] + away_stats["over_9_5_pct"]) / 2, 1)
        combined_over_10_5 = round((home_stats["over_10_5_pct"] + away_stats["over_10_5_pct"]) / 2, 1)

        # Selección de la mejor línea de córners totales
        if proj_total >= 10.8 and combined_over_10_5 >= 60.0:
            rec_line = "Más de 10.5 Córners Totales"
            rec_odd = "1.85 - 2.05"
            confidence = min(88.0, combined_over_10_5)
        elif proj_total >= 9.8 and combined_over_9_5 >= 65.0:
            rec_line = "Más de 9.5 Córners Totales"
            rec_odd = "1.70 - 1.88"
            confidence = min(86.0, combined_over_9_5)
        elif proj_total >= 8.8 and combined_over_8_5 >= 70.0:
            rec_line = "Más de 8.5 Córners Totales"
            rec_odd = "1.50 - 1.68"
            confidence = min(90.0, combined_over_8_5)
        elif proj_total <= 8.2 and combined_over_8_5 <= 40.0:
            rec_line = "Menos de 9.5 Córners Totales"
            rec_odd = "1.75 - 1.95"
            confidence = round(100.0 - combined_over_9_5, 1)
        else:
            rec_line = "Más de 8.5 Córners Totales"
            rec_odd = "1.55 - 1.72"
            confidence = 72.0

        # Selección de línea individual por equipo
        if proj_home >= 5.5:
            ind_home = f"{home_name}: Más de 4.5 Córners Individuales (Proyección: {proj_home})"
        else:
            ind_home = f"{home_name}: Más de 3.5 Córners Individuales (Proyección: {proj_home})"

        if proj_away >= 4.5:
            ind_away = f"{away_name}: Más de 3.5 Córners Individuales (Proyección: {proj_away})"
        else:
            ind_away = f"{away_name}: Más de 2.5 Córners Individuales (Proyección: {proj_away})"

        # Combinada de córners sugerida
        parlay_suggestion = (
            f"🎯 <b>Combinada de Córners Sugerida:</b>\n"
            f"  1️⃣ {home_name} Más de 3.5 Córners\n"
            f"  2️⃣ Total del Partido Más de 8.5 Córners\n"
            f"  💵 <i>Cuota Estimada Combinada: 1.85 - 2.10</i>"
        )

        return {
            "match": f"{home_name} vs {away_name}",
            "home": home_stats,
            "away": away_stats,
            "projected_home": proj_home,
            "projected_away": proj_away,
            "projected_total": proj_total,
            "combined_over_8_5": combined_over_8_5,
            "combined_over_9_5": combined_over_9_5,
            "combined_over_10_5": combined_over_10_5,
            "recommended_line": rec_line,
            "recommended_odd": rec_odd,
            "confidence": confidence,
            "ind_home": ind_home,
            "ind_away": ind_away,
            "parlay_suggestion": parlay_suggestion
        }
