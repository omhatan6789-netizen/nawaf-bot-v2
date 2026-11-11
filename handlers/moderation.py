"""Async moderation handlers: mute, restrict, ban, warnings and moderation lists."""
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
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions, ReactionTypeEmoji,
)
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.moderation import (
    get_moderation_settings, set_moderation_setting,
    save_target_user, get_user_by_id, get_user_by_username,
    save_sanction, delete_sanction, get_active_mute,
    get_user_restrictions, get_sanction_rows, clear_sanction_table,
    get_warning_count, add_warning, clear_warnings,
    get_expired_sanctions, get_user_messages,
    get_repetition_punishment_duration,
)
from database.roles import get_rank, get_rank_level

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
DURATION_PATTERN = re.compile(
    r"^(\d+)\s*(ث|ثانية|ثواني|د|دقيقة|دقائق|س|ساعة|ساعات|ي|يوم|أيام)$",
    re.IGNORECASE,
)
ACTION_NAMES = {"كتم": "mute", "تقييد": "restrict", "حظر": "ban"}
ACTION_LABELS = {"mute": "الكتم", "restrict": "التقييد", "ban": "الحظر"}
TABLES = {
    "mute": ("bot_mutes", "قائمه المكتومين", "مسح المكتومين"),
    "restrict": ("restrictions", "قائمه المقيدين", "مسح المقيدين"),
    "ban": ("moderation_bans", "قائمه المحظورين", "مسح المحظورين"),
}
FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True,
    can_send_other_messages=True, can_add_web_page_previews=True,
    can_invite_users=True, can_manage_topics=True,
)


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def mention_user(user: Any) -> str:
    if not user:
        return ""
    name = getattr(user, "first_name", None) or getattr(user, "username", None) or str(user.id)
    return f'<a href="tg://user?id={int(user.id)}">{html_escape(name)}</a>'


def now_timestamp() -> int:
    return int(time.time())


def timestamp_to_iso(timestamp: int | None):
    return datetime.fromtimestamp(timestamp, timezone.utc) if timestamp is not None else None


def iso_to_timestamp(value):
    if not value:
        return None
    if hasattr(value, "timestamp"):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def parse_duration_token(token: str):
    match = DURATION_PATTERN.match((token or "").strip())
    if not match:
        return None
    amount = int(match.group(1))
    if amount <= 0:
        return None
    unit = match.group(2)
    if unit in ("ث", "ثانية", "ثواني"):
        return amount
    if unit in ("د", "دقيقة", "دقائق"):
        return amount * 60
    if unit in ("س", "ساعة", "ساعات"):
        return amount * 3600
    return amount * 86400


def format_duration(seconds: int) -> str:
    seconds = int(seconds)
    if seconds % 86400 == 0:
        return f"{seconds // 86400} يوم"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ساعة"
    if seconds % 60 == 0:
        return f"{seconds // 60} دقيقة"
    return f"{seconds} ثانية"


def parse_moderation_command(text, durations_enabled, reasons_enabled):
    parts = (text or "").strip().split()
    if not parts or parts[0] not in ACTION_NAMES:
        return None
    action = ACTION_NAMES[parts[0]]
    rest = parts[1:]
    duration_index = None
    duration = None
    target_index = None
    for index, part in enumerate(rest):
        parsed = parse_duration_token(part)
        if parsed is not None:
            duration_index = index
            duration = parsed if durations_enabled else None
            break
    for index, part in enumerate(rest):
        if index == duration_index:
            continue
        if part.isdigit() or part.startswith("@"):
            target_index = index
            break
    reason_parts = [
        part for index, part in enumerate(rest)
        if index not in (duration_index, target_index)
    ]
    reason = " ".join(reason_parts) if reason_parts and reasons_enabled else None
    return {"action": action, "duration": duration, "reason": reason}


async def _get_level(user_id: int, chat_id: int) -> int:
    try:
        return await get_rank_level(int(user_id), int(chat_id))
    except Exception:
        logger.exception("Failed to get moderation rank for %s", user_id)
        return 0


