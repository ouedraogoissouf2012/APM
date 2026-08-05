from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.exceptions import (
    ActiveSessionExistsError,
    NotFoundError,
    QuotaExhaustedError,
)
from app.features.auth.models import User
from app.features.sessions.service import SessionService, _as_utc
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
async def test_start_records_the_configured_voice_engine():
    users = InMemoryUserRepository()
    user = await users.create(
        User(
            email="e@b.com",
            hashed_password="x",
            native_language="fr",
            tier="free",
            quota_date=date.today(),
            minutes_used_today=0.0,
        )
    )
    service = SessionService(
        InMemorySessionRepository(), users, free_daily_minutes=10, voice_engine="deepseek"
    )

    started = await service.start(user.id, "free", None)

    assert started.session.voice_engine == "deepseek"


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
async def test_start_reaps_a_stale_session_instead_of_locking_the_user_out():
    # #119: a session abandoned without /end must NOT lock the user forever. On the
    # next start, a session idle beyond the timeout is auto-closed (and its usage
    # recorded), then the new session proceeds.
    service, user = await _service_with_user()
    first = await service.start(user.id, "free", None)
    # Make the active session look abandoned 40 min ago.
    stale = datetime.now(UTC) - timedelta(minutes=40)
    first.session.started_at = stale
    first.session.last_activity_at = stale

    second = await service.start(user.id, "free", None)

    assert second.session.id != first.session.id  # not locked out
    assert first.session.ended_at is not None  # the stale one was closed
    assert user.minutes_used_today > 0  # its usage was billed on close


@pytest.mark.asyncio
async def test_start_still_blocks_when_active_session_is_recent():
    # A genuinely active (recent) session must still block a second start.
    service, user = await _service_with_user()
    await service.start(user.id, "free", None)
    with pytest.raises(ActiveSessionExistsError):
        await service.start(user.id, "free", None)


@pytest.mark.asyncio
async def test_record_turn_activity_meters_quota_per_turn():
    # #119: usage is billed per turn, so a client that never calls /end is still
    # bounded. Each turn charges the gap since the last activity (capped).
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.session.last_activity_at = datetime.now(UTC) - timedelta(minutes=2)

    await service.record_turn_activity(started.session.id, user.id)

    assert user.minutes_used_today == pytest.approx(2.0, abs=0.2)
    # last_activity_at was bumped so the next turn charges from now, not double.
    assert (datetime.now(UTC) - _as_utc(started.session.last_activity_at)).total_seconds() < 5


@pytest.mark.asyncio
async def test_record_turn_activity_marks_the_day_active_for_the_streak():
    # #118: any turn today counts as an active day, starting/extending the streak.
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)

    await service.record_turn_activity(started.session.id, user.id)

    from datetime import date

    assert user.current_streak == 1
    assert user.last_active_date == date.today()


@pytest.mark.asyncio
async def test_record_turn_activity_is_capped_per_turn():
    # A huge gap between turns (client paused) can't bill an unbounded amount.
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.session.last_activity_at = datetime.now(UTC) - timedelta(hours=5)

    await service.record_turn_activity(started.session.id, user.id)

    assert user.minutes_used_today <= 5.0  # capped, not 300 minutes


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
    # No turns happened, so last_activity == start. Move both 3 min into the past;
    # end bills the residual gap since the last activity (here the whole 3 min).
    past = datetime.now(UTC) - timedelta(minutes=3)
    started.session.started_at = past
    started.session.last_activity_at = past

    ended = await service.end(started.session.id, user.id)

    assert ended.ended_at is not None
    assert ended.duration_minutes == pytest.approx(3.0, abs=0.2)
    assert user.minutes_used_today == pytest.approx(3.0, abs=0.2)


@pytest.mark.asyncio
async def test_end_is_idempotent_and_does_not_double_count():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    past = datetime.now(UTC) - timedelta(minutes=2)
    started.session.started_at = past
    started.session.last_activity_at = past

    first = await service.end(started.session.id, user.id)
    used_after_first = user.minutes_used_today
    second = await service.end(started.session.id, user.id)

    assert second.ended_at == first.ended_at
    assert user.minutes_used_today == used_after_first  # no double counting


@pytest.mark.asyncio
async def test_end_bills_only_the_residual_after_per_turn_metering():
    # The real flow: per-turn metering already charged most of the session; end
    # must bill only the small gap since the last turn, NOT the whole duration
    # again (no double-charge).
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.session.started_at = datetime.now(UTC) - timedelta(minutes=10)
    # A turn just happened (last_activity ~ 1 min ago); most was already metered.
    started.session.last_activity_at = datetime.now(UTC) - timedelta(minutes=1)

    await service.end(started.session.id, user.id)

    # Only the ~1 min residual is billed here, not the full 10.
    assert user.minutes_used_today == pytest.approx(1.0, abs=0.2)


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
