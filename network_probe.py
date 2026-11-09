import asyncio
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import asyncpg
import httpx

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

async def run_probe():
    result = {}
    if not BOT_TOKEN:
        result["telegram"] = {"error": "BOT_TOKEN is not configured"}
    else:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(http2=True, timeout=12.0) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
                )
                result["telegram"] = {
                    "http_status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "http_version": response.http_version,
                    "ok": response.status_code == 200,
                }
        except Exception as exc:
            result["telegram"] = {
                "error": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }

    if not DATABASE_URL:
        result["database"] = {"error": "DATABASE_URL is not configured"}
    else:
        started = time.perf_counter()
        try:
            conn = await asyncpg.connect(DATABASE_URL, timeout=10)
            try:
                await conn.fetchval("SELECT 1")
            finally:
                await conn.close()
            result["database"] = {
                "ok": True,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except Exception as exc:
            result["database"] = {
                "error": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
    return result

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/probe":
            payload = asyncio.run(run_probe())
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/", "/health"):
            body = b"Frankfurt network probe ready"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
