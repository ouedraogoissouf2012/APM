from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.exceptions import (
    ActiveSessionExistsError,
    NotFoundError,
    QuotaExhaustedError,
)
from app.models.user import User
from app.services.session_service import SessionService
from tests.unit.fakes import InMemorySessionRepository, InMemoryUserRepository


async def _service_with_user(**user_kw) -> tuple[SessionService, User]:
    users = InMemoryUserRepository()
    defaults = {
        "email": "s@b.com",
        "hashed_password": "x",
        "native_language": "fr",
        "tier": "free",
        "quota_date": date.today(),
        "minutes_used_today": 0.0,
    }
    defaults.update(user_kw)
    user = await users.create(User(**defaults))
    service = SessionService(InMemorySessionRepository(), users, free_daily_minutes=10)
    return service, user


@pytest.mark.asyncio
async def test_start_returns_session_with_token_and_uuid_room():
    service, user = await _service_with_user()
    started = await service.start(user.id, "scenario", "restaurant")
    assert started.session.id is not None
    assert started.session.room_name.startswith(f"apm-{user.id}-")
    assert len(started.session.room_name.split("-")[-1]) == 32  # uuid4 hex
    assert started.livekit_token.count(".") == 2


@pytest.mark.asyncio
async def test_start_raises_when_quota_exhausted():
    service, user = await _service_with_user(minutes_used_today=10.0)
    with pytest.raises(QuotaExhaustedError):
        await service.start(user.id, "free", None)


@pytest.mark.asyncio
async def test_start_raises_when_session_already_active():
    service, user = await _service_with_user()
    await service.start(user.id, "free", None)
    with pytest.raises(ActiveSessionExistsError):
        await service.start(user.id, "free", None)


@pytest.mark.asyncio
async def test_start_unknown_user_raises():
    service, _ = await _service_with_user()
    with pytest.raises(NotFoundError):
        await service.start(999, "free", None)


@pytest.mark.asyncio
async def test_end_computes_server_side_duration_and_records_usage():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    # Force a known start time 3 minutes in the past (server computes the duration).
    started.session.started_at = datetime.now(UTC) - timedelta(minutes=3)

    ended = await service.end(started.session.id, user.id)

    assert ended.ended_at is not None
    assert ended.duration_minutes == pytest.approx(3.0, abs=0.2)
    assert user.minutes_used_today == pytest.approx(3.0, abs=0.2)


@pytest.mark.asyncio
async def test_end_is_idempotent_and_does_not_double_count():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.session.started_at = datetime.now(UTC) - timedelta(minutes=2)

    first = await service.end(started.session.id, user.id)
    used_after_first = user.minutes_used_today
    second = await service.end(started.session.id, user.id)

    assert second.ended_at == first.ended_at
    assert user.minutes_used_today == used_after_first  # no double counting


@pytest.mark.asyncio
async def test_end_unknown_session_raises():
    service, user = await _service_with_user()
    with pytest.raises(NotFoundError):
        await service.end(424242, user.id)


@pytest.mark.asyncio
async def test_end_other_users_session_raises():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    with pytest.raises(NotFoundError):
        await service.end(started.session.id, user_id=user.id + 999)
