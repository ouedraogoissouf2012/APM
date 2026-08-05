from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.review.repository import SqlAlchemyReviewRepository
from app.features.review.service import ReviewService


def get_review_service(db: AsyncSession = Depends(get_db)) -> ReviewService:
    return ReviewService(SqlAlchemyReviewRepository(db))
