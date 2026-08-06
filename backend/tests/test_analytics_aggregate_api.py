"""Integration tests for GET /admin/analytics/summary (#129)."""

import pytest
from sqlalchemy import update

from app.features.analytics.domain import (
    EVENT_ACTIVATION,
    EVENT_SESSION_COMPLETED,
    EVENT_TRANSFER_STARTED,
)
from app.features.analytics.models import AnalyticsEventRow
from app.features.auth.models import User


async def _register(client, email):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return reg.json()["access_token"]


async def _make_admin(db_session, email):
    await db_session.execute(update(User).where(User.email == email).values(is_admin=True))
    await db_session.commit()


async def _seed(db_session, user_id, name):
    db_session.add(AnalyticsEventRow(name=name, user_id=user_id, properties={}))
    await db_session.commit()


@pytest.mark.asyncio
async def test_admin_sees_the_funnel_summary(client, db_session):
    token = await _register(client, "admin@b.com")
    await _make_admin(db_session, "admin@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    await _seed(db_session, user_id, EVENT_ACTIVATION)
    await _seed(db_session, user_id, EVENT_SESSION_COMPLETED)
    await _seed(db_session, user_id, EVENT_SESSION_COMPLETED)
    await _seed(db_session, user_id, EVENT_TRANSFER_STARTED)

    resp = await client.get("/admin/analytics/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["users_activated"] == 1
    assert body["completions_total"] == 2
    assert body["transfers_started_total"] == 1


@pytest.mark.asyncio
async def test_non_admin_is_forbidden(client):
    token = await _register(client, "user@b.com")
    resp = await client.get(
        "/admin/analytics/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_requires_auth(client):
    resp = await client.get("/admin/analytics/summary")
    assert resp.status_code == 401, resp.text
