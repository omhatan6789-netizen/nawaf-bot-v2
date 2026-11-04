"""Async repository for profile cards and per-admin group replies."""
from __future__ import annotations

import time
from typing import Any

from .pool import get_pool

OWNER_ID = 8453977662
_ADMIN_REPLY_CACHE_TTL = 20.0
_admin_reply_cache: dict[int, tuple[float, dict[str, int]]] = {}
_GROUP_SETTINGS_CACHE_TTL = 15.0
_group_settings_cache: dict[int, tuple[float, Any | None]] = {}


def _invalidate_admin_replies(chat_id: int) -> None:
    _admin_reply_cache.pop(int(chat_id), None)


async def get_saved_developer() -> tuple[int, str | None]:
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT user_id, username FROM profile_settings WHERE profile_type='developer'"
    )
    if not row:
        return OWNER_ID, None
    return int(row["user_id"]), row["username"]


async def save_developer(user_id: int, username: str | None) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO profile_settings(profile_type,user_id,username)
           VALUES('developer',$1,$2)
           ON CONFLICT(profile_type) DO UPDATE SET
               user_id=EXCLUDED.user_id, username=EXCLUDED.username""",
        int(user_id), username,
    )


async def ensure_group_settings(chat_id: int) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO group_profile_settings(chat_id)
           VALUES($1) ON CONFLICT(chat_id) DO NOTHING""",
        int(chat_id),
    )
    _group_settings_cache.pop(int(chat_id), None)


async def get_group_settings(chat_id: int) -> Any | None:
    chat_id = int(chat_id)
    cached = _group_settings_cache.get(chat_id)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT owner_user_id, owner_username, admin_replies_enabled
           FROM group_profile_settings WHERE chat_id=$1""",
        chat_id,
    )
    _group_settings_cache[chat_id] = (now + _GROUP_SETTINGS_CACHE_TTL, row)
    return row


async def save_group_owner(chat_id: int, user_id: int, username: str | None) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO group_profile_settings(chat_id,owner_user_id,owner_username)
           VALUES($1,$2,$3)
           ON CONFLICT(chat_id) DO UPDATE SET
               owner_user_id=EXCLUDED.owner_user_id,
               owner_username=EXCLUDED.owner_username""",
        int(chat_id), int(user_id), username,
    )
    _group_settings_cache.pop(int(chat_id), None)


async def set_admin_replies_status(chat_id: int, enabled: bool) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO group_profile_settings(chat_id,admin_replies_enabled)
           VALUES($1,$2)
           ON CONFLICT(chat_id) DO UPDATE SET
               admin_replies_enabled=EXCLUDED.admin_replies_enabled""",
        int(chat_id), bool(enabled),
    )
    _group_settings_cache.pop(int(chat_id), None)


async def save_admin_reply(chat_id: int, admin_user_id: int, reply_name: str) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO admin_replies(chat_id,admin_user_id,reply_name,created_date)
           VALUES($1,$2,$3,NOW())""",
        int(chat_id), int(admin_user_id), reply_name,
    )
    _invalidate_admin_replies(chat_id)


async def get_admin_reply_by_user(chat_id: int, admin_user_id: int) -> str | None:
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT reply_name FROM admin_replies
           WHERE chat_id=$1 AND admin_user_id=$2""",
        int(chat_id), int(admin_user_id),
    )
    return row["reply_name"] if row else None


async def get_admin_reply_by_name(chat_id: int, reply_name: str) -> tuple[int, str] | None:
    chat_id = int(chat_id)
    now = time.monotonic()
    cached = _admin_reply_cache.get(chat_id)
    if cached and cached[0] > now:
        user_id = cached[1].get(reply_name)
        return (user_id, reply_name) if user_id is not None else None

    pool = get_pool()
    rows = await pool.fetch(
        "SELECT admin_user_id,reply_name FROM admin_replies WHERE chat_id=$1",
        chat_id,
    )
    mapping = {str(row["reply_name"]): int(row["admin_user_id"]) for row in rows}
    _admin_reply_cache[chat_id] = (now + _ADMIN_REPLY_CACHE_TTL, mapping)
    user_id = mapping.get(reply_name)
    return (user_id, reply_name) if user_id is not None else None


async def delete_admin_reply(chat_id: int, admin_user_id: int) -> None:
    pool = get_pool()
    await pool.execute(
        "DELETE FROM admin_replies WHERE chat_id=$1 AND admin_user_id=$2",
        int(chat_id), int(admin_user_id),
    )
    _invalidate_admin_replies(chat_id)


async def delete_all_admin_replies(chat_id: int) -> None:
    pool = get_pool()
    await pool.execute("DELETE FROM admin_replies WHERE chat_id=$1", int(chat_id))
    _invalidate_admin_replies(chat_id)


async def get_all_admin_replies(chat_id: int) -> list[tuple[int, str]]:
    pool = get_pool()
    rows = await pool.fetch(
        """SELECT admin_user_id,reply_name FROM admin_replies
           WHERE chat_id=$1 ORDER BY created_date ASC,admin_user_id ASC""",
        int(chat_id),
    )
    return [(int(row["admin_user_id"]), str(row["reply_name"])) for row in rows]


async def get_group_user_id_by_username(username: str) -> int | None:
    clean = (username or "").strip().lstrip("@").lower()
    if not clean:
        return None
    pool = get_pool()
    row = await pool.fetchrow(
        """SELECT user_id FROM users
           WHERE LOWER(username)=$1 LIMIT 1""",
        clean,
    )
    return int(row["user_id"]) if row else None
