"""Integration tests for POST /minimal-pairs/attempt.

Default engines in tests: SHADOWING_ENGINE=fake, STT_ENGINE=device (conftest),
so the endpoint is 404 by default (no server STT); tests that need it override
the service with a fake STT.
"""

import pytest

from app.features.conversation.providers.interfaces import TranscriptWord, VerboseTranscript
from app.features.minimal_pairs.coach import PairCoach
from app.features.minimal_pairs.dependencies import get_minimal_pairs_service
from app.features.minimal_pairs.service import MinimalPairsService
from app.main import app


async def _register(client, email="pair@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return resp.json()["access_token"]


class _FakeStt:
    def __init__(self, heard: str) -> None:
        self._heard = heard

    async def transcribe(self, audio: bytes) -> str:
        return self._heard

    async def transcribe_verbose(self, audio: bytes) -> VerboseTranscript:
        words = [TranscriptWord(w) for w in self._heard.split()]
        return VerboseTranscript(text=self._heard, words=words)


class _CoachLlm:
    async def complete(self, system_prompt, history):
        return '{"coaching": "Keep the vowel long in sheep."}'


def _override_with(heard: str):
    def _override():
        return MinimalPairsService(coach=PairCoach(_CoachLlm()), stt=_FakeStt(heard))

    return _override


async def _attempt(client, headers, *, target, other):
    return await client.post(
        "/minimal-pairs/attempt",
        headers=headers,
        data={"target": target, "other": other},
        files={"audio": ("speech.wav", b"xxxx", "audio/wav")},
    )


@pytest.mark.asyncio
async def test_said_target_is_correct_no_coaching(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("sheep")
    try:
        resp = await _attempt(client, headers, target="sheep", other="ship")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["said_target"] is True
        assert body["said_other"] is False
        assert body["coaching"] == ""  # correct -> no coaching
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)


@pytest.mark.asyncio
async def test_said_other_word_gets_coaching(client):
    token = await _register(client, email="pair2@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    # Asked for "sheep", said "ship" -> the classic confusion.
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("ship")
    try:
        resp = await _attempt(client, headers, target="sheep", other="ship")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["said_target"] is False
        assert body["said_other"] is True
        assert body["coaching"]  # confusion -> coaching present
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)


@pytest.mark.asyncio
async def test_attempt_requires_auth(client):
    resp = await _attempt(client, {}, target="sheep", other="ship")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_attempt_404_when_stt_disabled(client):
    # Default STT_ENGINE=device -> no server STT.
    token = await _register(client, email="pair3@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await _attempt(client, headers, target="sheep", other="ship")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_attempt_rejects_oversized_upload(client, monkeypatch):
    # #230: /minimal-pairs/attempt previously read the whole upload with no cap.
    from app.features.minimal_pairs import router as minimal_pairs_router

    monkeypatch.setattr(
        minimal_pairs_router, "get_settings", lambda: _SettingsWithCap(max_upload_bytes=10)
    )
    token = await _register(client, email="pair-big@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("sheep")
    try:
        resp = await client.post(
            "/minimal-pairs/attempt",
            headers=headers,
            data={"target": "sheep", "other": "ship"},
            files={"audio": ("speech.wav", b"x" * 50, "audio/wav")},
        )
        assert resp.status_code == 413, resp.text
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)


class _SettingsWithCap:
    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        self.trust_proxy_headers = False
        self.max_request_body_bytes = 12 * 1024 * 1024


@pytest.mark.asyncio
async def test_attempt_rejects_oversized_target(client):
    # #328: target/other had no length bound — an oversized value would reach
    # the sync word-normalize step and the coaching LLM prompt unbounded. A
    # WORKING service is installed (like the accepted-at-bound test below) so
    # a passing request would otherwise get a normal 200 — proving the 422
    # comes from the new length check, not from the STT dependency being
    # unconfigured (get_minimal_pairs_service's own 404 for that resolves
    # BEFORE the route body runs at all, so an unguarded test here would 404
    # regardless of whether the length check exists).
    from app.features.minimal_pairs.schemas import MAX_WORD_CHARS

    token = await _register(client, email="pair-longtarget@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("sheep")
    try:
        resp = await _attempt(client, headers, target="x" * (MAX_WORD_CHARS + 1), other="ship")
        assert resp.status_code == 422, resp.text
        assert "target" in resp.text
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)


@pytest.mark.asyncio
async def test_attempt_rejects_oversized_other(client):
    # Same bound, the OTHER field — proves the check isn't only wired for target.
    from app.features.minimal_pairs.schemas import MAX_WORD_CHARS

    token = await _register(client, email="pair-longother@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("sheep")
    try:
        resp = await _attempt(client, headers, target="sheep", other="x" * (MAX_WORD_CHARS + 1))
        assert resp.status_code == 422, resp.text
        assert "other" in resp.text
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)


@pytest.mark.asyncio
async def test_attempt_accepts_target_and_other_at_the_exact_bound(client):
    # Boundary check: exactly MAX_WORD_CHARS must still be accepted.
    from app.features.minimal_pairs.schemas import MAX_WORD_CHARS

    token = await _register(client, email="pair-exact@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_minimal_pairs_service] = _override_with("sheep")
    try:
        resp = await _attempt(
            client, headers, target="x" * MAX_WORD_CHARS, other="y" * MAX_WORD_CHARS
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_minimal_pairs_service, None)
