"""Telegram Stars subscriptions for individual groups."""
from __future__ import annotations

import html
import logging
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes, ApplicationHandlerStop
from database.pool import get_pool

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
SESSIONS: dict[int, dict] = {}


def _back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="stars:panel")]])


async def _settings():
    return await get_pool().fetchrow(
        "SELECT price_stars, duration_days, sales_enabled FROM stars_subscription_settings WHERE id=1"
    )


async def _panel_text():
    row = await _settings()
    active = "مفعّل ✅" if row["sales_enabled"] else "متوقف ⛔"
    return (
        "⭐️ اشتراكات القروبات\n━━━━━━━━━━━━\n\n"
        f"💰 السعر: {row['price_stars']} نجمة\n"
        f"⏳ المدة: {row['duration_days']} يوم\n"
        f"🛒 استقبال المدفوعات: {active}\n\n"
        "لإنشاء فاتورة لقروب، اكتب داخل القروب: اشتراك القروب"
    )


async def _panel_keyboard():
    row = await _settings()
    toggle = "⛔ إيقاف استقبال الدفع" if row["sales_enabled"] else "✅ تفعيل استقبال الدفع"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 تغيير السعر", callback_data="stars:price"),
         InlineKeyboardButton("⏳ تغيير المدة", callback_data="stars:duration")],
        [InlineKeyboardButton(toggle, callback_data="stars:toggle")],
        [InlineKeyboardButton("📋 اشتراكات القروبات", callback_data="stars:list")],
        [InlineKeyboardButton("إيقاف اشتراك قروب", callback_data="stars:deactivate")],
        [InlineKeyboardButton("↩️ رجوع للقائمة الرئيسية", callback_data="devpanel:menu")],
    ])


async def open_stars_panel(target, user_id: int):
    if int(user_id) != OWNER_ID:
        return
    if hasattr(target, "edit_message_text"):
        await target.edit_message_text(await _panel_text(), reply_markup=await _panel_keyboard())
    else:
        await target.reply_text(await _panel_text(), reply_markup=await _panel_keyboard())


async def stars_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    if query.from_user.id != OWNER_ID:
        await query.answer()
        return
    data = query.data or ""
    await query.answer()
    if data == "stars:panel":
        await open_stars_panel(query, query.from_user.id)
    elif data in ("stars:price", "stars:duration", "stars:deactivate"):
        action = {"stars:price": "price", "stars:duration": "duration", "stars:deactivate": "deactivate"}[data]
        SESSIONS[OWNER_ID] = {"action": action}
        prompts = {
            "price": "ارسل السعر الجديد بالنجوم (من 1 إلى 100000).",
            "duration": "ارسل مدة الاشتراك بالأيام (من 1 إلى 3650).",
            "deactivate": "ارسل ID القروب لإيقاف اشتراكه.",
        }
        await query.edit_message_text(prompts[action], reply_markup=_back())
    elif data == "stars:toggle":
        await get_pool().execute(
            "UPDATE stars_subscription_settings SET sales_enabled = NOT sales_enabled, updated_at=NOW() WHERE id=1"
        )
        await open_stars_panel(query, query.from_user.id)
    elif data == "stars:list":
        rows = await get_pool().fetch(
            """SELECT s.chat_id, COALESCE(c.title, s.chat_id::text) AS title,
                      s.expires_at, (s.expires_at > NOW()) AS active
               FROM stars_group_subscriptions s
               LEFT JOIN developer_bot_chats c ON c.chat_id=s.chat_id
               ORDER BY s.expires_at DESC LIMIT 20"""
        )
        lines = ["📋 اشتراكات القروبات", "━━━━━━━━━━━━", ""]
        if not rows:
            lines.append("ما فيه اشتراكات مسجلة.")
        for row in rows:
            state = "نشط ✅" if row["active"] else "منتهي ⛔"
            lines.append(
                f"• {html.escape(str(row['title']))}\n"
                f"  ID: <code>{row['chat_id']}</code>\n"
                f"  الحالة: {state}\n"
                f"  الانتهاء: {row['expires_at'].strftime('%Y-%m-%d %H:%M')} UTC\n"
            )
        await query.edit_message_text(
            "\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع", callback_data="stars:panel")]]),
        )


