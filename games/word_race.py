from __future__ import annotations

import asyncio
import io
import os
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes, filters

from database.roles import get_rank_level, is_primary_developer, is_secondary_developer
from database.points import add_points

# ------------------------------------------------------------
# الإعدادات
# ------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_PATHS = [
    os.path.join(BASE_DIR, "assets", "word_race_board.jpg"),
    os.path.join(BASE_DIR, "assets", "word_race_board.png"),
    os.path.join(os.path.dirname(__file__), "word_race_board.jpg"),
    os.path.join(os.path.dirname(__file__), "word_race_board.png"),
]

# مواقع مربعات اللوحة في الصور المرفوعة 850x480.
# من اليمين إلى اليسار: 1,2,3,4 ثم النهاية.
STAGE_CENTERS = {
    1: (746, 385),
    2: (585, 385),
    3: (423, 385),
    4: (262, 385),
    5: (101, 385),
    6: (101, 385),
}

STAGE_BOARD_PATHS = {
    n: [
        os.path.join(BASE_DIR, f"word_race_board_{n}.jpg"),
        os.path.join(BASE_DIR, f"word_race_board_{n}.png"),
    ]
    for n in range(4, 10)
}

STAGE_TEXT_Y = 385
LABEL_MAX_WIDTH = 104
LABEL_HEIGHT = 28
LABEL_GAP = 4

SOLO_LABEL_COLORS = [
    (255, 65, 115),
    (0, 220, 255),
    (177, 85, 255),
    (255, 150, 25),
    (80, 255, 170),
    (255, 225, 60),
    (80, 145, 255),
    (255, 90, 220),
]

TEAM_INFO = {
    "احمر": ("🔴", "الأحمر", (255, 65, 90)),
    "ازرق": ("🔵", "الأزرق", (0, 205, 255)),
    "اخضر": ("🟢", "الأخضر", (55, 235, 125)),
    "اصفر": ("🟡", "الأصفر", (255, 205, 35)),
}

TEAM_ORDER = ["احمر", "ازرق", "اخضر", "اصفر"]


class WordRaceActiveFilter(filters.MessageFilter):
    """فلتر يمنع أوامر سباق الكلمات من اعتراض ألعاب البوت الأخرى."""
    def __init__(self, patterns):
        super().__init__()
        self.patterns = [re.compile(p) for p in patterns]

    def filter(self, message):
        chat = getattr(message, "chat", None)
        if not chat or chat.type not in ("group", "supergroup"):
            return False
        if chat.id not in RACES:
            return False
        text = getattr(message, "text", None) or ""
        return any(p.fullmatch(text) for p in self.patterns)


@dataclass
class Player:
    user_id: int
    name: str
    stage: int = 1
    team: Optional[str] = None
    label_color: Tuple[int, int, int] = (0, 220, 255)


@dataclass
class RaceState:
    chat_id: int
    host_id: int
    host_name: str
    players: Dict[int, Player] = field(default_factory=dict)
    mode: Optional[str] = None  # solo / teams
    team_count: int = 0
    stages_count: int = 5
    started: bool = False
    finished: bool = False
    current_round: int = 0
    accepted_words: Set[str] = field(default_factory=set)
    display_word: str = ""
    answer_locked: bool = False
    action_pending: bool = False
    pending_answerer_id: Optional[int] = None
    pending_answerer_name: str = ""
    board_message_id: Optional[int] = None
    prompt_message_id: Optional[int] = None
    hint_sent: bool = False
    waiting_continue: bool = False
    private_word_waiting: bool = False
    countdown_running: bool = False
    action_message_id: Optional[int] = None
    action_timeout_task: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)
    distribution_message_id: Optional[int] = None


RACES: Dict[int, RaceState] = {}
PRIVATE_HOST_CHAT: Dict[int, int] = {}

# ------------------------------------------------------------
# أدوات عامة
# ------------------------------------------------------------

def _clean_name(name: str) -> str:
    name = (name or "").strip()
    return name[:32] if name else "لاعب"


def _normalize_word(text: str) -> str:
    # المطلوب: إزالة المسافات الخارجية فقط؛ لا نحذف النقاط أو علامات الترقيم.
    return (text or "").strip()


async def _get_rank_level(user_id: int, chat_id: int) -> int:
    return await get_rank_level(user_id, chat_id)


async def _is_admin_plus(user_id: int, chat_id: int) -> bool:
    return await _get_rank_level(user_id, chat_id) >= 2


async def _is_developer(user_id: int) -> bool:
    return (
        await is_primary_developer(user_id)
        or await is_secondary_developer(user_id)
    )


async def _is_controller(state: RaceState, user_id: int) -> bool:
    return user_id == state.host_id or await _is_developer(user_id)


