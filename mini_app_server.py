from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from telegram import Bot
from database.pool import get_pool

WEB_ROOT = Path(__file__).resolve().parent / "mini_app"
_loop = None
_bot = None


def configure_mini_app(loop, bot):
    global _loop, _bot
    _loop = loop
    _bot = bot


async def _payload(top=None):
    pool = get_pool()
    settings = await pool.fetchrow("SELECT banner_file_id FROM mini_app_settings WHERE id=1")
    rows = await pool.fetch(
        """SELECT id,title,target,button_type,color,image_file_id
           FROM mini_app_buttons ORDER BY button_type DESC,button_order,id"""
    )
    leaderboard = None
    if top == "points":
        rows = await pool.fetch("SELECT u.first_name,u.username,p.points FROM points p LEFT JOIN users u ON u.user_id=p.user_id ORDER BY p.points DESC LIMIT 10")
        leaderboard = [{"name": r["first_name"] or r["username"] or "مستخدم", "value": int(r["points"] or 0), "unit": "نقطة"} for r in rows]
    elif top == "active":
        rows = await pool.fetch("SELECT first_name,username,activity_messages FROM users WHERE activity_messages>0 AND COALESCE(is_bot,FALSE)=FALSE ORDER BY activity_messages DESC LIMIT 10")
        leaderboard = [{"name": r["first_name"] or r["username"] or "مستخدم", "value": int(r["activity_messages"] or 0), "unit": "رسالة"} for r in rows]
    elif top == "robbers":
        rows = await pool.fetch("SELECT u.first_name,u.username,b.robbery_balance FROM bank_accounts b JOIN users u ON u.user_id=b.user_id WHERE b.robbery_balance>0 AND COALESCE(u.is_bot,FALSE)=FALSE ORDER BY b.robbery_balance DESC LIMIT 10")
        leaderboard = [{"name": r["first_name"] or r["username"] or "مستخدم", "value": int(r["robbery_balance"] or 0), "unit": "نقطة مسروقة"} for r in rows]
    return {
        "leaderboard": leaderboard,
        "banner": ("/tg-file/" + settings["banner_file_id"]) if settings and settings["banner_file_id"] else None,
        "buttons": [
            {"id": r["id"], "title": r["title"], "target": r["target"],
             "type": r["button_type"], "color": r["color"],
             "image": ("/tg-file/" + r["image_file_id"]) if r["image_file_id"] else None}
            for r in rows
        ],
    }


def _run(coro, timeout=12):
    if _loop is None:
        raise RuntimeError("Mini App backend is not ready")
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=timeout)


def handle_mini_app_request(handler):
    path = handler.path.split("?", 1)[0]
    if path in ("/", "/mini-app", "/mini-app/"):
        file_path = WEB_ROOT / "index.html"
        body = file_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path == "/api/mini-app":
        try:
            from urllib.parse import parse_qs, urlparse
            top = parse_qs(urlparse(handler.path).query).get("top", [None])[0]
            body = json.dumps(_run(_payload(top)), ensure_ascii=False).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            handler.send_error(503, "Mini App is starting")
        return True
    if path.startswith("/tg-file/"):
        file_id = unquote(path[len("/tg-file/"):])
        try:
            file = _run(_bot.get_file(file_id))
            token = os.environ["BOT_TOKEN"]
            url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "image/jpeg")
            handler.send_response(200)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "public, max-age=3600")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            handler.send_error(404, "Image not found")
        return True
    return False
