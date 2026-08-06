from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.features.analytics.aggregate import AnalyticsAggregateService
from app.features.analytics.repository import (
    SqlAlchemyAnalyticsAggregateSource,
    SqlAlchemyAnalyticsCounter,
)
from app.features.analytics.service import AnalyticsService
from app.features.analytics.sinks import SqlAlchemyAnalyticsSink


def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    # SQL sink for the pilot; swap for a vendor sink here with no caller change.
    return AnalyticsService(SqlAlchemyAnalyticsSink(db), SqlAlchemyAnalyticsCounter(db))


def get_analytics_aggregate_service(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsAggregateService:
    return AnalyticsAggregateService(SqlAlchemyAnalyticsAggregateSource(db))
