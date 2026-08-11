"""Unit tests for TTS cache backends (#234).

InMemoryTtsCache for single-process (dev/tests) and RedisTtsCache for
production multi-worker. Both implement the TtsCache interface.
"""

from unittest.mock import AsyncMock

from app.features.conversation.providers.tts_cache import (
    InMemoryTtsCache,
    RedisTtsCache,
)


class TestInMemoryTtsCache:
    """Tests for the LRU in-memory cache (dev/tests only)."""

    async def test_get_returns_none_for_missing_key(self):
        cache = InMemoryTtsCache(max_entries=2)
        assert await cache.get("hello") is None

    async def test_set_and_get_roundtrip(self):
        cache = InMemoryTtsCache(max_entries=2)
        audio = b"fake audio data"
        await cache.set("hello", audio)
        assert await cache.get("hello") == audio

    async def test_get_marks_as_recently_used(self):
        """Fetching an entry moves it to the end (MRU)."""
        cache = InMemoryTtsCache(max_entries=2)
        await cache.set("a", b"audio_a")
        await cache.set("b", b"audio_b")
        # Now at capacity (2 entries)
        # Access "a" to mark it MRU, then add "c"
        # Should evict "b", not "a"
        await cache.get("a")
        await cache.set("c", b"audio_c")
        # "a" should still be there, "b" should be evicted
        assert await cache.get("a") == b"audio_a"
        assert await cache.get("b") is None
        assert await cache.get("c") == b"audio_c"

    async def test_lru_eviction_at_capacity(self):
        """When cache is full, evict the least-recently used."""
        cache = InMemoryTtsCache(max_entries=2)
        await cache.set("a", b"audio_a")
        await cache.set("b", b"audio_b")
        # At capacity (2). Add a new entry → evict LRU ("a")
        await cache.set("c", b"audio_c")
        assert await cache.get("a") is None  # evicted
        assert await cache.get("b") == b"audio_b"  # still there
        assert await cache.get("c") == b"audio_c"  # newly added

    async def test_overwrite_existing_key(self):
        """Updating an existing key doesn't evict others."""
        cache = InMemoryTtsCache(max_entries=2)
        await cache.set("hello", b"audio_1")
        await cache.set("hello", b"audio_2")  # overwrite
        assert await cache.get("hello") == b"audio_2"


class TestRedisTtsCache:
    """Tests for the Redis-backed cache (production multi-worker).

    Uses a mock Redis client to avoid external dependencies in unit tests.
    """

    async def test_get_returns_none_when_redis_missing(self):
        """Key not in Redis → None, even if Redis is responsive."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        cache = RedisTtsCache(client=mock_client)
        assert await cache.get("missing") is None

    async def test_get_returns_bytes_from_redis(self):
        """Redis returns bytes → return to caller."""
        mock_client = AsyncMock()
        audio = b"fake audio data"
        mock_client.get = AsyncMock(return_value=audio)
        cache = RedisTtsCache(client=mock_client)
        assert await cache.get("hello") == audio
        mock_client.get.assert_called_once_with("tts:hello")

    async def test_set_calls_setex_with_ttl(self):
        """Store in Redis with TTL (24 hours by default)."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock()
        cache = RedisTtsCache(client=mock_client, ttl_seconds=3600)
        audio = b"fake audio"
        await cache.set("hello", audio)
        mock_client.setex.assert_called_once_with("tts:hello", 3600, audio)

    async def test_get_handles_redis_exception_silently(self):
        """Redis error (timeout, conn) → return None, don't raise."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Redis timeout"))
        cache = RedisTtsCache(client=mock_client)
        assert await cache.get("hello") is None

    async def test_set_ignores_redis_exception(self):
        """Redis error during store → best-effort, don't raise."""
        mock_client = AsyncMock()
        mock_client.setex = AsyncMock(side_effect=Exception("Redis connection failed"))
        cache = RedisTtsCache(client=mock_client)
        # Should not raise
        await cache.set("hello", b"audio")

    async def test_custom_namespace(self):
        """Use a custom Redis key prefix (#234)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b"audio")
        cache = RedisTtsCache(client=mock_client, namespace="custom")
        await cache.get("hello")
        mock_client.get.assert_called_once_with("custom:hello")

    async def test_get_ignores_non_bytes_from_redis(self):
        """If Redis returns non-bytes (shouldn't happen), treat as miss."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value="not bytes")  # type: ignore
        cache = RedisTtsCache(client=mock_client)
        assert await cache.get("hello") is None
