from __future__ import annotations

import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database.pool import get_pool
from database.points import charge_two_players
from games.connect4 import create_multiplayer_game

DEFAULT_WAGER = 20_000
MIN_WAGER = 1


def _rps_winner(a: str, b: str) -> int:
    if a == b:
        return 0
    return 1 if (a, b) in (("r", "s"), ("p", "r"), ("s", "p")) else 2


def _rps_keyboard(challenge_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✊ حجر", callback_data=f"c4r:{challenge_id}:r"),
            InlineKeyboardButton("✋ ورقة", callback_data=f"c4r:{challenge_id}:p"),
            InlineKeyboardButton("✌️ مقص", callback_data=f"c4r:{challenge_id}:s"),
        ],
        [InlineKeyboardButton("إلغاء وإرجاع الرهان", callback_data=f"c4x:{challenge_id}")],
    ])


async def connect4_challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or chat.type not in ("group", "supergroup"):
        return
    target_message = message.reply_to_message
    target = target_message.from_user if target_message else None
    if not target:
        await message.reply_text("❌ استخدم «كونكت» بالرد على الشخص اللي تبي تتحداه.")
        return
    if target.is_bot or target.id == user.id:
        await message.reply_text("❌ تقدر تتحدى شخصًا آخر فقط. لمواجهة البوت افتح كونكت 4 من الميني آب.")
        return
    parts = (message.text or "").split()
    wager = DEFAULT_WAGER
    if len(parts) > 2:
        await message.reply_text("الاستخدام: كونكت أو كونكت 50000")
        return
    if len(parts) == 2:
        try:
            wager = int(parts[1].replace(",", ""))
        except ValueError:
            await message.reply_text("❌ مبلغ الرهان غير صحيح.")
            return
    if wager < MIN_WAGER or wager > 2_000_000_000:
        await message.reply_text("❌ اختر مبلغًا بين 1 و 2,000,000,000 نقطة.")
        return
    if target.id == user.id:
        return
    challenge_id = uuid.uuid4()
    pool = get_pool()
    await pool.execute(
        """INSERT INTO connect4_challenges
           (id,chat_id,challenger_id,challenger_name,opponent_id,opponent_name,wager)
           VALUES($1,$2,$3,$4,$5,$6,$7)""",
        challenge_id, chat.id, user.id, user.first_name or "اللاعب الأول",
        target.id, target.first_name or "اللاعب الثاني", wager,
    )
    text = (
        "## اللعبة شغالة ↢ كونكت 4\n\n"
        "اللاعبين:\n"
        f"• ↢ {user.first_name or 'اللاعب الأول'}\n"
        f"• ↢ {target.first_name or 'اللاعب الثاني'}\n\n"
        f"الرهان على كل لاعب: {wager:,} نقطة\n"
        f"جائزة الفوز: {wager * 2:,} نقطة🎖️\n\n"
        "(بانتظار قبول التحدي)"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("قبول التحدي", callback_data=f"c4a:{challenge_id.hex}"),
        InlineKeyboardButton("رفض", callback_data=f"c4d:{challenge_id.hex}"),
    ]])
    await message.reply_text(text, reply_markup=keyboard)


