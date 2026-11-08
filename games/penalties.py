import asyncio
import random
import uuid


from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import ContextTypes

from database.roles import get_rank_level
from database.points import add_points

from games.big_game_lock import (
    get_big_game,
    lock_big_game,
    unlock_big_game
)
# ==================================================
# إعدادات اللعبة
# ==================================================

TURN_TIME = 30
WIN_POINTS = 50

# ==================================================
# صور الاستعداد
# ==================================================

READY_IMAGES = {
    "red": "AgACAgQAAxkBAAICQWrwgQ9V5SFgbCr0TH5yBUIvliGdAAIyD2sb8AyJU1PPTkWK9jLnAQADAgADeQADPQQ",
    "blue": "AgACAgQAAxkBAAICRGrwggKPr3jUz2UoWcR4QZhWkDwpAAIzD2sb8AyJU_E_9KsKbdRWAQADAgADeQADPQQ",
}

# ==================================================
# صور النتائج
#
# المفتاح:
# (فريق الحارس, اتجاه الحارس, اتجاه المسدد)
# ==================================================

RESULT_IMAGES = {

    # ==============================================
    # الحارس الأحمر
    # ==============================================

    (
        "red",
        "يسار",
        "يسار"
    ):
        "AgACAgQAAxkBAAICOWrwgJFDFWLLOHPGbGa6GgrOem7dAAIuD2sb8AyJU2xsgzSzxPWOAQADAgADeQADPQQ",

    (
        "red",
        "يسار",
        "وسط"
    ):
        "AgACAgQAAxkBAAICIGrwfdQVvp6bmLLOdwPD8v0m6QPNAAInD2sb8AyJU4KjQ3TdZr2yAQADAgADeQADPQQ",

    (
        "red",
        "يسار",
        "يمين"
    ):
        "AgACAgQAAxkBAAICO2rwgLJpryqOc3jv6QteQRD4hju7AAIvD2sb8AyJU9fLR0mO06krAQADAgADeQADPQQ",

    (
        "red",
        "وسط",
        "يسار"
    ):
        "AgACAgQAAxkBAAICM2rwf-9dlLzv7EAadoTGqDBdbb8CAAIrD2sb8AyJU4vgHB_slYWsAQADAgADeQADPQQ",

    (
        "red",
        "وسط",
        "وسط"
    ):
        "AgACAgQAAxkBAAICPWrwgM3V_GOgOeq-4J8ssvSunAxwAAIwD2sb8AyJU4mAY58Qkck0AQADAgADeQADPQQ",

    (
        "red",
        "وسط",
        "يمين"
    ):
        "AgACAgQAAxkBAAICN2rwgENwpN4v_xJKP9vE1kj3-tPaAAItD2sb8AyJU5MRbaFHUW4pAQADAgADeQADPQQ",

    (
        "red",
        "يمين",
        "يسار"
    ):
        "AgACAgQAAxkBAAICI2rwflgGWA7kAtS2GVfUPBqZ7uYfAAIoD2sb8AyJU37pfcFF22X8AQADAgADeQADPQQ",

    (
        "red",
        "يمين",
        "وسط"
    ):
        "AgACAgQAAxkBAAICNWrwgBXJ0U4PNc9C68jiaQkx6h-SAAIsD2sb8AyJU2m1tsd3W8o6AQADAgADeQADPQQ",

    (
        "red",
        "يمين",
        "يمين"
    ):
        "AgACAgQAAxkBAAICP2rwgO7OPDhsTWXjh0WDP0TvPSoEAAIxD2sb8AyJU7Q_0aiuTBIMAQADAgADeQADPQQ",

    # ==============================================
    # الحارس الأزرق
    # ==============================================

    (
        "blue",
        "يسار",
        "يسار"
    ):
        "AgACAgQAAxkBAAICVmrwg9BMZo_O0klQKpfYe4pgYbSsAAI-D2sb8AyJU-djiS1xQl0NAQADAgADeQADPQQ",

    (
        "blue",
        "يسار",
        "وسط"
    ):
        "AgACAgQAAxkBAAICRmrwgh4laErQZu_e5KmifBPqzMfnAAI0D2sb8AyJU4ttGXMOHnDMAQADAgADeQADPQQ",

    (
        "blue",
        "يسار",
        "يمين"
    ):
        "AgACAgQAAxkBAAICUmrwguS9B65vj44ETcKYdi6moApRAAI8D2sb8AyJUzwlwJDUwM2LAQADAgADeQADPQQ",

    (
        "blue",
        "وسط",
        "يسار"
    ):
        "AgACAgQAAxkBAAICSmrwgmfnxwHmi4rKsuvO_DDOQLDPAAI3D2sb8AyJU3XNYMaiGWcLAQADAgADeQADPQQ",

    (
        "blue",
        "وسط",
        "وسط"
    ):
        "AgACAgQAAxkBAAICTGrwgocMxm30RugYetJwrMszfRlHAAI4D2sb8AyJU72uLyf9KzHxAQADAgADeQADPQQ",

    (
        "blue",
        "وسط",
        "يمين"
    ):
        "AgACAgQAAxkBAAICSGrwgj1IpJWoTlKRdmqjLkqf7-SRAAI1D2sb8AyJU-AmXmZDBgF4AQADAgADeQADPQQ",

    (
        "blue",
        "يمين",
        "يسار"
    ):
        "AgACAgQAAxkBAAICVGrwgwnaKG8Ed9befVTpVzGdKOKGAAI9D2sb8AyJU-6mtQ86bc-JAQADAgADeQADPQQ",

    (
        "blue",
        "يمين",
        "وسط"
    ):
        "AgACAgQAAxkBAAICUGrwgsRQf-zMwtHFL8T6ZS0s3OXfAAI6D2sb8AyJUw-G9XNNIM9CAQADAgADeQADPQQ",

    (
        "blue",
        "يمين",
        "يمين"
    ):
        "AgACAgQAAxkBAAICTmrwgqb7CI5ZudMxHUTS4Na-aBn5AAI5D2sb8AyJUwqMG_1k73adAQADAgADeQADPQQ",
}

# ==================================================
# الاتجاهات
# ==================================================

