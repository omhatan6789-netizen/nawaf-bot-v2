from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from database.pool import get_pool


def _decode(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def _initial_state():
    discs = [{"x": 400.0, "y": 400.0, "color": "#ed172b", "type": "queen", "pocketed": False}]
    colors = ["#080808", "#f7f7f7"]
    for ring_index, (radius, count) in enumerate(((38, 6), (76, 12))):
        for i in range(count):
            angle = -math.pi / 2 + i * math.tau / count + (math.pi / 12 if ring_index else 0)
            discs.append({
                "x": 400 + math.cos(angle) * radius,
                "y": 400 + math.sin(angle) * radius,
                "color": colors[(i + ring_index) % 2],
                "type": "coin", "pocketed": False,
            })
    return {
        "discs": discs, "striker": {"x": 400.0, "y": 620.0},
        "scores": [], "queen_pending_cover": False,
    }


def _striker_baseline(index, count):
    if count == 2:
        return {"x": 400.0, "y": 620.0 if index % 2 == 0 else 180.0}
    return [
        {"x": 400.0, "y": 620.0},
        {"x": 180.0, "y": 400.0},
        {"x": 400.0, "y": 180.0},
        {"x": 620.0, "y": 400.0},
    ][index % 4]


def _public(row, uid):
    players = _decode(row["players"])
    state = _decode(row["game_state"])
    deadline = row["deadline"]
    remaining = None
    if deadline:
        remaining = max(0, int((deadline - datetime.now(timezone.utc)).total_seconds()))
    return {
        "id": row["id"].hex, "status": row["status"],
        "players": players, "settings": _decode(row["settings"]),
        "state": state, "turn_index": int(row["turn_index"]),
        "move_no": int(row["move_no"]), "deadline": deadline.timestamp() if deadline else None,
        "remaining": remaining, "winner_id": int(row["winner_id"]) if row["winner_id"] else None,
        "is_player": any(int(p["id"]) == int(uid) for p in players),
        "you_player_index": next((i for i, p in enumerate(players) if int(p["id"]) == int(uid)), 0),
        "your_turn": row["status"] == "playing" and int(players[int(row["turn_index"])]["id"]) == int(uid),
        "scores": state.get("scores", [0] * len(players)),
    }


async def create_game(conn, lobby, game_id):
    count = int(lobby["player_count"])
    ids = [lobby["creator_id"], lobby["player2_id"], lobby["player3_id"], lobby["player4_id"]][:count]
    players = [{"id": int(lobby["creator_id"]), "name": str(lobby["creator_name"] or "لاعب")[:80]}]
    for i in range(2, count + 1):
        players.append({"id": int(lobby[f"player{i}_id"]), "name": str(lobby[f"player{i}_name"] or "لاعب")[:80]})
    settings = {
        "player_count": count,
        "team_mode": lobby["team_mode"] if count == 4 else "individual",
        "duration_seconds": int(lobby["duration_seconds"] or 300),
    }
    state = _initial_state()
    state["scores"] = [0 for _ in players]
    deadline_seconds = settings["duration_seconds"]
    await conn.execute(
        """INSERT INTO carrom_online_games
           (id,lobby_id,players,settings,game_state,turn_index,move_no,deadline)
           VALUES($1,$2,$3::jsonb,$4::jsonb,$5::jsonb,0,0,NOW()+($6 * INTERVAL '1 second'))""",
        game_id, lobby["id"], json.dumps(players, ensure_ascii=False),
        json.dumps(settings), json.dumps(state), deadline_seconds,
    )


async def carrom_online_api(user_id: int, action: str, raw_game_id: str, payload=None):
    uid = int(user_id)
    payload = payload or {}
    pool = get_pool()
    if action == "active":
        async with pool.acquire() as conn:
            active = await conn.fetchrow(
                """SELECT id FROM carrom_online_games
                   WHERE status='playing' AND players @> $1::jsonb
                   ORDER BY updated_at DESC LIMIT 1""",
                json.dumps([{"id": uid}]),
            )
        if not active:
            return None
        raw_game_id = active["id"].hex
        action = "state"
    try:
        game_id = uuid.UUID(hex=str(raw_game_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط لعبة الكيرم غير صالح")
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT * FROM carrom_online_games WHERE id=$1 FOR UPDATE", game_id)
            if not row:
                raise ValueError("غرفة الكيرم غير موجودة")
            players = _decode(row["players"])
            ids = [int(p["id"]) for p in players]
            if uid not in ids and action != "state":
                raise ValueError("هذا الإجراء متاح للاعبين فقط")
            state = _decode(row["game_state"])
            if row["status"] == "playing" and row["deadline"] and row["deadline"] <= datetime.now(timezone.utc):
                scores = state.get("scores", [0] * len(players))
                settings = _decode(row["settings"])
                if len(players) == 4 and settings.get("team_mode") == "teams":
                    team_scores = [scores[0] + scores[2], scores[1] + scores[3]]
                    winner_id = ids[0] if team_scores[0] > team_scores[1] else ids[1] if team_scores[1] > team_scores[0] else None
                else:
                    high = max(scores) if scores else 0
                    winners = [i for i, score in enumerate(scores) if score == high]
                    winner_id = ids[winners[0]] if len(winners) == 1 else None
                row = await conn.fetchrow(
                    "UPDATE carrom_online_games SET status='finished',winner_id=$2,updated_at=NOW() WHERE id=$1 RETURNING *",
                    game_id, winner_id,
                )
            elif action == "shot":
                if row["status"] != "playing":
                    raise ValueError("انتهت المباراة")
                turn_index = int(row["turn_index"])
                if ids[turn_index] != uid:
                    raise ValueError("ليس دورك الآن")
                if int(payload.get("move_no", -1)) != int(row["move_no"]):
                    raise ValueError("وصلت حركة أقدم؛ حدّث اللعبة وحاول مجددًا")
                incoming = payload.get("discs")
                if not isinstance(incoming, list) or len(incoming) != len(state.get("discs", [])):
                    raise ValueError("بيانات الأقراص غير مكتملة")
                clean = []
                for item in incoming:
                    if not isinstance(item, dict):
                        raise ValueError("حالة القرص غير صالحة")
                    x, y = float(item.get("x", 400)), float(item.get("y", 400))
                    if not math.isfinite(x) or not math.isfinite(y) or not (35 <= x <= 765 and 35 <= y <= 765):
                        raise ValueError("موضع القرص خارج اللوحة")
                    original = state["discs"][len(clean)]
                    color = str(item.get("color", ""))
                    disc_type = str(item.get("type", "coin"))
                    if color != original["color"] or disc_type != original["type"]:
                        raise ValueError("تعريف القرص غير صالح")
                    clean.append({"x": x, "y": y, "color": color,
                                  "type": disc_type, "pocketed": bool(item.get("pocketed", False))})
                striker = payload.get("striker") or {}
                sx, sy = float(striker.get("x", 400)), float(striker.get("y", 620))
                if not math.isfinite(sx) or not math.isfinite(sy) or not (35 <= sx <= 765 and 35 <= sy <= 765):
                    raise ValueError("موضع المضرب غير صالح")
                old_discs = state.get("discs", [])
                newly_pocketed = [i for i, item in enumerate(clean) if item["pocketed"] and not old_discs[i].get("pocketed")]
                newly_normal = [i for i in newly_pocketed if clean[i]["type"] != "queen"]
                queen_index = next((i for i, d in enumerate(clean) if d["type"] == "queen"), 0)
                striker_foul = bool(payload.get("striker_pocketed"))
                scores = list(state.get("scores", [0] * len(players)))
                scores += [0] * (len(players) - len(scores))
                pending = bool(state.get("queen_pending_cover"))
                queen_new = queen_index in newly_pocketed
                event = None
                regular_before = [i for i, d in enumerate(old_discs) if d["type"] != "queen" and not d.get("pocketed")]
                if len(regular_before) == 1 and newly_normal and not queen_new and not pending:
                    last_idx = newly_normal[0]
                    clean[last_idx].update({"x": 400.0, "y": 455.0, "pocketed": False})
                    newly_normal = [i for i in newly_normal if i != last_idx]
                    event = "last_coin_returned"
                for i in newly_normal:
                    scores[turn_index] += 5 if clean[i]["color"] == "#080808" else 10
                if pending:
                    if newly_normal and not striker_foul:
                        scores[turn_index] += 50
                        pending = False
                        event = "queen_covered"
                    else:
                        clean[queen_index].update({"x": 400.0, "y": 400.0, "pocketed": False})
                        pending = False
                        event = "queen_returned"
                elif queen_new:
                    pending = True
                    event = "queen_pocketed"
                if striker_foul:
                    scores[turn_index] = max(0, scores[turn_index] - 5)
                    event = "striker_foul"
                has_pot = bool(newly_normal)
                keep_turn = (has_pot or pending) and not striker_foul
                if striker_foul or not keep_turn:
                    next_index = (turn_index + 1) % len(players)
                elif keep_turn:
                    next_index = turn_index
                else:
                    next_index = (turn_index + 1) % len(players)
                state = {"discs": clean, "striker": _striker_baseline(next_index, len(players)),
                          "scores": scores, "queen_pending_cover": pending,
                          "last_event": event, "event_move_no": int(row["move_no"]) + 1}
                all_regular_pocketed = all(d["pocketed"] for d in clean if d["type"] != "queen")
                queen_done = clean[queen_index]["pocketed"] and not pending
                status = "finished" if all_regular_pocketed and queen_done else "playing"
                winner_id = None
                if status == "finished":
                    if len(players) == 4 and _decode(row["settings"]).get("team_mode") == "teams":
                        team_scores = [scores[0] + scores[2], scores[1] + scores[3]]
                        if team_scores[0] != team_scores[1]:
                            winner_id = ids[0] if team_scores[0] > team_scores[1] else ids[1]
                    else:
                        high = max(scores)
                        winners = [i for i, score in enumerate(scores) if score == high]
                        if len(winners) == 1:
                            winner_id = ids[winners[0]]
                row = await conn.fetchrow(
                    """UPDATE carrom_online_games SET game_state=$2::jsonb,turn_index=$3,
                       move_no=move_no+1,status=$4,winner_id=$5,updated_at=NOW()
                       WHERE id=$1 RETURNING *""",
                    game_id, json.dumps(state), next_index, status, winner_id,
                )
            elif action not in ("state", "leave"):
                raise ValueError("طلب غير معروف")
            elif action == "leave" and row["status"] == "playing":
                winner_id = next((pid for pid in ids if pid != uid), None)
                row = await conn.fetchrow(
                    "UPDATE carrom_online_games SET status='finished',winner_id=$2,updated_at=NOW() WHERE id=$1 RETURNING *",
                    game_id, winner_id,
                )
    return _public(row, uid)
