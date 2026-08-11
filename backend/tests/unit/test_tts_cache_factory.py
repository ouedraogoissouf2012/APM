"""Unit tests for TTS cache factory (#234).

Selects between InMemoryTtsCache (dev/tests) and RedisTtsCache (production)
based on redis_url configuration.
"""

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
