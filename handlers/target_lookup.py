"""Resolve target users exclusively through the assistant's Pyrogram session."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from database.moderation import get_user_by_id, get_user_by_username, save_target_user

logger = logging.getLogger(__name__)


def _music_client():
    try:
        from music_call import get_music_client
        return get_music_client()
    except Exception:
        logger.exception("Could not access the assistant Pyrogram client")
        return None


async def lookup_user(context, value: str | int | None) -> Any | None:
    """Resolve usernames through Pyrogram; preserve the legacy lookup path for numeric IDs."""
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

    # For usernames, use the local user cache first; Pyrogram is the fallback.
    if not is_id:
        username = raw.lstrip("@")
        try:
            row = await get_user_by_username(username)
            if row:
                saved_name = (row["first_name"] or "").strip()
                if saved_name and saved_name != str(row["user_id"]):
                    return SimpleNamespace(
                        id=int(row["user_id"]),
                        username=row["username"] or username,
                        first_name=saved_name,
                        last_name=row["last_name"],
                        is_bot=False,
                    )
        except Exception:
            logger.debug("Database username lookup failed for %s", raw, exc_info=True)

        client = _music_client()
        if client is not None:
            try:
                user = await client.get_users(username)
                if user:
                    try:
                        await save_target_user(user)
                    except Exception:
                        logger.debug("Could not cache Pyrogram user %s", raw, exc_info=True)
                    return user
            except Exception:
                logger.debug("Pyrogram username lookup failed for %s", raw, exc_info=True)
        return None

    user_id = int(raw)
    saved_username = None

    # Numeric IDs use the previous working path: database -> Bot API -> Pyrogram.
    try:
        row = await get_user_by_id(user_id)
        if row:
            saved_username = row["username"]
            saved_name = (row["first_name"] or "").strip()
            if saved_name and saved_name != str(user_id):
                return SimpleNamespace(
                    id=user_id,
                    username=saved_username,
                    first_name=saved_name,
                    last_name=None,
                    is_bot=False,
                )
    except Exception:
        logger.debug("Database ID lookup failed for %s", raw, exc_info=True)

    try:
        user = await context.bot.get_chat(user_id)
        if user:
            try:
                await save_target_user(user)
            except Exception:
                logger.debug("Could not cache Bot API user %s", user_id, exc_info=True)
            return user
    except Exception:
        logger.debug("Bot API ID lookup failed for %s", raw, exc_info=True)

    client = _music_client()
    if client is not None:
        try:
            user = await client.get_users(saved_username or user_id)
            if user:
                try:
                    await save_target_user(user)
                except Exception:
                    logger.debug("Could not cache Pyrogram user %s", user_id, exc_info=True)
                return user
        except Exception:
            logger.debug("Pyrogram ID lookup failed for %s", raw, exc_info=True)

    # A numeric ID remains a valid target for ID-based moderation actions.
    return SimpleNamespace(
        id=user_id,
        username=saved_username,
        first_name=raw,
        last_name=None,
        is_bot=False,
    )


async def lookup_replied_user(message) -> Any | None:
    """Resolve the replied-to user through the assistant's Pyrogram session."""
    replied = getattr(message, "reply_to_message", None)
    replied_user = getattr(replied, "from_user", None)
    if replied_user is None:
        return None

    client = _music_client()
    if client is not None:
        try:
            user = await client.get_users(int(replied_user.id))
            if user:
                try:
                    await save_target_user(user)
                except Exception:
                    logger.debug("Could not cache replied user %s", replied_user.id, exc_info=True)
                return user
        except Exception:
            logger.debug(
                "Pyrogram lookup failed for replied user %s",
                getattr(replied_user, "id", None),
                exc_info=True,
            )

    # Telegram already supplied a valid User object with the replied message.
    # Keep the personal-account reveal working even if the assistant session
    # cannot independently resolve that account.
    try:
        await save_target_user(replied_user)
    except Exception:
        logger.debug("Could not cache Telegram replied user %s", replied_user.id, exc_info=True)
    return replied_user


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
