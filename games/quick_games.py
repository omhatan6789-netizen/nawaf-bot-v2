from __future__ import annotations
import json, random, time, uuid
from database.pool import get_pool

def _j(v): return json.loads(v) if isinstance(v,str) else (v or {})
def _public(r, uid):
    p,s,st=_j(r["players"]),_j(r["settings"]),_j(r["state"])
    out={"id":r["id"].hex,"game_type":r["game_type"],"mode":r["mode"],"status":r["status"],"owner_id":int(r["owner_id"]),"is_owner":int(r["owner_id"])==int(uid),"players":p,"settings":s,"round":int(st.get("round",1)),"phase":st.get("phase","waiting"),"scores":st.get("scores",{}),"target_ms":st.get("target_ms") if st.get("phase") in ("show_target","results") else None,"deadline":st.get("deadline"),"results":st.get("results",[]),"winner_id":st.get("winner_id"),"eliminated":st.get("eliminated",[]),"shuffle":st.get("shuffle",[]),"cups":s.get("cups",5),"difficulty":s.get("difficulty","متوسط"),"win_target":s.get("win_target",5)}
    me=str(uid)
    out["my_choice"]=st.get("choices",{}).get(me)
    out["my_elapsed_ms"]=st.get("stops",{}).get(me)
    out["active_players"]=st.get("active_players",[])
    return out

async def create_game(uid,name,game_type,mode="online",settings=None,bot_name="البوت"):
    if game_type not in ("cups","timer") or mode not in ("online","bot"): raise ValueError("إعدادات اللعبة غير صالحة")
    settings=dict(settings or {})
    if game_type=="cups":
        cups=int(settings.get("cups",6))
        if not 3<=cups<=12: raise ValueError("عدد الأكواب من 3 إلى 12")
        difficulty=settings.get("difficulty","متوسط")
        if difficulty not in ("سهل","متوسط","صعب","مستحيل"): raise ValueError("مستوى الصعوبة غير صالح")
        settings={"cups":cups,"difficulty":difficulty}
    else:
        target=int(settings.get("win_target",5))
        if not 1<=target<=20: raise ValueError("النقاط المطلوبة من 1 إلى 20")
        difficulty=settings.get("difficulty","متوسط")
        if difficulty not in ("سهل","متوسط","صعب","مستحيل"): raise ValueError("مستوى الصعوبة غير صالح")
        settings={"win_target":target,"difficulty":difficulty}
    uid=int(uid); players=[{"id":uid,"name":str(name or "لاعب")[:80]}]
    if mode=="bot": players.append({"id":-1,"name":str(bot_name or "البوت")[:80],"bot":True})
    state={"round":1,"phase":"waiting","scores":{str(p["id"]):0 for p in players},"active_players":[int(p["id"]) for p in players],"choices":{},"stops":{},"results":[],"eliminated":[]}
    pool=get_pool(); gid=uuid.uuid4()
    row=await pool.fetchrow("""INSERT INTO quick_game_rooms(id,game_type,owner_id,owner_name,mode,status,players,settings,state)
      VALUES($1,$2,$3,$4,$5,'waiting',$6::jsonb,$7::jsonb,$8::jsonb) RETURNING *""",gid,game_type,uid,players[0]["name"],mode,json.dumps(players,ensure_ascii=False),json.dumps(settings,ensure_ascii=False),json.dumps(state,ensure_ascii=False))
    return _public(row,uid)

