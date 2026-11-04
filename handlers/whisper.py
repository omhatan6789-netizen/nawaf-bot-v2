import html
import time
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.roles import get_rank_level


# ==================================================
# إعدادات الهمسات
# ==================================================
WHISPER_TTL = 5 * 60
LINES_PER_PAGE = 6
MAX_PAGES = 7
OWNER_ID = 8453977662

# حالة الهمسات لكل قروب: مفعلة افتراضيًا.
_whispers_enabled: Dict[int, bool] = {}


@dataclass
class WhisperDraft:
    token: str
    chat_id: int
    creator_id: int
    target_id: int
    target_name: str
    creator_name: str
    kind: str  # text / media
    creator_username: str = ""
    temporary: bool = False
    prompt_message_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Whisper:
    whisper_id: str
    chat_id: int
    message_id: int
    sender_id: int
    receiver_id: int
    sender_name: str
    receiver_name: str
    kind: str
    temporary: bool
    content: Optional[str] = None
    media_type: Optional[str] = None
    media_file_id: Optional[str] = None
    caption: Optional[str] = None
    sender_username: str = ""
    pages: List[str] = field(default_factory=list)
    receiver_opened: bool = False
    page_by_user: Dict[int, int] = field(default_factory=dict)


# الجلسات النشطة في الذاكرة.
# الهمسات المرسلة تبقى حتى إعادة تشغيل البوت.
_drafts: Dict[str, WhisperDraft] = {}
_whispers: Dict[str, Whisper] = {}


def _clean_expired_drafts() -> None:
    now = time.time()
    expired = [
        token
        for token, draft in _drafts.items()
        if now - draft.created_at >= WHISPER_TTL
    ]
    for token in expired:
        _drafts.pop(token, None)


def _display_name(user) -> str:
    return (getattr(user, "first_name", None) or "مستخدم").strip() or "مستخدم"


def _mention(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def _main_whisper_text(draft: WhisperDraft) -> str:
    return (
        f"• تم تحديد الهمسة لـ ↤︎ {_mention(draft.target_id, draft.target_name)}\n"
        "• اضغط الزر لكتابة الهمسة\n"
        "-"
    )


def _group_whisper_text(whisper: Whisper) -> str:
    return (
        f"• الهمسة لـ ↤︎ {_mention(whisper.receiver_id, whisper.receiver_name)}\n"
        f"• من ↤︎ {_mention(whisper.sender_id, whisper.sender_name)}\n"
        "-"
    )


def _start_keyboard(text_url: str, media_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("همسة نصية 💬", url=text_url)],
        [InlineKeyboardButton("همسة وسائط 🖼️", url=media_url)],
    ])


def _private_keyboard(token: str, temporary: bool) -> InlineKeyboardMarkup:
    # المؤقت متاح للنصوص فقط.
    label = "🟢 همسة مؤقتة ." if temporary else "🔴 همسة مؤقتة ."
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"wh_temp:{token}")]
    ])


def _view_keyboard(
    whisper_id: str,
    sender_name: str,
    reply_url: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "فتح الهمسة",
                callback_data=f"wh_open:{whisper_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"اهمس لـ {sender_name}",
                url=reply_url
            )
        ],
    ])


def _split_pages(text: str) -> List[str]:
    """تقسيم الهمسة إلى صفحات: بحد أقصى 6 سطور وقرابة 180 حرفًا للصفحة."""
    MAX_PAGE_CHARS = 180

    raw_lines = text.splitlines() or [""]
    prepared_lines: List[str] = []

    for line in raw_lines:
        if not line:
            prepared_lines.append("")
            continue

        while len(line) > MAX_PAGE_CHARS:
            prepared_lines.append(line[:MAX_PAGE_CHARS])
            line = line[MAX_PAGE_CHARS:]
        prepared_lines.append(line)

    pages: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in prepared_lines:
        extra = len(line) + (1 if current else 0)

        if current and (
            len(current) >= LINES_PER_PAGE
            or current_len + extra > MAX_PAGE_CHARS
        ):
            pages.append("\n".join(current))
            current = []
            current_len = 0

        current.append(line)
        current_len += len(line) + (1 if len(current) > 1 else 0)

    if current or not pages:
        pages.append("\n".join(current))

    return pages


