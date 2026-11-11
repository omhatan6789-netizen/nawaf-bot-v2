"""Async repetition protection. Message windows stay in memory; settings/warnings use asyncpg."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from database.repetition import get_repetition_settings, update_repetition_setting
from database.moderation import (
    add_warning, get_warning_count, clear_warnings, save_sanction,
    get_user_by_id, get_user_by_username,
)
from database.roles import get_rank_level, is_primary_developer
from handlers.target_lookup import lookup_user

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
DEFAULT_LIMIT = 3
DEFAULT_SECONDS = 5
DEFAULT_PUNISHMENT_DURATION = 300
MAX_MESSAGES_MEMORY = 50
RANK_LEVELS = {
    "عضو": 0, "مميز": 1, "ادمن": 2, "ادمن اساسي": 3,
    "نائب المالك": 4, "المالك": 5, "Dev": 6,
}
DURATION_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(ث|ثانية|ثواني|د|دقيقة|دقائق|س|ساعة|ساعات|ي|يوم|أيام)\s*$"
)
repetition_sessions: dict[tuple[int, int], dict[str, Any]] = {}
_repetition_messages = defaultdict(lambda: defaultdict(lambda: deque(maxlen=MAX_MESSAGES_MEMORY)))


def parse_duration_token(token: str) -> int | None:
    match = DURATION_PATTERN.match(str(token or ""))
    if not match:
        return None
    amount = float(match.group(1))
    if amount < 1:
        return None
    unit = match.group(2)
    multiplier = 1 if unit in ("ث", "ثانية", "ثواني") else (
        60 if unit in ("د", "دقيقة", "دقائق") else (
            3600 if unit in ("س", "ساعة", "ساعات") else 86400
        )
    )
    seconds = int(amount * multiplier)
    return seconds if seconds > 0 else None


def format_duration(seconds: int) -> str:
    seconds = int(seconds)
    if seconds % 86400 == 0:
        return f"{seconds // 86400} يوم"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ساعة"
    if seconds % 60 == 0:
        return f"{seconds // 60} دقيقة"
    return f"{seconds} ثانية"


def _user_mention(user: Any) -> str:
    name = getattr(user, "first_name", None) or getattr(user, "full_name", None) or "المستخدم"
    return f'<a href="tg://user?id={int(user.id)}">{html.escape(str(name))}</a>'


async def can_manage_repetition(user_id: int, chat_id: int) -> bool:
    if int(user_id) == OWNER_ID:
        return True
    if await is_primary_developer(user_id):
        return True
    return await get_rank_level(user_id, chat_id) >= 3


async def repetition_rank_allowed(user_id: int, chat_id: int, selected_rank: str) -> bool:
    if int(user_id) == OWNER_ID or await is_primary_developer(user_id):
        return False
    selected_level = RANK_LEVELS.get(selected_rank, 0)
    return await get_rank_level(user_id, chat_id) <= selected_level


def cleanup_user_messages(chat_id: int, user_id: int, seconds: int) -> None:
    now = time.monotonic()
    messages = _repetition_messages[int(chat_id)][int(user_id)]
    while messages and now - messages[0][1] > seconds:
        messages.popleft()


def add_repetition_message(chat_id: int, user_id: int, message_id: int, seconds: int):
    cleanup_user_messages(chat_id, user_id, seconds)
    messages = _repetition_messages[int(chat_id)][int(user_id)]
    messages.append((int(message_id), time.monotonic()))
    return list(messages)


def get_last_repetition_messages(chat_id: int, user_id: int, limit: int) -> list[int]:
    messages = _repetition_messages[int(chat_id)][int(user_id)]
    return [message_id for message_id, _ in list(messages)[-int(limit):]]


def reset_repetition_messages(chat_id: int, user_id: int) -> None:
    users = _repetition_messages.get(int(chat_id))
    if users is not None:
        users.pop(int(user_id), None)


async def delete_repetition_messages(bot, chat_id: int, message_ids: list[int]) -> None:
    if not message_ids:
        return
    semaphore = asyncio.Semaphore(8)

    async def delete_one(message_id):
        async with semaphore:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass

    await asyncio.gather(*(delete_one(mid) for mid in message_ids), return_exceptions=True)


async def send_third_warning_message(context, chat_id, user, warning_count):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("تقييد", callback_data=f"repetition_punish:restrict:{user.id}"),
        InlineKeyboardButton("كتم", callback_data=f"repetition_punish:mute:{user.id}"),
    ]])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"• المستخدم ↤︎ {_user_mention(user)}\n"
            f"• وصلت إنذاراته : {warning_count}\n"
            "اختر العقوبة المناسبة له:"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def repetition_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if (
        message.new_chat_members or message.left_chat_member or message.new_chat_title
        or message.new_chat_photo or message.delete_chat_photo or message.group_chat_created
        or message.supergroup_chat_created or message.channel_chat_created
        or message.migrate_to_chat_id or message.migrate_from_chat_id
    ):
        return
    if (message.text and message.text.startswith("/")) or (message.caption and message.caption.startswith("/")):
        return
    try:
        settings = await get_repetition_settings(chat.id)
        if not settings["enabled"]:
            return
        if not await repetition_rank_allowed(user.id, chat.id, settings["rank"]):
            return
        messages = add_repetition_message(
            chat.id, user.id, message.message_id, settings["seconds"]
        )
    except Exception:
        logger.exception("Failed to process repetition message")
        return
    if len(messages) < settings["limit"]:
        return

    logger.info(
        "Repetition detected chat=%s user=%s count=%s limit=%s seconds=%s",
        chat.id, user.id, len(messages), settings["limit"], settings["seconds"],
    )
    ids = get_last_repetition_messages(chat.id, user.id, settings["limit"])
    await delete_repetition_messages(context.bot, chat.id, ids)
    reset_repetition_messages(chat.id, user.id)

    try:
        new_count = await add_warning(chat.id, user.id, "repetition")
    except Exception:
        logger.exception("Failed to save repetition warning")
        return

    if new_count >= 3:
        try:
            await send_third_warning_message(context, chat.id, user, new_count)
        except Exception:
            logger.exception("Failed to send third-warning choices")
        return

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"⚠️ تحذير التكرار {new_count}/3\n\nالمستخدم ↤︎ {_user_mention(user)}",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to send repetition warning")


async def enable_repetition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not await can_manage_repetition(user.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    await update_repetition_setting(chat.id, "repetition_enabled", True)
    await message.reply_text("✅ تم تفعيل حماية التكرار.")


async def disable_repetition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not await can_manage_repetition(user.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    await update_repetition_setting(chat.id, "repetition_enabled", False)
    reset_repetition_messages(chat.id, user.id)
    await message.reply_text("✅ تم تعطيل حماية التكرار.")


async def set_repetition_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not await can_manage_repetition(user.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    parts = (message.text or "").strip().split()
    if len(parts) >= 3:
        try:
            limit = int(parts[2])
        except (ValueError, TypeError):
            limit = 0
        if limit < 1:
            await message.reply_text("❌ عدد التكرار يجب أن يكون 1 أو أكثر.")
            return
        repetition_sessions[(chat.id, user.id)] = {
            "type": "repetition_duration", "limit": limit,
            "created_at": datetime.now(timezone.utc),
        }
        await message.reply_text("حسنًا، ارسل المدة التي تريدها .")
        return
    await message.reply_text(
        "حسنًا، ارسل عدد التكرار أولًا.\nمثال:\nضع تكرار 5"
    )


async def receive_repetition_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat:
        return
    key = (chat.id, user.id)
    session = repetition_sessions.get(key)
    if not session or session.get("type") != "repetition_duration":
        return
    text = (message.text or "").strip()
    command_patterns = (
        r"^تفعيل التكرار$", r"^تعطيل التكرار$", r"^ضع تكرار(?:\s+\d+)?$",
        r"^ضع رتبة التكرار\s+", r"^تغيير رتبة التكرار\s+", r"^مسح انذاراته",
    )
    if any(re.match(pattern, text, flags=re.IGNORECASE) for pattern in command_patterns):
        return
    duration = parse_duration_token(text)
    if duration is None:
        await message.reply_text("❌ المدة غير صحيحة.\nأمثلة: 3ث - 5د - 1س - 2ي")
        return
    await update_repetition_setting(chat.id, "repetition_limit", int(session["limit"]))
    await update_repetition_setting(chat.id, "repetition_seconds", duration)
    repetition_sessions.pop(key, None)
    await message.reply_text(
        "✅ تم حفظ إعداد التكرار.\n\n"
        f"عدد الرسائل ↤︎ {session['limit']}\n"
        f"المدة ↤︎ {format_duration(duration)}"
    )


async def _set_punishment_duration(update, requested_action):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user:
        return
    if not await can_manage_repetition(user.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    parts = (message.text or "").strip().split()
    if len(parts) < 4:
        example = "ضع كتم تكرار 10د" if requested_action == "mute" else "ضع تقييد تكرار 10د"
        await message.reply_text(f"❌ المدة غير صحيحة.\nمثال: {example}")
        return
    duration = parse_duration_token(parts[-1])
    if duration is None:
        await message.reply_text("❌ المدة غير صحيحة.")
        return
    await update_repetition_setting(chat.id, "repetition_punishment_duration", duration)
    await message.reply_text(f"✅ تم تعيين مدة العقوبة إلى {format_duration(duration)}.")


async def set_mute_duration(update, context):
    await _set_punishment_duration(update, "mute")


async def set_restrict_duration(update, context):
    await _set_punishment_duration(update, "restrict")


async def set_repetition_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not await can_manage_repetition(user.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    match = re.match(
        r"^(?:ضع|تغيير)\s+رتبة\s+التكرار\s+(.+?)\s*$",
        (message.text or "").strip(), flags=re.IGNORECASE,
    )
    if not match:
        await message.reply_text("❌ اختر رتبة التكرار.\nمثال:\nضع رتبة التكرار المالك")
        return
    rank = match.group(1).strip()
    aliases = {
        "عضو": "عضو", "مميز": "مميز", "ادمن": "ادمن", "أدمن": "ادمن",
        "ادمن اساسي": "ادمن اساسي", "أدمن اساسي": "ادمن اساسي",
        "أدمن أساسي": "ادمن اساسي", "ادمن أساسي": "ادمن اساسي",
        "نائب المالك": "نائب المالك", "المالك": "المالك", "Dev": "Dev", "dev": "Dev",
    }
    rank = aliases.get(rank, rank)
    if rank not in RANK_LEVELS:
        await message.reply_text(
            "❌ الرتب المتاحة:\nعضو\nمميز\nادمن\nادمن اساسي\nنائب المالك\nالمالك\nDev"
        )
        return
    await update_repetition_setting(chat.id, "repetition_rank", rank)
    await message.reply_text(f"☑️ تم تعيين رتبة التكرار إلى {rank}.")


async def _get_warning_target(update, context):
    message = update.effective_message
    if not message:
        return None
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    parts = (message.text or "").strip().split()
    for value in parts[2:]:
        if value.isdigit() or value.startswith("@"):
            target = await lookup_user(context, value)
            if target:
                return target
    return None


async def clear_user_repetition_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not await can_manage_repetition(actor.id, chat.id):
        await message.reply_text("❌ هذا الأمر للادمن الاساسي وفوق فقط.")
        return
    target = await _get_warning_target(update, context)
    if not target:
        await message.reply_text("❌ استخدم الأمر بالرد على الشخص أو بالآيدي أو باليوزر.")
        return
    deleted = await clear_warnings(chat.id, target.id)
    reset_repetition_messages(chat.id, target.id)
    if deleted:
        await message.reply_text("☑️ تم مسح جميع انذاراته.")
    else:
        await message.reply_text("• الشخص هذا ماعنده انذارات من قبل.")


async def set_warning_duration(update, context):
    return


async def change_repetition_action(update, context):
    return


async def repetition_expiry_loop(application):
    while True:
        try:
            now = datetime.now(timezone.utc)
            for key, session in list(repetition_sessions.items()):
                created_at = session.get("created_at")
                if created_at and (now - created_at).total_seconds() > 300:
                    repetition_sessions.pop(key, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Repetition session cleanup failed")
        await asyncio.sleep(60)
