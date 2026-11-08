from __future__ import annotations

import json
import math
import random
import time
import uuid

from database.pool import get_pool

TABLE_W = 1.0
PUCK_R = 0.026
PADDLE_R = 0.062
GOAL_LEFT = 0.35
GOAL_RIGHT = 0.65
WIN_SCORE = 5
TABLE_ASPECT = 1.6  # height / width; keeps circular collisions proportional to the rendered table


def _initial_state():
    return {
        "p1": {"x": 0.5, "y": 0.84},
        "p2": {"x": 0.5, "y": 0.16},
        "puck": {"x": 0.5, "y": 0.5, "vx": 0.42, "vy": 0.78},
        "scores": [0, 0],
        "last_tick": time.time(),
        "goal_pause_until": 0.0,
    }


def _decode_state(value):
    return json.loads(value) if isinstance(value, str) else value


def _clamp(value, low, high):
    return max(low, min(high, float(value)))


def _advance(state, now):
    puck = state["puck"]
    if now < float(state.get("goal_pause_until", 0)):
        state["last_tick"] = now
        return None

    previous = float(state.get("last_tick", now))
    elapsed = _clamp(now - previous, 0.0, 0.18)
    state["last_tick"] = now
    if elapsed <= 0:
        return None

    steps = max(1, min(12, math.ceil(elapsed / 0.015)))
    dt = elapsed / steps
    goal = None

    for _ in range(steps):
        puck["x"] += puck["vx"] * dt
        puck["y"] += puck["vy"] * dt

        # Side walls.
        if puck["x"] < PUCK_R:
            puck["x"] = PUCK_R
            puck["vx"] = abs(puck["vx"]) * 0.94
        elif puck["x"] > 1 - PUCK_R:
            puck["x"] = 1 - PUCK_R
            puck["vx"] = -abs(puck["vx"]) * 0.94

        # End walls have a goal opening in the middle.
        in_goal = GOAL_LEFT <= puck["x"] <= GOAL_RIGHT
        if puck["y"] < PUCK_R / TABLE_ASPECT and not in_goal:
            puck["y"] = PUCK_R / TABLE_ASPECT
            puck["vy"] = abs(puck["vy"]) * 0.94
        elif puck["y"] > 1 - PUCK_R / TABLE_ASPECT and not in_goal:
            puck["y"] = 1 - PUCK_R / TABLE_ASPECT
            puck["vy"] = -abs(puck["vy"]) * 0.94

        # Paddle collisions.
        for key in ("p1", "p2"):
            paddle = state[key]
            dx = puck["x"] - paddle["x"]
            dy = (puck["y"] - paddle["y"]) * TABLE_ASPECT
            distance = math.hypot(dx, dy)
            minimum = PUCK_R + PADDLE_R
            if 0 < distance < minimum:
                nx, ny = dx / distance, dy / distance
                puck["x"] = paddle["x"] + nx * (minimum + 0.002)
                puck["y"] = paddle["y"] + ny * (minimum + 0.002) / TABLE_ASPECT
                speed = math.hypot(puck["vx"], puck["vy"] * TABLE_ASPECT)
                speed = max(0.78, min(1.65, speed + 0.12))
                puck["vx"] = nx * speed
                puck["vy"] = ny * speed / TABLE_ASPECT

        # Goal detection after the puck crosses the end line.
        if in_goal and puck["y"] < -PUCK_R / TABLE_ASPECT:
            goal = 0
            break
        if in_goal and puck["y"] > 1 + PUCK_R / TABLE_ASPECT:
            goal = 1
            break

        # Light air resistance keeps rallies lively without stopping the puck.
        drag = math.exp(-0.12 * dt)
        puck["vx"] *= drag
        puck["vy"] *= drag

    if goal is not None:
        state["scores"][goal] += 1
        state["puck"] = {
            "x": 0.5, "y": 0.5,
            "vx": random.choice((-1, 1)) * random.uniform(0.22, 0.42),
            "vy": 0.72 if goal == 0 else -0.72,
        }
        state["goal_pause_until"] = now + 0.85
        state["last_tick"] = now
    return goal


def _role(row, user_id):
    if int(row["player1_id"]) == int(user_id):
        return "player1"
    if row["player2_id"] is not None and int(row["player2_id"]) == int(user_id):
        return "player2"
    return "spectator"


