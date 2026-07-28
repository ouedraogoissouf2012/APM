"""Integration tests for the billing endpoints (subscription + admin tier change)."""

import pytest
from sqlalchemy import select, update

from app.features.auth.models import TIER_PREMIUM, User


async def _register(client, email="bill@b.com"):
    resp = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return resp.json()["access_token"]


async def _make_admin(db_session, email: str) -> None:
    # Admin is granted in the DB only (never via the API) — the bootstrap path.
    await db_session.execute(update(User).where(User.email == email).values(is_admin=True))
    await db_session.commit()


@pytest.mark.asyncio
async def test_subscription_defaults_to_free_with_quota(client):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/me/subscription", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "free"
    assert body["is_premium"] is False
    assert body["free_daily_minutes"] == 10
    assert body["remaining_minutes"] == 10.0


@pytest.mark.asyncio
async def test_subscription_requires_auth(client):
    resp = await client.get("/me/subscription")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_promote_a_user_to_premium(client, db_session):
    # An admin and a target user.
    admin_token = await _register(client, email="admin@b.com")
    await _make_admin(db_session, "admin@b.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user_token = await _register(client, email="target@b.com")
    user_headers = {"Authorization": f"Bearer {user_token}"}

    target = await db_session.scalar(select(User.id).where(User.email == "target@b.com"))

    resp = await client.post(
        f"/admin/users/{target}/tier", headers=admin_headers, json={"tier": "premium"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_premium"] is True
    assert resp.json()["remaining_minutes"] is None  # unlimited -> null

    # The promoted user now sees premium on their own subscription.
    me = await client.get("/me/subscription", headers=user_headers)
    assert me.json()["tier"] == TIER_PREMIUM


@pytest.mark.asyncio
async def test_non_admin_cannot_change_tiers(client):
    token = await _register(client, email="notadmin@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/admin/users/1/tier", headers=headers, json={"tier": "premium"})
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_admin_gets_404_for_unknown_user(client, db_session):
    token = await _register(client, email="admin2@b.com")
    await _make_admin(db_session, "admin2@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/admin/users/99999/tier", headers=headers, json={"tier": "premium"})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_admin_rejects_unknown_tier(client, db_session):
    token = await _register(client, email="admin3@b.com")
    await _make_admin(db_session, "admin3@b.com")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/admin/users/1/tier", headers=headers, json={"tier": "gold"})
    assert resp.status_code == 422, resp.text
