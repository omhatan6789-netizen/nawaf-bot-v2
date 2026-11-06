from __future__ import annotations
import json, random, uuid, unicodedata
from datetime import datetime, timezone
from database.pool import get_pool

WORDS = [
"سيارة","مدرسة","مكتبة","طائرة","حاسوب","هاتف","نافذة","حديقة","مفتاح","مصباح","نواف","أمين","خالد","فهد","سارة","ليان",
"وسادة","حقيبة","ساعة","مرآة","ثلاجة","غسالة","مروحة","تلفاز","سفينة","قطار",
"دراجة","مظلة","طاولة","كرسي","قلم","دفتر","كتاب","ملعقة","شوكة","سكين",
"برتقال","تفاحة","موزة","فراولة","بطيخ","ليمون","عنب","تمر","قهوة","شاي",
"أسد","نمر","فيل","زرافة","حصان","أرنب","سلحفاة","دلفين","صقر","حمامة",
"مطرقة","مفك","منشار","كماشة","مسمار","مفتاح","خوذة","حذاء","معطف","نظارة",
"مستشفى","مطار","مسجد","ملعب","متحف","مطعم","فندق","سوق","شاطئ","جبل",
"قمر","شمس","نجمة","سحابة","مطر","بحر","نهر","صحراء","غابة","جزيرة",
"كرة","مضرب","شبكة","خوذة","درع","سيف","قوس","سهم","درع","خريطة"
]
def _decode(v):
    return json.loads(v) if isinstance(v,str) else (v or {})
def _fold(text):
    s=unicodedata.normalize("NFKC",str(text or "")).strip().replace("ـ","")
    s="".join(ch for ch in s if unicodedata.category(ch) not in ("Mn","Me"))
    s=s.translate(str.maketrans({"أ":"ا","إ":"ا","آ":"ا","ٱ":"ا","ى":"ي","ؤ":"و","ئ":"ي","ة":"ه"}))
    return s
def _letter_class(target, guess, i):
    if guess[i] == target[i]:
        return "green"
    if guess[i] in target:
        return "orange"
    # Arabic orthographic variants: ة/ه and hamza/alef forms are accepted equivalently.
    folded_target, folded_guess = _fold(target), _fold(guess)
    if i < len(folded_target) and i < len(folded_guess) and folded_guess[i] == folded_target[i]:
        return "green_purple"
    if folded_guess[i] in folded_target:
        return "yellow_purple"
    return "white"
def word_feedback(target, guess):
    if len(guess) != len(target):
        return None
    tf,gf=_fold(target),_fold(guess)
    result=[None]*len(target)
    remaining=list(tf)
    for i in range(len(target)):
        if gf[i]==tf[i]:
            result[i]="green" if guess[i]==target[i] else "green_purple"
            remaining[i]=None
    for i in range(len(target)):
        if result[i] is not None: continue
        try:
            pos=remaining.index(gf[i])
        except ValueError:
            result[i]="white"
            continue
        result[i]="orange" if guess[i]==target[pos] else "yellow_purple"
        remaining[pos]=None
    return result
def _new_words(count):
    pool=list(dict.fromkeys(WORDS))
    random.shuffle(pool)
    return pool[:count]
def _public_word(row,user_id):
    players=_decode(row["players"])
    me=next((p for p in players if int(p["id"])==int(user_id)),None)
    answers=_decode(row["answers"])
    word_list=_decode(row["words"])
    winner=None
    if players and row["status"]=="finished":
        high=max(int(p.get("score",0)) for p in players)
        leaders=[p for p in players if int(p.get("score",0))==high]
        winner=leaders[0]["name"] if len(leaders)==1 else "تعادل"
    return {"id":str(row["id"]),"mode":row["mode"],"status":row["status"],
      "word_limit":row["word_limit"],"win_target":row["win_target"],
      "current_index":row["current_index"],"total":row["word_limit"],
      "players":[{"id":p["id"],"name":p["name"],"score":p.get("score",0)} for p in players],
      "my_score":me.get("score",0) if me else 0,"is_player":bool(me),
      "current_word_length":len(word_list[row["current_index"]]) if row["status"]=="playing" and row["current_index"]<len(word_list) else None,
      "round_until":int(row["round_until"].timestamp()*1000) if row["round_until"] else None,
      "round_winner":answers.get("last_winner"),"last_word":answers.get("last_word"),
      "last_feedback":answers.get("last_feedback"),"last_guess":answers.get("last_guess"),"answers":answers,
      "words":word_list if row["status"]=="finished" else [],
      "winner":winner,
      "started_at":int(row["started_at"].timestamp()*1000) if row["started_at"] else None}
async def word_create(user_id,name,mode="online",word_count=5,win_target=None):
    if not 1<=int(word_count)<=15: raise ValueError("اختر من 1 إلى 15 كلمة")
    if mode not in ("online","training"): raise ValueError("طور اللعبة غير صالح")
    target=max(1,min(int(win_target or word_count),int(word_count)))
    gid=uuid.uuid4(); words=_new_words(int(word_count))
    players=[{"id":int(user_id),"name":str(name or "لاعب")[:80],"score":0}]
    status="playing" if mode=="training" else "waiting"
    pool=get_pool()
    row=await pool.fetchrow("""INSERT INTO word_games(id,owner_id,mode,status,max_players,word_limit,win_target,words,players,started_at)
      VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,CASE WHEN $4='playing' THEN NOW() ELSE NULL END) RETURNING *""",
      gid,int(user_id),mode,status,1 if mode=="training" else 10,int(word_count),target,json.dumps(words,ensure_ascii=False),json.dumps(players,ensure_ascii=False))
    return _public_word(row,user_id)
