from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg

from config import Settings

logger = logging.getLogger(__name__)
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


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
