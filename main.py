import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, ChatMemberHandler, CommandHandler, ContextTypes, ConversationHandler, InlineQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters

from config import load_settings
from handlers.mini_app import mini_app_message, register_mini_app_menu
from handlers.game_end_sounds import (
    game_end_sound_command, game_end_sound_callback, game_end_sound_message,
)
from handlers.mini_app_panel import (
    mini_app_panel_command, mini_app_panel_callback, mini_app_panel_message, mini_app_color_command,
)
from mini_app_server import configure_mini_app
from database.update_processor import ChatSerialUpdateProcessor
from database import close_pool, init_pool
from database.pool import get_pool
from database.health import check_database
from database.migration_runner import apply_all_migrations
from database.activity import shutdown_activity
from handlers.message_tracking import save_group_text_message, track_observed_group_user
from handlers.user_events import chat_member_updated
from handlers.points import (
    add_points_command, remove_points_command, sell_points,
    my_points, flush_pending_points,
)
from handlers.top_menu import top_menu_command, top_menu_callback
from handlers.reset_stats import (
    reset_active_local_command, reset_active_global_command,
    reset_points_command, my_messages_command, stats_reset_callback,
)
from handlers.roles import (
    roles_command, change_rank, dev_list_command, rank_list_command,
    clear_dev_command, clear_rank_command, clear_all_ranks_command,
    roles_clear_callback,
)
from handlers.user_permissions import permission_command
from handlers.command_guard import command_guard
from handlers.command_lock import lock_command, save_lock_rank, open_command
from handlers.blocked_words import (
    blocked_words_message_handler, blocked_words_callback,
    blocked_words_expiry_loop,
)
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
from handlers.delete_messages import delete_messages
from ai_assistant import ai_assistant_message
from music_call import start_music_call, shutdown_music_call
from memory_monitor import log_memory_checkpoint
from account_clock import start_account_clock, shutdown_account_clock
from auto_private_reply import start_auto_private_reply, shutdown_auto_private_reply
from name_reaction import start_name_reaction, shutdown_name_reaction
from custom_commands import (
    build_add_command_conversation, load_custom_commands_cache,
    custom_commands_list, delete_command_start, delete_command,
    delete_all_commands, custom_command_alias_handler,
)
from button_colors import (
    load_button_color_cache, register_existing_panel_buttons,
    patch_inline_keyboard_buttons,
)
from handlers.button_colors import change_button_color_start, change_button_color_handler
from handlers.emoji_reactions import emoji_reactions_handler, load_emoji_reaction_rules
from handlers.mandatory_subscription import (
    mandatory_subscription_guard, mandatory_subscription_commands,
)
from handlers.whisper import (
    whisper_command, whisper_start_handler, whisper_private_message,
    whisper_callbacks, enable_whispers_command, disable_whispers_command,
    whispers_list_command,
)
from handlers.temporary_messages import (
    temporary_message_command, temporary_message_pending_handler,
    temporary_message_callback, temporary_message_scheduler,
    track_temporary_message_chat,
)
from games.rock_paper_scissors import (
    start_rock_paper_scissors, rock_paper_scissors_callback,
)
from games.online_mode import (
    online_games_inline_query, online_lobby_callback,
    online_image_add_start, online_image_select, online_image_receive,
)
from games.connect4_challenge import (
    connect4_challenge_command, connect4_challenge_callback,
)
from games.mini_games import (
    mini_game_challenge_command, mini_game_challenge_callback,
)
from games.xo import start_xo_game, xo_callback
from games.engine import ensure_game_tables, game_message_handler
from games.demon_nawaf import start_demon_nawaf, demon_nawaf_callback, ensure_demon_tables
from games.liar import (
    start_liar_game_lobby, force_voting,
    liar_lobby_callback, liar_vote_callback, liar_guess_callback,
    check_liar_message,
)
from games.hide_and_seek import (
    start_hide_game, hide_number_callback, search_number_callback,
)
from games.penalties import (
    start_penalty_game, distribute_penalties, manual_team_command,
    distribution_callback, penalty_direction_callback,
    penalty_direction_message,
)
from games.big_game_join import (
    join_big_game_router, begin_big_game_router,
    continue_big_game_router, end_big_game_router,
    leave_big_game_router, distribute_big_game_router,
    add_big_game_player_router,
)
from games.word_race import (
    start_word_race, word_race_mode, word_race_distribution,
    word_race_manual_team, word_race_add_solo,
    word_race_callback, check_word_race_message,
)
from games.image_quiz.image_quiz import (
    start_image_quiz, image_quiz_settings,
    check_image_quiz_message, image_quiz_callback,
    add_manual_image_command, receive_manual_image, cancel_manual_image,
    delete_manual_image_command, receive_delete_manual_image,
    cancel_delete_manual_image,
)
from handlers.tasliyat import (
    create_bank_account, bank_callback, my_bank_account,
    delete_bank_account, salary, tip, invest, luck,
    store, my_possessions, other_possessions, buy_sell, gift,
    rob, transfer, transfer_account_number,
    transfer_message_callback, transfer_message_receiver,
    show_scratch_codes, scratch_code, reset_scratch_cooldown,
)
from handlers.users import user_id_command
from handlers.newf_ai import newf_profile_request
from handlers.commands_menu import commands_menu_start, commands_menu_callback, games_keyboard
from handlers.start import start
from handlers.start_editor import (
    start_editor_command, start_editor_callback,
    start_editor_special_callback, start_editor_message,
)
from handlers.developer_panel import (
    developer_panel_command, developer_panel_callback, developer_panel_message,
)
from handlers.stars_subscriptions import (
    stars_panel_callback, stars_panel_message, stars_group_invoice_command,
    stars_precheckout_handler, stars_successful_payment_handler,
    stars_group_guard, stars_group_callback_guard,
)
from handlers.send import send_command, handle_send_media
from handlers.music import (
    music_message_handler, music_callback, voice_chat_started, voice_chat_ended,
)
from handlers.youtube_audio import youtube_audio_search, youtube_audio_callback

