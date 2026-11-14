import asyncio

import os

import re

import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.constants import ParseMode

from telegram.ext import ApplicationHandlerStop

from handlers.youtube_audio import (

    _download_audio,

    _format_duration,

    _search_youtube,

)

from database.roles import RANK_LEVELS, OWNER_ID, get_rank_level

from music_call import (

    play_track,

    stop_track,

    is_music_account_member,

    ensure_music_account_in_group,

    get_call_participants,

    get_music_account_id,

)

from datetime import datetime, timedelta, timezone

from html import escape

SEARCH_RESULT_COUNT = 4

def _format_call_duration(seconds):

    seconds = max(0, int(seconds or 0))

    hours, remainder = divmod(seconds, 3600)

    minutes, seconds = divmod(remainder, 60)

    parts = []

    if hours:

        parts.append(f"{hours} ساعة")

    if minutes:

        parts.append(f"{minutes} دقيقة")

    if seconds or not parts:

        parts.append(f"{seconds} ثانية")

    return " و".join(parts)

async def _is_music_admin(chat_id, user_id):
    try:
        return await get_rank_level(user_id, chat_id) >= RANK_LEVELS["ادمن"]
    except Exception as exc:
        print(f"[MUSIC] Rank check failed: {exc}")
        return False


async def _is_link_admin(chat_id, user_id):
    try:
        return await get_rank_level(user_id, chat_id) >= RANK_LEVELS["ادمن اساسي"]
    except Exception as exc:
        print(f"[MUSIC] Link rank check failed: {exc}")
        return False


def _call_mention(user):

    name = escape(user.full_name or user.first_name or "مستخدم")

    return f'<a href="tg://user?id={user.id}">{name}</a>'

async def _show_call_participants(message, context):

    chat_id = message.chat_id

    try:

        participants = await get_call_participants(chat_id)

        music_id = await get_music_account_id()

        if not participants:

            await message.reply_text("ما فيه مكالمة صوتية نشطة حاليًا.")

            return

        # استبعاد حساب تشغيل الموسيقى فقط

        user_ids = list(dict.fromkeys(

            p.user_id

            for p in participants

            if p.user_id != music_id

        ))

        if not user_ids:

            await message.reply_text("ما فيه أعضاء بالمكالمة حاليًا.")

            return

        developer = None

        admins = []

        members = []

        for user_id in user_ids:

            try:

                member = await context.bot.get_chat_member(

                    chat_id,

                    user_id,

                )

                user = member.user

                if user_id == OWNER_ID:

                    developer = user

                elif member.status in ("administrator", "creator"):

                    admins.append(user)

                else:

                    members.append(user)

            except Exception as exc:

                print(

                    f"[MUSIC] Could not get call member {user_id}: {exc}"

                )

        lines = ["الحلوين الي بالمكالمة:", ""]

        if developer:

            lines.append(

                f"~ القوت معكم بالكول「 {_call_mention(developer)} 」❤️‍🔥"

            )

            lines.append("")

        lines.append("المشرفين:")

        if admins:

            for index, user in enumerate(admins, 1):

                lines.append(

                    f"{index} ~「 {_call_mention(user)} 」"

                )

        else:

            lines.append("~ مافيه مشرف بالكول حاليًا")

        lines.extend([

            "—————————————————",

            "الاعضاء:",

        ])

        for index, user in enumerate(members, 1):

            lines.append(

                f"{index} ~「 {_call_mention(user)} 」"

            )

        if not members:

            lines.append("~ ما فيه أعضاء آخرين بالكول")

        keyboard = InlineKeyboardMarkup([

            [

                InlineKeyboardButton(

                    "🌷",

                    url=f"https://t.me/{(await context.bot.get_me()).username}",

                )

            ]

        ])

        await message.reply_text(

            "\n".join(lines),

            parse_mode=ParseMode.HTML,

            reply_markup=keyboard,

        )

    except Exception as exc:

        print(f"[MUSIC] Get call participants failed: {exc}")

        await message.reply_text(

            "تعذّر جلب قائمة الموجودين بالمكالمة."

        )