DIRECTIONS = {
    "يسار": "👈🏻",
    "وسط": "🎯",
    "يمين": "👉🏻",
}

# ==================================================
# الألعاب النشطة
# ==================================================

active_penalty_games = {}

# ==================================================
# الصلاحية
# نفس نظام غميضة
# ==================================================

async def can_manage_penalties(user_id, chat_id):

    return await get_rank_level(user_id, chat_id) > 0

# ==================================================
# اسم اللاعب
# ==================================================

def get_player_name(user):

    if not user:
        return "مستخدم"

    # اسم الحساب الظاهر في تيليجرام، وليس اليوزر
    return user.full_name or user.first_name or "مستخدم"

# ==================================================
# لوحة الاتجاهات
# ==================================================

def direction_keyboard(chat_id):

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "يسار 👈🏻",
                callback_data=f"penalty:direction:{chat_id}:يسار"
            ),
            InlineKeyboardButton(
                "وسط 🎯",
                callback_data=f"penalty:direction:{chat_id}:وسط"
            ),
            InlineKeyboardButton(
                "يمين 👉🏻",
                callback_data=f"penalty:direction:{chat_id}:يمين"
            )
        ]
    ])

# ==================================================
# بدء التسجيل
# ==================================================

async def start_penalty_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    # ==================================================
    # التأكد أنها داخل قروب
    # ==================================================

    if chat.type == "private":

        await update.message.reply_text(
            "❌ لعبة البلنتيات تبدأ من القروب."
        )

        return

    # ==================================================
    # الصلاحية
    # ==================================================

    if not await can_manage_penalties(user.id, chat.id):

        await update.message.reply_text(
            "❌ هذا الأمر للرتب فقط."
        )

        return

    # ==================================================
    # فحص قفل الألعاب الكبيرة
    # ==================================================

    big_game = get_big_game(chat.id)

    if big_game:

        await update.message.reply_text(
            f"❌ فيه لعبة شغالة حاليًا!: "
            f"{big_game['name']}\n\n"
            "🛑 أنهِ اللعبة الحالية أولًا قبل بدء لعبة أخرى."
        )

        return
   
    # ==================================================
    # التأكد من عدم وجود بلنتيات شغالة
    # ==================================================

    if chat.id in active_penalty_games:

        await update.message.reply_text(
            "❌ توجد مباراة بلنتيات شغالة بالفعل."
        )

        return

    # ==================================================
    # إنشاء اللعبة
    # ==================================================

    active_penalty_games[chat.id] = {

        "stats_game_key": uuid.uuid4().hex,
        "players": {},
        "order": [],

        "phase": "registration",

        "red": {
            "shooters": [],
            "goalies": []
        },

        "blue": {
            "shooters": [],
            "goalies": []
        },

        "shoot_index": {
            "red": 0,
            "blue": 0
        },

        "goalie_index": {
            "red": 0,
            "blue": 0
        },

        "score": {
            "red": 0,
            "blue": 0
        },

        "kick_number": 1,

        "current_team": "red",

        "current_shooter": None,
        "current_goalie": None,

        "shooter_choice": None,
        "goalie_choice": None,

        "shooter_ready": False,
        "goalie_ready": False,

        "ready_message_id": None,

        "shooter_task": None,
        "goalie_task": None,

        "resolving": False,

        "manual_message_id": None,

        "used_players": set(),
    }

    # ==================================================
    # قفل الألعاب الكبيرة
    # ==================================================

    lock_big_game(
        chat.id,
        "penalties",
        "البلنتيات ⚽"
    )

    # ==================================================
    # رسالة البداية
    # ==================================================

    await update.message.reply_text(
        "⚽️ تم بدء لعبة البلنتيات 🥅\n\n"
        "• للانضمام اكتب: دخول\n"
        "• للبدء اكتب: ابدا"
    )

# ==================================================
# دخول اللاعب
# ==================================================

async def join_penalty_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    game = active_penalty_games.get(chat_id)

    if not game:
        return

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

    await update.message.reply_text(
        f"انضم {get_player_name(user)} ⚽ "
        f"(العدد: {len(game['players'])})"
    )

# ==================================================
# بدء التوزيع
# ==================================================

async def distribute_penalties(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if not await can_manage_penalties(user.id, chat_id):
        return

    if game["phase"] != "registration":
        return

    if len(game["players"]) < 2:

        await update.message.reply_text(
            "❌ يجب أن يكون هناك لاعبان على الأقل."
        )

        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔘 يدوي",
                callback_data=f"penalty:distribution:{chat_id}:manual"
            ),
            InlineKeyboardButton(
                "🔘 عشوائي",
                callback_data=f"penalty:distribution:{chat_id}:random"
            )
        ]
    ])

    await update.message.reply_text(
        "🛡️ توزيع فرق مباراة البلنتيات "
        "(أحمر ضد أزرق)\n"
        f"يا {get_player_name(user)}، كيف تبي نوزّع اللاعبين؟",
        reply_markup=keyboard
    )

# ==================================================
# callback التوزيع
# ==================================================

async def distribution_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    try:

        parts = query.data.split(":")

        if len(parts) != 4:
            await query.answer()
            return

        _, action, chat_id_text, mode = parts

        chat_id = int(chat_id_text)

    except Exception:

        await query.answer()
        return

    game = active_penalty_games.get(chat_id)

    if not game:

        await query.answer(
            "❌ انتهت المباراة.",
            show_alert=True
        )

        return

    if not await can_manage_penalties(
        query.from_user.id,
        chat_id
    ):

        await query.answer(
            "❌ ما عندك صلاحية.",
            show_alert=True
        )

        return

    if game["phase"] != "registration":

        await query.answer(
            "❌ انتهى وقت التوزيع.",
            show_alert=True
        )

        return

    await query.answer()

    # ==================================================
    # احذف رسالة:
    # 🛡️ توزيع فرق مباراة البلنتيات...
    # ==================================================

    try:
        await query.message.delete()
    except Exception:
        pass

    # ==================================================
    # عشوائي
    # ==================================================

    if mode == "random":

        await random_distribution(
            context,
            chat_id
        )

        return

    # ==================================================
    # يدوي
    # ==================================================

    if mode == "manual":

        await show_manual_distribution(
            context,
            chat_id
        )

        return

