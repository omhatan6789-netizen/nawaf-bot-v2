import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import load_settings
from database import close_pool, init_pool
from database.health import check_database
from database.migration_runner import apply_all_migrations
from database.activity import shutdown_activity
from handlers.message_tracking import save_group_text_message
from handlers.user_events import chat_member_updated
from handlers.points import (
    add_points_command, remove_points_command, sell_points,
    my_points, top_points, flush_pending_points,
)
from handlers.roles import (
    roles_command, change_rank, dev_list_command, rank_list_command,
    clear_dev_command, clear_rank_command, clear_all_ranks_command,
    roles_clear_callback,
)
from handlers.user_permissions import permission_command
from handlers.command_guard import command_guard
from handlers.command_lock import lock_command, save_lock_rank, open_command
from handlers.repetition import (
    repetition_message_handler, repetition_expiry_loop,
    enable_repetition, disable_repetition, set_repetition_start,
    receive_repetition_duration, set_mute_duration,
    set_restrict_duration, set_repetition_rank,
    clear_user_repetition_warnings,
)
from handlers.moderation import (
    moderation_command, check_muted_message,
    unmute_command, unrestrict_command, unban_command,
    clear_restrictions_command, moderation_lists_command,
    clear_list_callback, enable_durations_command,
    disable_durations_command, enable_reasons_command,
    disable_reasons_command, warning_command,
    clear_warnings_command, reveal_restrictions_command,
    moderation_expiry_loop, reveal_command, repetition_action_callback,
)
from handlers.profile_replies import (
    developer_command, change_developer_username,
    owner_command, change_owner_username,
    add_my_admin_reply, delete_my_admin_reply, delete_other_admin_reply,
    admin_replies_list, enable_admin_replies, disable_admin_replies,
    delete_all_admin_replies_command, check_admin_profile_reply,
    profile_reply_pending_handler,
)

