"""Async PostgreSQL operations for the bank and economy mini-games."""
from __future__ import annotations

import secrets
from typing import Any

from .pool import get_pool

_COOLDOWN_COLUMNS = {
    "salary_until", "tip_until", "robber_until",
    "victim_rob_until", "investment_until", "luck_until",
}


async def games_enabled() -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM games_settings WHERE id = 1")
    return status is None or status != "off"


async def _ensure_user(conn: Any, user_id: int) -> None:
    await conn.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )
    await conn.execute(
        "INSERT INTO points(user_id, points) VALUES($1, 0) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )


async def get_points(user_id: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        value = await conn.fetchval("SELECT points FROM points WHERE user_id=$1", user_id)
    return int(value or 0)


async def get_bank(user_id: int) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT user_id, account_number, bank, card_type, robbery_balance
               FROM bank_accounts WHERE user_id=$1""",
            user_id,
        )
    return dict(row) if row else None


async def create_bank(user_id: int, bank_name: str, card_type: str) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            existing = await conn.fetchrow(
                """SELECT user_id, account_number, bank, card_type, robbery_balance
                   FROM bank_accounts WHERE user_id=$1""",
                user_id,
            )
            if existing:
                return dict(existing)
            for _ in range(8):
                number = str(secrets.randbelow(90000000000000000) + 10000000000000000)
                row = await conn.fetchrow(
                    """INSERT INTO bank_accounts(user_id, account_number, bank, card_type)
                       VALUES($1,$2,$3,$4)
                       ON CONFLICT DO NOTHING
                       RETURNING user_id, account_number, bank, card_type, robbery_balance""",
                    user_id, number, bank_name, card_type,
                )
                if row:
                    return dict(row)
    return None


async def delete_bank(user_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM bank_accounts WHERE user_id=$1", user_id)
    return result.endswith("1")


async def _claim_cooldown(conn: Any, user_id: int, column: str, now: int, until: int) -> tuple[bool, int]:
    if column not in _COOLDOWN_COLUMNS:
        raise ValueError("Invalid cooldown column")
    await conn.execute(
        "INSERT INTO tasliyat_cooldowns(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )
    row = await conn.fetchrow(
        f"""UPDATE tasliyat_cooldowns SET {column}=$3
            WHERE user_id=$1 AND {column}<=$2
            RETURNING {column}""",
        user_id, now, until,
    )
    if row:
        return True, 0
    current = await conn.fetchval(
        f"SELECT {column} FROM tasliyat_cooldowns WHERE user_id=$1",
        user_id,
    )
    return False, max(0, int(current or 0) - now)


async def claim_reward(user_id: int, column: str, now: int, cooldown_seconds: int, amount: int) -> tuple[bool, int, int]:
    """Claim a cooldown and credit the reward atomically."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            claimed, remaining = await _claim_cooldown(
                conn, user_id, column, now, now + cooldown_seconds
            )
            if not claimed:
                balance = await conn.fetchval("SELECT points FROM points WHERE user_id=$1", user_id)
                return False, int(balance or 0), remaining
            balance = await conn.fetchval(
                "UPDATE points SET points=points+$2 WHERE user_id=$1 RETURNING points",
                user_id, amount,
            )
    return True, int(balance), 0


async def run_investment(user_id: int, now: int, cooldown_seconds: int, amount: int, profit: int | None) -> tuple[str, int, int]:
    """Validate funds, claim cooldown, and apply an optional profit atomically."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = int(await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1 FOR UPDATE", user_id
            ) or 0)
            if amount <= 0 or balance < amount:
                return "insufficient", balance, 0
            claimed, remaining = await _claim_cooldown(
                conn, user_id, "investment_until", now, now + cooldown_seconds
            )
            if not claimed:
                return "cooldown", balance, remaining
            if profit is not None and profit > 0:
                balance = int(await conn.fetchval(
                    "UPDATE points SET points=points+$2 WHERE user_id=$1 RETURNING points",
                    user_id, profit,
                ))
    return ("success" if profit is not None else "failed"), balance, 0


async def run_luck(user_id: int, now: int, cooldown_seconds: int, amount: int, won: bool) -> tuple[str, int, int, int]:
    """Apply a win/loss and cooldown under one row lock."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = int(await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1 FOR UPDATE", user_id
            ) or 0)
            if amount <= 0 or balance < amount:
                return "insufficient", balance, balance, 0
            claimed, remaining = await _claim_cooldown(
                conn, user_id, "luck_until", now, now + cooldown_seconds
            )
            if not claimed:
                return "cooldown", balance, balance, remaining
            delta = amount if won else -amount
            new_balance = int(await conn.fetchval(
                "UPDATE points SET points=points+$2 WHERE user_id=$1 RETURNING points",
                user_id, delta,
            ))
    return ("won" if won else "lost"), balance, new_balance, 0
