import asyncio
import re

from telegram import MessageEntity, Update
from telegram.ext import ContextTypes

from database.pool import get_pool
from handlers.roles import get_rank


# =========================================================
# الإعدادات
# =========================================================

OWNER_ID = 8453977662

SEND_COMMAND_RE = re.compile(
    r"^/send(?:@[A-Za-z0-9_]+)?(?:\s+([\s\S]+))?$",
    re.IGNORECASE,
)


# =========================================================
# جلسات /send في الخاص
# =========================================================

send_sessions = {}


SEND_MEDIA_TYPES = {
    "صورة": "photo",
    "صور": "photo",

    "فيديو": "video",
    "فديو": "video",

    "gif": "animation",
    "جي اي اف": "animation",
    "جيف": "animation",

    "ملصق": "sticker",
    "ستيكر": "sticker",

    "فويس": "voice",
    "رسالة صوتية": "voice",

    "صوت": "audio",
    "اغنية": "audio",
    "أغنية": "audio",

    "ملف": "document",
    "مستند": "document",
}


SEND_MEDIA_LABELS = {
    "photo": "الصورة 📷",
    "video": "الفيديو 🎥",
    "animation": "الـ GIF 🎞️",
    "sticker": "الملصق 🧩",
    "voice": "الفويس 🎤",
    "audio": "المقطع الصوتي 🎵",
    "document": "الملف 📎",
}


# =========================================================
# أدوات عامة
# =========================================================

def get_message_text(message):
    if not message:
        return ""

    if message.text is not None:
        return message.text

    if message.caption is not None:
        return message.caption

    return ""


def get_message_entities(message):
    if not message:
        return []

    if message.text is not None:
        return message.entities or []

    if message.caption is not None:
        return message.caption_entities or []

    return []


# =========================================================
# الشخص الذي تم الرد على رسالته
# =========================================================

def get_replied_user(message):
    if not message or not message.reply_to_message:
        return None

    replied_message = message.reply_to_message

    if not replied_message.from_user:
        return None

    user = replied_message.from_user

    if user.is_bot:
        return None

    return user


def get_replied_message(message):
    if not message:
        return None

    return message.reply_to_message


# =========================================================
# اسم الشخص
# =========================================================

def get_target_name(user):
    if not user:
        return ""

    if user.full_name:
        return user.full_name

    if user.first_name:
        return user.first_name

    if user.username:
        return f"@{user.username}"

    return str(user.id)


# =========================================================
# اسم القروب / القناة
# =========================================================

def get_chat_name(chat):
    if not chat:
        return ""

    if getattr(chat, "title", None):
        return chat.title

    if getattr(chat, "full_name", None):
        return chat.full_name

    if getattr(chat, "username", None):
        return f"@{chat.username}"

    return ""


# =========================================================
# معالجة المتغيرات
# =========================================================

