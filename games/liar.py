import asyncio
import random
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.roles import get_rank_level
from database.points import add_points


from games.big_game_lock import (
    get_big_game,
    lock_big_game,
    unlock_big_game
)
# =========================================================
# الإعدادات
# =========================================================

DISCUSSION_TIME = 5 * 60
GUESS_TIME = 30

# أقل عدد لاعبين
MIN_PLAYERS = 3

# النقاط
CORRECT_VOTE_POINTS = 40
LIAR_CAUGHT_GUESS_POINTS = 20
LIAR_FREE_GUESS_POINTS = 40


# =========================================================
# الألعاب النشطة
# =========================================================

active_liar_games = {}


# =========================================================
# الكلمات
# =========================================================

WORD_PAIRS = [

    # الحيوانات
    ("ذيب", "أسد"),
    ("خنزير", "بقرة"),
    ("حصان", "جمل"),
    ("فيل", "زرافة"),
    ("قرد", "غوريلا"),
    ("نمر", "فهد"),
    ("دب", "ثعلب"),
    ("أرنب", "سلحفاة"),
    ("تمساح", "قرش"),
    ("حوت", "دلفين"),
    ("غراب", "صقر"),
    ("بومة", "نسر"),
    ("نحلة", "فراشة"),
    ("نملة", "عنكبوت"),
    ("دجاجة", "بط"),
    ("ماعز", "خروف"),
    ("حمار", "حصان"),
    ("قطوة", "كلب"),

    # فواكه
    ("تفاح", "موز"),
    ("برتقال", "تفاح"),
    ("بطيخ", "شمام"),
    ("عنب", "كرز"),
    ("فراولة", "توت"),
    ("مانجو", "أناناس"),
    ("ليمون", "برتقال"),
    ("خوخ", "شمام"),
    ("رمان", "تين"),
    ("كيوي", "جوافة"),

    # أكل
    ("بيتزا", "برجر"),
    ("كبسة", "برياني"),
    ("شاورما", "فلافل"),
    ("مكرونة", "أرز"),
    ("دجاج", "لحم"),
    ("بطاطس", "ذرة"),
    ("حلا اوريو", "دونات"),
    ("آيس كريم", "شوكولاتة"),
    ("شوربة", "سلطة"),
    ("بيض", "جبن"),

    # مشروبات
    ("قهوة", "عصير"),
    ("شاي", "قهوة"),
    ("حليب", "ماء"),
    ("ليمون", "برتقال"),
    ("مشروب غازي", "ماء"),

    # تقنية
    ("لابتوب", "آيباد"),
    ("جوال", "تلفزيون"),
    ("آيفون", "سامسونج"),
    ("كمبيوتر", "بلايستيشن"),
    ("سماعة", "ميكروفون"),
    ("كيبورد", "ماوس"),
    ("كاميرا", "جوال"),

    # سيارات ومواصلات
    ("سيارة", "طائرة"),
    ("قطار", "حافلة"),
    ("سفينة", "طائرة"),
    ("سيكل", "سيارة"),
    ("تاكسي", "حافلة"),
    ("دباب", "سيارة"),

    # رياضة
    ("كرة قدم", "كرة سلة"),
    ("تنس", "بادل"),
    ("سباحة", "جري"),
    ("كرة طائرة", "كرة سلة"),
    ("قولف", "تنس"),

    # ألعاب
    ("بلايستيشن", "إكس بوكس"),
    ("روكيت ليق", "فيفا"),
    ("ماينكرافت", "روبلوكس"),
    ("فورتنايت", "ببجي"),
    ("جوال", "بلايستيشن"),
    ("لعبة", "فيلم"),

    # المنزل
    ("بيت", "مدرسة"),
    ("غرفة", "مطبخ"),
    ("سرير", "كنبة"),
    ("طاولة", "كرسي"),
    ("ثلاجة", "فرن"),
    ("تلفزيون", "كمبيوتر"),
    ("باب", "نافذة"),
    ("مصباح", "مروحة"),
    ("حمام", "مطبخ"),
    ("حديقة", "سطح"),

    # الملابس
    ("ثوب", "بدلة"),
    ("قبعة", "شماغ"),
    ("شرَّابات", "قفازات"),
    ("نظارة", "ساعة"),

    # أماكن
    ("مدرسة", "جامعة"),
    ("مطعم", "مقهى"),
    ("شاطئ", "منتزه"),
    ("ملعب", "نادي"),
    ("سينما", "مسرح"),

    # الطبيعة
    ("بحر", "نهر"),
    ("صحراء", "غابة"),
    ("شمس", "قمر"),
    ("مطر", "ثلج"),
    ("برق", "رعد"),
    ("شجرة", "زهرة"),
    ("نخلة", "شجرة"),
    ("نار", "ماء"),

    # المدرسة
    ("كتاب", "دفتر"),
    ("سبورة", "شاشة"),
    ("معلم", "طالب"),
    ("اختبار", "واجب"),
    ("رياضيات", "علوم"),
    ("جامعة", "مدرسة"),

    # السفر
    ("جواز سفر", "تذكرة"),
    ("مطار", "فندق"),
    ("سيارة", "طائرة"),

    # المهن
    ("معلم", "مهندس"),
    ("محامي", "قاضي"),
    ("طيار", "سائق"),
    ("مبرمج", "مصمم"),

    # أشياء يومية
    ("محفظة", "حقيبة"),
    ("ساعة", "جوال"),
    ("قلم", "فرشاة"),
    ("كرسي", "طاولة"),
    ("سرير", "وسادة"),

    # ترفيه
    ("فيلم", "مسلسل"),
    ("أغنية", "بودكاست"),
    ("مغني", "ممثل"),
    ("يوتيوب", "تيك توك"),
    ("كتاب", "فيلم"),
    ("رواية", "قصة"),

    # مدن ودول
    ("الرياض", "جدة"),
    ("لندن", "باريس"),
    ("السعودية", "الإمارات"),
    ("تركيا", "اليونان"),

    # متنوعة
    ("ذهب", "فضة"),
    ("صيف", "شتاء"),
    ("بحر", "سماء"),
]


