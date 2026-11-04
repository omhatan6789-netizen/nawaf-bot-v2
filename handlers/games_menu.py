from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop

from games.liar import start_liar_game_lobby
from games.penalties import start_penalty_game
from games.hide_and_seek import start_hide_game


# =========================================================
# الألعاب الموجودة في القائمة
# لإضافة لعبة جديدة لاحقًا أضف سطر هنا فقط
# =========================================================

GAMES_MENU = {
    "liar": {
        "name": "الكذاب",
        "handler": start_liar_game_lobby,
    },
    "penalty": {
        "name": "بلنتيات",
        "handler": start_penalty_game,
    },
    "hide": {
        "name": "غميضة",
        "handler": start_hide_game,
    },
}


# =========================================================
# .لعبة
# =========================================================

async def games_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    keyboard = []
    row = []

    for game_id, game in GAMES_MENU.items():

        row.append(
            InlineKeyboardButton(
                game["name"],
                callback_data=f"game_menu:{game_id}"
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "<b>اختر اللعبة الي تبيها 👇🏻 .</b>",
        parse_mode="HTML",
        reply_markup=markup
    )

    raise ApplicationHandlerStop


# =========================================================
# تشغيل اللعبة من الزر
# =========================================================

async def games_menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    if not data.startswith("game_menu:"):
        return

    game_id = data.split(":", 1)[1]

    game = GAMES_MENU.get(game_id)

    if not game:
        await query.answer("اللعبة غير موجودة", show_alert=True)
        return

    # ==========================================
    # 1 - تغيير القائمة إلى جاري تحميل اللعبة
    # ==========================================

    await query.edit_message_text(
        "<b>جاري تحميل اللعبة… 🎮</b>",
        parse_mode="HTML"
    )

    # ==========================================
    # 2 - إنشاء رسالة مستقلة وهمية
    # ==========================================

    original_data = update.to_dict()

    callback_data = original_data.get("callback_query", {})
    callback_message = callback_data.get("message")
    user_data = callback_data.get("from")

    if not callback_message:
        return

    # ننسخ بيانات الرسالة
    fake_message = dict(callback_message)

    # صاحب الرسالة = الشخص الذي ضغط الزر
    if user_data:
        fake_message["from"] = user_data

    # اسم اللعبة كأنه الأمر الذي كتبه المستخدم
    fake_message["text"] = game["name"]

    # ==========================================
    # مهم جدًا:
    # إزالة أي Reply من الرسالة الوهمية
    # ==========================================

    fake_message.pop("reply_to_message", None)
    fake_message.pop("reply_to", None)

    # إزالة الكيبورد
    fake_message.pop("reply_markup", None)

    # ==========================================
    # إنشاء Update مستقل
    # ==========================================

    fake_update_data = {
        "update_id": original_data.get("update_id", 0) + 1,
        "message": fake_message,
    }

    fake_update = Update.de_json(
        fake_update_data,
        context.bot
    )

    # ==========================================
    # 3 - تشغيل اللعبة الأصلية
    # ==========================================

    await game["handler"](fake_update, context)
