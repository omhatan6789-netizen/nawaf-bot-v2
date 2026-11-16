from __future__ import annotations

import json
import uuid

from database.pool import get_pool


def _decode(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def _score(rolls):
    total = 0
    index = 0
    for _ in range(10):
        if index >= len(rolls):
            break
        first = int(rolls[index])
        if first == 10:
            total += 10 + int(rolls[index + 1] if index + 1 < len(rolls) else 0) + int(rolls[index + 2] if index + 2 < len(rolls) else 0)
            index += 1
        elif index + 1 < len(rolls) and first + int(rolls[index + 1]) == 10:
            total += 10 + int(rolls[index + 2] if index + 2 < len(rolls) else 0)
            index += 2
        else:
            total += first + int(rolls[index + 1] if index + 1 < len(rolls) else 0)
            index += 2
    return total


def _all_rolls(frames):
    return [int(roll) for frame in frames for roll in frame]


def _public(row, uid):
    players = _decode(row["players"])
    state = _decode(row["game_state"])
    index = int(state.get("turn_index", 0))
    frame = int(state.get("frame_index", 0))
    current_rolls = state["frames"][index][frame] if players else []
    scores = [_score(_all_rolls(player_frames)) for player_frames in state["frames"]]
    winner_id = int(row["winner_id"]) if row["winner_id"] else None
    winner = next((p for p in players if int(p["id"]) == winner_id), None)
    return {
        "id": row["id"].hex,
        "status": row["status"],
        "players": players,
        "frame": frame + 1,
        "turn_index": index,
        "current_player_id": int(players[index]["id"]) if players else None,
        "current_rolls": current_rolls,
        "standing": int(state.get("standing", 10)),
        "scores": scores,
        "your_turn": row["status"] == "playing" and bool(players) and int(players[index]["id"]) == int(uid),
        "is_player": any(int(p["id"]) == int(uid) for p in players),
        "winner_id": winner_id,
        "winner_name": winner["name"] if winner else None,
        "draw": bool(state.get("draw")),
        "last_event": state.get("last_event"),
    }


async def create_game(conn, lobby, game_id):
    count = int(lobby["player_count"])
    players = [{
        "id": int(lobby["creator_id"]),
        "name": str(lobby["creator_name"] or "لاعب")[:80],
    }]
    for i in range(2, count + 1):
        players.append({
            "id": int(lobby[f"player{i}_id"]),
            "name": str(lobby[f"player{i}_name"] or "لاعب")[:80],
        })
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS bowling_online_games (
             id UUID PRIMARY KEY,
             lobby_id UUID UNIQUE NOT NULL,
             players JSONB NOT NULL,
             game_state JSONB NOT NULL,
             status TEXT NOT NULL DEFAULT 'playing',
             winner_id BIGINT,
             created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
             updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
           )"""
    )
    state = {
        "frame_index": 0,
        "turn_index": 0,
        "standing": 10,
        "frames": [[[] for _ in range(10)] for _ in players],
        "completed": [],
        "draw": False,
    }
    await conn.execute(
        """INSERT INTO bowling_online_games(id,lobby_id,players,game_state)
           VALUES($1,$2,$3::jsonb,$4::jsonb)""",
        game_id, lobby["id"], json.dumps(players, ensure_ascii=False), json.dumps(state),
    )


async def bowling_online_api(user_id: int, action: str, raw_game_id: str = "", payload=None):
    uid = int(user_id)
    payload = payload or {}
    pool = get_pool()
    if action == "active":
        row = await pool.fetchrow(
            """SELECT id FROM bowling_online_games
               WHERE status='playing' AND players @> $1::jsonb
               ORDER BY updated_at DESC LIMIT 1""",
            json.dumps([{"id": uid}]),
        )
        if not row:
            return None
        raw_game_id = row["id"].hex
        action = "state"
    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("معرّف لعبة البولينق غير صالح")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM bowling_online_games WHERE id=$1 FOR UPDATE", game_id
            )
            if not row:
                raise ValueError("مباراة البولينق غير موجودة")
            players = _decode(row["players"])
            ids = [int(player["id"]) for player in players]
            if action != "state" and uid not in ids:
                raise ValueError("هذا الإجراء متاح للاعبين فقط")
            state = _decode(row["game_state"])
            if action == "shot":
                if row["status"] != "playing":
                    raise ValueError("انتهت المباراة بالفعل")
                current = int(state["turn_index"])
                if ids[current] != uid:
                    raise ValueError("انتظر دورك")
                knocked = payload.get("pins")
                if isinstance(knocked, bool) or not isinstance(knocked, int):
                    raise ValueError("عدد القوارير غير صالح")
                standing = int(state.get("standing", 10))
                if knocked < 0 or knocked > standing:
                    raise ValueError("عدد القوارير يتجاوز القوارير المتبقية")
                frame_index = int(state["frame_index"])
                frame_rolls = state["frames"][current][frame_index]
                frame_rolls.append(knocked)
                rack_reset = False
                frame_done = False
                if frame_index < 9:
                    frame_done = knocked == 10 or len(frame_rolls) >= 2
                    rack_reset = frame_done
                elif len(frame_rolls) == 1:
                    rack_reset = knocked == 10
                elif len(frame_rolls) == 2:
                    first, second = frame_rolls
                    if first == 10:
                        rack_reset = second == 10
                    elif first + second == 10:
                        rack_reset = True
                    else:
                        frame_done = True
                else:
                    frame_done = True

                if frame_done:
                    completed = set(int(x) for x in state.get("completed", []))
                    completed.add(current)
                    state["completed"] = sorted(completed)
                    if len(completed) == len(players):
                        if frame_index == 9:
                            totals = [_score(_all_rolls(frames)) for frames in state["frames"]]
                            high = max(totals)
                            winners = [i for i, value in enumerate(totals) if value == high]
                            state["draw"] = len(winners) != 1
                            winner_id = int(players[winners[0]]["id"]) if len(winners) == 1 else None
                            row = await conn.fetchrow(
                                """UPDATE bowling_online_games SET status='finished',winner_id=$2,
                                   game_state=$3::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *""",
                                game_id, winner_id, json.dumps(state),
                            )
                        else:
                            state["frame_index"] = frame_index + 1
                            state["completed"] = []
                            state["turn_index"] = 0
                            state["standing"] = 10
                    else:
                        state["turn_index"] = (current + 1) % len(players)
                        state["standing"] = 10
                else:
                    state["standing"] = 10 if rack_reset else standing - knocked

                if row["status"] == "playing":
                    row = await conn.fetchrow(
                        """UPDATE bowling_online_games SET game_state=$2::jsonb,updated_at=NOW()
                           WHERE id=$1 RETURNING *""",
                        game_id, json.dumps(state),
                    )
            elif action != "state":
                raise ValueError("إجراء غير معروف")
    return _public(row, uid)
