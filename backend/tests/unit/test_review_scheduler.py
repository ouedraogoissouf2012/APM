"""Unit tests for the spaced-repetition scheduler (J+1/J+3/J+7, mastery at 3)."""

from datetime import UTC, datetime, timedelta

from app.features.review.scheduler import (
    INTERVAL_DAYS,
    MASTERY_STREAK,
    STATUS_DUE,
    STATUS_MASTERED,
    ReviewState,
    on_error_absent,
    on_error_seen,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def test_seeing_an_error_schedules_it_at_j_plus_1():
    state = on_error_seen(ReviewState(), correction="I went", now=NOW)
    assert state.stage == 0
    assert state.status == STATUS_DUE
    assert state.next_review_at == NOW + timedelta(days=1)
    assert state.latest_correction == "I went"


def test_a_clean_session_before_the_review_date_does_not_advance():
    # The core of the fix: staying clean BEFORE next_review_at proves nothing, so
    # the schedule is untouched — no streak growth, no reschedule.
    seen = on_error_seen(ReviewState(), "c", NOW)  # due at NOW+1d
    early = on_error_absent(seen, NOW + timedelta(hours=2))  # same afternoon
    assert early.clean_streak == 0
    assert early.status == STATUS_DUE
    assert early.next_review_at == seen.next_review_at  # unchanged


def test_three_clean_sessions_the_same_day_do_not_master():
    # Exit criterion (pure-logic level): a fault then repeated clean sessions the
    # same day must NOT become mastered.
    state = on_error_seen(ReviewState(), "c", NOW)
    for _ in range(MASTERY_STREAK + 2):
        state = on_error_absent(state, NOW + timedelta(hours=1))
    assert state.status != STATUS_MASTERED
    assert state.clean_streak == 0


def test_clean_sessions_climb_the_ladder_only_when_spaced_past_each_interval():
    state = on_error_seen(ReviewState(), "c", NOW)  # scheduled J+1, stage 0
    # Each clean session happens AT its review date, so the interval has elapsed.
    due1 = state.next_review_at
    state = on_error_absent(state, due1)  # clean #1 -> stage 1 (J+3 from due1)
    assert state.stage == 1
    assert state.status == STATUS_DUE
    assert state.next_review_at == due1 + timedelta(days=INTERVAL_DAYS[1])
    due2 = state.next_review_at
    state = on_error_absent(state, due2)  # clean #2 -> stage 2 (J+7 from due2)
    assert state.stage == 2
    assert state.status == STATUS_DUE
    assert state.next_review_at == due2 + timedelta(days=INTERVAL_DAYS[2])
    state = on_error_absent(state, state.next_review_at)  # clean #3 -> mastered
    assert state.status == STATUS_MASTERED


def test_mastered_only_after_three_spaced_clean_sessions():
    state = on_error_seen(ReviewState(), "c", NOW)
    for _ in range(MASTERY_STREAK):
        # Advance to each item's own due date before the next clean session.
        state = on_error_absent(state, state.next_review_at)
    assert state.status == STATUS_MASTERED
    assert state.clean_streak == MASTERY_STREAK
    assert state.next_review_at is None


def test_interval_is_capped_at_the_last_rung():
    # Even before mastery, the stage never indexes past J+7.
    state = ReviewState(stage=2, clean_streak=0, status=STATUS_DUE)
    state = on_error_absent(state, NOW)
    assert state.stage == len(INTERVAL_DAYS) - 1
    assert state.next_review_at == NOW + timedelta(days=INTERVAL_DAYS[-1])


def test_reappearing_error_resets_to_j_plus_1_and_clears_streak():
    state = ReviewState(stage=2, clean_streak=2, status=STATUS_DUE)
    state = on_error_seen(state, "she runs", NOW)
    assert state.stage == 0
    assert state.clean_streak == 0
    assert state.next_review_at == NOW + timedelta(days=1)


def test_reappearing_error_reactivates_a_mastered_type():
    mastered = ReviewState(stage=2, clean_streak=3, status=STATUS_MASTERED, next_review_at=None)
    state = on_error_seen(mastered, "oops again", NOW)
    assert state.status == STATUS_DUE
    assert state.next_review_at == NOW + timedelta(days=1)


def test_clean_session_does_not_disturb_an_already_mastered_type():
    mastered = ReviewState(stage=2, clean_streak=3, status=STATUS_MASTERED)
    state = on_error_absent(mastered, NOW)
    assert state.status == STATUS_MASTERED
    assert state.next_review_at is None


def test_seeing_without_a_new_correction_keeps_the_previous_one():
    state = ReviewState(latest_correction="old fix")
    state = on_error_seen(state, correction="", now=NOW)
    assert state.latest_correction == "old fix"
