from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
import uuid
from urllib.parse import parse_qsl

from database.pool import get_pool

ROWS = 6
COLS = 7
TURN_SECONDS = 15
CENTER_ORDER = [3, 2, 4, 1, 5, 0, 6]


def verify_init_data(init_data: str, bot_token: str) -> dict:
    if not init_data or not bot_token:
        raise ValueError("افتح اللعبة من داخل تيليجرام أولاً")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise ValueError("تعذر التحقق من حساب تيليجرام")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise ValueError("بيانات تيليجرام غير صالحة")
    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not auth_date or time.time() - auth_date > 86400:
        raise ValueError("انتهت صلاحية الجلسة، أغلق اللعبة وافتحها مجددًا")
    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        raise ValueError("لم أستطع تحديد حسابك")
    return user


def legal_columns(board):
    return [c for c in CENTER_ORDER if board[0][c] == 0]


def drop_piece(board, col, piece):
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == 0:
            board[r][col] = piece
            return r
    return None


def winning_line(board, piece):
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] != piece:
                continue
            for dr, dc in directions:
                cells = [(r + i * dr, c + i * dc) for i in range(4)]
                if all(0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == piece
                       for rr, cc in cells):
                    return [[rr, cc] for rr, cc in cells]
    return None


def score_window(window, piece):
    opponent = 1 if piece == 2 else 2
    own = window.count(piece)
    other = window.count(opponent)
    empty = window.count(0)
    if own == 4:
        return 100000
    if own == 3 and empty == 1:
        return 120
    if own == 2 and empty == 2:
        return 12
    if other == 3 and empty == 1:
        return -150
    if other == 2 and empty == 2:
        return -10
    return 0


