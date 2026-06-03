import pytest

from app.features.profile.service import ProfileService
from tests.unit.fakes import InMemoryProfileRepository


def _service() -> ProfileService:
    return ProfileService(InMemoryProfileRepository())


@pytest.mark.asyncio
async def test_get_or_create_creates_when_absent():
    service = _service()
    profile = await service.get_or_create(user_id=42)
    assert profile.user_id == 42


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent():
    service = _service()
    first = await service.get_or_create(user_id=42)
    second = await service.get_or_create(user_id=42)
    assert first is second


@pytest.mark.asyncio
async def test_update_applies_changes():
    service = _service()
    profile = await service.update(user_id=42, changes={"goal": "job interview", "accent": "uk"})
    assert profile.goal == "job interview"
    assert profile.accent == "uk"


@pytest.mark.asyncio
async def test_update_creates_profile_if_missing_then_applies():
    service = _service()
    profile = await service.update(user_id=7, changes={"goal": "travel"})
    assert profile.user_id == 7
    assert profile.goal == "travel"