async def join_game(uid,name,raw):
    gid=uuid.UUID(hex=str(raw).replace("-","")); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        r=await c.fetchrow("SELECT * FROM quick_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not r: raise ValueError("الغرفة غير موجودة")
        p=_j(r["players"])
        if r["status"]=="waiting" and not any(int(x["id"])==int(uid) for x in p):
            if len(p)>=4: raise ValueError("الغرفة مكتملة، الحد الأقصى 4 لاعبين")
            p.append({"id":int(uid),"name":str(name or "لاعب")[:80]})
            st=_j(r["state"]); st["scores"][str(uid)]=0; st["active_players"].append(int(uid))
            r=await c.fetchrow("UPDATE quick_game_rooms SET players=$2::jsonb,state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(p,ensure_ascii=False),json.dumps(st,ensure_ascii=False))
    return _public(r,uid)

async def configure_game(uid,raw,settings):
    gid=uuid.UUID(hex=str(raw).replace("-","")); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        r=await c.fetchrow("SELECT * FROM quick_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not r or int(r["owner_id"])!=int(uid) or r["status"]!="waiting": raise ValueError("لا يمكن تعديل الإعدادات")
        s=_j(r["settings"])
        if r["game_type"]=="cups":
            n=int(settings.get("cups",s["cups"])); d=settings.get("difficulty",s["difficulty"])
            if not 3<=n<=12 or d not in ("سهل","متوسط","صعب","مستحيل"): raise ValueError("إعدادات الأكواب غير صالحة")
            s.update({"cups":n,"difficulty":d})
        else:
            n=int(settings.get("win_target",s["win_target"]))
            if not 1<=n<=20: raise ValueError("النقاط المطلوبة من 1 إلى 20")
            s["win_target"]=n
        r=await c.fetchrow("UPDATE quick_game_rooms SET settings=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(s,ensure_ascii=False))
    return _public(r,uid)

async def start_game(uid,raw):
    gid=uuid.UUID(hex=str(raw).replace("-","")); pool=get_pool()
    async with pool.acquire() as c:
      async with c.transaction():
        r=await c.fetchrow("SELECT * FROM quick_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not r or int(r["owner_id"])!=int(uid) or r["status"]!="waiting": raise ValueError("لا يمكن بدء الغرفة")
        p=_j(r["players"])
        if len(p)<2: raise ValueError("تحتاج لاعبين على الأقل")
        st=_j(r["state"]); st["phase"]="show_target" if r["game_type"]=="timer" else "shuffle"
        st["round_started"]=time.time(); st["deadline"]=time.time()+4 if r["game_type"]=="timer" else time.time()+2
        if r["game_type"]=="timer": st["target_ms"]=random.randint(5000,90000)
        else:
            st["ball_index"]=random.randrange(int(_j(r["settings"])["cups"]))
            st["shuffle"]=[{"a":random.randrange(int(_j(r["settings"])["cups"])),"b":random.randrange(int(_j(r["settings"])["cups"]))} for _ in range(18 if _j(r["settings"])["difficulty"] in ("صعب","مستحيل") else 12)]
            perm=list(range(int(_j(r["settings"])["cups"])))
            for move in st["shuffle"]: perm[move["a"]],perm[move["b"]]=perm[move["b"]],perm[move["a"]]
            st["ball_index"]=perm.index(st["ball_index"])
            st["choices"]={}
        r=await c.fetchrow("UPDATE quick_game_rooms SET status='playing',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
    return _public(r,uid)

async def _finish(conn,r,p,st):
    from database.game_stats import record_game_results
    winners=[]; losers=[]
    win=int(st.get("winner_id",0))
    for x in p:
        if x.get("bot"): continue
        (winners if int(x["id"])==win else losers).append(x)
    if winners or losers: await record_game_results(f"quick:{r['id']}",r["game_type"],winners,losers,conn=conn)

async def game_action(uid,raw,move):
    gid=uuid.UUID(hex=str(raw).replace("-","")); pool=get_pool(); now=time.time()
    async with pool.acquire() as c:
      async with c.transaction():
        r=await c.fetchrow("SELECT * FROM quick_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not r or r["status"]!="playing": raise ValueError("اللعبة غير متاحة")
        p,st,s=_j(r["players"]),_j(r["state"]),_j(r["settings"]); me=int(uid); ids=[int(x["id"]) for x in p]
        if me not in ids: raise ValueError("أنت لست لاعبًا في الغرفة")
        if r["game_type"]=="cups":
            if st.get("phase")!="choose": raise ValueError("انتظر انتهاء خلط الأكواب")
            idx=int(move.get("cup",-1))
            if not 0<=idx<int(s["cups"]): raise ValueError("اختر كوبًا صحيحًا")
            if me not in st["active_players"]: raise ValueError("تم استبعادك")
            if str(me) in st["choices"]: raise ValueError("تم تسجيل اختيارك بالفعل")
            st["choices"][str(me)]=idx
            if r["mode"]=="bot" and -1 in st["active_players"] and "-1" not in st["choices"]:
                d=s["difficulty"]; chance={"سهل":.25,"متوسط":.5,"صعب":.75,"مستحيل":.92}[d]
                st["choices"]["-1"]=st["ball_index"] if random.random()<chance else random.choice([i for i in range(s["cups"]) if i!=st["ball_index"]])
            if all(str(i) in st["choices"] for i in st["active_players"]):
                result=[]
                for i in st["active_players"]:
                    x=next(x for x in p if int(x["id"])==i)
                    ok=int(st["choices"][str(i)])==int(st["ball_index"])
                    result.append({"id":i,"name":x["name"],"correct":ok})
                st["results"]=result
                alive=[x["id"] for x in result if x["correct"]]
                for survivor in alive: st["scores"][str(survivor)]=int(st["scores"].get(str(survivor),0))+1
                if len(alive)<=1:
                    st["winner_id"]=alive[0] if alive else 0
                    st["phase"]="finished"; st["eliminated"]=[x["id"] for x in result if not x["correct"]]
                    r=await c.fetchrow("UPDATE quick_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
                    await _finish(c,r,p,st)
                else:
                    st["eliminated"]=[x["id"] for x in result if not x["correct"]]; st["active_players"]=alive; st["round"]+=1
                    st["ball_index"]=random.randrange(s["cups"]); st["choices"]={}; st["phase"]="shuffle"; st["deadline"]=now+2
                    st["shuffle"]=[{"a":random.randrange(s["cups"]),"b":random.randrange(s["cups"])} for _ in range(18 if s["difficulty"] in ("صعب","مستحيل") else 12)]
                    perm=list(range(s["cups"]))
                    for move in st["shuffle"]: perm[move["a"]],perm[move["b"]]=perm[move["b"]],perm[move["a"]]
                    st["ball_index"]=perm.index(st["ball_index"])
                    r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
            else: r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
        else:
            if st.get("phase")!="playing": raise ValueError("انتظر بداية العد")
            if me not in st["active_players"] or str(me) in st["stops"]: raise ValueError("تم تسجيل إيقافك")
            elapsed=int((now-float(st["started_at"]))*1000)
            target=int(st["target_ms"])
            if elapsed>target+30000:
                st["stops"][str(me)]=None; st["eliminated"].append(me)
            else: st["stops"][str(me)]=elapsed
            if r["mode"]=="bot" and "-1" not in st["stops"]:
                d=random.choice([-.8,-.35,.2,.65]) if s.get("difficulty")=="سهل" else random.choice([-.2,.12,.3]) if s.get("difficulty")=="متوسط" else random.choice([-.02,.015,.035])
                st["stops"]["-1"]=max(1,int(target*(1+d)))
            active=[i for i in st["active_players"] if str(i) in st["stops"]]
            if len(active)==len(st["active_players"]):
                ranked=sorted([(abs(int(st["stops"][str(i)])-target),i) for i in st["active_players"] if st["stops"][str(i)] is not None])
                winner=ranked[0][1] if ranked else 0
                if winner:
                    st["scores"][str(winner)]=int(st["scores"].get(str(winner),0))+1
                    st["round_winner"]=winner
                st["results"]=[{"id":int(x["id"]),"name":x["name"],"elapsed_ms":st["stops"].get(str(x["id"])),"difference_ms":abs(int(st["stops"][str(x["id"])])-target) if st["stops"].get(str(x["id"])) is not None else None,"score":int(st["scores"].get(str(x["id"]),0))} for x in p]
                if winner and int(st["scores"].get(str(winner),0))>=int(s["win_target"]):
                    st["winner_id"]=winner;st["phase"]="finished"
                    r=await c.fetchrow("UPDATE quick_game_rooms SET status='finished',state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
                    await _finish(c,r,p,st)
                else:
                    st["phase"]="results";st["deadline"]=now+5
                    r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
            else: r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
    return _public(r,uid)

async def get_state(uid,raw):
    gid=uuid.UUID(hex=str(raw).replace("-","")); pool=get_pool(); now=time.time()
    async with pool.acquire() as c:
      async with c.transaction():
        r=await c.fetchrow("SELECT * FROM quick_game_rooms WHERE id=$1 FOR UPDATE",gid)
        if not r: raise ValueError("الغرفة غير موجودة")
        if r["status"]=="playing":
            p,st,s=_j(r["players"]),_j(r["state"]),_j(r["settings"])
            if r["game_type"]=="cups" and st.get("phase")=="shuffle" and now>=float(st.get("deadline",0)):
                st["phase"]="choose"; st["deadline"]=None
                if r["mode"]=="bot" and -1 in st["active_players"]:
                    d=s["difficulty"]; st["choices"]={"-1":st["ball_index"] if random.random()<{"سهل":.25,"متوسط":.5,"صعب":.75,"مستحيل":.92}[d] else random.randrange(s["cups"])}
                r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
            elif r["game_type"]=="timer" and st.get("phase")=="show_target" and now>=float(st.get("deadline",0)):
                st["phase"]="playing";st["started_at"]=now;st["deadline"]=now+int(st["target_ms"])/1000+30
                r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
            elif r["game_type"]=="timer" and st.get("phase")=="playing" and now>=float(st.get("deadline",0)):
                for x in st["active_players"]:
                    if str(x) not in st["stops"]: st["stops"][str(x)]=None;st["eliminated"].append(x)
                st["phase"]="results";st["results"]=[{"id":int(x["id"]),"name":x["name"],"elapsed_ms":st["stops"].get(str(x["id"])),"difference_ms":abs(int(st["stops"][str(x["id"])])-int(st["target_ms"])) if st["stops"].get(str(x["id"])) is not None else None,"score":int(st["scores"].get(str(x["id"]),0))} for x in p]
                r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
            elif r["game_type"]=="timer" and st.get("phase")=="results" and now>=float(st.get("deadline",0)):
                st["round"]+=1;st["phase"]="show_target";st["target_ms"]=random.randint(5000,90000);st["stops"]={};st["eliminated"]=[]
                st["deadline"]=now+4;st["started_at"]=None
                r=await c.fetchrow("UPDATE quick_game_rooms SET state=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",gid,json.dumps(st,ensure_ascii=False))
    return _public(r,uid)
