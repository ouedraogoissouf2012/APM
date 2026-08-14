"""Integration tests for the streak endpoints and the per-turn hook."""

from datetime import date, timedelta

import pytest

from app.features.auth.repository import SqlAlchemyUserRepository


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "st@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_new_user_has_zero_streak_and_default_goal(client):
    headers = await _auth(client)
    resp = await client.get("/me/streak", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_streak"] == 0
    assert body["longest_streak"] == 0
    assert body["weekly_goal_minutes"] == 30  # default


@pytest.mark.asyncio
async def test_a_turn_today_starts_a_one_day_streak(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    # Simulate an active day by writing the streak fields as the turn hook would.
    users = SqlAlchemyUserRepository(db_session)
    user = await users.get_by_id(user_id)
    user.current_streak = 1
    user.longest_streak = 1
    user.last_active_date = date.today()
    await users.save(user)

    resp = await client.get("/me/streak", headers=headers)
    assert resp.json()["current_streak"] == 1


@pytest.mark.asyncio
async def test_broken_streak_reads_zero_but_keeps_the_record(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    users = SqlAlchemyUserRepository(db_session)
    user = await users.get_by_id(user_id)
    user.current_streak = 7
    user.longest_streak = 12
    user.last_active_date = date.today() - timedelta(days=3)  # missed days
    await users.save(user)

    body = (await client.get("/me/streak", headers=headers)).json()
    assert body["current_streak"] == 0  # broken
    assert body["longest_streak"] == 12  # record kept


@pytest.mark.asyncio
async def test_update_weekly_goal(client):
    headers = await _auth(client)
    resp = await client.put("/me/streak/goal", headers=headers, json={"weekly_goal_minutes": 60})
    assert resp.status_code == 200, resp.text
    assert resp.json()["weekly_goal_minutes"] == 60

    # Persisted.
    again = await client.get("/me/streak", headers=headers)
    assert again.json()["weekly_goal_minutes"] == 60


@pytest.mark.asyncio
async def test_weekly_goal_out_of_range_is_rejected(client):
    # #391: out-of-range is a real 422 at the edge, not a silent clamp.
    headers = await _auth(client)
    below = await client.put("/me/streak/goal", headers=headers, json={"weekly_goal_minutes": 1})
    assert below.status_code == 422, below.text
    above = await client.put("/me/streak/goal", headers=headers, json={"weekly_goal_minutes": 5000})
    assert above.status_code == 422, above.text
    # Nothing was persisted — the goal is still the untouched default.
    again = await client.get("/me/streak", headers=headers)
    assert again.json()["weekly_goal_minutes"] == 30


@pytest.mark.asyncio
async def test_streak_requires_auth(client):
    resp = await client.get("/me/streak")
    assert resp.status_code == 401, resp.text
