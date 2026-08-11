"""Periodic purge of unbounded-growth tables (#239/#271).

Expired refresh tokens, old idempotency keys and old analytics events are deleted;
fresh rows — and REVOKED-but-not-yet-expired refresh tokens (kept so reuse/theft
detection #253 can still recognise a replay) — survive.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.analytics.models import AnalyticsEventRow
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
