import asyncio
import html
import re
import time
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.pool import get_pool
from database.roles import is_developer

EXEMPT_USER_IDS = {8453977662}
GROUP_CONFIG_CACHE_TTL = 30
MEMBERSHIP_CACHE_TTL = 15
NEGATIVE_MEMBERSHIP_CACHE_TTL = 3

MANAGEMENT_PATTERN = re.compile(
    r"^(?:ضع اجباري\s+.+|حذف اجباري\s+.+|مسح الاجباري|عرض الاجباري|الاجباري|تفعيل الاجباري|تعطيل الاجباري)$"
)

START_ALIASES = {"بدء البوت", "ابدأ البوت", "تشغيل البوت بالخاص"}
_group_config_cache = {}
_group_config_locks = {}
_membership_cache = {}


def _invalidate_group_config(group_id):
    _group_config_cache.pop(int(group_id), None)


def _invalidate_membership_cache(target_chat_id, user_id=None):
    target_chat_id = int(target_chat_id)
    if user_id is not None:
        _membership_cache.pop((target_chat_id, int(user_id)), None)
        return
    for key in list(_membership_cache):
        if key[0] == target_chat_id:
            _membership_cache.pop(key, None)


async def _get_group_config_cached(group_id):
    now = time.monotonic()
    cached = _group_config_cache.get(int(group_id))
    if cached and now - cached[0] < GROUP_CONFIG_CACHE_TTL:
        return cached[1], cached[2]

    lock = _group_config_locks.setdefault(int(group_id), asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _group_config_cache.get(int(group_id))
        if cached and now - cached[0] < GROUP_CONFIG_CACHE_TTL:
            return cached[1], cached[2]

        pool = get_pool()
        async with pool.acquire() as conn:
            setting = await conn.fetchrow(
                "SELECT enabled FROM mandatory_subscription_settings WHERE chat_id=$1",
                int(group_id),
            )
            rows = await conn.fetch("""
                SELECT id,requirement_type,target_chat_id,target,title,join_url
                FROM mandatory_subscription_requirements
                WHERE group_id=$1 ORDER BY id
            """, int(group_id))
        requirements = [tuple(row) for row in rows]
        enabled = bool(setting["enabled"]) if setting else False
        _group_config_cache[int(group_id)] = (time.monotonic(), enabled, requirements)
        return enabled, requirements


def _cache_enabled_state(group_id, enabled):
    cached = _group_config_cache.get(int(group_id))
    if cached is not None:
        _group_config_cache[int(group_id)] = (
            time.monotonic(), bool(enabled), cached[2]
        )


async def _is_manager(user_id):
    return await is_developer(int(user_id))


async def _save_requirement(group_id, req_type, target_chat_id, target, title, join_url):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            if req_type == "start":
                await conn.execute("""
                    DELETE FROM mandatory_subscription_requirements
                    WHERE group_id=$1 AND requirement_type='start'
                """, int(group_id))
            await conn.execute("""
                INSERT INTO mandatory_subscription_requirements
                    (group_id,requirement_type,target_chat_id,target,title,join_url)
                VALUES($1,$2,$3,$4,$5,$6)
                ON CONFLICT(group_id,requirement_type,target)
                DO UPDATE SET target_chat_id=EXCLUDED.target_chat_id,
                    title=EXCLUDED.title,join_url=EXCLUDED.join_url
            """, int(group_id), req_type, target_chat_id, target, title, join_url)


async def _remove_requirement(group_id, req_type, target=None):
    pool = get_pool()
    if req_type == "start":
        result = await pool.execute("""
            DELETE FROM mandatory_subscription_requirements
            WHERE group_id=$1 AND requirement_type='start'
        """, int(group_id))
    else:
        result = await pool.execute("""
            DELETE FROM mandatory_subscription_requirements
            WHERE group_id=$1 AND requirement_type='chat' AND target=$2
        """, int(group_id), target)
    return int(result.rsplit(" ", 1)[-1])


async def _set_enabled(group_id, enabled, user_id):
    pool = get_pool()
    await pool.execute("""
        INSERT INTO mandatory_subscription_settings(chat_id,enabled,updated_by,updated_at)
        VALUES($1,$2,$3,NOW())
        ON CONFLICT(chat_id) DO UPDATE SET enabled=EXCLUDED.enabled,
            updated_by=EXCLUDED.updated_by,updated_at=NOW()
    """, int(group_id), bool(enabled), int(user_id))


async def _private_start_exists(user_id):
    pool = get_pool()
    return bool(await pool.fetchval(
        "SELECT EXISTS(SELECT 1 FROM developer_private_starts WHERE user_id=$1)",
        int(user_id),
    ))


def _parse_public_telegram_target(value):
    value = value.strip()
    if value.startswith("@"):
        username = value[1:]
        return username if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) else None
    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        if parsed.netloc.lower() not in {
            "t.me", "www.t.me", "telegram.me", "www.telegram.me"
        }:
            return None
        path = parsed.path.strip("/")
        if not path or path.startswith("+") or path.startswith("joinchat/"):
            return None
        username = path.split("/")[0]
        if username.lower() in {"share", "proxy", "addstickers", "iv"}:
            return None
        return username if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username) else None
    return None


