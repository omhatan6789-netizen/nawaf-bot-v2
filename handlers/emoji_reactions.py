import logging
import re

from telegram import (
    Update,
    ReactionTypeEmoji,
    ReactionTypeCustomEmoji,
)
from telegram.error import TelegramError
from telegram.ext import ContextTypes, ApplicationHandlerStop

from database.pool import get_pool
from database.roles import is_developer

logger = logging.getLogger(__name__)

OWNER_ACCOUNT_ID = 6496915877

_RULES_CACHE = []
_PENDING_EMOJI = {}


async def load_emoji_reaction_rules():
    global _RULES_CACHE
    pool = get_pool()
    rows = await pool.fetch("""
        SELECT match_type, keyword, emoji, custom_emoji_id, created_by
        FROM emoji_reaction_rules
        ORDER BY match_type, keyword
    """)
    _RULES_CACHE = [
        {
            "match_type": row["match_type"],
            "keyword": row["keyword"],
            "emoji": row["emoji"],
            "custom_emoji_id": row["custom_emoji_id"],
            "created_by": row["created_by"],
        }
        for row in rows
    ]


async def _save_rule(match_type, keyword, emoji, custom_id, user_id):
    pool = get_pool()
    await pool.execute("""
        INSERT INTO emoji_reaction_rules
            (match_type, keyword, emoji, custom_emoji_id, created_by)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (match_type, keyword)
        DO UPDATE SET
            emoji = EXCLUDED.emoji,
            custom_emoji_id = EXCLUDED.custom_emoji_id,
            created_by = EXCLUDED.created_by
    """, match_type, keyword, emoji, custom_id, user_id)
    await load_emoji_reaction_rules()


async def _delete_rule(match_type, keyword):
    pool = get_pool()
    result = await pool.execute("""
        DELETE FROM emoji_reaction_rules
        WHERE match_type = $1 AND keyword = $2
    """, match_type, keyword)
    deleted = result.endswith(" 1")
    await load_emoji_reaction_rules()
    return deleted


def _custom_emoji_id(message):
    for entity in (message.entities or []):
        if entity.type == "custom_emoji":
            return entity.custom_emoji_id
    return None


def _format_list():
    normal = [r for r in _RULES_CACHE if r["match_type"] == "exact"]
    special = [r for r in _RULES_CACHE if r["match_type"] == "contains"]
    lines = ["قائمة الايموجيات المضافة بالبوت:", "", "الايموجيات العادية:"]
    if normal:
        lines.extend(
            f"{i} ~ {r['keyword']} {r['emoji']}"
            for i, r in enumerate(normal, 1)
        )
    else:
        lines.append("لا توجد ايموجيات عادية مضافة.")
    lines.extend(["", "—————————————————————", "", "الايموجيات المميزة:"])
    if special:
        lines.extend(
            f"{i} ~ {r['keyword']} {r['emoji']}"
            for i, r in enumerate(special, 1)
        )
    else:
        lines.append("لا توجد ايموجيات مميزة مضافة.")
    return "\n".join(lines)


async def emoji_reactions_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or message.text is None:
        return

    text = message.text.strip()
    if not text:
        return

    is_management_command = (
        text == "الايموجيات المضافة"
        or re.match(
            r"^(اضف ايموجي(?: مميز)?|مسح ايموجي(?: مميز)?)(?:\s|$)",
            text,
        )
    )
    if is_management_command:
        if user.id != OWNER_ACCOUNT_ID and not await is_developer(user.id):
            return

        if text == "الايموجيات المضافة":
            await message.reply_text(_format_list())
            raise ApplicationHandlerStop

        match = re.match(r"^اضف ايموجي مميز\s+(.+)$", text)
        if match:
            _PENDING_EMOJI[user.id] = {
                "match_type": "contains",
                "keyword": match.group(1).strip(),
            }
            await message.reply_text("• تمام، ارسل الإيموجي المميز الحين…")
            raise ApplicationHandlerStop

        match = re.match(r"^اضف ايموجي\s+(.+)$", text)
        if match:
            _PENDING_EMOJI[user.id] = {
                "match_type": "exact",
                "keyword": match.group(1).strip(),
            }
            await message.reply_text("• تمام ارسل الايموجي الحين…")
            raise ApplicationHandlerStop

        match = re.match(r"^مسح ايموجي مميز\s+(.+)$", text)
        if match:
            keyword = match.group(1).strip()
            deleted = await _delete_rule("contains", keyword)
            await message.reply_text(
                f"• {'تم مسح' if deleted else 'ما لقيت'} الإيموجي المميز للكلمة: {keyword}"
            )
            raise ApplicationHandlerStop

        match = re.match(r"^مسح ايموجي\s+(.+)$", text)
        if match:
            keyword = match.group(1).strip()
            deleted = await _delete_rule("exact", keyword)
            await message.reply_text(
                f"• {'تم مسح' if deleted else 'ما لقيت'} الإيموجي العادي للكلمة: {keyword}"
            )
            raise ApplicationHandlerStop

        await message.reply_text(
            "الأوامر:\nاضف ايموجي الكلمة\nاضف ايموجي مميز الكلمة\n"
            "مسح ايموجي الكلمة\nمسح ايموجي مميز الكلمة\nالايموجيات المضافة"
        )
        raise ApplicationHandlerStop

    pending = _PENDING_EMOJI.get(user.id)
    if pending:
        if user.id != OWNER_ACCOUNT_ID and not await is_developer(user.id):
            _PENDING_EMOJI.pop(user.id, None)
            return
        custom_id = _custom_emoji_id(message)
        emoji = text
        if custom_id is None and (len(text) > 8 or len(text.split()) != 1):
            await message.reply_text("• ارسل إيموجي واحد فقط.")
            raise ApplicationHandlerStop
        try:
            await _save_rule(
                pending["match_type"],
                pending["keyword"],
                emoji,
                custom_id,
                user.id,
            )
        except Exception:
            logger.exception("تعذر حفظ قاعدة تفاعل الإيموجي")
            await message.reply_text("• صار خطأ أثناء حفظ الإيموجي، حاول مرة ثانية.")
            raise ApplicationHandlerStop
        _PENDING_EMOJI.pop(user.id, None)
        kind = "المميز" if pending["match_type"] == "contains" else "العادي"
        await message.reply_text(
            f"• تم حفظ الإيموجي {kind} للكلمة: {pending['keyword']} {emoji}"
        )
        raise ApplicationHandlerStop

    lowered = text.casefold()
    for rule in _RULES_CACHE:
        keyword = rule["keyword"]
        if rule["match_type"] == "exact":
            matched = lowered == keyword.casefold()
        else:
            matched = keyword.casefold() in lowered
        if not matched:
            continue
        try:
            if rule["custom_emoji_id"]:
                reaction = ReactionTypeCustomEmoji(
                    custom_emoji_id=rule["custom_emoji_id"]
                )
            else:
                reaction = ReactionTypeEmoji(emoji=rule["emoji"])
            await context.bot.set_message_reaction(
                chat_id=chat.id,
                message_id=message.message_id,
                reaction=[reaction],
            )
        except TelegramError as exc:
            logger.warning(
                "فشل التفاعل بالإيموجي | chat_id=%s | message_id=%s | emoji=%s | error=%s",
                chat.id,
                message.message_id,
                rule["emoji"],
                exc,
            )
        except Exception:
            logger.exception("خطأ أثناء وضع تفاعل الإيموجي")
        return
