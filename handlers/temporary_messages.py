import asyncio
import json
import re
import time
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.error import Forbidden, TelegramError

from database import temporary_messages as db
from database.pool import get_pool
from database.roles import get_rank_level


OWNER_ID = 8453977662
MAX_MESSAGES = 8
MIN_INTERVAL = 300


# ==========================================
# إنشاء الجداول
# ==========================================

async def ensure_temporary_message_tables():
    # Schema is installed by migration 006.
    return None

# ==========================================
# النطاق: عام أو القروب الحالي
# ==========================================

def _scope(update, text):
    text = text.strip()

    if text.endswith(" عام"):
        return "global", 0, text[:-4].strip()

    return "chat", update.effective_chat.id, text


async def _get_rows(scope, chat_id):
    return await db.get_rows(scope, chat_id)

async def _get_row(scope, chat_id, number):
    rows = await _get_rows(scope, chat_id)
    if 1 <= number <= len(rows):
        return rows[number - 1]
    return None

async def _get_row_by_id(scope, chat_id, row_id):
    return await db.get_row_by_id(scope, chat_id, row_id)

# ==========================================
# استخراج الأزرار من الرسالة
# ==========================================

def _parse_buttons(text):
    buttons = []
    kept_lines = []
    pattern = re.compile(r"\[([^\[\]]+?)\s+-\s+([^\[\]]+?)\]")

    for line in (text or "").splitlines():
        matches = list(pattern.finditer(line))

        if (
            matches
            and "".join(m.group(0) for m in matches).replace(" ", "")
            == line.replace(" ", "")
        ):
            row = []

            for match in matches:
                label = match.group(1).strip()
                target = match.group(2).strip()

                if target.startswith("@"):
                    target = "https://t.me/" + target[1:]

                parsed = urlparse(target)
                if label and parsed.scheme in ("https", "http") and parsed.netloc:
                    row.append({"text": label, "url": target})

            if row:
                buttons.append(row)
            else:
                kept_lines.append(line)
        else:
            kept_lines.append(line)

    return "\n".join(kept_lines).strip(), buttons


def _payload_from_message(message):
    if message.text is not None:
        content, buttons = _parse_buttons(message.text)
        return {
            "type": "text",
            "text": content,
            "entities": [
                entity.to_dict()
                for entity in (message.entities or [])
            ],
        }, buttons

    caption, buttons = _parse_buttons(message.caption or "")
    payload = {
        "caption": caption,
        "caption_entities": [
            entity.to_dict()
            for entity in (message.caption_entities or [])
        ],
    }

    media_types = (
        ("photo", "photo"),
        ("video", "video"),
        ("animation", "animation"),
        ("document", "document"),
        ("audio", "audio"),
        ("voice", "voice"),
        ("video_note", "video_note"),
        ("sticker", "sticker"),
    )

    for attribute, kind in media_types:
        item = getattr(message, attribute, None)
        if not item:
            continue

        if kind == "photo":
            item = item[-1]

        payload.update({"type": kind, "file_id": item.file_id})

        if kind == "audio":
            payload["title"] = item.title
            payload["performer"] = item.performer

        return payload, buttons

    return None, []


# ==========================================
# إرسال الرسالة المحفوظة
# ==========================================

def _markup(buttons):
    if not buttons:
        return None

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(button["text"], url=button["url"])
            for button in row
        ]
        for row in buttons
    ])


