import asyncio
import html
import re
import uuid

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from database.points import get_points, transfer_points_atomic


# ============================================================
# إعدادات اللعبة
# ============================================================

DEFAULT_POINTS = 30
CHALLENGE_TIMEOUT = 120
ROUND_TIMEOUT = 60
CONTINUE_TIMEOUT = 60

MOVES = {
    "rock": "✊🏻",
    "paper": "🖐🏻",
    "scissors": "✌🏻",
}

MOVE_NAMES = {
    "rock": "حجرة",
    "paper": "ورقة",
    "scissors": "مقص",
}

# game_id -> game data
_active_games = {}
_game_lock = asyncio.Lock()


# ============================================================
# أدوات النص
# ============================================================

def escape_html(value):
    return html.escape(str(value or ""))


def user_name(user):
    name = user.first_name or user.username or "المستخدم"
    return (
        f'<a href="tg://user?id={user.id}">'
        f'{escape_html(name)}</a>'
    )


def get_player(game, user_id):
    if game["challenger_id"] == user_id:
        return game["challenger"]
    if game["target_id"] == user_id:
        return game["target_user"]
    return None


def get_required_wins(best_of):
    return (best_of // 2) + 1


def is_valid_move_pair(first, second):
    if first == second:
        return 0
    wins_against = {
        "rock": "scissors",
        "paper": "rock",
        "scissors": "paper",
    }
    return 1 if wins_against[first] == second else 2


# ============================================================
# لوحات الأزرار
# ============================================================

def build_rounds_keyboard(game):
    game_id = game["game_id"]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("BO1", callback_data=f"rps:{game_id}:rounds:1"),
            InlineKeyboardButton("BO3", callback_data=f"rps:{game_id}:rounds:3"),
        ],
        [
            InlineKeyboardButton("BO5", callback_data=f"rps:{game_id}:rounds:5"),
            InlineKeyboardButton("BO7", callback_data=f"rps:{game_id}:rounds:7"),
        ],
    ])


def build_accept_keyboard(game):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "قبول التحدي 🔥",
            callback_data=f"rps:{game['game_id']}:accept",
        )
    ]])


def build_moves_keyboard(game):
    game_id = game["game_id"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✊🏻", callback_data=f"rps:{game_id}:move:rock"),
        InlineKeyboardButton("🖐🏻", callback_data=f"rps:{game_id}:move:paper"),
        InlineKeyboardButton("✌🏻", callback_data=f"rps:{game_id}:move:scissors"),
    ]])


def build_continue_keyboard(game):
    label = "إعادة الجولة 🔁" if game.get("last_tie") else "كمل الجولة 🔥"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"rps:{game['game_id']}:next")
    ]])


# ============================================================
# نصوص الرسائل
# ============================================================

def build_challenge_caption(game):
    return (
        "<b>• تم بدء لعبة حجرة ورقة مقص ✊🏻🖐🏻✌🏻</b>\n"
        f"<b>• عدد النقاط : {game['points']} 🎖️</b>\n"
        f"<b>• تم اختيار ↤ {user_name(game['target_user'])}</b>\n"
        "<b>• حدد الجولات الي تبيها بالزر الي تحت</b>"
    )


def build_accept_caption(game):
    return (
        "<b>• تم بدء لعبة حجرة ورقة مقص ✊🏻🖐🏻✌🏻</b>\n"
        f"<b>• عدد النقاط : {game['points']} 🎖️</b>\n"
        f"<b>• عدد الجولات : BO{game['best_of']}</b>\n"
        f"<b>• تم اختيار ↤ {user_name(game['target_user'])}</b>\n"
        "<b>• عشان تلعب معه اضغط الزر</b>"
    )


def build_round_caption(game):
    number = game["round_number"]
    challenger_wins = game["wins"][game["challenger_id"]]
    target_wins = game["wins"][game["target_id"]]
    return (
        f"<b>الجولة {number} 🎮</b>\n\n"
        "<b>• ركززز ورووووق واختر الي تبي تحطه.</b>\n\n"
        f"<b>• {user_name(game['challenger'])} : {challenger_wins}</b>\n"
        f"<b>• {user_name(game['target_user'])} : {target_wins}</b>"
    )


