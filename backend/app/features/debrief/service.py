from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.conversation.repository import TranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.models import Debrief
from app.features.debrief.repository import DebriefRepository
from app.features.profile.repository import ProfileRepository
from app.features.sessions.repository import SessionRepository


class DebriefService:
    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        debriefs: DebriefRepository,
        analyzer: DebriefAnalyzer,
        profiles: ProfileRepository | None = None,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._debriefs = debriefs
        self._analyzer = analyzer
        self._profiles = profiles

    async def _owned_session(self, session_id: int, user: User) -> None:
        session = await self._sessions.get(session_id)
        if session is None or session.user_id != user.id:
            raise NotFoundError("Session not found")

    async def generate(self, session_id: int, user: User) -> Debrief:
        await self._owned_session(session_id, user)
        existing = await self._debriefs.get_by_session(session_id)
        if existing is not None:
            return existing
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
        debrief = await self._debriefs.save(
            session_id, result.cefr_estimate, result.summary, errors
        )
        await self._update_memory(user.id, result.summary, errors)
        return debrief

    async def get(self, session_id: int, user: User) -> Debrief:
        await self._owned_session(session_id, user)
        debrief = await self._debriefs.get_by_session(session_id)
        if debrief is None:
            raise NotFoundError("No debrief for this session")
        return debrief

    async def _update_memory(self, user_id: int, summary: str, errors: list[dict]) -> None:
        if self._profiles is None:
            return
        profile = await self._profiles.get_by_user_id(user_id)
        if profile is None:
            return

        error_types = [str(error.get("error_type", "")) for error in errors]
        error_types = [error_type for error_type in error_types if error_type]
        details = summary.strip()
        if error_types:
            details = f"{details} Recurring focus: {', '.join(error_types[:3])}.".strip()
        if not details:
            return

        profile.memory_summary = details[:500]
        await self._profiles.save(profile)