def evaluate(board, piece=2):
    score = 0
    center = [board[r][COLS // 2] for r in range(ROWS)]
    score += center.count(piece) * 7
    for r in range(ROWS):
        for c in range(COLS - 3):
            score += score_window([board[r][c+i] for i in range(4)], piece)
    for c in range(COLS):
        for r in range(ROWS - 3):
            score += score_window([board[r+i][c] for i in range(4)], piece)
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            score += score_window([board[r+i][c+i] for i in range(4)], piece)
    for r in range(3, ROWS):
        for c in range(COLS - 3):
            score += score_window([board[r-i][c+i] for i in range(4)], piece)
    return score


def minimax(board, depth, alpha, beta, maximizing):
    valid = legal_columns(board)
    if winning_line(board, 2):
        return (None, 10_000_000 + depth)
    if winning_line(board, 1):
        return (None, -10_000_000 - depth)
    if not valid or depth == 0:
        return (None, evaluate(board, 2))
    if maximizing:
        value, choice = -float("inf"), random.choice(valid)
        for col in valid:
            copy = [row[:] for row in board]
            drop_piece(copy, col, 2)
            score = minimax(copy, depth - 1, alpha, beta, False)[1]
            if score > value:
                value, choice = score, col
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return choice, value
    value, choice = float("inf"), random.choice(valid)
    for col in valid:
        copy = [row[:] for row in board]
        drop_piece(copy, col, 1)
        score = minimax(copy, depth - 1, alpha, beta, True)[1]
        if score < value:
            value, choice = score, col
        beta = min(beta, value)
        if alpha >= beta:
            break
    return choice, value


def choose_bot_move(board, difficulty):
    valid = legal_columns(board)
    if not valid:
        return None
    # Always take a winning move, and always block an immediate player win.
    for piece, col_piece in [(2, 2), (1, 1)]:
        for col in valid:
            test = [row[:] for row in board]
            drop_piece(test, col, col_piece)
            if winning_line(test, col_piece):
                return col
    if difficulty == "سهل":
        return random.choice(valid)
    if difficulty == "متوسط":
        return random.choice(valid[:3] if len(valid) > 3 else valid)
    depth = 4 if difficulty == "صعب" else 5
    return minimax(board, depth, -float("inf"), float("inf"), True)[0]


def public_state(row, viewer_id: int | None = None):
    board = row["board"]
    if isinstance(board, str):
        board = json.loads(board)
    cells = row["winning_cells"]
    if isinstance(cells, str):
        cells = json.loads(cells)
    mode = row.get("game_mode", "bot")
    stored_status = row["status"]
    status = stored_status
    if mode == "human" and stored_status == "won" and viewer_id is not None:
        status = "won" if int(row["winner_id"] or 0) == int(viewer_id) else "lost"
    is_player1 = viewer_id is None or int(viewer_id) == int(row["user_id"])
    opponent_name = row.get("bot_name") if mode == "bot" else (
        row.get("player2_name") if is_player1 else row.get("player1_name")
    )
    your_turn = True
    if mode == "human" and viewer_id is not None:
        your_turn = int(row.get("turn_player_id") or 0) == int(viewer_id)
    elif mode == "bot":
        your_turn = not bool(row.get("bot_move_pending", False))
    return {
        "id": str(row["id"]), "board": board, "status": status,
        "difficulty": row["difficulty"], "last_move": row["last_move"],
        "winning_cells": cells or [], "turn_seconds": TURN_SECONDS,
        "turn_started_at": int(row["turn_started_at"].timestamp() * 1000) if row.get("turn_started_at") else None,
        "game_mode": mode, "player1_name": row.get("player1_name") or "أنت",
        "player2_name": row.get("player2_name") or opponent_name or "البوت",
        "bot_name": row.get("bot_name") or "البوت",
        "your_turn": your_turn, "bot_move_pending": bool(row.get("bot_move_pending", False)),
        "my_piece": (1 if is_player1 else 2), "turn_player_id": row.get("turn_player_id"),
        "winner_id": row.get("winner_id"), "wager": int(row.get("wager") or 0),
        "winner_name": (row.get("player1_name") if row.get("winner_id") == row.get("user_id")
                        else row.get("player2_name") if row.get("winner_id") == row.get("player2_id")
                        else ("أنت" if mode == "bot" and stored_status == "won" else row.get("bot_name"))),
    }


async def create_game(user_id: int, difficulty: str, bot_name: str = "البوت", bot_id: int | None = None, rps_choice: str = "r"):
    if difficulty not in ("سهل", "متوسط", "صعب", "مستحيل"):
        raise ValueError("اختر مستوى صحيحًا")
    if rps_choice not in ("r", "p", "s"):
        raise ValueError("اختر حجر أو ورقة أو مقص لتحديد من يبدأ")
    game_id = uuid.uuid4()
    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    bot_starts = random.random() < 0.40
    bot_choices = {"r": ("p", "s"), "p": ("s", "r"), "s": ("r", "p")}
    bot_choice = bot_choices[rps_choice][0 if bot_starts else 1]
    last_move = None
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO connect4_games
           (id,user_id,difficulty,board,game_mode,bot_id,bot_name,bot_move_pending,last_move)
           VALUES($1,$2,$3,$4::jsonb,'bot',$5,$6,$7,$8) RETURNING *""",
        game_id, user_id, difficulty, json.dumps(board), bot_id, bot_name, bot_starts, last_move,
    )
    state = public_state(row, user_id)
    state["rps_result"] = "bot_starts" if bot_starts else "player_starts"
    state["rps_player_choice"] = rps_choice
    state["rps_bot_choice"] = bot_choice
    return state


async def create_multiplayer_game(
    challenge_id: uuid.UUID, player1_id: int, player2_id: int,
    player1_name: str, player2_name: str, starter_id: int,
    wager: int, chat_id: int,
):
    game_id = uuid.uuid4()
    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO connect4_games
           (id,user_id,player2_id,difficulty,board,game_mode,chat_id,
            player1_name,player2_name,turn_player_id,wager)
           VALUES($1,$2,$3,'متوسط',$4::jsonb,'human',$5,$6,$7,$8,$9)
           RETURNING *""",
        game_id, player1_id, player2_id, json.dumps(board), chat_id,
        player1_name, player2_name, starter_id, wager,
    )
    return public_state(row, starter_id)


async def get_game_state(user_id: int, game_id: str):
    try:
        parsed_id = uuid.UUID(game_id)
    except Exception:
        raise ValueError("المباراة غير موجودة")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM connect4_games
                   WHERE id=$1 AND (user_id=$2 OR player2_id=$2) FOR UPDATE""",
                parsed_id, user_id,
            )
            if not row:
                raise ValueError("المباراة غير موجودة أو ليست لك")

            # The server owns the shared turn clock. Any participant polling after
            # expiry can advance the timed-out player's move exactly once.
            if row["game_mode"] == "human" and row["status"] == "playing":
                expired = await conn.fetchval(
                    "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                    row["turn_started_at"], TURN_SECONDS,
                )
                if expired:
                    board = row["board"]
                    if isinstance(board, str):
                        board = json.loads(board)
                    valid = legal_columns(board)
                    if valid:
                        timed_out_player = int(row["turn_player_id"])
                        piece = 1 if timed_out_player == int(row["user_id"]) else 2
                        chosen = random.choice(valid)
                        drop_piece(board, chosen, piece)
                        cells = winning_line(board, piece) or []
                        status = "won" if cells else ("draw" if not legal_columns(board) else "playing")
                        winner_id = timed_out_player if status == "won" else None
                        if status in ("won", "draw"):
                            await _settle_human_wager(conn, row, winner_id)
                        next_player = int(
                            row["player2_id"] if timed_out_player == int(row["user_id"])
                            else row["user_id"]
                        )
                        row = await conn.fetchrow(
                            """UPDATE connect4_games SET board=$2::jsonb,status=$3,
                               last_move=$4,winning_cells=$5::jsonb,winner_id=$6,
                               turn_player_id=$7,turn_started_at=NOW(),updated_at=NOW()
                               WHERE id=$1 RETURNING *""",
                            parsed_id, json.dumps(board), status, chosen,
                            json.dumps(cells), winner_id, next_player,
                        )
            return public_state(row, user_id)


async def _settle_human_wager(conn, row, winner_id: int | None):
    if int(row.get("wager") or 0) <= 0 or row.get("wager_settled"):
        return
    first_id, second_id = int(row["user_id"]), int(row["player2_id"])
    wager = int(row["wager"])
    await conn.execute(
        "INSERT INTO points(user_id,points) VALUES($1,0),($2,0) ON CONFLICT(user_id) DO NOTHING",
        first_id, second_id,
    )
    if winner_id is None:
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", first_id, wager)
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", second_id, wager)
    else:
        await conn.execute("UPDATE points SET points=points+$2 WHERE user_id=$1", winner_id, wager * 2)
    await conn.execute("UPDATE connect4_games SET wager_settled=TRUE WHERE id=$1", row["id"])


async def play_move(user_id: int, game_id: str, col: int):
    if not isinstance(col, int) or col < 0 or col >= COLS:
        raise ValueError("العمود غير صالح")
    try:
        parsed_id = uuid.UUID(game_id)
    except Exception:
        raise ValueError("المباراة غير موجودة")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT * FROM connect4_games
                   WHERE id=$1 AND (user_id=$2 OR player2_id=$2) FOR UPDATE""",
                parsed_id, user_id,
            )
            if not row:
                raise ValueError("المباراة غير موجودة أو ليست لك")
            board = row["board"]
            if isinstance(board, str):
                board = json.loads(board)
            status = row["status"]
            winning_cells = row["winning_cells"]
            if isinstance(winning_cells, str):
                winning_cells = json.loads(winning_cells)
            if status != "playing":
                return public_state(row, user_id)
            if row["game_mode"] == "human":
                if int(row["turn_player_id"] or 0) != int(user_id):
                    raise ValueError("انتظر دور اللاعب الآخر")
                expired = await conn.fetchval(
                    "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                    row["turn_started_at"], TURN_SECONDS,
                )
                valid = legal_columns(board)
                if not valid:
                    status = "draw"
                else:
                    chosen = random.choice(valid) if expired else col
                    if chosen not in valid:
                        raise ValueError("هذا العمود ممتلئ، اختر عمودًا آخر")
                    piece = 1 if int(user_id) == int(row["user_id"]) else 2
                    drop_piece(board, chosen, piece)
                    winning_cells = winning_line(board, piece)
                    if winning_cells:
                        status = "won"
                        await _settle_human_wager(conn, row, int(user_id))
                    elif not legal_columns(board):
                        status = "draw"
                        await _settle_human_wager(conn, row, None)
                    next_player = int(row["player2_id"] if user_id == row["user_id"] else row["user_id"])
                    updated = await conn.fetchrow(
                        """UPDATE connect4_games SET board=$2::jsonb,status=$3,
                           last_move=$4,winning_cells=$5::jsonb,winner_id=$6,
                           turn_player_id=$7,turn_started_at=NOW(),updated_at=NOW()
                           WHERE id=$1 RETURNING *""",
                        parsed_id, json.dumps(board), status, chosen,
                        json.dumps(winning_cells or []), user_id if status == "won" else None,
                        next_player,
                    )
                    if status in ("won", "draw") and row["player2_id"] is not None:
                        from database.game_stats import record_game_results
                        first = {"id": int(row["user_id"]), "name": row.get("player1_name") or "اللاعب الأول"}
                        second = {"id": int(row["player2_id"]), "name": row.get("player2_name") or "اللاعب الثاني"}
                        winners = [first if int(user_id) == int(row["user_id"]) else second] if status == "won" else []
                        losers = [second if winners and winners[0]["id"] == first["id"] else first] if status == "won" else []
                        await record_game_results(f"connect4:{row['id']}", "connect", winners, losers, conn=conn)
                    return public_state(updated, user_id)
            else:
                if int(row["user_id"]) != int(user_id):
                    raise ValueError("هذه المباراة ضد البوت وليست تحديًا بين لاعبين")
                if row.get("bot_move_pending"):
                    raise ValueError("انتظر حركة البوت")
                valid = legal_columns(board)
                expired = await conn.fetchval(
                    "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                    row["turn_started_at"], TURN_SECONDS,
                )
                chosen = random.choice(valid) if expired and valid else col
                if chosen not in valid:
                    raise ValueError("هذا العمود ممتلئ، اختر عمودًا آخر")
                drop_piece(board, chosen, 1)
                winning_cells = winning_line(board, 1)
                if winning_cells:
                    status = "won"
                elif not legal_columns(board):
                    status = "draw"
                updated = await conn.fetchrow(
                    """UPDATE connect4_games SET board=$2::jsonb,status=$3,
                       last_move=$4,winning_cells=$5::jsonb,bot_move_pending=$6,
                       turn_started_at=NOW(),updated_at=NOW()
                       WHERE id=$1 RETURNING *""",
                    parsed_id, json.dumps(board), status, chosen,
                    json.dumps(winning_cells or []), status == "playing",
                )
                return public_state(updated, user_id)


