"""Integration tests for voice-data export & erasure (#128, #186)."""

import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rate_limit import InMemoryRateLimiter
from app.features.analytics.models import AnalyticsEventRow
from app.features.auth.models import User
from app.features.conversation.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.conversation.models import Transcript
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.domain import VocabularyWord
from app.features.debrief.models import Debrief
from app.features.idempotency.models import IdempotencyKey
from app.features.missions.models import Mission
from app.features.profile.models import LearnerProfile
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry
from app.features.vocabulary.repository import SqlAlchemyVocabularyRepository
from app.features.vocabulary.service import VocabularyService
from app.features.voice_data.dependencies import get_voice_data_export_rate_limiter
from app.features.voice_data.repository import SqlAlchemyVoiceDataSource
from app.main import app


async def _auth(client, email="vd@b.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "s3cret!pass"})
    token = reg.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    return {"Authorization": f"Bearer {token}"}, me.json()["id"]


async def _seed_voice_data(
    client, db_session, headers, user_id, *, memory="Prefers sports topics.", stats=True
):
    """Seed the full voice-derived footprint for a user: a session, a transcript,
    vocabulary, a debrief, a review item, a compiled mission, a per-session
    analytics event, the profile memory summary, the cached turn reply (idempotency
    key), and — when `stats` — the speech-derived user fields. Enough for erasure to
    have something of every kind to clear."""
    start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
    session_id = start.json()["session_id"]
    await SqlAlchemyTranscriptRepository(db_session).save(
        session_id,
        [
            {"role": ROLE_USER, "content": "I like sports"},
            {"role": ROLE_ASSISTANT, "content": "Nice!"},
        ],
    )
    await VocabularyService(SqlAlchemyVocabularyRepository(db_session)).capture(
        user_id, session_id, [VocabularyWord(word="deployment", translation="déploiement")]
    )
    db_session.add_all(
        [
            Debrief(
                session_id=session_id,
                cefr_estimate="B1",
                summary="Good effort on the past tense.",
                errors=[{"error_type": "tense", "original": "I go", "correction": "I went"}],
            ),
            ReviewItem(
                user_id=user_id,
                error_type="tense",
                latest_correction="I went",
                status="due",
            ),
            Mission(
                user_id=user_id,
                source_type="text",
                persona="A job recruiter",
                goal="Practise an interview",
                likely_questions=["Tell me about yourself"],
                system_prompt="You are a recruiter interviewing the learner.",
            ),
            AnalyticsEventRow(
                name="session_completed",
                user_id=user_id,
                properties={"session_id": session_id, "cefr": "B1", "error_count": 2},
            ),
            IdempotencyKey(user_id=user_id, key=f"turn-{user_id}", response="cached reply"),
        ]
    )
    # merge = upsert by PK, robust whether or not a profile row already exists.
    if memory is not None:
        await db_session.merge(LearnerProfile(user_id=user_id, memory_summary=memory))
    if stats:
        # Speech-derived user fields nudged away from their onboarding defaults.
        await db_session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                cefr_level="B1",
                current_streak=3,
                longest_streak=5,
                last_active_date=date(2026, 8, 1),
            )
        )
    await db_session.commit()
    return session_id


async def _count(db_session, model, user_id):
    db_session.expire_all()
    return await db_session.scalar(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )


