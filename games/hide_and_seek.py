import random
import asyncio
from collections import Counter

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

from database.roles import get_rank_level
from database.points import adjust_points

from games.big_game_lock import (
    get_big_game,
    lock_big_game,
    unlock_big_game
)
# ==================================================
# إعدادات اللعبة
# ==================================================

HIDE_TIME = 60
SEARCH_TIME = 30
MIN_PLAYERS = 2
WIN_POINTS = 30


# ==================================================
# الألعاب النشطة
# ==================================================

active_hide_games = {}


# ==================================================
# صلاحية إدارة اللعبة
# ==================================================

async def can_manage_hide_game(user_id, chat_id):
    return await get_rank_level(user_id, chat_id) > 0


# ==================================================
# اسم اللاعب
# ==================================================

def get_player_name(user):

    if not user:
        return "مستخدم"

    if user.username:
        return f"@{user.username}"

    return user.first_name or "مستخدم"


# ==================================================
# حجم اللوحة
# ==================================================

def get_board_size(player_count):

    if player_count <= 2:
        return 16

    if player_count <= 5:
        return 20

    return 24


# ==================================================
# محتويات المربعات
# ==================================================

def create_contents(board_size):

    if board_size <= 16:

        items = [
            "bomb",
            "bomb",
            "bomb",

            "extra",
            "extra",

            "plus5",
            "plus5",

            "plus10",

            "minus3",
            "minus3",

            "minus5",
            "minus5",
        ]

    elif board_size <= 20:

        items = [
            "bomb",
            "bomb",
            "bomb",
            "bomb",

            "extra",
            "extra",
            "extra",

            "plus5",
            "plus5",
            "plus5",

            "plus10",
            "plus10",

            "minus3",
            "minus3",
            "minus3",

            "minus5",
            "minus5",
            "minus5",
        ]

    else:

        items = [
            "bomb",
            "bomb",
            "bomb",
            "bomb",
            "bomb",

            "extra",
            "extra",
            "extra",

            "plus5",
            "plus5",
            "plus5",

            "plus10",
            "plus10",

            "minus3",
            "minus3",
            "minus3",

            "minus5",
            "minus5",
            "minus5",
        ]

    while len(items) < board_size:
        items.append("empty")

    random.shuffle(items)

    return {
        number: items[number - 1]
        for number in range(1, board_size + 1)
    }


# ==================================================
# إنشاء لوحة الأرقام
# ==================================================

def build_board(numbers, callback_prefix):

    buttons = []
    row = []

    for number in numbers:

        row.append(
            InlineKeyboardButton(
                str(number),
                callback_data=f"{callback_prefix}:{number}"
            )
        )

        if len(row) == 4:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)


# ==================================================
# بدء التسجيل
# ==================================================

async def start_hide_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":

        await update.message.reply_text(
            "❌ لعبة الغميضة تبدأ من القروب."
        )

        return

    if not await can_manage_hide_game(user.id, chat.id):

        await update.message.reply_text(
            "❌ هذا الأمر للرتب فقط."
        )

        return

    big_game = get_big_game(chat.id)

    if big_game:

        await update.message.reply_text(
            f"❌ فيه لعبة شغالة حاليًا!: "
            f"{big_game['name']}\n\n"
            "🛑 أنهِ اللعبة الحالية أولًا قبل بدء لعبة أخرى."
        )

        return

    if chat.id in active_hide_games:

        await update.message.reply_text(
            "❌ توجد لعبة غميضة شغالة بالفعل."
        )

        return


    
    active_hide_games[chat.id] = {

        "players": {},
        "order": [],

        "board_size": 16,

        "available": [],
        "contents": {},

        "phase": "registration",

        "current_index": 0,

        # رسالة البحث الحالية
        "search_message_id": None,

        # اللاعب صاحب الدور الحالي
        "search_player": None,

        # مؤقت البحث
        "search_task": None,
        "hide_task": None,

        # رسائل الاختباء الخاصة
        "hide_messages": {},

        "hide_tasks": {},

        "discoveries": Counter(),
        "bomb_hits": Counter(),

        "scores": {},

        "hidden": {},

        "searching": False,

        # يمنع معالجة ضغطتين بنفس اللحظة
        "resolving": False,
    }

    lock_big_game(
        chat.id,
        "hide",
        "غميضة 🕵️"
    )


    await update.message.reply_text(
        "🚪 تم فتح التسجيل في لعبة الغميضة!\n\n"
        "• نوع اللوحة المختار: الأرقام 🔢\n"
        "• اكتب دخول للانضمام إلى اللعبة.\n"
        "• عندما يكتمل اللاعبون، يكتب الأدمن ابدا لبدء اللعبة.\n"
        "• الحد الأدنى لبدء اللعبة: 2 لاعبين."
    )


