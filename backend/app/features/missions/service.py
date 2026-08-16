from collections.abc import Awaitable, Callable

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.missions.compiler import MissionCompiler
from app.features.missions.domain import SourceType
from app.features.missions.models import Mission
from app.features.missions.repository import MissionRepository

IoBoundaryHook = Callable[[], Awaitable[None]]


class MissionService:
    """Compiles a learner's raw material into a persisted mission simulation.

    Creating a mission does not consume the conversation quota — that is charged
    when a session actually runs (see SessionService). Ownership is enforced on
    every read so one learner can never load another's mission.
    """

    def __init__(
        self,
        missions: MissionRepository,
        compiler: MissionCompiler,
        io_boundary: IoBoundaryHook | None = None,
    ) -> None:
        self._missions = missions
        self._compiler = compiler
        self._io_boundary = io_boundary

    async def create(
        self, user: User, source_type: SourceType, content: str, *, directive: str = ""
    ) -> Mission:
        # #415: hand the request connection back before the compile LLM, then
        # persist on the same session (it checkouts a short-lived connection for
        # the write). user.id is an already-loaded column — safe after expunge.
        if self._io_boundary is not None:
            await self._io_boundary()
        brief = await self._compiler.compile(
            source_type=source_type, content=content, directive=directive
        )
        return await self._missions.add(
            user_id=user.id,
            source_type=source_type,
            persona=brief.persona,
            goal=brief.goal,
            likely_questions=brief.likely_questions,
            system_prompt=brief.system_prompt,
        )

    async def get(self, mission_id: int, user: User) -> Mission:
        mission = await self._missions.get_owned(mission_id, user.id)
        if mission is None:
            # 404 (not 403) so we never reveal that a mission id exists for
            # another user.
            raise NotFoundError("Mission not found")
        return mission
