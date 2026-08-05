from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.idempotency.repository import SqlAlchemyIdempotencyRepository
from app.features.idempotency.service import IdempotencyService


def get_idempotency_service(db: AsyncSession = Depends(get_db)) -> IdempotencyService:
    return IdempotencyService(SqlAlchemyIdempotencyRepository(db))
