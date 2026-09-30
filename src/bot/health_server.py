import os
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/status"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()

            try:
                from src.bot.pick_tracker import get_stats
                from src.bot.subscribers import get_subscribers
                stats = get_stats()
                sub_count = len(get_subscribers())
            except Exception as e:
                logger.debug(f"Error consultando métricas en health check: {e}")
                stats = {}
                sub_count = 0

            response = {
                "status": "healthy",
                "service": "BetBot AI Prediction Engine",
                "version": "2.0.0",
                "database": "SQLite WAL Active",
                "subscribers_active": sub_count,
                "metrics": {
                    "total_picks": stats.get("total", 0),
                    "winrate_pct": stats.get("efectividad", 0.0),
                    "net_profit_units": stats.get("net_profit", 0.0),
                    "yield_pct": stats.get("yield_pct", 0.0),
                    "current_streak": stats.get("streak", "0")
                }
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Evitar inundar los logs de la consola con pings de UptimeRobot
        pass


def start_health_server(port: int = None) -> threading.Thread:
    """Inicia un servidor HTTP ligero en segundo plano para health checks en Koyeb / Render."""
    if port is None:
        port = int(os.getenv("PORT", "8000"))

    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"🌐 Servidor HTTP de salud activo en el puerto {port} (rutas / y /health)")
    return thread
