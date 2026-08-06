from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.messages import ROLE_USER
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.proof.service import SessionErrors
from app.features.sessions.models import ConversationSession


class SqlAlchemyProofDataSource:
    """Sessions for a skill (keyed by ``scenario_id``) that have a debrief, oldest
    first, each summarised as per-error-type counts plus the learner-turn count.

    Scope note (deliberate): proof is a same-skill before/after, and a skill is a
    scenario. Free and mission sessions have no ``scenario_id``, so they are NOT
    comparable here and are excluded by design — not silently dropped. They still
    feed the debrief, streaks and SRS; they simply aren't a 'skill' to prove."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sessions_for_skill(self, user_id: int, skill: str) -> list[SessionErrors]:
        rows = await self._session.execute(
            select(
                ConversationSession.id,
                ConversationSession.started_at,
                Debrief.cefr_estimate,
                Debrief.errors,
                Transcript.turns,
            )
            .join(Debrief, Debrief.session_id == ConversationSession.id)
            .outerjoin(Transcript, Transcript.session_id == ConversationSession.id)
            .where(
                ConversationSession.user_id == user_id,
                ConversationSession.scenario_id == skill,
            )
            .order_by(ConversationSession.started_at.asc())
        )
        out: list[SessionErrors] = []
        for session_id, started_at, cefr, errors, turns in rows:
            counts: Counter[str] = Counter()
            for error in errors or []:
                if isinstance(error, dict):
                    etype = str(error.get("error_type", "")).strip() or "other"
                    counts[etype] += 1
            turn_count = sum(
                1
                for turn in turns or []
                if isinstance(turn, dict) and turn.get("role") == ROLE_USER
            )
            out.append(
                SessionErrors(
                    session_id=session_id,
                    started_at=started_at.isoformat(),
                    cefr=cefr,
                    error_counts=dict(counts),
                    turn_count=turn_count,
                )
            )
        return out
