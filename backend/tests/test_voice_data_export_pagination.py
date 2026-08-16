"""Tests for the #389 fix: POST /me/voice-data/export must not pin a pooled
connection (+ open server-side cursor/transaction) for the whole client-paced
download. Each page now opens/closes its OWN short-lived session — these tests
measure the pool directly (not intuition) to prove the connection is released
between pages, and that keyset pagination covers every row exactly once.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.llm.messages import ROLE_ASSISTANT, ROLE_USER
from app.features.auth.models import User
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.review.models import ReviewItem
from app.features.sessions.models import ConversationSession
from app.features.vocabulary.models import VocabularyEntry
from app.features.voice_data import repository as voice_data_repository
from app.features.voice_data.repository import VoiceDataExportRepository


async def _user(db_session, email="vd-page@b.com") -> User:
    user = User(email=email, hashed_password="x", native_language="fr")
    db_session.add(user)
    await db_session.flush()
    return user


async def _session_with_turns(db_session, user_id, *, started_at, texts):
    session = ConversationSession(
        user_id=user_id, mode="free", started_at=started_at, ended_at=started_at
    )
    db_session.add(session)
    await db_session.flush()
    turns = []
    for text in texts:
        turns.append({"role": ROLE_ASSISTANT, "content": "?"})
        turns.append({"role": ROLE_USER, "content": text})
    await SqlAlchemyTranscriptRepository(db_session).save(session.id, turns)
    return session.id


@pytest.mark.asyncio
async def test_pagination_releases_the_pooled_connection_between_pages(
    db_session, _engine, monkeypatch
):
    """The core #389 claim, measured directly against the real pool: while the
    caller is consuming rows (i.e. control is back with US, standing in for the
    client reading HTTP bytes), the connection used to fetch the page that
    produced those rows must already be checked back in — not held open for
    the whole iteration."""
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 2)
    user = await _user(db_session)
    now = datetime.now(UTC)
    for i in range(5):
        await _session_with_turns(
            db_session, user.id, started_at=now + timedelta(seconds=i), texts=[f"turn {i}"]
        )
    await db_session.commit()

    sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    checkouts_while_consuming = []
    async for _item in VoiceDataExportRepository(sessionmaker).stream_utterances(user.id):
        # Measured the instant control returns to the consumer — i.e. AFTER
        # whichever page produced this item has already closed its session.
        checkouts_while_consuming.append(_engine.pool.checkedout())

    assert len(checkouts_while_consuming) == 5  # 5 utterances, 3 pages (2+2+1)
    assert all(n == 0 for n in checkouts_while_consuming), checkouts_while_consuming
    # And after full consumption, the pool is back to its resting state too.
    assert _engine.pool.checkedout() == 0


@pytest.mark.asyncio
async def test_utterances_keyset_pagination_covers_every_row_exactly_once_in_order(
    db_session, _engine, monkeypatch
):
    """Composite (started_at, session_id) keyset cursor: 7 sessions, page size 3
    -> 3 pages (3+3+1), forcing 2 page boundaries. Every utterance must appear
    exactly once, in the original started_at order — no row skipped or
    duplicated at a boundary."""
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 3)
    user = await _user(db_session, email="vd-page-utt@b.com")
    now = datetime.now(UTC)
    for i in range(7):
        await _session_with_turns(
            db_session, user.id, started_at=now + timedelta(seconds=i), texts=[f"turn {i}"]
        )
    await db_session.commit()

    sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    texts = [
        item["text"]
        async for item in VoiceDataExportRepository(sessionmaker).stream_utterances(user.id)
    ]

    assert texts == [f"turn {i}" for i in range(7)]  # exact order, no dup/skip


@pytest.mark.asyncio
async def test_vocabulary_keyset_pagination_covers_every_row_exactly_once(
    db_session, _engine, monkeypatch
):
    """Single-column (id) keyset cursor, 10 rows, page size 3 -> 4 pages
    (3+3+3+1)."""
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 3)
    user = await _user(db_session, email="vd-page-vocab@b.com")
    for i in range(10):
        db_session.add(VocabularyEntry(user_id=user.id, word=f"word{i}", translation=f"t{i}"))
    await db_session.commit()

    sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    words = [
        item["word"]
        async for item in VoiceDataExportRepository(sessionmaker).stream_vocabulary(user.id)
    ]

    assert sorted(words) == sorted(f"word{i}" for i in range(10))
    assert len(words) == len(set(words))  # no duplicates at a page boundary


@pytest.mark.asyncio
async def test_review_items_keyset_pagination_covers_every_row_exactly_once(
    db_session, _engine, monkeypatch
):
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 3)
    user = await _user(db_session, email="vd-page-review@b.com")
    for i in range(8):
        db_session.add(ReviewItem(user_id=user.id, error_type=f"type{i}", latest_correction="c"))
    await db_session.commit()

    sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    types = [
        item["error_type"]
        async for item in VoiceDataExportRepository(sessionmaker).stream_review_items(user.id)
    ]

    assert sorted(types) == sorted(f"type{i}" for i in range(8))
    assert len(types) == len(set(types))


@pytest.mark.asyncio
async def test_debriefs_keyset_pagination_covers_every_row_exactly_once_in_order(
    db_session, _engine, monkeypatch
):
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 2)
    user = await _user(db_session, email="vd-page-debrief@b.com")
    now = datetime.now(UTC)
    for i in range(5):
        session = ConversationSession(
            user_id=user.id,
            mode="free",
            started_at=now + timedelta(seconds=i),
            ended_at=now + timedelta(seconds=i),
        )
        )
        db_session.add(session)
        await db_session.flush()
        await SqlAlchemyDebriefRepository(db_session).save(session.id, "B1", f"summary {i}", [])
    await db_session.commit()

    sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    summaries = [
        item["summary"]
        async for item in VoiceDataExportRepository(sessionmaker).stream_debriefs(user.id)
    ]

    assert summaries == [f"summary {i}" for i in range(5)]


@pytest.mark.asyncio
async def test_export_endpoint_is_complete_across_multiple_pages(client, db_session, monkeypatch):
    """End-to-end: with a tiny page size forcing several page round-trips, the
    HTTP response must still contain EVERY utterance — proving the endpoint
    itself (not just the internal generator) is correct across page boundaries."""
    monkeypatch.setattr(voice_data_repository, "_EXPORT_PAGE_SIZE", 2)
    reg = await client.post(
        "/auth/register", json={"email": "vd-page-http@b.com", "password": "s3cret!pass"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    expected_texts = set()
    for i in range(5):
        start = await client.post("/sessions/start", headers=headers, json={"mode": "free"})
        session_id = start.json()["session_id"]
        text = f"session {i}"
        expected_texts.add(text)
        await SqlAlchemyTranscriptRepository(db_session).save(
            session_id,
            [{"role": ROLE_ASSISTANT, "content": "?"}, {"role": ROLE_USER, "content": text}],
        )
        await client.post(f"/sessions/{session_id}/end", headers=headers)
    await db_session.commit()

    resp = await client.post("/me/voice-data/export", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["raw_audio_retained"] is False
    assert {u["text"] for u in body["utterances"]} == expected_texts
