"""
Suite de pruebas automatizada para el Asistente Personal de Apuestas (BetBot Assistant).
Valida:
1. CornersAssistant (cálculo sobre 10 partidos, promedios, over/under, líneas recomendadas)
2. PlayersAssistant (detección de alineaciones oficiales y probables, tiros a puerta, tiros totales y faltas)
3. BetAssistant (fachada y formateadores HTML de Telegram)
4. Inicialización y registro de comandos en telegram_client
"""

import sys
import os
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from src.assistant.corners_assistant import CornersAssistant
from src.assistant.players_assistant import PlayersAssistant
from src.assistant.assistant_facade import (
    BetAssistant,
    format_corners_report,
    format_players_report,
    format_full_match_report,
    format_lineup_alert
)
from src.bot.telegram_client import (
    get_main_menu_keyboard,
    build_assistant_matches_keyboard,
    get_assistant_navigation_keyboard
)


class TestAssistantSuite(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.corners_assistant = CornersAssistant(limit_matches=10)
        self.players_assistant = PlayersAssistant()
        self.assistant = BetAssistant(limit_corners_matches=10)

    async def test_corners_analysis_logic(self):
        """Verifica que el cálculo estadístico de córners proyecte métricas consistentes."""
        # Datos simulados de 10 partidos para cada equipo
        mock_home_stats = {
            "team": "PSG",
            "matches_analyzed": 10,
            "avg_for": 6.8,
            "avg_against": 3.2,
            "avg_total": 10.0,
            "over_8_5_pct": 80.0,
            "over_9_5_pct": 70.0,
            "over_10_5_pct": 50.0,
            "matches": []
        }
        mock_away_stats = {
            "team": "Barcelona",
            "matches_analyzed": 10,
            "avg_for": 5.9,
            "avg_against": 4.1,
            "avg_total": 10.0,
            "over_8_5_pct": 70.0,
            "over_9_5_pct": 60.0,
            "over_10_5_pct": 40.0,
            "matches": []
        }

        with patch.object(self.corners_assistant, "fetch_team_recent_corner_history") as mock_fetch:
            mock_fetch.side_effect = [mock_home_stats, mock_away_stats]
            result = await self.corners_assistant.analyze_match_corners(
                client=AsyncMock(),
                home_id=1,
                away_id=2,
                home_name="PSG",
                away_name="Barcelona"
            )

            self.assertEqual(result["match"], "PSG vs Barcelona")
            self.assertGreater(result["projected_total"], 9.0)
            self.assertIn("Más de", result["recommended_line"])
            self.assertIn("PSG", result["ind_home"])
            self.assertIn("Barcelona", result["ind_away"])
            self.assertIn("Combinada de Córners", result["parlay_suggestion"])

    async def test_players_analysis_logic(self):
        """Verifica la extracción de alineaciones titulares y selección de props de jugador."""
        mock_game_obj = {
            "id": 12345,
            "competitionDisplayName": "UEFA Champions League",
            "members": [
                {"id": 101, "name": "Kylian Mbappé", "competitorId": 1},
                {"id": 102, "name": "Ousmane Dembélé", "competitorId": 1},
                {"id": 103, "name": "Manuel Ugarte", "competitorId": 1},
                {"id": 201, "name": "Robert Lewandowski", "competitorId": 2},
                {"id": 202, "name": "Lamine Yamal", "competitorId": 2},
                {"id": 203, "name": "Gavi", "competitorId": 2},
            ],
            "homeCompetitor": {
                "id": 1,
                "name": "PSG",
                "lineups": {
                    "status": "Confirmado",
                    "formation": "4-3-3",
                    "members": [
                        {"id": 101, "statusText": "Starting", "position": {"name": "Delantero"}, "stats": []},
                        {"id": 102, "statusText": "Starting", "position": {"name": "Delantero"}, "stats": []},
                        {"id": 103, "statusText": "Starting", "position": {"name": "Mediocampista"}, "stats": []},
                    ]
                }
            },
            "awayCompetitor": {
                "id": 2,
                "name": "Barcelona",
                "lineups": {
                    "status": "Confirmado",
                    "formation": "4-3-3",
                    "members": [
                        {"id": 201, "statusText": "Starting", "position": {"name": "Delantero"}, "stats": []},
                        {"id": 202, "statusText": "Starting", "position": {"name": "Delantero"}, "stats": []},
                        {"id": 203, "statusText": "Starting", "position": {"name": "Mediocampista"}, "stats": []},
                    ]
                }
            }
        }

        result = await self.players_assistant.analyze_match_players(
            client=AsyncMock(),
            game_id=12345,
            home_id=1,
            away_id=2,
            home_name="PSG",
            away_name="Barcelona",
            game_obj=mock_game_obj
        )

        self.assertTrue(result["is_confirmed"])
        self.assertIn("Confirmada", result["lineup_status_text"])
        self.assertEqual(result["formation_home"], "4-3-3")
        self.assertGreater(len(result["top_shots_on_target"]), 0)
        self.assertGreater(len(result["top_total_shots"]), 0)
        self.assertGreater(len(result["top_fouls_committed"]), 0)

    def test_formatters(self):
        """Verifica que los formateadores HTML produzcan textos válidos y completos."""
        corners_data = {
            "match": "PSG vs Barcelona",
            "home": {
                "team": "PSG",
                "matches_analyzed": 10,
                "avg_for": 6.8,
                "avg_against": 3.2,
                "avg_total": 10.0,
                "over_8_5_pct": 80.0,
                "over_9_5_pct": 70.0
            },
            "away": {
                "team": "Barcelona",
                "matches_analyzed": 10,
                "avg_for": 5.9,
                "avg_against": 4.1,
                "avg_total": 10.0,
                "over_8_5_pct": 70.0,
                "over_9_5_pct": 60.0
            },
            "projected_total": 9.9,
            "combined_over_8_5": 75.0,
            "combined_over_9_5": 65.0,
            "recommended_line": "Más de 9.5 Córners Totales",
            "recommended_odd": "1.75",
            "confidence": 80.0,
            "ind_home": "PSG: Más de 4.5 Córners",
            "ind_away": "Barcelona: Más de 3.5 Córners",
            "parlay_suggestion": "🎯 Combinada Sugerida: PSG +3.5 Córners & Over 8.5"
        }

        players_data = {
            "match": "PSG vs Barcelona",
            "lineup_status_text": "🟢 Confirmada (Oficial)",
            "formation_home": "4-3-3",
            "formation_away": "4-3-3",
            "top_shots_on_target": [
                {"player": "Kylian Mbappé", "team": "PSG", "line": "+1.5 Disparos a Puerta", "odd": "1.90", "avg": 2.1, "confidence": 85.0}
            ],
            "top_total_shots": [
                {"player": "Kylian Mbappé", "team": "PSG", "line": "+2.5 Disparos Totales", "odd": "1.80", "avg": 4.2, "confidence": 88.0}
            ],
            "top_fouls_committed": [
                {"player": "Gavi", "team": "Barcelona", "position": "Pivote", "line": "+1.5 Faltas Cometidas", "odd": "1.65", "avg": 2.4}
            ],
            "top_fouls_received": [
                {"player": "Lamine Yamal", "team": "Barcelona", "position": "Extremo", "line": "+1.5 Faltas Recibidas", "odd": "1.70", "avg": 2.2}
            ],
            "player_parlay": "🎰 Combinada de Jugador Sugerida: Mbappé +0.5 al arco & Gavi +1.5 faltas"
        }

        # 1. Reporte Córners
        report_corners = format_corners_report(corners_data)
        self.assertIn("AYUDANTE DE TIROS DE ESQUINA", report_corners)
        self.assertIn("PSG vs Barcelona", report_corners)

        # 2. Reporte Jugadores
        report_players = format_players_report(players_data)
        self.assertIn("AYUDANTE DE JUGADORES", report_players)
        self.assertIn("Kylian Mbappé", report_players)
        self.assertIn("Gavi", report_players)

        # 3. Reporte Completo
        full_match_data = {"match": "PSG vs Barcelona", "corners": corners_data, "players": players_data}
        report_full = format_full_match_report(full_match_data)
        self.assertIn("INFORME COMPLETO DEL AYUDANTE BETBOT", report_full)

        # 4. Alerta de Alineación
        alert_msg = format_lineup_alert("PSG vs Barcelona", "Champions League", "14:00", players_data, corners_data)
        self.assertIn("ALINEACIÓN OFICIAL CONFIRMADA", alert_msg)

    async def test_assistant_keyboards(self):
        """Valida que los teclados del menú principal y de navegación se construyan correctamente."""
        main_kb = get_main_menu_keyboard()
        cb_data_list = [btn.callback_data for row in main_kb.inline_keyboard for btn in row]
        self.assertIn("btn_oficiales_1h", cb_data_list)
        self.assertIn("btn_horas_antes", cb_data_list)
        self.assertIn("btn_partidos_hoy", cb_data_list)
        self.assertIn("btn_ayudante_corners", cb_data_list)
        self.assertIn("btn_ayudante_players", cb_data_list)

        nav_kb = get_assistant_navigation_keyboard("9999", "corners")
        nav_cbs = [btn.callback_data for row in nav_kb.inline_keyboard for btn in row]
        self.assertIn("ply_9999", nav_cbs)
        self.assertIn("ful_9999", nav_cbs)
        self.assertIn("btn_main_menu", nav_cbs)

        # Probar generación de teclados de partidos con mock
        mock_game = {
            "id": 1234,
            "homeCompetitor": {"name": "Real Madrid", "id": 10},
            "awayCompetitor": {"name": "Barcelona", "id": 20},
            "competitionDisplayName": "LaLiga",
            "startTime": "2026-10-11T16:00:00Z",
            "time_left_str": "en 45m",
            "is_lineup_confirmed": True
        }
        with patch("src.scraper.scraper_365.Scraper365.fetch_assistant_matches", new_callable=AsyncMock) as mock_matches:
            mock_matches.return_value = [mock_game]
            txt_oficial, kb_oficial = await build_assistant_matches_keyboard("oficiales")
            self.assertIn("ALINEACIONES OFICIALES", txt_oficial)
            oficial_cbs = [btn.callback_data for row in kb_oficial.inline_keyboard for btn in row]
            self.assertIn("ply_1234", oficial_cbs)

            txt_horas, kb_horas = await build_assistant_matches_keyboard("horas_antes")
            self.assertIn("PRE-PARTIDO HORAS ANTES", txt_horas)


if __name__ == "__main__":
    unittest.main()
