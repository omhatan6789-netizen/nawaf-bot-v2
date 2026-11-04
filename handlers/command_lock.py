from telegram import Update
from telegram.ext import ContextTypes

from database.roles import get_rank_level, set_command_lock, remove_command_lock, RANK_LEVELS

RANKS = ["Dev", "المالك", "نائب المالك", "ادمن اساسي", "ادمن", "مميز"]


async def _is_owner_or_above(user_id: int, chat_id: int) -> bool:
    try:
        return await get_rank_level(user_id, chat_id) >= 5
    except Exception:
        return False


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    if not await _is_owner_or_above(user.id, chat.id):
        await message.reply_text("• اعذرني بس هذا الامر للمالك وفوق فقط .")
        return
    command = (message.text or "").replace("قفل امر ", "", 1).strip()
    if not command:
        await message.reply_text("❌ اكتب اسم الأمر\nمثال:\nقفل امر اضف رد")
        return
    context.user_data["lock_command"] = command
    await message.reply_text(
        "• حسنًا اختر الرتبة التي تريدها :\n"
        f"1 - `{RANKS[0]}`\n"
        f"2 - `{RANKS[1]}`\n"
        f"3 - `{RANKS[2]}`\n"
        f"4 - `{RANKS[3]}`\n"
        f"5 - `{RANKS[4]}`\n"
        f"6 - `{RANKS[5]}`\n\n\n"
        f"- سيتم وضع امر ↤︎ {command} له فقط",
        parse_mode="Markdown",
    )


async def save_lock_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or "lock_command" not in context.user_data:
        return
    rank = (message.text or "").strip()
    if rank not in RANKS:
        return
    command = context.user_data.get("lock_command")
    if not command:
        return
    try:
        await set_command_lock(command, rank)
    except Exception:
        return
    context.user_data.pop("lock_command", None)
    await message.reply_text(f"✅ تم قفل الأمر {command} على رتبة {rank} وفوق")


async def open_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    if not await _is_owner_or_above(user.id, chat.id):
        await message.reply_text("• اعذرني بس هذا الامر للمالك وفوق فقط .")
        return
    command = (message.text or "").replace("فتح امر ", "", 1).strip()
    if not command:
        return
    try:
        await remove_command_lock(command)
    except Exception:
        return
    await message.reply_text(f"✅ تم فتح الأمر {command}")
