from typing import TYPE_CHECKING

from app.domain.exceptions import NotFoundError
from app.features.auth.models import User
from app.features.conversation.prompt import strip_persistent_instructions
from app.features.conversation.repository import TranscriptRepository
from app.features.debrief.analyzer import DebriefAnalyzer
from app.features.debrief.cefr import next_cefr_level
from app.features.debrief.domain import DebriefResult
from app.features.debrief.models import Debrief
from app.features.debrief.repository import DebriefRepository
from app.features.profile.models import LearnerProfile
from app.features.profile.repository import ProfileRepository
from app.features.sessions.ownership import get_owned_session
from app.features.sessions.repository import SessionRepository

if TYPE_CHECKING:
    from app.features.debrief.enrichment import PostDebriefEnrichment

# How many recurring error types persist into the learner's memory summary.
_MAX_RECURRING_FOCUS = 3


class DebriefService:
    """Generates the authoritative debrief for a session and triggers enrichment.

    Reduced to orchestration (ADR 0001): it persists the AUTHORITATIVE core — the
    Debrief row, the CEFR nudge and the memory summary — atomically in one commit,
    then hands off best-effort side-effects (vocabulary, SRS, analytics) to an
    injected `PostDebriefEnrichment`. Each effect lives behind its own collaborator.
    """

    def __init__(
        self,
        sessions: SessionRepository,
        transcripts: TranscriptRepository,
        debriefs: DebriefRepository,
        analyzer: DebriefAnalyzer,
        profiles: ProfileRepository | None = None,
        enrichment: "PostDebriefEnrichment | None" = None,
    ) -> None:
        self._sessions = sessions
        self._transcripts = transcripts
        self._debriefs = debriefs
        self._analyzer = analyzer
        self._profiles = profiles
        # Best-effort side-effects run AFTER the core is durable (ADR 0001). Injected
        # (DIP), optional so the debrief works without any enrichment wired.
        self._enrichment = enrichment

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
            return await self._debriefs.save(
                session_id, user.cefr_level, "Pas encore de conversation à analyser.", []
            )

        # Load the profile ONCE — reused for both the correction intensity and the
        # memory update below (no second query).
        profile = (
            await self._profiles.get_by_user_id(user.id) if self._profiles is not None else None
        )
        # Honour the learner's correction_intensity (#114); default gentle when no
        # profile.
        intensity = profile.correction_intensity if profile is not None else "gentle"
        result = await self._analyzer.analyze(
            transcript.turns, native_language=user.native_language, intensity=intensity
        )
        errors = _serialise_errors(result)

        debrief = await self._persist_core(session_id, user, profile, result, errors)

        # Best-effort enrichment, only AFTER the authoritative core is durable.
        if self._enrichment is not None:
            await self._enrichment.run(user.id, session_id, result, errors)
        return debrief

    async def _persist_core(
        self,
        session_id: int,
        user: User,
        profile: LearnerProfile | None,
        result: DebriefResult,
        errors: list[dict],
    ) -> Debrief:
        """The authoritative, ATOMIC write (ADR 0001). Stage the CEFR nudge and the
        memory summary onto the shared request session, then the SINGLE debrief
        commit persists all three together. If it fails, nothing is committed — a
        retry re-runs cleanly and can never double-promote the CEFR level."""
        # Adaptive difficulty: nudge the level one step toward the session estimate.
        user.cefr_level = next_cefr_level(user.cefr_level, result.cefr_estimate)
        _stage_memory(profile, result.summary, errors)
        # One commit — persists the debrief + the staged CEFR nudge + the staged
        # memory summary on the shared session, atomically.
        return await self._debriefs.save(session_id, result.cefr_estimate, result.summary, errors)

    async def get(self, session_id: int, user: User) -> Debrief:
        await get_owned_session(self._sessions, session_id, user.id)
        debrief = await self._debriefs.get_by_session(session_id)
        if debrief is None:
            raise NotFoundError("No debrief for this session")
        return debrief


def _serialise_errors(result: DebriefResult) -> list[dict]:
    return [
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


def _stage_memory(profile: LearnerProfile | None, summary: str, errors: list[dict]) -> None:
    """Stage (do NOT commit) the learner's memory summary on the shared-session
    profile, so the debrief commit persists it atomically with the debrief and the
    CEFR nudge. Injection commands are stripped — this text is re-injected into every
    future prompt, so it must never carry instructions."""
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
