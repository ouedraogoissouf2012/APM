"""Unit tests for the process-wide HTTP client shutdown registry (#280).

Covers the registry mechanism (register/close_all/best-effort) and that each
client-owning provider's `aclose()` closes its OWN client via the right method —
`httpx.AsyncClient.aclose()` for pronunciation, `AsyncOpenAI.close()` for LLM/STT
(calling the wrong one would only surface as an AttributeError at shutdown).
"""

import pytest

from app.core import http_lifecycle


class _SpyCloseable:
    """A minimal AsyncCloseable that records how many times it was closed."""

    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture(autouse=True)
def _isolate_registry():
    # The registry is process-wide module state also populated by other tests
    # that build real providers — clear it around each test here so assertions
    # see only what this test registered.
    http_lifecycle._registered.clear()
    yield
    http_lifecycle._registered.clear()


def test_register_returns_the_same_object_it_was_given():
    obj = _SpyCloseable()
    assert http_lifecycle.register_closeable(obj) is obj
    assert http_lifecycle._registered == [obj]


@pytest.mark.asyncio
async def test_close_all_closes_every_registered_client_and_drains_the_registry():
    a, b = _SpyCloseable(), _SpyCloseable()
    http_lifecycle.register_closeable(a)
    http_lifecycle.register_closeable(b)

    await http_lifecycle.close_all()

    assert a.closed == 1
    assert b.closed == 1
    assert http_lifecycle._registered == []  # drained, so no double-close later


@pytest.mark.asyncio
async def test_close_all_is_best_effort_one_failure_does_not_block_the_others():
    class _Boom:
        async def aclose(self) -> None:
            raise RuntimeError("cannot close")

    survivor = _SpyCloseable()
    http_lifecycle.register_closeable(_Boom())
    http_lifecycle.register_closeable(survivor)

    await http_lifecycle.close_all()  # must not raise

    assert survivor.closed == 1  # the failing one did not abort shutdown
    assert http_lifecycle._registered == []


@pytest.mark.asyncio
async def test_close_all_on_an_empty_registry_is_a_noop():
    await http_lifecycle.close_all()
    assert http_lifecycle._registered == []


class _SpyHttpxClient:
    """Mimics httpx.AsyncClient's async `aclose()`."""

    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class _SpyOpenAiClient:
    """Mimics AsyncOpenAI's async `close()` (note: NOT `aclose`)."""

    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


@pytest.mark.asyncio
async def test_http_gop_provider_aclose_closes_its_httpx_client():
    from app.features.pronunciation.provider import HttpGopProvider

    client = _SpyHttpxClient()
    provider = HttpGopProvider(client=client, base_url="http://gop")

    await provider.aclose()

    assert client.closed == 1


@pytest.mark.asyncio
async def test_openai_llm_provider_aclose_closes_its_client_via_close():
    from app.features.conversation.providers.deepseek import OpenAiCompatibleLlmProvider

    client = _SpyOpenAiClient()
    provider = OpenAiCompatibleLlmProvider(client=client, model="m", max_tokens=1)

    await provider.aclose()

    assert client.closed == 1


@pytest.mark.asyncio
async def test_groq_stt_provider_aclose_closes_its_client_via_close():
    from app.features.conversation.providers.stt import GroqSttProvider

    provider = GroqSttProvider(api_key="k", base_url="http://x", model="whisper")
    provider._client = _SpyOpenAiClient()  # swap the real client for a spy

    await provider.aclose()

    assert provider._client.closed == 1
