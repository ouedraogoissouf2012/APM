from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.progress.repository import SqlAlchemyProgressDataSource
from app.features.progress.service import ProgressService


def get_progress_service(db: AsyncSession = Depends(get_db)) -> ProgressService:
    return ProgressService(SqlAlchemyProgressDataSource(db))
