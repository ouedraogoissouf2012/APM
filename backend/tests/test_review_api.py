"""Integration tests for the review (SRS) endpoint and the debrief hook.

A generated debrief feeds its error types into the SRS schedule; GET /me/review
lists what is due. We seed the schedule through the ReviewService on the shared
db session, then assert the endpoint.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.review.models import ReviewItem
from app.features.review.repository import SqlAlchemyReviewRepository
from app.features.review.service import ReviewService


async def _auth(client):
    reg = await client.post("/auth/register", json={"email": "rv@b.com", "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_review_empty_by_default(client):
    headers = await _auth(client)
    resp = await client.get("/me/review", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


@pytest.mark.asyncio
async def test_seen_error_type_becomes_due_after_its_interval(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    past = datetime(2026, 8, 1, tzinfo=UTC)
    await service.record_session(user_id, {"verb_tense": "I went"}, past)

    # Scheduled at past + 1 day, which is well before now -> due.
    resp = await client.get("/me/review", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["error_type"] == "verb_tense"
    assert body[0]["latest_correction"] == "I went"
    assert body[0]["status"] == "due"


@pytest.mark.asyncio
async def test_not_yet_due_item_is_not_listed(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    # Scheduled in the future (now + 1 day) -> not due yet.
    await service.record_session(user_id, {"article": "a cat"}, datetime.now(UTC))

    resp = await client.get("/me/review", headers=headers)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_mastered_type_is_not_listed(client, db_session):
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    past = datetime(2026, 8, 1, tzinfo=UTC)
    await service.record_session(user_id, {"verb_tense": "x"}, past)
    # Three clean sessions, each AT the next due date so the J+1/J+3/J+7 intervals
    # actually elapse (same-day sessions would no longer master it).
    t = past + timedelta(days=1)
    await service.record_session(user_id, {}, t)  # clean #1 (due) -> J+3
    t += timedelta(days=3)
    await service.record_session(user_id, {}, t)  # clean #2 (due) -> J+7
    t += timedelta(days=7)
    await service.record_session(user_id, {}, t)  # clean #3 (due) -> mastered

    resp = await client.get("/me/review", headers=headers)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_review_only_sees_own_items(client, db_session):
    headers_a = await _auth(client)
    me_a = await client.get("/auth/me", headers=headers_a)
    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    await service.record_session(
        me_a.json()["id"], {"verb_tense": "x"}, datetime(2026, 8, 1, tzinfo=UTC)
    )

    reg_b = await client.post(
        "/auth/register", json={"email": "rv-b@b.com", "password": "s3cret!pass"}
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
    resp = await client.get("/me/review", headers=headers_b)
    assert resp.json() == []


@pytest.mark.asyncio
async def test_review_requires_auth(client):
    resp = await client.get("/me/review")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_review_items_has_next_review_at_index(db_session):
    """#288: next_review_at must stay index-covered so list_due's per-user scan
    doesn't regress to an unindexed column if the model is edited later.

    Checks the LIVE schema (this test's DB is provisioned by
    Base.metadata.create_all, same as CI) rather than the ORM's in-memory
    metadata, so it also catches a name/column mismatch between models.py and
    the Alembic migration that create_all-only CI can't see.
    """
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'review_items'"
            " AND indexname = 'ix_review_items_user_id_next_review_at'"
        )
    )
    indexdef = result.scalar_one_or_none()
    assert indexdef is not None, "composite (user_id, next_review_at) index is missing"
    assert indexdef.endswith("(user_id, next_review_at)"), indexdef


@pytest.mark.asyncio
async def test_concurrent_record_session_same_user_does_not_duplicate_or_crash(
    client, db_session, _engine
):
    """#361: two concurrent record_session calls for the SAME user (e.g. two
    devices each finishing a different session around the same time) must not
    crash on review_items' uq_review_user_error_type constraint, and must not
    end up with two rows for the same error_type. Two independent DB sessions
    reproduce genuinely concurrent transactions — mirrors
    test_debrief_api.py's #302 concurrency test, at the service layer since
    record_session has no dedicated HTTP endpoint of its own (it's a hook off
    the debrief flow). The repository's advisory lock (lock_for_user)
    serialises them: the loser blocks until the winner's commit releases it.
    """
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session_a, maker() as session_b:
        service_a = ReviewService(SqlAlchemyReviewRepository(session_a))
        service_b = ReviewService(SqlAlchemyReviewRepository(session_b))
        await asyncio.gather(
            service_a.record_session(user_id, {"verb_tense": "I go"}, now),
            service_b.record_session(user_id, {"verb_tense": "I go"}, now),
        )

    db_session.expire_all()
    count = await db_session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.user_id == user_id, ReviewItem.error_type == "verb_tense")
    )
    assert count == 1  # no duplicate row, no IntegrityError


@pytest.mark.asyncio
async def test_debrief_feeds_the_review_schedule(client, db_session):
    """End-to-end: a debrief with an error schedules that type for review."""
    from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER
    from app.features.conversation.repository import SqlAlchemyTranscriptRepository

    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    # A transcript so the debrief runs the (fake) analyzer.
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id,
        [
            {"role": ROLE_ASSISTANT, "content": "How was your day?"},
            {"role": ROLE_USER, "content": "I go to school yesterday"},
        ],
    )
    created = await client.post(f"/sessions/{session_id}/debrief", headers=headers)
    assert created.status_code == 201, created.text

    # The fake analyzer returns no errors, so nothing is scheduled — but the hook
    # ran without breaking the debrief. Seed one error type to prove the wiring end
    # to end via the same schedule the debrief writes to.
    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    await service.record_session(
        user_id, {"verb_tense": "I went"}, datetime(2026, 8, 1, tzinfo=UTC)
    )
    resp = await client.get("/me/review", headers=headers)
    assert [i["error_type"] for i in resp.json()] == ["verb_tense"]