def _mention_html(user_id: int, name: str) -> str:
    safe = (
        name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f'<a href="tg://user?id={user_id}">{safe}</a>'


def _team_title(team: str) -> str:
    icon, name, _ = TEAM_INFO[team]
    return f"{icon} {name}"


def _team_color(team: str) -> Tuple[int, int, int]:
    return TEAM_INFO[team][2]


def _load_font(size: int, bold: bool = False):
    candidates = []
    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    candidates += [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def _find_asset() -> Optional[str]:
    for path in ASSET_PATHS:
        if os.path.exists(path):
            return path
    return None


def _find_stage_asset(stages_count: int) -> Optional[str]:
    for path in STAGE_BOARD_PATHS.get(stages_count, []):
        if os.path.exists(path):
            return path
    return _find_asset()


def _base_board(stages_count: int) -> Image.Image:
    path = _find_stage_asset(stages_count)
    if path:
        try:
            image = Image.open(path).convert("RGBA")
            return image
        except Exception:
            pass

    # fallback في حال لم يرفع المستخدم صورة القالب.
    image = Image.new("RGBA", (850, 480), (10, 18, 38, 255))
    draw = ImageDraw.Draw(image)
    title_font = _load_font(38, True)
    draw.text((425, 42), "سباق الكلمات", font=title_font, anchor="mm",
              fill=(245, 250, 255))
    for stage in range(1, stages_count + 1):
        x, y = STAGE_CENTERS.get(stage, STAGE_CENTERS[5])
        draw.rounded_rectangle((x - 75, y - 22, x + 75, y + 22),
                               radius=12, outline=(40, 190, 255), width=3)
        draw.text((x, y), str(stage), font=_load_font(22, True),
                  anchor="mm", fill=(245, 250, 255))
    return image


def _fit_text(draw, text, max_width, start_size=16, bold=True):
    size = start_size
    while size >= 9:
        font = _load_font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 1
    return _load_font(9, bold)


def _draw_glow_label(
    base: Image.Image,
    center_x: int,
    center_y: int,
    text: str,
    rgb: Tuple[int, int, int],
):
    # الاسم فقط، بدون صورة شخصية أو رقم لاعب.
    text = _clean_name(text)
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    temp_font = _fit_text(gd, text, LABEL_MAX_WIDTH - 18, 16, True)
    bbox = gd.textbbox((0, 0), text, font=temp_font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    width = min(LABEL_MAX_WIDTH, max(54, tw + 22))
    height = LABEL_HEIGHT

    x1 = int(center_x - width / 2)
    y1 = int(center_y - height / 2)
    x2 = x1 + width
    y2 = y1 + height

    # توهج
    for blur, alpha, grow in [(12, 85, 8), (6, 130, 4)]:
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle(
            (x1 - grow, y1 - grow, x2 + grow, y2 + grow),
            radius=10 + grow // 2,
            fill=(rgb[0], rgb[1], rgb[2], alpha),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        base.alpha_composite(layer)

    gd.rounded_rectangle(
        (x1, y1, x2, y2),
        radius=8,
        fill=(12, 20, 40, 235),
        outline=(rgb[0], rgb[1], rgb[2], 255),
        width=2,
    )

    # لمعان داخلي خفيف
    gd.line((x1 + 6, y1 + 2, x2 - 6, y1 + 2),
            fill=(255, 255, 255, 70), width=1)

    gd.text(
        (center_x, center_y + 1),
        text,
        font=temp_font,
        anchor="mm",
        fill=(245, 250, 255, 255),
    )

    base.alpha_composite(glow)


def _grouped_positions(state: RaceState):
    """
    يعيد العناصر مجمعة حسب المرحلة.
    في الفردي: اللاعبين.
    في الفرق: الفرق الموجودة فقط.
    """
    groups: Dict[int, List[Tuple[str, Tuple[int, int, int]]]] = {
        stage: [] for stage in range(1, state.stages_count + 1)
    }

    if state.mode == "teams":
        teams = {}
        for p in state.players.values():
            if p.team:
                teams[p.team] = p.stage
        for team, stage in teams.items():
            if stage < 1:
                stage = 1
            if stage > state.stages_count:
                stage = state.stages_count
            groups.setdefault(stage, []).append(
                (_team_title(team), _team_color(team))
            )
    else:
        for p in state.players.values():
            stage = max(1, min(state.stages_count, p.stage))
            groups.setdefault(stage, []).append(
                (p.name, p.label_color)
            )

    return groups


def _render_board(state: RaceState) -> bytes:
    base = _base_board(state.stages_count).convert("RGBA")
    groups = _grouped_positions(state)

    # لكل مرحلة، نضع الملصقات فوق بعضها عموديًا حول مركز المرحلة.
    for stage, entries in groups.items():
        if not entries:
            continue

        cx, cy = STAGE_CENTERS.get(stage, STAGE_CENTERS[5])
        # الملصقات تظهر فوق المربع، مثل التصميم المرفوع.
        label_center_y = cy - 54
        total_h = len(entries) * LABEL_HEIGHT + (len(entries) - 1) * LABEL_GAP
        start_y = label_center_y - total_h / 2

        for i, (label, rgb) in enumerate(entries):
            ly = int(start_y + LABEL_HEIGHT / 2 + i * (LABEL_HEIGHT + LABEL_GAP))
            _draw_glow_label(base, cx, ly, label, rgb)

    out = io.BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=88, optimize=True)
    out.seek(0)
    return out.getvalue()


async def _send_or_edit_board(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
):
    data = _render_board(state)
    bio = io.BytesIO(data)
    bio.name = "word_race.jpg"

    # كل تحديث للوحة يرسل صورة جديدة ولا يعدل الصورة السابقة.
    msg = await context.bot.send_photo(
        chat_id=state.chat_id,
        photo=bio,
    )
    state.board_message_id = msg.message_id


async def _safe_delete(context, chat_id: int, message_id: Optional[int]):
    if not message_id:
        return
    try:
        await context.bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def _state(update: Update) -> Optional[RaceState]:
    if not update.effective_chat:
        return None
    return RACES.get(update.effective_chat.id)


async def _deny_controller(update: Update):
    if update.message:
        await update.message.reply_text("❌ هذا الأمر خاص بأدمن اللعبة.")


async def _ensure_group(update: Update) -> bool:
    return bool(
        update.effective_chat
        and update.effective_chat.type in ("group", "supergroup")
    )


# ------------------------------------------------------------
# بدء اللوبي
# ------------------------------------------------------------

async def start_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    user = update.effective_user
    chat_id = update.effective_chat.id

    if not user or not await _is_admin_plus(user.id, chat_id):
        return

    if chat_id in RACES:
        await update.message.reply_text("⚠️ يوجد سباق كلمات قائم بالفعل في هذه المجموعة.")
        return

    state = RaceState(
        chat_id=chat_id,
        host_id=user.id,
        host_name=_clean_name(user.full_name),
    )
    RACES[chat_id] = state

    await update.message.reply_text(
        "<b>تم بدأ لعبة (سباق الكلمات 🐎)</b>\n\n"
        "اكتب `دخول`",
        parse_mode="HTML",
    )


async def join_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    if not state or state.started or state.finished:
        return

    user = update.effective_user
    if not user:
        return

    if user.id in state.players:
        return

    state.players[user.id] = Player(
        user_id=user.id,
        name=_clean_name(user.full_name),
        label_color=random.choice(SOLO_LABEL_COLORS),
    )

    await update.message.reply_text(
        f"✅ انضم {_clean_name(user.full_name)} إلى لعبة سباق الكلمات🐎!\n"
        f"👥 العدد: {len(state.players)}"
    )


async def leave_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    if not state or state.started:
        return

    user = update.effective_user
    if not user or user.id not in state.players:
        return

    name = state.players[user.id].name
    del state.players[user.id]

    await update.message.reply_text(
        f"🚪 خرج {name} من لعبة سباق الكلمات🐎!\n"
        f"👥 العدد: {len(state.players)}"
    )


# ------------------------------------------------------------
# الطور وعدد المراحل
# ------------------------------------------------------------

async def word_race_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or state.started:
        return
    if not user or not await _is_controller(state, user.id):
        await _deny_controller(update)
        return
    if len(state.players) < 2:
        await update.message.reply_text("❌ لازم يكون فيه لاعبين اثنين على الأقل.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("فردي", callback_data="wr:mode:solo"),
            InlineKeyboardButton("فرق", callback_data="wr:mode:teams"),
        ]
    ])
    await update.message.reply_text(
        "اختر الطور الذي تريده",
        reply_markup=keyboard,
    )


def _active_teams(state: RaceState) -> List[str]:
    if not (2 <= state.team_count <= 4):
        return []
    return TEAM_ORDER[:state.team_count]


async def _ask_team_count(query, state: RaceState):
    buttons = [
        InlineKeyboardButton("فريقين 2", callback_data="wr:teams:2"),
        InlineKeyboardButton("ثلاث أفرقة 3", callback_data="wr:teams:3"),
        InlineKeyboardButton("أربع أفرقة 4", callback_data="wr:teams:4"),
    ]
    await query.get_bot().send_message(
        chat_id=state.chat_id,
        text="اختر عدد الأفرقة!",
        reply_markup=InlineKeyboardMarkup([buttons]),
    )


async def _ask_stage_count(query, state: RaceState):
    labels = {
        4: "أربع مراحل 4", 5: "خمس مراحل 5", 6: "ست مراحل 6",
        7: "سبع مراحل 7", 8: "ثمان مراحل 8", 9: "تسع مراحل 9",
    }
    buttons = [InlineKeyboardButton(labels[n], callback_data=f"wr:stages:{n}") for n in range(4, 10)]
    await query.get_bot().send_message(
        chat_id=state.chat_id,
        text="اختر عدد المراحل التي تريدها.",
        reply_markup=InlineKeyboardMarkup([buttons[:3], buttons[3:6]]),
    )


async def _show_distribution(
    update: Update,
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
):
    if state.mode != "teams" or not state.team_count:
        return

    lines = ["📋 قائمة الفرق — سباق الكلمات", ""]

    for team in _active_teams(state):
        members = [
            p for p in state.players.values()
            if p.team == team
        ]

        lines.append(f"{_team_title(team)}:")

        if members:
            for i, p in enumerate(members, 1):
                lines.append(f"  {i}. {p.name}")
        else:
            lines.append("  لا يوجد")

        lines.append("")

    text = "\n".join(lines).strip()

    # إذا كانت القائمة موجودة، نعدل نفس الرسالة فقط
    if state.distribution_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=state.chat_id,
                message_id=state.distribution_message_id,
                text=text,
            )
            return
        except Exception:
            # إذا الرسالة انحذفت أو لم تعد قابلة للتعديل
            state.distribution_message_id = None

    # أول مرة فقط: إرسال رسالة القائمة
    msg = await context.bot.send_message(
        chat_id=state.chat_id,
        text=text,
    )

    state.distribution_message_id = msg.message_id

    # تثبيت القائمة
    try:
        await context.bot.pin_chat_message(
            chat_id=state.chat_id,
            message_id=msg.message_id,
            disable_notification=True,
        )
    except Exception:
        pass


