from pathlib import Path
from .pool import get_pool

LOCK_ID = 739184621

async def apply_all_migrations():
    root = Path(__file__).resolve().parent
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute((root / 'schema.sql').read_text(encoding='utf-8'))
        for path in sorted((root / 'migrations').glob('[0-9]*.sql')):
            async with conn.transaction():
                await conn.execute('SELECT pg_advisory_xact_lock($1)', LOCK_ID)
                version = path.name
                done = await conn.fetchval('SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)', version)
                if done:
                    continue
                await conn.execute(path.read_text(encoding='utf-8'))
                await conn.execute('INSERT INTO schema_migrations(version) VALUES($1)', version)
