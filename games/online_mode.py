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
    "connect": ("Connect Four 🔴", "لعبة توصيل أربعة أقراص"),
    "dots": ("Dots and Boxes 🟦", "ارسم الخطوط واجمع أكبر عدد من المربعات"),
    "memory": ("Memory Match 🧠", "اختبر ذاكرتك وطابق الألوان والتسلسل"),
    "word": ("خمن الكلمة 🔤", "تحدَّ حتى 10 لاعبين واكتشفوا الكلمة قبل انتهاء الوقت"),
    "match": ("تطابق البطاقات 🃏", "طابق أكبر عدد من أزواج البطاقات ضد لاعب أو البوت"),
    "number": ("خمن الرقم 🔢", "اخمن الرقم الصحيح مع تلميحات أعلى أو أقل"),
}

def _safe_player_name(value, fallback: str) -> str:
    if isinstance(value, str):
        name = value.strip()
        if name and "InlineKeyboardButton" not in name and not name.startswith(("اللاعب ", "لاعب ")):
            return name
    return fallback


def _lobby_text(game_type: str, count: int, mode: str, joined_players=None) -> str:
    joined_players = joined_players or {}
    lines = [
        f"• {joined_players.get(i, 'بانتظار لاعب')}"
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



OWNER_ID = 8453977662


async def online_image_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if int(user.id) != OWNER_ID:
        await message.reply_text("هذا الأمر للمالك فقط.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("كونكت 4 🔴", callback_data="online_image:connect")],
        [InlineKeyboardButton("المربعات 🟦", callback_data="online_image:dots")],
        [InlineKeyboardButton("اختبر ذاكرتك 🧠", callback_data="online_image:memory")],
        [InlineKeyboardButton("خمن الكلمة 🔤", callback_data="online_image:word")],
        [InlineKeyboardButton("تطابق البطاقات 🃏", callback_data="online_image:match")],
        [InlineKeyboardButton("خمن الرقم 🔢", callback_data="online_image:number")],
    ])
    await message.reply_text("اختر اللعبة التي تريد إضافة صورتها، وبعدها أرسل الصورة:", reply_markup=keyboard)


async def online_image_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    if int(query.from_user.id) != OWNER_ID:
        await query.answer("هذا الخيار للمالك فقط.", show_alert=True)
        return
    game_type = query.data.split(":", 1)[1]
    if game_type not in GAME_INFO:
        await query.answer("اللعبة غير معروفة.", show_alert=True)
        return
    context.user_data["online_image_pending_game"] = game_type
    await query.answer()
    await query.edit_message_text(
        f"أرسل الآن صورة لعبة {GAME_INFO[game_type][0]} في هذه المحادثة."
    )


async def online_image_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    game_type = context.user_data.get("online_image_pending_game")
    if not user or not message or not game_type:
        return
    if int(user.id) != OWNER_ID:
        return
    if not message.photo:
        await message.reply_text("أرسل صورة عادية للعبة.")
        return
    file_id = message.photo[-1].file_id
    await get_pool().execute(
        """INSERT INTO online_game_images(game_type, photo_file_id, updated_by)
           VALUES($1,$2,$3)
           ON CONFLICT(game_type) DO UPDATE SET
             photo_file_id=EXCLUDED.photo_file_id,
             updated_by=EXCLUDED.updated_by,
             updated_at=NOW()""",
        game_type, file_id, int(user.id),
    )
    context.user_data.pop("online_image_pending_game", None)
    await message.reply_text(f"تم حفظ صورة {GAME_INFO[game_type][0]} ✅")


def _select_games(query: str):
    value = (query or "").strip().lower()
    supported_inline = ["connect", "dots", "memory", "word", "match", "number"]
    if not value:
        return supported_inline
    if any(word in value for word in ("كونكت", "connect", "4")):
        return ["connect"]
    if any(word in value for word in ("مربع", "المربعات", "dots", "dot")):
        return ["dots"]
    if any(word in value for word in ("ذاكرة", "ذاكرت", "memory")):
        return ["memory"]
    if any(word in value for word in ("بطاقات", "تطابق", "match", "كروت")):
        return ["match"]
    if any(word in value for word in ("رقم", "الرقم", "number")):
        return ["number"]
    if any(word in value for word in ("خمن", "كلمة", "word")):
        return ["word"]
    return supported_inline


