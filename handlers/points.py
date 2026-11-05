import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from database.timing import timed

from database.points import (
    add_points,
    deduct_points,
    get_points,
    get_points_leaderboard,
    sell_points_for_messages,
    flush_pending_points,
)

logger = logging.getLogger("nawaf.performance")

async def _timed_reply(message, label: str, *args, **kwargs):
    started = time.perf_counter()
    result = await message.reply_text(*args, **kwargs)
    logger.info("PERF %s duration_ms=%.1f", label, (time.perf_counter() - started) * 1000)
    return result

OWNER_ID = 8453977662
POINTS_PER_MESSAGE = 10


def _get_user_id_from_update(update: Update) -> int | None:
    message = update.message
    if not message:
        return None
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    return update.effective_user.id if update.effective_user else None


async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمالك فقط.")
        return

    parts = (update.message.text or "").strip().split()
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n\n"
            "اضف 500\n\n"
            "ويُفضل استخدام الأمر بالرد على الشخص."
        )
        return
    try:
        amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("❌ عدد النقاط غير صحيح.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ يجب أن يكون عدد النقاط أكبر من صفر.")
        return

    target_id = _get_user_id_from_update(update)
    if target_id is None:
        return
    new_points = await add_points(target_id, amount)

    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_name = update.message.reply_to_message.from_user.first_name or "المستخدم"
        await update.message.reply_text(
            f"✅ تمت إضافة {amount} نقطة إلى {target_name}.\n\n"
            f"🏆 نقاطه الآن: {new_points}"
        )
    else:
        await update.message.reply_text(
            f"✅ تمت إضافة {amount} نقطة لك.\n\n"
            f"🏆 نقاطك الآن: {new_points}"
        )


async def remove_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمالك فقط.")
        return

    parts = (update.message.text or "").strip().split()
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n\n"
            "خصم 500\n\n"
            "ويجب استخدام الأمر بالرد على الشخص."
        )
        return
    try:
        amount = int(parts[1])
    except ValueError:
        await update.message.reply_text("❌ عدد النقاط غير صحيح.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ يجب أن يكون عدد النقاط أكبر من صفر.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ يجب استخدام الأمر بالرد على الشخص.")
        return

    target_user = update.message.reply_to_message.from_user
    if not target_user:
        return
    remaining_points = await deduct_points(target_user.id, amount)
    if remaining_points is None:
        current_points = await get_points(target_user.id)
        await update.message.reply_text(
            "❌ لا يمكن الخصم.\n\n"
            f"🏆 نقاطه الحالية: {current_points}\n"
            f"💰 المطلوب خصمه: {amount}"
        )
        return

    target_name = target_user.first_name or "المستخدم"
    await update.message.reply_text(
        f"✅ تم خصم {amount} نقطة من {target_name}.\n\n"
        f"🏆 نقاطه المتبقية: {remaining_points}"
    )


async def sell_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    parts = (update.message.text or "").strip().split()
    if len(parts) != 3:
        await update.message.reply_text(
            "❌ الاستخدام الصحيح:\n\n"
            "بيع نقاطي 200"
        )
        return
    try:
        amount = int(parts[2])
    except ValueError:
        await update.message.reply_text("❌ عدد النقاط غير صحيح.")
        return
    if amount <= 0:
        await update.message.reply_text("❌ يجب أن يكون عدد النقاط أكبر من صفر.")
        return

    result = await sell_points_for_messages(
        update.effective_user.id, amount, POINTS_PER_MESSAGE
    )
    if result is None:
        current_points = await get_points(update.effective_user.id)
        await update.message.reply_text(
            "❌ ما عندك نقاط كافية.\n\n"
            f"🏆 نقاطك الحالية: {current_points}\n"
            f"💰 المطلوب: {amount}"
        )
        return

    remaining_points, messages_to_add = result
    await update.message.reply_text(
        f"✅ تم بيع {amount} نقطة.\n\n"
        f"💬 حصلت على {messages_to_add} رسالة.\n"
        f"🏆 نقاطك المتبقية: {remaining_points}"
    )


@timed("handler.my_points")
async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    points = await get_points(update.effective_user.id)
    await _timed_reply(update.message, "handler.my_points.telegram_reply", f"🏆 نقاطك الحالية: {points}")


@timed("handler.top_points")
async def top_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    started = time.perf_counter()
    rows = await get_points_leaderboard(10)
    fetched = time.perf_counter()
    logger.info(
        "PERF handler.top_points.fetch_duration_ms=%.1f",
        (fetched - started) * 1000,
    )

    if not rows:
        send_started = time.perf_counter()
        await update.message.reply_text("❌ لا يوجد ترتيب حتى الآن")
        logger.info(
            "PERF handler.top_points.telegram_reply_duration_ms=%.1f",
            (time.perf_counter() - send_started) * 1000,
        )
        return

    format_started = time.perf_counter()
    lines = ["🏆 ترتيب اللاعبين", ""]
    for place, row in enumerate(rows, 1):
        name = row["first_name"] or "مستخدم"
        lines.append(f"{place} - {name} : {row['points'] or 0} نقطة")
    response_text = "\n".join(lines)
    formatted = time.perf_counter()
    logger.info(
        "PERF handler.top_points.format_duration_ms=%.1f",
        (formatted - format_started) * 1000,
    )

    await update.message.reply_text(response_text)
    logger.info(
        "PERF handler.top_points.telegram_reply_duration_ms=%.1f",
        (time.perf_counter() - formatted) * 1000,
    )
