"""Profile cards and per-admin group replies.

The public command wording and response text match the legacy handlers.
All database work is asyncpg-only.
"""
from __future__ import annotations

import html
import logging
from typing import Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMemberStatus,
    ChatType,
)
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database.profile_replies import (
    get_saved_developer,
    save_developer,
    ensure_group_settings,
    get_group_settings,
    save_group_owner,
    set_admin_replies_status,
    save_admin_reply,
    get_admin_reply_by_user,
    get_admin_reply_by_name,
    delete_admin_reply,
    delete_all_admin_replies,
    get_all_admin_replies,
    get_group_user_id_by_username,
)
from database.roles import get_rank_level

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
PENDING_KEYS = ("profile_waiting", "profile_waiting_type")


def is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


def html_mention(user: Any) -> str:
    if not user:
        return ""
    name = html.escape(getattr(user, "first_name", None) or "المستخدم")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def send_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: Any,
    caption: str,
) -> None:
    """Send the user's latest profile photo, or text if no photo is available."""
    message = update.effective_message
    if not user or not message:
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            user.first_name or "الحساب",
            url=f"tg://user?id={user.id}",
        )
    ]])

    photo_file_id = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            photo_file_id = photos.photos[0][-1].file_id
    except Exception:
        logger.exception("تعذر جلب صورة المستخدم %s", user.id)

    if photo_file_id:
        await message.reply_photo(
            photo=photo_file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    else:
        await message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


async def get_user_info(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    try:
        return await context.bot.get_chat(int(user_id))
    except Exception:
        return None


async def is_group_admin_or_above(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return False
    if user.id == OWNER_ID:
        return True
    try:
        if await get_rank_level(user.id, chat.id) >= 2:
            return True
    except Exception:
        logger.exception("تعذر فحص رتبة المستخدم %s", user.id)
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def is_owner_or_above(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat:
        return False
    if user.id == OWNER_ID:
        return True
    try:
        if await get_rank_level(user.id, chat.id) >= 5:
            return True
    except Exception:
        logger.exception("تعذر فحص رتبة المستخدم %s", user.id)
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status == ChatMemberStatus.OWNER
    except Exception:
        return False


async def get_group_user_from_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    username: str,
):
    chat = update.effective_chat
    username = (username or "").strip()
    if not chat or not username.startswith("@"):
        return None
    clean = username[1:].strip().lower()
    if not clean or " " in clean:
        return None

    user_id = await get_group_user_id_by_username(clean)
    if not user_id:
        return None
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
    except Exception as exc:
        logger.warning("تعذر التحقق من عضوية %s: %s", username, exc)
        return None
    if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        return None
    return member.user


def clear_profile_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in PENDING_KEYS:
        context.user_data.pop(key, None)


def set_profile_pending(context: ContextTypes.DEFAULT_TYPE, pending_type: str) -> None:
    clear_profile_pending(context)
    context.user_data["profile_waiting"] = True
    context.user_data["profile_waiting_type"] = pending_type


def get_profile_pending(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not context.user_data.get("profile_waiting"):
        return None
    return context.user_data.get("profile_waiting_type")


async def developer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    developer_id, _developer_username = await get_saved_developer()
    developer = await get_user_info(context, developer_id)
    if not developer:
        developer = update.effective_user
    bot = await context.bot.get_me()
    bot_name = html.escape(bot.first_name or "البوت")
    bio = html.escape(getattr(developer, "bio", None) or "لا يوجد بايو.")
    caption = (
        f"Dev Bot ↦ {bot_name}\n"
        f"━━━━━━━━━━━━━━\n"
        f"Dev ↦ {html_mention(developer)}\n"
        f"Bio ↦ {bio}"
    )
    await send_profile(update, context, developer, caption)
    raise ApplicationHandlerStop()


async def change_developer_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("• هذا الأمر للمطور الأساسي فقط.")
        raise ApplicationHandlerStop()
    if not is_group(update):
        await update.message.reply_text("• هذا الأمر يستخدم داخل المجموعة.")
        raise ApplicationHandlerStop()
    set_profile_pending(context, "developer_username")
    await update.message.reply_text("حسنًا، ارسل يوزر المطور الجديد.")
    raise ApplicationHandlerStop()


async def change_owner_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_group(update):
        await update.message.reply_text("• هذا الأمر يستخدم داخل المجموعة.")
        raise ApplicationHandlerStop()
    if not await is_owner_or_above(update, context):
        await update.message.reply_text("• هذا الأمر للمالك ومن فوق.")
        raise ApplicationHandlerStop()
    set_profile_pending(context, "owner_username")
    await update.message.reply_text("حسنًا، ارسل يوزر المالك الجديد.")
    raise ApplicationHandlerStop()


async def receive_developer_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _receive_profile_username(update, context, "developer_username")


async def receive_owner_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _receive_profile_username(update, context, "owner_username")


async def _receive_profile_username(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    pending_type: str,
) -> None:
    message = update.message
    if not message:
        clear_profile_pending(context)
        return
    value = (message.text or "").strip()
    clear_profile_pending(context)

    if not value.startswith("@") or " " in value:
        await message.reply_text("• اليوزر غير صحيح، تم إلغاء العملية.")
        raise ApplicationHandlerStop()

    target = await get_group_user_from_username(update, context, value)
    if not target:
        await message.reply_text("• اليوزر غير موجود في المجموعة، تم إلغاء العملية.")
        raise ApplicationHandlerStop()

    if pending_type == "developer_username":
        await save_developer(target.id, value)
        await message.reply_text("• تم تغيير يوزر المطور بنجاح.")
    else:
        await save_group_owner(update.effective_chat.id, target.id, value)
        await message.reply_text("• تم تغيير يوزر المالك بنجاح.")
    raise ApplicationHandlerStop()


async def get_default_group_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return None
    try:
        administrators = await context.bot.get_chat_administrators(chat.id)
    except Exception:
        return None
    for member in administrators:
        if member.status == ChatMemberStatus.OWNER:
            return member.user
    return None


async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_group(update):
        await update.message.reply_text("• هذا الأمر يستخدم داخل المجموعة.")
        raise ApplicationHandlerStop()

    chat = update.effective_chat
    try:
        await ensure_group_settings(chat.id)
        settings = await get_group_settings(chat.id)
    except Exception as exc:
        logger.exception("خطأ في إعدادات المالك للمجموعة %s", chat.id)
        await update.message.reply_text(f"• حدث خطأ أثناء جلب بيانات المالك.\n\n{exc}")
        raise ApplicationHandlerStop()

    owner = None
    if settings and settings["owner_user_id"]:
        owner = await get_user_info(context, settings["owner_user_id"])
    if not owner:
        owner = await get_default_group_owner(update, context)
    if not owner:
        await update.message.reply_text("• تعذر العثور على مالك المجموعة.")
        raise ApplicationHandlerStop()

    group_name = html.escape(chat.title or "المجموعة")
    bio = html.escape(getattr(owner, "bio", None) or "لا يوجد بايو.")
    caption = (
        f"Owner group ↦ {group_name}\n"
        f"━━━━━━━━━━━━━━\n"
        f"USE ↤ {html_mention(owner)}\n"
        f"bio ↤ {bio}"
    )
    try:
        await send_profile(update, context, owner, caption)
    except Exception as exc:
        logger.exception("خطأ أثناء إرسال بروفايل المالك")
        await update.message.reply_text(f"• حدث خطأ أثناء إرسال بروفايل المالك.\n\n{exc}")
    raise ApplicationHandlerStop()


async def add_my_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_group(update):
        await update.message.reply_text("• هذا الأمر يستخدم داخل المجموعة.")
        raise ApplicationHandlerStop()
    if not await is_group_admin_or_above(update, context):
        await update.message.reply_text("• هذا الأمر للادمن ومن فوق.")
        raise ApplicationHandlerStop()

    settings = await get_group_settings(update.effective_chat.id)
    if not settings or not settings["admin_replies_enabled"]:
        await update.message.reply_text("• ردود الادمن غير مفعلة في هذه المجموعة.")
        raise ApplicationHandlerStop()

    old_reply = await get_admin_reply_by_user(update.effective_chat.id, update.effective_user.id)
    if old_reply:
        await update.message.reply_text(
            f"عندك رد قديم اسمه ({old_reply}) اكتب حذف ردي لحذفه وإضافة رد جديد!"
        )
        raise ApplicationHandlerStop()

    set_profile_pending(context, "admin_reply_name")
    await update.message.reply_text("حسنًا، ارسل كلمة الرد")
    raise ApplicationHandlerStop()


async def receive_my_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        clear_profile_pending(context)
        return
    value = (message.text or "").strip()
    clear_profile_pending(context)
    if not value or "\n" in value:
        await message.reply_text("• اسم الرد غير صحيح، تم إلغاء العملية.")
        raise ApplicationHandlerStop()

    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    old_reply = await get_admin_reply_by_user(chat_id, user_id)
    if old_reply:
        await message.reply_text(
            f"عندك رد قديم اسمه ({old_reply}) اكتب حذف ردي لحذفه وإضافة رد جديد!"
        )
        raise ApplicationHandlerStop()

    existing = await get_admin_reply_by_name(chat_id, value)
    if existing:
        await message.reply_text("• اسم الرد مستخدم بالفعل، تم إلغاء العملية.")
        raise ApplicationHandlerStop()

    try:
        await save_admin_reply(chat_id, user_id, value)
    except Exception:
        logger.exception("خطأ في حفظ رد الادمن")
        await message.reply_text("• حدث خطأ أثناء إضافة الرد، تم إلغاء العملية.")
        raise ApplicationHandlerStop()

    await message.reply_text("تم إضافة ردك الجديد!\nاكتب اسم الرد في المجموعة لتجربته.")
    raise ApplicationHandlerStop()


async def delete_my_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not is_group(update):
        raise ApplicationHandlerStop()
    if not await is_group_admin_or_above(update, context):
        raise ApplicationHandlerStop()
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    old_reply = await get_admin_reply_by_user(chat_id, user_id)
    if not old_reply:
        await update.message.reply_text("• ما عندك رد ادمن.")
        raise ApplicationHandlerStop()
    await delete_admin_reply(chat_id, user_id)
    await update.message.reply_text("• تم حذف ردك.")
    raise ApplicationHandlerStop()


async def delete_other_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_group(update):
        return
    if not await is_owner_or_above(update, context):
        raise ApplicationHandlerStop()
    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        raise ApplicationHandlerStop()
    await delete_admin_reply(update.effective_chat.id, reply.from_user.id)
    await update.message.reply_text("تم حذف رده.")
    raise ApplicationHandlerStop()


async def admin_replies_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not is_group(update):
        raise ApplicationHandlerStop()
    rows = await get_all_admin_replies(update.effective_chat.id)
    result = "• ردود الاعضاء في المجموعة :\n\n"
    if not rows:
        await update.message.reply_text(result + "لا يوجد ردود ادمن.", parse_mode="HTML")
        raise ApplicationHandlerStop()

    for number, (admin_id, reply_name) in enumerate(rows, 1):
        admin = await get_user_info(context, admin_id)
        mention = html_mention(admin) if admin else f'<a href="tg://user?id={admin_id}">عضو</a>'
        result += f"{number} - 〖 {html.escape(reply_name)} 〗- {mention}\n"
    await update.message.reply_text(result, parse_mode="HTML")
    raise ApplicationHandlerStop()


async def enable_admin_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_admin_replies(update, context, True)


async def disable_admin_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_admin_replies(update, context, False)


async def _set_admin_replies(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    enabled: bool,
) -> None:
    if not update.message:
        return
    if not is_group(update):
        raise ApplicationHandlerStop()
    if not await is_owner_or_above(update, context):
        await update.message.reply_text("• هذا الأمر للمالك ومن فوق.")
        raise ApplicationHandlerStop()
    await set_admin_replies_status(update.effective_chat.id, enabled)
    await update.message.reply_text(
        "• تم تفعيل ردود الادمن." if enabled else "• تم تعطيل ردود الادمن."
    )
    raise ApplicationHandlerStop()


async def delete_all_admin_replies_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return
    if not is_group(update):
        raise ApplicationHandlerStop()
    if not await is_owner_or_above(update, context):
        await update.message.reply_text("• هذا الأمر للمالك ومن فوق.")
        raise ApplicationHandlerStop()
    await delete_all_admin_replies(update.effective_chat.id)
    await update.message.reply_text("• تم حذف جميع ردود الادمن.")
    raise ApplicationHandlerStop()


async def check_admin_profile_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text or not is_group(update):
        return
    reply_name = message.text.strip()
    if not reply_name:
        return
    row = await get_admin_reply_by_name(update.effective_chat.id, reply_name)
    if not row:
        return
    admin = await get_user_info(context, row[0])
    if not admin:
        return
    bio = html.escape(getattr(admin, "bio", None) or "لا يوجد بايو.")
    caption = f"USE ↤ {html_mention(admin)}\nBio ↤ {bio}"
    await send_profile(update, context, admin, caption)
    raise ApplicationHandlerStop()


async def profile_reply_pending_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return
    pending_type = get_profile_pending(context)
    if not pending_type:
        return
    if pending_type == "developer_username":
        await receive_developer_username(update, context)
    elif pending_type == "owner_username":
        await receive_owner_username(update, context)
    elif pending_type == "admin_reply_name":
        await receive_my_admin_reply(update, context)
    else:
        clear_profile_pending(context)
        raise ApplicationHandlerStop()
