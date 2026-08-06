from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.analytics.repository import SqlAlchemyAnalyticsCounter
from app.features.analytics.service import AnalyticsService
from app.features.analytics.sinks import SqlAlchemyAnalyticsSink


def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    # SQL sink for the pilot; swap for a vendor sink here with no caller change.
    return AnalyticsService(SqlAlchemyAnalyticsSink(db), SqlAlchemyAnalyticsCounter(db))
