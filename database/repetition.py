"""Async repository for repetition-protection settings."""
from __future__ import annotations

import time

from database.pool import get_pool
from database.moderation import ensure_chat

DEFAULTS = {
    "enabled": False,
    "limit": 3,
    "seconds": 5,
    "action": "mute",
    "punishment_duration": 300,
    "rank": "عضو",
}
_ALLOWED_COLUMNS = {
    "repetition_enabled", "repetition_limit", "repetition_seconds",
    "repetition_action", "repetition_punishment_duration", "repetition_rank",
}
_cache: dict[int, tuple[float, dict]] = {}
_CACHE_TTL = 10.0


async def get_repetition_settings(chat_id: int) -> dict:
    chat_id = int(chat_id)
    cached = _cache.get(chat_id)
    now = time.monotonic()
    if cached and cached[0] > now:
        return dict(cached[1])
    await ensure_chat(chat_id)
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO protection_settings(chat_id)
           VALUES($1)
           ON CONFLICT(chat_id) DO UPDATE SET chat_id=EXCLUDED.chat_id
           RETURNING repetition_enabled,repetition_limit,repetition_seconds,
                     repetition_action,repetition_punishment_duration,repetition_rank""",
        chat_id,
    )
    result = {
        "enabled": bool(row["repetition_enabled"]),
        "limit": max(1, int(row["repetition_limit"] or 3)),
        "seconds": max(1, int(row["repetition_seconds"] or 5)),
        "action": row["repetition_action"] if row["repetition_action"] in ("mute", "restrict", "ban") else "mute",
        "punishment_duration": max(1, int(row["repetition_punishment_duration"] or 300)),
        "rank": row["repetition_rank"] if row["repetition_rank"] else "عضو",
    }
    _cache[chat_id] = (now + _CACHE_TTL, result)
    return dict(result)


async def update_repetition_setting(chat_id: int, column: str, value) -> None:
    if column not in _ALLOWED_COLUMNS:
        raise ValueError("Invalid repetition setting")
    await ensure_chat(chat_id)
    pool = get_pool()
    await pool.execute(
        f"""INSERT INTO protection_settings(chat_id,{column})
            VALUES($1,$2)
            ON CONFLICT(chat_id) DO UPDATE SET {column}=EXCLUDED.{column}""",
        int(chat_id), value,
    )
    _cache.pop(int(chat_id), None)
