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
async def test_start_returns_the_persisted_session():
    service, user = await _service_with_user()
    session = await service.start(user.id, "scenario", "restaurant")
    assert session.id is not None
    assert session.user_id == user.id
    assert session.mode == "scenario"
    assert session.scenario_id == "restaurant"


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

    assert started.voice_engine == "deepseek"


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
    first.started_at = stale
    first.last_activity_at = stale

    second = await service.start(user.id, "free", None)

    assert second.id != first.id  # not locked out
    assert first.ended_at is not None  # the stale one was closed
    assert user.minutes_used_today > 0  # its usage was billed on close


@pytest.mark.asyncio
async def test_start_blocks_when_the_reap_itself_pushes_over_quota():
    # #301: the quota check above runs BEFORE the reap bills the abandoned
    # session's residual usage, so it can pass on a stale balance the reap alone
    # pushes over the cap. Issue's own numbers: 9.9/10 min used, a session
    # abandoned 40 min ago gets reaped for +5 min (turn_meter_cap) -> 14.9, 49%
    # over budget. A second quota check after the reap must catch this instead
    # of letting the new session start anyway.
    service, user = await _service_with_user(minutes_used_today=9.9)
    first = await service.start(user.id, "free", None)
    stale = datetime.now(UTC) - timedelta(minutes=40)
    first.started_at = stale
    first.last_activity_at = stale

    with pytest.raises(QuotaExhaustedError):
        await service.start(user.id, "free", None)

    # The reap's own billing must still land — it's real usage that happened,
    # and skipping it would leave the abandoned session active forever (#119).
    assert first.ended_at is not None
    assert user.minutes_used_today == pytest.approx(14.9, abs=0.05)


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
    started.last_activity_at = datetime.now(UTC) - timedelta(minutes=2)

    await service.record_turn_activity(started.id, user.id)

    assert user.minutes_used_today == pytest.approx(2.0, abs=0.2)
    # last_activity_at was bumped so the next turn charges from now, not double.
    assert (datetime.now(UTC) - _as_utc(started.last_activity_at)).total_seconds() < 5


@pytest.mark.asyncio
async def test_record_turn_activity_marks_the_day_active_for_the_streak():
    # #118: any turn counts as an active day, starting/extending the streak. `now`
    # is injected so this asserts a KNOWN date, not the same clock the code reads
    # (the old `== date.today()` assertion was tautological).
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)

    await service.record_turn_activity(
        started.id, user.id, now=datetime(2026, 8, 5, 9, 0, tzinfo=UTC)
    )

    assert user.current_streak == 1
    assert user.last_active_date == date(2026, 8, 5)


@pytest.mark.asyncio
async def test_active_day_uses_the_utc_calendar_date_not_server_local():
    # A turn at 23:30 UTC belongs to that UTC date regardless of where the server
    # runs — the streak day boundary is UTC, not the server's local `date.today()`.
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)

    await service.record_turn_activity(
        started.id, user.id, now=datetime(2026, 8, 5, 23, 30, tzinfo=UTC)
    )

    assert user.last_active_date == date(2026, 8, 5)


@pytest.mark.asyncio
async def test_two_consecutive_utc_days_extend_the_streak():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)

    await service.record_turn_activity(
        started.id, user.id, now=datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
    )
    await service.record_turn_activity(
        started.id, user.id, now=datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    )

    assert user.current_streak == 2
    assert user.last_active_date == date(2026, 8, 6)


@pytest.mark.asyncio
async def test_record_turn_activity_is_capped_per_turn():
    # A huge gap between turns (client paused) can't bill an unbounded amount.
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.last_activity_at = datetime.now(UTC) - timedelta(hours=5)

    await service.record_turn_activity(started.id, user.id)

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
        started.id,
        [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}],
    )

    active = await service.active(user.id)

    assert active is not None
    assert active.session.id == started.id
    assert active.session.scenario_id == "restaurant"
    assert [t["content"] for t in active.turns] == ["hi", "Hello!"]


@pytest.mark.asyncio
async def test_active_returns_empty_turns_before_the_first_turn():
    service, user, _ = await _service_with_transcripts()
    started = await service.start(user.id, "free", None)

    active = await service.active(user.id)

    assert active is not None
    assert active.session.id == started.id
    assert active.turns == []


@pytest.mark.asyncio
async def test_active_ignores_ended_sessions():
    service, user, _ = await _service_with_transcripts()
    started = await service.start(user.id, "free", None)
    await service.end(started.id, user.id)

    assert await service.active(user.id) is None


