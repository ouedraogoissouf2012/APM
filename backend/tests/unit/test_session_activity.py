"""Unit tests for the pure session-activity logic (#119).

The quota bug: usage is only counted at /end, so a client that never ends a
session runs unlimited LLM+TTS turns for free, and a stale active session can lock
the user out forever. These pure helpers underpin the fix — per-turn metering and
a lazy reaper — and are tested here without a DB or the clock.
"""

from datetime import UTC, datetime, timedelta

from app.features.sessions.activity import elapsed_minutes, is_stale


def _t(minute: int) -> datetime:
    return datetime(2026, 1, 1, 12, minute, 0, tzinfo=UTC)


def test_elapsed_minutes_between_two_instants():
    assert elapsed_minutes(_t(0), _t(3)) == 3.0


def test_elapsed_minutes_never_negative_on_clock_skew():
    # If "now" is earlier than the mark (clock skew), meter nothing, not a credit.
    assert elapsed_minutes(_t(5), _t(3)) == 0.0


def test_elapsed_minutes_is_capped_to_bound_a_long_gap():
    # A huge gap (client slept for hours between turns) must not bill the whole gap:
    # cap it so one turn can never charge more than the cap.
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    much_later = start + timedelta(hours=10)
    assert elapsed_minutes(start, much_later, cap=5.0) == 5.0


def test_elapsed_minutes_handles_naive_datetimes():
    naive_a = datetime(2026, 1, 1, 12, 0, 0)
    naive_b = datetime(2026, 1, 1, 12, 2, 0)
    assert elapsed_minutes(naive_a, naive_b) == 2.0


def test_is_stale_true_when_idle_beyond_timeout():
    assert is_stale(last_activity=_t(0), now=_t(31), timeout_minutes=30) is True


def test_is_stale_false_when_recently_active():
    assert is_stale(last_activity=_t(0), now=_t(10), timeout_minutes=30) is False


def test_is_stale_exactly_at_timeout_is_not_stale():
    # Boundary: at exactly the timeout the session is still considered alive.
    assert is_stale(last_activity=_t(0), now=_t(30), timeout_minutes=30) is False
