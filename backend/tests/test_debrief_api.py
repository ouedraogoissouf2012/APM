import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.dependencies import get_debrief_rate_limiter, get_debrief_service
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
