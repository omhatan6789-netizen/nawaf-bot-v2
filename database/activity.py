from __future__ import annotations

import asyncio
import logging
from .pool import get_pool

logger = logging.getLogger(__name__)
FLUSH_DELAY = 0.5
_pending_users = {}
_pending_chat_users = {}
_pending_chats = {}
_pending_members = set()
_pending_message_total = 0
_flush_lock = None
_flush_task = None


def _lock():
    global _flush_lock
    if _flush_lock is None:
        _flush_lock = asyncio.Lock()
    return _flush_lock


def record_group_text_message(*, chat_id, chat_type, chat_title, chat_username, user_id, username, first_name):
    global _pending_message_total
    old = _pending_users.get(user_id)
    _pending_users[user_id] = (username if username is not None else (old[0] if old else None), first_name or (old[1] if old else ""), (old[2] if old else 0) + 1)
    _pending_chats[chat_id] = (chat_type, chat_title, chat_username)
    _pending_chat_users[(chat_id, user_id)] = _pending_chat_users.get((chat_id, user_id), 0) + 1
    _pending_members.add((chat_id, user_id))
    _pending_message_total += 1
    _schedule_flush(0 if _pending_message_total >= 100 else FLUSH_DELAY)


def _schedule_flush(delay):
    global _flush_task
    if _flush_task is None or _flush_task.done():
        try:
            _flush_task = asyncio.get_running_loop().create_task(_flush_worker(delay))
        except RuntimeError:
            pass


async def _flush_worker(delay):
    if delay:
        await asyncio.sleep(delay)
    while _pending_users or _pending_chat_users or _pending_chats or _pending_members:
        try:
            await flush_pending_activity()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Message activity flush failed; retrying")
            await asyncio.sleep(2)


async def flush_pending_activity():
    global _pending_message_total
    if not (_pending_users or _pending_chat_users or _pending_chats or _pending_members):
        return
    async with _lock():
        if not (_pending_users or _pending_chats or _pending_members):
            return
        users, chat_users, chats, members = dict(_pending_users), dict(_pending_chat_users), dict(_pending_chats), set(_pending_members)
        message_total = _pending_message_total
        _pending_message_total = 0
        _pending_users.clear()
        _pending_chat_users.clear()
        _pending_chats.clear()
        _pending_members.clear()
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if chats:
                        await conn.executemany("""INSERT INTO chats(chat_id,chat_type,title,username) VALUES($1,$2,$3,$4) ON CONFLICT(chat_id) DO UPDATE SET chat_type=EXCLUDED.chat_type,title=COALESCE(EXCLUDED.title,chats.title),username=COALESCE(EXCLUDED.username,chats.username),is_active=TRUE,updated_at=NOW()""", [(cid, *data) for cid, data in chats.items()])
                    if users:
                        await conn.executemany("""INSERT INTO users(user_id,username,first_name,messages,activity_messages,rank,joined_date) VALUES($1,$2,$3,$4,$5,'عضو',NOW()) ON CONFLICT(user_id) DO UPDATE SET messages=COALESCE(users.messages,0)+EXCLUDED.messages,activity_messages=COALESCE(users.activity_messages,0)+EXCLUDED.activity_messages,username=COALESCE(EXCLUDED.username,users.username),first_name=COALESCE(EXCLUDED.first_name,users.first_name),updated_at=NOW()""", [(uid, username, first_name, count, count) for uid, (username, first_name, count) in users.items()])
                    if chat_users:
                        await conn.executemany("""INSERT INTO chat_activity(chat_id,user_id,message_count) VALUES($1,$2,$3) ON CONFLICT(chat_id,user_id) DO UPDATE SET message_count=chat_activity.message_count+EXCLUDED.message_count,updated_at=NOW()""", [(cid, uid, count) for (cid, uid), count in chat_users.items()])
                    if members:
                        await conn.executemany("""INSERT INTO chat_members(chat_id,user_id,member_status) VALUES($1,$2,'member') ON CONFLICT(chat_id,user_id) DO UPDATE SET member_status='member',updated_at=NOW()""", list(members))
        except Exception:
            _pending_message_total += message_total
            for uid, (username, first_name, count) in users.items():
                newer = _pending_users.get(uid)
                _pending_users[uid] = (newer[0] if newer and newer[0] is not None else username, newer[1] if newer and newer[1] else first_name, count + (newer[2] if newer else 0))
            for (cid, uid), count in chat_users.items():
                _pending_chat_users[(cid, uid)] = _pending_chat_users.get((cid, uid), 0) + count
            for cid, data in chats.items():
                _pending_chats.setdefault(cid, data)
            _pending_members.update(members)
            raise


async def shutdown_activity():
    global _flush_task
    await flush_pending_activity()
    task = _flush_task
    if task is not None and task is not asyncio.current_task() and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _flush_task = None