# ==================================================
# دخول لاعب
# ==================================================

async def join_hide_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat

    if chat.id not in active_hide_games:
        return

    game = active_hide_games[chat.id]

    if game["phase"] != "registration":
        return

    user = update.effective_user

    if user.id in game["players"]:

        await update.message.reply_text(
            f"❌ أنت داخل اللعبة بالفعل يا "
            f"{get_player_name(user)}."
        )

        return

    game["players"][user.id] = user
    game["order"].append(user.id)
    game["scores"][user.id] = 0

    game["board_size"] = get_board_size(
        len(game["players"])
    )

    names = []

    for player_id in game["order"]:

        player = game["players"][player_id]

        names.append(
            f"{len(names) + 1}. "
            f"{get_player_name(player)}"
        )

    await update.message.reply_text(
        f"✅ تم تسجيل {get_player_name(user)} "
        f"في لعبة الغميضة!\n\n"
        f"👥 عدد اللاعبين: {len(game['players'])}\n"
        f"🔢 عدد المربعات: {game['board_size']}\n\n"
        + "\n".join(names)
    )


# ==================================================
# بدء اللعبة
# ==================================================

async def begin_hide_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if chat.id not in active_hide_games:
        return

    game = active_hide_games[chat.id]

    if not await can_manage_hide_game(user.id, chat.id):
        return

    if game["phase"] != "registration":

        await update.message.reply_text(
            "❌ اللعبة بدأت بالفعل."
        )

        return

    player_count = len(game["players"])

    if player_count < MIN_PLAYERS:

        await update.message.reply_text(
            "❌ لا يمكن بدء اللعبة.\n"
            f"الحد الأدنى: {MIN_PLAYERS} لاعبين."
        )

        return

    game["board_size"] = get_board_size(
        player_count
    )

    # كل الأرقام تكون موجودة من البداية
    game["available"] = list(
        range(
            1,
            game["board_size"] + 1
        )
    )

    game["contents"] = create_contents(
        game["board_size"]
    )

    game["phase"] = "hiding"

    await update.message.reply_text(
        "😶‍🌫️ بدأت لعبة الغميضة!\n\n"
        "📩 أرسلت لكل لاعب رسالة خاصة لاختيار مكان اختبائه.\n"
        "⏱ أمام كل لاعب 60 ثانية.\n\n"
        "إذا لم يختر اللاعب خلال الوقت، سأختار له رقمًا عشوائيًا."
    )

    for player_id in game["order"]:

        await send_hide_choice(
            context,
            chat.id,
            player_id
        )

    game["hide_task"] = context.application.create_task(
        hide_phase_timeout(
            context,
            chat.id
        ),
        name=f"hide-phase-{chat.id}",
    )


# ==================================================
# إرسال رسالة الاختباء الخاصة
# ==================================================