async def connect4_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    parts = query.data.split(":")
    action = parts[0]
    raw_id = parts[1] if len(parts) > 1 else ""
    try:
        challenge_id = uuid.UUID(hex=raw_id)
    except Exception:
        await query.answer("تعذر قراءة التحدي.", show_alert=True)
        return
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM connect4_challenges WHERE id=$1", challenge_id)
    if not row:
        await query.answer("التحدي غير موجود.", show_alert=True)
        return
    user_id = query.from_user.id

    if action == "c4d":
        if user_id not in (row["challenger_id"], row["opponent_id"]):
            await query.answer("هذا التحدي ليس لك.", show_alert=True)
            return
        if row["status"] != "pending":
            await query.answer("انتهى هذا التحدي.", show_alert=True)
            return
        await pool.execute(
            "UPDATE connect4_challenges SET status='declined',updated_at=NOW() WHERE id=$1",
            challenge_id,
        )
        await query.edit_message_text("تم رفض تحدي كونكت 4.", reply_markup=None)
        await query.answer("تم رفض التحدي.")
        return

    if action == "c4a":
        if user_id != row["opponent_id"]:
            await query.answer("اللاعب المدعو فقط يقدر يقبل التحدي.", show_alert=True)
            return
        if row["status"] != "pending":
            await query.answer("هذا التحدي لم يعد متاحًا.", show_alert=True)
            return
        charged = await charge_two_players(
            int(row["challenger_id"]), int(row["opponent_id"]), int(row["wager"])
        )
        if charged != "ok":
            who = "صاحب التحدي" if charged == "first_insufficient" else "أنت"
            await query.answer(f"{who} ما عنده رصيد كافٍ للرهان.", show_alert=True)
            return
        changed = await pool.fetchval(
            """UPDATE connect4_challenges SET status='choosing',updated_at=NOW()
               WHERE id=$1 AND status='pending' RETURNING id""",
            challenge_id,
        )
        if not changed:
            # A simultaneous acceptance must never charge twice.
            from database.points import settle_two_player_wager
            await settle_two_player_wager(
                int(row["challenger_id"]), int(row["opponent_id"]), int(row["wager"]), None
            )
            await query.answer("تم قبول التحدي من قبل.", show_alert=True)
            return
        rps_message = await query.message.reply_text(
            "✊ حجر ورقة مقص\n\n"
            f"• {row['challenger_name']}\n"
            f"• {row['opponent_name']}\n\n"
            "اختاروا حركة لتحديد من يبدأ اللعب.",
            reply_markup=_rps_keyboard(challenge_id.hex),
        )
        await pool.execute(
            "UPDATE connect4_challenges SET rps_message_id=$2 WHERE id=$1",
            challenge_id, rps_message.message_id,
        )
        await query.edit_message_text(
            "تم قبول تحدي كونكت 4 وحُجز الرهان.\n\nبانتظار اختيار حجر ورقة مقص من اللاعبين.",
            reply_markup=None,
        )
        await query.answer("تم قبول التحدي وحُجز الرهان.")
        return

    if action == "c4x":
        if user_id not in (row["challenger_id"], row["opponent_id"]):
            await query.answer("هذا التحدي ليس لك.", show_alert=True)
            return
        if row["status"] != "choosing":
            await query.answer("لا يمكن إلغاء التحدي في هذه المرحلة.", show_alert=True)
            return
        cancelled = await pool.fetchval(
            """UPDATE connect4_challenges SET status='cancelled',updated_at=NOW()
               WHERE id=$1 AND status='choosing'
                 AND (challenger_choice IS NULL OR opponent_choice IS NULL)
               RETURNING id""",
            challenge_id,
        )
        if cancelled:
            from database.points import settle_two_player_wager
            await settle_two_player_wager(
                int(row["challenger_id"]), int(row["opponent_id"]), int(row["wager"]), None
            )
            await query.edit_message_text("تم إلغاء تحدي كونكت 4 وإرجاع الرهان للاعبين.")
            await query.answer("تم إرجاع الرهان.")
        else:
            await query.answer("تم إلغاء التحدي مسبقًا.", show_alert=True)
        return

    if action == "c4r":
        if len(parts) != 3 or parts[2] not in ("r", "p", "s"):
            return
        if row["status"] != "choosing":
            await query.answer("اختيار حجر ورقة مقص غير متاح الآن.", show_alert=True)
            return
        if user_id == row["challenger_id"]:
            column = "challenger_choice"
        elif user_id == row["opponent_id"]:
            column = "opponent_choice"
        else:
            await query.answer("هذا الاختيار للاعبين فقط.", show_alert=True)
            return
        choice = parts[2]
        updated = await pool.fetchrow(
            f"""UPDATE connect4_challenges SET {column}=$2,updated_at=NOW()
                WHERE id=$1 AND status='choosing' AND {column} IS NULL
                RETURNING *""",
            challenge_id, choice,
        )
        if not updated:
            await query.answer("سجلت اختيارك من قبل.", show_alert=True)
            return
        await query.answer("تم تسجيل اختيارك.")
        if not updated["challenger_choice"] or not updated["opponent_choice"]:
            return
        winner = _rps_winner(updated["challenger_choice"], updated["opponent_choice"])
        if winner == 0:
            await pool.execute(
                """UPDATE connect4_challenges SET challenger_choice=NULL,
                   opponent_choice=NULL,updated_at=NOW() WHERE id=$1 AND status='choosing'""",
                challenge_id,
            )
            try:
                await query.edit_message_text(
                    "تعادل! ✊ ورقة مقص\n\nاختاروا من جديد لتحديد أول لاعب.",
                    reply_markup=_rps_keyboard(challenge_id.hex),
                )
            except Exception:
                pass
            return
        starter_id = int(updated["challenger_id"] if winner == 1 else updated["opponent_id"])
        game = await create_multiplayer_game(
            challenge_id=challenge_id,
            player1_id=int(updated["challenger_id"]),
            player2_id=int(updated["opponent_id"]),
            player1_name=updated["challenger_name"],
            player2_name=updated["opponent_name"],
            starter_id=starter_id,
            wager=int(updated["wager"]),
            chat_id=int(updated["chat_id"]),
        )
        await pool.execute(
            """UPDATE connect4_challenges SET status='playing',game_id=$2,updated_at=NOW()
               WHERE id=$1 AND status='choosing'""",
            challenge_id, uuid.UUID(game["id"]),
        )
        me = await context.bot.get_me()
        start_url = f"https://t.me/{me.username}?start=c4_{game['id']}"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔴 فتح لعبة كونكت 4", url=start_url)
        ]])
        starter_name = updated["challenger_name"] if starter_id == updated["challenger_id"] else updated["opponent_name"]
        try:
            await query.edit_message_text(
                f"✅ انتهت جولة حجر ورقة مقص!\n"
                f"يبدأ أولًا: {starter_name}\n\n"
                "تم تجهيز كونكت 4، افتحوا اللعبة من الزر بالأسفل.",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.message.reply_text(
            f"اللعبة شغالة ↢ كونكت 4\n\n"
            f"اللاعبين:\n• ↢ {updated['challenger_name']}\n"
            f"• ↢ {updated['opponent_name']}\n\n"
            f"الرهان على كل لاعب: {int(updated['wager']):,} نقطة\n"
            f"جائزة الفوز: {int(updated['wager'])*2:,} نقطة🎖️\n"
            f"يبدأ أولًا: {starter_name}",
            reply_markup=keyboard,
        )
        return