async def react_clown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    try:
        await context.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji="🤡")],
        )
    except Exception:
        logger.debug("Could not set clown reaction", exc_info=True)


async def resolve_target(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allow_music_lookup: bool = False,
):
    message = update.effective_message
    if not message:
        return None
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        await save_target_user(user)
        return user

    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        return None
    target_value = next(
        (part for part in parts[1:] if part.isdigit() or part.startswith("@")),
        None,
    )
    if not target_value:
        return None

    row = (
        await get_user_by_id(int(target_value))
        if target_value.isdigit()
        else await get_user_by_username(target_value.lstrip("@"))
    )
    if row:
        return SimpleNamespace(
            id=int(row["user_id"]),
            username=row["username"],
            first_name=row["first_name"] or "",
            is_bot=False,
        )

    if target_value.isdigit():
        try:
            user = await context.bot.get_chat(int(target_value))
            if user:
                await save_target_user(user)
                return user
        except Exception:
            pass
    elif allow_music_lookup:
        try:
            from music_call import get_music_client

            music_client = get_music_client()
            if music_client is not None:
                user = await music_client.get_users(target_value.lstrip("@"))
                if user:
                    await save_target_user(user)
                    return user
        except Exception:
            logger.debug("Music account username lookup failed", exc_info=True)
    return None


def moderation_message(action, target, duration, reason=None, actor_rank=None):
    mention = mention_user(target)
    if action == "mute":
        text = f"تم كتمته لين يهجد بعدين فكوه\nالمستخدم ↤︎ {mention}"
    elif action == "restrict":
        text = f"تم قيَّدته لين يهجد بعدين فكوه\nالمستخدم ↤︎ {mention}"
    else:
        text = f"تم حظرته لعيونك يـ {html_escape(actor_rank or 'عضو')}\nالمستخدم ↤︎ {mention}"
    if duration is not None:
        text += f"\nمدة {ACTION_LABELS[action]} ↤︎ {format_duration(duration)}"
    if reason:
        text += f"\nالسبب ↤︎ {html_escape(reason)}"
    return text


async def moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    actor_level = await _get_level(actor.id, chat.id)
    if actor_level < 2:
        return
    settings = await get_moderation_settings(chat.id)
    parsed = parse_moderation_command(
        message.text, settings["durations_enabled"], settings["reasons_enabled"]
    )
    if not parsed:
        return
    target = await resolve_target(update, context)
    if not target:
        return
    action, duration, reason = parsed["action"], parsed["duration"], parsed["reason"]
    if action == "mute" and settings["durations_enabled"] and duration is None:
        duration = 3600
    if target.id in (context.bot.id, actor.id):
        await react_clown(update, context)
        return
    target_level = await _get_level(target.id, chat.id)
    if target_level >= actor_level:
        higher_messages = {
            "mute": "صحصح شف من الي تبي تكتمه ياورع!",
            "restrict": "صحصح شف من الي تبي تقيده ياورع!",
            "ban": "صحصح شف من الي تبي تحظره ياورع!",
        }
        await message.reply_text(higher_messages[action])
        return

    until_timestamp = now_timestamp() + duration if duration is not None else None
    until_time = timestamp_to_iso(until_timestamp)
    table = {"mute": "bot_mutes", "restrict": "restrictions", "ban": "moderation_bans"}[action]

    if action == "restrict":
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=target.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_time,
            )
        except Exception:
            logger.exception("Telegram restrict failed")
            return
    elif action == "ban":
        try:
            await context.bot.ban_chat_member(
                chat_id=chat.id, user_id=target.id, until_date=until_time,
            )
        except Exception:
            logger.exception("Telegram ban failed")
            return

    await save_sanction(table, chat.id, target, until_time, reason, actor.id)
    actor_rank = await get_rank(actor.id) if action == "ban" else None
    await message.reply_text(
        moderation_message(action, target, duration, reason, actor_rank),
        parse_mode="HTML",
    )


async def check_muted_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not user:
        return
    if await get_active_mute(chat.id, user.id):
        try:
            await message.delete()
        except Exception:
            pass


