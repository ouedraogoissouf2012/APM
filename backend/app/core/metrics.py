"""In-process counters for ops-visible best-effort failures (#435).

Not Prometheus: a JSON snapshot at GET /metrics so a scrape or a human can
see metering/purge failures that would otherwise only exist as warnings.
"""

from collections import Counter

METER_FAILURES = "meter_failures"
PURGE_FAILURES = "purge_failures"
PURGE_LOCK_SKIPS = "purge_lock_skips"

_counts: Counter[str] = Counter()


def inc(name: str) -> None:
    _counts[name] += 1
    if name == METER_FAILURES:
        from app.core.alerts import notify

        notify("meter_failures", "meter_failures incremented")


def snapshot() -> dict[str, int]:
    return dict(_counts)


def reset() -> None:
    _counts.clear()
