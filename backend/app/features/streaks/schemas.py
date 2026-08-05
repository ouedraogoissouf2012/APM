from pydantic import BaseModel, Field


class StreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    weekly_goal_minutes: int
    minutes_this_week: int


class WeeklyGoalUpdate(BaseModel):
    # Bounds mirror the service clamp; a wildly out-of-range value is a 422.
    weekly_goal_minutes: int = Field(ge=1, le=100000)
