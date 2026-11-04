import asyncio
import html
import random
import re
import uuid

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from database.points import (
    get_points,
    charge_two_players,
    settle_two_player_wager,
)


# ============================================================
# إعدادات اللعبة
# ============================================================

DEFAULT_POINTS = 30

BOARD_SIZE = 9

X = "X"
O = "O"

X_MARK = "❌"
O_MARK = "⭕️"

EMPTY_MARK = "⬜️"

WIN_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


# ============================================================
# الألعاب الحالية
# ============================================================

# game_id -> game data
_active_games = {}

# لمنع ضغطتين بنفس اللحظة على نفس اللعبة
_game_lock = asyncio.Lock()


# ============================================================
# أدوات النص
# ============================================================

def escape_html(value):
    return html.escape(
        str(value or "")
    )


def user_name(user):
    """
    اسم المستخدم بشكل آمن مع منشن قابل للضغط.
    """

    name = (
        user.first_name
        or user.username
        or "المستخدم"
    )

    return (
        f'<a href="tg://user?id={user.id}">'
        f'{escape_html(name)}'
        f'</a>'
    )


# ============================================================
# أدوات اللعبة
# ============================================================

def get_mark(symbol):
    if symbol == X:
        return X_MARK

    return O_MARK


def get_player_symbol(game, user_id):
    if game["x_player_id"] == user_id:
        return X

    if game["o_player_id"] == user_id:
        return O

    return None


def get_symbol_user(game, symbol):
    if symbol == X:
        return game["x_player"]

    return game["o_player"]


def get_current_player(game):
    if game["turn"] == X:
        return game["x_player"]

    return game["o_player"]


def check_winner(board):
    for a, b, c in WIN_LINES:

        if (
            board[a] != ""
            and board[a] == board[b]
            and board[a] == board[c]
        ):
            return board[a]

    return None


def board_full(board):
    return all(
        cell != ""
        for cell in board
    )


# ============================================================
# لوحة XO
# ============================================================

def build_board_keyboard(game):
    board = game["board"]
    game_id = game["game_id"]

    keyboard = []

    for row in range(3):

        buttons = []

        for col in range(3):

            index = (
                row * 3
                + col
            )

            value = board[index]

            if value == X:
                text = X_MARK

            elif value == O:
                text = O_MARK

            else:
                text = EMPTY_MARK

            buttons.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=(
                        f"xo:{game_id}:cell:{index}"
                    ),
                )
            )

        keyboard.append(buttons)

    return InlineKeyboardMarkup(
        keyboard
    )


def build_accept_keyboard(game):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "قبول التحدي 🔥",
                    callback_data=(
                        f"xo:{game['game_id']}:accept"
                    ),
                )
            ]
        ]
    )


# ============================================================
# كابشن بداية التحدي
# ============================================================

def build_challenge_caption(game):
    points = game["points"]
    challenger = game["challenger"]
    target = game.get("target_user")

    if target:

        return (
            "<b>• تم بدء لعبة XO</b>\n"
            f"<b>• عدد النقاط : {points} 🎖️</b>\n"
            f"<b>• تم اختيار ↤ {user_name(target)}</b>\n"
            "<b>• عشان تلعب معه اضغط الزر</b>"
        )

    return (
        "<b>• تم بدء لعبة XO</b>\n"
        f"<b>• عدد النقاط : {points} 🎖️</b>\n"
        "<b>• اللي يبي يلعب ضده يضغط الزر</b>"
    )


# ============================================================
# كابشن بداية اللعب بعد القبول
# ============================================================

def build_game_caption(game):
    x_player = game["x_player"]
    o_player = game["o_player"]

    current_player = get_current_player(
        game
    )

    current_symbol = game["turn"]

    return (
        f"<b>• اللاعب الاول : "
        f"{user_name(x_player)} {X_MARK}</b>\n"
        f"<b>• اللاعب الثاني : "
        f"{user_name(o_player)} {O_MARK}</b>\n\n"
        f"<b>• دور اللاعب : "
        f"{user_name(current_player)} "
        f"{get_mark(current_symbol)}</b>"
    )


# ============================================================
# كابشن الفوز
# ============================================================

