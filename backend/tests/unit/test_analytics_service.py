"""Unit tests for the analytics service (#129)."""

import pytest

from app.features.analytics.domain import (
    EVENT_ACTIVATION,
    EVENT_SESSION_COMPLETED,
    EVENT_TRANSFER_STARTED,
    AnalyticsEvent,
)
from app.features.analytics.service import AnalyticsService


class _CapturingSink:
    def __init__(self, fail=False):
        self.events: list[AnalyticsEvent] = []
        self._fail = fail

    async def emit(self, event):
        if self._fail:
            raise RuntimeError("sink down")
        self.events.append(event)


class _Counter:
    """Counts by consulting what the sink captured (completion events)."""

    def __init__(self, sink: _CapturingSink):
        self._sink = sink

    async def count_events(self, user_id, name):
        return sum(1 for e in self._sink.events if e.user_id == user_id and e.name == name)


def _service(fail=False):
    sink = _CapturingSink(fail=fail)
    return AnalyticsService(sink, _Counter(sink)), sink


@pytest.mark.asyncio
async def test_first_completion_also_emits_activation():
    service, sink = _service()
    await service.session_completed(user_id=1, session_id=10, cefr="B1", error_count=2)

    names = [e.name for e in sink.events]
    assert EVENT_SESSION_COMPLETED in names
    assert EVENT_ACTIVATION in names


@pytest.mark.asyncio
async def test_second_completion_does_not_re_emit_activation():
    service, sink = _service()
    await service.session_completed(1, 10, "B1", 2)
    await service.session_completed(1, 11, "B1", 0)

    activations = [e for e in sink.events if e.name == EVENT_ACTIVATION]
    assert len(activations) == 1  # activation is once per user


@pytest.mark.asyncio
async def test_completion_carries_no_transcript_content_only_metadata():
    service, sink = _service()
    await service.session_completed(1, 10, "A2", 3)
    completion = next(e for e in sink.events if e.name == EVENT_SESSION_COMPLETED)
    assert completion.properties == {"session_id": 10, "cefr": "A2", "error_count": 3}


@pytest.mark.asyncio
async def test_transfer_started_event():
    service, sink = _service()
    await service.transfer_started(1, "job_interview")
    e = next(e for e in sink.events if e.name == EVENT_TRANSFER_STARTED)
    assert e.properties == {"skill": "job_interview"}


@pytest.mark.asyncio
async def test_a_sink_failure_never_raises():
    service, _ = _service(fail=True)
    # Must not raise — analytics is best-effort.
    await service.session_completed(1, 10, "B1", 0)
    await service.transfer_started(1, "x")