async def _show_search(message, context, query, requester):

    status = await message.reply_text("🔎 جاري البحث عن الأغاني...")

    try:

        results = await _search_youtube(query)

        if not results:

            await status.edit_text("ما حصلت نتائج للبحث.")

            return

        search_id = os.urandom(5).hex()

        searches = context.chat_data.setdefault("music_searches", {})

        searches[search_id] = {

            "results": results[:SEARCH_RESULT_COUNT],

            "requester_id": requester.id,

        }

        keyboard = []

        for index, result in enumerate(results[:SEARCH_RESULT_COUNT]):

            title = str(result.get("title") or "مقطع بدون عنوان")

            if len(title) > 55:

                title = title[:52] + "..."

            duration = _format_duration(result.get("duration"))

            label = f"{index + 1}. {title}"

            if duration:

                label += f" [{duration}]"

            keyboard.append([

                InlineKeyboardButton(

                    label,

                    callback_data=f"musicpick:{search_id}:{index}",

                )

            ])

        await status.edit_text(

            f"🎵 نتائج البحث عن: {query}\n\nاختر المقطع:",

            reply_markup=InlineKeyboardMarkup(keyboard),

        )

    except Exception as exc:

        print(f"[MUSIC] YouTube search failed: {exc}")

        await status.edit_text(

            "تعذّر البحث الآن. تأكد من إعداد YOUTUBE_API_KEY "

            "وراجع سجلات Render."

        )

async def _ensure_music_joined(chat_id, context, chat_username=None):

    if await is_music_account_member(chat_id):

        return

    invite_link = None

    try:

        if not chat_username:

            invite = await context.bot.create_chat_invite_link(

                chat_id=chat_id,

                member_limit=1,

                expire_date=datetime.now(timezone.utc) + timedelta(minutes=5),

            )

            invite_link = invite.invite_link

        await ensure_music_account_in_group(

            chat_id=chat_id,

            invite_link=invite_link,

            public_username=chat_username,

        )

    finally:

        if invite_link:

            try:

                await context.bot.revoke_chat_invite_link(

                    chat_id=chat_id,

                    invite_link=invite_link,

                )

            except Exception as exc:

                print(f"[MUSIC] Invite revoke failed: {exc}")

async def _play_selected(

    chat_id,

    context,

    source_message,

    video,

    requester,

    status_message=None,

):

    status = status_message

    if status is None:

        status = await source_message.reply_text("⏳ جاري تجهيز المقطع...")

    try:

        with tempfile.TemporaryDirectory(prefix="music_call_") as folder:

            file_path, info = await _download_audio(

                video["url"],

                folder,

            )

            title = info.get("title") or video.get("title") or "مقطع صوتي"

            duration_seconds = (

                info.get("duration")

                or video.get("duration")

                or 0

            )

            duration_text = _format_duration(duration_seconds) or "غير معروف"

            await _ensure_music_joined(

                chat_id=chat_id,

                context=context,

                chat_username=source_message.chat.username,

            )

            

            await play_track(

                chat_id=chat_id,

                source_path=file_path,

                title=title,

                duration=duration_text,

                requester=requester.full_name,

            )

        context.chat_data["music_last_track"] = {

            "id": video.get("id"),

            "url": video["url"],

            "title": title,

            "duration": duration_seconds,

        }

        text = (

            "<blockquote>"

            + "\u200e"

            + "\u00a0" * 15

            + "♡ تم بدء التشغيل"

            + "</blockquote>\n\n\n"

            f"- العنوان : {escape(str(title))}\n"

            f"- مدة التشغيل : {escape(str(duration_text))}\n"

            f"- الشخص الي شغله : {escape(requester.full_name)}"

        )

        keyboard = InlineKeyboardMarkup([

            [

                InlineKeyboardButton(

                    "🌷",

                    url=f"https://t.me/{(await context.bot.get_me()).username}",

                )

            ]

        ])

        sent = await context.bot.send_message(

            chat_id=chat_id,

            text=text,

            parse_mode=ParseMode.HTML,

            reply_markup=keyboard,

        )

        

        context.chat_data["music_last_message_id"] = sent.message_id

    except Exception as exc:

        print(f"[MUSIC] Could not play selected track: {exc}")

        try:

            await status.edit_text(

                "تعذّر تشغيل هذا المقطع داخل المكالمة. "

                "تأكد من وجود مكالمة صوتية وأن حساب الموسيقى عضو في المجموعة، "

                "ثم راجع سجلات Render."

            )

        except Exception:

            pass

