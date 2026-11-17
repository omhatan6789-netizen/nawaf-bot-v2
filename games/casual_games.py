from __future__ import annotations
import json, random, uuid, time
from database.pool import get_pool

CARD_COUNTS = (12, 16, 20, 24, 30)
LEVELS = ("سهل", "متوسط", "صعب", "مستحيل")
FIND_ITEMS = ["car","plane","kite","boat","bike","bus","train","truck","rocket","helicopter","balloon","umbrella","camera","clock","headphones","key","crown","gift","house","flower","tree","sun","moon","star","diamond","guitar","football","basketball","pizza","icecream","sailboat","scooter","ship","trophy","lamp","book","glasses","bell","anchor","pencil","watch","camera2"]

def _obj(value):
    return json.loads(value) if isinstance(value, str) else (value or {})

def _deck(count):
    symbols = ["🍎","🍋","🍇","🍉","🍒","🥝","🍓","🍍","🥥","🥑","🍑","🍊","🫐","🥕","🌽"]
    pairs = symbols[:count // 2] * 2
    random.shuffle(pairs)
    return [{"value": v, "matched": False, "matched_by": None} for v in pairs]

def _find_board():
    shared = random.choice(FIND_ITEMS)
    others = random.sample([x for x in FIND_ITEMS if x != shared], 16)
    left = [shared, *others[:8]]
    right = [shared, *others[8:]]
    random.shuffle(left)
    random.shuffle(right)
    return left, right, shared


def _find_reset_round(state, settings, players, mode):
    left, right, target = _find_board()
    state.update({"left_items": left, "right_items": right, "target": target,
                  "round": int(state.get("round", 0)) + 1, "round_winner_id": None, "round_next_at": None, "wrong_by": None})
    if mode == "bot":
        delays = {"سهل": (7.0, 9.0), "متوسط": (5.0, 6.8),
                  "صعب": (3.5, 4.8), "مستحيل": (2.5, 3.4)}
        low, high = delays.get(settings.get("difficulty", "متوسط"), (5.0, 6.8))
        state["bot_due_at"] = time.time() + random.uniform(low, high)


def _initial(game_type, settings, players, mode):
    if game_type == "find":
        state = {"scores": [0] * len(players), "round": 0, "winner_id": None,
                 "round_winner_id": None, "target_score": int(settings.get("target_score", 5))}
        _find_reset_round(state, settings, players, mode)
        return state
    if game_type == "match":
        return {"cards": _deck(int(settings.get("card_count", 16))), "scores": [0]*len(players),
                "turn_index": 0, "first": None, "second": None, "matched": 0,
                "bot_memory": {}, "bot_pending": False, "bot_step": 0, "bot_first": None, "bot_reveal": []}
    return {"secret": random.randint(int(settings.get("min", 1)), int(settings.get("max", 100))),
            "guesses": [], "winner_id": None, "hint": None, "attempts": {},
            "max_attempts": int(settings.get("attempts", 7)), "turn_index": 0}

def _reset_deadline(state, settings):
    state["turn_deadline"] = int(time.time()) + int(settings.get("turn_seconds",20))

def _next_number_player(players, state, settings, after_index):
    attempts = state.setdefault("attempts", {})
    limit = int(settings.get("attempts", 7))
    for offset in range(1, len(players) + 1):
        index = (int(after_index) + offset) % len(players)
        player = players[index]
        if not player.get("bot") and int(attempts.get(str(int(player["id"])), 0)) < limit:
            return index
    return None


def _expired(players, state, settings, game_type):
    if game_type == "find":
        return False
    if not state.get("turn_deadline") or int(time.time()) < int(state["turn_deadline"]):
        return False
    current_index = int(state.get("turn_index", 0)) % len(players)
    loser = players[current_index]
    state["timed_out_id"] = int(loser["id"])
    if len(players) <= 2:
        winner = next((p for p in players if int(p["id"]) != int(loser["id"])), None)
        state["winner_id"] = int(winner["id"]) if winner else None
        state["end_reason"] = "timeout"
        return True
    if game_type == "match":
        state["first"] = state["second"] = None
        state["turn_index"] = (current_index + 1) % len(players)
        state["bot_pending"] = False
        state["bot_reveal"] = []
        state["bot_step"] = 0
        state["bot_first"] = None
        _reset_deadline(state, settings)
        return True
    next_index = _next_number_player(players, state, settings, current_index)
    if next_index is None:
        state["winner_id"] = None
        state["end_reason"] = "timeout"
        return True
    state["turn_index"] = next_index
    _reset_deadline(state, settings)
    return True

async def _record_finished(conn, row):
    """Record every human participant when a casual game reaches finished."""
    if not row or row.get("status") != "finished":
        return
    players, state = _obj(row["players"]), _obj(row["state"])
    humans = [p for p in players if not p.get("bot") and int(p.get("id", 0)) > 0]
    winners, losers = [], []
    if row["game_type"] in ("number", "find"):
        winner_id = state.get("winner_id")
        if winner_id is not None:
            winners = [p for p in humans if int(p["id"]) == int(winner_id)]
            losers = [p for p in humans if int(p["id"]) != int(winner_id)]
        elif state.get("end_reason") == "attempts_exhausted":
            losers = humans[:]
    else:
        winner_id = state.get("winner_id")
        if winner_id is not None:
            winners = [p for p in humans if int(p["id"]) == int(winner_id)]
            losers = [p for p in humans if int(p["id"]) != int(winner_id)]
        else:
            scores = list(state.get("scores") or [])
            if scores and players:
                high = max(scores)
                winning_indexes = {i for i, score in enumerate(scores) if score == high}
                winners = [p for i, p in enumerate(players) if i in winning_indexes and not p.get("bot") and int(p.get("id", 0)) > 0]
                losers = [p for i, p in enumerate(players) if i not in winning_indexes and not p.get("bot") and int(p.get("id", 0)) > 0]
    withdrawn_id = state.get("withdrawn_id")
    if withdrawn_id and int(withdrawn_id) > 0 and not any(int(p["id"]) == int(withdrawn_id) for p in humans):
        losers.append({"id": int(withdrawn_id), "name": "منسحب"})
    if winners or losers:
        from database.game_stats import record_game_results
        await record_game_results(f"casual:{row['id']}", str(row["game_type"]), winners, losers, conn=conn)


def _public(row, uid):
    players = _obj(row["players"]); settings = _obj(row["settings"]); state = _obj(row["state"])
    result = {"id": row["id"].hex, "game_type": row["game_type"], "mode": row["mode"],
              "status": row["status"], "owner_id": int(row["owner_id"]),
              "is_owner": int(row["owner_id"]) == int(uid), "players": players,
              "settings": settings, "turn_deadline": state.get("turn_deadline"), "turn_seconds": int(settings.get("turn_seconds",20)), "end_reason": state.get("end_reason")}
    if row["game_type"] == "find":
        result.update({"left_items": state.get("left_items", []),
                       "right_items": state.get("right_items", []),
                       "round": int(state.get("round", 1)),
                       "round_winner_id": state.get("round_winner_id"),
                       "winner_id": state.get("winner_id"),
                       "scores": state.get("scores", []),
                       "target_score": int(state.get("target_score", 5)),
                       "round_winner_name": next((p.get("name") for p in players if int(p["id"]) == int(state.get("round_winner_id") or 0)), None),
                        "reveal_target": state.get("target") if state.get("round_winner_id") is not None else None,
                       "difficulty": settings.get("difficulty", "متوسط"),
                       "wrong_by": state.get("wrong_by")})
    elif row["game_type"] == "match":
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
                       "turn_index": state.get("turn_index",0),
                       "attempts": state.get("attempts",{}) if row["status"]=="finished" else {}})
        if row["status"] == "finished": result["secret"] = state.get("secret")
    return result

