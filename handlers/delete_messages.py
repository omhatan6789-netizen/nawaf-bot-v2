from telegram import Update
from telegram.ext import ContextTypes

from database.roles import get_rank_level


async def delete_messages(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return
    if chat.type not in ("group", "supergroup"):
        return

    rank = await get_rank_level(user.id, chat.id)
    text = (message.text or "").strip()

    # مسح بالرد على رسالة.
    if text == "مسح":
        target = message.reply_to_message
        if not target:
            return

        # الأدمن وفوق يحذف أي رسالة، والعضو يحذف رسالته فقط.
        if rank < 2:
            if not target.from_user or target.from_user.id != user.id:
                return

        # ابدأ بأمر المسح نفسه، ثم الرسالة المستهدفة.
        try:
            await context.bot.delete_message(
                chat_id=chat.id,
                message_id=message.message_id,
            )
        except Exception:
            pass
        try:
            await context.bot.delete_message(
                chat_id=chat.id,
                message_id=target.message_id,
            )
        except Exception:
            pass
        return

    if not text.startswith("مسح"):
        return

    number_text = text[3:].strip()
    if not number_text.isdigit():
        return

    amount = int(number_text)
    if amount < 3:
        if rank >= 2:
            await message.reply_text("الحد الادنى 3 رسائل .")
        return
    if amount > 800:
        if rank >= 2:
            await message.reply_text("الحد الأقصى 800 رسالة .")
        return
    if rank < 2:
        return

    # حذف من الأحدث إلى الأقدم: أمر المسح أولًا، ثم الرسائل السابقة.
    try:
        await context.bot.delete_message(
            chat_id=chat.id,
            message_id=message.message_id,
        )
    except Exception:
        pass

    remaining_ids = list(
        range(message.message_id - 1, message.message_id - amount - 1, -1)
    )
    for offset in range(0, len(remaining_ids), 100):
        batch = remaining_ids[offset:offset + 100]
        try:
            await context.bot.delete_messages(
                chat_id=chat.id,
                message_ids=batch,
            )
        except Exception:
            # بعض الرسائل قد تكون قديمة أو غير قابلة للحذف؛ تابع الباقي.
            for message_id in batch:
                try:
                    await context.bot.delete_message(
                        chat_id=chat.id,
                        message_id=message_id,
                    )
                except Exception:
                    pass
