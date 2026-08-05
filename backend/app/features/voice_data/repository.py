from typing import cast

from sqlalchemy import CursorResult, Delete, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.messages import ROLE_USER
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry


class SqlAlchemyVoiceDataSource:
    """Aggregates and erases the learner's voice-derived rows across features.

    Raw audio is never stored, so 'voice data' is the persisted derivations:
    transcripts (their utterances), debriefs, vocabulary, and review items."""

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

    async def purge(self, user_id: int) -> dict[str, int]:
        # Sub-select the user's session ids once; transcripts and debriefs are
        # keyed by session, vocabulary and review by user directly.
        user_sessions = select(ConversationSession.id).where(ConversationSession.user_id == user_id)

        async def _delete(stmt: Delete) -> int:
            # execute(DELETE ...) returns a CursorResult whose rowcount is the
            # number of rows deleted; the async Result type doesn't surface it
            # statically, so read it off the typed cursor result.
            result = cast(CursorResult, await self._session.execute(stmt))
            return result.rowcount or 0

        deleted = {
            "transcripts": await _delete(
                delete(Transcript).where(Transcript.session_id.in_(user_sessions))
            ),
            "debriefs": await _delete(delete(Debrief).where(Debrief.session_id.in_(user_sessions))),
            "vocabulary": await _delete(
                delete(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
            ),
            "review_items": await _delete(delete(ReviewItem).where(ReviewItem.user_id == user_id)),
        }
        await self._session.commit()
        return deleted
