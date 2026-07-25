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
async def test_transcribe_requires_auth(client):
    resp = await client.post(
        "/transcribe", files={"audio": ("speech.webm", b"x", "audio/webm")}
    )
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
