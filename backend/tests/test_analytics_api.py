"""Integration test: a completed debrief emits analytics events (#129)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.analytics.domain import EVENT_ACTIVATION, EVENT_SESSION_COMPLETED
from app.features.analytics.models import AnalyticsEventRow
from app.features.conversation.repository import SqlAlchemyTranscriptRepository


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "an@b.com", "password": "s3cret!pass"})
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}"}, me.json()["id"]


async def _complete_a_session(client, db_session, headers):
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id,
        [
            {"role": ROLE_USER, "content": "I like sports"},
            {"role": ROLE_ASSISTANT, "content": "Nice!"},
        ],
    )
    await client.post(f"/sessions/{session_id}/debrief", headers=headers)
    # End it so the next session can start (one active session per user).
    await client.post(f"/sessions/{session_id}/end", headers=headers)
    return session_id


async def _events(db_session, user_id, name):
    rows = await db_session.scalars(
        select(AnalyticsEventRow).where(
            AnalyticsEventRow.user_id == user_id, AnalyticsEventRow.name == name
        )
    )
    return list(rows)


@pytest.mark.asyncio
async def test_first_completed_session_emits_completion_and_activation(client, db_session):
    headers, user_id = await _auth(client)
    session_id = await _complete_a_session(client, db_session, headers)

    completions = await _events(db_session, user_id, EVENT_SESSION_COMPLETED)
    activations = await _events(db_session, user_id, EVENT_ACTIVATION)

    assert len(completions) == 1
    assert len(activations) == 1
    # Privacy: only structured metadata, no transcript content.
    assert set(completions[0].properties) == {"session_id", "cefr", "error_count"}
    assert completions[0].properties["session_id"] == session_id


@pytest.mark.asyncio
async def test_activation_is_emitted_once_across_sessions(client, db_session):
    headers, user_id = await _auth(client)
    await _complete_a_session(client, db_session, headers)
    await _complete_a_session(client, db_session, headers)

    completions = await _events(db_session, user_id, EVENT_SESSION_COMPLETED)
    activations = await _events(db_session, user_id, EVENT_ACTIVATION)

    assert len(completions) == 2
    assert len(activations) == 1  # activation only on the first


@pytest.mark.asyncio
async def test_activation_is_unique_per_user_at_the_db_level(client, db_session):
    # The count-based check cannot stop a CONCURRENT double-activation (#188); a
    # partial unique index does. A second activation row for the same user is
    # rejected, while other event types stay append-only.
    headers, user_id = await _auth(client)

    db_session.add(AnalyticsEventRow(name=EVENT_ACTIVATION, user_id=user_id, properties={}))
    await db_session.commit()

    db_session.add(AnalyticsEventRow(name=EVENT_ACTIVATION, user_id=user_id, properties={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    # A completion for the same user is NOT blocked — the guard is activation-only.
    db_session.add(AnalyticsEventRow(name=EVENT_SESSION_COMPLETED, user_id=user_id, properties={}))
    await db_session.commit()

    assert len(await _events(db_session, user_id, EVENT_ACTIVATION)) == 1
