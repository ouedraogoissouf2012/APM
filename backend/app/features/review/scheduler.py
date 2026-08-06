"""Spaced-repetition scheduling for recurring error types (pure logic).

Fixed intervals J+1 / J+3 / J+7 (the issue's spec). When an error type appears in
a session it is (re)scheduled at J+1 and its stage resets; if it does NOT appear,
its clean streak grows and, after MASTERY_STREAK clean sessions, it is mastered.

Kept free of I/O and of the wall clock: the current time is passed in, so the
whole ladder is deterministically unit-testable.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

# The J+1 / J+3 / J+7 ladder, in days. Re-appearing resets to stage 0 (J+1).
INTERVAL_DAYS = (1, 3, 7)
# Consecutive sessions without an error type before it is considered mastered.
MASTERY_STREAK = 3

STATUS_DUE = "due"
STATUS_MASTERED = "mastered"


@dataclass
class ReviewState:
    """The mutable SRS fields of one (user, error_type) item."""

    stage: int = 0
    clean_streak: int = 0
    status: str = STATUS_DUE
    next_review_at: datetime | None = None
    latest_correction: str = ""


def on_error_seen(state: ReviewState, correction: str, now: datetime) -> ReviewState:
    """The error type appeared this session: reset to the first interval (J+1),
    clear the clean streak, and re-activate it if it had been mastered."""
    return ReviewState(
        stage=0,
        clean_streak=0,
        status=STATUS_DUE,
        next_review_at=now + timedelta(days=INTERVAL_DAYS[0]),
        latest_correction=correction or state.latest_correction,
    )


def on_error_absent(state: ReviewState, now: datetime) -> ReviewState:
    """The error type did NOT appear this session.

    A clean session only counts toward mastery once the spacing interval has
    ELAPSED. If the item is not due yet (``now < next_review_at``), nothing changes:
    staying clean *before* the review date is expected and proves nothing about
    retention — otherwise three sessions the same afternoon would 'master' a fault
    the learner just made, and the J+1/J+3/J+7 ladder would be computed then ignored
    (the original bug). Once due (``now >= next_review_at``, or never scheduled),
    grow the clean streak; at MASTERY_STREAK mark it mastered, else advance one rung
    up the ladder (J+1 -> J+3 -> J+7, capped) and reschedule from ``now``."""
    if state.status == STATUS_MASTERED:
        return state  # already mastered; a clean session doesn't change it

    if state.next_review_at is not None and now < state.next_review_at:
        return state  # not due yet — keep waiting, the schedule is untouched

    clean_streak = state.clean_streak + 1
    if clean_streak >= MASTERY_STREAK:
        return ReviewState(
            stage=state.stage,
            clean_streak=clean_streak,
            status=STATUS_MASTERED,
            next_review_at=None,
            latest_correction=state.latest_correction,
        )

    next_stage = min(state.stage + 1, len(INTERVAL_DAYS) - 1)
    return ReviewState(
        stage=next_stage,
        clean_streak=clean_streak,
        status=STATUS_DUE,
        next_review_at=now + timedelta(days=INTERVAL_DAYS[next_stage]),
        latest_correction=state.latest_correction,
    )
