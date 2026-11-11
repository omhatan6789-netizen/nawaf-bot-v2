from __future__ import annotations

from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.points import get_points
from database.roles import OWNER_ID, get_rank
from handlers.cache import ensure_user_loaded, get_user_data
from handlers.roles import get_target_user
from music_call import get_music_client


async def user_id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor:
        return

    # يدعم أمر ايدي منفردًا أو بالرد على رسالة الشخص.
    target = await get_target_user(update, context) if (
        message.reply_to_message or len((message.text or "").strip().split()) > 1
    ) else actor
    if target is None:
        await message.reply_text("❌ حدد الشخص بالرد أو اليوزر أو الآيدي.")
        return

    user_id = int(target.id)
    username_value = getattr(target, "username", None)
    first_name_value = getattr(target, "first_name", None) or ""

    try:
        profile = await ensure_user_loaded(
            user_id,
            username=username_value,
            first_name=first_name_value,
            is_bot=bool(getattr(target, "is_bot", False)),
        )
    except Exception:
        profile = await get_user_data(user_id)

    if profile is None:
        # تعذّر إنشاء/قراءة السجل؛ لا نعرض أرقامًا مفترضة.
        await message.reply_text("❌ تعذر جلب بيانات المستخدم حاليًا.")
        return

    try:
        rank = await get_rank(user_id, chat.id if chat else None) or "عضو"
    except Exception:
        rank = "عضو"

    try:
        points = await get_points(user_id)
    except Exception:
        points = int(profile.get("points") or 0)

    bio = "لا يوجد"
    display_name = first_name_value or "غير معروف"
    try:
        music_client = get_music_client()
        user_info = await music_client.get_chat(user_id) if music_client is not None else None
        if user_info is None:
            raise RuntimeError("Assistant account could not load user profile")
        bio = getattr(user_info, "bio", None) or "لا يوجد"
        display_name = (
            getattr(user_info, "first_name", None)
            or getattr(user_info, "title", None)
            or display_name
        )
        username_value = getattr(user_info, "username", None) or username_value
    except Exception:
        pass

    username_text = f"@{username_value}" if username_value else "لا يوجد"
    joined_date = profile.get("joined_date") or "غير معروف"
    if hasattr(joined_date, "strftime"):
        joined_date = joined_date.strftime("%Y/%m/%d")

    rank_text = escape(str(rank))
    if user_id == OWNER_ID:
        rank_text = f"<tg-spoiler>{rank_text}</tg-spoiler>"

    caption = (
        "\n🌷ᵂᴱᴸᶜᴼᴹᴱ ᵀᴼ ᴳᴿᴼᵁᴾ🌷\n"
        "- عـيـونـي تـنـظـفـت يـوم شـفـت افـتارك\n"
        f"🖱️ Name 𖦹 {escape(str(display_name))}\n"
        f"🖥️ USER 𖦹 {escape(str(username_text))}\n"
        f"💬 MSG 𖦹 {int(profile.get('messages') or 0)}\n"
        f"🛡 STA 𖦹 {rank_text}\n"
        f"ℹ️ ID 𖦹 <code>{user_id}</code>\n"
        f"🗒 BIO 𖦹 {escape(str(bio))}\n"
        f"📅 Joined Group 𖦹 {escape(str(joined_date))}"
    )

    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count:
            photo_id = photos.photos[0][-1].file_id
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🌷",
                    url="https://t.me/Lewadbot",
                )
            ]])

            await message.reply_photo(
                photo=photo_id,
                caption=caption,
                parse_mode="HTML",
                has_spoiler=True,
                reply_markup=keyboard,
            )
            return
    except Exception:
        pass

    await message.reply_text(caption, parse_mode="HTML")
