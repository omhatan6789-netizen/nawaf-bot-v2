"""Lightweight async duration logging for performance diagnosis."""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("nawaf.performance")


def timed(label: str):
    """Log total wall-clock duration of an async handler or DB operation."""
    def decorate(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            started = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info("PERF %s duration_ms=%.1f", label, elapsed_ms)
        return wrapper
    return decorate
