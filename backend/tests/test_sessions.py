"""Integration tests for the sessions API (real DB).

Unit tests for the quota policy and SessionService live in tests/unit/.
"""

import pytest


async def _auth_header(client, email="s@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_start_session_returns_token_and_room(client):
    headers = await _auth_header(client)
    resp = await client.post(
        "/sessions/start", headers=headers, json={"mode": "scenario", "scenario_id": "restaurant"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["session_id"]
    assert body["room_name"].startswith("apm-")
    assert body["livekit_token"].count(".") == 2


@pytest.mark.asyncio
async def test_cannot_start_two_active_sessions(client):
    headers = await _auth_header(client, email="s2@b.com")
    first = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert first.status_code == 201
    second = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert second.status_code == 409  # an active session already exists


@pytest.mark.asyncio
async def test_end_closes_session_and_allows_restart(client):
    headers = await _auth_header(client, email="s3@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    end = await client.post(f"/sessions/{session_id}/end", headers=headers)
    assert end.status_code == 200, end.text
    body = end.json()
    assert body["duration_minutes"] is not None
    assert body["duration_minutes"] >= 0  # server-computed, not client-supplied

    # With the previous session ended, a new one can start.
    again = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert again.status_code == 201


@pytest.mark.asyncio
async def test_end_is_idempotent(client):
    headers = await _auth_header(client, email="s4@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(f"/sessions/{session_id}/end", headers=headers)
    second = await client.post(f"/sessions/{session_id}/end", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
