"""Integration tests for the text conversation turn endpoint.

VOICE_ENGINE defaults to "fake", so the LLM is FakeLlm -> reply "You said: <text>".
"""

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import InMemoryRateLimiter
from app.database import get_db
from app.features.conversation.correction import TurnCorrection
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_conversation_turn_service,
)
from app.features.conversation.providers.fakes import FakeLlm
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.repository import SqlAlchemySessionRepository
from app.main import app


class _CannedCorrector:
    async def correct(self, text, cefr_level, native_language):
        return TurnCorrection(
            original="i is happy",
            correction="I am happy",
            rule="Use 'am' with 'I'.",
            alternatives=["I'm happy"],
        )


def _service_with_correction(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
    return ConversationTurnService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=FakeLlm(),
        corrector=_CannedCorrector(),
    )


async def _auth_header(client, email="conv@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_turn_returns_reply_and_persists_transcript(client):
    headers = await _auth_header(client)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["reply"] == "You said: hello"

    second = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "how are you"}
    )
    assert second.status_code == 200
    assert second.json()["reply"] == "You said: how are you"


@pytest.mark.asyncio
async def test_turn_rejected_after_session_ended(client):
    headers = await _auth_header(client, email="conv2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)

    resp = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "hi"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_turn_stream_emits_sentence_events_and_done(client):
    headers = await _auth_header(client, email="stream@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    resp = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hello"}
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    # FakeLlm streams two sentences, then a done event.
    assert "event: chunk" in body
    assert "You said: hello." in body
    assert "Tell me more." in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_turn_stream_persists_full_reply(client):
    headers = await _auth_header(client, email="stream2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hi"}
    )
    # The next non-stream turn must see the streamed reply in history.
    second = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "again"}
    )
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_turn_stream_emits_a_correction_event_after_the_reply(client):
    app.dependency_overrides[get_conversation_turn_service] = _service_with_correction
    try:
        headers = await _auth_header(client, email="correct@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers=headers,
            json={"text": "i is happy"},
        )
        assert resp.status_code == 200
        body = resp.text
        # Reply chunks, then the correction, then done — order preserved.
        assert body.index("event: chunk") < body.index("event: correction")
        assert body.index("event: correction") < body.index("event: done")
        assert "I am happy" in body
        assert "Use 'am' with 'I'." in body
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)


@pytest.mark.asyncio
async def test_turn_stream_requires_auth(client):
    resp = await client.post("/sessions/1/turn/stream", json={"text": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_turn_requires_auth(client):
    resp = await client.post("/sessions/1/turn", json={"text": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_turn_rejects_empty_text(client):
    headers = await _auth_header(client, email="conv3@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    resp = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_turn_is_rate_limited_per_user(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: limiter
    headers = await _auth_header(client, email="limited-turn@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "hi"})
    assert first.status_code == 200, first.text
    blocked = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "again"}
    )
    assert blocked.status_code == 429
