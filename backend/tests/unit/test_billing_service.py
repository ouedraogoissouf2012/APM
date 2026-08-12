"""Unit tests for BillingService — no DB, no network (fakes only). TDD: written
before the implementation."""

from datetime import UTC, date, datetime

import pytest

from app.domain.exceptions import NotFoundError
from app.features.auth.models import TIER_FREE, TIER_PREMIUM, User
from app.features.billing import service as billing_service_module
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
        quota_date=datetime.now(UTC).date(),  # matches subscription_of's UTC "today" (#305)
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


class _FixedUtcDatetime:
    """Stands in for the stdlib `datetime` class inside the service module so
    `datetime.now(UTC)` resolves to a controlled instant instead of wall-clock
    time — proves subscription_of asks for UTC specifically (#305), not just
    "some notion of today" that would happen to pass under the local timezone."""

    def __init__(self, fixed_now: datetime) -> None:
        self.fixed_now = fixed_now

    def now(self, tz: object) -> datetime:
        assert tz is UTC, "subscription_of must call datetime.now(UTC), not local time"
        return self.fixed_now


@pytest.mark.asyncio
async def test_subscription_of_compares_quota_date_against_utc_today(monkeypatch):
    """#305: quota_date must be compared against datetime.now(UTC).date(), not
    date.today() (local system time) — a server running in a timezone ahead of
    UTC could otherwise treat a still-current UTC day as stale (wrongly
    resetting usage) or a stale UTC day as current (wrongly denying reset)."""
    fixed_now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(billing_service_module, "datetime", _FixedUtcDatetime(fixed_now))

    same_utc_day = _user(1, tier=TIER_FREE, used=4.0)
    same_utc_day.quota_date = fixed_now.date()
    sub = _service(_FakeUsers([])).subscription_of(same_utc_day)
    assert sub.minutes_used_today == 4.0  # same UTC day -> usage still counts

    stale_utc_day = _user(2, tier=TIER_FREE, used=4.0)
    stale_utc_day.quota_date = date(2026, 2, 28)  # a prior UTC day
    sub2 = _service(_FakeUsers([])).subscription_of(stale_utc_day)
    assert sub2.minutes_used_today == 0.0  # different UTC day -> usage reset
