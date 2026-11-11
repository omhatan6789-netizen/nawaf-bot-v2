"""Shared Telegram user lookup by reply, numeric ID, or username."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from database.moderation import get_user_by_id, get_user_by_username, save_target_user

logger = logging.getLogger(__name__)


async def lookup_user(context, value: str | int | None) -> Any | None:
    """Resolve a Telegram user from the database, Bot API, or music Pyrogram session."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    is_id = raw.isdigit()
    username = raw.lstrip("@") if not is_id else None
    if not is_id and not raw.startswith("@"):
        return None

    saved_username = None
    try:
        row = await (get_user_by_id(int(raw)) if is_id else get_user_by_username(username))
        if row:
            saved_username = row["username"]
            saved_name = (row["first_name"] or "").strip()
            # Older versions could save the numeric ID as first_name.
            # Do not treat that placeholder as a real profile; refresh via Telegram.
            if saved_name and saved_name != str(row["user_id"]):
                return SimpleNamespace(
                    id=int(row["user_id"]),
                    username=row["username"],
                    first_name=saved_name,
                    is_bot=False,
                )
    except Exception:
        logger.debug("Database user lookup failed for %s", raw, exc_info=True)

    try:
        user = await context.bot.get_chat(int(raw) if is_id else "@" + username)
        if user:
            await save_target_user(user)
            return user
    except Exception:
        pass

    try:
        from music_call import get_music_client

        music_client = get_music_client()
        if music_client is not None:
            user = await music_client.get_users(
                saved_username if is_id and saved_username else (int(raw) if is_id else username)
            )
            if user:
                await save_target_user(user)
                return user
    except Exception:
        logger.debug("Music account lookup failed for %s", raw, exc_info=True)

    # Telegram cannot always resolve an unseen account from its numeric ID.
    # The ID is still sufficient for database-backed actions and Bot API
    # moderation methods, so preserve it as a minimal target object.
    if is_id and int(raw) > 0:
        return SimpleNamespace(
            id=int(raw),
            username=None,
            first_name=raw,
            last_name=None,
            is_bot=False,
        )
    return None


async def resolve_message_user(update, context, *, token_index: int = 1):
    message = update.effective_message
    if not message:
        return None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        try:
            await save_target_user(user)
        except Exception:
            logger.debug("Could not save replied user", exc_info=True)
        return user

    parts = (message.text or "").strip().split()
    for token in parts[token_index:]:
        if token.isdigit() or token.startswith("@"):
            user = await lookup_user(context, token)
            if user:
                return user
    return None
