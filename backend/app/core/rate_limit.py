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


class RedisRateLimitClient(Protocol):
    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> object: ...


class InMemoryRateLimiter:
    """Fixed-window in-memory limiter (dev/test only, not for production).

    Single-process only — each worker has its own limiter, so limits are per-worker
    (limit × N workers). Evicts expired buckets and enforces a global entry cap
    to prevent a DoS via high-cardinality keys (attacker-controlled emails/tokens).

    Production should use RedisRateLimiter instead."""

    def __init__(self, max_hits: int, window_seconds: int, *, max_keys: int = 1000) -> None:
        self._max = max_hits
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def check(self, key: str) -> None:
        now = time.monotonic()
        # Evict expired hits from this key's sliding window (normal operation).
        if key in self._hits:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self._window:
                bucket.popleft()
            # Cleanup: if bucket is now empty, remove the key entirely.
            if not bucket:
                del self._hits[key]
        # If this is a new key and we're at capacity, evict the oldest bucket
        # before accepting it (FIFO eviction when at capacity).
        if key not in self._hits and len(self._hits) >= self._max_keys:
            oldest_key = next(iter(self._hits))  # First key inserted (FIFO order)
            del self._hits[oldest_key]
        # Now get or create the bucket for this key.
        bucket = self._hits[key]
        # Check rate limit: if bucket is at capacity, reject.
        if len(bucket) >= self._max:
            raise RateLimitedError("Too many attempts, please retry later")
        # Accept the hit.
        bucket.append(now)


class RedisRateLimiter:
    """Fixed-window Redis-compatible limiter.

    The client only needs async `incr` and `expire` methods, which keeps the
    production wiring swappable without forcing a Redis dependency in tests.
    """

    def __init__(
        self,
        client: RedisRateLimitClient,
        *,
        namespace: str,
        max_hits: int,
        window_seconds: int,
    ) -> None:
        self._client = client
        self._namespace = namespace
        self._max = max_hits
        self._window = window_seconds

    async def check(self, key: str) -> None:
        bucket = int(time.time() // self._window)
        redis_key = f"rate:{self._namespace}:{bucket}:{key}"
        hits = await self._client.incr(redis_key)
        if hits == 1:
            await self._client.expire(redis_key, self._window + 1)
        if hits > self._max:
            raise RateLimitedError("Too many attempts, please retry later")


class NoOpRateLimiter:
    async def check(self, key: str) -> None:
        return None
