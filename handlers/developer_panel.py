"""PostgreSQL-backed developer panel (legacy Arabic entry points)."""
from __future__ import annotations

import asyncio
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from database.pool import get_pool
from database.moderation import get_sanction_rows, clear_sanction_table

logger = logging.getLogger(__name__)
OWNER_ID = 8453977662
SESSIONS: dict[int, dict] = {}
LISTS = {
    "mute": ("bot_mutes", "المكتومين"),
    "restrict": ("restrictions", "المقيدين"),
    "ban": ("moderation_bans", "المحظورين"),
}


def _esc(value):
    return html.escape(str(value or ""), quote=True)


def _mention(user_id, name):
    return f'<a href="tg://user?id={int(user_id)}">{_esc(name or user_id)}</a>'


def _back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="devpanel:menu")]])


def _main_keyboard(user_id):
    rows = [
        [InlineKeyboardButton("الإحصائيات", callback_data="devpanel:stats"),
         InlineKeyboardButton("الإذاعة", callback_data="devpanel:broadcast")],
        [InlineKeyboardButton("المكتومين", callback_data="devpanel:list:mute"),
         InlineKeyboardButton("المحظورين", callback_data="devpanel:list:ban")],
        [InlineKeyboardButton("تعديل ستارت", callback_data="devpanel:startedit")],
        [InlineKeyboardButton("سجل الإذاعة", callback_data="devpanel:logs"),
         InlineKeyboardButton("المقيدين", callback_data="devpanel:list:restrict")],
    ]
    if user_id == OWNER_ID:
        rows[2].append(InlineKeyboardButton("المسموحين بالوصول", callback_data="devpanel:access"))
    return InlineKeyboardMarkup(rows)


async def _allowed(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    return bool(await get_pool().fetchval(
        "SELECT 1 FROM developer_panel_access WHERE user_id=$1", int(user_id)
    ))


async def developer_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not update.effective_chat or update.effective_chat.type != "private":
        return
    if not await _allowed(user.id):
        raise ApplicationHandlerStop
    SESSIONS.pop(user.id, None)
    await msg.reply_text(
        f"أهلًا يـ {_mention(user.id, user.first_name)} 👋",
        parse_mode="HTML", reply_markup=_main_keyboard(user.id),
    )
    raise ApplicationHandlerStop


async def _show_stats(query):
    pool = get_pool()
    private_count, groups, channels = await asyncio.gather(
        pool.fetchval("SELECT COUNT(*) FROM developer_private_starts"),
        pool.fetchval("SELECT COUNT(*) FROM developer_bot_chats WHERE active=1 AND chat_type IN ('group','supergroup')"),
        pool.fetchval("SELECT COUNT(*) FROM developer_bot_chats WHERE active=1 AND chat_type='channel'"),
    )
    await query.edit_message_text(
        "📊 الإحصائيات\n━━━━━━━━━━━━\n\n"
        f"👤 عدد المشتركين: {private_count or 0}\n"
        f"👥 عدد المجموعات: {groups or 0}\n"
        f"📢 عدد القنوات: {channels or 0}",
        reply_markup=_back(),
    )


async def _show_access(query):
    rows = await get_pool().fetch(
        "SELECT user_id,username,first_name FROM developer_panel_access ORDER BY id"
    )
    text = "المسموحين بالوصول:\n\n"
    if not rows:
        text += "لا يوجد أشخاص مضافين."
    else:
        for i, row in enumerate(rows, 1):
            label = "@" + row["username"].lstrip("@") if row["username"] else (row["first_name"] or str(row["user_id"]))
            text += f"{i}. {_esc(label)} — <code>{row['user_id']}</code>\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("إضافة شخص", callback_data="devpanel:access:add"),
         InlineKeyboardButton("حذف شخص", callback_data="devpanel:access:delete")],
        [InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="devpanel:menu")],
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _show_list(query, kind):
    table, title = LISTS[kind]
    chats = await get_pool().fetch(
        "SELECT chat_id,title FROM developer_bot_chats WHERE active=1 AND chat_type IN ('group','supergroup') ORDER BY title"
    )
    lines = [f"• قائمة {title}", "━━━━━━━━━━━━", ""]
    total = 0
    for chat in chats:
        rows = await get_sanction_rows(table, int(chat["chat_id"]))
        if not rows:
            continue
        lines.append(f"📍 {_esc(chat['title'] or chat['chat_id'])} — <code>{chat['chat_id']}</code>")
        for row in rows:
            name = ("@" + row["username"].lstrip("@")) if row["username"] else (row["first_name"] or str(row["user_id"]))
            lines.append(f"• {_esc(name)} (<code>{row['user_id']}</code>)")
            total += 1
        lines.append("")
    if total == 0:
        lines.append("لا يوجد.")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("مسح القائمة من جميع المجموعات", callback_data=f"devpanel:clear:confirm:{kind}")],
        [InlineKeyboardButton("↩️ الرجوع للقائمة", callback_data="devpanel:menu")],
    ])
    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3850] + "\n… تم اختصار القائمة."
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _ask_broadcast(query, user_id, kind):
    SESSIONS[user_id] = {"action": "broadcast_message", "kind": kind}
    await query.edit_message_text("ارسل الآن رسالة الإذاعة.", reply_markup=_back())