def prepare_text_and_entities(
    text,
    entities,
    *,
    chat=None,
    replied_user=None,
):
    """
    عند الرد على شخص:

    #الاسم = اسم الشخص
    #منشن = منشن الشخص

    بدون Reply:

    #الاسم = اسم القروب / القناة
    #منشن = اسم القروب / القناة
    """

    if not text:
        return text, list(entities or [])

    if replied_user:
        name_value = get_target_name(replied_user)
        mention_value = get_target_name(replied_user)
    else:
        name_value = get_chat_name(chat)
        mention_value = get_chat_name(chat)

    replacements = {
        "#الاسم": name_value,
        "#منشن": mention_value,
    }

    # =====================================================
    # إيجاد الاستبدالات
    # =====================================================

    occurrences = []

    for variable, value in replacements.items():

        start = 0

        while True:

            position = text.find(
                variable,
                start,
            )

            if position == -1:
                break

            occurrences.append(
                (
                    position,
                    position + len(variable),
                    value,
                    variable,
                )
            )

            start = (
                position
                + len(variable)
            )

    occurrences.sort(
        key=lambda item: item[0]
    )

    # =====================================================
    # منع التداخل
    # =====================================================

    filtered_occurrences = []

    last_end = -1

    for item in occurrences:

        start, end, value, variable = item

        if start < last_end:
            continue

        filtered_occurrences.append(item)

        last_end = end

    if not filtered_occurrences:
        return text, list(entities or [])

    # =====================================================
    # بناء النص الجديد
    # =====================================================

    parts = []

    position_map = []

    old_cursor = 0
    new_cursor = 0

    for start, end, value, variable in filtered_occurrences:

        before = text[
            old_cursor:start
        ]

        parts.append(before)

        for i in range(
            old_cursor,
            start,
        ):
            position_map.append(
                (
                    i,
                    new_cursor
                    + (i - old_cursor),
                )
            )

        new_cursor += len(before)

        parts.append(value)

        for i in range(
            start,
            end,
        ):
            position_map.append(
                (
                    i,
                    new_cursor,
                )
            )

        new_cursor += len(value)

        old_cursor = end

    tail = text[old_cursor:]

    parts.append(tail)

    for i in range(
        old_cursor,
        len(text),
    ):
        position_map.append(
            (
                i,
                new_cursor
                + (i - old_cursor),
            )
        )

    new_text = "".join(parts)

    # =====================================================
    # تحويل Offset
    # =====================================================

    def map_offset(old_offset):

        if old_offset <= 0:
            return 0

        if old_offset >= len(text):
            return len(new_text)

        for old_pos, new_pos in position_map:

            if old_pos == old_offset:
                return new_pos

        previous = 0

        for old_pos, new_pos in position_map:

            if old_pos > old_offset:
                break

            previous = new_pos

        return previous

    # =====================================================
    # إعادة بناء Entities
    # =====================================================

    new_entities = []

    for entity in entities or []:

        try:

            old_start = entity.offset

            old_end = (
                entity.offset
                + entity.length
            )

            new_start = map_offset(
                old_start
            )

            new_end = map_offset(
                old_end
            )

            new_length = (
                new_end
                - new_start
            )

            if new_length <= 0:
                continue

            kwargs = {
                "type": entity.type,
                "offset": new_start,
                "length": new_length,
            }

            if entity.url is not None:
                kwargs["url"] = entity.url

            if entity.user is not None:
                kwargs["user"] = entity.user

            if entity.language is not None:
                kwargs["language"] = entity.language

            if entity.custom_emoji_id is not None:
                kwargs["custom_emoji_id"] = (
                    entity.custom_emoji_id
                )

            try:

                new_entities.append(
                    MessageEntity(
                        **kwargs
                    )
                )

            except Exception:

                new_entities.append(
                    MessageEntity(
                        type=entity.type,
                        offset=new_start,
                        length=new_length,
                    )
                )

        except Exception:
            continue

    # =====================================================
    # إضافة منشن حقيقي
    # =====================================================

    if replied_user and mention_value:

        # نحدد مواقع #منشن الأصلية
        mention_positions = []

        for start, end, value, variable in filtered_occurrences:

            if variable == "#منشن":

                # تحويل مكان المتغير القديم
                new_position = map_offset(start)

                mention_positions.append(
                    new_position
                )

        for position in mention_positions:

            new_entities.append(
                MessageEntity(
                    type=MessageEntity.TEXT_MENTION,
                    offset=position,
                    length=len(mention_value),
                    user=replied_user,
                )
            )

    new_entities.sort(
        key=lambda entity: (
            entity.offset,
            entity.length,
        )
    )

    return new_text, new_entities


# =========================================================
# استخراج محتوى /send
# =========================================================

def get_send_payload(message):

    if not message:
        return None

    if not message.text:
        return None

    match = SEND_COMMAND_RE.match(
        message.text.strip()
    )

    if not match:
        return None

    payload = match.group(1)

    if payload is None:
        return ""

    return payload.strip()


# =========================================================
# تحديد نوع الوسائط المطلوبة
# =========================================================

def get_requested_media_type(payload):

    if not payload:
        return None

    value = payload.strip().lower()

    # السماح مثل:
    # GIF
    # gif
    # جيف

    return SEND_MEDIA_TYPES.get(value)