from handlers.games_menu import games_menu_command, games_menu_callback
from handlers.games_help import games_help
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
    log_memory_checkpoint("post_init_start")
    settings = application.bot_data["settings"]
    configure_mini_app(asyncio.get_running_loop(), application.bot)
    await register_mini_app_menu(application)
    await init_pool(settings)
    log_memory_checkpoint("database_pool_ready")
    await apply_all_migrations()
    await ensure_demon_tables()
    await ensure_game_tables()
    from database.replies import load_replies_cache
    await load_replies_cache()
    await load_button_color_cache()
    await register_existing_panel_buttons()
    patch_inline_keyboard_buttons()
    await load_custom_commands_cache()
    await load_emoji_reaction_rules()
    log_memory_checkpoint("caches_loaded")
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
    application.bot_data["blocked_words_expiry_task"] = application.create_task(
        blocked_words_expiry_loop(application),
        name="blocked-words-expiry-loop",
    )
    application.bot_data["temporary_message_scheduler_task"] = application.create_task(
        temporary_message_scheduler(application),
        name="temporary-message-scheduler",
    )
    try:
        log_memory_checkpoint("before_music_account_start")
        music_started = await start_music_call()
        log_memory_checkpoint("after_music_account_start")
        if music_started:
            await start_account_clock()
            log_memory_checkpoint("after_account_clock_start")
            await start_auto_private_reply()
            log_memory_checkpoint("after_auto_reply_start")
            await start_name_reaction()
            log_memory_checkpoint("after_name_reaction_start")
            logger.info("Music account connected; profile clock, auto-reply and name reactions started.")
    except Exception:
        logger.exception("Music account startup failed")
    logger.info("Bot startup completed")

