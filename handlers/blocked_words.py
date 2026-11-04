"""Async dual-list blocked-word protection and moderation UI."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Any

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions,
)
from telegram.constants import ChatType
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.blocked_words import (
    get_settings, set_enabled, set_direct_action, set_warning_action,
    get_words, add_words, delete_words, add_blocked_warning,
    get_active_warning_count, clear_blocked_warnings,
    cleanup_expired_blocked_warnings, invalidate_blocked_cache,
)
from database.moderation import (
    save_sanction, delete_sanction, get_user_by_id, get_user_by_username,
)
from database.roles import get_rank_level, is_primary_developer

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
MIN_RANK_LEVEL = 4
MANAGE_MIN_RANK_LEVEL = 4
BLOCKED_WORDS_MAX_AFFECTED_RANK = 1
LIST_1, LIST_2 = 1, 2
LIST_ALIASES = {
    "الكلمات المحظورة": 1,
    "الكلمات المحظورة/ه": 1,
    "الكلمات المحظورة2": 2,
    "الكلمات المحظورة/ه2": 2,
}
BLOCKED_PERMISSION_MESSAGE = "• هذا الأمر لـ نائب المالك وفوق فقط ."
RIYADH_TZ = timezone(timedelta(hours=3))
_blocked_sessions: dict[tuple[int, int], dict[str, Any]] = {}
_blocked_regex_cache: dict[str, re.Pattern] = {}
FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True, can_manage_topics=True,
)


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def mention_user(user: Any) -> str:
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)
    return f'<a href="tg://user?id={int(user.id)}">{html_escape(name)}</a>'


def current_timestamp() -> int:
    return int(time.time())


def parse_duration_token(token: str) -> int | None:
    match = re.match(
        r"^\s*(\d+(?:\.\d+)?)\s*(ث|ثانية|ثواني|د|دقيقة|دقائق|س|ساعة|ساعات|ي|يوم|أيام)\s*$",
        str(token or ""),
    )
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


async def get_blocked_level(user_id: int, chat_id: int) -> int:
    try:
        return await get_rank_level(user_id, chat_id)
    except Exception:
        logger.exception("Failed to read blocked-word rank for %s", user_id)
        return 0


async def can_manage_blocked_words(user_id: int, chat_id: int) -> bool:
    return await get_blocked_level(user_id, chat_id) >= MANAGE_MIN_RANK_LEVEL


async def can_be_affected_by_blocked_words(user_id: int, chat_id: int) -> bool:
    if int(user_id) == OWNER_ID or await is_primary_developer(user_id):
        return False
    return await get_blocked_level(user_id, chat_id) <= BLOCKED_WORDS_MAX_AFFECTED_RANK


def invalidate_blocked_words_cache(chat_id: int, list_id: int | None = None):
    invalidate_blocked_cache(chat_id, list_id)
    _blocked_regex_cache.clear()


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", str(word or "").replace("\r", " ").replace("\n", " ")).strip()


def extract_input_words(text: str) -> list[str]:
    result = []
    for line in (text or "").splitlines():
        word = normalize_word(line)
        if word and word not in result:
            result.append(word)
    return result


def get_blocked_regex(word: str):
    cached = _blocked_regex_cache.get(word)
    if cached is not None:
        return cached
    normalized = normalize_word(word)
    if not normalized:
        return None
    pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)", flags=re.UNICODE)
    _blocked_regex_cache[word] = pattern
    return pattern


def word_matches(text: str, word: str) -> bool:
    regex = get_blocked_regex(word)
    return bool(regex and regex.search(text or ""))


def find_blocked_word(text: str, words: list[str]):
    for word in words:
        if word_matches(text, word):
            return word
    return None


def format_until(timestamp: int | None) -> str:
    if timestamp is None:
        return "لا توجد مدة"
    return datetime.fromtimestamp(timestamp, RIYADH_TZ).strftime("%Y/%m/%d - %H:%M:%S")


def punishment_keyboard(action: str, chat_id: int, user_id: int):
    labels = {"mute": "رفع الكتم ☑️", "restrict": "رفع القيود ☑️", "ban": "رفع الحظر ☑️"}
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            labels[action],
            callback_data=f"bw:lift:{action}:{chat_id}:{user_id}",
        )
    ]])


def punishment_message(action: str, target: Any, until_timestamp: int | None):
    mention = mention_user(target)
    if action == "mute":
        return f"🔐 تَمَّ كتم {mention} [{target.id}].\n⏰ لمدة حتى: {format_until(until_timestamp)}"
    if action == "restrict":
        return f"🔐 قُيِّدَ {mention} [{target.id}].\n⏰ لمدة حتى: {format_until(until_timestamp)}"
    return f"🔐 تَمَّ حظر {mention} [{target.id}].\n⏰ لمدة حتى: {format_until(until_timestamp)}"


async def apply_punishment(update, context, chat_id, target, action, duration):
    until_timestamp = current_timestamp() + int(duration) if duration is not None else None
    until_time = datetime.fromtimestamp(until_timestamp, timezone.utc) if until_timestamp is not None else None
    if action == "mute":
        await save_sanction("bot_mutes", chat_id, target, until_time, None, context.bot.id)
    elif action == "restrict":
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id, user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_time,
            )
        except Exception:
            logger.exception("Failed to restrict user for blocked word")
            return False
        await save_sanction("restrictions", chat_id, target, until_time, None, context.bot.id)
    elif action == "ban":
        try:
            await context.bot.ban_chat_member(
                chat_id=chat_id, user_id=target.id, until_date=until_time,
            )
        except Exception:
            logger.exception("Failed to ban user for blocked word")
            return False
        await save_sanction("moderation_bans", chat_id, target, until_time, None, context.bot.id)
    else:
        return False
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=punishment_message(action, target, until_timestamp),
            parse_mode="HTML",
            reply_markup=punishment_keyboard(action, chat_id, target.id),
        )
    except Exception:
        logger.exception("Failed to send blocked-word punishment message")
    return True


async def send_blocked_warning(update, context, target, count):
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "• كتب كلمة محظورة وجاه انذار .\n"
                f"• المستخدم ↤︎ {mention_user(target)}\n"
                f"• عدد إنذاراته ↤︎ {count}"
            ),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to send blocked-word warning")


async def handle_warning_punishment(update, context, chat_id, list_id, target, settings):
    warning_duration = settings["warning_duration"]
    warning_action = settings["warning_action"]
    punishment_duration = settings["warning_punishment_duration"]
    if not warning_duration or not warning_action:
        return
    count = await add_blocked_warning(chat_id, list_id, target.id, warning_duration)
    if count < 3:
        await send_blocked_warning(update, context, target, count)
        return
    await clear_blocked_warnings(chat_id, list_id, target.id)
    await apply_punishment(
        update, context, chat_id, target, warning_action, punishment_duration
    )


def list_title(list_id: int) -> str:
    return "قائمة الكلمات المحظورة" if list_id == LIST_1 else "قائمة الكلمات المحظورة2"


def list_command_name(list_id: int) -> str:
    return "الكلمات المحظورة" if list_id == LIST_1 else "الكلمات المحظورة2"


async def build_list_message(chat_id: int, list_id: int):
    words = await get_words(chat_id, list_id)
    settings = await get_settings(chat_id, list_id)
    title = list_title(list_id)
    if not words:
        text = "لا توجد كلمات محظورة حاليًا ."
    else:
        lines = [f"🚫 {title}:", ""]
        lines.extend(f"{index} - {html_escape(word)}" for index, word in enumerate(words, 1))
        text = "\n".join(lines)
    status_text = "الحالة: مفعلة 🟢" if settings["enabled"] else "الحالة: معطلة 🔴"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("اضافة كلمات ➕", callback_data=f"bw:add:{list_id}:{chat_id}"),
            InlineKeyboardButton("حذف كلمات 🗑️", callback_data=f"bw:delete:{list_id}:{chat_id}"),
        ],
        [InlineKeyboardButton(status_text, callback_data=f"bw:toggle:{list_id}:{chat_id}")],
    ])
    return text, keyboard


def welcome_keyboard(chat_id: int, list_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("هنا 👆🏻", callback_data=f"bw:here:{list_id}:{chat_id}"),
        InlineKeyboardButton("فتح القائمة بالخاص❕", callback_data=f"bw:private:{list_id}:{chat_id}"),
    ]])


async def blocked_words_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, actor, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not actor or not chat:
        return
    text = (message.text or "").strip()
    list_id = LIST_ALIASES.get(text)

    if list_id is None:
        toggle_match = re.fullmatch(
            r"(تفعيل|تعطيل)\s+(الكلمات المحظورة|الكلمات المحظورة/ه|الكلمات المحظورة2|الكلمات المحظورة/ه2)",
            text,
        )
        if toggle_match:
            list_id = LIST_ALIASES[toggle_match.group(2)]
            if not await can_manage_blocked_words(actor.id, chat.id):
                await message.reply_text(BLOCKED_PERMISSION_MESSAGE)
                raise ApplicationHandlerStop
            enabled = toggle_match.group(1) == "تفعيل"
            await set_enabled(chat.id, list_id, enabled)
            await message.reply_text(
                "• تم تفعيل الكلمات المحظورة ✅ ." if enabled else "• تم تعطيل الكلمات المحظورة ✅ ."
            )
            raise ApplicationHandlerStop

        punishment_match = re.fullmatch(
            r"ضع عقوبة\s+(الكلمات المحظورة|الكلمات المحظورة/ه|الكلمات المحظورة2|الكلمات المحظورة/ه2)\s+(كتم|تقييد|حظر|انذار)",
            text,
        )
        if punishment_match:
            list_id = LIST_ALIASES[punishment_match.group(1)]
            punishment = punishment_match.group(2)
            if not await can_manage_blocked_words(actor.id, chat.id):
                await message.reply_text(BLOCKED_PERMISSION_MESSAGE)
                raise ApplicationHandlerStop
            if punishment == "انذار":
                _blocked_sessions[(actor.id, chat.id)] = {"type": "warning_setup", "list_id": list_id}
                await message.reply_text(
                    "تمام، أرسل مدة الانذار+ العقوبة الي بعد الانذارات مع المدة بهذي الطريقة:\n\n3د كتم 5ي"
                )
                raise ApplicationHandlerStop
            if punishment == "حظر":
                await set_direct_action(chat.id, list_id, "ban", None)
                await message.reply_text(
                    "• تم وضع عقوبة الحظر على الكلمات المحظورة بنجاح ✅ ."
                )
                raise ApplicationHandlerStop
            action = "mute" if punishment == "كتم" else "restrict"
            _blocked_sessions[(actor.id, chat.id)] = {
                "type": "direct_duration", "list_id": list_id, "action": action,
            }
            await message.reply_text(
                "• حسنًا اختر مدة الكتم ." if action == "mute" else "• حسنًا اختر مدة التقييد ."
            )
            raise ApplicationHandlerStop
        return

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await can_manage_blocked_words(actor.id, chat.id):
            await message.reply_text(BLOCKED_PERMISSION_MESSAGE)
            raise ApplicationHandlerStop
        mention = f'<a href="tg://user?id={actor.id}">{html_escape(actor.first_name or "المشرف")}</a>'
        await message.reply_text(
            f"اهلًا يالمشرف {mention}\nاختر وين تبي تفك القائمة:",
            parse_mode="HTML", reply_markup=welcome_keyboard(chat.id, list_id),
        )
        raise ApplicationHandlerStop
    if chat.type == ChatType.PRIVATE:
        message_text, keyboard = await build_list_message(chat.id, list_id)
        await message.reply_text(message_text, parse_mode="HTML", reply_markup=keyboard)
        raise ApplicationHandlerStop


async def handle_blocked_session(update, context) -> bool:
    message, actor, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not actor or not chat:
        return False
    key = (actor.id, chat.id)
    session = _blocked_sessions.get(key)
    if not session:
        return False
    origin_chat_id = int(session.get("origin_chat_id", chat.id))
    if not await can_manage_blocked_words(actor.id, origin_chat_id):
        _blocked_sessions.pop(key, None)
        await message.reply_text(BLOCKED_PERMISSION_MESSAGE)
        return True

    kind = session["type"]
    list_id = int(session["list_id"])
    if kind in ("add", "delete"):
        words = extract_input_words(message.text or "")
        if not words:
            await message.reply_text(
                "• لم يتم العثور على كلمات لإضافتها ." if kind == "add"
                else "• لم يتم العثور على كلمات لحذفها ."
            )
            return True
        if kind == "add":
            await add_words(origin_chat_id, list_id, words)
        else:
            await delete_words(origin_chat_id, list_id, words)
        _blocked_sessions.pop(key, None)
        try:
            await message.delete()
        except Exception:
            pass
        success_text = "تم حفظ الكلمات بنجاح ✅ ." if kind == "add" else "تم حذف الكلمات بنجاح ✅ ."
        await message.reply_text(
            success_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ رجوع لقائمة الكلمات", callback_data=f"bw:back:{list_id}:{origin_chat_id}"),
                InlineKeyboardButton("اغلاق القائمة", callback_data=f"bw:close:{origin_chat_id}"),
            ]]),
        )
        return True

    if kind == "direct_duration":
        duration = parse_duration_token((message.text or "").strip())
        if duration is None:
            await message.reply_text("• المدة غير صحيحة .\n• مثال: 5ي أو 30ث أو 50د أو 1س")
            return True
        await set_direct_action(origin_chat_id, list_id, session["action"], duration)
        _blocked_sessions.pop(key, None)
        await message.reply_text("• تم حفظ إعداد العقوبة بنجاح ✅ .")
        return True

    if kind == "warning_setup":
        parts = (message.text or "").strip().split()
        if len(parts) not in (2, 3):
            await message.reply_text("• الصيغة غير صحيحة .\n\nمثال:\n3د كتم 5ي")
            return True
        warning_duration = parse_duration_token(parts[0])
        if warning_duration is None:
            await message.reply_text("• مدة الانذار غير صحيحة .\n\nمثال:\n3د كتم 5ي")
            return True
        warning_action = {"كتم": "mute", "تقييد": "restrict", "حظر": "ban"}.get(parts[1])
        if not warning_action:
            await message.reply_text("• العقوبة غير صحيحة .\n\nاستخدم: كتم أو تقييد أو حظر")
            return True
        punishment_duration = None
        if warning_action in ("mute", "restrict"):
            if len(parts) != 3:
                await message.reply_text("• يجب كتابة مدة العقوبة أيضًا .\n\nمثال:\n3د كتم 5ي")
                return True
            punishment_duration = parse_duration_token(parts[2])
            if punishment_duration is None:
                await message.reply_text("• مدة العقوبة غير صحيحة .\n\nمثال:\n3د كتم 5ي")
                return True
        elif len(parts) != 2:
            await message.reply_text("• الحظر دائم، اكتبها هكذا:\n\n3د حظر")
            return True
        await set_warning_action(
            origin_chat_id, list_id, warning_duration,
            warning_action, punishment_duration,
        )
        _blocked_sessions.pop(key, None)
        await message.reply_text("• تم حفظ إعدادات الانذار بنجاح ✅ .")
        return True
    return False


async def check_blocked_words(update, context) -> bool:
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP) or not actor:
        return False
    if actor.id == OWNER_ID:
        return False
    text = message.text or ""
    if not text:
        return False
    for list_id in (LIST_1, LIST_2):
        words = await get_words(chat.id, list_id)
        matched = find_blocked_word(text, words)
        if not matched:
            continue
        settings = await get_settings(chat.id, list_id)
        if not settings["enabled"]:
            continue
        level = await get_blocked_level(actor.id, chat.id)
        if actor.id == OWNER_ID:
            return False
        if level >= 2:
            try:
                await message.delete()
            except Exception:
                logger.warning("Could not delete blocked-word message from admin", exc_info=True)
            return True
        if level <= BLOCKED_WORDS_MAX_AFFECTED_RANK:
            try:
                await message.delete()
            except Exception:
                logger.warning("Could not delete blocked-word message", exc_info=True)
            if settings["action"] in ("mute", "restrict", "ban"):
                await apply_punishment(
                    update, context, chat.id, actor,
                    settings["action"], settings["duration"],
                )
                return True
            if settings["action"] == "warning":
                await handle_warning_punishment(
                    update, context, chat.id, list_id, actor, settings,
                )
                return True
            return True
        try:
            await message.delete()
        except Exception:
            pass
        return True
    return False


async def blocked_words_message_handler(update, context):
    if not update.effective_message or not update.effective_user:
        return
    if await handle_blocked_session(update, context):
        raise ApplicationHandlerStop
    text = (update.effective_message.text or "").strip()
    command_names = set(LIST_ALIASES)
    is_punishment_command = bool(re.fullmatch(
        r"ضع عقوبة\s+(الكلمات المحظورة|الكلمات المحظورة/ه|الكلمات المحظورة2|الكلمات المحظورة/ه2)\s+(كتم|تقييد|حظر|انذار)",
        text,
    ))
    is_toggle_command = bool(re.fullmatch(
        r"(تفعيل|تعطيل)\s+(الكلمات المحظورة|الكلمات المحظورة/ه|الكلمات المحظورة2|الكلمات المحظورة/ه2)",
        text,
    ))
    if text in command_names or is_punishment_command or is_toggle_command:
        await blocked_words_command(update, context)
        raise ApplicationHandlerStop
    if await check_blocked_words(update, context):
        raise ApplicationHandlerStop


async def blocked_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    if not data.startswith("bw:"):
        return
    actor = query.from_user
    if not actor:
        return
    parts = data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]
    list_id = None
    origin_chat_id = None
    punishment_action = None
    target_id = None
    if action in ("here", "private", "add", "delete", "toggle", "back"):
        if len(parts) != 4:
            return
        try:
            list_id, origin_chat_id = int(parts[2]), int(parts[3])
        except ValueError:
            return
    elif action == "close":
        if len(parts) != 3:
            return
        try:
            origin_chat_id = int(parts[2])
        except ValueError:
            return
    elif action == "lift":
        if len(parts) != 5:
            return
        punishment_action = parts[2]
        if punishment_action not in ("mute", "restrict", "ban"):
            return
        try:
            origin_chat_id, target_id = int(parts[3]), int(parts[4])
        except ValueError:
            return
    else:
        return

    if not await can_manage_blocked_words(actor.id, origin_chat_id):
        await query.answer(BLOCKED_PERMISSION_MESSAGE, show_alert=True)
        return
    await query.answer()

    if action == "here":
        if not query.message:
            return
        text, keyboard = await build_list_message(origin_chat_id, list_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        return
    if action == "private":
        if not query.message:
            return
        text, keyboard = await build_list_message(origin_chat_id, list_id)
        try:
            await context.bot.send_message(
                chat_id=actor.id, text=text, parse_mode="HTML", reply_markup=keyboard,
            )
            await query.edit_message_text("تم الإرسال بالخاص ✅ .")
        except Exception:
            logger.exception("Could not send blocked-word list privately")
            try:
                await query.edit_message_text("تعذر إرسال القائمة بالخاص.")
            except Exception:
                pass
        return
    if action in ("add", "delete"):
        if not query.message:
            return
        _blocked_sessions[(actor.id, query.message.chat.id)] = {
            "type": action, "list_id": list_id, "origin_chat_id": origin_chat_id,
        }
        prompt = "• حسنًا ارسل الكلمات التي تريد إضافتها ." if action == "add" else "• حسنًا ارسل الكلمات التي تريد حذفها ."
        await query.edit_message_text(
            prompt + "\n\nمثال:\n\nكلزق\nكلتبن\nياكلب\nالخ…"
        )
        return
    if action == "toggle":
        settings = await get_settings(origin_chat_id, list_id)
        await set_enabled(origin_chat_id, list_id, not settings["enabled"])
        if not query.message:
            return
        text, keyboard = await build_list_message(origin_chat_id, list_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        return
    if action == "back":
        if not query.message:
            return
        text, keyboard = await build_list_message(origin_chat_id, list_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        return
    if action == "close":
        if query.message:
            try:
                await query.message.delete()
            except Exception:
                pass
        return
    if action == "lift":
        try:
            member = await context.bot.get_chat_member(origin_chat_id, target_id)
            target = member.user
        except Exception:
            target = SimpleNamespace(id=target_id, username=None, first_name=str(target_id))
        if punishment_action == "mute":
            await delete_sanction("bot_mutes", origin_chat_id, target_id)
        elif punishment_action == "restrict":
            try:
                await context.bot.restrict_chat_member(
                    chat_id=origin_chat_id, user_id=target_id, permissions=FULL_PERMISSIONS,
                )
            except Exception:
                logger.exception("Failed to lift blocked-word restriction")
                return
            await delete_sanction("restrictions", origin_chat_id, target_id)
        else:
            try:
                await context.bot.unban_chat_member(
                    chat_id=origin_chat_id, user_id=target_id, only_if_banned=False,
                )
            except Exception:
                logger.exception("Failed to lift blocked-word ban")
                return
            await delete_sanction("moderation_bans", origin_chat_id, target_id)
        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass


async def blocked_words_expiry_loop(application):
    while True:
        try:
            await cleanup_expired_blocked_warnings()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Blocked-word warning expiry loop failed")
        await asyncio.sleep(15)
