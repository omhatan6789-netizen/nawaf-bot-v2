import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_url: str
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10
    db_command_timeout: int = 30


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not token:
        raise RuntimeError("BOT_TOKEN is missing. Set it in the environment.")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing. Set it in the environment.")

    min_size = _int_env("DB_POOL_MIN_SIZE", 1)
    max_size = _int_env("DB_POOL_MAX_SIZE", 10)
    command_timeout = _int_env("DB_COMMAND_TIMEOUT", 30)

    if min_size < 1 or max_size < min_size:
        raise RuntimeError("Database pool sizes are invalid.")
    if command_timeout < 1:
        raise RuntimeError("DB_COMMAND_TIMEOUT must be greater than zero.")

    return Settings(
        bot_token=token,
        database_url=database_url,
        db_pool_min_size=min_size,
        db_pool_max_size=max_size,
        db_command_timeout=command_timeout,
    )
