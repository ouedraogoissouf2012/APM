"""ConversationSession persistence (interface + SQLAlchemy implementation).

Exposes `commit()` so the service can group the lock + checks + insert of a
"start session" use case into a single atomic transaction.
"""

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.debrief.models import Debrief
from app.features.sessions.models import ConversationSession


class SessionRepository(Protocol):
    async def get(self, session_id: int) -> ConversationSession | None: ...

    async def get_active_for_user(self, user_id: int) -> ConversationSession | None: ...

    async def list_recent_for_user(
        self, user_id: int, limit: int, *, before_id: int | None = None
    ) -> list[tuple[ConversationSession, str | None]]: ...

    async def add(self, session: ConversationSession) -> ConversationSession: ...

    async def refresh(self, session: ConversationSession) -> None:
        """Re-read a loaded session from the DB (e.g. after taking a lock) so a
        field a concurrent path committed — like last_activity_at — is not stale."""
        ...

    async def commit(self) -> None: ...


class SqlAlchemySessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: int) -> ConversationSession | None:
        return await self._session.get(ConversationSession, session_id)

    async def get_active_for_user(self, user_id: int) -> ConversationSession | None:
        return await self._session.scalar(
            select(ConversationSession).where(
                ConversationSession.user_id == user_id,
                ConversationSession.ended_at.is_(None),
            )
        )

    async def list_recent_for_user(
        self, user_id: int, limit: int, *, before_id: int | None = None
    ) -> list[tuple[ConversationSession, str | None]]:
        q = (
            select(ConversationSession, Debrief.cefr_estimate)
            .outerjoin(Debrief, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
        )
        if before_id is not None:
            cursor = await self.get(before_id)
            if cursor is not None and cursor.user_id == user_id:
                q = q.where(
                    (ConversationSession.started_at < cursor.started_at)
                    | (
                        (ConversationSession.started_at == cursor.started_at)
                        & (ConversationSession.id < cursor.id)
                    )
                )
        result = await self._session.execute(
            q.order_by(ConversationSession.started_at.desc(), ConversationSession.id.desc()).limit(
                limit
            )
        )
        return [(session, cefr) for session, cefr in result.all()]

    async def add(self, session: ConversationSession) -> ConversationSession:
        self._session.add(session)
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def refresh(self, session: ConversationSession) -> None:
        await self._session.refresh(session)

    async def commit(self) -> None:
        await self._session.commit()
