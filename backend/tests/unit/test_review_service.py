"""Unit tests for the review (SRS) service — session -> schedule."""

from datetime import UTC, datetime, timedelta

import pytest

from app.features.review.models import STATUS_DUE, STATUS_MASTERED, ReviewItem
from app.features.review.scheduler import MASTERY_STREAK
from app.features.review.service import ReviewService

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _InMemoryReviewRepo:
    def __init__(self) -> None:
        self._rows: dict[tuple[int, str], ReviewItem] = {}
        self._seq = 0

    async def list_for_user(self, user_id):
        return [i for (u, _), i in self._rows.items() if u == user_id]

    async def upsert(
        self, user_id, error_type, *, stage, clean_streak, status, next_review_at, latest_correction
    ):
        key = (user_id, error_type)
        item = self._rows.get(key)
        if item is None:
            self._seq += 1
            item = ReviewItem(id=self._seq, user_id=user_id, error_type=error_type)
            self._rows[key] = item
        item.stage = stage
        item.clean_streak = clean_streak
        item.status = status
        item.next_review_at = next_review_at
        item.latest_correction = latest_correction

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def list_due(self, user_id, now):
        return [
            i
            for i in await self.list_for_user(user_id)
            if i.status != STATUS_MASTERED and (i.next_review_at is None or i.next_review_at <= now)
        ]


def _service():
    repo = _InMemoryReviewRepo()
    return ReviewService(repo), repo


@pytest.mark.asyncio
async def test_first_session_schedules_seen_error_types():
    service, repo = _service()
    await service.record_session(
        1, errors_seen={"verb_tense": "I went", "article": "a cat"}, now=NOW
    )
    items = {i.error_type: i for i in await repo.list_for_user(1)}
    assert set(items) == {"verb_tense", "article"}
    assert items["verb_tense"].next_review_at == NOW + timedelta(days=1)
    assert items["verb_tense"].latest_correction == "I went"


async def _clean_until_due(service, repo, user_id, times):
    """Run `times` clean sessions, each at the item's current due date so the
    spacing interval has elapsed and the streak actually grows."""
    for _ in range(times):
        item = (await repo.list_for_user(user_id))[0]
        await service.record_session(user_id, {}, item.next_review_at)


@pytest.mark.asyncio
async def test_absent_type_masters_only_when_sessions_are_spaced():
    service, repo = _service()
    await service.record_session(1, {"verb_tense": "x"}, NOW)
    await _clean_until_due(service, repo, 1, MASTERY_STREAK)
    item = (await repo.list_for_user(1))[0]
    assert item.status == STATUS_MASTERED


@pytest.mark.asyncio
async def test_same_day_clean_sessions_do_not_master():
    # Exit criterion (service level): repeated clean sessions the same day, before
    # the review date, must NOT master a fault just made.
    service, repo = _service()
    await service.record_session(1, {"verb_tense": "x"}, NOW)  # due NOW+1d
    for _ in range(MASTERY_STREAK + 2):
        await service.record_session(1, {}, NOW + timedelta(hours=1))
    item = (await repo.list_for_user(1))[0]
    assert item.status != STATUS_MASTERED
    assert item.clean_streak == 0


@pytest.mark.asyncio
async def test_reappearing_type_resets_and_reactivates():
    service, repo = _service()
    await service.record_session(1, {"verb_tense": "x"}, NOW)
    await _clean_until_due(service, repo, 1, MASTERY_STREAK)  # mastered
    assert (await repo.list_for_user(1))[0].status == STATUS_MASTERED
    # It comes back in a later session.
    await service.record_session(1, {"verb_tense": "again"}, NOW + timedelta(days=30))
    item = (await repo.list_for_user(1))[0]
    assert item.status == STATUS_DUE
    assert item.clean_streak == 0
    assert item.next_review_at == NOW + timedelta(days=30) + timedelta(days=1)


@pytest.mark.asyncio
async def test_list_due_excludes_mastered_and_future_items():
    service, repo = _service()
    await service.record_session(1, {"verb_tense": "x"}, NOW)  # due at NOW+1d
    # Nothing is due yet at NOW (next_review_at is NOW+1d).
    assert await service.list_due(1, NOW) == []
    # At NOW+2d it is due.
    due = await service.list_due(1, NOW + timedelta(days=2))
    assert [i.error_type for i in due] == ["verb_tense"]


@pytest.mark.asyncio
async def test_blank_error_type_is_ignored():
    service, repo = _service()
    await service.record_session(1, {"": "x", "  ": "y"}, NOW)
    assert await repo.list_for_user(1) == []
