"""Integration tests for the text conversation turn endpoint.

VOICE_ENGINE defaults to "fake", so the LLM is FakeLlm -> reply "You said: <text>".
"""

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.llm.providers.fakes import FakeLlm
from app.core.rate_limit import InMemoryRateLimiter, user_rate_limit_key
from app.database import get_db
from app.features.auth.models import User
from app.features.conversation.correction import TurnCorrection
from app.features.conversation.dependencies import (
    get_conversation_rate_limiter,
    get_conversation_turn_service,
)
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.conversation.turn_service import ConversationTurnService
from app.features.profile.repository import SqlAlchemyProfileRepository
from app.features.sessions.models import ConversationSession
from app.features.sessions.repository import SqlAlchemySessionRepository
from app.main import app


class _CannedCorrector:
    async def correct(self, text, cefr_level, native_language, intensity="gentle"):
        return TurnCorrection(
            original="i is happy",
            correction="I am happy",
            rule="Use 'am' with 'I'.",
            alternatives=["I'm happy"],
        )


def _service_with_correction(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
    return ConversationTurnService(
        sessions=SqlAlchemySessionRepository(db),
        transcripts=SqlAlchemyTranscriptRepository(db),
        profiles=SqlAlchemyProfileRepository(db),
        llm=FakeLlm(),
        corrector=_CannedCorrector(),
    )


async def _auth_header(client, email="conv@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


@pytest.mark.asyncio
async def test_turn_returns_reply_and_persists_transcript(client):
    headers = await _auth_header(client)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["reply"] == "You said: hello"

    second = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "how are you"}
    )
    assert second.status_code == 200
    assert second.json()["reply"] == "You said: how are you"


@pytest.mark.asyncio
async def test_turn_meters_quota_and_streak_on_fresh_session(client, db_session):
    """#418: POST /turn through the real DI (fresh-session meter) must advance
    quota + streak. Existing /turn tests only assert the transcript, which is
    saved BEFORE the meter and independently of it."""
    email = "meter-fresh@b.com"
    headers = await _auth_header(client, email=email)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    past = datetime.now(UTC) - timedelta(minutes=2)
    await db_session.execute(
        update(ConversationSession)
        .where(ConversationSession.id == session_id)
        .values(last_activity_at=past)
    )
    await db_session.commit()

    resp = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    user = await db_session.scalar(select(User).where(User.email == email))
    session = await db_session.get(ConversationSession, session_id)
    assert user is not None and session is not None
    assert user.minutes_used_today == pytest.approx(2.0, abs=0.2)
    assert user.current_streak == 1
    assert user.last_active_date == datetime.now(UTC).date()
    assert session.last_activity_at > past


@pytest.mark.asyncio
async def test_turn_rejected_after_session_ended(client):
    headers = await _auth_header(client, email="conv2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)

    resp = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "hi"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_concurrent_http_end_and_turn_does_not_500(client):
    # #450 / #427: HTTP-level gather of /end + /turn must not 500.
    headers = await _auth_header(client, email="end-turn-race@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    end, turn = await asyncio.gather(
        client.post(f"/sessions/{session_id}/end", headers=headers),
        client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "hello"}),
    )
    assert end.status_code == 200, end.text
    assert turn.status_code in (200, 409), turn.text


@pytest.mark.asyncio
async def test_turn_refuses_a_second_turn_while_one_is_in_flight(client, db_session):
    # #299: /turn (non-streaming) now carries the SAME per-session lock as
    # /turn/stream (#256/#229) — a turn already in flight (its lock held)
    # refuses a concurrent one with 409 instead of reading the same base
    # transcript and overwriting it.
    from sqlalchemy import select

    from app.features.auth.models import User
    from app.features.idempotency.repository import SqlAlchemyIdempotencyRepository
    from app.features.idempotency.service import IdempotencyService

    email = "inflight-turn@b.com"
    headers = await _auth_header(client, email=email)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    user_id = (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()
    lock = IdempotencyService(SqlAlchemyIdempotencyRepository(db_session))
    assert await lock.acquire_turn_lock(user_id, session_id) is True  # a turn is "in flight"

    blocked = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "two"}
    )
    assert blocked.status_code == 409, blocked.text

    # Once the in-flight turn releases, a new turn is accepted again.
    await lock.release_turn_lock(user_id, session_id)
    ok = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "three"})
    assert ok.status_code == 200, ok.text


