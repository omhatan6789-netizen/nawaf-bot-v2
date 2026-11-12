from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import unquote, parse_qs, urlparse

import httpx

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
    settings = await pool.fetchrow(
        "SELECT banner_file_id,banner_media_kind,banner_mime_type FROM mini_app_settings WHERE id=1"
    )
    buttons = await pool.fetch(
        """SELECT id,title,target,button_type,color,image_file_id,
                  COALESCE(media_kind,'image') AS media_kind,mime_type
           FROM mini_app_buttons ORDER BY button_type DESC,button_order,id"""
    )
    sounds = await pool.fetch(
        "SELECT id,title,media_kind,mime_type FROM mini_app_sounds ORDER BY id"
    )
    online_images = await pool.fetch(
        "SELECT game_type,photo_file_id FROM online_game_images"
    )
    button_colors = await pool.fetch("SELECT button_text,color_hex FROM mini_app_button_colors")
    leaderboard = None
    if top == "points":
        from database.points import get_points_leaderboard
        rows = await get_points_leaderboard(10)
        leaderboard = [
            {"name": r["first_name"] or r["username"] or "مستخدم",
             "value": int(r["points"] or 0), "unit": "نقطة"}
            for r in rows
        ]
    elif top == "active":
        rows = await pool.fetch(
            """SELECT first_name,username,activity_messages
               FROM users
               WHERE activity_messages > 0
                 AND COALESCE(is_bot,FALSE)=FALSE
                 AND COALESCE(first_name,'') <> 'Deleted Account'
               ORDER BY activity_messages DESC,user_id ASC LIMIT 10"""
        )
        leaderboard = [
            {"name": r["first_name"] or r["username"] or "مستخدم",
             "value": int(r["activity_messages"] or 0), "unit": "رسالة"}
            for r in rows
        ]
    elif top in ("game_wins", "game_losses"):
        from database.game_stats import get_game_leaderboard
        result = "win" if top == "game_wins" else "loss"
        rows = await get_game_leaderboard(result, 10)
        leaderboard = [
            {"name": r["name"], "value": int(r["total"]),
             "unit": "فوز" if result == "win" else "خسارة"}
            for r in rows
        ]
    elif top == "robbers":
        rows = await pool.fetch(
            """SELECT u.first_name,u.username,b.robbery_balance
               FROM bank_accounts b
               JOIN users u ON u.user_id=b.user_id
               WHERE b.robbery_balance > 0
                 AND COALESCE(u.is_bot,FALSE)=FALSE
                 AND COALESCE(u.first_name,'') <> 'Deleted Account'
               ORDER BY b.robbery_balance DESC,b.user_id ASC LIMIT 10"""
        )
        leaderboard = [
            {"name": r["first_name"] or r["username"] or "مستخدم",
             "value": int(r["robbery_balance"] or 0), "unit": "نقطة مسروقة"}
            for r in rows
        ]
    me = await _bot.get_me() if _bot else None
    return {
        "leaderboard": leaderboard,
        "bot_username": me.username if me else None,
        "bot_name": me.first_name if me else "البوت",
        "banner": ("/tg-file/" + settings["banner_file_id"]) if settings and settings["banner_file_id"] else None,
        "banner_type": settings["banner_media_kind"] if settings and settings["banner_media_kind"] else "image",
        "banner_mime_type": settings["banner_mime_type"] if settings and settings["banner_mime_type"] else None,
        "buttons": [
            {"id": r["id"], "title": r["title"], "target": r["target"],
             "type": r["button_type"], "color": r["color"],
             "image": ("/tg-file/" + r["image_file_id"]) if r["image_file_id"] else None,
             "media_kind": r["media_kind"], "mime_type": r["mime_type"]}
            for r in buttons
        ],
        "button_colors": {r["button_text"]: r["color_hex"] for r in button_colors},
        "sounds": [
            {"id": r["id"], "title": r["title"], "type": r["media_kind"],
             "mime_type": r["mime_type"], "url": f"/mini-app/sound/{r['id']}"}
            for r in sounds
        ],
        "online_game_images": {
            r["game_type"]: "/tg-file/" + r["photo_file_id"] for r in online_images
        },
    }

