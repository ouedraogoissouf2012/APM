from datetime import date

from app.features.auth.models import TIER_FREE, User


def remaining_minutes(user: User, free_daily: int, today: date) -> float:
    if user.tier != TIER_FREE:
        return float("inf")
    used = user.minutes_used_today if user.quota_date == today else 0.0
    return max(0.0, free_daily - used)


def record_usage(user: User, minutes: float, today: date) -> None:
    if user.quota_date != today:
        user.quota_date = today
        user.minutes_used_today = 0.0
    user.minutes_used_today += minutes
