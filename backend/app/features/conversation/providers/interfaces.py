from typing import Protocol

from app.features.conversation.messages import Message


class SttProvider(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


class LlmProvider(Protocol):
    async def complete(self, system_prompt: str, history: list[Message]) -> str: ...


class TtsProvider(Protocol):
    async def synthesize(self, text: str) -> bytes: ...
