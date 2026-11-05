"""Asynchronous custom command aliases, preserving the original PTB update flow."""
from __future__ import annotations

from telegram import Update
from telegram.ext import (
    ApplicationHandlerStop, ContextTypes, ConversationHandler, MessageHandler, filters,
)
from database.custom_commands import (
    load_commands, save_command, delete_command as db_delete_command,
    delete_all_commands as db_delete_all_commands,
)

OWNER_ID = 8453977662
OWNER_ACCOUNT_ID = 6496915877
AUTHORIZED_OWNER_IDS = {OWNER_ID, OWNER_ACCOUNT_ID}
WAIT_OLD, WAIT_NEW = range(2)
add_command_sessions = {}
_custom_commands_cache = None
_alias_execution_keys = set()


def _update_key(update):
    message = getattr(update, "message", None) if update else None
    if not message:
        return None
    return (getattr(message, "chat_id", None), getattr(message, "message_id", None))


def is_alias_execution(update):
    key = _update_key(update)
    return key in _alias_execution_keys if key else False


async def load_custom_commands_cache():
    global _custom_commands_cache
    rows = await load_commands()
    _custom_commands_cache = {
        str(row["new_command"]).strip(): str(row["old_command"]).strip()
        for row in rows if row["new_command"] and row["old_command"]
    }
    return _custom_commands_cache


def get_custom_commands_cache():
    return _custom_commands_cache if _custom_commands_cache is not None else {}


async def invalidate_custom_commands_cache():
    return await load_custom_commands_cache()


def set_custom_command_cache(old_command, new_command):
    global _custom_commands_cache
    if _custom_commands_cache is None:
        _custom_commands_cache = {}
    old = str(old_command or "").strip()
    new = str(new_command or "").strip()
    if old and new:
        _custom_commands_cache[new] = old


def remove_custom_command_cache(new_command):
    if _custom_commands_cache is not None:
        _custom_commands_cache.pop(str(new_command or "").strip(), None)


def clear_custom_commands_cache():
    global _custom_commands_cache
    _custom_commands_cache = {}


async def add_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or user.id not in AUTHORIZED_OWNER_IDS:
        return ConversationHandler.END
    add_command_sessions[user.id] = {}
    context.user_data["custom_command"] = True
    await message.reply_text("حسناً، أرسل الأمر القديم")
    return WAIT_OLD


async def receive_old_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or user.id not in add_command_sessions:
        return ConversationHandler.END
    if not message or not message.text:
        return WAIT_OLD
    old = message.text.strip()
    if not old:
        await message.reply_text("• أرسل الأمر القديم")
        return WAIT_OLD
    add_command_sessions[user.id]["old"] = old
    await message.reply_text("حسناً، أرسل الأمر الجديد")
    return WAIT_NEW


async def receive_new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if not user or user.id not in add_command_sessions:
        return ConversationHandler.END
    if not message or not message.text:
        return WAIT_NEW
    new = message.text.strip()
    if not new:
        await message.reply_text("• أرسل الأمر الجديد")
        return WAIT_NEW
    old = add_command_sessions[user.id].get("old")
    if not old:
        add_command_sessions.pop(user.id, None)
        context.user_data.pop("custom_command", None)
        return ConversationHandler.END
    if old == new:
        await message.reply_text("• الأمر الجديد لازم يكون مختلف عن الأمر القديم")
        return WAIT_NEW
    try:
        # The new name is unique; replace an existing alias atomically.
        from database.pool import get_pool
        async with get_pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM custom_commands WHERE new_command=$1", new)
                await conn.execute(
                    "INSERT INTO custom_commands(old_command,new_command) VALUES($1,$2)",
                    old, new,
                )
    except Exception as exc:
        print(f"[CustomCommands] save failed: {exc}")
        await message.reply_text("❌ حصل خطأ أثناء حفظ الأمر.")
        return WAIT_NEW
    set_custom_command_cache(old, new)
    add_command_sessions.pop(user.id, None)
    context.user_data.pop("custom_command", None)
    await message.reply_text(f"✅ تم إضافة الأمر\n\n{new} يعمل الآن مثل {old}")
    return ConversationHandler.END


def build_add_command_conversation():
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^اضف امر$"), add_command_start),
        ],
        states={
            WAIT_OLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_old_command)],
            WAIT_NEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_command)],
        },
        fallbacks=[],
        name="custom-command-add",
        persistent=False,
    )


async def custom_commands_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    data = [(old, new) for new, old in get_custom_commands_cache().items()]
    data.sort(key=lambda item: item[1])
    if not data:
        await message.reply_text("لا توجد أوامر مضافة")
        return
    output = "📌 الأوامر المضافة:\n\n" + "".join(f"{new} ➜ {old}\n" for old, new in data)
    await message.reply_text(output)


async def delete_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    context.user_data["delete_command"] = True
    await message.reply_text("أرسل الأمر الجديد الذي تريد حذفه")


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("delete_command"):
        return
    message = update.effective_message
    if not message or not message.text:
        return
    command = message.text.strip()
    try:
        deleted = await db_delete_command(command)
    except Exception as exc:
        print(f"[CustomCommands] delete failed: {exc}")
        context.user_data.pop("delete_command", None)
        await message.reply_text("❌ حصل خطأ أثناء حذف الأمر.")
        return
    remove_custom_command_cache(command)
    context.user_data.pop("delete_command", None)
    if deleted:
        await message.reply_text("✅ تم حذف الأمر المضاف")
    else:
        await message.reply_text("• ما لقيت هذا الأمر ضمن الأوامر المضافة")


async def delete_all_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return
    try:
        await db_delete_all_commands()
    except Exception as exc:
        print(f"[CustomCommands] delete all failed: {exc}")
        await message.reply_text("❌ حصل خطأ أثناء حذف الأوامر.")
        return
    clear_custom_commands_cache()
    await message.reply_text("✅ تم حذف جميع الأوامر المضافة")


def get_custom_command(text):
    value = str(text or "").strip()
    if not value:
        return None
    return get_custom_commands_cache().get(value)


async def check_custom_commands(update, context, application=None):
    message = update.effective_message
    if not message or not message.text or not application or is_alias_execution(update):
        return False
    user = update.effective_user
    if user and user.id in add_command_sessions:
        return False
    if context.user_data.get("delete_command"):
        return False
    text = message.text.strip()
    old_command = get_custom_command(text)
    if not old_command or old_command.strip() == text:
        return False
    try:
        data = update.to_dict()
        message_data = data.get("message")
        if not message_data:
            return False
        message_data["text"] = old_command.strip()
        message_data.pop("entities", None)
        fake_update = Update.de_json(data, application.bot)
        key = _update_key(fake_update)
        if key:
            _alias_execution_keys.add(key)
        try:
            await application.process_update(fake_update)
        finally:
            if key:
                _alias_execution_keys.discard(key)
        print(f"[CustomCommands] executed alias: {text} -> {old_command}")
        return True
    except Exception as exc:
        print(f"[CustomCommands] alias execution failed: {exc}")
        return False


async def custom_command_alias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_custom_commands(update, context, context.application):
        raise ApplicationHandlerStop