async def stars_panel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or user.id != OWNER_ID or not chat or chat.type != "private":
        return
    session = SESSIONS.get(OWNER_ID)
    if not session:
        return
    action = session.get("action")
    value = (msg.text or "").strip()
    if action in ("price", "duration"):
        if not value.isdigit():
            await msg.reply_text("ارسل رقمًا صحيحًا فقط.", reply_markup=_back())
            raise ApplicationHandlerStop
        number = int(value)
        if action == "price":
            if not 1 <= number <= 100000:
                await msg.reply_text("السعر لازم يكون بين 1 و100000 نجمة.", reply_markup=_back())
                raise ApplicationHandlerStop
            await get_pool().execute(
                "UPDATE stars_subscription_settings SET price_stars=$1, updated_at=NOW() WHERE id=1", number
            )
            result = f"تم تغيير السعر إلى {number} نجمة ⭐️"
        else:
            if not 1 <= number <= 3650:
                await msg.reply_text("المدة لازم تكون بين يوم واحد و3650 يوم.", reply_markup=_back())
                raise ApplicationHandlerStop
            await get_pool().execute(
                "UPDATE stars_subscription_settings SET duration_days=$1, updated_at=NOW() WHERE id=1", number
            )
            result = f"تم تغيير مدة الاشتراك إلى {number} يوم ⏳"
    elif action == "deactivate":
        if not value.lstrip("-").isdigit():
            await msg.reply_text("ارسل ID قروب صحيح.", reply_markup=_back())
            raise ApplicationHandlerStop
        status = await get_pool().execute(
            "UPDATE stars_group_subscriptions SET expires_at=NOW() WHERE chat_id=$1", int(value)
        )
        result = "تم إيقاف اشتراك القروب ✅" if status.endswith("1") else "ما لقيت اشتراك لهذا القروب."
    else:
        return
    SESSIONS.pop(OWNER_ID, None)
    await msg.reply_text(result, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("فتح لوحة الاشتراكات", callback_data="stars:panel")]
    ]))
    raise ApplicationHandlerStop


async def stars_group_invoice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or not chat or chat.type not in ("group", "supergroup"):
        return
    if user.id != OWNER_ID:
        raise ApplicationHandlerStop
    settings = await _settings()
    if not settings["sales_enabled"]:
        await msg.reply_text("استقبال مدفوعات الاشتراكات متوقف حاليًا من لوحة التحكم.")
        raise ApplicationHandlerStop
    payload = uuid.uuid4().hex
    await get_pool().execute(
        """INSERT INTO stars_subscription_orders
           (payload, chat_id, created_by, amount_stars, duration_days, status)
           VALUES($1,$2,$3,$4,$5,'pending')""",
        payload, chat.id, user.id, int(settings["price_stars"]), int(settings["duration_days"]),
    )
    try:
        await context.bot.send_invoice(
            chat_id=chat.id,
            title="اشتراك بوت نواف",
            description=f"تفعيل البوت في {chat.title or 'هذا القروب'} لمدة {settings['duration_days']} يوم",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"اشتراك {settings['duration_days']} يوم", int(settings["price_stars"]))],
        )
    except Exception:
        await get_pool().execute(
            "UPDATE stars_subscription_orders SET status='failed' WHERE payload=$1", payload
        )
        logger.exception("Failed to send Stars invoice to group %s", chat.id)
        await msg.reply_text("تعذر إرسال فاتورة النجوم. تأكد أن البوت يستطيع إرسال الرسائل في القروب.")
    raise ApplicationHandlerStop


