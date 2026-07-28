"""Unit tests for BillingService — no DB, no network (fakes only). TDD: written
before the implementation."""

from datetime import date

import pytest

from app.domain.exceptions import NotFoundError
from app.features.auth.models import TIER_FREE, TIER_PREMIUM, User
from app.features.billing.service import BillingService


class _FakeUsers:
    """In-memory user store, substitutable for the SQLAlchemy repo (LSP)."""

    def __init__(self, users: list[User]) -> None:
        self._by_id = {u.id: u for u in users}
        self.saved: list[User] = []

    async def lock(self, user_id: int) -> User | None:
        return self._by_id.get(user_id)

    async def get_by_id(self, user_id: int) -> User | None:
        return self._by_id.get(user_id)

    async def save(self, user: User) -> User:
        self.saved.append(user)
        return user


def _user(user_id: int = 1, tier: str = TIER_FREE, used: float = 0.0) -> User:
    return User(
        id=user_id,
        email=f"u{user_id}@b.com",
        hashed_password="x",
        tier=tier,
        quota_date=date.today(),
        minutes_used_today=used,
    )


def _service(users: _FakeUsers, free_daily: int = 10) -> BillingService:
    return BillingService(users, free_daily_minutes=free_daily)


@pytest.mark.asyncio
async def test_set_tier_promotes_a_user_to_premium():
    users = _FakeUsers([_user(1, tier=TIER_FREE)])
    updated = await _service(users).set_tier(1, TIER_PREMIUM)
    assert updated.tier == TIER_PREMIUM
    assert users.saved  # persisted


@pytest.mark.asyncio
async def test_set_tier_can_downgrade_to_free():
    users = _FakeUsers([_user(1, tier=TIER_PREMIUM)])
    updated = await _service(users).set_tier(1, TIER_FREE)
    assert updated.tier == TIER_FREE


@pytest.mark.asyncio
async def test_set_tier_rejects_unknown_user():
    users = _FakeUsers([])
    with pytest.raises(NotFoundError):
        await _service(users).set_tier(999, TIER_PREMIUM)


@pytest.mark.asyncio
async def test_subscription_of_free_user_reports_remaining_minutes():
    sub = _service(_FakeUsers([])).subscription_of(_user(1, tier=TIER_FREE, used=4.0))
    assert sub.tier == TIER_FREE
    assert sub.is_premium is False
    assert sub.free_daily_minutes == 10
    assert sub.minutes_used_today == 4.0
    assert sub.remaining_minutes == 6.0


@pytest.mark.asyncio
async def test_subscription_of_premium_user_is_unlimited():
    sub = _service(_FakeUsers([])).subscription_of(_user(1, tier=TIER_PREMIUM, used=99.0))
    assert sub.is_premium is True
    assert sub.remaining_minutes == float("inf")
