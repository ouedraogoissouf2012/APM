from datetime import date, timedelta

import pytest

from app.core import quota
from app.features.auth.models import User


def _make_user(**kw) -> User:
    defaults = {"id": 1, "email": "q@b.com", "hashed_password": "x", "tier": "free"}
    defaults.update(kw)
    return User(**defaults)


def test_quota_resets_on_new_day():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    assert quota.remaining_minutes(user, free_daily=10, today=date.today()) == 10.0


def test_quota_counts_today_usage():
    user = _make_user(quota_date=date.today(), minutes_used_today=7.0)
    assert quota.remaining_minutes(user, free_daily=10, today=date.today()) == 3.0


def test_premium_user_has_unlimited():
    user = _make_user(tier="premium", quota_date=date.today(), minutes_used_today=999.0)
    assert quota.remaining_minutes(user, free_daily=10, today=date.today()) == float("inf")


def test_record_usage_resets_then_adds():
    user = _make_user(quota_date=date.today() - timedelta(days=1), minutes_used_today=9.0)
    quota.record_usage(user, minutes=2.0, today=date.today())
    assert user.quota_date == date.today()
    assert user.minutes_used_today == 2.0


def test_quota_allows_just_under_limit():
    user = _make_user(quota_date=date.today(), minutes_used_today=9.9)
    assert quota.remaining_minutes(user, free_daily=10, today=date.today()) == pytest.approx(0.1)


def test_quota_blocks_exactly_at_limit():
    user = _make_user(quota_date=date.today(), minutes_used_today=10.0)
    assert quota.remaining_minutes(user, free_daily=10, today=date.today()) == 0.0
