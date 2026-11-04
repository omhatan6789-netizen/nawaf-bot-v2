from .pool import get_pool


async def check_database() -> bool:
    pool = get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval("SELECT TRUE")
