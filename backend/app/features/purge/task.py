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

from app.features.analytics.models import AnalyticsEventRow
from app.features.auth.models import RefreshToken
from app.features.idempotency.models import IdempotencyKey

_logger = logging.getLogger(__name__)

# Purge old idempotency keys after 24 hours (request completion unlikely after this)
IDEMPOTENCY_KEY_TTL_HOURS = 24

# Purge old analytics events after 30 days (retention policy)
ANALYTICS_EVENT_TTL_DAYS = 30


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

        # Purge old analytics events (retention policy)
        cutoff_analytics = now - timedelta(days=ANALYTICS_EVENT_TTL_DAYS)
        result = await db.execute(
            delete(AnalyticsEventRow).where(AnalyticsEventRow.created_at < cutoff_analytics)
        )
        results["analytics_events"] = getattr(result, "rowcount", 0) or 0

        await db.commit()
        total = sum(results.values())
        if total > 0:
            _logger.info("Purged expired entries: %s", results)
    except Exception as exc:
        await db.rollback()
        _logger.warning("Purge failed (best-effort): %s", exc)

    return results
