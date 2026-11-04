"""Async PostgreSQL repository for moderation, warnings and sanctions."""
from __future__ import annotations

import time
from typing import Any

from database.pool import get_pool

_settings_cache: dict[int, tuple[float, dict[str, bool]]] = {}
_mute_cache: dict[tuple[int, int], tuple[float, bool]] = {}
CACHE_TTL = 10.0


async def ensure_chat(chat_id: int) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO chats(chat_id,chat_type,title)
           VALUES($1,'supergroup','')
           ON CONFLICT(chat_id) DO NOTHING""",
        int(chat_id),
    )


async def get_moderation_settings(chat_id: int) -> dict[str, bool]:
    chat_id = int(chat_id)
    cached = _settings_cache.get(chat_id)
    now = time.monotonic()
    if cached and cached[0] > now:
        return dict(cached[1])
    await ensure_chat(chat_id)
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO moderation_settings(chat_id,durations_enabled,reasons_enabled)
           VALUES($1,FALSE,FALSE)
           ON CONFLICT(chat_id) DO UPDATE SET chat_id=EXCLUDED.chat_id
           RETURNING durations_enabled,reasons_enabled""",
        chat_id,
    )
    result = {
        "durations_enabled": bool(row["durations_enabled"]),
        "reasons_enabled": bool(row["reasons_enabled"]),
    }
    _settings_cache[chat_id] = (now + CACHE_TTL, result)
    return dict(result)


async def set_moderation_setting(chat_id: int, column: str, enabled: bool) -> None:
    columns = {"durations_enabled", "reasons_enabled"}
    if column not in columns:
        raise ValueError("Invalid moderation setting")
    await ensure_chat(chat_id)
    pool = get_pool()
    await pool.execute(
        f"""INSERT INTO moderation_settings(chat_id,{column})
            VALUES($1,$2)
            ON CONFLICT(chat_id) DO UPDATE SET {column}=EXCLUDED.{column}""",
        int(chat_id), bool(enabled),
    )
    _settings_cache.pop(int(chat_id), None)


async def save_target_user(user: Any) -> None:
    if not user:
        return
    pool = get_pool()
    await pool.execute(
        """INSERT INTO users(user_id,username,first_name,last_name,is_bot)
           VALUES($1,$2,$3,$4,$5)
           ON CONFLICT(user_id) DO UPDATE SET
             username=COALESCE(EXCLUDED.username,users.username),
             first_name=COALESCE(EXCLUDED.first_name,users.first_name),
             last_name=COALESCE(EXCLUDED.last_name,users.last_name),
             updated_at=NOW()""",
        int(user.id), getattr(user, "username", None),
        getattr(user, "first_name", None), getattr(user, "last_name", None),
        bool(getattr(user, "is_bot", False)),
    )


async def get_user_by_id(user_id: int) -> Any | None:
    pool = get_pool()
    return await pool.fetchrow(
        "SELECT user_id,username,first_name FROM users WHERE user_id=$1",
        int(user_id),
    )


async def get_user_by_username(username: str) -> Any | None:
    pool = get_pool()
    return await pool.fetchrow(
        """SELECT user_id,username,first_name FROM users
           WHERE LOWER(username)=$1 LIMIT 1""",
        (username or "").lstrip("@").lower(),
    )


async def save_sanction(
    table: str, chat_id: int, user: Any, until_time: Any,
    reason: str | None, by_user: int,
) -> None:
    allowed = {"bot_mutes", "restrictions", "moderation_bans"}
    if table not in allowed:
        raise ValueError("Invalid moderation table")
    await ensure_chat(chat_id)
    await save_target_user(user)
    pool = get_pool()
    await pool.execute(
        f"""INSERT INTO {table}
            (chat_id,user_id,username,first_name,until_time,reason,by_user)
            VALUES($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET
              username=EXCLUDED.username,first_name=EXCLUDED.first_name,
              until_time=EXCLUDED.until_time,reason=EXCLUDED.reason,
              by_user=EXCLUDED.by_user""",
        int(chat_id), int(user.id), getattr(user, "username", None),
        getattr(user, "first_name", None), until_time, reason, int(by_user),
    )
    if table == "bot_mutes":
        until_ts = until_time.timestamp() if hasattr(until_time, "timestamp") else None
        _mute_cache[(int(chat_id), int(user.id))] = (
            time.monotonic() + CACHE_TTL,
            until_ts is None or until_ts > time.time(),
        )


async def delete_sanction(table: str, chat_id: int, user_id: int) -> None:
    if table not in {"bot_mutes", "restrictions", "moderation_bans"}:
        raise ValueError("Invalid moderation table")
    pool = get_pool()
    await pool.execute(
        f"DELETE FROM {table} WHERE chat_id=$1 AND user_id=$2",
        int(chat_id), int(user_id),
    )
    if table == "bot_mutes":
        _mute_cache[(int(chat_id), int(user_id))] = (time.monotonic() + CACHE_TTL, False)