async def online_games_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline = update.inline_query
    if not inline:
        return
    pool = get_pool()
    await pool.execute(
        "DELETE FROM online_game_lobbies WHERE created_at < NOW() - INTERVAL '2 days' AND status <> 'playing'"
    )
    results = []
    me = await context.bot.get_me()
    for game_type in _select_games(inline.query):
        title, description = GAME_INFO[game_type]
        if game_type in ("match", "number"):
            from games.casual_games import create_game
            game = await create_game(
                inline.from_user.id,
                inline.from_user.full_name or inline.from_user.first_name or "مستخدم",
                game_type, mode="online",
            )
            game_id = uuid.UUID(hex=game["id"])
            room_url = f"https://t.me/{me.username}?startapp=casual_{game_type}_{game_id.hex}"
            lobby_text = (
                f"🎮 غرفة أونلاين — {title}\\n\\n"
                f"أنشأ {inline.from_user.full_name or inline.from_user.first_name or 'لاعب'} غرفة جديدة.\\n"
                "افتحوا الغرفة من الزر بالأسفل للانضمام، ويمكن لصاحبها ضبط الإعدادات وبدء اللعب."
            )
            result_id = game_id.hex
        elif game_type == "word":
            from games.extra_mini_games import word_create
            game = await word_create(
                inline.from_user.id,
                inline.from_user.full_name or inline.from_user.first_name or "مستخدم",
                mode="online",
            )
            game_id = uuid.UUID(hex=game["id"])
            room_url = f"https://t.me/{me.username}?startapp=word_{game_id.hex}"
            lobby_text = (
                f"🔤 غرفة أونلاين — {title}\n\n"
                f"أنشأ {inline.from_user.full_name or inline.from_user.first_name or 'لاعب'} غرفة خمن الكلمة.\n"
                "انضموا من الزر بالأسفل، ويمكن لصاحب الغرفة بدء اللعبة بعد انضمام اللاعبين."
            )
            result_id = game_id.hex
        else:
            lobby_id = uuid.uuid4()
            await pool.execute(
                """INSERT INTO online_game_lobbies
                   (id,game_type,creator_id,creator_name)
                   VALUES($1,$2,$3,$4)""",
                lobby_id, game_type, inline.from_user.id,
                inline.from_user.full_name or inline.from_user.first_name or "مستخدم",
            )
            room_url = f"https://t.me/{me.username}?startapp=online_lobby_{lobby_id.hex}"
            lobby_text = (
                f"🎮 غرفة أونلاين — {title}\n\n"
                "افتحوا الغرفة من الزر بالأسفل للانضمام وضبط الإعدادات وبدء اللعبة داخل الميني آب."
            )
            result_id = lobby_id.hex
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("فتح غرفة اللعبة", url=room_url)
        ]])
        photo_file_id = await pool.fetchval(
            "SELECT photo_file_id FROM online_game_images WHERE game_type=$1",
            game_type,
        )
        # Article results are rendered as a vertical list: thumbnail on the side,
        # with the game title and description visible beside it.
        result_kwargs = {
            "id": result_id,
            "title": title,
            "description": description,
            "input_message_content": InputTextMessageContent(lobby_text),
            "reply_markup": keyboard,
        }
        if photo_file_id:
            photo_url = f"https://nawaf-bot-v2.onrender.com/tg-file/{photo_file_id}"
            result_kwargs["thumbnail_url"] = photo_url
            result_kwargs["thumbnail_width"] = 80
            result_kwargs["thumbnail_height"] = 80
        results.append(InlineQueryResultArticle(**result_kwargs))
    await inline.answer(results, cache_time=0, is_personal=True)


