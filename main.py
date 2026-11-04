import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_text_message), group=1)
    application.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER), group=-1)
    return application


if __name__ == "__main__":
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)