# =========================================================
# أدوات مساعدة
# =========================================================

def normalize_text(text):
    if not text:
        return ""

    text = text.strip().lower()

    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    text = (
        text
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
    )

    text = re.sub(r"\s+", " ", text)

    return text


def player_name(user):
    if user.username:
        return f"@{user.username}"

    return user.first_name or "مستخدم"


def mention_user(user):
    name = user.first_name or "مستخدم"
    return f"[{name}](tg://user?id={user.id})"


def lobby_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎮 دخول",
                callback_data="liar:join"
            ),
            InlineKeyboardButton(
                "🚪 خروج",
                callback_data="liar:leave"
            )
        ]
    ])


def lobby_text(game):
    players = game["players"]

    text = (
        "🕵️ **لعبة الكذاب**\n\n"
        "🎮 اكتب للانضمام إلى اللعبة.\n"
        "🚪 يمكنك الخروج قبل بدء اللعبة.\n\n"
        f"👥 عدد اللاعبين: **{len(players)}**\n"
    )

    if len(players) < MIN_PLAYERS:
        text += (
            f"\n⚠️ الحد الأدنى لبدء اللعبة: **{MIN_PLAYERS} لاعبين**"
        )

    text += "\n\n"

    if players:
        text += "👥 **اللاعبون:**\n"

        for index, user in enumerate(players.values(), 1):
            text += f"{index}. {mention_user(user)}\n"

    return text


def choose_word_pair():
    return random.choice(WORD_PAIRS)


def choose_guess_options(correct_word):
    """
    يختار 7 كلمات للتخمين.
    واحدة منها صحيحة، والباقي من نفس مجموعة الكلمات.
    """

    correct_normalized = normalize_text(correct_word)

    candidates = []

    for pair in WORD_PAIRS:
        for word in pair:
            if normalize_text(word) != correct_normalized:
                candidates.append(word)

    candidates = list(dict.fromkeys(candidates))

    random.shuffle(candidates)

    options = [correct_word]

    for word in candidates:
        if normalize_text(word) == correct_normalized:
            continue

        if word not in options:
            options.append(word)

        if len(options) >= 7:
            break

    random.shuffle(options)

    return options[:7]


def guess_keyboard(options):
    rows = []

    for i in range(0, len(options), 2):
        row = []

        for word in options[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    word,
                    callback_data=f"liar_guess:{normalize_text(word)}"
                )
            )

        rows.append(row)

    return InlineKeyboardMarkup(rows)


# =========================================================
# بدء اللعبة
# =========================================================

