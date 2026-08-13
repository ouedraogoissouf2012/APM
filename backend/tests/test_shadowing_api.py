"""Integration tests for the shadowing endpoints (/tts, /shadowing/*).

Default engines in tests: SHADOWING_ENGINE=fake, TTS_ENGINE=device, STT_ENGINE=device
(conftest). So /tts and /shadowing/attempt are 404 by default (no server TTS/STT);
tests that need them override the provider with a fake.
"""

import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.conversation.dependencies import get_tts_provider
from app.features.shadowing.coach import ShadowingCoach
from app.features.shadowing.dependencies import (
    get_shadowing_rate_limiter,
    get_shadowing_service_with_stt,
)
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


@pytest.mark.asyncio
async def test_generate_phrase_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (LLM-backed) endpoint — a denial-of-wallet."""
    token = await _register(client, email="phrase-ip@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_shadowing_rate_limiter] = lambda: limiter
    try:
        first = await client.post(
            "/shadowing/phrase", headers={**headers, "X-Forwarded-For": "1.1.1.1"}
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/shadowing/phrase", headers={**headers, "X-Forwarded-For": "2.2.2.2"}
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_shadowing_rate_limiter, None)


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
async def test_attempt_rejects_oversized_upload(client, monkeypatch):
    # #230: /shadowing/attempt previously read the whole upload with no size cap.
    from app.features.shadowing import router as shadowing_router

    monkeypatch.setattr(
        shadowing_router, "get_settings", lambda: _SettingsWithCap(max_upload_bytes=10)
    )
    token = await _register(client, email="attempt-big@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with("x")
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "The ship is sinking"},
            files={"audio": ("speech.webm", b"x" * 50, "audio/webm")},
        )
        assert resp.status_code == 413, resp.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)


class _SettingsWithCap:
    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        self.trust_proxy_headers = False
        self.max_request_body_bytes = 12 * 1024 * 1024


@pytest.mark.asyncio
async def test_attempt_rejects_oversized_target_text(client):
    # #328: target_text had no length bound — an oversized value would reach
    # the sync word-diff (target.split()), the GOP call, and the coaching LLM
    # prompt unbounded. Must 422 BEFORE any of that. A WORKING service is
    # installed (like the accepted-at-bound test below) so a passing request
    # would otherwise get a normal 200 — proving the 422 comes from the new
    # length check itself, not from the STT dependency being unconfigured
    # (get_shadowing_service_with_stt's own 404 for that resolves BEFORE the
    # route body runs at all, so an unguarded test here would 404 regardless
    # of whether the length check exists).
    from app.features.shadowing.schemas import MAX_TARGET_TEXT_CHARS

    token = await _register(client, email="attempt-longtext@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with("x")
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "x" * (MAX_TARGET_TEXT_CHARS + 1)},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)
    assert "target_text" in resp.text


@pytest.mark.asyncio
async def test_attempt_accepts_target_text_at_the_exact_bound(client):
    # Boundary check: exactly MAX_TARGET_TEXT_CHARS must still be accepted —
    # the fix must reject what's OVER the bound, not the bound itself.
    from app.features.shadowing.schemas import MAX_TARGET_TEXT_CHARS

    token = await _register(client, email="attempt-exact@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with("x")
    try:
        resp = await client.post(
            "/shadowing/attempt",
            headers=headers,
            data={"target_text": "x" * MAX_TARGET_TEXT_CHARS},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
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
async def test_coach_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (LLM-backed) endpoint — a denial-of-wallet."""
    token = await _register(client, email="coach-ip@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_shadowing_rate_limiter] = lambda: limiter
    try:
        first = await client.post(
            "/shadowing/coach",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json={"target_text": "hi", "missed_words": ["hi"]},
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/shadowing/coach",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json={"target_text": "hi", "missed_words": ["hi"]},
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_shadowing_rate_limiter, None)


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


@pytest.mark.asyncio
async def test_attempt_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (STT-backed) endpoint — a denial-of-wallet."""
    token = await _register(client, email="attempt-ip@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_shadowing_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_shadowing_service_with_stt] = _override_service_with("x")
    try:
        first = await client.post(
            "/shadowing/attempt",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            data={"target_text": "hi"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/shadowing/attempt",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            data={"target_text": "hi"},
            files={"audio": ("speech.webm", b"xxxx", "audio/webm")},
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_shadowing_service_with_stt, None)
        app.dependency_overrides.pop(get_shadowing_rate_limiter, None)


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


@pytest.mark.asyncio
async def test_tts_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (TTS-backed) endpoint — a denial-of-wallet."""
    token = await _register(client, email="tts-ip@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_shadowing_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_tts_provider] = lambda: _FakeTts()
    try:
        first = await client.post(
            "/tts",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json={"text": "hello"},
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/tts",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json={"text": "hello"},
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_tts_provider, None)
        app.dependency_overrides.pop(get_shadowing_rate_limiter, None)
