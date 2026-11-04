from __future__ import annotations

import json

from telegram import MessageEntity, ReplyParameters, Update
from telegram.ext import ContextTypes

from database.replies import (
    delete_all_replies as db_delete_all,
    delete_reply as db_delete,
    get_reply as db_get,
    list_replies as db_list,
    load_replies_cache,
    save_reply as db_save,
)
from database.users import get_user
from database.roles import get_rank, get_rank_level, is_developer, is_primary_developer

add_reply_sessions: dict[int, dict] = {}
add_special_reply_sessions: dict[int, dict] = {}
delete_special_reply_sessions: dict[int, bool] = {}
edit_special_reply_sessions: dict[int, dict] = {}
edit_reply_sessions: dict[int, dict] = {}
delete_reply_sessions: dict[int, bool] = {}


def clear_reply_sessions(user_id: int):
    for sessions in (
        add_reply_sessions, add_special_reply_sessions,
        delete_special_reply_sessions, edit_special_reply_sessions,
        edit_reply_sessions, delete_reply_sessions,
    ):
        sessions.pop(user_id, None)


async def _is_admin(user_id: int) -> bool:
    if await is_developer(user_id):
        return True
    return await get_rank_level(user_id) >= 2


async def _admin_error(message, special=False):
    await message.reply_text("❌ هذا الأمر للإدارة فقط" if special else "❌ ليس لديك صلاحية")


def serialize_entities(entities, message=None):
    if not entities and not message:
        return None
    serialized = []
    for entity in entities or []:
        item = {"type": entity.type, "offset": entity.offset, "length": entity.length}
        if entity.custom_emoji_id:
            item["custom_emoji_id"] = entity.custom_emoji_id
        if entity.url:
            item["url"] = entity.url
        if entity.user:
            item["user_id"] = entity.user.id
        if entity.language:
            item["language"] = entity.language
        serialized.append(item)
    if not serialized and not message:
        return None
    data = {"entities": serialized}
    if message:
        text = message.text or ""
        data.update({
            "source_chat_id": message.chat.id,
            "source_message_id": message.message_id,
            "copyable": not any(token in text for token in (
                "#الاسم", "#يوزره", "#اليوزر", "#الرسائل",
                "#الايدي", "#الرتبه", "#التعديل", "#النقاط",
            )),
        })
    return data


