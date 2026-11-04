"""Fast async points operations for the bot."""
from __future__ import annotations

import asyncio
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
    pool = get_pool()
    async with pool.acquire() as conn:
        value = await conn.fetchval(
            "SELECT points FROM points WHERE user_id = $1", user_id
        )
    return int(value or 0)


async def add_points(user_id: int, amount: int) -> int:
    """Atomically add a positive amount and return the new balance."""
    _validate_amount(amount)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = await conn.fetchval(
                """
                INSERT INTO points(user_id, points) VALUES($1, $2)
                ON CONFLICT(user_id) DO UPDATE
                SET points = points.points + EXCLUDED.points
                RETURNING points
                """,
                user_id, amount,
            )
    return int(balance)


async def deduct_points(user_id: int, amount: int) -> int | None:
    """Atomically deduct points only when the balance is sufficient."""
    _validate_amount(amount)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            await conn.execute(
                "INSERT INTO points(user_id, points) VALUES($1, 0) ON CONFLICT DO NOTHING",
                user_id,
            )
            balance = await conn.fetchval(
                """
                UPDATE points SET points = points - $2
                WHERE user_id = $1 AND points >= $2
                RETURNING points
                """,
                user_id, amount,
            )
    return int(balance) if balance is not None else None


async def sell_points_for_messages(user_id: int, amount: int, points_per_message: int = 10) -> tuple[int, int] | None:
    """Debit points and credit message count in one transaction."""
    _validate_amount(amount)
    _validate_amount(points_per_message)
    messages = amount * points_per_message
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            await conn.execute(
                "INSERT INTO points(user_id, points) VALUES($1, 0) ON CONFLICT DO NOTHING",
                user_id,
            )
            remaining = await conn.fetchval(
                """
                UPDATE points SET points = points - $2
                WHERE user_id = $1 AND points >= $2
                RETURNING points
                """,
                user_id, amount,
            )
            if remaining is None:
                return None
            await conn.execute(
                """
                UPDATE users SET messages = COALESCE(messages, 0) + $2,
                    updated_at = NOW()
                WHERE user_id = $1
                """,
                user_id, messages,
            )
    return int(remaining), messages


