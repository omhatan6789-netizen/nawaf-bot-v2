from __future__ import annotations
import json, random, uuid, time
from database.pool import get_pool

CARD_COUNTS = (12, 16, 20, 24, 30)
LEVELS = ("سهل", "متوسط", "صعب", "مستحيل")

def _obj(value):
    return json.loads(value) if isinstance(value, str) else (value or {})

def _deck(count):
    symbols = ["🍎","🍋","🍇","🍉","🍒","🥝","🍓","🍍","🥥","🥑","🍑","🍊","🫐","🥕","🌽"]
    pairs = symbols[:count // 2] * 2
    random.shuffle(pairs)
    return [{"value": v, "matched": False, "matched_by": None} for v in pairs]

def _initial(game_type, settings, players, mode):
    if game_type == "match":
        return {"cards": _deck(int(settings.get("card_count", 16))), "scores": [0]*len(players),
                "turn_index": 0, "first": None, "second": None, "matched": 0,
                "bot_memory": {}, "bot_pending": False, "bot_step": 0, "bot_first": None, "bot_reveal": []}
    return {"secret": random.randint(int(settings.get("min", 1)), int(settings.get("max", 100))),
            "guesses": [], "winner_id": None, "hint": None, "attempts": {},
            "max_attempts": int(settings.get("attempts", 7)), "turn_index": 0}

def _reset_deadline(state, settings):
    state["turn_deadline"] = int(time.time()) + int(settings.get("turn_seconds",20))

def _expired(players, state):
    if not state.get("turn_deadline") or int(time.time()) < int(state["turn_deadline"]): return False
    loser = players[int(state.get("turn_index",0))]
    winner = next((p for p in players if int(p["id"]) != int(loser["id"])), None)
    state["winner_id"] = int(winner["id"]) if winner else None
    state["timed_out_id"] = int(loser["id"]); state["end_reason"] = "timeout"
    return True

def _public(row, uid):
    players = _obj(row["players"]); settings = _obj(row["settings"]); state = _obj(row["state"])
    result = {"id": row["id"].hex, "game_type": row["game_type"], "mode": row["mode"],
              "status": row["status"], "owner_id": int(row["owner_id"]),
              "is_owner": int(row["owner_id"]) == int(uid), "players": players,
              "settings": settings, "turn_deadline": state.get("turn_deadline"), "turn_seconds": int(settings.get("turn_seconds",20))}
    if row["game_type"] == "match":
        result.update({"cards": [{"value": c["value"] if c["matched"] or i in (state.get("first"), state.get("second")) or i in state.get("bot_reveal", []) else None,
                                   "matched": bool(c["matched"]), "matched_by": c.get("matched_by"), "index": i}
                                  for i,c in enumerate(state.get("cards", []))],
                       "scores": state.get("scores", []), "turn_index": state.get("turn_index",0),
                       "first": state.get("first"), "second": state.get("second"),
                       "bot_pending": bool(state.get("bot_pending")),
                       "bot_revealing": bool(state.get("bot_reveal")), "bot_step": int(state.get("bot_step",0)),
                       "winner_id": state.get("winner_id"), "matched": state.get("matched",0),
                       "total_pairs": len(state.get("cards",[]))//2})
    else:
        result.update({"min": settings.get("min",1), "max": settings.get("max",100),
                       "max_attempts": settings.get("attempts",7),
                       "guesses": state.get("guesses", []), "hint": state.get("hint"),
                       "winner_id": state.get("winner_id"),
                       "attempts_used": state.get("attempts",{}).get(str(uid),0),
                       "attempts": state.get("attempts",{}) if row["status"]=="finished" else {}})
        if row["status"] == "finished": result["secret"] = state.get("secret")
    return result

async def create_game(user_id, name, game_type, mode="bot", settings=None, bot_name="البوت"):
    if game_type not in ("match","number"): raise ValueError("اللعبة غير معروفة")
    if mode not in ("bot","online"): raise ValueError("طور اللعب غير صالح")
    settings = dict(settings or {})
    if game_type == "match":
        count = int(settings.get("card_count",16))
        if count not in CARD_COUNTS: raise ValueError("اختر عدد البطاقات من 12 أو 16 أو 20 أو 24 أو 30")
        settings = {"card_count":count, "difficulty":settings.get("difficulty","متوسط"), "turn_seconds":int(settings.get("turn_seconds",20))}
    else:
        low, high = int(settings.get("min",1)), int(settings.get("max",100))
        attempts = int(settings.get("attempts",7))
        if low < 0 or high <= low or high-low > 1000000: raise ValueError("نطاق الأرقام غير صالح")
        if not 1 <= attempts <= 30: raise ValueError("عدد المحاولات من 1 إلى 30")
        settings = {"min":low,"max":high,"attempts":attempts,"difficulty":settings.get("difficulty","متوسط"),"turn_seconds":int(settings.get("turn_seconds",20))}
    uid = int(user_id); gid = uuid.uuid4()
    players = [{"id":uid,"name":str(name or "لاعب")[:80]}]
    if mode == "bot": players.append({"id":-1,"name":str(bot_name or "البوت")[:80],"bot":True})
    if not 5 <= int(settings.get("turn_seconds",20)) <= 60: raise ValueError("مدة الدور من 5 إلى 60 ثانية")
    state = _initial(game_type,settings,players,mode)
    state["turn_deadline"] = int(time.time()) + int(settings.get("turn_seconds",20))
    status = "playing" if mode == "bot" else "waiting"
    pool = get_pool()
    row = await pool.fetchrow("""INSERT INTO casual_game_rooms
      (id,game_type,owner_id,owner_name,mode,status,players,settings,state)
      VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb) RETURNING *""",
      gid,game_type,uid,players[0]["name"],mode,status,json.dumps(players,ensure_ascii=False),
      json.dumps(settings,ensure_ascii=False),json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def join_game(user_id, name, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("الغرفة غير موجودة")
        if row["status"]=="waiting":
            players=_obj(row["players"])
            if not any(int(p["id"])==uid for p in players):
                if len(players)>=2: raise ValueError("الغرفة مكتملة")
                players.append({"id":uid,"name":str(name or "لاعب")[:80]})
                await c.execute("UPDATE casual_game_rooms SET players=$2::jsonb,updated_at=NOW() WHERE id=$1",gid,json.dumps(players,ensure_ascii=False))
                row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1",gid)
    return _public(row,uid)

async def game_action(user_id, raw_id, action):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("اللعبة غير موجودة")
        if row["status"]!="playing": raise ValueError("اللعبة لم تبدأ أو انتهت")
        players=_obj(row["players"]); state=_obj(row["state"]); settings=_obj(row["settings"])
        player_index=next((i for i,p in enumerate(players) if int(p["id"])==uid),None)
        if player_index is None: raise ValueError("أنت لست لاعبًا في هذه اللعبة")
        if _expired(players,state):
            row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            return _public(row,uid)
        if row["game_type"]=="match":
            if action.get("action") == "continue":
                if state.get("bot_reveal"):
                    state["bot_reveal"] = []
                    state["bot_step"] = 0
                    state["bot_first"] = None
                elif state.get("first") is not None and state.get("second") is not None:
                    state["first"]=state["second"]=None
                    state["turn_index"]=int(state.pop("next_turn",state.get("turn_index",0)))
                    _reset_deadline(state,settings)
                else:
                    raise ValueError("لا توجد حركة معلقة")
                row=await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
                return _public(row,uid)
            if state.get("bot_pending"): raise ValueError("انتظر حركة البوت")
            if player_index != int(state.get("turn_index",0)): raise ValueError("انتظر دورك")
            state["bot_reveal"]=[]
            idx=int(action.get("index",-1)); cards=state["cards"]
            if idx<0 or idx>=len(cards) or cards[idx]["matched"] or idx in (state.get("first"),state.get("second")): raise ValueError("اختر بطاقة متاحة")
            if state.get("first") is None: state["first"]=idx
            else:
                state["second"]=idx
                a,b=state["first"],state["second"]
                if cards[a]["value"]==cards[b]["value"]:
                    cards[a]["matched"]=cards[b]["matched"]=True
                    cards[a]["matched_by"]=cards[b]["matched_by"]=players[player_index]["name"]
                    state["scores"][player_index]+=1; state["matched"]+=1
                    _reset_deadline(state,settings)
                    state["first"]=state["second"]=None
                else:
                    state["bot_pending"] = (row["mode"]=="bot" and players[(player_index+1)%len(players)].get("bot"))
                    state["next_turn"]= (player_index+1)%len(players)
            if state["matched"]>=len(cards)//2:
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            else:
                row=await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
        else:
            if state.get("winner_id") is not None: raise ValueError("اللعبة انتهت")
            if row["mode"]=="online" and player_index != int(state.get("turn_index",0)): raise ValueError("انتظر دورك")
            guess=int(action.get("guess",-999999))
            if guess < int(settings["min"]) or guess > int(settings["max"]): raise ValueError("الرقم خارج النطاق")
            attempts=state.setdefault("attempts",{}); used=int(attempts.get(str(uid),0))
            if used>=int(settings["attempts"]): raise ValueError("انتهت محاولاتك")
            used+=1; attempts[str(uid)]=used
            hint="صحيح" if guess==state["secret"] else ("أعلى ⬆️" if guess<state["secret"] else "أقل ⬇️")
            state["guesses"].append({"id":uid,"name":players[player_index]["name"],"guess":guess,"hint":hint,"n":used})
            state["hint"]=hint
            exhausted = all(int(attempts.get(str(int(p["id"])),0)) >= int(settings["attempts"]) for p in players if not p.get("bot"))
            if guess==state["secret"]:
                state["winner_id"]=uid
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            elif exhausted:
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            else:
                if row["mode"]=="online": state["turn_index"]=(player_index+1)%len(players)
                _reset_deadline(state,settings)
                row=await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def bot_turn(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or row["status"]!="playing": raise ValueError("اللعبة غير متاحة")
        if int(row["owner_id"])!=uid or row["mode"]!="bot": raise ValueError("حركة البوت غير متاحة لهذه اللعبة")
        state=_obj(row["state"]); players=_obj(row["players"])
        if row["game_type"]!="match" or not state.get("bot_pending"): return _public(row,uid)
        cards=state["cards"]; known=state.setdefault("bot_memory",{})
        available=[i for i,x in enumerate(cards) if not x["matched"]]
        level=_obj(row["settings"]).get("difficulty","متوسط")
        if level=="سهل": known.clear()
        elif level=="متوسط" and len(known)>4:
            known=dict(list(known.items())[-4:]); state["bot_memory"]=known
        elif level=="مستحيل":
            known={str(i):cards[i]["value"] for i in available}; state["bot_memory"]=known
        if int(state.get("bot_step",0)) == 0:
            pairs={}
            for k,v in known.items():
                i=int(k)
                if i in available: pairs.setdefault(v,[]).append(i)
            pair=next((v[:2] for v in pairs.values() if len(v)>=2),None)
            if pair: first=pair[0]
            else:
                choices=[i for i in available if str(i) not in known] or available
                first=random.choice(choices)
            known[str(first)]=cards[first]["value"]
            state["bot_first"]=first; state["bot_reveal"]=[first]; state["bot_step"]=1
        else:
            first=int(state.get("bot_first")); choices=[i for i in available if i!=first]
            pair=next((int(k) for k,v in known.items() if v==cards[first]["value"] and int(k) in choices),None)
            if pair is not None: second=pair
            else:
                unknown=[i for i in choices if str(i) not in known] or choices
                second=random.choice(unknown)
            known[str(second)]=cards[second]["value"]
            matched=cards[first]["value"]==cards[second]["value"]
            state["bot_reveal"]=[first,second]; state["bot_step"]=2; state["bot_first"]=None
            if matched:
                bot_name=players[1]["name"]
                cards[first]["matched"]=cards[second]["matched"]=True
                cards[first]["matched_by"]=cards[second]["matched_by"]=bot_name
                state["scores"][1]+=1; state["matched"]+=1; state["turn_index"]=1; state["bot_pending"]=True
            else:
                state["turn_index"]=0; state["bot_pending"]=False
        status="finished" if state["matched"]>=len(cards)//2 else "playing"
        row=await c.fetchrow("UPDATE casual_game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,status,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)
async def get_state(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("اللعبة غير موجودة")
        players=_obj(row["players"]); state=_obj(row["state"])
        if row["status"]=="playing" and _expired(players,state):
            row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def leave_game(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or row["status"]!="playing": raise ValueError("لا يمكن الانسحاب الآن")
        players=_obj(row["players"]); state=_obj(row["state"])
        if not any(int(p["id"])==uid for p in players): raise ValueError("أنت لست لاعبًا في هذه اللعبة")
        winner=next((p for p in players if int(p["id"])!=uid),None)
        state["winner_id"]=int(winner["id"]) if winner else None
        state["withdrawn_id"]=uid; state["end_reason"]="withdraw"
        row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def configure_game(user_id, raw_id, settings):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or int(row["owner_id"])!=uid: raise ValueError("الإعدادات لصاحب الغرفة فقط")
        if row["status"]!="waiting": raise ValueError("لا يمكن تعديل الإعدادات بعد بدء اللعبة")
        current=_obj(row["settings"])
        if row["game_type"]=="match":
            count=int(settings.get("card_count",current.get("card_count",16)))
            if count not in CARD_COUNTS: raise ValueError("اختر 12 أو 16 أو 20 أو 24 أو 30 بطاقة")
            current["card_count"]=count
        else:
            low=int(settings.get("min",current.get("min",1))); high=int(settings.get("max",current.get("max",100)))
            attempts=int(settings.get("attempts",current.get("attempts",7)))
            if low<0 or high<=low or high-low>1000000: raise ValueError("نطاق الأرقام غير صالح")
            if not 1<=attempts<=30: raise ValueError("عدد المحاولات من 1 إلى 30")
            current.update({"min":low,"max":high,"attempts":attempts})
        if not 5 <= int(current.get("turn_seconds",20)) <= 60: raise ValueError("مدة الدور من 5 إلى 60 ثانية")
        state=_initial(row["game_type"],current,_obj(row["players"]),row["mode"])
        state["turn_deadline"] = int(time.time()) + int(current.get("turn_seconds",20))
        row=await c.fetchrow("UPDATE casual_game_rooms SET settings=$2::jsonb,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(current,ensure_ascii=False),json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def start_game(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or int(row["owner_id"])!=uid: raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
        if row["status"]!="waiting": raise ValueError("الغرفة بدأت بالفعل")
        players=_obj(row["players"])
        if len(players)<2: raise ValueError("تحتاج لاعبين على الأقل")
        state=_initial(row["game_type"],_obj(row["settings"]),players,"online")
        state["turn_deadline"] = int(time.time()) + int(_obj(row["settings"]).get("turn_seconds",20))
        row=await c.fetchrow("UPDATE casual_game_rooms SET status='playing',mode='online',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)
