"""Atomic points/economy operations.

All balance changes are performed in PostgreSQL so concurrent bot updates
cannot overwrite one another or create negative balances.
"""
from __future__ import annotations

from typing import Any

from .pool import get_pool


def _validate_amount(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("amount must be a positive integer")


async def _ensure_user(conn: Any, user_id: int) -> None:
    await conn.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )


async def get_points(user_id: int) -> int:
    """Return a user's balance; users without a points row have zero points."""
    pool = get_pool()
    async with pool.acquire() as conn:
        value = await conn.fetchval(
            "SELECT points FROM points WHERE user_id = $1", user_id
        )
    return int(value or 0)


async def add_points(user_id: int, amount: int) -> int:
    """Atomically add points and return the resulting balance."""
    _validate_amount(amount)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = await conn.fetchval(
                """
                INSERT INTO points(user_id, points)
                VALUES($1, $2)
                ON CONFLICT(user_id) DO UPDATE
                    SET points = points.points + EXCLUDED.points
                RETURNING points
                """,
                user_id, amount,
            )
    return int(balance)


async def deduct_points(user_id: int, amount: int) -> int | None:
    """Deduct only when the balance is sufficient; return None otherwise."""
    _validate_amount(amount)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = await conn.fetchval(
                """
                UPDATE points
                SET points = points - $2
                WHERE user_id = $1 AND points >= $2
                RETURNING points
                """,
                user_id, amount,
            )
    return int(balance) if balance is not None else None


async def transfer_points(sender_id: int, receiver_id: int, amount: int) -> dict[str, int] | None:
    """Transfer points atomically. Return both balances, or None if funds are insufficient."""
    _validate_amount(amount)
    if sender_id == receiver_id:
        raise ValueError("sender and receiver must be different users")

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Create user rows first to satisfy the points foreign key.
            await _ensure_user(conn, sender_id)
            await _ensure_user(conn, receiver_id)

            # Ensure both balance rows exist before the conditional debit.
            await conn.execute(
                """
                INSERT INTO points(user_id, points) VALUES($1, 0), ($2, 0)
                ON CONFLICT(user_id) DO NOTHING
                """,
                sender_id, receiver_id,
            )

            sender_balance = await conn.fetchval(
                """
                UPDATE points SET points = points - $2
                WHERE user_id = $1 AND points >= $2
                RETURNING points
                """,
                sender_id, amount,
            )
            if sender_balance is None:
                return None

            receiver_balance = await conn.fetchval(
                """
                UPDATE points SET points = points + $2
                WHERE user_id = $1
                RETURNING points
                """,
                receiver_id, amount,
            )

    return {
        "sender_balance": int(sender_balance),
        "receiver_balance": int(receiver_balance),
    }


async def get_points_leaderboard(limit: int = 10) -> list[Any]:
    """Return users ordered by points, highest first."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT p.user_id, p.points, u.username, u.first_name
            FROM points AS p
            LEFT JOIN users AS u ON u.user_id = p.user_id
            WHERE p.points > 0
            ORDER BY p.points DESC, p.user_id ASC
            LIMIT $1
            """,
            limit,
        )