async def send_hide_choice(
    context,
    chat_id,
    player_id
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    player = game["players"].get(player_id)

    if not player:
        return

    # كل الأرقام موجودة عند بداية الاختباء
    numbers = list(
        range(
            1,
            game["board_size"] + 1
        )
    )

    keyboard = build_board(
        numbers,
        f"hide:{chat_id}:{player_id}"
    )

    try:

        message = await context.bot.send_message(
            chat_id=player_id,
            text=(
                "😶‍🌫️ اختر الرقم الذي تريد الاختباء فيه.\n\n"
                "⏱ لديك 60 ثانية.\n"
                "يمكن لأكثر من لاعب الاختباء في نفس الرقم."
            ),
            reply_markup=keyboard
        )

        # نخزن ID الرسالة حتى نعدل نفس الرسالة
        game["hide_messages"][player_id] = message.message_id

    except Exception:

        try:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚠️ لم أستطع إرسال رسالة خاصة إلى "
                    f"{get_player_name(player)}.\n"
                    "يجب عليه فتح محادثة البوت والضغط على Start."
                )
            )

        except Exception:
            pass


# ==================================================
# اختيار مكان الاختباء
# ==================================================

async def hide_number_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    data = query.data

    parts = data.split(":")

    # الصحيح:
    # hide:chat_id:player_id:number
    if len(parts) != 4:
        await query.answer()
        return

    try:

        chat_id = int(parts[1])
        player_id = int(parts[2])
        number = int(parts[3])

    except Exception:
        await query.answer()
        return

    game = active_hide_games.get(chat_id)

    if not game:

        await query.answer(
            "❌ انتهت اللعبة.",
            show_alert=True
        )

        return

    if game["phase"] != "hiding":

        await query.answer(
            "❌ انتهى وقت الاختباء.",
            show_alert=True
        )

        return

    if query.from_user.id != player_id:

        await query.answer(
            "❌ هذه اللوحة ليست لك.",
            show_alert=True
        )

        return

    if player_id in game["hidden"]:

        await query.answer(
            "❌ لقد اخترت رقمًا بالفعل.",
            show_alert=True
        )

        return

    if number < 1 or number > game["board_size"]:

        await query.answer(
            "❌ رقم غير صحيح.",
            show_alert=True
        )

        return

    # تسجيل الاختيار
    game["hidden"][player_id] = number

    await query.answer(
        "✅ تم اختيار الرقم."
    )

    # تعديل نفس رسالة الخاص
    try:

        await query.edit_message_text(
            text=(
                "😶‍🌫️ تم اختيار مكان اختبائك!\n\n"
                f"🔢 الرقم: {number}\n\n"
                "✅ تم تسجيل اختيارك بنجاح."
            )
        )

    except Exception:
        pass

    # إذا الجميع اختار
    if len(game["hidden"]) == len(game["players"]):

        await finish_hiding(
            context,
            chat_id
        )


# ==================================================
# انتهاء وقت الاختباء
# ==================================================

async def hide_phase_timeout(
    context,
    chat_id
):

    await asyncio.sleep(HIDE_TIME)

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "hiding":
        return

    numbers = list(
        range(
            1,
            game["board_size"] + 1
        )
    )

    for player_id in game["order"]:

        if player_id in game["hidden"]:
            continue

        number = random.choice(numbers)

        game["hidden"][player_id] = number

        message_id = game["hide_messages"].get(
            player_id
        )

        # تعديل رسالة اللاعب نفسها
        if message_id:

            try:

                await context.bot.edit_message_text(
                    chat_id=player_id,
                    message_id=message_id,
                    text=(
                        "⏰ انتهى وقت الاختباء!\n\n"
                        f"🎲 تم اختيار المربع ({number}) "
                        "لك عشوائيًا.\n\n"
                        "✅ تم تسجيل اختيارك."
                    )
                )

            except Exception:
                pass

    await finish_hiding(
        context,
        chat_id
    )


# ==================================================
# إنهاية الاختباء
# ==================================================

