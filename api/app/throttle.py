"""Login throttling (architecture Section 6.4 / PRD 9.1).

A lightweight in-memory per-IP + per-email failure counter that locks
out further attempts after MAX_FAILURES rapid failures within a
COOLDOWN_WINDOW. Not a WAF, just enough to blunt brute force, per the
architecture's explicit "lightweight ... in-memory" call (assumption 6).

NOTE: this state is a module-level dict, so it is per-process. That is
acceptable for the MVP's single-Uvicorn-process deployment (architecture
8.2); it resets on restart and is not shared across multiple processes.
"""

import time

MAX_FAILURES = 5
COOLDOWN_SECONDS = 15 * 60

# key -> (failure_count, first_failure_timestamp)
_failures: dict[str, tuple[int, float]] = {}


def _is_locked(key: str, now: float) -> bool:
    entry = _failures.get(key)
    if entry is None:
        return False
    count, first_failure_at = entry
    if now - first_failure_at > COOLDOWN_SECONDS:
        # Window has expired; clear it lazily and treat as not locked.
        del _failures[key]
        return False
    return count >= MAX_FAILURES


def check_locked(*keys: str) -> bool:
    """Return True if any of the given keys (e.g. IP, email) is locked out."""
    now = time.monotonic()
    return any(_is_locked(key, now) for key in keys)


def record_failure(*keys: str) -> None:
    """Record a failed login attempt for each of the given keys."""
    now = time.monotonic()
    for key in keys:
        count, first_failure_at = _failures.get(key, (0, now))
        if now - first_failure_at > COOLDOWN_SECONDS:
            # Previous window expired; start a fresh one.
            count, first_failure_at = 0, now
        _failures[key] = (count + 1, first_failure_at)


def record_success(*keys: str) -> None:
    """Clear failure counters for the given keys on a successful login."""
    for key in keys:
        _failures.pop(key, None)