async def start_liar_game_lobby(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    chat = update.effective_chat

    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "❌ اللعبة تعمل داخل القروبات فقط."
        )
        return

    chat_id = chat.id


    big_game = get_big_game(chat.id)

    if big_game:

        await update.message.reply_text(
            f"❌ فيه لعبة شغالة حاليًا!: "
            f"{big_game['name']}\n\n"
            "🛑 أنهِ اللعبة الحالية أولًا قبل بدء لعبة أخرى."
        )

        return

    if chat_id in active_liar_games:
        await update.message.reply_text(
            "⚠️ توجد لعبة كذاب شغالة حاليًا في هذه المجموعة."
        )
        return

    game = {
        "chat_id": chat_id,
        "players": {},
        "started": False,
        "phase": "lobby",
        "liar_id": None,
        "base_word": None,
        "liar_word": None,
        "votes": {},
        "eliminated": set(),
        "guess_options": [],
        "guess_selected": False,
        "guess_result": None,
        "lobby_message_id": None,
        "discussion_task": None,
        "vote_task": None,
        "guess_task": None,
        "voting_started": False,
    }

    active_liar_games[chat_id] = game


    lock_big_game(
        chat_id,
        "liar",
        "الكذاب 🎭"
    )

    message = await update.message.reply_text(
        lobby_text(game),
        parse_mode="Markdown",
        reply_markup=lobby_keyboard()
    )

    game["lobby_message_id"] = message.message_id


# =========================================================
# دخول
# =========================================================

async def join_liar_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    game = active_liar_games.get(chat.id)

    if not game:
        return

    if game["started"]:
        return

    user = update.effective_user

    if user.id in game["players"]:
        await update.message.reply_text(
            "⚠️ أنت داخل اللعبة بالفعل."
        )
        return

    game["players"][user.id] = user

    await update.message.reply_text(
        f"✅ انضم {mention_user(user)} إلى لعبة الكذاب!\n"
        f"👥 العدد: **{len(game['players'])}**",
        parse_mode="Markdown"
    )

    await update_lobby(context, game)


# =========================================================
# خروج
# =========================================================

async def leave_liar_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    game = active_liar_games.get(chat.id)

    if not game or game["started"]:
        return

    user = update.effective_user

    if user.id not in game["players"]:
        await update.message.reply_text(
            "❌ أنت لست داخل اللعبة."
        )
        return

    del game["players"][user.id]

    await update.message.reply_text(
        f"🚪 خرج {mention_user(user)} من اللعبة.",
        parse_mode="Markdown"
    )

    await update_lobby(context, game)


# =========================================================
# تحديث اللوبي
# =========================================================

async def update_lobby(context, game):
    try:
        await context.bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["lobby_message_id"],
            text=lobby_text(game),
            parse_mode="Markdown",
            reply_markup=lobby_keyboard()
        )
    except Exception:
        pass


# =========================================================
# بدء اللعبة
# =========================================================

async def begin_liar_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    game = active_liar_games.get(chat.id)

    if not game:
        return

    if game["started"]:
        return

    user = update.effective_user

    # المطور / الأدمن فقط
    if await get_rank_level(user.id, chat.id) < 1:
        return

    player_ids = list(game["players"].keys())

    if len(player_ids) < MIN_PLAYERS:
        await update.message.reply_text(
            f"❌ لا يمكن بدء اللعبة.\n\n"
            f"👥 يجب أن يكون عدد اللاعبين **{MIN_PLAYERS} لاعبين على الأقل**."
        )
        return

    await begin_game(context, game)


# =========================================================
# تشغيل اللعبة فعليًا
# =========================================================

