from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence import advisory_xact_lock
from app.features.debrief.models import Debrief


class DebriefRepository(Protocol):
    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief: ...

    async def get_by_session(self, session_id: int) -> Debrief | None: ...

    async def lock_for_session(self, session_id: int) -> None:
        """Acquire a Postgres transaction-scoped advisory lock keyed on this
        session_id, serialising concurrent debrief generation for the SAME
        session (#302). Deliberately NOT a row lock on `sessions` or `users`:
        those are already locked in a fixed order elsewhere (start()/end() lock
        the user row first; a row lock here would invert that order against a
        concurrent /end for the same session) and a row lock would stay held
        for the whole — multi-second — LLM analysis, stalling unrelated
        session-lifecycle calls (start/end/record_turn_activity) for this user.
        An advisory lock has no row to collide with, so it serialises this one
        invariant without touching either. Auto-released at commit/rollback."""
        ...


class SqlAlchemyDebriefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_for_session(self, session_id: int) -> None:
        # Namespaced by "debrief" (#371, core.persistence) so this can never
        # collide with an unrelated advisory lock elsewhere keyed by a raw id
        # (e.g. ReviewRepository's, namespaced by "review").
        await advisory_xact_lock(self._session, "debrief", session_id)

    async def save(
        self, session_id: int, cefr_estimate: str, summary: str, errors: list[dict]
    ) -> Debrief:
        existing = await self.get_by_session(session_id)
        if existing is None:
            existing = Debrief(
                session_id=session_id, cefr_estimate=cefr_estimate, summary=summary, errors=errors
            )
            self._session.add(existing)
        else:
            existing.cefr_estimate = cefr_estimate
            existing.summary = summary
            existing.errors = errors
        await self._session.commit()
        await self._session.refresh(existing)
        return existing

    async def get_by_session(self, session_id: int) -> Debrief | None:
        return await self._session.scalar(select(Debrief).where(Debrief.session_id == session_id))
