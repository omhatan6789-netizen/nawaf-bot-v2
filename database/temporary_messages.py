"""Async PostgreSQL operations for temporary messages."""
import time
from database.pool import get_pool


async def get_rows(scope, chat_id):
    async with get_pool().acquire() as conn:
        if scope == "global":
            return await conn.fetch("SELECT id,payload,buttons,interval_seconds,next_run_at FROM temporary_messages WHERE scope='global' ORDER BY id")
        return await conn.fetch("SELECT id,payload,buttons,interval_seconds,next_run_at FROM temporary_messages WHERE scope='chat' AND chat_id=$1 ORDER BY id", chat_id)


async def get_row_by_id(scope, chat_id, row_id):
    async with get_pool().acquire() as conn:
        if scope == "global":
            return await conn.fetchrow("SELECT id,payload,buttons,interval_seconds,next_run_at FROM temporary_messages WHERE id=$1 AND scope='global'", row_id)
        return await conn.fetchrow("SELECT id,payload,buttons,interval_seconds,next_run_at FROM temporary_messages WHERE id=$1 AND scope='chat' AND chat_id=$2", row_id, chat_id)


async def create_message(scope, chat_id, creator_id, payload, buttons, max_messages=8):
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"tmp:{scope}:{chat_id}")
            count = await conn.fetchval("SELECT COUNT(*) FROM temporary_messages WHERE scope=$1 AND chat_id=$2", scope, chat_id)
            if count >= max_messages:
                return False
            await conn.execute("INSERT INTO temporary_messages(scope,chat_id,creator_id,payload,buttons,created_at) VALUES($1,$2,$3,$4,$5,$6)", scope, chat_id, creator_id, payload, buttons, time.time())
    return True


async def delete_row(scope, chat_id, row_id):
    async with get_pool().acquire() as conn:
        if scope == "global":
            result = await conn.execute("DELETE FROM temporary_messages WHERE id=$1 AND scope='global'", row_id)
        else:
            result = await conn.execute("DELETE FROM temporary_messages WHERE id=$1 AND scope='chat' AND chat_id=$2", row_id, chat_id)
    return result.endswith("1")


async def delete_scope(scope, chat_id):
    async with get_pool().acquire() as conn:
        if scope == "global":
            await conn.execute("DELETE FROM temporary_messages WHERE scope='global'")
        else:
            await conn.execute("DELETE FROM temporary_messages WHERE scope='chat' AND chat_id=$1", chat_id)


async def set_interval(scope, chat_id, row_id, seconds, next_run):
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE temporary_messages SET interval_seconds=$1,next_run_at=$2 WHERE id=$3 AND scope=$4 AND chat_id=$5", seconds, next_run, row_id, scope, chat_id)


async def update_buttons(scope, chat_id, row_id, buttons):
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE temporary_messages SET buttons=$1 WHERE id=$2 AND scope=$3 AND chat_id=$4", buttons, row_id, scope, chat_id)


async def update_payload(scope, chat_id, row_id, payload, buttons):
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE temporary_messages SET payload=$1,buttons=$2 WHERE id=$3 AND scope=$4 AND chat_id=$5", payload, buttons, row_id, scope, chat_id)


async def claim_due_messages(now=None):
    now = now or time.time()
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("SELECT id,scope,chat_id,payload,buttons,interval_seconds FROM temporary_messages WHERE interval_seconds IS NOT NULL AND next_run_at IS NOT NULL AND next_run_at<=$1 ORDER BY next_run_at,id FOR UPDATE SKIP LOCKED", now)
            for row in rows:
                await conn.execute("UPDATE temporary_messages SET next_run_at=$1 WHERE id=$2", now + int(row["interval_seconds"]), row["id"])
    return rows


async def get_active_chats():
    async with get_pool().acquire() as conn:
        rows = await conn.fetch("SELECT chat_id FROM temporary_message_chats WHERE active=TRUE")
    return [row["chat_id"] for row in rows]


async def deactivate_chat(chat_id):
    async with get_pool().acquire() as conn:
        await conn.execute("UPDATE temporary_message_chats SET active=FALSE WHERE chat_id=$1", chat_id)


async def upsert_chat(chat_id, title):
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO temporary_message_chats(chat_id,title,active,updated_at) VALUES($1,$2,TRUE,$3) ON CONFLICT(chat_id) DO UPDATE SET title=EXCLUDED.title,active=TRUE,updated_at=EXCLUDED.updated_at", chat_id, title or "", time.time())
