import asyncio
import io
import json
import os
import random
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, List

from PIL import Image

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import ContextTypes


# =========================================================
# الإعدادات
# =========================================================

GAME_NAME = "توقع الصورة"

MIN_PLAYERS = 2

MIN_TARGET_POINTS = 5
MAX_TARGET_POINTS = 15

# نقاط البوت الأصلية حسب سرعة الإجابة
ROUND_FIRST_REWARD = 60
ROUND_SECOND_REWARD = 45
ROUND_THIRD_REWARD = 30
ROUND_FINAL_REWARD = 15

REVEAL_INTERVAL = 20
FINAL_GUESS_SECONDS = 5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions.json")


from database.roles import get_rank_level
from database.points import add_points
from database.image_quiz import (
    load_manual_images,
    add_manual_image,
    delete_manual_image,
    get_manual_images_count,
)


# =========================================================
# بيانات اللاعب
# =========================================================

@dataclass
class ImagePlayer:
    user_id: int
    name: str

    game_points: int = 0
    original_points: int = 0


# =========================================================
# حالة اللعبة
# =========================================================

@dataclass
class ImageQuizState:
    chat_id: int

    host_id: int
    host_name: str

    players: Dict[int, ImagePlayer] = field(default_factory=dict)

    eliminated_players: Set[int] = field(default_factory=set)

    target_points: Optional[int] = None

    started: bool = False
    finished: bool = False

    current_round: int = 0

    current_question: Optional[dict] = None

    board_message_id: Optional[int] = None
    image_message_id: Optional[int] = None
    result_message_id: Optional[int] = None

    waiting_continue: bool = False
    answer_locked: bool = False

    round_started_at: Optional[float] = None

    reveal_stage: int = 0

    final_guess_phase: bool = False

    round_task: Optional[asyncio.Task] = None

    used_question_ids: Set[str] = field(default_factory=set)


# =========================================================
# الألعاب النشطة
# =========================================================

IMAGE_QUIZZES: Dict[int, ImageQuizState] = {}


# =========================================================
# جلسات إضافة الصور
# =========================================================

# chat_id -> user_id
ADDING_IMAGE_USERS: Dict[int, int] = {}

# chat_id -> user_id
DELETING_IMAGE_USERS: Dict[int, int] = {}


# =========================================================
# الصلاحيات
# =========================================================

async def _get_rank_level(user_id: int, chat_id: int) -> int:
    return await get_rank_level(user_id, chat_id)


async def _is_admin(user_id: int, chat_id: int) -> bool:
    return await _get_rank_level(user_id, chat_id) >= 2


# =========================================================
# التأكد من القروب
# =========================================================

async def _ensure_group(update: Update) -> bool:
    chat = update.effective_chat

    if not chat:
        return False

    if chat.type not in ("group", "supergroup"):
        if update.effective_message:
            await update.effective_message.reply_text(
                "❌ هذا الأمر يعمل داخل القروبات فقط."
            )
        return False

    return True


# =========================================================
# اسم اللاعب
# =========================================================

def _player_name(user) -> str:
    if user.first_name:
        return user.first_name

    if user.username:
        return f"@{user.username}"

    return str(user.id)


# =========================================================
# تنظيف الإجابات
# =========================================================

def _normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.strip().lower()

    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("ـ", "")

    text = re.sub(r"[^\w\s]", " ", text)

    text = re.sub(r"\s+", " ", text).strip()

    return text


# =========================================================
# استخراج إجابات السؤال
# =========================================================

def _question_answers(question: dict) -> List[str]:
    answers = []

    def add_answers(value):
        if isinstance(value, str):
            # كل سطر = إجابة مستقلة
            for line in value.splitlines():
                line = line.strip()

                if line:
                    answers.append(line)

        elif isinstance(value, list):
            for item in value:
                add_answers(item)

    # الإجابة الأساسية
    add_answers(question.get("answer"))

    # الإجابات البديلة
    add_answers(
        question.get(
            "alternative_answers",
            []
        )
    )

    result = []
    seen = set()

    for answer_text in answers:
        normalized = _normalize_text(
            answer_text
        )

        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result


# =========================================================
# تحميل الأسئلة الأصلية
# =========================================================

