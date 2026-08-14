"""A content-addressed cache in front of any TtsProvider (#123, #234).

Every turn re-synthesized audio, re-doing identical work for repeated lines (e.g.
the same opening served to every user) and hitting the unofficial edge endpoint
each time. This decorator memoizes bytes by the synthesized text, so a repeat is
instant and endpoint-free. The cache backend (in-memory LRU for single-process,
Redis for multi-worker production) is swappable.

The key is the text only: one CachingTtsProvider wraps one provider, which is
pinned to a single voice — so text uniquely identifies the audio here.
"""

from app.core.llm.interfaces import TtsCache, TtsProvider


class CachingTtsProvider:
    """Wraps a TtsProvider and caches its output by text.

    Delegates caching strategy (in-memory LRU vs Redis) to the TtsCache
    implementation, so multi-worker production uses Redis while dev/tests stay
    in-memory (#234).
    """

    def __init__(self, inner: TtsProvider, cache: TtsCache) -> None:
        self._inner = inner
        self._cache = cache

    async def synthesize(self, text: str) -> bytes:
        if not text:
            return b""  # nothing to speak; don't cache or call the backend
        cached = await self._cache.get(text)
        if cached is not None:
            return cached
        audio = await self._inner.synthesize(text)
        await self._cache.set(text, audio)
        return audio
