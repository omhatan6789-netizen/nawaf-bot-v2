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
    if not await check_database():
        raise RuntimeError("Database health check failed")
    logger.info("Bot startup completed")


async def post_shutdown(application: Application) -> None:
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

    # Plain-text commands retain the legacy wording.
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
    application.add_handler(MessageHandler(filters.Regex(r"^قفل امر .+$"), lock_command))
    application.add_handler(MessageHandler(filters.Regex(r"^فتح امر .+$"), open_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(Dev|المالك|نائب المالك|ادمن اساسي|ادمن|مميز)$"), save_lock_rank))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, command_guard), group=-2)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_text_message), group=1)
    application.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER), group=-1)
    return application


if __name__ == "__main__":
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)