def build_round_result_caption(game, first_move, second_move, round_winner_id):
    challenger = game["challenger"]
    target = game["target_user"]
    challenger_move = first_move if game["challenger_id"] in game["choices"] else second_move
    # الاختيارات محفوظة بمعرّف كل لاعب؛ نقرأها مباشرة لتفادي الاعتماد على ترتيب الضغط.
    challenger_move = game["round_choices"][game["challenger_id"]]
    target_move = game["round_choices"][game["target_id"]]

    if round_winner_id is None:
        return (
            "<b>تعادل!! 😂😂</b>\n\n"
            f"<b>{user_name(challenger)} حط {MOVES[challenger_move]}</b>\n"
            f"<b>{user_name(target)} حط {MOVES[target_move]}</b>\n\n"
            "<b>• محد فاز بالجولة، بنعيدها.</b>"
        )

    winner = get_player(game, round_winner_id)
    loser = target if round_winner_id == game["challenger_id"] else challenger
    winner_move = challenger_move if round_winner_id == game["challenger_id"] else target_move
    loser_move = target_move if round_winner_id == game["challenger_id"] else challenger_move
    return (
        "<b>انتهت الجولة 🎉</b>\n\n"
        f"<b>• الفائز بالجولة 🏆 : {user_name(winner)} {MOVES[winner_move]}</b>\n"
        f"<b>• اختياره : {MOVE_NAMES[winner_move]}</b>\n"
        f"<b>• اختيار الخصم : {MOVES[loser_move]}</b>\n\n"
        f"<b>• النتيجة : {game['wins'][game['challenger_id']]} - {game['wins'][game['target_id']]}</b>"
    )


def build_final_caption(game, winner_id, amount_transferred):
    winner = get_player(game, winner_id)
    loser_id = game["target_id"] if winner_id == game["challenger_id"] else game["challenger_id"]
    loser = get_player(game, loser_id)
    return (
        "<b>انتهت اللعبة 🎉🥳</b>\n\n"
        f"<b>• الفائز 🏆 : {user_name(winner)}</b>\n"
        f"<b>• النقاط الي كسبها : {amount_transferred} 🎖️🎉</b>\n\n"
        f"<b>• الخاسر 😂 : {user_name(loser)}</b>\n"
        f"<b>• النقاط الي خسرها : {amount_transferred} 😂</b>"
    )


# ============================================================
# المهلة التلقائية
# ============================================================

def set_timeout(game, seconds, reason):
    game["timeout_token"] = game.get("timeout_token", 0) + 1
    token = game["timeout_token"]
    asyncio.create_task(_timeout_game(game["game_id"], token, seconds, reason))


async def _timeout_game(game_id, token, seconds, reason):
    await asyncio.sleep(seconds)
    game = _active_games.get(game_id)
    if not game or game.get("finished") or game.get("timeout_token") != token:
        return

    game["finished"] = True
    game["status"] = "finished"
    try:
        await game["bot"].edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["message_id"],
            text=(
                "<b>انتهت مهلة لعبة حجرة ورقة مقص ⏰</b>\n\n"
                f"<b>• {escape_html(reason)}</b>"
            ),
            parse_mode="HTML",
            reply_markup=None,
        )
    except Exception as exc:
        print(f"⚠️ تعذر تحديث رسالة مهلة حجرة ورقة مقص: {exc}")
    _active_games.pop(game_id, None)


# ============================================================
# بدء التحدي
# ============================================================

