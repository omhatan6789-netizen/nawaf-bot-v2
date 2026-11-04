from telegram import Update
from telegram.ext import ContextTypes

from database.activity import record_group_text_message


async def save_group_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or chat is None or user is None:
        return
    if chat.type not in ("group", "supergroup") or user.is_bot:
        return
    if not message.text or message.text.startswith("/"):
        return

    record_group_text_message(
        chat_id=chat.id,
        chat_type=chat.type,
        chat_title=chat.title,
        chat_username=chat.username,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
