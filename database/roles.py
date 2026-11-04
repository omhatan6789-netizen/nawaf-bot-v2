"""Async rank and permission repository.

All database access in this module is asyncpg-only. Frequently-read role data is
cached briefly; every mutation invalidates the affected cache entries.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from database.pool import get_pool

OWNER_ID = 8453977662
DEV_PRIMARY = "primary"
DEV_SECONDARY = "secondary"

RANK_LEVELS = {
    "عضو": 0,
    "مميز": 1,
    "ادمن": 2,
    "ادمن اساسي": 3,
    "نائب المالك": 4,
    "المالك": 5,
    "Dev": 6,
}
NORMAL_RANKS = ("مميز", "ادمن", "ادمن اساسي", "نائب المالك", "المالك")
RANK_ORDER_SQL = """CASE rank
    WHEN 'المالك' THEN 5
    WHEN 'نائب المالك' THEN 4
    WHEN 'ادمن اساسي' THEN 3
    WHEN 'ادمن' THEN 2
    WHEN 'مميز' THEN 1
    ELSE 0 END"""

_CACHE_TTL = 30.0
_CACHE_MAX = 20_000
_cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()


def _cache_get(key: tuple):
    item = _cache.get(key)
    if item is None:
        return None, False
    expires, value = item
    if expires <= time.monotonic():
        _cache.pop(key, None)
        return None, False
    _cache.move_to_end(key)
    return value, True


def _cache_set(key: tuple, value: Any) -> None:
    _cache[key] = (time.monotonic() + _CACHE_TTL, value)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _invalidate(*prefix: Any) -> None:
    for key in list(_cache):
        if key[:len(prefix)] == prefix:
            _cache.pop(key, None)


def normalize_rank(rank: Any) -> str:
    value = str(rank or "").strip()
    return value if value in RANK_LEVELS else "عضو"


def get_highest_rank(ranks) -> str:
    return max((normalize_rank(r) for r in ranks), key=lambda r: RANK_LEVELS[r], default="عضو")


async def get_developer_type(user_id: int) -> str | None:
    if int(user_id) == OWNER_ID:
        return DEV_PRIMARY
    key = ("developer", int(user_id))
    value, found = _cache_get(key)
    if found:
        return value
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT developer_type FROM developers WHERE user_id=$1",
        int(user_id),
    )
    result = row["developer_type"] if row else None
    _cache_set(key, result)
    return result


async def is_primary_developer(user_id: int) -> bool:
    return await get_developer_type(user_id) == DEV_PRIMARY


async def is_secondary_developer(user_id: int) -> bool:
    return await get_developer_type(user_id) == DEV_SECONDARY


async def is_developer(user_id: int) -> bool:
    return await get_developer_type(user_id) is not None


async def get_group_ranks(chat_id: int, user_id: int) -> list[str]:
    if int(user_id) == OWNER_ID or await is_secondary_developer(user_id):
        return ["Dev"]
    key = ("group_ranks", int(chat_id), int(user_id))
    value, found = _cache_get(key)
    if found:
        return list(value)
    pool = get_pool()
    rows = await pool.fetch(
        f"""SELECT rank FROM group_user_ranks
            WHERE chat_id=$1 AND user_id=$2 AND rank = ANY($3::text[])
            ORDER BY {RANK_ORDER_SQL} DESC""",
        int(chat_id), int(user_id), list(NORMAL_RANKS),
    )
    ranks = [normalize_rank(row["rank"]) for row in rows]
    if not ranks:
        ranks = ["عضو"]
    _cache_set(key, tuple(ranks))
    return ranks


async def get_group_rank(chat_id: int, user_id: int) -> str:
    return get_highest_rank(await get_group_ranks(chat_id, user_id))


async def get_global_rank(user_id: int) -> str:
    if int(user_id) == OWNER_ID or await is_developer(user_id):
        return "Dev"
    key = ("global_rank", int(user_id))
    value, found = _cache_get(key)
    if found:
        return value
    pool = get_pool()
    row = await pool.fetchrow("SELECT rank FROM ranks WHERE user_id=$1", int(user_id))
    result = normalize_rank(row["rank"]) if row else "عضو"
    _cache_set(key, result)
    return result


async def get_rank(user_id: int, chat_id: int | None = None) -> str:
    if int(user_id) == OWNER_ID or await is_developer(user_id):
        return "Dev"
    if chat_id is not None:
        return await get_group_rank(chat_id, user_id)
    return await get_global_rank(user_id)


async def get_rank_level(user_id: int, chat_id: int | None = None) -> int:
    if int(user_id) == OWNER_ID:
        return 7
    if await is_secondary_developer(user_id):
        return 6
    rank = await get_rank(user_id, chat_id)
    return RANK_LEVELS.get(rank, 0)


async def has_group_rank(chat_id: int, user_id: int, rank: str) -> bool:
    rank = normalize_rank(rank)
    if rank == "عضو":
        return True
    if rank == "Dev":
        return await is_developer(user_id)
    return rank in await get_group_ranks(chat_id, user_id)


async def add_group_rank(chat_id: int, user_id: int, rank: str) -> bool:
    rank = normalize_rank(rank)
    if rank not in NORMAL_RANKS:
        return False
    pool = get_pool()
    result = await pool.execute(
        """INSERT INTO group_user_ranks(chat_id,user_id,rank)
           VALUES($1,$2,$3) ON CONFLICT(chat_id,user_id,rank) DO NOTHING""",
        int(chat_id), int(user_id), rank,
    )
    _invalidate("group_ranks", int(chat_id), int(user_id))
    _invalidate("command_permission")
    return result.endswith("1")


async def remove_group_rank(chat_id: int, user_id: int, rank: str) -> bool:
    rank = normalize_rank(rank)
    if rank not in NORMAL_RANKS:
        return False
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM group_user_ranks WHERE chat_id=$1 AND user_id=$2 AND rank=$3",
        int(chat_id), int(user_id), rank,
    )
    _invalidate("group_ranks", int(chat_id), int(user_id))
    _invalidate("command_permission")
    return result.endswith("1")


async def update_developer_rank(user_id: int, rank: str, added_by: int = OWNER_ID) -> None:
    user_id = int(user_id)
    if user_id == OWNER_ID:
        raise ValueError("Cannot modify the primary developer")
    pool = get_pool()
    if rank == "Dev":
        await pool.execute(
            """INSERT INTO developers(user_id,developer_type,added_by,added_date)
               VALUES($1,$2,$3,NOW())
               ON CONFLICT(user_id) DO UPDATE SET
                   developer_type=EXCLUDED.developer_type,
                   added_by=EXCLUDED.added_by,
                   added_date=NOW()""",
            user_id, DEV_SECONDARY, int(added_by),
        )
    else:
        await pool.execute(
            "DELETE FROM developers WHERE user_id=$1 AND developer_type=$2",
            user_id, DEV_SECONDARY,
        )
    _invalidate("developer", user_id)
    _invalidate("global_rank", user_id)
    _invalidate("group_ranks")
    _invalidate("command_permission")


async def set_global_rank(user_id: int, rank: str) -> None:
    rank = normalize_rank(rank)
    if rank == "Dev":
        await update_developer_rank(user_id, "Dev")
        return
    pool = get_pool()
    await pool.execute(
        """INSERT INTO ranks(user_id,rank) VALUES($1,$2)
           ON CONFLICT(user_id) DO UPDATE SET rank=EXCLUDED.rank""",
        int(user_id), rank,
    )
    _invalidate("global_rank", int(user_id))


async def get_command_locks() -> dict[str, str]:
    key = ("command_locks",)
    value, found = _cache_get(key)
    if found:
        return dict(value)
    pool = get_pool()
    rows = await pool.fetch("SELECT command,rank FROM command_locks")
    result = {row["command"]: normalize_rank(row["rank"]) for row in rows if row["command"]}
    _cache_set(key, result)
    return dict(result)


async def set_command_lock(command: str, rank: str) -> None:
    command = " ".join((command or "").split())
    rank = normalize_rank(rank)
    if not command or rank not in RANK_LEVELS or rank == "عضو":
        raise ValueError("Invalid command lock")
    pool = get_pool()
    await pool.execute(
        """INSERT INTO command_locks(command,rank) VALUES($1,$2)
           ON CONFLICT(command) DO UPDATE SET rank=EXCLUDED.rank""",
        command, rank,
    )
    _invalidate("command_locks")
    _invalidate("command_permission")


async def remove_command_lock(command: str) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM command_locks WHERE command=$1", command)
    _invalidate("command_locks")
    _invalidate("command_permission")


async def check_command_permission(user_id: int, command: str, chat_id: int | None = None):
    command = " ".join((command or "").split())
    key = ("command_permission", int(user_id), command, chat_id)
    value, found = _cache_get(key)
    if found:
        return value
    locks = await get_command_locks()
    required = locks.get(command)
    if not required:
        result = (True, None)
    elif await is_developer(user_id):
        result = (True, required)
    else:
        level = await get_rank_level(user_id, chat_id)
        result = (level >= RANK_LEVELS.get(required, 0), required)
    _cache_set(key, result)
    return result


async def set_user_permission(chat_id: int, user_id: int, command: str, allowed: bool) -> None:
    command = " ".join((command or "").split())
    if not command:
        raise ValueError("Permission command cannot be empty")
    pool = get_pool()
    await pool.execute(
        """INSERT INTO group_user_permissions(chat_id,user_id,permission,allowed)
           VALUES($1,$2,$3,$4)
           ON CONFLICT(chat_id,user_id,permission)
           DO UPDATE SET allowed=EXCLUDED.allowed""",
        int(chat_id), int(user_id), command, bool(allowed),
    )
    _invalidate("user_permission", int(chat_id), int(user_id), command)


async def check_user_permission(chat_id: int, user_id: int, command: str):
    command = " ".join((command or "").split())
    if not command:
        return None
    if await is_primary_developer(user_id):
        return True
    key = ("user_permission", int(chat_id), int(user_id), command)
    value, found = _cache_get(key)
    if found:
        return value
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT allowed FROM group_user_permissions
           WHERE chat_id=$1 AND user_id=$2 AND permission=$3""",
        int(chat_id), int(user_id), command,
    )
    result = bool(row["allowed"]) if row else None
    _cache_set(key, result)
    return result