async def _send_payload(bot, chat_id, payload, buttons):
    kind = payload.get("type")
    markup = _markup(buttons)
    caption = payload.get("caption") or None

    caption_entities = [
        MessageEntity.de_json(entity, bot)
        for entity in payload.get("caption_entities", [])
    ]

    if kind == "text":
        entities = [
            MessageEntity.de_json(entity, bot)
            for entity in payload.get("entities", [])
        ]
        return await bot.send_message(
            chat_id=chat_id,
            text=payload.get("text") or " ",
            entities=entities or None,
            reply_markup=markup,
        )

    file_id = payload["file_id"]

    if kind == "photo":
        return await bot.send_photo(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            reply_markup=markup,
        )
    if kind == "video":
        return await bot.send_video(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            reply_markup=markup,
        )
    if kind == "animation":
        return await bot.send_animation(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            reply_markup=markup,
        )
    if kind == "document":
        return await bot.send_document(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            reply_markup=markup,
        )
    if kind == "audio":
        return await bot.send_audio(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            title=payload.get("title"),
            performer=payload.get("performer"),
            reply_markup=markup,
        )
    if kind == "voice":
        return await bot.send_voice(
            chat_id, file_id, caption=caption,
            caption_entities=caption_entities or None,
            reply_markup=markup,
        )
    if kind == "video_note":
        sent = await bot.send_video_note(chat_id, file_id)
        if markup:
            await bot.send_message(chat_id, "\u200e", reply_markup=markup)
        return sent
    if kind == "sticker":
        sent = await bot.send_sticker(chat_id, file_id)
        if markup:
            await bot.send_message(chat_id, "\u200e", reply_markup=markup)
        return sent

    raise ValueError("نوع الرسالة غير مدعوم")


# ==========================================
# تنسيق الوقت
# ==========================================

def _format_duration(seconds):
    if not seconds:
        return "غير محدد"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}ي"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}س"
    return f"{seconds // 60}د"


