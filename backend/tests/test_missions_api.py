"""Integration tests for the missions endpoints and the mission->conversation
wiring. The default fake mission engine is active (conftest), so no network."""

import pytest

from app.core.rate_limit import InMemoryRateLimiter
from app.features.missions.compiler import MissionCompiler
from app.features.missions.dependencies import (
    get_mission_rate_limiter,
    get_mission_service,
)
from app.features.missions.repository import SqlAlchemyMissionRepository
from app.features.missions.service import MissionService
from app.main import app


async def _register(client, email="mission@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_mission_returns_a_compiled_brief(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/missions",
        headers=headers,
        json={"source_type": "offer", "content": "Backend engineer role at Acme"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["persona"]  # the fake engine returns a generic but valid brief
    assert body["goal"]
    assert isinstance(body["likely_questions"], list)
    # The internal system prompt must never leak to the client.
    assert "system_prompt" not in body


@pytest.mark.asyncio
async def test_create_mission_requires_auth(client):
    resp = await client.post("/missions", json={"source_type": "offer", "content": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_mission_rejects_unknown_source_type(client):
    token = await _register(client, email="m2@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/missions", headers=headers, json={"source_type": "nonsense", "content": "x"}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_mission_rejects_empty_content(client):
    token = await _register(client, email="m3@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/missions", headers=headers, json={"source_type": "offer", "content": ""}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_get_mission_is_isolated_between_users(client):
    token_a = await _register(client, email="owner@b.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    created = await client.post(
        "/missions", headers=headers_a, json={"source_type": "offer", "content": "offer"}
    )
    mission_id = created.json()["id"]

    token_b = await _register(client, email="intruder@b.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    resp = await client.get(f"/missions/{mission_id}", headers=headers_b)
    assert resp.status_code == 404, resp.text  # never reveals another user's mission


@pytest.mark.asyncio
async def test_create_mission_is_rate_limited(client):
    token = await _register(client, email="rl@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    # One shared limiter instance so the hit count accumulates across requests
    # (a fresh limiter per call would never trip).
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_mission_rate_limiter] = lambda: limiter
    try:
        first = await client.post(
            "/missions", headers=headers, json={"source_type": "offer", "content": "a"}
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            "/missions", headers=headers, json={"source_type": "offer", "content": "b"}
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_mission_rate_limiter, None)


@pytest.mark.asyncio
async def test_create_mission_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (LLM-compiled) endpoint — a denial-of-wallet."""
    token = await _register(client, email="rl-ip@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_mission_rate_limiter] = lambda: limiter
    try:
        first = await client.post(
            "/missions",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json={"source_type": "offer", "content": "a"},
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            "/missions",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json={"source_type": "offer", "content": "b"},
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_mission_rate_limiter, None)


class _BrokenLlm:
    async def complete(self, system_prompt, history):
        return "sorry, I cannot help"  # non-JSON -> compile error


@pytest.mark.asyncio
async def test_create_mission_maps_compile_failure_to_502(client, db_session):
    token = await _register(client, email="broken@b.com")
    headers = {"Authorization": f"Bearer {token}"}

    def _override():
        return MissionService(
            missions=SqlAlchemyMissionRepository(db_session),
            compiler=MissionCompiler(_BrokenLlm()),
        )

    app.dependency_overrides[get_mission_service] = _override
    try:
        resp = await client.post(
            "/missions", headers=headers, json={"source_type": "offer", "content": "x"}
        )
        assert resp.status_code == 502, resp.text
    finally:
        app.dependency_overrides.pop(get_mission_service, None)


# --- mission -> conversation wiring -------------------------------------------


@pytest.mark.asyncio
async def test_start_session_with_mission_persists_mission_id(client):
    token = await _register(client, email="run@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(
        "/missions", headers=headers, json={"source_type": "offer", "content": "offer"}
    )
    mission_id = created.json()["id"]

    started = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "mission", "mission_id": mission_id},
    )
    assert started.status_code == 201, started.text


@pytest.mark.asyncio
async def test_start_mission_session_requires_a_mission_id(client):
    token = await _register(client, email="nomission@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/sessions/start", headers=headers, json={"mode": "mission"})
    assert resp.status_code == 422, resp.text  # schema: mission_id required for mission mode


@pytest.mark.asyncio
async def test_start_session_rejects_another_users_mission(client):
    token_a = await _register(client, email="owns@b.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    created = await client.post(
        "/missions", headers=headers_a, json={"source_type": "offer", "content": "offer"}
    )
    mission_id = created.json()["id"]

    token_b = await _register(client, email="thief@b.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    resp = await client.post(
        "/sessions/start",
        headers=headers_b,
        json={"mode": "mission", "mission_id": mission_id},
    )
    assert resp.status_code == 404, resp.text  # ownership re-checked server-side


@pytest.mark.asyncio
async def test_free_session_rejects_a_mission_id(client):
    token = await _register(client, email="freemode@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/sessions/start", headers=headers, json={"mode": "free", "mission_id": 1}
    )
    assert resp.status_code == 422, resp.text  # mission_id only allowed in mission mode


class _SpyLlm:
    """Records the system prompt it was driven with (and streams one sentence)."""

    def __init__(self) -> None:
        self.seen_system_prompt: str | None = None

    async def complete(self, system_prompt, history):
        self.seen_system_prompt = system_prompt
        return "ok"

    async def stream_complete(self, system_prompt, history):
        self.seen_system_prompt = system_prompt
        yield "ok."


@pytest.mark.asyncio
async def test_mission_session_drives_the_turn_with_the_mission_prompt(client, db_session):
    """The whole point of a mission: its persona prompt (not the profile prompt)
    drives the conversation LLM."""
    from fastapi import Depends

    from app.database import get_db
    from app.features.conversation.dependencies import get_conversation_turn_service
    from app.features.conversation.repository import SqlAlchemyTranscriptRepository
    from app.features.conversation.turn_service import ConversationTurnService
    from app.features.profile.repository import SqlAlchemyProfileRepository
    from app.features.sessions.repository import SqlAlchemySessionRepository

    token = await _register(client, email="drives@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post(
        "/missions", headers=headers, json={"source_type": "offer", "content": "offer"}
    )
    mission_id = created.json()["id"]
    started = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "mission", "mission_id": mission_id},
    )
    session_id = started.json()["session_id"]

    spy = _SpyLlm()

    def _override(db=Depends(get_db)):
        return ConversationTurnService(
            sessions=SqlAlchemySessionRepository(db),
            transcripts=SqlAlchemyTranscriptRepository(db),
            profiles=SqlAlchemyProfileRepository(db),
            llm=spy,
            missions=SqlAlchemyMissionRepository(db),
        )

    app.dependency_overrides[get_conversation_turn_service] = _override
    try:
        resp = await client.post(
            f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
        )
        assert resp.status_code == 200, resp.text
        # The mission's persona-driven system prompt reached the LLM, and it is
        # clearly a mission prompt (role-play), not the default profile prompt.
        assert spy.seen_system_prompt is not None
        assert "spoken English practice simulation" in spy.seen_system_prompt
        assert "friendly interviewer" in spy.seen_system_prompt
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)
