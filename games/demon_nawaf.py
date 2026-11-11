"""Demon Nawaf — Akinator-backed game (no local character/question bank)."""
import asyncio
import html
import logging
import time

import akipy
import httpx
from akipy.async_akinator import Akinator
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

GAME_NAME = "ديمون نواف"
SESSION_TTL = 20 * 60
MAX_SESSIONS = 100
MAX_CONCURRENT_AKI_CALLS = 4
log = logging.getLogger(__name__)

TEXT = {
    "ar": {
        "intro": "بوو 👻\nأنا ديمون نواف! فكر بشخصية في بالك، وبحاول أعرفها من خلال أسئلتي.\n\nاختر لغة اللعبة:",
        "thinking": "خلني أفكر... 🧠",
        "busy": "اللعبة مشغولة حاليًا، حاول بعد قليل.",
        "expired": "انتهت صلاحية اللعبة. اكتب ديمون نواف لبدء لعبة جديدة.",
        "question": "السؤال {step} • نسبة التقدم {progress:.0f}%\n\n{question}",
        "guess": "أتوقع أن الشخصية اللي في بالك هي:\n\n<b>{name}</b>\n{description}\n\nهل هذا هو تخميني؟",
        "win": "كنت عارف! 👻✨\nالشخصية هي <b>{name}</b>!",
        "lost": "ما قدرت أوصل للشخصية هالمرة 😅\nجرّب مرة ثانية!",
        "error": "واجهت مشكلة في الاتصال بعاكيناتور. حاول تبدأ لعبة جديدة بعد قليل.",
        "stop": "تم إيقاف اللعبة. اكتب ديمون نواف للعب مرة ثانية.",
        "answers": ["ايه", "لا", "مدري", "يمكن", "يمكن لا"],
    },
    "en": {
        "intro": "Boo! 👻 Think of a character and I'll try to guess it.\n\nChoose your language:",
        "thinking": "Let me think... 🧠",
        "busy": "The game is busy right now. Please try again shortly.",
        "expired": "This game expired. Type Demon Nawaf to start a new game.",
        "question": "Question {step} • Progress {progress:.0f}%\n\n{question}",
        "guess": "I think your character is:\n\n<b>{name}</b>\n{description}\n\nIs that correct?",
        "win": "I knew it! 👻✨\nYour character was <b>{name}</b>!",
        "lost": "I couldn't guess your character this time. Try again!",
        "error": "Akinator connection failed. Please start a new game shortly.",
        "stop": "Game stopped. Type Demon Nawaf to play again.",
        "answers": ["Yes", "No", "Don't know", "Probably", "Probably not"],
    },
}

def _sessions(context):
    return context.application.bot_data.setdefault("demon_nawaf_sessions", {})

def _semaphore(context):
    return context.application.bot_data.setdefault(
        "demon_nawaf_semaphore", asyncio.Semaphore(MAX_CONCURRENT_AKI_CALLS)
    )

def _lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("العربية 🇸🇦", callback_data="dn:lang:ar")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="dn:lang:en")],
        [InlineKeyboardButton("إيقاف اللعبة", callback_data="dn:stop")],
    ])

def _answer_keyboard(lang, user_id):
    labels = TEXT[lang]["answers"]
    rows = [
        [InlineKeyboardButton(labels[0], callback_data=f"dn:a:{user_id}:0"),
         InlineKeyboardButton(labels[1], callback_data=f"dn:a:{user_id}:1")],
        [InlineKeyboardButton(labels[2], callback_data=f"dn:a:{user_id}:2")],
        [InlineKeyboardButton(labels[3], callback_data=f"dn:a:{user_id}:3"),
         InlineKeyboardButton(labels[4], callback_data=f"dn:a:{user_id}:4")],
        [InlineKeyboardButton("رجوع" if lang == "ar" else "Back", callback_data=f"dn:a:{user_id}:b"),
         InlineKeyboardButton("إيقاف اللعبة" if lang == "ar" else "Stop", callback_data=f"dn:stop:{user_id}")],
    ]
    return InlineKeyboardMarkup(rows)

def _guess_keyboard(lang, user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ايه، صح" if lang == "ar" else "Yes",
                              callback_data=f"dn:g:{user_id}:y")],
        [InlineKeyboardButton("لا، جرّب غيره" if lang == "ar" else "No, try again",
                              callback_data=f"dn:g:{user_id}:n")],
        [InlineKeyboardButton("إيقاف اللعبة" if lang == "ar" else "Stop",
                              callback_data=f"dn:stop:{user_id}")],
    ])

async def ensure_demon_tables():
    """Compatibility hook: Akinator now owns the character and question bank."""
    return None

async def _close_session(session):
    aki = session.get("aki")
    session["aki"] = None
    if aki is not None:
        try:
            await aki.close()
        except Exception:
            log.debug("Could not close Akinator client", exc_info=True)

