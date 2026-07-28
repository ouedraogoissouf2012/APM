"""Billing business logic: read a user's subscription, change a user's tier.

Tier changes are the only write here today. Payment (Stripe) will later call
`set_tier` from a verified webhook — the same method, so the tier/quota rules live
in one place regardless of how the change is triggered (admin action now, payment
later).
"""

from datetime import date

from app.core import quota
from app.domain.exceptions import NotFoundError
from app.features.auth.models import TIER_PREMIUM, User
from app.features.auth.repository import UserRepository
from app.features.billing.domain import Subscription


class BillingService:
    def __init__(self, users: UserRepository, free_daily_minutes: int) -> None:
        self._users = users
        self._free_daily = free_daily_minutes

    async def set_tier(self, user_id: int, tier: str) -> User:
        # Lock the row so a concurrent tier change or quota update can't interleave.
        user = await self._users.lock(user_id)
        if user is None:
            raise NotFoundError("User not found")
        user.tier = tier
        return await self._users.save(user)

    def subscription_of(self, user: User) -> Subscription:
        used = user.minutes_used_today if user.quota_date == date.today() else 0.0
        return Subscription(
            tier=user.tier,
            is_premium=user.tier == TIER_PREMIUM,
            free_daily_minutes=self._free_daily,
            minutes_used_today=used,
            remaining_minutes=quota.remaining_minutes(user, self._free_daily, date.today()),
        )
