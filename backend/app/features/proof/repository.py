from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.debrief.models import Debrief
from app.features.proof.service import SessionErrors
from app.features.sessions.models import ConversationSession


class SqlAlchemyProofDataSource:
    """Sessions for a skill (keyed by scenario_id) that have a debrief, oldest
    first, each summarised as per-error-type counts from its debrief."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sessions_for_skill(self, user_id: int, skill: str) -> list[SessionErrors]:
        rows = await self._session.execute(
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Debrief.cefr_estimate,
                Debrief.errors,
            )
            .join(Debrief, Debrief.session_id == ConversationSession.id)
            .where(
                ConversationSession.user_id == user_id,
                ConversationSession.scenario_id == skill,
            )
            .order_by(ConversationSession.started_at.asc())
        )
        out: list[SessionErrors] = []
        for session_id, started_at, cefr, errors in rows:
            counts: Counter[str] = Counter()
            for error in errors or []:
                if isinstance(error, dict):
                    etype = str(error.get("error_type", "")).strip() or "other"
                    counts[etype] += 1
            out.append(
                SessionErrors(
                    session_id=session_id,
                    started_at=started_at.isoformat(),
                    cefr=cefr,
                    error_counts=dict(counts),
                )
            )
        return out
