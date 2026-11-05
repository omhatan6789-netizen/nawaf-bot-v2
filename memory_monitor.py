"""Low-overhead process/container memory diagnostics for Render.

Uses Linux procfs/cgroup counters and deliberately avoids tracemalloc/psutil so
monitoring itself adds negligible memory overhead.
"""
import logging
import os
from pathlib import Path
from threading import Event, Thread
import time

logger = logging.getLogger("nawaf.memory")
_stop = Event()
_thread = None


def _read_number(path):
    try:
        value = Path(path).read_text(encoding="ascii").strip()
        if value == "max":
            return None
        return int(value)
    except (OSError, ValueError):
        return None


def _memory_snapshot():
    values = {}
    try:
        for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "VmSize:", "Threads:")):
                key, raw = line.split(":", 1)
                parts = raw.strip().split()
                if parts:
                    values[key.lower()] = int(parts[0])
    except (OSError, ValueError):
        pass

    # cgroup v2 first, then the common cgroup v1 memory controller paths.
    usage = _read_number("/sys/fs/cgroup/memory.current")
    limit = _read_number("/sys/fs/cgroup/memory.max")
    if usage is None:
        usage = _read_number("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if limit is None:
        limit = _read_number("/sys/fs/cgroup/memory/memory.limit_in_bytes")

    try:
        fd_count = len(os.listdir("/proc/self/fd"))
    except OSError:
        fd_count = -1

    return {
        "rss_mb": round(values.get("vmrss", 0) / 1024, 1),
        "peak_rss_mb": round(values.get("vmhwm", 0) / 1024, 1),
        "vmsize_mb": round(values.get("vmsize", 0) / 1024, 1),
        "threads": values.get("threads", -1),
        "fds": fd_count,
        "container_mb": round(usage / (1024 * 1024), 1) if usage is not None else None,
        "container_limit_mb": round(limit / (1024 * 1024), 1) if limit and limit < (1 << 60) else None,
    }


def _monitor_loop(interval_seconds):
    previous = None
    while not _stop.is_set():
        snapshot = _memory_snapshot()
        rss_delta = round(snapshot["rss_mb"] - previous, 1) if previous is not None else 0.0
        previous = snapshot["rss_mb"]
        fields = " ".join(f"{key}={value}" for key, value in snapshot.items() if value is not None)
        fields += f" rss_delta_prev_mb={rss_delta}"
        limit = snapshot.get("container_limit_mb")
        usage = snapshot.get("container_mb")
        if limit and usage is not None and usage >= limit * 0.75:
            logger.warning("MEMORY_HIGH %s", fields)
        else:
            logger.info("MEMORY_SNAPSHOT %s", fields)
        _stop.wait(interval_seconds)


def log_memory_checkpoint(label):
    """Log a named startup/runtime checkpoint with current process memory."""
    snapshot = _memory_snapshot()
    fields = " ".join(f"{key}={value}" for key, value in snapshot.items() if value is not None)
    logger.info("MEMORY_CHECKPOINT label=%s %s", label, fields)


def start_memory_monitor(interval_seconds=15):
    """Start one daemon monitor thread; safe to call more than once."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = Thread(
        target=_monitor_loop,
        args=(max(15, int(interval_seconds)),),
        name="render-memory-monitor",
        daemon=True,
    )
    _thread.start()
