"""API-level coverage for the quota-exhausted (402) path (#282, audit #242).

Existing coverage before this file: a UNIT test (test_session_service.py) that
`SessionService.start()` raises `QuotaExhaustedError` when the quota is spent, and
a UNIT test that `record_turn_activity` records usage. Neither exercised the real
HTTP request -> FastAPI exception handler -> 402 response wiring end to end, and
none documented WHERE quota is actually enforced.

That matters because #282 (an audit finding) assumed the server checks quota
MID-TURN ("Backend commence le turn, à mi-chemin détecte quota insuffisant, retourne
402"). Reading turn_service.py and sessions/service.py shows that isn't how it
works: `record_turn_activity` (called after every turn, see conversation/router.py)
only RECORDS usage — it never re-checks it, and `/turn` /`/turn/stream` never raise
QuotaExhaustedError. The only gate is `SessionService.start()`, at the START of a
session. So a learner who starts a session with a sliver of quota left can run
turns past their daily cap for the REST of that session; they are only blocked the
next time they try to start a new one. This file covers the REAL boundary
end-to-end and documents the mid-session behaviour explicitly, instead of testing
a 402-mid-turn path that does not exist in the code.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import update

from app.config import get_settings
from app.features.auth.models import User


async def _auth_header(client, email="quota@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _set_usage(db_session, email: str, minutes: float, quota_date: date) -> None:
    await db_session.execute(
        update(User)
        .where(User.email == email)
        .values(minutes_used_today=minutes, quota_date=quota_date)
    )
    await db_session.commit()


async def _exhaust_quota(db_session, email: str, *, quota_date: date | None = None) -> None:
    """Directly sets this user's usage to their full daily free allowance, on
    `quota_date` (default today in UTC via `datetime.now(UTC).date()` — the exact
    clock `SessionService` compares against at service.py:115, NOT `date.today()`,
    which is the server's LOCAL date and would silently mismatch UTC near midnight
    in a non-UTC timezone; the code itself avoids `date.today()` for this reason,
    see service.py:209), so the next `/sessions/start` is evaluated as quota-exhausted.
    Reads the CONFIGURED cap (not a literal like 10) because
    `FREE_TIER_DAILY_MINUTES` is overridable per environment (a developer's
    local `.env` has been seen overriding it) — a hardcoded value would
    silently stop actually exhausting the quota wherever the override differs
    from the code's default, making these tests pass for the wrong reason
    instead of failing loudly."""
    minutes = get_settings().free_tier_daily_minutes
    await _set_usage(db_session, email, minutes, quota_date or datetime.now(UTC).date())


@pytest.mark.asyncio
async def test_start_session_returns_402_when_quota_exhausted(client, db_session):
    headers = await _auth_header(client, email="exhausted-start@b.com")
    await _exhaust_quota(db_session, "exhausted-start@b.com")

    resp = await client.post("/sessions/start", headers=headers, json={"mode": "free"})

    assert resp.status_code == 402, resp.text
    body = resp.json()
    assert body["error"]["code"] == "QuotaExhaustedError"


@pytest.mark.asyncio
async def test_turn_is_not_quota_gated_mid_session_only_session_start_is(client, db_session):
    """Documents the ACTUAL behaviour #282 assumed was different (see module
    docstring): once a session is running, exhausting the daily quota mid-session
    does NOT interrupt it with a 402. This is the honest coverage for #282's
    scenario — the "mid-turn 402" it describes has no code path to test."""
    email = "exhausted-midturn@b.com"
    headers = await _auth_header(client, email=email)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    # The learner's quota runs out WHILE this session is in progress (e.g. a long
    # conversation, or another session billed concurrently) — mirrors #282's "0.5
    # credits remaining mid-turn" setup, but via the field the server actually reads.
    await _exhaust_quota(db_session, email)

    turn = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
    )

    assert turn.status_code == 200, turn.text  # NOT 402 — the turn is not gated
    assert turn.json()["reply"] == "You said: hello"


@pytest.mark.asyncio
async def test_quota_exhausted_mid_session_blocks_only_the_next_session_start(client, db_session):
    """The full lifecycle #282 actually cares about: a learner who goes over their
    daily cap during one session is blocked from starting the NEXT one — not
    interrupted mid-flow. Confirms the boundary is real, just at a different place
    than the issue assumed."""
    email = "exhausted-next-start@b.com"
    headers = await _auth_header(client, email=email)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await _exhaust_quota(db_session, email)

    turn = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "still going"}
    )
    assert turn.status_code == 200, turn.text  # the in-flight session finishes turns fine

    end = await client.post(f"/sessions/{session_id}/end", headers=headers)
    assert end.status_code == 200, end.text

    again = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert again.status_code == 402, again.text  # blocked here, not mid-session


@pytest.mark.asyncio
async def test_quota_resets_on_a_new_utc_day(client, db_session):
    """Sanity guard for the exhaustion helper/assertions above: yesterday's usage
    must not carry over — otherwise the 402 tests could pass for the wrong reason
    (a permanently-exhausted account) instead of the actual daily-reset boundary."""
    email = "quota-resets@b.com"
    headers = await _auth_header(client, email=email)
    await _exhaust_quota(db_session, email, quota_date=date(2000, 1, 1))

    resp = await client.post("/sessions/start", headers=headers, json={"mode": "free"})

    assert resp.status_code == 201, resp.text
