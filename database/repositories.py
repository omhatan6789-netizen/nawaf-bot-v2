from __future__ import annotations

from typing import Any

from .pool import get_pool


async def upsert_user(
    user_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    is_bot: bool = False,
) -> None:
    """Insert or refresh a Telegram user without overwriting bot-owned counters/ranks."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, is_bot)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT(user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                is_bot = EXCLUDED.is_bot,
                updated_at = NOW()
            """,
            user_id, username, first_name, last_name, is_bot,
        )


async def upsert_chat(
    chat_id: int,
    *,
    chat_type: str,
    title: str | None = None,
    username: str | None = None,
) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chats(chat_id, chat_type, title, username)
            VALUES($1, $2, $3, $4)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type = EXCLUDED.chat_type,
                title = EXCLUDED.title,
                username = EXCLUDED.username,
                is_active = TRUE,
                updated_at = NOW()
            """,
            chat_id, chat_type, title, username,
        )


async def upsert_chat_member(
    chat_id: int,
    user_id: int,
    *,
    member_status: str = "member",
) -> None:
    """Persist a membership snapshot; the chat and user must already exist."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO chat_members(chat_id, user_id, member_status)
            VALUES($1, $2, $3)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                member_status = EXCLUDED.member_status,
                updated_at = NOW()
            """,
            chat_id, user_id, member_status,
        )


async def get_user(user_id: int) -> Any | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1",
            user_id,
        )


async def add_user_messages(user_id: int, amount: int = 1) -> None:
    if amount < 1:
        raise ValueError("amount must be positive")
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET messages = messages + $2, updated_at = NOW() WHERE user_id = $1",
            user_id, amount,
        )