async def _unpin_distribution(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not state.distribution_message_id:
        return

    try:
        await context.bot.unpin_chat_message(
            chat_id=state.chat_id,
            message_id=state.distribution_message_id,
        )
    except Exception:
        pass

async def word_race_distribution(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or state.started or not user:
        return
    if not await _is_controller(state, user.id):
        await _deny_controller(update)
        return
    if state.mode != "teams":
        await update.message.reply_text("❌ التوزيع متاح في طور الفرق فقط.")
        return

    if not (2 <= state.team_count <= 4):
        return
    players = list(state.players.values())
    random.shuffle(players)
    active = _active_teams(state)
    for i, p in enumerate(players):
        p.team = active[i % len(active)]
    await _show_distribution(update, state, context)



async def word_race_manual_team(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or not user:
        return

    if not await _is_controller(state, user.id):
        await _deny_controller(update)
        return

    match = re.match(
        r"^\\.اضافة\\s+(احمر|ازرق|اخضر|اصفر)$",
        update.message.text.strip()
    )

    if not match:
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لازم ترد على رسالة اللاعب.")
        return

    target = update.message.reply_to_message.from_user
    if not target:
        return

    if state.mode != "teams":
        return

    team = match.group(1)

    # لا يسمح بإضافة لاعب إلى فريق غير مختار.
    if team not in _active_teams(state):
        return

    # لاعب جديد: يضاف مباشرة إلى السباق والفريق المحدد.
    if target.id not in state.players:
        initial_stage = _team_stage(state, team) if state.started else 1
        state.players[target.id] = Player(
            user_id=target.id,
            name=_clean_name(target.full_name),
            stage=initial_stage,
            team=team,
            label_color=random.choice(SOLO_LABEL_COLORS),
        )
        action_text = (
            f"✅ تمت إضافة {state.players[target.id].name} إلى الفريق "
            f"{_team_title(team)}"
        )
    else:
        # اللاعب الموجود ينتقل للفريق الجديد، ويختفي تلقائيًا من الفريق القديم.
        old_team = state.players[target.id].team
        state.players[target.id].team = team

        if old_team == team:
            action_text = (
                f"✅ {state.players[target.id].name} موجود أصلًا في "
                f"{_team_title(team)}"
            )
        else:
            action_text = (
                f"✅ تم نقل {state.players[target.id].name} إلى الفريق "
                f"{_team_title(team)}"
            )

    await update.message.reply_text(action_text)

    # تعديل نفس رسالة قائمة الفرق، وليس إرسال قائمة جديدة.
    await _show_distribution(update, state, context)

    # إذا كان القيم بدأ، حدث اللوحة فورًا.
    if state.started:
        await _send_or_edit_board(state, context)


async def word_race_add_solo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or not user:
        return

    if not await _is_controller(state, user.id):
        await _deny_controller(update)
        return

    if update.message.text.strip() != ".اضافة":
        return

    if state.mode != "solo":
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ لازم ترد على رسالة اللاعب.")
        return

    target = update.message.reply_to_message.from_user
    if not target:
        return

    if target.id in state.players:
        return

    state.players[target.id] = Player(
        user_id=target.id,
        name=_clean_name(target.full_name),
        stage=1,
        team=None,
        label_color=random.choice(SOLO_LABEL_COLORS),
    )

    await update.message.reply_text(
        f"✅ تمت إضافة {state.players[target.id].name} إلى سباق الكلمات!"
    )

    # أثناء القيم يظهر اللاعب على اللوحة فورًا.
    if state.started:
        await _send_or_edit_board(state, context)


# ------------------------------------------------------------
# بدء السباق
# ------------------------------------------------------------

async def begin_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or not user or state.started:
        return
    if not await _is_controller(state, user.id):
        return

    if len(state.players) < 2:
        await update.message.reply_text("❌ لازم يكون فيه لاعبين اثنين على الأقل.")
        return

    if not state.mode:
        await update.message.reply_text("❌ اختر الطور أولًا باستخدام `.الطور`.")
        return

    if state.mode == "teams":
        if not any(p.team for p in state.players.values()):
            await update.message.reply_text("❌ وزّع اللاعبين أولًا باستخدام `.توزيع` أو `.اضافة`.")
            return
        if not (2 <= state.team_count <= 4):
            await update.message.reply_text("❌ اختر عدد الأفرقة أولًا.")
            return
        active = _active_teams(state)
        if not any(p.team in active for p in state.players.values()):
            await update.message.reply_text("❌ وزّع اللاعبين أولًا باستخدام `.توزيع` أو `.اضافة`.")
            return
        for p in state.players.values():
            if p.team not in active:
                counts = {t: sum(x.team == t for x in state.players.values()) for t in active}
                p.team = min(active, key=lambda t: counts[t])

    for p in state.players.values():
        p.stage = 1

    state.started = True
    state.current_round = 1
    state.countdown_running = True

    await context.bot.send_message(
        chat_id=state.chat_id,
        text="<b>🏁 استعدوا للسباق! 🏁</b>",
        parse_mode="HTML",
    )
    for n in (3, 2, 1):
        await asyncio.sleep(1)
        await context.bot.send_message(
            chat_id=state.chat_id,
            text=f"<b>{n} 🔢….</b>",
            parse_mode="HTML",
        )

    await asyncio.sleep(0.5)
    await context.bot.send_message(
        chat_id=state.chat_id,
        text="<b>🚀 انطلقنا!</b>",
        parse_mode="HTML",
    )
    await _send_or_edit_board(state, context)

    state.countdown_running = False
    await _request_word_from_host(state, context)


async def _request_word_from_host(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
):
    state.private_word_waiting = True
    state.accepted_words.clear()
    state.display_word = ""
    state.answer_locked = False
    state.action_pending = False
    state.pending_answerer_id = None
    state.pending_answerer_name = ""
    state.hint_sent = False

    PRIVATE_HOST_CHAT[state.host_id] = state.chat_id

    try:
        await context.bot.send_message(
            chat_id=state.host_id,
            text=(
                f"✏️ سباق الكلمات - الجولة {state.current_round}\n\n"
                "أرسل الكلمة أو الكلمات المطلوبة بهذه الصيغة:\n"
                "الكلمة\n"
                "أو للكلمات البديلة المقبولة:\n"
                "كلمة1 - كلمة2 - كلمة3"
            ),
        )
    except Exception:
        # لا نكسر اللعبة إذا كان الحكم لم يبدأ محادثة خاصة مع البوت.
        await context.bot.send_message(
            chat_id=state.chat_id,
            text="⚠️ لم أستطع إرسال الكلمة للأدمن في الخاص. "
                 "يجب أن يفتح الادمن محادثة البوت أولًا."
        )


# ------------------------------------------------------------
# استقبال الكلمة من الخاص
# ------------------------------------------------------------

async def check_word_race_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    user = update.effective_user

    # الخاص: كلمة الحكم.
    if update.effective_chat and update.effective_chat.type == "private":
        if not user:
            return

        chat_id = PRIVATE_HOST_CHAT.get(user.id)
        if not chat_id:
            return

        state = RACES.get(chat_id)
        if not state or not state.started or not state.private_word_waiting:
            return
        if user.id != state.host_id:
            return

        raw = text.strip()
        if not raw:
            return

        words = [_normalize_word(x) for x in raw.split("-")]
        words = [x for x in words if x]
        if not words:
            return

        state.accepted_words = set(words)
        state.display_word = words[0]
        state.private_word_waiting = False

        await update.message.reply_text(
            f"✅ تم حفظ الكلمة: {words[0]}\n"
            + (
                "الكلمات المقبولة: " +
                " + ".join(words[1:])
                if len(words) > 1
                else ""
            )
        )

        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(
                f"📢 يا حكم {_mention_html(state.host_id, state.host_name)}، "
                f"لمح للكلمة المطلوبة في الجولة ({state.current_round})!"
            ),
            parse_mode="HTML",
        )
        state.hint_sent = True
        return

    # المجموعة: إجابات اللاعبين.
    if not update.effective_chat or update.effective_chat.type not in (
        "group", "supergroup"
    ):
        return

    state = _state(update)
    if not state or not state.started or state.finished:
        return

    if state.private_word_waiting or state.waiting_continue:
        return

    if state.answer_locked or state.action_pending:
        return

    if not state.accepted_words:
        return

    if not user or user.id not in state.players:
        return

    # حتى لو كان الحكم مشاركًا، لا تحتسب إجابته من المجموعة.
    if user.id == state.host_id:
        return

    answer = _normalize_word(text)
    if answer not in state.accepted_words:
        return

    # أول إجابة صحيحة فقط.
    state.answer_locked = True
    state.action_pending = True
    state.pending_answerer_id = user.id
    state.pending_answerer_name = _clean_name(user.full_name)

    if state.mode == "solo":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "تقديم",
                    callback_data=f"wr:advance:{user.id}",
                ),
                InlineKeyboardButton(
                    "ترجيع",
                    callback_data=f"wr:backmenu:{user.id}",
                ),
            ]
        ])
        sent = await update.message.reply_text(
            f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n"
            f"الكلمة الصحيحة هي: {state.display_word}\n\n"
            "اختر تقديم فريقك! او ترجيع فريق الخصم.</b>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        state.action_message_id = sent.message_id
        _start_action_timeout(state, context, user.id)
        return

    # الفرق.
    answerer = state.players[user.id]
    own_team = answerer.team

    buttons = [
        InlineKeyboardButton(
            "تقديم",
            callback_data=f"wr:advance:{user.id}",
        )
    ]

    for team in TEAM_ORDER:
        if team != own_team and any(
            p.team == team for p in state.players.values()
        ):
            buttons.append(
                InlineKeyboardButton(
                    f"ترجيع {_team_title(team)}",
                    callback_data=f"wr:backteam:{user.id}:{team}",
                )
            )

    sent = await update.message.reply_text(
        f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n"
        f"الكلمة الصحيحة هي: {state.display_word}\n\n"
        "اختر تقديم فريقك! او ترجيع فريق الخصم.</b>",
        reply_markup=InlineKeyboardMarkup([buttons]),
        parse_mode="HTML",
    )
    state.action_message_id = sent.message_id
    _start_action_timeout(state, context, user.id)


# ------------------------------------------------------------
# ترجيع الفردي: اختيار الخصم
# ------------------------------------------------------------

async def _solo_back_menu(query, state: RaceState, answerer_id: int):
    buttons = []
    for p in state.players.values():
        if p.user_id != answerer_id:
            buttons.append(
                InlineKeyboardButton(
                    p.name,
                    callback_data=f"wr:backplayer:{answerer_id}:{p.user_id}",
                )
            )

    if not buttons:
        await query.answer("لا يوجد خصم.", show_alert=True)
        return

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ------------------------------------------------------------
# تطبيق الحركة
# ------------------------------------------------------------

def _advance_player(state: RaceState, user_id: int) -> Tuple[bool, bool]:
    """
    return (reached_final, won)
    """
    p = state.players.get(user_id)
    if not p:
        return False, False

    if p.stage < state.stages_count:
        p.stage += 1
        return p.stage == state.stages_count, False

    return True, True


def _back_player(state: RaceState, user_id: int) -> bool:
    p = state.players.get(user_id)
    if not p:
        return False
    old = p.stage
    p.stage = max(1, p.stage - 1)
    return old != p.stage


def _team_stage(state: RaceState, team: str) -> int:
    members = [p for p in state.players.values() if p.team == team]
    return members[0].stage if members else 1


def _advance_team(state: RaceState, team: str) -> Tuple[bool, bool]:
    members = [p for p in state.players.values() if p.team == team]
    if not members:
        return False, False

    old = _team_stage(state, team)
    new = min(state.stages_count, old + 1)
    for p in members:
        p.stage = new

    return new == state.stages_count, new == state.stages_count and old == state.stages_count


def _back_team(state: RaceState, team: str) -> bool:
    members = [p for p in state.players.values() if p.team == team]
    if not members:
        return False

    old = _team_stage(state, team)
    new = max(1, old - 1)
    for p in members:
        p.stage = new

    return old != new


# ------------------------------------------------------------
# مؤقت اختيار الحركة
# ------------------------------------------------------------

async def _cancel_action_timeout(state: RaceState):
    task = state.action_timeout_task
    state.action_timeout_task = None
    if not task or task.done() or task is asyncio.current_task():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _auto_advance_after_timeout(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
    answerer_id: int,
):
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        return

    if state.finished or not state.action_pending:
        return
    if state.pending_answerer_id != answerer_id:
        return

    # نفس اختيار «تقديم» الطبيعي، بدون إنشاء إجابة جديدة.
    await _apply_advance_action(state, context, answerer_id)


def _start_action_timeout(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
    answerer_id: int,
):
    old = state.action_timeout_task
    if old and not old.done():
        old.cancel()
    state.action_timeout_task = context.application.create_task(
        _auto_advance_after_timeout(state, context, answerer_id),
        name=f"word-race-timeout-{state.chat_id}-{answerer_id}",
    )


async def _apply_advance_action(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
    answerer_id: int,
    query=None,
):
    if state.finished or not state.action_pending:
        return
    if state.pending_answerer_id != answerer_id:
        return

    await _cancel_action_timeout(state)

    if state.mode == "teams":
        answerer = state.players.get(answerer_id)
        if not answerer or not answerer.team:
            return

        team = answerer.team
        old_stage = _team_stage(state, team)
        if old_stage >= state.stages_count:
            if query is not None:
                try:
                    await query.edit_message_text("<b>🎉 إجابة صحيحة! من " + state.pending_answerer_name + "\n\nالكلمة الصحيحة هي: " + state.display_word + "\n\n✅ تم اختيار: تقديم</b>", parse_mode="HTML")
                except Exception:
                    pass
            else:
                # timeout: لا توجد query، نعدل رسالة الإجابة مباشرة إذا كانت محفوظة.
                if state.action_message_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=state.chat_id,
                            message_id=state.action_message_id,
                            text=(f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
                                  f"الكلمة الصحيحة هي: {state.display_word}\n\n"
                                  "✅ تم اختيار: تقديم</b>"),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            await _declare_winner(state, context, team=team)
            return

        new_stage = old_stage + 1
        for p in state.players.values():
            if p.team == team:
                p.stage = new_stage

        text = (f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
                f"الكلمة الصحيحة هي: {state.display_word}\n\n"
                "✅ تم اختيار: تقديم</b>")
        if query is not None:
            try:
                await query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                pass
        elif state.action_message_id:
            try:
                await context.bot.edit_message_text(chat_id=state.chat_id, message_id=state.action_message_id, text=text, parse_mode="HTML")
            except Exception:
                pass

        await context.bot.send_message(
            chat_id=state.chat_id,
            text=f"<b>🚀 يتقدم {_team_title(team)} إلى المرحلة {new_stage}!</b>",
            parse_mode="HTML",
        )
        await _send_or_edit_board(state, context)

        if new_stage == state.stages_count:
            await context.bot.send_message(
                chat_id=state.chat_id,
                text=(f"<b>🚨 انتبه! {_team_title(team)} وصل إلى المرحلة "
                      f"{state.stages_count} والأخيرة! الإجابة الصحيحة القادمة "
                      f"له تعني الفوز بالسباق! 🏁</b>"),
                parse_mode="HTML",
            )
        await _finish_action(state, context)
        return

    p = state.players.get(answerer_id)
    if not p:
        return

    if p.stage >= state.stages_count:
        text = (f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
                f"الكلمة الصحيحة هي: {state.display_word}\n\n"
                "✅ تم اختيار: تقديم</b>")
        if query is not None:
            try:
                await query.edit_message_text(text, parse_mode="HTML")
            except Exception:
                pass
        elif state.action_message_id:
            try:
                await context.bot.edit_message_text(chat_id=state.chat_id, message_id=state.action_message_id, text=text, parse_mode="HTML")
            except Exception:
                pass
        await _declare_winner(state, context, player_id=answerer_id)
        return

    p.stage += 1
    text = (f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
            f"الكلمة الصحيحة هي: {state.display_word}\n\n"
            "✅ تم اختيار: تقديم</b>")
    if query is not None:
        try:
            await query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            pass
    elif state.action_message_id:
        try:
            await context.bot.edit_message_text(chat_id=state.chat_id, message_id=state.action_message_id, text=text, parse_mode="HTML")
        except Exception:
            pass
    await context.bot.send_message(
        chat_id=state.chat_id,
        text=f"<b>🚀 يتقدم {p.name} إلى المرحلة {p.stage}!</b>",
        parse_mode="HTML",
    )
    await _send_or_edit_board(state, context)
    if p.stage == state.stages_count:
        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(f"<b>🚨 انتبه! {p.name} وصل إلى المرحلة "
                  f"{state.stages_count} والأخيرة! الإجابة الصحيحة القادمة "
                  f"له تعني الفوز بالسباق! 🏁</b>"),
            parse_mode="HTML",
        )
    await _finish_action(state, context)