async def post_shutdown(application: Application) -> None:
    try:
        await shutdown_name_reaction()
    except Exception:
        logger.exception("Name reaction shutdown failed")
    try:
        await shutdown_auto_private_reply()
    except Exception:
        logger.exception("Private auto-reply shutdown failed")
    try:
        await shutdown_account_clock()
    except Exception:
        logger.exception("Account clock shutdown failed")
    try:
        await shutdown_music_call()
    except Exception:
        logger.exception("Music account shutdown failed")
    for task_key in ("moderation_expiry_task", "repetition_expiry_task", "blocked_words_expiry_task", "temporary_message_scheduler_task"):
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
    user = update.effective_user
    chat = update.effective_chat
    if user and chat and chat.type == "private":
        try:
            await get_pool().execute(
                """INSERT INTO developer_private_starts
                   (user_id, username, first_name)
                   VALUES($1, $2, $3)
                   ON CONFLICT(user_id) DO UPDATE SET
                       username=EXCLUDED.username,
                       first_name=EXCLUDED.first_name,
                       last_start_at=CURRENT_TIMESTAMP""",
                user.id,
                user.username or "",
                user.first_name or "",
            )
        except Exception:
            logger.exception("Failed to record private /start for mandatory subscription")
    if context.args and context.args[0].startswith("c4_"):
        game_id = context.args[0][3:]
        try:
            import uuid
            uuid.UUID(game_id)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
            game_url = f"https://nawaf-bot-frankfurt.onrender.com/mini-app?game_id={game_id}"
            await update.effective_message.reply_text(
                "تم تجهيز تحدي كونكت 4. افتح اللعبة من الزر بالأسفل.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "🔴 فتح لعبة كونكت 4",
                        web_app=WebAppInfo(url=game_url),
                    )
                ]]),
            )
        except Exception:
            await update.effective_message.reply_text("رابط لعبة كونكت 4 غير صالح.")
        return
    if context.args and context.args[0].lower() == "help":
        await commands_menu_start(update, context)
        return
    if context.args and context.args[0].lower() == "games":
        if update.effective_message:
            await update.effective_message.reply_text(
                "<b>اختر اللعبة الي تبيها 👇🏻</b>",
                parse_mode="HTML",
                reply_markup=games_keyboard(),
            )
        return
    await start(update, context)


async def track_developer_bot_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    member_update = update.my_chat_member
    if not member_update:
        return
    chat = member_update.chat
    if not chat or chat.type not in ("group", "supergroup", "channel"):
        return
    active = member_update.new_chat_member.status not in ("left", "kicked")
    try:
        await get_pool().execute(
            """INSERT INTO developer_bot_chats
               (chat_id, chat_type, title, username, active)
               VALUES($1, $2, $3, $4, $5)
               ON CONFLICT(chat_id) DO UPDATE SET
                   chat_type=EXCLUDED.chat_type,
                   title=EXCLUDED.title,
                   username=EXCLUDED.username,
                   active=EXCLUDED.active,
                   updated_at=CURRENT_TIMESTAMP""",
            chat.id, chat.type, chat.title or "", chat.username or "",
            1 if active else 0,
        )
    except Exception:
        logger.exception("Failed to track bot chat %s", chat.id)


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



