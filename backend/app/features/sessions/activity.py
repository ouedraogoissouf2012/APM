"""Pure session-activity helpers (#119): per-turn metering and staleness.

Kept free of the DB and the clock (both passed in) so the quota-metering and
lazy-reaper logic is unit-tested deterministically. The rule everywhere: server
time only, never trust the client; and one turn can never charge more than a cap.
"""

from datetime import UTC, datetime


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def elapsed_minutes(mark: datetime, now: datetime, cap: float | None = None) -> float:
    """Minutes between `mark` and `now`, never negative (clock skew -> 0) and
    optionally capped so a single long gap can't bill an unbounded amount."""
    delta = (_as_utc(now) - _as_utc(mark)).total_seconds() / 60.0
    minutes = max(0.0, delta)
    if cap is not None:
        minutes = min(minutes, cap)
    return minutes


def is_stale(last_activity: datetime, now: datetime, timeout_minutes: float) -> bool:
    """True when a session has been idle STRICTLY longer than the timeout — the
    signal the lazy reaper uses to auto-close an abandoned session. At exactly the
    timeout it is still alive (strict inequality)."""
    return elapsed_minutes(last_activity, now) > timeout_minutes
