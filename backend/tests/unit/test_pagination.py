"""Unit tests for the shared pagination clamp (#233)."""

from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, resolve_limit


def test_none_falls_back_to_default():
    assert resolve_limit(None) == DEFAULT_PAGE_SIZE


def test_value_in_range_is_kept():
    assert resolve_limit(25) == 25


def test_over_maximum_is_clamped():
    assert resolve_limit(10_000) == MAX_PAGE_SIZE


def test_below_one_is_clamped_to_one():
    assert resolve_limit(0) == 1
    assert resolve_limit(-5) == 1


def test_custom_default_and_maximum():
    assert resolve_limit(None, default=10, maximum=20) == 10
    assert resolve_limit(999, default=10, maximum=20) == 20
