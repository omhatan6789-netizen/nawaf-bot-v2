"""Natural-language self profile requests prefixed with نيوف."""
from __future__ import annotations

import logging
import re
import unicodedata

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database.roles import get_rank_level
from database.pool import get_pool

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", text)
    text = text.lower()
    # Collapse repeated letters so forms like افتارييي / نيووووف are recognized.
    text = re.sub(r"([^\W\d_])\1+", r"\1", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _detect_request(raw: str):
    normalized = _normalize(raw)
    words = normalized.split()
    if not words or not words[0].startswith("نيوف"):
        return None

    rest = " ".join(words[1:])
    if not rest:
        return None

    if any(word in rest for word in ("افتار", "افتر", "صورتي", "صور حسابي", "صوري")):
        match = re.search(r"(?<!\d)(\d+)(?!\d)", rest)
        index = max(1, int(match.group(1))) if match else 1
        return ("avatar", index)

    if any(word in rest for word in ("بايو", "نبذه", "نبذة", "وصف حسابي")):
        return ("bio", None)

    if any(word in rest for word in ("يوزر", "يوزري", "يوزرات", "معرفي", "معرفاتي", "username")):
        return ("usernames", None)

    if any(word in rest for word in ("اسمي", "اسم حسابي", "اسمك")):
        return ("name", None)

    return None


def _music_client():
    try:
        from music_call import get_music_client
        return get_music_client()
    except Exception:
        logger.exception("Could not access profile Pyrogram client")
        return None


async def _get_music_user(user_id: int):
    client = _music_client()
    if client is None:
        return None, None
    try:
        user = await client.get_users(int(user_id))
    except Exception:
        logger.debug("Could not fetch profile user %s", user_id, exc_info=True)
        user = None
    try:
        chat = await client.get_chat(int(user_id))
    except Exception:
        logger.debug("Could not fetch profile chat %s", user_id, exc_info=True)
        chat = None
    return user, chat


def _display_name(user, fallback) -> str:
    first = getattr(user, "first_name", None) or getattr(fallback, "first_name", None) or ""
    last = getattr(user, "last_name", None) or getattr(fallback, "last_name", None) or ""
    return " ".join(part.strip() for part in (first, last) if part and part.strip()) or "غير معروف"


async def newf_profile_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor or not chat or not message.text:
        return

    normalized_message = _normalize(message.text)

    # Lookup any Telegram account by numeric ID using the music account session.
    account_match = re.fullmatch(r"(?:حسابه|حساب)\s+(\d+)", normalized_message)
    if account_match:
        target_id = int(account_match.group(1))
        try:
            # First search people whose messages the bot has actually received.
            # This works even when the group's member list is hidden.
            seen = await get_pool().fetchrow(
                """SELECT username, first_name, last_name
                   FROM telegram_seen_users WHERE user_id=$1""",
                target_id,
            )
            music_user = music_chat = None
            if seen:
                display_name = " ".join(
                    part.strip() for part in
                    (seen["first_name"] or "", seen["last_name"] or "")
                    if part and part.strip()
                ) or "غير معروف"
                username = seen["username"]
            else:
                # Fall back to the Pyrogram session for accounts it already knows.
                music_user, music_chat = await _get_music_user(target_id)
                target = music_user or music_chat
                if target is None:
                    await message.reply_text("ما قدرت أوصل للحساب بهذا الايدي.")
                    raise ApplicationHandlerStop
                display_name = _display_name(target, None)
                usernames = getattr(target, "usernames", None) or []
                username = getattr(target, "username", None)
                if not username:
                    for item in usernames:
                        username = getattr(item, "username", None) or (item if isinstance(item, str) else None)
                        if username:
                            break
            profile_url = f"https://t.me/{str(username).lstrip('@')}" if username else f"tg://user?id={target_id}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(display_name, url=profile_url)
            ]])
            await message.reply_text("حسابه:", reply_markup=keyboard)
        except ApplicationHandlerStop:
            raise
        except Exception:
            logger.exception("Could not look up Telegram account %s", target_id)
            await message.reply_text("تعذر جلب الحساب حاليًا.")
        raise ApplicationHandlerStop

    words = normalized_message.split()
    if not words or not words[0].startswith("نيوف"):
        return

    request = _detect_request(message.text)
    if not request:
        # Not a profile request: let the general AI handler answer it.
        return

    kind, value = request
    if kind != "name":
        try:
            level = await get_rank_level(actor.id, chat.id)
        except Exception:
            logger.exception("Could not check rank for profile request")
            raise ApplicationHandlerStop
        # Restricted profile details are only available to ادمن and higher.
        if level < 2:
            raise ApplicationHandlerStop

    # The display name is already present in the Telegram update. Do not
    # depend on the separate Pyrogram music session for this simple request.
    if kind == "name":
        display_name = _display_name(None, actor)
        await message.reply_text(f"اسمك > {display_name}")
        raise ApplicationHandlerStop

    music_user, music_chat = await _get_music_user(actor.id)
    display_name = _display_name(music_user or music_chat, actor)

    if kind == "avatar":
        photo_index = int(value or 1)
        try:
            photos = await context.bot.get_user_profile_photos(
                user_id=actor.id, offset=photo_index - 1, limit=1
            )
            if not photos.photos:
                await message.reply_text("ماعندك يالطيب.")
                raise ApplicationHandlerStop
            photo_id = photos.photos[0][-1].file_id
            username = getattr(music_user, "username", None) or getattr(music_chat, "username", None) or actor.username
            button_url = f"https://t.me/{username}" if username else f"tg://user?id={actor.id}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(display_name, url=button_url)
            ]])
            await message.reply_photo(
                photo=photo_id,
                caption=f"افتارك رقم {photo_index}",
                reply_markup=keyboard,
            )
        except ApplicationHandlerStop:
            raise
        except Exception:
            logger.exception("Could not send profile photo for %s", actor.id)
            await message.reply_text("تعذر جلب افتارك حاليًا.")
        raise ApplicationHandlerStop

    if kind == "bio":
        bio = getattr(music_chat, "bio", None) or getattr(music_user, "bio", None)
        await message.reply_text(str(bio).strip() if bio and str(bio).strip() else "ما عندك بايو.")
        raise ApplicationHandlerStop

    if kind == "usernames":
        values = []
        raw_usernames = (getattr(music_user, "usernames", None) or getattr(music_chat, "usernames", None) or [])
        for item in raw_usernames:
            name = getattr(item, "username", None) or (item if isinstance(item, str) else None)
            if name:
                values.append(str(name).lstrip("@"))
        primary = getattr(music_user, "username", None) or getattr(music_chat, "username", None) or actor.username
        if primary:
            values.insert(0, str(primary).lstrip("@"))
        unique, seen = [], set()
        for name in values:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                unique.append("@" + name)
        await message.reply_text(" ، ".join(unique) if unique else "ماعندك يوزر.")
        raise ApplicationHandlerStop
