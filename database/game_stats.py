from __future__ import annotations

from typing import Iterable, Mapping, Any
from database.pool import get_pool


async def record_game_results(
    game_key: str,
    game_type: str,
    winners: Iterable[Mapping[str, Any]],
    losers: Iterable[Mapping[str, Any]],
    *,
    conn=None,
) -> None:
    """Record each participant once. Repeated finish callbacks are safe."""
    key = str(game_key or "").strip()
    if not key:
        return
    rows = []
    for result, players in (("win", winners), ("loss", losers)):
        for player in players or ():
            try:
                user_id = int(player.get("id") or player.get("user_id"))
            except (TypeError, ValueError):
                continue
            name = str(player.get("name") or player.get("first_name") or "لاعب")[:100]
            rows.append((key, str(game_type or "game")[:60], user_id, name, result))
    if not rows:
        return
    if conn is None:
        pool = get_pool()
        async with pool.acquire() as acquired:
            await _insert(acquired, rows)
    else:
        await _insert(conn, rows)


async def _insert(conn, rows):
    await conn.executemany(
        """INSERT INTO game_player_results
           (game_key, game_type, user_id, player_name, result)
           VALUES($1,$2,$3,$4,$5)
           ON CONFLICT (game_key, user_id) DO NOTHING""",
        rows,
    )


async def get_game_leaderboard(result: str, limit: int = 10):
    if result not in ("win", "loss"):
        raise ValueError("Invalid game result")
    pool = get_pool()
    return await pool.fetch(
        """SELECT r.user_id,
                  COALESCE(NULLIF(MAX(u.first_name), ''),
                           NULLIF(MAX(u.username), ''),
                           MAX(r.player_name), 'لاعب') AS name,
                  COUNT(*)::BIGINT AS total
           FROM game_player_results r
           LEFT JOIN users u ON u.user_id = r.user_id
           WHERE r.result = $1
             AND COALESCE(u.is_bot, FALSE) = FALSE
             AND COALESCE(u.first_name, '') <> 'Deleted Account'
           GROUP BY r.user_id
           ORDER BY total DESC, r.user_id ASC
           LIMIT $2""",
        result, max(1, min(int(limit), 10)),
    )