def _page_text(whisper: Whisper, user_id: int, page_index: int) -> str:
    page = whisper.pages[page_index]
    # Telegram CallbackQuery answer محدود بـ 200 حرفًا. نحافظ على شكل الصفحة
    # كما هو قدر الإمكان؛ الصفحات التي تتجاوز الحد تُرسل في الخاص بدل القص.
    return page


def _is_whispers_enabled(chat_id: int) -> bool:
    return _whispers_enabled.get(chat_id, True)


async def _can_manage_whispers(user_id: int, chat_id: int) -> bool:
    try:
        return await get_rank_level(user_id, chat_id) >= 2
    except Exception:
        return user_id == OWNER_ID


async def enable_whispers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    user = update.effective_user
    if not user or not await _can_manage_whispers(user.id, update.effective_chat.id):
        return

    _whispers_enabled[update.effective_chat.id] = True
    await update.message.reply_text("• تم تفعيل الهمسات بنجاح .")


async def disable_whispers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    user = update.effective_user
    if not user or not _can_manage_whispers(user.id):
        return

    _whispers_enabled[update.effective_chat.id] = False
    await update.message.reply_text("• تم تعطيل الهمسات بنجاح .")


async def whispers_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الهمسات - أمر خاص بالمطور الأساسي فقط."""
    if not update.message or update.effective_chat.type != ChatType.PRIVATE:
        return

    user = update.effective_user
    if not user or user.id != OWNER_ID:
        return

    if not _whispers:
        await update.message.reply_text("• لا توجد همسات مسجلة حاليًا .")
        return

    # كل همسة في رسالة مستقلة حتى لا نصل لحد 4096 حرفًا.
    for whisper in _whispers.values():
        username = f"@{whisper.sender_username}" if whisper.sender_username else "لا يوجد"

        if whisper.kind == "text":
            whisper_content = whisper.content or ""
        elif whisper.media_type == "photo":
            whisper_content = "[صورة]"
            if whisper.caption:
                whisper_content += f"\n{whisper.caption}"
        elif whisper.media_type == "animation":
            whisper_content = "[GIF / متحركة]"
            if whisper.caption:
                whisper_content += f"\n{whisper.caption}"
        elif whisper.media_type == "sticker":
            whisper_content = "[ملصق]"
        else:
            whisper_content = "[وسائط]"

        temporary = "\nنوع الهمسة: مؤقتة 🔴" if whisper.temporary else ""
        text = (
            f"الاسم: {whisper.sender_name}\n"
            f"اليوزر: {username}\n"
            f"همسته: {whisper_content}"
            f"{temporary}\n"
            f"مستلم الهمسة: {whisper.receiver_name}"
        )

        # تقسيم التقرير أيضًا إذا كانت الهمسة نفسها أطول من حد رسالة تيليجرام.
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i + 4000])


async def whisper_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """همسه/همسة/اهمس - يعمل فقط عند الرد على شخص."""
    if not update.message or update.message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if not _is_whispers_enabled(update.effective_chat.id):
        return

    reply = update.message.reply_to_message
    if not reply or not reply.from_user:
        return

    target = reply.from_user
    creator = update.effective_user
    if not creator:
        return

    # ممنوع الهمس للنفس.
    if target.id == creator.id:
        return

    # ممنوع الهمس للبوت.
    if getattr(target, "is_bot", False):
        return

    # تنظيف الجلسات المنتهية.
    _clean_expired_drafts()

    token = secrets.token_urlsafe(10)
    draft = WhisperDraft(
        token=token,
        chat_id=update.effective_chat.id,
        creator_id=creator.id,
        target_id=target.id,
        target_name=_display_name(target),
        creator_name=_display_name(creator),
        kind="pending",
        creator_username=getattr(creator, "username", None) or "",
    )
    _drafts[token] = draft

    me = await context.bot.get_me()
    text_url = f"https://t.me/{me.username}?start=whisper_text_{token}"
    media_url = f"https://t.me/{me.username}?start=whisper_media_{token}"

    await update.message.reply_text(
        _main_whisper_text(draft),
        parse_mode="HTML",
        reply_markup=_start_keyboard(text_url, media_url),
    )


async def whisper_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يعالج /start whisper_TOKEN فقط، ويترك /start العادي للهاندلر الأصلي."""
    if not update.message or update.effective_chat.type != ChatType.PRIVATE:
        return False

    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].startswith("whisper_"):
        return False

    payload = parts[1][len("whisper_"):]
    if payload.startswith("text_"):
        kind = "text"
        token = payload[len("text_"):]
    elif payload.startswith("media_"):
        kind = "media"
        token = payload[len("media_"):]
    else:
        return False

    _clean_expired_drafts()
    draft = _drafts.get(token)

    if not draft or draft.creator_id != update.effective_user.id:
        await update.message.reply_text("❌ انتهت جلسة الهمسة، اكتب اهمس من جديد.")
        return True

    draft.kind = kind
    draft.created_at = time.time()

    draft.prompt_message_id = (
        await update.message.reply_text(
            "تمام ارسل همستك الحين .",
            reply_markup=(
                _private_keyboard(token, draft.temporary)
                if draft.kind == "text"
                else None
            ),
        )
    ).message_id

    return True


