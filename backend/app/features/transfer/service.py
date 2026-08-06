"""Surprise-transfer challenge (#126).

A skill is only mastered when the learner reuses it, unaided, in a NEW situation.
This service compiles an equivalent task for a skill by reusing the Mission
Compiler: the skill name is the (untrusted) content, and a SYSTEM-authored design
directive — passed on the compiler's trusted channel, not smuggled through the
untrusted content — asks for a role-play in a fresh, unfamiliar everyday context
exercising the same communication skill.

Honest scope: the challenge builds a NEW everyday context; it cannot promise to
avoid one SPECIFIC prior scenario, because the learner's past settings are not
given to it. It tests transfer by being unfamiliar, not by dodging a named origin.
"""

from typing import Protocol

from app.features.auth.models import User
from app.features.missions.domain import SourceType
from app.features.missions.models import Mission


class MissionCreator(Protocol):
    async def create(
        self, user: User, source_type: SourceType, content: str, *, directive: str = ""
    ) -> Mission: ...


def _transfer_directive() -> str:
    """The SYSTEM-authored (trusted) design directive handed to the compiler. It
    overrides the default 'rehearse the real situation' framing and asks for a
    genuinely new, unfamiliar context so the challenge tests transfer, not recall.
    The skill it applies to is the (untrusted) content the compiler is given."""
    return (
        "This is a SURPRISE-TRANSFER challenge. Do NOT rehearse a familiar setting: "
        "design a spoken role-play set in a NEW, unfamiliar everyday context that "
        "exercises the SAME communication skill named in the untrusted content. Give "
        "no hints, so it tests whether that skill transfers to a fresh situation."
    )


class TransferService:
    def __init__(self, missions: MissionCreator) -> None:
        self._missions = missions

    async def challenge(self, user: User, skill: str) -> Mission:
        # The skill is the untrusted content the compiler builds around; the transfer
        # brief rides the TRUSTED directive channel so its intent binds instead of
        # being neutralised as untrusted data.
        return await self._missions.create(
            user, source_type="freeform", content=skill, directive=_transfer_directive()
        )