async def developer_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    user = query.from_user
    if not await _allowed(user.id):
        await query.answer()
        return
    data = query.data or ""
    await query.answer()
    if data == "devpanel:menu":
        SESSIONS.pop(user.id, None)
        await query.edit_message_text(
            f"أهلًا يـ {_mention(user.id, user.first_name)} 👋",
            parse_mode="HTML", reply_markup=_main_keyboard(user.id),
        )
    elif data == "devpanel:stats":
        await _show_stats(query)
    elif data == "devpanel:startedit":
        from handlers.start_editor import open_start_editor_from_panel
        SESSIONS.pop(user.id, None)
        context.user_data["developer_panel_start_editor"] = True
        await open_start_editor_from_panel(query, context)
    elif data == "devpanel:access":
        if user.id == OWNER_ID:
            await _show_access(query)
    elif data == "devpanel:access:add":
        if user.id == OWNER_ID:
            SESSIONS[user.id] = {"action": "access_add"}
            await query.edit_message_text("ارسل ID الشخص أو يوزره لإضافته.", reply_markup=_back())
    elif data == "devpanel:access:delete":
        if user.id == OWNER_ID:
            SESSIONS[user.id] = {"action": "access_delete"}
            await query.edit_message_text("ارسل ID الشخص أو يوزره لحذفه.", reply_markup=_back())
    elif data.startswith("devpanel:list:"):
        kind = data.split(":")[-1]
        if kind in LISTS:
            await _show_list(query, kind)
    elif data.startswith("devpanel:clear:confirm:"):
        kind = data.split(":")[-1]
        if kind in LISTS:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("نعم، تأكيد المسح", callback_data=f"devpanel:clear:execute:{kind}")],
                [InlineKeyboardButton("إلغاء", callback_data=f"devpanel:list:{kind}")],
            ])
            await query.edit_message_text("⚠️ هل أنت متأكد من مسح هذه القائمة من جميع المجموعات؟", reply_markup=keyboard)
    elif data.startswith("devpanel:clear:execute:"):
        kind = data.split(":")[-1]
        if kind in LISTS:
            table = LISTS[kind][0]
            chats = await get_pool().fetch("SELECT chat_id FROM developer_bot_chats WHERE active=1 AND chat_type IN ('group','supergroup')")
            total = 0
            for chat in chats:
                ids = await clear_sanction_table(table, int(chat["chat_id"]))
                total += len(ids)
                if kind == "restrict":
                    for uid in ids:
                        try:
                            from telegram import ChatPermissions
                            await context.bot.restrict_chat_member(
                                chat_id=int(chat["chat_id"]), user_id=uid,
                                permissions=ChatPermissions.all_permissions(),
                            )
                        except Exception:
                            pass
                elif kind == "ban":
                    for uid in ids:
                        try:
                            await context.bot.unban_chat_member(chat_id=int(chat["chat_id"]), user_id=uid, only_if_banned=False)
                        except Exception:
                            pass
            await query.edit_message_text(f"تم مسح {LISTS[kind][1]} من جميع المجموعات ✅\nعدد السجلات: {total}", reply_markup=_back())
    elif data == "devpanel:broadcast":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("الخاص", callback_data="devpanel:broadcast:private"),
             InlineKeyboardButton("المجموعات", callback_data="devpanel:broadcast:groups")],
            [InlineKeyboardButton("القنوات", callback_data="devpanel:broadcast:channels"),
             InlineKeyboardButton("الكل", callback_data="devpanel:broadcast:all")],
            [InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="devpanel:menu")],
        ])
        await query.edit_message_text("اختر وجهة الإذاعة:", reply_markup=keyboard)
    elif data.startswith("devpanel:broadcast:"):
        kind = data.split(":")[-1]
        if kind in ("private", "groups", "channels", "all"):
            await _ask_broadcast(query, user.id, kind)
    elif data == "devpanel:logs":
        rows = await get_pool().fetch(
            "SELECT id,broadcast_type,created_at FROM developer_broadcasts ORDER BY id DESC LIMIT 15"
        )
        if not rows:
            await query.edit_message_text("لا توجد إذاعات مسجلة.", reply_markup=_back())
        else:
            lines = ["سجل الإذاعة:"]
            keys = []
            for row in rows:
                lines.append(f"• إذاعة {row['id']} — {row['broadcast_type']} — {row['created_at']}")
                keys.append([InlineKeyboardButton(f"عرض الإذاعة {row['id']}", callback_data=f"devpanel:log:view:{row['id']}")])
            keys.append([InlineKeyboardButton("↩️ رجوع للقائمة", callback_data="devpanel:menu")])
            await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keys))
    elif data.startswith("devpanel:log:view:"):
        bid = int(data.rsplit(":", 1)[-1])
        row = await get_pool().fetchrow("SELECT source_chat_id,source_message_id FROM developer_broadcasts WHERE id=$1", bid)
        if row:
            try:
                await context.bot.copy_message(chat_id=query.message.chat.id, from_chat_id=int(row["source_chat_id"]), message_id=int(row["source_message_id"]))
                await query.message.reply_text("↩️", reply_markup=_back())
            except Exception:
                await query.edit_message_text("تعذر إظهار الرسالة الأصلية.", reply_markup=_back())


