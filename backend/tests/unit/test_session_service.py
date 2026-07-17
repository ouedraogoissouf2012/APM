from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.exceptions import (
    ActiveSessionExistsError,
    NotFoundError,
    QuotaExhaustedError,
)
from app.features.auth.models import User
from app.features.sessions.service import SessionService
from tests.unit.fakes import (
    InMemorySessionRepository,
    InMemoryTranscriptRepository,
    InMemoryUserRepository,
)


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


async def _service_with_transcripts(
    **user_kw,
) -> tuple[SessionService, User, InMemoryTranscriptRepository]:
    users = InMemoryUserRepository()
    defaults = {
        "email": "t@b.com",
        "hashed_password": "x",
        "native_language": "fr",
        "tier": "free",
        "quota_date": date.today(),
        "minutes_used_today": 0.0,
    }
    defaults.update(user_kw)
    user = await users.create(User(**defaults))
    transcripts = InMemoryTranscriptRepository()
    service = SessionService(
        InMemorySessionRepository(), users, free_daily_minutes=10, transcripts=transcripts
    )
    return service, user, transcripts


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
async def test_active_returns_none_when_no_session_in_progress():
    service, user, _ = await _service_with_transcripts()
    assert await service.active(user.id) is None


@pytest.mark.asyncio
async def test_active_returns_the_in_progress_session_with_its_transcript():
    service, user, transcripts = await _service_with_transcripts()
    started = await service.start(user.id, "scenario", "restaurant")
    await transcripts.save(
        started.session.id,
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}],
    )

    active = await service.active(user.id)

    assert active is not None
    assert active.session.id == started.session.id
    assert active.session.scenario_id == "restaurant"
    assert [t["content"] for t in active.turns] == ["hi", "Hello!"]


@pytest.mark.asyncio
async def test_active_returns_empty_turns_before_the_first_turn():
    service, user, _ = await _service_with_transcripts()
    started = await service.start(user.id, "free", None)

    active = await service.active(user.id)

    assert active is not None
    assert active.session.id == started.session.id
    assert active.turns == []


@pytest.mark.asyncio
async def test_active_ignores_ended_sessions():
    service, user, _ = await _service_with_transcripts()
    started = await service.start(user.id, "free", None)
    await service.end(started.session.id, user.id)

    assert await service.active(user.id) is None


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


@pytest.mark.asyncio
async def test_history_returns_recent_sessions_for_user_only():
    service, user = await _service_with_user()
    older = await service.start(user.id, "free", None)
    await service.end(older.session.id, user.id)
    newer = await service.start(user.id, "scenario", "restaurant")

    history = await service.history(user.id)

    assert [item.id for item in history] == [newer.session.id, older.session.id]
    assert history[0].scenario_id == "restaurant"
