from collections.abc import AsyncIterator

from app.features.conversation.messages import Message
from app.features.conversation.providers.interfaces import (
    TranscriptWord,
    VerboseTranscript,
)


class FakeStt:
    """Returns scripted transcripts in order; repeats the last one when exhausted."""

    def __init__(self, transcripts: list[str] | None = None) -> None:
        self._transcripts = transcripts or ["(silence)"]
        self._i = 0

    async def transcribe(self, audio: bytes) -> str:
        text = self._transcripts[min(self._i, len(self._transcripts) - 1)]
        self._i += 1
        return text

    async def transcribe_verbose(self, audio: bytes) -> VerboseTranscript:
        text = await self.transcribe(audio)
        words = [TranscriptWord(word=w, probability=0.9) for w in text.split()]
        return VerboseTranscript(text=text, words=words)


class FakeLlm:
    """Deterministic reply that echoes the last user message (no network)."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        return f"You said: {last_user}"

    async def stream_complete(
        self, system_prompt: str, history: list[Message]
    ) -> AsyncIterator[str]:
        """Two deterministic sentences, so the streaming path is exercisable
        without a network provider."""
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        yield f"You said: {last_user}."
        yield "Tell me more."


class FakeTts:
    """Encodes text to bytes — stands in for synthesized audio."""

    async def synthesize(self, text: str) -> bytes:
        return text.encode("utf-8")
