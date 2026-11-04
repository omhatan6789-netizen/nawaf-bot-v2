import json
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    MessageEntity,
    InputMediaPhoto,
)
from telegram.ext import ContextTypes
from database.pool import get_pool
from handlers.cache import get_user_data
async def _get_start_data():
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT message_text, message_entities
            FROM start_settings
            WHERE id = 1
        """)
        images = await conn.fetch("""
            SELECT id, file_id
            FROM start_images
            ORDER BY image_order ASC, id ASC
        """)
        buttons = await conn.fetch("""
            SELECT button_text, button_url
            FROM start_buttons
            ORDER BY button_order ASC, id ASC
        """)
    if not row:
        return None, "[]", images, buttons
    return row["message_text"], row["message_entities"] or "[]", images, buttons


def _get_start_replacements(user, user_data):
    username = (
        f"@{user.username}"
        if user.username
        else "لا يوجد"
    )
    messages = 0
    rank = "عضو"
    points = 0
    if user_data:
        messages = user_data.get("messages", 0) or 0
        rank = user_data.get("rank", "عضو") or "عضو"
        points = user_data.get("points", 0) or 0
    return {
        "#الاسم": user.first_name or "مستخدم",
        "#منشن": user.first_name or "مستخدم",
        "#يوزره": username,
        "#اليوزر": username,
        "#الرسائل": str(messages),
        "#الايدي": str(user.id),
        "#الرتبه": rank,
        "#التعديل": "0",
        "#النقاط": str(points),
    }
def _replace_start_variables(text, user, user_data):
    if not text:
        return text
    replacements = _get_start_replacements(
        user,
        user_data
    )
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text
def _utf16_length(text):
    return len(
        text.encode("utf-16-le")
    ) // 2
def _load_entities(entities_json):
    try:
        raw_entities = json.loads(
            entities_json or "[]"
        )
    except Exception:
        return []
    entities = []
    for entity_data in raw_entities:
        try:
            entity = MessageEntity.de_json(
                entity_data
            )
            if entity:
                entities.append(entity)
        except Exception:
            continue
    return entities
def _build_start_text_and_entities(
    original_text,
    original_entities,
    user,
    user_data
):
    replacements = _get_start_replacements(
        user,
        user_data
    )
    # إذا ما فيه متغيرات أصلًا، نرجع النص والـ entities
    # كما هي بدون أي تعديل.
    has_variables = any(
        key in original_text
        for key in replacements
    )
    if not has_variables:
        return original_text, original_entities
    # تسجيل أماكن المتغيرات في النص الأصلي
    replacement_positions = []
    for key, value in replacements.items():
        search_from = 0
        while True:
            position = original_text.find(
                key,
                search_from
            )
            if position == -1:
                break
            old_start = _utf16_length(
                original_text[:position]
            )
            old_length = _utf16_length(key)
            new_length = _utf16_length(value)
            replacement_positions.append({
                "start": old_start,
                "end": old_start + old_length,
                "old_length": old_length,
                "new_length": new_length,
                "key": key,
            })
            search_from = (
                position + len(key)
            )
    replacement_positions.sort(
        key=lambda item: item["start"]
    )
    final_text = original_text
    # استبدال النص
    for key, value in replacements.items():
        final_text = final_text.replace(
            key,
            value
        )
    # نسخ الـ entities بعد تعديل offsets
    final_entities = []
    for old_entity in original_entities:
        old_offset = old_entity.offset or 0
        old_length = old_entity.length or 0
        old_end = old_offset + old_length
        new_offset = old_offset
        new_length = old_length
        for replacement in replacement_positions:
            start = replacement["start"]
            end = replacement["end"]
            difference = (
                replacement["new_length"]
                - replacement["old_length"]
            )
            # المتغير قبل الـ entity
            if end <= old_offset:
                new_offset += difference
            # المتغير داخل الـ entity
            elif (
                start >= old_offset
                and end <= old_end
            ):
                new_length += difference
        # إنشاء Entity جديدة بدل تعديل الأصل
        # حتى نحافظ على جميع الخصائص مثل:
        # bold / italic / spoiler / underline / link / custom emoji
        try:
            new_entity = MessageEntity(
                type=old_entity.type,
                offset=new_offset,
                length=new_length,
                url=old_entity.url,
                user=old_entity.user,
                language=old_entity.language,
                custom_emoji_id=old_entity.custom_emoji_id,
            )
            final_entities.append(
                new_entity
            )
        except Exception:
            # إذا تعذر إنشاء Entity معينة،
            # نحافظ على الأصل بدل حذف جميع التنسيقات.
            final_entities.append(
                old_entity
            )
    # ==================================================
    # إنشاء منشن قابل للضغط
    # ==================================================
    for replacement in replacement_positions:
        if replacement["key"] != "#منشن":
            continue
        old_start = replacement["start"]
        # نحسب مكان المنشن بعد كل الاستبدالات
        # التي جاءت قبله في النص.
        new_offset = old_start
        for previous in replacement_positions:
            if previous is replacement:
                break
            if previous["end"] <= old_start:
                new_offset += (
                    previous["new_length"]
                    - previous["old_length"]
                )
        mention_text = replacements["#منشن"]
        mention_entity = MessageEntity(
            type="text_mention",
            offset=new_offset,
            length=_utf16_length(mention_text),
            user=user,
        )
        final_entities.append(
            mention_entity
        )
    return final_text, final_entities
def _build_start_keyboard(buttons):
    if not buttons:
        return None
    rows = []
    # كل زرين في صف واحد
    for i in range(0, len(buttons), 2):
        row = []
        for button_text, button_url in buttons[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=button_text,
                    url=button_url
                )
            )
        rows.append(row)
    return InlineKeyboardMarkup(rows)
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    # تجاهل Deep Links مثل:
    # /start commands
    # /start whisper_xxx
    if context.args:
        return
    user = update.effective_user
    chat_id = update.effective_chat.id
    message_text, entities_json, images, buttons = (
        await _get_start_data()
    )
    # إذا ما فيه رسالة مخصصة
    if not message_text:
        message_text = (
            f"حياك الله {user.first_name} 🤍\n"
            "في البوت الجديد ⭐"
        )
        entities_json = "[]"
    # جلب بيانات المستخدم من الكاش
    user_data = await get_user_data(
        user.id
    )
    # تحميل تنسيقات الرسالة المحفوظة
    entities = _load_entities(
        entities_json
    )
    # إنشاء النص النهائي + الحفاظ على التنسيقات
    final_text, entities = (
        _build_start_text_and_entities(
            message_text,
            entities,
            user,
            user_data
        )
    )
    # إنشاء الأزرار
    reply_markup = _build_start_keyboard(
        buttons
    )
    # ==================================================
    # صورة واحدة
    # ==================================================
    if len(images) == 1:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=images[0][1],
            caption=final_text,
            caption_entities=entities or None,
            reply_markup=reply_markup
        )
        return
    # ==================================================
    # أكثر من صورة
    # ==================================================
    if len(images) > 1:
        media = []
        for index, image in enumerate(images):
            if index == len(images) - 1:
                media.append(
                    InputMediaPhoto(
                        media=image[1],
                        caption=final_text,
                        caption_entities=entities or None
                    )
                )
            else:
                media.append(
                    InputMediaPhoto(
                        media=image[1]
                    )
                )
        await context.bot.send_media_group(
            chat_id=chat_id,
            media=media
        )
        # Telegram لا يسمح بوضع Inline Keyboard
        # مباشرة على Media Group.
        if reply_markup:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⠀",
                reply_markup=reply_markup
            )
        return
    # ==================================================
    # بدون صورة
    # ==================================================
    await context.bot.send_message(
        chat_id=chat_id,
        text=final_text,
        entities=entities or None,
        reply_markup=reply_markup
    )
