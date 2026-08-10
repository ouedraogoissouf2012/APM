"""Integration tests for idempotent turns (#127, offline replay safety)."""

import pytest
from sqlalchemy import select

from app.features.auth.models import User
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.idempotency.models import IdempotencyKey


async def _auth(client, email="idem@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _minutes_used(db_session, email):
    db_session.expire_all()  # see the request's committed writes, not a cached object
    user = await db_session.scalar(select(User).where(User.email == email))
    return user.minutes_used_today


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
    minutes_after_first = await _minutes_used(db_session, "idem@b.com")

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

    # ...and the quota (#119) was NOT charged again — the replay returned the
    # cached reply without re-running the metered turn work.
    assert await _minutes_used(db_session, "idem@b.com") == minutes_after_first


@pytest.mark.asyncio
async def test_replaying_a_stream_turn_with_the_same_key_is_idempotent(client, db_session):
    # #261: a SEQUENTIAL double-tour on the streaming endpoint (a network retry / an
    # offline replay) with the same Idempotency-Key must not duplicate the transcript
    # nor re-charge the quota — the second call replays the cached reply as a stream.
    # (Complements #256's per-session lock, which only stops CONCURRENT turns.)
    headers = await _auth(client, email="idemstream@b.com")
    session_id = await _start(client, headers)

    body = {"text": "I like sports."}
    key = {"Idempotency-Key": "stream-abc-123"}

    first = await client.post(
        f"/sessions/{session_id}/turn/stream", headers={**headers, **key}, json=body
    )
    assert first.status_code == 200, first.text
    assert "event: done" in first.text
    minutes_after_first = await _minutes_used(db_session, "idemstream@b.com")

    second = await client.post(
        f"/sessions/{session_id}/turn/stream", headers={**headers, **key}, json=body
    )
    assert second.status_code == 200, second.text
    assert "event: done" in second.text
    assert "You said: I like sports." in second.text  # cached reply replayed

    # The turn persisted ONLY ONCE (no duplicate user/assistant pair)...
    transcript = await SqlAlchemyTranscriptRepository(db_session).get_by_session(session_id)
    user_turns = [t for t in transcript.turns if t["role"] == "user"]
    assert len(user_turns) == 1
    # ...and the quota (#119) was NOT charged again.
    assert await _minutes_used(db_session, "idemstream@b.com") == minutes_after_first


@pytest.mark.asyncio
async def test_a_concurrent_stream_turn_with_a_live_key_claim_gets_409(client, db_session):
    # A retry that finds the SAME key still IN FLIGHT (a live claim) must get a 409
    # before the 200 stream is committed — never a second processed turn (#261).
    headers = await _auth(client, email="idemstream2@b.com")
    session_id = await _start(client, headers)
    user = await db_session.scalar(select(User).where(User.email == "idemstream2@b.com"))
    # Stand in for the concurrent winner: a fresh, still-pending claim on the key.
    db_session.add(IdempotencyKey(user_id=user.id, key="live-stream-key", response=None))
    await db_session.commit()

    resp = await client.post(
        f"/sessions/{session_id}/turn/stream",
        headers={**headers, "Idempotency-Key": "live-stream-key"},
        json={"text": "hi"},
    )
    assert resp.status_code == 409  # IN_FLIGHT -> retry; the turn is not re-processed

    # Nothing new was persisted under the live claim.
    transcript = await SqlAlchemyTranscriptRepository(db_session).get_by_session(session_id)
    assert transcript is None or all(t["content"] != "hi" for t in transcript.turns)


@pytest.mark.asyncio
async def test_a_stream_turn_key_is_released_when_validation_fails(client):
    # begin() claims the key BEFORE prepare_turn validates. If validation fails
    # (ended session -> 409), the claim must be RELEASED — otherwise the key would be
    # stuck as a phantom "in-flight" 409 for the whole stale window on any later use.
    headers = await _auth(client, email="idemstream3@b.com")
    ended_session = await _start(client, headers)
    await client.post(f"/sessions/{ended_session}/end", headers=headers)

    key = {"Idempotency-Key": "released-key"}
    rejected = await client.post(
        f"/sessions/{ended_session}/turn/stream", headers={**headers, **key}, json={"text": "hi"}
    )
    assert rejected.status_code == 409  # session ended -> validation fails after the claim

    # The claim was released: the SAME key now works on a fresh, valid session
    # (it is not stuck as a phantom in-flight claim).
    ok_session = await _start(client, headers)
    accepted = await client.post(
        f"/sessions/{ok_session}/turn/stream", headers={**headers, **key}, json={"text": "hi"}
    )
    assert accepted.status_code == 200, accepted.text
    assert "event: done" in accepted.text


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
