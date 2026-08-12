"""Swappable TTS cache backends: in-memory (dev/tests) and Redis (production multi-worker).

Abstracts the caching strategy (#123, #234) so a single-process dev/test build stays
in-memory (no Redis dependency) while production multi-worker deployments use Redis
to share the cache across instances.
"""

import contextlib
from collections import OrderedDict
from typing import Any


class InMemoryTtsCache:
    """LRU cache for synthesized audio, single-process (dev/tests only).

    Each worker has its own cache (limits × N workers, cache misses after rotation),
    but single-process dev/test stays simple and fast.
    """

    def __init__(self, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max = max_entries
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    async def get(self, text: str) -> bytes | None:
        """Fetch cached audio, marking it as recently used."""
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        return None

    async def set(self, text: str, audio: bytes) -> None:
        """Store audio, evicting LRU entry if at capacity."""
        self._cache[text] = audio
        self._cache.move_to_end(text)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)  # evict least-recently used


class RedisTtsCache:
    """Redis-backed TTS cache, shared across all app instances (#234).

    Trades memory footprint (Redis overhead) for multi-worker correctness:
    the same audio is cached once, shared by all workers, so a repeat is always
    instant regardless of which worker served the original synthesis.

    Each entry has a TTL so the cache never grows without bound. Entries older
    than the TTL are silently dropped by Redis.
    """

    def __init__(self, client: Any, namespace: str = "tts", ttl_seconds: int = 86400) -> None:
        """
        Args:
            client: Redis async client (e.g., from redis.asyncio.Redis.from_url).
            namespace: Redis key prefix, so TTS cache doesn't collide with other caches.
            ttl_seconds: How long to keep each cache entry (default 24 hours).
        """
        self._client = client
        self._namespace = namespace
        self._ttl = ttl_seconds

    async def get(self, text: str) -> bytes | None:
        """Fetch cached audio from Redis."""
        key = f"{self._namespace}:{text}"
        # Redis failure (timeout, conn error): silently fall through, caller
        # will re-synthesize (#234 best-effort caching).
        with contextlib.suppress(Exception):
            result = await self._client.get(key)
            return result if isinstance(result, bytes) else None
        return None

    async def set(self, text: str, audio: bytes) -> None:
        """Store audio in Redis with TTL, ignoring failures (best-effort)."""
        key = f"{self._namespace}:{text}"
        # Redis failure: cache miss, caller re-synthesizes on next request.
        # Non-fatal — synthesis is always possible, just slower.
        with contextlib.suppress(Exception):
            await self._client.setex(key, self._ttl, audio)

    async def aclose(self) -> None:
        """Close the underlying Redis client's connection pool at process
        shutdown (app.core.http_lifecycle, #303)."""
        await self._client.aclose()
