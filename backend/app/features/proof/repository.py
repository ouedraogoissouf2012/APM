from collections import Counter
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversation.messages import ROLE_USER
from app.features.conversation.models import Transcript
from app.features.debrief.models import Debrief
from app.features.proof.service import SessionErrors
from app.features.sessions.models import ConversationSession


class SqlAlchemyProofDataSource:
    """The baseline (earliest) and latest sessions for a skill (keyed by
    ``scenario_id``) that have a debrief, each summarised as per-error-type
    counts plus the learner-turn count. Only these two rows are ever fetched —
    the proof is a two-point before/after, so nothing else is needed (#363).

    Scope note (deliberate): proof is a same-skill before/after, and a skill is a
    scenario. Free and mission sessions have no ``scenario_id``, so they are NOT
    comparable here and are excluded by design — not silently dropped. They still
    feed the debrief, streaks and SRS; they simply aren't a 'skill' to prove."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sessions_for_skill(self, user_id: int, skill: str) -> list[SessionErrors]:
        # Two targeted queries (earliest / latest session with a debrief) instead
        # of fetching every session on the skill: the caller (ProofService.proof)
        # only ever reads the first and last element (#363). Transcript.turns —
        # a JSONB blob that can run tens of KB per session — is now selected for
        # AT MOST these two rows, never for the whole history.
        def _edge_query(*order_by: ColumnElement[Any]) -> Select[Any]:
            return (
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
                .order_by(*order_by)
                .limit(1)
            )

        baseline_row = (
            await self._session.execute(
                _edge_query(ConversationSession.started_at.asc(), ConversationSession.id.asc())
            )
        ).first()
        if baseline_row is None:
            return []
        baseline = self._to_session_errors(baseline_row)

        latest_row = (
            await self._session.execute(
                _edge_query(ConversationSession.started_at.desc(), ConversationSession.id.desc())
            )
        ).first()
        # The two edge queries are separate executes sharing one READ COMMITTED
        # transaction, so a concurrent self-purge committing between them can delete
        # every matching row and make this DESC query return None even though the ASC
        # one didn't. Degrade to the single-session shape the caller already handles
        # instead of asserting a concurrency-reachable invariant (an assert would 500,
        # and is stripped entirely under `python -O`).
        if latest_row is None:
            return [baseline]
        latest = self._to_session_errors(latest_row)

        # A single session on this skill: baseline and latest are the SAME row.
        # Return one element (not a duplicated pair) so the caller's
        # `len(sessions) < 2` correctly reads "not enough sessions yet".
        return [baseline] if latest.session_id == baseline.session_id else [baseline, latest]

    @staticmethod
    def _to_session_errors(row: Sequence[Any]) -> SessionErrors:
        session_id, started_at, cefr, errors, turns = row
        counts: Counter[str] = Counter()
        for error in errors or []:
            if isinstance(error, dict):
                etype = str(error.get("error_type", "")).strip() or "other"
                counts[etype] += 1
        turn_count = sum(
            1 for turn in turns or [] if isinstance(turn, dict) and turn.get("role") == ROLE_USER
        )
        return SessionErrors(
            session_id=session_id,
            started_at=started_at.isoformat(),
            cefr=cefr,
            error_counts=dict(counts),
            turn_count=turn_count,
        )