@pytest.mark.asyncio
async def test_export_returns_every_voice_derived_category(client, db_session):
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    resp = await client.post("/me/voice-data/export", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["raw_audio_retained"] is False  # honest: never stored
    # Only the learner's own turns are exported (not the assistant's).
    texts = [u["text"] for u in body["utterances"]]
    assert "I like sports" in texts
    assert "Nice!" not in texts
    assert body["vocabulary"][0]["word"] == "deployment"
    # The module now honours its promise to export the full footprint (#186).
    assert body["debriefs"][0]["cefr_estimate"] == "B1"
    assert body["debriefs"][0]["summary"].startswith("Good effort")
    assert body["review_items"][0]["error_type"] == "tense"


@pytest.mark.asyncio
async def test_erase_deletes_every_voice_derived_kind_and_reports_counts(client, db_session):
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    erased = await client.delete("/me/voice-data", headers=headers)
    assert erased.status_code == 200, erased.text
    deleted = erased.json()["deleted"]
    for kind in (
        "transcripts",
        "debriefs",
        "vocabulary",
        "review_items",
        "sessions",
        "missions",
        "analytics_events",
        "idempotency_keys",
    ):
        assert deleted[kind] >= 1, f"{kind} not erased: {deleted}"

    # A follow-up export is now empty across every category.
    again = (await client.post("/me/voice-data/export", headers=headers)).json()
    assert again["utterances"] == []
    assert again["vocabulary"] == []
    assert again["debriefs"] == []
    assert again["review_items"] == []

    # And the rows themselves are gone (not merely hidden by an empty join).
    assert await _count(db_session, ConversationSession, user_id) == 0
    assert await _count(db_session, Mission, user_id) == 0
    assert await _count(db_session, AnalyticsEventRow, user_id) == 0


@pytest.mark.asyncio
async def test_erase_clears_residues_on_kept_rows(client, db_session):
    """The #186 gap the adversarial sweep widened: erasure must also wipe the
    voice-derived residues that live on rows we KEEP — the profile memory summary,
    the cached turn replies, and the speech-derived user fields (CEFR + streaks)."""
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    deleted = (await client.delete("/me/voice-data", headers=headers)).json()["deleted"]
    assert deleted["memory_summary"] == 1  # there was content, so it counts honestly
    assert deleted["user_stats"] == 1  # CEFR + streaks were non-default
    assert deleted["idempotency_keys"] >= 1

    # Read fresh from the DB (identity map may hold stale copies from the seed).
    db_session.expire_all()
    memory = await db_session.scalar(
        select(LearnerProfile.memory_summary).where(LearnerProfile.user_id == user_id)
    )
    assert memory == ""  # profile row kept, but the voice-derived memory is gone
    user = await db_session.get(User, user_id)
    assert user is not None  # account kept — this is erasure, not deletion
    assert user.cefr_level == "A1"  # reset to onboarding baseline
    assert user.current_streak == 0
    assert user.longest_streak == 0
    assert user.last_active_date is None
    assert await _count(db_session, IdempotencyKey, user_id) == 0


@pytest.mark.asyncio
async def test_erase_reports_zero_when_there_was_nothing_derived_to_clear(client, db_session):
    """Honest counts: a user with an empty memory and default stats reports 0, not 1."""
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id, memory="", stats=False)

    deleted = (await client.delete("/me/voice-data", headers=headers)).json()["deleted"]
    assert deleted["memory_summary"] == 0
    assert deleted["user_stats"] == 0


@pytest.mark.asyncio
async def test_erase_only_touches_the_callers_data(client, db_session):
    headers_a, user_a = await _auth(client, email="vd-a@b.com")
    await _seed_voice_data(client, db_session, headers_a, user_a)

    headers_b, user_b = await _auth(client, email="vd-b@b.com")
    await _seed_voice_data(client, db_session, headers_b, user_b)

    # B erases -> A's data survives, entirely.
    await client.delete("/me/voice-data", headers=headers_b)
    a_export = await client.post("/me/voice-data/export", headers=headers_a)
    assert len(a_export.json()["utterances"]) >= 1

    assert await _count(db_session, ConversationSession, user_a) >= 1
    assert await _count(db_session, Mission, user_a) >= 1
    assert await _count(db_session, AnalyticsEventRow, user_a) >= 1
    assert await _count(db_session, IdempotencyKey, user_a) >= 1
    db_session.expire_all()
    a_user = await db_session.get(User, user_a)
    assert a_user.cefr_level == "B1"  # A's speech-derived level untouched
    assert a_user.current_streak == 3


@pytest.mark.asyncio
async def test_concurrent_erasure_from_same_user(client, db_session):
    """Two DELETE /me/voice-data for the SAME user in flight at once (#290
    scenario 1 — e.g. a double-tap or a client retry racing the original call)
    must not corrupt state: both requests succeed and every category ends up
    erased exactly once, with no orphaned rows left behind by the race."""
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)

    responses = await asyncio.gather(
        client.delete("/me/voice-data", headers=headers),
        client.delete("/me/voice-data", headers=headers),
    )
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]

    db_session.expire_all()
    assert await _count(db_session, ConversationSession, user_id) == 0
    assert await _count(db_session, Mission, user_id) == 0
    assert await _count(db_session, AnalyticsEventRow, user_id) == 0
    assert await _count(db_session, IdempotencyKey, user_id) == 0
    assert await _count(db_session, ReviewItem, user_id) == 0
    assert await _count(db_session, VocabularyEntry, user_id) == 0
    memory = await db_session.scalar(
        select(LearnerProfile.memory_summary).where(LearnerProfile.user_id == user_id)
    )
    assert memory == ""
    user = await db_session.get(User, user_id)
    assert user.cefr_level == "A1"
    assert user.current_streak == 0
    assert user.longest_streak == 0