async def create_game(user_id, name, game_type, mode="bot", settings=None, bot_name="البوت"):
    if game_type not in ("match","number","find"): raise ValueError("اللعبة غير معروفة")
    if mode not in ("bot","online"): raise ValueError("طور اللعب غير صالح")
    settings = dict(settings or {})
    if game_type == "find":
        difficulty = settings.get("difficulty", "متوسط")
        if difficulty not in LEVELS: difficulty = "متوسط"
        target_score = max(1, min(10, int(settings.get("target_score", 5))))
        settings = {"difficulty": difficulty, "target_score": target_score, "turn_seconds": 20}
    elif game_type == "match":
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
                max_players = 2 if row["game_type"] == "find" else 4
                if len(players)>=max_players: raise ValueError(f"الغرفة مكتملة، الحد الأقصى {max_players} لاعبين")
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
        if _expired(players, state, settings, row["game_type"]):
            status = "finished" if state.get("end_reason") else "playing"
            row=await c.fetchrow("UPDATE casual_game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,status,json.dumps(state,ensure_ascii=False))
            await _record_finished(c, row)
            return _public(row,uid)
        if row["game_type"] == "find":
            if state.get("winner_id") is not None:
                raise ValueError("انتهت اللعبة")
            if state.get("round_winner_id") is not None:
                raise ValueError("الجولة انتهت، انتظر الجولة التالية")
            if int(action.get("round", state.get("round", 1))) != int(state.get("round", 1)):
                raise ValueError("تغيرت الجولة، ابحث عن الغرض الجديد")
            value = str(action.get("value", ""))
            if value != str(state.get("target", "")):
                # A wrong pick immediately awards the round to the other player.
                other_index = (player_index + 1) % len(players)
                other_player = players[other_index]
                other_id = int(other_player["id"])
                state["scores"][other_index] = int(state["scores"][other_index]) + 1
                state["round_winner_id"] = other_id
                state["wrong_by"] = None
                state["round_next_at"] = time.time() + 2.0
                if state["scores"][other_index] >= int(state.get("target_score", 5)):
                    state["winner_id"] = other_id
                    state["final_due_at"] = time.time() + 2.0
                row = await c.fetchrow(
                    "UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                    gid, json.dumps(state, ensure_ascii=False))
                return _public(row, uid)
            state["scores"][player_index] = int(state["scores"][player_index]) + 1
            state["round_winner_id"] = uid
            state["wrong_by"] = None
            state["round_next_at"] = time.time() + 2.0
            if state["scores"][player_index] >= int(state.get("target_score", 5)):
                state["winner_id"] = uid
                state["final_due_at"] = time.time() + 2.0
            row = await c.fetchrow(
                "UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                gid, json.dumps(state, ensure_ascii=False))
        elif row["game_type"]=="match":
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
                await _record_finished(c, row)
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
            if guess==state["secret"]:
                state["winner_id"]=uid
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
                await _record_finished(c, row)
            else:
                next_index = _next_number_player(players, state, settings, player_index) if row["mode"]=="online" else None
                if row["mode"]=="online" and next_index is None:
                    state["winner_id"] = None
                    state["end_reason"] = "attempts_exhausted"
                    row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
                    await _record_finished(c, row)
                else:
                    if row["mode"]=="online": state["turn_index"]=next_index
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
        if row["game_type"] == "find":
            if row["mode"] != "bot" or int(row["owner_id"]) != uid:
                raise ValueError("حركة البوت غير متاحة لهذه اللعبة")
            now = time.time()
            if state.get("winner_id") is not None and now >= float(state.get("final_due_at", now + 999)):
                row = await c.fetchrow("UPDATE casual_game_rooms SET status='finished',updated_at=NOW() WHERE id=$1 RETURNING *", gid)
                await _record_finished(c, row)
            elif state.get("round_winner_id") is not None and state.get("winner_id") is None and now >= float(state.get("round_next_at", now + 999)):
                _find_reset_round(state, _obj(row["settings"]), players, "bot")
                row = await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *", gid, json.dumps(state, ensure_ascii=False))
            elif state.get("winner_id") is None and state.get("round_winner_id") is None and now >= float(state.get("bot_due_at", 0)):
                bot_index = next((i for i, p in enumerate(players) if p.get("bot")), None)
                if bot_index is not None:
                    state["scores"][bot_index] = int(state["scores"][bot_index]) + 1
                    state["round_winner_id"] = int(players[bot_index]["id"])
                    state["round_next_at"] = now + 2.0
                    if state["scores"][bot_index] >= int(state.get("target_score", 5)):
                        state["winner_id"] = int(players[bot_index]["id"])
                        state["final_due_at"] = now + 2.0
                    row = await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *", gid, json.dumps(state, ensure_ascii=False))
            return _public(row, uid)
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
        if int(state.get("bot_step",0)) == 2:
            _reset_deadline(state, _obj(row["settings"]))
        status="finished" if state["matched"]>=len(cards)//2 else "playing"
        row=await c.fetchrow("UPDATE casual_game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,status,json.dumps(state,ensure_ascii=False))
        await _record_finished(c, row)
    return _public(row,uid)
async def get_state(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row: raise ValueError("اللعبة غير موجودة")
        players=_obj(row["players"]); state=_obj(row["state"])
        if row["status"] == "playing" and row["game_type"] == "find":
            now = time.time()
            if state.get("winner_id") is not None and now >= float(state.get("final_due_at", now + 999)):
                row = await c.fetchrow("UPDATE casual_game_rooms SET status='finished',updated_at=NOW() WHERE id=$1 RETURNING *", gid)
                await _record_finished(c, row)
            elif state.get("round_winner_id") is not None and state.get("winner_id") is None and now >= float(state.get("round_next_at", now + 999)):
                _find_reset_round(state, _obj(row["settings"]), players, row["mode"])
                row = await c.fetchrow("UPDATE casual_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *", gid, json.dumps(state, ensure_ascii=False))
        if row["status"]=="playing" and _expired(players, state, _obj(row["settings"]), row["game_type"]):
            status = "finished" if state.get("end_reason") else "playing"
            row=await c.fetchrow("UPDATE casual_game_rooms SET status=$2,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,status,json.dumps(state,ensure_ascii=False))
            await _record_finished(c, row)
    return _public(row,uid)

async def leave_game(user_id, raw_id):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or row["status"]!="playing": raise ValueError("لا يمكن الانسحاب الآن")
        players=_obj(row["players"]); state=_obj(row["state"])
        if not any(int(p["id"])==uid for p in players): raise ValueError("أنت لست لاعبًا في هذه اللعبة")
        leaving_index = next(i for i,p in enumerate(players) if int(p["id"]) == uid)
        state["withdrawn_id"] = uid
        from database.game_stats import record_game_results
        await record_game_results(
            f"casual:{gid}", str(row["game_type"]), [],
            [{"id": uid, "name": next(p.get("name") or "منسحب" for p in players if int(p["id"]) == uid)}],
            conn=c,
        )
        if len(players) > 2:
            players.pop(leaving_index)
            if row["game_type"] == "match":
                scores = state.get("scores", [])
                if leaving_index < len(scores): scores.pop(leaving_index)
                state["scores"] = scores
                state["first"] = state["second"] = None
                state["bot_pending"] = False
                state["bot_reveal"] = []
            old_turn = int(state.get("turn_index", 0))
            if old_turn > leaving_index: old_turn -= 1
            elif old_turn == leaving_index: old_turn = leaving_index % len(players)
            state["turn_index"] = old_turn
            if row["game_type"] == "number":
                next_index = _next_number_player(players, state, _obj(row["settings"]), old_turn - 1)
                if next_index is not None: state["turn_index"] = next_index
            if len(players) == 1:
                state["end_reason"] = "withdraw"
                state["winner_id"] = int(players[0]["id"])
                row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',players=$2::jsonb,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(players,ensure_ascii=False),json.dumps(state,ensure_ascii=False))
                await _record_finished(c, row)
            else:
                _reset_deadline(state, _obj(row["settings"]))
                row=await c.fetchrow("UPDATE casual_game_rooms SET players=$2::jsonb,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(players,ensure_ascii=False),json.dumps(state,ensure_ascii=False))
        else:
            state["end_reason"] = "withdraw"
            winner=next((p for p in players if int(p["id"])!=uid),None)
            state["winner_id"]=int(winner["id"]) if winner else None
            row=await c.fetchrow("UPDATE casual_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(state,ensure_ascii=False))
            await _record_finished(c, row)
    return _public(row,uid)

async def configure_game(user_id, raw_id, settings):
    gid=uuid.UUID(hex=str(raw_id).replace("-","")); uid=int(user_id); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        row=await c.fetchrow("SELECT * FROM casual_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not row or int(row["owner_id"])!=uid: raise ValueError("الإعدادات لصاحب الغرفة فقط")
        if row["status"]!="waiting": raise ValueError("لا يمكن تعديل الإعدادات بعد بدء اللعبة")
        current=_obj(row["settings"])
        if row["game_type"] == "find":
            difficulty = settings.get("difficulty", current.get("difficulty", "متوسط"))
            if difficulty not in LEVELS: raise ValueError("مستوى اللعبة غير صالح")
            current["difficulty"] = difficulty
            current["target_score"] = max(1, min(10, int(settings.get("target_score", current.get("target_score", 5)))))
        elif row["game_type"]=="match":
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
        await _record_finished(c, row)
    return _public(row,uid)
