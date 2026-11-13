
import re
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pyrogram import filters
from pyrogram.enums import UserStatus, ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait

from music_call import get_music_client
from database.pool import get_pool

# ==========================================
# الإعدادات
# ==========================================

TARGET_WORD = "نواف"
REACTION_EMOJI = "💯"

ONLINE_REPLY = "مشغول👾"
OFFLINE_REPLY = "نايم"

ENABLE_REPLY = "طيب لا تنفخ فعلت لك الردود"
DISABLE_REPLY = "طيب عطلته"

MUTE_REPLY = "زين انك كتمته النشبه ذا 😂"
UNMUTE_REPLY = "طول عمرك ترحم الناس والله قوت يا نواف❤️‍🔥"

RESTRICT_REPLY = "زين انك قيدته 😂"
UNRESTRICT_REPLY = "طول عمرك ترحم الناس والله قوت يا نواف❤️‍🔥"

MUTE_LIST_TITLE = "• السبايك ذول مكتومين😂😂"
RESTRICT_LIST_TITLE = "• السبايك ذول مقيدين😂😂"

RESTRICT_NOTICE = "يالسبك مايمديك ترسل لا تتعب نفسك😂😂"

HANDLER_GROUP = 1100
CONTROL_HANDLER_GROUP = 1099
PRIVATE_HANDLER_GROUP = 1101

SETTINGS_FILE = Path("name_reaction_settings.json")
DEFAULT_ENABLED = True

# المدة بين رسائل تنبيه التقييد للشخص نفسه
RESTRICT_NOTICE_INTERVAL = 60

# عدد الرسائل في كل دفعة حذف
DELETE_BATCH_SIZE = 100

# ==========================================
# الإرسال اليومي
# ==========================================

DAILY_MESSAGE = "@W_H_8"

DAILY_SEND_HOUR = 1
DAILY_SEND_MINUTE = 30

DAILY_TIMEZONE = ZoneInfo("Asia/Riyadh")

DAILY_STATE_FILE = Path("daily_mention_state.json")

# ==========================================
# المتغيرات العامة
# ==========================================

_client = None
_account_user_id = None

_handler = None
_control_handler = None
_private_handler = None

_daily_task = None
_daily_chat_id = None

# آخر وقت أرسلنا فيه تنبيه التقييد
restrict_notice_times = {}

# ==========================================
# حفظ الإعدادات
# ==========================================

replies_enabled = DEFAULT_ENABLED
muted_users = {}
restricted_users = {}