async def play_bot_move(user_id: int, game_id: str):
    try:
        parsed_id = uuid.UUID(game_id)
    except Exception:
        raise ValueError("المباراة غير موجودة")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM connect4_games WHERE id=$1 AND user_id=$2 FOR UPDATE",
                parsed_id, user_id,
            )
            if not row or row["game_mode"] != "bot":
                raise ValueError("المباراة غير موجودة")
            if row["status"] != "playing" or not row["bot_move_pending"]:
                return public_state(row, user_id)
            board = row["board"]
            if isinstance(board, str):
                board = json.loads(board)
            bot_col = choose_bot_move(board, row["difficulty"])
            status = "playing"
            winning_cells = []
            if bot_col is not None:
                drop_piece(board, bot_col, 2)
                winning_cells = winning_line(board, 2) or []
                if winning_cells:
                    status = "lost"
                elif not legal_columns(board):
                    status = "draw"
            updated = await conn.fetchrow(
                """UPDATE connect4_games SET board=$2::jsonb,status=$3,last_move=$4,
                   winning_cells=$5::jsonb,bot_move_pending=FALSE,
                   turn_started_at=NOW(),updated_at=NOW() WHERE id=$1 RETURNING *""",
                parsed_id, json.dumps(board), status, bot_col,
                json.dumps(winning_cells),
            )
            return public_state(updated, user_id)