async def developer_panel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not update.effective_chat or update.effective_chat.type != "private":
        return
    session = SESSIONS.get(user.id)
    if not session:
        return
    if not await _allowed(user.id):
        SESSIONS.pop(user.id, None)
        raise ApplicationHandlerStop
    action = session.get("action")
    if action in ("access_add", "access_delete"):
        if user.id != OWNER_ID:
            SESSIONS.pop(user.id, None)
            raise ApplicationHandlerStop
        value = (msg.text or "").strip()
        pool = get_pool()
        if action == "access_add":
            if value.isdigit():
                row = await pool.fetchrow("SELECT user_id,username,first_name FROM users WHERE user_id=$1", int(value))
            else:
                row = await pool.fetchrow("SELECT user_id,username,first_name FROM users WHERE LOWER(username)=$1", value.lstrip("@").lower())
            if not row:
                await msg.reply_text("ما لقيت المستخدم ضمن المستخدمين المسجلين.", reply_markup=_back())
                raise ApplicationHandlerStop
            await pool.execute(
                """INSERT INTO developer_panel_access(user_id,username,first_name,added_by)
                   VALUES($1,$2,$3,$4) ON CONFLICT(user_id) DO UPDATE SET
                   username=EXCLUDED.username,first_name=EXCLUDED.first_name""",
                int(row["user_id"]), row["username"], row["first_name"], user.id,
            )
            result = "تمت إضافته للمسموحين بالوصول ✅"
        else:
            if value.isdigit():
                result = await pool.execute("DELETE FROM developer_panel_access WHERE user_id=$1", int(value))
            else:
                result = await pool.execute("DELETE FROM developer_panel_access WHERE LOWER(username)=$1", value.lstrip("@").lower())
            result = "تم حذف الشخص من المسموحين بالوصول ✅" if result.endswith("1") else "لم يتم العثور على الشخص."
        SESSIONS.pop(user.id, None)
        await msg.reply_text(result, reply_markup=_back())
        raise ApplicationHandlerStop
    if action == "broadcast_message":
        kind = session["kind"]
        pool = get_pool()
        if kind == "private":
            targets = await pool.fetch("SELECT user_id AS chat_id,'private' AS chat_type,'' AS title,'' AS username FROM developer_private_starts")
        elif kind == "groups":
            targets = await pool.fetch("SELECT chat_id,chat_type,title,username FROM developer_bot_chats WHERE active=1 AND chat_type IN ('group','supergroup')")
        elif kind == "channels":
            targets = await pool.fetch("SELECT chat_id,chat_type,title,username FROM developer_bot_chats WHERE active=1 AND chat_type='channel'")
        else:
            targets = await pool.fetch("SELECT user_id AS chat_id,'private' AS chat_type,'' AS title,'' AS username FROM developer_private_starts UNION ALL SELECT chat_id,chat_type,title,username FROM developer_bot_chats WHERE active=1")
        row = await pool.fetchrow(
            """INSERT INTO developer_broadcasts(sender_id,sender_name,source_chat_id,source_message_id,broadcast_type)
               VALUES($1,$2,$3,$4,$5) RETURNING id""",
            user.id, user.first_name or "", msg.chat_id, msg.message_id, kind,
        )
        bid = int(row["id"])
        ok = failed = 0
        for target in targets:
            target_id = int(target["chat_id"])
            try:
                sent = await context.bot.copy_message(
                    chat_id=target_id, from_chat_id=msg.chat_id, message_id=msg.message_id
                )
                await pool.execute(
                    """INSERT INTO developer_broadcast_targets(broadcast_id,chat_id,chat_type,title,username,sent_message_id,success)
                       VALUES($1,$2,$3,$4,$5,$6,1)""",
                    bid, target_id, target["chat_type"], target["title"] or "", target["username"] or "", sent.message_id,
                )
                ok += 1
            except Exception as exc:
                await pool.execute(
                    """INSERT INTO developer_broadcast_targets(broadcast_id,chat_id,chat_type,title,username,success,error)
                       VALUES($1,$2,$3,$4,$5,0,$6)""",
                    bid, target_id, target["chat_type"], target["title"] or "", target["username"] or "", str(exc)[:1000],
                )
                failed += 1
            await asyncio.sleep(0.04)
        SESSIONS.pop(user.id, None)
        await msg.reply_text(f"تمت الإذاعة ✅\n\nنجح الإرسال: {ok}\nفشل الإرسال: {failed}", reply_markup=_back())
        raise ApplicationHandlerStop


async def track_private_start(user):
    if not user:
        return
    await get_pool().execute(
        """INSERT INTO developer_private_starts(user_id,username,first_name)
           VALUES($1,$2,$3) ON CONFLICT(user_id) DO UPDATE SET
           username=EXCLUDED.username,first_name=EXCLUDED.first_name,last_start_at=NOW()""",
        int(user.id), user.username or "", user.first_name or "",
    )


async def track_bot_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.my_chat_member
    if not member or member.chat.type not in ("group", "supergroup", "channel"):
        return
    chat = member.chat
    active = member.new_chat_member.status not in ("left", "kicked")
    await get_pool().execute(
        """INSERT INTO developer_bot_chats(chat_id,chat_type,title,username,active)
           VALUES($1,$2,$3,$4,$5) ON CONFLICT(chat_id) DO UPDATE SET
           chat_type=EXCLUDED.chat_type,title=EXCLUDED.title,username=EXCLUDED.username,
           active=EXCLUDED.active,updated_at=NOW()""",
        chat.id, chat.type, chat.title or "", chat.username or "", 1 if active else 0,
    )
