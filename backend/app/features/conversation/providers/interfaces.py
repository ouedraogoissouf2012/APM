from collections.abc import AsyncIterator
from typing import Protocol

from app.features.conversation.messages import Message


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


class TextCompletionProvider(Protocol):
    """Just a single blocking completion — all the debrief analyzer needs."""

    async def complete(self, system_prompt: str, history: list[Message]) -> str: ...


class LlmProvider(TextCompletionProvider, Protocol):
    """A conversation LLM: blocking completion plus streamed sentences."""

    def stream_complete(
        self, system_prompt: str, history: list[Message]
    ) -> AsyncIterator[str]:
        """Yield the reply as speakable chunks (sentences) as they are generated,
        so the client can start speaking before the whole reply is ready."""
        ...


class TtsProvider(Protocol):
    async def synthesize(self, text: str) -> bytes: ...
