"""Learner progress aggregation.

Replaces a client-side N+1 (the mobile app fetched one debrief per recent
session to compute the CEFR trend and recurring errors). The backend now
aggregates both in one place from the sessions + debriefs it already stores.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CefrPoint:
    session_id: int
    started_at: datetime
    level: str


@dataclass(frozen=True)
class RecurringError:
    error_type: str
    count: int
    latest_correction: str


@dataclass
class ProgressSnapshot:
    cefr_trend: list[CefrPoint] = field(default_factory=list)
    recurring_errors: list[RecurringError] = field(default_factory=list)


class ProgressDataSource(Protocol):
    async def cefr_points(self, user_id: int) -> list[CefrPoint]:
        """Completed sessions with a CEFR estimate, oldest first."""
        ...

    async def recent_error_rows(self, user_id: int, session_window: int) -> list[tuple[str, str]]:
        """(error_type, correction) rows from the learner's most recent debriefs,
        newest debrief first. One row per error."""
        ...


class ProgressService:
    # Mirror the previous client window/limits so the surfaced numbers are stable.
    RECENT_DEBRIEFS_WINDOW = 5
    MAX_RECURRING_ERRORS = 3

    def __init__(self, source: ProgressDataSource) -> None:
        self._source = source

    async def snapshot(self, user_id: int) -> ProgressSnapshot:
        trend = await self._source.cefr_points(user_id)
        rows = await self._source.recent_error_rows(user_id, self.RECENT_DEBRIEFS_WINDOW)
        return ProgressSnapshot(
            cefr_trend=trend,
            recurring_errors=self._recurring(rows),
        )

    def _recurring(self, rows: list[tuple[str, str]]) -> list[RecurringError]:
        counts: Counter[str] = Counter()
        latest_correction: dict[str, str] = {}
        # rows are newest-first, so the FIRST time we see a type carries its most
        # recent correction; don't overwrite it with older ones.
        for error_type, correction in rows:
            etype = error_type.strip() or "other"
            counts[etype] += 1
            latest_correction.setdefault(etype, correction)

        recurring = [
            RecurringError(
                error_type=etype,
                count=count,
                latest_correction=latest_correction.get(etype, ""),
            )
            for etype, count in counts.items()
        ]
        # Most frequent first; ties broken alphabetically for a stable order.
        recurring.sort(key=lambda r: (-r.count, r.error_type))
        return recurring[: self.MAX_RECURRING_ERRORS]