async def get_group_rank_users(chat_id: int) -> list[tuple[int, str]]:
    pool = get_pool()
    rows = await pool.fetch(
        f"""SELECT user_id,rank FROM group_user_ranks
            WHERE chat_id=$1 AND rank=ANY($2::text[])
            ORDER BY {RANK_ORDER_SQL} DESC,user_id""",
        int(chat_id), list(NORMAL_RANKS),
    )
    return [(int(row["user_id"]), row["rank"]) for row in rows]


async def get_users_by_group_rank(chat_id: int, rank: str) -> list[int]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT user_id FROM group_user_ranks WHERE chat_id=$1 AND rank=$2 ORDER BY user_id",
        int(chat_id), normalize_rank(rank),
    )
    return [int(row["user_id"]) for row in rows]


async def get_secondary_developers() -> list[int]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT user_id FROM developers WHERE developer_type=$1 ORDER BY user_id",
        DEV_SECONDARY,
    )
    return [int(row["user_id"]) for row in rows]


async def clear_secondary_developers() -> int:
    pool = get_pool()
    result = await pool.execute(
        "DELETE FROM developers WHERE developer_type=$1",
        DEV_SECONDARY,
    )
    _invalidate("developer")
    _invalidate("global_rank")
    _invalidate("group_ranks")
    _invalidate("command_permission")
    return int(result.rsplit(" ", 1)[-1])


