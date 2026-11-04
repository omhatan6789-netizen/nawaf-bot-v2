"""Asyncpg repository and short-lived caches for blocked-word lists."""
from __future__ import annotations

import time
from database.pool import get_pool
from database.moderation import ensure_chat

LIST_IDS = (1, 2)
_SETTINGS_TTL = 10.0
_WORDS_TTL = 30.0
_settings_cache: dict[tuple[int, int], tuple[float, dict]] = {}
_words_cache: dict[tuple[int, int], tuple[float, list[str]]] = {}


def _key(chat_id: int, list_id: int) -> tuple[int, int]:
    chat_id, list_id = int(chat_id), int(list_id)
    if list_id not in LIST_IDS:
        raise ValueError("Invalid blocked words list")
    return chat_id, list_id


def invalidate_blocked_cache(chat_id: int, list_id: int | None = None) -> None:
    chat_id = int(chat_id)
    for key in list(_settings_cache):
        if key[0] == chat_id and (list_id is None or key[1] == int(list_id)):
            _settings_cache.pop(key, None)
    for key in list(_words_cache):
        if key[0] == chat_id and (list_id is None or key[1] == int(list_id)):
            _words_cache.pop(key, None)


async def ensure_list_settings(chat_id: int, list_id: int) -> None:
    chat_id, list_id = _key(chat_id, list_id)
    await ensure_chat(chat_id)
    pool = get_pool()
    await pool.execute(
        """INSERT INTO blocked_words_settings_v2(chat_id,list_id)
           VALUES($1,$2) ON CONFLICT(chat_id,list_id) DO NOTHING""",
        chat_id, list_id,
    )


async def get_settings(chat_id: int, list_id: int) -> dict:
    key = _key(chat_id, list_id)
    cached = _settings_cache.get(key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return dict(cached[1])
    await ensure_list_settings(*key)
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT enabled,action,duration,warning_duration,
                  warning_action,warning_punishment_duration
           FROM blocked_words_settings_v2
           WHERE chat_id=$1 AND list_id=$2""",
        *key,
    )
    result = {
        "enabled": bool(row["enabled"]),
        "action": row["action"] or "mute",
        "duration": row["duration"],
        "warning_duration": row["warning_duration"],
        "warning_action": row["warning_action"],
        "warning_punishment_duration": row["warning_punishment_duration"],
    }
    _settings_cache[key] = (now + _SETTINGS_TTL, result)
    return dict(result)


async def _update_settings(chat_id: int, list_id: int, assignments: dict) -> None:
    key = _key(chat_id, list_id)
    allowed = {
        "enabled", "action", "duration", "warning_duration",
        "warning_action", "warning_punishment_duration",
    }
    if not assignments or any(column not in allowed for column in assignments):
        raise ValueError("Invalid blocked words setting")
    await ensure_list_settings(*key)
    columns = list(assignments)
    values = [assignments[column] for column in columns]
    sets = ", ".join(column + "=$" + str(index + 3) for index, column in enumerate(columns))
    pool = get_pool()
    await pool.execute(
        f"UPDATE blocked_words_settings_v2 SET {sets} WHERE chat_id=$1 AND list_id=$2",
        key[0], key[1], *values,
    )
    _settings_cache.pop(key, None)


async def set_enabled(chat_id: int, list_id: int, enabled: bool) -> None:
    await _update_settings(chat_id, list_id, {"enabled": bool(enabled)})


async def set_direct_action(chat_id: int, list_id: int, action: str, duration: int | None) -> None:
    if action not in ("mute", "restrict", "ban"):
        raise ValueError("Invalid direct punishment")
    await _update_settings(chat_id, list_id, {"action": action, "duration": duration})


async def set_warning_action(
    chat_id: int, list_id: int, warning_duration: int,
    warning_action: str, warning_punishment_duration: int | None,
) -> None:
    if warning_action not in ("mute", "restrict", "ban"):
        raise ValueError("Invalid warning punishment")
    await _update_settings(chat_id, list_id, {
        "action": "warning",
        "warning_duration": int(warning_duration),
        "warning_action": warning_action,
        "warning_punishment_duration": warning_punishment_duration,
    })


async def get_words(chat_id: int, list_id: int) -> list[str]:
    key = _key(chat_id, list_id)
    cached = _words_cache.get(key)
    now = time.monotonic()
    if cached and cached[0] > now:
        return list(cached[1])
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT word FROM blocked_words_v2
           WHERE chat_id=$1 AND list_id=$2 ORDER BY word""",
        *key,
    )
    words = [str(row["word"]) for row in rows]
    _words_cache[key] = (now + _WORDS_TTL, words)
    return list(words)


async def add_words(chat_id: int, list_id: int, words: list[str]) -> None:
    key = _key(chat_id, list_id)
    if not words:
        return
    pool = get_pool()
    await pool.executemany(
        """INSERT INTO blocked_words_v2(chat_id,list_id,word)
           VALUES($1,$2,$3) ON CONFLICT(chat_id,list_id,word) DO NOTHING""",
        [(key[0], key[1], word) for word in words],
    )
    invalidate_blocked_cache(*key)


async def delete_words(chat_id: int, list_id: int, words: list[str]) -> None:
    key = _key(chat_id, list_id)
    if not words:
        return
    pool = get_pool()
    await pool.execute(
        """DELETE FROM blocked_words_v2
           WHERE chat_id=$1 AND list_id=$2 AND word=ANY($3::text[])""",
        key[0], key[1], list(words),
    )
    invalidate_blocked_cache(*key)


async def get_active_warning_count(chat_id: int, list_id: int, user_id: int) -> int:
    key = _key(chat_id, list_id)
    now = int(time.time())
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """DELETE FROM blocked_words_warnings_v2
                   WHERE chat_id=$1 AND list_id=$2 AND user_id=$3 AND expires_at <= $4""",
                key[0], key[1], int(user_id), now,
            )
            return int(await conn.fetchval(
                """SELECT COUNT(*) FROM blocked_words_warnings_v2
                   WHERE chat_id=$1 AND list_id=$2 AND user_id=$3""",
                key[0], key[1], int(user_id),
            ) or 0)


async def add_blocked_warning(chat_id: int, list_id: int, user_id: int, duration: int) -> int:
    key = _key(chat_id, list_id)
    now = int(time.time())
    pool = get_pool()
    await pool.execute(
        """INSERT INTO blocked_words_warnings_v2
           (chat_id,list_id,user_id,expires_at,created_at)
           VALUES($1,$2,$3,$4,$5)""",
        key[0], key[1], int(user_id), now + int(duration), now,
    )
    return await get_active_warning_count(key[0], key[1], user_id)


async def clear_blocked_warnings(chat_id: int, list_id: int, user_id: int) -> int:
    key = _key(chat_id, list_id)
    pool = get_pool()
    result = await pool.execute(
        """DELETE FROM blocked_words_warnings_v2
           WHERE chat_id=$1 AND list_id=$2 AND user_id=$3""",
        key[0], key[1], int(user_id),
    )
    return int(result.rsplit(" ", 1)[-1])


async def cleanup_expired_blocked_warnings() -> int:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM blocked_words_warnings_v2 WHERE expires_at <= $1",
        int(time.time()),
    )
    return int(result.rsplit(" ", 1)[-1])
