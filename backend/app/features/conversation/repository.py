from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.models import Transcript


class TranscriptRepository(Protocol):
    async def save(self, session_id: int, turns: list[dict]) -> Transcript: ...

    async def get_by_session(self, session_id: int) -> Transcript | None: ...


class SqlAlchemyTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, session_id: int, turns: list[dict]) -> Transcript:
        existing = await self.get_by_session(session_id)
        if existing is None:
            existing = Transcript(session_id=session_id, turns=turns)
            self._session.add(existing)
        else:
            existing.turns = turns
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def get_by_session(self, session_id: int) -> Transcript | None:
        return await self._session.scalar(
            select(Transcript).where(Transcript.session_id == session_id)
        )
