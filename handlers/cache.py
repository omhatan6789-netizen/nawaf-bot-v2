"""Small bounded in-process cache; all database access remains async."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from database.users import ensure_user as ensure_user_in_db, get_user as get_user_from_db

CACHE_TTL = 900
CACHE_MAX_USERS = 20_000
_user_cache: OrderedDict[int, tuple[float, dict[str, Any]]] = OrderedDict()
_load_locks: dict[int, asyncio.Lock] = {}


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    joined = data.get("joined_date")
    if joined is None:
        data["joined_date"] = "غير معروف"
    elif hasattr(joined, "strftime"):
        data["joined_date"] = joined.strftime("%Y/%m/%d")
    data["messages"] = int(data.get("messages") or 0)
    data["points"] = int(data.get("points") or 0)
    data["rank"] = data.get("rank") or "عضو"
    data["first_name"] = data.get("first_name") or ""
    return data


def _put(user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    _user_cache[user_id] = (time.monotonic() + CACHE_TTL, data)
    _user_cache.move_to_end(user_id)
    while len(_user_cache) > CACHE_MAX_USERS:
        _user_cache.popitem(last=False)
    return data


def get_cached_user(user_id: int) -> dict[str, Any] | None:
    entry = _user_cache.get(user_id)
    if entry is None:
        return None
    expires, data = entry
    if expires <= time.monotonic():
        _user_cache.pop(user_id, None)
        return None
    _user_cache.move_to_end(user_id)
    return data


def set_cached_user(user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    return _put(user_id, data)


async def get_user_data(user_id: int) -> dict[str, Any] | None:
    cached = get_cached_user(user_id)
    if cached is not None:
        return cached
    lock = _load_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        cached = get_cached_user(user_id)
        if cached is not None:
            return cached
        row = await get_user_from_db(user_id)
        if row is None:
            return None
        return _put(user_id, _row_to_dict(row))


async def ensure_user_loaded(
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    is_bot: bool = False,
) -> dict[str, Any]:
    cached = get_cached_user(user_id)
    if cached is not None:
        if username is not None:
            cached["username"] = username
        if first_name is not None:
            cached["first_name"] = first_name
        if last_name is not None:
            cached["last_name"] = last_name
        return cached
    lock = _load_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        cached = get_cached_user(user_id)
        if cached is not None:
            return cached
        row = await ensure_user_in_db(
            user_id, username=username, first_name=first_name,
            last_name=last_name, is_bot=is_bot,
        )
        return _put(user_id, _row_to_dict(row))


def increment_cached_messages(
    user_id: int,
    amount: int = 1,
    username: str | None = None,
    first_name: str | None = None,
) -> dict[str, Any]:
    data = get_cached_user(user_id)
    if data is None:
        data = {
            "user_id": user_id, "messages": 0, "rank": "عضو",
            "joined_date": "غير معروف", "username": username,
            "first_name": first_name or "", "points": 0,
        }
        _put(user_id, data)
    data["messages"] = int(data.get("messages") or 0) + amount
    if username is not None:
        data["username"] = username
    if first_name is not None:
        data["first_name"] = first_name
    return data


def set_cached_points(user_id: int, points: int) -> None:
    data = get_cached_user(user_id)
    if data is not None:
        data["points"] = int(points)


def set_cached_rank(user_id: int, rank: str) -> None:
    data = get_cached_user(user_id)
    if data is not None:
        data["rank"] = rank or "عضو"


def update_cached_profile(
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    data = get_cached_user(user_id)
    if data is None:
        data = {
            "user_id": user_id, "messages": 0, "rank": "عضو",
            "joined_date": "غير معروف", "username": username,
            "first_name": first_name or "", "points": 0,
        }
        _put(user_id, data)
    if username is not None:
        data["username"] = username
    if first_name is not None:
        data["first_name"] = first_name


def clear_cached_user(user_id: int) -> None:
    _user_cache.pop(user_id, None)


def clear_all_user_cache() -> None:
    _user_cache.clear()


def get_cache_size() -> int:
    return len(_user_cache)
