from __future__ import annotations
import json, random, uuid, unicodedata
from datetime import datetime, timezone
from database.pool import get_pool

WORDS_BY_LENGTH = {
    4: ["نواف","خالد","أمين","سارة","ليان","سامي","رامي","مازن","زياد","ياسر","ناصر","راشد","صالح","طارق","عادل","وليد","حمزة","حاتم","باسل","مالك","تامر","ماهر","جابر","حازم","عمار","رائد","إياد","جلال","كنان","فارس","حارس","لاعب","فريق","نحاس","حديد","زجاج","قماش","تراب","هواء","دخان","رماد","جدار","دجاج","حليب","سكين","كتاب","دفتر","ذراع","أصبع","مطار","مسجد","ملعب","متحف","فندق","شاطئ","غابة","مضرب","شبكة","حروف","نجوم","ورود","قلوب","عيون","أيام","أسود","أبيض","أحمر","أزرق","أخضر","كبير","صغير","جميل","سريع","هادئ","سعيد","حزين","ضعيف","طويل","قصير","جديد","قديم","ثقيل","خفيف","قريب","بعيد","نظيف","واضح","غامض","صادق","كاذب","شجاع","جبان","كريم","بخيل","لطيف","نشيط","كسول","مدرب","كورة","سحاب","رياح","شتاء","ربيع","خريف","صباح","مساء","طريق","شارع","قرية","دولة","عالم","وادي","قارب","مركب","حذاء","قميص","قبعة","ساعة","خاتم","سوار","مكتب","كرسي","سرير","مكيف","هاتف","شاشة","لوحة","فأرة","جهاز","موقع","صفحة","بريد","حساب","كلمة","صورة","لعبة","فكرة","سؤال","جواب","عربي","مربع","مثلث","كوكب","فضاء","سماء","ضباب","شجرة","زهرة","وردة","ثمرة","ورقة","جذور","نبات","طيور","نملة","نحلة","عقرب","أرنب","حصان","حمار","بقرة","ماعز","بلبل","بومة","غراب","ثعلب","غزال","سمكة"],
    5: ["سيارة","مدرسة","مكتبة","طائرة","حاسوب","نافذة","حديقة","مفتاح","مصباح","وسادة","حقيبة","ثلاجة","غسالة","مروحة","تلفاز","سفينة","دراجة","طاولة","ملعقة","تفاحة","ليمون","دلفين","حمامة","مطرقة","منشار","كماشة","مسمار","نظارة","جزيرة","سحابة","صحراء","خريطة","كلمات","ألوان","أصوات","ألعاب","أحلام","أوقات","أرقام","أسماء","مهاجم","بطولة","جائزة","ظهيرة","أسبوع","مدينة","ميناء","حافلة","سروال","عباءة","قلادة","محفظة","صندوق","ستارة","سجادة","سماعة","رسالة","فيديو","رواية","قصيدة","صحيفة","حقيقة","تجربة","دراسة","جامعة","نتيجة","شهادة","مختبر","أسنان","رياضة","سباحة","كتابة","قراءة","تاريخ","أحياء","إيقاع","دائرة","حيوان","أسماك","حشرات","فراشة","ذبابة","بعوضة","ثعبان","سحلية","تمساح","عصفور","طاووس","زرافة"],
}

def _decode(v):
    return json.loads(v) if isinstance(v, str) else (v or {})

def _fold(text):
    s = unicodedata.normalize("NFKC", str(text or "")).strip().replace("ـ", "")
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Me"))
    return s.translate(str.maketrans({"أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ؤ":"و", "ئ":"ي", "ة":"ه"}))

def word_feedback(target, guess):
    if len(guess) != len(target):
        return None
    tf, gf = _fold(target), _fold(guess)
    result = [None] * len(target)
    remaining = list(tf)
    for i in range(len(target)):
        if gf[i] == tf[i]:
            result[i] = "green" if guess[i] == target[i] else "green_purple"
            remaining[i] = None
    for i in range(len(target)):
        if result[i] is not None:
            continue
        try:
            pos = remaining.index(gf[i])
        except ValueError:
            result[i] = "white"
            continue
        result[i] = "orange" if guess[i] == target[pos] else "yellow_purple"
        remaining[pos] = None
    return result

def _new_words(count, length):
    pool = list(WORDS_BY_LENGTH[int(length)])
    random.shuffle(pool)
    return pool[:count]

