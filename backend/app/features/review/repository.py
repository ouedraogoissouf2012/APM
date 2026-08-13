from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence import advisory_xact_lock
from app.features.review.models import STATUS_MASTERED, ReviewItem


class ReviewRepository(Protocol):
    async def list_for_user(self, user_id: int) -> list[ReviewItem]: ...

    async def lock_for_user(self, user_id: int) -> None:
        """Acquire a Postgres transaction-scoped advisory lock keyed on this
        user_id, serialising concurrent record_session calls for the SAME
        learner (#361, mirrors DebriefRepository.lock_for_session, #302).

        upsert()'s ON CONFLICT DO UPDATE already makes each row-level write
        race-free — two concurrent INSERTs for the same (user_id, error_type)
        can never raise IntegrityError. But record_session's scheduling logic
        reads the item's CURRENT stage/streak first (list_for_user) and
        computes the NEXT one from it (on_error_seen/on_error_absent) before
        writing: two concurrent calls (e.g. two devices each finishing a
        different session) would both read the same pre-update state and
        silently overwrite each other's computed next stage — a lost update
        that ON CONFLICT cannot see, since neither write conflicts at the SQL
        level. The lock is held for the whole read-compute-upsert-commit
        below, so the loser blocks until the winner commits, then reads its
        result instead of stale state. Auto-released at commit/rollback."""
        ...

    async def upsert(
        self,
        user_id: int,
        error_type: str,
        *,
        stage: int,
        clean_streak: int,
        status: str,
        next_review_at: datetime | None,
        latest_correction: str,
    ) -> None:
        """Stage one item's new SRS state WITHOUT committing. The caller commits
        once per session so a whole session's schedule advances atomically."""
        ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

    async def list_due(self, user_id: int, now: datetime, *, limit: int) -> list[ReviewItem]: ...


class SqlAlchemyReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[ReviewItem]:
        result = await self._session.scalars(
            select(ReviewItem).where(ReviewItem.user_id == user_id)
        )
        return list(result)

    async def lock_for_user(self, user_id: int) -> None:
        # Namespaced by "review" (#371, core.persistence) so this can never
        # collide with an unrelated advisory lock elsewhere keyed by a raw id
        # (e.g. DebriefRepository's, namespaced by "debrief").
        await advisory_xact_lock(self._session, "review", user_id)

    async def upsert(
        self,
        user_id: int,
        error_type: str,
        *,
        stage: int,
        clean_streak: int,
        status: str,
        next_review_at: datetime | None,
        latest_correction: str,
    ) -> None:
        # Atomic INSERT ... ON CONFLICT DO UPDATE on uq_review_user_error_type:
        # a plain get-then-write (the previous implementation) raced two
        # concurrent first-sightings of the same error type into a double
        # INSERT that trips the unique constraint — one IntegrityError (#361).
        # Row-level races are closed by this ON CONFLICT clause; the
        # read-before-write scheduling race across the whole session is closed
        # separately by lock_for_user (see its docstring).
        insert_stmt = pg_insert(ReviewItem).values(
            user_id=user_id,
            error_type=error_type,
            stage=stage,
            clean_streak=clean_streak,
            status=status,
            next_review_at=next_review_at,
            latest_correction=latest_correction,
        )
        await self._session.execute(
            insert_stmt.on_conflict_do_update(
                constraint="uq_review_user_error_type",
                set_={
                    "stage": insert_stmt.excluded.stage,
                    "clean_streak": insert_stmt.excluded.clean_streak,
                    "status": insert_stmt.excluded.status,
                    "next_review_at": insert_stmt.excluded.next_review_at,
                    "latest_correction": insert_stmt.excluded.latest_correction,
                },
            )
        )
        # No commit here: the service stages every item then commits once, so a
        # failure mid-session can't leave the schedule half-advanced.

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def list_due(self, user_id: int, now: datetime, *, limit: int) -> list[ReviewItem]:
        # Items to review now: not mastered, and either due already (next_review_at
        # in the past) or never scheduled. Ordered by soonest due first, with an id
        # tiebreaker for a deterministic page, and bounded (#233).
        result = await self._session.scalars(
            select(ReviewItem)
            .where(
                ReviewItem.user_id == user_id,
                ReviewItem.status != STATUS_MASTERED,
                (ReviewItem.next_review_at.is_(None)) | (ReviewItem.next_review_at <= now),
            )
            .order_by(ReviewItem.next_review_at.asc().nulls_first(), ReviewItem.id.asc())
            .limit(limit)
        )
        return list(result)
