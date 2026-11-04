
from telegram import Update
from telegram.ext import ContextTypes

OWNER_ID = 8453977662
from telegram.ext import ConversationHandler

WAIT_PHOTO_ID = 999


async def get_photo_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.effective_user:
        return

    if update.effective_user.id != OWNER_ID:
        return

    if not update.message or not update.message.photo:
        return

    photo = update.message.photo[-1]

    await update.message.reply_text(
        f"🆔 ID الصورة:\n\n`{photo.file_id}`",
        parse_mode="Markdown"
    )


async def show_photo_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "• أرسل ID الصورة"
    )

    return WAIT_PHOTO_ID


async def show_photo_by_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.message or not update.message.text:
        return WAIT_PHOTO_ID

    photo_id = update.message.text.strip()

    try:
        await update.message.reply_photo(
            photo=photo_id
        )

        return ConversationHandler.END

    except Exception:
        await update.message.reply_text(
            "• الـID غير صحيح أو الصورة غير متاحة."
        )

        return WAIT_PHOTO_ID
