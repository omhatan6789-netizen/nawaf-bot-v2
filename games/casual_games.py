from __future__ import annotations
import json, random, uuid
from database.pool import get_pool

CARD_COUNTS = (12, 16, 20, 24, 30)
LEVELS = ("سهل", "متوسط", "صعب", "مستحيل")

def _obj(value):
    return json.loads(value) if isinstance(value, str) else (value or {})

def _deck(count):
    symbols = ["🍎","🍋","🍇","🍉","🍒","🥝","🍓","🍍","🥥","🥑","🍑","🍊","🫐","🥕","🌽"]
    pairs = (symbols * 2)[:count]
    random.shuffle(pairs)
    return [{"value": v, "matched": False} for v in pairs]

def _initial(game_type, settings, players, mode):
    if game_type == "match":
        return {"cards": _deck(int(settings.get("card_count", 16))), "scores": [0]*len(players),
                "turn_index": 0, "first": None, "second": None, "matched": 0,
                "bot_memory": {}, "bot_pending": False}
    return {"secret": random.randint(int(settings.get("min", 1)), int(settings.get("max", 100))),
            "guesses": [], "winner_id": None, "hint": None, "attempts": {},
            "max_attempts": int(settings.get("attempts", 7))}

def _public(row, uid):
    players = _obj(row["players"]); settings = _obj(row["settings"]); state = _obj(row["state"])
    result = {"id": row["id"].hex, "game_type": row["game_type"], "mode": row["mode"],
              "status": row["status"], "owner_id": int(row["owner_id"]),
              "is_owner": int(row["owner_id"]) == int(uid), "players": players,
              "settings": settings}
    if row["game_type"] == "match":
        result.update({"cards": [{"value": c["value"] if c["matched"] or i in (state.get("first"), state.get("second")) else None,
                                   "matched": bool(c["matched"]), "index": i}
                                  for i,c in enumerate(state.get("cards", []))],
                       "scores": state.get("scores", []), "turn_index": state.get("turn_index",0),
                       "first": state.get("first"), "second": state.get("second"),
                       "bot_pending": bool(state.get("bot_pending")),
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

async def create_game(user_id, name, game_type, mode="bot", settings=None):
    if game_type not in ("match","number"): raise ValueError("اللعبة غير معروفة")
    if mode not in ("bot","online"): raise ValueError("طور اللعب غير صالح")
    settings = dict(settings or {})
    if game_type == "match":
        count = int(settings.get("card_count",16))
        if count not in CARD_COUNTS: raise ValueError("اختر عدد البطاقات من 12 أو 16 أو 20 أو 24 أو 30")
        settings = {"card_count":count, "difficulty":settings.get("difficulty","متوسط")}
    else:
        low, high = int(settings.get("min",1)), int(settings.get("max",100))
        attempts = int(settings.get("attempts",7))
        if low < 0 or high <= low or high-low > 1000000: raise ValueError("نطاق الأرقام غير صالح")
        if not 1 <= attempts <= 30: raise ValueError("عدد المحاولات من 1 إلى 30")
        settings = {"min":low,"max":high,"attempts":attempts,"difficulty":settings.get("difficulty","متوسط")}
    uid = int(user_id); gid = uuid.uuid4()
    players = [{"id":uid,"name":str(name or "لاعب")[:80]}]
    if mode == "bot": players.append({"id":-1,"name":"البوت","bot":True})
    state = _initial(game_type,settings,players,mode)
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
        if row["game_type"]=="match":
            if state.get("bot_pending"): raise ValueError("انتظر حركة البوت")
            if player_index != int(state.get("turn_index",0)): raise ValueError("انتظر دورك")
            idx=int(action.get("index",-1)); cards=state["cards"]
            if idx<0 or idx>=len(cards) or cards[idx]["matched"] or idx in (state.get("first"),state.get("second")): raise ValueError("اختر بطاقة متاحة")
            if state.get("first") is None: state["first"]=idx
            else:
                state["second"]=idx
                a,b=state["first"],state["second"]
                if cards[a]["value"]==cards[b]["value"]:
                    cards[a]["matched"]=cards[b]["matched"]=True
                    state["scores"][player_index]+=1; state["matched"]+=1
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
            guess=int(action.get("guess",-999999))
            if guess < int(settings["min"]) or guess > int(settings["max"]): raise ValueError("الرقم خارج النطاق")
            attempts=state.setdefault("attempts",{}); used=int(attempts.get(str(uid),0))
            if used>=int(settings["attempts"]): raise ValueError("انتهت محاولاتك")
            used+=1; attempts[str(uid)]=used
            hint="صحيح" if guess==state["secret"] else ("أعلى ⬆️" if guess<state["secret"] else "أقل ⬇️")
            state["guesses"].append({"id":uid,"name":players[player_index]["name"],"guess":guess,"hint":hint,"n":used})
            state["hint"]=hint
            if guess==state["secret"]:
                state["winner_id"]=uid
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            else:
                row=await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def bot_turn(raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or row["status"]!="playing": raise ValueError("اللعبة غير متاحة")
        state=_obj(row["state"]); players=_obj(row["players"])
        if row["game_type"]!="match" or not state.get("bot_pending"): return _public(row,int(row["owner_id"]))
        cards=state["cards"]; known=state.setdefault("bot_memory",{})
        available=[i for i,x in enumerate(cards) if not x["matched"]]
        first=state.get("first")
        if first is not None:
            known[str(first)]=cards[first]["value"]
        pairs={}
        for k,v in known.items():
            i=int(k)
            if i in available: pairs.setdefault(v,[]).append(i)
        pair=next((v[:2] for v in pairs.values() if len(v)>=2),None)
        if pair: picks=pair
        else:
            level=(_obj(row["settings"]).get("difficulty","متوسط"))
            random.shuffle(available)
            picks=available[:2]
            if level in ("صعب","مستحيل") and first is not None:
                known[str(first)]=cards[first]["value"]
        if len(picks)==2:
            for i in picks: known[str(i)]=cards[i]["value"]
            if cards[picks[0]]["value"]==cards[picks[1]]["value"]:
                cards[picks[0]]["matched"]=cards[picks[1]]["matched"]=True
                state["scores"][1]+=1;state["matched"]+=1
            state["first"]=state["second"]=None
        state["bot_pending"]=False;state["turn_index"]=0
        status="finished" if state["matched"]>=len(cards)//2 else "playing"
        row=await c.fetchrow("UPDATE casual_game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,status,json.dumps(state,ensure_ascii=False))
    return _public(row,int(row["owner_id"]))

async def get_state(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id)
    row=await get_pool().fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1",gid)
    if not row: raise ValueError("اللعبة غير موجودة")
    return _public(row,uid)