async def finish_hiding(
    context,
    chat_id
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "hiding":
        return

    game["phase"] = "searching"

    # إذا انتهى الاختباء مبكرًا، ألغِ مؤقته بدل إبقائه نائمًا حتى نهاية الـ60 ثانية.
    hide_task = game.get("hide_task")
    if hide_task and hide_task is not asyncio.current_task() and not hide_task.done():
        hide_task.cancel()
    game["hide_task"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "😶‍🌫️ لقد اختبأ جميع اللاعبين بنجاح.\n\n"
            "تبدأ الآن أدوار البحث!\n\n"
            "في كل دور يختار اللاعب مربعًا واحدًا "
            "للبحث فيه.\n\n"
            "💥 إذا وجد لاعبًا مختبئًا يتم استبعاده.\n"
            "🎁 بعض المربعات تحتوي على هدايا."
        )
    )

    await start_next_search_turn(
        context,
        chat_id
    )


# ==================================================
# اللاعبين داخل مربع
# ==================================================

def players_in_box(game, number):

    found = []

    for player_id, hidden_number in game["hidden"].items():

        if hidden_number != number:
            continue

        if player_id not in game["players"]:
            continue

        found.append(player_id)

    return found


# ==================================================
# اللاعبين الأحياء
# ==================================================

def alive_players(game):

    return [
        player_id
        for player_id in game["order"]
        if player_id in game["players"]
    ]


# ==================================================
# فحص نهاية اللعبة
# ==================================================

def check_game_finished(game):

    alive = alive_players(game)

    # بقي لاعب واحد = يفوز
    if len(alive) <= 1:
        return True

    # جميع اللاعبين الباقين في نفس الرقم = يفوزون كلهم
    hidden_numbers = {
        game["hidden"].get(player_id)
        for player_id in alive
    }

    if len(hidden_numbers) == 1:
        return True

    return False


# ==================================================
# بدء دور البحث التالي
# ==================================================

async def start_next_search_turn(
    context,
    chat_id
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "searching":
        return

    if game["resolving"]:
        return

    if check_game_finished(game):

        await finish_hide_game(
            context,
            chat_id
        )

        return

    order = game["order"]

    if not order:
        await finish_hide_game(
            context,
            chat_id
        )
        return

    checked = 0

    while checked < len(order):

        index = game["current_index"] % len(order)

        player_id = order[index]

        game["current_index"] += 1

        checked += 1

        if player_id not in game["players"]:
            continue

        player = game["players"][player_id]

        # استبدال: جميع الأرقام المتاحة
        available = list(game["available"])

        if not available:

            await finish_hide_game(
                context,
                chat_id
            )

            return

        game["searching"] = True
        game["search_player"] = player_id
        game["resolving"] = False

        keyboard = build_board(
            available,
            f"search:{chat_id}:{player_id}"
        )

        # رسالة جديدة لهذا اللاعب
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🫣 تفضل يا {get_player_name(player)} "
                "اختر مربع لكشف ما بداخله.\n\n"
                f"⏱ أمامك {SEARCH_TIME} ثانية."
            ),
            reply_markup=keyboard
        )

        game["search_message_id"] = message.message_id

        # مؤقت الدور
        game["search_task"] = context.application.create_task(
            search_timeout(
                context,
                chat_id,
                player_id
            )
        )

        return

    await finish_hide_game(
        context,
        chat_id
    )


# ==================================================
# اختيار مربع البحث
# ==================================================

async def search_number_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    try:

        parts = query.data.split(":")

        if len(parts) != 4:
            await query.answer()
            return

        _, chat_id_text, player_id_text, number_text = parts

        chat_id = int(chat_id_text)
        player_id = int(player_id_text)
        number = int(number_text)

    except Exception:

        await query.answer()
        return

    game = active_hide_games.get(chat_id)

    if not game:

        await query.answer(
            "❌ انتهت اللعبة.",
            show_alert=True
        )

        return

    if game["phase"] != "searching":

        await query.answer(
            "❌ انتهى الدور.",
            show_alert=True
        )

        return

    if query.from_user.id != player_id:

        await query.answer(
            "❌ انتظر، ليس دورك!",
            show_alert=True
        )

        return

    if game.get("search_player") != player_id:

        await query.answer(
            "❌ انتظر، ليس دورك!",
            show_alert=True
        )

        return

    if game["resolving"]:

        await query.answer(
            "⏳ انتظر...",
            show_alert=True
        )

        return

    if number not in game["available"]:

        await query.answer(
            "❌ هذا الرقم تم اختياره بالفعل.",
            show_alert=True
        )

        return

    game["resolving"] = True

    await query.answer(
        f"تم اختيار {number}."
    )

    # إلغاء مؤقت الدور
    task = game.get("search_task")

    if task:

        task.cancel()

    game["search_task"] = None

    # حل الاختيار
    await resolve_search(
        context,
        chat_id,
        player_id,
        number,
        query.message
    )


