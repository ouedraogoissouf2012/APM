"""Build a TTS cache backend from configuration (#234).

`InMemoryTtsCache` for single-process (dev/tests, no Redis dependency);
`RedisTtsCache` for production multi-worker (set REDIS_URL). Callers depend on
the `TtsCache` interface, so nothing changes when the backend does.
"""

from typing import cast

from app.core.http_lifecycle import register_closeable
from app.core.llm.interfaces import TtsCache
from app.features.conversation.providers.tts_cache import (
    InMemoryTtsCache,
    RedisTtsCache,
)


def build_tts_cache(
    *,
    max_entries: int = 256,
    redis_url: str = "",
    ttl_seconds: int = 86400,
) -> TtsCache:
    """Build a TTS cache backend from config.

    If redis_url is empty, returns InMemoryTtsCache (dev/test, single process).
    In production (multi-worker), set REDIS_URL to share cache across instances.

    Args:
        max_entries: Max entries in the in-memory cache (ignored if redis_url is set).
        redis_url: Redis URL (empty → in-memory, single-process).
        ttl_seconds: Redis entry TTL in seconds (ignored if in-memory mode).
    """
    if not redis_url.strip():
        return InMemoryTtsCache(max_entries=max_entries)
    # Import redis lazily so dev/test installs need no Redis dependency.
    from redis.asyncio import Redis

    # redis-py's async client provides get, setex, etc. callable positionally,
    # satisfying our minimal interface; cast to the protocol we actually use.
    client = cast(type, Redis.from_url(redis_url))
    # Registered so its connection pool is closed at shutdown (#303) — otherwise
    # it's reclaimed only by process exit/GC, like the LLM/STT/pronunciation
    # clients were before #280.
    return register_closeable(RedisTtsCache(client=client, ttl_seconds=ttl_seconds))