async def begin_game(context, game):

    player_ids = list(game["players"].keys())

    game["started"] = True
    game["phase"] = "preparing"

    # -----------------------------------------------------
    # التأكد من أن الجميع بدأوا البوت بالخاص
    # -----------------------------------------------------

    unavailable = []

    for player_id in player_ids:
        try:
            await context.bot.send_chat_action(
                chat_id=player_id,
                action="typing"
            )
        except Exception:
            unavailable.append(player_id)

    if unavailable:

        names = []

        for player_id in unavailable:
            user = game["players"].get(player_id)

            if user:
                names.append(mention_user(user))

        game["started"] = False
        game["phase"] = "lobby"

        await context.bot.send_message(
            chat_id=game["chat_id"],
            text=(
                "⚠️ لا يمكن بدء لعبة الكذاب حاليًا.\n\n"
                "الأشخاص التاليون لم يبدأوا البوت في الخاص:\n\n"
                + "\n".join(names)
                + "\n\n"
                "📩 كل لاعب منهم يرسل للبوت `/start` في الخاص، "
                "ثم يعيد الأدمن كتابة `.ابدا`."
            ),
            parse_mode="Markdown"
        )

        return

    # -----------------------------------------------------
    # اختيار الكلمات
    # -----------------------------------------------------

    base_word, liar_word = choose_word_pair()

    liar_id = random.choice(player_ids)

    game["base_word"] = base_word
    game["liar_word"] = liar_word
    game["liar_id"] = liar_id
    game["phase"] = "discussion"

    # -----------------------------------------------------
    # إرسال الكلمات بالخاص
    # -----------------------------------------------------

    for player_id in player_ids:

        if player_id == liar_id:
            word = liar_word

            private_text = (
                "🕵️ **أنت الكذاب!**\n\n"
                f"🔐 كلمتك السرية: **{word}**\n\n"
                "⚠️ حاول تندمج مع اللاعبين ولا تخليهم يعرفون أنك الكذاب.\n"
                "💬 جاوب على أسئلتهم بطريقة ذكية.\n\n"
                "وفي نهاية التصويت قد تحصل على فرصة لتخمين كلمة الأبرياء."
            )

        else:
            word = base_word

            private_text = (
                "🤫 **كلمتك السرية**\n\n"
                f"🔐 كلمتك هي: **{word}**\n\n"
                "⚠️ لا ترسل الكلمة نفسها في القروب.\n"
                "💬 صف كلمتك وأجب على أسئلة اللاعبين بدون ذكرها مباشرة.\n\n"
                "🕵️ يوجد لاعب واحد حصل على كلمة مختلفة، "
                "وهو الكذاب."
            )

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=private_text,
                parse_mode="Markdown"
            )
        except Exception:
            pass

    # -----------------------------------------------------
    # رسالة بداية اللعبة
    # -----------------------------------------------------

    start_text = (
        "🕵️ **بدأت لعبة الكذاب!**\n\n"
        f"👥 عدد اللاعبين: **{len(player_ids)}**\n\n"

        "🔐 تم إرسال كلمة سرية لكل لاعب في الخاص.\n"

        "💬 **الآن تبدأ مرحلة النقاش!**\n\n"

        "يسأل اللاعبون بعضهم البعض عن كلماتهم، "
        "ويحاول كل لاعب معرفة من يملك الكلمة المختلفة.\n\n"

        "❓ مثال على الأسئلة:\n"
        "• هل الكلمة حقتك لها أكثر من لون؟\n"
        "• هل نستخدمها داخل البيت؟\n"

        "⚠️ **ممنوع ذكر الكلمة نفسها بشكل مباشر.**\n"
        "حاول توصفها بطريقة تساعد فريقك بدون ما تكشفها للكذاب.\n\n"

        "🚨 إذا أرسلت كلمتك السرية نفسها في القروب، "
        "سيتم استبعادك من الجولة وتحصل على **0 نقطة**.\n\n"

        "⏱️ وقت النقاش: **5 دقائق**\n\n"

        "🗳️ بعد انتهاء النقاش يبدأ التصويت تلقائيًا.\n"
        "👑 الأدمن يقدر ينهي النقاش ويبدأ التصويت مباشرة بـ `.التصويت`"
    )

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=start_text,
        parse_mode="Markdown"
    )

    # -----------------------------------------------------
    # مؤقت النقاش
    # -----------------------------------------------------

    game["discussion_task"] = context.application.create_task(
        discussion_timer(context, game),
        name=f"liar-discussion-timeout-{game['chat_id']}",
    )


# =========================================================
# مؤقت النقاش
# =========================================================

async def discussion_timer(context, game):

    try:
        await asyncio.sleep(DISCUSSION_TIME)
    except asyncio.CancelledError:
        return

    if game not in active_liar_games.values():
        return

    if game["phase"] != "discussion":
        return

    await start_voting(context, game)


# =========================================================
# التصويت يدويًا
# =========================================================

async def force_voting(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    game = active_liar_games.get(chat.id)

    if not game:
        return

    if game["phase"] != "discussion":
        return

    user = update.effective_user

    if await get_rank_level(user.id, chat.id) < 1:
        return

    if game["discussion_task"]:
        game["discussion_task"].cancel()
        game["discussion_task"] = None

    await start_voting(context, game)


# =========================================================
# إنشاء أزرار التصويت
# =========================================================

def build_vote_keyboard(game, voter_id):

    buttons = []

    for player_id, user in game["players"].items():

        if player_id == voter_id:
            continue

        if player_id in game["eliminated"]:
            continue

        buttons.append(
            InlineKeyboardButton(
                user.first_name or "مستخدم",
                callback_data=f"liar_vote:{player_id}"
            )
        )

    rows = []

    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i + 2])

    return InlineKeyboardMarkup(rows)


# =========================================================
# بدء التصويت
# =========================================================

