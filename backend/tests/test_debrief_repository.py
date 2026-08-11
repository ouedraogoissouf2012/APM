import pytest

from app.features.auth.models import User
from app.features.debrief.repository import SqlAlchemyDebriefRepository
from app.features.sessions.models import ConversationSession


async def _make_session(db) -> int:
    user = User(email="d@b.com", hashed_password="x", native_language="fr")
    db.add(user)
    await db.flush()
    convo = ConversationSession(user_id=user.id, mode="free")
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo.id


@pytest.mark.asyncio
async def test_save_then_get_roundtrips(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyDebriefRepository(db_session)
    errors = [
        {"original": "i go", "correction": "I go", "rule": "Capital I", "error_type": "spelling"}
    ]

    await repo.save(session_id, "A2", "nice", errors)

    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.cefr_estimate == "A2"
    assert fetched.errors == errors


@pytest.mark.asyncio
async def test_save_is_idempotent_per_session(db_session):
    session_id = await _make_session(db_session)
    repo = SqlAlchemyDebriefRepository(db_session)
    await repo.save(session_id, "A2", "first", [])
    await repo.save(session_id, "B1", "second", [])
    fetched = await repo.get_by_session(session_id)
    assert fetched is not None
    assert fetched.cefr_estimate == "B1"
    assert fetched.summary == "second"
