from __future__ import annotations

import json
import random
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.pool import get_pool
from database.points import charge_two_players

DEFAULT_WAGER = 20_000
TURN_SECONDS = {"dots": 15, "memory": 60}
GAME_NAMES = {"dots": "المربعات", "memory": "اختبر ذاكرتك"}


def _rps_winner(a: str, b: str) -> int:
    if a == b:
        return 0
    return 1 if (a, b) in (("r", "s"), ("p", "r"), ("s", "p")) else 2


async def mini_game_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat or chat.type not in ("group", "supergroup"):
        return
    text = (message.text or "").strip()
    parts = text.split()
    if text.startswith("اختبر ذاكرتك"):
        parts = ["ذاكرة"] + parts[2:]
    game_type = "dots" if parts[0] in ("مربعات", "المربعات") else "memory"
    target_message = message.reply_to_message
    target = target_message.from_user if target_message else None
    if not target:
        await message.reply_text("❌ استخدم الأمر بالرد على الشخص اللي تبي تتحداه.")
        return
    if target.is_bot or target.id == user.id:
        await message.reply_text("❌ تقدر تتحدى شخصًا آخر فقط.")
        return
    if len(parts) > 2:
        await message.reply_text("الاستخدام: مربعات أو مربعات 50000 — ذاكرة أو ذاكرة 50000")
        return
    wager = DEFAULT_WAGER
    if len(parts) == 2:
        try:
            wager = int(parts[1].replace(",", ""))
        except ValueError:
            await message.reply_text("❌ مبلغ الرهان غير صحيح.")
            return
    if wager < 1 or wager > 2_000_000_000:
        await message.reply_text("❌ اختر مبلغًا بين 1 و 2,000,000,000 نقطة.")
        return
    challenge_id = uuid.uuid4()
    pool = get_pool()
    await pool.execute(
        """INSERT INTO mini_game_challenges
           (id,game_type,chat_id,player1_id,player1_name,player2_id,player2_name,wager)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8)""",
        challenge_id, game_type, chat.id, user.id, user.first_name or "اللاعب الأول",
        target.id, target.first_name or "اللاعب الثاني", wager,
    )
    body = (
        f"## تحدي ↢ {GAME_NAMES[game_type]}\n\n"
        f"اللاعبين:\n• ↢ {user.first_name or 'اللاعب الأول'}\n"
        f"• ↢ {target.first_name or 'اللاعب الثاني'}\n\n"
        f"الرهان على كل لاعب: {wager:,} نقطة\n"
        f"جائزة الفوز: {wager * 2:,} نقطة🎖️\n\n"
        "(بانتظار قبول التحدي)"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("قبول التحدي", callback_data=f"mg:a:{challenge_id.hex}"),
        InlineKeyboardButton("رفض", callback_data=f"mg:d:{challenge_id.hex}"),
    ]])
    await message.reply_text(body, reply_markup=keyboard)


async def mini_game_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    _, action, raw_id = query.data.split(":", 2)
    try:
        challenge_id = uuid.UUID(hex=raw_id)
    except Exception:
        await query.answer("رابط التحدي غير صالح.", show_alert=True)
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM mini_game_challenges WHERE id=$1 FOR UPDATE", challenge_id
            )
            if not row:
                await query.answer("التحدي غير موجود.", show_alert=True)
                return
            user_id = int(query.from_user.id)
            if action == "d":
                if user_id not in (int(row["player1_id"]), int(row["player2_id"])):
                    await query.answer("هذا التحدي ليس لك.", show_alert=True)
                    return
                if row["status"] != "pending":
                    await query.answer("انتهى هذا التحدي.", show_alert=True)
                    return
                await conn.execute(
                    "UPDATE mini_game_challenges SET status='declined',updated_at=NOW() WHERE id=$1",
                    challenge_id,
                )
                await query.edit_message_text("تم رفض التحدي.", reply_markup=None)
                await query.answer("تم رفض التحدي.")
                return
            if action != "a":
                return
            if user_id != int(row["player2_id"]):
                await query.answer("اللاعب المدعو فقط يقدر يقبل التحدي.", show_alert=True)
                return
            if row["status"] != "pending":
                await query.answer("هذا التحدي لم يعد متاحًا.", show_alert=True)
                return
            await conn.execute(
                "UPDATE mini_game_challenges SET status='choosing',updated_at=NOW() WHERE id=$1",
                challenge_id,
            )
    charged = await charge_two_players(
        int(row["player1_id"]), int(row["player2_id"]), int(row["wager"])
    )
    if charged != "ok":
        await pool.execute(
            "UPDATE mini_game_challenges SET status='pending',updated_at=NOW() WHERE id=$1 AND status='choosing'",
            challenge_id,
        )
        who = "صاحب التحدي" if charged == "first_insufficient" else "أنت"
        await query.answer(f"{who} ما عنده رصيد كافٍ للرهان.", show_alert=True)
        return
    me = await context.bot.get_me()
    mini_url = f"https://t.me/{me.username}?startapp=mg_{challenge_id.hex}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 فتح الميني آب — ابدأ حجر ورقة مقص", url=mini_url)
    ]])
    await query.edit_message_text(
        f"✅ تم قبول تحدي {GAME_NAMES[row['game_type']]} وحُجز الرهان.\n\n"
        "افتحوا الميني آب من الزر بالأسفل، واختاروا حجر ورقة مقص لتحديد من يبدأ.",
        reply_markup=keyboard,
    )
    await query.answer("تم قبول التحدي وحُجز الرهان.")


