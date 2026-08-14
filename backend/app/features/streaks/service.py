"""Streak & weekly-goal read/update service.

The streak itself is updated on every turn (see SessionService.record_turn_activity);
this service exposes the current state for display and lets the learner edit the
weekly minutes goal. `today` is injected for deterministic tests.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.features.streaks.logic import StreakState as _StreakState
from app.features.streaks.logic import current_streak_for
from app.features.streaks.schemas import (
    MAX_WEEKLY_GOAL_MINUTES,
    MIN_WEEKLY_GOAL_MINUTES,
)


@dataclass(frozen=True)
class StreakSnapshot:
    current_streak: int
    longest_streak: int
    weekly_goal_minutes: int
    minutes_this_week: int


class StreakDataSource(Protocol):
    async def get_streak_fields(self, user_id: int) -> tuple[int, int, date | None, int] | None:
        """(current_streak, longest_streak, last_active_date, weekly_goal_minutes)."""
        ...

    async def minutes_since(self, user_id: int, since: date) -> float:
        """Total practised minutes for the user from `since` (inclusive) to now."""
        ...

    async def set_weekly_goal(self, user_id: int, minutes: int) -> None: ...


def _week_start(today: date) -> date:
    """Monday of the current week."""
    return date.fromordinal(today.toordinal() - today.weekday())


class StreakService:
    def __init__(self, source: StreakDataSource) -> None:
        self._source = source

    async def snapshot(self, user_id: int, today: date) -> StreakSnapshot | None:
        fields = await self._source.get_streak_fields(user_id)
        if fields is None:
            return None
        current, longest, last_active, goal = fields
        displayed = current_streak_for(
            _StreakState(
                current_streak=current, longest_streak=longest, last_active_date=last_active
            ),
            today,
        )
        minutes = await self._source.minutes_since(user_id, _week_start(today))
        return StreakSnapshot(
            current_streak=displayed,
            longest_streak=longest,
            weekly_goal_minutes=goal,
            minutes_this_week=int(minutes),
        )

    async def set_weekly_goal(self, user_id: int, minutes: int) -> int:
        """Clamp to a sane range and persist. Returns the stored value."""
        clamped = max(MIN_WEEKLY_GOAL_MINUTES, min(MAX_WEEKLY_GOAL_MINUTES, minutes))
        await self._source.set_weekly_goal(user_id, clamped)
        return clamped