def deserialize_reply_metadata(value):
    if not value:
        return None, None, None, False
    try:
        data = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, None, None, False
    if isinstance(data, list):
        entities_data, source_chat_id, source_message_id, copyable = data, None, None, False
    elif isinstance(data, dict):
        entities_data = data.get("entities") or []
        source_chat_id = data.get("source_chat_id")
        source_message_id = data.get("source_message_id")
        copyable = bool(data.get("copyable"))
    else:
        return None, None, None, False
    result = []
    for item in entities_data:
        if not isinstance(item, dict):
            continue
        try:
            kwargs = {}
            for key in ("custom_emoji_id", "url", "language"):
                if item.get(key):
                    kwargs[key] = item[key]
            result.append(MessageEntity(
                type=item["type"], offset=int(item["offset"]),
                length=int(item["length"]), **kwargs,
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return result or None, source_chat_id, source_message_id, copyable


def _message_content(message):
    if message.text is not None:
        return message.text, "text", None, serialize_entities(message.entities, message)
    if message.photo:
        return message.photo[-1].file_id, "photo", message.caption, None
    if message.video:
        return message.video.file_id, "video", message.caption, None
    if message.animation:
        return message.animation.file_id, "animation", message.caption, None
    if message.sticker:
        return message.sticker.file_id, "sticker", None, None
    if message.voice:
        return message.voice.file_id, "voice", None, None
    if message.audio:
        return message.audio.file_id, "audio", message.caption, None
    if message.document:
        return message.document.file_id, "document", message.caption, None
    return None, None, None, None


async def _save_session_content(update: Update, sessions: dict, special: bool):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or user.id not in sessions:
        return
    session = sessions[user.id]
    command = "اضف رد مميز" if special else "اضف رد"
    if message.text == command:
        return
    if session.get("step") == "name":
        if not message.text:
            await message.reply_text("❌ أرسل имя الرد كنص" if special else "❌ أرسل الاسم كنص")
            return
        session["name"] = message.text.strip()
        session["step"] = "content"
        await message.reply_text(
            "• حسناً يمكنك اضافة\n"
            "( نص, صوره, فيديو, متحركه, بصمه, اغنيه, ملف, ملصق )\n\n"
            "ويمكنك اضافة الرد بتلك الطريقة :\n\n"
            "▹ #الاسم - اسم العضو .\n"
            "▹ #يوزره - يوزر الرد .\n"
            "▹ #اليوزر - يوزر مرسل الرساله .\n"
            "▹ #الرسائل - عدد رسائل المستخدم .\n"
            "▹ #الايدي - ايدي المستخدم .\n"
            "▹ #الرتبه - رتبة المستخدم .\n"
            "▹ #التعديل - عدد تعديلات .\n"
            "▹ #النقاط - نقاط المستخدم ."
        )
        return
    if session.get("step") != "content":
        return
    content, reply_type, caption, entities = _message_content(message)
    if content is None:
        await message.reply_text("❌ هذا النوع غير مدعوم")
        return
    name = session["name"]
    await db_save(name, content, reply_type, caption, entities, special=special)
    sessions.pop(user.id, None)
    await message.reply_text(
        f"⭐ تم حفظ الرد المميز: {name}" if special else f"✅ تم إضافة الرد: {name}"
    )


async def add_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message)
        return
    add_reply_sessions[user.id] = {"step": "name"}
    await message.reply_text("حسنًا، ارسل اسم الرد")


async def add_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_session_content(update, add_reply_sessions, False)


async def add_special_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    add_special_reply_sessions[user.id] = {"step": "name"}
    await message.reply_text("⭐ أرسل اسم الرد المميز")


async def add_special_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_session_content(update, add_special_reply_sessions, True)


async def _list_replies(update: Update, special: bool):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    names = await db_list(special)
    if not names:
        await message.reply_text("📭 لا توجد ردود مميزة" if special else "📭 لا يوجد ردود")
        return
    if special:
        body = "⭐ قائمة الردود المميزة:\n\n"
    else:
        body = "📋 الردود:\n\n"
    body += "".join(f"• {name}\n" for name in names)
    await message.reply_text(body)


async def replies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_replies(update, False)


async def special_replies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _list_replies(update, True)


async def _start_delete(update: Update, sessions: dict, special: bool):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    sessions[user.id] = True
    if special:
        await message.reply_text("⭐ أرسل اسم الرد المميز الذي تريد حذفه")
    else:
        await message.reply_text("🗑️ أرسل اسم الرد الذي تريد حذفه")


async def delete_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_delete(update, delete_reply_sessions, False)


async def delete_special_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_delete(update, delete_special_reply_sessions, True)


async def _delete_handler(update: Update, sessions: dict, special: bool):
    message, user = update.effective_message, update.effective_user
    if not message or not user or user.id not in sessions:
        return
    trigger = "مسح رد مميز" if special else "مسح رد"
    if message.text == trigger or not message.text:
        return
    name = message.text.strip()
    deleted = await db_delete(name, special)
    sessions.pop(user.id, None)
    if special:
        await message.reply_text(
            f"✅ تم حذف الرد المميز: {name}" if deleted else "❌ لم أجد رد مميز بهذا الاسم"
        )
    else:
        await message.reply_text(
            f"✅ تم حذف الرد: {name}" if deleted else "❌ لا يوجد رد بهذا الاسم"
        )


async def delete_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _delete_handler(update, delete_reply_sessions, False)


async def delete_special_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _delete_handler(update, delete_special_reply_sessions, True)


async def _start_edit(update: Update, sessions: dict, special: bool):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    sessions[user.id] = {"step": "name"}
    if special:
        await message.reply_text("⭐ أرسل اسم الرد المميز الذي تريد تعديله")
    else:
        await message.reply_text("✏️ أرسل اسم الرد الذي تريد تعديله")


async def edit_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_edit(update, edit_reply_sessions, False)


async def edit_special_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_edit(update, edit_special_reply_sessions, True)


async def _edit_handler(update: Update, sessions: dict, special: bool):
    message, user = update.effective_message, update.effective_user
    if not message or not user or user.id not in sessions:
        return
    trigger = "تعديل رد مميز" if special else "تعديل رد"
    if message.text == trigger:
        return
    session = sessions[user.id]
    if session["step"] == "name":
        if not message.text:
            await message.reply_text("❌ أرسل اسم الرد كنص")
            sessions.pop(user.id, None)
            return
        name = message.text.strip()
        if not await db_get(name, special):
            await message.reply_text(
                "❌ لا يوجد رد مميز بهذا الاسم" if special else "❌ لا يوجد رد بهذا الاسم"
            )
            sessions.pop(user.id, None)
            return
        session["name"] = name
        session["step"] = "content"
        await message.reply_text(
            "✅ تم العثور على الرد\n\nأرسل المحتوى الجديد للرد المميز"
            if special else "✅ تم العثور على الرد\n\nأرسل المحتوى الجديد"
        )
        return
    if session.get("step") != "content":
        return
    content, reply_type, caption, entities = _message_content(message)
    if content is None:
        await message.reply_text("❌ هذا النوع غير مدعوم")
        return
    name = session["name"]
    await db_save(name, content, reply_type, caption, entities, special=special)
    sessions.pop(user.id, None)
    await message.reply_text(
        f"⭐ تم تعديل الرد المميز: {name}" if special else f"✅ تم تعديل الرد: {name}"
    )


async def edit_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _edit_handler(update, edit_reply_sessions, False)


async def edit_special_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _edit_handler(update, edit_special_reply_sessions, True)


async def delete_all_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    await db_delete_all(False)
    await message.reply_text("✅ تم حذف جميع الردود العادية")


async def delete_all_special_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.effective_message, update.effective_user
    if not message or not user:
        return
    if not await _is_admin(user.id):
        await _admin_error(message, True)
        return
    await db_delete_all(True)
    await message.reply_text("⭐ تم حذف جميع الردود المميزة")


def replace_user_data(text, user, messages=0, rank="عضو", points=0):
    if not text:
        return text
    username = f"@{user.username}" if user.username else "لا يوجد"
    return (
        text.replace("#الاسم", user.first_name or "مستخدم")
        .replace("#يوزره", username)
        .replace("#اليوزر", username)
        .replace("#الرسائل", str(messages))
        .replace("#الايدي", str(user.id))
        .replace("#الرتبه", rank)
        .replace("#التعديل", "0")
        .replace("#النقاط", str(points))
    )


async def get_reply_user_data(user, content=None, caption=None, chat_id=None):
    needs = any(token in (content or "") or token in (caption or "") for token in (
        "#الرسائل", "#الرتبه", "#النقاط"
    ))
    if not needs:
        return 0, "عضو", 0
    data = await get_user(user.id)
    if not data:
        return 0, "عضو", 0
    messages = int(data.get("messages", 0) or 0)
    rank = await get_rank(user.id, chat_id)
    points = int(data.get("points", 0) or 0)
    return messages, rank, points


async def send_reply_content(update, context, content, reply_type, caption=None,
                             entities=None, source_chat_id=None, source_message_id=None,
                             copyable=False):
    message = update.effective_message
    if reply_type == "text":
        if copyable and source_chat_id and source_message_id:
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=int(source_chat_id),
                    message_id=int(source_message_id),
                    reply_parameters=ReplyParameters(message_id=message.message_id),
                )
                return
            except Exception:
                pass
        await message.reply_text(content, entities=entities)
    elif reply_type == "photo":
        await message.reply_photo(photo=content, caption=caption)
    elif reply_type == "video":
        await message.reply_video(video=content, caption=caption)
    elif reply_type == "animation":
        await message.reply_animation(animation=content, caption=caption)
    elif reply_type == "sticker":
        await message.reply_sticker(sticker=content)
    elif reply_type == "voice":
        await message.reply_voice(voice=content)
    elif reply_type == "audio":
        await message.reply_audio(audio=content, caption=caption)
    elif reply_type == "document":
        await message.reply_document(document=content, caption=caption)


