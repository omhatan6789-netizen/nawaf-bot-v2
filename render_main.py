"""Render Free Web Service entrypoint for the Telegram polling bot.

The HTTP endpoint keeps Render's web-service health checks satisfied.
Telegram polling continues in the main process; the HTTP server runs in a daemon thread.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from threading import Thread

from main import build_application
from mini_app_server import handle_mini_app_request, handle_chess_post


class HealthHandler(BaseHTTPRequestHandler):
    def _respond(self, include_body=True):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self):
        if handle_mini_app_request(self):
            return
        self._respond(include_body=True)

    def do_POST(self):
        if handle_chess_post(self):
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        # UptimeRobot and some proxies probe endpoints with HEAD requests.
        # HEAD must return the same headers/status as GET, without a body.
        self._respond(include_body=False)

    def log_message(self, format, *args):
        # Keep routine health checks out of the logs.
        return


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    Thread(target=server.serve_forever, name="render-health-server", daemon=True).start()


if __name__ == "__main__":
    start_health_server()
    build_application().run_polling()