def load_questions() -> List[dict]:
    if not os.path.exists(QUESTIONS_FILE):
        return []

    try:
        with open(
            QUESTIONS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            questions = data.get("questions", [])

            if isinstance(questions, list):
                return questions

    except Exception as e:
        print(f"[IMAGE QUIZ] Error loading questions: {e}")

    return []


# =========================================================
# اختيار سؤال

# =========================================================

async def choose_question(
    state: ImageQuizState
) -> Optional[dict]:

    questions = load_questions()
    manual_images = await load_manual_images()

    all_questions = []

    # -----------------------------------------------------
    # الصور الأصلية
    # -----------------------------------------------------

    for index, question in enumerate(questions):

        if not isinstance(question, dict):
            continue

        question_copy = dict(question)

        question_id = str(
            question_copy.get(
                "id",
                f"question_{index}"
            )
        )

        question_copy["_quiz_source"] = "builtin"
        question_copy["_quiz_id"] = question_id

        all_questions.append(
            question_copy
        )

    # -----------------------------------------------------
    # الصور المضافة يدويًا
    # -----------------------------------------------------

    for index, image in enumerate(manual_images):

        if not isinstance(image, dict):
            continue

        file_id = image.get("file_id")

        if not file_id:
            continue

        answer = image.get("answer")

        if not isinstance(answer, str):
            continue

        question_id = str(
            image.get(
                "id",
                f"manual_{index}"
            )
        )

        question = {
            "id": question_id,
            "answer": answer,
            "alternative_answers": image.get(
                "alternative_answers",
                []
            ),
            "_quiz_source": "manual",
            "_quiz_id": question_id,
            "file_id": file_id
        }

        all_questions.append(question)

    if not all_questions:
        return None

    available = []

    for question in all_questions:
        question_id = str(
            question.get("_quiz_id", "")
        )

        if question_id not in state.used_question_ids:
            available.append(question)

    # إذا انتهت جميع الصور نعيد استخدامها
    if not available:
        state.used_question_ids.clear()
        available = all_questions.copy()

    if not available:
        return None

    question = random.choice(available)

    question_id = str(
        question.get("_quiz_id", "")
    )

    if question_id:
        state.used_question_ids.add(
            question_id
        )

    return question


# =========================================================
# مسار الصورة
# =========================================================

def _get_image_path(image_path: str) -> str:
    if not image_path:
        return ""

    image_path = str(image_path).strip()

    if not image_path:
        return ""

    # إذا كان المسار كاملًا
    if os.path.isabs(image_path):
        if os.path.exists(image_path):
            return image_path

    # الأماكن المحتملة للصورة
    possible_paths = [
        image_path,

        os.path.join(
            BASE_DIR,
            image_path
        ),

        os.path.join(
            BASE_DIR,
            "images",
            image_path
        ),

        os.path.join(
            BASE_DIR,
            "animals",
            image_path
        ),

        os.path.join(
            BASE_DIR,
            "..",
            image_path
        ),

        os.path.join(
            BASE_DIR,
            "..",
            "..",
            image_path
        ),
    ]

    for path in possible_paths:
        path = os.path.abspath(path)

        if os.path.isfile(path):
            return path

    # نرجع المسار الأساسي حتى تظهر رسالة الخطأ
    # بدل ما يحصل خطأ غير واضح
    return os.path.abspath(
        os.path.join(
            BASE_DIR,
            image_path
        )
    )


# =========================================================
# قص الصورة من PIL
# =========================================================

def _crop_image_object(
    image: Image.Image,
    stage: int
) -> Optional[io.BytesIO]:

    try:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")

        if image.mode == "RGBA":
            background = Image.new(
                "RGB",
                image.size,
                "white"
            )

            background.paste(
                image,
                mask=image.getchannel("A")
            )

            image = background

        else:
            image = image.convert("RGB")

        width, height = image.size

        crop_ratios = {
            0: 0.30,
            1: 0.52,
            2: 0.72,
            3: 1.00,
        }

        ratio = crop_ratios.get(
            stage,
            1.00
        )

        if ratio < 1.0:
            crop_width = int(
                width * ratio
            )

            crop_height = int(
                height * ratio
            )

            left = max(
                0,
                (width - crop_width) // 2
            )

            top = max(
                0,
                (height - crop_height) // 2
            )

            right = min(
                width,
                left + crop_width
            )

            bottom = min(
                height,
                top + crop_height
            )

            image = image.crop(
                (
                    left,
                    top,
                    right,
                    bottom
                )
            )

        image.thumbnail(
            (1280, 1280),
            Image.Resampling.LANCZOS
        )

        output = io.BytesIO()

        image.save(
            output,
            format="JPEG",
            quality=92,
            optimize=True
        )

        output.seek(0)

        return output

    except Exception as e:
        print(
            f"[IMAGE QUIZ] Image processing error: {e}"
        )

        return None


# =========================================================
# قص الصورة من ملف محلي
# =========================================================

def _crop_zoom_image(
    image_path: str,
    stage: int
) -> Optional[io.BytesIO]:

    if not os.path.exists(image_path):
        return None

    try:
        image = Image.open(
            image_path
        )

        return _crop_image_object(
            image,
            stage
        )

    except Exception as e:
        print(
            f"[IMAGE QUIZ] Image processing error: {e}"
        )

        return None


# =========================================================
# تحميل صورة Telegram المضافة يدويًا
# =========================================================

async def _download_telegram_image(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str
) -> Optional[bytes]:

    try:
        telegram_file = await context.bot.get_file(
            file_id
        )

        output = io.BytesIO()

        await telegram_file.download_to_memory(
            output
        )

        return output.getvalue()

    except Exception as e:
        print(
            f"[IMAGE QUIZ] Failed downloading Telegram image: {e}"
        )

        return None


# =========================================================
# تجهيز صورة السؤال
# =========================================================

async def _get_question_image(
    context: ContextTypes.DEFAULT_TYPE,
    question: dict,
    stage: int
) -> Optional[io.BytesIO]:

    if not question:
        return None

    # -----------------------------------------------------
    # صورة مضافة يدويًا من Telegram
    # -----------------------------------------------------

    file_id = question.get("file_id")

    if file_id:

        cached_data = question.get(
            "_cached_image_bytes"
        )

        if cached_data:
            try:
                image = Image.open(
                    io.BytesIO(cached_data)
                )

                return _crop_image_object(
                    image,
                    stage
                )

            except Exception:
                question.pop(
                    "_cached_image_bytes",
                    None
                )

        image_bytes = await _download_telegram_image(
            context,
            file_id
        )

        if not image_bytes:
            print(
                "[IMAGE QUIZ] تعذر تحميل الصورة اليدوية."
            )

            return None

        question["_cached_image_bytes"] = (
            image_bytes
        )

        try:
            image = Image.open(
                io.BytesIO(image_bytes)
            )

            return _crop_image_object(
                image,
                stage
            )

        except Exception as e:
            print(
                f"[IMAGE QUIZ] Failed opening Telegram image: {e}"
            )

            return None

    # -----------------------------------------------------
    # صورة أصلية من questions.json
    # -----------------------------------------------------

    image_path = (
        question.get("image")
        or question.get("image_path")
        or question.get("path")
    )

    if not image_path:
        print(
            "[IMAGE QUIZ] السؤال لا يحتوي على مسار صورة:"
            f" {question.get('_quiz_id')}"
        )

        return None

    image_path = _get_image_path(
        image_path
    )

    if not os.path.isfile(image_path):
        print(
            "[IMAGE QUIZ] الصورة غير موجودة:"
            f" {image_path}"
        )

        return None

    return _crop_zoom_image(
        image_path,
        stage
    )


# =========================================================
# نص مرحلة الصورة
# =========================================================

def _stage_text(
    state: ImageQuizState
) -> str:

    if state.reveal_stage == 0:
        return "🔎 الصورة مخفية بشكل كبير"

    if state.reveal_stage == 1:
        return "👀 بدأت الصورة تتضح"

    if state.reveal_stage == 2:
        return "👁️ الصورة أصبحت أوضح"

    return "🖼️ الصورة كاملة"


# =========================================================
# إرسال / تعديل الصورة
# =========================================================

async def _send_or_edit_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    if not state.current_question:
        return

    image_data = await _get_question_image(
        context,
        state.current_question,
        state.reveal_stage
    )

    if image_data is None:
        await context.bot.send_message(
            chat_id=state.chat_id,
            text="❌ تعذر تحميل صورة الجولة."
        )

        return

    if state.reveal_stage == 0:
        elapsed_text = "⏱️ الوقت: 0 - 20 ثانية"

    elif state.reveal_stage == 1:
        elapsed_text = "⏱️ الوقت: 20 - 40 ثانية"

    elif state.reveal_stage == 2:
        elapsed_text = "⏱️ الوقت: 40 - 60 ثانية"

    else:
        elapsed_text = "⏱️ آخر 5 ثواني"

    caption = (
        f"🖼️ *الجولة {state.current_round}*\n\n"
        f"{_stage_text(state)}\n"
        f"{elapsed_text}\n\n"
        f"🎯 كل إجابة صحيحة = +1 نقطة"
    )

    if state.image_message_id:

        try:
            media = InputMediaPhoto(
                media=image_data,
                caption=caption,
                parse_mode="Markdown"
            )

            await context.bot.edit_message_media(
                chat_id=state.chat_id,
                message_id=state.image_message_id,
                media=media
            )

            return

        except Exception as e:
            print(
                f"[IMAGE QUIZ] Failed to edit image: {e}"
            )

    message = await context.bot.send_photo(
        chat_id=state.chat_id,
        photo=image_data,
        caption=caption,
        parse_mode="Markdown"
    )

    state.image_message_id = message.message_id


# =========================================================
# لوحة اللاعبين
# =========================================================

async def _update_board(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    if not state.board_message_id:
        return

    players = list(
        state.players.values()
    )

    players.sort(
        key=lambda p: (
            p.game_points,
            p.original_points
        ),
        reverse=True
    )

    lines = [
        "🖼️ *توقع الصورة*",
        ""
    ]

    if state.target_points:
        lines.append(
            f"🎯 الهدف: *{state.target_points} نقاط*"
        )

        lines.append("")

    if not players:
        lines.append(
            "👥 لا يوجد لاعبين."
        )

    else:
        for index, player in enumerate(
            players,
            start=1
        ):
            lines.append(
                f"{index}. {player.name} — "
                f"*{player.game_points}* نقطة"
            )

    lines.append("")

    if not state.started:
        lines.append(
            "⏳ بانتظار بدء القيم…"
        )

    elif state.waiting_continue:
        lines.append(
            "⏸️ الجولة انتهت.\n"
            "الأدمن يكتب `.كمل` للجولة التالية."
        )

    elif state.final_guess_phase:
        lines.append(
            "⏰ الصورة كاملة!\n"
            "لديكم 5 ثوانٍ للإجابة."
        )

    else:
        lines.append(
            "🎮 الجولة جارية…"
        )

    try:
        await context.bot.edit_message_text(
            chat_id=state.chat_id,
            message_id=state.board_message_id,
            text="\n".join(lines),
            parse_mode="Markdown"
        )

    except Exception:
        pass


# =========================================================
# بدء الجولة
# =========================================================

async def start_round(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    if state.finished:
        return

    if len(state.players) < MIN_PLAYERS:

        state.waiting_continue = True

        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(
                "❌ لا يمكن بدء الجولة.\n"
                f"يجب أن يكون عدد اللاعبين "
                f"{MIN_PLAYERS} على الأقل."
            )
        )

        return

    question = await choose_question(
        state
    )

    if not question:

        state.waiting_continue = True

        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(
                "❌ لا توجد صور في مكتبة توقع الصورة.\n\n"
                "تأكد من وجود `questions.json` "
                "أو أضف صورًا باستخدام `اضف صور توقع`."
            ),
            parse_mode="Markdown"
        )

        return

    state.current_question = question
    state.current_round += 1

    state.answer_locked = False
    state.waiting_continue = False

    state.round_started_at = (
        asyncio.get_running_loop().time()
    )

    state.reveal_stage = 0
    state.final_guess_phase = False

    await _update_board(
        context,
        state
    )

    image_data = await _get_question_image(
        context,
        question,
        0
    )

    if image_data:

        caption = (
            f"🖼️ *الجولة {state.current_round}*\n\n"
            "🔎 الصورة مخفية بشكل كبير\n"
            "⏱️ الوقت: 0 - 20 ثانية\n\n"
            "🎯 كل إجابة صحيحة = +1 نقطة"
        )

        try:
            message = await context.bot.send_photo(
                chat_id=state.chat_id,
                photo=image_data,
                caption=caption,
                parse_mode="Markdown"
            )

            state.image_message_id = (
                message.message_id
            )

        except Exception as e:
            print(
                f"[IMAGE QUIZ] Failed sending first image: {e}"
            )

    await context.bot.send_message(
        chat_id=state.chat_id,
        text=(
            f"🎮 *الجولة {state.current_round} بدأت!*\n\n"
            "🖼️ حاول معرفة الصورة.\n"
            "⚡ كل إجابة صحيحة = +1 نقطة في القيم.\n\n"
            "💰 نقاط البوت الأصلية:\n"
            "• 0 - 20 ثانية: +60\n"
            "• 20 - 40 ثانية: +45\n"
            "• 40 - 60 ثانية: +30\n"
            "• آخر 5 ثواني: +15"
        ),
        parse_mode="Markdown"
    )

    if state.round_task and not state.round_task.done():

        state.round_task.cancel()

    state.round_task = context.application.create_task(
        run_round_timer(context, state),
        name=f"image-quiz-round-{state.chat_id}-{state.current_round}",
    )


# =========================================================
# مؤقت الجولة
# =========================================================

async def run_round_timer(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    try:

        await asyncio.sleep(20)

        if state.finished or state.answer_locked:
            return

        state.reveal_stage = 1

        await _update_round_image(
            context,
            state
        )

        await asyncio.sleep(20)

        if state.finished or state.answer_locked:
            return

        state.reveal_stage = 2

        await _update_round_image(
            context,
            state
        )

        await asyncio.sleep(20)

        if state.finished or state.answer_locked:
            return

        state.reveal_stage = 3
        state.final_guess_phase = True

        await _update_round_image(
            context,
            state
        )

        await _update_board(
            context,
            state
        )

        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(
                "⏰ *انتهت الـ60 ثانية!*\n\n"
                "🖼️ الصورة كاملة الآن.\n"
                "⚡ أمامكم *5 ثوانٍ* للإجابة.\n"
                "🎯 الإجابة الصحيحة الآن = +1 نقطة\n"
                "💰 وتحصل على +15 نقطة أصلية."
            ),
            parse_mode="Markdown"
        )

        await asyncio.sleep(
            FINAL_GUESS_SECONDS
        )

        if state.finished or state.answer_locked:
            return

        await finish_round_without_answer(
            context,
            state
        )

    except asyncio.CancelledError:
        return

    except Exception as e:
        print(
            f"[IMAGE QUIZ] Timer error: {e}"
        )


# =========================================================
# تحديث صورة الجولة
# =========================================================

async def _update_round_image(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    if not state.current_question:
        return

    image_data = await _get_question_image(
        context,
        state.current_question,
        state.reveal_stage
    )

    if image_data is None:
        return

    if state.reveal_stage == 1:

        caption = (
            f"🖼️ *الجولة {state.current_round}*\n\n"
            "👀 الصورة أصبحت أوضح\n"
            "⏱️ 20 - 40 ثانية\n\n"
            "🎯 كل إجابة صحيحة = +1 نقطة"
        )

    elif state.reveal_stage == 2:

        caption = (
            f"🖼️ *الجولة {state.current_round}*\n\n"
            "👁️ الصورة أصبحت أوضح أكثر\n"
            "⏱️ 40 - 60 ثانية\n\n"
            "🎯 كل إجابة صحيحة = +1 نقطة"
        )

    else:

        caption = (
            f"🖼️ *الجولة {state.current_round}*\n\n"
            "🖼️ الصورة كاملة\n"
            "⏰ آخر 5 ثواني!\n\n"
            "🎯 كل إجابة صحيحة = +1 نقطة\n"
            "💰 المكافأة الأصلية: +15"
        )

    try:

        if state.image_message_id:

            media = InputMediaPhoto(
                media=image_data,
                caption=caption,
                parse_mode="Markdown"
            )

            await context.bot.edit_message_media(
                chat_id=state.chat_id,
                message_id=state.image_message_id,
                media=media
            )

        else:

            message = await context.bot.send_photo(
                chat_id=state.chat_id,
                photo=image_data,
                caption=caption,
                parse_mode="Markdown"
            )

            state.image_message_id = (
                message.message_id
            )

    except Exception as e:
        print(
            f"[IMAGE QUIZ] Failed updating image: {e}"
        )


# =========================================================
# نهاية الجولة بدون إجابة
# =========================================================

async def finish_round_without_answer(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState
):

    state.answer_locked = True
    state.final_guess_phase = False
    state.waiting_continue = True

    if state.round_task:

        current_task = asyncio.current_task()

        if state.round_task != current_task:

            try:
                state.round_task.cancel()
            except Exception:
                pass

    question = state.current_question

    answer = "غير معروف"

    if question:
        answer = question.get(
            "answer",
            "غير معروف"
        )

    await context.bot.send_message(
        chat_id=state.chat_id,
        text=(
            f"⏱️ *انتهت الجولة "
            f"{state.current_round}!*\n\n"
            "❌ لم يجب أحد بشكل صحيح.\n\n"
            f"✅ الإجابة: *{answer}*\n\n"
            "⏸️ الأدمن يكتب `.كمل` للجولة التالية."
        ),
        parse_mode="Markdown"
    )

    await _update_board(
        context,
        state
    )


# =========================================================
# إضافة نقاط البوت الأصلية
# =========================================================

async def _give_original_points(user_id: int, points: int):
    if points > 0:
        try:
            await add_points(user_id, points)
        except Exception as exc:
            print(f"[IMAGE QUIZ] Failed adding points: {exc}")


# =========================================================
# حساب مكافأة الإجابة
# =========================================================

def _get_original_reward(
    elapsed: float
) -> int:

    if elapsed < 20:
        return ROUND_FIRST_REWARD

    if elapsed < 40:
        return ROUND_SECOND_REWARD

    if elapsed < 60:
        return ROUND_THIRD_REWARD

    return ROUND_FINAL_REWARD


# =========================================================
# فحص إجابة اللاعب
# =========================================================

async def check_image_quiz_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not state.started:
        return

    if state.finished:
        return

    if state.answer_locked:
        return

    if user.id not in state.players:
        return

    if not message.text:
        return

    text = message.text.strip()

    ignored_commands = {
        "دخول",
        "خروج",
        ".اضافة",
        ".اعدادات",
        ".ابدا",
        ".كمل",
        ".انهاء",
        "توقع الصورة",
        "اضف صور توقع",
        "حذف صور توقع",
    }

    if text in ignored_commands:
        return

    normalized_text = _normalize_text(
        text
    )

    if not normalized_text:
        return

    if not state.current_question:
        return

    correct_answers = _question_answers(
        state.current_question
    )

    if normalized_text not in correct_answers:
        return

    state.answer_locked = True
    state.final_guess_phase = False

    if state.round_task:

        try:
            state.round_task.cancel()
        except Exception:
            pass

    now = asyncio.get_running_loop().time()

    if state.round_started_at:
        elapsed = (
            now - state.round_started_at
        )
    else:
        elapsed = 0

    reward = _get_original_reward(
        elapsed
    )

    player = state.players.get(
        user.id
    )

    if not player:

        state.answer_locked = False
        return

    player.game_points += 1
    player.original_points += reward

    answer = state.current_question.get(
        "answer",
        text
    )

    target_reached = (
        state.target_points is not None
        and player.game_points >= state.target_points
    )

    if target_reached:

        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"🎉 *إجابة صحيحة!*\n\n"
                f"👤 اللاعب: *{player.name}*\n"
                f"✅ الإجابة: *{answer}*\n\n"
                f"🎯 +1 نقطة في القيم\n"
                f"💰 +{reward} نقطة أصلية\n\n"
                f"🏆 وصل إلى الهدف "
                f"*{state.target_points} نقاط*!"
            ),
            parse_mode="Markdown"
        )

        await finish_image_quiz(
            context,
            state,
            winner_id=user.id
        )

        return

    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            f"🎯 *إجابة صحيحة!*\n\n"
            f"👤 {player.name}\n"
            f"✅ {answer}\n\n"
            f"🏅 +1 نقطة في القيم\n"
            f"💰 +{reward} نقطة أصلية\n\n"
            f"📊 نقاطه الآن: *{player.game_points}*"
        ),
        parse_mode="Markdown"
    )

    state.waiting_continue = True

    await _update_board(
        context,
        state
    )

    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            "⏸️ انتهت الجولة.\n"
            "الأدمن يكتب `.كمل` للجولة التالية."
        )
    )


