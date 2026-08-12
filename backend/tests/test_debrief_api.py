import asyncio

import pytest
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import InMemoryRateLimiter
from app.database import get_db
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.dependencies import get_debrief_rate_limiter, get_debrief_service
from app.features.debrief.models import Debrief
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.debrief.service import DebriefService
from app.features.sessions.repository import SqlAlchemySessionRepository
from app.main import app


class _CannedLlm:
    async def complete(self, system_prompt, history):
        return (
            '{"cefr_estimate": "A2", "summary": "Nice work",'
            ' "errors": [{"original": "i is happy", "correction": "I am happy",'
            ' "rule": "Subject-verb agreement", "error_type": "grammar"}]}'
        )


async def _register(client, email="dbg@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_generate_and_get_debrief(client, db_session):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id, [{"role": "user", "content": "i is happy"}]
    )

    def _override():
        return DebriefService(
            sessions=SqlAlchemySessionRepository(db_session),
            transcripts=SqlAlchemyTranscriptRepository(db_session),
            debriefs=SqlAlchemyDebriefRepository(db_session),
            analyzer=DebriefAnalyzer(_CannedLlm()),
        )

    app.dependency_overrides[get_debrief_service] = _override
    try:
        created = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["cefr_estimate"] == "A2"
        assert body["errors"][0]["correction"] == "I am happy"

        fetched = await client.get(f"/sessions/{session_id}/debrief", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["summary"] == "Nice work"
    finally:
        app.dependency_overrides.pop(get_debrief_service, None)


@pytest.mark.asyncio
async def test_get_debrief_404_when_absent(client):
    token = await _register(client, email="dbg2@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    resp = await client.get(f"/sessions/{session_id}/debrief", headers=headers)
    assert resp.status_code == 404


class _UnparseableLlm:
    async def complete(self, system_prompt, history):
        return "Sorry, I cannot produce that."


@pytest.mark.asyncio
async def test_generate_returns_502_when_llm_output_unparseable(client, db_session):
    token = await _register(client, email="dbg3@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id, [{"role": "user", "content": "i is happy"}]
    )

    def _override():
        return DebriefService(
            sessions=SqlAlchemySessionRepository(db_session),
            transcripts=SqlAlchemyTranscriptRepository(db_session),
            debriefs=SqlAlchemyDebriefRepository(db_session),
            analyzer=DebriefAnalyzer(_UnparseableLlm()),
        )

    app.dependency_overrides[get_debrief_service] = _override
    try:
        resp = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
        assert resp.status_code == 502, resp.text
    finally:
        app.dependency_overrides.pop(get_debrief_service, None)


@pytest.mark.asyncio
async def test_generate_debrief_is_rate_limited_per_user(client, db_session):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_debrief_rate_limiter] = lambda: limiter
    token = await _register(client, email="limited-debrief@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id, [{"role": "user", "content": "i is happy"}]
    )

    def _override():
        return DebriefService(
            sessions=SqlAlchemySessionRepository(db_session),
            transcripts=SqlAlchemyTranscriptRepository(db_session),
            debriefs=SqlAlchemyDebriefRepository(db_session),
            analyzer=DebriefAnalyzer(_CannedLlm()),
        )

    app.dependency_overrides[get_debrief_service] = _override
    try:
        first = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
        assert first.status_code == 201, first.text
        blocked = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
        assert blocked.status_code == 429
    finally:
        app.dependency_overrides.pop(get_debrief_service, None)


class _CountingLlm:
    """Counts real analyses and adds a small delay so two concurrent requests
    are genuinely both in flight when they'd reach the analyzer — widening the
    race window instead of relying on luck to prove the lock, not the timing."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, system_prompt, history):
        self.calls += 1
        await asyncio.sleep(0.05)
        return '{"cefr_estimate": "A2", "summary": "Nice work", "errors": []}'


@pytest.mark.asyncio
async def test_concurrent_debrief_requests_run_the_analyzer_once(client, db_session):
    """#302: two concurrent POST /sessions/{id}/debrief for the SAME session must
    not both run the slow/costly LLM analysis, nor crash on debriefs.session_id's
    unique constraint. generate()'s session-row lock serialises them: the loser
    blocks until the winner's save() commits, then its own existence re-check sees
    the persisted debrief and returns it directly — the analyzer never runs a
    second time.

    The override below deliberately keeps `db: AsyncSession = Depends(get_db)` as
    its own parameter (rather than closing over the `db_session` fixture, as the
    other tests in this file do) so each concurrent request gets its own
    request-scoped session/connection through the test's overridden get_db —
    mirroring production, where two real concurrent requests never share a
    session. Reusing one AsyncSession across two concurrent coroutines would
    both misrepresent production and be unsafe on its own (AsyncSession does not
    support concurrent use)."""
    token = await _register(client, email="concurrent-debrief@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id, [{"role": "user", "content": "i is happy"}]
    )
    await db_session.commit()

    llm = _CountingLlm()

    def _override(db: AsyncSession = Depends(get_db)) -> DebriefService:
        return DebriefService(
            sessions=SqlAlchemySessionRepository(db),
            transcripts=SqlAlchemyTranscriptRepository(db),
            debriefs=SqlAlchemyDebriefRepository(db),
            analyzer=DebriefAnalyzer(llm),
        )

    app.dependency_overrides[get_debrief_service] = _override
    try:
        responses = await asyncio.gather(
            client.post(f"/sessions/{session_id}/debrief", headers=headers),
            client.post(f"/sessions/{session_id}/debrief", headers=headers),
        )
    finally:
        app.dependency_overrides.pop(get_debrief_service, None)

    for r in responses:
        assert r.status_code == 201, r.text  # neither request 500s
    bodies = [r.json() for r in responses]
    assert bodies[0]["summary"] == bodies[1]["summary"] == "Nice work"
    assert llm.calls == 1  # only the winner ran the (slow, costly) analysis

    db_session.expire_all()
    count = await db_session.scalar(
        select(func.count()).select_from(Debrief).where(Debrief.session_id == session_id)
    )
    assert count == 1  # no duplicate row, no IntegrityError


@pytest.mark.asyncio
async def test_cannot_read_another_users_debrief(client):
    # User A starts a session.
    token_a = await _register(client, email="owner@b.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    start = await client.post("/sessions/start", headers=headers_a, json={"mode": "free"})
    session_id = start.json()["session_id"]

    # User B must not be able to read A's session debrief.
    token_b = await _register(client, email="intruder@b.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    resp = await client.get(f"/sessions/{session_id}/debrief", headers=headers_b)
    assert resp.status_code == 404  # ownership enforced, existence not leaked
