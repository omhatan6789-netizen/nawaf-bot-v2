"""Async PostgreSQL storage for custom command aliases."""
from database.pool import get_pool


async def load_commands():
    async with get_pool().acquire() as conn:
        return await conn.fetch("SELECT old_command,new_command FROM custom_commands")


async def save_command(old_command, new_command):
    async with get_pool().acquire() as conn:
        await conn.execute("""
            INSERT INTO custom_commands(old_command,new_command)
            VALUES($1,$2)
            ON CONFLICT(new_command) DO UPDATE SET old_command=EXCLUDED.old_command
        """, old_command, new_command)


async def delete_command(new_command):
    async with get_pool().acquire() as conn:
        status = await conn.execute("DELETE FROM custom_commands WHERE new_command=$1", new_command)
    return int(status.rsplit(" ", 1)[-1])


async def delete_all_commands():
    async with get_pool().acquire() as conn:
        await conn.execute("DELETE FROM custom_commands")