# =========================================================
# بدء إضافة صورة يدويًا
# =========================================================

async def add_manual_image_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    ADDING_IMAGE_USERS[
        chat.id
    ] = user.id

    # إذا كان فيه حذف سابق نوقفه
    DELETING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    count = await get_manual_images_count()

    await message.reply_text(
        (
            "🖼️ *إضافة صورة لتوقع الصورة*\n\n"
            "أرسل الآن الصورة التي تريد إضافتها.\n"
            "✏️ واكتب *إجابة الصورة في الكابشن*.\n\n"
            "مثال:\n"
            "ترسل صورة أسد وتكتب في الكابشن:\n"
            "`أسد`\n\n"
            "`الاسد`\n"
            f"📸 الصور المضافة حاليًا: *{count}*\n\n"
            "يمكنك إلغاء العملية بكتابة:\n"
            "`الغاء اضافة صورة`"
        ),
        parse_mode="Markdown"
    )


# =========================================================
# استقبال الصورة المضافة يدويًا
# =========================================================

async def receive_manual_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    expected_user = ADDING_IMAGE_USERS.get(
        chat.id
    )

    if expected_user != user.id:
        return

    if not await _is_admin(user.id, chat.id):

        ADDING_IMAGE_USERS.pop(
            chat.id,
            None
        )

        return

    photo = message.photo

    if not photo:
        return

    answer = (
        message.caption
        or ""
    ).strip()

    if not answer:

        await message.reply_text(
            (
                "❌ لازم تكتب إجابة الصورة في الكابشن.\n\n"
                "أرسل الصورة مرة ثانية، "
                "واكتب الإجابة في الكابشن."
            )
        )

        return

    file_id = photo[-1].file_id

    success = await add_manual_image(
        file_id,
        answer
    )

    if not success:

        await message.reply_text(
            "⚠️ هذه الصورة موجودة مسبقًا أو تعذر حفظها."
        )

        ADDING_IMAGE_USERS.pop(
            chat.id,
            None
        )

        return

    ADDING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    count = await get_manual_images_count()

    await message.reply_text(
        (
            "✅ *تمت إضافة الصورة بنجاح!*\n\n"
            f"📝 الإجابة: *{answer}*\n"
            f"📸 إجمالي الصور المضافة يدويًا: *{count}*\n\n"
            "🎲 ستدخل الصورة الآن مع باقي صور "
            "توقع الصورة بشكل عشوائي."
        ),
        parse_mode="Markdown"
    )