def _run(coro, timeout=20):
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
    if path == "/mini_app/ambient.js":
        file_path = WEB_ROOT / "ambient.js"
        try:
            body = file_path.read_bytes()
        except OSError:
            handler.send_error(404, "Music script not found")
            return True
        handler.send_response(200)
        handler.send_header("Content-Type", "application/javascript; charset=utf-8")
        handler.send_header("Cache-Control", "public, max-age=3600")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path == "/api/youtube/search":
        try:
            query = parse_qs(urlparse(handler.path).query).get("q", [""])[0].strip()
            if not query or len(query) > 100:
                raise ValueError("اكتب اسم المقطع للبحث")
            from handlers.youtube_audio import _search_youtube
            results = _run(_search_youtube(query), timeout=30)
            body = json.dumps({"ok": True, "results": results}, ensure_ascii=False).encode()
            handler.send_response(200)
        except ValueError as exc:
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
            handler.send_response(400)
        except Exception:
            logging.getLogger(__name__).exception("Mini App YouTube search failed")
            body = json.dumps({"ok": False, "error": "تعذر البحث في يوتيوب الآن"}, ensure_ascii=False).encode()
            handler.send_response(503)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path == "/api/youtube/resolve":
        try:
            video_id = parse_qs(urlparse(handler.path).query).get("id", [""])[0].strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                raise ValueError("معرّف المقطع غير صالح")
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=20.0), follow_redirects=True) as client:
                response = client.post(
                    "https://api.samplecut.app/v1/downloads",
                    json={"url": video_url, "format": "mp3", "response": "url"},
                    headers={"X-Client-Name": "NawafMiniApp", "Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
            audio_url = data.get("download_url") or data.get("downloadUrl")
            if not audio_url or not audio_url.startswith("https://"):
                raise RuntimeError("لم يتم الحصول على رابط الصوت")
            body = json.dumps({"ok": True, "url": audio_url}, ensure_ascii=False).encode()
            handler.send_response(200)
        except ValueError as exc:
            body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
            handler.send_response(400)
        except Exception:
            logging.getLogger(__name__).exception("Mini App YouTube audio resolve failed")
            body = json.dumps({"ok": False, "error": "تعذر تجهيز صوت المقطع، جرّب نتيجة ثانية"}, ensure_ascii=False).encode()
            handler.send_response(502)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path == "/api/mini-app":
        try:
            top = parse_qs(urlparse(handler.path).query).get("top", [None])[0]
            body = json.dumps(_run(_payload(top)), ensure_ascii=False).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception as exc:
            logging.getLogger(__name__).exception("Mini App payload failed")
            body = json.dumps(
                {"ok": False, "error": str(exc)[:300] or "تعذر تحميل بيانات الميني آب"},
                ensure_ascii=False,
            ).encode()
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        return True
    if path.startswith("/mini-app/sound/"):
        try:
            sound_id = int(path.rsplit("/", 1)[-1])
            sound = _run(get_pool().fetchrow(
                "SELECT file_id,mime_type,media_kind FROM mini_app_sounds WHERE id=$1",
                sound_id,
            ))
            if not sound:
                handler.send_error(404, "Sound not found")
                return True
            telegram_file = _run(_bot.get_file(sound["file_id"]))
            body = bytes(_run(telegram_file.download_as_bytearray()))
            handler.send_response(200)
            handler.send_header("Content-Type", sound["mime_type"] or ("video/mp4" if sound["media_kind"] == "video" else "audio/mpeg"))
            handler.send_header("Content-Length", str(len(body)))
            handler.send_header("Accept-Ranges", "none")
            handler.send_header("Cache-Control", "public, max-age=3600")
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            logging.getLogger(__name__).exception("Failed to serve Mini App sound")
            handler.send_error(404, "Sound not found")
        return True
    if path.startswith("/tg-file/"):
        file_id = unquote(path[len("/tg-file/"):])
        try:
            telegram_file = _run(_bot.get_file(file_id))
            body = _run(telegram_file.download_as_bytearray())
            body = bytes(body)
            if body.startswith(b"\x89PNG\r\n\x1a\n"):
                content_type = "image/png"
            elif body.startswith(b"\xff\xd8\xff"):
                content_type = "image/jpeg"
            elif body.startswith((b"GIF87a", b"GIF89a")):
                content_type = "image/gif"
            elif body.startswith(b"RIFF") and body[8:12] == b"WEBP":
                content_type = "image/webp"
            elif len(body) >= 12 and body[4:8] == b"ftyp":
                content_type = "video/mp4"
            elif body.startswith(b"\x1a\x45\xdf\xa3"):
                content_type = "video/webm"
            else:
                raise ValueError("Unsupported media format returned by Telegram")
            handler.send_response(200)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "public, max-age=3600")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            logging.getLogger(__name__).exception("Failed to serve Mini App image")
            handler.send_error(404, "Image not found")
        return True
    return False


def handle_connect4_post(handler):
    path = handler.path.split("?", 1)[0]
    if path not in (
        "/api/connect4/new", "/api/connect4/move",
        "/api/connect4/bot-move", "/api/connect4/state",
        "/api/connect4/challenge/state", "/api/connect4/challenge/choice",
        "/api/minigames/challenge/state", "/api/minigames/challenge/choice",
        "/api/minigames/action", "/api/minigames/solo/new",
        "/api/minigames/solo/state", "/api/minigames/solo/action",
        "/api/minigames/solo/bot-move",
        "/api/online/restart", "/api/online/spectate", "/api/online/lobby", "/api/online/withdraw",
        "/api/extra-games", "/api/casual-games",
    ):
        return False
    try:
        length = min(int(handler.headers.get("Content-Length", "0")), 16384)
        payload = json.loads(handler.rfile.read(length) or b"{}")
        from games.connect4 import (
            verify_init_data, create_game, play_move,
            play_bot_move, get_game_state,
        )
        from games.connect4_challenge import (
            get_connect4_challenge_state, choose_connect4_challenge_rps,
        )
        from games.mini_games import (
            get_mini_game_challenge_state, choose_mini_game_rps,
            play_mini_game_action, create_mini_game_solo,
            get_mini_game_solo_state, play_mini_game_solo_action,
            play_mini_game_solo_bot_move,
        )
        from games.online_mode import restart_online_game, get_online_spectator_state, online_lobby_api, withdraw_online_game
        if _bot is None:
            raise RuntimeError("البوت ما زال يستعد، حاول بعد قليل")
        user = verify_init_data(payload.get("initData", ""), _bot.token)
        is_challenge_api = path.startswith("/api/connect4/challenge/") or path.startswith("/api/minigames/") or path == "/api/extra-games"
        is_online_api = path in ("/api/online/restart", "/api/online/spectate", "/api/online/lobby", "/api/online/withdraw")
        if path == "/api/casual-games":
            from games import casual_games as casual
            action = str(payload.get("action") or "state")
            uid = int(user["id"])
            name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or user.get("username") or "مستخدم"
            if action == "create":
                result = _run(casual.create_game(uid, name, payload.get("game_type","match"), payload.get("mode","bot"), payload.get("settings") or {}))
            elif action == "join":
                result = _run(casual.join_game(uid, name, payload.get("game_id","")))
            elif action == "configure":
                result = _run(casual.configure_game(uid, payload.get("game_id",""), payload.get("settings") or {}))
            elif action == "start":
                result = _run(casual.start_game(uid, payload.get("game_id","")))
            elif action == "action":
                result = _run(casual.game_action(uid, payload.get("game_id",""), payload.get("move") or {}))
            elif action == "bot-turn":
                result = _run(casual.bot_turn(payload.get("game_id","")))
            else:
                result = _run(casual.get_state(uid, payload.get("game_id","")))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/extra-games":
            from games import extra_mini_games as extra
            action = str(payload.get("action") or "")
            game_type = str(payload.get("game_type") or "")
            uid = int(user["id"])
            profile = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or user.get("username") or "مستخدم"
            if game_type == "word":
                if action == "create":
                    result = _run(extra.word_create(uid, profile, payload.get("mode","online"), payload.get("word_count",5), payload.get("win_target"), payload.get("attempts_limit",6), payload.get("word_length",5), payload.get("round_seconds",180)))
                elif action == "join":
                    result = _run(extra.word_join(uid, profile, payload.get("game_id","")))
                elif action == "configure":
                    result = _run(extra.word_update_settings(
                        uid, payload.get("game_id",""), payload.get("word_count",5),
                        payload.get("win_target",3), payload.get("attempts_limit",6),
                        payload.get("word_length",5), payload.get("round_seconds",180),
                    ))
                elif action == "start":
                    result = _run(extra.word_start(uid, payload.get("game_id","")))
                elif action == "leave":
                    result = _run(extra.word_leave(uid, payload.get("game_id","")))
                elif action == "hint":
                    result = _run(extra.word_hint_vote(uid, payload.get("game_id","")))
                elif action == "guess":
                    result = _run(extra.word_guess(uid, payload.get("game_id",""), payload.get("guess","")))
                elif action == "next":
                    result = _run(extra.word_next(uid, payload.get("game_id","")))
                else:
                    result = _run(extra.word_state(uid, payload.get("game_id","")))
            else:
                raise ValueError("نوع اللعبة غير معروف")
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/online/lobby":
            result = _run(online_lobby_api(
                int(user["id"]), payload.get("action", "state"),
                payload.get("lobby_id", ""), payload.get("settings") or {},
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/online/withdraw":
            result = _run(withdraw_online_game(
                int(user["id"]), payload.get("game_type", ""), payload.get("game_id", "")
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/online/spectate":
            result = _run(get_online_spectator_state(
                int(user["id"]), payload.get("game_type", ""), payload.get("game_id", "")
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/online/restart":
            result = _run(restart_online_game(
                int(user["id"]), payload.get("game_type", ""), payload.get("game_id", "")
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/solo/new":
            result = _run(create_mini_game_solo(
                int(user["id"]), payload.get("game_type", ""),
                payload.get("difficulty", "متوسط"),
            ))
            me = _run(_bot.get_me())
            result["bot_name"] = me.first_name or me.username or "البوت"
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/solo/state":
            result = _run(get_mini_game_solo_state(
                int(user["id"]), payload.get("game_id", "")
            ))
            me = _run(_bot.get_me())
            result["bot_name"] = me.first_name or me.username or "البوت"
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/solo/action":
            result = _run(play_mini_game_solo_action(
                int(user["id"]), payload.get("game_id", ""),
                payload.get("action") or {},
            ))
            me = _run(_bot.get_me())
            result["bot_name"] = me.first_name or me.username or "البوت"
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/solo/bot-move":
            result = _run(play_mini_game_solo_bot_move(
                int(user["id"]), payload.get("game_id", "")
            ))
            me = _run(_bot.get_me())
            result["bot_name"] = me.first_name or me.username or "البوت"
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/challenge/state":
            result = _run(get_mini_game_challenge_state(
                int(user["id"]), payload.get("challenge_id", "")
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/challenge/choice":
            result = _run(choose_mini_game_rps(
                int(user["id"]), payload.get("challenge_id", ""),
                payload.get("choice", ""),
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/minigames/action":
            result = _run(play_mini_game_action(
                int(user["id"]), payload.get("challenge_id", ""),
                payload.get("action") or {},
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/connect4/challenge/state":
            result = _run(get_connect4_challenge_state(
                int(user["id"]), payload.get("challenge_id", "")
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path == "/api/connect4/challenge/choice":
            result = _run(choose_connect4_challenge_rps(
                int(user["id"]), payload.get("challenge_id", ""),
                payload.get("choice", ""),
            ))
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            handler.send_response(200)
        elif path.endswith("/new"):
            me = _run(_bot.get_me())
            state = _run(create_game(
                int(user["id"]), payload.get("difficulty", "متوسط"),
                bot_name=me.first_name or me.username or "البوت",
                bot_id=me.id,
                rps_choice=payload.get("rps_choice", "r"),
            ))
        elif path.endswith("/move"):
            state = _run(play_move(
                int(user["id"]), payload.get("game_id", ""), payload.get("column")
            ))
        elif path.endswith("/bot-move"):
            state = _run(play_bot_move(int(user["id"]), payload.get("game_id", "")))
        else:
            state = _run(get_game_state(int(user["id"]), payload.get("game_id", "")))
        if not is_challenge_api and not is_online_api:
            body = json.dumps({"ok": True, "game": state}, ensure_ascii=False).encode()
            handler.send_response(200)
    except ValueError as exc:
        body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode()
        handler.send_response(400)
    except Exception:
        logging.getLogger(__name__).exception("Connect 4 request failed")
        body = json.dumps({"ok": False, "error": "تعذر تنفيذ الحركة الآن، حاول مرة ثانية"} , ensure_ascii=False).encode()
        handler.send_response(503)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True
