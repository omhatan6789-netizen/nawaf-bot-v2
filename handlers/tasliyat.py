"""Legacy-compatible async bank and economy commands."""
from __future__ import annotations

import random
import time
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.tasliyat import (
    games_enabled, get_points, get_bank, create_bank, delete_bank,
    claim_reward, run_investment, run_luck,
)

OWNER_ID = 8453977662
BANKS = {
    "ahli": {"name": "الاهلي", "card": "فيزا"},
    "inma": {"name": "الانماء", "card": "مدى"},
    "rajhi": {"name": "الراجحي", "card": "ماستر كارد"},
}
JOBS = [
    ("دكتور", "👨🏻‍⚕️", 3900), ("مهندس", "👷🏻", 3000),
    ("معلّم", "👨🏻‍🏫", 2500), ("محامي", "⚖️", 3200),
    ("مبرمج", "👨🏻‍💻", 1800), ("طيار", "👨🏻‍✈️", 4000),
    ("شرطي", "👮🏻", 1700), ("صيدلي", "💊", 1000),
    ("مصمم", "🎨", 1400), ("طباخ", "👨🏻‍🍳", 1200),
    ("ممرض", "🧑🏻‍⚕️", 1500), ("سائق", "🚗", 900),
    ("رقاصة", "💃🏻", 600), ("كاشير", "🧑🏻‍💼", 800),
    ("كهربائي", "⚡️", 1400), ("محاسب", "🧑🏻‍💼", 2000),
    ("قاضي", "👨🏻‍⚖️", 3800), ("مزارع", "👨🏻‍🌾", 1100),
]


def _mention(user) -> str:
    from telegram.helpers import mention_html
    return mention_html(user.id, user.full_name)


def _format_arabic_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes <= 0:
        return "ثانية" if secs == 1 else f"{secs} ثانية"
    if secs == 0:
        if minutes == 1:
            return "دقيقة"
        if minutes == 2:
            return "دقيقتين"
        names = {3:"ثلاث",4:"أربع",5:"خمس",6:"ست",7:"سبع",8:"ثمان",9:"تسع",10:"عشر"}
        if 3 <= minutes <= 10:
            return f"{names[minutes]} دقائق"
        return f"{minutes} دقيقة"
    names = {3:"ثلاث",4:"أربع",5:"خمس",6:"ست",7:"سبع",8:"ثمان",9:"تسع",10:"عشر"}
    if minutes == 1:
        minute_text = "دقيقة"
    elif minutes == 2:
        minute_text = "دقيقتين"
    elif 3 <= minutes <= 10:
        minute_text = f"{names[minutes]} دقائق"
    else:
        minute_text = f"{minutes} دقيقة"
    return f"{minute_text} و {'ثانية' if secs == 1 else f'{secs} ثانية'}"


async def _enabled() -> bool:
    return await games_enabled()


async def _require_bank(message, user_id: int):
    bank = await get_bank(user_id)
    if not bank:
        await message.reply_text("• ماعندك حساب بنكي .")
        return None
    return bank


