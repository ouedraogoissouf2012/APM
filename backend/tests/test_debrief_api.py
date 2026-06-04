import pytest

from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.dependencies import get_debrief_service
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
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
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