async def _remove_restriction(update, context, action):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor:
        return
    actor_level = await _get_level(actor.id, chat.id)
    if actor_level < 2 or (action == "ban" and actor_level < 3):
        return
    target = await resolve_target(update, context)
    if not target:
        return
    if target.id in (context.bot.id, actor.id):
        await react_clown(update, context)
        return
    if action == "mute":
        await delete_sanction("bot_mutes", chat.id, target.id)
        text = f"فكيت عنه الكتم يارب يعقل 🙏🏻\n• المستخدم ↤︎ {mention_user(target)}"
    elif action == "restrict":
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=target.id, permissions=FULL_PERMISSIONS
            )
        except Exception:
            logger.exception("Telegram unrestrict failed")
            return
        await delete_sanction("restrictions", chat.id, target.id)
        text = f"فكيت عنه يارب يعقل 🙏🏻\n• المستخدم ↤︎ {mention_user(target)}"
    else:
        try:
            await context.bot.unban_chat_member(
                chat_id=chat.id, user_id=target.id, only_if_banned=False
            )
        except Exception:
            logger.exception("Telegram unban failed")
            return
        await delete_sanction("moderation_bans", chat.id, target.id)
        text = f"فكيت عنه يارب يعقل 🙏🏻\nالمستخدم ↤︎ {mention_user(target)}"
    await message.reply_text(text, parse_mode="HTML")


async def unmute_command(update, context):
    await _remove_restriction(update, context, "mute")


async def unrestrict_command(update, context):
    await _remove_restriction(update, context, "restrict")


async def unban_command(update, context):
    await _remove_restriction(update, context, "ban")


async def clear_restrictions_command(update, context):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or await _get_level(actor.id, chat.id) < 2:
        return
    target = await resolve_target(update, context)
    if not target:
        return
    if target.id in (context.bot.id, actor.id):
        await react_clown(update, context)
        return
    restrictions = await get_user_restrictions(chat.id, target.id)
    if "كتم" in restrictions:
        await delete_sanction("bot_mutes", chat.id, target.id)
    if "تقييد" in restrictions:
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=target.id, permissions=FULL_PERMISSIONS
            )
        except Exception:
            logger.exception("Failed to remove restriction")
        else:
            await delete_sanction("restrictions", chat.id, target.id)
    if "حظر" in restrictions and await _get_level(actor.id, chat.id) >= 3:
        try:
            await context.bot.unban_chat_member(
                chat_id=chat.id, user_id=target.id, only_if_banned=False
            )
        except Exception:
            logger.exception("Failed to remove ban")
        else:
            await delete_sanction("moderation_bans", chat.id, target.id)
    await message.reply_text(
        "• تم رفع القيود عنه، قيوده كانت ( "
        + "، ".join(restrictions)
        + " )\n"
        + f"المستخدم ↤︎ {mention_user(target)}",
        parse_mode="HTML",
    )


async def moderation_lists_command(update, context):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or await _get_level(actor.id, chat.id) < 3:
        return
    kind = {"المكتومين": "mute", "المقيدين": "restrict", "المحظورين": "ban"}.get((message.text or "").strip())
    if not kind:
        return
    rows = await get_sanction_rows(TABLES[kind][0], chat.id)
    text = f"• {TABLES[kind][1]}\n━━━━━━━━━━━━\n"
    if not rows:
        text += "لا يوجد\n"
    else:
        for index, row in enumerate(rows, 1):
            user_id, username, first_name = row["user_id"], row["username"], row["first_name"]
            display = (
                "@" + str(username).lstrip("@")
                if username else
                f'<a href="tg://user?id={user_id}">{html_escape(first_name or user_id)}</a>'
            )
            text += f"{index} - {display}\n"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(TABLES[kind][2], callback_data=f"moderation:clear:{kind}")
    ]])
    await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def clear_list_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return
    chat_id = query.message.chat.id
    if await _get_level(query.from_user.id, chat_id) < 3:
        await query.answer("هذا الأمر للأدمن الأساسي وفوق فقط!", show_alert=True)
        return
    parts = (query.data or "").split(":")
    if len(parts) != 3 or parts[2] not in TABLES:
        await query.answer()
        return
    kind = parts[2]
    table = TABLES[kind][0]
    rows = await get_sanction_rows(table, chat_id)
    await query.answer()
    if kind == "restrict":
        for row in rows:
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id, user_id=row["user_id"], permissions=FULL_PERMISSIONS
                )
            except Exception:
                pass
    elif kind == "ban":
        for row in rows:
            try:
                await context.bot.unban_chat_member(
                    chat_id=chat_id, user_id=row["user_id"], only_if_banned=False
                )
            except Exception:
                pass
    await clear_sanction_table(table, chat_id)
    await query.edit_message_text(f"• تم {TABLES[kind][2]} .")