async def stars_precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query:
        return
    try:
        order = await get_pool().fetchrow(
            """SELECT chat_id, amount_stars, status,
                      (created_at > NOW() - INTERVAL '2 hours') AS fresh
               FROM stars_subscription_orders WHERE payload=$1""",
            query.invoice_payload,
        )
        settings = await _settings()
        ok = bool(
            order and order["status"] in ("pending", "paid") and order["fresh"]
            and query.currency == "XTR"
            and int(query.total_amount) == int(order["amount_stars"])
            and settings["sales_enabled"]
        )
        await query.answer(
            ok=ok,
            error_message=None if ok else "الفاتورة غير صالحة أو انتهت صلاحيتها. اطلب فاتورة جديدة من إدارة القروب.",
        )
    except Exception:
        logger.exception("Stars pre-checkout validation failed")
        await query.answer(ok=False, error_message="تعذر التحقق من الفاتورة، حاول مرة ثانية.")


async def stars_successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    payment = msg.successful_payment if msg else None
    if not payment or payment.currency != "XTR":
        return
    payload = payment.invoice_payload
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                order = await conn.fetchrow(
                    """SELECT chat_id, amount_stars, duration_days, status
                       FROM stars_subscription_orders WHERE payload=$1 FOR UPDATE""",
                    payload,
                )
                if not order or order["status"] not in ("pending", "paid") or int(order["amount_stars"]) != int(payment.total_amount):
                    logger.warning("Ignoring unmatched Stars payment payload=%s", payload)
                    return
                inserted = await conn.fetchval(
                    """INSERT INTO stars_subscription_payments
                       (charge_id, payload, chat_id, payer_id, amount_stars)
                       VALUES($1,$2,$3,$4,$5)
                       ON CONFLICT(charge_id) DO NOTHING RETURNING charge_id""",
                    payment.telegram_payment_charge_id, payload, int(order["chat_id"]),
                    int(update.effective_user.id), int(payment.total_amount),
                )
                if not inserted:
                    return
                await conn.execute(
                    """INSERT INTO stars_group_subscriptions(chat_id, expires_at, last_charge_id)
                       VALUES($1, NOW() + ($2 * INTERVAL '1 day'), $3)
                       ON CONFLICT(chat_id) DO UPDATE SET
                           expires_at=GREATEST(stars_group_subscriptions.expires_at, NOW())
                                      + ($2 * INTERVAL '1 day'),
                           last_charge_id=EXCLUDED.last_charge_id, updated_at=NOW()""",
                    int(order["chat_id"]), int(order["duration_days"]), payment.telegram_payment_charge_id,
                )
                await conn.execute(
                    "UPDATE stars_subscription_orders SET status='paid', paid_at=NOW() WHERE payload=$1", payload
                )
        await context.bot.send_message(
            chat_id=int(order["chat_id"]),
            text=f"تم تفعيل اشتراك هذا القروب لمدة {int(order['duration_days'])} يوم ⭐️\nشكرًا لك!",
        )
    except Exception:
        logger.exception("Failed to activate group after Stars payment")


async def _group_has_subscription(chat_id: int) -> bool:
    return bool(await get_pool().fetchval(
        "SELECT 1 FROM stars_group_subscriptions WHERE chat_id=$1 AND expires_at > NOW()", int(chat_id)
    ))


async def stars_group_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user = update.effective_chat, update.effective_user
    if not chat or chat.type not in ("group", "supergroup") or (user and user.id == OWNER_ID):
        return
    if not await _group_has_subscription(chat.id):
        raise ApplicationHandlerStop


async def stars_group_callback_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.message:
        return
    chat, user = query.message.chat, query.from_user
    if chat.type not in ("group", "supergroup") or (user and user.id == OWNER_ID):
        return
    if not await _group_has_subscription(chat.id):
        await query.answer("اشتراك هذا القروب منتهي أو غير مفعّل.", show_alert=True)
        raise ApplicationHandlerStop
