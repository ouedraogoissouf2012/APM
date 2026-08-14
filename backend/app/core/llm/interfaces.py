from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

from app.core.llm.messages import Message


@dataclass(frozen=True)
class TranscriptWord:
    """One recognized word with the recognizer's confidence in it (0..1), used to
    score how clearly it was pronounced. `probability` is None when the STT
    backend does not expose per-word confidence."""

    word: str
    probability: float | None = None


@dataclass(frozen=True)
class VerboseTranscript:
    """A transcript plus per-word confidence, for pronunciation scoring."""

    text: str
    words: list[TranscriptWord] = field(default_factory=list)


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...

    async def transcribe_verbose(self, audio: bytes) -> VerboseTranscript:
        """Transcribe with per-word confidence (for pronunciation scoring). A
        provider that cannot supply word confidence returns words with
        probability=None (or an empty word list)."""
        ...


class TextCompletionProvider(Protocol):
    """Just a single blocking completion — all the debrief analyzer needs."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str: ...


class LlmProvider(TextCompletionProvider, Protocol):
    """A conversation LLM: blocking completion plus streamed sentences."""

    def stream_complete(self, system_prompt: str, history: list[Message]) -> AsyncIterator[str]:
        """Yield the reply as speakable chunks (sentences) as they are generated,
        so the client can start speaking before the whole reply is ready."""
        ...


class TtsProvider(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


class TtsCache(Protocol):
    """Content-addressed cache for synthesized audio.

    Abstracts the caching backend (in-memory for dev/tests, Redis for multi-worker
    production). Key is the synthesis text; value is audio bytes. Entries may be
    evicted by the cache itself (TTL/LRU) — callers should not assume persistence.
    """

    async def get(self, text: str) -> bytes | None:
        """Fetch cached audio for text, or None if not in cache."""
        ...

    async def set(self, text: str, audio: bytes) -> None:
        """Store audio for text, subject to cache eviction policy."""
        ...