def _public_word(row, user_id):
    players = _decode(row["players"])
    me = next((p for p in players if int(p["id"]) == int(user_id)), None)
    answers = _decode(row["answers"])
    guesses_by_player = answers.get("guesses") or {}
    my_guesses = guesses_by_player.get(str(int(user_id)), [])
    winner = None
    if players and row["status"] == "finished":
        high = max(int(p.get("score", 0)) for p in players)
        leaders = [p for p in players if int(p.get("score", 0)) == high]
        winner = leaders[0]["name"] if len(leaders) == 1 else "تعادل"
    idx = int(row["current_index"])
    word_list = _decode(row["words"])
    return {
        "id": str(row["id"]), "mode": row["mode"], "status": row["status"],
        "word_limit": row["word_limit"], "win_target": row["win_target"],
        "attempts_limit": row["attempts_limit"], "attempts_left": max(0, int(row["attempts_limit"]) - len(my_guesses)),
        "word_length": row["word_length"], "round_seconds": row["round_seconds"],
        "my_guesses": my_guesses,
        "current_index": idx, "total": row["word_limit"],
        "players": [{"id": p["id"], "name": p["name"], "score": p.get("score", 0)} for p in players],
        "my_score": me.get("score", 0) if me else 0, "is_player": bool(me),
        "current_word_length": int(row["word_length"]) if row["status"] == "playing" else None,
        "round_deadline": int(row["round_deadline"].timestamp() * 1000) if row["round_deadline"] else None,
        "round_until": int(row["round_until"].timestamp() * 1000) if row["round_until"] else None,
        "round_winner": answers.get("round_winner"), "round_word": answers.get("last_word"),
        "round_end_reason": answers.get("round_end_reason"),
        "last_guess": answers.get("last_guess"), "last_feedback": answers.get("last_feedback"),
        "words": word_list if row["status"] == "finished" else [],
        "winner": winner,
        "started_at": int(row["started_at"].timestamp() * 1000) if row["started_at"] else None,
    }

