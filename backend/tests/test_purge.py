"""Periodic purge of unbounded-growth tables (#239/#271).

Expired refresh tokens, old idempotency keys and old analytics events are deleted;
fresh rows — and REVOKED-but-not-yet-expired refresh tokens (kept so reuse/theft
detection #253 can still recognise a replay) — survive.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.analytics.domain import EVENT_ACTIVATION, EVENT_SESSION_COMPLETED
from app.features.analytics.models import AnalyticsEventRow
from app.features.analytics.repository import SqlAlchemyAnalyticsAggregateSource
from app.features.auth.models import RefreshToken, User
from app.features.idempotency.models import IdempotencyKey
from app.features.purge.task import (
    ANALYTICS_EVENT_TTL_DAYS,
    IDEMPOTENCY_KEY_TTL_HOURS,
    purge_expired_entries,
)


async def _user(db_session) -> User:
    user = User(email="purge@b.com", hashed_password="x", native_language="fr")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_purge_deletes_old_entries_and_keeps_fresh(db_session):
    now = datetime.now(UTC)
    user = await _user(db_session)

    # Refresh tokens: expired (delete), revoked-but-unexpired (KEEP #253), fresh (keep).
    db_session.add(
        RefreshToken(user_id=user.id, token_hash="expired", expires_at=now - timedelta(days=1))
    )
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash="revoked-fresh",
            expires_at=now + timedelta(days=1),
            revoked_at=now,
        )
    )
    db_session.add(
        RefreshToken(user_id=user.id, token_hash="fresh", expires_at=now + timedelta(days=1))
    )
    # Idempotency keys: old (delete), fresh (keep).
    old_idem = IdempotencyKey(user_id=user.id, key="old", response="r")
    fresh_idem = IdempotencyKey(user_id=user.id, key="fresh", response="r")
    db_session.add_all([old_idem, fresh_idem])
    # Analytics events: old (delete), fresh (keep).
    old_ev = AnalyticsEventRow(name="old", user_id=user.id, properties={})
    fresh_ev = AnalyticsEventRow(name="fresh", user_id=user.id, properties={})
    db_session.add_all([old_ev, fresh_ev])
    await db_session.flush()

    # created_at is server-set to now on insert; backdate the "old" rows past their TTL.
    old_idem.created_at = now - timedelta(hours=IDEMPOTENCY_KEY_TTL_HOURS + 1)
    old_ev.created_at = now - timedelta(days=ANALYTICS_EVENT_TTL_DAYS + 1)
    await db_session.commit()

    result = await purge_expired_entries(db_session)

    # Exactly the aged-out rows are removed. refresh_tokens == 1 means ONLY the
    # expired token went — the revoked-but-unexpired one was KEPT (#253); the old
    # buggy `expires_at < now OR revoked_at IS NOT NULL` would have deleted 2. The
    # fresh token, fresh idempotency key and fresh analytics event all survive.
    assert result == {"refresh_tokens": 1, "idempotency_keys": 1, "analytics_events": 1}


@pytest.mark.asyncio
async def test_purge_keeps_activation_past_ttl_but_still_purges_other_old_events(db_session):
    """#385: `activation` is a permanent, exactly-once funnel marker (partial
    unique index uq_analytics_activation_per_user) — the aggregate reports
    users_activated as a lifetime count derived from this row's mere existence.
    Deleting it after 30 days silently undercounts a still-active learner
    forever, since service.py only re-emits activation when the user has ZERO
    prior completions (never true for someone who kept practicing).

    A same-age session_completed row must still be purged normally: this is a
    TARGETED exemption for funnel markers, not "stop purging analytics_events"."""
    now = datetime.now(UTC)
    user = await _user(db_session)
    old_activation = AnalyticsEventRow(name=EVENT_ACTIVATION, user_id=user.id, properties={})
    old_completion = AnalyticsEventRow(name=EVENT_SESSION_COMPLETED, user_id=user.id, properties={})
    db_session.add_all([old_activation, old_completion])
    await db_session.flush()
    activation_id, completion_id = old_activation.id, old_completion.id
    old_activation.created_at = now - timedelta(days=ANALYTICS_EVENT_TTL_DAYS + 1)
    old_completion.created_at = now - timedelta(days=ANALYTICS_EVENT_TTL_DAYS + 1)
    await db_session.commit()

    result = await purge_expired_entries(db_session)

    # Only the completion was purged — 1, not 2.
    assert result["analytics_events"] == 1
    db_session.expire_all()
    remaining = await db_session.get(AnalyticsEventRow, activation_id)
    assert remaining is not None  # the >30-day-old activation row survives
    assert await db_session.get(AnalyticsEventRow, completion_id) is None

    # The real aggregate query (not just a row count) must still see this user
    # as activated — the actual thing an admin dashboard reads.
    aggregate = SqlAlchemyAnalyticsAggregateSource(db_session)
    assert await aggregate.distinct_users_with_event(EVENT_ACTIVATION) == 1
