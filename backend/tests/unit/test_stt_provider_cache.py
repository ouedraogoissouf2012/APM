"""The STT provider must be reused across requests, not rebuilt each time.

Rebuilding GroqSttProvider per /transcribe call opened a fresh connection pool
every turn — paying a TCP+TLS handshake (and a possible ~1 s cold DNS lookup) on
each transcription. Caching it (one keep-alive pool) roughly halved transcription
latency. These tests pin that the same config yields the same instance and that
"device" still means no server STT.
"""

from app.features.conversation.providers.stt import (
    _STT_MAX_RETRIES,
    _STT_TIMEOUT_SECONDS,
    GroqSttProvider,
    build_stt_provider,
    shared_stt_provider,
)


def test_device_engine_has_no_server_provider():
    assert build_stt_provider("device", "", "", "") is None


def test_shared_provider_reuses_the_same_instance_for_one_config():
    a = shared_stt_provider(
        engine="groq", api_key="k", base_url="https://api.groq.com", model="whisper"
    )
    b = shared_stt_provider(
        engine="groq", api_key="k", base_url="https://api.groq.com", model="whisper"
    )
    assert isinstance(a, GroqSttProvider)
    assert a is b  # cached: one connection pool reused across turns


def test_shared_provider_distinguishes_configs():
    a = shared_stt_provider(engine="groq", api_key="k1", base_url="u", model="m")
    b = shared_stt_provider(engine="groq", api_key="k2", base_url="u", model="m")
    assert a is not b  # a different key is a different client


def test_client_has_a_bounded_timeout_and_no_default_600s_hang(monkeypatch):
    # #230: without an explicit timeout/max_retries, the openai SDK's defaults
    # apply (~600s connect timeout, up to 2 silent retries) on the critical path
    # the learner is waiting on for a reply.
    calls: list[dict] = []

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    GroqSttProvider(api_key="k", base_url="u", model="m")

    assert calls[0]["timeout"] == _STT_TIMEOUT_SECONDS
    assert calls[0]["max_retries"] == _STT_MAX_RETRIES
    assert _STT_TIMEOUT_SECONDS < 60  # meaningfully bounded, not just "set to something"


def test_client_timeout_and_retries_are_overridable(monkeypatch):
    calls: list[dict] = []

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    GroqSttProvider(api_key="k", base_url="u", model="m", timeout_seconds=5.0, max_retries=0)

    assert calls[0]["timeout"] == 5.0
    assert calls[0]["max_retries"] == 0