# =========================================================
# التحقق من نوع الوسائط
# =========================================================

def get_message_media_type(message):

    if message.photo:
        return "photo"

    if message.video:
        return "video"

    if message.animation:
        return "animation"

    if message.sticker:
        return "sticker"

    if message.voice:
        return "voice"

    if message.audio:
        return "audio"

    if message.document:
        return "document"

    return None


# =========================================================
# هل الرسالة من الوسائط؟
# =========================================================

def has_supported_media(message):

    return get_message_media_type(
        message
    ) is not None


# =========================================================
# إرسال محتوى الرسالة
# =========================================================

async def send_message_content(
    bot,
    target_chat_id,
    source_message,
    text,
    entities,
    *,
    reply_to_message_id=None,
):
    # =====================================================
    # نص
    # =====================================================

    if source_message.text is not None:

        return await bot.send_message(
            chat_id=target_chat_id,
            text=text or " ",
            entities=entities or None,
            reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=True,
        )

    # =====================================================
    # صورة
    # =====================================================

    if source_message.photo:

        return await bot.send_photo(
            chat_id=target_chat_id,
            photo=source_message.photo[-1].file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # فيديو
    # =====================================================

    if source_message.video:

        return await bot.send_video(
            chat_id=target_chat_id,
            video=source_message.video.file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # GIF
    # =====================================================

    if source_message.animation:

        return await bot.send_animation(
            chat_id=target_chat_id,
            animation=source_message.animation.file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Audio
    # =====================================================

    if source_message.audio:

        return await bot.send_audio(
            chat_id=target_chat_id,
            audio=source_message.audio.file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Voice
    # =====================================================

    if source_message.voice:

        return await bot.send_voice(
            chat_id=target_chat_id,
            voice=source_message.voice.file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Document
    # =====================================================

    if source_message.document:

        return await bot.send_document(
            chat_id=target_chat_id,
            document=source_message.document.file_id,
            caption=text or None,
            caption_entities=(
                entities or None
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Sticker
    # =====================================================

    if source_message.sticker:

        return await bot.send_sticker(
            chat_id=target_chat_id,
            sticker=source_message.sticker.file_id,
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Video Note
    # =====================================================

    if source_message.video_note:

        return await bot.send_video_note(
            chat_id=target_chat_id,
            video_note=source_message.video_note.file_id,
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Contact
    # =====================================================

    if source_message.contact:

        return await bot.send_contact(
            chat_id=target_chat_id,
            phone_number=(
                source_message.contact.phone_number
            ),
            first_name=(
                source_message.contact.first_name
            ),
            last_name=(
                source_message.contact.last_name
            ),
            vcard=(
                source_message.contact.vcard
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Location
    # =====================================================

    if source_message.location:

        return await bot.send_location(
            chat_id=target_chat_id,
            latitude=(
                source_message.location.latitude
            ),
            longitude=(
                source_message.location.longitude
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Venue
    # =====================================================

    if source_message.venue:

        return await bot.send_venue(
            chat_id=target_chat_id,
            latitude=(
                source_message.venue.location.latitude
            ),
            longitude=(
                source_message.venue.location.longitude
            ),
            title=(
                source_message.venue.title
            ),
            address=(
                source_message.venue.address
            ),
            foursquare_id=(
                source_message.venue.foursquare_id
            ),
            foursquare_type=(
                source_message.venue.foursquare_type
            ),
            google_place_id=(
                source_message.venue.google_place_id
            ),
            google_place_type=(
                source_message.venue.google_place_type
            ),
            reply_to_message_id=reply_to_message_id,
        )

    # =====================================================
    # Fallback
    # =====================================================

    if text:

        return await bot.send_message(
            chat_id=target_chat_id,
            text=text,
            entities=entities or None,
            reply_to_message_id=reply_to_message_id,
            allow_sending_without_reply=True,
        )

    return None


# =========================================================
# إرسال الوسائط للقروبات والقنوات
# =========================================================

async def broadcast_send(
    update,
    context,
    source_message,
    *,
    replied_user=None,
):
    """
    يرسل الرسالة لكل القروبات والقنوات المسجلة
    في developer_bot_chats.
    """

    try:

        registered_chats = await get_pool().fetch(
            """SELECT chat_id, chat_type, title, username
               FROM developer_bot_chats
               WHERE active=1 AND chat_type IN ('group','supergroup','channel')
               ORDER BY chat_id"""
        )

    except Exception:

        registered_chats = []

    original_content = (
        source_message.caption or ""
    )

    original_entities = (
        source_message.caption_entities or []
    )

    # =====================================================
    # إرسال لكل القروبات والقنوات
    # =====================================================

    for row in registered_chats:

        try:

            chat_id = row[0]
            chat_type = row[1]
            title = row[2]
            username = row[3]

            class RegisteredChat:

                def __init__(
                    self,
                    title=None,
                    username=None,
                    chat_type=None,
                ):
                    self.title = title
                    self.username = username
                    self.type = chat_type
                    self.full_name = title

            target_chat = RegisteredChat(
                title=title,
                username=username,
                chat_type=chat_type,
            )

            final_text, final_entities = (
                prepare_text_and_entities(
                    original_content,
                    original_entities,
                    chat=target_chat,
                    replied_user=replied_user,
                )
            )

            await send_message_content(
                context.bot,
                chat_id,
                source_message,
                final_text,
                final_entities,
                reply_to_message_id=None,
            )

        except Exception:
            continue


# =========================================================
# التعامل مع الوسائط المنتظرة في الخاص
# =========================================================

async def handle_send_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    user = update.effective_user

    if not user:
        return

    # =====================================================
    # فقط الخاص
    # =====================================================

    if message.chat.type != "private":
        return

    # =====================================================
    # فقط المالك الأساسي
    # =====================================================

    if user.id != OWNER_ID:
        return

    # =====================================================
    # هل توجد جلسة انتظار؟
    # =====================================================

    session = send_sessions.get(
        user.id
    )

    if not session:
        return

    requested_type = session.get(
        "type"
    )

    # =====================================================
    # تحديد نوع الوسائط المرسلة
    # =====================================================

    actual_type = get_message_media_type(
        message
    )

    # =====================================================
    # إذا أرسل نوعًا خاطئًا
    # =====================================================

    if actual_type != requested_type:

        # إلغاء العملية بالكامل
        send_sessions.pop(
            user.id,
            None,
        )

        try:
            await message.reply_text(
                "تم إلغاء العملية، أرسل /send من جديد."
            )
        except Exception:
            pass

        return

    # =====================================================
    # حفظ الـ Reply إن كانت الوسائط ردًا على رسالة
    # =====================================================

    replied_user = get_replied_user(
        message
    )

    # =====================================================
    # إرسال للقروبات والقنوات
    # =====================================================

    try:

        await broadcast_send(
            update,
            context,
            message,
            replied_user=replied_user,
        )

    except Exception:
        pass

    # =====================================================
    # حذف رسالة الوسائط من الخاص
    # =====================================================

    try:
        await message.delete()
    except Exception:
        pass

    # =====================================================
    # إنهاء الجلسة
    # =====================================================

    send_sessions.pop(
        user.id,
        None,
    )


# =========================================================
# /send
# =========================================================

async def send_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    user = update.effective_user

    if not user:
        return

    # =====================================================
    # الصلاحيات
    # =====================================================

    # -----------------------------------------------------
    # الخاص:
    # المالك الأساسي فقط
    # -----------------------------------------------------

    if message.chat.type == "private":

        if user.id != OWNER_ID:
            return

    # -----------------------------------------------------
    # القروبات والقنوات:
    # ادمن اساسي وفوق
    # -----------------------------------------------------

    else:

        rank = await get_rank(
            user.id, message.chat.id
        )

        allowed_ranks = {
            "ادمن اساسي",
            "نائب المالك",
            "المالك",
            "Dev",
        }

        if rank not in allowed_ranks:
            return

    # =====================================================
    # استخراج محتوى /send
    # =====================================================

    payload = get_send_payload(
        message
    )

    if payload is None:
        return

    # =====================================================
    # الخاص + أوامر الوسائط
    # =====================================================

    if message.chat.type == "private":

        requested_type = (
            get_requested_media_type(
                payload
            )
        )

        # -------------------------------------------------
        # /send صورة
        # /send فيديو
        # إلخ
        # -------------------------------------------------

        if requested_type:

            # حذف أي جلسة قديمة
            send_sessions.pop(
                user.id,
                None,
            )

            send_sessions[user.id] = {
                "type": requested_type,
            }

            label = SEND_MEDIA_LABELS.get(
                requested_type,
                "الوسائط",
            )

            try:
                await message.delete()
            except Exception:
                pass

            try:

                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=(
                        f"حسنًا، أرسل {label}"
                    ),
                )

            except Exception:
                pass

            return

    # =====================================================
    # النص / الوسائط العادية
    # =====================================================

    if message.text is not None:

        original_content = payload

        original_entities = []

        payload_start = message.text.find(
            payload
        )

        if payload and payload_start >= 0:

            for entity in (
                message.entities or []
            ):

                entity_start = (
                    entity.offset
                )

                entity_end = (
                    entity.offset
                    + entity.length
                )

                if entity_start < payload_start:
                    continue

                if entity_end > len(
                    message.text
                ):
                    continue

                new_offset = (
                    entity_start
                    - payload_start
                )

                if new_offset < 0:
                    continue

                try:

                    original_entities.append(
                        MessageEntity(
                            type=entity.type,
                            offset=new_offset,
                            length=entity.length,
                            url=entity.url,
                            user=entity.user,
                            language=entity.language,
                            custom_emoji_id=(
                                entity.custom_emoji_id
                            ),
                        )
                    )

                except Exception:
                    pass

    else:

        original_content = (
            message.caption or ""
        )

        original_entities = (
            message.caption_entities
            or []
        )

    # =====================================================
    # حذف رسالة /send
    # =====================================================

    try:
        await message.delete()
    except Exception:
        pass

    # =====================================================
    # التحقق من وجود محتوى
    # =====================================================

    has_media = has_supported_media(
        message
    )

    if not original_content and not has_media:
        return

    # =====================================================
    # الشخص الذي تم الرد عليه
    # =====================================================

    replied_message = (
        get_replied_message(message)
    )

    replied_user = (
        get_replied_user(message)
    )

    # =====================================================
    # القروب / السوبرقروب / القناة
    # =====================================================

    if message.chat.type in (
        "group",
        "supergroup",
        "channel",
    ):

        final_text, final_entities = (
            prepare_text_and_entities(
                original_content,
                original_entities,
                chat=message.chat,
                replied_user=replied_user,
            )
        )

        reply_to_message_id = None

        if replied_message:

            reply_to_message_id = (
                replied_message.message_id
            )

        try:

            await send_message_content(
                context.bot,
                message.chat.id,
                message,
                final_text,
                final_entities,
                reply_to_message_id=(
                    reply_to_message_id
                ),
            )

        except Exception:

            # fallback بدون Reply
            try:

                await send_message_content(
                    context.bot,
                    message.chat.id,
                    message,
                    final_text,
                    final_entities,
                    reply_to_message_id=None,
                )

            except Exception:
                pass

        return

    # =====================================================
    # الخاص
    # =====================================================

    if message.chat.type == "private":

        await broadcast_send(
            update,
            context,
            message,
            replied_user=replied_user,
        )

        return


# =========================================================
# حذف أوامر Slash
# =========================================================

async def delete_slash_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    يحذف أي رسالة تبدأ بـ /

    ما عدا:

        /

    لا يوقف تنفيذ الأوامر بعد الحذف.
    """

    message = update.effective_message

    if not message:
        return

    text = message.text

    if not text:
        return

    if not text.startswith("/"):
        return

    if text == "/":
        return

    try:
        await message.delete()
    except Exception:
        pass
