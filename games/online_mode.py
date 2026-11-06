from __future__ import annotations

import json
import random
import uuid

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
    InputTextMessageContent, Update,
)
from telegram.ext import ContextTypes

from database.pool import get_pool

GAME_INFO = {
    "connect": ("كونكت 4 🔴", "لعبة توصيل أربعة أقراص"),
    "dots": ("المربعات 🟦", "ارسم الخطوط واجمع أكبر عدد من المربعات"),
    "memory": ("اختبر ذاكرتك 🧠", "احفظ التسلسل وتحدَّ لاعبًا آخر"),
}

def _safe_player_name(value, fallback: str) -> str:
    if isinstance(value, str):
        name = value.strip()
        if name and "InlineKeyboardButton" not in name:
            return name
    return fallback


def _lobby_text(game_type: str, count: int, mode: str, joined_players=None) -> str:
    joined_players = joined_players or {}
    lines = [
        f"• {joined_players.get(i, f'بانتظار اللاعب {i + 1}')}"
        for i in range(count)
    ]
    mode_label = "فريقين (2 ضد 2)" if count == 4 and mode == "teams" else "كل لاعب لحاله"
    return (
        f"🎮 غرفة أونلاين — {GAME_INFO[game_type][0]}\n\n"
        f"اللاعبون: {len(joined_players)}/{count}\n"
        + "\n".join(lines)
        + f"\n\nالطور: {mode_label}\n"
        + "اضغطوا «انضمام» حتى يكتمل عدد اللاعبين."
    )


def _select_games(query: str):
    value = (query or "").strip().lower()
    if not value:
        return list(GAME_INFO)
    if any(word in value for word in ("كونكت", "connect", "4")):
        return ["connect"]
    if any(word in value for word in ("مربع", "المربعات", "dots", "dot")):
        return ["dots"]
    if any(word in value for word in ("ذاكرة", "ذاكرت", "memory")):
        return ["memory"]
    return list(GAME_INFO)


async def online_games_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline = update.inline_query
    if not inline:
        return
    pool = get_pool()
    await pool.execute(
        "DELETE FROM online_game_lobbies WHERE created_at < NOW() - INTERVAL '2 days' AND status <> 'playing'"
    )
    results = []
    for game_type in _select_games(inline.query):
        lobby_id = uuid.uuid4()
        title, description = GAME_INFO[game_type]
        await pool.execute(
            """INSERT INTO online_game_lobbies
               (id,game_type,creator_id,creator_name)
               VALUES($1,$2,$3,$4)""",
            lobby_id, game_type, inline.from_user.id,
            inline.from_user.full_name or inline.from_user.first_name or "اللاعب الأول",
        )
        keyboard = InlineKeyboardMarkup(
            ([[InlineKeyboardButton("⚙️ إعدادات اللاعبين", callback_data=f"online_settings:{lobby_id.hex}")]]
             if game_type == "dots" else [])
            + [[InlineKeyboardButton("انضمام 👥", callback_data=f"online_join:{lobby_id.hex}")]]
        )
        results.append(InlineQueryResultArticle(
            id=lobby_id.hex,
            title=title,
            description=description,
            input_message_content=InputTextMessageContent(
                _lobby_text(game_type, 2, "individual")
            ),
            reply_markup=keyboard,
        ))
    await inline.answer(results, cache_time=0, is_personal=True)


async def _edit_lobby_message(query, context, text, keyboard):
    if query.inline_message_id:
        await context.bot.edit_message_text(
            text=text, inline_message_id=query.inline_message_id,
            reply_markup=keyboard,
        )
    elif query.message:
        await query.edit_message_text(text, reply_markup=keyboard)


