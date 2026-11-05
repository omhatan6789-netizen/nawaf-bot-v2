import json
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.pool import get_pool

OWNER_ID = 8453977662
sessions = {}


async def _is_allowed(user):
    if not user:
        return False
    if user.id == OWNER_ID:
        return True
    row = await get_pool().fetchrow(
        """SELECT 1 FROM start_access
           WHERE user_id=$1 OR (username IS NOT NULL AND lower(username)=$2)
           LIMIT 1""",
        user.id, (user.username or "").lower() or None,
    )
    return row is not None


def _main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("تعديل رسالة البدء", callback_data="startedit:message"),
         InlineKeyboardButton("اضافة ازرار", callback_data="startedit:buttons")],
        [InlineKeyboardButton("المسموحين بالوصول", callback_data="startedit:access"),
         InlineKeyboardButton("اضافة صورة", callback_data="startedit:image")],
    ])


def _back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ الرجوع للقائمة", callback_data="startedit:menu")]])


def _buttons_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اضف زر", callback_data="startedit:add_button"),
         InlineKeyboardButton("تعديل ترتيب زر", callback_data="startedit:order_button")],
        [InlineKeyboardButton("حذف زر", callback_data="startedit:delete_button"),
         InlineKeyboardButton("↩️ الرجوع للقائمة", callback_data="startedit:menu")],
    ])


def _images_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("اضف صورة", callback_data="startedit:image_add"),
         InlineKeyboardButton("حذف صورة", callback_data="startedit:image_delete")],
        [InlineKeyboardButton("حذف كل الصور", callback_data="startedit:image_delete_all"),
         InlineKeyboardButton("↩️ الرجوع للقائمة", callback_data="startedit:menu")],
    ])


async def _show_access(query):
    rows = await get_pool().fetch("SELECT id,user_id,username FROM start_access ORDER BY id")
    text = "المسموحين بالوصول:\n\n"
    text += "\n".join(
        f"{i}. @{r['username']}" if r["username"] else f"{i}. {r['user_id']}"
        for i, r in enumerate(rows, 1)
    ) if rows else "لا يوجد أشخاص مضافين."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("اضافة شخص", callback_data="startedit:access_add"),
         InlineKeyboardButton("حذف شخص", callback_data="startedit:access_delete")],
        [InlineKeyboardButton("↩️ الرجوع للقائمة", callback_data="startedit:menu")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard)


async def _show_images(query):
    rows = await get_pool().fetch("SELECT id FROM start_images ORDER BY image_order,id")
    await query.edit_message_text(
        f"عدد صور الستارت الحالية: {len(rows)}\n\n"
        "تقدر تضيف صور متعددة، وعند استخدام /start ترسل الصور كلها مع بعض.",
        reply_markup=_images_keyboard(),
    )


async def start_editor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.effective_chat.type != "private":
        return
    if not await _is_allowed(update.effective_user):
        raise ApplicationHandlerStop
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "اهلًا بك عزيزي المطور 🎖️\nهذي قائمة تعديل الستارت❗️",
        reply_markup=_main_keyboard(),
    )
    raise ApplicationHandlerStop


async def open_start_editor_from_panel(query, context):
    if not await _is_allowed(query.from_user):
        return
    sessions.pop(query.from_user.id, None)
    await query.edit_message_text(
        "اهلًا بك عزيزي المطور 🎖️\nهذي قائمة تعديل الستارت❗️",
        reply_markup=_main_keyboard(),
    )


async def start_editor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if not await _is_allowed(user):
        await query.answer()
        raise ApplicationHandlerStop
    await query.answer()
    data = query.data

    if data == "startedit:menu":
        sessions.pop(user.id, None)
        await query.edit_message_text("اهلًا بك عزيزي المطور 🎖️\nهذي قائمة تعديل الستارت❗️", reply_markup=_main_keyboard())
    elif data == "startedit:message":
        sessions[user.id] = {"action": "message"}
        await query.edit_message_text("حسنًا ارسل الرسالة", reply_markup=_back_keyboard())
    elif data == "startedit:buttons":
        sessions.pop(user.id, None)
        await query.edit_message_text("اختر العملية التي تريدها:", reply_markup=_buttons_keyboard())
    elif data == "startedit:add_button":
        sessions[user.id] = {"action": "button_text"}
        await query.edit_message_text("حسنًا ارسل اسم الزر", reply_markup=_back_keyboard())
    elif data in ("startedit:order_button", "startedit:delete_button"):
        rows = await get_pool().fetch("SELECT id,button_text FROM start_buttons ORDER BY button_order,id")
        if not rows:
            await query.edit_message_text("ما فيه أزرار مضافة حاليًا.", reply_markup=_buttons_keyboard())
            raise ApplicationHandlerStop
        title = "أزرارك الحالية:\n\n" + "\n".join(f"{i}. {r['button_text']}" for i,r in enumerate(rows,1))
        if data.endswith("order_button"):
            title += "\n\nارسل رقم الزر الذي تريد تغيير ترتيبه:"
            action = "order_select"
        else:
            title += "\n\nارسل رقم الزر الذي تريد حذفه:"
            action = "delete_button"
        sessions[user.id] = {"action": action, "buttons": [(r["id"],r["button_text"]) for r in rows]}
        await query.edit_message_text(title, reply_markup=_back_keyboard())
    elif data == "startedit:access":
        if user.id != OWNER_ID:
            await query.answer("لا يمكنك الدخول لهذا الزر 🚨", show_alert=True)
            raise ApplicationHandlerStop
        sessions.pop(user.id, None)
        await _show_access(query)
    elif data == "startedit:image":
        sessions.pop(user.id, None)
        await _show_images(query)
    else:
        raise ApplicationHandlerStop
    raise ApplicationHandlerStop


