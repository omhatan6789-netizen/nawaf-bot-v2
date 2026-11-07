from __future__ import annotations

import html
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, ContextTypes
from database.pool import get_pool

OWNER_ID = 8453977662
SESSIONS: dict[int, dict] = {}

PALETTE = [
    ("🔴 أحمر", "#ef4444"), ("🍷 خمري", "#991b1b"),
    ("🟠 برتقالي", "#f97316"), ("🟡 ذهبي", "#f59e0b"),
    ("💛 أصفر", "#eab308"), ("🟢 أخضر", "#22c55e"),
    ("🌿 زيتي", "#65a30d"), ("🩵 تركواز", "#14b8a6"),
    ("🩵 سماوي", "#06b6d4"), ("🔵 أزرق", "#3b82f6"),
    ("🟣 نيلي", "#6366f1"), ("💜 بنفسجي", "#a855f7"),
    ("🩷 وردي", "#ec4899"), ("🌺 فوشي", "#f43f5e"),
    ("⚫ أسود", "#171717"), ("⚪ أبيض", "#ffffff"),
    ("🩶 رمادي", "#6b7280"), ("🤎 بني", "#92400e"),
]

def _menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 تعديل لون زر بالميني", callback_data="minipanel:color")],
        [InlineKeyboardButton("📋 الألوان المعدلة", callback_data="minipanel:colors")],
        [InlineKeyboardButton("🔘 إدارة الأزرار", callback_data="minipanel:buttons"),
         InlineKeyboardButton("🎧 إدارة الأصوات", callback_data="minipanel:sounds")],
        [InlineKeyboardButton("🖼️ صورة الميني آب", callback_data="minipanel:banner")],
    ])

def _back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ لوحة الميني", callback_data="minipanel:menu")]])

def _palette():
    rows = []
    for i in range(0, len(PALETTE), 3):
        rows.append([InlineKeyboardButton(label, callback_data=f"minipanel:pick:{color}") for label, color in PALETTE[i:i+3]])
    rows.append([InlineKeyboardButton("✏️ لون مخصص HEX", callback_data="minipanel:custom")])
    rows.append([InlineKeyboardButton("↩️ إلغاء", callback_data="minipanel:menu")])
    return InlineKeyboardMarkup(rows)

async def mini_app_color_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or not chat or chat.type != "private" or user.id != OWNER_ID:
        return
    SESSIONS[user.id] = {"action": "color", "step": "button"}
    await msg.reply_text("ارسل اسم الزر كما يظهر لك داخل الميني آب. تقدر تختار أي زر، حتى زر الرجوع أو أزرار الألعاب.")
    raise ApplicationHandlerStop

async def mini_app_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or not chat or chat.type != "private" or user.id != OWNER_ID:
        return
    SESSIONS.pop(user.id, None)
    await msg.reply_text("⚙️ لوحة التحكم الخاصة بالميني آب\nاختر القسم اللي تبي تديره:", reply_markup=_menu())
    raise ApplicationHandlerStop

