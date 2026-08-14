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

    async def _emit(self, event: AnalyticsEvent) -> bool:
        """Emit one event best-effort. Returns whether it was actually recorded, so
        a derived event (activation) is never emitted for a completion that failed."""
        try:
            await self._sink.emit(event)
            return True
        except Exception:
            logging.getLogger(__name__).warning(
                "analytics emit failed (%s)", event.name, exc_info=True
            )
            return False

    async def session_completed(
        self, user_id: int, session_id: int, cefr: str, error_count: int
    ) -> None:
        """Emit completion, plus activation the first time a user completes one.

        Fully best-effort: even the activation-detecting COUNT is guarded, so an
        analytics read failure can never break the caller (the debrief that emitted
        it) — the completion is still recorded, only the activation is skipped.
        Activation fires only when its completion was actually recorded AND it is the
        user's first — never an activation without a completion behind it."""
        try:
            # Detect activation BEFORE emitting completion (so the count is prior).
            prior: int | None = await self._counter.count_events(user_id, EVENT_SESSION_COMPLETED)
        except Exception:
            # Can't confirm it's the first; still record the completion, skip activation.
            logging.getLogger(__name__).warning("analytics count failed", exc_info=True)
            prior = None
        completed = await self._emit(
            AnalyticsEvent(
                name=EVENT_SESSION_COMPLETED,
                user_id=user_id,
                properties={"session_id": session_id, "cefr": cefr, "error_count": error_count},
            )
        )
        # First-ever completion AND it was actually recorded -> activation. A DB
        # partial-unique index on activation makes the write idempotent, so a
        # cross-session race can't produce two activations (the loser's commit fails
        # and is swallowed here). This exactly-once guarantee relies on the
        # activation row never being deleted: it is exempt from the analytics
        # retention purge (#385, purge/task.py) specifically so this index keeps
        # blocking a second insert for the lifetime of the account — if it were
        # ever purged, `prior` (session_completed count) would stay >0 for an
        # active user and activation would never be re-emitted.
        if completed and prior == 0:
            await self._emit(AnalyticsEvent(name=EVENT_ACTIVATION, user_id=user_id))

    async def transfer_started(self, user_id: int, skill: str) -> None:
        await self._emit(
            AnalyticsEvent(
                name=EVENT_TRANSFER_STARTED, user_id=user_id, properties={"skill": skill}
            )
        )
