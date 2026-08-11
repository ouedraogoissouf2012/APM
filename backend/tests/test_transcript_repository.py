import pytest

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
