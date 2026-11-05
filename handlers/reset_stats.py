from __future__ import annotations

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.activity import flush_pending_activity
from database.points import flush_pending_points
from database.pool import get_pool
from database.roles import OWNER_ID


def _confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("تأكيد التصفير", callback_data=f"statsreset:yes:{action}")],
        [InlineKeyboardButton("إلغاء", callback_data="statsreset:no")],
    ])


async def _ask_reset(update: Update, action: str, text: str) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    if user.id != OWNER_ID:
        await message.reply_text("❌ هذا الأمر مخصص للمالك فقط.")
        return
    if action == "active_local" and (
        not update.effective_chat or update.effective_chat.type not in ("group", "supergroup")
    ):
        await message.reply_text("❌ استخدم هذا الأمر داخل القروب المطلوب.")
        return
    await message.reply_text(text, reply_markup=_confirm_keyboard(action))


async def reset_active_local_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask_reset(
        update, "active_local",
        "⚠️ بتصفر توب المتفاعلين في هذا القروب فقط. متأكد؟",
    )


async def reset_active_global_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask_reset(
        update, "active_global",
        "⚠️ بتصفر توب المتفاعلين العام في كل القروبات. متأكد؟",
    )


async def reset_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask_reset(
        update, "points",
        "⚠️ بتصفر نقاط جميع المستخدمين فقط، بدون تغيير أي بيانات ثانية. متأكد؟",
    )


async def my_messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    # Flush the short in-memory batch first so the displayed total is current.
    await flush_pending_activity()
    count = await get_pool().fetchval(
        "SELECT COALESCE(messages, 0) FROM users WHERE user_id=$1",
        user.id,
    )
    # The current group text message is tracked later in the update pipeline.
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup") and not user.is_bot:
        count = int(count or 0) + 1
    await message.reply_text(f"• رسائلك ~ {int(count or 0):,}")


async def stats_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    if not query.from_user or query.from_user.id != OWNER_ID:
        await query.answer("هذا الزر مخصص للمالك فقط.", show_alert=True)
        return

    data = query.data or ""
    if data == "statsreset:no":
        await query.answer("تم الإلغاء")
        await query.edit_message_text("تم إلغاء التصفير.")
        return
    if not data.startswith("statsreset:yes:"):
        await query.answer()
        return

    action = data.removeprefix("statsreset:yes:")
    pool = get_pool()
    try:
        if action == "active_local":
            chat = query.message.chat if query.message else None
            if not chat or chat.type not in ("group", "supergroup"):
                await query.answer("تعذر تحديد القروب.", show_alert=True)
                return
            await flush_pending_activity()
            result = await pool.execute(
                "UPDATE chat_activity SET message_count=0, updated_at=NOW() WHERE chat_id=$1",
                chat.id,
            )
            message = "✅ تم تصفير توب المتفاعلين في هذا القروب."
        elif action == "active_global":
            await flush_pending_activity()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE users SET activity_messages=0, updated_at=NOW()"
                    )
                    await conn.execute(
                        "UPDATE chat_activity SET message_count=0, updated_at=NOW()"
                    )
            message = "✅ تم تصفير توب المتفاعلين العام في كل القروبات."
        elif action == "points":
            await flush_pending_points()
            await pool.execute("UPDATE points SET points=0")
            message = "✅ تم تصفير نقاط جميع المستخدمين فقط."
        else:
            await query.answer("طلب غير معروف.", show_alert=True)
            return
    except Exception:
        await query.answer("تعذر تنفيذ التصفير، راجع سجلات البوت.", show_alert=True)
        raise

    await query.answer("تم التصفير")
    await query.edit_message_text(message)
