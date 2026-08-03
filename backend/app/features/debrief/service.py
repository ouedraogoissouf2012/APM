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
        if transcript is None or not transcript.turns:
            # No conversation happened (started then ended without speaking). Return
            # an EMPTY debrief instead of a 404: a 404 made the client retry forever
            # (GET->404->POST->404...). Persisting an empty one makes the next call a
            # cache hit and stops the loop at the source.
            empty = await self._debriefs.save(
                session_id, user.cefr_level, "Pas encore de conversation à analyser.", []
            )
            return empty
        # Honour the learner's correction_intensity (#114): it sets the debrief's
        # tone and how many errors to surface. Default gentle when no profile.
        intensity = "gentle"
        if self._profiles is not None:
            profile = await self._profiles.get_by_user_id(user.id)
            if profile is not None:
                intensity = profile.correction_intensity
        result = await self._analyzer.analyze(
            transcript.turns, native_language=user.native_language, intensity=intensity
        )
        # Adaptive difficulty: nudge the learner's level one step toward the
        # session estimate.
        user.cefr_level = next_cefr_level(user.cefr_level, result.cefr_estimate)
        errors = [
            {
                "original": e.original,
                "correction": e.correction,
                "rule": e.rule,
                "error_type": e.error_type,
                "explanation": e.explanation,
                "examples": e.examples,
                "alternatives": e.alternatives,
            }
            for e in result.errors
        ]
        # Order matters for atomicity: the debrief commit persists the pending
        # CEFR nudge in the SAME transaction (shared request session). If it
        # fails, both roll back — a retry cannot double-promote. users.save
        # afterwards makes the intent explicit and covers repository
        # implementations that do not share the session.
        debrief = await self._debriefs.save(
            session_id, result.cefr_estimate, result.summary, errors
        )
        if self._users is not None:
            await self._users.save(user)
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
