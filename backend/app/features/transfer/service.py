"""Surprise-transfer challenge (#126).

A skill is only mastered when the learner reuses it, unaided, in a NEW situation.
This service compiles a novel equivalent task for a skill by reusing the Mission
Compiler: it feeds it a directive to build a role-play in an unfamiliar context
exercising the SAME communication skill, and returns the resulting mission so the
learner attempts it (a normal mission conversation; the debrief evaluates it).
"""

from typing import Protocol

from app.features.auth.models import User
from app.features.missions.domain import SourceType
from app.features.missions.models import Mission


class MissionCreator(Protocol):
    async def create(self, user: User, source_type: SourceType, content: str) -> Mission: ...


def _transfer_directive(skill: str) -> str:
    """The (system-generated) brief handed to the Mission Compiler. Names the
    skill, demands a genuinely new context, and forbids reusing the setting so
    the challenge really tests transfer rather than recall."""
    return (
        f"Transfer challenge for the skill '{skill}'. Build a realistic spoken "
        "role-play in a NEW, everyday context the learner has NOT rehearsed, that "
        f"exercises the SAME communication skill as '{skill}'. Do not reuse the "
        "original setting, and give no hints — it must test whether the skill "
        "transfers to an unfamiliar situation."
    )


class TransferService:
    def __init__(self, missions: MissionCreator) -> None:
        self._missions = missions

    async def challenge(self, user: User, skill: str) -> Mission:
        return await self._missions.create(
            user, source_type="topic", content=_transfer_directive(skill)
        )