def _decode_state(value):
    return json.loads(value) if isinstance(value, str) else value


def _public_state(row, user_id: int):
    game_type = row["game_type"]
    state = _decode_state(row["game_state"]) or {}
    ids = state.get("multi_player_ids") or [int(row["player1_id"]), int(row["player2_id"])]
    names = state.get("multi_player_names") or [row["player1_name"], row["player2_name"]]
    winner = row["winner_id"]
    status = row["status"]
    if status == "won":
        status = "won" if int(winner or 0) == int(user_id) else "lost"
    try:
        my_index = ids.index(int(user_id)) + 1
    except ValueError:
        my_index = 0
    try:
        turn_index = ids.index(int(row["turn_player_id"] or 0)) + 1
    except ValueError:
        turn_index = 0
    return {
        "id": str(row["id"]), "game_type": game_type, "status": status,
        "player1_name": names[0], "player2_name": names[1],
        "player_names": names, "player_scores": state.get("scores", [0] * len(ids)),
        "player_count": len(ids), "team_mode": state.get("team_mode", "individual"),
        "board_size": state.get("board_size", len(state.get("boxes", [])) or 4),
        "your_turn": int(row["turn_player_id"] or 0) == int(user_id),
        "turn_player_id": row["turn_player_id"], "turn_index": turn_index,
        "turn_started_at": int(row["turn_started_at"].timestamp() * 1000) if row["turn_started_at"] else None,
        "turn_seconds": TURN_SECONDS[game_type],
        "wager": int(row["wager"]), "winner_id": winner,
        "winner_name": names[ids.index(int(winner))] if winner is not None and int(winner) in ids else None,
        "my_player": my_index, "state": state,
    }


async def _settle_wager(conn, row, winner_id: int | None):
    if row["wager_settled"]:
        return
    first, second, amount = int(row["player1_id"]), int(row["player2_id"]), int(row["wager"])
    await conn.execute(
        "INSERT INTO points(user_id,points) VALUES($1,0),($2,0) ON CONFLICT(user_id) DO NOTHING",
        first, second,
    )
    if winner_id is None:
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", first, amount)
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", second, amount)
    else:
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", winner_id, amount * 2)
    await conn.execute(
        "UPDATE mini_game_challenges SET wager_settled=TRUE WHERE id=$1", row["id"]
    )


def _dots_edges():
    return {
        "h": [[0 for _ in range(4)] for _ in range(5)],
        "v": [[0 for _ in range(5)] for _ in range(4)],
        "boxes": [[0 for _ in range(4)] for _ in range(4)],
        "scores": [0, 0],
    }


def _available_dot_edges(state):
    edges = []
    rows = len(state["boxes"])
    cols = len(state["boxes"][0]) if rows else 0
    for r in range(rows + 1):
        for c in range(cols):
            if not state["h"][r][c]:
                edges.append({"kind": "h", "r": r, "c": c})
    for r in range(rows):
        for c in range(cols + 1):
            if not state["v"][r][c]:
                edges.append({"kind": "v", "r": r, "c": c})
    return edges