async def start_voting(context, game):

    if game["phase"] != "discussion":
        return

    game["phase"] = "voting"
    game["voting_started"] = True
    game["votes"] = {}

    await context.bot.send_message(
        chat_id=game["chat_id"],
        text=(
            "🗳️ **بدأ التصويت!**\n\n"
            "اختر الشخص الذي تعتقد أنه الكذاب.\n\n"
            "⚠️ لا يمكنك التصويت لنفسك.\n"
            "🎯 التصويت الصحيح على الكذاب = **+40 نقطة**.\n\n"
            "⏱️ أمامكم **60 ثانية**."
        ),
        parse_mode="Markdown"
    )

    # إرسال التصويت بالخاص
    for player_id, user in game["players"].items():

        if player_id in game["eliminated"]:
            continue

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=(
                    "🗳️ **التصويت**\n\n"
                    "من تعتقد أنه الكذاب؟\n\n"
                    "⚠️ لديك تصويت واحد فقط."
                ),
                parse_mode="Markdown",
                reply_markup=build_vote_keyboard(game, player_id)
            )
        except Exception:
            pass

    game["vote_task"] = context.application.create_task(
        vote_timer(context, game),
        name=f"liar-vote-timeout-{game['chat_id']}",
    )


# =========================================================
# مؤقت التصويت
# =========================================================

async def vote_timer(context, game):

    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        return

    if game["phase"] != "voting":
        return

    await finish_voting(context, game)


# =========================================================
# التصويت
# =========================================================

async def liar_vote_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query:
        return

    user = query.from_user

    try:
        await query.answer()
    except Exception:
        pass

    if not query.data.startswith("liar_vote:"):
        return

    try:
        target_id = int(
            query.data.split(":", 1)[1]
        )
    except Exception:
        return

    game = None

    for current_game in active_liar_games.values():

        if (
            current_game["phase"] == "voting"
            and user.id in current_game["players"]
        ):
            game = current_game
            break

    if not game:
        await query.answer(
            "❌ انتهى التصويت.",
            show_alert=True
        )
        return

    voter_id = user.id

    if voter_id in game["votes"]:
        await query.answer(
            "⚠️ صوتك مسجل بالفعل.",
            show_alert=True
        )
        return

    if target_id == voter_id:
        await query.answer(
            "❌ لا يمكنك التصويت لنفسك.",
            show_alert=True
        )
        return

    if target_id not in game["players"]:
        return

    if target_id in game["eliminated"]:
        return

    game["votes"][voter_id] = target_id

    try:
        await query.edit_message_text(
            "✅ **تم تسجيل تصويتك.**\n\n"
            "لا يمكنك تغيير اختيارك.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    eligible = [
        player_id
        for player_id in game["players"]
        if player_id not in game["eliminated"]
    ]

    if len(game["votes"]) >= len(eligible):
        await finish_voting(context, game)


# =========================================================
# نهاية التصويت
# =========================================================

async def finish_voting(context, game):

    if game["phase"] != "voting":
        return

    game["phase"] = "guessing"

    liar_id = game["liar_id"]

    # هل تم التصويت على الكذاب؟
    caught = False

    for target_id in game["votes"].values():

        if target_id == liar_id:
            caught = True
            break

    game["liar_caught"] = caught

    # -----------------------------------------------------
    # نقاط التصويت
    # -----------------------------------------------------

    for voter_id, target_id in game["votes"].items():

        if target_id == liar_id:
            try:
                await add_points(
                    voter_id,
                    CORRECT_VOTE_POINTS
                )
            except Exception as e:
                print(
                    f"⚠️ خطأ في إضافة نقاط التصويت: {e}"
                )

    # -----------------------------------------------------
    # إرسال الكذاب إلى مرحلة التخمين
    # -----------------------------------------------------

    options = choose_guess_options(
        game["base_word"]
    )

    game["guess_options"] = options
    game["guess_selected"] = False

    try:
        await context.bot.send_message(
            chat_id=liar_id,
            text=(
                "🕵️ **مرحلة تخمين كلمة الأبرياء**\n\n"

                "انتهى التصويت.\n"
                "الآن لديك فرصة واحدة فقط لتخمين كلمة الأبرياء.\n\n"

                "🎯 اختر كلمة واحدة من القائمة.\n"
                "⚠️ لا يمكنك تغيير اختيارك بعد الضغط.\n"
                "⏱️ أمامك **30 ثانية**."
            ),
            parse_mode="Markdown",
            reply_markup=guess_keyboard(options)
        )

    except Exception:
        game["guess_result"] = False

        await finish_game(
            context,
            game
        )
        return

    game["guess_task"] = context.application.create_task(
        guess_timer(context, game),
        name=f"liar-guess-timeout-{game['chat_id']}",
    )


# =========================================================
# مؤقت التخمين
# =========================================================