# ==================================================
# التوزيع العشوائي
# ==================================================

def make_random_teams(game):

    player_ids = list(game["players"].keys())

    random.shuffle(player_ids)

    count = len(player_ids)

    if count == 2:

        red_id = player_ids[0]
        blue_id = player_ids[1]

        game["red"]["shooters"] = [red_id]
        game["red"]["goalies"] = [red_id]

        game["blue"]["shooters"] = [blue_id]
        game["blue"]["goalies"] = [blue_id]

        return

    red_count = (count + 1) // 2
    blue_count = count - red_count

    red_players = player_ids[:red_count]
    blue_players = player_ids[red_count:]

    def assign_team(team_players, team):

        shuffled = list(team_players)

        random.shuffle(shuffled)

        if len(shuffled) == 1:

            game[team]["shooters"] = [shuffled[0]]
            game[team]["goalies"] = [shuffled[0]]

            return

        # المسددون أكثر من الحراس
        goalie_count = max(1, len(shuffled) // 3)

        if goalie_count >= len(shuffled):
            goalie_count = 1

        goalie_ids = shuffled[:goalie_count]
        shooter_ids = shuffled[goalie_count:]

        game[team]["shooters"] = shooter_ids
        game[team]["goalies"] = goalie_ids

    assign_team(red_players, "red")
    assign_team(blue_players, "blue")

async def random_distribution(
    context,
    chat_id
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    make_random_teams(game)

    game["phase"] = "distributed"

    await send_distribution_result(
        context,
        chat_id,
        random_mode=True
    )

# ==================================================
# عرض التوزيع اليدوي
# ==================================================

async def show_manual_distribution(
    context,
    chat_id
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    game["phase"] = "manual"

    lines = []

    for index, player_id in enumerate(
        game["order"],
        start=1
    ):

        player = game["players"][player_id]

        lines.append(
            f"{index}. {get_player_name(player)}"
        )

    message = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🎯 التوزيع اليدوي لمباراة البلنتيات\n\n"
            + "\n".join(lines)
            + "\n\n"
            "استخدم:\n"
            ".احمر رقم رقم*\n"
            ".ازرق رقم رقم*\n\n"
            "ضع * بجانب الرقم لجعل اللاعب حارسًا.\n"
            "مثال:\n"
            ".احمر 1 2*\n\n"
            "يعني:\n"
            "1 = مسدد\n"
            "2 = حارس"
        )
    )

    game["manual_message_id"] = message.message_id

# ==================================================
# تحويل رقم اللاعب
# ==================================================

def get_player_by_number(game, number):

    if number < 1 or number > len(game["order"]):
        return None

    player_id = game["order"][number - 1]

    return player_id

# ==================================================
# الأمر اليدوي
# ==================================================

async def manual_team_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "manual":
        return

    user = update.effective_user

    if not await can_manage_penalties(user.id, chat_id):
        return

    text = update.message.text.strip()

    parts = text.split()

    if len(parts) < 2:
        return

    command = parts[0]

    if command not in (".احمر", ".ازرق"):
        return

    team = "red" if command == ".احمر" else "blue"

    selected = []

    for raw in parts[1:]:

        is_goalie = raw.endswith("*")

        clean = raw[:-1] if is_goalie else raw

        try:
            number = int(clean)
        except ValueError:
            await update.message.reply_text(
                f"❌ الرقم {clean} غير صحيح."
            )
            return

        player_id = get_player_by_number(
            game,
            number
        )

        if player_id is None:

            await update.message.reply_text(
                f"❌ لا يوجد لاعب بالرقم {number}."
            )

            return

        selected.append(
            (player_id, is_goalie)
        )

    # لا يسمح بتكرار اللاعب
    for player_id, _ in selected:

        if player_id in game["used_players"]:

            player = game["players"].get(player_id)

            await update.message.reply_text(
                f"❌ اللاعب {get_player_name(player)} "
                "تم توزيعه بالفعل."
            )

            return

    # ==================================================
    # إذا يوجد أكثر من لاعب:
    # يجب أن يكون كل لاعب دورًا واحدًا
    # ==================================================

    unassigned_before = (
        len(game["players"])
        - len(game["used_players"])
    )

    if unassigned_before > len(selected):

        # لا يسمح بأن يكون اللاعب حارس + مسدد
        # إلا إذا كان هذا اللاعب هو الوحيد المتبقي
        pass

    for player_id, is_goalie in selected:

        if is_goalie:

            game[team]["goalies"].append(
                player_id
            )

        else:

            game[team]["shooters"].append(
                player_id
            )

        game["used_players"].add(
            player_id
        )

    await show_manual_status(
        update,
        game,
        team
    )

    await check_manual_completion(
        context,
        chat_id
    )

# ==================================================
# حالة التوزيع اليدوي
# ==================================================

async def show_manual_status(
    update,
    game,
    team
):

    red_shooters = [
        get_player_name(game["players"].get(pid))
        for pid in game["red"]["shooters"]
    ]

    red_goalies = [
        get_player_name(game["players"].get(pid))
        for pid in game["red"]["goalies"]
    ]

    blue_shooters = [
        get_player_name(game["players"].get(pid))
        for pid in game["blue"]["shooters"]
    ]

    blue_goalies = [
        get_player_name(game["players"].get(pid))
        for pid in game["blue"]["goalies"]
    ]

    remaining = [
        index + 1
        for index, player_id in enumerate(game["order"])
        if player_id not in game["used_players"]
    ]

    text = (
        "📋 حالة التوزيع:\n\n"
        "🔴 الفريق الأحمر:\n"
        f"🎯 المسددين: "
        f"{', '.join(red_shooters) if red_shooters else '—'}\n"
        f"🛡️ الحراس: "
        f"{', '.join(red_goalies) if red_goalies else '—'}\n\n"
        "🔵 الفريق الأزرق:\n"
        f"🎯 المسددين: "
        f"{', '.join(blue_shooters) if blue_shooters else '—'}\n"
        f"🛡️ الحراس: "
        f"{', '.join(blue_goalies) if blue_goalies else '—'}"
    )

    if remaining:

        text += (
            "\n\n👥 اللاعبون المتبقون:\n"
            + "\n".join(
                str(number)
                for number in remaining
            )
        )

    await update.message.reply_text(text)

# ==================================================
# إكمال التوزيع اليدوي
# ==================================================

async def check_manual_completion(
    context,
    chat_id
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    remaining = [
        player_id
        for player_id in game["order"]
        if player_id not in game["used_players"]
    ]

    if remaining:
        return

    # ==================================================
    # كل اللاعبين تم توزيعهم
    # ==================================================

    for team in ("red", "blue"):

        total_players = set(
            game[team]["shooters"]
            + game[team]["goalies"]
        )

        # فريق فيه لاعب واحد فقط:
        # يكون مسدد + حارس
        if len(total_players) == 1:

            player_id = next(
                iter(total_players)
            )

            game[team]["shooters"] = [player_id]
            game[team]["goalies"] = [player_id]

    # ==================================================
    # كل فريق لازم عنده مسدد وحارس
    # ==================================================

    for team in ("red", "blue"):

        if not game[team]["shooters"]:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ لا يمكن إكمال التوزيع.\n"
                    f"الفريق "
                    f"{'الأحمر 🔴' if team == 'red' else 'الأزرق 🔵'} "
                    "ليس لديه مسدد."
                )
            )

            return

        if not game[team]["goalies"]:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ لا يمكن إكمال التوزيع.\n"
                    f"الفريق "
                    f"{'الأحمر 🔴' if team == 'red' else 'الأزرق 🔵'} "
                    "ليس لديه حارس."
                )
            )

            return

    game["phase"] = "distributed"

    await send_distribution_result(
        context,
        chat_id,
        random_mode=False
    )

