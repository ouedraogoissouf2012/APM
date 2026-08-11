"""Unit tests for FallbackLlmProvider (the Groq -> DeepSeek safety net).

Groq (fast, free) is tried first; on ANY failure (429 quota, timeout, network),
DeepSeek (paid, unlimited) takes over — so the conversation never breaks and the
learner never sees a dead turn. History is engine-neutral (stored as text), so the
takeover is seamless: DeepSeek receives the same messages Groq did.

Streaming caveat encoded here: fall back ONLY if the primary fails BEFORE emitting
its first chunk. Once tokens have streamed to the client, we cannot un-send them.
"""

import asyncio

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


# --- Global deadline across the whole chain (#230) -----------------------------
#
# Each provider already has its OWN client-level timeout, but nothing previously
# capped the TOTAL time the chain could spend trying every provider in sequence —
# two ~20s timeouts could stack to ~40s+. These stubs simulate a provider that
# HANGS (never resolves) rather than erroring, so only a deadline (not the
# provider's own failure path) can end the attempt.


class _HangingLlm:
    """Never completes — simulates a provider whose request is stuck, not failed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.complete_calls = 0
        self.stream_calls = 0

    async def complete(self, system_prompt: str, history: list[Message]) -> str:
        self.complete_calls += 1
        await asyncio.sleep(10)  # far longer than any test's deadline
        return "never"  # pragma: no cover

    async def stream_complete(self, system_prompt, history):
        self.stream_calls += 1
        await asyncio.sleep(10)
        yield "never"  # pragma: no cover


@pytest.mark.asyncio
async def test_complete_gives_up_once_the_global_deadline_is_exceeded():
    primary = _HangingLlm("groq")
    secondary = _StubLlm("deepseek", reply="should not be reached")
    # A short deadline so the test itself stays fast (the real default is 15s).
    provider = FallbackLlmProvider([primary, secondary], deadline_seconds=0.05)

    with pytest.raises(LlmProviderError):
        await provider.complete("sys", _HISTORY)


@pytest.mark.asyncio
async def test_stream_gives_up_once_the_global_deadline_is_exceeded():
    # Deterministic: an INJECTED clock drives the deadline instead of a sub-100 ms
    # wall-clock sleep, which was flaky under load. The primary is tried and fails,
    # then the clock reports the global deadline exceeded, so the chain gives up
    # WITHOUT falling through to the secondary.
    primary = _StubLlm("groq", error=LlmProviderError("boom"))
    secondary = _StubLlm("deepseek", reply="should not be reached")
    ticks = iter([0.0, 0.0])  # anchor the deadline at 0; the primary is still in budget...
    provider = FallbackLlmProvider(
        [primary, secondary],
        deadline_seconds=15.0,
        now=lambda: next(ticks, 100.0),  # ...then the clock jumps past the deadline
    )

    chunks = []
    with pytest.raises(LlmProviderError):
        async for c in provider.stream_complete("sys", _HISTORY):
            chunks.append(c)

    assert chunks == []
    assert primary.stream_calls == 1  # the primary WAS attempted
    assert secondary.stream_calls == 0  # ...but the deadline stopped the fallover


@pytest.mark.asyncio
async def test_stream_deadline_no_longer_applies_once_a_chunk_has_been_emitted():
    # A provider that starts streaming slowly (one word, then a long pause) must
    # be allowed to keep going past the deadline — a turn that has started
    # speaking must never be aborted mid-reply, deadline or not.
    class _SlowAfterFirstChunk:
        stream_calls = 0

        async def stream_complete(self, system_prompt, history):
            type(self).stream_calls += 1
            yield "first"
            await asyncio.sleep(0.1)  # longer than the deadline below
            yield "second"

        async def complete(self, system_prompt, history):  # pragma: no cover
            return ""

    primary = _SlowAfterFirstChunk()
    secondary = _StubLlm("deepseek", reply="should not be reached")
    provider = FallbackLlmProvider([primary, secondary], deadline_seconds=0.02)

    chunks = [c async for c in provider.stream_complete("sys", _HISTORY)]

    assert chunks == ["first", "second"]  # completed despite exceeding the deadline
    assert secondary.stream_calls == 0


@pytest.mark.asyncio
async def test_a_fast_primary_still_succeeds_within_the_default_deadline():
    # Sanity check: the (generous) default deadline never gets in the way of a
    # normal, fast-completing turn.
    primary = _StubLlm("groq", reply="Hi from Groq")
    secondary = _StubLlm("deepseek", reply="unused")
    provider = FallbackLlmProvider([primary, secondary])  # default deadline

    assert await provider.complete("sys", _HISTORY) == "Hi from Groq"
