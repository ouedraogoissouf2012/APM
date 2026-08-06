from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.models import User
from app.features.sessions.models import ConversationSession


class SqlAlchemyStreakDataSource:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_streak_fields(self, user_id: int) -> tuple[int, int, date | None, int] | None:
        row = await self._session.execute(
            select(
                User.current_streak,
                User.longest_streak,
                User.last_active_date,
                User.weekly_goal_minutes,
            ).where(User.id == user_id)
        )
        result = row.first()
        if result is None:
            return None
        return (result[0], result[1], result[2], result[3])

    async def minutes_since(self, user_id: int, since: date) -> float:
        # Sum session durations for sessions started on/after `since`. Anchor the
        # boundary in UTC: started_at is a tz-aware column, so a naive datetime would
        # be compared under the DB session's timezone and could shift the cutoff.
        since_dt = datetime.combine(since, time.min, tzinfo=UTC)
        total = await self._session.scalar(
            select(func.coalesce(func.sum(ConversationSession.duration_minutes), 0.0)).where(
                ConversationSession.user_id == user_id,
                ConversationSession.started_at >= since_dt,
            )
        )
        return float(total or 0.0)

    async def set_weekly_goal(self, user_id: int, minutes: int) -> None:
        user = await self._session.get(User, user_id)
        if user is not None:
            user.weekly_goal_minutes = minutes
            await self._session.commit()
