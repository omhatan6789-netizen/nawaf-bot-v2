"""Async PostgreSQL operations for the bank and economy mini-games."""
from __future__ import annotations

import secrets
from typing import Any
from datetime import timedelta
import time

_games_cache_value: bool | None = None
_games_cache_expires: float = 0.0

from .pool import get_pool
from .timing import timed

_COOLDOWN_COLUMNS = {
    "salary_until", "tip_until", "robber_until",
    "victim_rob_until", "investment_until", "luck_until",
}


@timed("db.tasliyat.games_enabled")
async def games_enabled() -> bool:
    global _games_cache_value, _games_cache_expires
    now = time.monotonic()
    if _games_cache_value is not None and _games_cache_expires > now:
        return _games_cache_value
    pool = get_pool()
    async with pool.acquire() as conn:
        status = await conn.fetchval("SELECT status FROM games_settings WHERE id = 1")
    _games_cache_value = status is None or status != "off"
    _games_cache_expires = now + 60
    return _games_cache_value


async def _ensure_user(conn: Any, user_id: int) -> None:
    await conn.execute(
        "INSERT INTO users(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )
    await conn.execute(
        "INSERT INTO points(user_id, points) VALUES($1, 0) ON CONFLICT(user_id) DO NOTHING",
        user_id,
    )


@timed("db.tasliyat.get_points")
async def get_points(user_id: int) -> int:
    pool = get_pool()
    async with pool.acquire() as conn:
        value = await conn.fetchval("SELECT points FROM points WHERE user_id=$1", user_id)
    return int(value or 0)


@timed("db.tasliyat.get_bank")
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
                existing = await conn.fetchrow(
                    """SELECT user_id, account_number, bank, card_type, robbery_balance
                       FROM bank_accounts WHERE user_id=$1""",
                    user_id,
                )
                if existing:
                    return dict(existing)
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


@timed("db.tasliyat.claim_reward")
async def claim_reward(user_id: int, column: str, now: int, cooldown_seconds: int, amount: int) -> tuple[bool, int, int]:
    """Claim a cooldown and credit its reward atomically in one DB round trip."""
    if column not in _COOLDOWN_COLUMNS:
        raise ValueError("Invalid cooldown column")

    pool = get_pool()
    until = now + cooldown_seconds
    query = f"""
        WITH ensure_user AS (
            INSERT INTO users(user_id) VALUES($1)
            ON CONFLICT(user_id) DO NOTHING
            RETURNING user_id
        ),
        ensure_points AS (
            INSERT INTO points(user_id, points)
            SELECT $1 WHERE (SELECT COUNT(*) FROM ensure_user) >= 0
            ON CONFLICT(user_id) DO NOTHING
            RETURNING points
        ),
        existing_points AS (
            SELECT points
            FROM points
            WHERE user_id = $1
              AND NOT EXISTS (SELECT 1 FROM ensure_points)
            FOR UPDATE
        ),
        lock_points AS (
            SELECT points FROM ensure_points
            UNION ALL
            SELECT points FROM existing_points
        ),
        claimed AS (
            INSERT INTO tasliyat_cooldowns(user_id, {column})
            VALUES($1, $3)
            ON CONFLICT(user_id) DO UPDATE
            SET {column} = EXCLUDED.{column}
            WHERE tasliyat_cooldowns.{column} <= $2
            RETURNING {column}
        ),
        cooldown_state AS (
            SELECT {column} AS cooldown_until
            FROM tasliyat_cooldowns
            WHERE user_id = $1
              AND NOT EXISTS (SELECT 1 FROM claimed)
        ),
        credited AS (
            UPDATE points
            SET points = points + $4
            WHERE user_id = $1
              AND EXISTS (SELECT 1 FROM claimed)
            RETURNING points
        )
        SELECT
            EXISTS (SELECT 1 FROM claimed) AS claimed,
            COALESCE(
                (SELECT points FROM credited),
                (SELECT points FROM lock_points),
                0
            ) AS balance,
            CASE
                WHEN EXISTS (SELECT 1 FROM claimed) THEN 0
                ELSE GREATEST(
                    0,
                    COALESCE((SELECT cooldown_until FROM cooldown_state), 0) - $2
                )
            END AS remaining
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_id, now, until, amount)

    return bool(row["claimed"]), int(row["balance"] or 0), int(row["remaining"] or 0)


@timed("db.tasliyat.run_investment")
async def run_investment(user_id: int, now: int, cooldown_seconds: int, amount: int, profit: int | None) -> tuple[str, int, int]:
    """Validate and apply an investment atomically in one DB round trip."""
    pool = get_pool()
    until = now + cooldown_seconds
    query = """
        WITH ensure_user AS (
            INSERT INTO users(user_id) VALUES($1)
            ON CONFLICT(user_id) DO NOTHING
            RETURNING user_id
        ),
        ensure_points AS (
            INSERT INTO points(user_id, points)
            SELECT $1 WHERE (SELECT COUNT(*) FROM ensure_user) >= 0
            ON CONFLICT(user_id) DO NOTHING
            RETURNING points
        ),
        existing_points AS (
            SELECT points
            FROM points
            WHERE user_id = $1
              AND NOT EXISTS (SELECT 1 FROM ensure_points)
            FOR UPDATE
        ),
        lock_points AS (
            SELECT points FROM ensure_points
            UNION ALL
            SELECT points FROM existing_points
        ),
        claimed AS (
            INSERT INTO tasliyat_cooldowns(user_id, investment_until)
            VALUES(
                $1,
                CASE
                    WHEN $4 > 0 AND COALESCE((SELECT points FROM lock_points), 0) >= $4
                        THEN $3
                    ELSE 0
                END
            )
            ON CONFLICT(user_id) DO UPDATE
            SET investment_until = EXCLUDED.investment_until
            WHERE tasliyat_cooldowns.investment_until <= $2
              AND $4 > 0
              AND COALESCE((SELECT points FROM lock_points), 0) >= $4
            RETURNING investment_until
        ),
        cooldown_state AS (
            SELECT investment_until AS cooldown_until
            FROM tasliyat_cooldowns
            WHERE user_id = $1
              AND NOT EXISTS (SELECT 1 FROM claimed)
        ),
        credited AS (
            UPDATE points
            SET points = points + $5
            WHERE user_id = $1
              AND EXISTS (SELECT 1 FROM claimed)
              AND $4 > 0
              AND COALESCE((SELECT points FROM lock_points), 0) >= $4
              AND $5 IS NOT NULL
              AND $5 > 0
            RETURNING points
        )
        SELECT
            CASE
                WHEN COALESCE((SELECT cooldown_until FROM cooldown_state), 0) > $2
                    THEN 'cooldown'
                WHEN $4 <= 0 OR COALESCE((SELECT points FROM lock_points), 0) < $4
                    THEN 'insufficient'
                WHEN $5 IS NOT NULL THEN 'success'
                ELSE 'failed'
            END AS status,
            COALESCE(
                (SELECT points FROM credited),
                (SELECT points FROM lock_points),
                0
            ) AS balance,
            GREATEST(
                0,
                COALESCE((SELECT cooldown_until FROM cooldown_state), 0) - $2
            ) AS remaining
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_id, now, until, amount, profit)

    return str(row["status"]), int(row["balance"] or 0), int(row["remaining"] or 0)