async def start_editor_special_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    if data in ("startedit:access_add", "startedit:access_delete") and user.id != OWNER_ID:
        await query.answer("لا يمكنك الدخول لهذا الزر 🚨", show_alert=True)
        raise ApplicationHandlerStop
    if not await _is_allowed(user):
        await query.answer()
        raise ApplicationHandlerStop
    await query.answer()
    if data == "startedit:access_add":
        sessions[user.id] = {"action": "access_add"}
        await query.edit_message_text("ارسل أيدي الشخص أو يوزره.\n\nمثال:\n8453977662\n@username", reply_markup=_back_keyboard())
    elif data == "startedit:access_delete":
        sessions[user.id] = {"action": "access_delete"}
        await query.edit_message_text("ارسل أيدي الشخص أو يوزره لحذفه.", reply_markup=_back_keyboard())
    elif data == "startedit:image_add":
        sessions[user.id] = {"action": "image_add"}
        await query.edit_message_text("ارسل الصورة.", reply_markup=_back_keyboard())
    elif data == "startedit:image_delete":
        rows = await get_pool().fetch("SELECT id FROM start_images ORDER BY image_order,id")
        if not rows:
            await query.edit_message_text("ما فيه صور حاليًا.", reply_markup=_images_keyboard())
        else:
            sessions[user.id] = {"action": "image_delete"}
            await query.edit_message_text("ارسل رقم الصورة التي تريد حذفها.", reply_markup=_back_keyboard())
    elif data == "startedit:image_delete_all":
        await get_pool().execute("DELETE FROM start_images")
        sessions.pop(user.id, None)
        await query.edit_message_text("تم حذف جميع صور الستارت ✅", reply_markup=_back_keyboard())
    raise ApplicationHandlerStop