@pytest.mark.asyncio
async def test_end_computes_server_side_duration_and_records_usage():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    # No turns happened, so last_activity == start. Move both 3 min into the past;
    # end bills the residual gap since the last activity (here the whole 3 min).
    past = datetime.now(UTC) - timedelta(minutes=3)
    started.started_at = past
    started.last_activity_at = past

    ended = await service.end(started.id, user.id)

    assert ended.ended_at is not None
    assert ended.duration_minutes == pytest.approx(3.0, abs=0.2)
    assert user.minutes_used_today == pytest.approx(3.0, abs=0.2)


@pytest.mark.asyncio
async def test_end_is_idempotent_and_does_not_double_count():
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    past = datetime.now(UTC) - timedelta(minutes=2)
    started.started_at = past
    started.last_activity_at = past

    first = await service.end(started.id, user.id)
    used_after_first = user.minutes_used_today
    second = await service.end(started.id, user.id)

    assert second.ended_at == first.ended_at
    assert user.minutes_used_today == used_after_first  # no double counting


@pytest.mark.asyncio
async def test_end_bills_only_the_residual_after_per_turn_metering():
    # The real flow: per-turn metering already charged most of the session; end
    # must bill only the small gap since the last turn, NOT the whole duration
    # again (no double-charge).
    service, user = await _service_with_user()
    started = await service.start(user.id, "free", None)
    started.started_at = datetime.now(UTC) - timedelta(minutes=10)
    # A turn just happened (last_activity ~ 1 min ago); most was already metered.
    started.last_activity_at = datetime.now(UTC) - timedelta(minutes=1)

    await service.end(started.id, user.id)

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
        await service.end(started.id, user_id=user.id + 999)


@pytest.mark.asyncio
async def test_history_returns_recent_sessions_for_user_only():
    service, user = await _service_with_user()
    older = await service.start(user.id, "free", None)
    await service.end(older.id, user.id)
    newer = await service.start(user.id, "scenario", "restaurant")

    history = await service.history(user.id)

    assert [item.id for item in history] == [newer.id, older.id]
    assert history[0].scenario_id == "restaurant"


class _LockTrackingUserRepo(InMemoryUserRepository):
    """Records whether a call took the row lock (FOR UPDATE) or a plain get."""

    def __init__(self) -> None:
        super().__init__()
        self.locked_ids: list[int] = []
        self.got_ids: list[int] = []

    async def lock(self, user_id: int) -> User | None:
        self.locked_ids.append(user_id)
        return await super().lock(user_id)

    async def get_by_id(self, user_id: int) -> User | None:
        self.got_ids.append(user_id)
        return await super().get_by_id(user_id)


@pytest.mark.asyncio
async def test_end_locks_the_user_row_for_the_quota_write():
    # #228: end() bills the quota (a read-modify-write on minutes_used_today), so it
    # MUST take the row lock like start()/record_turn_activity — an unlocked get would
    # lost-update against a concurrent last-turn metering.
    users = _LockTrackingUserRepo()
    user = await users.create(
        User(
            email="q@b.com",
            hashed_password="x",
            native_language="fr",
            tier="free",
            quota_date=date.today(),
            minutes_used_today=0.0,
        )
    )
    service = SessionService(InMemorySessionRepository(), users, free_daily_minutes=10)
    started = await service.start(user.id, "free", None)
    past = datetime.now(UTC) - timedelta(minutes=2)
    started.started_at = past
    started.last_activity_at = past

    users.locked_ids.clear()  # ignore the lock start() already took
    users.got_ids.clear()
    await service.end(started.id, user.id)

    assert user.id in users.locked_ids  # end() locked the user for the quota write
    assert user.id not in users.got_ids  # and did NOT read it with an unlocked get


@pytest.mark.asyncio
async def test_record_turn_activity_aborts_if_session_ended_after_lock():
    # #427: /end billed the residual between our first read and the user lock.
    users = InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    user = await users.create(
        User(
            email="ended@b.com",
            hashed_password="x",
            native_language="fr",
            tier="free",
            quota_date=date.today(),
            minutes_used_today=0.0,
        )
    )
    service = SessionService(sessions, users, free_daily_minutes=10)
    started = await service.start(user.id, "free", None)
    past = datetime.now(UTC) - timedelta(minutes=2)
    started.last_activity_at = past
    orig = sessions.refresh

    async def _ended_on_refresh(session):
        session.ended_at = datetime.now(UTC)
        await orig(session)

    sessions.refresh = _ended_on_refresh  # type: ignore[method-assign]
    await service.record_turn_activity(started.id, user.id)
    assert user.minutes_used_today == 0.0
    assert started.last_activity_at == past