# =========================================================
# إلغاء إضافة صورة
# =========================================================

async def cancel_manual_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    expected_user = ADDING_IMAGE_USERS.get(
        chat.id
    )

    if expected_user != user.id:
        return

    ADDING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    await message.reply_text(
        "✅ تم إلغاء إضافة الصورة."
    )


# =========================================================
# بدء حذف صورة يدويًا
# =========================================================

async def delete_manual_image_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    count = await get_manual_images_count()

    if count <= 0:

        await message.reply_text(
            "❌ لا توجد صور مضافة يدويًا."
        )

        return

    DELETING_IMAGE_USERS[
        chat.id
    ] = user.id

    ADDING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    await message.reply_text(
        (
            "🗑️ *حذف صورة من توقع الصورة*\n\n"
            "أرسل الآن الصورة التي تريد حذفها.\n\n"
            "⚠️ يجب إرسال نفس الصورة التي سبق إضافتها.\n\n"
            "لإلغاء العملية اكتب:\n"
            "`الغاء حذف صورة`"
        ),
        parse_mode="Markdown"
    )


# =========================================================
# استقبال صورة الحذف
# =========================================================

async def receive_delete_manual_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    expected_user = DELETING_IMAGE_USERS.get(
        chat.id
    )

    if expected_user != user.id:
        return

    photo = message.photo

    if not photo:
        return

    file_id = photo[-1].file_id

    success = await delete_manual_image(
        file_id
    )

    DELETING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    if not success:

        await message.reply_text(
            "❌ لم أجد هذه الصورة ضمن الصور المضافة يدويًا."
        )

        return

    count = await get_manual_images_count()

    await message.reply_text(
        (
            "✅ *تم حذف الصورة بنجاح!*\n\n"
            f"📸 الصور المضافة يدويًا المتبقية: *{count}*"
        ),
        parse_mode="Markdown"
    )


