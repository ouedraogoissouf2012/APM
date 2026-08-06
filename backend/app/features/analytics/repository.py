from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.models import AnalyticsEventRow


class SqlAlchemyAnalyticsCounter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_events(self, user_id: int, name: str) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(AnalyticsEventRow)
            .where(AnalyticsEventRow.user_id == user_id, AnalyticsEventRow.name == name)
        )
        return int(total or 0)


class SqlAlchemyAnalyticsAggregateSource:
    """Aggregate reads over the append-only events (admin dashboard, #129)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def distinct_users_with_event(self, name: str) -> int:
        total = await self._session.scalar(
            select(func.count(func.distinct(AnalyticsEventRow.user_id))).where(
                AnalyticsEventRow.name == name
            )
        )
        return int(total or 0)

    async def count_event(self, name: str) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(AnalyticsEventRow)
            .where(AnalyticsEventRow.name == name)
        )
        return int(total or 0)

    async def count_event_since(self, name: str, since: datetime) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(AnalyticsEventRow)
            .where(
                AnalyticsEventRow.name == name,
                AnalyticsEventRow.created_at >= since,
            )
        )
        return int(total or 0)