# ==================================================
# نتيجة التوزيع
# ==================================================

async def send_distribution_result(
    context,
    chat_id,
    random_mode=False
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    def names(team, role):

        return ", ".join(
            get_player_name(
                game["players"].get(player_id)
            )
            for player_id in game[team][role]
        )

    text = (
        "🎯 اكتمل توزيع مباراة البلنتيات!\n\n"
        "🔴 الفريق الأحمر:\n"
        f"🎯 المسددين: {names('red', 'shooters')}\n"
        f"🛡️ الحراس: {names('red', 'goalies')}\n\n"
        "🔵 الفريق الأزرق:\n"
        f"🎯 المسددين: {names('blue', 'shooters')}\n"
        f"🛡️ الحراس: {names('blue', 'goalies')}\n\n"
        "الأدمن يكتب .ابدا لبدء ركلات الترجيح! 🚀"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text
    )

# ==================================================
# بدء ركلات الترجيح
# ==================================================

async def begin_penalties(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if not await can_manage_penalties(user.id, chat_id):
        return

    if game["phase"] != "distributed":

        await update.message.reply_text(
            "❌ لم يكتمل توزيع اللاعبين بعد."
        )

        return

    game["phase"] = "shootout"
    game["kick_number"] = 1
    game["current_team"] = "red"

    await start_kick(
        context,
        chat_id
    )

# ==================================================
# جلب المسدد التالي
# ==================================================

def next_shooter(game, team):

    players = game[team]["shooters"]

    index = game["shoot_index"][team] % len(players)

    player_id = players[index]

    game["shoot_index"][team] += 1

    return player_id

# ==================================================
# جلب الحارس التالي
# ==================================================

def next_goalie(game, team):

    players = game[team]["goalies"]

    index = game["goalie_index"][team] % len(players)

    player_id = players[index]

    game["goalie_index"][team] += 1

    return player_id


def get_kick_warning(game):

    red_score = game["score"]["red"]
    blue_score = game["score"]["blue"]

    team = game["current_team"]
    kick_number = game["kick_number"]

    shooter = game["players"].get(
        game["current_shooter"]
    )

    goalie = game["players"].get(
        game["current_goalie"]
    )

    if not shooter or not goalie:
        return None

    shooter_name = get_player_name(shooter)
    goalie_name = get_player_name(goalie)

    # ==================================================
    # أول 5 ركلات لكل فريق
    # ==================================================

    if kick_number <= 10:

        # عدد الركلات المكتملة قبل الركلة الحالية
        red_taken = (kick_number - 1) // 2
        blue_taken = (kick_number - 1) // 2

        # إذا كانت الركلة الحالية للأزرق
        if team == "blue":
            red_taken += 1

        # الركلات المتبقية بعد الركلة الحالية
        if team == "red":

            red_remaining_after = 5 - red_taken - 1
            blue_remaining_after = 5 - blue_taken

            current_score = red_score
            opponent_score = blue_score

            # ------------------------------------------
            # ركلة حاسمة
            # ------------------------------------------

            if (
                current_score + 1
                >
                opponent_score + blue_remaining_after
            ):
                return (
                    "⚠️ *ركلة حاسمة للبطولة!* "
                    f"إذا سجلها *{shooter_name}*، "
                    "يفوز *🔴 الفريق الأحمر* باللقب! 🏆"
                )

            # ------------------------------------------
            # ركلة بقاء
            # ------------------------------------------

            if (
                current_score
                + red_remaining_after
                <= opponent_score
            ):
                return (
                    "⚠️ *ضغوط هائلة!* "
                    f"يجب على *{shooter_name}* التسجيل للاستمرار، "
                    f"إذا ضاعت أو صدها الحارس *{goalie_name}* "
                    "يفوز *🔵 الفريق الأزرق* باللقب! 🏆"
                )

        else:

            red_remaining_after = 5 - red_taken
            blue_remaining_after = 5 - blue_taken - 1

            current_score = blue_score
            opponent_score = red_score

            # ------------------------------------------
            # ركلة حاسمة
            # ------------------------------------------

            if (
                current_score + 1
                >
                opponent_score + red_remaining_after
            ):
                return (
                    "⚠️ *ركلة حاسمة للبطولة!* "
                    f"إذا سجلها *{shooter_name}*، "
                    "يفوز *🔵 الفريق الأزرق* باللقب! 🏆"
                )

            # ------------------------------------------
            # ركلة بقاء
            # ------------------------------------------

            if (
                current_score
                + blue_remaining_after
                <= opponent_score
            ):
                return (
                    "⚠️ *ضغوط هائلة!* "
                    f"يجب على *{shooter_name}* التسجيل للاستمرار، "
                    f"إذا ضاعت أو صدها الحارس *{goalie_name}* "
                    "يفوز *🔴 الفريق الأحمر* باللقب! 🏆"
                )

    # ==================================================
    # Sudden Death
    # ==================================================

    if kick_number > 10:

        # ------------------------------------------
        # الركلة الأولى من ثنائي Sudden Death
        # ------------------------------------------

        if kick_number % 2 == 1:

            # أول ركلة لا تكون حاسمة بحد ذاتها،
            # لأن الفريق الآخر سيأخذ ركلته بعدها.
            return None

        # ------------------------------------------
        # الركلة الثانية من ثنائي Sudden Death
        # ------------------------------------------

        if team == "red":

            # إذا كان الأحمر متأخرًا قبل الركلة
            if red_score < blue_score:
                return (
                    "⚠️ *ضغوط هائلة!* "
                    f"يجب على *{shooter_name}* التسجيل للاستمرار، "
                    f"إذا ضاعت أو صدها الحارس *{goalie_name}* "
                    "يفوز *🔵 الفريق الأزرق* باللقب! 🏆"
                )

            # إذا كان التعادل، فالهدف يحسم
            if red_score == blue_score:
                return (
                    "⚠️ *ركلة حاسمة للبطولة!* "
                    f"إذا سجلها *{shooter_name}*، "
                    "يفوز *🔴 الفريق الأحمر* باللقب! 🏆"
                )

        else:

            # إذا كان الأزرق متأخرًا قبل الركلة
            if blue_score < red_score:
                return (
                    "⚠️ *ضغوط هائلة!* "
                    f"يجب على *{shooter_name}* التسجيل للاستمرار، "
                    f"إذا ضاعت أو صدها الحارس *{goalie_name}* "
                    "يفوز *🔴 الفريق الأحمر* باللقب! 🏆"
                )

            # إذا كان التعادل، فالهدف يحسم
            if blue_score == red_score:
                return (
                    "⚠️ *ركلة حاسمة للبطولة!* "
                    f"إذا سجلها *{shooter_name}*، "
                    "يفوز *🔵 الفريق الأزرق* باللقب! 🏆"
                )

    return None
    
# ==================================================
# بدء الركلة
# ==================================================

async def start_kick(
    context,
    chat_id
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "shootout":
        return

    team = game["current_team"]

    goalie_team = (
        "blue"
        if team == "red"
        else "red"
    )

    shooter_id = next_shooter(
        game,
        team
    )

    goalie_id = next_goalie(
        game,
        goalie_team
    )

    game["current_shooter"] = shooter_id
    game["current_goalie"] = goalie_id

    game["shooter_choice"] = None
    game["goalie_choice"] = None

    game["shooter_ready"] = False
    game["goalie_ready"] = False

    game["resolving"] = False
    game["ready_message_id"] = None

    shooter_task = context.application.create_task(
        choice_timeout(context, chat_id, "shooter"),
        name=f"penalty-shooter-timeout-{chat_id}",
    )

    goalie_task = context.application.create_task(
        choice_timeout(context, chat_id, "goalie"),
        name=f"penalty-goalie-timeout-{chat_id}",
    )

    game["shooter_task"] = shooter_task
    game["goalie_task"] = goalie_task

    await send_ready_image(
        context,
        chat_id,
        goalie_team
    )

# ==================================================
# صورة استعداد الحارس
# ==================================================

async def send_ready_image(
    context,
    chat_id,
    goalie_team
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    file_id = READY_IMAGES.get(goalie_team)

    if not file_id:
        return

    team = game["current_team"]

    shooter = game["players"].get(
        game["current_shooter"]
    )

    goalie = game["players"].get(
        game["current_goalie"]
    )

    shooter_status = (
        "✅ جاهز"
        if game["shooter_ready"]
        else
        "⏳ ينتظر الاختيار"
    )

    goalie_status = (
        "✅ جاهز"
        if game["goalie_ready"]
        else
        "⏳ ينتظر الاختيار"
    )

    # ==================================================
    # اسم الجولة
    # ==================================================

    if game["kick_number"] <= 2:
        round_number = 1
    elif game["kick_number"] <= 4:
        round_number = 2
    elif game["kick_number"] <= 6:
        round_number = 3
    elif game["kick_number"] <= 8:
        round_number = 4
    elif game["kick_number"] <= 10:
        round_number = 5
    else:
        round_number = (
            (game["kick_number"] - 1) // 2
        )

    # ==================================================
    # أول / ثاني ركلة في الجولة
    # ==================================================

    if game["kick_number"] % 2 == 1:
        kick_name = "الركلة الأولى"
    else:
        kick_name = "الركلة الثانية"

    caption = (
        f"🎮 *الجولة {round_number} — {kick_name} "
        f"{'🔴' if team == 'red' else '🔵'}*\n\n"
        f"🎯 المسدد: *{get_player_name(shooter)}* "
        f"{'🔴' if team == 'red' else '🔵'} "
        f"({shooter_status})\n"
        f"🛡️ الحارس: *{get_player_name(goalie)}* "
        f"{'🔵' if goalie_team == 'blue' else '🔴'} "
        f"({goalie_status})\n\n"
    )

    # ==================================================
    # التحذير
    # ==================================================

    warning = get_kick_warning(game)

    if warning:
        caption += warning + "\n\n"

    caption += (
        "اختر الزاوية من الأزرار بالأسفل:"
    )

    message = await context.bot.send_photo(
        chat_id=chat_id,
        photo=file_id,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=direction_keyboard(chat_id)
    )

    game["ready_message_id"] = message.message_id

async def update_ready_message(context, chat_id):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    message_id = game.get("ready_message_id")

    if not message_id:
        return

    team = game["current_team"]

    shooter = game["players"].get(
        game["current_shooter"]
    )

    goalie = game["players"].get(
        game["current_goalie"]
    )

    if not shooter or not goalie:
        return

    shooter_status = (
        "✅ جاهز"
        if game["shooter_ready"]
        else "⏳ ينتظر الاختيار"
    )

    goalie_status = (
        "✅ جاهز"
        if game["goalie_ready"]
        else "⏳ ينتظر الاختيار"
    )

    round_number = (
        (game["kick_number"] + 1) // 2
    )

    if game["kick_number"] % 2 == 1:
        kick_name = "الركلة الأولى"
    else:
        kick_name = "الركلة الثانية"

    shooter_color = (
        "🔴"
        if team == "red"
        else "🔵"
    )

    goalie_color = (
        "🔵"
        if team == "red"
        else "🔴"
    )

    caption = (
        f"🎮 *الجولة {round_number} — {kick_name} "
        f"{shooter_color}*\n\n"

        f"🎯 المسدد: *{get_player_name(shooter)}* "
        f"{shooter_color} "
        f"({shooter_status})\n"

        f"🛡️ الحارس: *{get_player_name(goalie)}* "
        f"{goalie_color} "
        f"({goalie_status})\n\n"
    )

    # رسالة الضغط / الركلة الحاسمة
    warning = get_kick_warning(game)

    if warning:
        caption += warning + "\n\n"

    caption += (
        "اختر الزاوية من الأزرار بالأسفل:"
    )

    try:
        await context.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=direction_keyboard(chat_id)
        )

    except Exception:
        pass

# ==================================================
# تحديث حالة الاختيار
# ==================================================

async def update_kick_status(
    context,
    chat_id
):

    # الحالة تعرض في رسالة جديدة عند بدء الركلة.
    # النتائج نفسها تعتمد على الاختيارات المخزنة.
    return

# ==================================================
# مؤقت الاختيار 
# ==================================================        
   
async def choice_timeout(
    context,
    chat_id,
    role
):

    try:
        await asyncio.sleep(TURN_TIME)

    except asyncio.CancelledError:
        return

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "shootout":
        return

    if role == "shooter":

        if game.get("shooter_choice") is None:
            game["shooter_choice"] = "وسط"
            game["shooter_ready"] = True

    elif role == "goalie":

        if game.get("goalie_choice") is None:
            game["goalie_choice"] = "وسط"
            game["goalie_ready"] = True

    await update_ready_message(
        context,
        chat_id
    )

    # إذا الاثنين اختاروا أو انتهى وقتهم
    if (
        game.get("shooter_choice") is not None
        and game.get("goalie_choice") is not None
    ):
        await resolve_kick(
            context,
            chat_id
        )    

# ==================================================
# إلغاء المؤقتات
# ==================================================

def cancel_kick_tasks(game):

    current_task = asyncio.current_task()

    for key in (
        "shooter_task",
        "goalie_task"
    ):

        task = game.get(key)

        if task:

            # لا تلغي المهمة الحالية إذا كانت هي التي تنفذ النتيجة
            if task is not current_task:
                task.cancel()

        game[key] = None

# ==================================================
# نتيجة الركلة
# ==================================================
async def penalty_direction_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    try:
        _, _, chat_id_text, direction = query.data.split(":")
        chat_id = int(chat_id_text)

    except Exception:
        await query.answer()
        return

    game = active_penalty_games.get(chat_id)

    if not game:
        await query.answer(
            "❌ انتهت المباراة.",
            show_alert=True
        )
        return

    if game["phase"] != "shootout":
        await query.answer(
            "❌ لا توجد ركلة حالية.",
            show_alert=True
        )
        return

    user_id = query.from_user.id

    shooter_id = game["current_shooter"]
    goalie_id = game["current_goalie"]

    if user_id not in game["players"]:
        await query.answer(
            "❌ انت مو بالقيم اصلا!",
            show_alert=True
        )
        return

    if user_id != shooter_id and user_id != goalie_id:
        await query.answer(
            "❌ انتظر، ليس دورك!",
            show_alert=True
        )
        return

    # ==============================
    # المسدد
    # ==============================

    if user_id == shooter_id:

        if game["shooter_choice"] is not None:
            await query.answer(
                "❌ اخترت اتجاهك بالفعل.",
                show_alert=True
            )
            return

        game["shooter_choice"] = direction
        game["shooter_ready"] = True

        task = game.get("shooter_task")

        if task:
            task.cancel()

        game["shooter_task"] = None

        await query.answer(
            "✅ تم تسجيل اختيارك."
        )

    # ==============================
    # الحارس
    # ==============================

    elif user_id == goalie_id:

        if game["goalie_choice"] is not None:
            await query.answer(
                "❌ اخترت اتجاهك بالفعل.",
                show_alert=True
            )
            return

        game["goalie_choice"] = direction
        game["goalie_ready"] = True

        task = game.get("goalie_task")

        if task:
            task.cancel()

        game["goalie_task"] = None

        await query.answer(
            "✅ تم تسجيل اختيارك."
        )

    await update_ready_message(
        context,
        chat_id
    )

    # ==============================
    # إذا الاثنين اختاروا
    # ==============================

    if (
        game["shooter_choice"] is not None
        and game["goalie_choice"] is not None
    ):
        await resolve_kick(
            context,
            chat_id
        )





async def penalty_direction_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Accept direction choices typed by the active shooter or goalie."""

    message = update.message
    if not message or not message.text:
        return

    direction = message.text.strip()
    if direction not in DIRECTIONS:
        return

    chat_id = update.effective_chat.id
    game = active_penalty_games.get(chat_id)

    # Ignore typed directions unless a penalty kick is currently active.
    if not game or game.get("phase") != "shootout" or game.get("resolving"):
        return

    user_id = update.effective_user.id
    shooter_id = game.get("current_shooter")
    goalie_id = game.get("current_goalie")

    # Players who are not taking this kick must be completely ignored.
    if user_id != shooter_id and user_id != goalie_id:
        return

    if user_id == shooter_id:
        if game.get("shooter_choice") is not None:
            return
        role = "shooter"
        game["shooter_choice"] = direction
        game["shooter_ready"] = True
    else:
        if game.get("goalie_choice") is not None:
            return
        role = "goalie"
        game["goalie_choice"] = direction
        game["goalie_ready"] = True

    # A valid typed choice is consumed immediately and cannot be changed by
    # pressing a button afterward (the callback checks the same stored choice).
    try:
        await message.delete()
    except Exception:
        pass

    task_key = "shooter_task" if role == "shooter" else "goalie_task"
    task = game.get(task_key)
    if task:
        task.cancel()
    game[task_key] = None

    await update_ready_message(context, chat_id)

    if (
        game.get("shooter_choice") is not None
        and game.get("goalie_choice") is not None
    ):
        await resolve_kick(context, chat_id)

async def resolve_kick(
    context,
    chat_id
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if game["phase"] != "shootout":
        return

    # منع تنفيذ نفس الركلة أكثر من مرة
    if game.get("resolving"):
        return

    game["resolving"] = True

    try:

        # ==============================
        # إذا أحد ما اختار
        # ==============================

        if game.get("shooter_choice") is None:
            game["shooter_choice"] = "وسط"

        if game.get("goalie_choice") is None:
            game["goalie_choice"] = "وسط"

        game["shooter_ready"] = True
        game["goalie_ready"] = True

        shooter_choice = game["shooter_choice"]
        goalie_choice = game["goalie_choice"]

        # ==============================
        # إلغاء التايمرات
        # ==============================

        cancel_kick_tasks(game)

        shooter_id = game["current_shooter"]
        goalie_id = game["current_goalie"]

        shooter = game["players"].get(shooter_id)
        goalie = game["players"].get(goalie_id)

        if not shooter or not goalie:
            return

        shooting_team = game["current_team"]

        goalie_team = (
            "blue"
            if shooting_team == "red"
            else "red"
        )

        # ==============================
        # التحذير
        # ==============================

        warning = get_kick_warning(game)

        is_decisive_kick = (
            warning is not None
            and "ركلة حاسمة للبطولة" in warning
        )

        is_survival_kick = (
            warning is not None
            and "ضغوط هائلة" in warning
        )

        # ==============================
        # تحديد الهدف
        # ==============================

        goal = (
            shooter_choice != goalie_choice
        )

        if goal:
            game["score"][shooting_team] += 1

        # ==============================
        # التشويق
        # ==============================

        teaser = None

        try:

            teaser = await context.bot.send_message(
                chat_id=chat_id,
                text="هل يسجلها المسدد؟ ام يصدها الحارس…🧤🔥"
            )

        except Exception as e:

            print(
                f"❌ خطأ في إرسال رسالة التشويق: {e}"
            )

        # ==============================
        # انتظار 5 ثواني
        # ==============================

        await asyncio.sleep(5)

        if teaser:

            try:
                await teaser.delete()

            except Exception:
                pass

        # ==============================
        # صورة النتيجة
        # ==============================

        image_id = RESULT_IMAGES.get(
            (
                goalie_team,
                goalie_choice,
                shooter_choice
            )
        )

        # ==============================
        # نص النتيجة
        # ==============================

        if goal:

            team_name = (
                "الأحمر 🔴"
                if shooting_team == "red"
                else
                "الأزرق 🔵"
            )

            text = (
                f"⚽ قوووول!! هدف لصالح "
                f"{get_player_name(shooter)} "
                f"(فريق {team_name}) 🔥\n\n"

                f"🎯 المسدد سدد في "
                f"{shooter_choice} "
                f"{DIRECTIONS[shooter_choice]} "
                f"والحارس ارتمى إلى "
                f"{goalie_choice} "
                f"{DIRECTIONS[goalie_choice]}!\n\n"

                f"📊 النتيجة: "
                f"🔴 الأحمر {game['score']['red']} "
                f"- {game['score']['blue']} الأزرق 🔵"
            )

        else:

            goalie_team_name = (
                "الأحمر 🔴"
                if goalie_team == "red"
                else
                "الأزرق 🔵"
            )

            text = (
                "🧤 ياساتر صدها الحارس! مستحييل! 💥\n\n"

                f"🛡️ الحارس {get_player_name(goalie)} "
                f"(فريق {goalie_team_name}) "
                f"تصدى للكرة في "
                f"{goalie_choice} "
                f"{DIRECTIONS[goalie_choice]}!\n\n"

                f"📊 النتيجة: "
                f"🔴 الأحمر {game['score']['red']} "
                f"- {game['score']['blue']} الأزرق 🔵"
            )

        # ==============================
        # إرسال صورة النتيجة
        # ==============================

        try:

            if image_id:

                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=image_id,
                    caption=text
                )

            else:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text
                )

        except Exception as e:

            print(
                f"❌ خطأ في إرسال صورة النتيجة: {e}"
            )

            try:

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text
                )

            except Exception as e2:

                print(
                    f"❌ خطأ في إرسال النتيجة: {e2}"
                )

        # ==============================
        # ركلة حاسمة
        # ==============================

        if is_decisive_kick:

            if goal:

                await finish_penalty_game(
                    context,
                    chat_id,
                    shooting_team
                )

            else:

                await finish_penalty_game(
                    context,
                    chat_id,
                    goalie_team
                )

            return

        # ==============================
        # ركلة البقاء
        # ==============================

        if is_survival_kick:

            if not goal:

                await finish_penalty_game(
                    context,
                    chat_id,
                    goalie_team
                )

                return

        # ==============================
        # التحقق من انتهاء المباراة
        # ==============================

        winner = get_winner_if_finished(game)

        if winner:

            await finish_penalty_game(
                context,
                chat_id,
                winner
            )

            return

        # ==============================
        # انتظار .كمل
        # ==============================

        await context.bot.send_message(
            chat_id=chat_id,
            text="⏸️ اكتب .كمل للركلة التالية."
        )

    except asyncio.CancelledError:

        # لا نخلي إلغاء مهمة جانبية يسكت الخطأ
        print(
            f"⚠️ تم إلغاء مهمة نتيجة الركلة في القروب {chat_id}"
        )

    except Exception as e:

        print(
            f"خطأ غير متوقع ❌"
            f"للقروب {chat_id}: {e}"
        )

    finally:

        # إذا اللعبة ما انتهت، افتحها للركلة التالية
        current_game = active_penalty_games.get(chat_id)

        if current_game:
            if current_game["phase"] == "shootout":
                current_game["resolving"] = False

# ==================================================
# تحديد الفائز حسب نظام الركلات الحقيقي
# ==================================================

def get_winner_if_finished(game):

    red_score = game["score"]["red"]
    blue_score = game["score"]["blue"]

    kick_number = game["kick_number"]

    # ==================================================
    # أول 5 ركلات لكل فريق
    # ==================================================

    if kick_number <= 10:

        # عدد الركلات المكتملة بعد الركلة الحالية
        if kick_number % 2 == 1:
            # الأحمر هو الذي أخذ الركلة الحالية
            red_taken = (kick_number + 1) // 2
            blue_taken = (kick_number - 1) // 2

        else:
            # الأزرق هو الذي أخذ الركلة الحالية
            red_taken = kick_number // 2
            blue_taken = kick_number // 2

        # لازم الفريقين يكملون 5 ركلات
        if red_taken < 5 or blue_taken < 5:
            return None

        # بعد إكمال 5-5
        if red_score > blue_score:
            return "red"

        if blue_score > red_score:
            return "blue"

        # التعادل = Sudden Death
        return None

    # ==================================================
    # Sudden Death
    # ==================================================

    if kick_number > 10:

        # بعد الركلة الثانية من كل ثنائي
        # نقارن النتيجة.
        #
        # إذا اختلفت النتيجة:
        # الفريق المتقدم يفوز.
        #
        # إذا تعادلت:
        # نكمل ثنائي جديد.

        if kick_number % 2 == 0:

            if red_score > blue_score:
                return "red"

            if blue_score > red_score:
                return "blue"

        return None

    return None


# ==================================================
# .كمل
# ==================================================

async def continue_penalties(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if not await can_manage_penalties(user.id, chat_id):
        return

    if game["phase"] != "shootout":
        return

    if game["resolving"]:

        await update.message.reply_text(
            "⏳ انتظر حتى تنتهي الركلة الحالية."
        )

        return

    # يجب أن تكون الركلة السابقة منتهية
    if (
        game["shooter_choice"] is None
        or game["goalie_choice"] is None
    ):

        await update.message.reply_text(
            "❌ الركلة الحالية لم تنتهِ بعد."
        )

        return

    # الفائز لو كانت المباراة انتهت
    winner = get_winner_if_finished(game)

    if winner:

        await finish_penalty_game(
            context,
            chat_id,
            winner
        )

        return

    # الجولة التالية
    game["kick_number"] += 1

    # أحمر ثم أزرق دائمًا
    game["current_team"] = (
        "blue"
        if game["current_team"] == "red"
        else "red"
    )

    await start_kick(
        context,
        chat_id
    )

# ==================================================
# إنهاء المباراة يدويًا
# ==================================================

async def end_penalty_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if not await can_manage_penalties(user.id, chat_id):
        return

    cancel_kick_tasks(game)

    active_penalty_games.pop(
        chat_id,
        None
    )

    unlock_big_game(
        chat_id,
        "penalties"
    )

    await update.message.reply_text(
        "🛑 تم إنهاء مباراة البلنتيات."
    )

# ==================================================
# إنهاء المباراة + الجوائز
# ==================================================
async def finish_penalty_game(
    context,
    chat_id,
    winner
):

    game = active_penalty_games.get(chat_id)

    if not game:
        return

    if game["phase"] == "finished":
        return

    game["phase"] = "finished"

    cancel_kick_tasks(game)

    loser = (
        "blue"
        if winner == "red"
        else "red"
    )

    winner_name = (
        "🔴 الفريق الأحمر"
        if winner == "red"
        else "🔵 الفريق الأزرق"
    )

    text = (
        "🏆 انتهت مباراة البلنتيات! 🏆\n\n"
        f"🎉 الفائز: {winner_name}!\n\n"
        f"النتيجة النهائية: "
        f"🔴 الأحمر {game['score']['red']} "
        f"- {game['score']['blue']} الأزرق 🔵"
    )

    # ==================================================
    # رسالة نهاية المباراة
    # ==================================================

    await context.bot.send_message(
        chat_id=chat_id,
        text=text
    )

    # ==================================================
    # جوائز الفريق الفائز
    # ==================================================

    winners = list(dict.fromkeys(
        game[winner]["shooters"]
        + game[winner]["goalies"]
    ))

    losers = list(dict.fromkeys(
        game[loser]["shooters"] + game[loser]["goalies"]
    ))
    try:
        from database.game_stats import record_game_results
        player_map = game.get("players", {})
        winner_rows = [{"id": int(pid), "name": get_player_name(player_map[pid])}
                       for pid in winners if pid in player_map]
        loser_rows = [{"id": int(pid), "name": get_player_name(player_map[pid])}
                      for pid in losers if pid in player_map]
        await record_game_results(
            f"penalties:{game.get('stats_game_key') or chat_id}", "penalties",
            winner_rows, loser_rows,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to record penalties results")

    reward_lines = [
        "✨ جوائز الفريق الفائز: ✨"
    ]

    for player_id in winners:

        player = game["players"].get(player_id)

        if not player:
            continue

        try:

            await add_points(
                player_id,
                WIN_POINTS
            )

            reward_lines.append(
                f"• {get_player_name(player)} — "
                f"حصل على {WIN_POINTS} نقطة! 🎖️"
            )

        except Exception as e:

            print(
                f"❌ خطأ في إضافة النقاط للاعب "
                f"{player_id}: {e}"
            )

            reward_lines.append(
                f"• {get_player_name(player)} — "
                f"حصل على {WIN_POINTS} نقطة! 🎖️"
            )

    # ==================================================
    # إرسال رسالة الجوائز
    # ==================================================

    try:

        await context.bot.send_message(
            chat_id=chat_id,
            text="\n".join(reward_lines)
        )

    except Exception as e:

        print(
            f"❌ خطأ في إرسال رسالة الجوائز: {e}"
        )

    # ==================================================
    # حذف اللعبة
    # ==================================================

    active_penalty_games.pop(
        chat_id,
        None
    )

    unlock_big_game(
        chat_id,
        "penalties"
    )