async def run_luck(user_id: int, now: int, cooldown_seconds: int, amount: int, won: bool) -> tuple[str, int, int, int]:
    """Apply a win/loss and cooldown under one row lock."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            balance = int(await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1 FOR UPDATE", user_id
            ) or 0)
            await conn.execute(
                "INSERT INTO tasliyat_cooldowns(user_id) VALUES($1) ON CONFLICT(user_id) DO NOTHING",
                user_id,
            )
            current_until = int(await conn.fetchval(
                "SELECT luck_until FROM tasliyat_cooldowns WHERE user_id=$1 FOR UPDATE",
                user_id,
            ) or 0)
            if current_until > now:
                return "cooldown", balance, balance, current_until - now
            if amount <= 0 or balance < amount:
                return "insufficient", balance, balance, 0
            await conn.execute(
                "UPDATE tasliyat_cooldowns SET luck_until=$2 WHERE user_id=$1",
                user_id, now + cooldown_seconds,
            )
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
            await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1 FOR UPDATE",
                user_id,
            )
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
            first_id, second_id = sorted((sender_id, recipient_id))
            await conn.execute("SELECT pg_advisory_xact_lock($1)", first_id)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", second_id)
            await _ensure_user(conn, sender_id)
            await _ensure_user(conn, recipient_id)
            # Conditional update prevents double gifting.
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


async def get_bank_by_number(account_number: str) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT user_id, account_number, bank, card_type, robbery_balance
               FROM bank_accounts WHERE account_number=$1""",
            account_number,
        )
    return dict(row) if row else None


