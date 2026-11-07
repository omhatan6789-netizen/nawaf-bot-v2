from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.pool import get_pool
from database.points import get_points_leaderboard


def _top_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("توب النقاط", callback_data="topmenu:points")],
        [InlineKeyboardButton("🏆 توب الألعاب", callback_data="topmenu:games")],
        [
            InlineKeyboardButton("توب الحرامية", callback_data="topmenu:robbers"),
            InlineKeyboardButton("توب المتفاعلين", callback_data="topmenu:active"),
        ],
    ])


def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ رجوع لقائمة التوب", callback_data="topmenu:back")]
    ])


async def top_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text(
        "<b>اختر زر التوب الي تبيه:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=_top_menu_keyboard(),
    )


async def _build_top_text(kind: str, chat_id: int | None = None) -> str:
    pool = get_pool()

    if kind == "points":
        rows = await get_points_leaderboard(10)
        lines = ["توب النقاط:", ""]
        for place, row in enumerate(rows, 1):
            name = row["first_name"] or row["username"] or "مستخدم"
            lines.append(f"{place} - {name} : {int(row['points'] or 0)} نقطة")
        return "\n".join(lines) if rows else "توب النقاط:\n\nلا يوجد ترتيب حتى الآن."

    if kind in {"game_wins", "game_losses"}:
        from database.game_stats import get_game_leaderboard
        result = "win" if kind == "game_wins" else "loss"
        rows = await get_game_leaderboard(result, 10)
        title = "🏆 أكثر 10 لاعبين فوزًا في الألعاب:" if result == "win" else "💀 أكثر 10 لاعبين خسارة في الألعاب:"
        lines = [title, ""]
        for place, row in enumerate(rows, 1):
            lines.append(f"{place}. {row['name']} — {int(row['total'])} مباراة")
        return "\n".join(lines) if rows else f"{title}\n\nلا توجد نتائج مسجلة حتى الآن."

    if kind == "robbers":
        rows = await pool.fetch(
            """
            SELECT b.user_id, b.robbery_balance, u.first_name, u.username
            FROM bank_accounts AS b
            JOIN users AS u ON u.user_id = b.user_id
            WHERE b.robbery_balance > 0
              AND COALESCE(u.is_bot, FALSE) = FALSE
              AND COALESCE(u.first_name, '') <> 'Deleted Account'
            ORDER BY b.robbery_balance DESC, b.user_id ASC
            LIMIT 10
            """
        )
        lines = ["توب الحرامية:", "", "أكثر ناس يزرفون:", ""]
        for place, row in enumerate(rows, 1):
            name = row["first_name"] or row["username"] or "مستخدم"
            lines.append(
                f"{place} - {name} : {int(row['robbery_balance'] or 0)} نقطة مسروقة"
            )
        return "\n".join(lines) if rows else "توب الحرامية:\n\nأكثر ناس يزرفون:\n\nلا يوجد ترتيب حتى الآن."

    if kind == "active":
        if chat_id is not None:
            rows = await pool.fetch(
                """
                SELECT u.user_id, u.first_name, u.username, ca.message_count
                FROM chat_activity AS ca
                JOIN users AS u ON u.user_id = ca.user_id
                WHERE ca.chat_id = $1
                  AND ca.message_count > 0
                  AND COALESCE(u.is_bot, FALSE) = FALSE
                  AND COALESCE(u.first_name, '') <> 'Deleted Account'
                ORDER BY ca.message_count DESC, u.user_id ASC
                LIMIT 10
                """,
                chat_id,
            )
            count_key = "message_count"
            title = "توب المتفاعلين في هذا القروب:"
        else:
            rows = await pool.fetch(
                """
                SELECT user_id, first_name, username, activity_messages
                FROM users
                WHERE activity_messages > 0
                  AND COALESCE(is_bot, FALSE) = FALSE
                  AND COALESCE(first_name, '') <> 'Deleted Account'
                ORDER BY activity_messages DESC, user_id ASC
                LIMIT 10
                """
            )
            count_key = "activity_messages"
            title = "توب المتفاعلين العام:"
        lines = [title, ""]
        for place, row in enumerate(rows, 1):
            name = row["first_name"] or row["username"] or "مستخدم"
            lines.append(f"{place} - {name} : ( رسالة {int(row[count_key] or 0)} )")
        return "\n".join(lines) if rows else f"{title}\n\nلا يوجد ترتيب حتى الآن."

    return "تعذر عرض التوب المطلوب."


async def top_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    if data == "topmenu:games":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 الأكثر فوزًا", callback_data="topmenu:game_wins")],
            [InlineKeyboardButton("💀 الأكثر خسارة", callback_data="topmenu:game_losses", style="danger")],
            [InlineKeyboardButton("↩️ رجوع لقائمة التوب", callback_data="topmenu:back")],
        ])
        await query.edit_message_text("🎮 <b>إحصائيات جميع الألعاب</b>\nاختر الترتيب:", parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    if data == "topmenu:back":
        await query.edit_message_text(
            "<b>اختر زر التوب الي تبيه:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=_top_menu_keyboard(),
        )
        return

    kind = data.removeprefix("topmenu:")
    if kind not in {"points", "robbers", "active", "game_wins", "game_losses"}:
        return

    chat = query.message.chat if query.message else None
    chat_id = chat.id if chat and chat.type in ('group', 'supergroup') else None
    text = await _build_top_text(kind, chat_id=chat_id)
    await query.edit_message_text(text, reply_markup=_back_keyboard())