async def mini_app_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.from_user:
        return
    if q.from_user.id != OWNER_ID:
        await q.answer("هذه اللوحة للمالك فقط", show_alert=True)
        return
    data = q.data or ""
    await q.answer()
    uid = q.from_user.id
    pool = get_pool()

    if data == "minipanel:menu":
        SESSIONS.pop(uid, None)
        await q.edit_message_text("⚙️ لوحة التحكم الخاصة بالميني آب\nاختر القسم اللي تبي تديره:", reply_markup=_menu())
    elif data == "minipanel:buttons":
        rows = await pool.fetch("SELECT id,title,button_type,target FROM mini_app_buttons ORDER BY button_type DESC,button_order,id")
        lines = ["🔘 أزرار الميني آب", "━━━━━━━━━━━━"]
        if rows:
            for i, row in enumerate(rows, 1):
                kind = "كبير" if row["button_type"] == "large" else "صغير"
                lines.append(f"{i}. {html.escape(row['title'])} — {kind}")
        else:
            lines.append("ما فيه أزرار مضافة حاليًا.")
        keys = [
            [InlineKeyboardButton("➕ إضافة زر صغير", callback_data="minipanel:add:small"),
             InlineKeyboardButton("➕ إضافة زر كبير", callback_data="minipanel:add:large")],
        ]
        for row in rows:
            keys.append([InlineKeyboardButton(f"🗑️ حذف: {row['title'][:35]}", callback_data=f"minipanel:delbutton:{row['id']}")])
        keys.append([InlineKeyboardButton("↩️ لوحة الميني", callback_data="minipanel:menu")])
        await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keys))
    elif data.startswith("minipanel:add:"):
        kind = data.rsplit(":", 1)[-1]
        if kind not in ("small", "large"):
            return
        SESSIONS[uid] = {"action": "add_button", "step": "title", "type": kind}
        await q.edit_message_text("ارسل اسم الزر الجديد:", reply_markup=_back())
    elif data.startswith("minipanel:delbutton:"):
        button_id = int(data.rsplit(":", 1)[-1])
        row = await pool.fetchrow("DELETE FROM mini_app_buttons WHERE id=$1 RETURNING title", button_id)
        await q.edit_message_text(f"تم حذف «{html.escape(row['title'])}» ✅" if row else "الزر غير موجود.", parse_mode="HTML", reply_markup=_back())
    elif data == "minipanel:sounds":
        rows = await pool.fetch("SELECT id,title,media_kind FROM mini_app_sounds ORDER BY id")
        lines = ["🎧 أصوات الميني آب", "━━━━━━━━━━━━"]
        lines += [f"{i}. {html.escape(r['title'])} — {'فيديو' if r['media_kind']=='video' else 'صوت'}" for i, r in enumerate(rows, 1)] or ["ما فيه أصوات مضافة."]
        keys = [[InlineKeyboardButton("➕ إضافة صوت", callback_data="minipanel:addsound")]]
        keys += [[InlineKeyboardButton(f"🗑️ حذف: {r['title'][:35]}", callback_data=f"minipanel:delsound:{r['id']}")] for r in rows]
        keys.append([InlineKeyboardButton("↩️ لوحة الميني", callback_data="minipanel:menu")])
        await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keys))
    elif data == "minipanel:addsound":
        SESSIONS[uid] = {"action": "add_sound", "step": "media"}
        await q.edit_message_text("ارسل ملف صوت أو فيديو (حتى 20 ميجابايت):", reply_markup=_back())
    elif data.startswith("minipanel:delsound:"):
        sound_id = int(data.rsplit(":", 1)[-1])
        row = await pool.fetchrow("DELETE FROM mini_app_sounds WHERE id=$1 RETURNING title", sound_id)
        await q.edit_message_text(f"تم حذف الصوت «{html.escape(row['title'])}» ✅" if row else "الصوت غير موجود.", parse_mode="HTML", reply_markup=_back())
    elif data == "minipanel:banner":
        SESSIONS[uid] = {"action": "banner", "step": "photo"}
        await q.edit_message_text("ارسل الصورة الجديدة للميني آب:", reply_markup=_back())
    elif data == "minipanel:color":
        SESSIONS[uid] = {"action": "color", "step": "button"}
        await q.edit_message_text("ارسل اسم الزر كما يظهر لك داخل الميني آب. تقدر تختار أي زر، حتى زر الرجوع أو أزرار الألعاب.", reply_markup=_back())
    elif data.startswith("minipanel:pick:"):
        session = SESSIONS.get(uid)
        if not session or session.get("action") != "color" or session.get("step") != "palette":
            return
        color = data.rsplit(":", 1)[-1]
        await _save_color(q, uid, session["button"], color)
    elif data == "minipanel:custom":
        session = SESSIONS.get(uid)
        if not session or session.get("action") != "color":
            return
        session["step"] = "custom"
        await q.edit_message_text("ارسل كود اللون بصيغة HEX مثل #12a4ff:", reply_markup=_back())
    elif data == "minipanel:colors":
        rows = await pool.fetch("SELECT button_text,color_hex FROM mini_app_button_colors ORDER BY button_text")
        lines = ["🎨 الألوان المخصصة", "━━━━━━━━━━━━"]
        lines += [f"• {html.escape(r['button_text'])}: <code>{r['color_hex']}</code>" for r in rows] or ["ما عدلت ألوان أي أزرار حتى الآن."]
        keys = [[InlineKeyboardButton(f"↩️ لوحة الميني", callback_data="minipanel:menu")]]
        await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keys))

