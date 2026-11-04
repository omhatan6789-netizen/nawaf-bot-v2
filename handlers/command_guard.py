from __future__ import annotations

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database.roles import check_command_permission

MULTI_WORD_COMMANDS = [
    "كشف المجموعة", "كشف القيود", "رفع القيود", "الغاء التقييد",
    "الغاء الحظر", "الغاء الكتم", "تفعيل المدة للمشرفين",
    "تعطيل المدة للمشرفين", "تفعيل الاسباب", "تعطيل الاسباب",
    "مسح انذاراته", "المكتومين", "المقيدين", "المحظورين",
    "كشف", "كتم", "تقييد", "حظر", "انذار",
    "تفعيل التكرار", "تعطيل التكرار", "ضع تكرار",
    "ضع كتم تكرار", "ضع تقييد تكرار", "ضع رتبة التكرار",
    "تغيير رتبة التكرار",
    "حظر عام", "كتم عام", "قفل امر", "فتح امر",
    "اضف رد مميز", "تعديل رد مميز", "مسح رد مميز", "الردود المميزة",
    "مسح الردود المميزة", "اضف رد", "تعديل رد", "مسح رد", "الردود",
    "مسح الردود", "اضف ردي", "حذف ردي", "حذف رده", "ردود الادمن",
    "تفعيل ردود الادمن", "تعطيل ردود الادمن", "حذف ردود الادمن",
    "تغيير يوزر المطور", "تغيير يوزر المالك",
    "اضف لعبة", "الالعاب", "حذف لعبة",
    "رفع Dev", "تنزيل Dev", "رفع المالك", "تنزيل المالك",
    "رفع نائب المالك", "تنزيل نائب المالك", "رفع ادمن اساسي",
    "تنزيل ادمن اساسي", "رفع ادمن", "تنزيل ادمن", "رفع مميز",
    "تنزيل مميز", "اوامر الادمن", "اوامر المطور", "نقاطي",
    "سباق الكلمات", "انهاء سباق الكلمات",
]

WAITING_KEYS = (
    "add_reply", "edit_reply", "delete_reply", "add_special_reply",
    "edit_special_reply", "delete_special_reply", "add_game",
    "add_question", "lock_command", "custom_command",
    "delete_command", "button_color",
)


def get_command_name(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    matches = [command for command in MULTI_WORD_COMMANDS
               if text == command or text.startswith(command + " ")]
    return max(matches, key=len) if matches else text.split()[0]


def command_lock_message(required: str) -> str:
    messages = {
        "Dev": "• اعذرني هذا الامر للـ Dev فقط .",
        "المالك": "• اعذرني بس هذا الامر للمالك وفوق فقط .",
        "نائب المالك": "• اعذرني بس هذا الامر لنائب المالك وفوق فقط .",
        "ادمن اساسي": "• اعذرني بس هذا الامر للادمن الاساسي وفوق فقط .",
        "ادمن": "• اعذرني بس هذا الامر للادمن وفوق فقط .",
        "مميز": "• اعذرني بس هذا الامر للمميز وفوق فقط .",
    }
    return messages.get(required, "• اعذرني بس ما عندك الصلاحية لهذا الامر .")


async def command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return
    text = (message.text or "").strip()
    if not text:
        return

    if any(key in context.user_data for key in WAITING_KEYS):
        return
    try:
        from handlers.replies import (
            add_reply_sessions, add_special_reply_sessions,
            delete_special_reply_sessions, edit_special_reply_sessions,
            edit_reply_sessions, delete_reply_sessions,
        )
        if any(user.id in sessions for sessions in (
            add_reply_sessions, add_special_reply_sessions,
            delete_special_reply_sessions, edit_special_reply_sessions,
            edit_reply_sessions, delete_reply_sessions,
        )):
            return
    except ImportError:
        pass
    if text == "منع" or text.startswith("منع ") or text == "سماح" or text.startswith("سماح "):
        return
    if text.startswith("قفل امر ") or text.startswith("فتح امر "):
        return

    command = get_command_name(text)
    if not command:
        return
    allowed, required = await check_command_permission(user.id, command, chat.id)
    if required is not None and not allowed:
        await message.reply_text(command_lock_message(required))
        raise ApplicationHandlerStop()
