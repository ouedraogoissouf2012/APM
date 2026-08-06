"""AnalyticsSink implementations (#129).

The sink is abstract so the app is not coupled to any vendor: a logging sink for
dev, a SQL sink that appends to `analytics_events` for the pilot. Swapping in a
third-party sink later is a one-line DI change.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.analytics.domain import AnalyticsEvent
from app.features.analytics.models import AnalyticsEventRow

_logger = logging.getLogger("apm.analytics")


class LoggingAnalyticsSink:
    """Dev/default sink: logs the event, persists nothing."""

    async def emit(self, event: AnalyticsEvent) -> None:
        _logger.info(
            "analytics",
            extra={"event": event.name, "user_id": event.user_id, "props": event.properties},
        )


class SqlAlchemyAnalyticsSink:
    """Appends the event to the analytics_events table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def emit(self, event: AnalyticsEvent) -> None:
        self._session.add(
            AnalyticsEventRow(
                name=event.name,
                user_id=event.user_id,
                properties=event.properties,
            )
        )
        await self._session.commit()
