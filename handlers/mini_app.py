from __future__ import annotations

import json
import re
from telegram import Update, WebAppInfo, MenuButtonWebApp
from telegram.ext import ContextTypes, MessageHandler, filters, ApplicationHandlerStop

from database.pool import get_pool

OWNER_ID = 8453977662
WEB_APP_URL = "https://nawaf-bot-v2.onrender.com/"
_sessions: dict[int, dict] = {}


async def register_mini_app_menu(application) -> None:
    try:
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="بوت نواف",
                web_app=WebAppInfo(url=WEB_APP_URL),
            )
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to set Mini App menu button")


def _normalize_target(value: str) -> str | None:
    value = value.strip()
    if re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
        return "https://t.me/" + value[1:]
    if re.fullmatch(r"(?:https?://)?t\.me/[A-Za-z0-9_+/=?-]+", value, re.I):
        return value if value.startswith("http") else "https://" + value
    if re.match(r"^https?://", value, re.I):
        return value
    return None


async def mini_app_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or chat.type != "private":
        return
    if user.id != OWNER_ID:
        return
    text = (msg.text or "").strip()
    if text in ("اضف زر للميني", "اضف زر كبير للميني"):
        kind = "large" if text == "اضف زر كبير للميني" else "small"
        _sessions[user.id] = {"step": "title", "type": kind}
        await msg.reply_text("ارسل اسم الزر:")
        raise ApplicationHandlerStop

    session = _sessions.get(user.id)
    if not session:
        return

    step = session["step"]
    if step == "title":
        if not text:
            await msg.reply_text("ارسل اسم الزر كنص.")
            raise ApplicationHandlerStop
        session["title"] = text[:80]
        session["step"] = "target"
        await msg.reply_text("حسنًا، الآن ارسل محتوى الزر: رابط موقع أو يوزر تيليجرام مثل @username")
    elif step == "target":
        target = _normalize_target(text)
        if not target:
            await msg.reply_text("الرابط غير صحيح. ارسل رابط يبدأ بـ https:// أو يوزر مثل @username")
            raise ApplicationHandlerStop
        session["target"] = target
        session["step"] = "color"
        await msg.reply_text("ارسل لون الزر (مثال: احمر أو #ff3333). وللأبيض ارسل: ابيض")
    elif step == "color":
        colors = {"ابيض":"#ffffff","أبيض":"#ffffff","احمر":"#ffdddd","أحمر":"#ffdddd","اصفر":"#fff2b3","أصفر":"#fff2b3","اخضر":"#d8f5dc","أخضر":"#d8f5dc","ازرق":"#dcecff","أزرق":"#dcecff"}
        color = colors.get(text.lower(), text)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            await msg.reply_text("اكتب اللون بصيغة HEX مثل #ff3333 أو اختر: ابيض، احمر، اصفر، اخضر، ازرق")
            raise ApplicationHandlerStop
        session["color"] = color
        session["step"] = "image"
        await msg.reply_text("ارسل صورة الزر الآن، أو اكتب تخطي إذا ما تبي صورة.")
    elif step == "image":
        if text.lower() == "تخطي":
            file_id = None
        elif msg.photo:
            file_id = msg.photo[-1].file_id
        else:
            await msg.reply_text("ارسل صورة أو اكتب تخطي.")
            raise ApplicationHandlerStop
        order = await get_pool().fetchval(
            "SELECT COALESCE(MAX(button_order),0)+1 FROM mini_app_buttons WHERE button_type=$1",
            session["type"],
        )
        await get_pool().execute(
            """INSERT INTO mini_app_buttons
               (title,target,button_type,color,image_file_id,button_order,created_by)
               VALUES($1,$2,$3,$4,$5,$6,$7)""",
            session["title"], session["target"], session["type"],
            session["color"], file_id, order, user.id,
        )
        _sessions.pop(user.id, None)
        await msg.reply_text("تمت إضافة الزر للميني آب بنجاح ✅")
    raise ApplicationHandlerStop