def _is_member_status(member):
    status = getattr(member, "status", None)
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


async def _check_chat_membership(context, user_id, target_chat_id):
    key = (int(target_chat_id), int(user_id))
    now = time.monotonic()
    cached = _membership_cache.get(key)
    if cached is not None:
        checked_at, is_member = cached
        ttl = MEMBERSHIP_CACHE_TTL if is_member else NEGATIVE_MEMBERSHIP_CACHE_TTL
        if now - checked_at < ttl:
            return is_member
        _membership_cache.pop(key, None)
    try:
        member = await context.bot.get_chat_member(
            chat_id=int(target_chat_id), user_id=int(user_id)
        )
        is_member = _is_member_status(member)
        _membership_cache[key] = (time.monotonic(), is_member)
        return is_member
    except TelegramError as exc:
        _membership_cache[key] = (time.monotonic(), False)
        print(f"⚠️ تعذر التحقق من الاشتراك الإجباري في {target_chat_id}: {exc}")
        return False


async def _check_requirement(context, user_id, req):
    _rid, req_type, target_chat_id, _target, _title, _join_url = req
    if req_type == "start":
        return await _private_start_exists(user_id)
    if req_type != "chat" or target_chat_id is None:
        return False
    return await _check_chat_membership(context, user_id, target_chat_id)


def _escape(value):
    return html.escape(str(value or ""), quote=True)


async def mandatory_subscription_guard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    if not user or user.is_bot or user.id in EXEMPT_USER_IDS:
        return
    if (
        message.new_chat_members or message.left_chat_member
        or message.group_chat_created or message.supergroup_chat_created
        or message.channel_chat_created
    ):
        return

    text = message.text or message.caption or ""
    if text and MANAGEMENT_PATTERN.fullmatch(text.strip()):
        return

    try:
        enabled, requirements = await _get_group_config_cached(chat.id)
    except Exception as exc:
        print(f"[MANDATORY] DATABASE ERROR | chat_id={chat.id} | {type(exc).__name__}: {exc}")
        return
    if not enabled or not requirements:
        return

    missing = []
    for req in requirements:
        if not await _check_requirement(context, user.id, req):
            missing.append(req)
    if not missing:
        return

    try:
        await message.delete()
    except TelegramError as exc:
        print(f"⚠️ تعذر حذف رسالة غير المستوفي للشروط: {exc}")

    name = user.first_name or user.username or "مستخدم"
    lines = [
        f"• يالامير ~ <a href=\"tg://user?id={user.id}\">{_escape(name)}</a>",
        "مايمديك ترسل أي رسالة هنا لازم تستوفي الشروط تحت ⚠️",
        "تأكد أنك مستوفي الشروط التالية:",
    ]
    buttons = []
    bot_username = context.bot_data.get("mandatory_bot_username")
    if any(req[1] == "start" for req in missing) and not bot_username:
        try:
            me = await context.bot.get_me()
            bot_username = me.username
            context.bot_data["mandatory_bot_username"] = bot_username
        except TelegramError:
            bot_username = None

    for req in missing:
        _rid, req_type, _target_chat_id, _target, title, join_url = req
        lines.append(f"• {_escape(title)}")
        if req_type == "start":
            url = f"https://t.me/{bot_username}?start=mandatory" if bot_username else None
            label = "افتح البوت واضغط ابدأ"
        else:
            url = join_url
            label = f"اشترك في {title}"
        if url:
            buttons.append([InlineKeyboardButton(label[:64], url=url)])

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        print(f"⚠️ تعذر إرسال تنبيه الاشتراك الإجباري: {exc}")
    raise ApplicationHandlerStop


