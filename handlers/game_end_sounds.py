from __future__ import annotations
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, ContextTypes
from database.pool import get_pool

OWNER_ID = 8453977662
SESSIONS: dict[int, dict] = {}
GAMES = [
    ("number", "خمن الرقم 🔢"), ("match", "تطابق البطاقات 🃏"),
    ("connect", "كونكت 4 🔴"), ("dots", "المربعات"),
    ("memory", "الذاكرة 🧠"), ("word_guess", "خمن الكلمة"),
    ("image_guess", "توقع الصورة"), ("demon", "ديمون نواف"),
]
def _scope_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 لكل الألعاب", callback_data="gamesound:scope:all")],
        [InlineKeyboardButton("🎮 لعبة معينة", callback_data="gamesound:choose")],
        [InlineKeyboardButton("إلغاء", callback_data="gamesound:cancel")],
    ])
def _games_keyboard():
    rows = [[InlineKeyboardButton(label, callback_data=f"gamesound:game:{key}")] for key,label in GAMES]
    rows.append([InlineKeyboardButton("↩️ رجوع", callback_data="gamesound:menu")])
    return InlineKeyboardMarkup(rows)
async def game_end_sound_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg,user,chat=update.effective_message,update.effective_user,update.effective_chat
    if not msg or not user or not chat or chat.type!="private" or user.id!=OWNER_ID: return
    SESSIONS.pop(user.id,None)
    await msg.reply_text("🔊 إعداد صوت الفوز\nاختر وين تبي تطبق الصوت:",reply_markup=_scope_keyboard())
    raise ApplicationHandlerStop
async def game_end_sound_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.from_user: return
    if q.from_user.id!=OWNER_ID:
        await q.answer("هذا الإعداد للمالك فقط",show_alert=True); return
    data=q.data or ""; await q.answer(); uid=q.from_user.id
    if data=="gamesound:cancel":
        SESSIONS.pop(uid,None); await q.edit_message_text("تم الإلغاء.")
    elif data=="gamesound:menu":
        await q.edit_message_text("اختر نوع التخصيص:",reply_markup=_scope_keyboard())
    elif data=="gamesound:choose":
        await q.edit_message_text("اختر اللعبة التي تبي تخصص صوتها:",reply_markup=_games_keyboard())
    elif data.startswith("gamesound:scope:") or data.startswith("gamesound:game:"):
        scope="all" if data.startswith("gamesound:scope:") else data.split(":",2)[2]
        SESSIONS[uid]={"scope":scope,"step":"media"}
        label="كل الألعاب" if scope=="all" else dict(GAMES).get(scope,"اللعبة")
        await q.edit_message_text(f"ارسل الآن الصوت أو الفيديو لعدّ الفوز في «{label}».\nالصيغ المقبولة: ملف صوتي أو رسالة صوتية أو فيديو، بحد أقصى 20 ميجابايت.\nاكتب إلغاء للتراجع.")
async def game_end_sound_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg,user,chat=update.effective_message,update.effective_user,update.effective_chat
    if not msg or not user or not chat or chat.type!="private" or user.id!=OWNER_ID: return
    session=SESSIONS.get(user.id)
    if not session: return
    if (msg.text or "").strip() in ("إلغاء","الغاء","الغاء الامر"):
        SESSIONS.pop(user.id,None); await msg.reply_text("تم إلغاء إعداد صوت الفوز."); raise ApplicationHandlerStop
    media=msg.audio or msg.voice or msg.video
    if msg.document and (msg.document.mime_type or "").startswith(("audio/","video/")): media=msg.document
    if not media:
        await msg.reply_text("ارسل ملفًا صوتيًا أو رسالة صوتية أو فيديو، أو اكتب إلغاء."); raise ApplicationHandlerStop
    size=getattr(media,"file_size",0) or 0
    if size>20*1024*1024:
        await msg.reply_text("الملف أكبر من 20 ميجابايت. أرسل ملفًا أصغر."); raise ApplicationHandlerStop
    mime=getattr(media,"mime_type",None) or ("video/mp4" if msg.video else "audio/ogg" if msg.voice else "audio/mpeg")
    scope=session["scope"]
    await get_pool().execute(
      """INSERT INTO game_end_sounds(scope_key,file_id,mime_type,media_kind,updated_by,updated_at)
         VALUES($1,$2,$3,$4,$5,NOW()) ON CONFLICT(scope_key) DO UPDATE SET
         file_id=EXCLUDED.file_id,mime_type=EXCLUDED.mime_type,media_kind=EXCLUDED.media_kind,
         updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
      scope,media.file_id,mime,"video" if mime.startswith("video/") or msg.video else "audio",user.id)
    SESSIONS.pop(user.id,None)
    label="كل الألعاب" if scope=="all" else dict(GAMES).get(scope,"اللعبة المحددة")
    await msg.reply_text(f"تم حفظ صوت الفوز لـ «{label}» بنجاح ✅\nالصوت الخاص باللعبة له الأولوية، وإذا ما لها صوت خاص تستخدم الصوت العام.")
    raise ApplicationHandlerStop