async def guess_timer(context, game):

    try:
        await asyncio.sleep(GUESS_TIME)
    except asyncio.CancelledError:
        return

    if game["phase"] != "guessing":
        return

    if game["guess_selected"]:
        return

    game["guess_selected"] = True
    game["guess_result"] = False

    await context.bot.send_message(
        chat_id=game["liar_id"],
        text=(
            "⏰ **انتهى الوقت!**\n\n"
            "لم تختر أي كلمة.\n"
            "❌ تخمينك يعتبر خاطئًا.\n"
            "💰 النقاط: **0**"
        ),
        parse_mode="Markdown"
    )

    await finish_game(
        context,
        game
    )


# =========================================================
# اختيار تخمين الكذاب
# =========================================================

async def liar_guess_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query:
        return

    user = query.from_user

    if not query.data.startswith("liar_guess:"):
        return

    game = None

    for current_game in active_liar_games.values():

        if (
            current_game["phase"] == "guessing"
            and current_game["liar_id"] == user.id
        ):
            game = current_game
            break

    if not game:
        try:
            await query.answer(
                "❌ لا يوجد تخمين متاح.",
                show_alert=True
            )
        except Exception:
            pass

        return

    if game["guess_selected"]:

        try:
            await query.answer(
                "⚠️ تم تسجيل اختيارك بالفعل.",
                show_alert=True
            )
        except Exception:
            pass

        return

    selected_word = query.data.split(":", 1)[1]

    game["guess_selected"] = True

    correct_word = game["base_word"]

    correct = (
        normalize_text(selected_word)
        == normalize_text(correct_word)
    )

    game["guess_result"] = correct

    if game["guess_task"]:
        game["guess_task"].cancel()
        game["guess_task"] = None

    # -----------------------------------------------------
    # النقاط
    # -----------------------------------------------------

    points = 0

    if correct:

        if game["liar_caught"]:
            points = LIAR_CAUGHT_GUESS_POINTS
        else:
            points = LIAR_FREE_GUESS_POINTS

        try:
            await add_points(
                game["liar_id"],
                points
            )
        except Exception as e:
            print(
                f"⚠️ خطأ في إضافة نقاط الكذاب: {e}"
            )

    # -----------------------------------------------------
    # نتيجة خاصة للكذاب
    # -----------------------------------------------------

    if correct:

        result_text = (
            "🎯 **تخمين صحيح!**\n\n"
            f"✅ الكلمة كانت: **{correct_word}**\n"
            f"💰 حصلت على **+{points} نقطة**."
        )

    else:

        result_text = (
            "❌ **تخمين خاطئ!**\n\n"
            f"🔐 الكلمة الصحيحة كانت: **{correct_word}**\n"
            "💰 حصلت على **0 نقطة**."
        )

    try:
        await query.edit_message_text(
            result_text,
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await finish_game(
        context,
        game
    )


# =========================================================
# استقبال رسائل الكذاب
#
# 1 - كشف تسريب الكلمة
# 2 - تخمين الكذاب بالخاص
# =========================================================

async def check_liar_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    # -----------------------------------------------------
    # البحث عن لعبة اللاعب
    # -----------------------------------------------------

    game = None

    for current_game in active_liar_games.values():

        if user.id in current_game["players"]:
            game = current_game
            break

    if not game:
        return

    # -----------------------------------------------------
    # الكذاب يرسل تخمينه نصيًا بالخاص
    #
    # نترك الأزرار هي الطريقة الأساسية.
    # -----------------------------------------------------

    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and game["phase"] == "guessing"
        and user.id == game["liar_id"]
    ):
        # لا نعتبر النص تخمينًا حتى لا يستطيع تجاوز
        # نظام المحاولة الواحدة والأزرار.
        return

    # -----------------------------------------------------
    # كشف تسريب الكلمة
    # -----------------------------------------------------

    if not update.effective_chat:
        return

    if update.effective_chat.type not in (
        "group",
        "supergroup"
    ):
        return

    if game["phase"] != "discussion":
        return

    if user.id in game["eliminated"]:
        return

    text = update.message.text

    if not text:
        return

    normalized_message = normalize_text(text)

    secret_word = None

    if user.id == game["liar_id"]:
        secret_word = game["liar_word"]
    else:
        secret_word = game["base_word"]

    if normalize_text(secret_word) != normalized_message:
        return

    # -----------------------------------------------------
    # استبعاد اللاعب
    # -----------------------------------------------------

    game["eliminated"].add(user.id)

    await update.message.reply_text(
        f"🚨 تم استبعاد {mention_user(user)} من الجولة!\n\n"
        "❌ لقد أرسلت كلمتك السرية في القروب.\n"
        "💰 نقاطك في هذه الجولة: **0**.",
        parse_mode="Markdown"
    )