async def _show_state(query, session, user_id):
    aki, lang = session["aki"], session["lang"]
    words = TEXT[lang]
    if aki.finished:
        if aki.win:
            body = words["win"].format(name=html.escape(str(aki.name_proposition or "؟")))
        else:
            body = words["lost"]
        await query.edit_message_text(body, parse_mode="HTML")
        return "finished"
    if aki.win:
        body = words["guess"].format(
            name=html.escape(str(aki.name_proposition or "؟")),
            description=html.escape(str(aki.description_proposition or "")),
        )
        await query.edit_message_text(
            body, parse_mode="HTML", reply_markup=_guess_keyboard(lang, user_id)
        )
        return "guess"
    try:
        progress = max(0.0, min(100.0, float(aki.progression or 0)))
        step = max(1, int(aki.step or 0) + 1)
    except (TypeError, ValueError):
        progress, step = 0.0, 1
    body = words["question"].format(
        step=step, progress=progress, question=html.escape(str(aki.question or "…"))
    )
    await query.edit_message_text(body, parse_mode="HTML",
                                  reply_markup=_answer_keyboard(lang, user_id))
    return "question"

async def start_demon_nawaf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user = update.effective_message, update.effective_user
    if not message or not user or message.chat.type not in (
        ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP
    ):
        return
    sessions = _sessions(context)
    old = sessions.pop(user.id, None)
    if old:
        await _close_session(old)
    if len(sessions) >= MAX_SESSIONS:
        await message.reply_text(TEXT["ar"]["busy"])
        return
    sessions[user.id] = {"aki": None, "lang": "ar", "state": "language",
                         "chat_id": message.chat_id, "created": time.monotonic(),
                         "lock": asyncio.Lock()}
    await message.reply_text(TEXT["ar"]["intro"], reply_markup=_lang_keyboard())

async def demon_nawaf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user or not query.message:
        return
    data = query.data or ""
    user_id = query.from_user.id
    parts = data.split(":")
    if parts[:2] == ["dn", "stop"]:
        target_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else user_id
        if target_id != user_id:
            await query.answer("هذه ليست لعبتك.", show_alert=True)
            return
        session = _sessions(context).pop(user_id, None)
        if session:
            await _close_session(session)
        await query.answer()
        await query.edit_message_text(TEXT[(session or {}).get("lang", "ar")]["stop"])
        return

    sessions = _sessions(context)
    session = sessions.get(user_id)
    if not session or time.monotonic() - session["created"] > SESSION_TTL:
        sessions.pop(user_id, None)
        await query.answer(TEXT["ar"]["expired"], show_alert=True)
        return

    # Buttons belong to the player who started this game, not other group members.
    if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) != user_id:
        await query.answer("هذه ليست لعبتك.", show_alert=True)
        return

    async with session["lock"]:
        if parts[:2] == ["dn", "lang"] and len(parts) == 3:
            lang = parts[2]
            if lang not in TEXT:
                await query.answer()
                return
            await query.answer(TEXT[lang]["thinking"])
            session["lang"] = lang
            try:
                async with _semaphore(context):
                    aki = Akinator()
                    aki.client = httpx.AsyncClient(
                        timeout=30,
                        limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
                    )
                    session["aki"] = aki
                    await aki.start_game(language=lang, child_mode=False, game_mode="c")
                session["state"] = "playing"
                await _show_state(query, session, user_id)
            except Exception as exc:
                log.warning("Akinator start failed: %s", type(exc).__name__)
                sessions.pop(user_id, None)
                await _close_session(session)
                await query.edit_message_text(TEXT[lang]["error"])
            return

        aki = session.get("aki")
        if aki is None:
            await query.answer(TEXT["ar"]["expired"], show_alert=True)
            return

        try:
            if parts[:2] == ["dn", "a"] and len(parts) == 4:
                choice = parts[3]
                if choice not in {"0", "1", "2", "3", "4", "b"}:
                    await query.answer()
                    return
                await query.answer()
                async with _semaphore(context):
                    if choice == "b":
                        await aki.back()
                    else:
                        await aki.answer(choice)
                await _show_state(query, session, user_id)
                return

            if parts[:2] == ["dn", "g"] and len(parts) == 4:
                choice = parts[3]
                if choice not in {"y", "n"} or not aki.win:
                    await query.answer()
                    return
                await query.answer()
                async with _semaphore(context):
                    if choice == "y":
                        await aki.choose()
                    else:
                        await aki.exclude()
                state = await _show_state(query, session, user_id)
                if state == "finished":
                    sessions.pop(user_id, None)
                    await _close_session(session)
                return
        except Exception as exc:
            log.warning("Akinator action failed: %s", type(exc).__name__)
            sessions.pop(user_id, None)
            await _close_session(session)
            try:
                await query.edit_message_text(TEXT[session["lang"]]["error"])
            except TelegramError:
                pass
            return
        await query.answer()

async def demon_nawaf_private_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Optional /start deep-link entry point: /start demon_nawaf."""
    if context.args and context.args[0] == "demon_nawaf":
        await start_demon_nawaf(update, context)
        raise ApplicationHandlerStop