async def mandatory_subscription_commands(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not message or not chat or not user:
        return
    text = (message.text or "").strip()
    if not MANAGEMENT_PATTERN.fullmatch(text):
        return
    if not await _is_manager(user.id):
        await message.reply_text("• هذا الأمر للمالك والمطورين فقط.")
        raise ApplicationHandlerStop

    if text == "تفعيل الاجباري":
        _enabled, requirements = await _get_group_config_cached(chat.id)
        if not requirements:
            await message.reply_text(
                "• ما أضفت أي شرط حتى الآن.\n"
                "أضف قناة/قروب بكتابة: ضع اجباري @username\n"
                "أو أضف شرط بدء البوت: ضع اجباري بدء البوت"
            )
            raise ApplicationHandlerStop
        await _set_enabled(chat.id, True, user.id)
        _cache_enabled_state(chat.id, True)
        await message.reply_text("• تم تفعيل الاشتراك الإجباري في هذه المجموعة.")
        raise ApplicationHandlerStop

    if text == "تعطيل الاجباري":
        await _set_enabled(chat.id, False, user.id)
        _cache_enabled_state(chat.id, False)
        await message.reply_text("• تم تعطيل الاشتراك الإجباري في هذه المجموعة.")
        raise ApplicationHandlerStop

    if text in ("عرض الاجباري", "الاجباري"):
        enabled, requirements = await _get_group_config_cached(chat.id)
        status = "مفعّل" if enabled else "معطّل"
        lines = [f"• حالة الاشتراك الإجباري: {status}", "", "الشروط المسجلة:"]
        if not requirements:
            lines.append("• ما فيه شروط مضافة.")
        for i, req in enumerate(requirements, 1):
            _rid, req_type, _target_chat_id, target, title, _join_url = req
            if req_type == "start":
                lines.append(f"{i}. {title} (بدء البوت بالخاص)")
            else:
                lines.append(f"{i}. {title} — {target}")
        lines.append("\nلإضافة شرط: ضع اجباري @username أو ضع اجباري بدء البوت")
        lines.append("لحذف شرط: حذف اجباري @username أو حذف اجباري بدء البوت")
        await message.reply_text("\n".join(lines))
        raise ApplicationHandlerStop

    if text == "مسح الاجباري":
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM mandatory_subscription_requirements WHERE group_id=$1",
                    chat.id,
                )
                await conn.execute("""
                    UPDATE mandatory_subscription_settings
                    SET enabled=FALSE,updated_by=$1,updated_at=NOW()
                    WHERE chat_id=$2
                """, user.id, chat.id)
        _invalidate_group_config(chat.id)
        await message.reply_text("• تم حذف جميع شروط الاشتراك الإجباري وتعطيله في هذه المجموعة.")
        raise ApplicationHandlerStop

    if text.startswith("حذف اجباري "):
        value = text[len("حذف اجباري "):].strip()
        if value in START_ALIASES:
            count = await _remove_requirement(chat.id, "start")
        else:
            username = _parse_public_telegram_target(value)
            target = "@" + username if username else value
            count = await _remove_requirement(chat.id, "chat", target)
        _invalidate_group_config(chat.id)
        await message.reply_text(
            "• تم حذف الشرط." if count else "• ما لقيت هذا الشرط ضمن الشروط المسجلة."
        )
        raise ApplicationHandlerStop

    if text.startswith("ضع اجباري "):
        value = text[len("ضع اجباري "):].strip()
        if value in START_ALIASES:
            await _save_requirement(
                chat.id, "start", None, "start",
                "بدء البوت في الخاص", "https://t.me/",
            )
            _invalidate_group_config(chat.id)
            await message.reply_text(
                "• تمت إضافة شرط بدء البوت.\n"
                "أي شخص ما سبق أرسل /start للبوت لازم يفتحه ويضغط ابدأ."
            )
            raise ApplicationHandlerStop

        parts = value.split(maxsplit=1)
        target_value = parts[0]
        custom_url = parts[1].strip() if len(parts) == 2 else None
        username = _parse_public_telegram_target(target_value)
        chat_identifier = "@" + username if username else target_value

        if not username and not re.fullmatch(r"-?\d{5,20}", chat_identifier):
            await message.reply_text(
                "• ما قدرت أتحقق من هذا الهدف.\n"
                "استخدم @username لقناة/قروب عام، أو ارسل آيدي القناة/القروب ثم رابط الدعوة الخاص.\n"
                "روابط الدعوة الخاصة وحدها لا تسمح للبوت بمعرفة القروب للتحقق من العضوية."
            )
            raise ApplicationHandlerStop

        try:
            target_chat = await context.bot.get_chat(chat_identifier)
        except TelegramError as exc:
            await message.reply_text(
                "• ما قدرت أوصل للقناة/القروب. تأكد أن اليوزر أو الآيدي صحيح، "
                "وأن البوت مضاف للمكان ومشرف فيه.\nالتفاصيل: " + _escape(str(exc)),
                parse_mode=ParseMode.HTML,
            )
            raise ApplicationHandlerStop

        if target_chat.type not in (ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP):
            await message.reply_text("• الهدف لازم يكون قناة أو قروب تيليجرام، مو حساب شخصي.")
            raise ApplicationHandlerStop

        if custom_url:
            parsed = urlparse(custom_url)
            if parsed.scheme not in ("https", "http") or not parsed.netloc:
                await message.reply_text("• رابط الدعوة غير صحيح.")
                raise ApplicationHandlerStop
            join_url = custom_url
        elif target_chat.username:
            join_url = f"https://t.me/{target_chat.username}"
        else:
            await message.reply_text(
                "• هذه قناة/مجموعة خاصة. استخدم الصيغة التالية مع رابط الدعوة:\n"
                "ضع اجباري -1001234567890 https://t.me/+رابط_الدعوة"
            )
            raise ApplicationHandlerStop

        title = target_chat.title or (
            "@" + target_chat.username if target_chat.username else str(target_chat.id)
        )
        stored_target = "@" + target_chat.username if target_chat.username else str(target_chat.id)
        await _save_requirement(
            chat.id, "chat", target_chat.id, stored_target, title, join_url
        )
        _invalidate_group_config(chat.id)
        _invalidate_membership_cache(target_chat.id)
        await message.reply_text(
            f"• تمت إضافة شرط الاشتراك في <b>{_escape(title)}</b>.\n"
            "تأكد أن البوت مشرف في القناة/القروب حتى يقدر يتحقق من العضوية.",
            parse_mode=ParseMode.HTML,
        )
        raise ApplicationHandlerStop