async def _set_setting(update, enabled, column, response):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or await _get_level(actor.id, chat.id) < 2:
        return
    await set_moderation_setting(chat.id, column, enabled)
    await message.reply_text(response)


async def enable_durations_command(update, context):
    await _set_setting(update, True, "durations_enabled", "• تم تفعيل المدة للمشرفين .")


async def disable_durations_command(update, context):
    await _set_setting(update, False, "durations_enabled", "• تم تعطيل المدة للمشرفين .")


async def enable_reasons_command(update, context):
    await _set_setting(update, True, "reasons_enabled", "• تم تفعيل الاسباب .")


async def disable_reasons_command(update, context):
    await _set_setting(update, False, "reasons_enabled", "• تم تعطيل الاسباب .")


async def warning_command(update, context):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or await _get_level(actor.id, chat.id) < 2:
        return
    target = await resolve_target(update, context)
    if not target or target.id in (actor.id, context.bot.id):
        return
    actor_level = await _get_level(actor.id, chat.id)
    if await _get_level(target.id, chat.id) >= actor_level:
        await message.reply_text(
            "• اعذرني بس هذا الأمر لـ ↤︎〖 الادمن 〗وفوق فقط ."
        )
        return
    await save_target_user(target)
    count = await add_warning(chat.id, target.id, "manual")
    mention = mention_user(target)
    if count >= 3:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("تقييد", callback_data=f"repetition_punish:restrict:{target.id}"),
            InlineKeyboardButton("كتم", callback_data=f"repetition_punish:mute:{target.id}"),
        ]])
        await message.reply_text(
            f"• المستخدم ↤︎ {mention}\n• وصلت إنذاراته : {count}\nاختر العقوبة المناسبة له:",
            parse_mode="HTML", reply_markup=keyboard,
        )
        return
    await message.reply_text(
        "• تمام عطيته انذار .\n"
        f"• المستخدم ↤︎ {mention}\n"
        f"• عدد إنذاراته : {count}",
        parse_mode="HTML",
    )


async def clear_warnings_command(update, context):
    message, chat, actor = update.effective_message, update.effective_chat, update.effective_user
    if not message or not chat or not actor or await _get_level(actor.id, chat.id) < 2:
        return
    target = await resolve_target(update, context)
    if not target or await _get_level(target.id, chat.id) >= await _get_level(actor.id, chat.id):
        return
    await clear_warnings(chat.id, target.id)
    await message.reply_text(
        "• تم مسح جميع إنذاراته .\n"
        f"• المستخدم ↤︎ {mention_user(target)}",
        parse_mode="HTML",
    )


async def reveal_restrictions_command(update, context):
    message, chat = update.effective_message, update.effective_chat
    if not message or not chat:
        return
    target = await resolve_target(update, context)
    if not target:
        return
    restrictions = await get_user_restrictions(chat.id, target.id)
    warning_count = await get_warning_count(chat.id, target.id)
    text = (
        "• معلومات الكشف \n━━━━━━━━━━━━\n"
        f"• الحظر : {'محظور' if 'حظر' in restrictions else 'غير محظور'}\n"
        f"• الكتم : {'مكتوم' if 'كتم' in restrictions else 'غير مكتوم'}\n"
        f"• التقييد : {'مقيد' if 'تقييد' in restrictions else 'غير مقيد'}\n"
        f"• الانذارات : {warning_count}"
    )
    await message.reply_text(text, parse_mode="HTML")