async def word_join(user_id,name,raw_id):
    try: gid=uuid.UUID(hex=str(raw_id).replace("-",""))
    except Exception: raise ValueError("رابط الغرفة غير صالح")
    pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("الغرفة غير موجودة")
        if row["status"]!="waiting": return _public_word(row,user_id)
        players=_decode(row["players"])
        if not any(int(p["id"])==int(user_id) for p in players):
          if len(players)>=10: raise ValueError("اكتمل عدد اللاعبين")
          players.append({"id":int(user_id),"name":str(name or "لاعب")[:80],"score":0})
          await c.execute("UPDATE word_games SET players=$2::jsonb,updated_at=NOW() WHERE id=$1",gid,json.dumps(players,ensure_ascii=False))
        row=await c.fetchrow("SELECT * FROM word_games WHERE id=$1",gid)
    return _public_word(row,user_id)
async def word_start(user_id,raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); pool=get_pool()
    row=await pool.fetchrow("SELECT * FROM word_games WHERE id=$1",gid)
    if not row or int(row["owner_id"])!=int(user_id): raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
    if row["status"]!="waiting": raise ValueError("اللعبة بدأت بالفعل")
    if len(_decode(row["players"]))<2: raise ValueError("تحتاج لاعبين على الأقل")
    await pool.execute("UPDATE word_games SET status='playing',started_at=NOW(),updated_at=NOW() WHERE id=$1",gid)
    return await word_state(user_id,raw_id)
async def word_state(user_id,raw_id):
    try: gid=uuid.UUID(hex=str(raw_id).replace("-",""))
    except Exception: raise ValueError("رابط اللعبة غير صالح")
    row=await get_pool().fetchrow("SELECT * FROM word_games WHERE id=$1",gid)
    if not row: raise ValueError("الغرفة غير موجودة")
    return _public_word(row,user_id)
async def word_guess(user_id,raw_id,guess):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); guess=str(guess or "").strip()
    pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE",gid)
        if not row or row["status"]!="playing": raise ValueError("اللعبة غير نشطة")
        players=_decode(row["players"]); me=next((p for p in players if int(p["id"])==int(user_id)),None)
        if not me: raise ValueError("أنت متفرج ولا يمكنك الإجابة")
        answers=_decode(row["answers"]); words=_decode(row["words"]); i=int(row["current_index"])
        if answers.get("last_winner") and row["round_until"] is not None: raise ValueError("انتظر انتقال الجولة التالية")
        if row["round_until"] and row["round_until"]>datetime.now(timezone.utc): raise ValueError("انتظر انتهاء عرض الإجابة")
        target=words[i]
        if len(guess) != len(target): raise ValueError("عدد الحروف غير مطابق للكلمة")
        if _fold(guess)==_fold(target):
          me["score"]=int(me.get("score",0))+1
          answers={"last_winner":me["name"],"last_word":target,"last_guess":guess,"last_feedback":word_feedback(target,guess),"last_user_id":int(user_id)}
          await c.execute("""UPDATE word_games SET players=$2::jsonb,answers=$3::jsonb,round_until=CASE WHEN mode='online' THEN NOW()+INTERVAL '3 seconds' ELSE NOW() END,updated_at=NOW() WHERE id=$1""",
            gid,json.dumps(players,ensure_ascii=False),json.dumps(answers,ensure_ascii=False))
          return {"correct":True,"round_winner":me["name"],"word":target,"guess":guess,"feedback":word_feedback(target,guess),"round_until":int((datetime.now(timezone.utc).timestamp()+3)*1000)}
        feedback=word_feedback(target,guess)
        return {"correct":False,"feedback":feedback}
async def word_next(user_id,raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("الغرفة غير موجودة")
        if row["status"]!="playing": return _public_word(row,user_id)
        players=_decode(row["players"])
        if not any(int(p["id"])==int(user_id) for p in players): raise ValueError("المتفرجون لا يمكنهم الانتقال بين الجولات")
        if row["round_until"] is None: raise ValueError("لا توجد إجابة مكتملة للانتقال")
        if row["round_until"]>datetime.now(timezone.utc): raise ValueError("لم ينته العد التنازلي")
        nxt=int(row["current_index"])+1
        players=_decode(row["players"])
        reached=any(int(p.get("score",0))>=int(row["win_target"]) for p in players)
        status="finished" if nxt>=int(row["word_limit"]) or (row["mode"]=="training" and reached) else "playing"
        await c.execute("UPDATE word_games SET current_index=$2,status=$3,answers='{}'::jsonb,round_until=NULL,updated_at=NOW(),finished_at=CASE WHEN $3='finished' THEN NOW() ELSE finished_at END WHERE id=$1",gid,nxt,status)
    return await word_state(user_id,raw_id)
