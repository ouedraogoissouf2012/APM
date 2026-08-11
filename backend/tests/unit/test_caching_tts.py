"""Unit tests for the TTS cache (#123, #234).

Every turn re-synthesized audio from scratch — including identical opening lines
served to every user. A content-addressed cache (same text+voice -> same bytes)
cuts latency and calls to the (unofficial) edge endpoint. It wraps any TtsProvider
(decorator/DIP) and uses a swappable cache backend (in-memory or Redis).
"""

import pytest

from app.features.conversation.providers.caching_tts import CachingTtsProvider
from app.features.conversation.providers.tts_cache import InMemoryTtsCache


class _CountingTts:
    """A fake provider that records how many times it actually synthesized."""

    def __init__(self) -> None:
        self.calls = 0

    async def synthesize(self, text: str) -> bytes:
        self.calls += 1
        return f"audio::{text}".encode()


@pytest.mark.asyncio
async def test_first_call_synthesizes_and_returns_bytes():
    inner = _CountingTts()
    cache = InMemoryTtsCache(max_entries=8)
    tts = CachingTtsProvider(inner, cache)
    assert await tts.synthesize("hello") == b"audio::hello"
    assert inner.calls == 1


@pytest.mark.asyncio
async def test_repeated_text_is_served_from_cache():
    inner = _CountingTts()
    cache = InMemoryTtsCache(max_entries=8)
    tts = CachingTtsProvider(inner, cache)
    a = await tts.synthesize("hello")
    b = await tts.synthesize("hello")
    assert a == b
    assert inner.calls == 1  # second call hit the cache, no re-synthesis


@pytest.mark.asyncio
async def test_different_text_is_synthesized_separately():
    inner = _CountingTts()
    cache = InMemoryTtsCache(max_entries=8)
    tts = CachingTtsProvider(inner, cache)
    await tts.synthesize("hello")
    await tts.synthesize("goodbye")
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_cache_is_bounded_and_evicts_least_recently_used():
    inner = _CountingTts()
    cache = InMemoryTtsCache(max_entries=2)
    tts = CachingTtsProvider(inner, cache)
    await tts.synthesize("a")  # cache: [a]
    await tts.synthesize("b")  # cache: [a, b]
    await tts.synthesize("c")  # evicts a -> cache: [b, c]
    await tts.synthesize("a")  # a was evicted -> re-synthesized
    assert inner.calls == 4


@pytest.mark.asyncio
async def test_empty_text_is_not_cached_and_not_synthesized():
    # Nothing to speak: return empty bytes without calling the backend.
    inner = _CountingTts()
    cache = InMemoryTtsCache(max_entries=8)
    tts = CachingTtsProvider(inner, cache)
    assert await tts.synthesize("") == b""
    assert inner.calls == 0
