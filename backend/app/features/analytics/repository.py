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