def _draw_dot_edge(state, edge, player):
    kind, r, c = edge["kind"], int(edge["r"]), int(edge["c"])
    matrix = state.get(kind)
    rows = len(state["boxes"])
    cols = len(state["boxes"][0]) if rows else 0
    max_r, max_c = ((rows + 1, cols) if kind == "h" else (rows, cols + 1))
    if kind not in ("h", "v") or not (0 <= r < max_r and 0 <= c < max_c):
        raise ValueError("الحركة غير صالحة")
    if matrix[r][c]:
        raise ValueError("هذا الخط مرسوم بالفعل")
    matrix[r][c] = player
    completed = []
    for br in range(rows):
        for bc in range(cols):
            if state["boxes"][br][bc]:
                continue
            closed = (
                state["h"][br][bc] and state["h"][br + 1][bc]
                and state["v"][br][bc] and state["v"][br][bc + 1]
            )
            if closed:
                state["boxes"][br][bc] = player
                state["scores"][player - 1] += 1
                completed.append([br, bc])
    return completed


async def _finish_game(conn, row, winner_id):
    status = "draw" if winner_id is None else "won"
    await _settle_wager(conn, row, winner_id)
    return await conn.fetchrow(
        """UPDATE mini_game_challenges SET status=$2,winner_id=$3,
           turn_started_at=NOW(),updated_at=NOW() WHERE id=$1 RETURNING *""",
        row["id"], status, winner_id,
    )


async def get_mini_game_challenge_state(user_id: int, raw_id: str):
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM mini_game_challenges WHERE id=$1
                   AND (player1_id=$2 OR player2_id=$2) FOR UPDATE""",
                game_id, user_id,
            )
            if not row:
                raise ValueError("هذا التحدي ليس لك أو لم يعد موجودًا")
            if row["status"] == "choosing":
                first = int(user_id) == int(row["player1_id"])
                return {"phase": "choosing", "player1_name": row["player1_name"],
                        "player2_name": row["player2_name"],
                        "my_choice": row["player1_choice"] if first else row["player2_choice"],
                        "opponent_chosen": bool(row["player2_choice"] if first else row["player1_choice"]),
                        "tie": row["rps_result"] == "tie"}
            if row["status"] not in ("playing", "won", "draw"):
                raise ValueError("هذا التحدي لم يعد متاحًا")
            if row["status"] == "playing":
                seconds = TURN_SECONDS[row["game_type"]]
                expired = await conn.fetchval(
                    "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                    row["turn_started_at"], seconds,
                )
                if expired:
                    if row["game_type"] == "memory":
                        winner_id = int(row["player2_id"] if row["turn_player_id"] == row["player1_id"] else row["player1_id"])
                        row = await _finish_game(conn, row, winner_id)
                    else:
                        state = _decode_state(row["game_state"])
                        edges = _available_dot_edges(state)
                        if edges:
                            player = 1 if int(row["turn_player_id"]) == int(row["player1_id"]) else 2
                            completed = _draw_dot_edge(state, random.choice(edges), player)
                            next_player = int(row["turn_player_id"]) if completed else int(
                                row["player2_id"] if row["turn_player_id"] == row["player1_id"] else row["player1_id"]
                            )
                            if sum(state["scores"]) == 16:
                                winner_id = int(row["player1_id"] if state["scores"][0] > state["scores"][1] else row["player2_id"]) if state["scores"][0] != state["scores"][1] else None
                                row = await _finish_game(conn, row, winner_id)
                            else:
                                row = await conn.fetchrow(
                                    """UPDATE mini_game_challenges SET game_state=$2::jsonb,
                                       turn_player_id=$3,turn_started_at=NOW(),updated_at=NOW()
                                       WHERE id=$1 RETURNING *""",
                                    game_id, json.dumps(state), next_player,
                                )
            return {"phase": "playing", "game": _public_state(row, user_id)}


async def choose_mini_game_rps(user_id: int, raw_id: str, choice: str):
    if choice not in ("r", "p", "s"):
        raise ValueError("اختر حجر أو ورقة أو مقص")
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM mini_game_challenges WHERE id=$1
                   AND (player1_id=$2 OR player2_id=$2) FOR UPDATE""",
                game_id, user_id,
            )
            if not row or row["status"] != "choosing":
                raise ValueError("مرحلة حجر ورقة مقص غير متاحة")
            first = int(user_id) == int(row["player1_id"])
            column = "player1_choice" if first else "player2_choice"
            if row[column]:
                raise ValueError("سجلت اختيارك بالفعل، انتظر اللاعب الآخر")
            row = await conn.fetchrow(
                f"""UPDATE mini_game_challenges SET {column}=$2,rps_result=NULL,
                    updated_at=NOW() WHERE id=$1 RETURNING *""",
                game_id, choice,
            )
            if not row["player1_choice"] or not row["player2_choice"]:
                return {"phase": "choosing", "my_choice": choice, "opponent_chosen": False}
            winner = _rps_winner(row["player1_choice"], row["player2_choice"])
            if winner == 0:
                await conn.execute(
                    """UPDATE mini_game_challenges SET player1_choice=NULL,
                       player2_choice=NULL,rps_result='tie',updated_at=NOW() WHERE id=$1""",
                    game_id,
                )
                return {"phase": "choosing", "tie": True}
            starter = int(row["player1_id"] if winner == 1 else row["player2_id"])
            if row["game_type"] == "dots":
                state = _dots_edges()
            else:
                state = {"sequence": [random.randrange(4), random.randrange(4), random.randrange(4)],
                         "level": 3, "progress": 0, "round_successes": [],
                         "starter_id": starter}
            row = await conn.fetchrow(
                """UPDATE mini_game_challenges SET status='playing',turn_player_id=$2,
                   turn_started_at=NOW(),game_state=$3::jsonb,
                   rps_result=$4,updated_at=NOW() WHERE id=$1 RETURNING *""",
                game_id, starter, json.dumps(state),
                "player1_starts" if winner == 1 else "player2_starts",
            )
            return {"phase": "playing", "game": _public_state(row, user_id)}


