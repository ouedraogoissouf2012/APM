"""Unit tests for the analytics aggregation service (#129)."""

from datetime import UTC, datetime

import pytest

from app.features.analytics.aggregate import AnalyticsAggregateService
from app.features.analytics.domain import (
    EVENT_ACTIVATION,
    EVENT_SESSION_COMPLETED,
    EVENT_TRANSFER_STARTED,
)

# A Wednesday, so week_start (Monday) is 2 days earlier.
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _StubSource:
    def __init__(self, distinct=None, totals=None, since=None):
        self._distinct = distinct or {}
        self._totals = totals or {}
        self._since = since or {}
        self.since_arg: datetime | None = None

    async def distinct_users_with_event(self, name):
        return self._distinct.get(name, 0)

    async def count_event(self, name):
        return self._totals.get(name, 0)

    async def count_event_since(self, name, since):
        self.since_arg = since
        return self._since.get(name, 0)


@pytest.mark.asyncio
async def test_summary_maps_each_metric():
    source = _StubSource(
        distinct={EVENT_ACTIVATION: 12},
        totals={EVENT_SESSION_COMPLETED: 40, EVENT_TRANSFER_STARTED: 7},
        since={EVENT_SESSION_COMPLETED: 9},
    )
    summary = await AnalyticsAggregateService(source).summary(NOW)

    assert summary.users_activated == 12
    assert summary.completions_total == 40
    assert summary.completions_this_week == 9
    assert summary.transfers_started_total == 7


@pytest.mark.asyncio
async def test_this_week_is_measured_from_monday():
    source = _StubSource()
    await AnalyticsAggregateService(source).summary(NOW)
    assert source.since_arg == datetime(2026, 8, 3)  # Monday of NOW's week


@pytest.mark.asyncio
async def test_empty_analytics_yields_zeros():
    summary = await AnalyticsAggregateService(_StubSource()).summary(NOW)
    assert summary.users_activated == 0
    assert summary.completions_total == 0
    assert summary.completions_this_week == 0
    assert summary.transfers_started_total == 0