async def word_create(user_id, name, mode="online", word_count=5, win_target=None,
                      attempts_limit=6, word_length=5, round_seconds=180):
    word_count = int(word_count)
    word_length = int(word_length)
    attempts_limit = int(attempts_limit)
    round_seconds = int(round_seconds)
    if not 1 <= word_count <= 15:
        raise ValueError("اختر من 1 إلى 15 كلمة")
    if mode not in ("online", "training"):
        raise ValueError("طور اللعبة غير صالح")
    if word_length not in WORDS_BY_LENGTH:
        raise ValueError("اختر كلمات من 4 أو 5 أحرف")
    if not 1 <= attempts_limit <= 12:
        raise ValueError("عدد المحاولات يجب أن يكون من 1 إلى 12")
    if not 15 <= round_seconds <= 3600:
        raise ValueError("مدة الجولة يجب أن تكون بين 15 و3600 ثانية")
    target = max(1, min(int(win_target or word_count), word_count))
    gid = uuid.uuid4()
    words = _new_words(word_count, word_length)
    players = [{"id": int(user_id), "name": str(name or "لاعب")[:80], "score": 0}]
    status = "playing" if mode == "training" else "waiting"
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO word_games
        (id,owner_id,mode,status,max_players,word_limit,win_target,words,players,
         attempts_limit,word_length,round_seconds,started_at,round_deadline)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,
          CASE WHEN $4='playing' THEN NOW() ELSE NULL END,
          CASE WHEN $4='playing' THEN NOW()+($12::integer * INTERVAL '1 second') ELSE NULL END)
        RETURNING *""",
        gid, int(user_id), mode, status, 1 if mode == "training" else 10,
        word_count, target, json.dumps(words, ensure_ascii=False),
        json.dumps(players, ensure_ascii=False), attempts_limit, word_length, round_seconds
    )
    return _public_word(row, user_id)

async def word_join(user_id, name, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط الغرفة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] != "waiting":
                return _public_word(row, user_id)
            players = _decode(row["players"])
            if not any(int(p["id"]) == int(user_id) for p in players):
                if len(players) >= 10:
                    raise ValueError("اكتمل عدد اللاعبين")
                players.append({"id": int(user_id), "name": str(name or "لاعب")[:80], "score": 0})
                await c.execute("UPDATE word_games SET players=$2::jsonb,updated_at=NOW() WHERE id=$1",
                                gid, json.dumps(players, ensure_ascii=False))
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1", gid)
    return _public_word(row, user_id)

async def word_start(user_id, raw_id):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row or int(row["owner_id"]) != int(user_id):
                raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
            if row["status"] != "waiting":
                raise ValueError("اللعبة بدأت بالفعل")
            if len(_decode(row["players"])) < 2:
                raise ValueError("تحتاج لاعبين على الأقل")
            row = await c.fetchrow(
                """UPDATE word_games SET status='playing',started_at=NOW(),
                round_deadline=NOW()+(round_seconds * INTERVAL '1 second'),
                round_until=NULL,answers='{}'::jsonb,updated_at=NOW()
                WHERE id=$1 RETURNING *""", gid
            )
    return _public_word(row, user_id)

async def word_state(user_id, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] == "playing" and row["round_deadline"] and row["round_deadline"] <= datetime.now(timezone.utc) and row["round_until"] is None:
                words = _decode(row["words"])
                idx = int(row["current_index"])
                answers = _decode(row["answers"])
                answers.update({"last_word": words[idx], "round_end_reason": "timeout"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
    return _public_word(row, user_id)

async def word_guess(user_id, raw_id, guess):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    guess = str(guess or "").strip()
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة غير نشطة")
            players = _decode(row["players"])
            me = next((p for p in players if int(p["id"]) == int(user_id)), None)
            if not me:
                raise ValueError("أنت متفرج ولا يمكنك الإجابة")
            answers = _decode(row["answers"])
            if row["round_until"] is not None:
                raise ValueError("انتهت الجولة، انتظر الكلمة التالية")
            if row["round_deadline"] and row["round_deadline"] <= datetime.now(timezone.utc):
                words = _decode(row["words"])
                answers.update({"last_word": words[int(row["current_index"])], "round_end_reason": "timeout"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
                return {"round_over": True, "state": _public_word(row, user_id)}
            if len(guess) != int(row["word_length"]):
                raise ValueError(f"اكتب كلمة من {row['word_length']} أحرف")
            if any(ch.isspace() for ch in guess):
                raise ValueError("اكتب الكلمة بدون مسافات")
            guesses_by_player = answers.setdefault("guesses", {})
            mine = guesses_by_player.setdefault(str(int(user_id)), [])
            if len(mine) >= int(row["attempts_limit"]):
                raise ValueError("خلصت محاولاتك في هذه الكلمة")
            words = _decode(row["words"])
            target = words[int(row["current_index"])]
            feedback = word_feedback(target, guess)
            mine.append({"guess": guess, "feedback": feedback})
            if _fold(guess) == _fold(target):
                me["score"] = int(me.get("score", 0)) + 1
                answers.update({"round_winner": me["name"], "last_word": target,
                                "last_guess": guess, "last_feedback": feedback,
                                "round_end_reason": "winner"})
                row = await c.fetchrow(
                    """UPDATE word_games SET players=$2::jsonb,answers=$3::jsonb,
                    round_until=NOW()+INTERVAL '3 seconds',round_deadline=NULL,updated_at=NOW()
                    WHERE id=$1 RETURNING *""",
                    gid, json.dumps(players, ensure_ascii=False), json.dumps(answers, ensure_ascii=False)
                )
                return {"correct": True, "state": _public_word(row, user_id)}
            all_out = all(
                len(guesses_by_player.get(str(int(p["id"])), [])) >= int(row["attempts_limit"])
                for p in players
            )
            if all_out:
                answers.update({"last_word": target, "round_end_reason": "attempts"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
            else:
                row = await c.fetchrow(
                    "UPDATE word_games SET answers=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
    return {"correct": False, "feedback": feedback, "state": _public_word(row, user_id)}

async def word_next(user_id, raw_id):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] != "playing":
                return _public_word(row, user_id)
            if not any(int(p["id"]) == int(user_id) for p in _decode(row["players"])):
                raise ValueError("المتفرجون لا يمكنهم الانتقال بين الجولات")
            if row["round_until"] is None:
                return _public_word(row, user_id)
            if row["round_until"] > datetime.now(timezone.utc):
                return _public_word(row, user_id)
            nxt = int(row["current_index"]) + 1
            players = _decode(row["players"])
            reached = any(int(p.get("score", 0)) >= int(row["win_target"]) for p in players)
            status = "finished" if nxt >= int(row["word_limit"]) or (row["mode"] == "training" and reached) else "playing"
            row = await c.fetchrow(
                """UPDATE word_games SET current_index=$2,status=$3,answers='{}'::jsonb,
                round_until=NULL,round_deadline=CASE WHEN $3='playing'
                THEN NOW()+(round_seconds * INTERVAL '1 second') ELSE NULL END,
                updated_at=NOW(),finished_at=CASE WHEN $3='finished' THEN NOW() ELSE finished_at END
                WHERE id=$1 RETURNING *""", gid, nxt, status
            )
    return _public_word(row, user_id)