def _parse_duration(text):
    match = re.fullmatch(
        r"\s*(\d+)\s*"
        r"(دقيقة|دقائق|د|ساعة|ساعه|ساعات|س|يوم|أيام|ايام|ي)"
        r"\s*",
        text or "",
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    if unit in ("دقيقة", "دقائق", "د"):
        seconds = amount * 60
    elif unit in ("ساعة", "ساعه", "ساعات", "س"):
        seconds = amount * 3600
    else:
        seconds = amount * 86400

    return seconds if seconds >= MIN_INTERVAL else None


# ==========================================
# الأوامر
# ==========================================

async def temporary_message_command(update, context):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return
    if chat.type not in ("group", "supergroup"):
        return

    text = (message.text or "").strip()
    scope, chat_id, command = _scope(update, text)

    if scope == "global":
        if user.id != OWNER_ID:
            await message.reply_text("• أوامر الرسائل المؤقتة العامة للمطور فقط.")
            return
    elif user.id != OWNER_ID and (await get_rank_level(user.id, chat.id)) < 2:
        await message.reply_text("• هذا الأمر للمشرفين وفوق فقط.")
        return

    if command in ("اضف رسالة مؤقتة", "اضف رساله مؤقته"):
        if len(await _get_rows(scope, chat_id)) >= MAX_MESSAGES:
            await message.reply_text("• وصلت للحد الأعلى، وهو 8 رسائل مؤقتة.")
            return

        context.user_data["temporary_message_pending"] = {
            "scope": scope,
            "chat_id": chat_id,
            "creator_id": user.id,
            "stage": "content",
        }
        await message.reply_text(
            "• أرسل الرسالة أو الوسائط التي تبي تكرارها.\n"
            "تقدر تضيف الأزرار في آخر الرسالة بهذا الشكل:\n"
            "[قناتي 🌷 - @channel]\n"
            "كل سطر صف مستقل، وحط أكثر من زر في السطر نفسه "
            "إذا تبيها جنب بعض."
        )
        return

    if command in ("الرسائل المؤقتة", "الرسائل المؤقته"):
        await _show_list(message, scope, chat_id)
        return

    match = re.fullmatch(r"مسح الرس(?:الة|اله) المؤقت(?:ة|ه)\s+(\d+)", command)
    if match:
        number = int(match.group(1))
        row = await _get_row(scope, chat_id, number)
        if not row:
            await message.reply_text("• مافيه رسالة يالطيب .")
            return

        await db.delete_row(scope, chat_id, row[0])

        await message.reply_text(f"• تم مسح الرسالة المؤقتة {number}.")
        return

    if command in ("مسح الرسائل المؤقتة", "مسح الرسائل المؤقته"):
        await db.delete_scope(scope, chat_id)

        await message.reply_text("• تم مسح الرسائل المؤقتة.")
        return

    match = re.fullmatch(r"ضع الرسالة\s+(\d+)", command)
    if match:
        number = int(match.group(1))
        row = await _get_row(scope, chat_id, number)
        if not row:
            await message.reply_text("• مافيه رسالة يالطيب .")
            return

        context.user_data["temporary_message_pending"] = {
            "scope": scope,
            "chat_id": chat_id,
            "creator_id": user.id,
            "stage": "duration",
            "row_id": row[0],
        }
        await message.reply_text(
            "• أرسل المدة مثل 5د أو 1س أو 2س أو 1ي.\n"
            "أقل مدة مسموحة 5 دقائق."
        )


# ==========================================
# قائمة الرسائل المؤقتة
# ==========================================

async def _show_list(message, scope, chat_id):
    rows = await _get_rows(scope, chat_id)
    title = (
        "قائمة الرسائل المؤقتة العامة:"
        if scope == "global"
        else "قائمة الرسائل المؤقتة بالقروب:"
    )

    if not rows:
        await message.reply_text(title + "\n• ما فيه رسائل مؤقتة.")
        return

    lines = [title]
    buttons = []

    for number, row in enumerate(rows, 1):
        payload = json.loads(row[1])
        raw = payload.get("text") or payload.get("caption") or "[رسالة وسائط]"
        words = raw.split()
        preview = " ".join(words[:4])
        if len(words) > 4:
            preview += "..."

        timing = f" — كل {_format_duration(row[3])}" if row[3] else " — لم يحدد الوقت"
        lines.append(f"{number} ~ {preview or 'رسالة وسائط'}{timing}")
        buttons.append(
            InlineKeyboardButton(
                f"عرض الرسالة {number}",
                callback_data=f"tmp:view:{scope}:{chat_id}:{row[0]}",
            )
        )

    keyboard = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    await message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ==========================================
# استقبال المحتوى أو مدة التكرار
# ==========================================

async def temporary_message_pending_handler(update, context):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return
    if chat.type not in ("group", "supergroup"):
        return

    pending = context.user_data.get("temporary_message_pending")
    if not pending or pending.get("creator_id") != user.id:
        return

    text = (message.text or "").strip()

    # لا تسمح لأوامر إدارة الرسائل أن تُحفظ كمحتوى جديد.
    if text and re.fullmatch(
        r"(?:اضف رسالة مؤقتة|اضف رساله مؤقته|الرسائل المؤقتة|الرسائل المؤقته|"
        r"مسح الرس(?:الة|اله) المؤقت(?:ة|ه)(?:\s+\d+)?|"
        r"مسح الرسائل المؤقتة|مسح الرسائل المؤقته|ضع الرسالة\s+\d+)(?: عام)?",
        text,
    ):
        return

    if text == "إلغاء":
        context.user_data.pop("temporary_message_pending", None)
        await message.reply_text("تم إلغاء العملية.")
        return

    scope = pending.get("scope", "chat")
    target_chat_id = pending.get("chat_id", chat.id)
    row_id = pending.get("row_id")
    stage = pending.get("stage")

    # ضبط مدة التكرار
    if stage == "duration":
        seconds = _parse_duration(text)
        if seconds is None:
            await message.reply_text(
                "• المدة غير صحيحة أو أقل من 5 دقائق.\n"
                "أرسل مثلًا: 5د أو 1س أو 2س أو 1ي."
            )
            return

        try:
            await db.set_interval(scope, target_chat_id, row_id, seconds, time.time() + seconds)
        except Exception:
            await message.reply_text("تعذر حفظ المدة. راجع سجل الأخطاء في Render.")
            return

        context.user_data.pop("temporary_message_pending", None)
        await message.reply_text(
            f"• تم ضبط تكرار الرسالة كل {_format_duration(seconds)}."
        )
        return

    # تعديل أزرار رسالة موجودة
    if stage == "edit_buttons":
        if text == "حذف الكل":
            buttons = []
        else:
            _, buttons = _parse_buttons(message.text or "")
            if not buttons:
                await message.reply_text(
                    "ما لقيت أزرارًا بالتنسيق الصحيح.\n"
                    "مثال:\n[قناتي 🌷 - @channel]\n"
                    "[حسابي 🌹 - @username]\n\n"
                    "لإزالة جميع الأزرار أرسل: حذف الكل\n"
                    "ولإلغاء العملية أرسل: إلغاء"
                )
                return

        try:
            await db.update_buttons(scope, target_chat_id, row_id, json.dumps(buttons, ensure_ascii=False))
        except Exception:
            await message.reply_text("تعذر حفظ الأزرار. راجع سجل الأخطاء في Render.")
            return

        context.user_data.pop("temporary_message_pending", None)
        await message.reply_text("تم تحديث أزرار الرسالة المؤقتة بنجاح.")
        return

    # استقبال محتوى الرسالة أو تعديل محتواها
    payload, buttons = _payload_from_message(message)
    if payload is None:
        await message.reply_text(
            "أرسل نصًا أو صورة أو فيديو أو ملفًا أو صوتًا أو ملصقًا."
        )
        return

    if stage == "edit_content":
        try:
            await db.update_payload(
                scope, target_chat_id, row_id,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(buttons, ensure_ascii=False),
            )
        except Exception:
            await message.reply_text("تعذر حفظ التعديل. راجع سجل الأخطاء في Render.")
            return

        context.user_data.pop("temporary_message_pending", None)
        await message.reply_text("تم تعديل الرسالة المؤقتة بنجاح.")
        return

    # إضافة رسالة مؤقتة جديدة
    try:
        created = await db.create_message(
            scope, target_chat_id, user.id,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(buttons, ensure_ascii=False),
            MAX_MESSAGES,
        )
    except Exception:
        await message.reply_text("تعذر حفظ الرسالة المؤقتة. راجع سجل الأخطاء في Render.")
        return
    if not created:
        context.user_data.pop("temporary_message_pending", None)
        await message.reply_text("وصلت للحد الأقصى، وهو 8 رسائل مؤقتة لهذا النطاق.")
        return

    context.user_data.pop("temporary_message_pending", None)
    await message.reply_text(
        "تمت إضافة الرسالة المؤقتة بنجاح.\n"
        "لتحديد وقت تكرارها استخدم:\n"
        "ضع الرسالة رقم"
        + (" عام" if scope == "global" else "")
    )


# ==========================================
# عرض الرسالة وأزرار التحكم
# ==========================================


async def temporary_message_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return

    parts = (query.data or "").split(":")
    if len(parts) != 5:
        await query.answer()
        return

    _, action, scope, chat_text, id_text = parts
    chat_id = int(chat_text)
    row_id = int(id_text)
    user = query.from_user

    if scope == "global":
        if user.id != OWNER_ID:
            await query.answer("هذا للمطور فقط.", show_alert=True)
            return
    elif user.id != OWNER_ID and (await get_rank_level(user.id, chat_id)) < 2:
        await query.answer("هذا للمشرفين وفوق فقط.", show_alert=True)
        return

    await query.answer()

    # جلب الرسالة المطلوبة، باستثناء الرجوع للقائمة
    row = None
    if action != "list":
        row = await _get_row_by_id(scope, chat_id, row_id)
        if not row:
            await query.answer("الرسالة غير موجودة.", show_alert=True)
            return

    # الرجوع للقائمة داخل نفس رسالة لوحة التحكم
    if action == "list":
        rows = await _get_rows(scope, chat_id)
        title = (
            "قائمة الرسائل المؤقتة العامة:"
            if scope == "global"
            else "قائمة الرسائل المؤقتة بالقروب:"
        )

        if not rows:
            await query.edit_message_text(
                title + "\n• ما فيه رسائل مؤقتة."
            )
            return

        lines = [title]
        buttons = []

        for number, item in enumerate(rows, 1):
            payload = json.loads(item[1])
            raw = (
                payload.get("text")
                or payload.get("caption")
                or "[رسالة وسائط]"
            )
            words = raw.split()
            preview = " ".join(words[:4])
            if len(words) > 4:
                preview += "..."

            timing = (
                f" — كل {_format_duration(item[3])}"
                if item[3]
                else " — لم يحدد الوقت"
            )
            lines.append(
                f"{number} ~ {preview or 'رسالة وسائط'}{timing}"
            )
            buttons.append(
                InlineKeyboardButton(
                    f"عرض الرسالة {number}",
                    callback_data=(
                        f"tmp:view:{scope}:{chat_id}:{item[0]}"
                    ),
                )
            )

        keyboard = [
            buttons[index:index + 2]
            for index in range(0, len(buttons), 2)
        ]

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # طلب تعديل المحتوى؛ نحدّث لوحة التحكم نفسها
    if action == "edit":
        context.user_data["temporary_message_pending"] = {
            "scope": scope,
            "chat_id": chat_id,
            "creator_id": user.id,
            "stage": "edit_content",
            "row_id": row_id,
        }

        await query.edit_message_text(
            "✏️ **تعديل محتوى الرسالة**\n\n"
            "أرسل الرسالة أو الوسائط الجديدة في القروب.\n"
            "لإلغاء العملية أرسل: إلغاء",
            parse_mode="Markdown",
        )
        return

    # طلب تعديل الأزرار؛ نحدّث لوحة التحكم نفسها
    if action == "buttons":
        context.user_data["temporary_message_pending"] = {
            "scope": scope,
            "chat_id": chat_id,
            "creator_id": user.id,
            "stage": "edit_buttons",
            "row_id": row_id,
        }

        await query.edit_message_text(
            "🔘 **تعديل أزرار الرسالة**\n\n"
            "أرسل الأزرار الجديدة، كل صف في سطر:\n"
            "[قناتي 🌷 - @channel]\n"
            "[حسابي 🌹 - @username]\n\n"
            "لحذف جميع الأزرار أرسل: حذف الكل\n"
            "للإلغاء أرسل: إلغاء",
            parse_mode="Markdown",
        )
        return

    # عرض تفاصيل الرسالة
    payload = json.loads(row[1])
    saved_buttons = json.loads(row[2] or "[]")
    rows = await _get_rows(scope, chat_id)

    number = next(
        (
            index
            for index, item in enumerate(rows, 1)
            if item[0] == row_id
        ),
        0,
    )

    content = (
        payload.get("text")
        or payload.get("caption")
        or f"[{payload.get('type', 'وسائط')}]"
    )

    button_info = []
    index = 0

    for button_row in saved_buttons:
        for button in button_row:
            index += 1
            button_info.append(
                f"{index} ~ اسم الزر: ( {button['text']} ) "
                f"معلومات الزر: ( {button['url']} )"
            )

    display = (
        f"الرسالة {number}:\n{content}\n\n"
        "الأزرار المضافة بالرسالة:\n"
        + (
            "\n".join(button_info)
            if button_info
            else "لا توجد أزرار."
        )
    )

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "تعديل الرسالة",
                callback_data=f"tmp:edit:{scope}:{chat_id}:{row_id}",
            ),
            InlineKeyboardButton(
                "تعديل الأزرار",
                callback_data=f"tmp:buttons:{scope}:{chat_id}:{row_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                "رجوع للقائمة",
                callback_data=f"tmp:list:{scope}:{chat_id}:{row_id}",
            ),
        ],
    ])

    # إذا كانت لوحة التحكم نصية، نحدّثها بدل إنشاء رسالة جديدة
    try:
        await query.edit_message_text(
            display[:4000],
            reply_markup=markup,
        )
    except TelegramError:
        # إذا تعذّر تعديل الرسالة، نعرض التفاصيل برسالة بديلة
        await query.message.reply_text(
            display[:4000],
            reply_markup=markup,
        )


# ==========================================
# إرسال الرسائل في وقتها المحدد
# ==========================================

async def temporary_message_scheduler(application):
    while True:
        try:
            now = time.time()
            due = await db.claim_due_messages(now)

            for row in due:
                if row[1] == "global":
                    chats = await db.get_active_chats()
                else:
                    chats = [row[2]]

                payload = json.loads(row[3])
                buttons = json.loads(row[4] or "[]")

                for target_chat_id in chats:
                    try:
                        await _send_payload(
                            application.bot, target_chat_id, payload, buttons
                        )
                    except Forbidden:
                        if row[1] == "global":
                            await db.deactivate_chat(target_chat_id)
                    except (TelegramError, ValueError) as exc:
                        print(
                            "⚠️ تعذر إرسال الرسالة المؤقتة "
                            f"{row[0]} إلى {target_chat_id}: {exc}"
                        )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"⚠️ خطأ في مجدول الرسائل المؤقتة: {exc}")

        await asyncio.sleep(5)


# ==========================================
# تسجيل القروبات لاستقبال الرسائل العامة
# ==========================================

async def track_temporary_message_chat(update, context):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        return

    try:
        await db.upsert_chat(chat.id, chat.title or "")
    except Exception:
        return
