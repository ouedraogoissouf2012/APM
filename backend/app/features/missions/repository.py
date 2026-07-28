from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.missions.models import Mission


class MissionRepository(Protocol):
    async def add(
        self,
        user_id: int,
        source_type: str,
        persona: str,
        goal: str,
        likely_questions: list[str],
        system_prompt: str,
    ) -> Mission: ...

    async def get_owned(self, mission_id: int, user_id: int) -> Mission | None: ...


class SqlAlchemyMissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        user_id: int,
        source_type: str,
        persona: str,
        goal: str,
        likely_questions: list[str],
        system_prompt: str,
    ) -> Mission:
        mission = Mission(
            user_id=user_id,
            source_type=source_type,
            persona=persona,
            goal=goal,
            likely_questions=likely_questions,
            system_prompt=system_prompt,
        )
        self._session.add(mission)
        await self._session.commit()
        await self._session.refresh(mission)
        return mission

    async def get_owned(self, mission_id: int, user_id: int) -> Mission | None:
        return await self._session.scalar(
            select(Mission).where(Mission.id == mission_id, Mission.user_id == user_id)
        )