class _GatedLlm:
    """Blocks inside complete() until released, so a test can pin the exact
    moment a request is mid-flight (past acquire_turn_lock, before persist)
    and fire a genuinely concurrent second request at a deterministic point —
    instead of racing on unpredictable real timing."""

    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        self._started = started
        self._release = release

    async def complete(self, system_prompt, history):
        self._started.set()
        await self._release.wait()
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        return f"You said: {last_user}"

    async def stream_complete(self, system_prompt, history):
        raise NotImplementedError("not exercised by this test")
        yield  # pragma: no cover - makes this an async generator


@pytest.mark.asyncio
async def test_turn_concurrent_requests_second_rejected_only_one_persists_and_meters(
    client, db_session
):
    """#299: two REALLY concurrent POST /turn (asyncio.gather, no
    Idempotency-Key) for the same session, racing on the real Postgres-backed
    IdempotencyRepository — not a manually pre-seeded lock. Before this fix,
    both would read the same base transcript; the second's save would
    overwrite the first (a lost turn) while both charged the quota."""
    headers = await _auth_header(client, email="race-turn@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    started = asyncio.Event()
    release = asyncio.Event()
    meter_calls: list[tuple[int, int]] = []

    async def _counting_meter(session_id: int, user_id: int) -> None:
        meter_calls.append((session_id, user_id))

    def _gated_service(db: AsyncSession = Depends(get_db)) -> ConversationTurnService:
        return ConversationTurnService(
            sessions=SqlAlchemySessionRepository(db),
            transcripts=SqlAlchemyTranscriptRepository(db),
            profiles=SqlAlchemyProfileRepository(db),
            llm=_GatedLlm(started, release),
            meter=_counting_meter,
        )

    app.dependency_overrides[get_conversation_turn_service] = _gated_service
    try:
        first_task = asyncio.create_task(
            client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "first"})
        )
        # Wait until the first request holds the lock and is mid-flight (blocked
        # inside the LLM call) before firing the second — deterministic overlap.
        await asyncio.wait_for(started.wait(), timeout=5)

        try:
            second = await asyncio.wait_for(
                client.post(
                    f"/sessions/{session_id}/turn", headers=headers, json={"text": "second"}
                ),
                timeout=5,
            )
        finally:
            # Always release the gate, even if the second request times out or
            # the assertion below fails — a regression that removes the lock
            # would let "second" through to the same gated LLM and hang both
            # requests forever instead of a fast, clear test failure.
            release.set()
        assert second.status_code == 409, second.text

        first = await asyncio.wait_for(first_task, timeout=5)
        assert first.status_code == 200, first.text
        assert first.json()["reply"] == "You said: first"
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)

    # Exactly one turn persisted (the second's 409 never reached the transcript —
    # no overwrite), and the quota metered exactly once (no double-charge).
    from sqlalchemy import select

    from app.features.auth.models import User

    user_id = (
        await db_session.execute(select(User.id).where(User.email == "race-turn@b.com"))
    ).scalar_one()
    transcript = await SqlAlchemyTranscriptRepository(db_session).get_by_session(session_id)
    assert transcript is not None
    assert [t["content"] for t in transcript.turns] == ["first", "You said: first"]
    assert meter_calls == [(session_id, user_id)]


@pytest.mark.asyncio
async def test_turn_stream_emits_sentence_events_and_done(client):
    headers = await _auth_header(client, email="stream@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    resp = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hello"}
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    # FakeLlm streams two sentences, then a done event.
    assert "event: chunk" in body
    assert "You said: hello." in body
    assert "Tell me more." in body
    assert "event: done" in body


@pytest.mark.asyncio
async def test_turn_stream_persists_full_reply(client):
    headers = await _auth_header(client, email="stream2@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    await client.post(f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hi"})
    # The next non-stream turn must see the streamed reply in history.
    second = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "again"}
    )
    assert second.status_code == 200


