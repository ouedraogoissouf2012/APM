"""Pure streak logic — how a day of activity updates the consecutive-day count.

Kept free of I/O and the wall clock (today is passed in) so every transition is
deterministically unit-testable.
"""

from dataclasses import dataclass
from datetime import date, timedelta

# The weekly practice goal a new account starts with (editable by the learner).
DEFAULT_WEEKLY_GOAL_MINUTES = 30


@dataclass
class StreakState:
    current_streak: int = 0
    longest_streak: int = 0
    last_active_date: date | None = None


def register_active_day(state: StreakState, today: date) -> StreakState:
    """Record that the learner practised on `today`.

    - Same day already counted -> unchanged (idempotent within a day).
    - Yesterday was the last active day -> streak extends by one.
    - Any older last active day (a gap) or none -> streak restarts at 1.
    `longest_streak` never decreases.
    """
    last = state.last_active_date
    if last == today:
        return state  # already counted today

    if last is not None and last == today - timedelta(days=1):
        current = state.current_streak + 1
    else:
        current = 1  # first ever, or the streak was broken by a missed day

    return StreakState(
        current_streak=current,
        longest_streak=max(state.longest_streak, current),
        last_active_date=today,
    )


def current_streak_for(state: StreakState, today: date) -> int:
    """The streak as it should be DISPLAYED today: a streak whose last active day
    is neither today nor yesterday is already broken and reads as 0, even though
    the stored value only resets on the next active day."""
    last = state.last_active_date
    if last is None:
        return 0
    if last == today or last == today - timedelta(days=1):
        return state.current_streak
    return 0