# ==================================================
# حل البحث
# ==================================================

async def resolve_search(
    context,
    chat_id,
    player_id,
    number,
    current_message=None
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if number not in game["available"]:
        game["resolving"] = False
        return

    player = game["players"].get(player_id)

    if not player:
        game["resolving"] = False
        return

    # الرقم المختار فقط هو الذي ينحذف
    game["available"].remove(number)

    # اللاعبين المختبئين
    found_players = players_in_box(
        game,
        number
    )

    content = game["contents"].get(
        number,
        "empty"
    )

    # بناء نتيجة الدور
    text = (
        f"🎯 قام اللاعب {get_player_name(player)} "
        f"باختيار المربع ({number}).\n\n"
    )

    if found_players:

        names = []

        for found_id in found_players:

            found_user = game["players"].get(found_id)

            if found_user:

                names.append(
                    get_player_name(found_user)
                )

        text += (
            "💥 تم كشف المخبأ!\n"
            "تم العثور على اللاعبين:\n"
            + "\n".join(
                f"• {name} ❌"
                for name in names
            )
            + "\n\n"
            "تم استبعادهم من اللعبة."
        )

        for found_id in found_players:

            game["players"].pop(
                found_id,
                None
            )

        game["discoveries"][player_id] += len(
            found_players
        )

    else:

        text += (
            "💨 المربع فارغ!\n"
            "لم يتم العثور على أحد."
        )

        # القنبلة
        if content == "bomb":

            game["bomb_hits"][player_id] += 1

            alive = alive_players(game)

            if alive:

                target_id = random.choice(alive)

                target = game["players"].get(
                    target_id
                )

                if target:

                    secret_number = game["hidden"].get(
                        target_id
                    )

                    if secret_number is not None:

                        if secret_number % 2 == 0:
                            parity = "زوجي"
                        else:
                            parity = "فردي"

                        text += (
                            "\n\n💣 انفجرت قنبلة!\n"
                            f"تم كشف تلميح عن "
                            f"{get_player_name(target)}:\n"
                            f"🔎 رقمه السري {parity}."
                        )

        # فرصة إضافية
        elif content == "extra":

            text += (
                "\n\n🔄 حصل اللاعب "
                f"{get_player_name(player)} "
                "على فرصة إضافية!"
            )

        # +5
        elif content == "plus5":

            game["scores"][player_id] += 5

            await adjust_points(
                player_id,
                5
            )

            text += (
                "\n\n🎁 حصل اللاعب "
                f"{get_player_name(player)} "
                "على +5 نقاط!"
            )

        # +10
        elif content == "plus10":

            game["scores"][player_id] += 10

            await adjust_points(
                player_id,
                10
            )

            text += (
                "\n\n🎁 حصل اللاعب "
                f"{get_player_name(player)} "
                "على +10 نقاط!"
            )

        # -3
        elif content == "minus3":

            game["scores"][player_id] -= 3

            await adjust_points(
                player_id,
                -3
            )

            text += (
                "\n\n💥 أوبس!\n"
                "تم خصم 3 نقاط من اللاعب "
                f"{get_player_name(player)}."
            )

        # -5
        elif content == "minus5":

            game["scores"][player_id] -= 5

            await adjust_points(
                player_id,
                -5
            )

            text += (
                "\n\n💥 أوبس!\n"
                "تم خصم 5 نقاط من اللاعب "
                f"{get_player_name(player)}."
            )

    # تعديل نفس رسالة اللاعب
    message = current_message

    if message is None:

        message_id = game.get(
            "search_message_id"
        )

        if message_id:

            try:

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text
                )

            except Exception:
                pass

    else:

        try:

            await message.edit_text(
                text=text
            )

        except Exception:
            pass

    # فحص نهاية اللعبة
    if check_game_finished(game):

        game["resolving"] = False

        await finish_hide_game(
            context,
            chat_id
        )

        return

    # فرصة إضافية
    if (
        not found_players
        and content == "extra"
        and player_id in game["players"]
    ):

        game["resolving"] = False

        await start_specific_search_turn(
            context,
            chat_id,
            player_id
        )

        return

    # الدور التالي
    game["searching"] = False
    game["resolving"] = False

    await start_next_search_turn(
        context,
        chat_id
    )