async def play_mini_game_action(user_id: int, raw_id: str, action: dict):
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM mini_game_challenges WHERE id=$1
                   AND (player1_id=$2 OR player2_id=$2) FOR UPDATE""",
                game_id, user_id,
            )
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة غير متاحة الآن")
            if int(row["turn_player_id"]) != int(user_id):
                raise ValueError("انتظر دورك")
            state = _decode_state(row["game_state"])
            first = int(user_id) == int(row["player1_id"])
            player = 1 if first else 2
            other_id = int(row["player2_id"] if first else row["player1_id"])
            expired = await conn.fetchval(
                "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                row["turn_started_at"], TURN_SECONDS[row["game_type"]],
            )
            if expired and row["game_type"] == "memory":
                row = await _finish_game(conn, row, other_id)
                return {"phase": "playing", "game": _public_state(row, user_id)}
            if row["game_type"] == "dots":
                edge = random.choice(_available_dot_edges(state)) if expired else action
                completed = _draw_dot_edge(state, edge, player)
                if sum(state["scores"]) == 16:
                    winner_id = int(row["player1_id"] if state["scores"][0] > state["scores"][1] else row["player2_id"]) if state["scores"][0] != state["scores"][1] else None
                    row = await _finish_game(conn, row, winner_id)
                else:
                    next_player = int(user_id) if completed else other_id
                    row = await conn.fetchrow(
                        """UPDATE mini_game_challenges SET game_state=$2::jsonb,
                           turn_player_id=$3,turn_started_at=NOW(),updated_at=NOW()
                           WHERE id=$1 RETURNING *""",
                        game_id, json.dumps(state), next_player,
                    )
            else:
                color = action.get("color")
                if isinstance(color, bool) or not isinstance(color, int) or color not in range(4):
                    raise ValueError("اختيار اللون غير صالح")
                progress = int(state["progress"])
                if color != int(state["sequence"][progress]):
                    row = await _finish_game(conn, row, other_id)
                else:
                    progress += 1
                    if progress >= int(state["level"]):
                        passed = list(state.get("round_successes", []))
                        passed.append(int(user_id))
                        state["round_successes"] = passed
                        state["progress"] = 0
                        if len(passed) >= 2:
                            if int(state["level"]) >= 12:
                                row = await _finish_game(conn, row, None)
                            else:
                                state["level"] = int(state["level"]) + 1
                                state["sequence"].append(random.randrange(4))
                                state["round_successes"] = []
                                row = await conn.fetchrow(
                                    """UPDATE mini_game_challenges SET game_state=$2::jsonb,
                                       turn_player_id=$3,turn_started_at=NOW(),updated_at=NOW()
                                       WHERE id=$1 RETURNING *""",
                                    game_id, json.dumps(state), int(state.get("starter_id") or row["player1_id"]),
                                )
                        else:
                            row = await conn.fetchrow(
                                """UPDATE mini_game_challenges SET game_state=$2::jsonb,
                                   turn_player_id=$3,turn_started_at=NOW(),updated_at=NOW()
                                   WHERE id=$1 RETURNING *""",
                                game_id, json.dumps(state), other_id,
                            )
                    else:
                        state["progress"] = progress
                        row = await conn.fetchrow(
                            """UPDATE mini_game_challenges SET game_state=$2::jsonb,
                               updated_at=NOW() WHERE id=$1 RETURNING *""",
                            game_id, json.dumps(state),
                        )
            return {"phase": "playing", "game": _public_state(row, user_id)}


# Solo mode: player versus a lightweight local AI.
SOLO_LEVELS = ("سهل", "متوسط", "صعب", "مستحيل")
SOLO_TURN_SECONDS = {"dots": 30, "memory": 90}


def _solo_decode(value):
    return json.loads(value) if isinstance(value, str) else value


def _solo_public(row):
    state = _solo_decode(row["game_state"]) or {}
    return {
        "id": str(row["id"]), "game_type": row["game_type"],
        "difficulty": row["difficulty"], "status": row["status"],
        "your_turn": int(row["turn_player_id"]) == int(row["user_id"]),
        "turn_player_id": int(row["turn_player_id"]),
        "turn_started_at": int(row["turn_started_at"].timestamp() * 1000) if row["turn_started_at"] else None,
        "turn_seconds": SOLO_TURN_SECONDS[row["game_type"]],
        "player_name": "أنت", "bot_name": "البوت",
        "state": state,
    }


def _solo_winner(state):
    a, b = state["scores"]
    return "won" if a > b else "lost" if b > a else "draw"


def _solo_edge_score(state, edge, player):
    trial = json.loads(json.dumps(state))
    completed = _draw_dot_edge(trial, edge, player)
    score = len(completed) * 100
    if not completed:
        # Avoid handing the opponent a box with three surrounding edges.
        kind, r, c = edge["kind"], edge["r"], edge["c"]
        for br in range(4):
            for bc in range(4):
                if trial["boxes"][br][bc]:
                    continue
                count = int(bool(trial["h"][br][bc])) + int(bool(trial["h"][br+1][bc])) + int(bool(trial["v"][br][bc])) + int(bool(trial["v"][br][bc+1]))
                if count == 3:
                    score -= 30
                elif count == 2:
                    score -= 2
    return score, trial, completed


def _choose_solo_dot_edge(state, difficulty):
    edges = _available_dot_edges(state)
    if not edges:
        return None
    if difficulty == "سهل":
        return random.choice(edges)
    scored = [(_solo_edge_score(state, edge, 2)[0], edge) for edge in edges]
    best = max(score for score, _ in scored)
    if difficulty == "متوسط":
        pool = [edge for score, edge in scored if score >= best - 20]
        return random.choice(pool)
    # Hard/impossible prefer immediate boxes and avoid creating easy gifts.
    best_edges = [edge for score, edge in scored if score == best]
    if difficulty == "صعب":
        return random.choice(best_edges)
    # One-ply lookahead: choose the move with the best worst reply for the human.
    candidates = []
    for edge in best_edges:
        _, trial, completed = _solo_edge_score(state, edge, 2)
        if completed:
            candidates.append((100 + len(completed) * 10, edge))
            continue
        replies = _available_dot_edges(trial)
        worst = min((_solo_edge_score(trial, reply, 1)[0] for reply in replies), default=0)
        candidates.append((-worst, edge))
    return max(candidates, key=lambda item: item[0])[1]


async def create_mini_game_solo(user_id: int, game_type: str, difficulty: str):
    if game_type not in ("dots", "memory"):
        raise ValueError("اللعبة غير معروفة")
    if difficulty not in SOLO_LEVELS:
        raise ValueError("اختر مستوى صعوبة صحيحًا")
    game_id = uuid.uuid4()
    if game_type == "dots":
        state = _dots_edges()
        turn = int(user_id)
    else:
        state = {"sequence": [random.randrange(4) for _ in range(3)],
                 "level": 3, "progress": 0, "rounds_won": 0}
        turn = int(user_id)
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO mini_game_solo
           (id,user_id,game_type,difficulty,turn_player_id,game_state)
           VALUES($1,$2,$3,$4,$5,$6::jsonb) RETURNING *""",
        game_id, int(user_id), game_type, difficulty, turn, json.dumps(state),
    )
    return _solo_public(row)