async def start_rock_paper_scissors(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return

    text = message.text.strip()
    match = re.fullmatch(r"(?:حجرة(?: ورقة مقص)?|ورقة|مقص)(?:\s+(\d+))?", text)
    if not match:
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text(
            "<b>• لازم تستخدم اللعبة بالرد على رسالة اللاعب.</b>",
            parse_mode="HTML",
        )
        return

    target_user = message.reply_to_message.from_user
    if target_user.id == user.id:
        await message.reply_text("<b>• ما تقدر تتحدى نفسك 😂</b>", parse_mode="HTML")
        return
    if target_user.is_bot:
        await message.reply_text("<b>• ما تقدر تتحدى البوت 😂</b>", parse_mode="HTML")
        return

    try:
        points = int(match.group(1)) if match.group(1) else DEFAULT_POINTS
    except ValueError:
        points = DEFAULT_POINTS

    if points <= 0:
        await message.reply_text("<b>• عدد النقاط لازم يكون أكبر من صفر.</b>", parse_mode="HTML")
        return

    challenger_points = await get_points(user.id)
    if challenger_points < points:
        await message.reply_text("<b>• نقاطك ما تكفي لبدء التحدي.</b>", parse_mode="HTML")
        return

    game_id = uuid.uuid4().hex[:10]
    game = {
        "game_id": game_id,
        "chat_id": message.chat_id,
        "message_id": None,
        "bot": context.bot,
        "challenger": user,
        "challenger_id": user.id,
        "target_user": target_user,
        "target_id": target_user.id,
        "points": points,
        "best_of": None,
        "status": "choosing_rounds",
        "finished": False,
        "round_number": 1,
        "wins": {user.id: 0, target_user.id: 0},
        "choices": {},
        "round_choices": {},
        "last_tie": False,
        "timeout_token": 0,
    }
    _active_games[game_id] = game

    sent = await message.reply_text(
        build_challenge_caption(game),
        parse_mode="HTML",
        reply_markup=build_rounds_keyboard(game),
    )
    game["message_id"] = sent.message_id
    set_timeout(game, CHALLENGE_TIMEOUT, "لم يتم تحديد الجولات أو قبول التحدي في الوقت المحدد.")


# ============================================================
# Callback اللعبة
# ============================================================

async def rock_paper_scissors_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""
    if not data.startswith("rps:"):
        return

    parts = data.split(":")
    if len(parts) < 3:
        await query.answer()
        return

    game = _active_games.get(parts[1])
    if not game or game.get("finished"):
        await query.answer("• انتهت اللعبة", show_alert=False)
        return

    action = parts[2]

    if action == "rounds":
        await _choose_rounds(query, game, parts)
    elif action == "accept":
        await _accept_challenge(query, game)
    elif action == "move":
        await _choose_move(query, game, parts)
    elif action == "next":
        await _continue_game(query, game)
    else:
        await query.answer()


async def _choose_rounds(query, game, parts):
    user = query.from_user
    if user.id != game["challenger_id"]:
        await query.answer("• هذا الزر لا يخصك", show_alert=False)
        return
    if game["status"] != "choosing_rounds" or len(parts) != 4:
        await query.answer("• انتهت مهلة الاختيار", show_alert=False)
        return
    try:
        best_of = int(parts[3])
    except ValueError:
        await query.answer()
        return
    if best_of not in (1, 3, 5, 7):
        await query.answer()
        return

    async with _game_lock:
        if game["status"] != "choosing_rounds":
            await query.answer("• تم تحديد الجولات مسبقًا", show_alert=False)
            return
        game["best_of"] = best_of
        game["status"] = "waiting_accept"
        set_timeout(game, CHALLENGE_TIMEOUT, "لم يقبل اللاعب التحدي في الوقت المحدد.")
        await query.answer()
        await query.edit_message_text(
            build_accept_caption(game),
            parse_mode="HTML",
            reply_markup=build_accept_keyboard(game),
        )


async def _accept_challenge(query, game):
    user = query.from_user
    if user.id != game["target_id"] or user.is_bot:
        await query.answer("• هذا الزر لا يخصك", show_alert=False)
        return

    async with _game_lock:
        if game["status"] != "waiting_accept":
            await query.answer("• انتهى التحدي أو تم قبوله", show_alert=False)
            return

        # يجب أن يكون الطرفان قادرين على دفع المبلغ إذا خسر أي منهما.
        challenger_balance, target_balance = await asyncio.gather(
            get_points(game["challenger_id"]),
            get_points(game["target_id"]),
        )
        if challenger_balance < game["points"]:
            game["finished"] = True
            game["status"] = "finished"
            _active_games.pop(game["game_id"], None)
            await query.answer("• نقاط صاحب التحدي ما عادت تكفي", show_alert=True)
            await query.edit_message_text(
                "<b>• انتهى التحدي لأن نقاط صاحب التحدي ما عادت تكفي.</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
            return
        if target_balance < game["points"]:
            await query.answer("• نقاطك ما تكفي لهذا التحدي", show_alert=True)
            return

        game["status"] = "playing"
        game["round_number"] = 1
        game["choices"] = {}
        game["round_choices"] = {}
        set_timeout(game, ROUND_TIMEOUT, "لم يختر اللاعبان حركتيهما في الوقت المحدد.")
        await query.answer()
        await query.edit_message_text(
            build_round_caption(game),
            parse_mode="HTML",
            reply_markup=build_moves_keyboard(game),
        )


async def _choose_move(query, game, parts):
    user = query.from_user
    if user.id not in (game["challenger_id"], game["target_id"]):
        await query.answer("• هذا الزر لا يخصك", show_alert=False)
        return
    if len(parts) != 4 or parts[3] not in MOVES:
        await query.answer()
        return

    async with _game_lock:
        if game["status"] != "playing":
            await query.answer("• انتظر الجولة التالية", show_alert=False)
            return
        if user.id in game["choices"]:
            await query.answer("• اخترت حركتك بالفعل، انتظر خصمك", show_alert=False)
            return

        game["choices"][user.id] = parts[3]
        await query.answer("• تم تسجيل اختيارك بنجاح")

        if len(game["choices"]) < 2:
            try:
                await query.edit_message_text(
                    build_round_caption(game) + "\n\n<b>• تم اختيار حركة من أحد اللاعبين، ننتظر الثاني...</b>",
                    parse_mode="HTML",
                    reply_markup=build_moves_keyboard(game),
                )
            except Exception:
                pass
            return

        game["round_choices"] = dict(game["choices"])
        challenger_move = game["round_choices"][game["challenger_id"]]
        target_move = game["round_choices"][game["target_id"]]
        outcome = is_valid_move_pair(challenger_move, target_move)
        round_winner_id = None
        if outcome == 1:
            round_winner_id = game["challenger_id"]
        elif outcome == 2:
            round_winner_id = game["target_id"]

        game["last_tie"] = round_winner_id is None
        if round_winner_id is not None:
            game["wins"][round_winner_id] += 1

        required = get_required_wins(game["best_of"])
        match_winner_id = None
        if game["wins"][game["challenger_id"]] >= required:
            match_winner_id = game["challenger_id"]
        elif game["wins"][game["target_id"]] >= required:
            match_winner_id = game["target_id"]

        if match_winner_id is not None:
            await _finish_game(query, game, match_winner_id)
            return

        game["status"] = "round_result"
        set_timeout(game, CONTINUE_TIMEOUT, "لم يتم الانتقال للجولة التالية في الوقت المحدد.")
        result_text = build_round_result_caption(
            game, challenger_move, target_move, round_winner_id
        )
        await query.edit_message_text(
            result_text,
            parse_mode="HTML",
            reply_markup=build_continue_keyboard(game),
        )


async def _continue_game(query, game):
    user = query.from_user
    if user.id not in (game["challenger_id"], game["target_id"]):
        await query.answer("• هذا الزر لا يخصك", show_alert=False)
        return

    async with _game_lock:
        if game["status"] != "round_result":
            await query.answer("• انتظر انتهاء الجولة", show_alert=False)
            return
        game["round_number"] += 1
        game["choices"] = {}
        game["round_choices"] = {}
        game["status"] = "playing"
        game["last_tie"] = False
        set_timeout(game, ROUND_TIMEOUT, "لم يختر اللاعبان حركتيهما في الوقت المحدد.")
        await query.answer()
        await query.edit_message_text(
            build_round_caption(game),
            parse_mode="HTML",
            reply_markup=build_moves_keyboard(game),
        )


async def _finish_game(query, game, winner_id):
    loser_id = game["target_id"] if winner_id == game["challenger_id"] else game["challenger_id"]
    amount = game["points"]

    # لا تخصم اللعبة نقاطًا إلا بعد تحديد الفائز؛ نعيد فحص رصيد الخاسر.
    transferred = await transfer_points_atomic(loser_id, winner_id, amount)
    if not transferred:
        game["finished"] = True
        game["status"] = "finished"
        _active_games.pop(game["game_id"], None)
        await query.answer()
        await query.edit_message_text(
            "<b>انتهت اللعبة، لكن رصيد الخاسر لم يعد يكفي لتحويل المبلغ المحدد.</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
        return

    game["finished"] = True
    game["status"] = "finished"
    _active_games.pop(game["game_id"], None)
    await query.answer()
    await query.edit_message_text(
        build_final_caption(game, winner_id, amount),
        parse_mode="HTML",
        reply_markup=None,
    )