# ==================================================
# فرصة إضافية
# ==================================================

async def start_specific_search_turn(
    context,
    chat_id,
    player_id
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "searching":
        return

    if player_id not in game["players"]:
        return

    # استبدال: جميع الأرقام المتاحة
    available = list(game["available"])

    if not available:

        await finish_hide_game(
            context,
            chat_id
        )

        return

    player = game["players"][player_id]

    game["search_player"] = player_id
    game["searching"] = True
    game["resolving"] = False

    keyboard = build_board(
        available,
        f"search:{chat_id}:{player_id}"
    )

    # فرصة إضافية = رسالة جديدة
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔄 فرصة إضافية!\n\n"
            f"تفضل يا {get_player_name(player)} "
            "اختر مربعًا آخر.\n\n"
            f"⏱ أمامك {SEARCH_TIME} ثانية."
        ),
        reply_markup=keyboard
    )

    game["search_message_id"] = message.message_id

    game["search_task"] = context.application.create_task(
        search_timeout(
            context,
            chat_id,
            player_id
        )
    )


# ==================================================
# انتهاء وقت البحث
# ==================================================

async def search_timeout(
    context,
    chat_id,
    player_id
):

    try:

        await asyncio.sleep(
            SEARCH_TIME
        )

    except asyncio.CancelledError:

        return

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "searching":
        return

    if game.get("search_player") != player_id:
        return

    if game.get("resolving"):
        return

    player = game["players"].get(player_id)

    if not player:
        return

    # ==============================================
    # انتهى الوقت = استبعاد اللاعب من اللعبة
    # ==============================================

    game["resolving"] = True

    try:

        message_id = game.get(
            "search_message_id"
        )

        if message_id:

            try:

                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        f"⏰ انتهى وقت "
                        f"{get_player_name(player)}!\n\n"
                        "❌ تم استبعادك من اللعبة "
                        "لأنك لم تختر رقمًا."
                    )
                )

            except Exception:
                pass

        # طرد اللاعب من اللاعبين الأحياء
        game["players"].pop(
            player_id,
            None
        )

        game["search_task"] = None
        game["searching"] = False
        game["search_player"] = None
        game["resolving"] = False

        # إذا بقي واحد أو صاروا كلهم بنفس الرقم
        if check_game_finished(game):

            await finish_hide_game(
                context,
                chat_id
            )

            return

        # يكمل باقي اللاعبين
        await start_next_search_turn(
            context,
            chat_id
        )

    except Exception:

        game["resolving"] = False


# ==================================================
# إنهاء اللعبة يدويًا
# ==================================================

async def end_hide_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    if chat_id not in active_hide_games:
        return

    if not await can_manage_hide_game(user.id, chat_id):
        return

    await update.message.reply_text(
        "🛑 تم إنهاء لعبة الغميضة."
    )

    game = active_hide_games.pop(
        chat_id,
        None
    )

    unlock_big_game(
        chat_id,
        "hide"
    )

    if not game:
        return

    for task_key in ("hide_task", "search_task"):
        task = game.get(task_key)
        if task and not task.done():
            task.cancel()
        game[task_key] = None


