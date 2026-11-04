"""One automatic private reply per user every 24 hours (asyncpg + Pyrogram)."""
from __future__ import annotations

import asyncio
import time

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from database.pool import get_pool
from music_call import get_music_client

REPLY_TEXT = "الملك مشغول شوي لو فضى لك بيرد عليك🙏🏻"
REPLY_INTERVAL = 24 * 60 * 60
_client = None
_handler = None
_HANDLER_GROUP = 1000
_user_locks = {}


async def _claim_reply_slot(user_id, now):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            previous_time = await conn.fetchval(
                "SELECT replied_at FROM auto_private_replied WHERE user_id=$1",
                int(user_id),
            )
            claimed = await conn.fetchval(
                """INSERT INTO auto_private_replied(user_id,replied_at) VALUES($1,$2)
                   ON CONFLICT(user_id) DO UPDATE SET replied_at=EXCLUDED.replied_at
                   WHERE auto_private_replied.replied_at <= $2 - $3
                   RETURNING user_id""",
                int(user_id), int(now), REPLY_INTERVAL,
            )
            return claimed is not None, int(previous_time) if previous_time is not None else None


async def _restore_reply_time(user_id, previous_time, claimed_time):
    pool = get_pool()
    async with pool.acquire() as conn:
        if previous_time is None:
            await conn.execute(
                "DELETE FROM auto_private_replied WHERE user_id=$1 AND replied_at=$2",
                int(user_id), int(claimed_time),
            )
        else:
            await conn.execute(
                """UPDATE auto_private_replied SET replied_at=$1
                   WHERE user_id=$2 AND replied_at=$3""",
                int(previous_time), int(user_id), int(claimed_time),
            )


async def _private_message_handler(client, message):
    if not message.from_user:
        return
    user = message.from_user
    if user.is_bot:
        return
    user_id = int(user.id)
    lock = _user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        claimed_time = int(time.time())
        try:
            should_reply, previous_time = await _claim_reply_slot(user_id, claimed_time)
        except Exception as exc:
            print(f"[AUTO REPLY] Database error: {exc}")
            return
        if not should_reply:
            return
        try:
            await message.reply_text(REPLY_TEXT)
            print(f"[AUTO REPLY] Replied to user {user_id}")
        except Exception as exc:
            print(f"[AUTO REPLY] Send error for {user_id}: {exc}")
            try:
                await _restore_reply_time(user_id, previous_time, claimed_time)
            except Exception as db_exc:
                print(f"[AUTO REPLY] Restore error: {db_exc}")


async def start_auto_private_reply():
    global _client, _handler
    if _handler is not None:
        return
    _client = get_music_client()
    if _client is None:
        print("[AUTO REPLY] Music account is not connected.")
        return
    try:
        _handler = MessageHandler(
            _private_message_handler,
            filters.private & filters.incoming,
        )
        _client.add_handler(_handler, group=_HANDLER_GROUP)
        print("[AUTO REPLY] Private auto-reply started successfully.")
    except Exception as exc:
        _handler = None
        _client = None
        print(f"[AUTO REPLY] Failed to start: {exc}")


async def shutdown_auto_private_reply():
    global _client, _handler
    if _client is not None and _handler is not None:
        try:
            _client.remove_handler(_handler, group=_HANDLER_GROUP)
        except Exception as exc:
            print(f"[AUTO REPLY] Handler removal error: {exc}")
    _handler = None
    _client = None
    _user_locks.clear()
    print("[AUTO REPLY] Private auto-reply stopped.")
