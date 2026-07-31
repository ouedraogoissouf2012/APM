"""A content-addressed cache in front of any TtsProvider (#123).

Every turn re-synthesized audio, re-doing identical work for repeated lines (e.g.
the same opening served to every user) and hitting the unofficial edge endpoint
each time. This decorator memoizes bytes by the synthesized text, so a repeat is
instant and endpoint-free. Bounded (LRU) so it can never grow without limit.

The key is the text only: one CachingTtsProvider wraps one provider, which is
pinned to a single voice — so text uniquely identifies the audio here.
"""

from collections import OrderedDict

from app.features.conversation.providers.interfaces import TtsProvider


class CachingTtsProvider:
    """Wraps a TtsProvider and caches its output by text (bounded, LRU)."""

    def __init__(self, inner: TtsProvider, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._inner = inner
        self._max = max_entries
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    async def synthesize(self, text: str) -> bytes:
        if not text:
            return b""  # nothing to speak; don't cache or call the backend
        cached = self._cache.get(text)
        if cached is not None:
            self._cache.move_to_end(text)  # mark most-recently used
            return cached
        audio = await self._inner.synthesize(text)
        self._cache[text] = audio
        self._cache.move_to_end(text)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)  # evict least-recently used
        return audio
