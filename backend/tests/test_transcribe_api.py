"""Integration tests for the /transcribe endpoint (server-side STT)."""

import pytest

from app.features.conversation.dependencies import get_stt_provider
from app.main import app


class _FakeStt:
    async def transcribe(self, audio: bytes) -> str:
        return f"heard {len(audio)} bytes"


async def _auth_header(client, email="stt@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_transcribe_returns_text_from_the_stt_provider(client):
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth_header(client)
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("speech.webm", b"xxxxx", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "heard 5 bytes"
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


@pytest.mark.asyncio
async def test_transcribe_empty_audio_returns_empty_text(client):
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth_header(client, email="stt2@b.com")
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("speech.webm", b"", "audio/webm")},
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == ""
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


@pytest.mark.asyncio
async def test_transcribe_rejects_oversized_upload(client, monkeypatch):
    # #120: an upload larger than max_upload_bytes is rejected with 413 (payload
    # too large) rather than read wholesale into memory.
    from app.features.conversation import stt_router

    monkeypatch.setattr(stt_router, "get_settings", lambda: _SettingsWithCap(max_upload_bytes=10))
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth_header(client, email="big@b.com")
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("speech.webm", b"x" * 50, "audio/webm")},
        )
        assert resp.status_code == 413, resp.text
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


class _SettingsWithCap:
    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        self.trust_proxy_headers = False


@pytest.mark.asyncio
async def test_transcribe_handles_a_large_clip_without_413(client):
    # #227: a ~1.3 MB clip (a long turn) is well under max_upload_bytes (10 MB), so
    # it is transcribed normally — and read fully in memory, never spooled to disk
    # (see tests/unit/test_stt_in_memory_upload.py for the no-disk guarantee).
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth_header(client, email="bigclip@b.com")
        big = b"x" * 1_300_000
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("speech.wav", big, "audio/wav")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == f"heard {len(big)} bytes"
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


@pytest.mark.asyncio
async def test_transcribe_missing_audio_part_returns_422(client):
    # A multipart body without the expected 'audio' file part is a client error.
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth_header(client, email="noaudio@b.com")
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"other": ("note.txt", b"not audio", "text/plain")},
        )
        assert resp.status_code == 422, resp.text
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


@pytest.mark.asyncio
async def test_transcribe_requires_auth(client):
    resp = await client.post("/transcribe", files={"audio": ("speech.webm", b"x", "audio/webm")})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_transcribe_404_when_server_stt_disabled(client):
    # Default STT_ENGINE=device -> no server provider -> endpoint is disabled.
    headers = await _auth_header(client, email="stt3@b.com")
    resp = await client.post(
        "/transcribe",
        headers=headers,
        files={"audio": ("speech.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404