async def get_active_mute(chat_id: int, user_id: int) -> bool:
    key = (int(chat_id), int(user_id))
    now = time.monotonic()
    cached = _mute_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT until_time FROM bot_mutes WHERE chat_id=$1 AND user_id=$2",
        *key,
    )
    if not row:
        result = False
    else:
        until = row["until_time"]
        result = until is None or until.timestamp() > time.time()
        if not result:
            await pool.execute(
                "DELETE FROM bot_mutes WHERE chat_id=$1 AND user_id=$2",
                *key,
            )
    _mute_cache[key] = (now + CACHE_TTL, result)
    return result


async def get_user_restrictions(chat_id: int, user_id: int) -> list[str]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT 'كتم' AS kind FROM bot_mutes WHERE chat_id=$1 AND user_id=$2
           UNION ALL SELECT 'تقييد' FROM restrictions WHERE chat_id=$1 AND user_id=$2
           UNION ALL SELECT 'حظر' FROM moderation_bans WHERE chat_id=$1 AND user_id=$2""",
        int(chat_id), int(user_id),
    )
    return [row["kind"] for row in rows]


async def get_sanction_rows(table: str, chat_id: int) -> list[Any]:
    if table not in {"bot_mutes", "restrictions", "moderation_bans"}:
        raise ValueError("Invalid moderation table")
    pool = get_pool()
    return await pool.fetch(
        f"""SELECT user_id,username,first_name,until_time,reason,by_user
            FROM {table} WHERE chat_id=$1 ORDER BY user_id""",
        int(chat_id),
    )


async def clear_sanction_table(table: str, chat_id: int) -> list[int]:
    if table not in {"bot_mutes", "restrictions", "moderation_bans"}:
        raise ValueError("Invalid moderation table")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                f"SELECT user_id FROM {table} WHERE chat_id=$1",
                int(chat_id),
            )
            await conn.execute(f"DELETE FROM {table} WHERE chat_id=$1", int(chat_id))
    ids = [int(row["user_id"]) for row in rows]
    if table == "bot_mutes":
        for user_id in ids:
            _mute_cache[(int(chat_id), user_id)] = (time.monotonic() + CACHE_TTL, False)
    return ids


async def get_warning_count(chat_id: int, user_id: int) -> int:
    pool = get_pool()
    return int(await pool.fetchval(
        "SELECT COUNT(*) FROM warnings WHERE chat_id=$1 AND user_id=$2",
        int(chat_id), int(user_id),
    ) or 0)


async def add_warning(chat_id: int, user_id: int, source: str = "manual") -> int:
    await ensure_chat(chat_id)
    pool = get_pool()
    await pool.execute(
        """INSERT INTO warnings(chat_id,user_id,source)
           VALUES($1,$2,$3)""",
        int(chat_id), int(user_id), source,
    )
    return await get_warning_count(chat_id, user_id)


async def clear_warnings(chat_id: int, user_id: int) -> int:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM warnings WHERE chat_id=$1 AND user_id=$2",
        int(chat_id), int(user_id),
    )
    return int(result.rsplit(" ", 1)[-1])


async def get_expired_sanctions(now=None) -> dict[str, list[tuple[int, int]]]:
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    pool = get_pool()
    result = {"mutes": [], "restrictions": [], "bans": []}
    tables = (
        ("bot_mutes", "mutes"),
        ("restrictions", "restrictions"),
        ("moderation_bans", "bans"),
    )
    for table, key in tables:
        rows = await pool.fetch(
            f"""SELECT chat_id,user_id FROM {table}
                WHERE until_time IS NOT NULL AND until_time <= $1""",
            now,
        )
        result[key] = [(int(row["chat_id"]), int(row["user_id"])) for row in rows]
    return result


async def get_user_messages(user_id: int) -> int:
    pool = get_pool()
    return int(await pool.fetchval(
        "SELECT messages FROM users WHERE user_id=$1", int(user_id)
    ) or 0)


async def get_expired_moderation_rows(now=None) -> dict[str, list[tuple[int, int]]]:
    """Atomically fetch and remove expired DB sanctions; Telegram updates happen after."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    pool = get_pool()
    result = {"mutes": [], "restrictions": [], "bans": []}
    async with pool.acquire() as conn:
        async with conn.transaction():
            for table, key in (
                ("bot_mutes", "mutes"),
                ("restrictions", "restrictions"),
                ("moderation_bans", "bans"),
            ):
                rows = await conn.fetch(
                    f"""DELETE FROM {table}
                        WHERE until_time IS NOT NULL AND until_time <= $1
                        RETURNING chat_id,user_id""",
                    now,
                )
                result[key] = [(int(r["chat_id"]), int(r["user_id"])) for r in rows]
    for chat_id, user_id in result["mutes"]:
        _mute_cache[(chat_id, user_id)] = (time.monotonic() + CACHE_TTL, False)
    return result
