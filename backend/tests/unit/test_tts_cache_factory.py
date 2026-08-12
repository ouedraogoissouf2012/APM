"""Unit tests for TTS cache factory (#234).

Selects between InMemoryTtsCache (dev/tests) and RedisTtsCache (production)
based on redis_url configuration.
"""

import pytest

from app.core import http_lifecycle
from app.features.conversation.providers.tts_cache import (
    InMemoryTtsCache,
    RedisTtsCache,
)
from app.features.conversation.providers.tts_cache_factory import build_tts_cache


def test_builds_in_memory_when_no_redis_url():
    """Empty redis_url → single-process in-memory cache."""
    cache = build_tts_cache(redis_url="")
    assert isinstance(cache, InMemoryTtsCache)


def test_builds_redis_when_url_is_set():
    """redis_url set → multi-worker Redis-backed cache."""
    cache = build_tts_cache(redis_url="redis://localhost:6379/0")
    assert isinstance(cache, RedisTtsCache)


def test_in_memory_respects_max_entries():
    """InMemoryTtsCache receives the max_entries parameter."""
    cache = build_tts_cache(redis_url="", max_entries=512)
    assert isinstance(cache, InMemoryTtsCache)
    assert cache._max == 512


def test_redis_respects_ttl():
    """RedisTtsCache receives the ttl_seconds parameter."""
    cache = build_tts_cache(redis_url="redis://localhost:6379/0", ttl_seconds=3600)
    assert isinstance(cache, RedisTtsCache)
    assert cache._ttl == 3600


@pytest.fixture(autouse=True)
def _isolate_registry():
    # http_lifecycle's registry is process-wide module state — isolate it so
    # this file's assertions see only what it registered (#303).
    http_lifecycle._registered.clear()
    yield
    http_lifecycle._registered.clear()


@pytest.mark.asyncio
async def test_redis_cache_is_registered_for_shutdown_close():
    """#303: build_tts_cache's Redis-backed cache is registered with
    http_lifecycle so its connection pool is closed at shutdown — it was
    previously reclaimed only by process exit/GC, like the LLM/STT/pronunciation
    clients were before #280."""
    cache = build_tts_cache(redis_url="redis://localhost:6379/0")

    assert http_lifecycle._registered == [cache]

    await http_lifecycle.close_all()  # must not raise, even with no Redis server running
    assert http_lifecycle._registered == []


def test_in_memory_cache_is_not_registered_for_shutdown_close():
    """No Redis client to close in dev/test mode — nothing should be registered."""
    build_tts_cache(redis_url="")

    assert http_lifecycle._registered == []
