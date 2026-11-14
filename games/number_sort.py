from __future__ import annotations

import json
import random
import time
import uuid
from database.pool import get_pool

SIZES = (3, 4, 5)
DEFAULT_COLOR = "#7f1d2d"


def _obj(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def _board(size):
    goal = list(range(1, size * size)) + [0]
    board = goal[:]
    blank = len(board) - 1
    previous = -1
    for _ in range(size * size * 24):
        row, col = divmod(blank, size)
        options = []
        if row: options.append(blank - size)
        if row < size - 1: options.append(blank + size)
        if col: options.append(blank - 1)
        if col < size - 1: options.append(blank + 1)
        if previous in options: options.remove(previous)
        nxt = random.choice(options)
        board[blank], board[nxt] = board[nxt], board[blank]
        previous, blank = blank, nxt
    return board


def _progress(board):
    return sum(1 for i, value in enumerate(board) if value and value == i + 1)


def _public(row, uid):
    players = _obj(row["players"])
    settings = _obj(row["settings"])
    state = _obj(row["state"])
    return {
        "id": row["id"].hex,
        "status": row["status"],
        "mode": row["mode"],
        "owner_id": int(row["owner_id"]),
        "is_owner": int(row["owner_id"]) == int(uid),
        "settings": settings,
        "players": [{
            "id": int(p["id"]), "name": p["name"], "bot": bool(p.get("bot")),
            "board": p.get("board", []), "moves": int(p.get("moves", 0)),
            "progress": _progress(p.get("board", [])),
            "solved": _progress(p.get("board", [])) == settings["size"] * settings["size"] - 1,
        } for p in players],
        "deadline": state.get("deadline"),
        "winner_id": state.get("winner_id"),
        "end_reason": state.get("end_reason"),
        "remaining": max(0, int(state.get("deadline", 0)) - int(time.time())) if state.get("deadline") else None,
    }


def _score(players, size):
    if not players:
        return None
    best_progress = max(_progress(p.get("board", [])) for p in players)
    tied = [p for p in players if _progress(p.get("board", [])) == best_progress]
    return int(tied[0]["id"]) if len(tied) == 1 else None


async def get_settings():
    row = await get_pool().fetchrow("SELECT background_file_id,tile_color FROM number_sort_settings WHERE id=1")
    return {"background": ("/number-sort/background" if row and row["background_file_id"] else None),
            "tile_color": (row["tile_color"] if row and row["tile_color"] else DEFAULT_COLOR)}


async def save_settings(*, background_file_id=None, tile_color=None, reset_background=False, reset_color=False):
    pool = get_pool()
    await pool.execute("INSERT INTO number_sort_settings(id) VALUES(1) ON CONFLICT(id) DO NOTHING")
    if reset_background:
        await pool.execute("UPDATE number_sort_settings SET background_file_id=NULL,updated_at=NOW() WHERE id=1")
    elif background_file_id:
        await pool.execute("UPDATE number_sort_settings SET background_file_id=$1,updated_at=NOW() WHERE id=1", background_file_id)
    if reset_color:
        await pool.execute("UPDATE number_sort_settings SET tile_color=$1,updated_at=NOW() WHERE id=1", DEFAULT_COLOR)
    elif tile_color:
        await pool.execute("UPDATE number_sort_settings SET tile_color=$1,updated_at=NOW() WHERE id=1", tile_color.lower())


async def get_background_file():
    return await get_pool().fetchval("SELECT background_file_id FROM number_sort_settings WHERE id=1")


async def create_game(user_id, name, mode, size, duration):
    if mode not in ("bot", "online"): raise ValueError("طريقة اللعب غير صحيحة")
    size, duration = int(size), int(duration)
    if size not in SIZES: raise ValueError("اختر لوحة 3×3 أو 4×4 أو 5×5")
    if not 30 <= duration <= 420: raise ValueError("مدة القيم من 30 ثانية إلى 7 دقائق")
    uid, gid = int(user_id), uuid.uuid4()
    board = _board(size)
    players = [{"id": uid, "name": str(name or "لاعب")[:80], "board": board[:], "moves": 0}]
    if mode == "bot":
        players.append({"id": -1, "name": "البوت", "bot": True, "board": board[:], "moves": 0})
    state = {"deadline": int(time.time()) + duration if mode == "bot" else None, "winner_id": None}
    status = "playing" if mode == "bot" else "waiting"
    row = await get_pool().fetchrow(
        """INSERT INTO number_sort_rooms(id,owner_id,mode,status,players,settings,state)
           VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb) RETURNING *""",
        gid, uid, mode, status, json.dumps(players, ensure_ascii=False),
        json.dumps({"size": size, "duration": duration}, ensure_ascii=False),
        json.dumps(state, ensure_ascii=False))
    return _public(row, uid)


async def join_game(user_id, name, raw_id):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row: raise ValueError("الغرفة غير موجودة")
            players = _obj(row["players"])
            if row["status"] == "waiting" and not any(int(p["id"]) == uid for p in players):
                if len(players) >= 5: raise ValueError("الغرفة مكتملة، الحد الأقصى 5 لاعبين")
                players.append({"id": uid, "name": str(name or "لاعب")[:80],
                                "board": players[0]["board"][:], "moves": 0})
                await c.execute("UPDATE number_sort_rooms SET players=$2::jsonb,updated_at=NOW() WHERE id=$1",
                                gid, json.dumps(players, ensure_ascii=False))
                row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1", gid)
    return _public(row, uid)


async def configure_game(user_id, raw_id, size, duration):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    size, duration = int(size), int(duration)
    if size not in SIZES:
        raise ValueError("اختر لوحة 3×3 أو 4×4 أو 5×5")
    if not 30 <= duration <= 420:
        raise ValueError("مدة القيم من 30 ثانية إلى 7 دقائق")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if int(row["owner_id"]) != uid:
                raise ValueError("إعدادات الغرفة لصاحبها فقط")
            if row["status"] != "waiting":
                raise ValueError("لا يمكن تغيير الإعدادات بعد بدء القيم")
            players = _obj(row["players"])
            board = _board(size)
            for player in players:
                player["board"] = board[:]
                player["moves"] = 0
            settings = {"size": size, "duration": duration}
            row = await c.fetchrow(
                """UPDATE number_sort_rooms
                   SET players=$2::jsonb,settings=$3::jsonb,updated_at=NOW()
                   WHERE id=$1 RETURNING *""",
                gid, json.dumps(players, ensure_ascii=False),
                json.dumps(settings, ensure_ascii=False),
            )
    return _public(row, uid)


async def start_game(user_id, raw_id):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row or int(row["owner_id"]) != uid: raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
            if row["status"] != "waiting": raise ValueError("الغرفة بدأت بالفعل")
            players = _obj(row["players"])
            if len(players) < 2: raise ValueError("تحتاج لاعبين على الأقل")
            size = int(_obj(row["settings"])["size"])
            board = _board(size)
            for p in players:
                p["board"], p["moves"] = board[:], 0
            settings = _obj(row["settings"])
            state = {"deadline": int(time.time()) + int(settings["duration"]), "winner_id": None}
            row = await c.fetchrow(
                "UPDATE number_sort_rooms SET status='playing',players=$2::jsonb,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                gid, json.dumps(players, ensure_ascii=False), json.dumps(state))
    return _public(row, uid)


async def _finish_if_needed(c, row):
    players, state, settings = _obj(row["players"]), _obj(row["state"]), _obj(row["settings"])
    if row["status"] != "playing": return row
    now = int(time.time())
    solved = next((p for p in players if _progress(p.get("board", [])) == int(settings["size"]) ** 2 - 1), None)
    if solved:
        state["winner_id"], state["end_reason"] = int(solved["id"]), "solved"
    elif state.get("deadline") and now >= int(state["deadline"]):
        state["winner_id"], state["end_reason"] = _score(players, int(settings["size"])), "timeout"
    else:
        return row
    return await c.fetchrow(
        "UPDATE number_sort_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
        row["id"], json.dumps(state, ensure_ascii=False))


async def move(user_id, raw_id, index):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row: raise ValueError("اللعبة غير موجودة")
            row = await _finish_if_needed(c, row)
            if row["status"] != "playing": return _public(row, uid)
            players, settings = _obj(row["players"]), _obj(row["settings"])
            player = next((p for p in players if int(p["id"]) == uid), None)
            if not player or player.get("bot"): raise ValueError("أنت لست لاعبًا في هذه اللعبة")
            size, index = int(settings["size"]), int(index)
            board = player["board"]
            if index < 0 or index >= len(board): raise ValueError("المربع غير صالح")
            blank = board.index(0)
            r1, c1 = divmod(blank, size); r2, c2 = divmod(index, size)
            if abs(r1-r2) + abs(c1-c2) != 1: raise ValueError("تقدر تحرك المربع المجاور للفراغ فقط")
            board[blank], board[index] = board[index], board[blank]
            player["moves"] = int(player.get("moves", 0)) + 1
            row = await c.fetchrow(
                "UPDATE number_sort_rooms SET players=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                gid, json.dumps(players, ensure_ascii=False))
            row = await _finish_if_needed(c, row)
    return _public(row, uid)


async def bot_move(user_id, raw_id):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row: raise ValueError("اللعبة غير موجودة")
            row = await _finish_if_needed(c, row)
            if row["status"] != "playing" or row["mode"] != "bot" or int(row["owner_id"]) != uid:
                return _public(row, uid)
            players, settings = _obj(row["players"]), _obj(row["settings"])
            bot = next((p for p in players if p.get("bot")), None)
            if not bot: return _public(row, uid)
            board, size = bot["board"], int(settings["size"])
            blank = board.index(0); r, col = divmod(blank, size)
            opts = []
            for idx in (blank-size, blank+size, blank-1, blank+1):
                if idx < 0 or idx >= len(board): continue
                rr, cc = divmod(idx, size)
                if abs(rr-r)+abs(cc-col) != 1: continue
                candidate = board[:]; candidate[blank], candidate[idx] = candidate[idx], candidate[blank]
                distance = sum(abs((v-1)//size-i//size)+abs((v-1)%size-i%size)
                               for i,v in enumerate(candidate) if v)
                opts.append((distance, random.random(), candidate))
            if opts:
                bot["board"] = min(opts, key=lambda x: (x[0], x[1]))[2]
                bot["moves"] = int(bot.get("moves", 0)) + 1
                row = await c.fetchrow(
                    "UPDATE number_sort_rooms SET players=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                    gid, json.dumps(players, ensure_ascii=False))
                row = await _finish_if_needed(c, row)
    return _public(row, uid)


async def state(user_id, raw_id):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row: raise ValueError("الغرفة غير موجودة")
            row = await _finish_if_needed(c, row)
    return _public(row, uid)


async def leave(user_id, raw_id):
    gid, uid = uuid.UUID(hex=str(raw_id).replace("-", "")), int(user_id)
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM number_sort_rooms WHERE id=$1 FOR UPDATE", gid)
            if not row or row["status"] != "playing": raise ValueError("لا يمكن الانسحاب الآن")
            players, state = _obj(row["players"]), _obj(row["state"])
            if not any(int(p["id"]) == uid for p in players): raise ValueError("أنت لست لاعبًا")
            remaining = [p for p in players if int(p["id"]) != uid]
            state["winner_id"] = _score(remaining, int(_obj(row["settings"])["size"]))
            state["end_reason"], state["withdrawn_id"] = "withdraw", uid
            row = await c.fetchrow(
                "UPDATE number_sort_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                gid, json.dumps(state, ensure_ascii=False))
    return _public(row, uid)
