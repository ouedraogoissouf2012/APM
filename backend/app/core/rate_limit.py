"""Rate limiting as a swappable abstraction.

`RateLimiter` is the interface the API depends on. `InMemoryRateLimiter` is a
sliding-window implementation for a single process; a Redis-backed limiter can
be substituted later without touching callers (OCP/DIP/LSP). `NoOpRateLimiter`
disables limiting (used as the default in tests).
"""

import time
from collections import defaultdict, deque
from typing import Protocol

from app.domain.exceptions import RateLimitedError


class RateLimiter(Protocol):
    async def check(self, key: str) -> None:
        """Raise RateLimitedError if `key` has exceeded its allowance."""
        ...


class InMemoryRateLimiter:
    def __init__(self, max_hits: int, window_seconds: int) -> None:
        self._max = max_hits
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            raise RateLimitedError("Too many attempts, please retry later")
        bucket.append(now)


class NoOpRateLimiter:
    async def check(self, key: str) -> None:
        return None