from handlers.replies import (
    add_reply_start, add_reply_handler, check_replies, replies_list,
    add_special_reply_start, add_special_reply_handler, special_replies_list,
    edit_special_reply_start, edit_special_reply_handler,
    edit_reply_start, edit_reply_handler,
    delete_special_reply_start, delete_special_reply_handler,
    delete_reply_start, delete_reply_handler,
    delete_all_replies, delete_all_special_replies,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("nawaf-bot")


async def post_init(application: Application) -> None:
    settings = application.bot_data["settings"]
    await init_pool(settings)
    await apply_all_migrations()
    from database.replies import load_replies_cache
    await load_replies_cache()
    if not await check_database():
        raise RuntimeError("Database health check failed")
    application.bot_data["moderation_expiry_task"] = application.create_task(
        moderation_expiry_loop(application),
        name="moderation-expiry-loop",
    )
    application.bot_data["repetition_expiry_task"] = application.create_task(
        repetition_expiry_loop(application),
        name="repetition-expiry-loop",
    )
    logger.info("Bot startup completed")


async def post_shutdown(application: Application) -> None:
    for task_key in ("moderation_expiry_task", "repetition_expiry_task"):
        task = application.bot_data.get(task_key)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    try:
        await flush_pending_points()
        await shutdown_activity()
    finally:
        await close_pool()
    logger.info("Bot shutdown completed")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("أهلًا! بوت نواف قيد التجهيز 🎖️")


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        healthy = await check_database()
    except Exception:
        logger.exception("Database health check failed")
        healthy = False

    if update.effective_message:
        await update.effective_message.reply_text(
            "قاعدة البيانات تعمل ✅" if healthy else "تعذر الاتصال بقاعدة البيانات ❌"
        )


def build_application() -> Application:
    settings = load_settings()
    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health", health_command))

    # Repetition protection settings and message detector.
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, receive_repetition_duration), group=-10)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تفعيل التكرار$"), enable_repetition))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تعطيل التكرار$"), disable_repetition))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع تكرار \d+$"), set_repetition_start))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع كتم تكرار \S+$"), set_mute_duration))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع تقييد تكرار \S+$"), set_restrict_duration))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^(?:ضع|تغيير) رتبة التكرار (عضو|مميز|ادمن|ادمن اساسي|نائب المالك|المالك|Dev)$"), set_repetition_rank))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, repetition_message_handler), group=38)

    # Moderation / sanctions (same plain-text commands as the legacy bot).
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, check_muted_message), group=-30)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تفعيل المدة للمشرفين$"), enable_durations_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تعطيل المدة للمشرفين$"), disable_durations_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تفعيل الاسباب$"), enable_reasons_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تعطيل الاسباب$"), disable_reasons_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^كشف(?:\s+@[A-Za-z0-9_]+|\s+\d+)?$"), reveal_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^كشف القيود(?:\s+@[A-Za-z0-9_]+|\s+\d+)?$"), reveal_restrictions_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^(كتم|تقييد|حظر)(?:\s+.+)?$"), moderation_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^الغاء الكتم(?:\s+.+)?$"), unmute_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^الغاء التقييد(?:\s+.+)?$"), unrestrict_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^الغاء الحظر(?:\s+.+)?$"), unban_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^رفع القيود(?:\s+.+)?$"), clear_restrictions_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^(المكتومين|المقيدين|المحظورين)$"), moderation_lists_command))
    application.add_handler(CallbackQueryHandler(clear_list_callback, pattern=r"^moderation:clear:"))
    application.add_handler(CallbackQueryHandler(repetition_action_callback, pattern=r"^repetition_punish:(?:mute|restrict):\d+$"))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^انذار(?:\s+.+)?$"), warning_command))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^مسح انذاراته$"), clear_warnings_command))

    # Profile cards and admin replies (legacy plain-text commands).
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, profile_reply_pending_handler), group=-11)
    application.add_handler(MessageHandler(filters.Regex(r"^المطور$"), developer_command))
    application.add_handler(MessageHandler(filters.Regex(r"^تغيير يوزر المطور$"), change_developer_username))
    application.add_handler(MessageHandler(filters.Regex(r"^المالك$"), owner_command))
    application.add_handler(MessageHandler(filters.Regex(r"^تغيير يوزر المالك$"), change_owner_username))
    application.add_handler(MessageHandler(filters.Regex(r"^اضف ردي$"), add_my_admin_reply))
    application.add_handler(MessageHandler(filters.Regex(r"^حذف ردي$"), delete_my_admin_reply))
    application.add_handler(MessageHandler(filters.Regex(r"^حذف رده$"), delete_other_admin_reply))
    application.add_handler(MessageHandler(filters.Regex(r"^ردود الادمن$"), admin_replies_list))
    application.add_handler(MessageHandler(filters.Regex(r"^تفعيل ردود الادمن$"), enable_admin_replies))
    application.add_handler(MessageHandler(filters.Regex(r"^تعطيل ردود الادمن$"), disable_admin_replies))
    application.add_handler(MessageHandler(filters.Regex(r"^حذف ردود الادمن$"), delete_all_admin_replies_command))
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, check_admin_profile_reply),
        group=39,
    )

    # Plain-text commands retain the legacy wording.
    application.add_handler(MessageHandler(filters.Regex(r"^اضف رد مميز$"), add_special_reply_start))
    application.add_handler(MessageHandler(filters.Regex(r"^اضف رد$"), add_reply_start))
    application.add_handler(MessageHandler(filters.Regex(r"^نقاطي$"), my_points))
    application.add_handler(MessageHandler(filters.Regex(r"^توب النقاط(?:🎖️)?$"), top_points))
    application.add_handler(MessageHandler(filters.Regex(r"^اضف(?:\s+.*)?$"), add_points_command))
    application.add_handler(MessageHandler(filters.Regex(r"^خصم(?:\s+.*)?$"), remove_points_command))
    application.add_handler(MessageHandler(filters.Regex(r"^بيع نقاطي(?:\s+.*)?$"), sell_points))
    application.add_handler(MessageHandler(filters.Regex(r"^(رتبتي|رتبته(?:\s+@[A-Za-z0-9_]+|\s+\d+)?)$"), roles_command))
    application.add_handler(MessageHandler(filters.Regex(r"^كشف المجموعة$"), roles_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(رفع|تنزيل) (Dev|المالك|نائب المالك|ادمن اساسي|ادمن|مميز)(?:\s+(@[A-Za-z0-9_]+|\d+))?$"), change_rank))
    application.add_handler(MessageHandler(filters.Regex(r"^تنزيل الكل(?:\s+(@[A-Za-z0-9_]+|\d+))?$"), change_rank))
    application.add_handler(MessageHandler(filters.Regex(r"^قائمة (?:Dev|dev)$"), dev_list_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(المميزين|الادمنية|الادمنية الاساسيين|نواب المالك|المالكين)$"), rank_list_command))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح (?:Dev|dev)$"), clear_dev_command))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح (?:المميزين|الادمنية|الادمنية الاساسيين|نواب المالك|المالكين)$"), clear_rank_command))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح الرتب$"), clear_all_ranks_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(منع|سماح)\s+.+$"), permission_command))
    application.add_handler(CallbackQueryHandler(roles_clear_callback, pattern=r"^roles_clear:"))
    application.add_handler(MessageHandler(filters.ALL, add_special_reply_handler), group=2)
    application.add_handler(MessageHandler(filters.Regex(r"^تعديل رد مميز$"), edit_special_reply_start))
    application.add_handler(MessageHandler(filters.ALL, edit_special_reply_handler), group=3)
    application.add_handler(MessageHandler(filters.Regex(r"^مسح رد مميز$"), delete_special_reply_start))
    application.add_handler(MessageHandler(filters.ALL, delete_special_reply_handler), group=4)
    application.add_handler(MessageHandler(filters.ALL, add_reply_handler), group=5)
    application.add_handler(MessageHandler(filters.Regex(r"^تعديل رد$"), edit_reply_start))
    application.add_handler(MessageHandler(filters.ALL, edit_reply_handler), group=6)
    application.add_handler(MessageHandler(filters.Regex(r"^مسح رد$"), delete_reply_start))
    application.add_handler(MessageHandler(filters.ALL, delete_reply_handler), group=7)
    application.add_handler(MessageHandler(filters.Regex(r"^الردود$"), replies_list))
    application.add_handler(MessageHandler(filters.Regex(r"^الردود المميزة$"), special_replies_list))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح الردود$"), delete_all_replies))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح الردود المميزة$"), delete_all_special_replies))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_replies), group=40)
    application.add_handler(MessageHandler(filters.Regex(r"^قفل امر .+$"), lock_command))
    application.add_handler(MessageHandler(filters.Regex(r"^فتح امر .+$"), open_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(Dev|المالك|نائب المالك|ادمن اساسي|ادمن|مميز)$"), save_lock_rank))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, command_guard), group=-2)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_text_message), group=1)
    application.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER), group=-1)
    return application


if __name__ == "__main__":
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)
