"""Analytics emission service (#129).

Wraps a sink with the small amount of product logic the events need — chiefly
'activation = the user's FIRST completed session'. Best-effort throughout: an
analytics failure is swallowed so it can never break the feature that emitted it.
"""

import logging
from typing import Protocol

from app.features.analytics.domain import (
    EVENT_ACTIVATION,
    EVENT_SESSION_COMPLETED,
    EVENT_TRANSFER_STARTED,
    AnalyticsEvent,
    AnalyticsSink,
)


class CompletionCounter(Protocol):
    async def count_events(self, user_id: int, name: str) -> int:
        """How many events of `name` the user already has (to detect the first)."""
        ...


class AnalyticsService:
    def __init__(self, sink: AnalyticsSink, counter: CompletionCounter) -> None:
        self._sink = sink
        self._counter = counter

    async def _emit(self, event: AnalyticsEvent) -> None:
        try:
            await self._sink.emit(event)
        except Exception:
            logging.getLogger(__name__).warning(
                "analytics emit failed (%s)", event.name, exc_info=True
            )

    async def session_completed(
        self, user_id: int, session_id: int, cefr: str, error_count: int
    ) -> None:
        """Emit completion, plus activation the first time a user completes one."""
        # Detect activation BEFORE emitting completion (so the count is prior).
        prior = await self._counter.count_events(user_id, EVENT_SESSION_COMPLETED)
        await self._emit(
            AnalyticsEvent(
                name=EVENT_SESSION_COMPLETED,
                user_id=user_id,
                properties={"session_id": session_id, "cefr": cefr, "error_count": error_count},
            )
        )
        if prior == 0:
            await self._emit(AnalyticsEvent(name=EVENT_ACTIVATION, user_id=user_id))

    async def transfer_started(self, user_id: int, skill: str) -> None:
        await self._emit(
            AnalyticsEvent(
                name=EVENT_TRANSFER_STARTED, user_id=user_id, properties={"skill": skill}
            )
        )
