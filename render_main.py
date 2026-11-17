"""Render web service entrypoint for the Telegram webhook bot.

The same HTTP server serves the Mini App, game POST routes, health checks,
and Telegram webhook updates.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import signal
import socket
import struct
import threading
import time
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from telegram import Update

from main import build_application
from mini_app_server import handle_mini_app_request, handle_connect4_post
from memory_monitor import start_memory_monitor

logger = logging.getLogger("nawaf-webhook")


_carrom_ws_rooms = {}
_carrom_ws_lock = threading.Lock()


def _ws_frame(payload, opcode=1):
    payload = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
    length = len(payload)
    if length < 126:
        header = bytes([0x80 | opcode, length])
    elif length < 65536:
        header = bytes([0x80 | opcode, 126]) + struct.pack("!H", length)
    else:
        header = bytes([0x80 | opcode, 127]) + struct.pack("!Q", length)
    return header + payload


def _ws_send(client, payload, opcode=1):
    frame = _ws_frame(payload, opcode)
    with client["send_lock"]:
        client["handler"].wfile.write(frame)
        client["handler"].wfile.flush()


def _ws_read_exact(stream, length):
    chunks = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ConnectionError("WebSocket disconnected")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _ws_read_message(handler):
    first = _ws_read_exact(handler.rfile, 2)
    opcode = first[0] & 0x0F
    masked = bool(first[1] & 0x80)
    length = first[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _ws_read_exact(handler.rfile, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _ws_read_exact(handler.rfile, 8))[0]
    if length > 65536:
        raise ValueError("WebSocket frame too large")
    mask = _ws_read_exact(handler.rfile, 4) if masked else b""
    data = _ws_read_exact(handler.rfile, length)
    if masked:
        data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
    return opcode, data


def handle_carrom_websocket(handler):
    parsed = urlparse(handler.path)
    if parsed.path != "/ws/carrom":
        return False
    client = None
    upgraded = False
    try:
        query = parse_qs(parsed.query)
        game_id = (query.get("game_id") or [""])[0]
        init_data = (query.get("initData") or [""])[0]
        if not game_id or len(game_id) > 64 or len(init_data) > 12000:
            handler.send_error(400, "Invalid WebSocket parameters")
            return True
        if application is None or application_loop is None:
            handler.send_error(503, "Game server is starting")
            return True
        from games.connect4 import verify_init_data
        from games.carrom_online import carrom_online_api
        user = verify_init_data(init_data, application.bot.token)
        uid = int(user["id"])
        future = asyncio.run_coroutine_threadsafe(
            carrom_online_api(uid, "state", game_id, {}), application_loop
        )
        state = future.result(timeout=8)
        if not state.get("is_player"):
            handler.send_error(403, "Not a player in this room")
            return True
        key = handler.headers.get("Sec-WebSocket-Key", "")
        if handler.headers.get("Upgrade", "").lower() != "websocket" or not key:
            handler.send_error(400, "WebSocket upgrade required")
            return True
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        handler.protocol_version = "HTTP/1.1"
        handler.send_response(101, "Switching Protocols")
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept)
        handler.end_headers()
        handler.wfile.flush()
        upgraded = True
        handler.connection.settimeout(25)
        client = {"handler": handler, "uid": uid, "game_id": game_id, "send_lock": threading.Lock()}
        with _carrom_ws_lock:
            _carrom_ws_rooms.setdefault(game_id, set()).add(id(client))
            _carrom_ws_clients[id(client)] = client
        _ws_send(client, json.dumps({"type": "ready"}, separators=(",", ":")))
        last_motion_at = 0.0
        while True:
            try:
                opcode, raw = _ws_read_message(handler)
            except socket.timeout:
                _ws_send(client, b"", opcode=9)
                continue
            if opcode == 8:
                try:
                    _ws_send(client, raw, opcode=8)
                except Exception:
                    pass
                break
            if opcode == 9:
                _ws_send(client, raw, opcode=10)
                continue
            if opcode != 1:
                continue
            if len(raw) > 48000:
                continue
            try:
                packet = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if not isinstance(packet, dict) or packet.get("type") != "motion":
                continue
            motion = packet.get("motion")
            if not isinstance(motion, dict) or not isinstance(motion.get("discs"), list):
                continue
            now = time.monotonic()
            if now - last_motion_at < 0.018:
                continue
            last_motion_at = now
            motion["player_id"] = uid
            motion["sent_at"] = time.time()
            outgoing = json.dumps(motion, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            with _carrom_ws_lock:
                peers = [
                    item for item in _carrom_ws_clients.values()
                    if item["game_id"] == game_id and item["uid"] != uid
                ]
            for peer in peers:
                try:
                    _ws_send(peer, outgoing)
                except Exception:
                    pass
    except Exception as exc:
        logging.getLogger("nawaf-webhook").debug("Carrom WebSocket closed: %s", exc)
        if not upgraded:
            try:
                handler.send_error(400, "Carrom real-time connection failed")
            except Exception:
                pass
    finally:
        if client is not None:
            with _carrom_ws_lock:
                _carrom_ws_clients.pop(id(client), None)
                room = _carrom_ws_rooms.get(client["game_id"])
                if room is not None:
                    room.discard(id(client))
                    if not room:
                        _carrom_ws_rooms.pop(client["game_id"], None)
    return True


_carrom_ws_clients = {}

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
        if handle_carrom_websocket(self):
            return
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
    __import__("config").load_settings()
    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not webhook_secret:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is required for webhook mode")

    application_loop = asyncio.get_running_loop()
    application = build_application(use_updater=False)

    await application.initialize()
    try:
        if application.post_init:
            await application.post_init(application)

        base_url = os.environ.get("PUBLIC_BASE_URL", "https://nawaf-bot-v2.onrender.com").rstrip("/")
        webhook_url = f"{base_url}/telegram-webhook"
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
