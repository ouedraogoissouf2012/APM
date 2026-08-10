"""#230: edge-tts talks to an UNOFFICIAL Microsoft endpoint — no key, no SLA.
EdgeTtsProvider.synthesize must not be able to hang a turn indefinitely, and must
still return the right audio bytes on the normal path.
"""

import asyncio
import sys
import types

import pytest

from app.domain.exceptions import LlmProviderError
from app.features.conversation.providers.tts import EdgeTtsProvider


def _install_fake_edge_tts(monkeypatch, communicate_cls):
    fake_module = types.SimpleNamespace(Communicate=communicate_cls)
    monkeypatch.setitem(sys.modules, "edge_tts", fake_module)


@pytest.mark.asyncio
async def test_synthesize_returns_the_streamed_audio_bytes(monkeypatch):
    class _Communicate:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"AB"}
            yield {"type": "audio", "data": b"CD"}

    _install_fake_edge_tts(monkeypatch, _Communicate)

    result = await EdgeTtsProvider().synthesize("hello")

    assert result == b"ABCD"


@pytest.mark.asyncio
async def test_synthesize_ignores_non_audio_chunks(monkeypatch):
    class _Communicate:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            yield {"type": "WordBoundary", "data": b"ignored"}
            yield {"type": "audio", "data": b"only-audio"}

    _install_fake_edge_tts(monkeypatch, _Communicate)

    assert await EdgeTtsProvider().synthesize("hi") == b"only-audio"


@pytest.mark.asyncio
async def test_a_hung_stream_times_out_instead_of_blocking_forever(monkeypatch):
    class _HangingCommunicate:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            await asyncio.sleep(10)  # far longer than the test's short timeout below
            yield {"type": "audio", "data": b"never"}  # pragma: no cover

    _install_fake_edge_tts(monkeypatch, _HangingCommunicate)
    # A short timeout so the test stays fast (the real default is 10s).
    provider = EdgeTtsProvider(timeout_seconds=0.05)

    with pytest.raises(LlmProviderError):
        await provider.synthesize("hello")


@pytest.mark.asyncio
async def test_a_stream_failure_raises_llm_provider_error(monkeypatch):
    class _FailingCommunicate:
        def __init__(self, text, voice):
            pass

        async def stream(self):
            raise RuntimeError("endpoint unreachable")
            yield  # pragma: no cover - keeps this an async generator function

    _install_fake_edge_tts(monkeypatch, _FailingCommunicate)

    with pytest.raises(LlmProviderError):
        await EdgeTtsProvider().synthesize("hello")