async def rob_user(robber_id: int, victim_id: int, now: int, amount: int) -> tuple[str, int, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, robber_id)
            await _ensure_user(conn, victim_id)
            bank_rows = await conn.fetch(
                "SELECT user_id FROM bank_accounts WHERE user_id = ANY($1::bigint[])",
                [robber_id, victim_id],
            )
            if len(bank_rows) != 2:
                return "bank_missing", 0, 0

            # Lock point rows in a stable order to avoid deadlocks.
            ids = sorted((robber_id, victim_id))
            await conn.fetch(
                "SELECT user_id FROM points WHERE user_id = ANY($1::bigint[]) ORDER BY user_id FOR UPDATE",
                ids,
            )

            await conn.execute(
                "INSERT INTO tasliyat_cooldowns(user_id) VALUES($1),($2) ON CONFLICT(user_id) DO NOTHING",
                robber_id, victim_id,
            )
            # Fetch both cooldowns explicitly; no cooldown is consumed on a failed attempt.
            rows = await conn.fetch(
                """SELECT user_id, robber_until, victim_rob_until
                   FROM tasliyat_cooldowns WHERE user_id=ANY($1::bigint[])""",
                ids,
            )
            by_id = {int(row["user_id"]): row for row in rows}
            robber_left = max(0, int(by_id[robber_id]["robber_until"] or 0) - now)
            victim_left = max(0, int(by_id[victim_id]["victim_rob_until"] or 0) - now)
            if robber_left:
                return "robber_cooldown", 0, robber_left
            if victim_left:
                return "victim_cooldown", 0, victim_left

            victim_points = int(await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1", victim_id
            ) or 0)
            if victim_points <= 0:
                return "empty", 0, 0

            stolen = min(max(1, amount), victim_points)
            await conn.execute(
                """UPDATE tasliyat_cooldowns
                   SET robber_until=$2 WHERE user_id=$1""",
                robber_id, now + 300,
            )
            await conn.execute(
                """UPDATE tasliyat_cooldowns
                   SET victim_rob_until=$2 WHERE user_id=$1""",
                victim_id, now + 600,
            )
            await conn.execute(
                "UPDATE points SET points=points-$2 WHERE user_id=$1",
                victim_id, stolen,
            )
            await conn.execute(
                "UPDATE points SET points=points+$2 WHERE user_id=$1",
                robber_id, stolen,
            )
            await conn.execute(
                "UPDATE bank_accounts SET robbery_balance=robbery_balance+$2 WHERE user_id=$1",
                robber_id, stolen,
            )
    return "ok", stolen, 0