async def whisper_temp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _clean_expired_drafts()

    token = query.data.split(":", 1)[1]
    draft = _drafts.get(token)
    if not draft:
        await query.answer("❌ انتهت جلسة الهمسة، اكتب اهمس من جديد.", show_alert=True)
        return

    if query.from_user.id != draft.creator_id:
        await query.answer("❌ هذه الهمسة ليست لك.", show_alert=True)
        return

    if draft.kind != "text":
        await query.answer()
        return

    draft.temporary = not draft.temporary
    await query.answer()

    try:
        await query.edit_message_reply_markup(
            reply_markup=_private_keyboard(token, draft.temporary)
        )
    except Exception:
        pass


async def whisper_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يستقبل أول رسالة بعد تعليمات الهمسة في الخاص."""
    if not update.message or update.effective_chat.type != ChatType.PRIVATE:
        return

    _clean_expired_drafts()
    user_id = update.effective_user.id

    drafts = [d for d in _drafts.values() if d.creator_id == user_id]
    if not drafts:
        return

    # نستخدم أحدث جلسة.
    draft = max(drafts, key=lambda x: x.created_at)
    if time.time() - draft.created_at >= WHISPER_TTL:
        _drafts.pop(draft.token, None)
        return

    # لا نلتقط رسائل /start أو جلسات غير مكتملة.
    if draft.kind not in ("text", "media"):
        return

    message = update.message
    content = None
    media_type = None
    media_file_id = None
    caption = None

    if draft.kind == "text":
        if not message.text or message.text.startswith("/start"):
            return
        content = message.text
        pages = _split_pages(content)
        if len(pages) > MAX_PAGES:
            await message.reply_text("❌ الهمسة طويلة جدًا. الحد الأقصى 7 صفحات، وكل صفحة 6 سطور.")
            return
    else:
        if message.photo:
            media_type = "photo"
            media_file_id = message.photo[-1].file_id
            caption = message.caption
        elif message.animation:
            media_type = "animation"
            media_file_id = message.animation.file_id
            caption = message.caption
        elif message.sticker:
            media_type = "sticker"
            media_file_id = message.sticker.file_id
        else:
            return
        pages = []

    whisper_id = secrets.token_urlsafe(12)
    whisper = Whisper(
        whisper_id=whisper_id,
        chat_id=draft.chat_id,
        message_id=0,
        sender_id=draft.creator_id,
        receiver_id=draft.target_id,
        sender_name=draft.creator_name,
        receiver_name=draft.target_name,
        kind=draft.kind,
        sender_username=draft.creator_username,
        temporary=(draft.temporary if draft.kind == "text" else False),
        content=content,
        media_type=media_type,
        media_file_id=media_file_id,
        caption=caption,
        pages=pages,
    )

    # احذف رسالة المستخدم التي تحتوي الهمسة فقط.
    try:
        await message.delete()
    except Exception:
        pass

    _drafts.pop(draft.token, None)

    # ==================================================
    # تجهيز رابط الهمس للشخص المستلم
    # ==================================================

    reply_token = secrets.token_urlsafe(10)

    reply_draft = WhisperDraft(
        token=reply_token,
        chat_id=whisper.chat_id,
        creator_id=whisper.receiver_id,
        target_id=whisper.sender_id,
        target_name=whisper.sender_name,
        creator_name=whisper.receiver_name,
        kind="pending",
        creator_username="",
    )

    _drafts[reply_token] = reply_draft

    me = await context.bot.get_me()

    reply_url = (
        f"https://t.me/{me.username}"
        f"?start=whisper_text_{reply_token}"
    )

    sent = await context.bot.send_message(
        chat_id=whisper.chat_id,
        text=_group_whisper_text(whisper),
        parse_mode="HTML",
        reply_markup=_view_keyboard(
            whisper.whisper_id,
            whisper.sender_name,
            reply_url
        ),
    )

    whisper.message_id = sent.message_id
    _whispers[whisper.whisper_id] = whisper

    await context.bot.send_message(
        chat_id=user_id,
        text=f"تمام ارسلت همستك لـ {_display_name_from_saved(whisper.receiver_name)} بنجاح .",
    )


def _display_name_from_saved(name: str) -> str:
    return name or "مستخدم"


async def whisper_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    whisper_id = query.data.split(":", 1)[1]
    whisper = _whispers.get(whisper_id)

    if not whisper:
        await query.answer("❌ الهمسة غير موجودة.", show_alert=True)
        return

    user_id = query.from_user.id
    if user_id not in (whisper.sender_id, whisper.receiver_id):
        await query.answer("❌ هذه الهمسة ليست لك.", show_alert=True)
        return

    # الهمسة المؤقتة: المرسل يفتحها بلا استهلاك، المستلم يستهلكها من أول فتح.
    if whisper.temporary and whisper.receiver_opened:
        await query.answer("الهمسة اختفت… الهمسة كانت مؤقتة❕", show_alert=True)
        return

    if whisper.kind == "text":
        current = whisper.page_by_user.get(user_id, 0)
        if current >= len(whisper.pages):
            current = 0

        page = _page_text(whisper, user_id, current)
        page_label = f"📄 الصفحة {current + 1}/{len(whisper.pages)}"
        alert = f"{page}\n\n{page_label}"

        # CallbackQuery alert حدّه 200 حرفًا؛ الصفحات مقسمة مسبقًا لتجنب إرسالها في الخاص.
        await query.answer(alert[:200], show_alert=True)

        next_page = current + 1
        if next_page >= len(whisper.pages):
            next_page = 0
        whisper.page_by_user[user_id] = next_page

        if whisper.temporary and user_id == whisper.receiver_id:
            whisper.receiver_opened = True
            try:
                await context.bot.edit_message_text(
                    chat_id=whisper.chat_id,
                    message_id=whisper.message_id,
                    text="الهمسة اختفت… الهمسة كانت مؤقتة❕",
                )
            except Exception:
                try:
                    await context.bot.edit_message_reply_markup(
                        chat_id=whisper.chat_id,
                        message_id=whisper.message_id,
                        reply_markup=None,
                    )
                except Exception:
                    pass

        return

    # الوسائط
    if whisper.media_type == "photo":
        await context.bot.send_photo(
            chat_id=user_id,
            photo=whisper.media_file_id,
            caption=whisper.caption,
        )
    elif whisper.media_type == "animation":
        await context.bot.send_animation(
            chat_id=user_id,
            animation=whisper.media_file_id,
            caption=whisper.caption,
        )
    elif whisper.media_type == "sticker":
        await context.bot.send_sticker(
            chat_id=user_id,
            sticker=whisper.media_file_id,
        )

    await query.answer("تم فتح الهمسة.")


async def whisper_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هاندلر واحد للـ CallbackQuery الخاص بالهمسات."""
    data = update.callback_query.data or ""
    if data.startswith("wh_temp:"):
        return await whisper_temp_callback(update, context)
    if data.startswith("wh_open:"):
        return await whisper_open_callback(update, context)


def whisper_callback_filter(update: Update) -> bool:
    return bool(
        update.callback_query
        and isinstance(update.callback_query.data, str)
        and update.callback_query.data.startswith("wh_")
    )


async def whisper_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    handled = await whisper_start(update, context)
    if handled:
        raise ApplicationHandlerStop
