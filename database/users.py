"""Async user repository for the new bot."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .pool import get_pool


async def ensure_user(
    user_id: int,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    is_bot: bool = False,
) -> Any:
    """Create a user if needed and return the current user/profile/points row."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, is_bot)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                is_bot = EXCLUDED.is_bot,
                updated_at = NOW()
            """,
            user_id, username, first_name, last_name, is_bot,
        )
        return await conn.fetchrow(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   u.is_bot, u.messages, u.rank, u.joined_date,
                   u.is_banned, u.ban_type, u.is_muted, u.mute_type,
                   COALESCE(p.points, 0) AS points
            FROM users u LEFT JOIN points p ON p.user_id = u.user_id
            WHERE u.user_id = $1
            """,
            user_id,
        )


async def get_user(user_id: int) -> Any | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   u.is_bot, u.messages, u.rank, u.joined_date,
                   u.is_banned, u.ban_type, u.is_muted, u.mute_type,
                   COALESCE(p.points, 0) AS points
            FROM users u LEFT JOIN points p ON p.user_id = u.user_id
            WHERE u.user_id = $1
            """,
            user_id,
        )


async def register_joined_member(
    *,
    chat_id: int,
    chat_type: str,
    chat_title: str | None,
    chat_username: str | None,
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    is_bot: bool = False,
) -> None:
    """Persist a chat, user and membership together."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO chats(chat_id, chat_type, title, username)
                VALUES($1, $2, $3, $4)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_type = EXCLUDED.chat_type,
                    title = COALESCE(EXCLUDED.title, chats.title),
                    username = COALESCE(EXCLUDED.username, chats.username),
                    is_active = TRUE, updated_at = NOW()
                """,
                chat_id, chat_type, chat_title, chat_username,
            )
            await conn.execute(
                """
                INSERT INTO users(user_id, username, first_name, last_name, is_bot, joined_date)
                VALUES($1, $2, $3, $4, $5, NOW())
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                    is_bot = EXCLUDED.is_bot, updated_at = NOW()
                """,
                user_id, username, first_name, last_name, is_bot,
            )
            await conn.execute(
                """
                INSERT INTO chat_members(chat_id, user_id, member_status, joined_at)
                VALUES($1, $2, 'member', NOW())
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    member_status = 'member', joined_at = NOW(), updated_at = NOW()
                """,
                chat_id, user_id,
            )


async def update_member_status(chat_id: int, user_id: int, status: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE chat_members SET member_status = $3, updated_at = NOW()
            WHERE chat_id = $1 AND user_id = $2
            """,
            chat_id, user_id, status,
        )