async def clear_rank_list(chat_id: int, rank: str) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM group_user_ranks WHERE chat_id=$1 AND rank=$2",
                int(chat_id), normalize_rank(rank),
            )
            await conn.execute(
                "DELETE FROM group_user_ranks WHERE chat_id=$1 AND rank=$2",
                int(chat_id), normalize_rank(rank),
            )
    _invalidate("group_ranks")
    _invalidate("command_permission")
    return int(row["n"])


async def clear_group_ranks(chat_id: int) -> dict[str, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """SELECT rank,COUNT(*) AS n FROM group_user_ranks
                   WHERE chat_id=$1 AND rank=ANY($2::text[]) GROUP BY rank""",
                int(chat_id), list(NORMAL_RANKS),
            )
            counts = {rank: 0 for rank in NORMAL_RANKS}
            for row in rows:
                counts[row["rank"]] = int(row["n"])
            await conn.execute("DELETE FROM group_user_ranks WHERE chat_id=$1", int(chat_id))
    _invalidate("group_ranks")
    _invalidate("command_permission")
    return counts


async def clear_lower_group_ranks(chat_id: int, user_id: int, actor_level: int) -> int:
    pool = get_pool()
    result = await pool.execute(
        """DELETE FROM group_user_ranks
           WHERE chat_id=$1 AND user_id=$2
           AND CASE rank WHEN 'مميز' THEN 1 WHEN 'ادمن' THEN 2
               WHEN 'ادمن اساسي' THEN 3 WHEN 'نائب المالك' THEN 4
               WHEN 'المالك' THEN 5 ELSE 0 END < $3""",
        int(chat_id), int(user_id), int(actor_level),
    )
    _invalidate("group_ranks", int(chat_id), int(user_id))
    _invalidate("command_permission")
    return int(result.rsplit(" ", 1)[-1])


async def clear_all_role_caches() -> None:
    _cache.clear()


async def check_user_permission(chat_id: int, user_id: int, command: str):
    """Return True/False for an explicit override, or None when unset."""
    command = " ".join((command or "").split())
    if not command:
        return None
    if await is_primary_developer(user_id):
        return True
    key = ("user_permission", int(chat_id), int(user_id), command)
    value, found = _cache_get(key)
    if found:
        return value
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT allowed FROM group_user_permissions
           WHERE chat_id=$1 AND user_id=$2 AND permission=$3""",
        int(chat_id), int(user_id), command,
    )
    result = bool(row["allowed"]) if row else None
    _cache_set(key, result)
    return result
