"""Learner-profile business logic."""

from typing import Any

from app.models.learner_profile import LearnerProfile
from app.repositories.profile_repository import ProfileRepository


class ProfileService:
    def __init__(self, profiles: ProfileRepository) -> None:
        self._profiles = profiles

    async def get_or_create(self, user_id: int) -> LearnerProfile:
        profile = await self._profiles.get_by_user_id(user_id)
        if profile is None:
            profile = await self._profiles.create(LearnerProfile(user_id=user_id))
        return profile

    async def update(self, user_id: int, changes: dict[str, Any]) -> LearnerProfile:
        profile = await self.get_or_create(user_id)
        for field, value in changes.items():
            setattr(profile, field, value)
        return await self._profiles.save(profile)
