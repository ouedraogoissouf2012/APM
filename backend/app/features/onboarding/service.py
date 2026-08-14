"""Onboarding placement business logic.

A new learner speaks a short (~60 s) guided placement instead of everyone
starting at A1: their spoken answers are run through the existing debrief
analyzer to estimate a starting CEFR level, and their stated interests/goal
pre-fill the profile so the very first real conversation is already personalised.

Reuses the debrief analyzer (CEFR estimation) and the profile/user repositories;
no new estimation logic. The placement is optional — a learner who skips it just
keeps the A1 default and their level self-adjusts through later debriefs.
"""

from dataclasses import dataclass

from app.core.llm.messages import ROLE_USER
from app.core.prompt_safety import strip_persistent_instructions
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.domain import VALID_CEFR
from app.features.profile.repository import ProfileRepository
from app.features.profile.service import ProfileService

# Bounds so a placement submission cannot bloat the profile or the analyzer call.
_MAX_ANSWERS = 6
_MAX_ANSWER_CHARS = 1000
_MAX_INTERESTS = 10


@dataclass(frozen=True)
class PlacementResult:
    cefr_level: str
    interests: list[str]
    goal: str


class OnboardingService:
    def __init__(
        self,
        analyzer: DebriefAnalyzer,
        profiles: ProfileRepository,
        users: UserRepository,
    ) -> None:
        self._analyzer = analyzer
        self._profiles = profiles
        self._users = users

    async def place(
        self,
        user: User,
        answers: list[str],
        interests: list[str],
        goal: str,
    ) -> PlacementResult:
        """Estimate a starting CEFR from the spoken placement answers and pre-fill
        the profile with interests/goal. The level is SET (not nudged): this is the
        starting point, not an adjustment. With no usable spoken answer the level
        is left at the account default (self-adjusts later via debriefs)."""
        clean_answers = [a.strip()[:_MAX_ANSWER_CHARS] for a in answers[:_MAX_ANSWERS] if a.strip()]

        if clean_answers:
            turns = [{"role": ROLE_USER, "content": a} for a in clean_answers]
            result = await self._analyzer.analyze(
                turns, user.native_language, fallback_cefr=user.cefr_level
            )
            cefr = result.cefr_estimate if result.cefr_estimate in VALID_CEFR else user.cefr_level
        else:
            cefr = user.cefr_level

        user.cefr_level = cefr
        await self._users.save(user)

        # Pre-fill the profile via its service so the same sanitisation/validation
        # applies as a manual profile edit. Goal is sanitised (it feeds prompts).
        clean_interests = [i.strip() for i in interests[:_MAX_INTERESTS] if i.strip()]
        clean_goal = strip_persistent_instructions(goal.strip()) if goal.strip() else ""
        profile_service = ProfileService(self._profiles)
        await profile_service.update(
            user.id,
            {"interests": clean_interests, "goal": clean_goal},
        )

        return PlacementResult(cefr_level=cefr, interests=clean_interests, goal=clean_goal)
