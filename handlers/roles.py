from __future__ import annotations

from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import ContextTypes

from database.users import get_user
from handlers.target_lookup import resolve_message_user
from database.roles import (
    OWNER_ID, DEV_PRIMARY, DEV_SECONDARY, RANK_LEVELS, NORMAL_RANKS,
    add_group_rank, remove_group_rank, update_developer_rank,
    get_developer_type, is_developer, is_primary_developer,
    get_rank, get_rank_level, has_group_rank, get_group_rank_users,
    get_users_by_group_rank, get_secondary_developers, clear_secondary_developers,
    clear_rank_list, clear_group_ranks, clear_lower_group_ranks,
    check_command_permission, normalize_rank,
)

ROLE_LIST_NAMES = {
    "المميزين": "مميز",
    "الادمنية": "ادمن",
    "الادمنية الاساسيين": "ادمن اساسي",
    "نواب المالك": "نائب المالك",
    "المالكين": "المالك",
}
ROLE_TITLES = {
    "مميز": "المميزين",
    "ادمن": "الادمنية",
    "ادمن اساسي": "الادمنية الاساسيين",
    "نائب المالك": "نواب المالك",
    "المالك": "المالكين",
}
ROLE_COMMANDS = {
    "رفع Dev": ("Dev", True),
    "رفع المالك": ("المالك", True),
    "رفع نائب المالك": ("نائب المالك", True),
    "رفع ادمن اساسي": ("ادمن اساسي", True),
    "رفع ادمن": ("ادمن", True),
    "رفع مميز": ("مميز", True),
    "تنزيل Dev": ("Dev", False),
    "تنزيل المالك": ("المالك", False),
    "تنزيل نائب المالك": ("نائب المالك", False),
    "تنزيل ادمن اساسي": ("ادمن اساسي", False),
    "تنزيل ادمن": ("ادمن", False),
    "تنزيل مميز": ("مميز", False),
}


def role_mention(user_id: int, name: str | None = None) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{escape(str(name or user_id))}</a>'


