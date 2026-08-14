"""#399: the DB connection must NOT be held across the external LLM/TTS/STT I/O on
the hot conversation paths. These are the load-bearing proofs:

1. pool.checkedout() drops to 0 DURING the LLM call on /turn and /turn/stream, and
   during the STT call on /transcribe (mirrors the export proof, #389) — even though
   get_current_user opened a transaction that checked a connection out.
2. the per-session turn lock (#256) still serialises concurrent turns despite the
   connection being released mid-turn — the release must not defeat the lock.

They run against the REAL wiring (get_conversation_turn_service / the /transcribe
route), swapping only the external provider for a probe, so the release + fresh-scope
+ fresh-idempotency paths under test are exactly the production ones.
"""

import asyncio

import pytest
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.conversation.dependencies import (
    _fresh_turn_persistence_factory,
    _release_request_connection,
    get_conversation_turn_service,
    get_stt_provider,
)
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.repository import SqlAlchemySessionRepository
from app.main import app


async def _auth_header(client, email):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


class _PoolProbingLlm:
    """A conversation LLM that records the pool checkout count AT THE MOMENT it runs
    — i.e. while the "external I/O" is in flight. If the request connection was
    released at the boundary, this observes 0 checked-out connections."""

    def __init__(self, engine, observed: list[int]) -> None:
        self._engine = engine
        self._observed = observed

    async def complete(self, system_prompt, history):
        self._observed.append(self._engine.pool.checkedout())
        return "Probed reply."

    async def stream_complete(self, system_prompt, history):
        self._observed.append(self._engine.pool.checkedout())
        for sentence in ("Probed reply.", "Second sentence."):
            yield sentence


def _real_service_with_llm(db: AsyncSession, llm) -> ConversationTurnService:
    """Build the turn service with the SAME release + fresh-scope wiring as
    production (dependencies.get_conversation_turn_service), swapping only the LLM.
    So the connection-release path exercised here is the real one."""
    return ConversationTurnService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=llm,
        io_boundary=_release_request_connection(db),
        persistence=_fresh_turn_persistence_factory(db),
    )


@pytest.mark.asyncio
async def test_take_turn_releases_connection_during_llm(client, _engine):
    # #399: the pool connection get_current_user checked out is handed back BEFORE
    # the LLM runs, so a concurrent request could use it. Proven by observing 0
    # checked-out connections at the instant the LLM is called.
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
        return _real_service_with_llm(db, _PoolProbingLlm(_engine, observed))

    app.dependency_overrides[get_conversation_turn_service] = _override
    try:
        headers = await _auth_header(client, email="release-turn@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)

    assert observed == [0], f"connection held during LLM (checkedout={observed})"


@pytest.mark.asyncio
async def test_stream_turn_releases_connection_during_llm(client, _engine):
    # #399, streaming path: same guarantee. The SSE turn holds no pool connection
    # across the streamed LLM + per-sentence TTS.
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
        return _real_service_with_llm(db, _PoolProbingLlm(_engine, observed))

    app.dependency_overrides[get_conversation_turn_service] = _override
    try:
        headers = await _auth_header(client, email="release-stream@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hello"}
        )
        assert resp.status_code == 200, resp.text
        assert "event: done" in resp.text  # the whole stream completed on fresh sessions
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)

    assert observed == [0], f"connection held during streamed LLM (checkedout={observed})"


class _PoolProbingStt:
    """An STT provider that records the pool checkout count while it 'transcribes'."""

    def __init__(self, engine, observed: list[int]) -> None:
        self._engine = engine
        self._observed = observed

    async def transcribe(self, data: bytes) -> str:
        self._observed.append(self._engine.pool.checkedout())
        return "probed transcript"