def build_win_caption(game, winner_symbol):
    winner = get_symbol_user(
        game,
        winner_symbol
    )

    loser_symbol = (
        O
        if winner_symbol == X
        else X
    )

    loser = get_symbol_user(
        game,
        loser_symbol
    )

    points = game["points"]

    winner_mark = get_mark(
        winner_symbol
    )

    loser_mark = get_mark(
        loser_symbol
    )

    return (
        "<b>انتهت اللعبة 🎉🥳</b>\n\n"
        f"<b>• الفائز 🏆 : "
        f"{user_name(winner)} "
        f"{winner_mark}</b>\n"
        f"<b>• النقاط الي كسبها : "
        f"{points} 🎖️🎉</b>\n\n"
        f"<b>• الخاسر 😂 : "
        f"{user_name(loser)} "
        f"{loser_mark}</b>\n"
        "<b>• النقاط الي كسبها : "
        "0 😂😂</b>"
    )


# ============================================================
# كابشن التعادل
# ============================================================

def build_draw_caption(game):
    return (
        "<b>محد فاز يالسبايك 😂😂</b>\n\n"
        "<b>• نقاطكم رجعت لكم نفس ماهي 👍🏻</b>\n"
        "<b>————————————————</b>"
    )


# ============================================================
# بدء اللعبة
# ============================================================

async def start_xo_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    text = (
        message.text
        or ""
    ).strip()

    match = re.fullmatch(
        r"اكس او(?:\s+(\d+))?",
        text,
    )

    if not match:
        return

    # --------------------------------------------------------
    # النقاط
    # --------------------------------------------------------

    points_text = match.group(1)

    if points_text:
        try:
            points = int(points_text)
        except ValueError:
            return
    else:
        points = DEFAULT_POINTS

    if points <= 0:
        await message.reply_text(
            "<b>• عدد النقاط لازم يكون أكبر من صفر.</b>",
            parse_mode="HTML",
        )
        return

    # --------------------------------------------------------
    # اللاعب الذي يتم تحديه بالرد
    # --------------------------------------------------------

    target_user = None

    if message.reply_to_message:
        target_user = (
            message.reply_to_message.from_user
        )

        if not target_user:
            return

        # لا يتحدى نفسه
        if target_user.id == user.id:
            await message.reply_text(
                "<b>• ما تقدر تتحدى نفسك 😂</b>",
                parse_mode="HTML",
            )
            return

        # لا يتحدى البوت
        if target_user.is_bot:
            await message.reply_text(
                "<b>• ما تقدر تتحدى البوت 😂</b>",
                parse_mode="HTML",
            )
            return

    # --------------------------------------------------------
    # التأكد من نقاط صاحب التحدي
    # --------------------------------------------------------

    challenger_points = await get_points(user.id)

    if challenger_points < points:

        await message.reply_text(
            "<b>• نقاطك ماتكفي يامطفر</b>",
            parse_mode="HTML",
        )

        return

    # --------------------------------------------------------
    # إنشاء اللعبة
    # --------------------------------------------------------

    game_id = uuid.uuid4().hex[:10]

    game = {
        "game_id": game_id,

        "chat_id": message.chat_id,
        "message_id": None,

        "challenger": user,
        "challenger_id": user.id,

        "target_user": target_user,
        "target_id": (
            target_user.id
            if target_user
            else None
        ),

        "points": points,

        "status": "waiting",

        "x_player": None,
        "x_player_id": None,

        "o_player": None,
        "o_player_id": None,

        "board": [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ],

        "turn": X,

        "finished": False,
    }

    _active_games[game_id] = game

    # --------------------------------------------------------
    # إرسال رسالة التحدي
    # --------------------------------------------------------

    sent_message = await message.reply_text(
        build_challenge_caption(game),
        parse_mode="HTML",
        reply_markup=build_accept_keyboard(game),
    )

    game["message_id"] = (
        sent_message.message_id
    )


# ============================================================
# قبول التحدي
# ============================================================

async def xo_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    if not data.startswith("xo:"):
        return

    parts = data.split(":")

    if len(parts) < 3:
        await query.answer()
        return

    game_id = parts[1]
    action = parts[2]

    game = _active_games.get(
        game_id
    )

    # --------------------------------------------------------
    # لعبة غير موجودة
    # --------------------------------------------------------

    if not game:
        await query.answer(
            "• انتهت اللعبه",
            show_alert=False,
        )
        return

    # ========================================================
    # قبول التحدي
    # ========================================================

    if action == "accept":

        await _accept_challenge(
            query,
            game,
        )

        return

    # ========================================================
    # ضغط مربع
    # ========================================================

    if action == "cell":

        if len(parts) != 4:
            await query.answer()
            return

        try:
            cell_index = int(parts[3])
        except ValueError:
            await query.answer()
            return

        await _play_cell(
            query,
            game,
            cell_index,
        )

        return

    await query.answer()