async def online_lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    action = query.data.split(":", 1)[0]
    try:
        lobby_id = uuid.UUID(hex=query.data.split(":")[1])
    except (ValueError, IndexError):
        await query.answer("تعذر قراءة غرفة اللعب.", show_alert=True)
        return

    pool = get_pool()
    user = query.from_user
    action = query.data.split(":", 1)[0]
    if action == "online_settings":
        lobby = await pool.fetchrow("SELECT * FROM online_game_lobbies WHERE id=$1", lobby_id)
        if not lobby or lobby["status"] != "pending":
            await query.answer("الغرفة لم تعد متاحة.", show_alert=True)
            return
        if int(lobby["creator_id"]) != int(user.id):
            await query.answer("إعدادات الغرفة لصاحبها فقط.", show_alert=True)
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 لاعبان", callback_data=f"online_config:{lobby_id.hex}:2:individual"),
             InlineKeyboardButton("👥👥 أربعة لاعبين", callback_data=f"online_config:{lobby_id.hex}:4:choose")],
        ])
        await _edit_lobby_message(query, context, "⚙️ إعدادات لعبة المربعات\nاختر عدد اللاعبين ونظام اللعب:", keyboard)
        await query.answer()
        return
    if action == "online_config":
        parts = query.data.split(":")
        count, mode = int(parts[2]), parts[3]
        owner = await pool.fetchval("SELECT creator_id FROM online_game_lobbies WHERE id=$1 AND status='pending'", lobby_id)
        if owner is None or int(owner) != int(user.id):
            await query.answer("إعدادات الغرفة لصاحبها فقط.", show_alert=True)
            return
        if count not in (2, 4) or mode not in ("individual", "teams", "choose") or (count == 2 and mode != "individual"):
            await query.answer("الإعداد غير صالح.", show_alert=True)
            return
        if count == 4 and mode == "choose":
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 كل لاعب لحاله", callback_data=f"online_config:{lobby_id.hex}:4:individual"),
                InlineKeyboardButton("🤝 فريقين 2 ضد 2", callback_data=f"online_config:{lobby_id.hex}:4:teams"),
            ]])
            await _edit_lobby_message(query, context, "اختر نظام اللعب لأربعة لاعبين:", keyboard)
            await query.answer()
            return
        await pool.execute("UPDATE online_game_lobbies SET player_count=$2,team_mode=$3,updated_at=NOW() WHERE id=$1", lobby_id, count, mode)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("انضمام 👥", callback_data=f"online_join:{lobby_id.hex}")],
            [InlineKeyboardButton("⚙️ إعدادات اللاعبين", callback_data=f"online_settings:{lobby_id.hex}")],
        ])
        await _edit_lobby_message(query, context, f"🎮 غرفة أونلاين — {GAME_INFO['dots'][0]}\n\nعدد اللاعبين: {count}\nالطور: {'فريقين (2 ضد 2)' if mode == 'teams' else 'كل لاعب لحاله'}\n\nاضغطوا انضمام للانضمام إلى الغرفة.", keyboard)
        await query.answer("تم حفظ إعدادات اللاعبين.")
        return
    game_id = None
    game_type = None
    player1_name = player2_name = None
    chat_id = getattr(getattr(query, "message", None), "chat_id", None)
    waiting_text = None
    waiting_keyboard = None

    async with pool.acquire() as conn:
        async with conn.transaction():
            lobby = await conn.fetchrow(
                "SELECT * FROM online_game_lobbies WHERE id=$1 FOR UPDATE",
                lobby_id,
            )
            if not lobby or lobby["status"] != "pending":
                await query.answer("الغرفة لم تعد متاحة.", show_alert=True)
                return

            ids = [lobby["creator_id"], lobby["player2_id"], lobby["player3_id"], lobby["player4_id"]]
            joined_ids = [int(x) for x in ids[1:] if x is not None]
            if lobby["creator_joined"]:
                joined_ids.append(int(lobby["creator_id"]))
            if int(user.id) in joined_ids:
                await query.answer("أنت منضم بالفعل.", show_alert=True)
                return
            if int(user.id) == int(lobby["creator_id"]):
                slot = 0
            else:
                slot = next((i for i in range(1, int(lobby["player_count"])) if ids[i] is None), -1)
                if slot < 0:
                    await query.answer("اكتمل عدد اللاعبين.", show_alert=True)
                    return
            if slot == 0:
                await conn.execute(
                    "UPDATE online_game_lobbies SET creator_joined=TRUE,chat_id=COALESCE($2,chat_id),updated_at=NOW() WHERE id=$1",
                    lobby_id, chat_id,
                )
            else:
                id_col, name_col = f"player{slot+1}_id", f"player{slot+1}_name"
                await conn.execute(
                    f"UPDATE online_game_lobbies SET {id_col}=$2,{name_col}=$3,chat_id=COALESCE($4,chat_id),updated_at=NOW() WHERE id=$1",
                    lobby_id, user.id, user.full_name or user.first_name or f"اللاعب {slot+1}", chat_id,
                )

            lobby = await conn.fetchrow(
                "SELECT * FROM online_game_lobbies WHERE id=$1 FOR UPDATE",
                lobby_id,
            )
            player1_name = _safe_player_name(lobby["creator_name"], "اللاعب الأول")
            player2_name = _safe_player_name(lobby["player2_name"], "اللاعب الثاني")
            players = [
                (lobby["creator_id"], _safe_player_name(lobby["creator_name"], "اللاعب الأول"), bool(lobby["creator_joined"])),
                (lobby["player2_id"], _safe_player_name(lobby["player2_name"], "اللاعب الثاني"), bool(lobby["player2_id"])),
                (lobby["player3_id"], _safe_player_name(lobby["player3_name"], "اللاعب الثالث"), bool(lobby["player3_id"])),
                (lobby["player4_id"], _safe_player_name(lobby["player4_name"], "اللاعب الرابع"), bool(lobby["player4_id"])),
            ][:int(lobby["player_count"])]
            joined_count = sum(1 for pid, name, joined in players if pid is not None and joined)
            if joined_count < int(lobby["player_count"]):
                lines = [f"• {name if joined else 'بانتظار اللاعب ' + str(i+1)}" for i, (pid, name, joined) in enumerate(players)]
                waiting_text = (
                    f"🎮 غرفة أونلاين — {GAME_INFO[lobby['game_type']][0]}\n\n"
                    f"اللاعبون: {joined_count}/{lobby['player_count']}\n"
                    + "\n".join(lines) + "\n\n"
                    + ("الطور: فريقين (2 ضد 2)" if lobby["team_mode"] == "teams" else "الطور: كل لاعب لحاله")
                    + "\nاضغطوا «انضمام» حتى يكتمل عدد اللاعبين."
                )
                waiting_keyboard = InlineKeyboardMarkup(
                    ([[InlineKeyboardButton("⚙️ إعدادات اللاعبين", callback_data=f"online_settings:{lobby_id.hex}")]]
                     if lobby["game_type"] == "dots" else [])
                    + [[InlineKeyboardButton("انضمام 👥", callback_data=f"online_join:{lobby_id.hex}")]]
                )
            else:
                game_type = lobby["game_type"]
                chat_id = lobby["chat_id"] or 0
                await conn.execute(
                    """UPDATE online_game_lobbies SET status='starting',updated_at=NOW()
                       WHERE id=$1""",
                    lobby_id,
                )
                game_id = uuid.uuid4()
                if game_type == "connect":
                    from games.connect4 import ROWS, COLS
                    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
                    await conn.execute(
                        """INSERT INTO connect4_games
                           (id,user_id,player2_id,difficulty,board,game_mode,chat_id,
                            player1_name,player2_name,turn_player_id,wager,wager_settled)
                           VALUES($1,$2,$3,'متوسط',$4::jsonb,'human',$5,$6,$7,$2,0,TRUE)""",
                        game_id, int(lobby["creator_id"]), int(lobby["player2_id"]),
                        json.dumps(board), chat_id, player1_name, player2_name,
                    )
                else:
                    if game_type == "dots":
                        count = int(lobby["player_count"])
                        size = 4 if count == 2 else 6
                        ids_for_game = [int(x[0]) for x in players]
                        names_for_game = [x[1] or f"اللاعب {i+1}" for i, x in enumerate(players)]
                        state = {
                            "h": [[0 for _ in range(size)] for _ in range(size + 1)],
                            "v": [[0 for _ in range(size + 1)] for _ in range(size)],
                            "boxes": [[0 for _ in range(size)] for _ in range(size)],
                            "scores": [0 for _ in range(count)],
                            "multi_player_ids": ids_for_game,
                            "multi_player_names": names_for_game,
                            "player_count": count,
                            "team_mode": lobby["team_mode"] if count == 4 else "individual",
                            "board_size": size,
                            "turn_index": 0,
                        }
                    else:
                        state = {
                            "sequence": [random.randrange(4) for _ in range(3)],
                            "level": 3, "progress": 0, "round_successes": [],
                            "starter_id": int(lobby["creator_id"]),
                        }
                    await conn.execute(
                        """INSERT INTO mini_game_challenges
                           (id,game_type,chat_id,player1_id,player1_name,player2_id,player2_name,
                            player3_id,player3_name,player4_id,player4_name,
                            wager,status,turn_player_id,game_state,wager_settled)
                           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,1,'playing',$4,$12::jsonb,TRUE)""",
                        game_id, game_type, chat_id, int(lobby["creator_id"]),
                        player1_name, int(lobby["player2_id"]), player2_name,
                        int(lobby["player3_id"]) if lobby["player3_id"] else None, lobby["player3_name"],
                        int(lobby["player4_id"]) if lobby["player4_id"] else None, lobby["player4_name"],
                        json.dumps(state),
                    )
                await conn.execute(
                    """UPDATE online_game_lobbies SET status='playing',game_id=$2,updated_at=NOW()
                       WHERE id=$1""",
                    lobby_id, game_id,
                )

    if waiting_text:
        try:
            await _edit_lobby_message(query, context, waiting_text, waiting_keyboard)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Could not update online game join count")
        await query.answer("تم تسجيل انضمامك، ننتظر اللاعب الآخر.")
        return

    me = await context.bot.get_me()
    start_param = (
        f"online_c4_{game_id.hex}" if game_type == "connect"
        else f"online_mg_{game_id.hex}"
    )
    launch_url = f"https://t.me/{me.username}?startapp={start_param}"
    text = (
        f"✅ اكتمل عدد اللاعبين — {GAME_INFO[game_type][0]}\n\n"
        + "\n".join(f"👤 {name}" for _, name, _ in players)
        + "\n\nاضغطوا على الزر لفتح اللعبة والبدء مباشرة."
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 فتح اللعبة", url=launch_url)
    ]])
    try:
        await _edit_lobby_message(query, context, text, keyboard)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not update online game lobby message")
    await query.answer("اكتمل انضمام اللاعبين وبدأت الغرفة!")