async def start_editor_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or update.effective_chat.type != "private":
        return
    user = update.effective_user
    if not await _is_allowed(user):
        return
    session = sessions.get(user.id)
    if not session:
        return
    action = session["action"]

    if action == "message":
        text = message.text or message.caption or ""
        if not text:
            await message.reply_text("الرسالة ما تحتوي على نص أو كابشن.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        entities = message.entities if message.text else message.caption_entities
        await get_pool().execute(
            "UPDATE start_settings SET message_text=$1,message_entities=$2 WHERE id=1",
            text, json.dumps([e.to_dict() for e in (entities or [])], ensure_ascii=False),
        )
        sessions.pop(user.id, None)
        await message.reply_text("تم تعديل رسالة البدء بنجاح ✅", reply_markup=_back_keyboard())

    elif action == "button_text":
        if not message.text or not message.text.strip():
            await message.reply_text("ارسل اسم الزر كنص.", reply_markup=_back_keyboard())
        else:
            sessions[user.id] = {"action": "button_url", "button_text": message.text.strip()}
            await message.reply_text("حسنًا، الآن ارسل الرابط أو يوزر التليجرام:\n\nمثال:\nhttps://example.com\n@username", reply_markup=_back_keyboard())

    elif action == "button_url":
        if not message.text:
            await message.reply_text("ارسل الرابط أو اليوزر كنص.", reply_markup=_back_keyboard())
        else:
            url = message.text.strip()
            if url.startswith("@") and len(url) > 1:
                url = "https://t.me/" + url[1:]
            elif not re.match(r"^https?://", url, re.I):
                await message.reply_text("ارسل رابط يبدأ بـ https:// أو يوزر يبدأ بـ @", reply_markup=_back_keyboard())
                raise ApplicationHandlerStop
            max_order = await get_pool().fetchval("SELECT COALESCE(MAX(button_order),0) FROM start_buttons")
            await get_pool().execute("INSERT INTO start_buttons(button_text,button_url,button_order) VALUES($1,$2,$3)", session["button_text"], url, max_order + 1)
            sessions.pop(user.id, None)
            await message.reply_text("تمت إضافة الزر بنجاح ✅", reply_markup=_back_keyboard())

    elif action in ("order_select", "delete_button"):
        try:
            number = int((message.text or "").strip())
        except ValueError:
            await message.reply_text("ارسل رقم الزر فقط.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        buttons = session["buttons"]
        if number < 1 or number > len(buttons):
            await message.reply_text("رقم الزر غير صحيح.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        if action == "order_select":
            selected = buttons[number - 1]
            sessions[user.id] = {"action":"order_position","button_id":selected[0],"buttons":buttons}
            await message.reply_text(f"الزر المحدد: {selected[1]}\n\nارسل الترتيب الجديد.\nمثال: 1", reply_markup=_back_keyboard())
        else:
            async with get_pool().acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM start_buttons WHERE id=$1", buttons[number-1][0])
                    remaining = await conn.fetch("SELECT id FROM start_buttons ORDER BY button_order,id")
                    for i,row in enumerate(remaining,1):
                        await conn.execute("UPDATE start_buttons SET button_order=$1 WHERE id=$2", i, row["id"])
            sessions.pop(user.id, None)
            await message.reply_text("تم حذف الزر بنجاح ✅", reply_markup=_back_keyboard())

    elif action == "order_position":
        try:
            position = int((message.text or "").strip())
        except ValueError:
            await message.reply_text("ارسل رقم الترتيب فقط.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        buttons = session["buttons"]
        if position < 1 or position > len(buttons):
            await message.reply_text("الترتيب غير صحيح.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        ordered = [b for b in buttons if b[0] != session["button_id"]]
        selected = next(b for b in buttons if b[0] == session["button_id"])
        ordered.insert(position-1, selected)
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                for i,b in enumerate(ordered,1):
                    await conn.execute("UPDATE start_buttons SET button_order=$1 WHERE id=$2", i, b[0])
        sessions.pop(user.id, None)
        await message.reply_text("تم تعديل ترتيب الزر بنجاح ✅", reply_markup=_back_keyboard())

    elif action == "image_add":
        if not message.photo:
            await message.reply_text("ارسل صورة.", reply_markup=_back_keyboard())
        else:
            max_order = await get_pool().fetchval("SELECT COALESCE(MAX(image_order),0) FROM start_images")
            await get_pool().execute("INSERT INTO start_images(file_id,image_order) VALUES($1,$2)", message.photo[-1].file_id, max_order+1)
            sessions.pop(user.id, None)
            await message.reply_text("تمت إضافة الصورة بنجاح ✅", reply_markup=_back_keyboard())

    elif action == "image_delete":
        try:
            number = int((message.text or "").strip())
        except ValueError:
            await message.reply_text("ارسل رقم الصورة فقط.", reply_markup=_back_keyboard())
            raise ApplicationHandlerStop
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch("SELECT id FROM start_images ORDER BY image_order,id")
                if number < 1 or number > len(rows):
                    await message.reply_text("رقم الصورة غير صحيح.", reply_markup=_back_keyboard())
                    raise ApplicationHandlerStop
                await conn.execute("DELETE FROM start_images WHERE id=$1", rows[number-1]["id"])
                remaining = await conn.fetch("SELECT id FROM start_images ORDER BY image_order,id")
                for i,row in enumerate(remaining,1):
                    await conn.execute("UPDATE start_images SET image_order=$1 WHERE id=$2", i, row["id"])
        sessions.pop(user.id, None)
        await message.reply_text("تم حذف الصورة بنجاح ✅", reply_markup=_back_keyboard())

    elif action in ("access_add", "access_delete"):
        if user.id != OWNER_ID:
            sessions.pop(user.id, None)
            return
        value = (message.text or "").strip()
        if value.startswith("@"):
            username = value[1:].strip().lower()
            if not username:
                await message.reply_text("اليوزر غير صحيح.", reply_markup=_back_keyboard())
                raise ApplicationHandlerStop
            if action == "access_add":
                await get_pool().execute("INSERT INTO start_access(username) VALUES($1)", username)
            else:
                await get_pool().execute("DELETE FROM start_access WHERE lower(username)=$1", username)
        else:
            try:
                user_id = int(value)
            except ValueError:
                await message.reply_text("ارسل أيدي صحيح أو يوزر يبدأ بـ @.", reply_markup=_back_keyboard())
                raise ApplicationHandlerStop
            if action == "access_add":
                await get_pool().execute("INSERT INTO start_access(user_id) VALUES($1)", user_id)
            else:
                await get_pool().execute("DELETE FROM start_access WHERE user_id=$1", user_id)
        sessions.pop(user.id, None)
        await message.reply_text("تمت الإضافة إلى المسموحين بالوصول ✅" if action == "access_add" else "تم حذف الشخص من المسموحين ✅", reply_markup=_back_keyboard())

    raise ApplicationHandlerStop
