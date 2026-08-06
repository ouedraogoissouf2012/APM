from typing import cast

from sqlalchemy import CursorResult, Executable, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.models import AnalyticsEventRow
from app.features.auth.models import User
from app.features.conversation.messages import ROLE_USER
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.idempotency.models import IdempotencyKey
from app.features.missions.models import Mission
from app.features.profile.models import LearnerProfile
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry

# Onboarding default of User.cefr_level (mirrors the column server-default). The
# level is estimated from the learner's speech (placement + every debrief), so an
# erasure resets it to this pre-onboarding baseline rather than leaving it.
_DEFAULT_CEFR = "A1"


class SqlAlchemyVoiceDataSource:
    """Aggregates and erases the learner's voice-derived rows across features.

    Raw audio is never stored, so 'voice data' is the persisted derivations. An
    erasure must clear ALL of them, not just the obvious transcripts:
      - session-keyed speech: transcripts, debriefs, and the session envelopes
        themselves (when/how long/in what mode the learner spoke);
      - user-keyed derivations: vocabulary, review items, compiled missions, and
        the per-session analytics events (CEFR estimate + error counts);
      - residues on KEPT rows: the profile ``memory_summary`` (re-injected into
        every prompt) and the speech-derived user fields (``cefr_level`` and the
        habit-streak counters), reset to their onboarding defaults;
      - cached turn replies in ``idempotency_keys`` (the turn endpoint is the only
        user of idempotency, so every key is a conversation reply).

    Deliberately KEPT (not voice-derived): the user account row, refresh tokens,
    the voice-consent record (a consent audit trail), and the profile's onboarding
    settings (interests/goal/accent/correction_intensity)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def utterances(self, user_id: int) -> list[dict]:
        rows = await self._session.execute(
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Transcript.turns,
            )
            .join(Transcript, Transcript.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.started_at.asc())
        )
        out: list[dict] = []
        for session_id, started_at, turns in rows:
            for turn in turns or []:
                if isinstance(turn, dict) and turn.get("role") == ROLE_USER:
                    out.append(
                        {
                            "session_id": session_id,
                            "started_at": started_at.isoformat(),
                            "text": str(turn.get("content", "")),
                        }
                    )
        return out

    async def vocabulary(self, user_id: int) -> list[dict]:
        rows = await self._session.scalars(
            select(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
        )
        return [{"word": e.word, "translation": e.translation, "example": e.example} for e in rows]

    async def debriefs(self, user_id: int) -> list[dict]:
        rows = await self._session.execute(
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Debrief.cefr_estimate,
                Debrief.summary,
                Debrief.errors,
            )
            .join(Debrief, Debrief.session_id == ConversationSession.id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.started_at.asc())
        )
        return [
            {
                "session_id": session_id,
                "started_at": started_at.isoformat(),
                "cefr_estimate": cefr_estimate,
                "summary": summary,
                "errors": errors or [],
            }
            for session_id, started_at, cefr_estimate, summary, errors in rows
        ]

    async def review_items(self, user_id: int) -> list[dict]:
        rows = await self._session.scalars(select(ReviewItem).where(ReviewItem.user_id == user_id))
        return [
            {
                "error_type": r.error_type,
                "latest_correction": r.latest_correction,
                "stage": r.stage,
                "status": r.status,
                "next_review_at": r.next_review_at.isoformat() if r.next_review_at else None,
            }
            for r in rows
        ]

    async def purge(self, user_id: int) -> dict[str, int]:
        # Sub-select the user's session ids once; transcripts and debriefs are
        # keyed by session, everything else by user directly.
        user_sessions = select(ConversationSession.id).where(ConversationSession.user_id == user_id)

        async def _affected(stmt: Executable) -> int:
            # execute(DELETE/UPDATE ...) returns a CursorResult whose rowcount is
            # the number of rows touched; the async Result type doesn't surface it
            # statically, so read it off the typed cursor result.
            result = cast(CursorResult, await self._session.execute(stmt))
            return result.rowcount or 0

        # Delete the FK children of sessions first, then the session rows: this
        # keeps the counts exact and never relies on cascade. vocabulary.session_id
        # is SET NULL and vocabulary is deleted by user below, so no session-scoped
        # row is orphaned.
        deleted = {
            "transcripts": await _affected(
                delete(Transcript).where(Transcript.session_id.in_(user_sessions))
            ),
            "debriefs": await _affected(
                delete(Debrief).where(Debrief.session_id.in_(user_sessions))
            ),
            "vocabulary": await _affected(
                delete(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
            ),
            "review_items": await _affected(
                delete(ReviewItem).where(ReviewItem.user_id == user_id)
            ),
            # The session envelopes themselves — the record of when/how long/in what
            # mode the learner spoke. Their FK children were deleted just above.
            "sessions": await _affected(
                delete(ConversationSession).where(ConversationSession.user_id == user_id)
            ),
            # Compiled practice artifacts (persona/goal/system_prompt) derived from
            # the learner's own supplied material. sessions.mission_id is SET NULL,
            # and the sessions are already gone, so nothing references these.
            "missions": await _affected(delete(Mission).where(Mission.user_id == user_id)),
            # Per-session product metrics (CEFR estimate, error counts) lifted from
            # the learner's debriefs and keyed to the real user id — voice-derived.
            "analytics_events": await _affected(
                delete(AnalyticsEventRow).where(AnalyticsEventRow.user_id == user_id)
            ),
            # Voice-derived memory re-injected into every prompt (debrief/service.py
            # writes it). Reset the field but KEEP the profile row (interests/goal/
            # accent/intensity are onboarding settings, not voice). Counted only when
            # there was actually something to clear, so the reported count is honest.
            "memory_summary": await _affected(
                update(LearnerProfile)
                .where(LearnerProfile.user_id == user_id, LearnerProfile.memory_summary != "")
                .values(memory_summary="")
            ),
            # Speech-derived fields on the KEPT user row: the CEFR level estimated
            # from placement/debriefs and the habit-streak counters. Reset to their
            # onboarding defaults; identity/settings (email, password, tier, native
            # language, quota, weekly goal) are untouched. Counted only when a field
            # was non-default, so the reported count stays honest.
            "user_stats": await _affected(
                update(User)
                .where(
                    User.id == user_id,
                    or_(
                        User.cefr_level != _DEFAULT_CEFR,
                        User.current_streak != 0,
                        User.longest_streak != 0,
                        User.last_active_date.is_not(None),
                    ),
                )
                .values(
                    cefr_level=_DEFAULT_CEFR,
                    current_streak=0,
                    longest_streak=0,
                    last_active_date=None,
                )
            ),
            # Cached turn replies — every idempotency key belongs to a /turn call.
            "idempotency_keys": await _affected(
                delete(IdempotencyKey).where(IdempotencyKey.user_id == user_id)
            ),
        }
        await self._session.commit()
        return deleted