# ------------------------------------------------------------
# الأزرار
# ------------------------------------------------------------

async def word_race_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    if not query.message:
        return

    state = RACES.get(query.message.chat.id)
    if not state or state.finished:
        return

    user = query.from_user

    if query.data.startswith("wr:mode:"):
        if not await _is_controller(state, user.id):
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return
        if state.started:
            return

        mode = query.data.split(":")[-1]
        state.mode = mode
        await query.delete_message()
        if mode == "teams":
            await _ask_team_count(query, state)
        else:
            await _ask_stage_count(query, state)
        return

    if query.data.startswith("wr:teams:"):
        if not await _is_controller(state, user.id) or state.started:
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return
        try:
            count = int(query.data.split(":")[-1])
        except ValueError:
            return
        if not 2 <= count <= 4:
            return
        state.team_count = count
        active = _active_teams(state)
        players = list(state.players.values())
        random.shuffle(players)
        for i, p in enumerate(players):
            p.team = active[i % len(active)]
        await query.delete_message()
        await _show_distribution(update, state, context)
        await _ask_stage_count(query, state)
        return

    if query.data.startswith("wr:stages:"):
        if not await _is_controller(state, user.id):
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return

        try:
            stages = int(query.data.split(":")[-1])
        except ValueError:
            return

        if not 4 <= stages <= 9:
            return
        state.stages_count = stages
        await query.delete_message()
        if state.mode == "teams":
            text = ("تم اعتماد التعديلات! 👍🏻\n\n"
                    f"طور اللعبة: فِرَق\n"
                    f"عدد الفرق: {state.team_count}\n"
                    f"عدد المراحل: {state.stages_count}\n"
                    "الادمن يكتب .ابدا  لبدا اللعبة!")
        else:
            text = ("تم اعتماد التعديلات! 👍🏻\n\n"
                    "طور اللعبة: فردي\n"
                    f"عدد المراحل: {state.stages_count}\n"
                    "الادمن يكتب .ابدا  لبدا اللعبة!")
        await context.bot.send_message(chat_id=state.chat_id, text=f"<b>{text}</b>", parse_mode="HTML")
        return

    # كل أزرار الحركة لا يسمح بها إلا الشخص الذي أجاب أولًا.
    parts = query.data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]

    try:
        answerer_id = int(parts[2])
    except ValueError:
        return

    if state.pending_answerer_id != answerer_id:
        await query.answer("انتظر ليس دورك!", show_alert=True)
        return

    if action == "backmenu":
        if state.mode != "solo":
            return
        await _solo_back_menu(query, state, answerer_id)
        return

    if action == "backplayer":
        if len(parts) != 4:
            return
        try:
            target_id = int(parts[3])
        except ValueError:
            return

        if user.id != answerer_id:
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return
        if target_id == answerer_id or target_id not in state.players:
            return

        await _cancel_action_timeout(state)
        changed = _back_player(state, target_id)
        target = state.players[target_id]

        await query.edit_message_text(
            f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
            f"الكلمة الصحيحة هي: {state.display_word}\n\n"
            "✅ تم اختيار: ترجيع</b>",
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(f"<b>🔙 تم ترجيع {target.name} خطوة للخلف!</b>" if changed
                  else f"<b>🔙 {target.name} بالفعل في المرحلة الأولى.</b>"),
            parse_mode="HTML",
        )

        await _send_or_edit_board(state, context)
        await _finish_action(state, context)
        return

    if action == "backteam":
        if len(parts) != 4:
            return

        team = parts[3]
        if state.mode != "teams" or team not in _active_teams(state):
            return

        if user.id != answerer_id:
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return

        if team == state.players[answerer_id].team:
            return

        await _cancel_action_timeout(state)
        changed = _back_team(state, team)

        await query.edit_message_text(
            f"<b>🎉 إجابة صحيحة! من {state.pending_answerer_name}\n\n"
            f"الكلمة الصحيحة هي: {state.display_word}\n\n"
            f"✅ تم اختيار: ترجيع {TEAM_INFO[team][0]} {TEAM_INFO[team][1].replace('الفريق ', '')}</b>",
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=state.chat_id,
            text=(f"<b>🔙 تم ترجيع {_team_title(team)} خطوة للخلف!</b>" if changed
                  else f"<b>🔙 {_team_title(team)} بالفعل في المرحلة الأولى.</b>"),
            parse_mode="HTML",
        )

        await _send_or_edit_board(state, context)
        await _finish_action(state, context)
        return

    if action == "advance":
        if user.id != answerer_id:
            await query.answer("انتظر ليس دورك!", show_alert=True)
            return
        await _apply_advance_action(state, context, answerer_id, query=query)

