"""Learner-profile business logic."""

from typing import Any

from app.features.conversation.prompt import strip_persistent_instructions
from app.features.profile.models import LearnerProfile
from app.features.profile.repository import ProfileRepository


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
            # memory_summary is injected verbatim into every system prompt, so a
            # learner-supplied edit must be sanitised exactly like the debrief's
            # automatic write is (strip_persistent_instructions) — otherwise the
            # edit endpoint becomes a prompt-injection vector. An empty string is
            # a legitimate "forget what you know about me" and passes through.
            if field == "memory_summary" and isinstance(value, str):
                value = strip_persistent_instructions(value)
            setattr(profile, field, value)
        return await self._profiles.save(profile)
