from datetime import date, timedelta

import pytest

from app.core import quota
from app.core.livekit import build_room_token
from app.models.user import User


def _make_user(**kw) -> User:
    defaults = dict(id=1, email="q@b.com", hashed_password="x", tier="free")
    defaults.update(kw)
    return User(**defaults)


def test_quota_resets_on_new_day():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == 10.0  # yesterday's usage is wiped


def test_quota_counts_today_usage():
    user = _make_user(quota_date=date.today(), minutes_used_today=7.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == 3.0


def test_premium_user_has_unlimited():
    user = _make_user(tier="premium", quota_date=date.today(), minutes_used_today=999.0)
    remaining = quota.remaining_minutes(user, free_daily=10, today=date.today())
    assert remaining == float("inf")


def test_record_usage_resets_then_adds():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    quota.record_usage(user, minutes=2.0, today=date.today())
    assert user.quota_date == date.today()
    assert user.minutes_used_today == 2.0


def test_build_room_token_returns_jwt():
    token = build_room_token(identity="user-1", room="session-1")
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature


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
    assert body["room_name"]
    assert body["livekit_token"].count(".") == 2


@pytest.mark.asyncio
async def test_end_session_records_duration_and_usage(client):
    headers = await _auth_header(client, email="s2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    resp = await client.post(
        f"/sessions/{session_id}/end", headers=headers, json={"duration_minutes": 4.5}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["duration_minutes"] == 4.5


@pytest.mark.asyncio
async def test_start_session_blocked_when_quota_exhausted(client):
    headers = await _auth_header(client, email="s3@b.com")
    # Burn the full free daily quota in one session.
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    sid = start.json()["session_id"]
    await client.post(f"/sessions/{sid}/end", headers=headers, json={"duration_minutes": 10.0})

    blocked = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert blocked.status_code == 402  # Payment Required (quota exhausted)
