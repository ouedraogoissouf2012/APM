"""Periodic purge tasks for tables with unbounded growth (#239, #271).

Removes expired or old entries from:
- refresh_tokens (expired or revoked)
- idempotency_keys (old entries, completed requests)
- analytics_events (old events, >30 days)

Meant to run periodically (cron, background task, or best-effort on login).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.features.analytics.domain import EVENT_ACTIVATION
from app.features.analytics.models import AnalyticsEventRow
from app.features.auth.models import RefreshToken
from app.features.idempotency.models import IdempotencyKey

_logger = logging.getLogger(__name__)

# Purge old idempotency keys after 24 hours (request completion unlikely after this)
IDEMPOTENCY_KEY_TTL_HOURS = 24

# Purge old analytics events after 30 days (retention policy)
ANALYTICS_EVENT_TTL_DAYS = 30

# Event names EXEMPT from the retention purge above (#385): `activation` is not
# a volume/log event but a permanent, exactly-once per-user funnel marker (DB
# partial-unique index `uq_analytics_activation_per_user`, #188) — the aggregate
# reports `users_activated` as a LIFETIME count derived from this row existing.
# Deleting it after 30 days silently undercounts a still-active learner forever:
# service.py only re-emits activation when the user has ZERO prior completions,
# which stays false for anyone who kept practicing. Any future permanent/
# exactly-once funnel marker belongs in this set too — a per-event log
# (session_completed, transfer_started) does NOT: those are genuinely
# volume-bounded by design and must stay subject to the 30-day retention purge.
ANALYTICS_RETENTION_EXEMPT_NAMES = frozenset({EVENT_ACTIVATION})


async def try_acquire_purge_lock(redis_url: str, ttl_seconds: int) -> bool:
    """#446: only one worker should DELETE. Empty redis_url = single-process
    (dev/test) — always acquire. Redis SET NX; on Redis error skip this tick."""
    if not redis_url.strip():
        return True
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url)
        try:
            won = bool(await client.set("apm:purge:lock", "1", nx=True, ex=max(1, ttl_seconds)))
            if not won:
                metrics.inc(metrics.PURGE_LOCK_SKIPS)
            return won
        finally:
            await client.aclose()
    except Exception:
        metrics.inc(metrics.PURGE_LOCK_SKIPS)
        _logger.warning("Purge lock unavailable; skipping this tick", exc_info=True)
        return False


async def purge_expired_entries(db: AsyncSession) -> dict[str, int]:
    """Purge expired/revoked refresh tokens, old idempotency keys, and old analytics events.

    Returns a dict with counts deleted per table.
    """
    now = datetime.now(UTC)
    results = {"refresh_tokens": 0, "idempotency_keys": 0, "analytics_events": 0}

    try:
        # Purge EXPIRED refresh tokens only — a revoked-but-unexpired token is kept so
        # reuse/theft detection (#253) can still recognise it if replayed.
        from sqlalchemy import delete

        result = await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        results["refresh_tokens"] = getattr(result, "rowcount", 0) or 0

        # Purge old idempotency keys (request is done, safe to forget)
        cutoff_idempotency = now - timedelta(hours=IDEMPOTENCY_KEY_TTL_HOURS)
        result = await db.execute(
            delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff_idempotency)
        )
        results["idempotency_keys"] = getattr(result, "rowcount", 0) or 0

        # Purge old analytics events (retention policy) — EXCEPT the permanent
        # funnel markers in ANALYTICS_RETENTION_EXEMPT_NAMES (#385), which must
        # survive regardless of age.
        cutoff_analytics = now - timedelta(days=ANALYTICS_EVENT_TTL_DAYS)
        result = await db.execute(
            delete(AnalyticsEventRow).where(
                AnalyticsEventRow.created_at < cutoff_analytics,
                AnalyticsEventRow.name.notin_(ANALYTICS_RETENTION_EXEMPT_NAMES),
            )
        )
        results["analytics_events"] = getattr(result, "rowcount", 0) or 0

        await db.commit()
        total = sum(results.values())
        if total > 0:
            _logger.info("Purged expired entries: %s", results)
    except Exception as exc:
        await db.rollback()
        metrics.inc(metrics.PURGE_FAILURES)
        _logger.warning("Purge failed (best-effort): %s", exc)

    return results
