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
        self, user_id: int, limit: int
    ) -> list[tuple[ConversationSession, str | None]]: ...

    async def add(self, session: ConversationSession) -> ConversationSession: ...

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
        self, user_id: int, limit: int
    ) -> list[tuple[ConversationSession, str | None]]:
        result = await self._session.execute(
            select(ConversationSession, Debrief.cefr_estimate)
            .outerjoin(Debrief, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.started_at.desc(), ConversationSession.id.desc())
            .limit(limit)
        )
        return [(session, cefr) for session, cefr in result.all()]

    async def add(self, session: ConversationSession) -> ConversationSession:
        self._session.add(session)
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def commit(self) -> None:
        await self._session.commit()
