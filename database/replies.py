"""Async PostgreSQL repository and process-local cache for custom replies."""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from typing import Any

from database.pool import get_pool

_reply_cache: dict[str, tuple] | None = None
_special_cache: list[tuple] | None = None
_cache_lock = asyncio.Lock()


def _decode_entities(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


async def load_replies_cache(force: bool = False):
    global _reply_cache, _special_cache
    if not force and _reply_cache is not None and _special_cache is not None:
        return _reply_cache, _special_cache
    async with _cache_lock:
        if not force and _reply_cache is not None and _special_cache is not None:
            return _reply_cache, _special_cache
        pool = get_pool()
        normal_rows, special_rows = await asyncio.gather(
            pool.fetch("SELECT name,text,type,caption,entities FROM replies"),
            pool.fetch("SELECT name,text,type,caption,entities FROM special_replies"),
        )
        _reply_cache = {
            row["name"]: (
                row["text"], row["type"], row["caption"],
                _decode_entities(row["entities"]),
            )
            for row in normal_rows
        }
        _special_cache = [
            (
                row["name"], row["text"], row["type"],
                row["caption"], _decode_entities(row["entities"]),
            )
            for row in special_rows
        ]
        return _reply_cache, _special_cache


def invalidate_replies_cache() -> None:
    global _reply_cache, _special_cache
    _reply_cache = None
    _special_cache = None


async def save_reply(name: str, content: str, reply_type: str, caption: str | None,
                     entities: Any = None, special: bool = False) -> None:
    table = "special_replies" if special else "replies"
    pool = get_pool()
    await pool.execute(
        f"""INSERT INTO {table}(name,text,type,caption,entities)
            VALUES($1,$2,$3,$4,$5::jsonb)
            ON CONFLICT(name) DO UPDATE SET
                text=EXCLUDED.text,type=EXCLUDED.type,
                caption=EXCLUDED.caption,entities=EXCLUDED.entities""",
        name, content, reply_type, caption,
        json.dumps(entities, ensure_ascii=False) if entities is not None else None,
    )
    invalidate_replies_cache()


async def get_reply(name: str, special: bool = False):
    table = "special_replies" if special else "replies"
    row = await get_pool().fetchrow(
        f"SELECT name FROM {table} WHERE name=$1", name
    )
    return row


async def delete_reply(name: str, special: bool = False) -> bool:
    table = "special_replies" if special else "replies"
    result = await get_pool().execute(f"DELETE FROM {table} WHERE name=$1", name)
    deleted = result.endswith(" 1")
    if deleted:
        invalidate_replies_cache()
    return deleted


async def list_replies(special: bool = False) -> list[str]:
    table = "special_replies" if special else "replies"
    rows = await get_pool().fetch(f"SELECT name FROM {table} ORDER BY name")
    return [row["name"] for row in rows]


async def delete_all_replies(special: bool = False) -> int:
    table = "special_replies" if special else "replies"
    result = await get_pool().execute(f"DELETE FROM {table}")
    invalidate_replies_cache()
    return int(result.rsplit(" ", 1)[-1])
