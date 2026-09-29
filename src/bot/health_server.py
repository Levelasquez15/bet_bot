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
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "status": "healthy",
                "service": "BetBot Telegram",
                "version": "1.0.0"
            }
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Evitar inundar los logs con pings constantes de health checks
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
