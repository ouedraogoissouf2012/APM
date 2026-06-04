from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.debrief.models import Debrief


class DebriefRepository(Protocol):
    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief: ...

    async def get_by_session(self, session_id: int) -> Debrief | None: ...


class SqlAlchemyDebriefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief:
        existing = await self.get_by_session(session_id)
        if existing is None:
            existing = Debrief(
                session_id=session_id, cefr_estimate=cefr_estimate, summary=summary, errors=errors
            )
            self._session.add(existing)
        else:
            existing.cefr_estimate = cefr_estimate
            existing.summary = summary
            existing.errors = errors
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def get_by_session(self, session_id: int) -> Debrief | None:
        return await self._session.scalar(select(Debrief).where(Debrief.session_id == session_id))
