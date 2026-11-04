"""Buffered message activity tracking."""
import asyncio

from database.pool import get_pool

POINTS_PER_MESSAGE = 10
