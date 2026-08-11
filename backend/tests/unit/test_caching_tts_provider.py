"""Unit tests for CachingTtsProvider (#123, #234).

Caching strategy is delegated to a TtsCache implementation (in-memory or Redis),
so the provider doesn't care which backend is used — it just uses the abstract
protocol.
"""

from unittest.mock import AsyncMock

from app.features.conversation.providers.caching_tts import CachingTtsProvider


class TestCachingTtsProvider:
    """Tests for content-addressed TTS caching."""

    async def test_empty_text_returns_empty_bytes(self):
        """Empty text is a no-op: no synthesis, no caching."""
        tts_provider = AsyncMock()
        cache = AsyncMock()
        provider = CachingTtsProvider(tts_provider, cache)
        result = await provider.synthesize("")
        assert result == b""
        tts_provider.synthesize.assert_not_called()
        cache.get.assert_not_called()
        cache.set.assert_not_called()

    async def test_cache_miss_calls_tts_and_stores(self):
        """Text not in cache → synthesize, store, return."""
        tts_provider = AsyncMock()
        tts_provider.synthesize = AsyncMock(return_value=b"audio_bytes")
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)  # cache miss
        cache.set = AsyncMock()
        provider = CachingTtsProvider(tts_provider, cache)

        result = await provider.synthesize("hello")

        assert result == b"audio_bytes"
        cache.get.assert_called_once_with("hello")
        tts_provider.synthesize.assert_called_once_with("hello")
        cache.set.assert_called_once_with("hello", b"audio_bytes")

    async def test_cache_hit_returns_cached_without_synthesis(self):
        """Text in cache → return cached, no synthesis."""
        tts_provider = AsyncMock()
        cached_audio = b"cached_audio"
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=cached_audio)
        provider = CachingTtsProvider(tts_provider, cache)

        result = await provider.synthesize("hello")

        assert result == cached_audio
        cache.get.assert_called_once_with("hello")
        tts_provider.synthesize.assert_not_called()
        cache.set.assert_not_called()

    async def test_different_texts_use_separate_cache_entries(self):
        """Cache key is the text; different texts don't collide."""
        tts_provider = AsyncMock()
        tts_provider.synthesize = AsyncMock(side_effect=[b"audio1", b"audio2"])
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        provider = CachingTtsProvider(tts_provider, cache)

        await provider.synthesize("hello")
        await provider.synthesize("goodbye")

        assert cache.get.call_count == 2
        cache.get.assert_any_call("hello")
        cache.get.assert_any_call("goodbye")
        assert tts_provider.synthesize.call_count == 2
        assert cache.set.call_count == 2
