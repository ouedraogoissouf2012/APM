"""Unit tests for the streak read/update service."""

from datetime import date, timedelta

import pytest

from app.features.streaks.service import (
    MAX_WEEKLY_GOAL_MINUTES,
    MIN_WEEKLY_GOAL_MINUTES,
    StreakService,
)

# A Wednesday, so week_start (Monday) is 2 days earlier.
TODAY = date(2026, 8, 5)


class _StubSource:
    def __init__(self, fields, minutes=0.0):
        self._fields = fields
        self._minutes = minutes
        self.saved_goal: int | None = None
        self.since_seen: date | None = None

    async def get_streak_fields(self, user_id):
        return self._fields

    async def minutes_since(self, user_id, since):
        self.since_seen = since
        return self._minutes

    async def set_weekly_goal(self, user_id, minutes):
        self.saved_goal = minutes


@pytest.mark.asyncio
async def test_snapshot_returns_displayed_streak_and_weekly_minutes():
    source = _StubSource((5, 9, TODAY, 30), minutes=18.7)
    service = StreakService(source)
    snap = await service.snapshot(1, TODAY)
    assert snap.current_streak == 5
    assert snap.longest_streak == 9
    assert snap.weekly_goal_minutes == 30
    assert snap.minutes_this_week == 18  # truncated to int


@pytest.mark.asyncio
async def test_snapshot_shows_zero_when_streak_is_broken():
    three_days_ago = TODAY - timedelta(days=3)
    source = _StubSource((5, 9, three_days_ago, 30))
    snap = await StreakService(source).snapshot(1, TODAY)
    assert snap.current_streak == 0  # broken
    assert snap.longest_streak == 9  # record kept


@pytest.mark.asyncio
async def test_snapshot_sums_minutes_from_monday_of_this_week():
    source = _StubSource((1, 1, TODAY, 30))
    await StreakService(source).snapshot(1, TODAY)
    assert source.since_seen == date(2026, 8, 3)  # Monday


@pytest.mark.asyncio
async def test_snapshot_is_none_for_unknown_user():
    source = _StubSource(None)
    assert await StreakService(source).snapshot(1, TODAY) is None


@pytest.mark.asyncio
async def test_set_weekly_goal_persists_and_returns_value():
    source = _StubSource((0, 0, None, 30))
    stored = await StreakService(source).set_weekly_goal(1, 60)
    assert stored == 60
    assert source.saved_goal == 60


@pytest.mark.asyncio
async def test_weekly_goal_is_clamped_to_a_sane_range():
    source = _StubSource((0, 0, None, 30))
    service = StreakService(source)
    assert await service.set_weekly_goal(1, 0) == MIN_WEEKLY_GOAL_MINUTES
    assert await service.set_weekly_goal(1, 999999) == MAX_WEEKLY_GOAL_MINUTES
