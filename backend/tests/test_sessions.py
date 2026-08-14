"""Integration tests for the sessions API (real DB).

Unit tests for the quota policy and SessionService live in tests/unit/.
"""

import pytest


async def _auth_header(client, email="s@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_start_session_returns_session_id(client):
    headers = await _auth_header(client)
    resp = await client.post(
        "/sessions/start", headers=headers, json={"mode": "scenario", "scenario_id": "restaurant"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["session_id"]


@pytest.mark.asyncio
async def test_cannot_start_two_active_sessions(client):
    headers = await _auth_header(client, email="s2@b.com")
    first = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert first.status_code == 201
    second = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert second.status_code == 409  # an active session already exists


@pytest.mark.asyncio
async def test_end_closes_session_and_allows_restart(client):
    headers = await _auth_header(client, email="s3@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    end = await client.post(f"/sessions/{session_id}/end", headers=headers)
    assert end.status_code == 200, end.text
    body = end.json()
    assert body["duration_minutes"] is not None
    assert body["duration_minutes"] >= 0  # server-computed, not client-supplied

    # With the previous session ended, a new one can start.
    again = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    assert again.status_code == 201


@pytest.mark.asyncio
async def test_active_returns_the_in_progress_session(client):
    headers = await _auth_header(client, email="active-1@b.com")
    start = await client.post(
        "/sessions/start",
        headers=headers,
        json={"mode": "scenario", "scenario_id": "restaurant"},
    )
    session_id = start.json()["session_id"]

    resp = await client.get("/sessions/active", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == session_id
    assert body["mode"] == "scenario"
    assert body["scenario_id"] == "restaurant"
    assert body["turns"] == []


@pytest.mark.asyncio
async def test_active_returns_404_when_no_session_in_progress(client):
    headers = await _auth_header(client, email="active-2@b.com")
    resp = await client.get("/sessions/active", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_active_carries_the_transcript_so_the_client_can_resume(client):
    headers = await _auth_header(client, email="active-3@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    # One conversation turn (conftest forces the fake LLM engine -> no real DeepSeek).
    turn = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "i is happy"}
    )
    assert turn.status_code == 200, turn.text

    resp = await client.get("/sessions/active", headers=headers)
    body = resp.json()
    assert body["session_id"] == session_id
    assert [t["role"] for t in body["turns"]] == ["user", "assistant"]
    assert body["turns"][0]["content"] == "i is happy"


@pytest.mark.asyncio
async def test_end_is_idempotent(client):
    headers = await _auth_header(client, email="s4@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(f"/sessions/{session_id}/end", headers=headers)
    second = await client.post(f"/sessions/{session_id}/end", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_list_sessions_returns_only_current_users_sessions(client):
    headers_a = await _auth_header(client, email="history-a@b.com")
    headers_b = await _auth_header(client, email="history-b@b.com")

    own = await client.post(
        "/sessions/start",
        headers=headers_a,
        json={"mode": "scenario", "scenario_id": "restaurant"},
    )
    other = await client.post("/sessions/start", headers=headers_b, json={"mode": "free"})

    resp = await client.get("/sessions", headers=headers_a)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [item["id"] for item in body] == [own.json()["session_id"]]
    assert other.json()["session_id"] not in [item["id"] for item in body]
    assert body[0]["scenario_id"] == "restaurant"
    assert "started_at" in body[0]
    assert "cefr_estimate" in body[0]


@pytest.mark.asyncio
async def test_end_bills_the_last_turn_interval_only_once(_engine, _setup_db):
    # #258: end() reads the session BEFORE locking the user; a concurrent last-turn
    # metering (its own DB session) can advance last_activity_at — and bill up to it —
    # in between. end() must re-read the session after the lock, else _close_session
    # computes the residual from a stale last_activity_at and bills that turn's
    # interval a SECOND time. Two real DB sessions reproduce the staleness.
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.security import hash_password
    from app.features.auth.models import User
    from app.features.auth.repository import SqlAlchemyUserRepository
    from app.features.sessions.models import ConversationSession
    from app.features.sessions.ownership import get_owned_session
    from app.features.sessions.repository import SqlAlchemySessionRepository
    from app.features.sessions.service import SessionService

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    t0 = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    async with maker() as s:
        user = User(
            email="race-end@b.com", hashed_password=hash_password("x"), native_language="fr"
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        uid = user.id
        session = ConversationSession(
            user_id=uid,
            mode="free",
            started_at=t0,
            last_activity_at=t0,
            voice_engine="fake",
        )
        s.add(session)
        await s.commit()
        await s.refresh(session)
        sid = session.id

    def _svc(db: AsyncSession) -> SessionService:
        return SessionService(
            SqlAlchemySessionRepository(db), SqlAlchemyUserRepository(db), free_daily_minutes=1000
        )

    async with maker() as db_a, maker() as db_b:
        svc_a = _svc(db_a)
        # Seed db_a's identity map with the STALE last_activity_at (t0), exactly as
        # end()'s own read does, BEFORE the concurrent turn commits. Keep a STRONG
        # reference (`stale`): SQLAlchemy's identity map is weak-ref, so a discarded
        # object is GC'd and end()'s get() would re-query fresh, hiding the staleness.
        stale = await get_owned_session(svc_a._sessions, sid, uid)
        assert stale.last_activity_at == t0  # sanity: cached at t0
        # A concurrent last turn advances last_activity_at to t0+2min and bills 2 min.
        await _svc(db_b).record_turn_activity(sid, uid, now=t0 + timedelta(minutes=2))
        # end() at t0+3min: it re-reads the SAME cached (stale) object; with the fix's
        # refresh it bills only the residual (1 min); without it, it bills t0->t0+3
        # (3 min) on top of the turn — a double-count of the t0->t0+2 interval.
        await svc_a.end(sid, uid, now=t0 + timedelta(minutes=3))
        assert stale is not None  # keep `stale` referenced until after end()

    async with maker() as s:
        billed = (await s.get(User, uid)).minutes_used_today
    # Total billed = 2 (turn) + 1 (residual) = 3. The stale-read bug gives 2 + 3 = 5.
    assert billed == pytest.approx(3.0, abs=0.05)


@pytest.mark.asyncio
async def test_record_turn_activity_and_end_do_not_deadlock(_engine, _setup_db):
    """#381: start()/end() lock the user row BEFORE touching the session
    (USER->SESSION). Pre-fix, record_turn_activity dirtied
    `session.last_activity_at` BEFORE locking the user — the session factory
    leaves autoflush at its True default (database.py), so that lock() call's
    SELECT ... FOR UPDATE autoflushed the dirty session first, emitting
    `UPDATE sessions ...` THEN `SELECT users ... FOR UPDATE`: a SESSION->USER
    order, the reverse of start()/end(). Two real connections contending on the
    same (user, session) pair in opposite lock order deadlock (Postgres
    SQLSTATE 40P01) once genuinely concurrent.

    Reproduced with two independent real connections and `asyncio.gather` —
    each awaited DB round-trip is a genuine yield point, so the event loop
    truly interleaves the two connections' statements at the network level
    (mirrors this file's other real-concurrency tests, e.g.
    test_end_bills_the_last_turn_interval_only_once, and
    test_debrief_api.py's/test_review_api.py's concurrent-request tests).
    Repeated over several fresh sessions for the same user: an AB-BA deadlock
    depends on genuine timing, so one shot could pass by luck even with the
    bug present — a loop makes the reproduction reliable rather than a single
    coin flip. If either call raises, asyncio.gather propagates it and fails
    the test — a real 40P01 surfaces as an unhandled DBAPIError."""
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.security import hash_password
    from app.features.auth.models import User
    from app.features.auth.repository import SqlAlchemyUserRepository
    from app.features.sessions.models import ConversationSession
    from app.features.sessions.repository import SqlAlchemySessionRepository
    from app.features.sessions.service import SessionService

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    t0 = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    async with maker() as s:
        user = User(
            email="deadlock-race@b.com", hashed_password=hash_password("x"), native_language="fr"
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
        uid = user.id

    def _svc(db: AsyncSession) -> SessionService:
        return SessionService(
            SqlAlchemySessionRepository(db), SqlAlchemyUserRepository(db), free_daily_minutes=1000
        )

    for i in range(10):
        async with maker() as seed:
            session = ConversationSession(
                user_id=uid,
                mode="free",
                started_at=t0,
                last_activity_at=t0,
                voice_engine="fake",
            )
            seed.add(session)
            await seed.commit()
            await seed.refresh(session)
            sid = session.id

        moment = t0 + timedelta(minutes=i + 1)
        async with maker() as db_a, maker() as db_b:
            await asyncio.gather(
                _svc(db_a).record_turn_activity(sid, uid, now=moment),
                _svc(db_b).end(sid, uid, now=moment),
            )


@pytest.mark.asyncio
async def test_sessions_has_composite_user_id_started_at_index(db_session):
    """#359: (user_id, started_at) must stay index-covered — it serves
    get_active_for_user's plain user_id filter as a leftmost-prefix match and
    list_recent_for_user's ORDER BY started_at DESC. Checks the LIVE schema
    (provisioned by Base.metadata.create_all, same as CI), mirroring #288's
    review_items test. Also asserts the old single-column index is gone, since
    the composite fully subsumes it (#359 consolidates rather than adds)."""
    from sqlalchemy import text

    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'sessions'"
            " AND indexname = 'ix_sessions_user_id_started_at'"
        )
    )
    indexdef = result.scalar_one_or_none()
    assert indexdef is not None, "composite (user_id, started_at) index is missing"
    assert indexdef.endswith("(user_id, started_at)"), indexdef

    stale = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'sessions'"
            " AND indexname = 'ix_sessions_user_id'"
        )
    )
    assert stale.scalar_one_or_none() is None, "old single-column index should be dropped"
