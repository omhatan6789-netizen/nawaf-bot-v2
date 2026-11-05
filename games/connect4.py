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


def public_state(row):
    board = row["board"]
    if isinstance(board, str):
        board = json.loads(board)
    cells = row["winning_cells"]
    if isinstance(cells, str):
        cells = json.loads(cells)
    return {
        "id": str(row["id"]), "board": board, "status": row["status"],
        "difficulty": row["difficulty"], "last_move": row["last_move"],
        "winning_cells": cells or [], "turn_seconds": TURN_SECONDS,
    }


async def create_game(user_id: int, difficulty: str):
    if difficulty not in ("سهل", "متوسط", "صعب", "مستحيل"):
        raise ValueError("اختر مستوى صحيحًا")
    game_id = uuid.uuid4()
    board = [[0 for _ in range(COLS)] for _ in range(ROWS)]
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO connect4_games(id,user_id,difficulty,board)
           VALUES($1,$2,$3,$4::jsonb) RETURNING *""",
        game_id, user_id, difficulty, json.dumps(board),
    )
    return public_state(row)


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
                "SELECT * FROM connect4_games WHERE id=$1 AND user_id=$2 FOR UPDATE",
                parsed_id, user_id,
            )
            if not row:
                raise ValueError("المباراة غير موجودة")
            board = row["board"]
            if isinstance(board, str):
                board = json.loads(board)
            status = row["status"]
            winning_cells = row["winning_cells"]
            if isinstance(winning_cells, str):
                winning_cells = json.loads(winning_cells)
            last_move = row["last_move"]
            if status != "playing":
                return public_state(row)
            if not legal_columns(board):
                status = "draw"
            else:
                # A late request forfeits the player's requested move and plays randomly.
                expired = (await conn.fetchval(
                    "SELECT NOW() > $1::timestamptz + ($2 * INTERVAL '1 second')",
                    row["turn_started_at"], TURN_SECONDS,
                ))
                player_col = random.choice(legal_columns(board)) if expired else col
                if player_col not in legal_columns(board):
                    raise ValueError("هذا العمود ممتلئ، اختر عمودًا آخر")
                drop_piece(board, player_col, 1)
                last_move = player_col
                winning_cells = winning_line(board, 1)
                if winning_cells:
                    status = "won"
                elif not legal_columns(board):
                    status = "draw"
                else:
                    bot_col = choose_bot_move(board, row["difficulty"])
                    if bot_col is not None:
                        drop_piece(board, bot_col, 2)
                        last_move = bot_col
                        winning_cells = winning_line(board, 2)
                        if winning_cells:
                            status = "lost"
                        elif not legal_columns(board):
                            status = "draw"
            updated = await conn.fetchrow(
                """UPDATE connect4_games
                   SET board=$2::jsonb,status=$3,last_move=$4,winning_cells=$5::jsonb,
                       turn_started_at=NOW(),updated_at=NOW()
                   WHERE id=$1 RETURNING *""",
                parsed_id, json.dumps(board), status, last_move,
                json.dumps(winning_cells or []),
            )
            return public_state(updated)