# =========================================================
# إلغاء حذف صورة
# =========================================================

async def cancel_delete_manual_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if chat.type not in (
        "group",
        "supergroup"
    ):
        return

    expected_user = DELETING_IMAGE_USERS.get(
        chat.id
    )

    if expected_user != user.id:
        return

    DELETING_IMAGE_USERS.pop(
        chat.id,
        None
    )

    await message.reply_text(
        "✅ تم إلغاء حذف الصورة."
    )


# =========================================================
# بدء اللعبة
# =========================================================

async def start_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ لازم تكون أدمن لإنشاء لعبة توقع الصورة."
        )

        return

    from games.big_game_join import get_active_game
    active_game = get_active_game(chat.id)
    if active_game and active_game != "image":
        await message.reply_text(
            "⚠️ توجد لعبة أخرى قائمة بالفعل في هذا القروب."
        )
        return

    if chat.id in IMAGE_QUIZZES:

        await message.reply_text(
            "⚠️ توجد لعبة توقع الصورة بالفعل في هذا القروب."
        )

        return

    state = ImageQuizState(
        chat_id=chat.id,
        host_id=user.id,
        host_name=_player_name(user)
    )

    IMAGE_QUIZZES[
        chat.id
    ] = state

    keyboard = [
        [
            InlineKeyboardButton(
                "🎯 اختيار النقاط",
                callback_data="iq:settings"
            )
        ]
    ]

    board = await message.reply_text(
        (
            "🖼️ *توقع الصورة*\n\n"
            f"👑 المنظم: *{state.host_name}*\n\n"
            "👥 يجب دخول لاعبين على الأقل.\n"
            "🎯 حددوا نقاط الفوز من زر الإعدادات.\n\n"
            "اكتب `دخول` للانضمام."
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )

    state.board_message_id = (
        board.message_id
    )


# =========================================================
# دخول لاعب
# =========================================================

async def join_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if state.started:

        await message.reply_text(
            "❌ القيم بدأ بالفعل.\n"
            "إذا تبي تضيف شخص استخدم `.اضافة`."
        )

        return

    if user.id in state.players:

        await message.reply_text(
            "⚠️ أنت داخل القيم بالفعل."
        )

        return

    state.players[
        user.id
    ] = ImagePlayer(
        user_id=user.id,
        name=_player_name(user)
    )

    await message.reply_text(
        f"✅ تم دخول *{_player_name(user)}* للقيم.",
        parse_mode="Markdown"
    )

    await _update_board(
        context,
        state
    )


# =========================================================
# خروج لاعب
# =========================================================

async def leave_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    player = state.players.get(
        user.id
    )

    if not player:

        await message.reply_text(
            "❌ أنت لست داخل القيم."
        )

        return

    del state.players[
        user.id
    ]

    state.eliminated_players.add(
        user.id
    )

    await message.reply_text(
        f"🚪 خرج *{player.name}* من القيم.",
        parse_mode="Markdown"
    )

    if state.started and not state.waiting_continue:

        await _update_board(
            context,
            state
        )

        if len(state.players) < MIN_PLAYERS:

            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "⚠️ عدد اللاعبين أصبح أقل من "
                    f"{MIN_PLAYERS}.\n"
                    "يمكن للقيم الاستمرار، لكن يجب إضافة لاعب "
                    "بـ`.اضافة` قبل بدء الجولة التالية."
                )
            )

    else:

        await _update_board(
            context,
            state
        )