async def _save_color(q, uid: int, button: str, color: str):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        await q.edit_message_text("صيغة اللون غير صحيحة. استخدم #RRGGBB", reply_markup=_back())
        return
    await get_pool().execute(
        """INSERT INTO mini_app_button_colors(button_text,color_hex,updated_by,updated_at)
           VALUES($1,$2,$3,NOW()) ON CONFLICT(button_text) DO UPDATE
           SET color_hex=EXCLUDED.color_hex,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
        button, color.lower(), uid,
    )
    SESSIONS.pop(uid, None)
    await q.edit_message_text(f"تم تغيير لون زر «{html.escape(button)}» إلى <code>{color.lower()}</code> ✅\nافتح الميني آب من جديد لتطبيق اللون.", parse_mode="HTML", reply_markup=_back())

async def mini_app_panel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not msg or not user or not chat or chat.type != "private":
        return
    if user.id != OWNER_ID:
        return
    session = SESSIONS.get(user.id)
    if not session:
        return
    text = (msg.text or "").strip()
    action, step = session.get("action"), session.get("step")
    if text in ("إلغاء", "الغاء", "الغاء الامر"):
        SESSIONS.pop(user.id, None)
        await msg.reply_text("تم الإلغاء.", reply_markup=_back())
        raise ApplicationHandlerStop

    if action == "color":
        if step == "button":
            if not text:
                await msg.reply_text("ارسل اسم الزر كنص.")
                raise ApplicationHandlerStop
            session["button"] = " ".join(text.split())
            session["step"] = "palette"
            await msg.reply_text(f"اختر لون زر «{session['button']}» أو أدخل لونًا مخصصًا:", reply_markup=_palette())
            raise ApplicationHandlerStop
        if step == "custom":
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
                await msg.reply_text("اللون غير صحيح. ارسله بصيغة #RRGGBB.")
                raise ApplicationHandlerStop
            await get_pool().execute(
                """INSERT INTO mini_app_button_colors(button_text,color_hex,updated_by,updated_at)
                   VALUES($1,$2,$3,NOW()) ON CONFLICT(button_text) DO UPDATE
                   SET color_hex=EXCLUDED.color_hex,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
                session["button"], text.lower(), user.id,
            )
            SESSIONS.pop(user.id, None)
            await msg.reply_text(f"تم تغيير لون زر «{session['button']}» إلى {text.lower()} ✅\nافتح الميني آب من جديد لتطبيق اللون.", reply_markup=_back())
            raise ApplicationHandlerStop

    if action == "banner":
        if not msg.photo:
            await msg.reply_text("ارسل صورة، أو اكتب إلغاء.")
            raise ApplicationHandlerStop
        await get_pool().execute("UPDATE mini_app_settings SET banner_file_id=$1,updated_at=NOW() WHERE id=1", msg.photo[-1].file_id)
        SESSIONS.pop(user.id, None)
        await msg.reply_text("تم تحديث صورة الميني آب ✅", reply_markup=_back())
        raise ApplicationHandlerStop

    if action == "add_button":
        if step == "title":
            if not text:
                await msg.reply_text("ارسل اسم الزر.")
                raise ApplicationHandlerStop
            session["title"] = text[:80]
            session["step"] = "target"
            await msg.reply_text("ارسل رابط الموقع أو يوزر تيليجرام مثل @username.")
        elif step == "target":
            value = text.strip()
            if re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
                value = "https://t.me/" + value[1:]
            elif re.fullmatch(r"(?:https?://)?t\.me/[A-Za-z0-9_+/=?-]+", value, re.I):
                value = value if value.startswith("http") else "https://" + value
            if not re.match(r"^https?://", value, re.I):
                await msg.reply_text("الرابط غير صحيح. ارسل رابطًا يبدأ بـ https:// أو @username.")
                raise ApplicationHandlerStop
            session["target"] = value
            session["step"] = "color"
            await msg.reply_text("ارسل لون خلفية الزر بصيغة HEX مثل #ffffff.")
        elif step == "color":
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
                await msg.reply_text("اكتب اللون بصيغة #RRGGBB.")
                raise ApplicationHandlerStop
            session["color"] = text.lower()
            session["step"] = "image"
            await msg.reply_text("ارسل صورة للزر أو اكتب تخطي.")
        elif step == "image":
            if text.lower() == "تخطي":
                file_id = None
            elif msg.photo:
                file_id = msg.photo[-1].file_id
            else:
                await msg.reply_text("ارسل صورة أو اكتب تخطي.")
                raise ApplicationHandlerStop
            order = await get_pool().fetchval("SELECT COALESCE(MAX(button_order),0)+1 FROM mini_app_buttons WHERE button_type=$1", session["type"])
            await get_pool().execute(
                """INSERT INTO mini_app_buttons(title,target,button_type,color,image_file_id,button_order,created_by)
                   VALUES($1,$2,$3,$4,$5,$6,$7)""",
                session["title"], session["target"], session["type"], session["color"], file_id, order, user.id,
            )
            SESSIONS.pop(user.id, None)
            await msg.reply_text("تمت إضافة الزر للميني آب بنجاح ✅", reply_markup=_back())
        raise ApplicationHandlerStop

    if action == "add_sound":
        if step == "media":
            media = msg.audio or msg.voice or msg.video
            if msg.document and (msg.document.mime_type or "").startswith(("audio/", "video/")):
                media = msg.document
            if not media:
                await msg.reply_text("ارسل ملف صوتي أو فيديو.")
                raise ApplicationHandlerStop
            size = getattr(media, "file_size", 0) or 0
            if size > 20 * 1024 * 1024:
                await msg.reply_text("الملف أكبر من 20 ميجابايت.")
                raise ApplicationHandlerStop
            mime = getattr(media, "mime_type", None) or ("video/mp4" if msg.video else "audio/ogg" if msg.voice else "audio/mpeg")
            session.update({"step": "title", "file_id": media.file_id, "mime_type": mime, "media_kind": "video" if mime.startswith("video/") or msg.video else "audio", "file_size": size})
            await msg.reply_text("وش الاسم اللي تبيه يظهر للصوت؟")
        elif step == "title":
            if not text:
                await msg.reply_text("اكتب اسمًا للصوت.")
                raise ApplicationHandlerStop
            await get_pool().execute(
                """INSERT INTO mini_app_sounds(title,file_id,mime_type,media_kind,file_size,created_by)
                   VALUES($1,$2,$3,$4,$5,$6)""",
                text[:80], session["file_id"], session["mime_type"], session["media_kind"], session["file_size"], user.id,
            )
            SESSIONS.pop(user.id, None)
            await msg.reply_text("تمت إضافة الصوت للميني آب ✅", reply_markup=_back())
        raise ApplicationHandlerStop