async def delete_slash_command_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete slash-command messages without preventing their command handlers from running."""
    message = update.effective_message
    if message is None:
        return
    try:
        await message.delete()
    except Exception:
        # Telegram may reject deletion when the bot lacks permission or in unsupported chats.
        logger.debug("Could not delete slash command message", exc_info=True)


def instrument_telegram_requests() -> None:
    """Measure HTTPXRequest calls by wrapping the class method, which is read-only per instance."""
    from telegram.request import HTTPXRequest

    original_do_request = HTTPXRequest.do_request
    if getattr(original_do_request, "_telegram_perf_instrumented", False):
        return

    async def timed_do_request(self, url, method, request_data=None, **kwargs):
        started = asyncio.get_running_loop().time()
        endpoint = str(url).rsplit("/", 1)[-1].split("?", 1)[0]
        try:
            result = await original_do_request(self, url, method, request_data, **kwargs)
            status_code = result[0] if isinstance(result, tuple) and result else "unknown"
            elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
            logger.info(
                "PERF telegram.api_request endpoint=%s method=%s status=%s duration_ms=%.1f",
                endpoint, method, status_code, elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = (asyncio.get_running_loop().time() - started) * 1000
            logger.warning(
                "PERF telegram.api_request endpoint=%s method=%s error=%s duration_ms=%.1f",
                endpoint, method, type(exc).__name__, elapsed_ms,
            )
            raise

    timed_do_request._telegram_perf_instrumented = True
    HTTPXRequest.do_request = timed_do_request


def build_application(use_updater: bool = True) -> Application:
    settings = load_settings()
    builder = ApplicationBuilder().token(settings.bot_token)
    if not use_updater:
        builder = builder.updater(None)
    application = (
        builder
        # Keep Telegram's long-poll request alive longer than its 10s server wait.
        .get_updates_read_timeout(15)
        # Give regular Bot API calls room to complete during brief network jitter.
        .connect_timeout(10)
        # Negotiate HTTP/2 with Telegram where supported to reduce request overhead.
        .http_version("2")
        .read_timeout(15)
        .write_timeout(15)
        .pool_timeout(5)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(ChatSerialUpdateProcessor(max_concurrent_updates=16))
        .build()
    )
    # Instrument HTTPXRequest at class level; instance methods are read-only.
    instrument_telegram_requests()
    application.bot_data["settings"] = settings
    # Delete slash commands while allowing their normal handlers to execute in later groups.
    application.add_handler(InlineQueryHandler(online_games_inline_query), group=-100)
    application.add_handler(CallbackQueryHandler(online_lobby_callback, pattern=r"^online_(join|settings|config):"))
    application.add_handler(CallbackQueryHandler(online_image_select, pattern=r"^online_image:"))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^اضف صورة لعبة$"),
        online_image_add_start,
    ), group=-30)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.PHOTO,
        online_image_receive,
    ), group=-30)
    application.add_handler(MessageHandler(
        filters.COMMAND,
        delete_slash_command_message,
    ), group=-100)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO | filters.ANIMATION | filters.AUDIO | filters.VOICE | filters.VIDEO | filters.Document.ALL) & ~filters.COMMAND,
        mini_app_message,
    ), group=-31)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^صوت الفوز$"),
        game_end_sound_command,
    ), group=-30)
    application.add_handler(CallbackQueryHandler(
        game_end_sound_callback, pattern=r"^gamesound:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        game_end_sound_message,
    ), group=-29)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^(?:اوامر الميني|أوامر الميني|لوحة الميني)$"),
        mini_app_panel_command,
    ), group=-30)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^تعديل لون زر الميني$"),
        mini_app_color_command,
    ), group=-30)
    application.add_handler(CallbackQueryHandler(
        mini_app_panel_callback, pattern=r"^minipanel:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND, mini_app_panel_message,
    ), group=-30)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("send", send_command))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        music_message_handler,
    ), group=-1002)
    application.add_handler(CallbackQueryHandler(
        music_callback, pattern=r"^musicpick:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        youtube_audio_search,
    ), group=-1001)
    application.add_handler(CallbackQueryHandler(
        youtube_audio_callback, pattern=r"^ytpick:"
    ))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.VIDEO_CHAT_STARTED, voice_chat_started
    ))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.VIDEO_CHAT_ENDED, voice_chat_ended
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE,
        handle_send_media,
    ), group=-8)
    application.add_handler(ChatMemberHandler(
        track_developer_bot_chat, ChatMemberHandler.MY_CHAT_MEMBER
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^اوامر المطور$"),
        developer_panel_command,
    ), group=-9)
    application.add_handler(CallbackQueryHandler(
        developer_panel_callback, pattern=r"^devpanel:"
    ))
    application.add_handler(CallbackQueryHandler(stars_panel_callback, pattern=r"^stars:"))
    application.add_handler(PreCheckoutQueryHandler(stars_precheckout_handler))
    application.add_handler(MessageHandler(
        filters.SUCCESSFUL_PAYMENT, stars_successful_payment_handler,
    ), group=-10002)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^اشتراك القروب$"),
        stars_group_invoice_command,
    ), group=-10002)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS, stars_group_guard,
    ), group=-10000)
    application.add_handler(CallbackQueryHandler(
        stars_group_callback_guard,
    ), group=-10000)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND, stars_panel_message,
    ), group=-8)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        developer_panel_message,
    ), group=-9)
    application.add_handler(CommandHandler("starteditor", start_editor_command))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^تعديل ستارت$"),
        start_editor_command,
    ))
    application.add_handler(CallbackQueryHandler(
        start_editor_callback,
        pattern=r"^startedit:(?:menu|message|buttons|add_button|order_button|delete_button|access|image)$",    ))
    application.add_handler(CallbackQueryHandler(
        start_editor_special_callback,
        pattern=r"^startedit:(?:access_add|access_delete|image_add|image_delete|image_delete_all)$",
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        start_editor_message,
    ), group=-3)
    application.add_handler(build_add_command_conversation(), group=-2)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, delete_command
    ), group=-2)
    application.add_handler(MessageHandler(
        filters.Regex(r"^الاوامر المضافة$"), custom_commands_list
    ))
    application.add_handler(MessageHandler(
        filters.Regex(r"^مسح امر$"), delete_command_start
    ))
    application.add_handler(MessageHandler(
        filters.Regex(r"^مسح الاوامر المضافة$"), delete_all_commands
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, custom_command_alias_handler
    ), group=-7)
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(
            r"^/start(?:@\w+)?\s+whisper_[A-Za-z0-9_-]+$"
        ),
        whisper_start_handler,
    ), group=-5)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^(?:همسه|همسة|اهمس)$"),
        whisper_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^تفعيل الهمسات$"),
        enable_whispers_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^تعطيل الهمسات$"),
        disable_whispers_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.Regex(r"^الهمسات$"),
        whispers_list_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (
            filters.TEXT | filters.PHOTO | filters.ANIMATION | filters.Sticker.ALL
        ) & ~filters.COMMAND,
        whisper_private_message,
    ), group=-4)
    application.add_handler(CallbackQueryHandler(
        whisper_callbacks, pattern=r"^wh_"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^تعديل لون$"),
        change_button_color_start,
    ), group=-20)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        change_button_color_handler,
    ), group=-14)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS,
        mandatory_subscription_guard,
    ), group=-100)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        mandatory_subscription_commands,
    ), group=-90)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        emoji_reactions_handler,
    ), group=-1003)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        ai_assistant_message,
    ), group=-1000)
    # Recurring temporary messages.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(
            r"^(?:اضف رسالة مؤقتة|اضف رساله مؤقته|الرسائل المؤقتة|الرسائل المؤقته|"
            r"مسح الرس(?:الة|اله) المؤقت(?:ة|ه)(?:\s+\d+)?|"
            r"مسح الرسائل المؤقتة|مسح الرسائل المؤقته|ضع الرسالة\s+\d+)(?: عام)?$"
        ),
        temporary_message_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS, temporary_message_pending_handler
    ), group=-10)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS, track_temporary_message_chat
    ), group=-2)
    application.add_handler(CallbackQueryHandler(
        temporary_message_callback, pattern=r"^tmp:"
    ))


    # Blocked words: both lists, admin controls, and callback UI.
    application.add_handler(
        MessageHandler(filters.TEXT & (filters.ChatType.GROUPS | filters.ChatType.PRIVATE), blocked_words_message_handler),
        group=-20,
    )
    application.add_handler(CallbackQueryHandler(blocked_words_callback, pattern=r"^bw:"))

    # Repetition protection settings and message detector.
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, receive_repetition_duration), group=-16)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تفعيل التكرار$"), enable_repetition))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^تعطيل التكرار$"), disable_repetition))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع تكرار \d+$"), set_repetition_start))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع كتم تكرار \S+$"), set_mute_duration))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^ضع تقييد تكرار \S+$"), set_restrict_duration))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^(?:ضع|تغيير) رتبة التكرار (عضو|مميز|ادمن|ادمن اساسي|نائب المالك|المالك|Dev)$"), set_repetition_rank))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, repetition_message_handler), group=38)

    # Cache senders from group messages, including groups with hidden member lists.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS,
        track_observed_group_user,
    ), group=-1005)

    # Newf natural-language profile requests run before command guards.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        newf_profile_request,
    ), group=-1004)

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
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.Regex(r"^مسح(?:\s*\d+)?$"), delete_messages))
    application.add_handler(MessageHandler(filters.Regex(r"^ايدي(?:\s+@?[A-Za-z0-9_]+)?$"), user_id_command))

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
    application.add_handler(MessageHandler(filters.Regex(r"^تصفير المتفاعلين$"), reset_active_local_command))
    application.add_handler(MessageHandler(filters.Regex(r"^تصفير المتفاعلين عام$"), reset_active_global_command))
    application.add_handler(MessageHandler(filters.Regex(r"^تصفير النقاط$"), reset_points_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(?:رسايلي|رسائلي)$"), my_messages_command))
    application.add_handler(CallbackQueryHandler(stats_reset_callback, pattern=r"^statsreset:"))
    application.add_handler(MessageHandler(filters.Regex(r"^توب$"), top_menu_command))
    application.add_handler(CallbackQueryHandler(top_menu_callback, pattern=r"^topmenu:"))
    application.add_handler(MessageHandler(filters.Regex(r"^اضف(?:\s+\d+)?$"), add_points_command))
    application.add_handler(MessageHandler(filters.Regex(r"^خصم(?:\s+.*)?$"), remove_points_command))
    application.add_handler(MessageHandler(filters.Regex(r"^بيع نقاطي(?:\s+.*)?$"), sell_points))

    # Connect 4 player-vs-player challenges and wager callbacks.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^كونكت(?:\s+\d+)?$"),
        connect4_challenge_command,
    ))
    application.add_handler(CallbackQueryHandler(
        connect4_challenge_callback, pattern=r"^c4(?:a|d|r|x):"
    ))

    # Multiplayer Mini App games: Dots and Boxes and memory challenge.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^(?:مربعات|المربعات|ذاكرة|اختبر ذاكرتك)(?:\s+\d+)?$"),
        mini_game_challenge_command,
    ))
    application.add_handler(CallbackQueryHandler(
        mini_game_challenge_callback, pattern=r"^mg:"
    ))

    # Rock-paper-scissors challenge (same legacy commands and callbacks).
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^(?:حجرة(?: ورقة مقص)?|ورقة|مقص)(?:\s+\d+)?$"),
        start_rock_paper_scissors,
    ))
    application.add_handler(CallbackQueryHandler(
        rock_paper_scissors_callback, pattern=r"^rps:"
    ))

    # Demon Nawaf character guessing game.
    application.add_handler(MessageHandler(
        filters.Regex(r"^ديمون نواف$"),
        start_demon_nawaf,
    ))
    application.add_handler(CallbackQueryHandler(
        demon_nawaf_callback, pattern=r"^dn:"
    ))

    # Image quiz (same async implementation, shared join/start/continue/end routing).
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^توقع الصورة$"),
        start_image_quiz,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.اعدادات$"),
        image_quiz_settings,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^(?:اضف صور توقع|اضف صورة)$"),
        add_manual_image_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^(?:حذف صور توقع|حذف صورة)$"),
        delete_manual_image_command,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^الغاء اضافة صورة$"),
        cancel_manual_image,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^الغاء حذف صورة$"),
        cancel_delete_manual_image,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.PHOTO,
        receive_manual_image,
        ),
        group=11,
    )
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.PHOTO,        receive_delete_manual_image,
        ),
        group=12,
    )
    application.add_handler(CallbackQueryHandler(
        image_quiz_callback, pattern=r"^iq:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        check_image_quiz_message,
    ), group=8)

    # Fast text path for the custom question games. Run it immediately after
    # the mandatory-subscription guard instead of after the many general
    # group handlers, so game starts and answers are not delayed by them.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        game_message_handler,
    ), group=-99)

    # Keep photo-based question creation on its existing later path.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.PHOTO,
        game_message_handler,
    ), group=30)

    # Shared big games: classic liar, hide-and-seek, and penalties.
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^الكذاب$"),
        start_liar_game_lobby,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^بلنتيات$"),
        start_penalty_game,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^سباق الكلمات$"),
        start_word_race,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.الطور$"),
        word_race_mode,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.اضافة (?:احمر|ازرق|اخضر|اصفر)$"),
        word_race_manual_team,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.اضافة$"),
        add_big_game_player_router,
    ))
    application.add_handler(CallbackQueryHandler(
        word_race_callback, pattern=r"^wr:"
    ))
    application.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.PRIVATE)
        & filters.TEXT & ~filters.COMMAND,
        check_word_race_message,
    ), group=10)
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^غميضة$"),
        start_hide_game,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^دخول$"),
        join_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.خروج$"),
        leave_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.ابدا$"),
        begin_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.التصويت$"),
        force_voting,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.كمل$"),
        continue_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.انهاء$"),
        end_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.وزع$"),
        distribute_big_game_router,
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.(?:احمر|ازرق)(?:\s+\d+\*?)+$"),
        manual_team_command,
    ))
    application.add_handler(CallbackQueryHandler(
        liar_lobby_callback, pattern=r"^liar_lobby:"
    ))
    application.add_handler(CallbackQueryHandler(
        liar_vote_callback, pattern=r"^liar_vote:"
    ))
    application.add_handler(CallbackQueryHandler(
        liar_guess_callback, pattern=r"^liar_guess:"
    ))
    application.add_handler(CallbackQueryHandler(
        hide_number_callback, pattern=r"^hide:"
    ))
    application.add_handler(CallbackQueryHandler(
        search_number_callback, pattern=r"^search:"
    ))
    application.add_handler(CallbackQueryHandler(
        distribution_callback, pattern=r"^penalty:distribution:"
    ))
    application.add_handler(CallbackQueryHandler(
        penalty_direction_callback, pattern=r"^penalty:direction:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        penalty_direction_message,
    ), group=-98)
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
            check_liar_message,
        ),
        group=9,
    )

    # Help and interactive command menus.
    application.add_handler(CommandHandler("help", commands_menu_start))
    application.add_handler(MessageHandler(
        filters.Regex(r"^(?:الأوامر|الاوامر)$"),
        commands_menu_start,
    ))
    application.add_handler(CallbackQueryHandler(
        commands_menu_callback, pattern=r"^cmdmenu:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^\.لعبة$"),
        games_menu_command,
    ))
    application.add_handler(CallbackQueryHandler(
        games_menu_callback, pattern=r"^game_menu:"
    ))
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.Regex(r"^شرح الالعاب$"),
        games_help,
    ))

    # Bank and economy commands (legacy wording retained).
    application.add_handler(MessageHandler(filters.Regex(r"^انشاء حساب بنكي$"), create_bank_account))
    application.add_handler(MessageHandler(filters.Regex(r"^حسابي$"), my_bank_account))
    application.add_handler(MessageHandler(filters.Regex(r"^مسح حسابي$"), delete_bank_account))
    application.add_handler(MessageHandler(filters.Regex(r"^(راتب|راتبي)$"), salary))
    application.add_handler(MessageHandler(filters.Regex(r"^بخشيش$"), tip))
    application.add_handler(MessageHandler(filters.Regex(r"^استثمار(?: نقاطي|\s+\d+)?$"), invest))
    application.add_handler(MessageHandler(filters.Regex(r"^حظ(?: نقاطي|\s+\d+)?$"), luck))

    application.add_handler(MessageHandler(filters.Regex(r"^المتجر$"), store))
    application.add_handler(MessageHandler(filters.Regex(r"^ممتلكاتي$"), my_possessions))
    application.add_handler(MessageHandler(filters.Regex(r"^ممتلكاته$"), other_possessions))
    application.add_handler(MessageHandler(filters.Regex(r"^(شراء|بيع) \d+ \S+$"), buy_sell))
    application.add_handler(MessageHandler(filters.Regex(r"^اهداء \d+ \S+$"), gift))

    application.add_handler(MessageHandler(filters.Regex(r"^زرف$"), rob))
    application.add_handler(MessageHandler(filters.Regex(r"^تحويل \d+$"), transfer))
    application.add_handler(MessageHandler(filters.Regex(r"^\d{17}$"), transfer_account_number))
    application.add_handler(CallbackQueryHandler(transfer_message_callback, pattern=r"^tasliyat:transfer_message:"))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE, transfer_message_receiver), group=-6)
    application.add_handler(CallbackQueryHandler(bank_callback, pattern=r"^tasliyat:bank:"))

    application.add_handler(MessageHandler(filters.Regex(r"^عرض الاكواد$"), show_scratch_codes))
    application.add_handler(MessageHandler(filters.Regex(r"^كشط\s+[A-Za-z0-9]+$"), scratch_code))
    application.add_handler(MessageHandler(filters.Regex(r"^رست الكشط$"), reset_scratch_cooldown))
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, command_guard), group=-22)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_group_text_message), group=1)
    application.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER), group=-1)
    return application


if __name__ == "__main__":
    build_application().run_polling(allowed_updates=Update.ALL_TYPES)