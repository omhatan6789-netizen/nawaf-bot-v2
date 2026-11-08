"""Render web service entrypoint for the Telegram webhook bot.

The same HTTP server serves the Mini App, game POST routes, health checks,
and Telegram webhook updates.
"""
import asyncio
import hmac
import json
import logging
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from telegram import Update

from main import build_application
from mini_app_server import handle_mini_app_request, handle_connect4_post
from memory_monitor import start_memory_monitor

logger = logging.getLogger("nawaf-webhook")
application = None
application_loop = None
webhook_secret = None


class HealthHandler(BaseHTTPRequestHandler):
    def _respond(self, status=200, body=b"OK", content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _health(self, include_body=True):
        if self.path not in ("/", "/health"):
            self._respond(404, b"")
            return
        self._respond(200, b"OK" if include_body else b"")

    def do_GET(self):
        if handle_mini_app_request(self):
            return
        self._health(include_body=True)

    def do_POST(self):
        if self.path == "/telegram-webhook":
            self._telegram_webhook()
            return
        if handle_connect4_post(self):
            return
        self._respond(404, b"")

    def _telegram_webhook(self):
        global application, application_loop, webhook_secret
        supplied_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not webhook_secret or not hmac.compare_digest(supplied_secret, webhook_secret):
            self._respond(403, b"Forbidden")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 1024 * 1024:
                self._respond(413, b"Invalid payload size")
                return
            payload = json.loads(self.rfile.read(content_length))
            update = Update.de_json(data=payload, bot=application.bot)
            if update is None or application_loop is None:
                self._respond(400, b"Invalid update")
                return
            future = asyncio.run_coroutine_threadsafe(
                application.update_queue.put(update), application_loop
            )
            future.result(timeout=10)
        except Exception:
            logger.exception("Failed to enqueue Telegram webhook update")
            self._respond(500, b"Webhook processing failed")
            return
        self._respond(200, b"OK")

    def do_HEAD(self):
        self._health(include_body=False)

    def log_message(self, format, *args):
        return


def start_http_server():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    Thread(target=server.serve_forever, name="render-http-server", daemon=True).start()
    return server


async def run_webhook_bot():
    global application, application_loop, webhook_secret
    settings = __import__("config").load_settings()
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required for webhook mode")

    application_loop = asyncio.get_running_loop()
    application = build_application(use_updater=False)

    await application.initialize()
    try:
        if application.post_init:
            await application.post_init(application)

        webhook_url = "https://nawaf-bot-v2.onrender.com/telegram-webhook"
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
            max_connections=20,
        )
        await application.start()
        logger.info("Telegram webhook is active at %s", webhook_url)

        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                application_loop.add_signal_handler(sig, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
        await stop_event.wait()
    finally:
        if application.running:
            await application.stop()
        if application.post_shutdown:
            await application.post_shutdown(application)
        await application.shutdown()


if __name__ == "__main__":
    start_http_server()
    start_memory_monitor(interval_seconds=15)
    asyncio.run(run_webhook_bot())
