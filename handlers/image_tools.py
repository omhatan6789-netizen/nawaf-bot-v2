from html import escape

from telegram import Update
from telegram.ext import ContextTypes

OWNER_ID = 8453977662


async def owner_photo_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to the owner with the Telegram file_id of a private photo."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or chat.type != "private" or user.id != OWNER_ID:
        return
    if not message.photo:
        return

    photo = message.photo[-1]
    await message.reply_text(
        "🖼️ معرّف الصورة (file_id):\n\n"
        f"<code>{escape(photo.file_id)}</code>\n\n"
        "اضغط على المعرّف لنسخه.\n"
        "لاستعراضها لاحقًا، اكتب: اعرض الصورة ثم أرسل المعرّف.",
        parse_mode="HTML",
    )


async def owner_show_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner can request a preview by sending 'اعرض الصورة' then a file_id."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or chat.type != "private" or user.id != OWNER_ID:
        return

    text = (message.text or "").strip()
    if text == "اعرض الصورة":
        context.user_data["awaiting_owner_image_file_id"] = True
        await message.reply_text("أرسل الآن معرّف الصورة (file_id).")
        return

    if not context.user_data.get("awaiting_owner_image_file_id"):
        return

    context.user_data.pop("awaiting_owner_image_file_id", None)
    file_id = text.strip()
    if not file_id or len(file_id) > 2048 or any(ch.isspace() for ch in file_id):
        await message.reply_text("❌ المعرّف غير صالح. اكتب «اعرض الصورة» وحاول مرة ثانية.")
        return

    try:
        await context.bot.send_photo(
            chat_id=chat.id,
            photo=file_id,
            caption="✅ هذه هي الصورة المرتبطة بهذا المعرّف.",
        )
    except Exception as exc:
        await message.reply_text(
            "❌ ما قدرت أرسل الصورة بهذا المعرّف. تأكد أنه كامل وصحيح، "
            "وأن الصورة مرفوعة من نفس البوت.\n"
            f"التفاصيل: {type(exc).__name__}"
        )