# ------------------------------------------------------------
# نهاية الحركة والجولة التالية
# ------------------------------------------------------------

async def _finish_action(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
):
    await _cancel_action_timeout(state)
    state.action_pending = False
    state.answer_locked = True
    state.waiting_continue = True
    state.action_message_id = None

    await context.bot.send_message(
        chat_id=state.chat_id,
        text="الادمن يكتب .كمل للجولة التالية."
    )


async def continue_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state or not state.started or state.finished:
        return
    if not user or user.id != state.host_id:
        await _deny_controller(update)
        return
    if not state.waiting_continue:
        return

    state.waiting_continue = False
    state.current_round += 1
    await _request_word_from_host(state, context)


# ------------------------------------------------------------
# الفوز والنقاط
# ------------------------------------------------------------

async def _give_points(user_id: int, amount: int = 70):
    await add_points(user_id, amount)


async def _declare_winner(
    state: RaceState,
    context: ContextTypes.DEFAULT_TYPE,
    player_id: Optional[int] = None,
    team: Optional[str] = None,
):

    await _unpin_distribution(state, context)

    if state.finished:
        return

    await _cancel_action_timeout(state)
    state.finished = True
    state.started = False
    state.waiting_continue = False
    state.private_word_waiting = False
    state.answer_locked = True
    state.action_pending = False

    winners: List[Player] = []

    if team:
        winners = [p for p in state.players.values() if p.team == team]
        winner_title = _team_title(team)
        winner_line = f"ألف مبروك لـ {winner_title} الفوز بسباق الكلمات! 🥇"
    elif player_id is not None and player_id in state.players:
        winners = [state.players[player_id]]
        winner_title = state.players[player_id].name
        winner_line = f"ألف مبروك لـ {winner_title} الفوز بسباق الكلمات! 🥇"
    else:
        return

    await context.bot.send_message(
        chat_id=state.chat_id,
        text=(
            "<b>🏆🎉 الفائز بالسباق! 🎉🏆\n\n"
            f"{winner_line}</b>"
        ),
        parse_mode="HTML",
    )

    await _send_or_edit_board(state, context)

    # كل فائز +70، والحكم +70 حتى لو لم يكن مشاركًا.
    awarded: List[Tuple[str, int]] = []
    seen = set()

    for p in winners:
        if p.user_id not in seen:
            await _give_points(p.user_id, 70)
            awarded.append((p.name, 70))
            seen.add(p.user_id)

    if state.host_id not in seen:
        await _give_points(state.host_id, 70)
        awarded.append((state.host_name, 70))

    lines = ["✨ جوائز النقاط للفائزين ✨"]
    for name, amount in awarded:
        lines.append(f"• {name} — حصل على +{amount} نقطة 🏅")

    await context.bot.send_message(
        chat_id=state.chat_id,
        text="<b>" + "\n".join(lines) + "</b>",
        parse_mode="HTML",
    )

    # نبقي اللوحة النهائية، ونزيل حالة السباق من الذاكرة بعد إرسال كل شيء.
    PRIVATE_HOST_CHAT.pop(state.host_id, None)
    RACES.pop(state.chat_id, None)


# ------------------------------------------------------------
# إنهاء اللعبة يدويًا
# ------------------------------------------------------------

async def end_word_race(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not await _ensure_group(update):
        return

    state = _state(update)
    user = update.effective_user

    if not state:
        return

    if not user or not await _is_admin_plus(user.id, state.chat_id):
        return

    # فك تثبيت قائمة الفرق، مع إبقاء الرسالة موجودة في المحادثة.
    await _unpin_distribution(state, context)

    # إلغاء كل الحالة فورًا: الجولة، الكلمة، الانتظار، .كمل، إلخ.
    await _cancel_action_timeout(state)
    RACES.pop(state.chat_id, None)
    PRIVATE_HOST_CHAT.pop(state.host_id, None)
    
    await update.message.reply_text(
        "🛑 تم إنهاء لعبة سباق الكلمات."
    )
