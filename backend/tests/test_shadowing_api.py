"""Integration tests for the shadowing endpoints (/tts, /shadowing/*).

Default engines in tests: SHADOWING_ENGINE=fake, TTS_ENGINE=device, STT_ENGINE=device
(conftest). So /tts and /shadowing/attempt are 404 by default (no server TTS/STT);
tests that need them override the provider with a fake.
"""

import pytest

from app.features.conversation.dependencies import get_tts_provider
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.dependencies import get_shadowing_service_with_stt
from app.features.shadowing.generator import PhraseGenerator
from app.features.shadowing.service import ShadowingService
from app.main import app


async def _register(client, email="shadow@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return resp.json()["access_token"]


class _FakeStt:
    def __init__(self, transcript: str, prob: float = 0.9) -> None:
        self._transcript = transcript
        self._prob = prob

    async def transcribe(self, audio: bytes) -> str:
        return self._transcript

    async def transcribe_verbose(self, audio: bytes):
        from app.features.conversation.providers.interfaces import (
            TranscriptWord,
            VerboseTranscript,
        )

        words = [TranscriptWord(w, self._prob) for w in self._transcript.split()]
        return VerboseTranscript(text=self._transcript, words=words)


class _FakeTts:
    async def synthesize(self, text: str) -> bytes:
        return b"ID3fake-mp3-bytes"


class _CoachLlm:
    async def complete(self, system_prompt, history):
        if "coach" in system_prompt.lower():
            return '{"coaching": "Say ship with a short i."}'
        return '{"text": "The ship is sinking", "focus": "ship_sheep", "tip": "short i"}'


# ---- /shadowing/phrase ------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_phrase_returns_a_target(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/shadowing/phrase", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["text"]  # fake engine gives a usable phrase
    assert body["focus"]


@pytest.mark.asyncio
async def test_generate_phrase_requires_auth(client):
    resp = await client.post("/shadowing/phrase")
    assert resp.status_code == 401


# ---- /shadowing/attempt -----------------------------------------------------


def _override_service_with(stt_transcript: str, pronunciation=None):
    def _override():
        llm = _CoachLlm()
        return ShadowingService(
            generator=PhraseGenerator(llm),
            coach=ShadowingCoach(llm),
            stt=_FakeStt(stt_transcript),
            pronunciation=pronunciation,
        )

    return _override


@pytest.mark.asyncio
async def test_attempt_flags_missed_words_without_blocking_on_coaching(client):
    token = await _register(client, email="attempt@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    # The recognizer heard "sheep" instead of "ship" -> "ship" missed.
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with(
        "the sheep is sinking"
    )
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "The ship is sinking"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["missed_words"] == ["ship"]
        # Responsiveness: the attempt returns fast and does NOT wait on the coaching
        # LLM — coaching is empty here, fetched separately via /shadowing/coach.
        assert body["coaching"] == ""
        assert body["transcript"] == "the sheep is sinking"
        # Pronunciation scores (#111): the missed word scores 0, a heard word scores high.
        by_word = {w["target"]: w for w in body["words"]}
        assert by_word["ship"]["score"] == 0.0
        assert by_word["The"]["score"] is not None and by_word["The"]["score"] > 0.5
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)


@pytest.mark.asyncio
async def test_coach_endpoint_returns_advice_for_missed_words(client):
    token = await _register(client, email="coach@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/shadowing/coach",
        headers=headers,
        json={"target_text": "The ship is sinking", "missed_words": ["ship"]},
    )
    assert resp.status_code == 200, resp.text
    # Fake shadowing LLM returns coaching for missed words.
    assert resp.json()["coaching"]


@pytest.mark.asyncio
async def test_coach_endpoint_requires_auth(client):
    resp = await client.post(
        "/shadowing/coach",
        json={"target_text": "hi", "missed_words": ["hi"]},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_attempt_perfect_has_no_misses_and_no_coaching(client):
    token = await _register(client, email="perfect@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with(
        "the ship is sinking"
    )
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "The ship is sinking"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["missed_words"] == []
        assert body["coaching"] == ""  # nothing missed -> no coaching
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)


@pytest.mark.asyncio
async def test_attempt_surfaces_phoneme_scores_when_gop_engine_wired(client):
    from app.features.pronunciation.domain import PhonemeScore

    class _StubPron:
        async def score_phonemes(self, audio, target_text):
            return [PhonemeScore(phoneme="θ", score=0.08), PhonemeScore(phoneme="k", score=0.9)]

    token = await _register(client, email="gop@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with(
        "think", pronunciation=_StubPron()
    )
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "think"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        phonemes = resp.json()["phonemes"]
        assert phonemes == [
            {"phoneme": "θ", "score": 0.08},
            {"phoneme": "k", "score": 0.9},
        ]
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)


@pytest.mark.asyncio
async def test_attempt_has_empty_phonemes_by_default(client):
    # No pronunciation provider wired -> phonemes is an empty list, not absent.
    token = await _register(client, email="nogop@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with(
        "the ship is sinking"
    )
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "The ship is sinking"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["phonemes"] == []
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)


@pytest.mark.asyncio
async def test_attempt_requires_auth(client):
    resp = await client.post(
        "/shadowing/attempt",
        data={"target_text": "hi"},
        files={"audio": ("speech.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_attempt_404_when_stt_disabled(client):
    # Default STT_ENGINE=device -> no server STT -> the whole service dep 404s.
    token = await _register(client, email="nostt@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/shadowing/attempt",
        headers=headers,
        data={"target_text": "hi"},
        files={"audio": ("speech.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404, resp.text


# ---- /tts -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tts_404_when_tts_disabled(client):
    # Default TTS_ENGINE=device -> no server TTS.
    token = await _register(client, email="notts@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/tts", headers=headers, json={"text": "hello"})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_tts_returns_base64_audio_when_enabled(client):
    token = await _register(client, email="tts@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_tts_provider] = lambda: _FakeTts()
    try:
        resp = await client.post("/tts", headers=headers, json={"text": "The ship is sinking"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mime"] == "audio/mpeg"
        assert body["audio"]  # base64 payload
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)


@pytest.mark.asyncio
async def test_tts_rejects_empty_text(client):
    token = await _register(client, email="empty@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_tts_provider] = lambda: _FakeTts()
    try:
        resp = await client.post("/tts", headers=headers, json={"text": ""})
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)
