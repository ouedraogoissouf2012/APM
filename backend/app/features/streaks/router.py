from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends

from app.domain.exceptions import NotFoundError
from app.features.auth.dependencies import get_current_user
from app.features.auth.models import User
from app.features.streaks.dependencies import get_streak_service
from app.features.streaks.schemas import StreakOut, WeeklyGoalUpdate
from app.features.streaks.service import StreakService

router = APIRouter(prefix="/me", tags=["streaks"])


def _today() -> date:
    return datetime.now(UTC).date()


@router.get("/streak", response_model=StreakOut)
async def get_streak(
    current_user: User = Depends(get_current_user),
    service: StreakService = Depends(get_streak_service),
) -> StreakOut:
    """The learner's current/longest streak and this week's practised minutes vs
    their weekly goal."""
    snap = await service.snapshot(current_user.id, _today())
    if snap is None:
        raise NotFoundError("No streak for this user")
    return StreakOut(
        current_streak=snap.current_streak,
        longest_streak=snap.longest_streak,
        weekly_goal_minutes=snap.weekly_goal_minutes,
        minutes_this_week=snap.minutes_this_week,
    )


@router.put("/streak/goal", response_model=StreakOut)
async def update_weekly_goal(
    payload: WeeklyGoalUpdate,
    current_user: User = Depends(get_current_user),
    service: StreakService = Depends(get_streak_service),
) -> StreakOut:
    """Set the weekly practice goal (clamped to a sane range) and return the
    refreshed streak snapshot."""
    await service.set_weekly_goal(current_user.id, payload.weekly_goal_minutes)
    snap = await service.snapshot(current_user.id, _today())
    assert snap is not None  # the user exists (authenticated)
    return StreakOut(
        current_streak=snap.current_streak,
        longest_streak=snap.longest_streak,
        weekly_goal_minutes=snap.weekly_goal_minutes,
        minutes_this_week=snap.minutes_this_week,
    )