def _view(row, user_id):
    state = _decode_state(row["game_state"])
    role = _role(row, user_id)
    winner_name = None
    if row["winner_id"] is not None:
        winner_name = row["player1_name"] if int(row["winner_id"]) == int(row["player1_id"]) else row["player2_name"]
    return {
        "id": row["id"].hex,
        "status": row["status"],
        "role": role,
        "spectator": role == "spectator",
        "player1": {"id": int(row["player1_id"]), "name": row["player1_name"]},
        "player2": (
            {"id": int(row["player2_id"]), "name": row["player2_name"]}
            if row["player2_id"] is not None else None
        ),
        "state": state,
        "winner_id": int(row["winner_id"]) if row["winner_id"] is not None else None,
        "winner_name": winner_name,
        "win_score": WIN_SCORE,
        "server_time": time.time(),
    }


async def air_hockey_api(user_id: int, action: str, raw_game_id: str = "", name: str = "", x=None, y=None):
    pool = get_pool()
    user_id = int(user_id)
    name = (str(name or "لاعب").strip() or "لاعب")[:80]

    if action == "create":
        game_id = uuid.uuid4()
        state = _initial_state()
        await pool.execute(
            """INSERT INTO air_hockey_games
               (id, player1_id, player1_name, status, game_state)
               VALUES($1,$2,$3,'pending',$4::jsonb)""",
            game_id, user_id, name, json.dumps(state),
        )
        row = await pool.fetchrow("SELECT * FROM air_hockey_games WHERE id=$1", game_id)
        return _view(row, user_id)

    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط مباراة الهوكي غير صالح")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM air_hockey_games WHERE id=$1 FOR UPDATE", game_id
            )
            if not row:
                raise ValueError("المباراة غير موجودة أو انتهت صلاحيتها")

            if action == "join":
                if int(row["player1_id"]) != user_id and (
                    row["player2_id"] is None and row["status"] == "pending"
                ):
                    await conn.execute(
                        """UPDATE air_hockey_games
                           SET player2_id=$2,player2_name=$3,status='playing',updated_at=NOW()
                           WHERE id=$1""",
                        game_id, user_id, name,
                    )
                elif row["player2_id"] is not None and int(row["player2_id"]) != user_id:
                    # Additional visitors are spectators, never players.
                    pass
                row = await conn.fetchrow("SELECT * FROM air_hockey_games WHERE id=$1", game_id)

            elif action == "move":
                role = _role(row, user_id)
                if role == "spectator":
                    raise ValueError("المشاهدة فقط؛ لست أحد لاعبي المباراة")
                if row["status"] != "playing":
                    raise ValueError("المباراة لم تبدأ بعد")
                state = _decode_state(row["game_state"])
                now = time.time()
                _advance(state, now)
                px = _clamp(x, 0.08, 0.92)
                py = _clamp(y, 0.06, 0.94)
                if role == "player1":
                    state["p1"] = {"x": px, "y": _clamp(py, 0.53, 0.93)}
                else:
                    state["p2"] = {"x": px, "y": _clamp(py, 0.07, 0.47)}
                winner_id = None
                if max(state["scores"]) >= WIN_SCORE:
                    row_winner = 0 if state["scores"][0] > state["scores"][1] else 1
                    winner_id = int(row["player1_id"] if row_winner == 0 else row["player2_id"])
                await conn.execute(
                    """UPDATE air_hockey_games
                       SET game_state=$2::jsonb,
                           status=CASE WHEN $3::bigint IS NULL THEN status ELSE 'finished' END,
                           winner_id=COALESCE($3,winner_id),updated_at=NOW()
                       WHERE id=$1""",
                    game_id, json.dumps(state), winner_id,
                )
                row = await conn.fetchrow("SELECT * FROM air_hockey_games WHERE id=$1", game_id)

            elif action == "state":
                if row["status"] == "playing":
                    state = _decode_state(row["game_state"])
                    _advance(state, time.time())
                    winner_id = None
                    if max(state["scores"]) >= WIN_SCORE:
                        winner_index = 0 if state["scores"][0] > state["scores"][1] else 1
                        winner_id = int(row["player1_id"] if winner_index == 0 else row["player2_id"])
                    await conn.execute(
                        """UPDATE air_hockey_games
                           SET game_state=$2::jsonb,
                               status=CASE WHEN $3::bigint IS NULL THEN status ELSE 'finished' END,
                               winner_id=COALESCE($3,winner_id),updated_at=NOW()
                           WHERE id=$1""",
                        game_id, json.dumps(state), winner_id,
                    )
                    row = await conn.fetchrow("SELECT * FROM air_hockey_games WHERE id=$1", game_id)
            else:
                raise ValueError("طلب غير معروف")

    return _view(row, user_id)
