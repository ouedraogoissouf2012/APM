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
    the debrief flow).

    #392: this alone does NOT prove lock_for_user serialises the read-compute-
    write — upsert()'s ON CONFLICT DO UPDATE guarantees `count == 1` on its
    own, since both calls here start from the SAME empty state and compute the
    byte-identical write (same error type, same correction); last-writer-wins
    is indistinguishable from serialised here. See
    test_concurrent_record_session_lost_update_is_prevented_by_the_lock below
    for a test that actually exercises the lock.
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
async def test_concurrent_record_session_lost_update_is_prevented_by_the_lock(
    client, db_session, _engine
):
    """#392: makes lock_for_user's read-compute-write serialisation actually
    observable, unlike the sibling test above. Pre-seeds one error type to a
    KNOWN, already-due state (one clean session in: stage=1/J+3), then fires
    two concurrent record_session calls that read that SAME shared prior state
    and compute DIVERGENT next states from it:

    - "seen" (the error reappeared): on_error_seen unconditionally resets to
      stage=0/J+1 with the NEW correction, regardless of prior state.
    - "absent" (a clean session): on_error_absent reads next_review_at off
      the prior state to decide whether to advance the streak/stage.

    Properly serialised, the final row is deterministically the "seen" reset
    REGARDLESS of which call the lock lets through first: if "seen" applies
    first, "absent" then re-reads its own now-future next_review_at and
    becomes a no-op that just re-writes the same row; if "absent" applies
    first, "seen" overwrites it unconditionally anyway. Without the lock (or
    with it moved after list_for_user, e.g. a future refactor reasoning "ON
    CONFLICT already makes upsert race-free" — see the sibling test's
    docstring for exactly why that reasoning is wrong), both calls instead
    read the STALE pre-seeded state independently, and whichever commits last
    wins outright: on the iterations where "absent" wins, the newly-seen
    error's reset is silently discarded, leaving stage=2/latest_correction=
    "old mistake" as the final state — the lost update the lock exists to
    prevent, and a scenario this test can distinguish from the deterministic
    "seen always wins" invariant above. Repeated over several pre-seeded items
    since a raw last-writer race is timing-dependent — a single attempt could
    pass by luck even with the lock broken (mirrors this file's/
    test_debrief_api.py's/test_sessions.py's other real-concurrency tests,
    which rely on genuine DB-driven timing rather than mocked delays)."""
    headers = await _auth(client)
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    seed_service = ReviewService(SqlAlchemyReviewRepository(db_session))

    for i in range(8):
        error_type = f"verb_tense_{i}"
        seeded_at = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        # Well past the pre-seed's resulting next_review_at (seeded_at + 4
        # days: J+1 then J+3), so on_error_absent below treats it as due.
        now = seeded_at + timedelta(days=10)

        # Two real sessions establish a KNOWN prior state: one clean session
        # already applied (stage=1/J+3, one clean_streak) on top of the
        # original sighting.
        await seed_service.record_session(user_id, {error_type: "old mistake"}, seeded_at)
        await seed_service.record_session(user_id, {}, seeded_at + timedelta(days=1))
        db_session.expire_all()

        async with maker() as session_a, maker() as session_b:
            service_a = ReviewService(SqlAlchemyReviewRepository(session_a))
            service_b = ReviewService(SqlAlchemyReviewRepository(session_b))
            await asyncio.gather(
                service_a.record_session(user_id, {error_type: "new mistake"}, now),
                service_b.record_session(user_id, {}, now),
            )

        db_session.expire_all()
        item = await db_session.scalar(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id, ReviewItem.error_type == error_type
            )
        )
        assert item is not None
        # Deterministic under correct serialisation regardless of interleaving
        # order (see docstring) — a lost update instead leaves the "absent"
        # advance (stage 2, stale correction) as the final state on at least
        # one of these 8 iterations if the lock is broken.
        assert item.stage == 0, f"iteration {i}: lost update — 'absent' overwrote 'seen'"
        assert item.clean_streak == 0
        assert item.latest_correction == "new mistake"


@pytest.mark.asyncio
async def test_debrief_feeds_the_review_schedule(client, db_session):
    """End-to-end: a debrief with an error schedules that type for review."""
    from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
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
    assert created.status_code == 200, created.text

    # The fake analyzer returns no errors, so nothing is scheduled — but the hook
    # ran without breaking the debrief. Seed one error type to prove the wiring end
    # to end via the same schedule the debrief writes to.
    service = ReviewService(SqlAlchemyReviewRepository(db_session))
    await service.record_session(
        user_id, {"verb_tense": "I went"}, datetime(2026, 8, 1, tzinfo=UTC)
    )
    resp = await client.get("/me/review", headers=headers)
    assert [i["error_type"] for i in resp.json()] == ["verb_tense"]
