from telegram import Update
from telegram.ext import ContextTypes

from database.activity import record_group_text_message
from handlers.cache import increment_cached_messages


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

    increment_cached_messages(
        user_id=user.id,
        amount=1,
        username=user.username,
        first_name=user.first_name,
    )

    record_group_text_message(
        chat_id=chat.id,
        chat_type=chat.type,
        chat_title=chat.title,
        chat_username=chat.username,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )



async def track_observed_group_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember users who actually send messages in groups, even when member lists are hidden."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return
    if chat.type not in ("group", "supergroup") or user.is_bot:
        return

    try:
        from database.pool import get_pool
        await get_pool().execute(
            """INSERT INTO telegram_seen_users
               (user_id, username, first_name, last_name, seen_in_chat_id,
                seen_in_chat_title, observed_count, last_seen_at)
               VALUES($1, $2, $3, $4, $5, $6, 1, NOW())
               ON CONFLICT(user_id) DO UPDATE SET
                   username=EXCLUDED.username,
                   first_name=EXCLUDED.first_name,
                   last_name=EXCLUDED.last_name,
                   seen_in_chat_id=EXCLUDED.seen_in_chat_id,
                   seen_in_chat_title=EXCLUDED.seen_in_chat_title,
                   observed_count=telegram_seen_users.observed_count + 1,
                   last_seen_at=NOW()""",
            int(user.id), user.username, user.first_name or "",
            user.last_name or "", int(chat.id), chat.title or "",
        )
    except Exception:
        # Profile caching must never interrupt normal group message handling.
        import logging
        logging.getLogger(__name__).debug(
            "Could not cache observed Telegram user %s", user.id, exc_info=True
        )