async def get_user_mention(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    name = None
    try:
        info = await context.bot.get_chat(user_id)
        name = (
            getattr(info, "first_name", None)
            or getattr(info, "title", None)
            or getattr(info, "username", None)
        )
    except Exception:
        pass
    saved_username = None
    if not name or str(name).strip() == str(user_id):
        name = None
        try:
            row = await get_user(user_id)
            if row:
                saved_name = (row["first_name"] or "").strip()
                saved_username = row["username"]
                if saved_name and saved_name != str(user_id):
                    name = saved_name
        except Exception:
            pass
    # Refresh legacy rows through the assistant account, preferring a saved username.
    if not name:
        try:
            from music_call import get_music_client
            from database.moderation import save_target_user

            music_client = get_music_client()
            if music_client is not None:
                profile = await music_client.get_users(saved_username or int(user_id))
                if profile:
                    name = profile.first_name or profile.username
                    await save_target_user(profile)
        except Exception:
            pass
    if not name:
        name = f"@{saved_username}" if saved_username else None
    return role_mention(user_id, name or str(user_id))


async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await resolve_message_user(update, context, token_index=1)


def rank_permission_message(rank: str) -> str:
    level = RANK_LEVELS.get(rank, 0)
    next_rank = next((name for name, value in RANK_LEVELS.items() if value == level + 1), None)
    if next_rank == "Dev":
        return "• اعذرني بس هذا الأمر لـ ↤︎〖 Dev 〗 فقط ."
    if next_rank:
        return f"• اعذرني بس هذا الأمر لـ ↤︎〖 {next_rank} 〗 فقط ."
    return "• اعذرني بس ما عندك الصلاحية لهذا الأمر ."


async def _can_change(actor_id: int, target_id: int, rank: str, chat_id: int | None = None):
    actor_dev = await get_developer_type(actor_id)
    target_dev = await get_developer_type(target_id)
    if rank == "Dev":
        if actor_dev != DEV_PRIMARY:
            return False, "• اعذرني بس هذا الأمر للمطور الأساسي فقط ."
        if target_id == OWNER_ID:
            return False, "❌ لا يمكن تعديل المطور الأساسي."
        if target_dev == DEV_SECONDARY:
            return False, "• المستخدم Dev مسبقًا."
        return True, None

    if actor_dev == DEV_PRIMARY:
        return True, None
    if target_id == OWNER_ID:
        return False, "❌ لا يمكن تعديل المطور الأساسي."
    if actor_dev == DEV_SECONDARY and target_dev == DEV_SECONDARY:
        return False, "❌ لا يمكنك تعديل مطور من نفس رتبتك."
    if target_dev == DEV_SECONDARY:
        return False, "❌ لا يمكنك تعديل مطور Dev."
    actor_level = await get_rank_level(actor_id, chat_id)
    new_level = RANK_LEVELS.get(rank, 0)
    if new_level >= actor_level:
        return False, rank_permission_message(rank)
    return True, None


async def roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor:
        return
    text = (message.text or "").strip()
    chat_id = chat.id if chat else None

    if text == "رتبتي":
        rank = await get_rank(actor.id, chat_id)
        await message.reply_text(
            f"• رتبتك هي ↤︎ <tg-spoiler>{escape(rank)}</tg-spoiler>",
            parse_mode="HTML",
        )
        return

    if text == "رتبته" or text.startswith("رتبته "):
        target = await get_target_user(update, context)
        if not target:
            return
        rank = await get_rank(target.id, chat_id)
        await message.reply_text(f"• رتبته هي ↤︎ {escape(rank)}", parse_mode="HTML")
        return

    if text == "كشف المجموعة" and chat_id is not None:
        allowed, required = await check_command_permission(actor.id, text, chat_id)
        if not allowed:
            await message.reply_text(f"❌ هذا الأمر لـ {required} وفوق فقط")
            return
        rows = await get_group_rank_users(chat_id)
        buckets = {rank: [] for rank in NORMAL_RANKS}
        for user_id, rank in rows:
            if rank in buckets:
                buckets[rank].append(await get_user_mention(context, user_id))
        sections = [
            ("• قائمة المالك", "المالك"),
            ("• قائمة نواب المالك", "نائب المالك"),
            ("• قائمة الادمنية الاساسيين", "ادمن اساسي"),
            ("• قائمة الادمنية", "ادمن"),
            ("• قائمة المميزين", "مميز"),
        ]
        output = "كشف المجموعة: 📋\n\n"
        for title, rank in sections:
            output += f"{title}\n━━━━━━━━━━━━\n"
            output += "".join(f"{i} - {name}\n" for i, name in enumerate(buckets[rank], 1)) or "لا يوجد\n"
            output += "\n"
        await message.reply_text(output.rstrip(), parse_mode="HTML")
        return


async def change_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor:
        return
    chat_id = chat.id if chat else None
    text = (message.text or "").strip()

    if text == "تنزيل الكل":
        if chat_id is None:
            return
        target = await get_target_user(update, context)
        if not target:
            return
        if target.id == OWNER_ID:
            await message.reply_text("❌ لا يمكن تعديل المطور الأساسي.")
            return
        actor_dev = await get_developer_type(actor.id)
        actor_level = await get_rank_level(actor.id, chat_id)
        target_level = await get_rank_level(target.id, chat_id)
        if actor_dev not in (DEV_PRIMARY, DEV_SECONDARY) and target_level != actor_level:
            await message.reply_text("• عيب عيب احترم الي اعلى منك . ")
            return
        if actor_dev == DEV_SECONDARY and target.id == actor.id:
            await message.reply_text("❌ لا يمكنك إزالة Dev من نفسك.")
            return
        deleted = await clear_lower_group_ranks(chat_id, target.id, 6 if actor_dev else actor_level)
        await message.reply_text(
            "• تم تنزيل جميع الرتب الأقل منه بنجاح .\n"
            f"• المستخدم ↤︎ {await get_user_mention(context, target.id)}\n"
            f"• عدد الرتب التي تم تنزيلها ↤︎「 {deleted} 」",
            parse_mode="HTML",
        )
        return

    selected = next(((cmd, rank, promote) for cmd, (rank, promote) in ROLE_COMMANDS.items()
                     if text == cmd or text.startswith(cmd + " ")), None)
    if not selected:
        return
    command, rank, promoting = selected
    target = await get_target_user(update, context)
    if not target:
        return

    if rank == "Dev":
        if target.id == actor.id and promoting:
            await message.reply_text("❌ لا يمكنك رفع نفسك إلى Dev.")
            return
        if target.id == actor.id and not promoting:
            await message.reply_text("❌ لا يمكنك إزالة Dev من نفسك.")
            return
        allowed, reason = await _can_change(actor.id, target.id, "Dev", chat_id)
        if not allowed:
            await message.reply_text(reason)
            return
        if promoting:
            if await is_developer(target.id):
                await message.reply_text(
                    "• تم رفعه Dev مسبقًا .\n"
                    f"• المستخدم ↤︎ {await get_user_mention(context, target.id)}",
                    parse_mode="HTML",
                )
                return
            await update_developer_rank(target.id, "Dev", actor.id)
            success = "• تم رفعه Dev بنجاح .\n"
        else:
            if await get_developer_type(target.id) != DEV_SECONDARY:
                await message.reply_text("❌ هذا الشخص ليس Dev.")
                return
            await update_developer_rank(target.id, "عضو", actor.id)
            success = "• تم تنزيله من Dev بنجاح .\n"
        await message.reply_text(success + f"• المستخدم ↤︎ {await get_user_mention(context, target.id)}", parse_mode="HTML")
        return

    if chat_id is None:
        return
    if target.id == OWNER_ID:
        await message.reply_text("❌ لا يمكن تعديل رتبة الـDev الأساسي.")
        return
    allowed, reason = await _can_change(actor.id, target.id, rank, chat_id)
    if not allowed:
        await message.reply_text(reason)
        return
    already = await has_group_rank(chat_id, target.id, rank)
    if promoting and already:
        await message.reply_text(f"• تم رفعه {rank} مسبقًا .\n• المستخدم ↤︎ {await get_user_mention(context, target.id)}", parse_mode="HTML")
        return
    if not promoting and not already:
        await message.reply_text(f"• تم تنزيله من {rank} مسبقًا .\n• المستخدم ↤︎ {await get_user_mention(context, target.id)}", parse_mode="HTML")
        return
    if promoting:
        await add_group_rank(chat_id, target.id, rank)
        response = f"• تم رفعه {rank} بنجاح .\n"
    else:
        await remove_group_rank(chat_id, target.id, rank)
        response = f"• تم تنزيله من {rank} بنجاح .\n"
    await message.reply_text(response + f"• المستخدم ↤︎ {await get_user_mention(context, target.id)}", parse_mode="HTML")


async def rank_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor or not chat or chat.type not in ("group", "supergroup"):
        return
    rank = ROLE_LIST_NAMES.get((message.text or "").strip())
    if not rank:
        return
    level = await get_rank_level(actor.id, chat.id)
    if actor.id != OWNER_ID and not await is_developer(actor.id) and level <= RANK_LEVELS[rank]:
        denied = {
            "ادمن": "• هذا الامر للأدمن الاساسي وفوق .",
            "ادمن اساسي": "• هذا الأمر لـ المالك وفوق .",
            "المالك": "• هذا الامر لـ نواف والـ Dev فقط .",
        }.get(rank, "• هذا الأمر لرتبة اعلى منك .")
        await message.reply_text(denied)
        return
    users = await get_users_by_group_rank(chat.id, rank)
    body = f"• قائمة {ROLE_TITLES[rank]}\n━━━━━━━━━━━━\n"
    if users:
        for index, user_id in enumerate(users, 1):
            body += f"{index} - {await get_user_mention(context, user_id)}\n\n"
    else:
        body += "لا يوجد\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("مسح القائمة", callback_data=f"roles_clear:{rank}")]])
    await message.reply_text(body, reply_markup=keyboard, parse_mode="HTML")


async def dev_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    if not message or not actor:
        return
    if not await is_primary_developer(actor.id):
        owner_mention = await get_user_mention(context, OWNER_ID)
        await message.reply_text(f"• هذا الأمر للمطور الاساسي ({owner_mention}) فقط !", parse_mode="HTML")
        return
    primary = await get_user_mention(context, OWNER_ID)
    developers = await get_secondary_developers()
    body = (
        "اهلًا بك عزيزي المطور في قائمة Dev الخاص بك🎖️\n\n"
        "المطور الاساسي👇🏻\n\n" + primary +
        "\n\n\nالمساعدين 🎖️\n\n—————————————————\n\n"
    )
    if developers:
        for index, user_id in enumerate(developers, 1):
            body += f"{index} - {await get_user_mention(context, user_id)}\n\n"
    else:
        body += "مافيه احد رتبته Dev حاليًا.\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("مسح القائمة", callback_data="roles_clear:Dev")]])
    await message.reply_text(body, reply_markup=keyboard, parse_mode="HTML")


async def clear_dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    if not message or not actor:
        return
    if not await is_primary_developer(actor.id):
        owner_mention = await get_user_mention(context, OWNER_ID)
        await message.reply_text(f"• هذا الأمر للمطور الاساسي ({owner_mention}) فقط !", parse_mode="HTML")
        return
    deleted = await clear_secondary_developers()
    await message.reply_text("• تم مسح جميع مطورين Dev المساعدين بنجاح .\n" f"「 {deleted} 」Dev/مساعدين المطور")


async def clear_rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor or not chat or chat.type not in ("group", "supergroup"):
        return
    rank = {
        "مسح المميزين": "مميز", "مسح الادمنية": "ادمن",
        "مسح الادمنية الاساسيين": "ادمن اساسي", "مسح نواب المالك": "نائب المالك",
        "مسح المالكين": "المالك",
    }.get((message.text or "").strip())
    if not rank:
        return
    level = await get_rank_level(actor.id, chat.id)
    allowed = actor.id == OWNER_ID or await is_primary_developer(actor.id) or (
        level >= RANK_LEVELS[rank] if rank == "المالك" else level > RANK_LEVELS[rank]
    )
    if not allowed:
        denied = {
            "مميز": "• هذا الامر للأدمن وفوق .",
            "ادمن": "• هذا الامر للأدمن الاساسي وفوق .",
            "ادمن اساسي": "• هذا الأمر لـ المالك وفوق .",
            "نائب المالك": "• هذا الأمر لـ المالك وفوق .",
            "المالك": "• هذا الامر لـ نواف والـ Dev فقط .",
        }.get(rank, "• هذا الأمر لرتبة اعلى منك .")
        await message.reply_text(denied)
        return
    deleted = await clear_rank_list(chat.id, rank)
    await message.reply_text(f"• تم مسح القائمة بنجاح .\n「 {deleted} 」{ROLE_TITLES[rank]}")


async def clear_all_ranks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    actor = update.effective_user
    chat = update.effective_chat
    if not message or not actor or not chat or chat.type not in ("group", "supergroup"):
        return
    if not await is_primary_developer(actor.id):
        owner_mention = await get_user_mention(context, OWNER_ID)
        await message.reply_text(f"• هذا الأمر للمطور الاساسي ({owner_mention}) فقط !", parse_mode="HTML")
        return
    counts = await clear_group_ranks(chat.id)
    dev_count = await clear_secondary_developers()
    await message.reply_text(
        "• تم مسح الكل بنجاح .\n"
        f"「 {dev_count} 」Dev/مساعدين المطور\n"
        f"• المالكين ↤︎「 {counts['المالك']} 」\n"
        f"• نوّاب المالك ↤︎「 {counts['نائب المالك']} 」\n"
        f"• الادمنية الاساسيين ↤︎「 {counts['ادمن اساسي']} 」\n"
        f"• الادمنية ↤︎「 {counts['ادمن']} 」\n"
        f"• المميزين ↤︎「 {counts['مميز']} 」"
    )


async def roles_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    actor = query.from_user
    target_rank = (query.data or "").partition(":")[2]
    if target_rank == "Dev":
        if not await is_primary_developer(actor.id):
            await query.answer("• رح اطلب من نواف يحولك ملكية البوت احسن .", show_alert=True)
            return
        deleted = await clear_secondary_developers()
        await query.answer("☑️ تم مسح القائمة.")
        await query.edit_message_text("• تم مسح القائمة بنجاح .\n" f"「 {deleted} 」Dev/مساعدين المطور")
        return
    if target_rank not in NORMAL_RANKS or not query.message:
        return
    chat_id = query.message.chat.id
    level = await get_rank_level(actor.id, chat_id)
    allowed = actor.id == OWNER_ID or await is_primary_developer(actor.id) or (
        level >= RANK_LEVELS[target_rank] if target_rank == "المالك" else level > RANK_LEVELS[target_rank]
    )
    if not allowed:
        await query.answer("• هذا الأمر لرتبة اعلى منك .", show_alert=True)
        return
    deleted = await clear_rank_list(chat_id, target_rank)
    await query.answer("☑️ تم مسح القائمة.")
    await query.edit_message_text(f"• تم مسح القائمة بنجاح .\n「 {deleted} 」{ROLE_TITLES[target_rank]}")
