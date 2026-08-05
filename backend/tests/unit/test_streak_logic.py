"""Unit tests for the pure streak logic."""

from datetime import date, timedelta

from app.features.streaks.logic import (
    StreakState,
    current_streak_for,
    register_active_day,
)

TODAY = date(2026, 8, 5)
YESTERDAY = TODAY - timedelta(days=1)


def test_first_ever_activity_starts_a_streak_of_one():
    state = register_active_day(StreakState(), TODAY)
    assert state.current_streak == 1
    assert state.longest_streak == 1
    assert state.last_active_date == TODAY


def test_activity_on_consecutive_days_extends_the_streak():
    state = StreakState(current_streak=3, longest_streak=3, last_active_date=YESTERDAY)
    state = register_active_day(state, TODAY)
    assert state.current_streak == 4
    assert state.longest_streak == 4


def test_second_activity_same_day_is_idempotent():
    state = StreakState(current_streak=2, longest_streak=5, last_active_date=TODAY)
    state = register_active_day(state, TODAY)
    assert state.current_streak == 2  # unchanged
    assert state.last_active_date == TODAY


def test_a_missed_day_restarts_the_streak_at_one():
    two_days_ago = TODAY - timedelta(days=2)
    state = StreakState(current_streak=6, longest_streak=6, last_active_date=two_days_ago)
    state = register_active_day(state, TODAY)
    assert state.current_streak == 1
    # Longest is a record — it must not drop.
    assert state.longest_streak == 6


def test_longest_streak_never_decreases():
    state = StreakState(current_streak=1, longest_streak=10, last_active_date=YESTERDAY)
    state = register_active_day(state, TODAY)
    assert state.longest_streak == 10


def test_displayed_streak_is_intact_when_last_active_is_today_or_yesterday():
    assert current_streak_for(StreakState(5, 5, TODAY), TODAY) == 5
    assert current_streak_for(StreakState(5, 5, YESTERDAY), TODAY) == 5


def test_displayed_streak_is_zero_once_a_day_was_missed():
    two_days_ago = TODAY - timedelta(days=2)
    # Stored value is still 5, but for display it is already broken.
    assert current_streak_for(StreakState(5, 5, two_days_ago), TODAY) == 0


def test_displayed_streak_is_zero_with_no_history():
    assert current_streak_for(StreakState(), TODAY) == 0
