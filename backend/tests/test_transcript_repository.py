import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.features.auth.models import User
from app.features.conversation.repository import SqlAlchemyTranscriptRepository
from app.features.sessions.models import ConversationSession


async def _make_session(db) -> int:
    user = User(email="t@b.com", hashed_password="x", native_language="fr")
    db.add(user)
    await db.flush()
    convo = ConversationSession(user_id=user.id, mode="free")
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo.id


@pytest.mark.asyncio
async def test_save_then_get_roundtrips_turns(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyTranscriptRepository(db_session)

    turns = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    await repo.save(session_id, turns)

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.turns == turns


@pytest.mark.asyncio
async def test_save_is_idempotent_per_session(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyTranscriptRepository(db_session)

    await repo.save(session_id, [{"role": "user", "content": "first"}])
    await repo.save(session_id, [{"role": "user", "content": "second"}])

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.turns == [{"role": "user", "content": "second"}]


@pytest.mark.asyncio
async def test_concurrent_first_saves_for_the_same_new_session_do_not_race(
    _engine, _setup_db, db_session
):
    # #364: save() used to SELECT-then-branch (INSERT if absent, else UPDATE).
    # Two concurrent first saves for the SAME session (a client retry racing the
    # original, before any row exists yet) could both see "no row" and both
    # attempt an INSERT — the second failing on the session_id UNIQUE
    # constraint. The rewrite to an atomic upsert (ON CONFLICT DO UPDATE) closes
    # that race at the database level: this must NOT raise, regardless of which
    # write ends up winning. Each save runs on its OWN connection/session (a
    # single AsyncSession cannot run two operations concurrently), mirroring how
    # two real concurrent requests would each get their own.
    session_id = await _make_session(db_session)
    maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async def _save(turns: list[dict]) -> None:
        async with maker() as session:
            await SqlAlchemyTranscriptRepository(session).save(session_id, turns)

    turns_a = [{"role": "user", "content": "a"}]
    turns_b = [{"role": "user", "content": "b"}]
    await asyncio.gather(_save(turns_a), _save(turns_b))  # must not raise

    repo = SqlAlchemyTranscriptRepository(db_session)
    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    # Whichever write actually landed last, exactly one of them did — never a
    # crash and never a merged/corrupted value.
    assert fetched.turns in (turns_a, turns_b)
