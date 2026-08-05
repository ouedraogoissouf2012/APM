from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.streaks.repository import SqlAlchemyStreakDataSource
from app.features.streaks.service import StreakService


def get_streak_service(db: AsyncSession = Depends(get_db)) -> StreakService:
    return StreakService(SqlAlchemyStreakDataSource(db))
