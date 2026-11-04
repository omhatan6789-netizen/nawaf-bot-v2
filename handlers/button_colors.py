from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes
from button_colors import COLOR_STYLES, button_exists, normalize_button_name, set_button_color
from database.roles import get_rank_level, is_primary_developer, is_secondary_developer

color_sessions = {}


async def _can_change_button_color(user_id, chat_id):
    if await get_rank_level(user_id, chat_id) >= 5:
        return True
    return await is_primary_developer(user_id) or await is_secondary_developer(user_id)


async def change_button_color_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type not in ("group", "supergroup"):
        return
    if not await _can_change_button_color(user.id, chat.id):
        return
    color_sessions[chat.id] = {"user_id": user.id, "step": "button"}
    await message.reply_text("• طيب ياحلو ارسل اسم الزر الي تبي تغير لونه،")
    raise ApplicationHandlerStop


async def change_button_color_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user or chat.type not in ("group", "supergroup"):
        return
    session = color_sessions.get(chat.id)
    if not session or session["user_id"] != user.id:
        return
    text = message.text
    if not text:
        return
    if session["step"] == "button":
        button_name = normalize_button_name(text)
        if not button_exists(button_name):
            await message.reply_text("• مضيع يالحبيب، تاكد من اسم الزر.")
            color_sessions.pop(chat.id, None)
            raise ApplicationHandlerStop
        session["button"] = button_name
        session["step"] = "color"
        await message.reply_text(
            "• اوكيه، ارسل اللون الي تبيه.\n"
            "ملاحظة: عندك ( احمر، ازرق، اخضر، شفاف، فقط! )"
        )
        raise ApplicationHandlerStop
    if session["step"] == "color":
        color = text.strip()
        if color not in COLOR_STYLES:
            await message.reply_text("• قلت لك بس فيه احمر وازرق واخضر وشفاف!!")
            raise ApplicationHandlerStop
        if not await set_button_color(session["button"], color):
            await message.reply_text("• مضيع يالحبيب، تاكد من اسم الزر.")
            color_sessions.pop(chat.id, None)
            raise ApplicationHandlerStop
        color_sessions.pop(chat.id, None)
        await message.reply_text("• تم عدلت لونه ياحلو يمديك تتاكد الحين!")
        raise ApplicationHandlerStop
