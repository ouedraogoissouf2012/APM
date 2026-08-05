from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.debrief.models import Debrief
from app.features.progress.service import CefrPoint
from app.features.sessions.models import ConversationSession


class SqlAlchemyProgressDataSource:
    """Aggregates progress from sessions + debriefs in two bounded queries,
    replacing the client's one-debrief-per-session fetch loop."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cefr_points(self, user_id: int) -> list[CefrPoint]:
        # Every completed session (has a debrief) with its estimate, oldest first
        # so the trend reads left-to-right in time.
        rows = await self._session.execute(
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Debrief.cefr_estimate,
            )
            .join(Debrief, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.started_at.asc())
        )
        return [
            CefrPoint(session_id=r.id, started_at=r.started_at, level=r.cefr_estimate) for r in rows
        ]

    async def recent_error_rows(self, user_id: int, session_window: int) -> list[tuple[str, str]]:
        # The most recent `session_window` debriefs, newest first; each debrief's
        # errors JSONB is expanded into (error_type, correction) rows in Python
        # (small, bounded payload — no need for a JSONB lateral join).
        debriefs = await self._session.scalars(
            select(Debrief)
            .join(ConversationSession, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.started_at.desc())
            .limit(session_window)
        )
        rows: list[tuple[str, str]] = []
        for debrief in debriefs:
            for error in debrief.errors or []:
                if not isinstance(error, dict):
                    continue
                rows.append(
                    (
                        str(error.get("error_type", "")),
                        str(error.get("correction", "")),
                    )
                )
        return rows
