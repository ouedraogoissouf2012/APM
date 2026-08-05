"""GroqSttProvider must send the right decoding params to Whisper.

temperature=0 makes transcription deterministic (no sampling that invents an
unrelated word on an unclear non-native accent); the context prompt biases
decoding toward plausible everyday words. An empty prompt must be omitted, not
sent as "" (Whisper would treat a blank prompt as noise).
"""

import pytest

from app.features.conversation.providers.stt import GroqSttProvider


class _StubResult:
    def __init__(self) -> None:
        self.text = "hello there"
        self.words: list = []


class _StubTranscriptions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResult()


class _StubAudio:
    def __init__(self) -> None:
        self.transcriptions = _StubTranscriptions()


class _StubClient:
    def __init__(self) -> None:
        self.audio = _StubAudio()


def _provider_with_stub(prompt: str) -> tuple[GroqSttProvider, _StubClient]:
    provider = GroqSttProvider(api_key="k", base_url="u", model="m", prompt=prompt)
    stub = _StubClient()
    provider._client = stub  # type: ignore[attr-defined]
    return provider, stub


@pytest.mark.asyncio
async def test_transcribe_sends_temperature_zero_and_prompt():
    provider, stub = _provider_with_stub(prompt="French speaker practising English.")

    await provider.transcribe(b"audio")

    call = stub.audio.transcriptions.calls[0]
    assert call["temperature"] == 0
    assert call["prompt"] == "French speaker practising English."
    assert call["language"] == "en"


@pytest.mark.asyncio
async def test_empty_prompt_is_omitted_not_sent_blank():
    provider, stub = _provider_with_stub(prompt="")

    await provider.transcribe(b"audio")

    call = stub.audio.transcriptions.calls[0]
    assert call["temperature"] == 0
    assert "prompt" not in call  # blank prompt must not be sent


@pytest.mark.asyncio
async def test_verbose_transcribe_also_pins_params():
    provider, stub = _provider_with_stub(prompt="ctx")

    await provider.transcribe_verbose(b"audio")

    call = stub.audio.transcriptions.calls[0]
    assert call["temperature"] == 0
    assert call["prompt"] == "ctx"
    assert call["response_format"] == "verbose_json"