async def music_callback(update, context):

    query = update.callback_query

    if not query or not query.data or not query.message:

        return

    match = re.fullmatch(r"musicpick:([a-f0-9]+):(\d+)", query.data)

    if not match:

        await query.answer()

        return

    chat_id = query.message.chat_id

    user = query.from_user

    if not await _is_music_admin(chat_id, user.id):

        await query.answer("التشغيل للأدمن وفوق فقط.", show_alert=True)

        return

    search_id = match.group(1)

    index = int(match.group(2))

    search_data = context.chat_data.get("music_searches", {}).get(search_id)

    results = search_data.get("results", []) if search_data else []

    if index >= len(results):

        await query.answer("انتهت صلاحية النتائج، ابحث مرة ثانية.", show_alert=True)

        return

    await query.answer()

    video = results[index]

    try:

        await query.message.delete()

    except Exception:

        pass

    status = await context.bot.send_message(

        chat_id=chat_id,

        text="⏳ جاري تجهيز المقطع وتشغيله في المكالمة...",

    )

    # Run audio download and playback outside the serial update processor.

    context.application.create_task(

        _play_selected(

            chat_id=chat_id,

            context=context,

            source_message=query.message,

            video=video,

            requester=user,

            status_message=status,

        ),

        update=update,

    )

    context.chat_data.get("music_searches", {}).pop(search_id, None)

async def _stop_music(message, chat_id, user):

    stopped = await stop_track(chat_id)

    if not stopped:

        await message.reply_text("مافيه شي شغال بالمكالمة .")

        return

    await message.reply_text(f"تم الإيقاف بواسطة ~ {user.full_name}")

