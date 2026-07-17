from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.auth.repository import UserRepository
from app.features.conversation.prompt import strip_persistent_instructions
from app.features.conversation.repository import TranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.cefr import next_cefr_level
from app.features.debrief.models import Debrief
from app.features.debrief.repository import DebriefRepository
from app.features.profile.repository import ProfileRepository
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository

# How many recurring error types persist into the learner's memory summary.
_MAX_RECURRING_FOCUS = 3


class DebriefService:
    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        debriefs: DebriefRepository,
        analyzer: DebriefAnalyzer,
        profiles: ProfileRepository | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._debriefs = debriefs
        self._analyzer = analyzer
        self._profiles = profiles
        self._users = users

    async def generate(self, session_id: int, user: User) -> Debrief:
        await get_owned_session(self._sessions, session_id, user.id)
        existing = await self._debriefs.get_by_session(session_id)
        if existing is not None:
            return existing
        transcript = await self._transcripts.get_by_session(session_id)
        if transcript is None:
            raise NotFoundError("No transcript for this session")
        result = await self._analyzer.analyze(
            transcript.turns, native_language=user.native_language
        )
        # Adaptive difficulty: nudge the learner's level one step toward the
        # session estimate, persisted explicitly through the user repository.
        user.cefr_level = next_cefr_level(user.cefr_level, result.cefr_estimate)
        if self._users is not None:
            await self._users.save(user)
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
        await get_owned_session(self._sessions, session_id, user.id)
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
        details = strip_persistent_instructions(summary)
        if error_types:
            focus = ", ".join(error_types[:_MAX_RECURRING_FOCUS])
            details = f"{details} Recurring focus: {focus}.".strip()
        if not details:
            return

        profile.memory_summary = strip_persistent_instructions(details)
        await self._profiles.save(profile)
