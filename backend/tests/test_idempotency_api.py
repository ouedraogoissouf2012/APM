"""Integration tests for idempotent turns (#127, offline replay safety)."""

import pytest

from app.features.conversation.repository import SqlAlchemyTranscriptRepository


async def _auth(client):
    reg = await client.post(
        "/auth/register", json={"email": "idem@b.com", "password": "s3cret!pass"}
    )
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _start(client, headers):
    resp = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    return resp.json()["session_id"]


@pytest.mark.asyncio
async def test_replaying_a_turn_with_the_same_key_is_idempotent(client, db_session):
    headers = await _auth(client)
    session_id = await _start(client, headers)

    body = {"text": "I like sports."}
    key = {"Idempotency-Key": "turn-abc-123"}

    first = await client.post(f"/sessions/{session_id}/turn", headers={**headers, **key}, json=body)
    assert first.status_code == 200, first.text
    reply = first.json()["reply"]

    # Replay the SAME key (as an offline client reconnecting would).
    second = await client.post(
        f"/sessions/{session_id}/turn", headers={**headers, **key}, json=body
    )
    assert second.status_code == 200, second.text
    assert second.json()["reply"] == reply  # same result

    # The turn was persisted only ONCE (no duplicate user/assistant pair).
    transcript = await SqlAlchemyTranscriptRepository(db_session).get_by_session(session_id)
    user_turns = [t for t in transcript.turns if t["role"] == "user"]
    assert len(user_turns) == 1


@pytest.mark.asyncio
async def test_a_new_key_processes_a_new_turn(client, db_session):
    headers = await _auth(client)
    session_id = await _start(client, headers)

    await client.post(
        f"/sessions/{session_id}/turn",
        headers={**headers, "Idempotency-Key": "k1"},
        json={"text": "Hello."},
    )
    await client.post(
        f"/sessions/{session_id}/turn",
        headers={**headers, "Idempotency-Key": "k2"},
        json={"text": "How are you?"},
    )

    transcript = await SqlAlchemyTranscriptRepository(db_session).get_by_session(session_id)
    user_turns = [t for t in transcript.turns if t["role"] == "user"]
    assert len(user_turns) == 2  # two distinct keys -> two turns


@pytest.mark.asyncio
async def test_turn_without_a_key_still_works(client):
    headers = await _auth(client)
    session_id = await _start(client, headers)
    resp = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "Hi."})
    assert resp.status_code == 200, resp.text