# ==================================================
# نهاية اللعبة
# ==================================================

async def finish_hide_game(
    context,
    chat_id
):

    game = active_hide_games.get(chat_id)

    if not game:
        return

    if game["phase"] == "finished":
        return

    game["phase"] = "finished"

    for task_key in ("hide_task", "search_task"):
        task = game.get(task_key)
        if task and not task.done():
            task.cancel()
        game[task_key] = None

    alive = alive_players(game)

    winners = []

    if alive:
        winners = alive

    # ==============================================
    # الفائزون يأخذون 30 نقطة
    # ==============================================

    if winners:

        for winner_id in winners:

            await adjust_points(
                winner_id,
                WIN_POINTS
            )

            game["scores"][winner_id] += WIN_POINTS

    # ==============================================
    # أكثر اكتشافات
    # ==============================================

    most_discoveries = None

    if game["discoveries"]:

        most_discoveries = max(
            game["discoveries"],
            key=game["discoveries"].get
        )

        discovery_count = game["discoveries"][
            most_discoveries
        ]

        if discovery_count > 0:

            await adjust_points(
                most_discoveries,
                5
            )

    # ==============================================
    # أكثر قنابل
    # ==============================================

    most_bombs = None

    if game["bomb_hits"]:

        most_bombs = max(
            game["bomb_hits"],
            key=game["bomb_hits"].get
        )

        bomb_count = game["bomb_hits"][
            most_bombs
        ]

        if bomb_count > 0:

            await adjust_points(
                most_bombs,
                -5
            )

    # ==============================================
    # الرسالة النهائية
    # ==============================================

    text = "🏆 انتهت لعبة الغميضة!\n\n"

    if len(winners) == 1:

        winner = game["players"].get(
            winners[0]
        )

        if winner:

            text += (
                f"🥇 {get_player_name(winner)} — الفائز\n"
                f"🎁 حصل على +{WIN_POINTS} نقطة.\n"
            )

    elif len(winners) > 1:

        names = []

        for winner_id in winners:

            winner = game["players"].get(
                winner_id
            )

            if winner:

                names.append(
                    get_player_name(winner)
                )

        text += (
            "🥇 الفائزون:\n"
            + "\n".join(
                f"• {name} 🎁 +{WIN_POINTS}"
                for name in names
            )
            + "\n"
        )

    # ==============================================
    # الإحصائيات
    # ==============================================

    if most_discoveries:

        user = game["players"].get(
            most_discoveries
        )

        if user:

            text += (
                "\n🔎 أكثر لاعب اكتشف مخابئ: "
                f"{get_player_name(user)} "
                f"({game['discoveries'][most_discoveries]} اكتشاف)"
                "\n🎁 حصل على +5 نقاط."
            )

    if most_bombs:

        user = game["players"].get(
            most_bombs
        )

        if user:

            text += (
                "\n\n💣 أكثر لاعب أصابته القنابل: "
                f"{get_player_name(user)} "
                f"({game['bomb_hits'][most_bombs]} قنابل)"
                "\n💥 تم خصم 5 نقاط منه."
            )

    # ==============================================
    # نقاط الجولة
    # ==============================================

    scored = [
        (player_id, points)
        for player_id, points in game["scores"].items()
        if points != 0
    ]

    if scored:

        text += "\n\n📊 نقاط الجولة:\n"

        scored.sort(
            key=lambda x: x[1],
            reverse=True
        )

        for player_id, points in scored:

            player = game["players"].get(
                player_id
            )

            if not player:
                continue

            sign = "+" if points > 0 else ""

            text += (
                f"• {get_player_name(player)}: "
                f"{sign}{points}\n"
            )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text
    )

    # ==============================================
    # حذف اللعبة
    # ==============================================

    active_hide_games.pop(
        chat_id,
        None
    )

    unlock_big_game(
        chat_id,
        "hide"
    )
