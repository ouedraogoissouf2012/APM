"""Integration tests for POST /me/transfer/{skill} (#126).

With MISSION_ENGINE=fake (conftest), the compiler returns a valid generic brief,
so the transfer endpoint yields a launchable mission.
"""

import pytest
from sqlalchemy import select

from app.features.analytics.domain import EVENT_TRANSFER_STARTED
from app.features.analytics.models import AnalyticsEventRow


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
async def test_transfer_requires_auth(client):
    resp = await client.post("/me/transfer/job_interview")
    assert resp.status_code == 401, resp.text