async def get_mini_game_solo_state(user_id: int, raw_id: str):
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM mini_game_solo WHERE id=$1 AND user_id=$2",
        game_id, int(user_id),
    )
    if not row:
        raise ValueError("اللعبة غير موجودة")
    return _solo_public(row)


async def _solo_update(conn, row, state, turn, status=None):
    return await conn.fetchrow(
        """UPDATE mini_game_solo SET game_state=$2::jsonb,turn_player_id=$3,
           status=COALESCE($4,status),turn_started_at=NOW(),updated_at=NOW()
           WHERE id=$1 RETURNING *""",
        row["id"], json.dumps(state), int(turn), status,
    )


async def play_mini_game_solo_action(user_id: int, raw_id: str, action: dict):
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM mini_game_solo WHERE id=$1 AND user_id=$2 FOR UPDATE",
                game_id, int(user_id),
            )
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة انتهت أو غير موجودة")
            if int(row["turn_player_id"]) != int(user_id):
                raise ValueError("انتظر دورك")
            state = _solo_decode(row["game_state"])
            expired = await conn.fetchval(
                "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                row["turn_started_at"], SOLO_TURN_SECONDS[row["game_type"]],
            )
            if row["game_type"] == "dots":
                edge = random.choice(_available_dot_edges(state)) if expired or action.get("automatic") else action
                completed = _draw_dot_edge(state, edge, 1)
                if sum(state["scores"]) >= 16:
                    status = _solo_winner(state)
                    row = await _solo_update(conn, row, state, int(user_id), status)
                else:
                    row = await _solo_update(conn, row, state, -1 if not completed else int(user_id))
            else:
                if expired:
                    row = await _solo_update(conn, row, state, int(user_id), "lost")
                else:
                    color = action.get("color")
                    if isinstance(color, bool) or not isinstance(color, int) or color not in range(4):
                        raise ValueError("اختيار اللون غير صالح")
                    progress = int(state["progress"])
                    if color != int(state["sequence"][progress]):
                        row = await _solo_update(conn, row, state, int(user_id), "lost")
                    else:
                        progress += 1
                        if progress < int(state["level"]):
                            state["progress"] = progress
                            row = await conn.fetchrow(
                                "UPDATE mini_game_solo SET game_state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                                game_id, json.dumps(state),
                            )
                        else:
                            state["progress"] = 0
                            state["rounds_won"] = int(state.get("rounds_won", 0)) + 1
                            chances = {"سهل": 0.38, "متوسط": 0.62, "صعب": 0.82, "مستحيل": 0.96}
                            bot_passes = random.random() < chances[row["difficulty"]]
                            if not bot_passes:
                                row = await _solo_update(conn, row, state, int(user_id), "won")
                            elif int(state["level"]) >= 12:
                                row = await _solo_update(conn, row, state, int(user_id), "won")
                            else:
                                state["level"] = int(state["level"]) + 1
                                state["sequence"].append(random.randrange(4))
                                row = await _solo_update(conn, row, state, int(user_id))
            return _solo_public(row)


async def play_mini_game_solo_bot_move(user_id: int, raw_id: str):
    try:
        game_id = uuid.UUID(hex=raw_id.replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM mini_game_solo WHERE id=$1 AND user_id=$2 FOR UPDATE",
                game_id, int(user_id),
            )
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة انتهت أو غير موجودة")
            if int(row["turn_player_id"]) != -1:
                return _solo_public(row)
            state = _solo_decode(row["game_state"])
            if row["game_type"] == "dots":
                edge = _choose_solo_dot_edge(state, row["difficulty"])
                if edge:
                    completed = _draw_dot_edge(state, edge, 2)
                    if sum(state["scores"]) >= 16:
                        status = _solo_winner(state)
                        row = await _solo_update(conn, row, state, -1, status)
                    else:
                        row = await _solo_update(conn, row, state, -1 if completed else int(user_id))
            return _solo_public(row)
