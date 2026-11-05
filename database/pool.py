from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

import asyncpg

from config import Settings

logger = logging.getLogger(__name__)
perf_logger = logging.getLogger("nawaf.performance")
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


def _log_query(record: asyncpg.Record) -> None:
    """Log slow SQL timings without logging SQL text or user data."""
    elapsed_ms = record.elapsed * 1000
    if elapsed_ms < 50:
        return
    query_hash = hashlib.sha1(record.query.encode("utf-8")).hexdigest()[:10]
    outcome = "error" if record.exception is not None else "ok"
    perf_logger.info(
        "PERF database.query duration_ms=%.1f query_id=%s outcome=%s",
        elapsed_ms,
        query_hash,
        outcome,
    )


async def _init_connection(connection: asyncpg.Connection) -> None:
    """Attach per-query timing to every connection created by the pool."""
    connection.add_query_logger(_log_query)


async def init_pool(settings: Settings) -> asyncpg.Pool:
    """Create the shared asyncpg pool once during application startup."""
    global _pool

    async with _pool_lock:
        if _pool is not None and not _pool._closed:
            return _pool

        logger.info("Opening PostgreSQL connection pool")
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            command_timeout=settings.db_command_timeout,
            # Compatible with PgBouncer/Supabase transaction poolers.
            statement_cache_size=0,
            ssl="require",
            init=_init_connection,
        )

        async with _pool.acquire() as connection:
            await connection.execute("SELECT 1")

        logger.info("PostgreSQL connection pool is ready")
        return _pool


def get_pool() -> asyncpg.Pool:
    if _pool is None or _pool._closed:
        raise RuntimeError("Database pool is not initialized")
    return _pool


async def close_pool() -> None:
    global _pool

    async with _pool_lock:
        if _pool is None:
            return
        pool, _pool = _pool, None
        if not pool._closed:
            await pool.close()
            logger.info("PostgreSQL connection pool closed")
