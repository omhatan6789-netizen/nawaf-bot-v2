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
    delete_commands = {
        "حذف زر الميني": "small",
        "حذف زر ميني كبير": "large",
    }
    if text in delete_commands:
        _sessions[user.id] = {"step": "delete_button_title", "type": delete_commands[text]}
        label = "الصغير" if delete_commands[text] == "small" else "الكبير"
        await msg.reply_text(f"ارسل اسم الزر {label} اللي تبي تحذفه، أو اكتب إلغاء.")
        raise ApplicationHandlerStop

    session = _sessions.get(user.id)
    if session and session.get("step") == "delete_button_title":
        if text in ("إلغاء", "الغاء"):
            _sessions.pop(user.id, None)
            await msg.reply_text("تم إلغاء حذف الزر.")
            raise ApplicationHandlerStop
        if not text:
            await msg.reply_text("ارسل اسم الزر كنص، أو اكتب إلغاء.")
            raise ApplicationHandlerStop
        deleted = await get_pool().fetchrow(
            """DELETE FROM mini_app_buttons
               WHERE id = (
                   SELECT id FROM mini_app_buttons
                   WHERE button_type = $1 AND LOWER(BTRIM(title)) = LOWER(BTRIM($2))
                   ORDER BY id LIMIT 1
               )
               RETURNING title""",
            session["type"], text,
        )
        _sessions.pop(user.id, None)
        if deleted:
            await msg.reply_text(f"تم حذف زر «{deleted['title']}» بنجاح ✅")
        else:
            await msg.reply_text("ما لقيت زر بهذا الاسم ضمن النوع المحدد.")
        raise ApplicationHandlerStop
    if text == "تغيير صورة الميني":
        _sessions[user.id] = {"step": "banner_image"}
        await msg.reply_text("ارسل صورة أو فيديو أو GIF اللي تبيه أعلى الميني آب (حتى 20 ميجابايت).")
        raise ApplicationHandlerStop

    session = _sessions.get(user.id)
    if session and session.get("step") == "banner_image":
        if text in ("إلغاء", "الغاء"):
            _sessions.pop(user.id, None)
            await msg.reply_text("تم إلغاء تغيير الصورة.")
            raise ApplicationHandlerStop
        media = msg.photo[-1] if msg.photo else (msg.video or msg.animation)
        if msg.document and (msg.document.mime_type or "").startswith(("image/", "video/")):
            media = msg.document
        if not media:
            await msg.reply_text("ارسل صورة أو فيديو أو GIF، أو اكتب إلغاء.")
            raise ApplicationHandlerStop
        size = getattr(media, "file_size", 0) or 0
        if size > 20 * 1024 * 1024:
            await msg.reply_text("الملف أكبر من 20 ميجابايت. أرسل ملفًا أصغر.")
            raise ApplicationHandlerStop
        mime = getattr(media, "mime_type", None) or ("image/jpeg" if msg.photo else "video/mp4" if msg.video or msg.animation else "")
        kind = "video" if mime.startswith("video/") else "image"
        await get_pool().execute(
            """UPDATE mini_app_settings
               SET banner_file_id=$1,banner_media_kind=$2,banner_mime_type=$3,updated_at=NOW()
               WHERE id=1""",
            media.file_id, kind, mime or ("image/gif" if kind == "image" else "video/mp4"),
        )
        _sessions.pop(user.id, None)
        await msg.reply_text("تم تحديث وسيط أعلى الميني آب بنجاح ✅")
        raise ApplicationHandlerStop

    if text == "اضف صوت للميني":
        _sessions[user.id] = {"step": "sound_media"}
        await msg.reply_text("ارسل ملف صوتي أو مقطع فيديو (حتى 20 ميجابايت)، أو اكتب إلغاء.")
        raise ApplicationHandlerStop

    if text == "أصوات الميني":
        rows = await get_pool().fetch("SELECT id,title,media_kind FROM mini_app_sounds ORDER BY id")
        if not rows:
            await msg.reply_text("ما أضفت أي صوت للميني آب حتى الآن.")
        else:
            lines = [f"{i}. {r['title']} ({'فيديو' if r['media_kind'] == 'video' else 'صوت'})" for i, r in enumerate(rows, 1)]
            await msg.reply_text("أصوات الميني آب:\n" + "\n".join(lines))
        raise ApplicationHandlerStop

    if text == "حذف صوت من الميني":
        _sessions[user.id] = {"step": "delete_sound_title"}
        await msg.reply_text("ارسل اسم الصوت اللي تبي تحذفه، أو اكتب إلغاء.")
        raise ApplicationHandlerStop

    if text in ("اضف زر للميني", "اضف زر كبير للميني"):
        kind = "large" if text == "اضف زر كبير للميني" else "small"
        _sessions[user.id] = {"step": "title", "type": kind}
        await msg.reply_text("ارسل اسم الزر:")
        raise ApplicationHandlerStop

    session = _sessions.get(user.id)
    if not session:
        return

    step = session["step"]
    if step == "delete_sound_title":
        if text in ("إلغاء", "الغاء"):
            _sessions.pop(user.id, None)
            await msg.reply_text("تم إلغاء حذف الصوت.")
        elif not text:
            await msg.reply_text("ارسل اسم الصوت أو اكتب إلغاء.")
        else:
            deleted = await get_pool().fetchrow(
                """DELETE FROM mini_app_sounds
                   WHERE id = (SELECT id FROM mini_app_sounds
                               WHERE LOWER(BTRIM(title))=LOWER(BTRIM($1))
                               ORDER BY id LIMIT 1)
                   RETURNING title""", text
            )
            _sessions.pop(user.id, None)
            await msg.reply_text(f"تم حذف صوت «{deleted['title']}» من الميني آب ✅" if deleted else "ما لقيت صوت بهذا الاسم.")
        raise ApplicationHandlerStop
    if step == "sound_media":
        if text in ("إلغاء", "الغاء"):
            _sessions.pop(user.id, None)
            await msg.reply_text("تم إلغاء إضافة الصوت.")
            raise ApplicationHandlerStop
        media = msg.audio or msg.voice or msg.video
        if msg.document and (msg.document.mime_type or "").startswith(("audio/", "video/")):
            media = msg.document
        if not media:
            await msg.reply_text("ارسل ملف صوتي أو فيديو، أو اكتب إلغاء.")
            raise ApplicationHandlerStop
        size = getattr(media, "file_size", 0) or 0
        if size > 20 * 1024 * 1024:
            await msg.reply_text("حجم الملف أكبر من 20 ميجابايت. أرسل ملفًا أصغر.")
            raise ApplicationHandlerStop
        mime = getattr(media, "mime_type", None) or ("video/mp4" if msg.video else "audio/ogg" if msg.voice else "audio/mpeg")
        kind = "video" if mime.startswith("video/") or msg.video else "audio"
        session.update({"step": "sound_title", "file_id": media.file_id, "mime_type": mime, "media_kind": kind, "file_size": size})
        await msg.reply_text("وش الاسم اللي تبي يظهر في قائمة الأصوات؟")
        raise ApplicationHandlerStop
    if step == "sound_title":
        if text in ("إلغاء", "الغاء"):
            _sessions.pop(user.id, None)
            await msg.reply_text("تم إلغاء إضافة الصوت.")
        elif not text:
            await msg.reply_text("ارسل اسمًا للصوت.")
        else:
            await get_pool().execute(
                """INSERT INTO mini_app_sounds(title,file_id,mime_type,media_kind,file_size,created_by)
                   VALUES($1,$2,$3,$4,$5,$6)""",
                text[:80], session["file_id"], session["mime_type"],
                session["media_kind"], session["file_size"], user.id
            )
            _sessions.pop(user.id, None)
            await msg.reply_text(f"تمت إضافة «{text[:80]}» لقائمة أصوات الميني آب ✅")
        raise ApplicationHandlerStop
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