async def load_settings():
    global replies_enabled, muted_users, restricted_users

    default = {
        "replies_enabled": DEFAULT_ENABLED,
        "muted": {},
        "restricted": {}
    }

    pool = get_pool()
    raw = await pool.fetchval(
        "SELECT settings FROM name_reaction_settings WHERE id = 1"
    )

    if raw is None:
        # استيراد ملف الإعدادات القديم مرة واحدة إن كان ما زال موجوداً.
        imported = default
        try:
            if SETTINGS_FILE.exists():
                with SETTINGS_FILE.open("r", encoding="utf-8") as file:
                    old_data = json.load(file)
                if isinstance(old_data, dict):
                    imported = {
                        "replies_enabled": bool(old_data.get("replies_enabled", DEFAULT_ENABLED)),
                        "muted": old_data.get("muted", {}),
                        "restricted": old_data.get("restricted", {})
                    }
        except Exception as exc:
            print(f"[NAME REACTION] Legacy settings import error: {exc}")

        await pool.execute(
            """
            INSERT INTO name_reaction_settings (id, settings)
            VALUES (1, $1::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            json.dumps(imported, ensure_ascii=False)
        )
        raw = await pool.fetchval(
            "SELECT settings FROM name_reaction_settings WHERE id = 1"
        )

    if isinstance(raw, str):
        raw = json.loads(raw)

    if isinstance(raw, dict):
        replies_enabled = bool(raw.get("replies_enabled", DEFAULT_ENABLED))
        muted_users = raw.get("muted", {})
        restricted_users = raw.get("restricted", {})

    if not isinstance(muted_users, dict):
        muted_users = {}
    if not isinstance(restricted_users, dict):
        restricted_users = {}

    print("[NAME REACTION] Settings loaded from PostgreSQL.")

async def save_settings():
    data = {
        "replies_enabled": replies_enabled,
        "muted": muted_users,
        "restricted": restricted_users
    }

    try:
        pool = get_pool()
        await pool.execute(
            """
            INSERT INTO name_reaction_settings (id, settings, updated_at)
            VALUES (1, $1::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE
            SET settings = EXCLUDED.settings,
                updated_at = NOW()
            """,
            json.dumps(data, ensure_ascii=False)
        )
    except Exception as exc:
        print(f"[NAME REACTION] Settings save error: {exc}")
        raise

# ==========================================
# اسم المستخدم
# ==========================================

def get_user_display_name(user):
    if user.username:
        return f"@{user.username}"

    name = user.first_name or "مستخدم"

    if user.last_name:
        name += f" {user.last_name}"

    return name

# ==========================================
# اكتشاف كلمة نواف
# ==========================================

WORD_PATTERN = re.compile(
    rf"(?<!\w){re.escape(TARGET_WORD)}(?!\w)"
)

# ==========================================
# معرفة حالة الحساب
# ==========================================

async def get_account_status():
    try:
        me = await _client.get_me()

        if me.status == UserStatus.ONLINE:
            return ONLINE_REPLY

        if me.status == UserStatus.OFFLINE:
            return OFFLINE_REPLY

        return ONLINE_REPLY

    except Exception as exc:
        print(f"[NAME REACTION] Status error: {exc}")
        return ONLINE_REPLY

# ==========================================
# مسح رسائل الحساب في القروب
# ==========================================

async def delete_own_messages(client, message, count):

    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP
    ):
        return

    if count <= 0:
        return

    chat_id = message.chat.id
    message_ids = []

    try:
        me = await client.get_me()
        my_user_id = me.id
    except Exception as exc:
        print(f"[MESSAGE CLEANER] Cannot identify account: {exc}")
        return

    print(
        f"[MESSAGE CLEANER] Searching for {count} own messages "
        f"in chat {chat_id}; account_id={my_user_id}"
    )

    # البحث عن رسائل الحساب بمطابقة رقم المستخدم مباشرةً
    try:
        async for old_message in client.get_chat_history(chat_id):

            # تجاهل رسالة أمر المسح
            if old_message.id == message.id:
                continue

            sender = getattr(old_message, "from_user", None)
            if sender and sender.id == my_user_id:
                message_ids.append(old_message.id)

                if len(message_ids) >= count:
                    break

    except FloodWait as exc:
        print(
            f"[MESSAGE CLEANER] History FloodWait: {exc.value}s"
        )
        return

    except Exception as exc:
        print(
            f"[MESSAGE CLEANER] History error: {exc}"
        )
        return

    # حذف الرسائل على دفعات

    print(
        f"[MESSAGE CLEANER] Found {len(message_ids)} own messages "
        f"in chat {chat_id}"
    )

    deleted_count = 0
    failed_count = 0

    for start in range(0, len(message_ids), DELETE_BATCH_SIZE):

        batch = message_ids[
            start:start + DELETE_BATCH_SIZE
        ]

        while True:
            try:
                await client.delete_messages(
                    chat_id=chat_id,
                    message_ids=batch,
                    revoke=True
                )

                deleted_count += len(batch)
                break

            except FloodWait as exc:
                print(
                    f"[MESSAGE CLEANER] FloodWait: {exc.value}s"
                )

                await asyncio.sleep(exc.value + 1)

            except Exception as exc:
                print(
                    f"[MESSAGE CLEANER] Batch delete error: {exc}. "
                    "Retrying messages individually."
                )
                # إذا تعذر حذف الدفعة كاملة، جرّب كل رسالة منفردة
                # حتى لا تمنع رسالة واحدة حذف بقية الرسائل.
                for message_id in batch:
                    while True:
                        try:
                            await client.delete_messages(
                                chat_id=chat_id,
                                message_ids=message_id,
                                revoke=True
                            )
                            deleted_count += 1
                            break
                        except FloodWait as wait:
                            await asyncio.sleep(wait.value + 1)
                        except Exception as single_exc:
                            print(
                                f"[MESSAGE CLEANER] Message {message_id} "
                                f"delete error: {single_exc}"
                            )
                            failed_count += 1
                            break
                break

    print(
        f"[MESSAGE CLEANER] Finished in chat {chat_id}: "
        f"deleted={deleted_count}, failed={failed_count}, "
        f"found={len(message_ids)}"
    )

    # حذف رسالة الأمر

    try:
        await client.delete_messages(
            chat_id=chat_id,
            message_ids=message.id,
            revoke=True
        )

    except Exception as exc:
        print(
            f"[MESSAGE CLEANER] Command delete error: {exc}"
        )

    print(
        f"[MESSAGE CLEANER] Finished | "
        f"Requested: {count} | "
        f"Found: {len(message_ids)} | "
        f"Deleted: {deleted_count} | "
        f"Failed: {failed_count}"
    )

# ==========================================
# تنفيذ أوامر الكتم والتقييد
# ==========================================

async def moderate_user(message, action):

    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "هذا الأمر يعمل في الخاص فقط."
        )
        return

    replied = message.reply_to_message

    if not replied or not replied.from_user:
        await message.reply_text(
            "رد على رسالة الشخص أولاً."
        )
        return

    user = replied.from_user

    if user.is_self or user.is_bot:
        await message.reply_text(
            "ما تقدر تطبق الأمر على هذا المستخدم."
        )
        return

    user_id = str(user.id)
    display_name = get_user_display_name(user)

    if action == "mute":

        if user_id in muted_users:
            await message.reply_text(
                "الشخص مكتوم من قبل 😂"
            )
            return

        muted_users[user_id] = display_name
        await save_settings()

        await message.reply_text(MUTE_REPLY)

        print(
            f"[PRIVATE MODERATION] Muted {user_id}"
        )

    elif action == "unmute":

        if user_id not in muted_users:
            await message.reply_text(
                "هذا الشخص مب مكتوم أصلاً."
            )
            return

        del muted_users[user_id]
        await save_settings()

        await message.reply_text(UNMUTE_REPLY)

        print(
            f"[PRIVATE MODERATION] Unmuted {user_id}"
        )

    elif action == "restrict":

        if user_id in restricted_users:
            await message.reply_text(
                "الشخص مقيّد من قبل 😂"
            )
            return

        restricted_users[user_id] = display_name
        await save_settings()

        await message.reply_text(RESTRICT_REPLY)

        print(
            f"[PRIVATE MODERATION] Restricted {user_id}"
        )

    elif action == "unrestrict":

        if user_id not in restricted_users:
            await message.reply_text(
                "هذا الشخص مب مقيّد أصلاً."
            )
            return

        del restricted_users[user_id]

        restrict_notice_times.pop(user_id, None)

        await save_settings()

        await message.reply_text(UNRESTRICT_REPLY)

        print(
            f"[PRIVATE MODERATION] Unrestricted {user_id}"
        )

# ==========================================
# عرض قائمة المستخدمين
# ==========================================

async def show_users_list(message, user_list, title):

    if not user_list:
        await message.reply_text(
            title + "\n\nما فيه أحد حالياً 😂"
        )
        return

    lines = [title, ""]

    for index, (user_id, name) in enumerate(
        user_list.items(),
        start=1
    ):
        lines.append(
            f"{index} ~ {name}"
        )

    await message.reply_text(
        "\n".join(lines)
    )

# ==========================================
# أوامر التحكم
# ==========================================

async def _reply_control_handler(client, message):

    global replies_enabled

    # لا نعتمد على filters.outgoing أو message.outgoing وحدهما؛
    # نطابق هوية مرسل الرسالة مع الحساب المسجل في جلسة Pyrogram.
    sender = getattr(message, "from_user", None)
    sender_id = getattr(sender, "id", None)
    is_our_message = (
        bool(getattr(message, "outgoing", False))
        or bool(getattr(sender, "is_self", False))
        or (
            _account_user_id is not None
            and sender_id == _account_user_id
        )
    )
    if not is_our_message:
        return

    text = (
        message.text or message.caption or ""
    ).strip()

    if not text:
        return

    # كشف الحسابات من جلسة المساعد مباشرة، دون قاعدة البيانات.
    # يقبل: كشف @username / كشف ID / كشف بالرد على رسالة الشخص.
    reveal_match = re.fullmatch(r"كشف\s+(@?[A-Za-z0-9_]+)", text)
    replied_message = message.reply_to_message if text == "كشف" else None

    if reveal_match or replied_message:
        raw_target = reveal_match.group(1).strip() if reveal_match else "الرد"
        try:
            if reveal_match:
                # الحفاظ على البحث القديم باليوزر أو الآيدي.
                target = raw_target.lstrip("@")
                if target.isdigit():
                    if int(target) <= 0:
                        raise ValueError("Invalid Telegram ID")
                    user = await client.get_users(int(target))
                else:
                    user = await client.get_users(target)
            else:
                # عند الرد نأخذ صاحب الرسالة المردود عليها، وليس حساب المساعد نفسه.
                replied_user = replied_message.from_user
                if not replied_user:
                    await message.reply_text("❌ الرسالة اللي رديت عليها ما تخص حساب مستخدم.")
                    return

                me = await client.get_me()
                if replied_user.id == me.id or replied_user.is_self:
                    await message.reply_text("❌ رديت على رسالة حساب المساعد نفسه. رد على رسالة الشخص المطلوب.")
                    return

                try:
                    user = await client.get_users(replied_user.id)
                except Exception:
                    user = replied_user

            name = " ".join(
                part for part in (user.first_name, user.last_name) if part
            ).strip() or "لا يوجد"
            # Telegram may move collectible Fragment usernames into user.usernames
            # and leave user.username empty. Prefer the main username, then the
            # first active username in Telegram's ordered usernames list.
            username_value = getattr(user, "username", None)
            if not username_value:
                extra_usernames = getattr(user, "usernames", None) or []
                active_usernames = []
                for item in extra_usernames:
                    value = item if isinstance(item, str) else getattr(item, "username", None)
                    is_active = True if isinstance(item, str) else getattr(item, "active", True)
                    if value and is_active:
                        active_usernames.append(value)
                username_value = active_usernames[0] if active_usernames else None
            username = f"@{username_value}" if username_value else "لا يوجد"
            try:
                profile = await client.get_chat(user.id)
                bio = (getattr(profile, "bio", None) or "").strip() or "لا يوجد"
            except Exception:
                bio = "لا يوجد"

            await message.reply_text(
                f"• NAME : {name}\n"
                f"• ID : {user.id}\n"
                f"• BIO : {bio}\n"
                f"• USE : {username}"
            )
        except Exception as exc:
            print(f"[ACCOUNT REVEAL] Lookup failed for {raw_target}: {exc}")
            await message.reply_text("❌ ما قدرت أوصل للحساب. تأكد من اليوزر أو الآيدي.")
        return

    # --------------------------
    # مسح الرسائل
    # --------------------------

    match = re.fullmatch(
        r"مسح\s+(\d+)",
        text
    )

    if match:

        count = int(match.group(1))
        print(
            f"[MESSAGE CLEANER] Command received: chat={message.chat.id}, "
            f"message_id={message.id}, sender_id={sender_id}, "
            f"outgoing={getattr(message, 'outgoing', False)}, requested={count}"
        )

        # كل أمر مسح ينظف آخر 100 رسالة من رسائل الحساب نفسه.
        await delete_own_messages(
            client,
            message,
            100
        )

        return

    # --------------------------
    # فتح الردود
    # --------------------------

    if text == "فتح الردود":

        replies_enabled = True
        await save_settings()

        try:
            await message.reply_text(ENABLE_REPLY)

        except FloodWait as exc:
            print(
                f"[NAME REACTION] FloodWait: {exc.value}s"
            )

        except Exception as exc:
            print(
                f"[NAME REACTION] Enable error: {exc}"
            )

        return

    # --------------------------
    # قفل الردود
    # --------------------------

    if text == "قفل الردود":

        replies_enabled = False
        await save_settings()

        try:
            await message.reply_text(DISABLE_REPLY)

        except FloodWait as exc:
            print(
                f"[NAME REACTION] FloodWait: {exc.value}s"
            )

        except Exception as exc:
            print(
                f"[NAME REACTION] Disable error: {exc}"
            )

        return

    # --------------------------
    # الكتم
    # --------------------------

    if text == "كتم":
        await moderate_user(message, "mute")
        return

    if text == "الغاء الكتم":
        await moderate_user(message, "unmute")
        return

    # --------------------------
    # التقييد
    # --------------------------

    if text == "تقييد":
        await moderate_user(message, "restrict")
        return

    if text == "الغاء التقييد":
        await moderate_user(message, "unrestrict")
        return

    # --------------------------
    # قائمة المكتومين
    # --------------------------

    if text == "المكتومين":

        await show_users_list(
            message,
            muted_users,
            MUTE_LIST_TITLE
        )

        return

    # --------------------------
    # قائمة المقيدين
    # --------------------------

    if text == "المقيدين":

        await show_users_list(
            message,
            restricted_users,
            RESTRICT_LIST_TITLE
        )

        return

# ==========================================
# مراقبة رسائل الخاص
# ==========================================

async def _private_moderation_handler(client, message):

    if not message.from_user:
        return

    if message.from_user.is_self:
        return

    user_id = str(message.from_user.id)

    # تحديث الاسم المحفوظ

    display_name = get_user_display_name(
        message.from_user
    )

    changed = False

    if user_id in muted_users:

        if muted_users[user_id] != display_name:
            muted_users[user_id] = display_name
            changed = True

    if user_id in restricted_users:

        if restricted_users[user_id] != display_name:
            restricted_users[user_id] = display_name
            changed = True

    if changed:
        await save_settings()

    # التحقق من الكتم أو التقييد

    is_muted = user_id in muted_users
    is_restricted = user_id in restricted_users

    if not is_muted and not is_restricted:
        return

    # حذف الرسالة من الطرفين

    try:
        await client.delete_messages(
            chat_id=message.chat.id,
            message_ids=message.id,
            revoke=True
        )

        print(
            f"[PRIVATE MODERATION] Deleted message from {user_id}"
        )

    except FloodWait as exc:

        print(
            f"[PRIVATE MODERATION] Delete FloodWait: {exc.value}s"
        )

        return

    except Exception as exc:

        print(
            f"[PRIVATE MODERATION] Delete error: {exc}"
        )

    # إذا كان مكتوماً لا نرسل أي تنبيه

    if is_muted:
        return

    # إذا كان مقيداً نرسل تنبيهاً

    if is_restricted:

        now = time.monotonic()

        last_notice = restrict_notice_times.get(
            user_id,
            0
        )

        if now - last_notice < RESTRICT_NOTICE_INTERVAL:
            return

        try:

            await client.send_message(
                chat_id=message.chat.id,
                text=RESTRICT_NOTICE
            )

            restrict_notice_times[user_id] = now

            print(
                f"[PRIVATE MODERATION] Restriction notice sent to {user_id}"
            )

        except FloodWait as exc:

            print(
                f"[PRIVATE MODERATION] Notice FloodWait: {exc.value}s"
            )

        except Exception as exc:

            print(
                f"[PRIVATE MODERATION] Notice error: {exc}"
            )

# ==========================================
# استقبال رسائل القروبات واكتشاف نواف
# ==========================================

async def _name_reaction_handler(client, message):

    if not message.from_user:
        return

    if message.from_user.is_self:
        return

    text = message.text or message.caption or ""

    if not text:
        return

    if not WORD_PATTERN.search(text):
        return

    # إضافة التفاعل

    try:

        await client.send_reaction(
            chat_id=message.chat.id,
            message_id=message.id,
            emoji=REACTION_EMOJI
        )

        print(
            f"[NAME REACTION] Reacted in chat {message.chat.id}"
        )

    except FloodWait as exc:

        print(
            f"[NAME REACTION] Reaction FloodWait: {exc.value}s"
        )

    except Exception as exc:

        print(
            f"[NAME REACTION] Reaction error: {exc}"
        )

    # إذا الردود معطلة نتوقف هنا

    if not replies_enabled:
        return

    # تحديد الرد حسب حالة الحساب

    reply = await get_account_status()

    try:

        await message.reply_text(reply)

        print(
            f"[NAME REACTION] Replied: {reply}"
        )

    except FloodWait as exc:

        print(
            f"[NAME REACTION] Reply FloodWait: {exc.value}s"
        )

    except Exception as exc:

        print(
            f"[NAME REACTION] Reply error: {exc}"
        )

# ==========================================
# الإرسال اليومي التلقائي
# ==========================================

def load_daily_state():

    try:

        if DAILY_STATE_FILE.exists():

            with DAILY_STATE_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, dict):
                return data

    except Exception as exc:

        print(
            f"[DAILY MESSAGE] State load error: {exc}"
        )

    return {}

def save_daily_state(data):

    try:

        temp_file = DAILY_STATE_FILE.with_suffix(".tmp")

        with temp_file.open("w", encoding="utf-8") as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        temp_file.replace(DAILY_STATE_FILE)

    except Exception as exc:

        print(
            f"[DAILY MESSAGE] State save error: {exc}"
        )

async def resolve_daily_chat():
    try:
        chat = await _client.get_chat(DAILY_CHAT_ID)
        print(f"[DAILY MESSAGE] Target group: {chat.title}")
        return chat.id

    except Exception as exc:
        print(f"[DAILY MESSAGE] Group resolution error: {exc}")
        return None

async def daily_message_loop():

    global _daily_chat_id

    state = load_daily_state()

    print(
        "[DAILY MESSAGE] Scheduler started."
    )

    while True:

        try:

            now = datetime.now(DAILY_TIMEZONE)

            target = now.replace(
                hour=DAILY_SEND_HOUR,
                minute=DAILY_SEND_MINUTE,
                second=0,
                microsecond=0
            )

            if target <= now:
                target += timedelta(days=1)

            wait_seconds = (
                target - now
            ).total_seconds()

            print(
                f"[DAILY MESSAGE] Next send: {target.isoformat()}"
            )

            await asyncio.sleep(wait_seconds)

            send_date = target.date().isoformat()

            # منع تكرار الإرسال في نفس اليوم

            if state.get("last_sent_date") == send_date:
                continue

            # إعادة المحاولة حتى تنجح عملية الإرسال

            while state.get("last_sent_date") != send_date:

                try:

                    if _daily_chat_id is None:

                        _daily_chat_id = await resolve_daily_chat()

                    if _daily_chat_id is None:

                        print(
                            "[DAILY MESSAGE] Group unavailable. Retrying in 60 seconds."
                        )

                        await asyncio.sleep(60)
                        continue

                    await _client.send_message(
                        chat_id=_daily_chat_id,
                        text=DAILY_MESSAGE
                    )

                    # حفظ تاريخ الإرسال

                    state["last_sent_date"] = send_date

                    save_daily_state(state)

                    print(
                        f"[DAILY MESSAGE] Sent successfully: {send_date}"
                    )

                    break

                except FloodWait as exc:

                    print(
                        f"[DAILY MESSAGE] FloodWait: {exc.value}s"
                    )

                    await asyncio.sleep(exc.value + 1)

                except asyncio.CancelledError:
                    raise

                except Exception as exc:

                    print(
                        f"[DAILY MESSAGE] Send error: {exc}"
                    )

                    await asyncio.sleep(60)

        except asyncio.CancelledError:

            print(
                "[DAILY MESSAGE] Scheduler stopped."
            )

            raise

        except Exception as exc:

            print(
                f"[DAILY MESSAGE] Scheduler error: {exc}"
            )

            await asyncio.sleep(60)

# ==========================================
# التشغيل
# ==========================================

async def start_name_reaction():

    global _client
    global _account_user_id
    global _handler
    global _control_handler
    global _private_handler
    global _daily_task
    global _daily_chat_id

    if _handler is not None:
        return

    _client = get_music_client()

    if _client is None:

        print(
            "[NAME REACTION] Music account is not connected."
        )

        return

    try:
        account_me = await _client.get_me()
        _account_user_id = account_me.id
        print(
            f"[NAME REACTION] Control handler account id: {_account_user_id}"
        )
    except Exception as exc:
        print(f"[NAME REACTION] Cannot identify control account: {exc}")
        _client = None
        _account_user_id = None
        return

    # تحميل إعدادات الردود والكتم والتقييد من قاعدة البيانات
    try:
        await load_settings()
    except Exception as exc:
        print(f"[NAME REACTION] Cannot load persistent settings: {exc}")
        _client = None
        return

    # أوامر الحساب

    # استقبال رسائل الحساب نفسه صراحةً عبر فلتر Pyrogram المخصص له.
    # هذا يمنع الاعتماد على outgoing أو فحص مرسل الرسالة بعد وصول كل رسائل القروب.
    _control_handler = MessageHandler(
        _reply_control_handler,
        filters.me & (filters.text | filters.caption)
    )

    # اكتشاف نواف في القروبات

    _handler = MessageHandler(
        _name_reaction_handler,
        filters.group
        & (filters.text | filters.caption)
        & filters.incoming
    )

    # مراقبة الخاص

    _private_handler = MessageHandler(
        _private_moderation_handler,
        filters.private
        & filters.incoming
    )

    _client.add_handler(
        _control_handler,
        group=CONTROL_HANDLER_GROUP
    )

    _client.add_handler(
        _handler,
        group=HANDLER_GROUP
    )

    _client.add_handler(
        _private_handler,
        group=PRIVATE_HANDLER_GROUP
    )

    print(
        "[NAME REACTION] Started successfully."
    )

    print(
        f"[NAME REACTION] Replies enabled: {replies_enabled}"
    )

    print(
        f"[PRIVATE MODERATION] Muted: {len(muted_users)}"
    )

    print(
        f"[PRIVATE MODERATION] Restricted: {len(restricted_users)}"
    )

    # تشغيل الإرسال اليومي

    _daily_task = asyncio.create_task(
        daily_message_loop()
    )

    print(
        "[DAILY MESSAGE] Daily scheduler enabled."
    )

# ==========================================
# الإيقاف
# ==========================================

async def shutdown_name_reaction():

    global _client
    global _account_user_id
    global _handler
    global _control_handler
    global _private_handler
    global _daily_task
    global _daily_chat_id

    # إيقاف مهمة الإرسال اليومي

    if _daily_task is not None:

        _daily_task.cancel()

        try:
            await _daily_task

        except asyncio.CancelledError:
            pass

        _daily_task = None

    if _client is not None:

        handlers = [
            (_handler, HANDLER_GROUP),
            (_control_handler, CONTROL_HANDLER_GROUP),
            (_private_handler, PRIVATE_HANDLER_GROUP)
        ]

        for handler, group in handlers:

            if handler is None:
                continue

            try:

                _client.remove_handler(
                    handler,
                    group=group
                )

            except Exception as exc:

                print(
                    f"[NAME REACTION] Stop error: {exc}"
                )

    _handler = None
    _control_handler = None
    _private_handler = None

    _daily_chat_id = None
    _client = None
    _account_user_id = None

    print(
        "[NAME REACTION] Stopped."
    )