# =========================================================
# إضافة لاعب بواسطة الأدمن
# =========================================================

async def add_image_quiz_player(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    if not message.reply_to_message:

        await message.reply_text(
            "❌ رد على رسالة الشخص الذي تريد إضافته واكتب:\n"
            "`.اضافة`"
        )

        return

    target = (
        message.reply_to_message.from_user
    )

    if not target:

        await message.reply_text(
            "❌ لم أستطع معرفة الشخص."
        )

        return

    if target.is_bot:

        await message.reply_text(
            "❌ لا يمكنك إضافة بوت."
        )

        return

    if target.id in state.players:

        await message.reply_text(
            "⚠️ الشخص داخل القيم بالفعل."
        )

        return

    state.eliminated_players.discard(
        target.id
    )

    state.players[
        target.id
    ] = ImagePlayer(
        user_id=target.id,
        name=_player_name(target)
    )

    await message.reply_text(
        f"✅ تمت إضافة *{_player_name(target)}* إلى القيم.",
        parse_mode="Markdown"
    )

    await _update_board(
        context,
        state
    )


# =========================================================
# إعدادات اللعبة
# =========================================================

async def image_quiz_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    if state.started:

        await message.reply_text(
            "❌ لا يمكن تغيير الإعدادات بعد بدء القيم."
        )

        return

    keyboard = []
    row = []

    for points in range(
        MIN_TARGET_POINTS,
        MAX_TARGET_POINTS + 1
    ):

        row.append(
            InlineKeyboardButton(
                f"{points} 🎯",
                callback_data=f"iq:points:{points}"
            )
        )

        if len(row) == 4:

            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    await message.reply_text(
        (
            "⚙️ *إعدادات توقع الصورة*\n\n"
            "🎯 اختر عدد النقاط المطلوبة للفوز:"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# بدء القيم
# =========================================================

async def begin_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    if state.started:

        await message.reply_text(
            "⚠️ القيم بدأ بالفعل."
        )

        return

    if state.target_points is None:

        await message.reply_text(
            "❌ حدد نقاط الفوز أولًا باستخدام `.اعدادات`."
        )

        return

    if len(state.players) < MIN_PLAYERS:

        await message.reply_text(
            f"❌ يجب دخول {MIN_PLAYERS} لاعبين على الأقل."
        )

        return

    state.started = True
    state.finished = False

    await message.reply_text(
        (
            "🚀 *تم بدء القيم!*\n\n"
            f"🎯 الهدف: *{state.target_points} نقاط*\n"
            f"👥 اللاعبين: *{len(state.players)}*"
        ),
        parse_mode="Markdown"
    )

    await start_round(
        context,
        state
    )


# =========================================================
# الجولة التالية
# =========================================================

async def continue_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    if not state.started:

        await message.reply_text(
            "❌ القيم لم يبدأ بعد."
        )

        return

    if state.finished:
        return

    if not state.waiting_continue:

        await message.reply_text(
            "⚠️ الجولة الحالية لم تنتهِ بعد."
        )

        return

    if len(state.players) < MIN_PLAYERS:

        await message.reply_text(
            (
                f"❌ لا يمكن بدء الجولة التالية.\n"
                f"يجب أن يكون هناك {MIN_PLAYERS} لاعبين على الأقل.\n\n"
                "يمكن للأدمن إضافة لاعب باستخدام `.اضافة`."
            )
        )

        return

    await start_round(
        context,
        state
    )


# =========================================================
# إنهاء اللعبة
# =========================================================

async def end_image_quiz(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not await _ensure_group(update):
        return

    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:
        return

    if not await _is_admin(user.id, chat.id):

        await message.reply_text(
            "❌ هذا الأمر للأدمن فقط."
        )

        return

    await finish_image_quiz(
        context,
        state,
        winner_id=None,
        manual=True
    )


# =========================================================
# إنهاء اللعبة وإعلان النتائج
# =========================================================

async def finish_image_quiz(
    context: ContextTypes.DEFAULT_TYPE,
    state: ImageQuizState,
    winner_id: Optional[int] = None,
    manual: bool = False
):

    if state.finished:
        return

    state.finished = True
    state.answer_locked = True
    state.final_guess_phase = False
    state.waiting_continue = False

    if state.round_task:

        try:
            state.round_task.cancel()
        except Exception:
            pass

    players = list(
        state.players.values()
    )

    players.sort(
        key=lambda p: (
            p.game_points,
            p.original_points
        ),
        reverse=True
    )

    for player in players:

        if player.original_points > 0:

            await _give_original_points(
                player.user_id,
                player.original_points
            )

    lines = [
        "🏁 *انتهت لعبة توقع الصورة!*",
        ""
    ]

    if manual:

        lines.append(
            "🛑 تم إنهاء القيم بواسطة الأدمن."
        )

        lines.append("")

    if winner_id:

        winner = state.players.get(
            winner_id
        )

        if winner:

            lines.extend([
                "🏆 *الفائز*",
                f"👑 {winner.name}",
                f"🎯 نقاط القيم: *{winner.game_points}*",
                ""
            ])

    if players:

        lines.append(
            "📊 *النتائج النهائية:*"
        )

        lines.append("")

        for index, player in enumerate(
            players,
            start=1
        ):

            lines.append(
                f"{index}. {player.name}\n"
                f"   🎯 نقاط القيم: {player.game_points}\n"
                f"   💰 النقاط الأصلية: {player.original_points}"
            )

            lines.append("")

    await context.bot.send_message(
        chat_id=state.chat_id,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

    IMAGE_QUIZZES.pop(
        state.chat_id,
        None
    )


# =========================================================
# Callback Buttons
# =========================================================

async def image_quiz_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    message = query.message

    if not message:

        await query.answer()
        return

    chat = message.chat

    if not chat:

        await query.answer()
        return

    state = IMAGE_QUIZZES.get(
        chat.id
    )

    if not state:

        await query.answer(
            "❌ لا توجد لعبة نشطة.",
            show_alert=True
        )

        return

    user = query.from_user

    if not await _is_admin(user.id, chat.id):

        await query.answer(
            "❌ هذا الزر للأدمن فقط.",
            show_alert=True
        )

        return

    data = query.data or ""

    # -----------------------------------------------------
    # فتح إعدادات النقاط
    # -----------------------------------------------------

    if data == "iq:settings":

        if state.started:

            await query.answer(
                "❌ لا يمكن تغيير الإعدادات بعد بدء القيم.",
                show_alert=True
            )

            return

        keyboard = []
        row = []

        for points in range(
            MIN_TARGET_POINTS,
            MAX_TARGET_POINTS + 1
        ):

            row.append(
                InlineKeyboardButton(
                    f"{points} 🎯",
                    callback_data=f"iq:points:{points}"
                )
            )

            if len(row) == 4:

                keyboard.append(row)
                row = []

        if row:
            keyboard.append(row)

        await query.answer()

        try:

            await query.edit_message_text(
                (
                    "⚙️ *إعدادات توقع الصورة*\n\n"
                    "🎯 اختر عدد النقاط المطلوبة للفوز:"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                )
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # اختيار النقاط
    # -----------------------------------------------------

    if data.startswith("iq:points:"):

        if state.started:

            await query.answer(
                "❌ القيم بدأ بالفعل.",
                show_alert=True
            )

            return

        try:

            points = int(
                data.split(":")[-1]
            )

        except ValueError:

            await query.answer(
                "❌ قيمة غير صحيحة.",
                show_alert=True
            )

            return

        if not (
            MIN_TARGET_POINTS
            <= points
            <= MAX_TARGET_POINTS
        ):

            await query.answer(
                "❌ عدد النقاط غير مسموح.",
                show_alert=True
            )

            return

        state.target_points = points

        await query.answer(
            f"تم تحديد الهدف: {points} نقاط."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "⚙️ تعديل النقاط",
                    callback_data="iq:settings"
                )
            ]
        ]

        try:

            await query.edit_message_text(
                (
                    "🖼️ *توقع الصورة*\n\n"
                    f"🎯 هدف الفوز: *{points} نقاط*\n\n"
                    f"👥 اللاعبين الحاليين: "
                    f"*{len(state.players)}*\n\n"
                    "اكتب `دخول` للانضمام.\n"
                    "وبعد اكتمال اللاعبين يكتب الأدمن `.ابدا`."
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                )
            )

        except Exception:
            pass

        await _update_board(
            context,
            state
        )

        return

    await query.answer()
