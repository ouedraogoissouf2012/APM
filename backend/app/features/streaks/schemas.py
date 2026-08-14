from pydantic import BaseModel, Field

# A weekly goal must be a sane, positive number of minutes. These bounds are the
# SINGLE source of truth (#391): WeeklyGoalUpdate rejects anything outside them
# with a 422 at the API edge, and StreakService imports them for its defensive
# clamp — so the schema and the service can never drift apart again (the previous
# schema allowed 1..100000 while the service clamped to 5..1000, silently
# rewriting out-of-range input instead of the 422 this comment promised).
MIN_WEEKLY_GOAL_MINUTES = 5
MAX_WEEKLY_GOAL_MINUTES = 1000


class StreakOut(BaseModel):
    current_streak: int
    longest_streak: int
    weekly_goal_minutes: int
    minutes_this_week: int


class WeeklyGoalUpdate(BaseModel):
    # Out-of-range is a real 422 here, not a silent clamp (#391): a value the
    # service would have clamped is rejected at the edge instead.
    weekly_goal_minutes: int = Field(ge=MIN_WEEKLY_GOAL_MINUTES, le=MAX_WEEKLY_GOAL_MINUTES)