@pytest.mark.asyncio
async def test_turn_stream_refuses_a_second_turn_while_one_is_in_flight(client, db_session):
    # #229: /turn/stream has no Idempotency-Key, so a per-session lock serialises
    # turns. With a turn already in flight (its lock held), a concurrent turn is
    # refused with 409 instead of reading the same base transcript, overwriting the
    # first reply and double-charging the quota.
    from sqlalchemy import select

    from app.features.auth.models import User
    from app.features.idempotency.repository import SqlAlchemyIdempotencyRepository
    from app.features.idempotency.service import IdempotencyService

    email = "inflight-stream@b.com"
    headers = await _auth_header(client, email=email)
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    user_id = (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()
    lock = IdempotencyService(SqlAlchemyIdempotencyRepository(db_session))
    assert await lock.acquire_turn_lock(user_id, session_id) is True  # a turn is "in flight"

    blocked = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "two"}
    )
    assert blocked.status_code == 409, blocked.text

    # Once the in-flight turn releases, a new turn is accepted again.
    await lock.release_turn_lock(user_id, session_id)
    ok = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "three"}
    )
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_a_completed_stream_turn_releases_the_lock_for_the_next(client):
    # A normal stream must release the lock when it ends, or the session would be
    # wedged for every following turn. Two SEQUENTIAL streamed turns both succeed.
    headers = await _auth_header(client, email="seq-stream@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "one"}
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "two"}
    )
    assert second.status_code == 200, second.text


@pytest.mark.asyncio
async def test_turn_stream_emits_a_correction_event_after_the_reply(client):
    app.dependency_overrides[get_conversation_turn_service] = _service_with_correction
    try:
        headers = await _auth_header(client, email="correct@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers=headers,
            json={"text": "i is happy"},
        )
        assert resp.status_code == 200
        body = resp.text
        # Reply chunks, then the correction, then done — order preserved.
        assert body.index("event: chunk") < body.index("event: correction")
        assert body.index("event: correction") < body.index("event: done")
        assert "I am happy" in body
        assert "Use 'am' with 'I'." in body
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)


class _ExplodingService:
    """A turn service whose stream raises an UNEXPECTED error (not LlmProviderError),
    to prove the SSE loop still emits a typed `error` event instead of a broken
    frame that leaves the client hanging (#123). Validation passes; the failure
    happens once streaming has begun."""

    async def prepare_turn(self, session_id, user, text):
        return object()  # a validated placeholder; only streaming explodes

    async def stream_prepared(self, prepared):
        raise RuntimeError("boom")
        yield  # pragma: no cover - makes this an async generator


@pytest.mark.asyncio
async def test_turn_stream_emits_error_event_on_unexpected_failure(client):
    app.dependency_overrides[get_conversation_turn_service] = lambda: _ExplodingService()
    try:
        headers = await _auth_header(client, email="boom@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers=headers,
            json={"text": "hi"},
        )
        assert resp.status_code == 200
        # The stream degrades to a typed error event, never a silently broken frame.
        assert "event: error" in resp.text
    finally:
        app.dependency_overrides.pop(get_conversation_turn_service, None)


