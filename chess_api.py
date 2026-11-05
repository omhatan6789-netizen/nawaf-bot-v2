import hashlib, hmac, json, time
from urllib.parse import parse_qsl
import uuid
import chess
from database.pool import get_pool
from chess_engine import choose_ai_move

def telegram_user(init_data, token):
    data = dict(parse_qsl(init_data or "", keep_blank_values=True))
    supplied = data.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k,v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not supplied or not hmac.compare_digest(digest, supplied):
        raise ValueError("تعذر التحقق من حساب تيليجرام")
    if time.time() - int(data.get("auth_date", "0")) > 86400:
        raise ValueError("افتح الميني آب من جديد")
    user = json.loads(data.get("user", "{}"))
    if not user.get("id"):
        raise ValueError("تعذر تحديد حسابك")
    return user

async def new_ai(user, bot_name, difficulty, clock):
    if difficulty not in ("سهل","متوسط","صعب","مستحيل") or clock not in (0,600):
        raise ValueError("إعدادات المباراة غير صحيحة")
    game_id = uuid.uuid4().hex
    board = chess.Board()
    await get_pool().execute(
        """INSERT INTO chess_games
        (id,game_type,status,white_user_id,white_name,bot_name,difficulty,
         time_control_seconds,white_time_ms,black_time_ms,clock_started_at,fen)
        VALUES($1,'ai','active',$2,$3,$4,$5,$6,$7,$7,NOW(),$8)""",
        game_id,int(user["id"]),(user.get("first_name") or "لاعب")[:80],
        bot_name[:80],difficulty,clock,clock*1000,board.fen())
    return {"id":game_id,"fen":board.fen(),"turn":"white",
            "turn_name":(user.get("first_name") or "لاعب"),
            "white_name":(user.get("first_name") or "لاعب"),
            "black_name":bot_name,"status":"active","moves":[]}

async def play_ai(game_id, user, uci):
    pool=get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow("SELECT * FROM chess_games WHERE id=$1 FOR UPDATE",game_id)
            if not row or row["status"]!="active" or row["game_type"]!="ai":
                raise ValueError("المباراة غير متاحة")
            if int(user["id"])!=row["white_user_id"]:
                raise ValueError("هذه المباراة ليست لك")
            board=chess.Board(row["fen"])
            try: move=chess.Move.from_uci(uci)
            except Exception: raise ValueError("النقلة غير صحيحة")
            if board.turn!=chess.WHITE or move not in board.legal_moves:
                raise ValueError("النقلة غير قانونية أو ليس دورك")
            moves=list(row["moves"] or [])
            san=board.san(move); board.push(move); moves.append({"uci":uci,"san":san})
            if not board.is_game_over(claim_draw=True):
                ai=chess.Move.from_uci(choose_ai_move(board.fen(),row["difficulty"]))
                san=board.san(ai); board.push(ai); moves.append({"uci":ai.uci(),"san":san})
            status="finished" if board.is_game_over(claim_draw=True) else "active"
            outcome=board.outcome(claim_draw=True) if status=="finished" else None
            result=("draw" if outcome and outcome.winner is None else
                    "white" if outcome and outcome.winner else "black") if outcome else None
            await conn.execute("UPDATE chess_games SET fen=$2,moves=$3::jsonb,status=$4,result=$5,updated_at=NOW() WHERE id=$1",
                game_id,board.fen(),json.dumps(moves),status,result)
            return {"id":game_id,"fen":board.fen(),"moves":moves,"status":status,
                    "turn":"white" if board.turn else "black",
                    "turn_name":row["white_name"] if board.turn else row["bot_name"],
                    "white_name":row["white_name"],"black_name":row["bot_name"],"result":result}
