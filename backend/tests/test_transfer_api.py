"""Integration tests for POST /me/transfer/{skill} (#126).

With MISSION_ENGINE=fake (conftest), the compiler returns a valid generic brief,
so the transfer endpoint yields a launchable mission.
"""

import pytest
from sqlalchemy import select

from app.core.rate_limit import InMemoryRateLimiter
from app.features.analytics.domain import EVENT_TRANSFER_STARTED
from app.features.analytics.models import AnalyticsEventRow
from app.features.missions.dependencies import get_mission_rate_limiter
from app.main import app


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "tr@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_transfer_compiles_a_launchable_mission(client):
    headers = await _auth(client)

    resp = await client.post("/me/transfer/job_interview", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persona"]
    assert body["goal"]
    mission_id = body["id"]

    # The compiled challenge is launchable as a normal mission session.
    start = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "mission", "mission_id": mission_id},
    )
    assert start.status_code == 201, start.text


@pytest.mark.asyncio
async def test_transfer_emits_a_transfer_started_event(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    await client.post("/me/transfer/restaurant", headers=headers)

    rows = list(
        await db_session.scalars(
            select(AnalyticsEventRow).where(
                AnalyticsEventRow.user_id == user_id,
                AnalyticsEventRow.name == EVENT_TRANSFER_STARTED,
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].properties == {"skill": "restaurant"}


@pytest.mark.asyncio
async def test_transfer_rejects_an_overlong_skill(client):
    # The skill flows into an LLM prompt and a stored analytics property, so it is
    # bounded at the edge (max 64 chars) -> 422 rather than compiling/storing it.
    headers = await _auth(client)
    resp = await client.post("/me/transfer/" + "x" * 65, headers=headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_transfer_rejects_a_blank_skill(client):
    # A whitespace-only segment passes the length floor but is rejected after strip.
    headers = await _auth(client)
    resp = await client.post("/me/transfer/%20%20", headers=headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_transfer_requires_auth(client):
    resp = await client.post("/me/transfer/job_interview")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_transfer_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """#356: the limiter key must be user_id-only. Before the fix, the IP was
    part of the key, so a free account rotating its apparent IP (VPN, or
    X-Forwarded-For under trust_proxy_headers) got a fresh bucket per IP on
    this paid (LLM-compiled) endpoint — a denial-of-wallet."""
    headers = await _auth(client)
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_mission_rate_limiter] = lambda: limiter
    try:
        first = await client.post(
            "/me/transfer/job_interview", headers={**headers, "X-Forwarded-For": "1.1.1.1"}
        )
        assert first.status_code == 200, first.text
        second = await client.post(
            "/me/transfer/restaurant", headers={**headers, "X-Forwarded-For": "2.2.2.2"}
        )
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_mission_rate_limiter, None)