@pytest.mark.asyncio
async def test_turn_stream_rejects_session_not_owned(client):
    owner = await _auth_header(client, email="owner-stream@b.com")
    start = await client.post("/sessions/start", headers=owner, json={"mode": "free"})
    session_id = start.json()["session_id"]

    intruder = await _auth_header(client, email="intruder-stream@b.com")
    resp = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=intruder, json={"text": "hi"}
    )
    # A non-owner must get a clean 404 — not a 200 stream that then emits a
    # generic error (ownership is validated before the response is committed).
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_turn_stream_rejected_after_session_ended(client):
    headers = await _auth_header(client, email="ended-stream@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await client.post(f"/sessions/{session_id}/end", headers=headers)

    resp = await client.post(
        f"/sessions/{session_id}/turn/stream", headers=headers, json={"text": "hi"}
    )
    # An ended session must get a clean 409, not a committed 200 stream.
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_turn_stream_requires_auth(client):
    resp = await client.post("/sessions/1/turn/stream", json={"text": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_turn_stream_rejects_an_expired_access_token(client):
    # #281 (audit #242 coverage gap): current_user is resolved via FastAPI's
    # Depends(get_current_user) BEFORE the route body runs — there is no
    # re-check partway through streaming, so an expired token can only ever be
    # rejected up front, never mid-stream. This pins that: an already-expired
    # token gets a clean 401 (not a 500), which is what lets the mobile client's
    # postLineStream refresh-and-retry (already covered client-side) kick in —
    # it only works because the 401 arrives before any SSE byte is written.
    headers = await _auth_header(client, email="conv-expired@b.com")
    me = await client.get("/auth/me", headers=headers)
    user_id = me.json()["id"]

    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    settings = get_settings()
    expired_payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) - timedelta(minutes=1),
        "jti": "expired-test-token",
    }
    expired_token = jwt.encode(
        expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )

    resp = await client.post(
        f"/sessions/{session_id}/turn/stream",
        headers={"Authorization": f"Bearer {expired_token}"},
        json={"text": "hi"},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_turn_requires_auth(client):
    resp = await client.post("/sessions/1/turn", json={"text": "hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_turn_rejects_empty_text(client):
    headers = await _auth_header(client, email="conv3@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    resp = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_turn_is_rate_limited_per_user(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: limiter
    headers = await _auth_header(client, email="limited-turn@b.com")
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]

    first = await client.post(f"/sessions/{session_id}/turn", headers=headers, json={"text": "hi"})
    assert first.status_code == 200, first.text
    blocked = await client.post(
        f"/sessions/{session_id}/turn", headers=headers, json={"text": "again"}
    )
    assert blocked.status_code == 429


class _SpyRateLimiter:
    """Records every key .check() was called with, so a test can assert the
    EXACT string the route builds — the precise, unambiguous proof that no IP
    component leaked into it (#384), rather than an indirect behavioral
    inference."""

    def __init__(self) -> None:
        self.checked_keys: list[str] = []

    async def check(self, key: str) -> None:
        self.checked_keys.append(key)


@pytest.mark.asyncio
async def test_turn_rate_limit_key_has_no_ip_component(client):
    # #384: user_rate_limit_key() (#356) exists precisely so a paid/inf-quota
    # endpoint's bucket can't be reset by rotating the apparent IP. /turn was
    # the one paid endpoint still hand-rolling f"turn:{client_host}:user:{id}".
    spy = _SpyRateLimiter()
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: spy
    try:
        headers = await _auth_header(client, email="turn-key-noip@b.com")
        me = await client.get("/auth/me", headers=headers)
        user_id = me.json()["id"]
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn",
            headers={**headers, "X-Forwarded-For": "1.2.3.4"},
            json={"text": "hi"},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_conversation_rate_limiter, None)

    assert spy.checked_keys == [user_rate_limit_key("turn", user_id)]


@pytest.mark.asyncio
async def test_turn_stream_rate_limit_key_has_no_ip_component(client):
    spy = _SpyRateLimiter()
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: spy
    try:
        headers = await _auth_header(client, email="turn-stream-key-noip@b.com")
        me = await client.get("/auth/me", headers=headers)
        user_id = me.json()["id"]
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        resp = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers={**headers, "X-Forwarded-For": "1.2.3.4"},
            json={"text": "hi"},
        )
        assert resp.status_code == 200, resp.text
    finally:
        app.dependency_overrides.pop(get_conversation_rate_limiter, None)

    assert spy.checked_keys == [user_rate_limit_key("turn", user_id)]


@pytest.mark.asyncio
async def test_turn_rate_limit_is_not_bypassed_by_ip_rotation(client):
    """Regression (#384): before the fix, the key embedded client_host, so a
    different apparent IP per request (IP rotation, VPN, or — per #383 — a
    spoofed X-Forwarded-For) reset the bucket, defeating the limiter entirely
    on the single most expensive endpoint (LLM completion + per-sentence TTS).
    Mirrors the same regression test already applied to every other paid
    endpoint after #356 (see test_debrief_api.py et al.)."""
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: limiter
    try:
        headers = await _auth_header(client, email="turn-ip-rotate@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        first = await client.post(
            f"/sessions/{session_id}/turn",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json={"text": "hi"},
        )
        assert first.status_code == 200, first.text
        blocked = await client.post(
            f"/sessions/{session_id}/turn",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json={"text": "again"},
        )
        assert blocked.status_code == 429, blocked.text
    finally:
        app.dependency_overrides.pop(get_conversation_rate_limiter, None)


@pytest.mark.asyncio
async def test_turn_stream_rate_limit_is_not_bypassed_by_ip_rotation(client):
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_conversation_rate_limiter] = lambda: limiter
    try:
        headers = await _auth_header(client, email="turn-stream-ip-rotate@b.com")
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]

        first = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers={**headers, "X-Forwarded-For": "1.1.1.1"},
            json={"text": "hi"},
        )
        assert first.status_code == 200, first.text
        blocked = await client.post(
            f"/sessions/{session_id}/turn/stream",
            headers={**headers, "X-Forwarded-For": "2.2.2.2"},
            json={"text": "again"},
        )
        assert blocked.status_code == 429, blocked.text
    finally:
        app.dependency_overrides.pop(get_conversation_rate_limiter, None)
