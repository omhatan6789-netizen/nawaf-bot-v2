"""Resolve target users exclusively through the assistant's Pyrogram session."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _music_client():
    try:
        from music_call import get_music_client
        return get_music_client()
    except Exception:
        logger.exception("Could not access the assistant Pyrogram client")
        return None


async def lookup_user(context, value: str | int | None) -> Any | None:
    """Resolve a username or numeric Telegram ID using Pyrogram only."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    is_id = raw.isdigit()
    if not is_id and not raw.startswith("@"):
        return None
    if is_id and int(raw) <= 0:
        return None

    client = _music_client()
    if client is None:
        return None

    target = int(raw) if is_id else raw.lstrip("@")
    try:
        return await client.get_users(target)
    except Exception:
        logger.debug("Pyrogram user lookup failed for %s", raw, exc_info=True)
        return None


async def lookup_replied_user(message) -> Any | None:
    """Resolve the replied-to user through the assistant's Pyrogram session."""
    replied = getattr(message, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None)
    if replied_user is None:
        return None

    client = _music_client()
    if client is None:
        return None

    try:
        return await client.get_users(int(replied_user.id))
    except Exception:
        logger.debug(
            "Pyrogram lookup failed for replied user %s",
            getattr(replied_user, "id", None),
            exc_info=True,
        )
        return None


async def resolve_message_user(update, context, *, token_index: int = 1):
    message = update.effective_message
    if not message:
        return None

    if message.reply_to_message and message.reply_to_message.from_user:
        return await lookup_replied_user(message)

    parts = (message.text or "").strip().split()
    for token in parts[token_index:]:
        if token.isdigit() or token.startswith("@"):
            user = await lookup_user(context, token)
            if user:
                return user
    return None
