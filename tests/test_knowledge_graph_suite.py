"""
Suite de pruebas automatizada para el Grafo de Conocimiento y Auditor de Tickets (Ticket Vision).
Valida:
1. Creación y actualización de Nodos y Aristas en SQLite.
2. Auditoría de tickets y aprendizaje de patrones de error (Margen Corto / 'Uno Menos').
3. Generación de lecciones aprendidas y retroalimentación +EV.
4. Parser de visión multimodal (Gemini Vision mock) y formateador HTML para Telegram.
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

from src.db.database import DatabaseManager
from src.graph.knowledge_graph import KnowledgeGraph
from src.graph.ticket_vision import TicketVisionParser, format_ticket_audit_report


import tempfile

class TestKnowledgeGraphSuite(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Base de datos en archivo temporal para pruebas aisladas
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.test_db = DatabaseManager(self.temp_file.name)
        self.kg = KnowledgeGraph(self.test_db)
        self.parser = TicketVisionParser(api_key="mock_key")

    def tearDown(self):
        if hasattr(self, "temp_file") and os.path.exists(self.temp_file.name):
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass

    def test_nodes_and_edges_creation(self):
        """Valida que los nodos y aristas se creen y actualicen correctamente en la BD."""
        node = self.kg.get_or_create_node(
            "player:vinicius_jr",
            "PLAYER",
            "Vinicius Jr",
            {"role": "Extremo"}
        )
        self.assertEqual(node["id"], "player:vinicius_jr")
        self.assertEqual(node["name"], "Vinicius Jr")
        self.assertEqual(node["properties"]["role"], "Extremo")

        # Actualizar propiedades
        self.kg.update_node_properties("player:vinicius_jr", {"role": "Delantero", "total_audited": 1})
        node_updated = self.kg.get_or_create_node("player:vinicius_jr", "PLAYER", "Vinicius Jr")
        self.assertEqual(node_updated["properties"]["role"], "Delantero")
        self.assertEqual(node_updated["properties"]["total_audited"], 1)

        # Crear arista
        self.kg.add_or_update_edge("player:vinicius_jr", "market:fouls", "FREQUENT_IN", weight_delta=2.0)
        summary = self.kg.get_summary()
        self.assertGreaterEqual(summary["nodes_count"], 1)
        self.assertGreaterEqual(summary["edges_count"], 1)

    def test_ticket_learning_short_margin_error_pattern(self):
        """
        Valida que al auditar un ticket con fallo por margen de 1 tiro (ej. Lewandowski 2 tiros en línea +2.5):
        1. Se conecte al patrón de error 'error_pattern:short_margin_1_shot'.
        2. Se genere una lección aprendida que sugiera la línea base +1.5 (+EV).
        3. Se incremente el contador de fallos del jugador y se actualice el grafo.
        """
        ticket_data = {
            "bookmaker": "Bet365",
            "total_odd": 3.50,
            "overall_status": "PERDIDA",
            "legs": [
                {
                    "match": "Barcelona vs Sevilla",
                    "player": "Robert Lewandowski",
                    "market": "Disparos Totales",
                    "line": "+2.5 Disparos Totales",
                    "odd": 2.10,
                    "status": "PERDIDA",
                    "actual_value": 2,
                    "detail": "Registró 2 tiros, faltó 1 para la línea de 2.5"
                },
                {
                    "match": "Real Madrid vs Girona",
                    "player": "Kylian Mbappé",
                    "market": "Disparos a Puerta",
                    "line": "+0.5 Disparos a Puerta",
                    "odd": 1.45,
                    "status": "GANADA",
                    "actual_value": 2,
                    "detail": "2 tiros a puerta cumplidos holgadamente"
                }
            ],
            "summary": "Combinada de 2 piernas. 1 ganada y 1 perdida."
        }

        insights = self.kg.record_ticket_outcome(ticket_data, chat_id=12345)
        self.assertGreaterEqual(len(insights), 2)

        # Verificar que el insight sobre Lewandowski mencione el patrón de margen corto
        lewa_insights = [ins for ins in insights if "Lewandowski" in ins]
        self.assertTrue(len(lewa_insights) > 0)
        self.assertIn("+1.5", lewa_insights[0])
        self.assertIn("Margen Corto", lewa_insights[0])

        # Verificar inteligencia del jugador en el grafo
        lewa_intel = self.kg.get_player_intelligence("Robert Lewandowski")
        self.assertIsNotNone(lewa_intel)
        self.assertEqual(lewa_intel["total_audited"], 1)
        self.assertEqual(lewa_intel["misses"], 1)
        self.assertEqual(lewa_intel["short_margin_faults"], 1.0)

        # Verificar reporte del grafo
        graph_report = self.kg.format_graph_status_report()
        self.assertIn("GRAFO DE CONOCIMIENTO", graph_report)
        self.assertIn("Robert Lewandowski", graph_report)
        self.assertIn("Short Margin 1 Shot", graph_report)

    async def test_ticket_vision_parser_and_formatter(self):
        """Valida que el parser de visión procese respuestas estructuradas y el formateador genere HTML válido."""
        mock_gemini_json = {
            "bookmaker": "Rushbet",
            "total_odd": 4.20,
            "overall_status": "PERDIDA",
            "legs": [
                {
                    "match": "Arsenal vs Chelsea",
                    "player": "Bukayo Saka",
                    "market": "Disparos a Puerta",
                    "line": "+0.5 Disparos a Puerta",
                    "odd": 1.55,
                    "status": "GANADA",
                    "actual_value": 1,
                    "detail": "1 remate al arco registrado."
                },
                {
                    "match": "Liverpool vs Everton",
                    "player": "Mohamed Salah",
                    "market": "Disparos Totales",
                    "line": "+2.5 Disparos Totales",
                    "odd": 2.05,
                    "status": "PERDIDA",
                    "actual_value": 2,
                    "detail": "El delantero realizó 2 tiros.",
                    "suggested_better_line": "+1.5 Disparos Totales"
                }
            ],
            "summary": "Combinada premier league"
        }

        with patch.object(self.parser, "_call_gemini_vision", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_gemini_json
            parsed = await self.parser.parse_ticket_image(b"fake_image_bytes")

            self.assertEqual(parsed["bookmaker"], "Rushbet")
            self.assertEqual(len(parsed["legs"]), 2)

            insights = self.kg.record_ticket_outcome(parsed)
            report = format_ticket_audit_report(parsed, insights)

            self.assertIn("AUDITORÍA DE TICKET DE APUESTAS", report)
            self.assertIn("Rushbet", report)
            self.assertIn("Bukayo Saka", report)
            self.assertIn("Mohamed Salah", report)
            self.assertIn("SE DIO", report)
            self.assertIn("NO SE DIO", report)
            self.assertIn("+1.5 Disparos Totales", report)
            self.assertIn("APRENDIZAJE DEL GRAFO DE CONOCIMIENTO", report)


if __name__ == "__main__":
    unittest.main()