async def restart_online_game(user_id: int, game_type: str, raw_game_id: str):
    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("معرّف اللعبة غير صالح")

    pool = get_pool()
    if game_type == "connect":
        from games.connect4 import ROWS, COLS, public_state
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """SELECT * FROM connect4_games WHERE id=$1
                       AND (user_id=$2 OR player2_id=$2) FOR UPDATE""",
                    game_id, int(user_id),
                )
                if not row:
                    raise ValueError("هذه اللعبة ليست لك")
                if row["status"] not in ("won", "draw", "lost"):
                    raise ValueError("اللعبة ما انتهت بعد")
                starter = random.choice([int(row["user_id"]), int(row["player2_id"])])
                board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
                row = await conn.fetchrow(
                    """UPDATE connect4_games SET board=$2::jsonb,status='playing',
                       last_move=NULL,winning_cells='[]'::jsonb,winner_id=NULL,
                       turn_player_id=$3,turn_started_at=NOW(),wager=0,wager_settled=TRUE,
                       updated_at=NOW() WHERE id=$1 RETURNING *""",
                    game_id, json.dumps(board), starter,
                )
                return public_state(row, int(user_id))

    if game_type not in ("dots", "memory"):
        raise ValueError("نوع اللعبة غير معروف")
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM mini_game_challenges WHERE id=$1
                   AND (player1_id=$2 OR player2_id=$2 OR player3_id=$2 OR player4_id=$2) FOR UPDATE""",
                game_id, int(user_id),
            )
            if not row:
                raise ValueError("هذه اللعبة ليست لك")
            if row["status"] not in ("won", "draw"):
                raise ValueError("اللعبة ما انتهت بعد")
            old_state = row["game_state"] if isinstance(row["game_state"], dict) else json.loads(row["game_state"])
            ids = old_state.get("multi_player_ids") or [int(row["player1_id"]), int(row["player2_id"])]
            starter = random.choice(ids)
            if game_type == "dots":
                size = int(old_state.get("board_size", 4))
                state = {
                    "h": [[0 for _ in range(size)] for _ in range(size + 1)],
                    "v": [[0 for _ in range(size + 1)] for _ in range(size)],
                    "boxes": [[0 for _ in range(size)] for _ in range(size)],
                    "scores": [0 for _ in ids],
                    "multi_player_ids": ids,
                    "multi_player_names": old_state.get("multi_player_names", [row["player1_name"], row["player2_name"]]),
                    "player_count": len(ids),
                    "team_mode": old_state.get("team_mode", "individual"),
                    "board_size": size,
                    "turn_index": ids.index(starter),
                }
            else:
                state = {
                    "sequence": [random.randrange(4) for _ in range(3)],
                    "level": 3, "progress": 0, "round_successes": [],
                    "starter_id": starter,
                }
            await conn.execute(
                """UPDATE mini_game_challenges SET status='playing',winner_id=NULL,
                   turn_player_id=$2,turn_started_at=NOW(),game_state=$3::jsonb,
                   player1_choice=NULL,player2_choice=NULL,rps_result=NULL,
                   wager=1,wager_settled=TRUE,updated_at=NOW() WHERE id=$1""",
                game_id, starter, json.dumps(state),
            )
    from games.mini_games import get_mini_game_challenge_state
    return await get_mini_game_challenge_state(int(user_id), game_id.hex)


async def get_online_spectator_state(user_id: int, game_type: str, raw_game_id: str):
    """Return a read-only live view for anyone opening a shared online game."""
    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    if game_type == "connect":
        from games.connect4 import get_game_state
        row = await pool.fetchrow(
            "SELECT user_id,player2_id FROM connect4_games WHERE id=$1 AND game_mode='human'", game_id
        )
        if not row:
            raise ValueError("اللعبة غير موجودة")
        if int(user_id) in (int(row["user_id"]), int(row["player2_id"])):
            return {"game": await get_game_state(int(user_id), game_id.hex)}
        state = await get_game_state(int(row["user_id"]), game_id.hex)
        latest_status = await pool.fetchval("SELECT status FROM connect4_games WHERE id=$1", game_id)
        state["status"] = latest_status or state["status"]
        state.update({"spectator": True, "your_turn": False, "my_piece": 0})
        return {"game": state}
    if game_type in ("dots", "memory", "mini"):
        from games.mini_games import get_mini_game_challenge_state
        row = await pool.fetchrow(
            "SELECT player1_id,player2_id FROM mini_game_challenges WHERE id=$1 AND ($2='mini' OR game_type=$2)",
            game_id, game_type
        )
        if not row:
            raise ValueError("اللعبة غير موجودة")
        viewer_id = int(user_id) if int(user_id) in (int(row["player1_id"]), int(row["player2_id"])) else int(row["player1_id"])
        result = await get_mini_game_challenge_state(viewer_id, game_id.hex)
        if int(user_id) in (int(row["player1_id"]), int(row["player2_id"])):
            return result
        latest_status = await pool.fetchval("SELECT status FROM mini_game_challenges WHERE id=$1", game_id)
        if result.get("phase") == "playing":
            game = result["game"]
            game.update({"status": latest_status or game["status"], "spectator": True,
                         "your_turn": False, "my_player": 0})
            return {"game": game}
        result["spectator"] = True
        return result
    raise ValueError("نوع اللعبة غير معروف")