async def music_message_handler(update, context):

    message = update.effective_message

    chat = update.effective_chat

    user = update.effective_user

    if not message or not message.text or not chat or not user:

        return

    if chat.type not in ("group", "supergroup"):

        return

    original = message.text.strip()

    text = original

    ai_command = False

    ai_match = re.match(

        r"^نيوف\s+(.+?)\s*$",

        original,

        flags=re.IGNORECASE,

    )

    if ai_match:

        text = ai_match.group(1).strip()

        ai_command = True

    # ==========================================

    # إنشاء رابط المجموعة

    # ==========================================

    if text == "انشاء رابط":

        if not await _is_link_admin(chat.id, user.id):

            await message.reply_text(

                "هذا الأمر لرتبة ادمن اساسي وفوق فقط."

            )

        else:

            try:

                # المجموعات العامة لا تحتاج رابط دعوة جديد

                if chat.username:

                    await message.reply_text(

                        "المجموعة عامة، رابطها موجود بالفعل."

                    )

                else:

                    invite = await context.bot.create_chat_invite_link(

                        chat_id=chat.id

                    )

                    context.chat_data["music_group_invite_link"] = (

                        invite.invite_link

                    )

                    await message.reply_text(

                        "• تم انشاء رابط جديد\n"

                        "• لعرض الرابط ارسل 〖 الرابط 〗"

                    )

            except Exception as exc:

                print(f"[MUSIC] Create invite link failed: {exc}")

                await message.reply_text(

                    "تعذّر إنشاء الرابط. تأكد أن البوت يملك صلاحية دعوة المستخدمين."

                )

        raise ApplicationHandlerStop()

    # ==========================================

    # عرض رابط المجموعة

    # ==========================================

    if text == "الرابط":

        try:

            if chat.username:

                # رابط المجموعة العامة

                group_link = f"https://t.me/{chat.username}"

            else:

                # آخر رابط أنشأه البوت للمجموعة الخاصة

                group_link = context.chat_data.get(

                    "music_group_invite_link"

                )

            if not group_link:

                await message.reply_text(

                    "ما تم إنشاء رابط للمجموعة حتى الآن.\n"

                    "اكتب انشاء رابط لإنشاء رابط جديد."

                )

            else:

                keyboard = InlineKeyboardMarkup([

                    [

                        InlineKeyboardButton(

                            chat.title or "دخول المجموعة",

                            url=group_link,

                        )

                    ]

                ])

                await message.reply_text(

                    "• رابط المجموعة:",

                    reply_markup=keyboard,

                )

        except Exception as exc:

            print(f"[MUSIC] Show group link failed: {exc}")

            await message.reply_text(

                "تعذّر عرض رابط المجموعة."

            )

        raise ApplicationHandlerStop()

    if text in {"من بالكول", "مين في الكول", "مين بالكول", "مين بالمكالمة"}:

        await _show_call_participants(message, context)

        raise ApplicationHandlerStop()

    

    stop_words = {"ايقاف", "إيقاف", "وقف المقطع"}

    if text in stop_words:

        if not await _is_music_admin(chat.id, user.id):

            await message.reply_text("هذا الأمر للأدمن وفوق فقط.")

        else:

            await _stop_music(message, chat.id, user)

        raise ApplicationHandlerStop()

    search_match = re.fullmatch(

        r"تشغيل\s+(.+)",

        text,

        flags=re.IGNORECASE,

    )

    if search_match:

        if not await _is_music_admin(chat.id, user.id):

            await message.reply_text("البحث والتشغيل للأدمن وفوق فقط.")

        else:

            # Keep YouTube network work out of the serial message handler.

            context.application.create_task(

                _show_search(

                    message,

                    context,

                    search_match.group(1).strip(),

                    user,

                ),

                update=update,

            )

        raise ApplicationHandlerStop()

    if text == "تشغيل" and message.reply_to_message:

        last_message_id = context.chat_data.get("music_last_message_id")

        last_track = context.chat_data.get("music_last_track")

        if (

            last_track

            and last_message_id

            and message.reply_to_message.message_id == last_message_id

        ):

            if not await _is_music_admin(chat.id, user.id):

                await message.reply_text("التشغيل للأدمن وفوق فقط.")

            else:

                context.application.create_task(

                    _play_selected(

                        chat_id=chat.id,

                        context=context,

                        source_message=message,

                        video=last_track,

                        requester=user,

                    ),

                    update=update,

                )

            raise ApplicationHandlerStop()

    if ai_command and text in stop_words:

        raise ApplicationHandlerStop()

async def voice_chat_started(update, context):

    message = update.effective_message

    if not message or not message.video_chat_started:

        return

    try:

        await message.reply_text(

            "<b>• تم بدأ المكالمة.</b>",

            parse_mode=ParseMode.HTML,

        )

    except Exception as exc:

        print(f"[MUSIC] Could not reply to voice-chat start: {exc}")

async def voice_chat_ended(update, context):

    message = update.effective_message

    if not message or not message.video_chat_ended:

        return

    duration = getattr(message.video_chat_ended, "duration", None)

    duration_text = _format_call_duration(duration)

    try:

        await message.reply_text(

            "<b>• انتهت المكالمة.\n"

            f"مدتها: {duration_text}.</b>",

            parse_mode=ParseMode.HTML,

        )

    except Exception as exc:

        print(f"[MUSIC] Could not reply to voice-chat end: {exc}")
