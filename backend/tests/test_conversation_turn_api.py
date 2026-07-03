"""Integration tests for the text conversation turn endpoint.

VOICE_ENGINE defaults to "fake", so the LLM is FakeLlm -> reply "You said: <text>".
"""

import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.auth.dependencies import get_conversation_rate_limiter
from app.main import app


async def _auth_header(client, email="conv@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
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