# =========================================================
# إنهاء اللعبة يدويًا
# =========================================================


async def end_liar_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user

    if not chat:
        return

    chat_id = chat.id

    # ==================================================
    # التأكد من وجود اللعبة
    # ==================================================

    game = active_liar_games.get(chat_id)

    if not game:

        await update.message.reply_text(
            "❌ لا توجد لعبة كذاب شغالة حاليًا."
        )

        return

    # ==================================================
    # الصلاحية
    # ==================================================

    if await get_rank_level(user.id, chat.id) < 1:

        await update.message.reply_text(
            "❌ هذا الأمر للمشرفين فقط."
        )

        return

    # ==================================================
    # إلغاء المهام المؤقتة
    # ==================================================

    tasks = [
        game.get("discussion_task"),
        game.get("vote_task"),
        game.get("guess_task"),
    ]

    for task in tasks:

        if task and not task.done():

            task.cancel()

    # ==================================================
    # إزالة اللعبة
    # ==================================================

    active_liar_games.pop(chat_id, None)

    # ==================================================
    # فك قفل الألعاب الكبيرة
    # ==================================================

    unlock_big_game(
        chat_id,
        "liar"
    )

    # ==================================================
    # رسالة الإنهاء
    # ==================================================

    await update.message.reply_text(
        "🛑 تم إنهاء لعبة الكذاب.\n\n"
    )
    



# =========================================================
# إنهاء اللعبة وإرسال النتائج
# =========================================================

