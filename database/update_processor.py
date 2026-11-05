"""Bounded concurrent update processing while preserving order per chat."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable

from telegram.ext import BaseUpdateProcessor

logger = logging.getLogger("nawaf.performance")


class ChatSerialUpdateProcessor(BaseUpdateProcessor):
    """Run independent chats concurrently while keeping each chat sequential."""

    def __init__(self, max_concurrent_updates: int = 16, lock_stripes: int = 64):
        super().__init__(max_concurrent_updates=max_concurrent_updates)
        self._locks = tuple(asyncio.Lock() for _ in range(lock_stripes))

    def _lock_for(self, update: object) -> tuple[asyncio.Lock, str]:
        chat = getattr(update, "effective_chat", None)
        if chat is not None:
            key = ("chat", chat.id)
            label = "chat"
        else:
            user = getattr(update, "effective_user", None)
            if user is not None:
                key = ("user", user.id)
                label = "private"
            else:
                key = ("update", getattr(update, "update_id", 0))
                label = "other"
        return self._locks[hash(key) % len(self._locks)], label

    async def do_process_update(
        self,
        update: object,
        coroutine: Awaitable[Any],
    ) -> None:
        lock, update_kind = self._lock_for(update)
        queued_at = time.perf_counter()
        async with lock:
            started_at = time.perf_counter()
            try:
                await coroutine
            finally:
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                wait_ms = (started_at - queued_at) * 1000
                if wait_ms >= 50 or elapsed_ms >= 200:
                    logger.info(
                        "PERF update_processor kind=%s wait_ms=%.1f duration_ms=%.1f",
                        update_kind,
                        wait_ms,
                        elapsed_ms,
                    )
