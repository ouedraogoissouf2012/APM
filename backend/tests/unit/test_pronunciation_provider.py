"""Unit tests for the pronunciation providers (#111 step 2 — GOP bridge).

The backend does not run wav2vec2 itself; it calls the pronunciation microservice
over HTTP. These tests exercise:
- FakePronunciationProvider: the honest default (no engine configured -> no scores),
- HttpGopProvider: request shape + response parsing + failure handling, with the
  network mocked via httpx.MockTransport (no real service needed).
"""

import httpx
import pytest

from app.domain.exceptions import LlmProviderError
from app.features.pronunciation.domain import PhonemeScore
from app.features.pronunciation.provider import (
    FakePronunciationProvider,
    HttpGopProvider,
    gop_service_ready,
)


@pytest.mark.asyncio
async def test_fake_provider_returns_no_scores():
    # The default engine makes no phonetic claim — honest absence, not fake data.
    provider = FakePronunciationProvider()
    assert await provider.score_phonemes(audio=b"anything", target_text="think") == []


@pytest.mark.asyncio
async def test_gop_service_ready_true_on_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/health")
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await gop_service_ready("http://gop:8100", client=client) is True
    await client.aclose()


@pytest.mark.asyncio
async def test_gop_service_ready_false_on_down():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await gop_service_ready("http://gop:8100", client=client) is False
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_posts_audio_and_target_and_parses_scores():
    recorder: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorder["url"] = str(request.url)
        recorder["method"] = request.method
        recorder["content"] = request.content
        recorder["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={
                "phonemes": [
                    {"phoneme": "θ", "score": 0.08, "start": 3, "end": 3},
                    {"phoneme": "ɪ", "score": 0.48, "start": 7, "end": 7},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    scores = await provider.score_phonemes(audio=b"WAVDATA", target_text="thi")

    assert scores == [
        PhonemeScore(phoneme="θ", score=0.08),
        PhonemeScore(phoneme="ɪ", score=0.48),
    ]
    # Calls POST /score on the configured base URL...
    assert recorder["method"] == "POST"
    assert recorder["url"] == "http://gop:8100/score"
    # ...as multipart (the audio file + the target_text form field).
    assert "multipart/form-data" in recorder["content_type"]
    assert b"WAVDATA" in recorder["content"]
    assert b"thi" in recorder["content"]
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_empty_audio_short_circuits_without_calling():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={"phonemes": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    assert await provider.score_phonemes(audio=b"", target_text="think") == []
    assert called["n"] == 0  # never hit the network for empty audio
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_wraps_http_error_in_domain_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    with pytest.raises(LlmProviderError):
        await provider.score_phonemes(audio=b"WAV", target_text="think")
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_wraps_network_failure_in_domain_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("service down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    with pytest.raises(LlmProviderError):
        await provider.score_phonemes(audio=b"WAV", target_text="think")
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_sends_the_shared_secret_header_when_configured():
    # #231: the microservice's require_internal_secret checks X-Internal-Secret.
    recorder: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorder["header"] = request.headers.get("x-internal-secret")
        return httpx.Response(200, json={"phonemes": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100", secret="s3cret-internal")

    await provider.score_phonemes(audio=b"WAV", target_text="think")

    assert recorder["header"] == "s3cret-internal"
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_omits_the_header_when_no_secret_configured():
    # Unconfigured (default, dev/tests): no header sent, matching the service's
    # own no-op default — nothing breaks before both sides are configured.
    recorder: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorder["header"] = request.headers.get("x-internal-secret")
        return httpx.Response(200, json={"phonemes": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    await provider.score_phonemes(audio=b"WAV", target_text="think")

    assert recorder["header"] is None
    await client.aclose()


@pytest.mark.asyncio
async def test_http_provider_tolerates_malformed_phoneme_entries():
    # A phoneme missing its score is skipped, not a crash — defensive parsing.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"phonemes": [{"phoneme": "θ"}, {"phoneme": "k", "score": 0.9}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = HttpGopProvider(client=client, base_url="http://gop:8100")

    scores = await provider.score_phonemes(audio=b"WAV", target_text="thk")
    assert scores == [PhonemeScore(phoneme="k", score=0.9)]
    await client.aclose()