async def finish_game(context, game):

    if game["chat_id"] not in active_liar_games:
        return

    if game["phase"] == "finished":
        return

    game["phase"] = "finished"

    chat_id = game["chat_id"]

    liar_id = game["liar_id"]

    liar = game["players"].get(liar_id)

    # -----------------------------------------------------
    # أسماء الكلمات
    # -----------------------------------------------------

    base_word = game["base_word"]
    liar_word = game["liar_word"]

    # -----------------------------------------------------
    # نتائج التصويت
    # -----------------------------------------------------

    votes_text = ""

    if game["votes"]:

        for voter_id, target_id in game["votes"].items():

            voter = game["players"].get(voter_id)
            target = game["players"].get(target_id)

            if not voter or not target:
                continue

            is_correct = target_id == liar_id

            mark = "✅" if is_correct else "❌"

            votes_text += (
                f"• {mention_user(voter)} "
                f"➡️ {mention_user(target)} {mark}\n"
            )

    else:
        votes_text = "• لم يصوت أحد.\n"

    # -----------------------------------------------------
    # نقاط الجولة
    #
    # النقاط الإضافية التي تم منحها بالفعل محفوظة هنا
    # فقط للعرض.
    # -----------------------------------------------------

    scores_text = ""

    for player_id, user in game["players"].items():

        # نعرض فقط النقاط التي اكتسبها في هذه الجولة
        score = 0

        # تصويت صحيح
        if game["votes"].get(player_id) == liar_id:
            score += CORRECT_VOTE_POINTS

        # تخمين الكذاب
        if player_id == liar_id and game["guess_result"]:
            if game["liar_caught"]:
                score += LIAR_CAUGHT_GUESS_POINTS
            else:
                score += LIAR_FREE_GUESS_POINTS

        if player_id in game["eliminated"]:
            score = 0

        scores_text += (
            f"• {mention_user(user)} — **+{score}**\n"
        )

    # -----------------------------------------------------
    # نتيجة تخمين الكذاب
    # -----------------------------------------------------

    if game["guess_result"] is True:

        if game["liar_caught"]:
            guess_points = LIAR_CAUGHT_GUESS_POINTS
        else:
            guess_points = LIAR_FREE_GUESS_POINTS

        guess_text = (
            f"🎯 **تخمين الكذاب:** صحيح ✅\n"
            f"💰 حصل على **+{guess_points} نقطة**."
        )

    elif game["guess_result"] is False:

        guess_text = (
            "🎯 **تخمين الكذاب:** خاطئ ❌\n"
            "💰 حصل على **0 نقطة**."
        )

    else:

        guess_text = (
            "🎯 **تخمين الكذاب:** لم يتم الاختيار ⏰\n"
            "💰 حصل على **0 نقطة**."
        )

    # -----------------------------------------------------
    # الفائزون
    #
    # الفائزون هنا هم أصحاب التصويت الصحيح.
    # وإذا كان الكذاب نجح في التخمين، نضيفه للفائزين.
    # -----------------------------------------------------

    winners = []
    winner_ids = []

    for player_id, user in game["players"].items():

        score = 0

        if game["votes"].get(player_id) == liar_id:
            score += CORRECT_VOTE_POINTS

        if player_id == liar_id and game["guess_result"]:
            if game["liar_caught"]:
                score += LIAR_CAUGHT_GUESS_POINTS
            else:
                score += LIAR_FREE_GUESS_POINTS

        if player_id in game["eliminated"]:
            score = 0

        if score > 0:
            winner_ids.append(int(player_id))
            winners.append(
                mention_user(user)
            )

    winners_text = (
        "\n".join(
            f"🏆 {winner}"
            for winner in winners
        )
        if winners
        else "لا يوجد فائز بالنقاط في هذه الجولة."
    )

    # -----------------------------------------------------
    # هل انكشف الكذاب؟
    # -----------------------------------------------------

    if game["liar_caught"]:
        caught_text = "🚨 **تم كشف الكذاب!**"
    else:
        caught_text = "😈 **الكذاب لم يتم كشفه!**"

    # -----------------------------------------------------
    # النتيجة النهائية
    # -----------------------------------------------------

    result_text = (
        "🏆 **نتائج لعبة الكذاب**\n\n"

        f"📝 **كلمة الأبرياء:** {base_word}\n"
        f"🕵️ **كلمة الكذاب:** {liar_word}\n"
        f"👤 **الكذاب:** "
        f"{mention_user(liar) if liar else 'غير معروف'}\n\n"

        f"{caught_text}\n\n"

        "🗳️ **نتائج التصويت:**\n"
        f"{votes_text}\n"

        "🎯 **مرحلة تخمين الكذاب:**\n"
        f"{guess_text}\n\n"

        "💰 **نقاط الجولة:**\n"
        f"{scores_text}\n"

        "🏅 **الفائزون:**\n"
        f"{winners_text}"
    )

    try:
        from database.game_stats import record_game_results
        winner_id_set = set(winner_ids)
        winner_rows = [{"id": int(pid), "name": user.get("name", "لاعب")}
                       for pid, user in game["players"].items() if int(pid) in winner_id_set]
        loser_rows = [{"id": int(pid), "name": user.get("name", "لاعب")}
                      for pid, user in game["players"].items() if int(pid) not in winner_id_set]
        await record_game_results(
            f"liar:{game.get('game_id') or chat_id}:{game.get('started_at') or id(game)}",
            "liar", winner_rows, loser_rows,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to record liar results")

    await context.bot.send_message(
        chat_id=chat_id,
        text=result_text,
        parse_mode="Markdown"
    )

    # -----------------------------------------------------
    # تنظيف اللعبة
    # -----------------------------------------------------

    if game.get("discussion_task"):
        try:
            game["discussion_task"].cancel()
        except Exception:
            pass

    for task_key in ("discussion_task", "vote_task", "guess_task"):
        task = game.get(task_key)
        if task and not task.done():
            task.cancel()
        game[task_key] = None

    active_liar_games.pop(chat_id, None)


    unlock_big_game(
        chat_id,
        "liar"
    )


# =========================================================
# Callback أزرار دخول / خروج
# =========================================================

async def liar_lobby_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query:
        return

    user = query.from_user

    data = query.data

    # -----------------------------------------------------
    # العثور على اللعبة
    # -----------------------------------------------------

    game = None

    for current_game in active_liar_games.values():

        if (
            current_game["lobby_message_id"]
            == query.message.message_id
        ):
            game = current_game
            break

    if not game:
        try:
            await query.answer(
                "❌ انتهت اللعبة.",
                show_alert=True
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # اللعبة بدأت
    # -----------------------------------------------------

    if game["started"]:

        try:
            await query.answer(
                "⚠️ اللعبة بدأت بالفعل.",
                show_alert=True
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # دخول
    # -----------------------------------------------------

    if data == "liar:join":

        if user.id in game["players"]:

            try:
                await query.answer(
                    "⚠️ أنت داخل اللعبة بالفعل.",
                    show_alert=True
                )
            except Exception:
                pass

            return

        game["players"][user.id] = user

        try:
            await query.answer(
                "✅ تم انضمامك!"
            )
        except Exception:
            pass

        await update_lobby(
            context,
            game
        )

        return

    # -----------------------------------------------------
    # خروج
    # -----------------------------------------------------

    if data == "liar:leave":

        if user.id not in game["players"]:

            try:
                await query.answer(
                    "❌ أنت لست داخل اللعبة.",
                    show_alert=True
                )
            except Exception:
                pass

            return

        del game["players"][user.id]

        try:
            await query.answer(
                "🚪 تم خروجك من اللعبة."
            )
        except Exception:
            pass

        await update_lobby(
            context,
            game
        )