async def create_bank_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    target = user
    if message.reply_to_message:
        if user.id != OWNER_ID:
            return
        target = message.reply_to_message.from_user
        if not target:
            return
    if await get_bank(target.id):
        await message.reply_text(
            "• عنده حساب بنكي 😅\n\n"
            "• لعرض معلومات حسابه اكتب\n"
            "↤︎ حسابي"
        )
        return
    keyboard = [
        [InlineKeyboardButton("الاهلي", callback_data=f"tasliyat:bank:ahli:{target.id}")],
        [InlineKeyboardButton("الانماء", callback_data=f"tasliyat:bank:inma:{target.id}")],
        [InlineKeyboardButton("الراجحي", callback_data=f"tasliyat:bank:rajhi:{target.id}")],
    ]
    await message.reply_text(
        "• عشان تسوي حساب لازم تختار نوع البطاقة\n"
        "↤︎ الاهلي\n↤︎ الانماء\n↤︎ الراجحي\n",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def bank_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if not await _enabled():
        return
    parts = (query.data or "").split(":")
    if len(parts) != 4 or parts[2] not in BANKS:
        return
    try:
        target_id = int(parts[3])
    except ValueError:
        return
    if query.from_user.id not in (target_id, OWNER_ID):
        return
    info = BANKS[parts[2]]
    bank = await create_bank(target_id, info["name"], info["card"])
    if not bank:
        await query.edit_message_text("• تعذر إنشاء الحساب، حاول مرة ثانية.")
        return
    points = await get_points(target_id)
    await query.edit_message_text(
        f"• سويت لك حساب في البنك ( {info['name']} 💳 )\n"
        f"• رقم حسابك ↢ ( <code>{bank['account_number']}</code> )\n"
        f"• نوع البطاقة ↢ ( {info['card']} )\n"
        f"• نقاطك ↢ ( {points} 💵 )",
        parse_mode="HTML",
    )


async def my_bank_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    bank = await get_bank(user.id)
    if not bank:
        await message.reply_text("• ماعندك حساب بنكي ارسل ↢ ( انشاء حساب بنكي )")
        return
    points = await get_points(user.id)
    await message.reply_text(
        f"• الاسم ↢ {_mention(user)}\n"
        f"• الحساب ↢ <code>{bank['account_number']}</code>\n"
        f"• بنك ↢ ( {bank['bank']} )\n"
        f"• نوع ↢ ( {bank['card_type']} )\n"
        f"• الرصيد ↢ ( {points} نقطة 💵 )\n"
        f"• الزرف ↢ ( {bank['robbery_balance']} نقطة 🥷🏻 )",
        parse_mode="HTML",
    )


async def delete_bank_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not await get_bank(user.id):
        await message.reply_text("• ماعندك حساب بنكي .")
        return
    await delete_bank(user.id)
    await message.reply_text("• تم مسح حسابك البنكي .")


async def salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not await _require_bank(message, user.id):
        return
    job, emoji, amount = random.choice(JOBS)
    ok, balance, remaining = await claim_reward(user.id, "salary_until", int(time.time()), 600, amount)
    if not ok:
        await message.reply_text(f"• راتبك بينزل بعد {_format_arabic_duration(remaining)} .")
        return
    await message.reply_text(
        f"اشعار ايداع {_mention(user)}\n"
        f"المبلغ: {amount} نقطة\n"
        f"وظيفتك: {job} {emoji}\n"
        f"نوع العملية: اضافة راتب\n"
        f"رصيدك الحين: {balance} نقطة 💸",
        parse_mode="HTML",
    )


async def tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if not await _require_bank(message, user.id):
        return
    amount = random.randint(100, 2000)
    ok, _balance, remaining = await claim_reward(user.id, "tip_until", int(time.time()), 600, amount)
    if not ok:
        await message.reply_text(
            "• بس بس مب حلاو هو !!\n"
            f"↤︎ تعال بعد {_format_arabic_duration(remaining)}"
        )
        return
    await message.reply_text(f"• شفقت عليك وعطيتك {amount} نقطة 💵")


def _investment_percent() -> int:
    roll = random.randint(1, 100)
    if roll <= 50:
        return random.randint(1, 20)
    if roll <= 90:
        return random.randint(21, 30)
    return random.randint(31, 40)


def _parse_amount(text: str, current: int) -> int | None:
    parts = text.strip().split()
    if len(parts) == 1:
        return current
    if len(parts) == 2:
        if parts[1] == "نقاطي":
            return current
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


async def invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not message.text or not user:
        return
    if not await _require_bank(message, user.id):
        return
    current = await get_points(user.id)
    amount = _parse_amount(message.text, current)
    if amount is None or amount <= 0:
        return
    success = random.randint(1, 100) <= 90
    percent = _investment_percent() if success else 0
    profit = (amount * percent) // 100 if success else None
    status, balance, remaining = await run_investment(
        user.id, int(time.time()), 1200, amount, profit
    )
    if status == "insufficient":
        await message.reply_text("• نقاطك ماتكفي يا مطفر\n–")
        return
    if status == "cooldown":
        await message.reply_text(
            "• مايمديك تستثمر الحين\n"
            f"• تعال بعد {_format_arabic_duration(remaining)}"
        )
        return
    if status == "failed":
        await message.reply_text(
            "• استثمار فاشل\n"
            "• نسبة الربح ↢ 0%\n"
            "• مبلغ الربح ↢ ( 0 )\n"
            f"• نقاطك صارت ↢ ( {balance} )"
        )
        return
    await message.reply_text(
        "• استثمار ناجح\n"
        f"• نسبة الربح ↢ {percent}%\n"
        f"• مبلغ الربح ↢ ( {profit} )\n"
        f"• نقاطك صارت ↢ ( {balance} )"
    )


async def luck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _enabled():
        return
    message = update.effective_message
    user = update.effective_user
    if not message or not message.text or not user:
        return
    if not await _require_bank(message, user.id):
        return
    current = await get_points(user.id)
    amount = _parse_amount(message.text, current)
    if amount is None or amount <= 0:
        return
    won = random.randint(1, 2) == 1
    status, before, after, remaining = await run_luck(
        user.id, int(time.time()), 1200, amount, won
    )
    if status == "insufficient":
        await message.reply_text("• نقاطك ماتكفي يا مطفر\n–")
        return
    if status == "cooldown":
        await message.reply_text(
            "• مايمديك تسوي حظ الحين\n"
            f"• تعال بعد {_format_arabic_duration(remaining)}"
        )
        return
    if status == "won":
        await message.reply_text(
            "• مبروك فزت بالحظ 🥳🎉\n"
            f"• نقاطك قبل ↢ ( {before} نقطة 💵 )\n"
            f"• نقاطك الحين ↢ ( {after} نقطة 💵 )"
        )
        return
    await message.reply_text(
        "• للاسف خسرت بالحظ 😂😂 \n"
        f"• نقاطك قبل ↢ ( {before} نقطة 💵 )\n"
        f"• نقاطك  الحين ↢ ( {after} نقطة 💵 )\n"
        "-"
    )
