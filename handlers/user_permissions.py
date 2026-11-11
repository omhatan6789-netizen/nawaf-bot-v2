from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from handlers.target_lookup import resolve_message_user

from database.roles import (
    OWNER_ID, is_primary_developer, is_secondary_developer,
    get_rank, set_user_permission,
)

PERMISSION_LEVELS = {
    "عضو": 0,
    "مميز": 1,
    "ادمن": 2,
    "ادمن اساسي": 3,
    "المالك": 5,
}


async def can_manage_permissions(user_id: int) -> bool:
    if await is_primary_developer(user_id) or await is_secondary_developer(user_id):
        return True
    return await get_rank(user_id) == "المالك"


async def get_permission_level(user_id: int) -> int:
    if await is_primary_developer(user_id):
        return 7
    if await is_secondary_developer(user_id):
        return 6
    return PERMISSION_LEVELS.get(await get_rank(user_id), 0)


async def can_manage_target(actor_id: int, target_id: int) -> bool:
    actor_level = await get_permission_level(actor_id)
    target_level = await get_permission_level(target_id)
    return actor_id != target_id and actor_level >= 5 and target_level < actor_level


async def get_permission_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await resolve_message_user(update, context, token_index=-1)


async def permission_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    if not message or not actor:
        return
    text = (message.text or "").strip()
    parts = text.split()
    if not parts or parts[0] not in ("منع", "سماح"):
        return
    action = parts[0]

    if not await can_manage_permissions(actor.id):
        await message.reply_text("❌ هذا الأمر للمطور والمالك فقط.")
        return

    if message.reply_to_message:
        if len(parts) < 2:
            await message.reply_text("❌ اكتب اسم الأمر.\n\nمثال:\nمنع حظر")
            return
        target = message.reply_to_message.from_user
        command = " ".join(parts[1:]).strip()
    else:
        if len(parts) < 3:
            await message.reply_text(
                "❌ الاستخدام:\n\n"
                "منع حظر @username\n"
                "منع حظر 123456789\n\n"
                "أو بالرد على الشخص:\n"
                "منع حظر"
            )
            return
        command = " ".join(parts[1:-1]).strip()
        target = await get_permission_target(update, context)
        if not target:
            await message.reply_text("❌ لم أستطع العثور على الشخص.")
            return

    if not command:
        await message.reply_text("❌ اكتب اسم الأمر الذي تريد منعه أو السماح به.")
        return
    if not target:
        return
    if target.id == actor.id:
        await message.reply_text("❌ لا يمكنك تعديل صلاحيات نفسك.")
        return
    if await is_primary_developer(target.id):
        await message.reply_text("❌ لا يمكنك تعديل صلاحيات Dev الأساسي.")
        return
    if not await can_manage_target(actor.id, target.id):
        await message.reply_text("❌ لا يمكنك تعديل صلاحيات هذا الشخص.")
        return

    await set_user_permission(
        update.effective_chat.id, target.id, command, action == "سماح"
    )
    if action == "منع":
        await message.reply_text(
            f'🚫 تم منع <a href="tg://user?id={int(target.id)}">{escape(str(target.first_name or target.id))}</a> من الأمر:\n'
            f"↤︎ {command}",
            parse_mode="HTML",
        )
    else:
        await message.reply_text(
            f'✅ تم السماح لـ <a href="tg://user?id={int(target.id)}">{escape(str(target.first_name or target.id))}</a> بالأمر:\n'
            f"↤︎ {command}",
            parse_mode="HTML",
        )