@pytest.mark.asyncio
async def test_erase_is_atomic_on_partial_failure(client, db_session, _engine, monkeypatch):
    """A DB failure partway through the cascade (#290 scenario 2: transcripts
    delete succeeds, then the debriefs delete times out / the DB drops) must
    leave NOTHING committed — not a half-erased user with transcripts gone but
    analytics_events (and everything else) still present. purge() runs as one
    transaction with a single commit at the very end, and production's get_db()
    closes (= rolls back) the session on any unhandled exception, so this drives
    the SAME session lifecycle purge() actually runs under."""
    headers, user_id = await _auth(client)
    await _seed_voice_data(client, db_session, headers, user_id)
    db_session.expire_all()

    class _SimulatedOutage(Exception):
        pass

    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as purge_session:
        source = SqlAlchemyVoiceDataSource(purge_session)
        real_execute = purge_session.execute

        async def _flaky_execute(stmt, *args, **kwargs):
            # Target the debriefs delete specifically (by statement identity,
            # not by call count) so this keeps testing the issue's exact
            # scenario — transcripts succeeds, debriefs fails — even if the
            # cascade's statement order changes later.
            target = getattr(stmt, "table", None)
            if target is not None and target.name == Debrief.__tablename__:
                raise _SimulatedOutage("simulated DB outage mid-cascade")
            return await real_execute(stmt, *args, **kwargs)

        monkeypatch.setattr(purge_session, "execute", _flaky_execute)
        with pytest.raises(_SimulatedOutage):
            await source.purge(user_id)
    # pytest.raises absorbed the exception above, so this `async with` exits
    # normally rather than propagating it — but AsyncSession.close() rolls back
    # any uncommitted transaction on EITHER exit path, so this still exercises
    # the same rollback get_db() relies on when a route handler's exception
    # genuinely propagates out of it in production.

    # A fresh read must see the ENTIRE footprint untouched — exactly the one
    # row per kind _seed_voice_data created — including the transcript that
    # was "successfully" deleted before the simulated outage.
    assert await _count(db_session, ConversationSession, user_id) == 1
    assert await _count(db_session, Mission, user_id) == 1
    assert await _count(db_session, AnalyticsEventRow, user_id) == 1
    assert await _count(db_session, IdempotencyKey, user_id) == 1
    assert await _count(db_session, ReviewItem, user_id) == 1
    assert await _count(db_session, VocabularyEntry, user_id) == 1
    transcripts = await db_session.scalar(
        select(func.count())
        .select_from(Transcript)
        .join(ConversationSession, ConversationSession.id == Transcript.session_id)
        .where(ConversationSession.user_id == user_id)
    )
    assert transcripts == 1  # the "successful" first delete was rolled back too
    memory = await db_session.scalar(
        select(LearnerProfile.memory_summary).where(LearnerProfile.user_id == user_id)
    )
    assert memory != ""
    user = await db_session.get(User, user_id)
    assert user.cefr_level == "B1"  # user_stats reset never committed either


@pytest.mark.asyncio
async def test_voice_data_requires_auth(client):
    assert (await client.post("/me/voice-data/export")).status_code == 401
    assert (await client.delete("/me/voice-data")).status_code == 401


@pytest.mark.asyncio
async def test_export_streams_the_full_history_without_truncation(client, db_session):
    """#365: the export is now streamed off a server-side cursor instead of
    materialized in one query — a learner with a sizeable history must still
    get EVERY row back, not a silently truncated page. 6 sessions x 5 learner
    turns = 30 utterances, well past what any single default page size would
    return if truncation had crept back in."""
    headers, user_id = await _auth(client, email="vd-big@b.com")
    session_count, turns_per_session = 6, 5
    expected_texts = set()
    for s in range(session_count):
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]
        transcript = []
        for t in range(turns_per_session):
            text = f"session {s} turn {t}"
            transcript.append({"role": ROLE_ASSISTANT, "content": "?"})
            transcript.append({"role": ROLE_USER, "content": text})
            expected_texts.add(text)
        await SqlAlchemyTranscriptRepository(db_session).save(session_id, transcript)
        await client.post(f"/sessions/{session_id}/end", headers=headers)
    await db_session.commit()

    resp = await client.post("/me/voice-data/export", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["utterances"]) == session_count * turns_per_session
    assert {u["text"] for u in body["utterances"]} == expected_texts


@pytest.mark.asyncio
async def test_export_is_rate_limited(client):
    """#365: the export endpoint now has a dedicated limiter — repeated calls
    (the 'repetable sans throttle' half of the DoW-by-memory scenario) must be
    capped even though each individual call is now memory-bounded."""
    limiter = InMemoryRateLimiter(max_hits=1, window_seconds=60)
    app.dependency_overrides[get_voice_data_export_rate_limiter] = lambda: limiter
    try:
        headers, _ = await _auth(client, email="vd-rl@b.com")
        first = await client.post("/me/voice-data/export", headers=headers)
        assert first.status_code == 200, first.text
        second = await client.post("/me/voice-data/export", headers=headers)
        assert second.status_code == 429, second.text
    finally:
        app.dependency_overrides.pop(get_voice_data_export_rate_limiter, None)
