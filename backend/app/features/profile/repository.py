"""LearnerProfile persistence (interface + SQLAlchemy implementation)."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.profile.models import LearnerProfile


class ProfileRepository(Protocol):
    async def get_by_user_id(self, user_id: int) -> LearnerProfile | None: ...

    async def create(self, profile: LearnerProfile) -> LearnerProfile: ...

    async def save(self, profile: LearnerProfile) -> LearnerProfile: ...


class SqlAlchemyProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> LearnerProfile | None:
        return await self._session.get(LearnerProfile, user_id)

    async def create(self, profile: LearnerProfile) -> LearnerProfile:
        self._session.add(profile)
        await self._session.commit()
        await self._session.refresh(profile)
        return profile

    async def save(self, profile: LearnerProfile) -> LearnerProfile:
        await self._session.commit()
        await self._session.refresh(profile)
        return profile
