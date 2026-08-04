"""Unit tests for FallbackLlmProvider (the Groq -> DeepSeek safety net).

Groq (fast, free) is tried first; on ANY failure (429 quota, timeout, network),
DeepSeek (paid, unlimited) takes over — so the conversation never breaks and the
learner never sees a dead turn. History is engine-neutral (stored as text), so the
takeover is seamless: DeepSeek receives the same messages Groq did.

Streaming caveat encoded here: fall back ONLY if the primary fails BEFORE emitting
its first chunk. Once tokens have streamed to the client, we cannot un-send them.
"""

import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import ROLE_USER, Message
from app.features.conversation.providers.fallback import FallbackLlmProvider


class _StubLlm:
    """A scripted LLM: replies text (or raises), and records if it was called."""

    def __init__(self, name: str, *, reply: str | None = None, error: Exception | None = None):
        self.name = name
        self._reply = reply
        self._error = error
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        self.complete_calls += 1
        if self._error is not None:
            raise self._error
        return self._reply or ""

    async def stream_complete(self, system_prompt, history):
        self.stream_calls += 1
        if self._error is not None:
            raise self._error
        for word in (self._reply or "").split():
            yield word


_HISTORY = [Message(role=ROLE_USER, content="hello")]


@pytest.mark.asyncio
async def test_complete_uses_primary_when_it_succeeds():
    primary = _StubLlm("groq", reply="Hi from Groq")
    secondary = _StubLlm("deepseek", reply="Hi from DeepSeek")
    provider = FallbackLlmProvider([primary, secondary])

    assert await provider.complete("sys", _HISTORY) == "Hi from Groq"
    assert primary.complete_calls == 1
    assert secondary.complete_calls == 0  # never needed


@pytest.mark.asyncio
async def test_complete_falls_back_on_primary_error():
    primary = _StubLlm("groq", error=LlmProviderError("429 rate limited"))
    secondary = _StubLlm("deepseek", reply="Hi from DeepSeek")
    provider = FallbackLlmProvider([primary, secondary])

    assert await provider.complete("sys", _HISTORY) == "Hi from DeepSeek"
    assert primary.complete_calls == 1
    assert secondary.complete_calls == 1  # took over


@pytest.mark.asyncio
async def test_complete_raises_when_all_fail():
    primary = _StubLlm("groq", error=LlmProviderError("down"))
    secondary = _StubLlm("deepseek", error=LlmProviderError("also down"))
    provider = FallbackLlmProvider([primary, secondary])

    with pytest.raises(LlmProviderError):
        await provider.complete("sys", _HISTORY)


@pytest.mark.asyncio
async def test_stream_uses_primary_when_it_succeeds():
    primary = _StubLlm("groq", reply="one two three")
    secondary = _StubLlm("deepseek", reply="other")
    provider = FallbackLlmProvider([primary, secondary])

    chunks = [c async for c in provider.stream_complete("sys", _HISTORY)]
    assert chunks == ["one", "two", "three"]
    assert secondary.stream_calls == 0


@pytest.mark.asyncio
async def test_stream_falls_back_when_primary_fails_before_first_chunk():
    # Groq errors immediately (e.g. 429 on connect) -> DeepSeek streams instead.
    primary = _StubLlm("groq", error=LlmProviderError("429"))
    secondary = _StubLlm("deepseek", reply="fallback reply here")
    provider = FallbackLlmProvider([primary, secondary])

    chunks = [c async for c in provider.stream_complete("sys", _HISTORY)]
    assert chunks == ["fallback", "reply", "here"]
    assert primary.stream_calls == 1
    assert secondary.stream_calls == 1


@pytest.mark.asyncio
async def test_stream_does_not_fall_back_after_first_chunk_emitted():
    # Once a chunk has streamed to the client, a later failure must NOT restart on
    # the secondary (that would duplicate/garble the reply). It just ends.
    class _FailsMidStream:
        stream_calls = 0

        async def stream_complete(self, system_prompt, history):
            type(self).stream_calls += 1
            yield "first"
            raise LlmProviderError("died mid-stream")

        async def complete(self, system_prompt, history):  # pragma: no cover
            return ""

    primary = _FailsMidStream()
    secondary = _StubLlm("deepseek", reply="should not appear")
    provider = FallbackLlmProvider([primary, secondary])

    chunks = []
    with pytest.raises(LlmProviderError):
        async for c in provider.stream_complete("sys", _HISTORY):
            chunks.append(c)
    assert chunks == ["first"]  # what already streamed
    assert secondary.stream_calls == 0  # no restart after first chunk
