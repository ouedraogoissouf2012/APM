"""Integration tests for voice-data export & erasure (#128)."""

import pytest

from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.domain import VocabularyWord
from app.features.vocabulary.repository import SqlAlchemyVocabularyRepository
from app.features.vocabulary.service import VocabularyService


async def _auth(client, email="vd@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}"}, me.json()["id"]


async def _seed_voice_data(client, db_session, headers, user_id):
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id,
        [
            {"role": ROLE_USER, "content": "I like sports"},
            {"role": ROLE_ASSISTANT, "content": "Nice!"},
        ],
    )
    await VocabularyService(SqlAlchemyVocabularyRepository(db_session)).capture(
        user_id, session_id, [VocabularyWord(word="deployment", translation="déploiement")]
    )
    return session_id


@pytest.mark.asyncio
async def test_export_returns_utterances_and_vocabulary(client, db_session):
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    resp = await client.post("/me/voice-data/export", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["raw_audio_retained"] is False  # honest: never stored
    # Only the learner's own turns are exported (not the assistant's).
    texts = [u["text"] for u in body["utterances"]]
    assert "I like sports" in texts
    assert "Nice!" not in texts
    assert body["vocabulary"][0]["word"] == "deployment"


@pytest.mark.asyncio
async def test_erase_deletes_the_voice_data_and_reports_counts(client, db_session):
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    erased = await client.delete("/me/voice-data", headers=headers)
    assert erased.status_code == 200, erased.text
    deleted = erased.json()["deleted"]
    assert deleted["transcripts"] >= 1
    assert deleted["vocabulary"] >= 1

    # A follow-up export is now empty.
    again = await client.post("/me/voice-data/export", headers=headers)
    assert again.json()["utterances"] == []
    assert again.json()["vocabulary"] == []


@pytest.mark.asyncio
async def test_erase_only_touches_the_callers_data(client, db_session):
    headers_a, user_a = await _auth(client, email="vd-a@b.com")
    await _seed_voice_data(client, db_session, headers_a, user_a)

    headers_b, user_b = await _auth(client, email="vd-b@b.com")
    await _seed_voice_data(client, db_session, headers_b, user_b)

    # B erases -> A's data survives.
    await client.delete("/me/voice-data", headers=headers_b)
    a_export = await client.post("/me/voice-data/export", headers=headers_a)
    assert len(a_export.json()["utterances"]) >= 1


@pytest.mark.asyncio
async def test_voice_data_requires_auth(client):
    assert (await client.post("/me/voice-data/export")).status_code == 401
    assert (await client.delete("/me/voice-data")).status_code == 401