# ============================================================
# قبول التحدي - داخلي
# ============================================================

async def _accept_challenge(
    query,
    game,
):
    user = query.from_user

    # --------------------------------------------------------
    # اللعبة انتهت
    # --------------------------------------------------------

    if game["finished"]:
        await query.answer(
            "• انتهت اللعبه",
            show_alert=False,
        )
        return

    # --------------------------------------------------------
    # تحدي خاص بشخص معين
    # --------------------------------------------------------

    target_id = game["target_id"]

    if target_id is not None:

        if user.id != target_id:

            await query.answer(
                "• هذا الزر لا يخصك",
                show_alert=False,
            )

            return

    # --------------------------------------------------------
    # لا يسمح لصاحب التحدي بقبول تحديه
    # --------------------------------------------------------

    if user.id == game["challenger_id"]:

        await query.answer(
            "• هذا الزر لا يخصك",
            show_alert=False,
        )

        return

    # --------------------------------------------------------
    # منع قبول اللعبة من بوت
    # --------------------------------------------------------

    if user.is_bot:

        await query.answer(
            "• هذا الزر لا يخصك",
            show_alert=False,
        )

        return

    async with _game_lock:

        # ممكن شخص آخر قبله قبل هذه الضغطة
        if game["status"] != "waiting":
            await query.answer(
                "• انتهت اللعبه",
                show_alert=False,
            )
            return

        challenger_id = (
            game["challenger_id"]
        )

        points = game["points"]

        # ----------------------------------------------------
        # خصم الرهان من الطرفين ذريًا مع إعادة فحص الرصيد
        # ----------------------------------------------------

        charge_status = await charge_two_players(
            challenger_id, user.id, points
        )

        if charge_status == "first_insufficient":
            game["finished"] = True
            game["status"] = "cancelled"
            _active_games.pop(game["game_id"], None)
            await query.answer(
                "• الي ضدك مطفر اختر خصم غني 😂😂",
                show_alert=False,
            )
            try:
                await query.edit_message_text(
                    "<b>• انتهى التحدي لأن صاحب التحدي ما عاد معه النقاط المطلوبة.</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        if charge_status == "second_insufficient":
            await query.answer(
                "• نقاطك ما تكفي يامطفر",
                show_alert=False,
            )
            return

        # ----------------------------------------------------
        # منع أي قبول متزامن
        # ----------------------------------------------------

        game["status"] = "playing"

        # ----------------------------------------------------
        # اختيار X و O عشوائيًا
        # ----------------------------------------------------

        challenger = game["challenger"]

        if random.choice(
            [True, False]
        ):
            x_player = challenger
            o_player = user
        else:
            x_player = user
            o_player = challenger

        game["x_player"] = x_player
        game["x_player_id"] = x_player.id

        game["o_player"] = o_player
        game["o_player_id"] = o_player.id

        game["turn"] = X

        game["board"] = [
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]

        # ----------------------------------------------------
        # خصم الرهان من الطرفين
        #
        # كل لاعب يدفع 200 مثلًا.
        # الخاسر يخسر 200.
        # الفائز يستلم 400، أي ربحه الصافي 200.
        # ----------------------------------------------------


        # ----------------------------------------------------
        # تعديل نفس الرسالة
        # ----------------------------------------------------

        await query.answer()

        await query.edit_message_text(
            build_game_caption(game),
            parse_mode="HTML",
            reply_markup=build_board_keyboard(
                game
            ),
        )


# ============================================================
# لعب حركة
# ============================================================

async def _play_cell(
    query,
    game,
    cell_index,
):
    user = query.from_user

    # --------------------------------------------------------
    # التحقق من رقم الخانة
    # --------------------------------------------------------

    if cell_index < 0 or cell_index >= BOARD_SIZE:
        await query.answer()
        return

    # --------------------------------------------------------
    # اللعبة انتهت
    # --------------------------------------------------------

    if game["finished"]:

        await query.answer(
            "• انتهت اللعبه",
            show_alert=False,
        )

        return

    # --------------------------------------------------------
    # لازم اللعبة تكون بدأت
    # --------------------------------------------------------

    if game["status"] != "playing":

        await query.answer(
            "• انتظر قبول التحدي",
            show_alert=False,
        )

        return

    # --------------------------------------------------------
    # معرفة رمز اللاعب
    # --------------------------------------------------------

    player_symbol = get_player_symbol(
        game,
        user.id,
    )

    if player_symbol is None:

        await query.answer(
            "• هذا الزر لا يخصك",
            show_alert=False,
        )

        return

    # --------------------------------------------------------
    # التأكد من الدور
    # --------------------------------------------------------

    if game["turn"] != player_symbol:

        await query.answer(
            "• انتظر ليس دورك",
            show_alert=False,
        )

        return

    # --------------------------------------------------------
    # الخانة مأخوذة
    # --------------------------------------------------------

    if game["board"][cell_index] != "":

        await query.answer(
            "• هذه الخانة مستخدمة",
            show_alert=False,
        )

        return

    async with _game_lock:

        # إعادة الفحص بعد دخول القفل
        if game["finished"]:
            await query.answer(
                "• انتهت اللعبه",
                show_alert=False,
            )
            return

        if game["turn"] != player_symbol:
            await query.answer(
                "• انتظر ليس دورك",
                show_alert=False,
            )
            return

        if game["board"][cell_index] != "":
            await query.answer(
                "• هذه الخانة مستخدمة",
                show_alert=False,
            )
            return

        # ----------------------------------------------------
        # تسجيل الحركة
        # ----------------------------------------------------

        game["board"][cell_index] = (
            player_symbol
        )

        # ----------------------------------------------------
        # فحص الفوز
        # ----------------------------------------------------

        winner = check_winner(
            game["board"]
        )

        if winner:

            await _finish_win(
                query,
                game,
                winner,
            )

            return

        # ----------------------------------------------------
        # فحص التعادل
        # ----------------------------------------------------

        if board_full(
            game["board"]
        ):

            await _finish_draw(
                query,
                game,
            )

            return

        # ----------------------------------------------------
        # تبديل الدور
        # ----------------------------------------------------

        if player_symbol == X:
            game["turn"] = O
        else:
            game["turn"] = X

        # ----------------------------------------------------
        # تعديل نفس الرسالة
        # ----------------------------------------------------

        await query.answer()

        await query.edit_message_text(
            build_game_caption(game),
            parse_mode="HTML",
            reply_markup=build_board_keyboard(
                game
            ),
        )


# ============================================================
# الفوز
# ============================================================

async def _finish_win(
    query,
    game,
    winner_symbol,
):
    points = game["points"]

    winner = get_symbol_user(
        game,
        winner_symbol,
    )

    loser_symbol = (
        O
        if winner_symbol == X
        else X
    )

    loser = get_symbol_user(
        game,
        loser_symbol,
    )

    # --------------------------------------------------------
    # اللعبة انتهت
    # --------------------------------------------------------

    game["finished"] = True
    game["status"] = "finished"

    # --------------------------------------------------------
    # الفائز يستلم مجموع الرهانات
    #
    # كان قد دفع points مسبقًا.
    # نضيف له 2 * points.
    #
    # النتيجة:
    # الفائز: +points صافي
    # الخاسر: -points
    # --------------------------------------------------------

    await settle_two_player_wager(
        game["x_player_id"], game["o_player_id"],
        points, winner_id=winner.id,
    )

    # --------------------------------------------------------
    # حذفها من الألعاب النشطة بعد تعديل الرسالة
    # --------------------------------------------------------

    await query.answer()

    await query.edit_message_text(
        build_win_caption(
            game,
            winner_symbol,
        ),
        parse_mode="HTML",
        reply_markup=build_board_keyboard(
            game
        ),
    )

    _active_games.pop(
        game["game_id"],
        None,
    )


# ============================================================
# التعادل
# ============================================================

async def _finish_draw(
    query,
    game,
):
    game["finished"] = True
    game["status"] = "draw"

    points = game["points"]

    # --------------------------------------------------------
    # إعادة الرهان للطرفين
    # --------------------------------------------------------

    await settle_two_player_wager(
        game["x_player_id"], game["o_player_id"], points
    )

    # --------------------------------------------------------
    # تعديل نفس الرسالة
    # --------------------------------------------------------

    await query.answer()

    await query.edit_message_text(
        build_draw_caption(game),
        parse_mode="HTML",
        reply_markup=build_board_keyboard(
            game
        ),
    )

    _active_games.pop(
        game["game_id"],
        None,
    )


# ============================================================
# تنظيف الألعاب القديمة
# ============================================================

def clear_xo_games():
    _active_games.clear()


def get_active_xo_games_count():
    return len(_active_games)
