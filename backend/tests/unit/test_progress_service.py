"""Unit tests for the progress aggregation service (replaces the client N+1)."""

from datetime import UTC, datetime

import pytest

from app.features.progress.service import CefrPoint, ProgressService


class _StubSource:
    def __init__(self, points, rows):
        self._points = points
        self._rows = rows
        self.window_seen: int | None = None

    async def cefr_points(self, user_id):
        return self._points

    async def recent_error_rows(self, user_id, session_window):
        self.window_seen = session_window
        return self._rows


def _dt(day):
    return datetime(2026, 8, day, tzinfo=UTC)


@pytest.mark.asyncio
async def test_returns_the_cefr_trend_as_is():
    points = [
        CefrPoint(session_id=1, started_at=_dt(1), level="A1"),
        CefrPoint(session_id=2, started_at=_dt(2), level="A2"),
    ]
    service = ProgressService(_StubSource(points, []))
    snap = await service.snapshot(user_id=1)
    assert [p.level for p in snap.cefr_trend] == ["A1", "A2"]


@pytest.mark.asyncio
async def test_recurring_errors_counted_and_sorted_by_frequency():
    # newest-first rows
    rows = [
        ("verb_tense", "I went"),
        ("article", "a cat"),
        ("verb_tense", "she runs"),
        ("verb_tense", "they were"),
        ("article", "the sun"),
    ]
    service = ProgressService(_StubSource([], rows))
    snap = await service.snapshot(1)

    assert [(e.error_type, e.count) for e in snap.recurring_errors] == [
        ("verb_tense", 3),
        ("article", 2),
    ]


@pytest.mark.asyncio
async def test_latest_correction_is_the_most_recent_occurrence():
    # rows newest-first: the first verb_tense row is the most recent.
    rows = [("verb_tense", "MOST RECENT"), ("verb_tense", "older")]
    service = ProgressService(_StubSource([], rows))
    snap = await service.snapshot(1)
    assert snap.recurring_errors[0].latest_correction == "MOST RECENT"


@pytest.mark.asyncio
async def test_blank_error_type_falls_back_to_other():
    service = ProgressService(_StubSource([], [("", "x"), ("  ", "y")]))
    snap = await service.snapshot(1)
    assert snap.recurring_errors[0].error_type == "other"
    assert snap.recurring_errors[0].count == 2


@pytest.mark.asyncio
async def test_caps_to_three_recurring_errors():
    rows = [(t, "c") for t in ["a", "b", "c", "d", "e"]]
    service = ProgressService(_StubSource([], rows))
    snap = await service.snapshot(1)
    assert len(snap.recurring_errors) == 3


@pytest.mark.asyncio
async def test_passes_the_configured_session_window_to_the_source():
    source = _StubSource([], [])
    service = ProgressService(source)
    await service.snapshot(1)
    assert source.window_seen == ProgressService.RECENT_DEBRIEFS_WINDOW


@pytest.mark.asyncio
async def test_empty_history_yields_empty_snapshot():
    service = ProgressService(_StubSource([], []))
    snap = await service.snapshot(1)
    assert snap.cefr_trend == []
    assert snap.recurring_errors == []