async def transfer_points(sender_id: int, recipient_id: int, amount: int) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, sender_id)
            await _ensure_user(conn, recipient_id)
            banks = await conn.fetch(
                """SELECT user_id, account_number, bank, card_type, robbery_balance
                   FROM bank_accounts WHERE user_id = ANY($1::bigint[])""",
                [sender_id, recipient_id],
            )
            by_id = {int(row["user_id"]): dict(row) for row in banks}
            sender_bank = by_id.get(sender_id)
            recipient_bank = by_id.get(recipient_id)
            if not sender_bank or not recipient_bank:
                return "bank_missing", sender_bank, recipient_bank, 0
            ids = sorted((sender_id, recipient_id))
            await conn.fetch(
                "SELECT user_id FROM points WHERE user_id=ANY($1::bigint[]) ORDER BY user_id FOR UPDATE",
                ids,
            )
            balance = int(await conn.fetchval(
                "SELECT points FROM points WHERE user_id=$1", sender_id
            ) or 0)
            if balance < amount:
                return "insufficient", sender_bank, recipient_bank, 0
            received = (amount * (95 if sender_bank["bank"] == recipient_bank["bank"] else 90)) // 100
            await conn.execute(
                "UPDATE points SET points=points-$2 WHERE user_id=$1",
                sender_id, amount,
            )
            await conn.execute(
                "UPDATE points SET points=points+$2 WHERE user_id=$1",
                recipient_id, received,
            )
    return "ok", sender_bank, recipient_bank, received


async def get_user_name(user_id: int) -> str:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT first_name, username FROM users WHERE user_id=$1",
            user_id,
        )
    if not row:
        return str(user_id)
    return row["first_name"] or row["username"] or str(user_id)


async def ensure_scratch_codes(hour_key: int, expires_at) -> None:
    import random
    import secrets
    import string

    pool = get_pool()
    chars = string.ascii_uppercase + string.digits
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", 918273645)
            count = int(await conn.fetchval(
                "SELECT COUNT(*) FROM scratch_codes WHERE hour_key=$1",
                hour_key,
            ) or 0)
            while count < 10:
                code = "".join(secrets.choice(chars) for _ in range(12))
                amount = random.randint(70, 10_000_000)
                inserted = await conn.fetchval(
                    """INSERT INTO scratch_codes(code,amount,hour_key,expires_at)
                       VALUES($1,$2,$3,$4)
                       ON CONFLICT(code) DO NOTHING
                       RETURNING id""",
                    code, amount, hour_key, expires_at,
                )
                if inserted is not None:
                    count += 1


async def get_active_scratch_codes(now):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT code FROM scratch_codes
               WHERE used=FALSE AND expires_at>$1 ORDER BY id ASC""",
            now,
        )


async def redeem_scratch_code(user_id: int, code: str, now) -> tuple[str, int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await _ensure_user(conn, user_id)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            last = await conn.fetchval(
                "SELECT last_scratched_at FROM scratch_limits WHERE user_id=$1",
                user_id,
            )
            if last is not None:
                remaining = int((last + timedelta(hours=2) - now).total_seconds())
                if remaining > 0:
                    return "cooldown", remaining
            amount = await conn.fetchval(
                """UPDATE scratch_codes SET used=TRUE, used_by=$1
                   WHERE code=$2 AND used=FALSE AND expires_at>$3
                   RETURNING amount""",
                user_id, code, now,
            )
            if amount is None:
                return "invalid", 0
            await conn.execute(
                """INSERT INTO scratch_limits(user_id,last_scratched_at)
                   VALUES($1,$2)
                   ON CONFLICT(user_id) DO UPDATE
                   SET last_scratched_at=EXCLUDED.last_scratched_at""",
                user_id, now,
            )
            balance = await conn.fetchval(
                "UPDATE points SET points=points+$2 WHERE user_id=$1 RETURNING points",
                user_id, int(amount),
            )
    return "success", int(amount)


async def reset_scratch_limit(user_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM scratch_limits WHERE user_id=$1", user_id)
