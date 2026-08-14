"""LearnerProfile persistence (interface + SQLAlchemy implementation)."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence import first_touch_by_user_id
from app.features.profile.models import LearnerProfile


class ProfileRepository(Protocol):
    async def get_by_user_id(self, user_id: int) -> LearnerProfile | None: ...

    async def get_or_create(self, user_id: int) -> LearnerProfile: ...

    async def save(self, profile: LearnerProfile) -> LearnerProfile: ...


class SqlAlchemyProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> LearnerProfile | None:
        return await self._session.get(LearnerProfile, user_id)

    async def get_or_create(self, user_id: int) -> LearnerProfile:
        # Atomic first-touch (#371, core.persistence): a plain get-then-create
        # races two concurrent first requests for the SAME new user (e.g. two
        # devices onboarding, or the placement flow racing a manual profile
        # edit) into a double INSERT that trips learner_profiles' primary-key
        # constraint — one 500 (#362). Mirrors VoiceConsentRepository.get_or_create.
        return await first_touch_by_user_id(self._session, LearnerProfile, user_id)

    async def save(self, profile: LearnerProfile) -> LearnerProfile:
        await self._session.commit()
        await self._session.refresh(profile)
        return profile