async def reveal_command(update, context):
    message, chat = update.effective_message, update.effective_chat
    if not message or not chat:
        return
    target = await resolve_target(update, context, allow_music_lookup=True)
    if not target:
        return
    username = getattr(target, "username", None)
    rank = await get_rank(target.id, chat.id)
    messages = await get_user_messages(target.id)
    rank_text = f"<tg-spoiler>{html_escape(rank)}</tg-spoiler>" if target.id == OWNER_ID else html_escape(rank)
    text = (
        f"• ID : <code>{target.id}</code>\n"
        f"• USE : {html_escape('@' + username if username else '')}\n"
        f"• STE : {rank_text}\n"
        f"• MSG : {messages}"
    )
    await message.reply_text(text, parse_mode="HTML")


async def moderation_expiry_loop(application):
    while True:
        try:
            expired = await get_expired_sanctions(datetime.now(timezone.utc))
            for chat_id, user_id in expired["mutes"]:
                await delete_sanction("bot_mutes", chat_id, user_id)
            for chat_id, user_id in expired["restrictions"]:
                try:
                    await application.bot.restrict_chat_member(
                        chat_id=chat_id, user_id=user_id, permissions=FULL_PERMISSIONS
                    )
                except Exception:
                    logger.warning("Could not auto-unrestrict %s in %s", user_id, chat_id, exc_info=True)
                    continue
                await delete_sanction("restrictions", chat_id, user_id)
            for chat_id, user_id in expired["bans"]:
                try:
                    await application.bot.unban_chat_member(
                        chat_id=chat_id, user_id=user_id, only_if_banned=False
                    )
                except Exception:
                    logger.warning("Could not auto-unban %s in %s", user_id, chat_id, exc_info=True)
                    continue
                await delete_sanction("moderation_bans", chat_id, user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Moderation expiry loop failed")
        await asyncio.sleep(5)


async def repetition_action_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return
    chat = query.message.chat
    actor = query.from_user
    data = (query.data or "").split(":")
    if len(data) != 3 or data[0] != "repetition_punish" or data[1] not in ("mute", "restrict"):
        return
    try:
        target_id = int(data[2])
    except (TypeError, ValueError):
        return
    if await _get_level(actor.id, chat.id) < 3:
        await query.answer("❌ ليس لديك الصلاحية.", show_alert=True)
        return
    if await get_warning_count(chat.id, target_id) < 3:
        await query.answer("❌ لم يعد لديه 3 إنذارات.", show_alert=True)
        return
    if target_id == OWNER_ID:
        await query.answer("❌ لا يمكن تطبيق العقوبة على المطور الأساسي.", show_alert=True)
        return
    if await _get_level(target_id, chat.id) >= await _get_level(actor.id, chat.id):
        await query.answer("❌ لا يمكنك معاقبة شخص رتبته مساوية أو أعلى منك.", show_alert=True)
        return
    try:
        target = await context.bot.get_chat(target_id)
    except Exception:
        await query.answer("❌ تعذر العثور على المستخدم.", show_alert=True)
        return
    duration = await get_repetition_punishment_duration(chat.id)
    until_time = datetime.now(timezone.utc) + timedelta(seconds=duration)
    if data[1] == "mute":
        await save_sanction("bot_mutes", chat.id, target, until_time, "التكرار", context.bot.id)
    else:
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_time,
            )
        except Exception:
            logger.exception("Failed to apply repetition restriction")
            await query.answer("❌ تعذر تطبيق العقوبة.", show_alert=True)
            return
        await save_sanction("restrictions", chat.id, target, until_time, "التكرار", context.bot.id)
    await clear_warnings(chat.id, target_id)
    try:
        from handlers.repetition import reset_repetition_messages
        reset_repetition_messages(chat.id, target_id)
    except Exception:
        logger.debug("Could not reset repetition memory", exc_info=True)
    await query.answer("تم اختيار العقوبة وتصفير إنذاراته.")
    try:
        await query.edit_message_text("• ✅ تم اختيار العقوبة المناسبة بنجاح .")
    except Exception:
        logger.debug("Could not edit repetition punishment message", exc_info=True)
