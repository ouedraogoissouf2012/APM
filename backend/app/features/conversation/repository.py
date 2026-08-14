from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.models import Transcript


class TranscriptRepository(Protocol):
    async def save(self, session_id: int, turns: list[dict]) -> None: ...

    async def get_by_session(self, session_id: int) -> Transcript | None: ...


class SqlAlchemyTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, session_id: int, turns: list[dict]) -> None:
        """Upserts the (already-bounded, see ConversationTurnService.
        transcript_max_messages, #364) turns array in ONE round trip: an atomic
        INSERT-or-update-on-conflict, instead of a separate SELECT to decide
        which — the whole-column rewrite this does is now O(the caller's cap),
        never O(the session's full history). This also closes a latent race the
        old SELECT-then-branch pattern had: two concurrent saves for a session's
        FIRST turn could both see "no row yet" and both attempt an INSERT, the
        second failing on the session_id UNIQUE constraint. ON CONFLICT makes the
        upsert atomic at the database level regardless.

        Returns nothing: the only caller (ConversationTurnService._persist)
        never read the previous return value, and an upsert issued via Core (not
        session.add()) has no ORM instance to hand back in the first place —
        so there is nothing to spend an extra refresh() round trip keeping fresh.
        """
        stmt = pg_insert(Transcript).values(session_id=session_id, turns=turns)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Transcript.session_id],
            set_={"turns": stmt.excluded.turns},
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def get_by_session(self, session_id: int) -> Transcript | None:
        return await self._session.scalar(
            select(Transcript).where(Transcript.session_id == session_id)
        )
