"""The STT provider must be reused across requests, not rebuilt each time.

Rebuilding GroqSttProvider per /transcribe call opened a fresh connection pool
every turn — paying a TCP+TLS handshake (and a possible ~1 s cold DNS lookup) on
each transcription. Caching it (one keep-alive pool) roughly halved transcription
latency. These tests pin that the same config yields the same instance and that
"device" still means no server STT.
"""

from app.features.conversation.providers.stt import (
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
