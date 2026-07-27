"""Streaming path of the DeepSeek provider.

The provider must yield speakable chunks (sentences), not raw token deltas, so
the mobile TTS can start speaking the first sentence while the model is still
writing the rest — this is what removes the long silence before the reply.
"""

import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.messages import Message
from app.features.conversation.providers.deepseek import DeepSeekLlmProvider


class _Delta:
    def __init__(self, content):
        self.content = content


class _StreamChoice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content):
        self.choices = [_StreamChoice(content)]


class _AsyncStream:
    """Async iterator over token-delta chunks, like the OpenAI SDK returns."""

    def __init__(self, deltas):
        self._deltas = deltas

    def __aiter__(self):
        self._it = iter(self._deltas)
        return self

    async def __anext__(self):
        try:
            return _Chunk(next(self._it))
        except StopIteration:
            raise StopAsyncIteration from None


class _StreamingCompletions:
    def __init__(self, recorder, deltas):
        self._recorder = recorder
        self._deltas = deltas

    async def create(self, *, model, messages, max_tokens, stream):
        self._recorder["stream"] = stream
        self._recorder["model"] = model
        return _AsyncStream(self._deltas)


class _StreamingClient:
    def __init__(self, recorder, deltas):
        self.chat = type("C", (), {"completions": _StreamingCompletions(recorder, deltas)})()


class _FailingStreamCompletions:
    async def create(self, *, model, messages, max_tokens, stream):
        raise RuntimeError("stream broke")


class _FailingStreamClient:
    chat = type("C", (), {"completions": _FailingStreamCompletions()})()


async def _collect(provider, system, history):
    return [chunk async for chunk in provider.stream_complete(system, history)]


@pytest.mark.asyncio
async def test_stream_requests_streaming_and_yields_sentences():
    recorder: dict = {}
    # Token deltas that together form two sentences.
    deltas = ["That ", "sounds ", "great", "! ", "What ", "did ", "you ", "do", "?"]
    provider = DeepSeekLlmProvider(
        client=_StreamingClient(recorder, deltas),
        model="deepseek-chat",
        max_tokens=200,
    )

    chunks = await _collect(provider, "SYSTEM", [Message(role="user", content="hi")])

    assert recorder["stream"] is True
    # Speakable units, not raw tokens: each chunk ends a sentence.
    assert chunks == ["That sounds great!", "What did you do?"]


@pytest.mark.asyncio
async def test_stream_flushes_a_trailing_unfinished_sentence():
    deltas = ["Tell ", "me ", "more"]  # no terminal punctuation
    provider = DeepSeekLlmProvider(
        client=_StreamingClient({}, deltas), model="deepseek-chat", max_tokens=200
    )
    chunks = await _collect(provider, "s", [Message(role="user", content="x")])
    assert chunks == ["Tell me more"]


@pytest.mark.asyncio
async def test_stream_ignores_empty_deltas():
    deltas = ["Hi", None, "", " there", "."]
    provider = DeepSeekLlmProvider(
        client=_StreamingClient({}, deltas), model="deepseek-chat", max_tokens=200
    )
    chunks = await _collect(provider, "s", [Message(role="user", content="x")])
    assert chunks == ["Hi there."]


@pytest.mark.asyncio
async def test_stream_wraps_failures_in_domain_error():
    provider = DeepSeekLlmProvider(
        client=_FailingStreamClient(), model="deepseek-chat", max_tokens=50
    )
    with pytest.raises(LlmProviderError):
        await _collect(provider, "s", [Message(role="user", content="x")])