async def check_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not message.text or not user or not chat:
        return
    # Do not trigger replies while the user is in a multi-step admin flow.
    if any(user.id in sessions for sessions in (
        add_reply_sessions, add_special_reply_sessions,
        delete_special_reply_sessions, edit_special_reply_sessions,
        edit_reply_sessions, delete_reply_sessions,
    )):
        return
    normal, special = await load_replies_cache()
    lowered = message.text.lower()
    for row in special:
        name, content, reply_type, caption, metadata = row
        if name.lower() not in lowered:
            continue
        entities, source_chat_id, source_message_id, copyable = deserialize_reply_metadata(metadata)
        messages, rank, points = await get_reply_user_data(user, content, caption, chat.id)
        content = replace_user_data(content, user, messages, rank, points)
        caption = replace_user_data(caption, user, messages, rank, points)
        await send_reply_content(
            update, context, content, reply_type, caption, entities,
            source_chat_id, source_message_id, copyable,
        )
        return
    reply = normal.get(message.text)
    if not reply:
        return
    content, reply_type, caption, metadata = reply
    entities, source_chat_id, source_message_id, copyable = deserialize_reply_metadata(metadata)
    messages, rank, points = await get_reply_user_data(user, content, caption, chat.id)
    content = replace_user_data(content, user, messages, rank, points)
    caption = replace_user_data(caption, user, messages, rank, points)
    await send_reply_content(
        update, context, content, reply_type, caption, entities,
        source_chat_id, source_message_id, copyable,
    )
