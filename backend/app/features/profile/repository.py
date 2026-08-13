"""LearnerProfile persistence (interface + SQLAlchemy implementation)."""

from typing import Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
        # Atomic first-touch: INSERT ... ON CONFLICT DO NOTHING, then read back.
        # A plain get-then-create races two concurrent first requests for the
        # SAME new user (e.g. two devices onboarding, or the placement flow
        # racing a manual profile edit) into a double INSERT that trips
        # learner_profiles' primary-key constraint — one 500 (#362). Mirrors
        # VoiceConsentRepository.get_or_create.
        await self._session.execute(
            pg_insert(LearnerProfile)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self._session.commit()
        profile = await self.get_by_user_id(user_id)
        assert profile is not None  # just inserted, or already present
        return profile

    async def save(self, profile: LearnerProfile) -> LearnerProfile:
        await self._session.commit()
        await self._session.refresh(profile)
        return profile
