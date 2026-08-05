from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.review.models import STATUS_MASTERED, ReviewItem


class ReviewRepository(Protocol):
    async def list_for_user(self, user_id: int) -> list[ReviewItem]: ...

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
    ) -> None: ...

    async def list_due(self, user_id: int, now: datetime) -> list[ReviewItem]: ...


class SqlAlchemyReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[ReviewItem]:
        result = await self._session.scalars(
            select(ReviewItem).where(ReviewItem.user_id == user_id)
        )
        return list(result)

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
        existing = await self._session.scalar(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.error_type == error_type,
            )
        )
        if existing is None:
            self._session.add(
                ReviewItem(
                    user_id=user_id,
                    error_type=error_type,
                    stage=stage,
                    clean_streak=clean_streak,
                    status=status,
                    next_review_at=next_review_at,
                    latest_correction=latest_correction,
                )
            )
        else:
            existing.stage = stage
            existing.clean_streak = clean_streak
            existing.status = status
            existing.next_review_at = next_review_at
            existing.latest_correction = latest_correction
        await self._session.commit()

    async def list_due(self, user_id: int, now: datetime) -> list[ReviewItem]:
        # Items to review now: not mastered, and either due already (next_review_at
        # in the past) or never scheduled. Ordered by soonest due first.
        result = await self._session.scalars(
            select(ReviewItem)
            .where(
                ReviewItem.user_id == user_id,
                ReviewItem.status != STATUS_MASTERED,
                (ReviewItem.next_review_at.is_(None)) | (ReviewItem.next_review_at <= now),
            )
            .order_by(ReviewItem.next_review_at.asc().nulls_first())
        )
        return list(result)
