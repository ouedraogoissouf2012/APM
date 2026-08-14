"""Product-analytics aggregation for the pilot (#129).

An internal (admin-only) summary over the append-only events: the funnel counts,
how many learners activated, and recent activity. The North Star — 'weekly
minutes of useful speech leading to a transfer SUCCESS' — needs a transfer-success
event (the evaluation loop, a later increment); until then this reports the
honest, available signals and labels the transfer metric as 'started', not
'succeeded'. `now` is injected for deterministic tests.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class AnalyticsSummary:
    # A genuine LIFETIME count: `activation` is exempt from the analytics
    # retention purge (#385, purge/task.py's ANALYTICS_RETENTION_EXEMPT_NAMES),
    # so this distinct-user count never loses an activated learner to age.
    users_activated: int
    # NOT a lifetime count, despite the name (#385): `session_completed` rows ARE
    # subject to the 30-day retention purge (they're a genuine per-event log, not
    # a funnel marker — deliberately not exempted, or this table would grow
    # unbounded again). This is really "completions in roughly the last 30 days
    # since the last purge run". If a true lifetime total is ever needed, it
    # requires a durable counter updated at emit time (the issue's #385 own
    # suggestion), not COUNT(*) over a purged table.
    completions_total: int
    completions_this_week: int
    # Same caveat as completions_total: bounded by the retention window, not lifetime.
    transfers_started_total: int


class AnalyticsAggregateSource(Protocol):
    async def distinct_users_with_event(self, name: str) -> int: ...

    async def count_event(self, name: str) -> int: ...

    async def count_event_since(self, name: str, since: datetime) -> int: ...


def _week_start(today: date) -> datetime:
    monday = date.fromordinal(today.toordinal() - today.weekday())
    return datetime(monday.year, monday.month, monday.day)


class AnalyticsAggregateService:
    def __init__(self, source: AnalyticsAggregateSource) -> None:
        self._source = source

    async def summary(self, now: datetime) -> AnalyticsSummary:
        from app.features.analytics.domain import (
            EVENT_ACTIVATION,
            EVENT_SESSION_COMPLETED,
            EVENT_TRANSFER_STARTED,
        )

        return AnalyticsSummary(
            users_activated=await self._source.distinct_users_with_event(EVENT_ACTIVATION),
            completions_total=await self._source.count_event(EVENT_SESSION_COMPLETED),
            completions_this_week=await self._source.count_event_since(
                EVENT_SESSION_COMPLETED, _week_start(now.date())
            ),
            transfers_started_total=await self._source.count_event(EVENT_TRANSFER_STARTED),
        )
