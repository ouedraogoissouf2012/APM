"""Integration tests for voice consent (#128) + the /transcribe gate."""

import asyncio
import io
import wave

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.conversation.dependencies import get_stt_provider
from app.features.voice_consent.models import VoiceConsent
from app.features.voice_consent.repository import SqlAlchemyVoiceConsentRepository
from app.main import app


class _FakeStt:
    async def transcribe(self, audio: bytes) -> str:
        return "ok"


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "vc@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x01" * 1600)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_defaults_are_protective(client):
    headers = await _auth(client)
    resp = await client.get("/me/voice-consent", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcription"] is True
    assert body["scoring"] is False
    assert body["b2b_share"] is False
    assert body["model_training"] is False


@pytest.mark.asyncio
async def test_grant_and_revoke_persist(client):
    headers = await _auth(client)

    granted = await client.put("/me/voice-consent", headers=headers, json={"scoring": True})
    assert granted.json()["scoring"] is True
    # Other consents untouched.
    assert granted.json()["transcription"] is True

    revoked = await client.put("/me/voice-consent", headers=headers, json={"transcription": False})
    assert revoked.json()["transcription"] is False

    # Persisted across a fresh GET.
    again = await client.get("/me/voice-consent", headers=headers)
    assert again.json()["transcription"] is False
    assert again.json()["scoring"] is True


@pytest.mark.asyncio
async def test_transcribe_is_gated_by_consent(client):
    # Server STT is enabled here (fake provider) so the consent gate is what we
    # actually exercise, not the "server STT disabled" 404.
    app.dependency_overrides[get_stt_provider] = lambda: _FakeStt()
    try:
        headers = await _auth(client)

        # Default (transcription on): the endpoint accepts and transcribes.
        files = {"audio": ("speech.wav", _wav(), "audio/wav")}
        before = await client.post("/transcribe", headers=headers, files=files)
        assert before.status_code == 200, before.text

        # Revoke transcription consent -> the gate forbids it (403), no upload processed.
        await client.put("/me/voice-consent", headers=headers, json={"transcription": False})
        files = {"audio": ("speech.wav", _wav(), "audio/wav")}
        after = await client.post("/transcribe", headers=headers, files=files)
        assert after.status_code == 403, after.text
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)


@pytest.mark.asyncio
async def test_get_or_create_is_race_safe(client, _engine):
    """Two concurrent first-touches of a brand-new user's consent must not trip the
    unique(user_id) constraint. A get-then-create would double-INSERT and 500 one
    of them; the atomic ON CONFLICT DO NOTHING makes the loser a no-op, and exactly
    one row ends up present with the protective defaults."""
    headers = await _auth(client)
    user_id = (await client.get("/auth/me", headers=headers)).json()["id"]

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async def touch():
        async with maker() as session:
            return await SqlAlchemyVoiceConsentRepository(session).get_or_create(user_id)

    a, b = await asyncio.gather(touch(), touch())
    assert a.user_id == user_id and b.user_id == user_id
    assert a.transcription is True  # protective default applied by the DB

    async with maker() as session:
        count = await session.scalar(
            select(func.count()).select_from(VoiceConsent).where(VoiceConsent.user_id == user_id)
        )
    assert count == 1  # never a duplicate


@pytest.mark.asyncio
async def test_voice_consent_requires_auth(client):
    resp = await client.get("/me/voice-consent")
    assert resp.status_code == 401, resp.text
