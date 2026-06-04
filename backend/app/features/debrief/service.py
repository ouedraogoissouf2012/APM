from typing import Any

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.debrief.analyzer import DebriefAnalyzer


class DebriefService:
    def __init__(
        self,
        sessions: Any,
        transcripts: Any,
        debriefs: Any,
        analyzer: DebriefAnalyzer,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._debriefs = debriefs
        self._analyzer = analyzer

    async def _owned_session(self, session_id: int, user: User) -> None:
        session = await self._sessions.get(session_id)
        if session is None or session.user_id != user.id:
            raise NotFoundError("Session not found")

    async def generate(self, session_id: int, user: User) -> Any:
        await self._owned_session(session_id, user)
        transcript = await self._transcripts.get_by_session(session_id)
        if transcript is None:
            raise NotFoundError("No transcript for this session")
        result = await self._analyzer.analyze(
            transcript.turns, native_language=user.native_language
        )
        errors = [
            {
                "original": e.original,
                "correction": e.correction,
                "rule": e.rule,
                "error_type": e.error_type,
            }
            for e in result.errors
        ]
        return await self._debriefs.save(session_id, result.cefr_estimate, result.summary, errors)

    async def get(self, session_id: int, user: User) -> Any:
        await self._owned_session(session_id, user)
        debrief = await self._debriefs.get_by_session(session_id)
        if debrief is None:
            raise NotFoundError("No debrief for this session")
        return debrief
