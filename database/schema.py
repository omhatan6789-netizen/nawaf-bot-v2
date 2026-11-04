from pathlib import Path

from .pool import get_pool

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


async def apply_schema() -> None:
    """Apply the idempotent base schema during startup."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    pool = get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(sql)
