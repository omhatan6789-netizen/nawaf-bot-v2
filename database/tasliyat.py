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


STORE_ITEMS = {
    "برج": {"emoji":"🏰","min":2188,"max":4375},
    "جزيرة": {"emoji":"🏝","min":2625,"max":5250},
    "بيت": {"emoji":"🏠","min":1500,"max":3000},
    "طيارة": {"emoji":"🛩","min":1125,"max":2250},
    "سيارة": {"emoji":"🏎","min":750,"max":1500},
    "سفينة": {"emoji":"🛳","min":1000,"max":2000},
    "قطار": {"emoji":"🚂","min":1750,"max":3500},
    "قصر": {"emoji":"🏯","min":2438,"max":4875},
    "ماسة": {"emoji":"💎","min":625,"max":1250},
    "طعمية": {"emoji":"🧆","min":13,"max":25},
    "شاورما": {"emoji":"🌯","min":22,"max":44},
    "مزرعة": {"emoji":"🌾","min":500,"max":1000},
}
STORE_ORDER = ["برج","جزيرة","بيت","طيارة","سيارة","سفينة","قطار","قصر","ماسة","طعمية","شاورما","مزرعة"]


async def get_store_prices() -> dict[str, int]:
    import random
    import time

    hour_key = int(time.time()) // 3600
    pool = get_pool()
    prices: dict[str, int] = {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", 918273646)
            rows = await conn.fetch(
                "SELECT item_key, price, hour_key FROM store_prices WHERE item_key = ANY($1::text[])",
                STORE_ORDER,
            )
            existing = {row["item_key"]: row for row in rows}
            for item_key in STORE_ORDER:
                row = existing.get(item_key)
                if row and int(row["hour_key"]) == hour_key:
                    prices[item_key] = int(row["price"])
                    continue
                bounds = STORE_ITEMS[item_key]
                price = random.randint(bounds["min"], bounds["max"])
                await conn.execute(
                    """INSERT INTO store_prices(item_key, price, hour_key)
                       VALUES($1,$2,$3)
                       ON CONFLICT(item_key) DO UPDATE
                       SET price=EXCLUDED.price, hour_key=EXCLUDED.hour_key""",
                    item_key, price, hour_key,
                )
                prices[item_key] = price
    return prices


async def get_possessions(user_id: int) -> list[tuple[str, int]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT item_key, quantity FROM possessions
               WHERE user_id=$1 AND quantity>0 ORDER BY item_key""",
            user_id,
        )
    return [(row["item_key"], int(row["quantity"])) for row in rows]


async def purchase_item(user_id: int, item_key: str, quantity: int, total: int) -> int | None:
    """Debit points and add stock atomically; None means insufficient funds."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = await conn.fetchval(
                """UPDATE points SET points=points-$2
                   WHERE user_id=$1 AND points >= $2 RETURNING points""",
                user_id, total,
            )
            if balance is None:
                return None
            await conn.execute(
                """INSERT INTO possessions(user_id,item_key,quantity)
                   VALUES($1,$2,$3)
                   ON CONFLICT(user_id,item_key) DO UPDATE
                   SET quantity=possessions.quantity+EXCLUDED.quantity""",
                user_id, item_key, quantity,
            )
    return int(balance)


async def sell_item(user_id: int, item_key: str, quantity: int, value: int) -> tuple[str, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            row = await conn.fetchrow(
                """SELECT quantity FROM possessions
                   WHERE user_id=$1 AND item_key=$2 FOR UPDATE""",
                user_id, item_key,
            )
            owned = int(row["quantity"]) if row else 0
            if owned <= 0:
                return "none", 0
            if owned < quantity:
                return "short", owned
            remaining = owned - quantity
            if remaining:
                await conn.execute(
                    "UPDATE possessions SET quantity=$3 WHERE user_id=$1 AND item_key=$2",
                    user_id, item_key, remaining,
                )
            else:
                await conn.execute(
                    "DELETE FROM possessions WHERE user_id=$1 AND item_key=$2",
                    user_id, item_key,
                )
            balance = await conn.fetchval(
                "UPDATE points SET points=points+$2 WHERE user_id=$1 RETURNING points",
                user_id, value,
            )
    return "ok", int(balance)


async def gift_item(sender_id: int, recipient_id: int, item_key: str, quantity: int) -> tuple[str, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, sender_id)
            await _ensure_user(conn, recipient_id)
            # Lock the sender's inventory row; conditional update prevents double gifting.
            row = await conn.fetchrow(
                """UPDATE possessions SET quantity=quantity-$3
                   WHERE user_id=$1 AND item_key=$2 AND quantity >= $3
                   RETURNING quantity""",
                sender_id, item_key, quantity,
            )
            if row is None:
                owned = await conn.fetchval(
                    "SELECT quantity FROM possessions WHERE user_id=$1 AND item_key=$2",
                    sender_id, item_key,
                )
                return ("none" if not owned else "short"), int(owned or 0)
            remaining = int(row["quantity"])
            if remaining == 0:
                await conn.execute(
                    "DELETE FROM possessions WHERE user_id=$1 AND item_key=$2 AND quantity=0",
                    sender_id, item_key,
                )
            await conn.execute(
                """INSERT INTO possessions(user_id,item_key,quantity) VALUES($1,$2,$3)
                   ON CONFLICT(user_id,item_key) DO UPDATE
                   SET quantity=possessions.quantity+EXCLUDED.quantity""",
                recipient_id, item_key, quantity,
            )
    return "ok", remaining