async def _edit_lobby_message(query, context, text, keyboard):
    if query.inline_message_id:
        try:
            await context.bot.edit_message_caption(
                caption=text, inline_message_id=query.inline_message_id,
                reply_markup=keyboard,
            )
        except Exception:
            await context.bot.edit_message_text(
                text=text, inline_message_id=query.inline_message_id,
                reply_markup=keyboard,
            )
    elif query.message:
        if query.message.photo:
            await query.edit_message_caption(caption=text, reply_markup=keyboard)
        else:
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
        await _edit_lobby_message(query, context, _lobby_text("dots", count, mode), keyboard)
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
                    lobby_id, user.id, user.full_name or user.username or "مستخدم", chat_id,
                )

            lobby = await conn.fetchrow(
                "SELECT * FROM online_game_lobbies WHERE id=$1 FOR UPDATE",
                lobby_id,
            )
            player1_name = _safe_player_name(lobby["creator_name"], "مستخدم")
            player2_name = _safe_player_name(lobby["player2_name"], "مستخدم")
            players = [
                (lobby["creator_id"], _safe_player_name(lobby["creator_name"], "مستخدم"), bool(lobby["creator_joined"])),
                (lobby["player2_id"], _safe_player_name(lobby["player2_name"], "مستخدم"), bool(lobby["player2_id"])),
                (lobby["player3_id"], _safe_player_name(lobby["player3_name"], "مستخدم"), bool(lobby["player3_id"])),
                (lobby["player4_id"], _safe_player_name(lobby["player4_name"], "مستخدم"), bool(lobby["player4_id"])),
            ][:int(lobby["player_count"])]
            joined_count = sum(1 for pid, name, joined in players if pid is not None and joined)
            if joined_count < int(lobby["player_count"]):
                joined_names = {
                    i: name for i, (pid, name, joined) in enumerate(players)
                    if pid is not None and joined
                }
                waiting_text = _lobby_text(
                    lobby["game_type"], int(lobby["player_count"]),
                    lobby["team_mode"], joined_names,
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
                        names_for_game = [x[1] or "مستخدم" for i, x in enumerate(players)]
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
                            "online_free": True,
                        }
                    else:
                        state = {
                            "sequence": [random.randrange(4) for _ in range(3)],
                            "level": 3, "progress": 0, "round_successes": [],
                            "starter_id": int(lobby["creator_id"]),
                            "multi_player_ids": [int(x[0]) for x in players],
                            "multi_player_names": [x[1] for x in players],
                            "player_count": len(players),
                            "online_free": True,
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


async def online_lobby_api(user_id: int, action: str, raw_lobby_id: str, settings=None):
    """Mini App lobby operations; all membership and start transitions are row-locked."""
    try:
        lobby_id = uuid.UUID(hex=str(raw_lobby_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط الغرفة غير صالح")
    pool = get_pool()
    user_id = int(user_id)
    settings = settings or {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            lobby = await conn.fetchrow(
                "SELECT * FROM online_game_lobbies WHERE id=$1 FOR UPDATE", lobby_id
            )
            if not lobby:
                raise ValueError("الغرفة غير موجودة")
            if action == "join":
                if lobby["status"] != "pending":
                    raise ValueError("الغرفة لم تعد تستقبل لاعبين")
                ids = [lobby["creator_id"], lobby["player2_id"], lobby["player3_id"], lobby["player4_id"]]
                if user_id not in [int(x) for x in ids if x is not None]:
                    slot = next((i for i in range(1, int(lobby["player_count"])) if ids[i] is None), -1)
                    if slot < 0:
                        raise ValueError("اكتمل عدد اللاعبين")
                    name = str(settings.get("name") or "مستخدم")[:80]
                    await conn.execute(
                        f"UPDATE online_game_lobbies SET player{slot+1}_id=$2,player{slot+1}_name=$3,updated_at=NOW() WHERE id=$1",
                        lobby_id, user_id, name,
                    )
            elif action == "configure":
                if user_id != int(lobby["creator_id"]):
                    raise ValueError("الإعدادات لصاحب الغرفة فقط")
                if lobby["status"] != "pending":
                    raise ValueError("لا يمكن تغيير الإعدادات بعد بدء اللعبة")
                count = int(settings.get("player_count", 2))
                mode = str(settings.get("team_mode", "individual"))
                if lobby["game_type"] == "dots":
                    if count not in (2, 3, 4):
                        raise ValueError("اختر لاعبين أو ثلاثة أو أربعة")
                    if mode not in ("individual", "teams") or (count != 4 and mode != "individual"):
                        raise ValueError("نظام الفرق متاح لأربعة لاعبين فقط")
                else:
                    if count != 2 or mode != "individual":
                        raise ValueError("هذه اللعبة تدعم لاعبين فقط")
                await conn.execute(
                    """UPDATE online_game_lobbies SET player_count=$2,team_mode=$3,
                       player2_id=NULL,player2_name=NULL,player3_id=NULL,player3_name=NULL,
                       player4_id=NULL,player4_name=NULL,creator_joined=FALSE,updated_at=NOW()
                       WHERE id=$1""",
                    lobby_id, count, mode,
                )
            elif action == "leave":
                if lobby["status"] != "pending":
                    raise ValueError("لا يمكن مغادرة الغرفة بعد بدء اللعبة")
                if user_id == int(lobby["creator_id"]):
                    await conn.execute("UPDATE online_game_lobbies SET status='cancelled',updated_at=NOW() WHERE id=$1", lobby_id)
                else:
                    for i in range(2, 5):
                        if lobby[f"player{i}_id"] is not None and int(lobby[f"player{i}_id"]) == user_id:
                            await conn.execute(
                                f"UPDATE online_game_lobbies SET player{i}_id=NULL,player{i}_name=NULL,updated_at=NOW() WHERE id=$1",
                                lobby_id,
                            )
                            break
            elif action == "start":
                if user_id != int(lobby["creator_id"]):
                    raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
                if lobby["status"] != "pending":
                    raise ValueError("الغرفة بدأت أو انتهت")
                count = int(lobby["player_count"])
                ids = [lobby["creator_id"], lobby["player2_id"], lobby["player3_id"], lobby["player4_id"]][:count]
                if any(x is None for x in ids):
                    raise ValueError("لا يمكن البدء قبل اكتمال عدد اللاعبين")
                names = [
                    _safe_player_name(lobby["creator_name"], "مستخدم"),
                    *[_safe_player_name(lobby[f"player{i}_name"], "مستخدم") for i in range(2, count+1)]
                ]
                game_id = uuid.uuid4()
                if lobby["game_type"] == "connect":
                    from games.connect4 import ROWS, COLS
                    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
                    await conn.execute(
                        """INSERT INTO connect4_games
                           (id,user_id,player2_id,difficulty,board,game_mode,chat_id,
                            player1_name,player2_name,turn_player_id,wager,wager_settled)
                           VALUES($1,$2,$3,'متوسط',$4::jsonb,'human',$5,$6,$7,$2,0,TRUE)""",
                        game_id, int(ids[0]), int(ids[1]), json.dumps(board),
                        lobby["chat_id"] or 0, names[0], names[1],
                    )
                else:
                    if lobby["game_type"] == "dots":
                        size = 4 if count == 2 else (5 if count == 3 else 6)
                        state = {
                            "h": [[0 for _ in range(size)] for _ in range(size + 1)],
                            "v": [[0 for _ in range(size + 1)] for _ in range(size)],
                            "boxes": [[0 for _ in range(size)] for _ in range(size)],
                            "scores": [0 for _ in ids],
                            "multi_player_ids": [int(x) for x in ids],
                            "multi_player_names": names,
                            "player_count": count,
                            "team_mode": lobby["team_mode"] if count == 4 else "individual",
                            "board_size": size,
                            "turn_index": 0,
                            "online_free": True,
                        }
                    else:
                        state = {
                            "sequence": [random.randrange(4) for _ in range(3)],
                            "level": 3, "progress": 0, "round_successes": [],
                            "starter_id": int(ids[0]),
                            "online_free": True,
                        }
                    await conn.execute(
                        """INSERT INTO mini_game_challenges
                           (id,game_type,chat_id,player1_id,player1_name,player2_id,player2_name,
                            player3_id,player3_name,player4_id,player4_name,
                            wager,status,turn_player_id,game_state,wager_settled)
                           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,1,'playing',$4,$12::jsonb,TRUE)""",
                        game_id, lobby["game_type"], lobby["chat_id"] or 0,
                        int(ids[0]), names[0], int(ids[1]), names[1],
                        int(ids[2]) if count >= 3 else None, names[2] if count >= 3 else None,
                        int(ids[3]) if count >= 4 else None, names[3] if count >= 4 else None,
                        json.dumps(state),
                    )
                await conn.execute(
                    "UPDATE online_game_lobbies SET status='playing',game_id=$2,updated_at=NOW() WHERE id=$1",
                    lobby_id, game_id,
                )
            elif action != "state":
                raise ValueError("طلب غير معروف")
            lobby = await conn.fetchrow("SELECT * FROM online_game_lobbies WHERE id=$1", lobby_id)
    photo_file_id = await pool.fetchval(
        "SELECT photo_file_id FROM online_game_images WHERE game_type=$1",
        lobby["game_type"],
    )
    count = int(lobby["player_count"])
    player_rows = [{"id": int(lobby["creator_id"]), "name": _safe_player_name(lobby["creator_name"], "مستخدم")}]
    for i in range(2, count + 1):
        pid = lobby[f"player{i}_id"]
        if pid is not None:
            player_rows.append({"id": int(pid), "name": _safe_player_name(lobby[f"player{i}_name"], "مستخدم")})
    return {
        "id": lobby_id.hex, "game_type": lobby["game_type"], "status": lobby["status"],
        "creator_id": int(lobby["creator_id"]), "player_count": count,
        "team_mode": lobby["team_mode"], "players": player_rows,
        "is_creator": user_id == int(lobby["creator_id"]),
        "is_joined": user_id in [p["id"] for p in player_rows],
        "game_id": lobby["game_id"].hex if lobby["game_id"] else None,
        "image_url": ("/tg-file/" + photo_file_id) if photo_file_id else None,
    }


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
                    "online_free": True,
                }
            else:
                state = {
                    "sequence": [random.randrange(4) for _ in range(3)],
                    "level": 3, "progress": 0, "round_successes": [],
                    "starter_id": starter,
                    "online_free": True,
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
            """SELECT player1_id,player2_id,player3_id,player4_id
               FROM mini_game_challenges WHERE id=$1 AND ($2='mini' OR game_type=$2)""",
            game_id, game_type
        )
        if not row:
            raise ValueError("اللعبة غير موجودة")
        player_ids = [int(row[f"player{i}_id"]) for i in range(1, 5) if row[f"player{i}_id"] is not None]
        is_player = int(user_id) in player_ids
        viewer_id = int(user_id) if is_player else int(row["player1_id"])
        result = await get_mini_game_challenge_state(viewer_id, game_id.hex)
        if is_player:
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


async def withdraw_online_game(user_id: int, game_type: str, raw_game_id: str):
    """End an online match as a forfeit when one of its players withdraws."""
    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("معرّف اللعبة غير صالح")
    user_id = int(user_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if game_type == "connect":
                row = await conn.fetchrow(
                    "SELECT * FROM connect4_games WHERE id=$1 AND game_mode='human' FOR UPDATE",
                    game_id,
                )
                if not row:
                    raise ValueError("المباراة غير موجودة")
                ids = [int(row["user_id"]), int(row["player2_id"])]
                if user_id not in ids:
                    raise ValueError("أنت لست لاعبًا في هذه المباراة")
                if row["status"] != "playing":
                    raise ValueError("المباراة منتهية بالفعل")
                winner_id = ids[1] if user_id == ids[0] else ids[0]
                updated = await conn.fetchrow(
                    """UPDATE connect4_games SET status='won',winner_id=$2,
                       turn_started_at=NOW(),updated_at=NOW() WHERE id=$1 RETURNING *""",
                    game_id, winner_id,
                )
                from games.connect4 import public_state
                return {"game": public_state(updated, user_id), "withdrawn": True}
            if game_type not in ("dots", "memory"):
                raise ValueError("نوع اللعبة غير معروف")
            from games.mini_games import _finish_game, _public_state
            row = await conn.fetchrow(
                "SELECT * FROM mini_game_challenges WHERE id=$1 FOR UPDATE", game_id
            )
            if not row:
                raise ValueError("المباراة غير موجودة")
            state = row["game_state"]
            if isinstance(state, str):
                state = json.loads(state)
            state = state or {}
            ids = state.get("multi_player_ids") or [
                int(row["player1_id"]), int(row["player2_id"])
            ]
            ids = [int(value) for value in ids]
            if user_id not in ids:
                raise ValueError("أنت لست لاعبًا في هذه المباراة")
            if row["status"] != "playing":
                raise ValueError("المباراة منتهية بالفعل")
            index = ids.index(user_id)
            if state.get("team_mode") == "teams" and len(ids) == 4:
                winner_id = ids[1] if index in (0, 2) else ids[0]
            else:
                remaining = [i for i in range(len(ids)) if i != index]
                scores = state.get("scores") or [0] * len(ids)
                winner_index = max(remaining, key=lambda i: (int(scores[i] or 0), -i))
                winner_id = ids[winner_index]
            updated = await _finish_game(conn, row, winner_id)
            return {"phase": "playing", "game": _public_state(updated, user_id), "withdrawn": True}