async def get_points_leaderboard(limit: int = 10) -> list[Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT p.user_id, p.points, u.username, u.first_name
            FROM points p
            LEFT JOIN users u ON u.user_id = p.user_id
            WHERE p.points > 0
            ORDER BY p.points DESC, p.user_id ASC
            LIMIT $1
            """,
            limit,
        )


# Batched point accrual: one short-delay flush replaces one DB operation per message.
POINT_FLUSH_DELAY = 0.5
_pending_point_deltas: dict[int, int] = {}
_flush_lock: asyncio.Lock | None = None
_flush_task: asyncio.Task | None = None


def _get_flush_lock() -> asyncio.Lock:
    global _flush_lock
    if _flush_lock is None:
        _flush_lock = asyncio.Lock()
    return _flush_lock


def queue_points(user_id: int, amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
        raise ValueError("amount must be a non-zero integer")
    _pending_point_deltas[user_id] = _pending_point_deltas.get(user_id, 0) + amount
    _schedule_flush()


def _schedule_flush() -> None:
    global _flush_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _flush_task is None or _flush_task.done():
        _flush_task = loop.create_task(_delayed_flush())


async def _delayed_flush() -> None:
    try:
        await asyncio.sleep(POINT_FLUSH_DELAY)
        await flush_pending_points()
    except asyncio.CancelledError:
        raise
    except Exception:
        # Keep the deltas queued; the next flush/shutdown can retry them.
        return


async def flush_pending_points() -> None:
    if not _pending_point_deltas:
        return
    async with _get_flush_lock():
        if not _pending_point_deltas:
            return
        pending = dict(_pending_point_deltas)
        _pending_point_deltas.clear()
        pool = get_pool()
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    for user_id, amount in pending.items():
                        if amount == 0:
                            continue
                        await _ensure_user(conn, user_id)
                        if amount > 0:
                            await conn.execute(
                                """
                                INSERT INTO points(user_id, points) VALUES($1, $2)
                                ON CONFLICT(user_id) DO UPDATE
                                SET points = points.points + EXCLUDED.points
                                """,
                                user_id, amount,
                            )
                        else:
                            # Negative queued deltas are clamped at zero, preserving the
                            # non-negative balance constraint.
                            await conn.execute(
                                """
                                INSERT INTO points(user_id, points) VALUES($1, 0)
                                ON CONFLICT DO NOTHING
                                """,
                                user_id,
                            )
                            await conn.execute(
                                "UPDATE points SET points = GREATEST(0, points + $2) WHERE user_id = $1",
                                user_id, amount,
                            )
        except Exception:
            for user_id, amount in pending.items():
                _pending_point_deltas[user_id] = _pending_point_deltas.get(user_id, 0) + amount
            raise


async def transfer_points_atomic(sender_id: int, recipient_id: int, amount: int) -> bool:
    """Transfer points once, atomically, only if the sender can cover the stake."""
    _validate_amount(amount)
    if sender_id == recipient_id:
        return False
    first_id, second_id = sorted((sender_id, recipient_id))
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, sender_id)
            await _ensure_user(conn, recipient_id)
            await conn.execute(
                "INSERT INTO points(user_id, points) VALUES($1,0),($2,0) ON CONFLICT(user_id) DO NOTHING",
                first_id, second_id,
            )
            await conn.fetch(
                "SELECT user_id FROM points WHERE user_id=ANY($1::bigint[]) ORDER BY user_id FOR UPDATE",
                [first_id, second_id],
            )
            debited = await conn.fetchval(
                "UPDATE points SET points=points-$2 WHERE user_id=$1 AND points >= $2 RETURNING user_id",
                sender_id, amount,
            )
            if debited is None:
                return False
            await conn.execute(
                "UPDATE points SET points=points+$2 WHERE user_id=$1",
                recipient_id, amount,
            )
    return True


async def charge_two_players(first_id: int, second_id: int, amount: int) -> str:
    """Debit equal wagers from both players atomically, in stable lock order."""
    _validate_amount(amount)
    if first_id == second_id:
        return "first_insufficient"
    ids = sorted((first_id, second_id))
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, first_id)
            await _ensure_user(conn, second_id)
            await conn.execute(
                "INSERT INTO points(user_id,points) VALUES($1,0),($2,0) ON CONFLICT(user_id) DO NOTHING",
                ids[0], ids[1],
            )
            rows = await conn.fetch(
                "SELECT user_id,points FROM points WHERE user_id=ANY($1::bigint[]) ORDER BY user_id FOR UPDATE",
                ids,
            )
            balances = {int(row["user_id"]): int(row["points"]) for row in rows}
            if balances.get(first_id, 0) < amount:
                return "first_insufficient"
            if balances.get(second_id, 0) < amount:
                return "second_insufficient"
            await conn.execute(
                "UPDATE points SET points=points-$2 WHERE user_id=ANY($1::bigint[])",
                ids, amount,
            )
    return "ok"


async def settle_two_player_wager(
    first_id: int, second_id: int, amount: int, winner_id: int | None = None
) -> None:
    """Pay the winner 2x the stake, or refund both players on a draw."""
    _validate_amount(amount)
    if first_id == second_id or winner_id not in (None, first_id, second_id):
        raise ValueError("invalid wager participants")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, first_id)
            await _ensure_user(conn, second_id)
            if winner_id is None:
                await conn.execute(
                    "UPDATE points SET points=points+$2 WHERE user_id=$1",
                    first_id, amount,
                )
                await conn.execute(
                    "UPDATE points SET points=points+$2 WHERE user_id=$1",
                    second_id, amount,
                )
            else:
                await conn.execute(
                    "UPDATE points SET points=points+$2 WHERE user_id=$1",
                    winner_id, amount * 2,
                )


async def adjust_points(user_id: int, amount: int) -> int:
    """Apply a signed points delta, preserving legacy game penalties."""
    if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
        raise ValueError("amount must be a non-zero integer")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            value = await conn.fetchval(
                """INSERT INTO points(user_id,points) VALUES($1,GREATEST(0,$2))
                   ON CONFLICT(user_id) DO UPDATE
                   SET points=GREATEST(0,points.points+EXCLUDED.points)
                   RETURNING points""",
                int(user_id), int(amount),
            )
    return int(value)