@pytest.mark.asyncio
async def test_transcribe_releases_connection_during_stt(client, _engine):
    # #399: /transcribe holds the auth+consent connection across the Groq STT call.
    # After the fix it is released first, so the pool is free during transcription.
    observed: list[int] = []
    app.dependency_overrides[get_stt_provider] = lambda: _PoolProbingStt(_engine, observed)
    try:
        headers = await _auth_header(client, email="release-stt@b.com")
        # Grant transcription consent so the STT path is reached.
        await client.put("/me/voice-consent", headers=headers, json={"transcription": True})
        resp = await client.post(
            "/transcribe",
            headers=headers,
            files={"audio": ("clip.webm", b"not-really-audio", "audio/webm")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["text"] == "probed transcript"
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)

    assert observed == [0], f"connection held during STT (checkedout={observed})"


@pytest.mark.asyncio
async def test_turn_lock_is_released_on_client_disconnect_via_fresh_session(client, _engine):
    # #399 edge: the turn lock is freed in the SSE generator's `finally`, which also
    # runs on client disconnect (GeneratorExit). That release now uses a FRESH
    # session (the request one was detached at the LLM boundary). Prove it still
    # frees the lock when the consumer stops early, so the session isn't wedged.
    observed: list[int] = []

    def _override(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
        return _real_service_with_llm(db, _PoolProbingLlm(_engine, observed))

    app.dependency_overrides[get_conversation_turn_service] = _override
    try:
        headers = await _auth_header(client, email="disconnect@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        # Open the stream and abandon it after the first byte — the generator is
        # closed (GeneratorExit), running the `finally` that frees the lock.
        async with client.stream(
            "POST", f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "one"}
        ) as resp:
            assert resp.status_code == 200
            async for _chunk in resp.aiter_bytes():
                break  # abandon early -> GeneratorExit in event_stream

        # If the lock leaked, this next turn would 409. It succeeds -> the fresh-
        # session release in `finally` worked despite the disconnect.
        second = await client.post(
            f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "two"}
        )
        assert second.status_code == 200, second.text
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)


class _GatedStreamingLlm:
    """A streaming LLM whose first sentence blocks on an event, so a turn can be
    held 'mid-stream' while a second concurrent turn is attempted — to prove the
    per-session lock still serialises turns even though the connection was released."""

    def __init__(self, gate: asyncio.Event, started: asyncio.Event) -> None:
        self._gate = gate
        self._started = started

    async def stream_complete(self, system_prompt, history):
        self._started.set()  # signal: turn 1 is now mid-stream, connection released
        await self._gate.wait()  # hold here until the test releases it
        yield "Held reply."

    async def complete(self, system_prompt, history):  # pragma: no cover - unused
        return "Held reply."


@pytest.mark.asyncio
async def test_concurrent_turns_stay_serialised_despite_connection_release(client, _engine):
    # #256 must still hold after #399: releasing the connection mid-turn must NOT
    # defeat the per-session turn lock. Turn 1 is parked mid-stream (connection
    # already released); a concurrent Turn 2 for the same session must be refused
    # 409, not allowed to read the same base transcript and double-charge.
    gate = asyncio.Event()
    started = asyncio.Event()

    def _override(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
        return _real_service_with_llm(db, _GatedStreamingLlm(gate, started))

    app.dependency_overrides[get_conversation_turn_service] = _override
    try:
        headers = await _auth_header(client, email="serialise@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        async def _turn_one() -> int:
            resp = await client.post(
                f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "one"}
            )
            return resp.status_code

        task_one = asyncio.ensure_future(_turn_one())
        await asyncio.wait_for(started.wait(), timeout=5)  # turn 1 is mid-stream

        # The connection has been released by now — prove it, so this test also
        # guards that the lock does NOT depend on a held connection.
        assert _engine.pool.checkedout() == 0

        # Turn 2 for the SAME session, while turn 1 still holds the lock -> 409.
        blocked = await client.post(
            f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "two"}
        )
        assert blocked.status_code == 409, blocked.text

        gate.set()  # let turn 1 finish
        assert await asyncio.wait_for(task_one, timeout=5) == 200

        # Once turn 1 released the lock, a following turn is accepted again.
        gate2 = asyncio.Event()
        gate2.set()
        third = await client.post(
            f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "three"}
        )
        assert third.status_code == 200, third.text
    finally:
        gate.set()
        app.dependency_overrides.pop(get_conversation_turn_service, None)
