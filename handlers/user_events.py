from telegram import Update
from telegram.ext import ChatMemberHandler, ContextTypes

from database.users import register_joined_member, update_member_status
from handlers.cache import set_cached_user


async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    event = update.chat_member
    if event is None:
        return

    chat = event.chat
    member = event.new_chat_member
    user = member.user
    status = member.status

    if status in ("member", "administrator"):
        await register_joined_member(
            chat_id=chat.id,
            chat_type=chat.type,
            chat_title=chat.title,
            chat_username=chat.username,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            is_bot=user.is_bot,
        )
        # The event confirms membership; cache only a known default profile here.
        # A later profile read fetches counters and points from PostgreSQL.
        cached = {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name or "",
            "last_name": user.last_name,
            "messages": 0,
            "rank": "عضو",
            "joined_date": "غير معروف",
            "points": 0,
        }
        set_cached_user(user.id, cached)
    elif status in ("left", "kicked"):
        await update_member_status(chat.id, user.id, status)
